#!/usr/bin/env python3
"""Independent raw-input verification of the retrospective HistGB diagnostic."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rank_correlation(y: np.ndarray, pred: np.ndarray) -> float:
    if np.std(y) <= 0 or np.std(pred) <= 0:
        return float("nan")
    return float(np.corrcoef(stats.rankdata(y), stats.rankdata(pred))[0, 1])


def holm(values: list[float]) -> np.ndarray:
    p = np.asarray(values, float)
    order = np.argsort(p)
    adjusted = np.empty(len(p), float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p) - rank) * p[index])
        adjusted[index] = min(1.0, running)
    return adjusted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--all-dir", required=True)
    parser.add_argument("--baseline-predictions", required=True)
    parser.add_argument("--original-summary", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--analysis-script", required=True)
    parser.add_argument("--analysis-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    started = time.time()
    checks: list[dict] = []

    def check(name: str, passed: bool, detail) -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    analysis_dir = Path(args.analysis_dir)
    summary = json.loads((analysis_dir / "comparison_summary.json").read_text())
    original = json.loads(Path(args.original_summary).read_text())
    protocol = json.loads(Path(args.protocol).read_text())
    check("summary_pending", summary["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION", summary["status"])
    check("retrospective_label", summary["analysis_status"] == "retrospective_after_unpaired_metric_readout_not_preregistered", summary["analysis_status"])
    check("protocol_id", protocol["protocol_id"] == summary["protocol"] == "a8_rk08_histgb_diagnostic_v1_retrospective_after_unpaired_metric_readout", summary["protocol"])
    check("original_gate_false", original["rk_g1_pass"] is False and summary["original_rk_g1_pass"] is False, summary["original_rk_g1_pass"])
    check("original_gate_unchanged", summary["original_gate_modified"] is False, summary["original_gate_modified"])
    check("no_fitting", summary["model_fitting_performed"] is False, summary["model_fitting_performed"])
    check("no_selection", summary["model_selection_performed"] is False, summary["model_selection_performed"])
    check("no_generator_authorization", summary["expensive_generation_authorized"] is False, summary["expensive_generation_authorized"])
    check("no_sota", summary["sota_claimed"] is False, summary["sota_claimed"])
    check("no_fixed_protein_claim", summary["fixed_protein_synonymous_mechanism_supported"] is False, summary["fixed_protein_synonymous_mechanism_supported"])
    for name, path in [
        ("data_sha256", args.data),
        ("all_predictions_sha256", Path(args.all_dir) / "predictions.csv"),
        ("baseline_predictions_sha256", args.baseline_predictions),
        ("original_summary_sha256", args.original_summary),
        ("protocol_sha256", args.protocol),
        ("analysis_script_sha256", args.analysis_script),
    ]:
        observed = sha256(path)
        check(f"input_{name}", summary["inputs"][name] == observed, observed)
    for name, path in [("original_data", args.data), ("original_all_predictions", Path(args.all_dir) / "predictions.csv"), ("original_baseline", args.baseline_predictions)]:
        key = {"original_data": "data_sha256", "original_all_predictions": "all_predictions_sha256", "original_baseline": "baseline_predictions_sha256"}[name]
        check(name, original["inputs"][key] == sha256(path), sha256(path))

    columns = ["source_row", "construct_id", "ood_assignment", "operational_protein_cluster", "expression_value"]
    source = pd.read_csv(args.data, usecols=columns)
    source = source[source["ood_assignment"].isin(["train", "dev", "test", "sequence_ood"])].reset_index(drop=True)
    check("source_rows", len(source) == 6348, len(source))
    check("source_unique", not source[["construct_id", "ood_assignment"]].duplicated().any(), True)
    split_counts = source["ood_assignment"].value_counts().to_dict()
    check("split_counts", split_counts == {"train": 4019, "sequence_ood": 1336, "dev": 503, "test": 490}, split_counts)
    check("no_untouched_split", set(source["ood_assignment"]) == {"train", "dev", "test", "sequence_ood"}, sorted(set(source["ood_assignment"])))

    model = pd.read_csv(Path(args.all_dir) / "predictions.csv")
    model_map = {(r.record_id, r.split): (float(r.prediction), float(r.target), str(r.cluster_id)) for r in model.itertuples()}
    baseline = pd.read_csv(args.baseline_predictions)
    baseline_map = {(r.construct_id, r.ood_assignment): (float(r.pred_histgb_all), float(r.expression), int(r.source_row)) for r in baseline.itertuples()}
    check("model_prediction_rows", len(model_map) == len(source), len(model_map))
    check("baseline_prediction_rows", len(baseline_map) == len(source), len(baseline_map))
    ribo = np.empty(len(source), float)
    hist = np.empty(len(source), float)
    alignment_errors = []
    for index, row in enumerate(source.itertuples()):
        key = (row.construct_id, row.ood_assignment)
        if key not in model_map or key not in baseline_map:
            alignment_errors.append((key, "missing"))
            continue
        rp, rt, rc = model_map[key]
        hp, ht, hs = baseline_map[key]
        if rt != float(row.expression_value) or rc != str(row.operational_protein_cluster) or ht != float(row.expression_value) or hs != int(row.source_row):
            alignment_errors.append((key, "mismatch"))
        ribo[index] = rp
        hist[index] = hp
    check("raw_alignment", not alignment_errors, alignment_errors[:10])
    check("finite_predictions", bool(np.isfinite(ribo).all() and np.isfinite(hist).all()), True)

    recomputed_comparisons = []
    max_bootstrap_error = 0.0
    saved_boot = pd.read_csv(analysis_dir / "bootstrap_deltas.csv.gz")
    boot_offset = 0
    for partition in ["dev", "test", "sequence_ood"]:
        mask = source["ood_assignment"].to_numpy() == partition
        y = source.loc[mask, "expression_value"].to_numpy(float)
        clusters = source.loc[mask, "operational_protein_cluster"].to_numpy(str)
        names = np.unique(clusters)
        cluster_indices = [np.flatnonzero(clusters == name) for name in names]
        partition_metrics = {}
        for model_name, pred in [("ribokinetic_all", ribo[mask]), ("histgb_all", hist[mask])]:
            errors2 = (pred - y) ** 2
            per_cluster = np.array([float(np.mean(errors2[idx])) for idx in cluster_indices])
            metrics = {
                "row_spearman": rank_correlation(y, pred),
                "cluster_balanced_mse": float(np.mean(per_cluster)),
            }
            partition_metrics[model_name] = metrics
            for metric, observed in metrics.items():
                expected = summary["metrics"][partition][model_name][metric]
                check(f"metric:{partition}:{model_name}:{metric}", math.isclose(observed, expected, rel_tol=0, abs_tol=2e-12), {"recomputed": observed, "reported": expected})
            check(f"rows:{partition}:{model_name}", summary["metrics"][partition][model_name]["n_rows"] == len(y), len(y))
            check(f"clusters:{partition}:{model_name}", summary["metrics"][partition][model_name]["n_clusters"] == len(names), len(names))
        if partition == "dev":
            continue
        rng = np.random.default_rng(20261119 + (0 if partition == "test" else 0))
        # The analysis uses one RNG continuously across test then sequence-OOD.
        if partition == "sequence_ood":
            rng = np.random.default_rng(20261119)
            test_mask = source["ood_assignment"].to_numpy() == "test"
            test_clusters = source.loc[test_mask, "operational_protein_cluster"].to_numpy(str)
            test_group_count = len(np.unique(test_clusters))
            for _ in range(2000):
                rng.integers(0, test_group_count, test_group_count)
        deltas = {"spearman": [], "cluster_balanced_mse": []}
        cluster_mse = {}
        for model_name, pred in [("ribokinetic_all", ribo[mask]), ("histgb_all", hist[mask])]:
            errors2 = (pred - y) ** 2
            cluster_mse[model_name] = np.array([float(np.mean(errors2[idx])) for idx in cluster_indices])
        for _ in range(2000):
            selected = rng.integers(0, len(cluster_indices), len(cluster_indices))
            rows = np.concatenate([cluster_indices[j] for j in selected])
            deltas["spearman"].append(rank_correlation(y[rows], ribo[mask][rows]) - rank_correlation(y[rows], hist[mask][rows]))
            deltas["cluster_balanced_mse"].append(float(np.mean(cluster_mse["ribokinetic_all"][selected]) - np.mean(cluster_mse["histgb_all"][selected])))
        for metric in ["spearman", "cluster_balanced_mse"]:
            samples = np.asarray(deltas[metric], float)
            saved = saved_boot[(saved_boot["partition"] == partition) & (saved_boot["metric"] == metric)].sort_values("replicate")["delta"].to_numpy(float)
            check(f"bootstrap_rows:{partition}:{metric}", len(saved) == 2000, len(saved))
            if len(saved) == len(samples):
                error = float(np.max(np.abs(saved - samples)))
                max_bootstrap_error = max(max_bootstrap_error, error)
                check(f"bootstrap_values:{partition}:{metric}", error <= 5e-12, error)
            point_delta = partition_metrics["ribokinetic_all"]["row_spearman" if metric == "spearman" else "cluster_balanced_mse"] - partition_metrics["histgb_all"]["row_spearman" if metric == "spearman" else "cluster_balanced_mse"]
            valid = samples[np.isfinite(samples)]
            benefit = valid if metric == "spearman" else -valid
            pvalue = float(min(1.0, 2.0 * min(np.mean(benefit <= 0), np.mean(benefit >= 0))))
            recomputed_comparisons.append({
                "partition": partition,
                "metric": metric,
                "point_delta": point_delta,
                "ci95_low": float(np.quantile(valid, 0.025)),
                "ci95_high": float(np.quantile(valid, 0.975)),
                "sign_pvalue": pvalue,
                "bootstrap_valid": int(len(valid)),
            })
        boot_offset += 2000

    for partition in ["test", "sequence_ood"]:
        rows = [r for r in recomputed_comparisons if r["partition"] == partition]
        adjusted = holm([r["sign_pvalue"] for r in rows])
        for row, p_adj in zip(rows, adjusted):
            row["holm_pvalue_within_partition"] = float(p_adj)
            expected = next(r for r in summary["comparisons"] if r["partition"] == partition and r["metric"] == row["metric"])
            for field in ["point_delta", "ci95_low", "ci95_high", "sign_pvalue", "holm_pvalue_within_partition"]:
                check(f"comparison:{partition}:{row['metric']}:{field}", math.isclose(row[field], expected[field], rel_tol=0, abs_tol=5e-12), {"recomputed": row[field], "reported": expected[field]})
            check(f"comparison:{partition}:{row['metric']}:bootstrap_valid", row["bootstrap_valid"] == expected["bootstrap_valid"] == 2000, row["bootstrap_valid"])

    seq_rows = [r for r in recomputed_comparisons if r["partition"] == "sequence_ood"]
    favors = all(r["holm_pvalue_within_partition"] < 0.05 and ((r["metric"] == "spearman" and r["ci95_low"] > 0) or (r["metric"] == "cluster_balanced_mse" and r["ci95_high"] < 0)) for r in seq_rows)
    check("diagnostic_decision", favors == summary["diagnostic_favors_ribokinetic_all"] and favors is False, favors)
    failures = [c for c in checks if not c["pass"]]
    report = {
        "protocol": "a8_rk08_histgb_diagnostic_independent_v1",
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "checks_passed": len(checks) - len(failures),
        "checks_total": len(checks),
        "failures": failures,
        "recomputed_comparisons": recomputed_comparisons,
        "max_bootstrap_abs_delta": max_bootstrap_error,
        "analysis_summary_sha256": sha256(analysis_dir / "comparison_summary.json"),
        "production_analysis_imported": False,
        "model_training_rerun": False,
        "original_gate_modified": False,
        "expensive_generation_authorized": False,
        "sota_claimed": False,
        "fixed_protein_synonymous_mechanism_supported": False,
        "elapsed_seconds": time.time() - started,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "max_bootstrap_abs_delta": max_bootstrap_error, "output": args.output}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
