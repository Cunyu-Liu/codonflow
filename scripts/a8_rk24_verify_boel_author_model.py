#!/usr/bin/env python3
"""Independent RK24 reconstruction; imports no RK07/RK23/RK24 production module."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import pickle
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, log_softmax
from scipy.stats import pearsonr, spearmanr


GENETIC_CODE = {}
for codons, aa in [
    (("TTT", "TTC"), "F"), (("TTA", "TTG", "CTT", "CTC", "CTA", "CTG"), "L"),
    (("ATT", "ATC", "ATA"), "I"), (("ATG",), "M"),
    (("GTT", "GTC", "GTA", "GTG"), "V"),
    (("TCT", "TCC", "TCA", "TCG", "AGT", "AGC"), "S"),
    (("CCT", "CCC", "CCA", "CCG"), "P"),
    (("ACT", "ACC", "ACA", "ACG"), "T"),
    (("GCT", "GCC", "GCA", "GCG"), "A"),
    (("TAT", "TAC"), "Y"), (("TAA", "TAG", "TGA"), "*"),
    (("CAT", "CAC"), "H"), (("CAA", "CAG"), "Q"),
    (("AAT", "AAC"), "N"), (("AAA", "AAG"), "K"),
    (("GAT", "GAC"), "D"), (("GAA", "GAG"), "E"),
    (("TGT", "TGC"), "C"), (("TGG",), "W"),
    (("CGT", "CGC", "CGA", "CGG", "AGA", "AGG"), "R"),
    (("GGT", "GGC", "GGA", "GGG"), "G"),
]:
    for codon in codons:
        GENETIC_CODE[codon] = aa
SENSE = sorted(c for c, a in GENETIC_CODE.items() if a != "*")
ENDPOINTS = ["binary_delta_auc", "binary_logloss_improvement", "multiclass_delta_spearman", "multiclass_mse_improvement"]


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


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


def spearman_fast(y, p):
    a = average_ranks(y) - np.mean(average_ranks(y))
    b = average_ranks(p) - np.mean(average_ranks(p))
    return float(a @ b / math.sqrt((a @ a) * (b @ b)))


def repeat_definition(protein):
    total = 0.0
    for i, aa in enumerate(protein):
        later = protein.find(aa, i + 1)
        if later >= 0:
            total += 1.0 / (later - i)
    return total / len(protein)


def independent_author_features(seq):
    codons_all = [seq[i:i + 3] for i in range(0, len(seq), 3)]
    assert codons_all[-1] in ("TAA", "TAG", "TGA")
    protein_all = "".join(GENETIC_CODE[c] for c in codons_all[:-1])
    assert "*" not in protein_all and protein_all.endswith("LEHHHHHH")
    codons = codons_all[:-9]
    protein = protein_all[:-8]
    assert len(codons) >= 32 and "".join(GENETIC_CODE[c] for c in codons) == protein
    n = len(codons)
    head = "".join(codons[1:6])
    a_h = head.count("A") / 15
    g_h = head.count("G") / 15
    gc = (head.count("G") + head.count("C")) / 15
    gz = None  # supplied by caller
    f = {
        "core_length_nt": 3 * n, "core_length_aa": len(protein),
        "core_cds_sha256": hashlib.sha256("".join(codons).encode()).hexdigest(),
        "core_protein_sha256": hashlib.sha256(protein.encode()).hexdigest(),
        "GC2_6": gc, "aH": a_h, "aH2": a_h * a_h, "gH": g_h, "gH2": g_h * g_h,
        "u3H": sum(c[2] == "T" for c in codons[1:6]) / 5,
        "dAUA": float(any(codons[i:i + 2] == ["ATA", "ATA"] for i in range(n - 1))),
        "rAA": repeat_definition(protein), "L_knt": 3 * n / 1000, "Linv_knt": 1000 / (3 * n),
    }
    for codon in SENSE:
        f[f"cf_{codon}"] = codons.count(codon) / n
    return f, codons


def independent_load(protocol, splits):
    features = {}
    with gzip.open(protocol["feature_file"], "rt", newline="") as f:
        for row in csv.DictReader(f):
            if row["split_assignment"] in splits:
                features[(row["source_row"], row["construct_id"])] = row
    data = {s: [] for s in splits}
    used = set()
    max_feature_difference = 0.0
    compared_values = 0
    with open(protocol["split_file"], newline="") as f:
        for raw in csv.DictReader(f):
            split = raw["split_assignment"]
            if raw["source_id"] != protocol["source_id"] or split not in splits:
                continue
            assert split != protocol["forbidden_split"]
            key = (raw["source_row"], raw["construct_id"])
            assert key in features
            stored = features[key]
            seq = "".join(raw["cds"].upper().split())
            assert hashlib.sha256(seq.encode()).hexdigest() == stored["cds_sha256"]
            assert raw["operational_protein_cluster"] == stored["operational_protein_cluster"]
            independent, codons = independent_author_features(seq)
            gz = float(json.loads(raw["features_json"])["Gz48v"])
            independent["source_Gz48v"] = gz
            independent["I_62"] = float(gz < -39 and independent["GC2_6"] > 0.62)
            independent["I_65_descriptive"] = float(gz < -39 and independent["GC2_6"] > 0.65)
            for name, value in independent.items():
                if name.endswith("sha256"):
                    assert value == stored[name]
                else:
                    difference = abs(float(value) - float(stored[name]))
                    max_feature_difference = max(max_feature_difference, difference)
                    compared_values += 1
            coding = seq[:-3]
            assert len(coding) == int(stored["length_nt"])
            gc = (coding.count("G") + coding.count("C")) / len(coding)
            assert abs(gc - float(stored["gc_fraction"])) < 1e-14
            assert gz == float(stored["source_Gz48v"])
            row = dict(independent)
            row.update({
                "source_row": int(raw["source_row"]), "construct_id": raw["construct_id"],
                "cluster": raw["operational_protein_cluster"], "label": float(raw[protocol["label_field"]]),
                "length_nt": len(coding), "core_codons": codons,
            })
            for name in ("cai", "gc_fraction", "full_cds_mfe_per_nt", "mfe_5prime_48_kcal_mol"):
                row[name] = float(stored[name])
            data[split].append(row)
            used.add(key)
    assert used == set(features)
    for split, rows in data.items():
        rows.sort(key=lambda r: r["source_row"])
        assert len(rows) == protocol["expected_rows"][split]
    return data, max_feature_difference, compared_values


def matrix(rows, names, slopes):
    columns = []
    for name in names:
        if name == "log_length_nt":
            columns.append(np.log([r["length_nt"] for r in rows]))
        elif name == "s7_16":
            columns.append([np.mean([slopes[c] for c in r["core_codons"][6:16]]) for r in rows])
        elif name == "s17_32":
            columns.append([np.mean([slopes[c] for c in r["core_codons"][16:32]]) for r in rows])
        else:
            columns.append([r[name] for r in rows])
    return np.asarray(columns, dtype=float).T


def binary_fit(x, y, l2, max_iter, tolerance):
    x = np.asarray(x, dtype=float)
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    center = x.mean(0)
    spread = x.std(0)
    assert np.all(spread > 1e-12)
    z = (x - center) / spread
    n, d = z.shape

    def objective(flat):
        w, b = flat[:-1], flat[-1]
        score = z @ w + b
        prob = expit(score)
        loss = np.mean(np.logaddexp(0, score) - y * score) + 0.5 * l2 * (w @ w)
        residual = prob - y
        return loss, np.r_[z.T @ residual / n + l2 * w, residual.sum() / n]

    opt = minimize(objective, np.zeros(d + 1), jac=True, method="L-BFGS-B",
                   options={"maxiter": max_iter, "ftol": 1e-13, "gtol": 1e-9, "maxls": 50})
    assert opt.success and np.max(np.abs(objective(opt.x)[1])) <= tolerance
    return center, spread, opt.x[:-1], opt.x[-1]


def binary_predict(model, x):
    center, spread, w, b = model
    x = np.asarray(x)
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    return expit((x - center) / spread @ w + b)


def multiclass_fit(x, y, classes, l2, max_iter):
    center, spread = x.mean(0), x.std(0)
    assert np.all(spread > 1e-12)
    z = (x - center) / spread
    mapping = {int(c): i for i, c in enumerate(classes)}
    target = np.array([mapping[int(v)] for v in y])
    onehot = np.eye(len(classes))[target]
    n, d = z.shape
    k = len(classes)

    def objective(flat):
        w = flat[:k * d].reshape(k, d)
        b = flat[k * d:]
        logp = log_softmax(z @ w.T + b, axis=1)
        prob = np.exp(logp)
        residual = (prob - onehot) / n
        loss = -np.mean(logp[np.arange(n), target]) + 0.5 * l2 * np.sum(w * w)
        return loss, np.r_[(residual.T @ z + l2 * w).ravel(), residual.sum(0)]

    opt = minimize(objective, np.zeros(k * d + k), jac=True, method="L-BFGS-B",
                   options={"maxiter": max_iter, "ftol": 1e-12, "gtol": 1e-7, "maxls": 50})
    assert opt.success and np.max(np.abs(objective(opt.x)[1])) < 1e-4
    return center, spread, opt.x[:k * d].reshape(k, d), opt.x[k * d:]


def multiclass_predict(model, x, classes):
    center, spread, w, b = model
    return np.exp(log_softmax((x - center) / spread @ w.T + b, axis=1)) @ classes


def independent_fit(train, protocol):
    y = np.array([r["label"] for r in train])
    extreme = (y == 0) | (y == 5)
    train_extreme = [r for r, keep in zip(train, extreme) if keep]
    yb = (y[extreme] == 5).astype(float)
    cfg = protocol["models"]["single_codon_binary"]
    single = {}
    slopes = {}
    for codon in SENSE:
        model = binary_fit(np.array([r[f"cf_{codon}"] for r in train_extreme]), yb, cfg["l2"], cfg["max_iter"], cfg["gradient_max_abs_tolerance"])
        single[codon] = model
        slopes[codon] = model[2][0] / model[1][0]
    base_names = protocol["comparison"]["base_features"]
    full_names = protocol["comparison"]["author_noncodon_features"] + [f"cf_{c}" for c in SENSE if c != "ATG"] + protocol["comparison"]["author_regional_features"]
    assert len(full_names) == 72
    xb = matrix(train_extreme, base_names, slopes)
    xa = matrix(train_extreme, full_names, slopes)
    cfg = protocol["models"]["base_binary"]
    base_binary = binary_fit(xb, yb, cfg["l2"], cfg["max_iter"], cfg["gradient_max_abs_tolerance"])
    cfg = protocol["models"]["author_binary"]
    author_binary = binary_fit(xa, yb, cfg["l2"], cfg["max_iter"], cfg["gradient_max_abs_tolerance"])
    classes = np.array(protocol["label_classes"])
    cfg = protocol["models"]["base_multiclass"]
    base_multi = multiclass_fit(matrix(train, base_names, slopes), y, classes, cfg["l2"], cfg["max_iter"])
    cfg = protocol["models"]["author_multiclass"]
    author_multi = multiclass_fit(matrix(train, full_names, slopes), y, classes, cfg["l2"], cfg["max_iter"])
    return {"slopes": slopes, "single": single, "base_names": base_names, "full_names": full_names,
            "base_binary": base_binary, "author_binary": author_binary,
            "base_multiclass": base_multi, "author_multiclass": author_multi}


def independent_predict(fitted, rows, protocol):
    xb = matrix(rows, fitted["base_names"], fitted["slopes"])
    xa = matrix(rows, fitted["full_names"], fitted["slopes"])
    return {
        "base_binary_p_e5": binary_predict(fitted["base_binary"], xb),
        "author_binary_p_e5": binary_predict(fitted["author_binary"], xa),
        "base_multiclass_expected": multiclass_predict(fitted["base_multiclass"], xb, np.array(protocol["label_classes"])),
        "author_multiclass_expected": multiclass_predict(fitted["author_multiclass"], xa, np.array(protocol["label_classes"])),
    }


def auc(y, p):
    n1, n0 = int(sum(y == 1)), int(sum(y == 0))
    assert n1 and n0
    return float((average_ranks(p)[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def logloss(y, p):
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log1p(-p)))


def regression_metrics(y, p, source_rows, fraction, positive):
    top_n = max(1, int(math.ceil(fraction * len(y))))
    top = np.lexsort((source_rows, -p))[:top_n]
    mse = float(np.mean((y - p) ** 2))
    return {"spearman": float(spearmanr(y, p).statistic), "pearson": float(pearsonr(y, p).statistic),
            "mse": mse, "rmse": math.sqrt(mse), "mae": float(np.mean(np.abs(y - p))),
            "top10_e5_enrichment": float(np.mean(y[top] == positive) / np.mean(y == positive)), "n": len(y)}


def binary_effects(y, b, a):
    return auc(y, a) - auc(y, b), logloss(y, b) - logloss(y, a)


def multiclass_effects(y, b, a):
    return spearman_fast(y, a) - spearman_fast(y, b), float(np.mean((y - b) ** 2) - np.mean((y - a) ** 2))


def independent_resampling(y, predictions, clusters, protocol, split_index, output):
    count = protocol["bootstrap"]["replicates"]
    boot, perm = np.zeros((count, 4)), np.zeros((count, 4))
    brng = np.random.default_rng(protocol["bootstrap"]["seed"] + split_index)
    prng = np.random.default_rng(protocol["permutation"]["seed"] + split_index)
    mg = sorted(set(clusters))
    mi = [np.flatnonzero(clusters == g) for g in mg]
    mask = (y == 0) | (y == 5)
    yb = (y[mask] == 5).astype(float)
    cb = clusters[mask]
    bg = sorted(set(cb))
    bi = [np.flatnonzero(cb == g) for g in bg]
    bb, ab = predictions["base_binary_p_e5"][mask], predictions["author_binary_p_e5"][mask]
    bm, am = predictions["base_multiclass_expected"], predictions["author_multiclass_expected"]
    for rep in range(count):
        selected = brng.integers(0, len(bi), len(bi))
        idx = np.concatenate([bi[i] for i in selected])
        boot[rep, :2] = binary_effects(yb[idx], bb[idx], ab[idx])
        selected = brng.integers(0, len(mi), len(mi))
        idx = np.concatenate([mi[i] for i in selected])
        boot[rep, 2:] = multiclass_effects(y[idx], bm[idx], am[idx])
        pb, pa = bb.copy(), ab.copy()
        for flag, loc in zip(prng.random(len(bi)) < 0.5, bi):
            if flag:
                pb[loc], pa[loc] = ab[loc], bb[loc]
        perm[rep, :2] = binary_effects(yb, pb, pa)
        pb, pa = bm.copy(), am.copy()
        for flag, loc in zip(prng.random(len(mi)) < 0.5, mi):
            if flag:
                pb[loc], pa[loc] = am[loc], bm[loc]
        perm[rep, 2:] = multiclass_effects(y, pb, pa)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, bootstrap_effects=boot, permutation_effects=perm, endpoints=np.array(ENDPOINTS))
    points = np.r_[binary_effects(yb, bb, ab), float(spearmanr(y, am).statistic - spearmanr(y, bm).statistic), np.mean((y - bm) ** 2) - np.mean((y - am) ** 2)]
    report, pvals = {}, {}
    for j, name in enumerate(ENDPOINTS):
        effect = float(points[j])
        ci = np.percentile(boot[:, j], [2.5, 97.5])
        p = float((1 + np.sum(np.abs(perm[:, j]) >= abs(effect))) / (count + 1))
        pvals[name] = p
        report[name] = {"effect": effect, "ci95": ci.tolist(), "p_raw": p}
    previous = 0.0
    adjusted = {}
    for i, key in enumerate(sorted(pvals, key=pvals.get)):
        previous = max(previous, min(1.0, (len(pvals) - i) * pvals[key]))
        adjusted[key] = previous
    for key in ENDPOINTS:
        report[key]["p_holm"] = adjusted[key]
    return report, boot, perm


def close(report, name, observed, expected, tolerance=1e-9):
    difference = abs(float(observed) - float(expected))
    report["checks"].append({"name": name, "pass": difference <= tolerance, "observed": float(observed), "expected": float(expected), "abs_difference": difference, "tolerance": tolerance})


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
    check("published_coefficients_not_used", result["published_coefficients_used_for_prediction"] is False)
    splits = result["evaluation_splits"]
    data, max_feature_diff, feature_values = independent_load(protocol, splits)
    check("independent_static_features_reproduce", max_feature_diff < 1e-12, {"max_difference": max_feature_diff, "values": feature_values})
    check("row_counts", {s: len(v) for s, v in data.items()} == {s: protocol["expected_rows"][s] for s in splits})
    fitted = independent_fit(data["train"], protocol)
    with open(args.model_artifact, "rb") as f:
        frozen = pickle.load(f)["models"]
    max_single_diff = max(abs(fitted["slopes"][c] - frozen["single_slopes"][c]) for c in SENSE)
    check("single_codon_slopes_reproduce", max_single_diff < 1e-6, max_single_diff)
    max_binary_diff = 0.0
    for name in ("base_binary", "author_binary"):
        independent = fitted[name]
        original = frozen[name]
        max_binary_diff = max(max_binary_diff, float(np.max(np.abs(independent[2] - np.array(original["weights"])))), abs(independent[3] - original["bias"]))
    check("binary_models_reproduce", max_binary_diff < 1e-6, max_binary_diff)
    max_multi_diff = 0.0
    for name in ("base_multiclass", "author_multiclass"):
        independent = fitted[name]
        original = frozen[name]
        max_multi_diff = max(max_multi_diff, float(np.max(np.abs(independent[2] - np.array(original["weights"])))), float(np.max(np.abs(independent[3] - np.array(original["bias"])))))
    check("multiclass_models_reproduce", max_multi_diff < 1e-6, max_multi_diff)
    csv_predictions = {s: {} for s in splits}
    with gzip.open(args.predictions, "rt", newline="") as f:
        reader = csv.DictReader(f)
        names = [n for n in reader.fieldnames if n not in ("split_assignment", "source_row", "construct_id", "operational_protein_cluster", "label")]
        for row in reader:
            split = row["split_assignment"]
            csv_predictions[split].setdefault("rows", []).append((int(row["source_row"]), row["construct_id"], float(row["label"])))
            for name in names:
                csv_predictions[split].setdefault(name, []).append(float(row[name]))
    max_prediction_diff = max_metric_diff = max_boot_diff = max_perm_diff = 0.0
    scientific = {}
    for split_index, split in enumerate(splits):
        rows = data[split]
        check(f"{split}_prediction_identity_order", csv_predictions[split]["rows"] == [(r["source_row"], r["construct_id"], r["label"]) for r in rows])
        y = np.array([r["label"] for r in rows])
        source_rows = np.array([r["source_row"] for r in rows])
        clusters = np.array([r["cluster"] for r in rows])
        predictions = independent_predict(fitted, rows, protocol)
        mask = (y == 0) | (y == 5)
        yb = (y[mask] == 5).astype(float)
        expected_metrics = result["split_results"][split]["metrics"]
        actual_metrics = {"binary": {"n": int(mask.sum()), "n_e0": int(sum(y == 0)), "n_e5": int(sum(y == 5))}, "multiclass": {}}
        for role in ("base", "author"):
            p = predictions[f"{role}_binary_p_e5"][mask]
            actual_metrics["binary"][role] = {"auc": auc(yb, p), "logloss": logloss(yb, p), "brier": float(np.mean((yb - p) ** 2))}
            expected = predictions[f"{role}_multiclass_expected"]
            actual_metrics["multiclass"][role] = regression_metrics(y, expected, source_rows, protocol["top_k_fraction"], protocol["top_k_positive_label"])
        for track in ("binary", "multiclass"):
            for role, values in actual_metrics[track].items():
                if role in ("base", "author"):
                    for metric, value in values.items():
                        max_metric_diff = max(max_metric_diff, abs(float(value) - float(expected_metrics[track][role][metric])))
                        close(report, f"{split}_{track}_{role}_{metric}", value, expected_metrics[track][role][metric])
                else:
                    close(report, f"{split}_{track}_{role}", values, expected_metrics[track][role])
        for name, values in predictions.items():
            recorded = np.array(csv_predictions[split][name])
            max_prediction_diff = max(max_prediction_diff, float(np.max(np.abs(values - recorded))))
        actual_pairs = {
            "binary_delta_auc": actual_metrics["binary"]["author"]["auc"] - actual_metrics["binary"]["base"]["auc"],
            "binary_logloss_improvement": actual_metrics["binary"]["base"]["logloss"] - actual_metrics["binary"]["author"]["logloss"],
            "multiclass_delta_spearman": actual_metrics["multiclass"]["author"]["spearman"] - actual_metrics["multiclass"]["base"]["spearman"],
            "multiclass_mse_improvement": actual_metrics["multiclass"]["base"]["mse"] - actual_metrics["multiclass"]["author"]["mse"],
            "binary_brier_improvement_descriptive": actual_metrics["binary"]["base"]["brier"] - actual_metrics["binary"]["author"]["brier"],
            "multiclass_delta_pearson_descriptive": actual_metrics["multiclass"]["author"]["pearson"] - actual_metrics["multiclass"]["base"]["pearson"],
            "multiclass_delta_top10_e5_enrichment_descriptive": actual_metrics["multiclass"]["author"]["top10_e5_enrichment"] - actual_metrics["multiclass"]["base"]["top10_e5_enrichment"],
        }
        for name, value in actual_pairs.items():
            close(report, f"{split}_{name}", value, result["split_results"][split]["paired_effects"][name])
        if split != "train":
            independent, boot, perm = independent_resampling(y, predictions, clusters, protocol, split_index, f"{args.independent_resampling_prefix}_{split}.npz")
            original = np.load(result["split_results"][split]["primary_inference"]["resampling_file"])
            max_boot_diff = max(max_boot_diff, float(np.max(np.abs(boot - original["bootstrap_effects"]))))
            max_perm_diff = max(max_perm_diff, float(np.max(np.abs(perm - original["permutation_effects"]))))
            for key, values in independent.items():
                expected = result["split_results"][split]["primary_inference"]["comparisons"][key]
                for metric in ("effect", "p_raw", "p_holm"):
                    close(report, f"{split}_{key}_{metric}", values[metric], expected[metric], 1e-10)
                for i in (0, 1):
                    close(report, f"{split}_{key}_ci_{i}", values["ci95"][i], expected["ci95"][i])
            scientific[split] = independent
    check("all_prediction_values_reproduce", max_prediction_diff < 1e-8, max_prediction_diff)
    check("all_metric_values_reproduce", max_metric_diff < 1e-8, max_metric_diff)
    check("all_bootstrap_arrays_reproduce", max_boot_diff < 1e-8, max_boot_diff)
    check("all_permutation_arrays_reproduce", max_perm_diff < 1e-8, max_perm_diff)
    report.update({"max_static_feature_difference": max_feature_diff, "static_feature_values_compared": feature_values,
                   "max_single_codon_slope_difference": max_single_diff, "max_binary_weight_difference": max_binary_diff,
                   "max_multiclass_weight_difference": max_multi_diff, "max_prediction_difference": max_prediction_diff,
                   "max_metric_difference": max_metric_diff, "max_bootstrap_difference": max_boot_diff, "max_permutation_difference": max_perm_diff})
    if "test" in scientific:
        gate = {key: bool(v["effect"] > 0 and v["ci95"][0] > 0 and v["p_holm"] < 0.05) for key, v in scientific["test"].items()}
        report["scientific_gate"] = {"endpoints": gate, "all_four_pass": all(gate.values()),
            "state": "BOEL_AUTHOR_STRUCTURE_SUPERIORITY_SUPPORTED_LIMITED_SCOPE" if all(gate.values()) else "BOEL_AUTHOR_STRUCTURE_SUPERIORITY_NOT_FULLY_SUPPORTED",
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
    summary = {k: report[k] for k in ("status", "checks_total", "checks_passed", "checks_failed", "max_static_feature_difference", "max_prediction_difference", "max_bootstrap_difference", "max_permutation_difference")}
    if "scientific_gate" in report:
        summary["scientific_gate"] = report["scientific_gate"]
    print(json.dumps(summary, indent=2))
    if report["checks_failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
