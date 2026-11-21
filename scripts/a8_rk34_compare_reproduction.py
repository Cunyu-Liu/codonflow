#!/usr/bin/env python3
"""Compare RK34 clean-checkout production/independent artifacts with accepted references."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

PRODUCTION_CSV = [
    "analysis_start_context_150.csv", "fold_assignments.csv", "oof_predictions.csv",
    "training_log.csv", "seed_metrics.csv", "seed_effects.csv",
]
INDEPENDENT_CSV = ["oof_predictions.csv", "fold_assignments.csv", "training_log.csv", "seed_metrics.csv", "seed_effects.csv"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def science_view(summary):
    return {
        "scientific_conclusion": summary["scientific_conclusion"],
        "primary_family_pass": summary["primary_family_pass"],
        "family_results": summary["family_results"],
        "n_confirmatory_tests": summary["n_confirmatory_tests"],
        "n_confirmatory_pass": summary["n_confirmatory_pass"],
        "n_sensitivity_tests": summary["n_sensitivity_tests"],
        "new_model_fits": summary["new_model_fits"],
        "reused_rk32_model_fits": summary["reused_rk32_model_fits"],
        "evaluated_model_fits": summary["evaluated_model_fits"],
        "primary_tests": summary["primary_tests"],
        "primary_absolute_performance": summary["primary_absolute_performance"],
    }


def main():
    parser = argparse.ArgumentParser()
    for prefix in ("reference", "candidate"):
        parser.add_argument(f"--{prefix}-summary", type=Path, required=True)
        parser.add_argument(f"--{prefix}-root", type=Path, required=True)
        parser.add_argument(f"--{prefix}-independent-report", type=Path, required=True)
        parser.add_argument(f"--{prefix}-independent-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    checks = []

    def check(name, ok, details=None):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    reference = json.loads(args.reference_summary.read_text())
    candidate = json.loads(args.candidate_summary.read_text())
    check("protocol_sha", reference["protocol_sha256"] == candidate["protocol_sha256"])
    check("production_script_sha", reference["analysis_script_sha256"] == candidate["analysis_script_sha256"])
    check("production_science", science_view(reference) == science_view(candidate), {"reference_conclusion": reference["scientific_conclusion"], "candidate_conclusion": candidate["scientific_conclusion"]})
    for name in PRODUCTION_CSV:
        ref, cand = args.reference_root / name, args.candidate_root / name
        check(f"production_csv_{name}", ref.read_bytes() == cand.read_bytes(), {"reference_sha": sha(ref), "candidate_sha": sha(cand)})
    ref_arrays = np.load(args.reference_root / "primary_inference_arrays.npz")
    cand_arrays = np.load(args.candidate_root / "primary_inference_arrays.npz")
    check("production_array_keys", set(ref_arrays.files) == set(cand_arrays.files) and len(ref_arrays.files) == 82, len(ref_arrays.files))
    for key in sorted(ref_arrays.files):
        check(f"production_array_{key}", np.array_equal(ref_arrays[key], cand_arrays[key]), {"shape": list(ref_arrays[key].shape)})

    ref_ind = json.loads(args.reference_independent_report.read_text())
    cand_ind = json.loads(args.candidate_independent_report.read_text())
    check("reference_independent_pass", ref_ind["status"] == "PASS" and ref_ind["checks_passed"] == ref_ind["checks_total"], {"checks": f"{ref_ind['checks_passed']}/{ref_ind['checks_total']}"})
    check("candidate_independent_pass", cand_ind["status"] == "PASS" and cand_ind["checks_passed"] == cand_ind["checks_total"], {"checks": f"{cand_ind['checks_passed']}/{cand_ind['checks_total']}"})
    check("independent_science", ref_ind["scientific_conclusion"] == cand_ind["scientific_conclusion"] == reference["scientific_conclusion"])
    check("independent_fit_count", ref_ind["independent_model_fits"] == cand_ind["independent_model_fits"] == 900)
    check("independent_check_names", [row["name"] for row in ref_ind["checks"]] == [row["name"] for row in cand_ind["checks"]])
    for name in INDEPENDENT_CSV:
        ref, cand = args.reference_independent_root / name, args.candidate_independent_root / name
        check(f"independent_csv_{name}", ref.read_bytes() == cand.read_bytes(), {"reference_sha": sha(ref), "candidate_sha": sha(cand)})
    ref_tests = (args.reference_independent_root / "independent_primary_tests.json").read_bytes()
    cand_tests = (args.candidate_independent_root / "independent_primary_tests.json").read_bytes()
    check("independent_tests_byte_identity", ref_tests == cand_tests, {"reference_sha": hashlib.sha256(ref_tests).hexdigest(), "candidate_sha": hashlib.sha256(cand_tests).hexdigest()})
    ref_ind_arrays = np.load(args.reference_independent_root / "primary_inference_arrays.npz")
    cand_ind_arrays = np.load(args.candidate_independent_root / "primary_inference_arrays.npz")
    check("independent_array_keys", set(ref_ind_arrays.files) == set(cand_ind_arrays.files) and len(ref_ind_arrays.files) == 82, len(ref_ind_arrays.files))
    for key in sorted(ref_ind_arrays.files):
        check(f"independent_array_{key}", np.array_equal(ref_ind_arrays[key], cand_ind_arrays[key]), {"shape": list(ref_ind_arrays[key].shape)})
    check("functional_untouched_not_read", not reference["scientific_flags"]["functional_untouched_read"] and not candidate["scientific_flags"]["functional_untouched_read"] and not ref_ind["functional_untouched_read"] and not cand_ind["functional_untouched_read"])
    payload = {
        "schema": "a8-rk34-clean-reproduction-comparison-v1", "status": "PASS" if all(row["pass"] for row in checks) else "FAIL",
        "reference_summary_sha256": sha(args.reference_summary), "candidate_summary_sha256": sha(args.candidate_summary),
        "reference_independent_report_sha256": sha(args.reference_independent_report), "candidate_independent_report_sha256": sha(args.candidate_independent_report),
        "production_csv_byte_identical": sum(row["name"].startswith("production_csv_") and row["pass"] for row in checks),
        "production_arrays_exact": sum(row["name"].startswith("production_array_") and row["name"] != "production_array_keys" and row["pass"] for row in checks),
        "independent_csv_byte_identical": sum(row["name"].startswith("independent_csv_") and row["pass"] for row in checks),
        "independent_arrays_exact": sum(row["name"].startswith("independent_array_") and row["name"] != "independent_array_keys" and row["pass"] for row in checks),
        "checks": checks, "checks_passed": sum(row["pass"] for row in checks), "checks_total": len(checks),
        "scientific_conclusion": reference["scientific_conclusion"],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in payload.items() if key != "checks"}, indent=2))
    if payload["status"] != "PASS":
        print(json.dumps([row for row in checks if not row["pass"]], indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
