#!/usr/bin/env python3
"""Finalize the independently verified RK-13 seven-method science package."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

A7_SHA256 = "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ensemble-protocol", type=Path, required=True)
    parser.add_argument("--ensemble-report", type=Path, required=True)
    parser.add_argument("--ensemble-independent", type=Path, required=True)
    parser.add_argument("--matrix-protocol", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--matrix-independent", type=Path, required=True)
    parser.add_argument("--a7", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    ensemble_protocol = json.loads(args.ensemble_protocol.read_text())
    ensemble = json.loads(args.ensemble_report.read_text())
    ensemble_independent = json.loads(args.ensemble_independent.read_text())
    matrix_protocol = json.loads(args.matrix_protocol.read_text())
    matrix = json.loads(args.matrix.read_text())
    matrix_independent = json.loads(args.matrix_independent.read_text())
    checks = []

    def record(name, passed, evidence=None):
        checks.append({"check": name, "pass": bool(passed), "evidence": evidence})

    record("ensemble_protocol_schema", ensemble_protocol["schema"] == "a8-rk13-ensembledesign-unique18-v1" and ensemble_protocol["status"] == "FROZEN_BEFORE_EXECUTION")
    record("ensemble_complete", ensemble["status"] == "COMPLETE_UNIQUE18_OFFICIAL_ENSEMBLEDESIGN_11RUN" and ensemble["record_count"] == 18 and ensemble["run_count"] == 198)
    record("ensemble_protocol_hash", ensemble["protocol_sha256"] == sha256(args.ensemble_protocol))
    record("ensemble_independent_pass", ensemble_independent["status"] == "PASS" and not ensemble_independent["failures"])
    record("ensemble_independent_binding", ensemble_independent["report_sha256"] == sha256(args.ensemble_report) and ensemble_independent["run_count"] == 198)
    record("ensemble_identity_and_efe", ensemble["all_payload_metrics_verified"] is True and ensemble["official_source_unmodified"] is True and ensemble_independent["max_efe_abs_delta_from_rounded_official"] <= 0.051, ensemble_independent["max_efe_abs_delta_from_rounded_official"])
    record("ensemble_recovery_chain", ensemble["recovery"]["failed_attempt_preserved"] is True and ensemble["recovery"]["failed_outputs_overwritten"] is False and ensemble["recovery"]["tolerance_changed"] is False and ensemble["recovery"]["total_official_process_count_including_failed_attempt"] == 25 and ensemble["recovery"]["total_generator_run_count_including_failed_attempt"] == 209 and ensemble_independent["recovery_protocol_sha256"] == ensemble["recovery"]["recovery_protocol_sha256"] and ensemble_independent["failed_report_sha256"] == ensemble["recovery"]["failed_report_sha256"] and ensemble_independent["independent_efe_method"] == "mfe_then_exp_params_rescale_then_pf")
    record("matrix_protocol_schema", matrix_protocol["schema"] == "a8-rk13-seven-method-actual-set-matrix-v1" and len(matrix_protocol["primary_comparators"]) == 6)
    record("matrix_complete", matrix["status"] == "COMPLETE_UNIQUE18_SEVEN_METHOD_ACTUAL_SET_MATRIX_DEVELOPMENT_ONLY" and len(matrix["records"]) == 18)
    record("matrix_protocol_hash", matrix["protocol_sha256"] == sha256(args.matrix_protocol))
    record("matrix_method_order", all(list(r["methods"]) == matrix_protocol["method_order"] for r in matrix["records"]))
    record("matrix_base_hash", matrix["base_matrix_sha256"] == matrix_protocol["base_matrix_sha256"] == sha256(Path(matrix_protocol["base_matrix"])))
    record("matrix_base_independent", matrix["base_independent_sha256"] == matrix_protocol["base_independent_sha256"] and matrix["base_finalization_sha256"] == matrix_protocol["base_finalization_sha256"])
    record("matrix_added_evidence_hashes", matrix["ensemble_report_sha256"] == sha256(args.ensemble_report) and matrix["ensemble_independent_sha256"] == sha256(args.ensemble_independent))
    record("matrix_independent_pass", matrix_independent["status"] == "PASS" and matrix_independent["checks_passed"] == matrix_independent["checks_total"] and not matrix_independent["failed_checks"], f"{matrix_independent['checks_passed']}/{matrix_independent['checks_total']}")
    record("matrix_independent_binding", matrix_independent["matrix_sha256"] == sha256(args.matrix) and matrix_independent["protocol_sha256"] == sha256(args.matrix_protocol))
    record("matrix_numerical_exactness", matrix_independent["max_objective_recompute_delta"] <= 1e-9 and matrix_independent["max_hypervolume_recompute_delta"] <= 1e-9 and matrix_independent["max_ned_recompute_delta"] <= 1e-9)
    record("paired_family", len(matrix["primary_comparisons"]) == 12 and all("holm_p_twelve_primary" in item for item in matrix["primary_comparisons"].values()), len(matrix["primary_comparisons"]))
    record("base_methods_preserved", matrix["base_methods_copied_without_modification"] is True and matrix_independent["base_methods_evidence"].startswith("exact-field copy"))
    record("cost_boundaries", matrix["generation_cost_descriptive_not_time_matched"][matrix_protocol["added_method"]]["total_seconds"] == ensemble["total_generation_elapsed_s"] and matrix["time_matched_comparison"] is False)
    record("excluded_claims", ensemble["dense_budget_step_auc_v2"] is None and matrix["dense_budget_step_auc_v2"] is None and ensemble["scientific_gate_passed"] is False and matrix["scientific_gate_passed"] is False and ensemble["sota_claim"] is False and matrix["sota_claim"] is False)
    record("a7_unchanged", sha256(args.a7) == A7_SHA256)
    passed = sum(item["pass"] for item in checks)
    record_pairs = sum(record["unique_output_sequences"] for record in ensemble["records"])
    report = {
        "schema": "a8-rk13-finalization-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS_RK13_ENSEMBLEDESIGN_SEVEN_METHOD_MATRIX" if passed == len(checks) else "FAIL",
        "scope": "official EnsembleDesign unique18 actual-output generation and seven-method development matrix; main model, dense AUC, unified time-matched cost, OOD and SOTA remain open",
        "science_task_completion_authorized": passed == len(checks),
        "main_model_baseline_matrix_closed": False,
        "dense_budget_step_auc_v2": None,
        "time_matched_comparison": False,
        "functional_ood_closed": False,
        "sota_claim": False,
        "checks": checks,
        "checks_passed": passed,
        "checks_total": len(checks),
        "record_count": ensemble["record_count"],
        "run_count": ensemble["run_count"],
        "unique_output_sequences_global": record_pairs,
        "ensemble_unique_official_rna_sequences": ensemble["unique_output_sequences"],
        "ensemble_generation_seconds": ensemble["total_generation_elapsed_s"],
        "lineardesign_generation_seconds": matrix["generation_cost_descriptive_not_time_matched"]["lineardesign_lambda11"]["total_seconds"],
        "ensemble_sha256": sha256(args.ensemble_report),
        "ensemble_independent_sha256": sha256(args.ensemble_independent),
        "matrix_sha256": sha256(args.matrix),
        "matrix_independent_sha256": sha256(args.matrix_independent),
        "method_summary": matrix["method_summary"],
        "primary_comparisons": matrix["primary_comparisons"],
        "descriptive_highest_mean_hv_method": matrix["descriptive_highest_mean_hv_method"],
        "a7_sha256": sha256(args.a7),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in {"checks", "method_summary", "primary_comparisons"}}, indent=2))
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
