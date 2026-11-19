#!/usr/bin/env python3
"""Close RK-11 only after tests, independent inference and full retrain pass."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--production-artifacts", required=True, type=Path)
    parser.add_argument("--retrain-artifacts", required=True, type=Path)
    parser.add_argument("--production-report", required=True, type=Path)
    parser.add_argument("--retrain-report", required=True, type=Path)
    parser.add_argument("--independent-report", required=True, type=Path)
    parser.add_argument("--independent-initial-failure", required=True, type=Path)
    parser.add_argument("--independent-second-failure", required=True, type=Path)
    parser.add_argument("--development-report", required=True, type=Path)
    parser.add_argument("--test-log", required=True, type=Path)
    parser.add_argument("--initial-failure-log", required=True, type=Path)
    parser.add_argument("--second-failure-log", required=True, type=Path)
    parser.add_argument("--model-source", required=True, type=Path)
    parser.add_argument("--training-script", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text()); protocol_sha = sha256(args.protocol)
    production = json.loads(args.production_report.read_text())
    retrain = json.loads(args.retrain_report.read_text())
    independent = json.loads(args.independent_report.read_text())
    independent_initial = json.loads(args.independent_initial_failure.read_text())
    independent_second = json.loads(args.independent_second_failure.read_text())
    development = json.loads(args.development_report.read_text())
    test_text = args.test_log.read_text(errors="replace")
    initial_failure = args.initial_failure_log.read_text(errors="replace")
    second_failure = args.second_failure_log.read_text(errors="replace")
    arrays = ("candidates", "potentials", "cost", "allowed", "log_probabilities", "delta_phi", "delta_cost")
    checks = {
        "production_complete": production["status"] == "PASS_MINIMAL_NEURAL_SYNTHETIC_CUDA_CONTRACT" and production["checks_passed"] == production["checks_total"],
        "retrain_complete": retrain["status"] == "PASS_MINIMAL_NEURAL_SYNTHETIC_CUDA_CONTRACT" and retrain["checks_passed"] == retrain["checks_total"],
        "independent_complete": independent["status"] == "PASS_INDEPENDENT_MINIMAL_NEURAL" and independent["checks_passed"] == independent["checks_total"],
        "independent_initial_failure_preserved": independent_initial["status"] == "FAIL_INDEPENDENT_MINIMAL_NEURAL" and independent_initial["checks_passed"] == 24 and independent_initial["checks_total"] == 27,
        "independent_second_failure_preserved": independent_second["status"] == "FAIL_INDEPENDENT_MINIMAL_NEURAL" and independent_second["checks_passed"] == 25 and independent_second["checks_total"] == 27,
        "final_unit_tests_passed": "10 passed" in test_text,
        "initial_mapping_failure_preserved": "6 failed" in initial_failure,
        "second_test_setup_failure_preserved": "1 failed" in second_failure,
        "development_cuda_smoke_preserved": development["status"] == "PASS_MINIMAL_NEURAL_SYNTHETIC_CUDA_CONTRACT",
        "protocol_hash_consistent": production["protocol_sha256"] == retrain["protocol_sha256"] == independent["protocol_sha256"] == protocol_sha,
        "model_source_hash_consistent": production["code_sha256"]["model_source"] == retrain["code_sha256"]["model_source"] == sha256(args.model_source),
        "training_script_hash_consistent": production["code_sha256"]["training_script"] == retrain["code_sha256"]["training_script"] == sha256(args.training_script),
        "checkpoint_bytes_bitwise_equal": (args.production_artifacts / "checkpoint.pt").read_bytes() == (args.retrain_artifacts / "checkpoint.pt").read_bytes(),
        "state_tensors_bitwise_equal": independent["tensor_bitwise_equal"],
        "history_numeric_equal": independent["history_numeric_equal"],
        "kernel_arrays_bitwise_equal": independent["array_bitwise_equal"] and all((args.production_artifacts / f"{name}.npy").read_bytes() == (args.retrain_artifacts / f"{name}.npy").read_bytes() for name in arrays),
        "strict_loss_decrease": production["final_eval_loss"] < production["initial_eval_loss"],
        "probability_sum_within_frozen_tolerance": abs(production["probability_sum"] - 1.0) <= protocol["acceptance"]["probability_sum_abs_tolerance"],
        "budget_mask_has_zero_probability": production["masked_probability"] == 0.0 and production["budget_masked"] > 0,
        "candidate_accounting_complete": production["candidate_count"] == 9 and production["budget_allowed"] + production["budget_masked"] == 9,
        "kernel_gradient_finite_and_nonzero": production["kernel_gradient_finite"] and production["kernel_gradient_nonzero"],
        "independent_loss_recomputed": abs(independent["final_loss_recomputed"] - production["final_eval_loss"]) <= protocol["acceptance"]["independent_numeric_abs_tolerance"],
        "artifacts_on_team_storage": str(args.production_artifacts).startswith("/teams/HoulabData_1788502323/liucunyu/") and str(args.retrain_artifacts).startswith("/teams/HoulabData_1788502323/liucunyu/"),
        "synthetic_scope_and_no_generator_training": production["no_biological_training_data"] and production["no_full_generator_training"] and production["no_functional_untouched_access"],
        "forbidden_claims_retained": len(production["forbidden_claims"]) >= 6,
    }
    status = "PASS_COMPLETE_WITH_INDEPENDENT_RETRAIN_AND_CUDA_CONTRACT" if all(checks.values()) else "FAIL_MINIMAL_NEURAL_FINALIZATION"
    report = {
        "schema": "a8-rk11-minimal-neural-finalization-v1",
        "protocol_id": protocol["protocol_id"], "protocol_sha256": protocol_sha,
        "status": status, "checks": checks, "checks_passed": sum(checks.values()), "checks_total": len(checks),
        "production_status": production["status"], "retrain_status": retrain["status"], "independent_status": independent["status"],
        "unit_tests": "10 passed", "initial_failures_preserved": True, "second_failure_preserved": True, "independent_initial_failure_preserved": True, "independent_second_failure_preserved": True,
        "initial_eval_loss": production["initial_eval_loss"], "final_eval_loss": production["final_eval_loss"],
        "initial_unmasked_mse": production["initial_unmasked_mse"], "final_unmasked_mse": production["final_unmasked_mse"],
        "parameter_count": production["parameter_count"], "candidate_count": production["candidate_count"],
        "budget_allowed": production["budget_allowed"], "budget_masked": production["budget_masked"],
        "probability_sum": production["probability_sum"], "masked_probability": production["masked_probability"],
        "kernel_gradient_max_abs": production["kernel_gradient_max_abs"],
        "checkpoint_sha256": production["checkpoint_sha256"], "history_sha256": production["history_sha256"],
        "array_sha256": {name: production["arrays"][name]["sha256"] for name in arrays},
        "production_elapsed_seconds": production["elapsed_seconds"], "retrain_elapsed_seconds": retrain["elapsed_seconds"],
        "production_artifacts": str(args.production_artifacts), "retrain_artifacts": str(args.retrain_artifacts),
        "scientific_scope": protocol["scientific_scope"], "forbidden_claims": protocol["forbidden_claims"],
        "not_closed": ["RK-G0", "RK-G1", "functional/generation performance", "strong baseline main matrix", "OOD", "SOTA"],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True); args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": status, "checks": f"{report['checks_passed']}/{report['checks_total']}"}, indent=2))
    if status.startswith("FAIL"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
