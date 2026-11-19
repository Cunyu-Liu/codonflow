#!/usr/bin/env python3
"""Finalize the independently verified MAGE development-only nested-CV result."""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--production", required=True)
    parser.add_argument("--independent", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    cfg = json.loads(Path(args.config).read_text())
    production = json.loads(Path(args.production).read_text())
    independent = json.loads(Path(args.independent).read_text())
    checks = []

    def check(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("protocol_hash_production", sha256(args.config) == production["protocol_sha256"])
    check("protocol_hash_independent", sha256(args.config) == independent["protocol_sha256"])
    check("production_hash_independent", sha256(args.production) == independent["production_report_sha256"])
    check("independent_pass", independent["status"] == "PASS")
    check("independent_all_checks", independent["checks_passed"] == independent["checks_total"] and independent["checks_total"] >= 60, f"{independent['checks_passed']}/{independent['checks_total']}")
    check("production_no_go", production["status"] == "DEV_NO_GO_TEST_UNTOUCHED" and not production["development_go"])
    check("independent_no_go", not independent["development_go_recomputed"])
    check("primary_gate_not_met", not production["primary_development_ok"] and not independent["primary_development_ok_recomputed"])
    check("sensitivity_not_stable", not production["sensitivity_signs_ok"] and not independent["sensitivity_signs_ok_recomputed"])
    check("test_predictions_absent", not production["test_predictions_generated"])
    check("test_metrics_absent", not production["test_metrics_generated"])
    check("test_untouched_independent", independent["test_untouched"])
    check("v1_gate_unchanged", not production["original_v1_gate_modified"] and not production["test_authorized_by_v1"])
    check("mechanism_not_passed", not production["mechanism_increment_pass"])
    check("generator_not_authorized", not production["generator_training_authorized"])
    check("development_n", production["data_audit"]["development_n"] == 131)
    check("development_original_splits", production["data_audit"]["development_original_split_counts"] == {"train": 98, "dev": 33})
    check("test_n_excluded", production["data_audit"]["frozen_test_n_excluded"] == 33)
    check("test_ids_not_emitted", not production["data_audit"]["test_construct_ids_emitted"])
    check("prediction_tolerance", independent["max_numeric_deltas"]["prediction"] <= 1e-9, independent["max_numeric_deltas"]["prediction"])
    check("metric_tolerance", independent["max_numeric_deltas"]["metric"] <= 1e-10, independent["max_numeric_deltas"]["metric"])
    check("inference_tolerance", independent["max_numeric_deltas"]["inference"] <= 1e-10, independent["max_numeric_deltas"]["inference"])
    check("inner_selection_tolerance", independent["max_numeric_deltas"]["inner_rmse"] <= 1e-9, independent["max_numeric_deltas"]["inner_rmse"])
    test_log = Path(args.production).with_name("mage_development_nested_cv_unit_tests.console.log")
    initial_log = Path(args.production).with_name("mage_development_nested_cv_unit_tests_initial_failure.console.log")
    check("unit_tests_12_pass", test_log.exists() and "Ran 12 tests" in test_log.read_text() and "OK" in test_log.read_text())
    check("initial_test_failure_preserved", initial_log.exists() and "FileNotFoundError" in initial_log.read_text())
    check("production_commit_recorded", independent["git_head_at_verification"] == "b6f9f09c9873cab7af4d8b321f2bd9a452fbb8d7")
    check("primary_comparisons_complete", set(production["primary_comparisons"]) == {"full_mechanism_minus_intrinsic", "full_mechanism_minus_local_mfe"})
    check("two_sensitivity_repeats", set(production["sensitivity"]) == {"40261120", "40261121"})
    check("bootstrap_replicates", all(v["bootstrap_replicates"] == 20000 for v in production["primary_comparisons"].values()))
    check("permutation_replicates", all(v["permutation_replicates"] == 20000 for v in production["primary_comparisons"].values()))
    result = {
        "schema": "a8-rk03-mage-development-nested-cv-finalization-v2",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "checks": checks,
        "checks_passed": sum(c["pass"] for c in checks),
        "checks_total": len(checks),
        "scientific_outcome": "MAGE_DEVELOPMENT_MECHANISM_INCREMENT_NOT_SUPPORTED",
        "scope": "fixed_infA_synonymous_development_nested_cv_only",
        "development_n": 131,
        "test_n_untouched": 33,
        "development_go": False,
        "rk_g1_pass": False,
        "expensive_generation_authorized": False,
        "functional_untouched_evaluated": False,
        "manuscript_submittable": False,
        "primary_models": production["primary_models"],
        "primary_comparisons": production["primary_comparisons"],
        "sensitivity_comparisons": {seed: values["comparisons"] for seed, values in production["sensitivity"].items()},
        "evidence": {
            "protocol": {"path": str(Path(args.config).resolve()), "sha256": sha256(args.config)},
            "production": {"path": str(Path(args.production).resolve()), "sha256": sha256(args.production)},
            "independent": {"path": str(Path(args.independent).resolve()), "sha256": sha256(args.independent)},
            "production_script_sha256": independent["production_script_sha256"],
        },
        "git_head_at_independent_verification": independent["git_head_at_verification"],
        "conclusion": "Nested development CV did not support a stable full-mechanism increment over intrinsic or local-MFE baselines. The original v1 NO-GO stands, the 33-construct test remains untouched, and no generator training is authorized.",
    }
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({"status": result["status"], "checks": f"{result['checks_passed']}/{result['checks_total']}", "scientific_outcome": result["scientific_outcome"]}, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
