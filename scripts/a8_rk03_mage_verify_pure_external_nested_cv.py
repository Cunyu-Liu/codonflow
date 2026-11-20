#!/usr/bin/env python3
"""Independent recomputation for the pure external-RCS MAGE comparator.

This verifier imports neither the production comparator nor the old nested-CV
script. It reconstructs external-only features, refits every pure-arm model and
recomputes all paired intervals, permutation p values and Holm adjustments.
"""
from __future__ import annotations

import os
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_name] = "1"

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PURE = "pure_external_rcs"
OLD_ARMS = ["intrinsic", "rcs_only", "full_mechanism"]
PURE_COLUMNS = ["RCS", "delta_rcs_vs_wt", "abs_delta_rcs_vs_wt"]


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def folds_for(ids: list[str], n_folds: int, salt: str) -> dict[str, int]:
    ordered = sorted(ids, key=lambda value: (hashlib.sha256(f"{salt}:{value}".encode()).hexdigest(), value))
    return {value: i % n_folds for i, value in enumerate(ordered)}


def metrics(y: np.ndarray, pred: np.ndarray) -> dict:
    return {
        "n": int(len(y)),
        "rmse": float(np.sqrt(np.mean((y - pred) ** 2))),
        "mae": float(np.mean(np.abs(y - pred))),
        "spearman": float(spearmanr(y, pred).statistic),
        "mean_y": float(np.mean(y)),
        "mean_prediction": float(np.mean(pred)),
    }


def effect(y: np.ndarray, candidate: np.ndarray, reference: np.ndarray) -> dict:
    a = metrics(y, candidate)
    b = metrics(y, reference)
    return {"delta_spearman": a["spearman"] - b["spearman"], "delta_rmse": a["rmse"] - b["rmse"]}


def holm(values: list[float]) -> list[float]:
    p = np.asarray(values, dtype=np.float64)
    order = np.argsort(p)
    adjusted = np.empty(len(p), dtype=np.float64)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p) - rank) * p[index])
        adjusted[index] = min(1.0, running)
    return [float(value) for value in adjusted]


def paired(y: np.ndarray, candidate: np.ndarray, reference: np.ndarray, bootstrap_seed: int, permutation_seed: int, replicates: int) -> dict:
    observed = effect(y, candidate, reference)
    n = len(y)
    bootstrap = np.empty((replicates, 2), dtype=np.float64)
    rng = np.random.default_rng(bootstrap_seed)
    for b in range(replicates):
        selected = rng.integers(0, n, n)
        values = effect(y[selected], candidate[selected], reference[selected])
        bootstrap[b] = [values["delta_spearman"], values["delta_rmse"]]
    permutation = np.empty((replicates, 2), dtype=np.float64)
    rng = np.random.default_rng(permutation_seed)
    for b in range(replicates):
        swap = rng.random(n) < 0.5
        c = np.where(swap, reference, candidate)
        r = np.where(swap, candidate, reference)
        values = effect(y, c, r)
        permutation[b] = [values["delta_spearman"], values["delta_rmse"]]
    obs = np.asarray([observed["delta_spearman"], observed["delta_rmse"]])
    p = (1 + np.sum(np.abs(permutation) >= np.abs(obs)[None, :], axis=0)) / (replicates + 1.0)
    return {
        **observed,
        "delta_spearman_ci95": [float(value) for value in np.percentile(bootstrap[:, 0], [2.5, 97.5])],
        "delta_rmse_ci95": [float(value) for value in np.percentile(bootstrap[:, 1], [2.5, 97.5])],
        "permutation_p_spearman": float(p[0]),
        "permutation_p_rmse": float(p[1]),
        "bootstrap_replicates": replicates,
        "permutation_replicates": replicates,
    }


def fit_predict(matrix: np.ndarray, y: np.ndarray, train: np.ndarray, evaluation: np.ndarray, alpha: float) -> np.ndarray:
    model = Pipeline([
        ("scale", StandardScaler(with_mean=False)),
        ("ridge", Ridge(alpha=alpha, fit_intercept=True, solver="lsqr", tol=1e-12, max_iter=100000)),
    ])
    model.fit(matrix[train], y[train])
    return np.asarray(model.predict(matrix[evaluation]), dtype=np.float64)


