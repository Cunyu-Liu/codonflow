#!/usr/bin/env python3
"""Finalize RK04 sequence-OOD models after independent and repeated-run checks."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--retrain-summary", type=Path, required=True)
    parser.add_argument("--prior-summary", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--unit-test-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    a = json.loads(args.summary.read_text())
    b = json.loads(args.retrain_summary.read_text())
    prior = json.loads(args.prior_summary.read_text())
    independent = json.loads(args.independent.read_text())
    checks = []
    def check(name, condition):
        checks.append({"name": name, "pass": bool(condition)})
    check("production_pending", a["status"] == b["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION")
    check("independent_pass", independent["status"] == "PASS" and independent["checks_passed"] == independent["checks_total"])
    check("same_protocol", a["protocol_sha256"] == b["protocol_sha256"] == independent["protocol_sha256"] == hashlib.sha256(args.protocol.read_bytes()).hexdigest())
    check("same_production_code", a["production_code_sha256"] == b["production_code_sha256"] == independent["production_script_sha256"])
    check("independent_summary_identity", independent["summary_sha256"] == sha256_file(args.summary))
    check("same_primary_family", a["primary_family"] == b["primary_family"] == independent["primary_family"])
    check("constant_fix_preserves_selection_and_nonconstant_results",
          a["selected"] == prior["selected"]
          and {f: m for f, m in a["test_metrics"].items() if f != "constant"} == {f: m for f, m in prior["test_metrics"].items() if f != "constant"}
          and {f: m for f, m in a["sequence_ood_metrics"].items() if f != "constant"} == {f: m for f, m in prior["sequence_ood_metrics"].items() if f != "constant"}
          and a["primary_comparison"] == prior["primary_comparison"])
    check("constant_correlations_are_null", all(
        a[partition]["constant"][metric] is None
        for partition in ["test_metrics", "sequence_ood_metrics"]
        for metric in ["row_pearson", "row_spearman", "cluster_mean_pearson", "cluster_mean_spearman", "within_cluster_centered_spearman"]
    ))
    check("constant_fix_preserves_error_metrics", all(
        a[partition]["constant"][metric] == prior[partition]["constant"][metric]
        for partition in ["test_metrics", "sequence_ood_metrics"]
        for metric in ["row_mse", "row_r2", "cluster_balanced_mse"]
    ))
    for artifact in ["metrics", "dev_model_selection", "predictions"]:
        check("repeat_identical_" + artifact, a["artifacts"][artifact]["sha256"] == b["artifacts"][artifact]["sha256"] == independent[artifact + "_sha256"])
    check("selected_models_reloaded_with_zero_delta", independent["max_model_prediction_abs_delta"] <= 1e-12)
    check("untouched_excluded", a["untouched_rows_excluded"] == b["untouched_rows_excluded"] == independent["untouched_rows_excluded"] == 19072)
    check("no_untouched_evaluation", not a["functional_untouched_evaluated"] and not independent["functional_untouched_evaluated"])
    check("sequence_ood_actually_evaluated", independent["sequence_ood_evaluated"] is True)
    check("scope_proxy_only", not independent["generator_training_authorized"] and not independent["sota_claim"])
    test_log = args.unit_test_log.read_text()
    check("unit_tests_12_pass", "Ran 12 tests" in test_log and "\nOK\n" in test_log)
    passed = sum(c["pass"] for c in checks)
    report = {
        "schema_version": "a8-rk04-sequence-ood-model-finalization-v1",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "checks_passed": passed, "checks_total": len(checks), "checks": checks,
        "failed": [c["name"] for c in checks if not c["pass"]],
        "protocol_id": protocol["protocol_id"], "protocol_sha256": hashlib.sha256(args.protocol.read_bytes()).hexdigest(),
        "production_summary": str(args.summary.resolve()), "production_summary_sha256": sha256_file(args.summary),
        "retrain_summary": str(args.retrain_summary.resolve()), "retrain_summary_sha256": sha256_file(args.retrain_summary),
        "prior_constant_correlation_artifact_summary": str(args.prior_summary.resolve()),
        "prior_constant_correlation_artifact_summary_sha256": sha256_file(args.prior_summary),
        "independent_verification": str(args.independent.resolve()), "independent_verification_sha256": sha256_file(args.independent),
        "unit_test_log": str(args.unit_test_log.resolve()), "unit_test_log_sha256": sha256_file(args.unit_test_log),
        "primary_family": a["primary_family"],
        "repeated_run_predictions_metrics_selection_identical": passed == len(checks),
        "functional_untouched_evaluated": False, "sequence_ood_evaluated": True,
        "generator_training_authorized": False, "fixed_protein_synonymous_mechanism_claim": False,
        "sota_claim": False, "wet_lab_claim": False,
        "scope": "Boël nonsynonymous proxy prediction; retained cluster-disjoint test and sequence-OOD only.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + f".part.{os.getpid()}")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.output)
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "failed": report["failed"]}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
