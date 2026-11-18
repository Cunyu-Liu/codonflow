#!/usr/bin/env python3
"""Independent raw-source verification for RK07; no production-module imports."""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np
import ViennaRNA
from scipy.special import softmax
from scipy.stats import pearsonr, spearmanr

BASES = "TCAG"
CODONS = [a + b + c for a in BASES for b in BASES for c in BASES]
AAS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
TABLE = dict(zip(CODONS, AAS))
SENSE = [c for c in CODONS if TABLE[c] != "*"]
MODELS = ["cai", "gc_fraction", "full_cds_mfe_kcal_mol", "full_cds_mfe_per_nt", "mfe_5prime_48_kcal_mol", "combined_logistic"]
BOOT_METRICS = ["spearman", "pearson", "rmse", "top10_e5_enrichment"]
_WEIGHTS = None
_TEMPERATURE = None
_WINDOW = None


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def translate(cds):
    return "".join(TABLE.get(cds[i:i + 3], "X") for i in range(0, len(cds), 3))


def canonical(cds):
    cds = "".join(cds.upper().split())
    if len(cds) < 6 or len(cds) % 3 or set(cds) - set("ACGT") or TABLE.get(cds[-3:]) != "*":
        raise ValueError("invalid CDS")
    coding = cds[:-3]
    protein = translate(coding)
    if "*" in protein or "X" in protein:
        raise ValueError("invalid translation")
    return cds, coding, protein


def fasta(path):
    header, chunks = None, []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith(">"):
                if header is not None:
                    yield header, "".join(chunks)
                header, chunks = line[1:], []
            elif line:
                chunks.append(line)
    if header is not None:
        yield header, "".join(chunks)


def independent_weights(path):
    counts = {c: 0 for c in SENSE}
    used = 0
    for header, seq in fasta(path):
        if "[pseudo=true]" in header:
            continue
        try:
            _, coding, _ = canonical(seq)
        except ValueError:
            continue
        used += 1
        for i in range(0, len(coding), 3):
            counts[coding[i:i + 3]] += 1
    weights = {}
    for aa in set(TABLE[c] for c in SENSE):
        codons = [c for c in SENSE if TABLE[c] == aa]
        maximum = max(counts[c] for c in codons)
        if maximum <= 0:
            raise ValueError("missing reference codon")
        for codon in codons:
            weights[codon] = counts[codon] / maximum
    return weights, used


def read_features(path):
    rows = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["source_row"], row["construct_id"])
            if key in rows:
                raise ValueError("duplicate feature identity")
            for field in ("gc_fraction", "cai", "full_cds_mfe_kcal_mol", "full_cds_mfe_per_nt", "mfe_5prime_48_kcal_mol"):
                row[field] = float(row[field])
            row["length_nt"] = int(row["length_nt"])
            rows[key] = row
    return rows


def _init(weights, temperature, window):
    global _WEIGHTS, _TEMPERATURE, _WINDOW
    _WEIGHTS, _TEMPERATURE, _WINDOW = weights, temperature, window


