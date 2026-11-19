#!/usr/bin/env python3
"""Finalize the independently verified RiboMIMO cross-study baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--production", required=True)
    parser.add_argument("--independent", required=True)
    parser.add_argument("--verification", required=True)
    parser.add_argument("--unit-tests", required=True)
    parser.add_argument("--production-console", required=True)
    parser.add_argument("--independent-console", required=True)
    parser.add_argument("--verification-script", required=True)
    parser.add_argument("--driver", required=True)
    parser.add_argument("--frozen-code-commit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    paths = {key: Path(getattr(args, key)).resolve() for key in ("protocol", "production", "independent", "verification", "unit_tests", "production_console", "independent_console", "verification_script", "driver")}
    protocol = json.loads(paths["protocol"].read_text())
    production = json.loads(paths["production"].read_text())
    independent = json.loads(paths["independent"].read_text())
    verification = json.loads(paths["verification"].read_text())
    unit = json.loads(paths["unit_tests"].read_text())
    checks = []

    def check(name: str, condition: bool, evidence=None) -> None:
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})

    check("unit_tests_pass", unit["status"] == "PASS" and unit["tests_run"] == 10 and unit["failures"] == 0 and unit["errors"] == 0)
    check("production_pass_pending_independent", production["status"] == "PASS_STUDY_OOD_PENDING_INDEPENDENT")
    check("independent_retrain_complete", independent["status"] == "PASS_STUDY_OOD_PENDING_INDEPENDENT" and len(independent["runs"]) == 3)
    check("independent_verifier_pass", verification["status"] == "PASS_RK05_RIBOMIMO_STUDY_OOD_INDEPENDENT" and verification["n_checks"] == verification["n_passed"], {"passed": verification["n_passed"], "total": verification["n_checks"]})
    check("production_report_hash_bound", verification["production_report"]["sha256"] == sha256(paths["production"]))
    check("independent_report_hash_bound", verification["independent_report"]["sha256"] == sha256(paths["independent"]))
    check("protocol_hash_bound", verification["protocol"]["sha256"] == sha256(paths["protocol"]) == production["protocol_sha256"] == independent["protocol_sha256"])
    check("driver_hash_bound", verification["driver"]["sha256"] == sha256(paths["driver"]) == production["prepare"]["driver_sha256"] == independent["prepare"]["driver_sha256"])
    check("three_frozen_seeds", [run["seed"] for run in production["runs"]] == [1234, 2345, 3456] == [run["seed"] for run in independent["runs"]])
    check("official_source_commit", production["source"]["commit"] == "094c693d4df45f4b29f5a3209b31c452a39092a5")
    check("seven_compatibility_changes_only", production["compatibility"]["replacement_count"] == 7 and production["compatibility"]["algorithm_changed"] is False)
    check("source_target_sizes", production["runs"][0]["source_train_records"] == 1062 and production["runs"][0]["source_validation_records"] == 117 and production["runs"][0]["target_records"] == 3921)
    check("exact_cds_disjoint", all(run["exact_cds_overlap_source_target"] == 0 for run in production["runs"]))
    check("target_not_used_for_epoch_evaluation", all(run["target_evaluated_after_training_and_ridge_selection"] for run in production["runs"]))
    check("model_predictions_reproduced_exactly", verification["details"]["max_differences"]["model_independent_retrain"] == 0.0)
    check("ridge_predictions_reproduced_within_declared_solver_tolerance", verification["details"]["max_differences"]["ridge_independent_retrain"] <= verification["details"]["max_differences"]["ridge_independent_absolute_tolerance"] == 1e-6, {"max_abs_difference": verification["details"]["max_differences"]["ridge_independent_retrain"], "absolute_tolerance": 1e-6})
    check("raw_ridge_refit_within_declared_solver_tolerance", verification["details"]["max_differences"]["ridge_raw_refit"] <= verification["details"]["max_differences"]["ridge_raw_refit_absolute_tolerance"] == 1e-6, {"max_abs_difference": verification["details"]["max_differences"]["ridge_raw_refit"], "absolute_tolerance": 1e-6})
    primary_recompute_match = len(verification["primary_comparisons_recomputed"]) == 2
    for reported, recomputed in zip(production["primary_comparisons"], verification["primary_comparisons_recomputed"]):
        primary_recompute_match = primary_recompute_match and all(reported[key] == recomputed[key] for key in ("metric", "direction", "n_pairs"))
        primary_recompute_match = primary_recompute_match and all(abs(float(reported[key]) - float(recomputed[key])) <= 1e-12 for key in ("point_delta_ribomimo_minus_ridge", "ci95_low", "ci95_high", "sign_flip_pvalue", "holm_pvalue"))
    check("primary_inference_recomputed", primary_recompute_match)
    check("two_primary_endpoints_only", len(production["primary_comparisons"]) == 2)
    check("production_console_nonempty", paths["production_console"].is_file() and paths["production_console"].stat().st_size > 0)
    check("independent_console_nonempty", paths["independent_console"].is_file() and paths["independent_console"].stat().st_size > 0)
    check("production_console_no_traceback", "Traceback" not in paths["production_console"].read_text())
    check("independent_console_no_traceback", "Traceback" not in paths["independent_console"].read_text())
    driver_at_commit = subprocess.run(["git", "show", f"{args.frozen_code_commit}:scripts/a8_rk05_ribomimo_study_ood.py"], capture_output=True, check=True).stdout
    protocol_at_commit = subprocess.run(["git", "show", f"{args.frozen_code_commit}:configs/a8_rk05_ribomimo_study_ood_protocol_v1.json"], capture_output=True, check=True).stdout
    check("driver_frozen_in_git", hashlib.sha256(driver_at_commit).hexdigest() == sha256(paths["driver"]))
    check("protocol_frozen_in_git", hashlib.sha256(protocol_at_commit).hexdigest() == sha256(paths["protocol"]))
    check("no_rk_g1_change", production["scientific_scope"]["rk_g1_change_authorized"] is False)
    check("no_generation_authorization", production["scientific_scope"]["generation_authorized"] is False)
    check("no_sota_claim", production["scientific_scope"]["sota_claim"] is False)
    check("no_functional_or_homology_claim", production["scientific_scope"]["functional_ood_claim"] is False and production["scientific_scope"]["homology_ood_claim"] is False)
    check("not_globally_untouched_confirmation", production["scientific_scope"]["new_untouched_scientific_confirmation"] is False)

    endpoints = production["primary_comparisons"]
    favorable = []
    significant = []
    for endpoint in endpoints:
        delta = endpoint["point_delta_ribomimo_minus_ridge"]
        low, high = endpoint["ci95_low"], endpoint["ci95_high"]
        if endpoint["metric"] == "transcript_balanced_mse":
            favorable.append(delta < 0)
            significant.append(high < 0 and endpoint["holm_pvalue"] < 0.05)
        else:
            favorable.append(delta > 0)
            significant.append(low > 0 and endpoint["holm_pvalue"] < 0.05)
    if all(significant):
        outcome = "RIBOMIMO_STUDY_OOD_SIGNIFICANTLY_OUTPERFORMS_RIDGE_ON_BOTH_PRIMARY_ENDPOINTS"
    elif all(low <= 0 <= high for low, high in ((endpoint["ci95_low"], endpoint["ci95_high"]) for endpoint in endpoints)):
        outcome = "RIBOMIMO_STUDY_OOD_BOTH_PRIMARY_EFFECTS_INCONCLUSIVE"
    else:
        outcome = "RIBOMIMO_STUDY_OOD_NO_UNIFORM_SIGNIFICANT_ADVANTAGE_OVER_RIDGE"
    seed_summary = []
    for run in production["runs"]:
        seed_summary.append({
            "seed": run["seed"], "best_epoch": run["best_epoch"], "ridge_alpha": run["ridge_selected_alpha"],
            "ribomimo": run["target_metrics"]["ribomimo"], "ridge": run["target_metrics"]["ridge"],
        })
    passed = sum(item["pass"] for item in checks)
    report = {
        "schema_version": "a8-rk05-ribomimo-study-ood-finalization-v1",
        "status": "PASS_RK05_RIBOMIMO_STUDY_OOD" if passed == len(checks) else "FAIL",
        "n_checks": len(checks), "n_passed": passed, "checks": checks,
        "scientific_outcome": outcome,
        "primary_seed": 1234,
        "primary_endpoints": endpoints,
        "seed_sensitivity": seed_summary,
        "closed_scope": "Official RiboMIMO Mohammad16-to-Subtelny14 exact-CDS-disjoint study-OOD evaluation versus source-fitted ridge and constant baselines, with three-seed independent retraining and raw-data/statistical verification.",
        "open_scope": {
            "homology_aware_protein_ood": False,
            "functional_ood": False,
            "physical_velocity_measurement": False,
            "time_matched_unified_cost": False,
            "full_baseline_program": False,
            "generator_training_authorized": False,
            "rk_g1_changed": False
        },
        "hashes": {key: {"path": str(path), "sha256": sha256(path)} for key, path in paths.items()},
        "verification_script_sha256": sha256(paths["verification_script"]),
        "frozen_code_commit": args.frozen_code_commit,
        "artifacts": {
            "production_combined_matrix": production["artifacts"]["combined_matrix"],
            "independent_combined_matrix": independent["artifacts"]["combined_matrix"],
            "production_predictions": [{"seed": run["seed"], "path": run["target_predictions"], "arrays_sha256": run["target_predictions_arrays_sha256"]} for run in production["runs"]],
            "independent_predictions": [{"seed": run["seed"], "path": run["target_predictions"], "arrays_sha256": run["target_predictions_arrays_sha256"]} for run in independent["runs"]]
        }
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "scientific_outcome": outcome, "primary": endpoints}, indent=2))
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
