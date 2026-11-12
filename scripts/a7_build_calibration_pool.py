"""Build independent per-gene calibration pools without final-model outputs."""
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

from codonflow.core.codon import gc_fraction, split_codons
from codonflow.core.motifs import motif_penalty_score
from codonflow.data.dataset import read_fasta
from codonflow.eval.anytime import FrozenReference
from codonflow.eval.metrics import cai, cai_weights_from_rscu, mfe
from codonflow.models.simple_search import SimpleSearch
from codonflow.train.run_pretrain import file_sha256


def calibration_runs(n_uniform, n_per_axis):
    if n_uniform < 1 or n_per_axis < 1:
        raise ValueError("calibration run sizes must be positive")
    runs = [("uniform", [1.0, 1.0, 1.0, 0.5], n_uniform)]
    for axis in range(4):
        weights = [0.0] * 4
        weights[axis] = 1.0
        runs.append(("hill_climbing", weights, n_per_axis))
    return runs


def build_pool(source, objective_fn, n_uniform=40, n_per_axis=10, seed=1729):
    points = []
    runs = []
    for method, weights, budget in calibration_runs(n_uniform, n_per_axis):
        result = SimpleSearch(source, objective_fn, weights, seed=seed).run(
            method, max_unique_scorer=budget,
        )
        points.extend(point["objectives"] for point in result.points)
        runs.append({"method": method, "weights": weights, "budget": budget,
                     "status": result.status, "n_unique": len(result.points),
                     "attempts": result.attempts})
    return points, runs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--record-id")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--n-uniform", type=int, default=40)
    parser.add_argument("--n-per-axis", type=int, default=10)
    parser.add_argument("--gc-target", type=float, default=0.55)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    records = [(header.split()[0], sequence) for header, sequence in read_fasta(args.benchmark_fasta)]
    if args.record_id:
        records = [row for row in records if row[0] == args.record_id]
        if len(records) != 1:
            raise ValueError("record-id must match exactly one sequence")
    weights = cai_weights_from_rscu(json.loads(Path(args.rscu_json).read_text()))
    out_dir = Path(args.out_dir)
    pool_dir = out_dir / "pools"
    pool_dir.mkdir(parents=True, exist_ok=True)

    def objectives(sequence):
        return [
            cai(sequence, weights),
            -mfe(sequence),
            -abs(gc_fraction(sequence) - args.gc_target),
            -motif_penalty_score(sequence) / len(split_codons(sequence)),
        ]

    manifest = {
        "protocol": "a7_independent_calibration_pool_v1",
        "source_role": "independent_calibration_generation_not_final_evaluation",
        "seed": args.seed,
        "n_uniform": args.n_uniform,
        "n_per_axis": args.n_per_axis,
        "gc_target": args.gc_target,
        "benchmark_sha256": file_sha256(args.benchmark_fasta),
        "rscu_sha256": file_sha256(args.rscu_json),
        "records": [],
    }
    for header, source in records:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", header)
        reference_path = out_dir / f"{safe}.json"
        pool_path = pool_dir / f"{safe}.json"
        if args.resume and reference_path.exists() and pool_path.exists():
            manifest["records"].append({"record_id": header, "status": "skipped_existing"})
            continue
        points, runs = build_pool(source, objectives, args.n_uniform, args.n_per_axis, args.seed)
        unique_points = np.unique(np.asarray(points, dtype=float), axis=0)
        frozen = FrozenReference.from_calibration(unique_points)
        source_sha256 = hashlib.sha256(source.encode()).hexdigest()
        reference = {
            "protocol": "a7_independent_calibration_v1",
            "source_role": "independent_calibration_not_test",
            "record_id": header,
            "seed": args.seed,
            "source_sha256": source_sha256,
            "rscu_sha256": manifest["rscu_sha256"],
            "n_calibration_points": len(unique_points),
            **frozen.to_dict(),
        }
        reference_path.write_text(json.dumps(reference, indent=2))
        pool_path.write_text(json.dumps({
            "record_id": header, "source_sha256": source_sha256,
            "seed": args.seed, "runs": runs, "objectives": points,
        }, indent=2))
        manifest["records"].append({
            "record_id": header, "status": "done", "n_calibration_points": len(unique_points),
            "reference_sha256": file_sha256(str(reference_path)),
            "pool_sha256": file_sha256(str(pool_path)),
        })
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        print(json.dumps({"record_id": header, "n_calibration_points": len(unique_points)}), flush=True)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
