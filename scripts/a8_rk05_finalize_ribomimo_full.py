#!/usr/bin/env python3
"""Finalize one full RiboMIMO reproduction after retrain and independent inference."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import torch
from scipy.stats import pearsonr
from sklearn.metrics import average_precision_score, mean_squared_error, r2_score, roc_auc_score


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dump_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def metrics(row: dict) -> dict:
    pred = row["pred"]
    target = row["target"]
    onehot = np.eye(3)[row["level"]]
    return {
        "r2": float(r2_score(target, pred)),
        "mse": float(mean_squared_error(target, pred)),
        "pearson": float(pearsonr(target, pred)[0]),
        "auc": float(roc_auc_score(onehot, row["pred_cls"])),
        "aupr": float(average_precision_score(onehot, row["pred_cls"])),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-report", required=True)
    parser.add_argument("--independent-report", required=True)
    parser.add_argument("--retrain-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    production_path = Path(args.production_report).resolve()
    independent_path = Path(args.independent_report).resolve()
    retrain_path = Path(args.retrain_report).resolve()
    output = Path(args.output_dir).resolve()
    report_path = Path(args.report).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output must be absent or empty: {output}")
    if report_path.exists():
        raise FileExistsError(f"Refusing to overwrite: {report_path}")
    output.mkdir(parents=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    checks = []

    def check(name: str, condition: bool, detail: object) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})
        if not condition:
            raise AssertionError(f"{name}: {detail}")

    production = json.loads(production_path.read_text())
    independent = json.loads(independent_path.read_text())
    retrain = json.loads(retrain_path.read_text())
    protocol = json.loads(Path(production["protocol"]["protocol_path"]).read_text())
    check("production_status", production["status"].startswith("PASS_COMPLETE_OFFICIAL_1X10FOLD_MAX100"), production["status"])
    check("independent_status", independent["status"] == "PASS", independent["status"])
    check("retrain_status", retrain["status"].startswith("PASS_COMPLETE_OFFICIAL_1X10FOLD_MAX100"), retrain["status"])
    check("independent_checks", independent["checks_total"] == independent["checks_passed"] == len(independent["checks"]) and all(row["pass"] for row in independent["checks"]), f"{independent['checks_passed']}/{independent['checks_total']}")
    check("production_identity", independent["production_report_sha256"] == sha256(production_path), independent["production_report_sha256"])
    check("protocol_same", production["protocol"]["protocol_sha256"] == retrain["protocol"]["protocol_sha256"] == sha256(production["protocol"]["protocol_path"]), production["protocol"]["protocol_sha256"])
    check("matrix_same", production["matrix"]["sha256"] == retrain["matrix"]["sha256"] == "d093a3b0c53aa90d0626cc277a65a558c538ecbeb4d1cda091f02aad134588bc", production["matrix"]["sha256"])
    check("official_protocol", production["protocol"]["num_fold"] == 10 and production["protocol"]["max_epoch"] == 100 and production["protocol"]["early_stop"] == 5 and production["protocol"]["seed"] == 1234, {key: production["protocol"][key] for key in ("num_fold", "max_epoch", "early_stop", "seed")})
    check("seven_replacements", production["compatibility"]["replacement_count"] == 7 and retrain["compatibility"]["replacement_count"] == 7, production["compatibility"])
    check("deterministic_cuda", production["environment"]["deterministic_algorithms"] is True and production["environment"]["cudnn_deterministic"] is True and production["environment"]["cudnn_benchmark"] is False and production["environment"]["cuda_available"] is True, production["environment"])
    check("retrain_deterministic_cuda", retrain["environment"]["deterministic_algorithms"] is True and retrain["environment"]["cudnn_deterministic"] is True and retrain["environment"]["cudnn_benchmark"] is False and retrain["environment"]["cuda_available"] is True, retrain["environment"])
    check("driver_import_boundary", independent["production_driver_imported"] is False, independent["production_driver_imported"])
    check("independent_forward_scope", independent["full_training_rerun"] is False and independent["two_forward_passes_per_fold"] is True, independent["two_forward_passes_per_fold"])

    for name, report in (("production", production), ("retrain", retrain)):
        for artifact, info in report["artifacts"].items():
            check(f"{name}_artifact:{artifact}", sha256(info["path"]) == info["sha256"], info["sha256"])
    production_root = Path(production["compatibility"]["diff_path"]).parent
    retrain_root = Path(retrain["compatibility"]["diff_path"]).parent
    production_prepare = json.loads((production_root / "prepare_report.json").read_text())
    retrain_prepare = json.loads((retrain_root / "prepare_report.json").read_text())
    check("same_driver", production_prepare["driver_sha256"] == retrain_prepare["driver_sha256"] == sha256(production_root / "driver.py") == sha256(retrain_root / "driver.py"), production_prepare["driver_sha256"])
    check("same_runtime_diff", production["compatibility"]["diff_sha256"] == retrain["compatibility"]["diff_sha256"], production["compatibility"]["diff_sha256"])

    checkpoint_deltas = {}
    for fold in range(10):
        production_ckpt = production["official_result"]["checkpoints"][str(fold)]
        retrain_ckpt = retrain["official_result"]["checkpoints"][str(fold)]
        check(f"production_checkpoint_hash:{fold}", sha256(production_ckpt["path"]) == production_ckpt["sha256"], production_ckpt["sha256"])
        check(f"retrain_checkpoint_hash:{fold}", sha256(retrain_ckpt["path"]) == retrain_ckpt["sha256"], retrain_ckpt["sha256"])
        production_state = torch.load(production_ckpt["path"], map_location="cpu", weights_only=True)
        retrain_state = torch.load(retrain_ckpt["path"], map_location="cpu", weights_only=True)
        check(f"retrain_state_keys:{fold}", production_state.keys() == retrain_state.keys(), list(production_state))
        deltas = []
        for key in production_state:
            a = production_state[key]
            b = retrain_state[key]
            check(f"retrain_tensor_shape:{fold}:{key}", a.shape == b.shape and a.dtype == b.dtype, str(a.shape))
            deltas.append(float(torch.max(torch.abs(a - b)).item()) if a.numel() else 0.0)
        max_delta = max(deltas, default=0.0)
        checkpoint_deltas[str(fold)] = max_delta
        check(f"retrain_tensor_bitwise:{fold}", max_delta == 0.0 and all(torch.equal(production_state[key], retrain_state[key]) for key in production_state), max_delta)
    check("retrain_aggregate_exact", production["official_result"]["aggregate"] == retrain["official_result"]["aggregate"], {"production": production["official_result"]["aggregate"], "retrain": retrain["official_result"]["aggregate"]})
    for fold in range(10):
        production_fold = production["official_result"]["folds"][fold]
        retrain_fold = retrain["official_result"]["folds"][fold]
        check(f"retrain_fold_exact:{fold}", production_fold["best_epoch"] == retrain_fold["best_epoch"] and production_fold["test_at_best_validation"] == retrain_fold["test_at_best_validation"], {"production": production_fold, "retrain": retrain_fold})

    independent_root = Path(independent["output_dir"])
    fold_recalculation = []
    all_test_genes = []
    for fold_row in independent["fold_results"]:
        fold = fold_row["fold"]
        prediction_path = Path(fold_row["prediction_file"])
        check(f"prediction_hash:{fold}", sha256(prediction_path) == fold_row["prediction_file_sha256"], fold_row["prediction_file_sha256"])
        with np.load(prediction_path, allow_pickle=False) as data:
            row = {key: data[key] for key in ("pred", "target", "pred_cls", "level", "codon_counts", "gene_ids", "constant_train_mean_pred")}
        check(f"prediction_shape:{fold}", row["pred"].ndim == 1 and row["target"].shape == row["pred"].shape and row["constant_train_mean_pred"].shape == row["pred"].shape and row["pred_cls"].shape == (len(row["pred"]), 3) and row["level"].shape == row["pred"].shape, {key: list(row[key].shape) for key in ("pred", "target", "pred_cls", "level")})
        check(f"prediction_finite:{fold}", all(np.all(np.isfinite(row[key])) for key in ("pred", "target", "pred_cls", "constant_train_mean_pred")), fold)
        check(f"prediction_targets_positive:{fold}", bool(np.all(row["target"] > 0)), float(np.min(row["target"])))
        check(f"prediction_levels:{fold}", bool(np.all((row["level"] >= 0) & (row["level"] <= 2))), np.unique(row["level"]).tolist())
        check(f"prediction_counts:{fold}", int(np.sum(row["codon_counts"])) == len(row["pred"]) == fold_row["valid_masked_codons"] and len(row["codon_counts"]) == len(row["gene_ids"]), len(row["pred"]))
        check(f"prediction_gene_ids:{fold}", len(set(row["gene_ids"].tolist())) == len(row["gene_ids"]) == fold_row["sizes"]["test"], len(row["gene_ids"]))
        all_test_genes.extend(row["gene_ids"].tolist())
        recomputed = metrics(row)
        deltas = {key: abs(recomputed[key] - fold_row["metrics"][key]) for key in recomputed}
        check(f"prediction_metric_recalculation:{fold}", max(deltas.values()) <= 1e-7, deltas)
        baseline_recomputed = {
            "train_mean": float(row["constant_train_mean_pred"][0]),
            "r2": float(r2_score(row["target"], row["constant_train_mean_pred"])),
            "mse": float(mean_squared_error(row["target"], row["constant_train_mean_pred"])),
        }
        baseline_deltas = {key: abs(baseline_recomputed[key] - fold_row["constant_train_mean_baseline"][key]) for key in baseline_recomputed}
        check(f"constant_baseline_recalculation:{fold}", bool(np.all(row["constant_train_mean_pred"] == row["constant_train_mean_pred"][0])) and max(baseline_deltas.values()) <= 1e-7, baseline_deltas)
        production_logged = production["official_result"]["folds"][fold]["test_at_best_validation"]
        check(f"prediction_matches_production_log:{fold}", all(round(recomputed[key], 6) == round(production_logged[key], 6) for key in recomputed), {"recomputed": recomputed, "production": production_logged})
        fold_recalculation.append({"fold": fold, "metrics": recomputed, "deltas_to_independent": deltas, "constant_train_mean_baseline": baseline_recomputed, "constant_baseline_deltas_to_independent": baseline_deltas})
    check("all_eligible_tested_once", len(all_test_genes) == len(set(all_test_genes)) == production["matrix"]["official_loader_eligible_records"], len(all_test_genes))
    recomputed_aggregate = {
        "r2_mean": float(np.mean([row["metrics"]["r2"] for row in fold_recalculation])),
        "r2_std": float(np.std([row["metrics"]["r2"] for row in fold_recalculation])),
        "mse_mean": float(np.mean([row["metrics"]["mse"] for row in fold_recalculation])),
        "mse_std": float(np.std([row["metrics"]["mse"] for row in fold_recalculation])),
        "pearson_mean": float(np.mean([row["metrics"]["pearson"] for row in fold_recalculation])),
        "pearson_std": float(np.std([row["metrics"]["pearson"] for row in fold_recalculation])),
    }
    check("final_aggregate_matches_production", all(round(recomputed_aggregate[key], 6) == round(production["official_result"]["aggregate"][key], 6) for key in recomputed_aggregate), {"recomputed": recomputed_aggregate, "production": production["official_result"]["aggregate"]})
    recomputed_baseline_aggregate = {
        "r2_mean": float(np.mean([row["constant_train_mean_baseline"]["r2"] for row in fold_recalculation])),
        "r2_std": float(np.std([row["constant_train_mean_baseline"]["r2"] for row in fold_recalculation])),
        "mse_mean": float(np.mean([row["constant_train_mean_baseline"]["mse"] for row in fold_recalculation])),
        "mse_std": float(np.std([row["constant_train_mean_baseline"]["mse"] for row in fold_recalculation])),
    }
    check("constant_baseline_aggregate", all(abs(recomputed_baseline_aggregate[key] - independent["constant_train_mean_baseline_aggregate"][key]) <= 1e-7 for key in recomputed_baseline_aggregate), {"recomputed": recomputed_baseline_aggregate, "independent": independent["constant_train_mean_baseline_aggregate"]})

    previous = protocol["previous_attempt"]
    previous_report = Path(previous["failure_report"])
    previous_data = json.loads(previous_report.read_text())
    previous_log = Path(previous_data["log"])
    check("failed_v1_report_retained", previous_data["status"] == "FAIL_OFFICIAL_TRAINING" and sha256(previous_report) == previous["failure_report_sha256"], previous["failure_report_sha256"])
    check("failed_v1_log_retained", sha256(previous_log) == previous_data["log_sha256"] and "1D CPU int64 tensor" in previous_log.read_text(errors="replace"), previous_data["log_sha256"])

    test_script = Path(__file__).with_name("test_a8_rk05_ribomimo_full.py")
    completed = subprocess.run([sys.executable, str(test_script)], cwd=test_script.parent.parent, capture_output=True, text=True)
    test_output = completed.stdout + completed.stderr
    (output / "unit_tests.log").write_text(test_output)
    check("unit_tests", completed.returncode == 0 and "Ran 10 tests" in test_output and "OK" in test_output and "skipped" not in test_output, test_output)

    for boundary in ("homology_aware_split", "protein_ood", "study_ood", "functional_ood", "main_baseline_comparison", "publication_metrics_reproduced", "sota_claim"):
        check(f"scope:{boundary}", production[boundary] is False and retrain[boundary] is False and independent[boundary] is False, production[boundary])

    report = {
        "schema_version": "a8-rk05-ribomimo-full-finalization-v1",
        "status": "PASS_COMPLETE_WITH_INDEPENDENT_RETRAIN_AND_INFERENCE",
        "dataset": "Mohammad16",
        "production_report": str(production_path), "production_report_sha256": sha256(production_path),
        "independent_report": str(independent_path), "independent_report_sha256": sha256(independent_path),
        "retrain_report": str(retrain_path), "retrain_report_sha256": sha256(retrain_path),
        "production_aggregate": production["official_result"]["aggregate"],
        "recomputed_aggregate": recomputed_aggregate,
        "recomputed_constant_train_mean_baseline_aggregate": recomputed_baseline_aggregate,
        "fold_recalculation": fold_recalculation,
        "retrain_checkpoint_max_abs_delta": checkpoint_deltas,
        "all_checkpoints_bitwise_equal": all(value == 0.0 for value in checkpoint_deltas.values()),
        "unit_tests": {"ran": 10, "status": "PASS", "log": str(output / "unit_tests.log"), "log_sha256": sha256(output / "unit_tests.log")},
        "checks": checks, "checks_passed": sum(row["pass"] for row in checks), "checks_total": len(checks),
        "official_default_1x10fold_max100_protocol_executed_twice": True,
        "independent_two_forward_passes_per_fold": True,
        "all_four_datasets_reproduced": False,
        "homology_aware_split": False, "protein_ood": False, "study_ood": False,
        "functional_ood": False, "main_baseline_comparison": False,
        "publication_metrics_reproduced": False, "sota_claim": False,
        "limitations": production["limitations"],
    }
    dump_json(report_path, report)
    dump_json(output / "finalization_report.copy.json", report)
    print(json.dumps({"status": report["status"], "checks": f"{len(checks)}/{len(checks)}", "report": str(report_path), "report_sha256": sha256(report_path)}, indent=2))


if __name__ == "__main__":
    main()
