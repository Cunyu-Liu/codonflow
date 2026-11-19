#!/usr/bin/env python3
"""Independently recompute and verify the four-matrix full-CV summary."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import numpy as np


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    args = parser.parse_args()
    repo = args.repo
    root = repo / "audits/20261118/RK05"
    summary_path = root / "ribomimo_full_four_matrix_summary_v1.json"
    summary = load(summary_path)
    checks = []

    def check(name: str, condition: bool, detail: object) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})
        if not condition:
            raise AssertionError(f"{name}: {detail}")

    check("summary_status", summary["status"] == "PASS_COMPLETE_FOUR_MATRIX_OFFICIAL_CV", summary["status"])
    check("dataset_set", set(summary["datasets"]) == {"Mohammad16", "Subtelny14", "Mohammad19-1", "Mohammad19-2"}, list(summary["datasets"]))
    check("summary_fold_count", len(summary["folds"]) == 40, len(summary["folds"]))
    for dataset, row in summary["datasets"].items():
        final_path = Path(row["finalization_report"])
        production_path = Path(row["production_report"])
        independent_path = Path(row["independent_report"])
        retrain_path = Path(row["retrain_report"])
        final = load(final_path)
        production = load(production_path)
        independent = load(independent_path)
        retrain = load(retrain_path)
        check(f"evidence_hashes:{dataset}", sha256(final_path) == row["finalization_report_sha256"] and sha256(production_path) == row["production_report_sha256"] and sha256(independent_path) == row["independent_report_sha256"] and sha256(retrain_path) == row["retrain_report_sha256"], dataset)
        check(f"finalization:{dataset}", final["dataset"] == dataset and final["status"] == "PASS_COMPLETE_WITH_INDEPENDENT_RETRAIN_AND_INFERENCE" and final["checks_total"] == final["checks_passed"] and len(final["fold_recalculation"]) == 10, final["checks_total"])
        check(f"two_training_runs:{dataset}", final["all_checkpoints_bitwise_equal"] and len(final["retrain_checkpoint_max_abs_delta"]) == 10 and all(value == 0.0 for value in final["retrain_checkpoint_max_abs_delta"].values()) and production["official_result"]["aggregate"] == retrain["official_result"]["aggregate"], final["retrain_checkpoint_max_abs_delta"])
        check(f"independent:{dataset}", independent["status"] == "PASS" and independent["checks_total"] == independent["checks_passed"] and independent["production_driver_imported"] is False and independent["two_forward_passes_per_fold"] is True and len(independent["fold_results"]) == 10, independent["checks_total"])
        recomputed = {
            "r2_mean": float(np.mean([fold["metrics"]["r2"] for fold in final["fold_recalculation"]])),
            "r2_std": float(np.std([fold["metrics"]["r2"] for fold in final["fold_recalculation"]])),
            "mse_mean": float(np.mean([fold["metrics"]["mse"] for fold in final["fold_recalculation"]])),
            "mse_std": float(np.std([fold["metrics"]["mse"] for fold in final["fold_recalculation"]])),
            "pearson_mean": float(np.mean([fold["metrics"]["pearson"] for fold in final["fold_recalculation"]])),
            "pearson_std": float(np.std([fold["metrics"]["pearson"] for fold in final["fold_recalculation"]])),
        }
        check(f"aggregate_recalculation:{dataset}", all(abs(recomputed[key] - row["aggregate"][key]) <= 1e-7 and abs(recomputed[key] - final["recomputed_aggregate"][key]) <= 1e-7 for key in recomputed), recomputed)
        baseline = {
            "r2_mean": float(np.mean([fold["constant_train_mean_baseline"]["r2"] for fold in final["fold_recalculation"]])),
            "r2_std": float(np.std([fold["constant_train_mean_baseline"]["r2"] for fold in final["fold_recalculation"]])),
            "mse_mean": float(np.mean([fold["constant_train_mean_baseline"]["mse"] for fold in final["fold_recalculation"]])),
            "mse_std": float(np.std([fold["constant_train_mean_baseline"]["mse"] for fold in final["fold_recalculation"]])),
        }
        check(f"baseline_recalculation:{dataset}", all(abs(baseline[key] - row["constant_train_mean_baseline_aggregate"][key]) <= 1e-7 for key in baseline), baseline)
        check(f"matrix_and_counts:{dataset}", production["matrix"]["sha256"] == row["matrix_sha256"] and production["matrix"]["raw_records"] == row["raw_records"] and production["matrix"]["official_loader_eligible_records"] == row["eligible_genes"] and sum(fold["valid_masked_codons"] for fold in independent["fold_results"]) == row["valid_masked_codons"], row["matrix_sha256"])
        check(f"fold_rows:{dataset}", len(row["folds"]) == 10 and [fold["best_epoch"] for fold in row["folds"]] == [fold["best_epoch"] for fold in production["official_result"]["folds"]], row["best_epochs"])
    macro = {key: float(np.mean([row["aggregate"][key] for row in summary["datasets"].values()])) for key in ("r2_mean", "r2_std", "mse_mean", "mse_std", "pearson_mean", "pearson_std")}
    check("macro_recalculation", all(abs(macro[key] - summary["macro_average_of_dataset_fold_means_descriptive_only"][key]) <= 1e-12 for key in macro), macro)
    check("four_matrix_totals", summary["total_raw_records"] == 15669 and summary["total_official_loader_eligible_genes"] == 8124 and summary["total_valid_masked_test_codons"] == sum(row["valid_masked_codons"] for row in summary["datasets"].values()) and summary["rk03_clean_qc_count_not_interchanged"] == 8109, {"raw": summary["total_raw_records"], "eligible": summary["total_official_loader_eligible_genes"], "codons": summary["total_valid_masked_test_codons"]})
    check("execution_counts", summary["complete_training_runs"] == 8 and summary["checkpoint_pairs_bitwise_identical"] == 40 and summary["independent_forward_passes"] == 80 and summary["official_random_gene_cv_complete_all_four"] is True, 8)
    check("scientific_boundaries", all(summary[key] is False for key in ("homology_aware_split", "protein_ood", "study_ood", "functional_ood", "publication_metrics_reproduced", "unified_cost_baseline_matrix", "sota_claim")), summary["scope"])
    report = {
        "schema_version": "a8-rk05-ribomimo-full-four-matrix-summary-verification-v1",
        "status": "PASS", "summary": str(summary_path), "summary_sha256": sha256(summary_path),
        "checks": checks, "checks_passed": sum(row["pass"] for row in checks), "checks_total": len(checks),
        "summary_generator_imported": False,
        "scope": summary["scope"],
    }
    output = root / "ribomimo_full_four_matrix_summary_verification_v1.json"
    atomic_json(output, report)
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "summary_sha256": report["summary_sha256"], "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()
