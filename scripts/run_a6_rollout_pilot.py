"""Paired base/immediate/short-rollout inference with auditable resource costs.

This pilot evaluates algorithms, not a capacity or training claim. All arms
use the same model, initial states, terminal potential and number of designs.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.core.codon import feasible_edit, protein_of_cds
from codonflow.data.dataset import read_fasta
from codonflow.eval.metrics import (
    cai, cai_weights_from_rscu, hypervolume, pairwise_ned,
)
from codonflow.core.motifs import motif_penalty_score
from codonflow.gating.atc import ATCUtility
from codonflow.models.batched_sampler import BatchedReward
from codonflow.models.guided_sampler import synonymous_x0
from codonflow.models.synonymous_markov import (
    FiniteStepSynonymousMarkovEditor, SynonymousJumpProposal,
)
from codonflow.train.rloo_finetune import load_model
from codonflow.train.run_pretrain import file_sha256, git_commit
from scripts.recompute_s3_full_adaptive import joint_range_reference


TRACE_COST_FIELDS = (
    "forward_calls",
    "base_state_evaluations",
    "rollout_batch_forwards",
    "rollout_trajectories",
    "rollout_state_transitions",
    "terminal_reward_evaluations",
)


def aggregate_trace_costs(traces):
    """Sum final per-path counters without recounting cumulative trace rows."""
    if not traces or any(not trace for trace in traces):
        raise ValueError("cost aggregation requires nonempty path traces")
    final_rows = [trace[-1] for trace in traces]
    missing = [key for key in TRACE_COST_FIELDS if any(key not in row for row in final_rows)]
    if missing:
        raise ValueError(f"trace is missing cost fields: {missing}")
    costs = {key: sum(int(row[key]) for row in final_rows) for key in TRACE_COST_FIELDS}
    if costs["forward_calls"] != (
        costs["base_state_evaluations"] + costs["rollout_batch_forwards"]
    ):
        raise ValueError("model forward accounting is inconsistent")
    return costs


def summarize_arms(output):
    points = np.unique(np.asarray([
        point for arm in output["arms"].values() for point in arm["objectives"]
    ]), axis=0)
    reference, scale = joint_range_reference(points, allow_degenerate=True)
    output["normalization_scale"] = scale.tolist()
    output["degenerate_axes_use_unit_scale"] = True
    output["reference_protocol"] = "joint_all_arms_min_minus_5pct_range_normalized_v2"
    for arm in output["arms"].values():
        arm["reference"] = reference.tolist()
        normalized = (np.asarray(arm["objectives"]) - reference) / scale
        arm["hypervolume_joint_reference"] = hypervolume(normalized.tolist(), np.zeros(4))
    return {name: arm["hypervolume_joint_reference"] for name, arm in output["arms"].items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--atc-yaml", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--n-solutions", type=int, default=8)
    parser.add_argument("--terminal-step", type=int, default=4)
    parser.add_argument("--candidate-count", type=int, default=8)
    parser.add_argument("--rollout-count", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--beta", type=float, default=1.0)
    args = parser.parse_args()
    if args.n_solutions < 1 or args.rollout_count < 0:
        raise ValueError("n-solutions >= 1 and rollout-count >= 0 required")
    if args.terminal_step < 1 or args.candidate_count < 1:
        raise ValueError("terminal-step and candidate-count must be positive")
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("GPU required; silent CPU fallback forbidden")
    torch.manual_seed(args.seed)
    model = load_model(args.checkpoint, device)
    proposal = SynonymousJumpProposal(model, device)
    weights = cai_weights_from_rscu(json.loads(Path(args.rscu_json).read_text()))
    atc = ATCUtility.from_yaml(args.atc_yaml)
    sources = [(h.split()[0], s) for h, s in read_fasta(args.benchmark_fasta)]
    if len(sources) != 1:
        raise ValueError("pilot requires exactly one source CDS")
    name, source = sources[0]
    protein = protein_of_cds(source)
    initial_states = [
        synonymous_x0(source, np.random.default_rng(args.seed * 1009 + i))
        for i in range(args.n_solutions)
    ]
    output = {
        "config": vars(args), "source": name,
        "initial_states": initial_states,
        "checkpoint_sha256": file_sha256(args.checkpoint),
        "benchmark_sha256": file_sha256(args.benchmark_fasta),
        "rscu_sha256": file_sha256(args.rscu_json),
        "atc_sha256": file_sha256(args.atc_yaml),
        "code_commit": git_commit(),
        "protocol": "paired_same_initial_states_v4", "arms": {},
        "cost_accounting": {
            "forward_calls": "All model forwards: current-state base evaluations plus rollout batch forwards.",
            "base_state_evaluations": "Unbatched current-state base-kernel enumerations along sampled paths; excludes rollout states.",
            "rollout_batch_forwards": "Batched base-kernel forwards during value rollouts; R trajectories at one time share one call.",
            "rollout_trajectories": "Terminal rollout trajectories initiated; a trajectory count, not a model-forward count.",
            "rollout_state_transitions": "Sum of rollout batch sizes, i.e. individual simulated base-kernel transitions.",
            "terminal_reward_evaluations": "Terminal log-G requests before per-path cache deduplication; read from final cumulative trace rows.",
            "terminal_scorer_invocations": "Sequence scores actually computed after per-path cache deduplication, including cross-path repeats.",
            "unique_terminal_reward_calls": "Unique sequences submitted to the terminal scorer at least once across the arm.",
            "short_rollout_forward_formula": "For constant C and R>0: F=T+T(T+1)/2+C*T(T-1)/2; first step=1+T+C*(T-1); independent of R.",
            "formula_scope": "Actual trace counters are authoritative when candidate counts vary or paths are truncated.",
        },
    }
    for mode, rollouts in (("base", None), ("immediate", 0), ("short_rollout", args.rollout_count)):
        solutions, traces, scored_sequences = [], [], set()
        terminal_scorer_invocations = 0
        proposal.forward_calls = 0
        mfe_cache = {}
        base_terminal = BatchedReward(weights, atc, mfe_cache, skip_mfe=atc.omega[1] == 0)
        def terminal(seqs):
            nonlocal terminal_scorer_invocations
            terminal_scorer_invocations += len(seqs)
            scored_sequences.update(seqs)
            return [args.beta * value for value in base_terminal(seqs)]
        t0 = time.perf_counter()
        for index, initial in enumerate(initial_states):
            editor = FiniteStepSynonymousMarkovEditor(
                proposal, terminal, terminal_step=args.terminal_step,
                rollout_count=0 if rollouts is None else rollouts, candidate_count=args.candidate_count,
                rng=np.random.default_rng(args.seed * 101 + index),
                sampling_kernel="base" if mode == "base" else "guided",
            )
            terminal_seq, trace = editor.sample(initial)
            solutions.append(terminal_seq)
            traces.append(trace)
        elapsed = time.perf_counter() - t0
        path_costs = aggregate_trace_costs(traces)
        path_scorer_invocations = sum(
            trace[-1]["unique_terminal_reward_calls"] for trace in traces
        )
        if path_costs["forward_calls"] != proposal.forward_calls:
            raise RuntimeError("proposal and per-path forward accounting differ")
        if terminal_scorer_invocations != path_scorer_invocations:
            raise RuntimeError("terminal scorer and per-path accounting differ")
        objectives = [[
            cai(seq, weights),
            -mfe_cache[seq],
            -abs((seq.count("G") + seq.count("C")) / len(seq) - atc.gc_target),
            -motif_penalty_score(seq),
        ] for seq in solutions]
        output["arms"][mode] = {
            "n_solutions": len(solutions),
            "n_unique": len(set(solutions)),
            "identity_rate": float(np.mean([feasible_edit(s, source) for s in solutions])),
            "ned": pairwise_ned(solutions),
            "hypervolume_joint_reference": None,
            "reference": None,
            "objectives": objectives,
            "solutions": solutions,
            "elapsed_s": elapsed,
            **path_costs,
            "unique_terminal_reward_calls": len(scored_sequences),
            "terminal_scorer_invocations": terminal_scorer_invocations,
            "new_terminal_scores_per_path": [trace[-1]["unique_terminal_reward_calls"] for trace in traces],
            "traces": traces,
        }
    summarize_arms(output)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(output, indent=2))
    print(json.dumps({mode: {k: v for k, v in arm.items() if k not in ("traces", "solutions", "objectives")}
                      for mode, arm in output["arms"].items()}, indent=2))


if __name__ == "__main__":
    main()
