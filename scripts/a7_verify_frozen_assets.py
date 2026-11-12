"""Verify frozen confirmation and calibration assets without regenerating them."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.data.dataset import read_fasta
from codonflow.eval.anytime import FrozenReference
from codonflow.train.run_pretrain import file_sha256, git_commit

EXPECTED_CONFIRMATION_SHA256 = "a128bdbf6bfbc94f33d8d4d72f99173108ee0f0d8d3318d5a0d287de3b710d6d"
EXPECTED_D5_RSCU_SHA256 = "2a5e05ef17a03a2b3b063990fd875d565a6db3fbedebab7689bca1fa45658c5d"


def verify_frozen_assets(confirmation_fasta, rscu_json, calibration_dir, expected_n=24):
    calibration_dir = Path(calibration_dir)
    records = {header.split()[0]: sequence for header, sequence in read_fasta(confirmation_fasta)}
    manifest_path = calibration_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest_records = manifest.get("records", [])
    manifest_by_id = {row.get("record_id"): row for row in manifest_records}
    checks = {
        "confirmation_sha256": file_sha256(confirmation_fasta) == EXPECTED_CONFIRMATION_SHA256,
        "rscu_sha256": file_sha256(rscu_json) == EXPECTED_D5_RSCU_SHA256,
        "confirmation_count": len(records) == expected_n,
        "manifest_count": len(manifest_records) == expected_n and len(manifest_by_id) == expected_n,
        "manifest_status": all(row.get("status") == "done" for row in manifest_records),
        "manifest_ids": set(manifest_by_id) == set(records),
        "manifest_benchmark_sha256": manifest.get("benchmark_sha256") == file_sha256(confirmation_fasta),
        "manifest_rscu_sha256": manifest.get("rscu_sha256") == file_sha256(rscu_json),
        "manifest_source_role": manifest.get("source_role") == "independent_calibration_generation_not_final_evaluation",
    }
    rows = []
    for record_id, source in records.items():
        path = calibration_dir / f"{record_id}.json"
        pool_path = calibration_dir / "pools" / f"{record_id}.json"
        row = {"record_id": record_id, "reference_exists": path.exists(), "pool_exists": pool_path.exists()}
        if path.exists() and pool_path.exists() and record_id in manifest_by_id:
            reference = json.loads(path.read_text())
            pool = json.loads(pool_path.read_text())
            points = np.asarray(pool.get("objectives", []), dtype=float)
            unique_points = np.unique(points, axis=0) if points.size else points.reshape(0, 4)
            try:
                frozen = FrozenReference.from_calibration(unique_points) if len(unique_points) else None
            except ValueError:
                frozen = None
            record = manifest_by_id[record_id]
            row.update({
                "source_role": reference.get("source_role") == "independent_calibration_not_test",
                "record_id_matches": reference.get("record_id") == record_id and pool.get("record_id") == record_id,
                "source_sha256": reference.get("source_sha256") == hashlib.sha256(source.encode()).hexdigest()
                                  and pool.get("source_sha256") == reference.get("source_sha256"),
                "rscu_sha256": reference.get("rscu_sha256") == file_sha256(rscu_json),
                "reference_sha256": record.get("reference_sha256") == file_sha256(path),
                "pool_sha256": record.get("pool_sha256") == file_sha256(pool_path),
                "point_count": reference.get("n_calibration_points") == len(unique_points)
                                and record.get("n_calibration_points") == len(unique_points),
                "scale_positive_finite": len(reference.get("scale", [])) == 4
                                          and all(math.isfinite(float(value)) and float(value) > 0
                                                  for value in reference.get("scale", [])),
                "reference_recomputed": frozen is not None and np.allclose(
                    reference.get("reference", []), frozen.reference, rtol=0, atol=1e-12)
                    and np.allclose(reference.get("scale", []), frozen.scale, rtol=0, atol=1e-12),
            })
        row["passed"] = bool(row.get("reference_exists") and row.get("pool_exists")
                             and all(value for key, value in row.items()
                                     if key not in {"record_id", "reference_exists", "pool_exists", "passed"}))
        rows.append(row)
    checks["all_records"] = len(rows) == expected_n and all(row["passed"] for row in rows)
    return {
        "protocol": "a7_frozen_asset_verification_v1",
        "code_commit": git_commit(),
        "confirmation_fasta": str(confirmation_fasta),
        "confirmation_sha256": file_sha256(confirmation_fasta),
        "rscu_json": str(rscu_json),
        "rscu_sha256": file_sha256(rscu_json),
        "calibration_dir": str(calibration_dir),
        "expected_n": expected_n,
        "checks": checks,
        "passed": all(checks.values()),
        "records": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation-fasta", required=True)
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--calibration-dir", required=True)
    parser.add_argument("--expected-n", type=int, default=24)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = verify_frozen_assets(args.confirmation_fasta, args.rscu_json,
                                  args.calibration_dir, args.expected_n)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(out.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(out)
    print(json.dumps({"out": str(out), "passed": result["passed"], "checks": result["checks"]}))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
