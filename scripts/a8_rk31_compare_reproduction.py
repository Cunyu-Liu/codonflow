#!/usr/bin/env python3
"""Compare original and clean-checkout RK31 production artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--clean-root", type=Path, required=True)
    parser.add_argument("--original-result", type=Path, required=True)
    parser.add_argument("--clean-result", type=Path, required=True)
    parser.add_argument("--clean-independent", type=Path, required=True)
    parser.add_argument("--clean-clone", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = json.loads(args.original_result.read_text())
    clean = json.loads(args.clean_result.read_text())
    independent = json.loads(args.clean_independent.read_text())
    checks = []

    def check(name: str, condition: bool, evidence=None) -> None:
        checks.append({"check": name, "pass": bool(condition), "evidence": evidence})

    check("clean_independent", independent.get("status") == "PASS_INDEPENDENT_VERIFICATION" and
          independent.get("independent_fit_count") == 450 and not independent.get("failed_checks"))
    check("clean_pending_result", clean.get("status") == "ANALYSIS_COMPLETE_PENDING_INDEPENDENT_VERIFICATION")
    check("protocol_and_code", clean.get("protocol_sha256") == original.get("protocol_sha256") and
          clean.get("analysis_script_sha256") == original.get("analysis_script_sha256"))
    for field in ["scientific_conclusion", "known_context_applicability_pass", "gating_over_shared_full_pass",
                  "context_status", "n_variants", "n_clusters", "primary_seed", "ridge_fit_count",
                  "primary_endpoints", "primary_absolute_performance", "scientific_boundaries"]:
        check(f"scientific_{field}", clean.get(field) == original.get(field))
    csv_names = ["known_context_oof_predictions.csv", "whole_cluster_fold_assignments.csv", "seed_metrics.csv",
                 "seed_effects.csv", "training_log.csv"]
    csv_hashes = {}
    for name in csv_names:
        a, b = args.original_root / "model" / name, args.clean_root / "model" / name
        equal = a.read_bytes() == b.read_bytes()
        csv_hashes[name] = {"original_sha256": sha256(a), "clean_sha256": sha256(b), "byte_equal": equal}
        check(f"csv_byte_equal_{name}", equal)
    array_checks = 0
    max_delta = 0.0
    for context in ["hela_no_intron", "hela_with_intron", "hek293_no_intron"]:
        name = f"primary_inference__{context}.npz"
        a = np.load(args.original_root / "model" / name)
        b = np.load(args.clean_root / "model" / name)
        check(f"npz_names_{context}", set(a.files) == set(b.files))
        for array_name in a.files:
            aa, bb = a[array_name], b[array_name]
            same_shape_dtype = aa.shape == bb.shape and aa.dtype == bb.dtype
            if np.issubdtype(aa.dtype, np.floating):
                delta = float(np.max(np.abs(aa - bb))) if aa.size else 0.0
                max_delta = max(max_delta, delta)
                equal = delta == 0.0
            else:
                equal = bool(np.array_equal(aa, bb))
            check(f"array_{context}_{array_name}", same_shape_dtype and equal,
                  {"shape": aa.shape, "dtype": str(aa.dtype)})
            array_checks += 1
    tracked_dirty = subprocess.run(["git", "diff", "--quiet"], cwd=args.clean_clone).returncode != 0
    staged_dirty = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=args.clean_clone).returncode != 0
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=args.clean_clone, capture_output=True, text=True, check=True).stdout.strip()
    check("clean_checkout_tracked_clean", not tracked_dirty and not staged_dirty,
          {"tracked_dirty": tracked_dirty, "staged_dirty": staged_dirty, "head": head})
    failed = [c for c in checks if not c["pass"]]
    report = {
        "schema": "a8-rk31-clean-reproduction-comparison-v1",
        "status": "PASS_RK31_CLEAN_CHECKOUT_REPRODUCTION" if not failed else "FAIL_RK31_CLEAN_CHECKOUT_REPRODUCTION",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "original_result_sha256": sha256(args.original_result), "clean_result_sha256": sha256(args.clean_result),
        "clean_independent_sha256": sha256(args.clean_independent),
        "clean_clone_head": head, "clean_tracked_dirty": tracked_dirty, "clean_staged_dirty": staged_dirty,
        "original_root": str(args.original_root), "clean_root": str(args.clean_root),
        "csv_files": csv_hashes, "npz_array_count": array_checks, "max_array_abs_delta": max_delta,
        "checks_total": len(checks), "checks_passed": len(checks) - len(failed), "failed_checks": failed,
        "checks": checks,
        "scientific_conclusion": clean["scientific_conclusion"],
        "production_elapsed_seconds_original": original["elapsed_seconds"],
        "production_elapsed_seconds_clean": clean["elapsed_seconds"],
        "independent_elapsed_seconds_clean": independent["elapsed_seconds"],
        "boundary": "Clean-checkout reproduction of the same retrospective analysis; not independent untouched confirmation, unseen-context transport, functional OOD or SOTA."
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}",
                      "arrays": array_checks, "max_array_abs_delta": max_delta, "output": str(args.output)}, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
