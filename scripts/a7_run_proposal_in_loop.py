"""Evaluate a learned T=1 proposal inside the frozen hill-climbing optimizer."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
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
from codonflow.models.simple_search import SimpleSearch
from codonflow.train.run_pretrain import file_sha256, git_commit
from scripts.a7_provenance import resolve_accepted_code_commits
from scripts.a7_run_simple_search import code_dirty, completed_result


def validate_baseline(path, expected):
    payload = completed_result(path, expected)
    sequences = [point["sequence"] for point in payload["points"]]
    if len(sequences) != 500 or len(set(sequences)) != 500 or payload["identity_rate"] != 1.0:
        raise ValueError(f"baseline does not contain 500 unique legal solutions: {path}")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--baseline-dir", required=True)
    parser.add_argument("--baseline-code-commit", action="append", required=True)
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--calibration-dir", required=True)
    parser.add_argument("--data-split-sha256", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--record-id", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--max-unique-scorer", type=int, default=500)
    parser.add_argument("--gc-target", type=float, default=0.55)
    parser.add_argument("--weights", nargs="+", type=float, default=[1, 1, 1, 0.5])
    parser.add_argument("--accept-code-commit", action="append", default=[])
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if len(args.weights) != 4 or args.max_unique_scorer != 500:
        raise ValueError("diagnostic requires four weights and exactly 500 unique scorer calls")
    if not str(Path(args.out_dir).resolve()).startswith("/teams/"):
        raise ValueError("diagnostic outputs must remain on /teams")
    accepted_code_commits = resolve_accepted_code_commits(
        [*args.accept_code_commit, *args.baseline_code_commit])
    if file_sha256(args.checkpoint) != args.checkpoint_sha256:
        raise ValueError("checkpoint hash mismatch")
    records = [(header.split()[0], sequence) for header, sequence in read_fasta(args.benchmark_fasta)]
    records = [row for row in records if row[0] == args.record_id]
    if len(records) != 1:
        raise ValueError("record-id must match exactly one sequence")
    header, source = records[0]
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", header)
    calibration_path = Path(args.calibration_dir) / f"{safe}.json"
    calibration = json.loads(calibration_path.read_text())
    source_sha256 = hashlib.sha256(source.encode()).hexdigest()
    if calibration["source_sha256"] != source_sha256:
        raise ValueError("calibration source mismatch")
    initial = synonymous_x0(source, np.random.default_rng(args.seed * 1009))
    baseline_path = Path(args.baseline_dir) / f"{safe}_hill_climbing_s{args.seed}.json"
    validate_baseline(baseline_path, {
        "record_id": header, "seed": args.seed, "method": "hill_climbing",
        "source_sha256": source_sha256,
        "initial_sha256": hashlib.sha256(initial.encode()).hexdigest(),
        "benchmark_sha256": file_sha256(args.benchmark_fasta),
        "data_split_sha256": args.data_split_sha256,
        "calibration_sha256": file_sha256(str(calibration_path)),
        "rscu_sha256": file_sha256(args.rscu_json),
        "checkpoint_sha256": None, "code_commit": accepted_code_commits,
    })
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("proposal-in-loop diagnostic requires CUDA; CPU fallback forbidden")
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
    frozen = FrozenReference.from_dict(calibration)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{safe}_learned_hill_s{args.seed}.json"
    expected = {
        "record_id": header, "seed": args.seed, "method": "learned_hill",
        "source_sha256": source_sha256,
        "initial_sha256": hashlib.sha256(initial.encode()).hexdigest(),
        "benchmark_sha256": file_sha256(args.benchmark_fasta),
        "data_split_sha256": args.data_split_sha256,
        "calibration_sha256": file_sha256(str(calibration_path)),
        "rscu_sha256": file_sha256(args.rscu_json),
        "checkpoint_sha256": args.checkpoint_sha256,
        "terminal_step": 1, "path_batch_size": 1,
        "code_commit": accepted_code_commits,
    }
    if out_path.exists():
        if not args.resume:
            raise FileExistsError(f"refusing to overwrite result: {out_path}")
        validate_baseline(out_path, expected)
        print(json.dumps({"record_id": header, "method": "learned_hill", "status": "skipped_existing"}))
        return

    def objectives(sequence):
        return [cai(sequence, weights), -mfe(sequence),
                -abs(gc_fraction(sequence) - args.gc_target),
                -motif_penalty_score(sequence) / len(split_codons(sequence))]

    def learned_proposal(sequence, rng):
        transition = proposal.sample_transition_batch([split_codons(sequence)], 0, rng)[0]
        return "".join(transition.codons)

    result = SimpleSearch(initial, objectives, args.weights, seed=args.seed,
                          normalization=(frozen.reference, frozen.scale),
                          proposal_fn=learned_proposal).run(
        "hill_climbing", max_unique_scorer=args.max_unique_scorer)
    payload = result.to_dict()
    payload["method"] = "learned_hill"
    payload["status"] = "done" if result.status == "done" else "partial"
    payload["incomplete_reason"] = None if result.status == "done" else result.status
    payload.update({
        "protocol_version": "a7_evaluation_v1",
        "run_id": f"a7_proposal_loop_{safe}_learned_hill_s{args.seed}",
        "record_id": header,
        "seed": args.seed,
        "source_sha256": source_sha256,
        "initial_sha256": hashlib.sha256(initial.encode()).hexdigest(),
        "initial_index": 0,
        "terminal_step": 1,
        "path_batch_size": 1,
        "uniform_operator": "learned_single_codon_t1",
        "benchmark_sha256": file_sha256(args.benchmark_fasta),
        "data_split_sha256": args.data_split_sha256,
        "code_commit": git_commit(),
        "code_dirty": code_dirty(),
        "checkpoint_path": args.checkpoint,
        "checkpoint_sha256": args.checkpoint_sha256,
        "rscu_sha256": file_sha256(args.rscu_json),
        "calibration_sha256": file_sha256(str(calibration_path)),
        "anytime": anytime_curve(result.points, frozen),
        "identity_rate": float(np.mean([feasible_edit(point["sequence"], source) for point in result.points])),
        "ned": pairwise_ned([point["sequence"] for point in result.points]),
        "missing_methods": [],
        "exclusions": [],
        "device": str(device),
        "baseline_path": str(baseline_path),
        "baseline_sha256": file_sha256(str(baseline_path)),
    })
    payload["costs"].update({
        "forward_calls": proposal.forward_calls,
        "base_state_evaluations": proposal.forward_calls,
        "rollout_batch_forwards": 0,
        "rollout_state_transitions": 0,
    })
    validate_result_payload(payload)
    temporary = out_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2))
    temporary.replace(out_path)
    validate_baseline(out_path, expected)
    print(json.dumps({"record_id": header, "method": "learned_hill", "seed": args.seed,
                      "status": payload["status"], "auc": payload["anytime"]["auc"]}))


if __name__ == "__main__":
    main()
