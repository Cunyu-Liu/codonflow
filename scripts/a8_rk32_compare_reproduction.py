#!/usr/bin/env python3
"""Compare original and clean-checkout RK32 scientific artifacts without refitting."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path):
    return json.loads(path.read_text())


def arrays_equal(a: np.ndarray, b: np.ndarray) -> bool:
    if a.shape != b.shape or a.dtype != b.dtype:
        return False
    if np.issubdtype(a.dtype, np.number) or a.dtype == np.bool_:
        return bool(np.array_equal(a, b, equal_nan=True))
    return bool(np.array_equal(a, b))


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ["original-result", "clean-result", "original-independent", "clean-independent",
                 "original-root", "clean-root", "clean-clone", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args()
    original = load(args.original_result)
    clean = load(args.clean_result)
    original_ind = load(args.original_independent)
    clean_ind = load(args.clean_independent)
    checks = []

    def check(name: str, passed: bool, detail) -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    actual_head = subprocess.check_output(["git", "-C", str(args.clean_clone), "rev-parse", "HEAD"], text=True).strip()
    check("clean_clone_exact_head", actual_head == args.expected_head, actual_head)
    check("original_independent_pass", original_ind.get("status") == "PASS" and len(original_ind["checks"]) == 23 and all(x["pass"] for x in original_ind["checks"]), original_ind.get("status"))
    check("clean_independent_pass", clean_ind.get("status") == "PASS" and len(clean_ind["checks"]) == 23 and all(x["pass"] for x in clean_ind["checks"]), clean_ind.get("status"))
    check("original_result_hash_binding", original_ind["production_result_sha256"] == sha256(args.original_result), original_ind["production_result_sha256"])
    check("clean_result_hash_binding", clean_ind["production_result_sha256"] == sha256(args.clean_result), clean_ind["production_result_sha256"])
    check("protocol_hash_binding", original["protocol_sha256"] == clean["protocol_sha256"] == original_ind["protocol_sha256"] == clean_ind["protocol_sha256"], clean["protocol_sha256"])
    check("analysis_script_hash", original["analysis_script_sha256"] == clean["analysis_script_sha256"], clean["analysis_script_sha256"])
    check("scientific_conclusion", original["scientific_conclusion"] == clean["scientific_conclusion"] == clean_ind["scientific_conclusion"], clean["scientific_conclusion"])
    fields = ["analysis_type", "arm_results", "n_exact_cds_groups", "n_measurement_rows", "n_sequence_clusters",
              "n_structure_arms_all_four_pass", "primary_absolute_performance", "primary_seed", "primary_tests",
              "scientific_flags", "seeds", "folds_per_seed", "model_fits_per_fold", "structure_arms", "total_model_fits"]
    for field in fields:
        check("scientific_field__" + field, original[field] == clean[field], {"equal": original[field] == clean[field]})
    check("primary_endpoint_count", len(clean["primary_tests"]) == 24, len(clean["primary_tests"]))
    check("fit_accounting", clean["total_model_fits"] == 700, clean["total_model_fits"])

    artifact_rows = []
    for name, original_meta in original["outputs"].items():
        original_path = args.original_root / name
        clean_path = args.clean_root / name
        check("artifact_exists__" + name, original_path.is_file() and clean_path.is_file(), name)
        original_hash = sha256(original_path)
        clean_hash = sha256(clean_path)
        check("declared_original_hash__" + name, original_hash == original_meta["sha256"], original_hash)
        check("declared_clean_hash__" + name, clean_hash == clean["outputs"][name]["sha256"], clean_hash)
        row = {"name": name, "original_sha256": original_hash, "clean_sha256": clean_hash,
               "original_bytes": original_path.stat().st_size, "clean_bytes": clean_path.stat().st_size}
        if name.endswith(".csv"):
            row["byte_equal"] = original_path.read_bytes() == clean_path.read_bytes()
            check("csv_byte_equal__" + name, row["byte_equal"], row["byte_equal"])
        artifact_rows.append(row)

    original_npz_path = args.original_root / "primary_inference_arrays.npz"
    clean_npz_path = args.clean_root / "primary_inference_arrays.npz"
    npz_rows = []
    with np.load(original_npz_path, allow_pickle=False) as a, np.load(clean_npz_path, allow_pickle=False) as b:
        check("npz_key_set", sorted(a.files) == sorted(b.files), len(a.files))
        for key in sorted(a.files):
            if key not in b.files:
                check("npz_array__" + key, False, "missing")
                continue
            aa, bb = a[key], b[key]
            equal = arrays_equal(aa, bb)
            max_delta = None
            if np.issubdtype(aa.dtype, np.number) and aa.shape == bb.shape:
                max_delta = float(np.nanmax(np.abs(aa.astype(np.float64) - bb.astype(np.float64)))) if aa.size else 0.0
            npz_rows.append({"key": key, "shape": list(aa.shape), "dtype": str(aa.dtype), "exact_equal": equal, "max_abs_delta": max_delta})
            check("npz_array__" + key, equal, max_delta)
    check("npz_array_count", len(npz_rows) > 0, len(npz_rows))
    check("clean_independent_numeric_deltas", all(float(v) <= 1e-10 for v in clean_ind["max_deltas"].values()), clean_ind["max_deltas"])
    check("clean_scope_flags", clean_ind["independent_confirmation"] is False and clean_ind["functional_untouched_read"] is False and clean_ind["RK_G1_complete"] is False, "retrospective_only")

    report = {
        "schema": "a8-rk32-clean-reproduction-comparison-v1",
        "status": "PASS_RK32_CLEAN_CHECKOUT_REPRODUCTION" if all(x["pass"] for x in checks) else "FAIL_RK32_CLEAN_CHECKOUT_REPRODUCTION",
        "expected_head": args.expected_head,
        "clean_clone_head": actual_head,
        "original_result_sha256": sha256(args.original_result),
        "clean_result_sha256": sha256(args.clean_result),
        "original_independent_sha256": sha256(args.original_independent),
        "clean_independent_sha256": sha256(args.clean_independent),
        "scientific_conclusion": clean["scientific_conclusion"],
        "checks": checks,
        "checks_total": len(checks),
        "checks_passed": sum(x["pass"] for x in checks),
        "csv_count": sum(x["name"].endswith(".csv") for x in artifact_rows),
        "csv_byte_equal_count": sum(bool(x.get("byte_equal")) for x in artifact_rows),
        "npz_array_count": len(npz_rows),
        "npz_exact_equal_count": sum(x["exact_equal"] for x in npz_rows),
        "artifacts": artifact_rows,
        "npz_arrays": npz_rows,
        "production_elapsed_seconds_original": original["component_wall_seconds"],
        "production_elapsed_seconds_clean": clean["component_wall_seconds"],
        "independent_elapsed_seconds_original": original_ind["component_wall_seconds"],
        "independent_elapsed_seconds_clean": clean_ind["component_wall_seconds"],
        "clean_independent_max_deltas": clean_ind["max_deltas"],
        "independent_untouched_confirmation": False,
        "functional_untouched_read": False,
        "RK_G1_complete": False,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in {"checks", "artifacts", "npz_arrays"}}, indent=2))
    if report["status"] != "PASS_RK32_CLEAN_CHECKOUT_REPRODUCTION":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
