#!/usr/bin/env python3
"""Compare RK35 clean-checkout reproduction against the frozen production run.
CSV artifacts must be byte-identical; NPZ arrays exact; result JSON scientific
fields equal (timestamps/wall-seconds excluded)."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

CSV_FILES = [
    "analysis_start_aware_150.csv", "fold_assignments.csv", "oof_predictions.csv",
    "training_log.csv", "seed_metrics.csv", "seed_effects.csv",
]
RESULT_SCIENTIFIC_FIELDS = [
    "status", "analysis_type", "n_measurement_rows", "n_exact_cds_groups", "n_sequence_clusters",
    "primary_seed", "seeds", "folds_per_seed", "arms", "primary_contrasts", "gate_contrast",
    "secondary_contrasts", "new_model_fits", "reused_model_fits", "evaluated_model_fits",
    "consistency_gate", "primary_absolute_performance", "primary_tests", "gate_tests",
    "secondary_tests", "contrast_results", "scientific_conclusion", "decision_code", "scientific_flags",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--production-root", type=Path, required=True)
    ap.add_argument("--reproduction-root", type=Path, required=True)
    ap.add_argument("--production-summary", type=Path, required=True)
    ap.add_argument("--reproduction-summary", type=Path, required=True)
    ap.add_argument("--production-independent", type=Path, required=True)
    ap.add_argument("--reproduction-independent", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    checks = []

    def check(name, ok, details=None):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    csv_details = {}
    for name in CSV_FILES:
        a, b = args.production_root / name, args.reproduction_root / name
        same = a.read_bytes() == b.read_bytes()
        csv_details[name] = {"byte_identical": same, "production_sha256": sha256(a), "reproduction_sha256": sha256(b)}
        check(f"csv_byte_identical_{name}", same)

    pa = np.load(args.production_root / "primary_inference_arrays.npz")
    pb = np.load(args.reproduction_root / "primary_inference_arrays.npz")
    check("npz_key_sets_equal", set(pa.files) == set(pb.files), {"n_keys": len(pa.files)})
    npz_ok = True
    for key in pa.files:
        if pa[key].shape != pb[key].shape or pa[key].dtype != pb[key].dtype or not np.array_equal(pa[key], pb[key]):
            npz_ok = False
    check("npz_arrays_exact", npz_ok)

    ra = json.loads(args.production_summary.read_text())
    rb = json.loads(args.reproduction_summary.read_text())
    field_mismatch = []
    for field in RESULT_SCIENTIFIC_FIELDS:
        if ra.get(field) != rb.get(field):
            field_mismatch.append(field)
    check("result_scientific_fields_equal", not field_mismatch, field_mismatch)
    output_sha_match = all(ra["outputs"][k]["sha256"] == rb["outputs"][k]["sha256"] for k in ra["outputs"])
    check("result_output_hashes_equal", output_sha_match)

    ia = json.loads(args.production_independent.read_text())
    ib = json.loads(args.reproduction_independent.read_text())
    check("independent_status_equal", ia["status"] == ib["status"] == "PASS", {"production": ia["status"], "reproduction": ib["status"]})
    check("independent_conclusion_equal", ia["independent_conclusion"] == ib["independent_conclusion"])

    report = {
        "schema": "a8-rk35-reproduction-comparison-v1",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "production_root": str(args.production_root), "reproduction_root": str(args.reproduction_root),
        "csv_details": csv_details,
        "checks_passed": sum(c["pass"] for c in checks), "checks_total": len(checks), "checks": checks,
    }
    atomic_json(args.report, report)
    print(json.dumps({k: v for k, v in report.items() if k not in ("checks", "csv_details")}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()