#!/usr/bin/env python3
"""Retrospective paired diagnostic against the omitted frozen HistGB baseline.

This script performs no fitting or model selection. It preserves the original
RK-G1 gate and only adds the missing ribokinetic_all - histgb_all comparison.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import torch

from a8_rk08_compare_full_function import (
    fast_spearman,
    finite,
    holm_adjust,
    point_metrics,
    save_json,
    sha256,
)

MODELS = ["ribokinetic_all", "histgb_all"]
METRICS = ["spearman", "cluster_balanced_mse"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--all-dir", required=True)
    parser.add_argument("--baseline-predictions", required=True)
    parser.add_argument("--original-summary", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20261119)
    args = parser.parse_args()
    started = time.time()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    protocol = json.loads(Path(args.protocol).read_text())
    original = json.loads(Path(args.original_summary).read_text())
    if protocol["protocol_id"] != "a8_rk08_histgb_diagnostic_v1_retrospective_after_unpaired_metric_readout":
        raise ValueError("Unexpected diagnostic protocol")
    if args.bootstrap != 2000 or args.seed != 20261119:
        raise ValueError("Frozen diagnostic requires 2000 bootstrap replicates and seed 20261119")
    if original["inputs"]["data_sha256"] != sha256(args.data):
        raise ValueError("Source data differs from frozen comparison")
    if original["inputs"]["baseline_predictions_sha256"] != sha256(args.baseline_predictions):
        raise ValueError("Baseline predictions differ from frozen comparison")
    all_prediction_path = Path(args.all_dir) / "predictions.csv"
    if original["inputs"]["all_predictions_sha256"] != sha256(all_prediction_path):
        raise ValueError("Ribokinetic predictions differ from frozen comparison")

    usecols = ["source_row", "construct_id", "ood_assignment", "operational_protein_cluster", "expression_value", "cds"]
    source = pd.read_csv(args.data, usecols=usecols)
    source = source[source["ood_assignment"].isin(["train", "dev", "test", "sequence_ood"])].reset_index(drop=True)
    if len(source) != 6348 or source[["construct_id", "ood_assignment"]].duplicated().any():
        raise ValueError("Unexpected source rows or duplicate construct/split identifiers")

    model = pd.read_csv(all_prediction_path).rename(
        columns={"record_id": "construct_id", "split": "ood_assignment", "cluster_id": "cluster", "prediction": "pred", "target": "prediction_target"}
    )
    if len(model) != len(source) or model[["construct_id", "ood_assignment"]].duplicated().any():
        raise ValueError("Unexpected ribokinetic prediction rows")
    aligned = source[["construct_id", "ood_assignment", "operational_protein_cluster", "expression_value"]].merge(
        model[["construct_id", "ood_assignment", "cluster", "prediction_target", "pred"]],
        on=["construct_id", "ood_assignment"], how="left", validate="one_to_one",
    )
    if len(aligned) != len(source) or aligned["cluster"].isna().any():
        raise ValueError("Missing aligned ribokinetic predictions")
    if aligned["cluster"].tolist() != aligned["operational_protein_cluster"].tolist():
        raise ValueError("Cluster mismatch")
    if not np.array_equal(aligned["prediction_target"].to_numpy(), aligned["expression_value"].to_numpy()):
        raise ValueError("Target mismatch")
    predictions = {"ribokinetic_all": aligned["pred"].to_numpy(float)}

    baseline = pd.read_csv(args.baseline_predictions)
    baseline = baseline[["source_row", "construct_id", "ood_assignment", "expression", "pred_histgb_all"]]
    merged = source.merge(
        baseline, on=["source_row", "construct_id", "ood_assignment"], how="left", validate="one_to_one"
    )
    if len(merged) != len(source) or not np.allclose(merged["expression_value"], merged["expression"]):
        raise ValueError("Baseline alignment failed")
    predictions["histgb_all"] = merged["pred_histgb_all"].to_numpy(float)
    for name, values in predictions.items():
        if not np.isfinite(values).all():
            raise ValueError(f"Non-finite predictions: {name}")

    rng = np.random.default_rng(args.seed)
    all_metrics: dict[str, dict] = {}
    comparison_rows: list[dict] = []
    bootstrap_rows: list[dict] = []
    for partition in ["dev", "test", "sequence_ood"]:
        indices = np.flatnonzero(source["ood_assignment"].to_numpy() == partition)
        y = source["expression_value"].to_numpy(float)[indices]
        clusters = source["operational_protein_cluster"].to_numpy()[indices]
        part = {name: point_metrics(y, predictions[name][indices], clusters) for name in MODELS}
        for name in MODELS:
            for metric in ["row_spearman", "cluster_balanced_mse"]:
                observed = part[name][metric]
                expected = original["metrics"][partition][name][metric]
                if not np.isclose(observed, expected, rtol=0, atol=1e-12, equal_nan=True):
                    raise ValueError(f"Frozen metric mismatch: {partition}/{name}/{metric}: {observed} vs {expected}")
        all_metrics[partition] = part
        if partition == "dev":
            continue
        cluster_frame = pd.DataFrame({"cluster": clusters, "row": np.arange(len(indices))})
        groups = [g["row"].to_numpy() for _, g in cluster_frame.groupby("cluster", sort=True)]
        squared = {name: (predictions[name][indices] - y) ** 2 for name in MODELS}
        cluster_mse = {name: np.array([np.mean(squared[name][g]) for g in groups]) for name in MODELS}
        boot = {metric: [] for metric in METRICS}
        for _ in range(args.bootstrap):
            selected = rng.integers(0, len(groups), len(groups))
            rows = np.concatenate([groups[j] for j in selected])
            values = {
                "spearman": fast_spearman(y[rows], predictions["ribokinetic_all"][indices][rows])
                - fast_spearman(y[rows], predictions["histgb_all"][indices][rows]),
                "cluster_balanced_mse": float(np.mean(cluster_mse["ribokinetic_all"][selected]) - np.mean(cluster_mse["histgb_all"][selected])),
            }
            for metric in METRICS:
                boot[metric].append(values[metric])
        partition_rows = []
        for metric in METRICS:
            point_delta = part["ribokinetic_all"]["row_spearman" if metric == "spearman" else "cluster_balanced_mse"] - part["histgb_all"]["row_spearman" if metric == "spearman" else "cluster_balanced_mse"]
            samples = np.asarray(boot[metric], float)
            valid = samples[np.isfinite(samples)]
            benefit = samples if metric == "spearman" else -samples
            valid_benefit = benefit[np.isfinite(benefit)]
            pvalue = float(min(1.0, 2.0 * min(np.mean(valid_benefit <= 0), np.mean(valid_benefit >= 0)))) if len(valid_benefit) else 1.0
            row = {
                "partition": partition,
                "left": "ribokinetic_all",
                "right": "histgb_all",
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
                bootstrap_rows.append({"partition": partition, "left": "ribokinetic_all", "right": "histgb_all", "metric": metric, "replicate": replicate, "delta": value})
        adjusted = holm_adjust([row["sign_pvalue"] for row in partition_rows])
        for row, p_adj in zip(partition_rows, adjusted):
            row["holm_pvalue_within_partition"] = float(p_adj)
            comparison_rows.append(row)

    sequence_rows = [row for row in comparison_rows if row["partition"] == "sequence_ood"]
    diagnostic_favors_all = all(
        row["ci95_low"] is not None and row["ci95_high"] is not None and row["holm_pvalue_within_partition"] < 0.05
        and ((row["metric"] == "spearman" and row["ci95_low"] > 0) or (row["metric"] == "cluster_balanced_mse" and row["ci95_high"] < 0))
        for row in sequence_rows
    )
    summary = {
        "protocol": protocol["protocol_id"],
        "analysis_status": "retrospective_after_unpaired_metric_readout_not_preregistered",
        "status": "PASS_PENDING_INDEPENDENT_VERIFICATION",
        "scientific_scope": protocol["scientific_scope"],
        "model_fitting_performed": False,
        "model_selection_performed": False,
        "comparison": "ribokinetic_all minus histgb_all",
        "baseline_omission": "histgb_all was present in the frozen metrics but absent from the original paired comparisons.",
        "primary_diagnostic_partition": "sequence_ood",
        "diagnostic_favors_ribokinetic_all": bool(diagnostic_favors_all),
        "original_rk_g1_pass": bool(original["rk_g1_pass"]),
        "original_gate_modified": False,
        "expensive_generation_authorized": False,
        "sota_claimed": False,
        "fixed_protein_synonymous_mechanism_supported": False,
        "metrics": all_metrics,
        "comparisons": comparison_rows,
        "bootstrap": {"method": "operational_protein_cluster_resampling", "replicates": args.bootstrap, "seed": args.seed},
        "inputs": {
            "data_sha256": sha256(args.data),
            "all_predictions_sha256": sha256(all_prediction_path),
            "baseline_predictions_sha256": sha256(args.baseline_predictions),
            "original_summary": str(Path(args.original_summary).resolve()),
            "original_summary_sha256": sha256(args.original_summary),
            "protocol_sha256": sha256(args.protocol),
            "analysis_script_sha256": sha256(__file__),
        },
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "torch": torch.__version__,
        },
        "limitations": [
            "Retrospective diagnostic; it does not become a preregistered gate by using frozen predictions.",
            "Cross-protein nonsynonymous Boël prediction does not test fixed-protein synonymous design.",
            "No external method ranking, functional untouched evaluation, physical velocity measurement or generator result is provided.",
        ],
        "elapsed_seconds": time.time() - started,
    }
    pd.DataFrame(comparison_rows).to_csv(out / "paired_comparisons.csv", index=False)
    pd.DataFrame(bootstrap_rows).to_csv(out / "bootstrap_deltas.csv.gz", index=False, compression="gzip")
    metric_rows = []
    for partition, values in all_metrics.items():
        for name, metrics in values.items():
            metric_rows.append({"partition": partition, "model": name, **metrics})
    pd.DataFrame(metric_rows).to_csv(out / "metrics.csv", index=False)
    save_json(out / "comparison_summary.json", summary)
    print(json.dumps({
        "status": summary["status"],
        "diagnostic_favors_ribokinetic_all": diagnostic_favors_all,
        "original_rk_g1_pass": original["rk_g1_pass"],
        "output_dir": str(out),
        "elapsed_seconds": summary["elapsed_seconds"],
    }, indent=2))


if __name__ == "__main__":
    main()
