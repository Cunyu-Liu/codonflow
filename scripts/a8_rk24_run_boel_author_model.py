#!/usr/bin/env python3
"""Run the frozen RK24 Boel author-structure train-refit protein-OOD baseline."""
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
import pickle
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import pearsonr, rankdata, spearmanr

from scripts.a8_rk07_proxy_evaluate import fit_multinomial_logistic, logistic_expected_score
from scripts.a8_rk23_run_boel_uh import atomic_json, fast_spearman, holm_adjust, regression_metrics, sha256_file
from scripts.a8_rk24_build_features import CODONS, core_from_cds


INPUT_HASH_KEYS = {
    "split_file": "split_sha256",
    "base_feature_file": "base_feature_file_sha256",
    "base_feature_summary": "base_feature_summary_sha256",
    "feature_file": "feature_file_sha256",
    "feature_preflight": "feature_preflight_sha256",
    "main_article_file": "main_article_sha256",
    "supplementary_data1_file": "supplementary_data1_sha256",
}
ENDPOINTS = ["binary_delta_auc", "binary_logloss_improvement", "multiclass_delta_spearman", "multiclass_mse_improvement"]


def author_feature_names(protocol: dict) -> list[str]:
    names = list(protocol["comparison"]["author_noncodon_features"])
    names += [f"cf_{c}" for c in CODONS if c != "ATG"]
    names += list(protocol["comparison"]["author_regional_features"])
    if len(names) != int(protocol["comparison"]["author_feature_count"]) or len(set(names)) != len(names):
        raise ValueError("author feature contract mismatch")
    return names


def feature_matrix(rows: list[dict], names: list[str], single_slopes: dict[str, float] | None = None) -> np.ndarray:
    columns = []
    for name in names:
        if name == "log_length_nt":
            columns.append(np.log(np.asarray([float(r["length_nt"]) for r in rows], dtype=float)))
        elif name in {"s7_16", "s17_32"}:
            if single_slopes is None:
                raise ValueError("regional slopes require train-only single-codon model")
            start, end = (6, 16) if name == "s7_16" else (16, 32)
            values = []
            for row in rows:
                selected = row["core_codons"][start:end]
                if len(selected) != end - start:
                    raise ValueError(f"incomplete regional window: {name}")
                values.append(float(np.mean([single_slopes[c] for c in selected])))
            columns.append(np.asarray(values, dtype=float))
        else:
            columns.append(np.asarray([float(r[name]) for r in rows], dtype=float))
    matrix = np.column_stack(columns)
    if not np.isfinite(matrix).all():
        raise ValueError(f"non-finite features: {names}")
    return matrix