def refit_pure(ids: list[str], folds: dict[str, int], matrix: np.ndarray, y: np.ndarray, seed: str, alphas: list[float]) -> tuple[dict[str, float], list[dict], int]:
    index = {construct_id: i for i, construct_id in enumerate(ids)}
    predictions = {}
    selections = []
    fit_count = 0
    for fold in range(5):
        train_ids = [construct_id for construct_id in ids if folds[construct_id] != fold]
        eval_ids = [construct_id for construct_id in ids if folds[construct_id] == fold]
        inner = folds_for(train_ids, 4, f"{seed}:inner")
        inner_predictions = {alpha: {} for alpha in alphas}
        for inner_fold in range(4):
            inner_train = [construct_id for construct_id in train_ids if inner[construct_id] != inner_fold]
            inner_eval = [construct_id for construct_id in train_ids if inner[construct_id] == inner_fold]
            train_idx = np.asarray([index[value] for value in inner_train], dtype=int)
            eval_idx = np.asarray([index[value] for value in inner_eval], dtype=int)
            for alpha in alphas:
                pred = fit_predict(matrix, y, train_idx, eval_idx, alpha)
                fit_count += 1
                inner_predictions[alpha].update({value: float(p) for value, p in zip(inner_eval, pred)})
        train_idx = np.asarray([index[value] for value in train_ids], dtype=int)
        trials = []
        for alpha in alphas:
            pred = np.asarray([inner_predictions[alpha][value] for value in train_ids])
            trials.append({"alpha": alpha, "inner_oof_rmse": float(np.sqrt(np.mean((y[train_idx] - pred) ** 2)))})
        best = sorted(trials, key=lambda row: (row["inner_oof_rmse"], -row["alpha"], str(row["alpha"])))[0]
        eval_idx = np.asarray([index[value] for value in eval_ids], dtype=int)
        pred = fit_predict(matrix, y, train_idx, eval_idx, best["alpha"])
        fit_count += 1
        predictions.update({value: float(p) for value, p in zip(eval_ids, pred)})
        selections.append({"outer_fold": fold, "n_outer_train": len(train_ids), "n_outer_eval": len(eval_ids), "selected_alpha": best["alpha"], "inner_alpha_grid": trials})
    return predictions, selections, fit_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--production", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    production_path = Path(args.production).resolve()
    cfg = json.loads(config_path.read_text())
    production = json.loads(production_path.read_text())
    checks = []
    max_delta = 0.0

    def check(name: str, condition: bool, detail: object = None) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    def close(name: str, actual: object, expected: object, tolerance: float = 1e-12) -> None:
        nonlocal max_delta
        a = np.asarray(actual, dtype=np.float64)
        e = np.asarray(expected, dtype=np.float64)
        delta = float(np.max(np.abs(a - e))) if a.size else 0.0
        max_delta = max(max_delta, delta)
        check(name, a.shape == e.shape and bool(np.isfinite(a).all()) and bool(np.isfinite(e).all()) and delta <= tolerance, {"max_abs_delta": delta, "shape": list(a.shape)})

    check("protocol_schema", cfg["schema"] == "a8-rk03-mage-pure-external-nested-cv-protocol-v1")
    check("protocol_frozen_before_fit", cfg["frozen_before_pure_external_model_fitting"] is True)
    check("production_protocol_sha", production["protocol_sha256"] == sha256(config_path), production["protocol_sha256"])
    for key in ("oof_csv", "raw_feature_csv", "nested_report", "nested_protocol", "nested_production_script"):
        actual = sha256(cfg["source"][key])
        check(f"source_sha_{key}", actual == cfg["source"][f"{key}_sha256"], actual)

    with open(cfg["source"]["oof_csv"], newline="") as handle:
        oof = list(csv.DictReader(handle))
    ids = [row["construct_id"] for row in oof]
    check("oof_131_unique_development_ids", len(ids) == 131 and len(set(ids)) == 131)
    check("oof_only_train_dev", {row["original_split"] for row in oof} == {"train", "dev"})
    check("oof_original_split_counts", sum(row["original_split"] == "train" for row in oof) == 98 and sum(row["original_split"] == "dev" for row in oof) == 33)
    y = np.asarray([float(row["observed_rich"]) for row in oof], dtype=np.float64)
    check("development_labels_finite", bool(np.isfinite(y).all()))
    seeds = [cfg["nested_cv"]["primary_outer_seed"]] + cfg["nested_cv"]["sensitivity_outer_seeds"]
    folds = {}
    old_predictions = {}
    for seed in seeds:
        reconstructed = folds_for(ids, 5, seed)
        folds[seed] = {row["construct_id"]: int(row[f"outer_fold_{seed}"]) for row in oof}
        check(f"outer_folds_reconstructed_{seed}", folds[seed] == reconstructed)
        old_predictions[seed] = {arm: np.asarray([float(row[f"pred_{seed}_{arm}"]) for row in oof], dtype=np.float64) for arm in OLD_ARMS}
        for arm in OLD_ARMS:
            check(f"old_predictions_finite_{seed}_{arm}", bool(np.isfinite(old_predictions[seed][arm]).all()))

    artifact_name = "pure_external_oof_predictions.csv"
    artifact_path = Path(cfg["outputs"]["large_artifact_root"]) / artifact_name
    check("new_prediction_artifact_sha", sha256(artifact_path) == production["artifact_files"][artifact_name]["sha256"])
    with artifact_path.open(newline="") as handle:
        pure_rows = list(csv.DictReader(handle))
    check("new_prediction_ids_match", [row["construct_id"] for row in pure_rows] == ids)
    check("new_prediction_splits_match", all(a["original_split"] == b["original_split"] for a, b in zip(pure_rows, oof)))
    check("new_prediction_labels_match_frozen_oof", all(float(a["observed_rich"]) == float(b["observed_rich"]) for a, b in zip(pure_rows, oof)))
    check("new_prediction_no_test_split", all(row["original_split"] in {"train", "dev"} for row in pure_rows))

    development_ids = set(ids)
    wt_rcs = {}
    variant_rcs = {}
    positions = {}
    required = ["construct_id", "record_class", "expression_type", "codon_position", "features_json"]
    with open(cfg["source"]["raw_feature_csv"], newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        index = {column: header.index(column) for column in required}
        check("raw_expression_fields_not_selected", "expression_value" not in index and "expression_stdev" not in index)
        check("raw_sequence_fields_not_selected", "cds" not in index and "protein_sequence" not in index)
        for values in reader:
            if values[index["expression_type"]] != "relative_fitness_rich":
                continue
            if values[index["record_class"]] == "wild_type_control":
                wt_rcs[int(values[index["codon_position"]])] = float(json.loads(values[index["features_json"]])["RCS"])
            elif values[index["record_class"]] == "single_codon_variant" and values[index["construct_id"]] in development_ids:
                construct_id = values[index["construct_id"]]
                positions[construct_id] = int(values[index["codon_position"]])
                variant_rcs[construct_id] = float(json.loads(values[index["features_json"]])["RCS"])
    check("all_development_external_features_found", set(variant_rcs) == development_ids)
    matrix = np.asarray([[variant_rcs[value], variant_rcs[value] - wt_rcs[positions[value]], abs(variant_rcs[value] - wt_rcs[positions[value]])] for value in ids], dtype=np.float64)
    check("pure_feature_matrix_finite_shape", matrix.shape == (131, 3) and bool(np.isfinite(matrix).all()))
    artifact_matrix = np.asarray([[float(row[column]) for column in PURE_COLUMNS] for row in pure_rows], dtype=np.float64)
    close("external_features_match_new_artifact", artifact_matrix, matrix)
    canonical = [[value] + [float(variant_rcs[value]), float(variant_rcs[value] - wt_rcs[positions[value]]), float(abs(variant_rcs[value] - wt_rcs[positions[value]]))] for value in ids]
    digest = hashlib.sha256(json.dumps(canonical, separators=(",", ":")).encode()).hexdigest()
    check("external_feature_digest", production["data_audit"]["external_feature_digest"] == digest, digest)
    check("pure_schema_has_no_categorical", production["data_audit"]["categorical_feature_columns"] == [])
    check("pure_schema_exact", production["data_audit"]["pure_feature_columns"] == PURE_COLUMNS)
    check("forbidden_intrinsic_features_false", production["data_audit"]["forbidden_intrinsic_features_used"] is False)

    alphas = [float(value) for value in cfg["nested_cv"]["alpha_grid"]]
    independent_predictions = {}
    total_fits = 0
    for seed in seeds:
        predictions, selections, fit_count = refit_pure(ids, folds[seed], matrix, y, seed, alphas)
        independent_predictions[seed] = np.asarray([predictions[value] for value in ids], dtype=np.float64)
        total_fits += fit_count
        artifact_predictions = np.asarray([float(row[f"pred_{seed}_{PURE}"]) for row in pure_rows], dtype=np.float64)
        close(f"pure_predictions_recomputed_{seed}", independent_predictions[seed], artifact_predictions)
        check(f"fit_count_{seed}", production["fit_counts"][seed] == fit_count == 125, production["fit_counts"][seed])
        production_selections = production["nested_cv_selection"][seed]
        check(f"selection_fold_count_{seed}", len(production_selections) == len(selections) == 5)
        for fold, (actual, expected) in enumerate(zip(production_selections, selections)):
            check(f"selected_alpha_{seed}_{fold}", actual["selected_alpha"] == expected["selected_alpha"], {"production": actual["selected_alpha"], "independent": expected["selected_alpha"]})
            check(f"selection_sizes_{seed}_{fold}", actual["n_outer_train"] == expected["n_outer_train"] and actual["n_outer_eval"] == expected["n_outer_eval"])
            close(f"inner_alpha_rmse_{seed}_{fold}", [row["inner_oof_rmse"] for row in actual["inner_alpha_grid"]], [row["inner_oof_rmse"] for row in expected["inner_alpha_grid"]])
    check("total_fit_count_375", total_fits == 375, total_fits)

    primary_seed = seeds[0]
    primary = {PURE: independent_predictions[primary_seed], **old_predictions[primary_seed]}
    for arm in [PURE] + OLD_ARMS:
        recomputed = metrics(y, primary[arm])
        for key, value in recomputed.items():
            close(f"primary_metric_{arm}_{key}", production["primary_models"][arm][key], value)

    p_values = []
    independent_comparisons = {}
    for spec in cfg["primary_comparisons"]:
        result = paired(y, primary[spec["candidate"]], primary[spec["reference"]], spec["bootstrap_seed"], spec["permutation_seed"], int(cfg["inference"]["bootstrap_replicates"]))
        independent_comparisons[spec["comparison_id"]] = result
        p_values.extend([result["permutation_p_spearman"], result["permutation_p_rmse"]])
    adjusted = holm(p_values)
    for i, spec in enumerate(cfg["primary_comparisons"]):
        comparison_id = spec["comparison_id"]
        independent = independent_comparisons[comparison_id]
        independent["holm_p_spearman"] = adjusted[2 * i]
        independent["holm_p_rmse"] = adjusted[2 * i + 1]
        actual = production["primary_comparisons"][comparison_id]
        for key in ("delta_spearman", "delta_rmse", "delta_spearman_ci95", "delta_rmse_ci95", "permutation_p_spearman", "permutation_p_rmse", "holm_p_spearman", "holm_p_rmse"):
            close(f"comparison_{comparison_id}_{key}", actual[key], independent[key])
        sensitivity_ok = True
        for seed in seeds[1:]:
            candidate = independent_predictions[seed] if spec["candidate"] == PURE else old_predictions[seed][spec["candidate"]]
            reference = independent_predictions[seed] if spec["reference"] == PURE else old_predictions[seed][spec["reference"]]
            point = effect(y, candidate, reference)
            for key, value in point.items():
                close(f"sensitivity_{comparison_id}_{seed}_{key}", production["sensitivity"][seed]["comparisons"][comparison_id][key], value)
            sensitivity_ok &= point["delta_spearman"] > 0 and point["delta_rmse"] < 0
        check(f"sensitivity_flag_{comparison_id}", actual["sensitivity_signs_ok"] == sensitivity_ok)
        expected_support = bool(actual["delta_spearman_ci95"][0] > 0 and actual["delta_rmse_ci95"][1] < 0 and actual["holm_p_spearman"] < 0.05 and actual["holm_p_rmse"] < 0.05 and sensitivity_ok)
        check(f"support_flag_{comparison_id}", actual["supported_development_only"] == expected_support)

    check("pure_replacement_summary_flag", production["pure_external_replacement_supported_development_only"] == production["primary_comparisons"]["pure_external_rcs_minus_intrinsic"]["supported_development_only"])
    check("full_over_pure_summary_flag", production["full_over_pure_supported_development_only"] == production["primary_comparisons"]["full_mechanism_minus_pure_external_rcs"]["supported_development_only"])
    check("augmentation_summary_flag", production["intrinsic_augmentation_over_pure_supported_development_only"] == production["primary_comparisons"]["rcs_only_minus_pure_external_rcs"]["supported_development_only"])
    for key in ("test_predictions_generated", "test_metrics_generated", "raw_expression_value_or_stdev_fields_accessed", "new_sequences_read", "original_dev_no_go_modified", "test_authorized", "mechanism_increment_pass", "rk_g1_pass", "generator_training_authorized"):
        check(f"boundary_{key}", production[key] is False)
    check("test_feature_rows_zero", production["test_construct_feature_rows_selected"] == 0)
    check("scientific_status_bounded", production["scientific_status"] == "DEVELOPMENT_ONLY_NO_GATE_CHANGE")
    check("technical_status_pending_before_verification", production["technical_status"] == "PENDING_INDEPENDENT_VERIFICATION")

    passed = sum(row["pass"] for row in checks)
    failed = len(checks) - passed
    report = {
        "schema": "a8-rk03-mage-pure-external-nested-cv-independent-v1",
        "protocol_sha256": sha256(config_path),
        "production_report_sha256": sha256(production_path),
        "status": "PASS_PURE_EXTERNAL_INDEPENDENT_VERIFICATION" if failed == 0 else "FAIL_PURE_EXTERNAL_INDEPENDENT_VERIFICATION",
        "overall_pass": failed == 0,
        "checks_total": len(checks),
        "checks_passed": passed,
        "checks_failed": failed,
        "max_numeric_delta": max_delta,
        "independent_fit_count": total_fits,
        "independent_primary_models": {arm: metrics(y, primary[arm]) for arm in [PURE] + OLD_ARMS},
        "independent_primary_comparisons": independent_comparisons,
        "test_untouched": True,
        "rk_g1_pass": False,
        "generator_training_authorized": False,
        "checks": checks,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "max_numeric_delta": max_delta, "independent_fit_count": total_fits}, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
