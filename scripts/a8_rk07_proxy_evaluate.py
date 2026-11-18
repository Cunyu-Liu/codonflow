#!/usr/bin/env python3
"""Fit train-only RK07 proxy baselines and evaluate frozen protein-cluster splits."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.metadata
import io
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import log_softmax
from scipy.stats import pearsonr, spearmanr

from scripts.a8_rk07_proxy_features import atomic_json, sha256_file

MODEL_NAMES = ["cai", "gc_fraction", "full_cds_mfe_kcal_mol", "full_cds_mfe_per_nt", "mfe_5prime_48_kcal_mol", "combined_logistic"]
METRIC_NAMES = ["spearman", "pearson", "rmse", "mae", "top10_e5_enrichment"]
BOOTSTRAP_METRICS = ["spearman", "pearson", "rmse", "top10_e5_enrichment"]


def finite_float(value, field: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"non-finite {field}")
    return result


def read_features(path: str | Path, allowed_splits: list[str]) -> dict[str, list[dict]]:
    output = {split: [] for split in allowed_splits}
    numeric = [
        "gc_fraction", "cai", "full_cds_mfe_kcal_mol", "full_cds_mfe_per_nt",
        "mfe_5prime_48_kcal_mol", "source_Gave48", "source_Gave96",
        "source_Gave144", "source_Gz48v",
    ]
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            split = row["split_assignment"]
            if split not in output:
                continue
            row["length_nt"] = int(row["length_nt"])
            for key in numeric:
                row[key] = finite_float(row[key], key) if row[key] else None
            output[split].append(row)
    for split in output:
        output[split].sort(key=lambda row: int(row["source_row"]))
    return output


def attach_labels(features: dict[str, list[dict]], protocol: dict, enforce_expected: bool = True) -> None:
    wanted = {(row["source_row"], row["construct_id"]): row for rows in features.values() for row in rows}
    found = set()
    with open(protocol["split_file"], newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            if raw["source_id"] != protocol["source_id"] or raw["split_assignment"] not in features:
                continue
            key = (raw["source_row"], raw["construct_id"])
            if key not in wanted:
                if enforce_expected:
                    raise ValueError(f"unexpected source identity: {key}")
                continue
            row = wanted[key]
            if row["operational_protein_cluster"] != raw["operational_protein_cluster"]:
                raise ValueError(f"cluster mismatch: {key}")
            cds = "".join(raw["cds"].upper().split())
            if hashlib.sha256(cds.encode()).hexdigest() != row["cds_sha256"]:
                raise ValueError(f"CDS SHA mismatch: {key}")
            label = finite_float(raw[protocol["label_field"]], "expression label")
            if label not in protocol["label_classes"]:
                raise ValueError(f"unexpected label: {label}")
            row["label"] = label
            found.add(key)
    if found != set(wanted):
        raise ValueError(f"missing labels: {len(set(wanted) - found)}")
    for split, rows in features.items():
        if enforce_expected:
            expected = protocol["expected_rows"][split]
            if len(rows) != expected:
                raise ValueError(f"{split} rows={len(rows)} expected={expected}")


def feature_matrix(rows: list[dict], names: list[str]) -> np.ndarray:
    columns = []
    for name in names:
        if name == "log_length_nt":
            columns.append(np.log(np.array([row["length_nt"] for row in rows], dtype=float)))
        else:
            columns.append(np.array([row[name] for row in rows], dtype=float))
    matrix = np.column_stack(columns)
    if not np.isfinite(matrix).all():
        raise ValueError(f"non-finite feature matrix: {names}")
    return matrix


def fit_multinomial_logistic(x: np.ndarray, y: np.ndarray, classes: np.ndarray, l2: float, max_iter: int) -> dict:
    mean = x.mean(axis=0)
    scale = x.std(axis=0, ddof=0)
    if np.any(scale <= 1e-12):
        raise ValueError("zero-variance training feature")
    z = (x - mean) / scale
    class_index = {int(label): i for i, label in enumerate(classes)}
    targets = np.array([class_index[int(label)] for label in y], dtype=int)
    one_hot = np.eye(len(classes))[targets]
    n, d = z.shape
    k = len(classes)

    def objective(theta):
        weights = theta[:k * d].reshape(k, d)
        bias = theta[k * d:]
        logits = z @ weights.T + bias
        log_prob = log_softmax(logits, axis=1)
        prob = np.exp(log_prob)
        loss = -float(np.mean(log_prob[np.arange(n), targets])) + 0.5 * l2 * float(np.sum(weights * weights))
        residual = (prob - one_hot) / n
        grad_w = residual.T @ z + l2 * weights
        grad_b = residual.sum(axis=0)
        return loss, np.concatenate([grad_w.ravel(), grad_b])

    initial = np.zeros(k * d + k, dtype=float)
    result = minimize(objective, initial, jac=True, method="L-BFGS-B", options={"maxiter": int(max_iter), "ftol": 1e-12, "gtol": 1e-7, "maxls": 50})
    if not result.success:
        raise RuntimeError(f"logistic optimizer failed: {result.message}")
    weights = result.x[:k * d].reshape(k, d)
    bias = result.x[k * d:]
    _, gradient = objective(result.x)
    diagnostics = {
        "success": bool(result.success), "message": str(result.message),
        "iterations": int(result.nit), "objective": float(result.fun),
        "gradient_max_abs": float(np.max(np.abs(gradient))),
        "l2": float(l2), "max_iter": int(max_iter),
    }
    if diagnostics["gradient_max_abs"] > 1e-4:
        raise RuntimeError(f"logistic gradient did not converge: {diagnostics}")
    return {
        "feature_names": None, "classes": [int(v) for v in classes],
        "train_mean": mean.tolist(), "train_scale": scale.tolist(),
        "weights": weights.tolist(), "bias": bias.tolist(),
        "optimizer": diagnostics,
    }


def logistic_expected_score(model: dict, x: np.ndarray) -> np.ndarray:
    mean = np.array(model["train_mean"], dtype=float)
    scale = np.array(model["train_scale"], dtype=float)
    weights = np.array(model["weights"], dtype=float)
    bias = np.array(model["bias"], dtype=float)
    classes = np.array(model["classes"], dtype=float)
    logits = ((x - mean) / scale) @ weights.T + bias
    return np.exp(log_softmax(logits, axis=1)) @ classes


def fit_univariate(x: np.ndarray, y: np.ndarray) -> dict:
    design = np.column_stack([np.ones(len(x)), x])
    intercept, slope = np.linalg.lstsq(design, y, rcond=None)[0]
    return {"intercept": float(intercept), "slope": float(slope)}


def univariate_predict(model: dict, x: np.ndarray) -> np.ndarray:
    return model["intercept"] + model["slope"] * x


def prediction_metrics(y: np.ndarray, prediction: np.ndarray, source_rows: np.ndarray, top_fraction: float, positive_label: int) -> dict:
    y = np.asarray(y, dtype=float)
    prediction = np.asarray(prediction, dtype=float)
    if len(y) == 0 or len(y) != len(prediction):
        raise ValueError("invalid prediction vector")
    spearman = float(spearmanr(y, prediction).statistic)
    pearson = float(pearsonr(y, prediction).statistic)
    rmse = float(np.sqrt(np.mean((y - prediction) ** 2)))
    mae = float(np.mean(np.abs(y - prediction)))
    k = max(1, int(math.ceil(top_fraction * len(y))))
    order = np.lexsort((source_rows.astype(int), -prediction))[:k]
    positive = y == positive_label
    base_rate = float(np.mean(positive))
    top_rate = float(np.mean(positive[order]))
    enrichment = top_rate / base_rate if base_rate > 0 else float("nan")
    values = {
        "spearman": spearman, "pearson": pearson, "rmse": rmse, "mae": mae,
        "top10_e5_enrichment": float(enrichment), "top10_e5_rate": top_rate,
        "baseline_e5_rate": base_rate, "top10_n": k, "n": len(y),
    }
    if not all(math.isfinite(values[key]) for key in METRIC_NAMES):
        raise ValueError(f"non-finite metrics: {values}")
    return values


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values, key=p_values.get)
    adjusted = {}
    running = 0.0
    m = len(ordered)
    for rank, key in enumerate(ordered):
        running = max(running, min(1.0, (m - rank) * p_values[key]))
        adjusted[key] = running
    return adjusted


def bootstrap_analysis(y, predictions, clusters, source_rows, protocol, seed_offset=0) -> dict:
    cfg = protocol["bootstrap"]
    rng = np.random.default_rng(int(cfg["seed"]) + int(seed_offset))
    groups = sorted(set(clusters))
    indices_by_group = {group: np.flatnonzero(clusters == group) for group in groups}
    b = int(cfg["replicates"])
    arrays = {name: np.zeros((b, len(BOOTSTRAP_METRICS)), dtype=float) for name in MODEL_NAMES}
    for replicate in range(b):
        sampled = rng.choice(groups, size=len(groups), replace=True)
        indices = np.concatenate([indices_by_group[group] for group in sampled])
        for name in MODEL_NAMES:
            metrics = prediction_metrics(y[indices], predictions[name][indices], source_rows[indices], protocol["top_k_fraction"], protocol["top_k_positive_label"])
            arrays[name][replicate] = [metrics[key] for key in BOOTSTRAP_METRICS]
    intervals = {}
    for name in MODEL_NAMES:
        intervals[name] = {}
        for j, metric in enumerate(BOOTSTRAP_METRICS):
            low, high = np.percentile(arrays[name][:, j], [2.5, 97.5])
            intervals[name][metric] = [float(low), float(high)]
    paired = {}
    p_values = {}
    for proxy in protocol["primary_proxies"]:
        paired[proxy] = {}
        for j, metric in enumerate(BOOTSTRAP_METRICS):
            difference = arrays["combined_logistic"][:, j] - arrays[proxy][:, j]
            low, high = np.percentile(difference, [2.5, 97.5])
            paired[proxy][metric + "_difference"] = [float(low), float(high)]
        difference = arrays["combined_logistic"][:, 0] - arrays[proxy][:, 0]
        left = (int(np.sum(difference <= 0)) + 1) / (b + 1)
        right = (int(np.sum(difference >= 0)) + 1) / (b + 1)
        p_values[proxy] = min(1.0, 2 * min(left, right))
        paired[proxy]["spearman_p_raw"] = float(p_values[proxy])
    adjusted = holm_adjust(p_values)
    for proxy in protocol["primary_proxies"]:
        paired[proxy]["spearman_p_holm"] = float(adjusted[proxy])
    return {"metric_95ci": intervals, "paired_combined_minus_proxy": paired}


def tercile_thresholds(train_rows: list[dict], variables: list[str]) -> dict:
    return {
        variable: np.quantile(np.array([row[variable] for row in train_rows], dtype=float), [1 / 3, 2 / 3]).tolist()
        for variable in variables
    }


def tercile_index(value: float, thresholds: list[float]) -> int:
    return int(np.searchsorted(np.array(thresholds), value, side="right"))


def atomic_prediction_csv(path: str | Path, datasets, predictions, thresholds, protocol) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    fields = ["split_assignment", "source_row", "construct_id", "operational_protein_cluster", "label", "length_nt", "gc_fraction", "length_tercile", "gc_tercile"] + ["pred_" + name for name in MODEL_NAMES]
    with open(tmp, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                for split in datasets:
                    for i, row in enumerate(datasets[split]):
                        out = {key: row[key] for key in ("split_assignment", "source_row", "construct_id", "operational_protein_cluster", "label", "length_nt", "gc_fraction")}
                        out["length_tercile"] = tercile_index(row["length_nt"], thresholds["length_nt"])
                        out["gc_tercile"] = tercile_index(row["gc_fraction"], thresholds["gc_fraction"])
                        for name in MODEL_NAMES:
                            out["pred_" + name] = predictions[split][name][i]
                        writer.writerow(out)
    os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--features", required=True)
    parser.add_argument("--feature-summary", required=True)
    parser.add_argument("--evaluation-splits", nargs="+", default=["train", "dev"])
    parser.add_argument("--frozen-test-confirmation", action="store_true")
    parser.add_argument("--dev-baseline-result", default=None)
    parser.add_argument("--allow-smoke-evaluation", action="store_true", help="train/dev development only; never valid with test")
    parser.add_argument("--smoke-bootstrap-replicates", type=int, default=20)
    parser.add_argument("--output-result", required=True)
    parser.add_argument("--output-predictions", required=True)
    args = parser.parse_args()
    protocol_path = Path(args.protocol).resolve()
    protocol = json.loads(protocol_path.read_text())
    allowed = protocol["allowed_splits"]
    if not args.evaluation_splits or args.evaluation_splits[0] != "train" or any(split not in allowed for split in args.evaluation_splits):
        raise ValueError("evaluation splits must start with train and use train/dev/test")
    if len(set(args.evaluation_splits)) != len(args.evaluation_splits):
        raise ValueError("duplicate evaluation split")
    test_requested = "test" in args.evaluation_splits
    if test_requested and not args.frozen_test_confirmation:
        raise ValueError("test requires --frozen-test-confirmation")
    if test_requested and not args.dev_baseline_result:
        raise ValueError("test requires the frozen dev baseline result")
    if test_requested and args.allow_smoke_evaluation:
        raise ValueError("smoke evaluation can never access test")
    feature_summary = json.loads(Path(args.feature_summary).read_text())
    expected_feature_status = "smoke_features_only" if args.allow_smoke_evaluation else "full_features_ready"
    if feature_summary["status"] != expected_feature_status:
        raise ValueError(f"feature status must be {expected_feature_status}")
    if args.allow_smoke_evaluation:
        if args.smoke_bootstrap_replicates < 2:
            raise ValueError("smoke bootstrap needs at least two replicates")
        protocol["bootstrap"]["replicates"] = args.smoke_bootstrap_replicates
    if feature_summary["protocol_sha256"] != sha256_file(protocol_path):
        raise ValueError("protocol hash mismatch")
    if feature_summary["feature_file_sha256"] != sha256_file(args.features):
        raise ValueError("feature artifact hash mismatch")
    datasets = read_features(args.features, args.evaluation_splits)
    attach_labels(datasets, protocol, enforce_expected=not args.allow_smoke_evaluation)
    train_rows = datasets["train"]
    y_train = np.array([row["label"] for row in train_rows], dtype=float)
    model = fit_multinomial_logistic(
        feature_matrix(train_rows, protocol["combined_features"]), y_train,
        np.array(protocol["label_classes"], dtype=int),
        protocol["combined_model"]["l2"], protocol["combined_model"]["max_iter"],
    )
    model["feature_names"] = protocol["combined_features"]
    univariate = {}
    for proxy in protocol["primary_proxies"]:
        univariate[proxy] = fit_univariate(feature_matrix(train_rows, [proxy])[:, 0], y_train)
    predictions = {}
    for split, rows in datasets.items():
        predictions[split] = {}
        for proxy in protocol["primary_proxies"]:
            predictions[split][proxy] = univariate_predict(univariate[proxy], feature_matrix(rows, [proxy])[:, 0])
        predictions[split]["combined_logistic"] = logistic_expected_score(model, feature_matrix(rows, protocol["combined_features"]))
    thresholds = tercile_thresholds(train_rows, protocol["stratification"]["variables"])
    split_results = {}
    stratified_results = {}
    for split_index, split in enumerate(args.evaluation_splits):
        # The frozen dev baseline is checked before any test metric is computed.
        rows = datasets[split]
        y = np.array([row["label"] for row in rows], dtype=float)
        source_rows = np.array([row["source_row"] for row in rows], dtype=int)
        clusters = np.array([row["operational_protein_cluster"] for row in rows])
        model_results = {}
        for name in MODEL_NAMES:
            point = prediction_metrics(y, predictions[split][name], source_rows, protocol["top_k_fraction"], protocol["top_k_positive_label"])
            if name != "combined_logistic":
                point["raw_spearman"] = float(spearmanr(y, feature_matrix(rows, [name])[:, 0]).statistic)
            model_results[name] = {"point": point}
        if split != "train":
            boot = bootstrap_analysis(y, predictions[split], clusters, source_rows, protocol, seed_offset=split_index)
            for name in MODEL_NAMES:
                model_results[name]["bootstrap_95ci"] = boot["metric_95ci"][name]
            paired = boot["paired_combined_minus_proxy"]
            for proxy in protocol["primary_proxies"]:
                for metric in BOOTSTRAP_METRICS:
                    key = metric + "_point_difference"
                    paired[proxy][key] = model_results["combined_logistic"]["point"][metric] - model_results[proxy]["point"][metric]
            split_results[split] = {"n": len(rows), "models": model_results, "paired_comparisons": paired}
        else:
            split_results[split] = {"n": len(rows), "models": model_results}
        strata = {}
        for variable in protocol["stratification"]["variables"]:
            strata[variable] = {}
            for index, label in enumerate(("low", "mid", "high")):
                selected = np.array([tercile_index(row[variable], thresholds[variable]) == index for row in rows])
                if int(selected.sum()) < 10:
                    strata[variable][label] = {"n": int(selected.sum()), "status": "insufficient_n"}
                    continue
                models = {}
                for name in MODEL_NAMES:
                    models[name] = prediction_metrics(y[selected], predictions[split][name][selected], source_rows[selected], protocol["top_k_fraction"], protocol["top_k_positive_label"])
                strata[variable][label] = {"n": int(selected.sum()), "models": models}
        stratified_results[split] = strata
        if split == "dev" and test_requested:
            baseline_path = Path(args.dev_baseline_result)
            baseline = json.loads(baseline_path.read_text())
            current = {"model": model, "univariate": univariate, "dev": split_results["dev"], "dev_strata": stratified_results["dev"], "thresholds": thresholds}
            frozen = {"model": baseline["combined_model"], "univariate": baseline["univariate_models"], "dev": baseline["split_metrics"]["dev"], "dev_strata": baseline["stratified_metrics"]["dev"], "thresholds": baseline["train_stratification_thresholds"]}
            if current != frozen:
                raise RuntimeError("frozen dev model/results differ; test evaluation aborted")
    atomic_prediction_csv(args.output_predictions, datasets, predictions, thresholds, protocol)
    result = {
        "status": "frozen_test_evaluated_pending_independent_verification" if test_requested else ("smoke_dev_only_no_test_access" if args.allow_smoke_evaluation else "dev_only_no_test_access"),
        "protocol_id": protocol["protocol_id"], "protocol_sha256": sha256_file(protocol_path),
        "command": [sys.executable, "-m", "scripts.a8_rk07_proxy_evaluate", *sys.argv[1:]],
        "evaluation_code_sha256": sha256_file(Path(__file__).resolve()),
        "feature_file": str(Path(args.features).resolve()), "feature_file_sha256": sha256_file(args.features),
        "feature_summary_sha256": sha256_file(args.feature_summary),
        "split_file": protocol["split_file"], "split_sha256": protocol["split_sha256"],
        "evaluation_splits": args.evaluation_splits, "test_metrics_computed": test_requested,
        "runtime_overrides": {"smoke_bootstrap_replicates": args.smoke_bootstrap_replicates} if args.allow_smoke_evaluation else None,
        "dev_baseline_result": str(Path(args.dev_baseline_result).resolve()) if args.dev_baseline_result else None,
        "dev_baseline_result_sha256": sha256_file(args.dev_baseline_result) if args.dev_baseline_result else None,
        "dev_baseline_exact_match": bool(test_requested),
        "train_fit_only": True, "forbidden_split_used": False,
        "combined_model": model, "univariate_models": univariate,
        "split_metrics": split_results, "train_stratification_thresholds": thresholds,
        "stratified_metrics": stratified_results,
        "prediction_file": str(Path(args.output_predictions).resolve()),
        "prediction_file_sha256": sha256_file(args.output_predictions),
        "environment": {
            "python": os.sys.version.split()[0], "numpy": np.__version__,
            "scipy": importlib.metadata.version("scipy"),
        },
        "scientific_scope": protocol["scientific_scope"],
        "prohibited_claims": protocol["prohibited_claims"],
    }
    atomic_json(args.output_result, result)
    print(json.dumps({
        "status": result["status"], "model_iterations": model["optimizer"]["iterations"],
        "gradient_max_abs": model["optimizer"]["gradient_max_abs"],
        "splits": {split: {name: split_results[split]["models"][name]["point"]["spearman"] for name in MODEL_NAMES} for split in args.evaluation_splits},
        "prediction_file_sha256": result["prediction_file_sha256"],
    }, indent=2))


if __name__ == "__main__":
    main()
