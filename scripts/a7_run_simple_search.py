"""Run A7 simple searches with real CDS objectives and frozen calibration."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
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


def code_dirty():
    try:
        root = Path(__file__).resolve().parents[1]
        status = subprocess.check_output(["git", "status", "--short"], cwd=root, text=True)
        return bool(status.strip())
    except (OSError, subprocess.CalledProcessError):
        return None


def completed_result(path, expected):
    payload = json.loads(Path(path).read_text())
    validate_result_payload(payload)
    if payload["status"] != "done" or payload["code_dirty"] is not False:
        raise ValueError(f"cannot resume incomplete or dirty result: {path}")
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError(f"resume mismatch for {key}: {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--calibration-dir", required=True)
    parser.add_argument("--data-split-sha256", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--methods", nargs="+", choices=SimpleSearch.METHODS,
                        default=list(SimpleSearch.METHODS))
    parser.add_argument("--record-id")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-unique-scorer", type=int, default=500)
    parser.add_argument("--gc-target", type=float, default=0.55)
    parser.add_argument("--weights", nargs="+", type=float, default=[1, 1, 1, 0.5])
    args = parser.parse_args()
    if len(args.weights) != 4:
        raise ValueError("exactly four objective weights are required")
    records = [(header.split()[0], sequence) for header, sequence in read_fasta(args.benchmark_fasta)]
    if args.record_id:
        records = [row for row in records if row[0] == args.record_id]
        if len(records) != 1:
            raise ValueError("record-id must match exactly one sequence")
    cai_weights = cai_weights_from_rscu(json.loads(Path(args.rscu_json).read_text()))
    benchmark_sha256 = file_sha256(args.benchmark_fasta)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def objectives(sequence):
        return [
            cai(sequence, cai_weights),
            -mfe(sequence),
            -abs(gc_fraction(sequence) - args.gc_target),
            -motif_penalty_score(sequence) / len(split_codons(sequence)),
        ]

    for header, source in records:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", header)
        calibration_path = Path(args.calibration_dir) / f"{safe}.json"
        calibration = json.loads(calibration_path.read_text())
        if calibration["source_sha256"] != hashlib.sha256(source.encode()).hexdigest():
            raise ValueError(f"calibration source mismatch: {header}")
        frozen = FrozenReference.from_dict(calibration)
        initial = synonymous_x0(source, np.random.default_rng(args.seed * 1009))
        for method in args.methods:
            out_path = out_dir / f"{safe}_{method}_s{args.seed}.json"
            if out_path.exists():
                if not args.resume:
                    raise FileExistsError(f"refusing to overwrite result: {out_path}")
                completed_result(out_path, {
                    "record_id": header, "seed": args.seed, "method": method,
                    "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                    "initial_sha256": hashlib.sha256(initial.encode()).hexdigest(),
                    "calibration_sha256": file_sha256(str(calibration_path)),
                    "rscu_sha256": file_sha256(args.rscu_json),
                    "checkpoint_sha256": None, "code_commit": git_commit(),
                })
                print(json.dumps({"record_id": header, "method": method, "status": "skipped_existing"}), flush=True)
                continue
            result = SimpleSearch(
                initial, objectives, args.weights, seed=args.seed,
                normalization=(frozen.reference, frozen.scale),
            ).run(method, max_unique_scorer=args.max_unique_scorer)
            anytime = anytime_curve(result.points, frozen)
            payload = result.to_dict()
            payload.update({
                "protocol_version": "a7_evaluation_v1",
                "run_id": f"a7_{safe}_{method}_s{args.seed}",
                "record_id": header,
                "seed": args.seed,
                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "initial_sha256": hashlib.sha256(initial.encode()).hexdigest(),
                "initial_index": 0,
                "terminal_step": None,
                "benchmark_sha256": benchmark_sha256,
                "data_split_sha256": args.data_split_sha256,
                "code_commit": git_commit(),
                "code_dirty": code_dirty(),
                "checkpoint_path": None,
                "checkpoint_sha256": None,
                "rscu_sha256": file_sha256(args.rscu_json),
                "calibration_sha256": file_sha256(str(calibration_path)),
                "anytime": anytime,
                "identity_rate": float(np.mean([
                    feasible_edit(point["sequence"], source) for point in result.points
                ])),
                "ned": pairwise_ned([point["sequence"] for point in result.points]),
                "missing_methods": [],
                "exclusions": [],
            })
            payload["costs"].update({
                "base_state_evaluations": 0,
                "rollout_batch_forwards": 0,
                "rollout_state_transitions": 0,
            })
            validate_result_payload(payload)
            out_path = out_dir / f"{safe}_{method}_s{args.seed}.json"
            temporary = out_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, indent=2))
            temporary.replace(out_path)
            print(json.dumps({"record_id": header, "method": method, "seed": args.seed,
                              "status": result.status, "auc": anytime["auc"]}), flush=True)


if __name__ == "__main__":
    main()
