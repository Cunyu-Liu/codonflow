#!/usr/bin/env python3
"""Train frozen proxy predictors and evaluate retained test and sequence-OOD once."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
import scipy
import sklearn
from scipy.stats import pearsonr, spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    return value


def identity(row) -> tuple[str, str]:
    return row["source_row"], row["construct_id"]


def finite(value, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"non-finite {name}")
    return result


def read_core(split_path: Path, allowed: set[str], untouched: str):
    core = {}
    order = []
    untouched_count = 0
    with split_path.open(newline="") as handle:
        for raw in csv.DictReader(handle):
            assignment = raw["ood_assignment"]
            if assignment == untouched:
                untouched_count += 1
                continue
            if assignment not in allowed:
                continue
            key = identity(raw)
            if key in core:
                raise ValueError(f"duplicate identity {key}")
            expression = finite(raw["expression_value"], "expression_value")
            core[key] = {
                "source_row": raw["source_row"], "construct_id": raw["construct_id"],
                "protein_id": raw["protein_id"], "cluster_id": raw["operational_protein_cluster"],
                "ood_assignment": assignment, "origin_split": raw["split_assignment"],
                "expression": expression,
            }
            order.append(key)
    if untouched_count != 19072:
        raise ValueError(f"unexpected untouched count {untouched_count}")
    return core, order, untouched_count


def read_features(path: Path, core: dict, order: list[str]):
    numeric = [
        "gc_fraction", "cai", "full_cds_mfe_kcal_mol", "full_cds_mfe_per_nt",
        "mfe_5prime_48_kcal_mol", "source_Gave48", "source_Gave96",
        "source_Gave144", "source_Gz48v",
    ]
    required = set(numeric) - {"source_Gave144"}
    seen = set()
    with gzip.open(path, "rt", newline="") as handle:
        for raw in csv.DictReader(handle):
            key = identity(raw)
            if key not in core:
                continue
            if key in seen:
                raise ValueError(f"duplicate feature identity {key}")
            seen.add(key)
            row = core[key]
            if raw["protein_id"] != row["protein_id"] or raw["operational_protein_cluster"] != row["cluster_id"]:
                raise ValueError(f"identity/cluster mismatch {key}")
            if raw["split_assignment"] != row["origin_split"]:
                raise ValueError(f"origin split mismatch {key}")
            row["length_nt"] = int(raw["length_nt"])
            row["log_length_nt"] = math.log(row["length_nt"])
            for name in numeric:
                if raw[name] == "":
                    if name in required:
                        raise ValueError(f"missing required feature {name}")
                    row[name] = None
                else:
                    row[name] = finite(raw[name], name)
    if seen != set(order):
        raise ValueError("feature/core identity mismatch")
    return [core[key] for key in order]


def cluster_weights(rows: list[dict]) -> np.ndarray:
    counts = Counter(row["cluster_id"] for row in rows)
    return np.asarray([1.0 / counts[row["cluster_id"]] for row in rows], dtype=np.float64)


def make_transform(feature_names: list[str], normalization: dict, missing_indicators: list[str]):
    def transform(rows: list[dict]) -> tuple[np.ndarray, list[str]]:
        columns = []
        names = []
        for name in feature_names:
            stats = normalization[name]
            values = np.asarray([
                stats["mean"] if row[name] is None else row[name] for row in rows
            ], dtype=np.float64)
            columns.append((values - stats["mean"]) / stats["scale_ddof0"])
            names.append(name)
            if name in missing_indicators:
                columns.append(np.asarray([1.0 if row[name] is None else 0.0 for row in rows], dtype=np.float64))
                names.append(name + "__missing")
        if not columns:
            return np.zeros((len(rows), 0), dtype=np.float64), names
        matrix = np.column_stack(columns)
        if not np.isfinite(matrix).all():
            raise ValueError("non-finite transformed feature")
        return matrix, names
    return transform


def safe_corr(function, y, p):
    if len(y) < 2 or np.std(y) == 0 or np.std(p) == 0:
        return None
    value = float(function(y, p).statistic)
    return value if math.isfinite(value) else None


def metric_block(rows: list[dict], predictions: np.ndarray) -> dict:
    y = np.asarray([row["expression"] for row in rows], dtype=np.float64)
    p = np.asarray(predictions, dtype=np.float64)
    weights = cluster_weights(rows)
    mse = float(np.mean((y - p) ** 2))
    denominator = float(np.sum((y - np.mean(y)) ** 2))
    groups = defaultdict(list)
    for index, row in enumerate(rows):
        groups[row["cluster_id"]].append(index)
    group_y = np.asarray([np.mean(y[idx]) for idx in groups.values()])
    group_p = np.asarray([np.mean(p[idx]) for idx in groups.values()])
    centered_y = []
    centered_p = []
    eligible_clusters = 0
    for idx in groups.values():
        if len(idx) >= 2 and np.std(y[idx]) > 0:
            eligible_clusters += 1
            centered_y.extend((y[idx] - np.mean(y[idx])).tolist())
            centered_p.extend((p[idx] - np.mean(p[idx])).tolist())
    constant_prediction = bool(np.all(p == p[0]))
    return {
        "n_rows": len(rows), "n_clusters": len(groups),
        "row_mse": mse,
        "row_r2": float(1.0 - np.sum((y - p) ** 2) / denominator) if denominator > 0 else None,
        "row_pearson": safe_corr(pearsonr, y, p), "row_spearman": safe_corr(spearmanr, y, p),
        "cluster_balanced_mse": float(np.average((y - p) ** 2, weights=weights)),
        "cluster_mean_pearson": None if constant_prediction else safe_corr(pearsonr, group_y, group_p),
        "cluster_mean_spearman": None if constant_prediction else safe_corr(spearmanr, group_y, group_p),
        "within_cluster_centered_spearman": None if constant_prediction or not eligible_clusters else safe_corr(spearmanr, np.asarray(centered_y), np.asarray(centered_p)),
        "within_cluster_eligible_clusters": eligible_clusters,
        "within_cluster_eligible_rows": len(centered_y),
    }


def make_model(spec: dict, params: dict, histgb_fixed: dict):
    if spec["model"] == "ridge":
        return Ridge(alpha=float(params["alpha"]))
    if spec["model"] == "hist_gradient_boosting":
        return HistGradientBoostingRegressor(
            learning_rate=float(params["learning_rate"]), max_iter=int(params["max_iter"]),
            max_leaf_nodes=int(params["max_leaf_nodes"]), min_samples_leaf=int(params["min_samples_leaf"]),
            l2_regularization=float(params["l2_regularization"]),
            early_stopping=bool(histgb_fixed["early_stopping"]), random_state=int(histgb_fixed["random_state"]),
        )
    raise ValueError(spec["model"])


def bootstrap_comparison(rows, primary, reference, replicates, seed, percentiles):
    groups = defaultdict(list)
    for index, row in enumerate(rows):
        groups[row["cluster_id"]].append(index)
    cluster_ids = sorted(groups)
    y = np.asarray([row["expression"] for row in rows], dtype=np.float64)
    primary = np.asarray(primary, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    rng = np.random.default_rng(seed)
    deltas = {"row_spearman_delta": [], "cluster_balanced_mse_delta": []}
    for _ in range(replicates):
        sampled = rng.integers(0, len(cluster_ids), size=len(cluster_ids))
        idx = []
        weights = []
        for cluster_index in sampled:
            members = groups[cluster_ids[int(cluster_index)]]
            idx.extend(members)
            weights.extend([1.0 / len(members)] * len(members))
        idx = np.asarray(idx, dtype=int)
        weights = np.asarray(weights, dtype=np.float64)
        a = safe_corr(spearmanr, y[idx], primary[idx])
        b = safe_corr(spearmanr, y[idx], reference[idx])
        if a is not None and b is not None:
            deltas["row_spearman_delta"].append(a - b)
        deltas["cluster_balanced_mse_delta"].append(float(
            np.average((y[idx] - primary[idx]) ** 2, weights=weights)
            - np.average((y[idx] - reference[idx]) ** 2, weights=weights)
        ))
    output = {"replicates_requested": replicates, "seed": seed, "percentiles": percentiles, "statistics": {}}
    for name, values in deltas.items():
        array = np.asarray(values, dtype=np.float64)
        output["statistics"][name] = {
            "valid_replicates": len(array),
            "ci95": [float(x) for x in np.percentile(array, percentiles)] if len(array) else [None, None],
            "median": float(np.median(array)) if len(array) else None,
        }
    return output


def write_predictions(path: Path, rows: list[dict], predictions: dict[str, np.ndarray]):
    families = list(predictions)
    temporary = path.with_name(path.name + f".part.{os.getpid()}")
    with temporary.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            with gzip.io.TextIOWrapper(gz, encoding="utf-8", newline="") as text:
                writer = csv.writer(text, lineterminator="\n")
                writer.writerow(["source_row", "construct_id", "protein_id", "cluster_id", "ood_assignment", "origin_split", "expression"] + ["pred_" + f for f in families])
                for index, row in enumerate(rows):
                    writer.writerow([
                        row["source_row"], row["construct_id"], row["protein_id"], row["cluster_id"],
                        row["ood_assignment"], row["origin_split"], format(row["expression"], ".17g"),
                    ] + [format(float(predictions[f][index]), ".17g") for f in families])
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    protocol_bytes = args.protocol.read_bytes()
    protocol = json.loads(protocol_bytes)
    data = protocol["data"]
    for path_key, sha_key in [("split_csv", "split_sha256"), ("features_csv_gz", "features_sha256"), ("normalization_json", "normalization_sha256")]:
        if sha256_file(data[path_key]) != data[sha_key]:
            raise ValueError(f"SHA256 mismatch: {path_key}")
    core, order, untouched_count = read_core(Path(data["split_csv"]), set(data["allowed_assignments"]), data["untouched_assignment"])
    rows = read_features(Path(data["features_csv_gz"]), core, order)
    normalization_payload = json.loads(Path(data["normalization_json"]).read_text())
    normalization = normalization_payload["features"]
    by_partition = {name: [row for row in rows if row["ood_assignment"] == name] for name in data["allowed_assignments"]}
    if set(by_partition) != set(data["allowed_assignments"]):
        raise ValueError("partition mismatch")
    train = by_partition[data["fit_assignment"]]
    dev = by_partition[data["selection_assignment"]]
    y_train = np.asarray([row["expression"] for row in train], dtype=np.float64)
    w_train = cluster_weights(train)
    selection_records = []
    selected = {}
    selected_models = {}
    selected_transforms = {}
    for spec in protocol["families"]:
        family = spec["family"]
        candidates = []
        if spec["model"] == "weighted_train_mean":
            mean = float(np.average(y_train, weights=w_train))
            pred = np.full(len(dev), mean, dtype=np.float64)
            metrics = metric_block(dev, pred)
            candidates.append((metrics["cluster_balanced_mse"], 0, {}, mean, None, metrics))
        else:
            feature_names = protocol["feature_sets"][spec["feature_set"]]
            transform = make_transform(feature_names, normalization, protocol["missing_indicator_features"])
            x_train, transformed_names = transform(train)
            x_dev, _ = transform(dev)
            for index, params in enumerate(spec["candidates"]):
                model = make_model(spec, params, protocol["histgb_fixed"])
                model.fit(x_train, y_train, sample_weight=w_train)
                pred = model.predict(x_dev)
                metrics = metric_block(dev, pred)
                candidates.append((metrics["cluster_balanced_mse"], index, params, model, transform, metrics))
        best_score = min(item[0] for item in candidates)
        best = next(item for item in candidates if item[0] == best_score)
        for score, index, params, model, transform, metrics in candidates:
            selection_records.append({
                "family": family, "candidate_index": index, "params_json": json.dumps(params, sort_keys=True, separators=(",", ":")),
                "dev_cluster_balanced_mse": score, "dev_row_mse": metrics["row_mse"], "dev_row_spearman": metrics["row_spearman"],
                "selected": int(index == best[1]),
            })
        selected[family] = {"candidate_index": best[1], "params": best[2], "dev_metrics": best[5]}
        if spec["model"] == "weighted_train_mean":
            selected_models[family] = {"kind": "weighted_train_mean", "mean": best[3]}
            selected_transforms[family] = None
        else:
            selected_models[family] = {"kind": spec["model"], "model": best[3], "feature_names": feature_names, "transformed_names": transformed_names}
            selected_transforms[family] = best[4]
    primary_family = min(selected, key=lambda family: (selected[family]["dev_metrics"]["cluster_balanced_mse"], [x["family"] for x in protocol["families"]].index(family)))
    predictions = {}
    for family in selected:
        if family == "constant":
            predictions[family] = np.full(len(rows), selected_models[family]["mean"], dtype=np.float64)
        else:
            matrix, _ = selected_transforms[family](rows)
            predictions[family] = np.asarray(selected_models[family]["model"].predict(matrix), dtype=np.float64)
    if not all(np.isfinite(pred).all() for pred in predictions.values()):
        raise ValueError("non-finite predictions")
    metrics = {"partitions": {}, "sequence_ood_origin_strata": {}}
    row_indices = {name: [i for i, row in enumerate(rows) if row["ood_assignment"] == name] for name in data["allowed_assignments"]}
    for partition, indices in row_indices.items():
        subset = [rows[i] for i in indices]
        metrics["partitions"][partition] = {
            family: metric_block(subset, pred[indices]) for family, pred in predictions.items()
        }
    for origin in protocol["evaluation"]["sequence_ood_origin_strata"]:
        indices = [i for i, row in enumerate(rows) if row["ood_assignment"] == "sequence_ood" and row["origin_split"] == origin]
        subset = [rows[i] for i in indices]
        metrics["sequence_ood_origin_strata"][origin] = {
            family: metric_block(subset, pred[indices]) for family, pred in predictions.items()
        }
    boot = protocol["evaluation"]["bootstrap"]
    metrics["primary_comparison"] = {
        "primary_family": primary_family, "reference_family": "ridge_gc",
        "observed": {}, "bootstrap": {},
    }
    for partition in boot["partitions"]:
        indices = row_indices[partition]
        subset = [rows[i] for i in indices]
        primary = predictions[primary_family][indices]
        reference = predictions["ridge_gc"][indices]
        primary_metrics = metric_block(subset, primary)
        reference_metrics = metric_block(subset, reference)
        metrics["primary_comparison"]["observed"][partition] = {
            "row_spearman_delta": (primary_metrics["row_spearman"] - reference_metrics["row_spearman"]) if primary_metrics["row_spearman"] is not None and reference_metrics["row_spearman"] is not None else None,
            "cluster_balanced_mse_delta": primary_metrics["cluster_balanced_mse"] - reference_metrics["cluster_balanced_mse"],
        }
        metrics["primary_comparison"]["bootstrap"][partition] = bootstrap_comparison(
            subset, primary, reference, int(boot["replicates"]), int(boot["seed"]), boot["ci_percentiles"]
        )
    metrics_payload = {
        "schema_version": "a8-rk04-sequence-ood-model-metrics-v1",
        "protocol_id": protocol["protocol_id"], "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
        "split_sha256": data["split_sha256"], "features_sha256": data["features_sha256"], "normalization_sha256": data["normalization_sha256"],
        "primary_family": primary_family, "selected": selected, **metrics,
        "scope": protocol["scope"],
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    metrics_path = args.output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(json_safe(metrics_payload), indent=2, sort_keys=True, allow_nan=False) + "\n")
    selection_path = args.output_dir / "dev_model_selection.csv"
    with selection_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(selection_records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(selection_records)
    predictions_path = args.output_dir / "predictions.csv.gz"
    write_predictions(predictions_path, rows, predictions)
    models_path = args.output_dir / "selected_models.joblib"
    joblib.dump({"models": selected_models, "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(), "normalization": normalization}, models_path, compress=3)
    summary = {
        "schema_version": "a8-rk04-sequence-ood-model-summary-v1",
        "status": "PASS_PENDING_INDEPENDENT_VERIFICATION",
        "protocol_id": protocol["protocol_id"], "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
        "production_code_sha256": sha256_file(__file__),
        "primary_family": primary_family,
        "counts": {name: len(part) for name, part in by_partition.items()},
        "untouched_rows_excluded": untouched_count,
        "selected": selected,
        "test_metrics": metrics["partitions"]["test"], "sequence_ood_metrics": metrics["partitions"]["sequence_ood"],
        "primary_comparison": metrics["primary_comparison"],
        "artifacts": {
            "metrics": {"path": str(metrics_path), "sha256": sha256_file(metrics_path)},
            "dev_model_selection": {"path": str(selection_path), "sha256": sha256_file(selection_path)},
            "predictions": {"path": str(predictions_path), "sha256": sha256_file(predictions_path)},
            "selected_models": {"path": str(models_path), "sha256": sha256_file(models_path)},
        },
        "environment": {"python": sys.executable, "numpy": np.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__},
        "functional_untouched_evaluated": False, "generator_training_authorized": False,
        "scientific_scope": protocol["scope"],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.report.with_name(args.report.name + f".part.{os.getpid()}")
    temporary.write_text(json.dumps(json_safe(summary), indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(temporary, args.report)
    print(json.dumps(json_safe({
        "status": summary["status"], "primary_family": primary_family,
        "test": {family: {"row_spearman": values["row_spearman"], "cluster_balanced_mse": values["cluster_balanced_mse"]} for family, values in metrics["partitions"]["test"].items()},
        "sequence_ood": {family: {"row_spearman": values["row_spearman"], "cluster_balanced_mse": values["cluster_balanced_mse"]} for family, values in metrics["partitions"]["sequence_ood"].items()},
        "primary_comparison": metrics["primary_comparison"]["observed"],
    }), indent=2))


if __name__ == "__main__":
    main()