def raw_recompute(row):
    cds, coding, protein = canonical(row["cds"])
    if protein != row["protein_sequence"].rstrip("*"):
        raise ValueError("reference protein mismatch")
    weights = _WEIGHTS
    cai = math.exp(sum(math.log(weights[coding[i:i + 3]]) for i in range(0, len(coding), 3)) / (len(coding) // 3))
    gc = sum(base in "GC" for base in coding) / len(coding)
    md = ViennaRNA.md(); md.temperature = _TEMPERATURE
    full = float(ViennaRNA.fold_compound(cds.replace("T", "U"), md).mfe()[1])
    local = float(ViennaRNA.fold_compound(cds.replace("T", "U")[:_WINDOW], md).mfe()[1])
    return (row["source_row"], row["construct_id"]), {
        "length_nt": len(coding), "gc_fraction": gc, "cai": cai,
        "full_cds_mfe_kcal_mol": full, "full_cds_mfe_per_nt": full / len(cds),
        "mfe_5prime_48_kcal_mol": local,
        "cds_sha256": hashlib.sha256(cds.encode()).hexdigest(),
        "split_assignment": row["split_assignment"],
        "operational_protein_cluster": row["operational_protein_cluster"],
    }


def matrix(rows, names):
    cols = []
    for name in names:
        if name == "log_length_nt":
            cols.append(np.log(np.array([r["length_nt"] for r in rows], dtype=float)))
        else:
            cols.append(np.array([r[name] for r in rows], dtype=float))
    return np.column_stack(cols)


def metrics(y, pred, source_rows, fraction, positive):
    k = max(1, int(math.ceil(fraction * len(y))))
    selected = np.lexsort((source_rows.astype(int), -pred))[:k]
    base = float(np.mean(y == positive)); top = float(np.mean(y[selected] == positive))
    return {
        "n": len(y), "spearman": float(spearmanr(y, pred).statistic),
        "pearson": float(pearsonr(y, pred).statistic),
        "rmse": float(np.sqrt(np.mean((y - pred) ** 2))),
        "mae": float(np.mean(np.abs(y - pred))),
        "top10_e5_enrichment": top / base, "top10_e5_rate": top,
        "baseline_e5_rate": base, "top10_n": k,
    }


def close(actual, expected, tolerance, label, differences):
    difference = abs(float(actual) - float(expected))
    differences[label] = max(differences.get(label, 0.0), difference) if math.isfinite(difference) else difference
    if not math.isfinite(difference) or difference > tolerance:
        raise AssertionError(f"{label}: actual={actual} expected={expected} diff={difference}")


def holm(p):
    order = sorted(p, key=p.get); out = {}; running = 0.0
    for rank, key in enumerate(order):
        running = max(running, min(1.0, (len(order) - rank) * p[key])); out[key] = running
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True); parser.add_argument("--features", required=True)
    parser.add_argument("--feature-summary", required=True); parser.add_argument("--dev-results", required=True)
    parser.add_argument("--final-results", required=True); parser.add_argument("--predictions", required=True)
    parser.add_argument("--workers", type=int, default=8); parser.add_argument("--output", required=True)
    args = parser.parse_args()
    checks = []; differences = {}
    report = {"status": "FAIL", "checks": checks, "max_differences": differences, "production_modules_imported": False}
    try:
        protocol = json.loads(Path(args.protocol).read_text())
        feature_summary = json.loads(Path(args.feature_summary).read_text())
        result = json.loads(Path(args.final_results).read_text())
        dev_result = json.loads(Path(args.dev_results).read_text())
        if result["status"] != "frozen_test_evaluated_pending_independent_verification" or result["evaluation_splits"] != ["train", "dev", "test"]:
            raise AssertionError("final evaluation status/splits invalid")
        if feature_summary["status"] != "full_features_ready" or dev_result["status"] != "dev_only_no_test_access" or dev_result["test_metrics_computed"]:
            raise AssertionError("feature/dev freeze status invalid")
        for path, expected, label in ((args.protocol, result["protocol_sha256"], "protocol"), (args.feature_summary, result["feature_summary_sha256"], "feature_summary"), (protocol["split_file"], protocol["split_sha256"], "split"), (protocol["reference_cds"], protocol["reference_cds_sha256"], "reference"), (args.features, feature_summary["feature_file_sha256"], "features"), (args.predictions, result["prediction_file_sha256"], "predictions"), (args.dev_results, result["dev_baseline_result_sha256"], "dev_baseline")):
            actual = digest(path)
            if actual != expected:
                raise AssertionError(f"SHA mismatch {label}: {actual}")
        checks.append({"name": "protocol_and_artifact_sha", "pass": True, "details": "split/reference/features/predictions/dev-baseline hashes match"})

        weights, reference_used = independent_weights(protocol["reference_cds"])
        expected_weights = feature_summary["reference_stats"]["rscu_relative_adaptiveness"]
        if set(weights) != set(expected_weights) or reference_used != feature_summary["reference_stats"]["reference_used"]:
            raise AssertionError("reference used records or weight keys differ")
        for codon in weights:
            close(weights[codon], expected_weights[codon], 1e-15, "reference_weight_" + codon, differences)
        checks.append({"name": "independent_reference_rscu", "pass": True, "details": {"reference_used": reference_used, "weights": len(weights)}})

        features = read_features(args.features)
        raw_rows = []
        with open(protocol["split_file"], newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["source_id"] == protocol["source_id"]:
                    if row["split_assignment"] not in protocol["allowed_splits"]:
                        raise AssertionError("forbidden split entered raw verification")
                    raw_rows.append(row)
        if len(raw_rows) != protocol["expected_rows"]["total"] or len(features) != len(raw_rows):
            raise AssertionError("raw/feature total differs")
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers, initializer=_init, initargs=(weights, protocol["fold_temperature_c"], protocol["local_window_nt"])) as pool:
            recomputed = list(pool.map(raw_recompute, raw_rows, chunksize=8))
        counts = {split: 0 for split in protocol["allowed_splits"]}
        for key, values in recomputed:
            if key not in features:
                raise AssertionError(f"missing feature {key}")
            row = features[key]; counts[values["split_assignment"]] += 1
            if row["split_assignment"] != values["split_assignment"] or row["operational_protein_cluster"] != values["operational_protein_cluster"] or row["cds_sha256"] != values["cds_sha256"]:
                raise AssertionError(f"split/cluster/CDS mismatch {key}")
            close(row["length_nt"], values["length_nt"], 0, "raw_length_nt", differences)
            for field in ("gc_fraction", "cai"):
                close(row[field], values[field], 1e-12, "raw_" + field, differences)
            for field in ("full_cds_mfe_kcal_mol", "full_cds_mfe_per_nt", "mfe_5prime_48_kcal_mol"):
                close(row[field], values[field], 1e-4, "raw_" + field, differences)
        if counts != {k: v for k, v in protocol["expected_rows"].items() if k != "total"}:
            raise AssertionError(f"split counts differ: {counts}")
        checks.append({"name": "all_raw_cds_translation_cai_gc_mfe", "pass": True, "details": {"rows": len(raw_rows), "split_counts": counts, "mfe_tolerance": 1e-4}})

        prediction_rows = {split: [] for split in protocol["allowed_splits"]}
        with gzip.open(args.predictions, "rt", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                row["label"] = float(row["label"]); row["source_row_int"] = int(row["source_row"])
                row["length_nt"] = int(row["length_nt"]); row["gc_fraction"] = float(row["gc_fraction"])
                for name in MODELS:
                    row["pred_" + name] = float(row["pred_" + name])
                prediction_rows[row["split_assignment"]].append(row)
        feature_by_split = {split: sorted((r for r in features.values() if r["split_assignment"] == split), key=lambda r: int(r["source_row"])) for split in protocol["allowed_splits"]}
        raw_label = {(r["source_row"], r["construct_id"]): float(r["expression_value"]) for r in raw_rows}
        for split, rows in prediction_rows.items():
            rows.sort(key=lambda r: r["source_row_int"])
            if len(rows) != protocol["expected_rows"][split]:
                raise AssertionError(f"prediction count mismatch {split}")
            for row, feature in zip(rows, feature_by_split[split]):
                if (row["source_row"], row["construct_id"]) != (feature["source_row"], feature["construct_id"]):
                    raise AssertionError("prediction/feature order mismatch")
                close(row["label"], raw_label[(row["source_row"], row["construct_id"])], 0, "label", differences)
        checks.append({"name": "prediction_identities_labels_and_splits", "pass": True, "details": {s: len(v) for s, v in prediction_rows.items()}})

        train_features = feature_by_split["train"]
        combined = result["combined_model"]
        x_train = matrix(train_features, protocol["combined_features"])
        mean = x_train.mean(axis=0); scale = x_train.std(axis=0, ddof=0)
        for i, value in enumerate(mean): close(value, combined["train_mean"][i], 1e-12, "train_mean", differences)
        for i, value in enumerate(scale): close(value, combined["train_scale"][i], 1e-12, "train_scale", differences)
        y_train = np.array([raw_label[(r["source_row"], r["construct_id"])] for r in train_features])
        classes = np.array(combined["classes"]); weights_model = np.array(combined["weights"]); bias = np.array(combined["bias"])
        probabilities = softmax(((x_train - mean) / scale) @ weights_model.T + bias, axis=1)
        one_hot = np.eye(len(classes))[np.array([list(classes).index(int(y)) for y in y_train])]
        residual = (probabilities - one_hot) / len(y_train)
        gradient = np.concatenate([(residual.T @ ((x_train - mean) / scale) + protocol["combined_model"]["l2"] * weights_model).ravel(), residual.sum(axis=0)])
        gradient_max = float(np.max(np.abs(gradient)))
        if gradient_max > 1e-4:
            raise AssertionError(f"independent logistic gradient failed: {gradient_max}")
        close(gradient_max, combined["optimizer"]["gradient_max_abs"], 1e-8, "optimizer_gradient", differences)
        for proxy, fit in result["univariate_models"].items():
            x = matrix(train_features, [proxy])[:, 0]
            intercept, slope = np.linalg.lstsq(np.column_stack([np.ones(len(x)), x]), y_train, rcond=None)[0]
            close(intercept, fit["intercept"], 1e-10, "univariate_intercept_" + proxy, differences)
            close(slope, fit["slope"], 1e-10, "univariate_slope_" + proxy, differences)
        checks.append({"name": "train_only_preprocessing_and_convex_fit", "pass": True, "details": {"logistic_gradient_max_abs": gradient_max, "univariate_models": len(result["univariate_models"])}})

        independent_predictions = {}
        for split, features_split in feature_by_split.items():
            predictions = {}
            for proxy, fit in result["univariate_models"].items():
                predictions[proxy] = fit["intercept"] + fit["slope"] * matrix(features_split, [proxy])[:, 0]
            x = matrix(features_split, protocol["combined_features"])
            predictions["combined_logistic"] = softmax(((x - mean) / scale) @ weights_model.T + bias, axis=1) @ classes
            independent_predictions[split] = predictions
            for i, row in enumerate(prediction_rows[split]):
                for name in MODELS:
                    close(row["pred_" + name], predictions[name][i], 1e-10, "prediction_" + name, differences)
        checks.append({"name": "independent_model_predictions", "pass": True, "details": "all split/model prediction vectors recomputed"})

        rng_seed = protocol["bootstrap"]["seed"]
        for split_index, split in enumerate(protocol["allowed_splits"]):
            rows = prediction_rows[split]; y = np.array([r["label"] for r in rows]); source = np.array([r["source_row_int"] for r in rows]); clusters = np.array([r["operational_protein_cluster"] for r in rows])
            point = {name: metrics(y, independent_predictions[split][name], source, protocol["top_k_fraction"], protocol["top_k_positive_label"]) for name in MODELS}
            for name in MODELS:
                for key, value in point[name].items():
                    close(value, result["split_metrics"][split]["models"][name]["point"][key], 1e-10, f"point_{split}_{name}_{key}", differences)
                if name != "combined_logistic":
                    raw_spearman = float(spearmanr(y, matrix(feature_by_split[split], [name])[:, 0]).statistic)
                    close(raw_spearman, result["split_metrics"][split]["models"][name]["point"]["raw_spearman"], 1e-10, "raw_spearman", differences)
            if split == "train":
                continue
            groups = sorted(set(clusters)); lookup = {g: np.flatnonzero(clusters == g) for g in groups}
            rng = np.random.default_rng(rng_seed + split_index); b = protocol["bootstrap"]["replicates"]
            arrays = {name: np.zeros((b, len(BOOT_METRICS))) for name in MODELS}
            for replicate in range(b):
                sampled = rng.choice(groups, size=len(groups), replace=True); indices = np.concatenate([lookup[g] for g in sampled])
                for name in MODELS:
                    values = metrics(y[indices], independent_predictions[split][name][indices], source[indices], protocol["top_k_fraction"], protocol["top_k_positive_label"])
                    arrays[name][replicate] = [values[key] for key in BOOT_METRICS]
            p_values = {}
            for name in MODELS:
                for j, metric in enumerate(BOOT_METRICS):
                    expected = np.percentile(arrays[name][:, j], [2.5, 97.5])
                    actual = result["split_metrics"][split]["models"][name]["bootstrap_95ci"][metric]
                    close(actual[0], expected[0], 1e-10, "ci_low", differences); close(actual[1], expected[1], 1e-10, "ci_high", differences)
            for proxy in protocol["primary_proxies"]:
                for j, metric in enumerate(BOOT_METRICS):
                    difference = arrays["combined_logistic"][:, j] - arrays[proxy][:, j]
                    expected = np.percentile(difference, [2.5, 97.5]); comparison = result["split_metrics"][split]["paired_comparisons"][proxy]
                    close(comparison[metric + "_difference"][0], expected[0], 1e-10, "paired_low", differences); close(comparison[metric + "_difference"][1], expected[1], 1e-10, "paired_high", differences)
                    close(comparison[metric + "_point_difference"], point["combined_logistic"][metric] - point[proxy][metric], 1e-10, "paired_point", differences)
                difference = arrays["combined_logistic"][:, 0] - arrays[proxy][:, 0]
                p = min(1.0, 2 * min((int(np.sum(difference <= 0)) + 1) / (b + 1), (int(np.sum(difference >= 0)) + 1) / (b + 1)))
                p_values[proxy] = p
                close(p, result["split_metrics"][split]["paired_comparisons"][proxy]["spearman_p_raw"], 1e-15, "p_raw", differences)
            adjusted = holm(p_values)
            for proxy, p in adjusted.items():
                close(p, result["split_metrics"][split]["paired_comparisons"][proxy]["spearman_p_holm"], 1e-15, "p_holm", differences)
        checks.append({"name": "point_metrics_bootstrap_paired_ci_holm", "pass": True, "details": {"bootstrap_replicates_per_split": protocol["bootstrap"]["replicates"], "metrics": BOOT_METRICS}})

        thresholds = {variable: np.quantile(np.array([r[variable] for r in train_features], dtype=float), [1 / 3, 2 / 3]).tolist() for variable in protocol["stratification"]["variables"]}
        for variable in thresholds:
            for i in range(2): close(thresholds[variable][i], result["train_stratification_thresholds"][variable][i], 1e-12, "tercile", differences)
        for split, rows in prediction_rows.items():
            y = np.array([r["label"] for r in rows]); source = np.array([r["source_row_int"] for r in rows])
            for variable in protocol["stratification"]["variables"]:
                bins = np.searchsorted(np.array(thresholds[variable]), np.array([r[variable] for r in rows]), side="right")
                for index, label in enumerate(("low", "mid", "high")):
                    selected = bins == index
                    if int(selected.sum()) != result["stratified_metrics"][split][variable][label]["n"]:
                        raise AssertionError("stratum count mismatch")
                    for name in MODELS:
                        expected = metrics(y[selected], independent_predictions[split][name][selected], source[selected], protocol["top_k_fraction"], protocol["top_k_positive_label"])
                        for key, value in expected.items():
                            close(value, result["stratified_metrics"][split][variable][label]["models"][name][key], 1e-10, "stratum_metric", differences)
        checks.append({"name": "train_terciles_and_stratified_metrics", "pass": True, "details": "length/GC thresholds and every stratum recomputed"})

        frozen = {"model": dev_result["combined_model"], "univariate": dev_result["univariate_models"], "dev": dev_result["split_metrics"]["dev"], "dev_strata": dev_result["stratified_metrics"]["dev"], "thresholds": dev_result["train_stratification_thresholds"]}
        current = {"model": result["combined_model"], "univariate": result["univariate_models"], "dev": result["split_metrics"]["dev"], "dev_strata": result["stratified_metrics"]["dev"], "thresholds": result["train_stratification_thresholds"]}
        if frozen != current or not result["dev_baseline_exact_match"] or result["forbidden_split_used"]:
            raise AssertionError("dev freeze or untouched guard failed")
        checks.append({"name": "dev_freeze_and_untouched_guard", "pass": True, "details": "final model/dev results exactly match the pre-test artifact; functional_untouched unused"})
        report["status"] = "PASS"
        report["summary"] = {"raw_rows": len(raw_rows), "clean_split_counts": counts, "gradient_max_abs": gradient_max, "scientific_scope": result["scientific_scope"], "prohibited_claims": result["prohibited_claims"]}
    except Exception as error:
        checks.append({"name": "uncompleted_check", "pass": False, "details": str(error)})
        report["error"] = repr(error)
    report["check_count"] = len(checks); report["passed_checks"] = sum(bool(c["pass"]) for c in checks)
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"); os.replace(temporary, output)
    print(json.dumps({"status": report["status"], "checks": report["passed_checks"], "total": report["check_count"], "error": report.get("error")}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
