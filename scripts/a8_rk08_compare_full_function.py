#!/usr/bin/env python3
"""Pre-registered paired comparison for full RK08 function experiments.

Primary endpoint: sequence-OOD cluster-balanced MSE.
Secondary endpoint: sequence-OOD row Spearman.
The retained test is reported, never used for model selection or the RK-G1 gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from scipy import stats


MODELS = ["ribokinetic_all", "ribokinetic_none", "ridge_all", "ridge_gc", "histgb_all"]
COMPARISONS = [
    ("ribokinetic_all", "ribokinetic_none"),
    ("ribokinetic_all", "ridge_all"),
    ("ribokinetic_all", "ridge_gc"),
]
METRICS = ["spearman", "cluster_balanced_mse"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def finite(x):
    return None if x is None or not np.isfinite(x) else float(x)


def point_metrics(y, pred, cluster):
    y = np.asarray(y, float)
    pred = np.asarray(pred, float)
    err = pred - y
    frame = pd.DataFrame({"cluster": cluster, "squared_error": err ** 2})
    cluster_mse = frame.groupby("cluster")["squared_error"].mean()
    variance = float(np.sum((y - y.mean()) ** 2))
    r2 = None if variance <= 0 else float(1.0 - np.sum(err ** 2) / variance)
    rho = stats.spearmanr(y, pred).statistic
    pearson = stats.pearsonr(y, pred).statistic
    return {
        "n_rows": int(len(y)),
        "n_clusters": int(frame["cluster"].nunique()),
        "row_mse": float(np.mean(err ** 2)),
        "row_r2": r2,
        "row_spearman": finite(rho),
        "row_pearson": finite(pearson),
        "cluster_balanced_mse": float(cluster_mse.mean()),
    }


def fast_spearman(y, pred):
    if np.std(y) <= 0 or np.std(pred) <= 0:
        return np.nan
    yr = stats.rankdata(y)
    pr = stats.rankdata(pred)
    return float(np.corrcoef(yr, pr)[0, 1])


def holm_adjust(pvalues):
    p = np.asarray(pvalues, float)
    order = np.argsort(p)
    adjusted = np.empty(len(p), float)
    running = 0.0
    for rank, index in enumerate(order):
        value = (len(p) - rank) * p[index]
        running = max(running, value)
        adjusted[index] = min(1.0, running)
    return adjusted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--all-dir", required=True)
    parser.add_argument("--none-dir", required=True)
    parser.add_argument("--baseline-predictions", required=True)
    parser.add_argument("--train-script", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20261119)
    args = parser.parse_args()
    started = time.time()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    usecols = ["source_row", "construct_id", "ood_assignment", "operational_protein_cluster", "expression_value", "cds"]
    source = pd.read_csv(args.data, usecols=usecols)
    source = source[source["ood_assignment"].isin(["train", "dev", "test", "sequence_ood"])].reset_index(drop=True)
    assert len(source) == 6348
    assert not source[["construct_id", "ood_assignment"]].duplicated().any()
    assert source["cds"].notna().all()

    def read_model(path, name):
        frame = pd.read_csv(path).rename(columns={"record_id": "construct_id", "split": "ood_assignment", "cluster_id": "cluster", "prediction": "pred", "target": "prediction_target"})
        assert len(frame) == len(source)
        assert not frame[["construct_id", "ood_assignment"]].duplicated().any()
        assert np.isfinite(frame[["pred", "lower_95", "upper_95"]].to_numpy()).all()
        aligned = source[["construct_id", "ood_assignment", "operational_protein_cluster", "expression_value"]].merge(
            frame[["construct_id", "ood_assignment", "cluster", "prediction_target", "pred"]],
            on=["construct_id", "ood_assignment"], how="left", validate="one_to_one"
        )
        assert len(aligned) == len(source)
        assert aligned["cluster"].notna().all(), name
        assert aligned["cluster"].tolist() == aligned["operational_protein_cluster"].tolist(), (name, "cluster")
        assert np.array_equal(aligned["prediction_target"].to_numpy(), aligned["expression_value"].to_numpy()), (name, "target")
        return aligned["pred"].to_numpy(float)

    predictions = {
        "ribokinetic_all": read_model(Path(args.all_dir) / "predictions.csv", "all"),
        "ribokinetic_none": read_model(Path(args.none_dir) / "predictions.csv", "none"),
    }
    baseline = pd.read_csv(args.baseline_predictions)
    baseline = baseline[["source_row", "construct_id", "ood_assignment", "expression", "pred_ridge_all", "pred_ridge_gc", "pred_histgb_all"]]
    merged = source.merge(baseline, left_on=["source_row", "construct_id", "ood_assignment"], right_on=["source_row", "construct_id", "ood_assignment"], how="left", validate="one_to_one")
    assert len(merged) == len(source)
    assert np.allclose(merged["expression_value"], merged["expression"])
    predictions["ridge_all"] = merged["pred_ridge_all"].to_numpy(float)
    predictions["ridge_gc"] = merged["pred_ridge_gc"].to_numpy(float)
    predictions["histgb_all"] = merged["pred_histgb_all"].to_numpy(float)
    for name, values in predictions.items():
        assert np.isfinite(values).all(), name

    rng = np.random.default_rng(args.seed)
    all_metrics = {}
    comparison_rows = []
    bootstrap_rows = []
    for partition in ["dev", "test", "sequence_ood"]:
        indices = np.flatnonzero(source["ood_assignment"].to_numpy() == partition)
        y = source["expression_value"].to_numpy(float)[indices]
        clusters = source["operational_protein_cluster"].to_numpy()[indices]
        part = {}
        for model in MODELS:
            part[model] = point_metrics(y, predictions[model][indices], clusters)
        all_metrics[partition] = part
        if partition == "dev":
            continue

        cluster_frame = pd.DataFrame({"cluster": clusters, "row": np.arange(len(indices))})
        groups = [g["row"].to_numpy() for _, g in cluster_frame.groupby("cluster", sort=True)]
        cluster_names = sorted(cluster_frame["cluster"].unique())
        cluster_mse = {}
        for model in MODELS:
            squared = (predictions[model][indices] - y) ** 2
            cluster_mse[model] = np.array([np.mean(squared[g]) for g in groups])
        boot_metric = {(comparison, metric): [] for comparison in COMPARISONS for metric in METRICS}
        for _ in range(args.bootstrap):
            selected = rng.integers(0, len(groups), len(groups))
            rows = np.concatenate([groups[j] for j in selected])
            values = {}
            for model in MODELS:
                values[(model, "spearman")] = fast_spearman(y[rows], predictions[model][indices][rows])
                values[(model, "cluster_balanced_mse")] = float(np.mean(cluster_mse[model][selected]))
            for left, right in COMPARISONS:
                for metric in METRICS:
                    delta = values[(left, metric)] - values[(right, metric)]
                    boot_metric[((left, right), metric)].append(delta)
        partition_rows = []
        for left, right in COMPARISONS:
            for metric in METRICS:
                point_delta = part[left]["row_spearman" if metric == "spearman" else "cluster_balanced_mse"] - part[right]["row_spearman" if metric == "spearman" else "cluster_balanced_mse"]
                samples = np.asarray(boot_metric[((left, right), metric)], float)
                valid = samples[np.isfinite(samples)]
                benefit = samples if metric == "spearman" else -samples
                valid_benefit = benefit[np.isfinite(benefit)]
                pvalue = float(min(1.0, 2.0 * min(np.mean(valid_benefit <= 0), np.mean(valid_benefit >= 0)))) if len(valid_benefit) else 1.0
                row = {
                    "partition": partition,
                    "left": left,
                    "right": right,
                    "metric": metric,
                    "point_delta": finite(point_delta),
                    "ci95_low": finite(np.quantile(valid, 0.025)) if len(valid) else None,
                    "ci95_high": finite(np.quantile(valid, 0.975)) if len(valid) else None,
                    "sign_pvalue": pvalue,
                    "bootstrap_valid": int(len(valid)),
                    "bootstrap_requested": args.bootstrap,
                }
                partition_rows.append(row)
                for replicate, value in enumerate(samples):
                    bootstrap_rows.append({"partition": partition, "left": left, "right": right, "metric": metric, "replicate": replicate, "delta": value})
        adjusted = holm_adjust([row["sign_pvalue"] for row in partition_rows])
        for row, p_adj in zip(partition_rows, adjusted):
            row["holm_pvalue_within_partition"] = float(p_adj)
            comparison_rows.append(row)

    gate_rows = [r for r in comparison_rows if r["partition"] == "sequence_ood"]
    gate_pass = all(
        row["ci95_low"] is not None
        and row["ci95_high"] is not None
        and row["holm_pvalue_within_partition"] < 0.05
        and ((row["metric"] == "spearman" and row["ci95_low"] > 0) or (row["metric"] == "cluster_balanced_mse" and row["ci95_high"] < 0))
        for row in gate_rows
    )
    costs = {}
    for name, directory in [("ribokinetic_all", args.all_dir), ("ribokinetic_none", args.none_dir)]:
        run = json.loads((Path(directory) / "run_summary.json").read_text())
        checkpoint = torch.load(Path(directory) / "best.pt", map_location="cpu", weights_only=False)
        parameter_count = int(sum(tensor.numel() for tensor in checkpoint["state_dict"].values()))
        costs[name] = {
            "elapsed_seconds": run["training"]["elapsed_seconds"],
            "best_epoch": run["selected_epoch"],
            "forward_passes_including_dev_and_final_eval": run["training"]["forward_passes"],
            "parameters": parameter_count,
            "gpu": run["environment"]["gpu"],
            "deterministic_algorithms": run["environment"].get("deterministic_algorithms"),
            "sdp_backends": run["environment"].get("sdp_backends"),
            "checkpoint_sha256": run["hashes"]["checkpoint_sha256"],
            "config_sha256": run["hashes"]["config_sha256"],
        }
    summary = {
        "protocol": "a8_rk08_full_function_paired_v1_preregistered_before_result_readout",
        "status": "PASS_PENDING_INDEPENDENT_VERIFICATION",
        "scientific_scope": "Cross-protein nonsynonymous Boël function prediction; not fixed-protein synonymous mechanism evidence.",
        "selection": "Dev cluster-balanced MSE only; test and sequence-OOD were excluded from fitting and checkpoint selection.",
        "primary_endpoint": "sequence_ood cluster_balanced_mse",
        "secondary_endpoint": "sequence_ood row_spearman",
        "rk_g1_gate": "All three comparisons must favor ribokinetic_all on both sequence-OOD metrics, with 95% CI excluding zero and Holm p<0.05 within partition.",
        "rk_g1_pass": bool(gate_pass),
        "expensive_generation_authorized": False,
        "sota_claimed": False,
        "metrics": all_metrics,
        "comparisons": comparison_rows,
        "costs": costs,
        "bootstrap": {"method": "operational_protein_cluster_resampling", "replicates": args.bootstrap, "seed": args.seed},
        "inputs": {
            "data_sha256": sha256(args.data),
            "all_predictions_sha256": sha256(Path(args.all_dir) / "predictions.csv"),
            "none_predictions_sha256": sha256(Path(args.none_dir) / "predictions.csv"),
            "baseline_predictions_sha256": sha256(args.baseline_predictions),
            "train_script_sha256": sha256(args.train_script),
            "comparison_script_sha256": sha256(__file__),
        },
        "elapsed_seconds": time.time() - started,
    }
    pd.DataFrame(comparison_rows).to_csv(out / "paired_comparisons.csv", index=False)
    pd.DataFrame(bootstrap_rows).to_csv(out / "bootstrap_deltas.csv.gz", index=False, compression="gzip")
    metric_rows = []
    for partition, values in all_metrics.items():
        for model, metrics in values.items():
            metric_rows.append({"partition": partition, "model": model, **metrics})
    pd.DataFrame(metric_rows).to_csv(out / "metrics.csv", index=False)
    save_json(out / "comparison_summary.json", summary)
    print(json.dumps({"status": summary["status"], "rk_g1_pass": gate_pass, "output_dir": str(out), "elapsed_seconds": summary["elapsed_seconds"]}, indent=2))
    if not gate_pass:
        print("RK_G1_NOT_PASSED: negative or uncertain results retained; no generator launch.")


if __name__ == "__main__":
    main()
