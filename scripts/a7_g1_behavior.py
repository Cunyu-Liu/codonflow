"""Evaluate G1 convergence-era non-degeneracy on a frozen CUDA checkpoint."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.core.codon import SYNONYMOUS_CODONS, STANDARD_TABLE_1, feasible_edit, split_codons
from codonflow.data.dataset import read_fasta
from codonflow.eval.metrics import cai, cai_weights_from_rscu, gc_fraction
from codonflow.models.edit_flow import EditFlowConfig, EditFlowTransformer
from codonflow.models.guided_sampler import synonymous_x0
from codonflow.models.synonymous_markov import FiniteStepSynonymousMarkovEditor, SynonymousJumpProposal
from codonflow.train.run_pretrain import file_sha256, git_commit


def behavior_metrics(source, sequences, uniform_sequences):
    if not sequences:
        return {"identity_legal": 0.0, "non_source_rate": 0.0, "n_unique": 0,
                "max_single_frequency": 1.0, "uniform_exact_overlap": 0}
    counts = Counter(sequences)
    return {
        "identity_legal": float(np.mean([feasible_edit(sequence, source) for sequence in sequences])),
        "non_source_rate": float(np.mean([sequence != source for sequence in sequences])),
        "n_unique": len(counts),
        "max_single_frequency": max(counts.values()) / len(sequences),
        "uniform_exact_overlap": len(set(sequences) & set(uniform_sequences)),
    }


def passes_g1(row, n_samples=100):
    return bool(row["identity_legal"] == 1.0 and row["non_source_rate"] >= 0.95
                and row["n_unique"] >= 80 and row["max_single_frequency"] <= 0.20)


def uniform_path(source, terminal_step, rng):
    codons = split_codons(source)
    for _ in range(terminal_step):
        position = int(rng.integers(len(codons)))
        alternatives = SYNONYMOUS_CODONS[STANDARD_TABLE_1[codons[position]]]
        codons[position] = str(rng.choice(alternatives))
    return "".join(codons)


def evaluate_gene(source, proposal, seed, n_samples, terminal_step, reward_profiles):
    outputs, uniform_outputs = [], []
    sampled_positions = set()
    edit_indicators = []
    for index in range(n_samples):
        initial = synonymous_x0(source, np.random.default_rng(seed * 1009 + index))
        editor = FiniteStepSynonymousMarkovEditor(
            proposal, lambda sequences: [0.0] * len(sequences), terminal_step,
            rollout_count=0, rng=np.random.default_rng(seed * 7919 + index), sampling_kernel="base",
        )
        output, trace = editor.sample(initial)
        outputs.append(output)
        positions = [step["position"] for step in trace if step["position"] is not None]
        sampled_positions.update(positions)
        edit_indicators.append(bool(positions))
        uniform_outputs.append(uniform_path(initial, terminal_step, np.random.default_rng(seed * 1009 + index)))
    row = behavior_metrics(source, outputs, uniform_outputs)
    transitions = proposal.enumerate_transitions(split_codons(source))
    row["stay_p"] = float(np.exp([t.log_probability for t in transitions if t.is_stay][0]))
    row["p_edit"] = float(np.mean(edit_indicators))
    row["position_coverage"] = len(sampled_positions) / (len(split_codons(source)) - 1)
    response = {}
    for name, objective in reward_profiles.items():
        scores = []
        for index in range(min(10, n_samples)):
            initial = synonymous_x0(source, np.random.default_rng(seed * 1009 + index))
            editor = FiniteStepSynonymousMarkovEditor(
                proposal, lambda sequences: [objective(sequence) for sequence in sequences],
                terminal_step, rollout_count=0, candidate_count=4,
                rng=np.random.default_rng(seed * 7919 + index), sampling_kernel="guided",
            )
            output, _trace = editor.sample(initial)
            scores.append(objective(output))
        response[name] = {"mean_objective": float(np.mean(scores)), "outputs": scores}
    distinct = len({tuple(response[name]["outputs"]) for name in response})
    row["reward_response"] = {"profiles": response, "n_distinct_profile_outcomes": distinct}
    row["passed"] = passes_g1(row, n_samples)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-samples", type=int, default=100)
    parser.add_argument("--terminal-step", type=int, default=4)
    args = parser.parse_args()
    if args.n_samples < 100:
        raise ValueError("G1 requires at least 100 paired samples per gene")
    if file_sha256(args.checkpoint) != args.checkpoint_sha256:
        raise ValueError("checkpoint hash mismatch")
    if not torch.cuda.is_available():
        raise RuntimeError("G1 requires CUDA; CPU fallback forbidden")
    device = torch.device("cuda:0")
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    model = EditFlowTransformer(EditFlowConfig(d_model=768, n_layers=8, n_heads=12, dropout=0.0))
    model.load_state_dict(state)
    proposal = SynonymousJumpProposal(model, device)
    weights = cai_weights_from_rscu(json.loads(Path(args.rscu_json).read_text()))
    reward_profiles = {
        "cai": lambda sequence: cai(sequence, weights),
        "gc": lambda sequence: -abs(gc_fraction(sequence) - 0.55),
    }
    records = [(header.split()[0], sequence) for header, sequence in read_fasta(args.benchmark_fasta)]
    if len(records) < 3:
        raise ValueError("G1 requires at least three development genes")
    rows = []
    for record_id, source in records:
        print(json.dumps({"record_id": record_id, "status": "running"}), flush=True)
        row = evaluate_gene(source, proposal, args.seed, args.n_samples, args.terminal_step, reward_profiles)
        row.update({"record_id": record_id, "source_sha256": hashlib.sha256(source.encode()).hexdigest()})
        rows.append(row)
    result = {
        "protocol": "a7_g1_behavior_v1",
        "passed": len(rows) >= 3 and all(row["passed"] for row in rows),
        "checkpoint_path": args.checkpoint,
        "checkpoint_sha256": args.checkpoint_sha256,
        "benchmark_sha256": file_sha256(args.benchmark_fasta),
        "rscu_sha256": file_sha256(args.rscu_json),
        "code_commit": git_commit(),
        "device": str(device),
        "seed": args.seed,
        "n_samples": args.n_samples,
        "terminal_step": args.terminal_step,
        "records": rows,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(out.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(out)
    print(json.dumps({"out": str(out), "passed": result["passed"]}))


if __name__ == "__main__":
    main()
