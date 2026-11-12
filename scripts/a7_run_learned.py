"""Run the learned base proposal on paired warm starts with a fixed scorer budget."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.core.codon import feasible_edit, gc_fraction, split_codons
from codonflow.core.motifs import motif_penalty_score
from codonflow.data.dataset import read_fasta
from codonflow.eval.anytime import FrozenReference, anytime_curve
from codonflow.eval.metrics import cai, cai_weights_from_rscu, mfe, pairwise_ned
from codonflow.eval.protocol import validate_result_payload
from codonflow.models.guided_sampler import synonymous_x0
from codonflow.models.simple_search import UniqueObjectiveScorer
from codonflow.train.run_pretrain import file_sha256, git_commit
from scripts.a7_run_simple_search import code_dirty, completed_result


def learned_search(initial, proposal, objective_fn, weights, normalization, seed,
                   terminal_step=4, max_unique_scorer=500, path_batch_size=32):
    if path_batch_size < 1:
        raise ValueError("path_batch_size must be positive")
    scorer = UniqueObjectiveScorer(objective_fn)
    started = time.perf_counter()
    points = []

    def record(sequence):
        values = scorer(sequence)
        if len(scorer.cache) == len(points):
            return
        points.append({"budget": len(points) + 1, "sequence": sequence,
                       "objectives": list(values)})

    record(initial)
    forwards_at_start = proposal.forward_calls
    attempts = 0
    max_attempts = max(1000, 50 * max_unique_scorer)
    while len(points) < max_unique_scorer and attempts < max_attempts:
        count = min(path_batch_size, max_unique_scorer - len(points), max_attempts - attempts)
        states = [split_codons(initial) for _ in range(count)]
        rng = np.random.default_rng(seed * 7919 + attempts)
        for step in range(terminal_step):
            states = [transition.codons for transition in proposal.sample_transition_batch(
                states, step, rng,
            )]
        for state in states:
            record("".join(state))
        attempts += count
    return {
        "protocol": "a7_learned_base_v1",
        "method": "learned",
        "status": "done" if len(points) == max_unique_scorer else "max_attempts_exhausted",
        "source_sha256": hashlib.sha256(initial.encode()).hexdigest(),
        "points": points,
        "n_unique": len(points),
        "costs": {
            "forward_calls": proposal.forward_calls - forwards_at_start,
            "base_state_evaluations": attempts * terminal_step,
            "rollout_batch_forwards": 0,
            "rollout_state_transitions": 0,
            "generator_calls": attempts,
            "terminal_reward_evaluations": scorer.terminal_evaluations,
            "unique_terminal_reward_calls": len(points),
            "elapsed_s": time.perf_counter() - started,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--calibration-dir", required=True)
    parser.add_argument("--data-split-sha256", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--record-id", action="append", dest="record_ids")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--terminal-step", type=int, default=4)
    parser.add_argument("--path-batch-size", type=int, default=32)
    parser.add_argument("--max-unique-scorer", type=int, default=500)
    parser.add_argument("--gc-target", type=float, default=0.55)
    parser.add_argument("--weights", nargs="+", type=float, default=[1, 1, 1, 0.5])
    args = parser.parse_args()
    if len(args.weights) != 4:
        raise ValueError("exactly four objective weights are required")
    if args.max_unique_scorer < 500:
        raise ValueError("G2 requires at least 500 unique terminal scorer calls")
    if file_sha256(args.checkpoint) != args.checkpoint_sha256:
        raise ValueError("checkpoint hash mismatch")
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("G2 learned evaluation requires CUDA; CPU fallback forbidden")
    from codonflow.models.edit_flow import EditFlowConfig, EditFlowTransformer
    from codonflow.models.synonymous_markov import SynonymousJumpProposal
    device = torch.device("cuda:0")
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    model = EditFlowTransformer(EditFlowConfig(d_model=768, n_layers=8, n_heads=12, dropout=0.0))
    model.load_state_dict(state)
    proposal = SynonymousJumpProposal(model, device)
    if not next(model.parameters()).is_cuda:
        raise RuntimeError("model parameters are not on CUDA")
    weights = cai_weights_from_rscu(json.loads(Path(args.rscu_json).read_text()))
    records = [(header.split()[0], sequence) for header, sequence in read_fasta(args.benchmark_fasta)]
    if args.record_ids:
        selected = set(args.record_ids)
        if selected - {record_id for record_id, _sequence in records}:
            raise ValueError("unknown record-id")
        records = [row for row in records if row[0] in selected]
    if not records:
        raise ValueError("no records selected")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def objectives(sequence):
        return [cai(sequence, weights), -mfe(sequence),
                -abs(gc_fraction(sequence) - args.gc_target),
                -motif_penalty_score(sequence) / len(split_codons(sequence))]

    for header, source in records:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", header)
        calibration_path = Path(args.calibration_dir) / f"{safe}.json"
        calibration = json.loads(calibration_path.read_text())
        if calibration["source_sha256"] != hashlib.sha256(source.encode()).hexdigest():
            raise ValueError(f"calibration source mismatch: {header}")
        frozen = FrozenReference.from_dict(calibration)
        initial = synonymous_x0(source, np.random.default_rng(args.seed * 1009))
        out_path = out_dir / f"{safe}_learned_s{args.seed}.json"
        if out_path.exists():
            if not args.resume:
                raise FileExistsError(f"refusing to overwrite result: {out_path}")
            completed_result(out_path, {
                "record_id": header, "seed": args.seed, "method": "learned",
                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "initial_sha256": hashlib.sha256(initial.encode()).hexdigest(),
                "calibration_sha256": file_sha256(str(calibration_path)),
                "rscu_sha256": file_sha256(args.rscu_json),
                "checkpoint_sha256": args.checkpoint_sha256, "code_commit": git_commit(),
            })
            print(json.dumps({"record_id": header, "method": "learned", "status": "skipped_existing"}), flush=True)
            continue
        payload = learned_search(initial, proposal, objectives, args.weights,
                                 (frozen.reference, frozen.scale), args.seed,
                                 args.terminal_step, args.max_unique_scorer, args.path_batch_size)
        payload["path_batch_size"] = args.path_batch_size
        payload["status"] = "done" if payload["status"] == "done" else "partial"
        payload["incomplete_reason"] = None if payload["status"] == "done" else "max_attempts_exhausted"
        sequences = [point["sequence"] for point in payload["points"]]
        payload.update({
            "protocol_version": "a7_evaluation_v1",
            "run_id": f"a7_{safe}_learned_s{args.seed}",
            "record_id": header,
            "seed": args.seed,
            "initial_sha256": hashlib.sha256(initial.encode()).hexdigest(),
            "initial_index": 0,
            "terminal_step": args.terminal_step,
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "benchmark_sha256": file_sha256(args.benchmark_fasta),
            "data_split_sha256": args.data_split_sha256,
            "code_commit": git_commit(),
            "code_dirty": code_dirty(),
            "checkpoint_path": args.checkpoint,
            "checkpoint_sha256": args.checkpoint_sha256,
            "rscu_sha256": file_sha256(args.rscu_json),
            "calibration_sha256": file_sha256(str(calibration_path)),
            "anytime": anytime_curve(payload["points"], frozen),
            "identity_rate": float(np.mean([feasible_edit(sequence, source) for sequence in sequences])),
            "ned": pairwise_ned(sequences),
            "missing_methods": [],
            "exclusions": [],
            "device": str(device),
        })
        validate_result_payload(payload)
        out_path = out_dir / f"{safe}_learned_s{args.seed}.json"
        temporary = out_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2))
        temporary.replace(out_path)
        print(json.dumps({"record_id": header, "method": "learned", "seed": args.seed,
                          "status": payload["status"], "auc": payload["anytime"]["auc"]}), flush=True)


if __name__ == "__main__":
    main()
