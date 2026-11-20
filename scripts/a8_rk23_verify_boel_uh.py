#!/usr/bin/env python3
"""Independent RK23 reconstruction; imports neither RK23 nor RK07 production modules."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import pickle
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import log_softmax
from scipy.stats import pearsonr, spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def independent_gc3(seq):
    codons = [seq[i:i + 3] for i in range(0, len(seq), 3)]
    if codons[-1] not in ("TAA", "TAG", "TGA"):
        raise AssertionError("stop missing")
    third = "".join(c[-1] for c in codons[:-1])
    return (third.count("G") + third.count("C")) / len(third)


def independent_load(protocol, splits):
    features = {}
    with gzip.open(protocol["feature_file"], "rt", newline="") as f:
        for row in csv.DictReader(f):
            if row["split_assignment"] in splits:
                features[(row["source_row"], row["construct_id"])] = row
    data = {s: [] for s in splits}
    used = set()
    with open(protocol["split_file"], newline="") as f:
        for raw in csv.DictReader(f):
            if raw["source_id"] != protocol["source_id"] or raw["split_assignment"] not in splits:
                continue
            assert raw["split_assignment"] != protocol["forbidden_split"]
            key = (raw["source_row"], raw["construct_id"])
            assert key in features
            feat = features[key]
            seq = "".join(raw["cds"].upper().split())
            assert hashlib.sha256(seq.encode()).hexdigest() == feat["cds_sha256"]
            assert raw["operational_protein_cluster"] == feat["operational_protein_cluster"]
            assert len(seq) == int(feat["length_nt"])
            gc = (seq.count("G") + seq.count("C")) / len(seq)
            assert abs(gc - float(feat["gc_fraction"])) < 1e-14
            gz = float(json.loads(raw["features_json"])["Gz48v"])
            assert gz == float(feat["source_Gz48v"])
            row = {
                "source_row": int(raw["source_row"]), "construct_id": raw["construct_id"],
                "cluster": raw["operational_protein_cluster"], "label": float(raw[protocol["label_field"]]),
                "length_nt": len(seq), "gc3_fraction": independent_gc3(seq),
                "source_Gz48v": gz,
            }
            for name in ("cai", "gc_fraction", "full_cds_mfe_per_nt", "mfe_5prime_48_kcal_mol"):
                row[name] = float(feat[name])
            data[raw["split_assignment"]].append(row)
            used.add(key)
    assert used == set(features)
    for split, rows in data.items():
        rows.sort(key=lambda r: r["source_row"])
        assert len(rows) == protocol["expected_rows"][split]
    return data


def matrix(rows, names):
    return np.column_stack([
        np.log([r["length_nt"] for r in rows]) if n == "log_length_nt" else [r[n] for r in rows]
        for n in names
    ]).astype(float)


def independent_logistic_fit(x, y, classes, l2, max_iter):
    center = x.mean(0)
    spread = x.std(0)
    z = (x - center) / spread
    class_map = {int(c): i for i, c in enumerate(classes)}
    target = np.array([class_map[int(v)] for v in y])
    onehot = np.eye(len(classes))[target]
    n, d = z.shape
    k = len(classes)

    def fun(flat):
        w = flat[:k * d].reshape(k, d)
        b = flat[k * d:]
        logits = z @ w.T + b
        probs = np.exp(log_softmax(logits, axis=1))
        loss = -np.mean(log_softmax(logits, axis=1)[np.arange(n), target]) + 0.5 * l2 * np.sum(w ** 2)
        residual = (probs - onehot) / n
        grad = np.concatenate([(residual.T @ z + l2 * w).ravel(), residual.sum(0)])
        return loss, grad

    opt = minimize(fun, np.zeros(k * d + k), jac=True, method="L-BFGS-B",
                   options={"maxiter": max_iter, "ftol": 1e-12, "gtol": 1e-7, "maxls": 50})
    assert opt.success and np.max(np.abs(fun(opt.x)[1])) < 1e-4
    return {"mean": center, "scale": spread, "weights": opt.x[:k * d].reshape(k, d), "bias": opt.x[k * d:]}


def independent_logistic_predict(model, x, classes):
    z = (x - model["mean"]) / model["scale"]
    return np.exp(log_softmax(z @ model["weights"].T + model["bias"], axis=1)) @ classes


def independent_fit(train, protocol):
    y = np.array([r["label"] for r in train])
    classes = np.array(protocol["label_classes"])
    fitted = {}
    for contrast in ("primary_contrast", "secondary_descriptive_contrast"):
        fitted[contrast] = {}
        for role in ("base", "augmented"):
            names = protocol[contrast][role + "_features"]
            x = matrix(train, names)
            logistic = independent_logistic_fit(x, y, classes, protocol["models"]["logistic"]["l2"], protocol["models"]["logistic"]["max_iter"])
            cfg = protocol["models"]["histgb"]
            hist = HistGradientBoostingRegressor(
                learning_rate=cfg["learning_rate"], max_iter=cfg["max_iter"], max_leaf_nodes=cfg["max_leaf_nodes"],
                min_samples_leaf=cfg["min_samples_leaf"], l2_regularization=cfg["l2_regularization"],
                early_stopping=cfg["early_stopping"], random_state=cfg["random_state"])
            hist.fit(x, y)
            fitted[contrast][role] = (names, logistic, hist)
    return fitted


def independent_predict(fitted, rows, protocol):
    out = {}
    classes = np.array(protocol["label_classes"])
    for contrast in ("primary_contrast", "secondary_descriptive_contrast"):
        for role in ("base", "augmented"):
            names, logistic, hist = fitted[contrast][role]
            x = matrix(rows, names)
            out[f"{contrast}_{role}_logistic"] = independent_logistic_predict(logistic, x, classes)
            out[f"{contrast}_{role}_histgb"] = hist.predict(x)
    return out


def average_ranks(values):
    values = np.asarray(values)
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    ranks = np.empty(len(values), dtype=float)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and sorted_values[end] == sorted_values[start]:
            end += 1
        ranks[order[start:end]] = (start + end + 1) / 2
        start = end
    return ranks


def independent_spearman(y, p):
    a = average_ranks(y)
    b = average_ranks(p)
    a = a - a.mean()
    b = b - b.mean()
    return float(a @ b / math.sqrt((a @ a) * (b @ b)))


def metrics(y, p, source_rows, fraction, positive):
    mse = float(np.mean((y - p) ** 2))
    n_top = max(1, int(math.ceil(fraction * len(y))))
    top = np.lexsort((source_rows, -p))[:n_top]
    is_positive = y == positive
    return {
        "spearman": float(spearmanr(y, p).statistic), "pearson": float(pearsonr(y, p).statistic),
        "mse": mse, "rmse": math.sqrt(mse), "mae": float(np.mean(np.abs(y - p))),
        "top10_e5_enrichment": float(np.mean(is_positive[top]) / np.mean(is_positive)), "n": len(y),
    }


def independent_holm(pvals):
    result = {}
    previous = 0.0
    ordered = sorted(pvals, key=pvals.get)
    for i, key in enumerate(ordered):
        previous = max(previous, min(1.0, (len(ordered) - i) * pvals[key]))
        result[key] = previous
    return result


def independent_resampling(y, predictions, clusters, protocol, split_index, output):
    contrast = "primary_contrast"
    groups = sorted(set(clusters))
    indices = [np.flatnonzero(clusters == g) for g in groups]
    count = protocol["bootstrap"]["replicates"]
    boot = np.zeros((count, 2, 2))
    perm = np.zeros((count, 2, 2))
    brng = np.random.default_rng(protocol["bootstrap"]["seed"] + split_index)
    prng = np.random.default_rng(protocol["permutation"]["seed"] + split_index)
    for rep in range(count):
        selected = brng.integers(0, len(groups), len(groups))
        idx = np.concatenate([indices[i] for i in selected])
        swap = prng.random(len(groups)) < 0.5
        for mi, model in enumerate(("logistic", "histgb")):
            base = predictions[f"{contrast}_base_{model}"]
            aug = predictions[f"{contrast}_augmented_{model}"]
            boot[rep, mi, 0] = independent_spearman(y[idx], aug[idx]) - independent_spearman(y[idx], base[idx])
            boot[rep, mi, 1] = np.mean((y[idx] - base[idx]) ** 2) - np.mean((y[idx] - aug[idx]) ** 2)
            b = base.copy()
            a = aug.copy()
            for flag, loc in zip(swap, indices):
                if flag:
                    b[loc] = aug[loc]
                    a[loc] = base[loc]
            perm[rep, mi, 0] = independent_spearman(y, a) - independent_spearman(y, b)
            perm[rep, mi, 1] = np.mean((y - b) ** 2) - np.mean((y - a) ** 2)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, bootstrap_effects=boot, permutation_effects=perm)
    report = {}
    raw_p = {}
    for mi, model in enumerate(("logistic", "histgb")):
        base = predictions[f"{contrast}_base_{model}"]
        aug = predictions[f"{contrast}_augmented_{model}"]
        points = [float(spearmanr(y, aug).statistic - spearmanr(y, base).statistic), float(np.mean((y - base) ** 2) - np.mean((y - aug) ** 2))]
        for qi, metric in enumerate(("delta_spearman", "mse_improvement")):
            key = model + "_" + metric
            effect = points[qi]
            ci = np.percentile(boot[:, mi, qi], [2.5, 97.5])
            raw_p[key] = float((1 + np.sum(np.abs(perm[:, mi, qi]) >= abs(effect))) / (count + 1))
            report[key] = {"effect": effect, "ci95": ci.tolist(), "p_raw": raw_p[key]}
    adjusted = independent_holm(raw_p)
    for key in report:
        report[key]["p_holm"] = adjusted[key]
    return report, boot, perm


def close(report, name, observed, expected, tolerance=1e-10):
    difference = abs(float(observed) - float(expected))
    report["checks"].append({"name": name, "pass": bool(difference <= tolerance), "observed": float(observed), "expected": float(expected), "abs_difference": difference, "tolerance": tolerance})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--model-artifact", required=True)
    parser.add_argument("--independent-resampling-prefix", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    protocol_path = Path(args.protocol).resolve()
    protocol = json.loads(protocol_path.read_text())
    result_path = Path(args.result).resolve()
    result = json.loads(result_path.read_text())
    report = {"status": "RUNNING", "protocol_sha256": sha(protocol_path), "result_sha256": sha(result_path), "checks": []}
    def check(name, condition, detail=None):
        report["checks"].append({"name": name, "pass": bool(condition), "detail": detail})
    check("result_protocol_hash", result["protocol_sha256"] == sha(protocol_path))
    check("model_artifact_hash", result["model_artifact_sha256"] == sha(args.model_artifact))
    check("prediction_file_hash", result["prediction_file_sha256"] == sha(args.predictions))
    check("functional_untouched_closed", result["functional_untouched_accessed"] is False and result["functional_untouched_confirmed"] is False)
    check("rk_g1_remains_closed", result["rk_g1"] is False and result["generator_training_authorized"] is False)
    splits = result["evaluation_splits"]
    data = independent_load(protocol, splits)
    check("row_counts", {s: len(v) for s, v in data.items()} == {s: protocol["expected_rows"][s] for s in splits})
    fitted = independent_fit(data["train"], protocol)
    with open(args.model_artifact, "rb") as f:
        frozen = pickle.load(f)["models"]
    max_logistic_weight_diff = 0.0
    for contrast in fitted:
        for role in ("base", "augmented"):
            independent = fitted[contrast][role][1]
            original = frozen[contrast][role]["logistic"]
            max_logistic_weight_diff = max(max_logistic_weight_diff, float(np.max(np.abs(independent["weights"] - np.array(original["weights"])))), float(np.max(np.abs(independent["bias"] - np.array(original["bias"])))))
    check("independent_logistic_refit", max_logistic_weight_diff < 1e-7, max_logistic_weight_diff)
    report["max_logistic_weight_difference"] = max_logistic_weight_diff
    csv_predictions = {s: {} for s in splits}
    with gzip.open(args.predictions, "rt", newline="") as f:
        reader = csv.DictReader(f)
        names = [n for n in reader.fieldnames if n not in ("split_assignment", "source_row", "construct_id", "operational_protein_cluster", "label")]
        for row in reader:
            split = row["split_assignment"]
            csv_predictions[split].setdefault("rows", []).append((int(row["source_row"]), row["construct_id"], float(row["label"])))
            for name in names:
                csv_predictions[split].setdefault(name, []).append(float(row[name]))
    scientific = {}
    max_prediction_diff = 0.0
    max_metric_diff = 0.0
    max_bootstrap_diff = 0.0
    max_permutation_diff = 0.0
    for split_index, split in enumerate(splits):
        rows = data[split]
        recorded_identities = csv_predictions[split]["rows"]
        expected_identities = [(r["source_row"], r["construct_id"], r["label"]) for r in rows]
        check(f"{split}_prediction_identity_order", recorded_identities == expected_identities)
        y = np.array([r["label"] for r in rows])
        source_rows = np.array([r["source_row"] for r in rows])
        clusters = np.array([r["cluster"] for r in rows])
        predictions = independent_predict(fitted, rows, protocol)
        for name, values in predictions.items():
            recorded = np.array(csv_predictions[split][name])
            max_prediction_diff = max(max_prediction_diff, float(np.max(np.abs(values - recorded))))
            expected_metrics = result["split_results"][split]["metrics"][name]
            actual_metrics = metrics(y, values, source_rows, protocol["top_k_fraction"], protocol["top_k_positive_label"])
            for metric, value in actual_metrics.items():
                max_metric_diff = max(max_metric_diff, abs(float(value) - float(expected_metrics[metric])))
                close(report, f"{split}_{name}_{metric}", value, expected_metrics[metric], 1e-9)
        expected_pairs = result["split_results"][split]["paired_effects"]
        for contrast in ("primary_contrast", "secondary_descriptive_contrast"):
            for model in ("logistic", "histgb"):
                base = predictions[f"{contrast}_base_{model}"]
                aug = predictions[f"{contrast}_augmented_{model}"]
                actual = {
                    "delta_spearman": float(spearmanr(y, aug).statistic - spearmanr(y, base).statistic),
                    "mse_improvement": float(np.mean((y - base) ** 2) - np.mean((y - aug) ** 2)),
                    "delta_pearson": float(pearsonr(y, aug).statistic - pearsonr(y, base).statistic),
                }
                bm = metrics(y, base, source_rows, protocol["top_k_fraction"], protocol["top_k_positive_label"])
                am = metrics(y, aug, source_rows, protocol["top_k_fraction"], protocol["top_k_positive_label"])
                actual["delta_top10_e5_enrichment"] = am["top10_e5_enrichment"] - bm["top10_e5_enrichment"]
                for metric, value in actual.items():
                    close(report, f"{split}_{contrast}_{model}_{metric}", value, expected_pairs[f"{contrast}_{model}"][metric], 1e-9)
        if split != "train":
            independent, boot, perm = independent_resampling(y, predictions, clusters, protocol, split_index, f"{args.independent_resampling_prefix}_{split}.npz")
            original_arrays = np.load(result["split_results"][split]["primary_inference"]["resampling_file"])
            max_bootstrap_diff = max(max_bootstrap_diff, float(np.max(np.abs(boot - original_arrays["bootstrap_effects"]))))
            max_permutation_diff = max(max_permutation_diff, float(np.max(np.abs(perm - original_arrays["permutation_effects"]))))
            for key, values in independent.items():
                expected = result["split_results"][split]["primary_inference"]["comparisons"][key]
                for metric in ("effect", "p_raw", "p_holm"):
                    close(report, f"{split}_{key}_{metric}", values[metric], expected[metric], 1e-10)
                for i in (0, 1):
                    close(report, f"{split}_{key}_ci_{i}", values["ci95"][i], expected["ci95"][i], 1e-9)
            scientific[split] = independent
    check("all_prediction_values_reproduce", max_prediction_diff < 1e-8, max_prediction_diff)
    check("all_metric_values_reproduce", max_metric_diff < 1e-8, max_metric_diff)
    check("all_bootstrap_arrays_reproduce", max_bootstrap_diff < 1e-8, max_bootstrap_diff)
    check("all_permutation_arrays_reproduce", max_permutation_diff < 1e-8, max_permutation_diff)
    report.update({"max_prediction_difference": max_prediction_diff, "max_metric_difference": max_metric_diff,
                   "max_bootstrap_difference": max_bootstrap_diff, "max_permutation_difference": max_permutation_diff})
    if "test" in scientific:
        gate = {}
        for key, values in scientific["test"].items():
            gate[key] = bool(values["effect"] > 0 and values["ci95"][0] > 0 and values["p_holm"] < 0.05)
        report["scientific_gate"] = {"endpoints": gate, "all_four_pass": all(gate.values()),
            "state": "PROTEIN_OOD_INITIATION_STRUCTURE_INCREMENT_SUPPORTED_LIMITED_SCOPE" if all(gate.values()) else "PROTEIN_OOD_INITIATION_STRUCTURE_INCREMENT_NOT_FULLY_SUPPORTED",
            "rk_g1": False, "fixed_protein_synonymous_ood": False, "functional_untouched": False}
        check("production_gate_matches_independent_gate", result["split_results"]["test"]["primary_inference"]["all_four_pass"] == all(gate.values()))
        for key, passed in gate.items():
            expected = result["split_results"]["test"]["primary_inference"]["comparisons"][key]
            check(f"production_endpoint_gate_{key}", expected["passes_all"] == passed and expected["passes_direction"] == bool(expected["effect"] > 0 and expected["ci95"][0] > 0))
    report["checks_total"] = len(report["checks"])
    report["checks_passed"] = sum(c["pass"] for c in report["checks"])
    report["checks_failed"] = [c for c in report["checks"] if not c["pass"]]
    report["status"] = "PASS_INDEPENDENT_VERIFICATION" if not report["checks_failed"] else "FAIL_INDEPENDENT_VERIFICATION"
    atomic_json(args.output, report)
    print(json.dumps({k: report[k] for k in ("status", "checks_total", "checks_passed", "checks_failed", "max_prediction_difference", "max_bootstrap_difference", "max_permutation_difference")} | ({"scientific_gate": report["scientific_gate"]} if "scientific_gate" in report else {}), indent=2))
    if report["checks_failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
