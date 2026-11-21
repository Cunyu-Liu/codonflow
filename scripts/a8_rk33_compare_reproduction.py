#!/usr/bin/env python3
"""Compare original and clean-clone RK33 scientific artifacts."""
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for name in ["original-summary", "original-independent", "clean-summary", "clean-independent", "report"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    original = json.loads(args.original_summary.read_text()); clean = json.loads(args.clean_summary.read_text())
    original_ind = json.loads(args.original_independent.read_text()); clean_ind = json.loads(args.clean_independent.read_text())
    checks = []
    def check(name, ok, details):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    for key in ["protocol_sha256", "preflight_report_sha256", "analysis_script_sha256", "source_csv_sha256", "rk28_predictions_sha256", "n_variants", "n_sequence_clusters", "primary_seed", "seeds", "new_model_fits", "reused_rk28_model_fits", "evaluated_model_fits", "primary_absolute_performance", "primary_tests", "family_pass", "all_12_pass", "scientific_conclusion", "scientific_flags"]:
        check(f"production_field_{key}", original[key] == clean[key], {"original": original[key], "clean": clean[key]})
    check("original_independent_pass", original_ind["status"] == "PASS" and original_ind["checks_passed"] == original_ind["checks_total"], {"status": original_ind["status"], "checks": original_ind["checks_total"]})
    check("clean_independent_pass", clean_ind["status"] == "PASS" and clean_ind["checks_passed"] == clean_ind["checks_total"], {"status": clean_ind["status"], "checks": clean_ind["checks_total"]})
    for key in ["independent_conclusion", "family_pass", "independent_tests", "scientific_flags"]:
        check(f"independent_field_{key}", original_ind[key] == clean_ind[key], {"original": original_ind[key], "clean": clean_ind[key]})

    csv_comparisons, array_comparisons = [], []
    for label, left_summary, right_summary, output_key in [("production", original, clean, "outputs"), ("independent", original_ind, clean_ind, "independent_outputs")]:
        for name in sorted(left_summary[output_key]):
            if not name.endswith(".csv"):
                continue
            left = Path(left_summary[output_key][name]["path"]); right = Path(right_summary[output_key][name]["path"])
            equal = left.read_bytes() == right.read_bytes()
            row = {"component": label, "name": name, "byte_equal": equal, "original_sha256": digest(left), "clean_sha256": digest(right)}
            csv_comparisons.append(row); check(f"csv_byte_equal_{label}_{name}", equal, row)
        left_arrays = Path(left_summary[output_key]["primary_inference_arrays.npz"]["path"]); right_arrays = Path(right_summary[output_key]["primary_inference_arrays.npz"]["path"])
        left_npz, right_npz = np.load(left_arrays), np.load(right_arrays)
        check(f"npz_keys_{label}", set(left_npz.files) == set(right_npz.files), {"original": sorted(left_npz.files), "clean": sorted(right_npz.files)})
        for key in sorted(left_npz.files):
            exact = bool(np.array_equal(left_npz[key], right_npz[key]))
            delta = float(np.max(np.abs(left_npz[key].astype(float) - right_npz[key].astype(float)))) if left_npz[key].shape == right_npz[key].shape and left_npz[key].size else 0.0
            row = {"component": label, "array": key, "shape": list(left_npz[key].shape), "exact_equal": exact, "max_abs_delta": delta}
            array_comparisons.append(row); check(f"array_exact_{label}_{key}", exact, row)
    report = {
        "schema": "a8-rk33-clean-reproduction-comparison-v1", "status": "PASS" if all(row["pass"] for row in checks) else "FAIL",
        "checks": checks, "checks_passed": sum(row["pass"] for row in checks), "checks_total": len(checks), "failed_checks": [row["name"] for row in checks if not row["pass"]],
        "csv_comparisons": csv_comparisons, "array_comparisons": array_comparisons,
        "csv_byte_equal": sum(row["byte_equal"] for row in csv_comparisons), "csv_total": len(csv_comparisons),
        "arrays_exact_equal": sum(row["exact_equal"] for row in array_comparisons), "arrays_total": len(array_comparisons),
        "original_production_elapsed_seconds": original["elapsed_seconds"], "clean_production_elapsed_seconds": clean["elapsed_seconds"],
        "original_independent_elapsed_seconds": original_ind["elapsed_seconds"], "clean_independent_elapsed_seconds": clean_ind["elapsed_seconds"],
        "original_summary_sha256": digest(args.original_summary), "clean_summary_sha256": digest(args.clean_summary),
        "original_independent_sha256": digest(args.original_independent), "clean_independent_sha256": digest(args.clean_independent),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True); args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f'{report["checks_passed"]}/{report["checks_total"]}', "csv": f'{report["csv_byte_equal"]}/{report["csv_total"]}', "arrays": f'{report["arrays_exact_equal"]}/{report["arrays_total"]}', "failed_checks": report["failed_checks"], "report": str(args.report)}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
