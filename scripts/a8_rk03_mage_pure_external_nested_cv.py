#!/usr/bin/env python3
"""Pre-registered development-only pure external-RCS nested-CV comparator.

No intrinsic categorical/numeric feature is constructed for the new arm. Labels,
folds and old-arm predictions come only from the frozen development OOF artifact.
The frozen test partition is never selected for features, fitting or evaluation.
"""
from __future__ import annotations

import os
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_name] = "1"
os.environ.setdefault("PYTHONHASHSEED", "0")

import argparse
import csv
import hashlib
import json
import math
import platform
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import a8_rk03_mage_development_nested_cv as base

PURE = "pure_external_rcs"
OLD_ARMS = ["intrinsic", "rcs_only", "full_mechanism"]
PURE_COLUMNS = ["RCS", "delta_rcs_vs_wt", "abs_delta_rcs_vs_wt"]
RAW_COLUMNS = ["construct_id", "record_class", "expression_type", "codon_position", "wt_codon", "mutant_codon", "amino_acid", "features_json"]
FORBIDDEN_RAW_COLUMNS = {"expression_value", "expression_stdev", "cds", "protein_sequence"}


def pure_features(variant_rcs: float, wt_rcs: float) -> dict[str, float]:
    delta = float(variant_rcs) - float(wt_rcs)
    return {"RCS": float(variant_rcs), "delta_rcs_vs_wt": delta, "abs_delta_rcs_vs_wt": abs(delta)}


def raw_column_indices(header: list[str]) -> dict[str, int]:
    if any(column in RAW_COLUMNS for column in FORBIDDEN_RAW_COLUMNS):
        raise AssertionError("forbidden raw column entered the selected schema")
    missing = set(RAW_COLUMNS) - set(header)
    if missing:
        raise AssertionError(f"missing raw feature columns: {sorted(missing)}")
    indices = {column: header.index(column) for column in RAW_COLUMNS}
    if any(column in indices for column in FORBIDDEN_RAW_COLUMNS):
        raise AssertionError("label or sequence column was selected")
    return indices


def load_oof(cfg: dict) -> list[dict]:
    path = Path(cfg["source"]["oof_csv"])
    if base.sha256(path) != cfg["source"]["oof_csv_sha256"]:
        raise AssertionError("frozen development OOF hash mismatch")
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    expected = int(cfg["development_data"]["expected_n_constructs"])
    if len(rows) != expected:
        raise AssertionError("development OOF row-count mismatch")
    seeds = [cfg["nested_cv"]["primary_outer_seed"]] + cfg["nested_cv"]["sensitivity_outer_seeds"]
    ids = [row["construct_id"] for row in rows]
    if len(set(ids)) != expected or any(row["original_split"] not in {"train", "dev"} for row in rows):
        raise AssertionError("development IDs or split boundary mismatch")
    if dict(Counter(row["original_split"] for row in rows)) != {"train": 98, "dev": 33}:
        raise AssertionError("original development split counts changed")
    records = []
    for row in rows:
        record = {
            "construct_id": row["construct_id"],
            "original_split": row["original_split"],
            "position": row["position"],
            "y": float(row["observed_rich"]),
            "folds": {},
            "old_predictions": {},
        }
        if not math.isfinite(record["y"]):
            raise AssertionError("non-finite frozen development label")
        for seed in seeds:
            fold = int(row[f"outer_fold_{seed}"])
            expected_fold = base.assign_folds(ids, int(cfg["nested_cv"]["outer_folds"]), seed)[row["construct_id"]]
            if fold != expected_fold:
                raise AssertionError("frozen outer fold differs from protocol reconstruction")
            record["folds"][seed] = fold
            record["old_predictions"][seed] = {}
            for arm in OLD_ARMS:
                value = float(row[f"pred_{seed}_{arm}"])
                if not math.isfinite(value):
                    raise AssertionError("non-finite old-arm prediction")
                record["old_predictions"][seed][arm] = value
        records.append(record)
    return records


