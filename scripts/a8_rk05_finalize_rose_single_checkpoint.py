#!/usr/bin/env python3
"""Finalize ROSE evidence by independently reopening raw predictions and reports."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    log_loss,
    roc_auc_score,
)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, payload):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    os.replace(temporary, path)


def metrics(labels, probabilities):
    predicted = (probabilities >= 0.5).astype(np.int64)
    tn, fp, fn, tp = confusion_matrix(labels, predicted, labels=[0, 1]).ravel()
    prevalence = float(np.mean(labels))
    constant = np.full(len(labels), prevalence)
    return {
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "average_precision": float(average_precision_score(labels, probabilities)),
        "accuracy_at_0.5": float(accuracy_score(labels, predicted)),
        "balanced_accuracy_at_0.5": float(balanced_accuracy_score(labels, predicted)),
        "log_loss": float(log_loss(labels, probabilities, labels=[0, 1])),
        "brier_score": float(brier_score_loss(labels, probabilities)),
        "confusion_matrix_at_0.5": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "constant_prevalence_baseline": {
            "probability": prevalence,
            "roc_auc": 0.5,
            "average_precision": prevalence,
            "log_loss": float(log_loss(labels, constant, labels=[0, 1])),
            "brier_score": float(brier_score_loss(labels, constant)),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="/home/codonflow-a8-rk")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    audit = root / "audits/20261118/RK05"
    protocol_path = audit / "rose_official_single_checkpoint_protocol_v1.json"
    production_path = audit / "rose_official_single_checkpoint_v1.json"
    independent_path = audit / "rose_independent_verification_v4.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    production = json.loads(production_path.read_text(encoding="utf-8"))
    independent = json.loads(independent_path.read_text(encoding="utf-8"))
    checks = []

    def check(name, condition, details=None):
        checks.append({"name": name, "passed": bool(condition), "details": details})

    check("production_status", production["status"] == "PASS_COMPLETE_RELEASED_TEST_SINGLE_CHECKPOINT_INFERENCE")
    check("independent_status", independent["status"] == "PASS")
    check("independent_all_checks", independent["passed_count"] == independent["check_count"] and all(c["passed"] for c in independent["checks"]), "%d/%d" % (independent["passed_count"], independent["check_count"]))
    check("production_protocol_hash", production["protocol_sha256"] == sha256(protocol_path))
    check("independent_production_identity", independent["production_report_sha256"] == sha256(production_path))
    check("independent_driver_not_imported", independent["production_driver_imported"] is False)
    output_root = Path(production["execution"]["output_root"])
    check("protocol_raw_copy_byte_identical", sha256(output_root / "protocol.json") == sha256(protocol_path))
    check("production_raw_report_semantically_identical", json.loads((output_root / "production_report.copy.json").read_text(encoding="utf-8")) == production)
    production_log = output_root / "execution.log"
    production_log_text = production_log.read_text(encoding="utf-8", errors="replace")
    check("production_log_complete", "Pop14" in production_log_text and "Battle15" in production_log_text and "Traceback" not in production_log_text)
    independent_log = Path(independent["independent_output_root"]) / "execution.log"
    independent_log_text = independent_log.read_text(encoding="utf-8", errors="replace")
    check("independent_log_complete", '"status": "PASS"' in independent_log_text and "Traceback" not in independent_log_text)
    failure_specifications = [
        (1, "FAIL_VERIFIER_FLOAT32_FLOAT64_TOLERANCE", "probability_precision"),
        (2, "FAIL_VERIFIER_METRIC_PRECISION_TOLERANCE", "metric_precision"),
        (3, "FAIL_VERIFIER_AVERAGE_PRECISION_FLOAT32_TIES", "average_precision_precision"),
    ]
    for version, expected_status, suffix in failure_specifications:
        failure_path = audit / ("rose_independent_verification_v%d_failed_%s.json" % (version, suffix))
        failure = json.loads(failure_path.read_text(encoding="utf-8"))
        log_path = Path(failure["execution_log"]["path"])
        check("failed_attempt_%d_retained" % version, failure["status"] == expected_status and log_path.exists())
        check("failed_attempt_%d_log_hash" % version, sha256(log_path) == failure["execution_log"]["sha256"])
        check("failed_attempt_%d_science_unchanged" % version, failure["scientific_result_changed"] is False)
    source_root = Path(protocol["source"]["restored_root"])
    check("official_archive_hash", sha256(protocol["source"]["archive"]) == protocol["source"]["archive_sha256"])
    check("official_demo_hash", sha256(source_root / "script/demo_test.py") == protocol["source"]["official_demo_sha256"])
    study_summaries = {}
    for name, specification in protocol["studies"].items():
        study = production["studies"][name]
        independent_study = independent["studies"][name]
        model_dir = source_root / specification["relative_model_dir"]
        check(name + "_one_checkpoint_only", sorted(model_dir.glob("*.caffemodel")) == [model_dir / protocol["checkpoint_name"]])
        check(name + "_no_training_or_ensemble", study["training"] is False and study["checkpoint_count"] == 1 and study["forward_passes"] == 1)
        for artifact_name, artifact in study["artifacts"].items():
            path = Path(artifact["path"])
            check(name + "_artifact_" + artifact_name, path.exists() and path.stat().st_size == artifact["bytes"] and sha256(path) == artifact["sha256"])
        predictions_path = Path(study["artifacts"]["predictions"]["path"])
        with np.load(predictions_path, allow_pickle=False) as raw:
            labels = np.array(raw["labels"]).astype(np.int64)
            logits = np.array(raw["logits"])
            probabilities = np.array(raw["probabilities"]).astype(np.float64)
        check(name + "_full_prediction_shape", labels.shape == (specification["expected_records"],) and logits.shape == (specification["expected_records"], 2) and probabilities.shape == labels.shape)
        check(name + "_labels_complete_and_balanced", int(np.sum(labels == 1)) == specification["expected_positive"] and int(np.sum(labels == 0)) == specification["expected_negative"])
        check(name + "_finite_raw_outputs", bool(np.all(np.isfinite(logits)) and np.all(np.isfinite(probabilities))))
        recomputed_probabilities = np.divide(
            np.exp(logits[:, 1]),
            np.exp(logits[:, 0]) + np.exp(logits[:, 1]),
        ).astype(np.float64)
        check(name + "_official_probability_formula_exact", np.array_equal(recomputed_probabilities, probabilities))
        recomputed_metrics = metrics(labels, probabilities)
        scalar_keys = ["roc_auc", "average_precision", "accuracy_at_0.5", "balanced_accuracy_at_0.5", "log_loss", "brier_score"]
        metric_deltas = {key: abs(recomputed_metrics[key] - study["metrics"][key]) for key in scalar_keys}
        check(name + "_raw_prediction_metric_recompute", max(metric_deltas.values()) == 0.0, metric_deltas)
        check(name + "_confusion_matrix_recompute", recomputed_metrics["confusion_matrix_at_0.5"] == study["metrics"]["confusion_matrix_at_0.5"])
        check(name + "_independent_logits_exact", independent_study["logit_max_abs_delta"] == 0.0)
        check(name + "_independent_official_probability_exact", independent_study["production_float32_formula_max_abs_delta"] == 0.0)
        check(name + "_independent_stable_probability_rounding_bound", independent_study["probability_max_abs_delta"] <= 2e-7, independent_study["probability_max_abs_delta"])
        check(name + "_parameter_count", study["parameter_count"] == specification["expected_parameters"])
        check(name + "_complete_forward_recorded", study["timing_seconds"]["single_full_forward"] > 0 and study["metrics"]["roc_auc"] > 0.5)
        study_summaries[name] = {
            "records": int(len(labels)),
            "positive": int(np.sum(labels == 1)),
            "negative": int(np.sum(labels == 0)),
            "parameter_count": study["parameter_count"],
            "metrics": study["metrics"],
            "timing_seconds": study["timing_seconds"],
            "independent_logit_max_abs_delta": independent_study["logit_max_abs_delta"],
            "independent_stable_probability_max_abs_delta": independent_study["probability_max_abs_delta"],
            "raw_prediction_metric_abs_deltas": metric_deltas,
        }
    scope = production["scientific_scope"]
    check("scientific_boundaries", all([
        scope["not_continuous_velocity_regression"],
        scope["not_training"],
        scope["not_64_checkpoint_ensemble"],
        scope["not_protein_or_study_or_functional_ood"],
        scope["not_matched_cost_or_sota"],
        scope["not_raw_read_or_psite_remapping"],
        scope["not_codonflow_rk"],
    ]))
    passed = sum(item["passed"] for item in checks)
    report = {
        "schema_version": 1,
        "protocol_version": protocol["protocol_version"],
        "status": "PASS" if passed == len(checks) else "FAIL",
        "check_count": len(checks),
        "passed_count": passed,
        "checks": checks,
        "production_report": str(production_path),
        "production_report_sha256": sha256(production_path),
        "independent_report": str(independent_path),
        "independent_report_sha256": sha256(independent_path),
        "study_summaries": study_summaries,
        "scope": "ROSE released-test single-checkpoint binary-stalling inference is verified; training, 64-model ensemble, continuous velocity regression, OOD, matched-cost and SOTA remain unclaimed.",
    }
    write_json(args.report, report)
    print(json.dumps({"status": report["status"], "checks": "%d/%d" % (passed, len(checks)), "study_summaries": study_summaries}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
