#!/usr/bin/env python3
"""Compare RK37 production with an independent clean-checkout rerun."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

import numpy as np


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-report", required=True)
    parser.add_argument("--clean-report", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    production_path = Path(args.production_report).resolve()
    clean_path = Path(args.clean_report).resolve()
    production = json.loads(production_path.read_text())
    clean = json.loads(clean_path.read_text())
    checks = []
    array_count = 0

    def check(name, condition, evidence=None):
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})

    def close(name, left, right, tolerance=1e-9):
        if left is None or right is None:
            check(name, left is right)
            return
        difference = abs(float(left) - float(right))
        check(name, math.isfinite(difference) and difference <= tolerance, {"difference": difference, "tolerance": tolerance})

    check("production_status", production["status"] == "PASS_RK37_PRODUCTION_PENDING_INDEPENDENT")
    check("clean_status", clean["status"] == "PASS_RK37_PRODUCTION_PENDING_INDEPENDENT")
    check("protocol_sha", production["protocol_sha256"] == clean["protocol_sha256"])
    check("fit_accounting", production["fit_accounting"] == clean["fit_accounting"] == {"planned_unique_fits": 48, "actual_unique_fits": 48, "families_per_seed": 4, "alphas_per_family": 4, "seeds": 3})
    check("scientific_decision", production["scientific_decision"] == clean["scientific_decision"])
    check("target_access_gate", production["target_outcomes_accessed_after_all_source_fits"] is True and clean["target_outcomes_accessed_after_all_source_fits"] is True)
    check("distinct_clean_commit", production["frozen_git_commit"] != clean["frozen_git_commit"])
    for relative in ("scripts/a8_rk37_run_translation_pivot.py", "configs/a8_rk37_translation_pivot_protocol_v1.json", "tests/test_a8_rk37_translation_pivot.py"):
        old = subprocess.check_output(["git", "show", f"{production['frozen_git_commit']}:{relative}"])
        new = subprocess.check_output(["git", "show", f"{clean['frozen_git_commit']}:{relative}"])
        current = Path(relative).read_bytes()
        check(f"frozen_code_identity_{relative}", old == new == current)

    for i, (pseed, cseed) in enumerate(zip(production["source_reports"], clean["source_reports"])):
        seed = pseed["seed"]
        check(f"seed_{seed}_id", seed == cseed["seed"])
        check(f"seed_{seed}_split", pseed["split"]["train_ids"] == cseed["split"]["train_ids"] and pseed["split"]["validation_ids"] == cseed["split"]["validation_ids"] and pseed["split"]["split_seed"] == cseed["split"]["split_seed"])
        check(f"seed_{seed}_selected_alpha", pseed["selected_alpha"] == cseed["selected_alpha"])
        close(f"seed_{seed}_source_mean", pseed["split"]["source_train_raw_masked_mean"], cseed["split"]["source_train_raw_masked_mean"], 0.0)
        for family in pseed["candidates"]:
            pc = pseed["candidates"][family]
            cc = cseed["candidates"][family]
            check(f"seed_{seed}_{family}_candidate_count", len(pc) == len(cc) == 4)
            for j, (p, c) in enumerate(zip(pc, cc)):
                check(f"seed_{seed}_{family}_{j}_alpha", p["alpha"] == c["alpha"])
                for deployment in ("validation_raw", "validation_anchored"):
                    for metric in ("transcript_balanced_mse", "mean_transcript_pearson", "global_mse", "global_r2"):
                        close(f"seed_{seed}_{family}_{j}_{deployment}_{metric}", p[deployment][metric], c[deployment][metric], 1e-9)
        prun = pseed["target_evaluation"]
        crun = cseed["target_evaluation"]
        for arm in prun["target_metrics"]:
            for metric in prun["target_metrics"][arm]:
                close(f"seed_{seed}_{arm}_{metric}", prun["target_metrics"][arm][metric], crun["target_metrics"][arm][metric], 1e-9)
        for effect in prun["primary_effects"]:
            close(f"seed_{seed}_{effect}", prun["primary_effects"][effect], crun["primary_effects"][effect], 1e-9)
        for artifact in ("predictions", "source_models"):
            ppath = Path(prun["artifacts"][artifact]["path"])
            cpath = Path(crun["artifacts"][artifact]["path"])
            with np.load(ppath, allow_pickle=False) as parray, np.load(cpath, allow_pickle=False) as carray:
                check(f"seed_{seed}_{artifact}_names", set(parray.files) == set(carray.files))
                for key in parray.files:
                    array_count += 1
                    check(f"seed_{seed}_{artifact}_{key}_exact", np.array_equal(parray[key], carray[key]))
        pcsv = Path(prun["artifacts"]["transcript_metrics"]["path"])
        ccsv = Path(crun["artifacts"]["transcript_metrics"]["path"])
        check(f"seed_{seed}_transcript_csv_byte_exact", pcsv.read_bytes() == ccsv.read_bytes(), {"production_sha": sha256(pcsv), "clean_sha": sha256(ccsv)})

    for i, (p, c) in enumerate(zip(production["primary_endpoints"], clean["primary_endpoints"])):
        check(f"primary_{i}_identity", p["name"] == c["name"] and p["n_pairs"] == c["n_pairs"] and p["resamples"] == c["resamples"])
        for field in ("effect", "ci95_low", "ci95_high", "sign_flip_pvalue", "holm_pvalue"):
            close(f"primary_{i}_{field}", p[field], c[field], 1e-9)
        check(f"primary_{i}_sensitivity_exact", p["sensitivity_effects"] == c["sensitivity_effects"])
        for field in ("primary_pass", "sensitivity_pass", "gate_pass"):
            check(f"primary_{i}_{field}", p[field] == c[field])
    pinference = Path(production["artifacts"]["primary_inference_arrays"]["path"])
    cinference = Path(clean["artifacts"]["primary_inference_arrays"]["path"])
    with np.load(pinference, allow_pickle=False) as parray, np.load(cinference, allow_pickle=False) as carray:
        check("inference_array_names", set(parray.files) == set(carray.files))
        for key in parray.files:
            array_count += 1
            check(f"inference_{key}_exact", np.array_equal(parray[key], carray[key]))

    passed = sum(item["pass"] for item in checks)
    report = {
        "schema": "a8-rk37-clean-reproduction-comparison-v1",
        "status": "PASS_RK37_CLEAN_REPRODUCTION" if passed == len(checks) else "FAIL",
        "checks_passed": passed, "checks_total": len(checks), "failures": [c for c in checks if not c["pass"]],
        "checks": checks, "exact_arrays_compared": array_count,
        "production": {"path": str(production_path), "sha256": sha256(production_path), "commit": production["frozen_git_commit"]},
        "clean": {"path": str(clean_path), "sha256": sha256(clean_path), "commit": clean["frozen_git_commit"]},
        "scientific_decision": clean["scientific_decision"],
        "note": "Exact array/CSV reproduction verifies engineering determinism; it does not change the negative scientific gate or create independent confirmation.",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "exact_arrays": array_count, "failures": report["failures"][:5]}, indent=2))
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