def attach_external_features(cfg: dict, records: list[dict]) -> None:
    path = Path(cfg["source"]["raw_feature_csv"])
    if base.sha256(path) != cfg["source"]["raw_feature_csv_sha256"]:
        raise AssertionError("raw feature CSV hash mismatch")
    development_ids = {row["construct_id"] for row in records}
    wt_rcs: dict[int, float] = {}
    variants: dict[str, tuple[int, float]] = {}
    raw_rows_scanned = 0
    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        indices = raw_column_indices(next(reader))
        for values in reader:
            raw_rows_scanned += 1
            record_class = values[indices["record_class"]]
            expression_type = values[indices["expression_type"]]
            if expression_type != "relative_fitness_rich":
                continue
            if record_class == "wild_type_control":
                position = int(values[indices["codon_position"]])
                features = json.loads(values[indices["features_json"]])
                wt_rcs[position] = float(features["RCS"])
                continue
            construct_id = values[indices["construct_id"]]
            if record_class != "single_codon_variant" or construct_id not in development_ids:
                continue
            position = int(values[indices["codon_position"]])
            features = json.loads(values[indices["features_json"]])
            if construct_id in variants:
                raise AssertionError("duplicate selected development variant")
            variants[construct_id] = (position, float(features["RCS"]))
    if set(variants) != development_ids:
        raise AssertionError("not every development construct received external features")
    for row in records:
        position, variant_rcs = variants[row["construct_id"]]
        if str(position) != str(row["position"]):
            raise AssertionError("frozen OOF position differs from raw feature position")
        if position not in wt_rcs or not math.isfinite(wt_rcs[position]) or not math.isfinite(variant_rcs):
            raise AssertionError("missing or non-finite wild-type/variant RCS")
        row["pure_features"] = pure_features(variant_rcs, wt_rcs[position])
        if set(row["pure_features"]) != set(PURE_COLUMNS):
            raise AssertionError("pure external feature schema changed")


def feature_matrix(records: list[dict]) -> np.ndarray:
    matrix = np.asarray([[row["pure_features"][column] for column in PURE_COLUMNS] for row in records], dtype=np.float64)
    if matrix.shape != (len(records), 3) or not np.isfinite(matrix).all():
        raise AssertionError("invalid pure external feature matrix")
    return matrix


def fit_predict(matrix: np.ndarray, y: np.ndarray, train: np.ndarray, evaluation: np.ndarray, alpha: float) -> np.ndarray:
    model = Pipeline([
        ("numeric", StandardScaler(with_mean=False)),
        ("ridge", Ridge(alpha=alpha, fit_intercept=True, solver="lsqr", tol=1e-12, max_iter=100000)),
    ])
    model.fit(matrix[train], y[train])
    return np.asarray(model.predict(matrix[evaluation]), dtype=np.float64)


def nested_pure(records: list[dict], matrix: np.ndarray, y: np.ndarray, seed: str, cfg: dict) -> dict:
    ids = [row["construct_id"] for row in records]
    index = {construct_id: i for i, construct_id in enumerate(ids)}
    outer = {row["construct_id"]: row["folds"][seed] for row in records}
    alphas = [float(value) for value in cfg["nested_cv"]["alpha_grid"]]
    predictions: dict[str, float] = {}
    selections = []
    fit_count = 0
    for fold in range(int(cfg["nested_cv"]["outer_folds"])):
        outer_train_ids = [construct_id for construct_id in ids if outer[construct_id] != fold]
        outer_eval_ids = [construct_id for construct_id in ids if outer[construct_id] == fold]
        inner = base.assign_folds(outer_train_ids, int(cfg["nested_cv"]["inner_folds"]), f"{seed}:inner")
        inner_predictions = {alpha: {} for alpha in alphas}
        for inner_fold in range(int(cfg["nested_cv"]["inner_folds"])):
            inner_train_ids = [construct_id for construct_id in outer_train_ids if inner[construct_id] != inner_fold]
            inner_eval_ids = [construct_id for construct_id in outer_train_ids if inner[construct_id] == inner_fold]
            train_idx = np.asarray([index[construct_id] for construct_id in inner_train_ids], dtype=int)
            eval_idx = np.asarray([index[construct_id] for construct_id in inner_eval_ids], dtype=int)
            for alpha in alphas:
                pred = fit_predict(matrix, y, train_idx, eval_idx, alpha)
                fit_count += 1
                inner_predictions[alpha].update({construct_id: float(value) for construct_id, value in zip(inner_eval_ids, pred)})
        trials = []
        outer_train_idx = np.asarray([index[construct_id] for construct_id in outer_train_ids], dtype=int)
        for alpha in alphas:
            pred = np.asarray([inner_predictions[alpha][construct_id] for construct_id in outer_train_ids], dtype=np.float64)
            rmse = float(np.sqrt(np.mean((y[outer_train_idx] - pred) ** 2)))
            trials.append({"alpha": alpha, "inner_oof_rmse": rmse})
        best = sorted(trials, key=lambda trial: (trial["inner_oof_rmse"], -trial["alpha"], str(trial["alpha"])))[0]
        eval_idx = np.asarray([index[construct_id] for construct_id in outer_eval_ids], dtype=int)
        pred = fit_predict(matrix, y, outer_train_idx, eval_idx, float(best["alpha"]))
        fit_count += 1
        predictions.update({construct_id: float(value) for construct_id, value in zip(outer_eval_ids, pred)})
        selections.append({
            "outer_fold": fold,
            "n_outer_train": len(outer_train_ids),
            "n_outer_eval": len(outer_eval_ids),
            "selected_alpha": best["alpha"],
            "inner_alpha_grid": trials,
        })
    if set(predictions) != set(ids) or len(predictions) != len(ids) or not np.isfinite(list(predictions.values())).all():
        raise AssertionError("pure external OOF predictions incomplete or non-finite")
    return {"predictions": predictions, "selections": selections, "fit_count": fit_count}


