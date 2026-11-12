"""Audit unique18 baseline completion without claiming MFE/NED recomputation."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.data.dataset import read_fasta
from codonflow.train.run_pretrain import file_sha256

EXPECTED_METHODS = ("lineardesign_scan", "codongpt", "gemorna", "cai_greedy", "uniform_synonymous")


def audit_unique18(input_dir, benchmark_fasta, seeds=(0, 1, 2)):
    records = [header.split()[0] for header, _ in read_fasta(benchmark_fasta)]
    rows = []
    for record in records:
        for seed in seeds:
            path = Path(input_dir) / f"{record}_s{seed}.json"
            row = {"record_id": record, "seed": seed, "path": str(path),
                   "exists": path.exists(), "status": "missing"}
            if path.exists():
                payload = json.loads(path.read_text())
                methods = payload.get("methods", {})
                finite = all(
                    math.isfinite(float(value))
                    for result in methods.values()
                    for vector in result.get("obj_vectors", [])
                    for value in vector
                )
                identities = [result.get("identity_rate") for result in methods.values()]
                row.update({
                    "status": payload.get("status", "unknown"),
                    "methods": {name: methods.get(name, {}).get("status", "missing")
                                for name in EXPECTED_METHODS},
                    "n_unique": {name: methods.get(name, {}).get("n_unique")
                                 for name in EXPECTED_METHODS},
                    "identity_all_one": all(value == 1.0 for value in identities),
                    "objectives_finite": finite,
                    "benchmark_sha256_matches": payload.get("benchmark_sha256") == file_sha256(benchmark_fasta),
                })
            rows.append(row)
    complete_seed0 = all(
        row["exists"] and row["status"] == "done"
        and all(status == "done" for status in row["methods"].values())
        and row["identity_all_one"] and row["objectives_finite"]
        and row["benchmark_sha256_matches"]
        for row in rows if row["seed"] == 0
    )
    return {
        "protocol": "a7_unique18_manifest_review_v1",
        "benchmark_sha256": file_sha256(benchmark_fasta),
        "n_records": len(records),
        "seeds": list(seeds),
        "complete_seed0": complete_seed0,
        "complete_all_requested_seeds": all(
            row["exists"] and row["status"] == "done"
            and all(status == "done" for status in row["methods"].values())
            and row["identity_all_one"] and row["objectives_finite"]
            and row["benchmark_sha256_matches"]
            for row in rows
        ),
        "mfe_ned_independently_recomputed": False,
        "note": "This is a status/finite-value audit, not an independent MFE/NED recomputation.",
        "records": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = audit_unique18(args.input_dir, args.benchmark_fasta, args.seeds)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps({"complete_seed0": result["complete_seed0"],
                      "complete_all_requested_seeds": result["complete_all_requested_seeds"]}))


if __name__ == "__main__":
    main()
