#!/usr/bin/env python3
"""Finalize VeloHARMO only as a bounded official-algorithm smoke."""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

FALSE_FIELDS = [
    "model_training", "publication_metrics_reproduced", "held_out_performance",
    "main_baseline_comparison", "dense_budget_complete", "matched_cost_comparison",
    "five_species_processed_matrices_complete", "functional_ood", "sota_claim",
]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_text(path, text):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".part.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def scope_failures(production, independent):
    failures = []
    if production.get("status") != "BOUNDED_OFFICIAL_ALGORITHM_EXECUTION_COMPLETE":
        failures.append("production status")
    if independent.get("status") != "PASS" or independent.get("passed_checks") != independent.get("check_count"):
        failures.append("independent verification")
    if independent.get("max_numeric_delta") != 0:
        failures.append("numeric reproducibility")
    if production.get("official_ga_unmodified", {}).get("executed_successfully") is not False:
        failures.append("unmodified GA failure flag")
    if production.get("bounded_ga", {}).get("start_to_best_improved") is not False:
        failures.append("zero-improvement result flag")
    if independent.get("ga_best_equals_start") is not True:
        failures.append("independent zero-improvement confirmation")
    for name in FALSE_FIELDS:
        if production.get(name) is not False:
            failures.append(name)
    for name in ["main_baseline_comparison", "functional_ood", "sota_claim"]:
        if independent.get(name) is not False:
            failures.append(f"independent:{name}")
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-report", type=Path, required=True)
    parser.add_argument("--independent-report", type=Path, required=True)
    parser.add_argument("--materialization-report", type=Path, required=True)
    parser.add_argument("--loader-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    production = json.loads(args.production_report.read_text())
    independent = json.loads(args.independent_report.read_text())
    materialization = json.loads(args.materialization_report.read_text())
    loader = json.loads(args.loader_report.read_text())
    checks = []

    def check(name, passed, detail):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    required = ["status", "source_commit", "matrix_sha256", "selected_records", "official_velogru_test",
                "official_ga_unmodified", "bounded_ga", "environment", "artifacts", *FALSE_FIELDS]
    check("production_schema_and_required_fields", all(key in production for key in required), required)
    identity = (production["source_commit"] == materialization["commit"] == loader["commit"]
                and production["materialization_sha256"] == sha(args.materialization_report)
                and production["matrix_sha256"] == loader["matrix_sha256"]
                and loader["status"] == "PASS_OFFICIAL_LOADER_ONLY")
    check("pinned_source_materialization_loader_identity", identity,
          {"commit": production["source_commit"], "loader_status": loader["status"]})
    test = production["official_velogru_test"]
    test_ok = (test["returncode"] == 0 and test["feature_dimension"] == 105 and test["records"] == 7
               and test["model_parameter_count"] == 477185 and test["device"] == "cuda:0"
               and test["metric_delta"] <= 1e-7 and test["diagnostic_only_not_held_out"] is True)
    check("official_test_raw_metrics_and_device", test_ok,
          {"mean": test["mean_pearson"], "std": test["std_pearson"], "metric_delta": test["metric_delta"]})
    ga = production["bounded_ga"]
    ga_ok = (production["official_ga_unmodified"]["expected_missing_module_failure"] is True
             and production["official_ga_unmodified"]["executed_successfully"] is False
             and production["official_ga_unmodified"]["returncode"] != 0
             and len(ga["patch"]) == 7 and ga["population_size"] == 8 and ga["generations"] == 2
             and ga["seed"] == 20261118 and ga["device"] == "cpu")
    check("unmodified_failure_and_seven_item_bounded_patch", ga_ok,
          {"population": ga["population_size"], "generations": ga["generations"], "patch_items": len(ga["patch"])})
    sequences = [ga["native_sequence"], ga["start_sequence"], ga["best_sequence"]]
    sequence_ok = (all(len(x) == 108 and len(x) % 3 == 0 and set(x) <= set("ACGT") for x in sequences)
                   and ga["start_sequence"] == ga["best_sequence"]
                   and ga["legal_synonymous_count"] == ga["candidate_count"] == 2
                   and ga["unique_sequence_count"] == 2 and ga["native_terminal_stop"] is False)
    check("bounded_sequence_identity_and_native_stop_contract", sequence_ok,
          {"codons": 36, "legal": "2/2", "unique": 2, "native_terminal_stop": False})
    negative = (ga["best_minus_start"] == 0 and ga["start_to_best_improved"] is False
                and independent["ga_start_to_best_improved"] is False and independent["ga_best_equals_start"] is True)
    check("zero_iteration_improvement_not_hidden", negative,
          {"native": ga["fitness"]["native"], "start": ga["fitness"]["start"], "best": ga["fitness"]["best"]})
    verification = (independent["check_count"] == independent["passed_checks"] == 17
                    and independent["status"] == "PASS" and independent["max_numeric_delta"] == 0
                    and independent["official_metric_delta"] == test["metric_delta"])
    check("independent_verification_fully_passed", verification,
          {"checks": "17/17", "max_numeric_delta": independent["max_numeric_delta"]})
    artifact_details = []
    artifacts_ok = True
    for name, item in production["artifacts"].items():
        path = Path(item["path"])
        match = path.exists() and path.stat().st_size == item["bytes"] and sha(path) == item["sha256"]
        artifacts_ok &= match
        artifact_details.append({"name": name, "match": match})
    for name, path_value in independent["independent_artifacts"].items():
        path = Path(path_value)
        match = path.exists() and path.stat().st_size > 0
        artifacts_ok &= match
        artifact_details.append({"name": f"independent:{name}", "match": match})
    check("raw_and_independent_artifact_hashes_present", artifacts_ok, artifact_details)
    environment = production["environment"]
    env_ok = (environment["python"] == "3.10.22" and environment["torch"] == "2.11.0+cu128"
              and environment["numpy"] == "2.2.6" and environment["ga_device"] == "cpu"
              and environment["official_test_device"] == "cuda:0"
              and environment["ga_deterministic_algorithms"] is True
              and environment["official_test_deterministic_algorithms"] is False)
    check("runtime_and_dual_device_environment_reconciled", env_ok, environment)
    failures = scope_failures(production, independent)
    check("bounded_scope_gate_and_no_overclaim", not failures, {"failures": failures})
    check("production_report_immutable", independent["production_report_sha256"] == sha(args.production_report),
          {"sha256": sha(args.production_report)})
    attempt_root = args.production_report.parents[2] / "RK05"
    check("failure_history_paths_preserved_in_handoff_scope",
          production["official_ga_unmodified"]["returncode"] == 1 and len(ga["patch"]) == 7,
          {"note": "Earlier failed attempt directories remain under /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ and are not rewritten."})
    check("task14_bounded_ready_not_full_rk05_or_rkg0",
          production["main_baseline_comparison"] is False and production["functional_ood"] is False,
          {"task14_scope": "bounded official baseline smoke", "RK05": "not closed", "RK-G0": "not closed"})
    passed = sum(item["pass"] for item in checks)
    report = {
        "schema_version": "a8-rk05-veloharmo-finalization-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "CLOSED_BOUNDED_OFFICIAL_SMOKE" if passed == len(checks) else "FINALIZATION_FAILED",
        "check_count": len(checks), "passed_checks": passed, "checks": checks,
        "production_report": str(args.production_report), "production_report_sha256": sha(args.production_report),
        "independent_report": str(args.independent_report), "independent_report_sha256": sha(args.independent_report),
        "official_test_device": "cuda:0", "ga_device": "cpu", "ga_best_equals_start": True,
        "main_baseline_comparison": False, "functional_ood": False, "sota_claim": False,
        "main_matrix_complete": False, "five_species_processed_matrices_complete": False,
        "task14_status": "bounded_closed_only", "RK05_status": "open", "RK-G0_status": "open",
    }
    write_text(args.output, json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "output": str(args.output)}))
    if report["status"] != "CLOSED_BOUNDED_OFFICIAL_SMOKE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
