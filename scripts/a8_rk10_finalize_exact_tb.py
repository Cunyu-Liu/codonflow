#!/usr/bin/env python3
"""Finalize exact trajectory-balance evidence after independent retraining and verification."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from a8_rk10_verify_exact_tb import (
    evaluate,
    reference_features,
    reference_geometry,
    reference_paths,
    reference_target,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: dict) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def bitwise_equal(first: np.ndarray, second: np.ndarray) -> bool:
    return first.shape == second.shape and first.dtype == second.dtype and np.array_equal(
        np.ascontiguousarray(first).view(np.uint64),
        np.ascontiguousarray(second).view(np.uint64),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-report", type=Path, required=True)
    parser.add_argument("--retrain-report", type=Path, required=True)
    parser.add_argument("--independent-report", type=Path, required=True)
    parser.add_argument("--unit-test-log", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"Nonempty output directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    production = load(args.production_report)
    retrain = load(args.retrain_report)
    independent = load(args.independent_report)
    protocol_path = Path(production["protocol"])
    protocol = load(protocol_path)
    prod_checkpoint_path = Path(production["checkpoint"])
    retrain_checkpoint_path = Path(retrain["checkpoint"])
    prod_checkpoint = np.load(prod_checkpoint_path)
    retrain_checkpoint = np.load(retrain_checkpoint_path)

    edges, reverse = reference_geometry()
    paths = reference_paths(edges, reverse)
    features = reference_features()
    beta = float(protocol["conditional_kernel"]["beta"])
    counts = np.bincount(paths["end"], minlength=3721).astype(np.float64)
    target = reference_target(features, edges, paths, protocol)
    retrain_metrics, _, _, _ = evaluate(
        retrain_checkpoint["theta"], retrain_checkpoint["backward_logits"],
        features, edges, paths, target, beta,
    )
    prod_metrics, _, _, _ = evaluate(
        prod_checkpoint["theta"], prod_checkpoint["backward_logits"],
        features, edges, paths, target, beta,
    )

    checks = []

    def check(name: str, condition: bool, detail: object) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("production_pass", production["status"] == "PASS" and production["checks_passed"] == production["checks_total"], production["status"])
    check("retrain_pass", retrain["status"] == "PASS" and retrain["checks_passed"] == retrain["checks_total"], retrain["status"])
    check("independent_pass", independent["status"] == "PASS" and independent["checks_passed"] == independent["checks_total"] and independent["production_driver_imported"] is False, independent["status"])
    check("protocol_identity", production["protocol_sha256"] == retrain["protocol_sha256"] == sha256(protocol_path), production["protocol_sha256"])
    train_implementation = Path(__file__).resolve().with_name("a8_rk10_train_exact_tb.py")
    verifier_implementation = Path(__file__).resolve().with_name("a8_rk10_verify_exact_tb.py")
    check("training_implementation_identity", production["implementation_sha256"] == retrain["implementation_sha256"] == sha256(train_implementation), production["implementation_sha256"])
    check("independent_implementation_identity", independent["implementation_sha256"] == sha256(verifier_implementation), independent["implementation_sha256"])
    check("production_checkpoint_hash", sha256(prod_checkpoint_path) == production["checkpoint_sha256"] == independent["checkpoint_sha256"], production["checkpoint_sha256"])
    check("retrain_checkpoint_hash", sha256(retrain_checkpoint_path) == retrain["checkpoint_sha256"], retrain["checkpoint_sha256"])
    check("independent_production_hash", sha256(args.production_report) == independent["production_report_sha256"], independent["production_report_sha256"])
    check("theta_bitwise_equal", bitwise_equal(prod_checkpoint["theta"], retrain_checkpoint["theta"]), {"production": prod_checkpoint["theta"].tolist(), "retrain": retrain_checkpoint["theta"].tolist()})
    check("backward_bitwise_equal", bitwise_equal(prod_checkpoint["backward_logits"], retrain_checkpoint["backward_logits"]), {"shape": prod_checkpoint["backward_logits"].shape})
    check("history_identical", production["history"] == retrain["history"], {"production_rows": len(production["history"]), "retrain_rows": len(retrain["history"])})
    check("production_independent_metrics", all(abs(prod_metrics[key] - independent["metrics"][key]) <= 1e-12 for key in prod_metrics), prod_metrics)
    check("retrain_report_metrics", all(abs(retrain_metrics[key] - retrain["metrics"][key]) <= 1e-12 for key in retrain_metrics), retrain_metrics)
    check("retrain_independent_metrics", all(abs(retrain_metrics[key] - prod_metrics[key]) <= 1e-12 for key in retrain_metrics), retrain_metrics)
    acceptance = protocol["acceptance"]
    check("retrain_acceptance", retrain_metrics["loss"] <= acceptance["final_loss_max"] and retrain_metrics["max_abs_path_residual"] <= acceptance["max_abs_path_residual_max"] and retrain_metrics["max_abs_endpoint_reconstruction_error"] <= acceptance["max_abs_endpoint_reconstruction_error_max"] and retrain_metrics["max_abs_forward_target_error"] <= acceptance["max_abs_forward_target_error_max"] and retrain_metrics["forward_target_kl"] <= acceptance["forward_target_kl_max"], retrain_metrics)
    check("analytic_oracle", independent["analytic_oracle"]["max_abs_residual"] <= 1e-12 and independent["analytic_oracle"]["max_abs_forward_target_error"] <= 1e-12 and independent["analytic_oracle"]["max_abs_backward_normalization_error"] <= 1e-12, independent["analytic_oracle"])
    check("unit_tests", args.unit_test_log.exists() and "10 passed" in args.unit_test_log.read_text(encoding="utf-8"), str(args.unit_test_log))
    check("geometry_and_paths", len(paths["end"]) == 14641 and edges.shape == (3721, 121) and np.all(counts > 0), {"paths": len(paths["end"]), "minimum_endpoint_paths": int(counts.min())})
    check("mathematical_scope_only", all(production[key] is False and retrain[key] is False for key in ("biological_reward_measured", "functional_or_generation_performance_evaluated", "full_neural_model_trained", "rk_g1_gate_modified", "expensive_generation_authorized", "sota_claimed")), production["scope"])
    status = "PASS_COMPLETE_WITH_INDEPENDENT_RETRAIN_AND_ANALYTIC_ORACLE" if all(row["pass"] for row in checks) else "FAIL"
    report = {
        "schema_version": "a8-rk10-exact-trajectory-balance-finalization-v1",
        "status": status,
        "production_report": str(args.production_report),
        "production_report_sha256": sha256(args.production_report),
        "retrain_report": str(args.retrain_report),
        "retrain_report_sha256": sha256(args.retrain_report),
        "independent_report": str(args.independent_report),
        "independent_report_sha256": sha256(args.independent_report),
        "protocol_sha256": sha256(protocol_path),
        "production_checkpoint_sha256": sha256(prod_checkpoint_path),
        "retrain_checkpoint_sha256": sha256(retrain_checkpoint_path),
        "theta_bitwise_equal": bitwise_equal(prod_checkpoint["theta"], retrain_checkpoint["theta"]),
        "backward_logits_bitwise_equal": bitwise_equal(prod_checkpoint["backward_logits"], retrain_checkpoint["backward_logits"]),
        "production_metrics": prod_metrics,
        "retrain_metrics": retrain_metrics,
        "analytic_oracle": independent["analytic_oracle"],
        "checks": checks,
        "checks_passed": sum(row["pass"] for row in checks),
        "checks_total": len(checks),
        "biological_reward_measured": False,
        "functional_or_generation_performance_evaluated": False,
        "full_neural_model_trained": False,
        "rk_g1_gate_modified": False,
        "expensive_generation_authorized": False,
        "sota_claimed": False,
        "scope": protocol["scope"],
    }
    atomic_json(args.report, report)
    print(json.dumps({"status": status, "checks": f"{report['checks_passed']}/{report['checks_total']}", "production_metrics": prod_metrics, "retrain_metrics": retrain_metrics}, indent=2))
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