def prediction_array(records: list[dict], runs: dict, seed: str, arm: str) -> np.ndarray:
    if arm == PURE:
        return np.asarray([runs[seed]["predictions"][row["construct_id"]] for row in records], dtype=np.float64)
    return np.asarray([row["old_predictions"][seed][arm] for row in records], dtype=np.float64)


def favorable(values: dict) -> bool:
    return bool(values["delta_spearman"] > 0 and values["delta_rmse"] < 0)


def supported(comparison: dict) -> bool:
    return bool(
        comparison["delta_spearman_ci95"][0] > 0
        and comparison["delta_rmse_ci95"][1] < 0
        and comparison["holm_p_spearman"] < 0.05
        and comparison["holm_p_rmse"] < 0.05
        and comparison["sensitivity_signs_ok"]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    config_path = Path(args.config).resolve()
    cfg = json.loads(config_path.read_text())
    if cfg.get("schema") != "a8-rk03-mage-pure-external-nested-cv-protocol-v1" or not cfg.get("frozen_before_pure_external_model_fitting"):
        raise AssertionError("unexpected or unfrozen protocol")
    for key in ("nested_report", "nested_protocol", "nested_production_script"):
        if base.sha256(cfg["source"][key]) != cfg["source"][f"{key}_sha256"]:
            raise AssertionError(f"frozen source hash mismatch: {key}")
    records = load_oof(cfg)
    attach_external_features(cfg, records)
    matrix = feature_matrix(records)
    y = np.asarray([row["y"] for row in records], dtype=np.float64)
    seeds = [cfg["nested_cv"]["primary_outer_seed"]] + cfg["nested_cv"]["sensitivity_outer_seeds"]
    runs = {seed: nested_pure(records, matrix, y, seed, cfg) for seed in seeds}
    if sum(run["fit_count"] for run in runs.values()) != int(cfg["nested_cv"]["planned_pure_external_fit_count"]):
        raise AssertionError("pure external fit count mismatch")

    primary_seed = seeds[0]
    primary_predictions = {arm: prediction_array(records, runs, primary_seed, arm) for arm in [PURE] + OLD_ARMS}
    primary_models = {arm: base.metrics(y, pred) for arm, pred in primary_predictions.items()}
    comparisons = {}
    p_values = []
    for spec in cfg["primary_comparisons"]:
        candidate = primary_predictions[spec["candidate"]]
        reference = primary_predictions[spec["reference"]]
        result = base.paired_analysis(y, candidate, reference, spec["bootstrap_seed"], spec["permutation_seed"], int(cfg["inference"]["bootstrap_replicates"]))
        comparisons[spec["comparison_id"]] = result
        p_values.extend([result["permutation_p_spearman"], result["permutation_p_rmse"]])
    adjusted = base.holm(p_values)
    for i, spec in enumerate(cfg["primary_comparisons"]):
        result = comparisons[spec["comparison_id"]]
        result["holm_p_spearman"] = adjusted[2 * i]
        result["holm_p_rmse"] = adjusted[2 * i + 1]

    sensitivity = {}
    for seed in seeds[1:]:
        seed_comparisons = {}
        for spec in cfg["primary_comparisons"]:
            candidate = prediction_array(records, runs, seed, spec["candidate"])
            reference = prediction_array(records, runs, seed, spec["reference"])
            seed_comparisons[spec["comparison_id"]] = base.effect(y, candidate, reference)
        sensitivity[seed] = {
            "pure_external_model": base.metrics(y, prediction_array(records, runs, seed, PURE)),
            "comparisons": seed_comparisons,
        }
    for spec in cfg["primary_comparisons"]:
        comparison_id = spec["comparison_id"]
        comparisons[comparison_id]["sensitivity_signs_ok"] = all(favorable(sensitivity[seed]["comparisons"][comparison_id]) for seed in seeds[1:])
        comparisons[comparison_id]["supported_development_only"] = supported(comparisons[comparison_id])

    artifact_root = Path(cfg["outputs"]["large_artifact_root"])
    artifact_root.mkdir(parents=True, exist_ok=True)
    prediction_path = artifact_root / "pure_external_oof_predictions.csv"
    fields = ["construct_id", "original_split", "position", "observed_rich"] + PURE_COLUMNS
    for seed in seeds:
        fields.extend([f"outer_fold_{seed}", f"pred_{seed}_{PURE}"])
    with prediction_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for i, row in enumerate(records):
            out = {
                "construct_id": row["construct_id"],
                "original_split": row["original_split"],
                "position": row["position"],
                "observed_rich": row["y"],
                **{column: row["pure_features"][column] for column in PURE_COLUMNS},
            }
            for seed in seeds:
                out[f"outer_fold_{seed}"] = row["folds"][seed]
                out[f"pred_{seed}_{PURE}"] = runs[seed]["predictions"][row["construct_id"]]
            writer.writerow(out)
    feature_digest = hashlib.sha256(json.dumps([[row["construct_id"]] + [row["pure_features"][column] for column in PURE_COLUMNS] for row in records], separators=(",", ":")).encode()).hexdigest()
    artifact_files = {prediction_path.name: {"bytes": prediction_path.stat().st_size, "sha256": base.sha256(prediction_path)}}
    summary = {
        "schema": "a8-rk03-mage-pure-external-nested-cv-v1",
        "protocol_id": cfg["protocol_id"],
        "protocol_sha256": base.sha256(config_path),
        "technical_status": "PENDING_INDEPENDENT_VERIFICATION",
        "scientific_status": "DEVELOPMENT_ONLY_NO_GATE_CHANGE",
        "development_n": len(records),
        "test_construct_feature_rows_selected": 0,
        "test_predictions_generated": False,
        "test_metrics_generated": False,
        "raw_expression_value_or_stdev_fields_accessed": False,
        "new_sequences_read": False,
        "original_dev_no_go_modified": False,
        "test_authorized": False,
        "mechanism_increment_pass": False,
        "rk_g1_pass": False,
        "generator_training_authorized": False,
        "data_audit": {
            "original_split_counts": dict(Counter(row["original_split"] for row in records)),
            "external_feature_digest": feature_digest,
            "pure_feature_columns": PURE_COLUMNS,
            "categorical_feature_columns": [],
            "forbidden_intrinsic_features_used": False,
            "frozen_test_n_excluded": int(cfg["development_data"]["frozen_test_n"]),
        },
        "primary_seed": primary_seed,
        "primary_models": primary_models,
        "primary_comparisons": comparisons,
        "sensitivity": sensitivity,
        "pure_external_replacement_supported_development_only": comparisons["pure_external_rcs_minus_intrinsic"]["supported_development_only"],
        "full_over_pure_supported_development_only": comparisons["full_mechanism_minus_pure_external_rcs"]["supported_development_only"],
        "intrinsic_augmentation_over_pure_supported_development_only": comparisons["rcs_only_minus_pure_external_rcs"]["supported_development_only"],
        "nested_cv_selection": {seed: runs[seed]["selections"] for seed in seeds},
        "fit_counts": {seed: runs[seed]["fit_count"] for seed in seeds},
        "artifact_files": artifact_files,
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__, "numeric_threads": 1},
        "elapsed_s": time.perf_counter() - started,
        "limitations": cfg["gate_and_interpretation"],
    }
    base.dump(args.output, summary)
    print(json.dumps({
        "technical_status": summary["technical_status"],
        "pure_external_replacement_supported": summary["pure_external_replacement_supported_development_only"],
        "full_over_pure_supported": summary["full_over_pure_supported_development_only"],
        "intrinsic_augmentation_over_pure_supported": summary["intrinsic_augmentation_over_pure_supported_development_only"],
        "n": len(records),
        "fits": sum(run["fit_count"] for run in runs.values()),
        "elapsed_s": summary["elapsed_s"],
    }, indent=2))


if __name__ == "__main__":
    main()