def load_data(protocol: dict, splits: list[str]) -> dict[str, list[dict]]:
    wanted = {}
    with gzip.open(protocol["feature_file"], "rt", encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            split = raw["split_assignment"]
            if split not in splits:
                continue
            key = (raw["source_row"], raw["construct_id"])
            if key in wanted:
                raise ValueError(f"duplicate feature identity: {key}")
            wanted[key] = dict(raw)
    output = {s: [] for s in splits}
    found = set()
    with open(protocol["split_file"], newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            if raw["source_id"] != protocol["source_id"]:
                continue
            split = raw["split_assignment"]
            if split == protocol["forbidden_split"]:
                raise ValueError("forbidden functional_untouched row encountered")
            if split not in splits:
                continue
            key = (raw["source_row"], raw["construct_id"])
            if key not in wanted:
                raise ValueError(f"unexpected split identity: {key}")
            row = wanted[key]
            cds = "".join(raw["cds"].upper().split())
            if hashlib.sha256(cds.encode()).hexdigest() != row["cds_sha256"]:
                raise ValueError(f"CDS hash mismatch: {key}")
            if row["operational_protein_cluster"] != raw["operational_protein_cluster"]:
                raise ValueError(f"cluster mismatch: {key}")
            source = json.loads(raw["features_json"])
            if float(source["Gz48v"]) != float(row["source_Gz48v"]):
                raise ValueError(f"UH mismatch: {key}")
            core_cds, core_protein, core_codons = core_from_cds(cds)
            if hashlib.sha256(core_cds.encode()).hexdigest() != row["core_cds_sha256"]:
                raise ValueError(f"core CDS hash mismatch: {key}")
            if hashlib.sha256(core_protein.encode()).hexdigest() != row["core_protein_sha256"]:
                raise ValueError(f"core protein hash mismatch: {key}")
            if len(core_cds) != int(row["core_length_nt"]) or len(core_protein) != int(row["core_length_aa"]):
                raise ValueError(f"core length mismatch: {key}")
            label = float(raw[protocol["label_field"]])
            if label not in protocol["label_classes"]:
                raise ValueError(f"unexpected label: {label}")
            row["label"] = label
            row["core_codons"] = core_codons
            output[split].append(row)
            found.add(key)
    if found != set(wanted):
        raise ValueError("feature/split identities do not match")
    for split, rows in output.items():
        rows.sort(key=lambda r: int(r["source_row"]))
        if len(rows) != int(protocol["expected_rows"][split]):
            raise ValueError(f"{split} row count mismatch")
    return output


def fit_binary_logistic(x: np.ndarray, y: np.ndarray, l2: float, max_iter: int, gradient_tolerance: float) -> dict:
    x = np.asarray(x, dtype=float)
    if x.ndim == 1:
        x = x[:, None]
    y = np.asarray(y, dtype=float)
    if set(np.unique(y)) != {0.0, 1.0}:
        raise ValueError("binary logistic requires both classes")
    mean = x.mean(axis=0)
    scale = x.std(axis=0, ddof=0)
    if np.any(scale <= 1e-12):
        raise ValueError("zero-variance binary training feature")
    z = (x - mean) / scale
    n, d = z.shape

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        w = theta[:d]
        b = theta[d]
        logits = z @ w + b
        # mean log(1+exp(logit))-y*logit, evaluated stably
        loss = float(np.mean(np.logaddexp(0.0, logits) - y * logits)) + 0.5 * l2 * float(w @ w)
        residual = expit(logits) - y
        grad_w = z.T @ residual / n + l2 * w
        grad_b = float(np.sum(residual) / n)
        return loss, np.concatenate([grad_w, [grad_b]])

    result = minimize(objective, np.zeros(d + 1), jac=True, method="L-BFGS-B",
                      options={"maxiter": int(max_iter), "ftol": 1e-13, "gtol": 1e-9, "maxls": 50})
    _, gradient = objective(result.x)
    diagnostics = {
        "success": bool(result.success), "message": str(result.message), "iterations": int(result.nit),
        "objective": float(result.fun), "gradient_max_abs": float(np.max(np.abs(gradient))),
        "l2": float(l2), "max_iter": int(max_iter),
    }
    if not result.success or diagnostics["gradient_max_abs"] > gradient_tolerance:
        raise RuntimeError(f"binary logistic did not converge: {diagnostics}")
    w = result.x[:d]
    return {
        "train_mean": mean.tolist(), "train_scale": scale.tolist(),
        "weights": w.tolist(), "bias": float(result.x[d]), "optimizer": diagnostics,
    }


def binary_predict(model: dict, x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    if x.ndim == 1:
        x = x[:, None]
    mean = np.asarray(model["train_mean"], dtype=float)
    scale = np.asarray(model["train_scale"], dtype=float)
    weights = np.asarray(model["weights"], dtype=float)
    return expit(((x - mean) / scale) @ weights + float(model["bias"]))


def fit_models(train_rows: list[dict], protocol: dict) -> dict:
    y = np.asarray([r["label"] for r in train_rows], dtype=float)
    extreme = (y == 0) | (y == 5)
    y_binary = (y[extreme] == 5).astype(float)
    single_cfg = protocol["models"]["single_codon_binary"]
    single_models = {}
    single_slopes = {}
    for codon in CODONS:
        x = np.asarray([float(r[f"cf_{codon}"]) for r in train_rows], dtype=float)[extreme]
        model = fit_binary_logistic(x, y_binary, single_cfg["l2"], single_cfg["max_iter"], single_cfg["gradient_max_abs_tolerance"])
        raw_slope = float(model["weights"][0] / model["train_scale"][0])
        raw_intercept = float(model["bias"] - model["weights"][0] * model["train_mean"][0] / model["train_scale"][0])
        single_models[codon] = {"raw_slope": raw_slope, "raw_intercept": raw_intercept, "standardized_model": model}
        single_slopes[codon] = raw_slope

    base_names = list(protocol["comparison"]["base_features"])
    full_names = author_feature_names(protocol)
    base_extreme = feature_matrix([r for r, keep in zip(train_rows, extreme) if keep], base_names, single_slopes)
    full_extreme = feature_matrix([r for r, keep in zip(train_rows, extreme) if keep], full_names, single_slopes)
    binary_cfg = protocol["models"]["base_binary"]
    base_binary = fit_binary_logistic(base_extreme, y_binary, binary_cfg["l2"], binary_cfg["max_iter"], binary_cfg["gradient_max_abs_tolerance"])
    binary_cfg = protocol["models"]["author_binary"]
    author_binary = fit_binary_logistic(full_extreme, y_binary, binary_cfg["l2"], binary_cfg["max_iter"], binary_cfg["gradient_max_abs_tolerance"])

    base_all = feature_matrix(train_rows, base_names, single_slopes)
    full_all = feature_matrix(train_rows, full_names, single_slopes)
    classes = np.asarray(protocol["label_classes"], dtype=int)
    cfg = protocol["models"]["base_multiclass"]
    base_multi = fit_multinomial_logistic(base_all, y, classes, cfg["l2"], cfg["max_iter"])
    base_multi["feature_names"] = base_names
    cfg = protocol["models"]["author_multiclass"]
    author_multi = fit_multinomial_logistic(full_all, y, classes, cfg["l2"], cfg["max_iter"])
    author_multi["feature_names"] = full_names
    return {
        "single_models": single_models,
        "single_slopes": single_slopes,
        "base_binary": base_binary,
        "author_binary": author_binary,
        "base_multiclass": base_multi,
        "author_multiclass": author_multi,
        "base_feature_names": base_names,
        "author_feature_names": full_names,
    }


def predict_split(models: dict, rows: list[dict]) -> dict[str, np.ndarray]:
    slopes = models["single_slopes"]
    xb = feature_matrix(rows, models["base_feature_names"], slopes)
    xa = feature_matrix(rows, models["author_feature_names"], slopes)
    return {
        "base_binary_p_e5": binary_predict(models["base_binary"], xb),
        "author_binary_p_e5": binary_predict(models["author_binary"], xa),
        "base_multiclass_expected": logistic_expected_score(models["base_multiclass"], xb),
        "author_multiclass_expected": logistic_expected_score(models["author_multiclass"], xa),
    }


def fast_auc(y: np.ndarray, probability: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)
    n1 = int(np.sum(y == 1))
    n0 = int(np.sum(y == 0))
    if n1 == 0 or n0 == 0:
        raise ValueError("AUC requires both classes")
    ranks = rankdata(probability)
    return float((np.sum(ranks[y == 1]) - n1 * (n1 + 1) / 2) / (n1 * n0))


def fast_logloss(y: np.ndarray, probability: np.ndarray) -> float:
    p = np.clip(np.asarray(probability, dtype=float), 1e-15, 1 - 1e-15)
    y = np.asarray(y, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log1p(-p)))


def binary_effects(y: np.ndarray, base: np.ndarray, author: np.ndarray) -> tuple[float, float]:
    return fast_auc(y, author) - fast_auc(y, base), fast_logloss(y, base) - fast_logloss(y, author)


def multiclass_effects(y: np.ndarray, base: np.ndarray, author: np.ndarray) -> tuple[float, float]:
    return fast_spearman(y, author) - fast_spearman(y, base), float(np.mean((y - base) ** 2) - np.mean((y - author) ** 2))


def resample_primary(y: np.ndarray, predictions: dict[str, np.ndarray], clusters: np.ndarray, protocol: dict, split_index: int, output_npz: str | Path) -> dict:
    b = int(protocol["bootstrap"]["replicates"])
    if b != int(protocol["permutation"]["replicates"]):
        raise ValueError("paired arrays require equal replicate counts")
    boot = np.zeros((b, 4), dtype=float)
    perm = np.zeros((b, 4), dtype=float)
    boot_rng = np.random.default_rng(int(protocol["bootstrap"]["seed"]) + split_index)
    perm_rng = np.random.default_rng(int(protocol["permutation"]["seed"]) + split_index)

    multi_groups = sorted(set(clusters))
    multi_indices = [np.flatnonzero(clusters == g) for g in multi_groups]
    mask = (y == 0) | (y == 5)
    yb = (y[mask] == 5).astype(float)
    cb = clusters[mask]
    binary_groups = sorted(set(cb))
    binary_indices = [np.flatnonzero(cb == g) for g in binary_groups]
    bb = predictions["base_binary_p_e5"]
    ab = predictions["author_binary_p_e5"]
    bm = predictions["base_multiclass_expected"]
    am = predictions["author_multiclass_expected"]
    bb_extreme = bb[mask]
    ab_extreme = ab[mask]

    for replicate in range(b):
        sampled = boot_rng.integers(0, len(binary_indices), size=len(binary_indices))
        idx = np.concatenate([binary_indices[i] for i in sampled])
        boot[replicate, :2] = binary_effects(yb[idx], bb_extreme[idx], ab_extreme[idx])
        sampled = boot_rng.integers(0, len(multi_indices), size=len(multi_indices))
        idx = np.concatenate([multi_indices[i] for i in sampled])
        boot[replicate, 2:] = multiclass_effects(y[idx], bm[idx], am[idx])

        pb = bb_extreme.copy()
        pa = ab_extreme.copy()
        swap = perm_rng.random(len(binary_indices)) < 0.5
        for selected, indices in zip(swap, binary_indices):
            if selected:
                pb[indices], pa[indices] = ab_extreme[indices], bb_extreme[indices]
        perm[replicate, :2] = binary_effects(yb, pb, pa)
        pb = bm.copy()
        pa = am.copy()
        swap = perm_rng.random(len(multi_indices)) < 0.5
        for selected, indices in zip(swap, multi_indices):
            if selected:
                pb[indices], pa[indices] = am[indices], bm[indices]
        perm[replicate, 2:] = multiclass_effects(y, pb, pa)

    point = np.asarray([
        fast_auc(yb, ab_extreme) - fast_auc(yb, bb_extreme),
        fast_logloss(yb, bb_extreme) - fast_logloss(yb, ab_extreme),
        float(spearmanr(y, am).statistic - spearmanr(y, bm).statistic),
        float(np.mean((y - bm) ** 2) - np.mean((y - am) ** 2)),
    ])
    raw_p = {}
    report = {}
    for j, name in enumerate(ENDPOINTS):
        effect = float(point[j])
        ci = np.percentile(boot[:, j], [2.5, 97.5])
        p = float((1 + np.sum(np.abs(perm[:, j]) >= abs(effect))) / (b + 1))
        raw_p[name] = p
        report[name] = {
            "effect": effect, "ci95": [float(ci[0]), float(ci[1])], "p_raw": p,
            "passes_direction": bool(effect > 0 and ci[0] > 0),
        }
    adjusted = holm_adjust(raw_p)
    for name in ENDPOINTS:
        report[name]["p_holm"] = adjusted[name]
        report[name]["passes_all"] = bool(report[name]["passes_direction"] and adjusted[name] < 0.05)
    output_npz = Path(output_npz)
    output_npz.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_npz.with_name(output_npz.name + f".tmp.{os.getpid()}.npz")
    np.savez_compressed(tmp, bootstrap_effects=boot, permutation_effects=perm, endpoints=np.asarray(ENDPOINTS))
    os.replace(tmp, output_npz)
    return {
        "comparisons": report,
        "all_four_pass": bool(all(v["passes_all"] for v in report.values())),
        "passed_endpoints": sum(v["passes_all"] for v in report.values()),
        "bootstrap_replicates": b, "permutation_replicates": b,
        "binary_clusters": len(binary_groups), "multiclass_clusters": len(multi_groups),
        "resampling_file": str(output_npz.resolve()), "resampling_sha256": sha256_file(output_npz),
    }


def evaluate_split(models: dict, rows: list[dict], protocol: dict, split: str, split_index: int, resampling_path: str | Path | None, run_inference: bool = True) -> tuple[dict, dict]:
    y = np.asarray([r["label"] for r in rows], dtype=float)
    source_rows = np.asarray([r["source_row"] for r in rows], dtype=int)
    clusters = np.asarray([r["operational_protein_cluster"] for r in rows])
    predictions = predict_split(models, rows)
    mask = (y == 0) | (y == 5)
    yb = (y[mask] == 5).astype(float)
    metrics = {"binary": {"n": int(mask.sum()), "n_e0": int(np.sum(y == 0)), "n_e5": int(np.sum(y == 5))}, "multiclass": {}}
    for role in ("base", "author"):
        p = predictions[f"{role}_binary_p_e5"][mask]
        metrics["binary"][role] = {
            "auc": fast_auc(yb, p), "logloss": fast_logloss(yb, p),
            "brier": float(np.mean((yb - p) ** 2)),
        }
        expected = predictions[f"{role}_multiclass_expected"]
        metrics["multiclass"][role] = regression_metrics(y, expected, source_rows, protocol["top_k_fraction"], protocol["top_k_positive_label"])
    paired = {
        "binary_delta_auc": metrics["binary"]["author"]["auc"] - metrics["binary"]["base"]["auc"],
        "binary_logloss_improvement": metrics["binary"]["base"]["logloss"] - metrics["binary"]["author"]["logloss"],
        "multiclass_delta_spearman": metrics["multiclass"]["author"]["spearman"] - metrics["multiclass"]["base"]["spearman"],
        "multiclass_mse_improvement": metrics["multiclass"]["base"]["mse"] - metrics["multiclass"]["author"]["mse"],
        "binary_brier_improvement_descriptive": metrics["binary"]["base"]["brier"] - metrics["binary"]["author"]["brier"],
        "multiclass_delta_pearson_descriptive": metrics["multiclass"]["author"]["pearson"] - metrics["multiclass"]["base"]["pearson"],
        "multiclass_delta_top10_e5_enrichment_descriptive": metrics["multiclass"]["author"]["top10_e5_enrichment"] - metrics["multiclass"]["base"]["top10_e5_enrichment"],
    }
    inference = None
    if split != "train" and run_inference:
        inference = resample_primary(y, predictions, clusters, protocol, split_index, resampling_path)
    return {"n": len(rows), "metrics": metrics, "paired_effects": paired, "primary_inference": inference}, predictions


def atomic_predictions(path: str | Path, datasets: dict[str, list[dict]], predictions: dict[str, dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["split_assignment", "source_row", "construct_id", "operational_protein_cluster", "label"] + sorted(next(iter(predictions.values())).keys())
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with open(tmp, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                for split, rows in datasets.items():
                    for i, row in enumerate(rows):
                        out = {k: row[k] for k in fields[:5]}
                        out.update({name: float(values[i]) for name, values in predictions[split].items()})
                        writer.writerow(out)
    os.replace(tmp, path)


def training_diagnostics(models: dict) -> dict:
    return {
        "single_codon_count": len(models["single_models"]),
        "single_codon_max_gradient": max(m["standardized_model"]["optimizer"]["gradient_max_abs"] for m in models["single_models"].values()),
        "single_codon_max_iterations": max(m["standardized_model"]["optimizer"]["iterations"] for m in models["single_models"].values()),
        "single_codon_max_abs_raw_slope": max(abs(v) for v in models["single_slopes"].values()),
        "single_codon_slopes": models["single_slopes"],
        "base_binary_optimizer": models["base_binary"]["optimizer"],
        "author_binary_optimizer": models["author_binary"]["optimizer"],
        "base_multiclass_optimizer": models["base_multiclass"]["optimizer"],
        "author_multiclass_optimizer": models["author_multiclass"]["optimizer"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--evaluation-splits", nargs="+", default=["train", "dev"])
    parser.add_argument("--frozen-test-confirmation", action="store_true")
    parser.add_argument("--dev-result", default=None)
    parser.add_argument("--model-artifact", required=True)
    parser.add_argument("--output-result", required=True)
    parser.add_argument("--output-predictions", required=True)
    parser.add_argument("--resampling-prefix", required=True)
    args = parser.parse_args()
    protocol_path = Path(args.protocol).resolve()
    protocol = json.loads(protocol_path.read_text())
    if args.evaluation_splits[0] != "train" or args.evaluation_splits not in (["train", "dev"], ["train", "dev", "test"]):
        raise ValueError("evaluation splits must be train/dev or train/dev/test")
    test_requested = "test" in args.evaluation_splits
    if test_requested != args.frozen_test_confirmation:
        raise ValueError("test and --frozen-test-confirmation must agree")
    for key, digest_key in INPUT_HASH_KEYS.items():
        if sha256_file(protocol[key]) != protocol[digest_key]:
            raise ValueError(f"input hash mismatch: {key}")
    preflight = json.loads(Path(protocol["feature_preflight"]).read_text())
    if preflight["output_features_sha256"] != protocol["feature_file_sha256"] or preflight["implementation_sha256"] != protocol["feature_builder_sha256"]:
        raise ValueError("feature preflight hash contract mismatch")
    if sha256_file(Path(sys.modules["scripts.a8_rk24_build_features"].__file__).resolve()) != protocol["feature_builder_sha256"]:
        raise ValueError("feature builder implementation hash mismatch")
    datasets = load_data(protocol, args.evaluation_splits)
    model_path = Path(args.model_artifact).resolve()
    if not test_requested:
        models = fit_models(datasets["train"], protocol)
        payload = {"protocol_sha256": sha256_file(protocol_path), "feature_file_sha256": sha256_file(protocol["feature_file"]), "models": models}
        model_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = model_path.with_name(model_path.name + f".tmp.{os.getpid()}")
        with open(tmp, "wb") as handle:
            pickle.dump(payload, handle, protocol=4)
        os.replace(tmp, model_path)
        dev_result = None
    else:
        if not args.dev_result:
            raise ValueError("test requires --dev-result")
        dev_result_path = Path(args.dev_result).resolve()
        dev_result = json.loads(dev_result_path.read_text())
        if dev_result["protocol_sha256"] != sha256_file(protocol_path):
            raise ValueError("dev protocol hash mismatch")
        if dev_result["model_artifact_sha256"] != sha256_file(model_path):
            raise ValueError("model artifact hash mismatch")
        with open(model_path, "rb") as handle:
            payload = pickle.load(handle)
        if payload["protocol_sha256"] != sha256_file(protocol_path):
            raise ValueError("model protocol mismatch")
        models = payload["models"]
    results = {}
    predictions = {}
    for split_index, split in enumerate(args.evaluation_splits):
        frozen_dev_replay = bool(test_requested and split == "dev")
        resampling = None if split == "train" or frozen_dev_replay else Path(f"{args.resampling_prefix}_{split}.npz")
        results[split], predictions[split] = evaluate_split(models, datasets[split], protocol, split, split_index, resampling, run_inference=not frozen_dev_replay)
        if frozen_dev_replay:
            frozen_dev = dev_result["split_results"]["dev"]
            for key in ("n", "metrics", "paired_effects"):
                if results["dev"][key] != frozen_dev[key]:
                    raise RuntimeError(f"frozen dev results do not reproduce exactly: {key}; test aborted")
            results["dev"] = frozen_dev
            for name, values in predictions["dev"].items():
                old = dev_result["dev_prediction_sha256_by_name"][name]
                current = hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()
                if old != current:
                    raise RuntimeError(f"frozen dev prediction mismatch: {name}")
    atomic_predictions(args.output_predictions, datasets, predictions)
    status = "FROZEN_TEST_EVALUATED_PENDING_INDEPENDENT_VERIFICATION" if test_requested else "DEV_ONLY_NO_TEST_ACCESS"
    result = {
        "status": status,
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sha256_file(protocol_path),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "dependency_sha256": {
            "rk07": sha256_file(Path(sys.modules["scripts.a8_rk07_proxy_evaluate"].__file__).resolve()),
            "rk23": sha256_file(Path(sys.modules["scripts.a8_rk23_run_boel_uh"].__file__).resolve()),
            "feature_builder": sha256_file(Path(sys.modules["scripts.a8_rk24_build_features"].__file__).resolve()),
        },
        "command": [sys.executable, "-m", "scripts.a8_rk24_run_boel_author_model", *sys.argv[1:]],
        "evaluation_splits": args.evaluation_splits,
        "test_metrics_computed": test_requested,
        "test_reused_not_globally_untouched": True,
        "functional_untouched_accessed": False,
        "train_fit_only": True,
        "published_coefficients_used_for_prediction": False,
        "model_artifact": str(model_path),
        "model_artifact_sha256": sha256_file(model_path),
        "dev_result": str(Path(args.dev_result).resolve()) if args.dev_result else None,
        "dev_result_sha256": sha256_file(args.dev_result) if args.dev_result else None,
        "training_diagnostics": training_diagnostics(models),
        "split_results": results,
        "dev_prediction_sha256_by_name": {name: hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest() for name, values in predictions.get("dev", {}).items()},
        "prediction_file": str(Path(args.output_predictions).resolve()),
        "prediction_file_sha256": sha256_file(args.output_predictions),
        "environment": {"python": sys.version.split()[0], "numpy": np.__version__, "scipy": importlib.metadata.version("scipy"), "sklearn": importlib.metadata.version("scikit-learn")},
        "scientific_scope": protocol["scientific_scope"],
        "gate": protocol["gate"],
        "rk_g1": False,
        "generator_training_authorized": False,
        "functional_untouched_confirmed": False,
        "prohibited_claims": protocol["prohibited_claims"],
    }
    atomic_json(args.output_result, result)
    compact = {"status": status, "model_artifact_sha256": result["model_artifact_sha256"], "training": {k: v for k, v in result["training_diagnostics"].items() if k != "single_codon_slopes"}, "splits": {}}
    for split, value in results.items():
        compact["splits"][split] = {"paired_effects": value["paired_effects"], "primary_inference": value["primary_inference"]}
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
