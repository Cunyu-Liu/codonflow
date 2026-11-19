#!/usr/bin/env python3
"""Build a bounded four-matrix summary only after all full finalizations pass."""
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
    slugs = {"Mohammad16": "mohammad16", "Subtelny14": "subtelny14", "Mohammad19-1": "mohammad19_1", "Mohammad19-2": "mohammad19_2"}
    preflight_path = root / "ribomimo_full_loader_preflight_v1.json"
    preflight = load(preflight_path)
    rows = {}
    all_folds = []
    for dataset, slug in slugs.items():
        final_path = root / f"ribomimo_full_{slug}_finalization_v1.json"
        final = load(final_path)
        if final["status"] != "PASS_COMPLETE_WITH_INDEPENDENT_RETRAIN_AND_INFERENCE" or final["checks_total"] != final["checks_passed"] or not final["all_checkpoints_bitwise_equal"]:
            raise RuntimeError(f"Incomplete finalization: {dataset}")
        production_path = Path(final["production_report"])
        independent_path = Path(final["independent_report"])
        retrain_path = Path(final["retrain_report"])
        production = load(production_path)
        independent = load(independent_path)
        retrain = load(retrain_path)
        if final["dataset"] != dataset or production["official_result"]["aggregate"] != retrain["official_result"]["aggregate"]:
            raise RuntimeError(f"Training identity mismatch: {dataset}")
        if sha256(production_path) != final["production_report_sha256"] or sha256(independent_path) != final["independent_report_sha256"] or sha256(retrain_path) != final["retrain_report_sha256"]:
            raise RuntimeError(f"Evidence hash mismatch: {dataset}")
        folds = []
        for prod_fold, final_fold, independent_fold in zip(production["official_result"]["folds"], final["fold_recalculation"], independent["fold_results"]):
            if not (prod_fold["fold"] == final_fold["fold"] == independent_fold["fold"]):
                raise RuntimeError(f"Fold order mismatch: {dataset}")
            row = {
                "fold": prod_fold["fold"], "best_epoch": prod_fold["best_epoch"],
                "r2": final_fold["metrics"]["r2"], "mse": final_fold["metrics"]["mse"], "pearson": final_fold["metrics"]["pearson"],
                "constant_train_mean_baseline": final_fold["constant_train_mean_baseline"],
                "valid_masked_codons": independent_fold["valid_masked_codons"],
                "train_valid_test_sizes": independent_fold["sizes"],
            }
            folds.append(row)
            all_folds.append({"dataset": dataset, **row})
        rows[dataset] = {
            "raw_records": production["matrix"]["raw_records"],
            "eligible_genes": production["matrix"]["official_loader_eligible_records"],
            "matrix_sha256": production["matrix"]["sha256"],
            "aggregate": final["recomputed_aggregate"],
            "constant_train_mean_baseline_aggregate": final["recomputed_constant_train_mean_baseline_aggregate"],
            "valid_masked_codons": sum(row["valid_masked_codons"] for row in folds),
            "best_epochs": [row["best_epoch"] for row in folds],
            "folds": folds,
            "production_report": str(production_path), "production_report_sha256": sha256(production_path),
            "retrain_report": str(retrain_path), "retrain_report_sha256": sha256(retrain_path),
            "independent_report": str(independent_path), "independent_report_sha256": sha256(independent_path),
            "finalization_report": str(final_path), "finalization_report_sha256": sha256(final_path),
            "independent_checks": f"{independent['checks_passed']}/{independent['checks_total']}",
            "finalization_checks": f"{final['checks_passed']}/{final['checks_total']}",
            "two_training_runs_bitwise_identical": True,
        }
    macro = {
        key: float(np.mean([row["aggregate"][key] for row in rows.values()]))
        for key in ("r2_mean", "r2_std", "mse_mean", "mse_std", "pearson_mean", "pearson_std")
    }
    report = {
        "schema_version": "a8-rk05-ribomimo-full-four-matrix-summary-v1",
        "status": "PASS_COMPLETE_FOUR_MATRIX_OFFICIAL_CV",
        "source_commit": "094c693d4df45f4b29f5a3209b31c452a39092a5",
        "preflight_report": str(preflight_path), "preflight_report_sha256": sha256(preflight_path),
        "datasets": rows, "folds": all_folds,
        "macro_average_of_dataset_fold_means_descriptive_only": macro,
        "total_raw_records": sum(row["raw_records"] for row in rows.values()),
        "total_official_loader_eligible_genes": sum(row["eligible_genes"] for row in rows.values()),
        "total_valid_masked_test_codons": sum(row["valid_masked_codons"] for row in rows.values()),
        "rk03_clean_qc_count_not_interchanged": 8109,
        "complete_training_runs": 8, "folds_per_dataset": 10, "checkpoint_pairs_bitwise_identical": 40,
        "independent_two_forward_passes_per_fold": True, "independent_forward_passes": 80,
        "official_random_gene_cv_complete_all_four": True,
        "homology_aware_split": False, "protein_ood": False, "study_ood": False, "functional_ood": False,
        "publication_metrics_reproduced": False, "unified_cost_baseline_matrix": False, "sota_claim": False,
        "scope": "Four author-processed matrices completed the official random-gene 1x10-fold/max100/early-stop5 protocol twice with independent inference and finalization. This is not OOD, publication-metric reproduction, unified-cost ranking or SOTA.",
    }
    if report["total_raw_records"] != 15669 or report["total_official_loader_eligible_genes"] != 8124:
        raise RuntimeError("Unexpected four-matrix totals")
    output = root / "ribomimo_full_four_matrix_summary_v1.json"
    atomic_json(output, report)
    print(json.dumps({"status": report["status"], "output": str(output), "sha256": sha256(output), "macro": macro, "datasets": {key: value["aggregate"] for key, value in rows.items()}}, indent=2))


if __name__ == "__main__":
    main()
