#!/usr/bin/env python3
"""Independently verify frozen RK04 sequence-OOD model predictions and metrics."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
from scipy.stats import pearsonr, spearmanr


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def corr(function, y, p):
    y = np.asarray(y, dtype=float); p = np.asarray(p, dtype=float)
    if len(y) < 2 or np.std(y) == 0 or np.std(p) == 0:
        return None
    value = float(function(y, p).statistic)
    return value if math.isfinite(value) else None


def metrics(rows, p):
    y = np.asarray([r["expression"] for r in rows], dtype=float)
    p = np.asarray(p, dtype=float)
    groups = defaultdict(list)
    for i, row in enumerate(rows):
        groups[row["cluster_id"]].append(i)
    weights = np.asarray([1.0 / len(groups[row["cluster_id"]]) for row in rows])
    gy = np.asarray([np.mean(y[v]) for v in groups.values()])
    gp = np.asarray([np.mean(p[v]) for v in groups.values()])
    cy, cp = [], []
    eligible = 0
    for idx in groups.values():
        if len(idx) >= 2 and np.std(y[idx]) > 0:
            eligible += 1
            cy.extend((y[idx] - np.mean(y[idx])).tolist())
            cp.extend((p[idx] - np.mean(p[idx])).tolist())
    denominator = float(np.sum((y - np.mean(y)) ** 2))
    constant_prediction = bool(np.all(p == p[0]))
    return {
        "n_rows": len(rows), "n_clusters": len(groups),
        "row_mse": float(np.mean((y - p) ** 2)),
        "row_r2": float(1.0 - np.sum((y - p) ** 2) / denominator) if denominator > 0 else None,
        "row_pearson": corr(pearsonr, y, p), "row_spearman": corr(spearmanr, y, p),
        "cluster_balanced_mse": float(np.average((y - p) ** 2, weights=weights)),
        "cluster_mean_pearson": None if constant_prediction else corr(pearsonr, gy, gp),
        "cluster_mean_spearman": None if constant_prediction else corr(spearmanr, gy, gp),
        "within_cluster_centered_spearman": None if constant_prediction or not eligible else corr(spearmanr, cy, cp),
        "within_cluster_eligible_clusters": eligible, "within_cluster_eligible_rows": len(cy),
    }


def bootstrap(rows, primary, reference, replicates, seed, percentiles):
    groups = defaultdict(list)
    for i, row in enumerate(rows):
        groups[row["cluster_id"]].append(i)
    keys = sorted(groups)
    y = np.asarray([r["expression"] for r in rows], dtype=float)
    rng = np.random.default_rng(seed)
    values = {"row_spearman_delta": [], "cluster_balanced_mse_delta": []}
    for _ in range(replicates):
        selected = rng.integers(0, len(keys), size=len(keys))
        idx, weights = [], []
        for k in selected:
            members = groups[keys[int(k)]]
            idx.extend(members); weights.extend([1.0 / len(members)] * len(members))
        idx = np.asarray(idx, dtype=int); weights = np.asarray(weights, dtype=float)
        a = corr(spearmanr, y[idx], primary[idx]); b = corr(spearmanr, y[idx], reference[idx])
        if a is not None and b is not None:
            values["row_spearman_delta"].append(a - b)
        values["cluster_balanced_mse_delta"].append(float(
            np.average((y[idx] - primary[idx]) ** 2, weights=weights)
            - np.average((y[idx] - reference[idx]) ** 2, weights=weights)
        ))
    result = {"replicates_requested": replicates, "seed": seed, "percentiles": percentiles, "statistics": {}}
    for name, items in values.items():
        array = np.asarray(items, dtype=float)
        result["statistics"][name] = {
            "valid_replicates": len(array),
            "ci95": [float(x) for x in np.percentile(array, percentiles)] if len(array) else [None, None],
            "median": float(np.median(array)) if len(array) else None,
        }
    return result


def close(a, b, tolerance=1e-11):
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(close(a[k], b[k], tolerance) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y, tolerance) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return math.isclose(float(a), float(b), rel_tol=tolerance, abs_tol=tolerance)
    return a == b


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--production-script", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    summary = json.loads(args.summary.read_text())
    data = protocol["data"]
    artifacts = {name: Path(value["path"]) for name, value in summary["artifacts"].items()}
    checks = []
    def check(name, condition):
        checks.append({"name": name, "pass": bool(condition)})
    check("production_pending_status", summary["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION")
    check("protocol_hash", hashlib.sha256(args.protocol.read_bytes()).hexdigest() == summary["protocol_sha256"])
    check("production_script_hash", sha256_file(args.production_script) == summary["production_code_sha256"])
    for key, sha_key in [("split_csv", "split_sha256"), ("features_csv_gz", "features_sha256"), ("normalization_json", "normalization_sha256")]:
        check(key + "_hash", sha256_file(data[key]) == data[sha_key])
    for name, info in summary["artifacts"].items():
        check("artifact_hash_" + name, sha256_file(info["path"]) == info["sha256"])

    core = {}
    untouched = 0
    with open(data["split_csv"], newline="") as handle:
        for raw in csv.DictReader(handle):
            assignment = raw["ood_assignment"]
            if assignment == "functional_untouched":
                untouched += 1
                continue
            if assignment not in data["allowed_assignments"]:
                continue
            key = (raw["source_row"], raw["construct_id"])
            core[key] = {
                "source_row": raw["source_row"], "construct_id": raw["construct_id"],
                "protein_id": raw["protein_id"], "cluster_id": raw["operational_protein_cluster"],
                "ood_assignment": assignment, "origin_split": raw["split_assignment"],
                "expression": float(raw["expression_value"]),
            }
    check("core_and_untouched_counts", len(core) == 6348 and untouched == 19072)
    prediction_rows = []
    with gzip.open(artifacts["predictions"], "rt", newline="") as handle:
        reader = csv.DictReader(handle)
        prediction_fields = reader.fieldnames
        for raw in reader:
            key = (raw["source_row"], raw["construct_id"])
            row = dict(core[key])
            if float(raw["expression"]) != row["expression"]:
                raise ValueError(f"prediction expression mismatch {key}")
            for family in [f["family"] for f in protocol["families"]]:
                row["pred_" + family] = float(raw["pred_" + family])
            prediction_rows.append(row)
    families = [f["family"] for f in protocol["families"]]
    check("prediction_identities_exact", len(prediction_rows) == 6348 and {(r["source_row"], r["construct_id"]) for r in prediction_rows} == set(core))
    check("prediction_columns_no_untouched", all(r["ood_assignment"] != "functional_untouched" for r in prediction_rows))
    check("prediction_columns_only_expected_families", set(prediction_fields) == {"source_row", "construct_id", "protein_id", "cluster_id", "ood_assignment", "origin_split", "expression"} | {"pred_" + f for f in families})

    metrics_payload = json.loads(artifacts["metrics"].read_text())
    by_partition = {name: [r for r in prediction_rows if r["ood_assignment"] == name] for name in data["allowed_assignments"]}
    check("partition_counts", {k: len(v) for k, v in by_partition.items()} == {"train": 4019, "dev": 503, "test": 490, "sequence_ood": 1336})
    recomputed = {"partitions": {}, "sequence_ood_origin_strata": {}}
    for partition, rows in by_partition.items():
        recomputed["partitions"][partition] = {family: metrics(rows, [r["pred_" + family] for r in rows]) for family in families}
    for origin in protocol["evaluation"]["sequence_ood_origin_strata"]:
        rows = [r for r in by_partition["sequence_ood"] if r["origin_split"] == origin]
        recomputed["sequence_ood_origin_strata"][origin] = {family: metrics(rows, [r["pred_" + family] for r in rows]) for family in families}
    check("all_partition_metrics_recomputed", close(recomputed["partitions"], metrics_payload["partitions"]))
    check("ood_origin_metrics_recomputed", close(recomputed["sequence_ood_origin_strata"], metrics_payload["sequence_ood_origin_strata"]))
    check("ood_origin_counts", [len([r for r in by_partition["sequence_ood"] if r["origin_split"] == o]) for o in ["train", "dev", "test"]] == [1060, 132, 144])
    check("summary_test_ood_metrics_match", close(summary["test_metrics"], metrics_payload["partitions"]["test"]) and close(summary["sequence_ood_metrics"], metrics_payload["partitions"]["sequence_ood"]))

    with open(artifacts["dev_model_selection"], newline="") as handle:
        selection = list(csv.DictReader(handle))
    check("selection_candidate_count_17", len(selection) == 17)
    check("selection_file_has_no_final_metrics", not any("test" in key or "ood" in key for key in selection[0]))
    selected_recomputed = {}
    for family in families:
        rows = [r for r in selection if r["family"] == family]
        selected_rows = [r for r in rows if r["selected"] == "1"]
        best = min(float(r["dev_cluster_balanced_mse"]) for r in rows)
        selected_recomputed[family] = int(selected_rows[0]["candidate_index"]) if len(selected_rows) == 1 else -1
        check("one_dev_best_" + family, len(selected_rows) == 1 and float(selected_rows[0]["dev_cluster_balanced_mse"]) == best)
    check("selected_candidate_indices_match", all(selected_recomputed[f] == metrics_payload["selected"][f]["candidate_index"] for f in families))
    expected_primary = min(families, key=lambda f: (metrics_payload["selected"][f]["dev_metrics"]["cluster_balanced_mse"], families.index(f)))
    check("primary_selected_by_dev_only", metrics_payload["primary_family"] == expected_primary == summary["primary_family"])

    model_payload = joblib.load(artifacts["selected_models"])
    normalization = json.loads(open(data["normalization_json"]).read())["features"]
    check("model_normalization_exact", model_payload["normalization"] == normalization)
    max_delta = 0.0
    feature_cache = {}
    with gzip.open(data["features_csv_gz"], "rt", newline="") as handle:
        for raw in csv.DictReader(handle):
            key = (raw["source_row"], raw["construct_id"])
            if key not in core:
                continue
            raw["log_length_nt"] = format(math.log(int(raw["length_nt"])), ".17g")
            feature_cache[key] = raw
    for family in families:
        model_info = model_payload["models"][family]
        if family == "constant":
            predicted = np.full(len(prediction_rows), model_info["mean"])
        else:
            columns = []
            for name in model_info["feature_names"]:
                stats = normalization[name]
                observed = np.asarray([stats["mean"] if feature_cache[(r["source_row"], r["construct_id"])][name] == "" else float(feature_cache[(r["source_row"], r["construct_id"])][name]) for r in prediction_rows])
                columns.append((observed - stats["mean"]) / stats["scale_ddof0"])
                if name in protocol["missing_indicator_features"]:
                    columns.append(np.asarray([1.0 if feature_cache[(r["source_row"], r["construct_id"])][name] == "" else 0.0 for r in prediction_rows]))
            matrix = np.column_stack(columns)
            predicted = model_info["model"].predict(matrix)
        delta = float(np.max(np.abs(predicted - np.asarray([r["pred_" + family] for r in prediction_rows]))))
        max_delta = max(max_delta, delta)
        check("independent_model_forward_" + family, delta <= 1e-12)

    comparison = metrics_payload["primary_comparison"]
    primary = comparison["primary_family"]
    boot = protocol["evaluation"]["bootstrap"]
    for partition in boot["partitions"]:
        rows = by_partition[partition]
        p = np.asarray([r["pred_" + primary] for r in rows])
        g = np.asarray([r["pred_ridge_gc"] for r in rows])
        pm = metrics(rows, p); gm = metrics(rows, g)
        observed = {
            "row_spearman_delta": pm["row_spearman"] - gm["row_spearman"] if pm["row_spearman"] is not None and gm["row_spearman"] is not None else None,
            "cluster_balanced_mse_delta": pm["cluster_balanced_mse"] - gm["cluster_balanced_mse"],
        }
        check("observed_primary_delta_" + partition, close(observed, comparison["observed"][partition]))
        recomputed_boot = bootstrap(rows, p, g, int(boot["replicates"]), int(boot["seed"]), boot["ci_percentiles"])
        check("bootstrap_recomputed_" + partition, close(recomputed_boot, comparison["bootstrap"][partition]))
    check("scope_no_generator_or_sota", not protocol["scope"]["codonflow_rk_generator_claim"] and not protocol["scope"]["sota_claim"])
    check("untouched_not_evaluated", summary["functional_untouched_evaluated"] is False)
    passed = sum(c["pass"] for c in checks)
    report = {
        "schema_version": "a8-rk04-sequence-ood-model-independent-v1",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "checks_passed": passed, "checks_total": len(checks), "checks": checks,
        "failed": [c["name"] for c in checks if not c["pass"]],
        "summary": str(args.summary.resolve()), "summary_sha256": sha256_file(args.summary),
        "production_script_sha256": sha256_file(args.production_script),
        "protocol_sha256": hashlib.sha256(args.protocol.read_bytes()).hexdigest(),
        "metrics_sha256": sha256_file(artifacts["metrics"]), "predictions_sha256": sha256_file(artifacts["predictions"]),
        "dev_model_selection_sha256": sha256_file(artifacts["dev_model_selection"]),
        "max_model_prediction_abs_delta": max_delta,
        "primary_family": primary, "untouched_rows_excluded": untouched,
        "functional_untouched_evaluated": False, "sequence_ood_evaluated": True,
        "generator_training_authorized": False, "sota_claim": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + f".part.{os.getpid()}")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.output)
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "failed": report["failed"], "max_model_prediction_abs_delta": max_delta}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
