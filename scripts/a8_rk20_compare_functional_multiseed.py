#!/usr/bin/env python3
"""Hierarchically bootstrapped RK20 multi-seed functional comparison.

The estimand is the mean of per-seed effects, never an unbudgeted prediction
ensemble. Clusters and seeds are resampled independently with replacement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Dict, List, Mapping

import numpy as np
import pandas as pd
from scipy import stats


MODELS = ["ribokinetic_all", "ribokinetic_none", "ridge_all", "ridge_gc", "histgb_all"]
METRICS = ["spearman", "cluster_balanced_mse"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def finite(value):
    return None if value is None or not np.isfinite(value) else float(value)


def fast_spearman(y: np.ndarray, prediction: np.ndarray) -> float:
    if np.std(y) <= 0 or np.std(prediction) <= 0:
        return np.nan
    return float(np.corrcoef(stats.rankdata(y), stats.rankdata(prediction))[0, 1])


def point_metrics(y: np.ndarray, prediction: np.ndarray, clusters: np.ndarray) -> dict:
    y = np.asarray(y, float)
    prediction = np.asarray(prediction, float)
    error = prediction - y
    frame = pd.DataFrame({"cluster": clusters, "squared_error": error ** 2})
    cluster_mse = frame.groupby("cluster")["squared_error"].mean()
    variance = float(np.sum((y - y.mean()) ** 2))
    return {
        "n_rows": int(len(y)),
        "n_clusters": int(frame["cluster"].nunique()),
        "row_mse": float(np.mean(error ** 2)),
        "row_r2": None if variance <= 0 else float(1.0 - np.sum(error ** 2) / variance),
        "row_spearman": finite(stats.spearmanr(y, prediction).statistic),
        "row_pearson": finite(stats.pearsonr(y, prediction).statistic),
        "cluster_balanced_mse": float(cluster_mse.mean()),
    }


def metric_value(metrics: Mapping, metric: str) -> float:
    return float(metrics["row_spearman" if metric == "spearman" else "cluster_balanced_mse"])


def holm_adjust(pvalues: List[float]) -> np.ndarray:
    values = np.asarray(pvalues, float)
    order = np.argsort(values)
    adjusted = np.empty(len(values), float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(values) - rank) * values[index])
        adjusted[index] = min(1.0, running)
    return adjusted


def hierarchical_bootstrap_deltas(
    y: np.ndarray,
    indices: np.ndarray,
    clusters: np.ndarray,
    predictions: Dict[int, Dict[str, np.ndarray]],
    seeds: List[int],
    models: List[str],
    comparisons: List[tuple],
    replicates: int,
    seed: int,
) -> Dict[tuple, List[float]]:
    """Return paired mean-per-seed deltas under cluster and seed resampling."""
    rng = np.random.default_rng(seed)
    cluster_frame = pd.DataFrame({"cluster": clusters, "row": np.arange(len(indices))})
    groups = [group["row"].to_numpy() for _, group in cluster_frame.groupby("cluster", sort=True)]
    cluster_mse = {
        (current_seed, model): np.array([
            np.mean((predictions[current_seed][model][indices][group] - y[group]) ** 2) for group in groups
        ])
        for current_seed in seeds for model in models
    }
    boot = {(left, right, metric): [] for left, right in comparisons for metric in METRICS}
    for _ in range(replicates):
        selected_clusters = rng.integers(0, len(groups), len(groups))
        selected_rows = np.concatenate([groups[index] for index in selected_clusters])
        selected_seeds = rng.integers(0, len(seeds), len(seeds))
        per_replicate_seed_deltas = {(left, right, metric): [] for left, right in comparisons for metric in METRICS}
        for seed_index in selected_seeds:
            current_seed = seeds[int(seed_index)]
            values = {}
            for model in models:
                values[(model, "spearman")] = fast_spearman(
                    y[selected_rows], predictions[current_seed][model][indices][selected_rows]
                )
                values[(model, "cluster_balanced_mse")] = float(np.mean(
                    cluster_mse[(current_seed, model)][selected_clusters]
                ))
            for left, right in comparisons:
                for metric in METRICS:
                    per_replicate_seed_deltas[(left, right, metric)].append(
                        values[(left, metric)] - values[(right, metric)]
                    )
        for key, values in per_replicate_seed_deltas.items():
            boot[key].append(float(np.mean(values)))
    return boot


def resolve(repo: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo / path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--execution", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repo-root", default="/home/codonflow-a8-rk")
    args = parser.parse_args()
    started = time.time()
    repo = Path(args.repo_root).resolve()
    protocol_path = Path(args.protocol).resolve()
    manifest_path = Path(args.manifest).resolve()
    execution_path = Path(args.execution).resolve()
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    if sha256(protocol_path) != manifest["protocol_sha256"] or manifest["protocol_sha256"] != execution["protocol_sha256"]:
        raise ValueError("protocol hash chain mismatch")
    if sha256(manifest_path) != execution["manifest_sha256"]:
        raise ValueError("manifest hash mismatch")
    if execution["status"] != "PASS_ALL_FROZEN_RUNS_COMPLETE_PENDING_COMPARISON":
        raise ValueError("execution is not complete")
    if sha256(Path(protocol["data"]["functional_csv"])) != protocol["data"]["functional_csv_sha256"]:
        raise ValueError("functional data changed")
    if sha256(Path(protocol["data"]["baseline_predictions"])) != protocol["data"]["baseline_predictions_sha256"]:
        raise ValueError("baseline predictions changed")
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    usecols = ["source_row", "construct_id", "ood_assignment", "operational_protein_cluster", "expression_value", "cds"]
    source = pd.read_csv(protocol["data"]["functional_csv"], usecols=usecols)
    source = source[source["ood_assignment"].isin(protocol["data"]["partitions"])].reset_index(drop=True)
    if len(source) != protocol["data"]["rows"]:
        raise ValueError("unexpected source row count")
    if source[["construct_id", "ood_assignment"]].duplicated().any() or source["cds"].isna().any():
        raise ValueError("source identity or CDS validation failed")
    if source["ood_assignment"].isin(["functional_untouched", "untouched"]).any():
        raise ValueError("forbidden untouched partition detected")

    seeds = [int(seed) for seed in protocol["seeds"]]
    comparisons = [tuple(item) for item in protocol["comparisons"]]
    predictions: Dict[int, Dict[str, np.ndarray]] = {seed: {} for seed in seeds}
    prediction_hashes = {}
    entries = {(int(item["seed"]), item["model"]): item for item in manifest["entries"]}
    if len(entries) != 2 * len(seeds):
        raise ValueError("manifest does not contain exactly all/none for every seed")

    def read_neural(path: Path, seed: int, model: str) -> np.ndarray:
        frame = pd.read_csv(path).rename(columns={
            "record_id": "construct_id", "split": "ood_assignment", "cluster_id": "cluster",
            "prediction": "pred", "target": "prediction_target",
        })
        if len(frame) != len(source) or frame[["construct_id", "ood_assignment"]].duplicated().any():
            raise ValueError(f"prediction identity failed: {model} seed {seed}")
        if not np.isfinite(frame[["pred", "lower_95", "upper_95"]].to_numpy()).all():
            raise ValueError(f"nonfinite prediction or interval: {model} seed {seed}")
        aligned = source[["construct_id", "ood_assignment", "operational_protein_cluster", "expression_value"]].merge(
            frame[["construct_id", "ood_assignment", "cluster", "prediction_target", "pred"]],
            on=["construct_id", "ood_assignment"], how="left", validate="one_to_one",
        )
        if len(aligned) != len(source) or aligned["cluster"].isna().any():
            raise ValueError(f"prediction alignment failed: {model} seed {seed}")
        if aligned["cluster"].tolist() != aligned["operational_protein_cluster"].tolist():
            raise ValueError(f"cluster mismatch: {model} seed {seed}")
        if not np.array_equal(aligned["prediction_target"].to_numpy(), aligned["expression_value"].to_numpy()):
            raise ValueError(f"target mismatch: {model} seed {seed}")
        return aligned["pred"].to_numpy(float)

    for (seed, model), entry in sorted(entries.items()):
        prediction_path = Path(entry["output_dir"]) / "predictions.csv"
        observed_hash = sha256(prediction_path)
        if entry["predictions_sha256"] is not None and observed_hash != entry["predictions_sha256"]:
            raise ValueError(f"prediction hash mismatch: {model} seed {seed}")
        predictions[seed][model] = read_neural(prediction_path, seed, model)
        prediction_hashes[f"{model}_seed{seed}"] = observed_hash

    baseline = pd.read_csv(protocol["data"]["baseline_predictions"])
    baseline = baseline[["source_row", "construct_id", "ood_assignment", "expression", "pred_ridge_all", "pred_ridge_gc", "pred_histgb_all"]]
    merged = source.merge(baseline, on=["source_row", "construct_id", "ood_assignment"], how="left", validate="one_to_one")
    if len(merged) != len(source) or not np.allclose(merged["expression_value"], merged["expression"]):
        raise ValueError("baseline alignment failed")
    baseline_arrays = {
        "ridge_all": merged["pred_ridge_all"].to_numpy(float),
        "ridge_gc": merged["pred_ridge_gc"].to_numpy(float),
        "histgb_all": merged["pred_histgb_all"].to_numpy(float),
    }
    for seed in seeds:
        for model, values in baseline_arrays.items():
            predictions[seed][model] = values.copy()
        for model in MODELS:
            if not np.isfinite(predictions[seed][model]).all():
                raise ValueError(f"nonfinite aligned values: {model} seed {seed}")

    all_metrics = {}
    metric_rows = []
    comparison_rows = []
    per_seed_comparison_rows = []
    bootstrap_rows = []
    for partition in ("dev", "test", "sequence_ood"):
        indices = np.flatnonzero(source["ood_assignment"].to_numpy() == partition)
        y = source["expression_value"].to_numpy(float)[indices]
        clusters = source["operational_protein_cluster"].to_numpy()[indices]
        partition_metrics = {}
        for seed in seeds:
            seed_metrics = {}
            for model in MODELS:
                values = point_metrics(y, predictions[seed][model][indices], clusters)
                seed_metrics[model] = values
                metric_rows.append({"partition": partition, "seed": seed, "model": model, **values})
            partition_metrics[str(seed)] = seed_metrics
            for left, right in comparisons:
                for metric in METRICS:
                    per_seed_comparison_rows.append({
                        "partition": partition,
                        "seed": seed,
                        "left": left,
                        "right": right,
                        "metric": metric,
                        "delta": metric_value(seed_metrics[left], metric) - metric_value(seed_metrics[right], metric),
                    })
        mean_metrics = {}
        for model in MODELS:
            mean_metrics[model] = {
                key: float(np.mean([partition_metrics[str(seed)][model][key] for seed in seeds]))
                for key in ("row_mse", "row_r2", "row_spearman", "row_pearson", "cluster_balanced_mse")
            }
            mean_metrics[model]["seed_sd_cluster_balanced_mse"] = float(np.std([
                partition_metrics[str(seed)][model]["cluster_balanced_mse"] for seed in seeds
            ], ddof=1))
            mean_metrics[model]["seed_sd_row_spearman"] = float(np.std([
                partition_metrics[str(seed)][model]["row_spearman"] for seed in seeds
            ], ddof=1))
        all_metrics[partition] = {"per_seed": partition_metrics, "mean_across_seeds": mean_metrics}
        if partition == "dev":
            continue

        boot = hierarchical_bootstrap_deltas(
            y=y,
            indices=indices,
            clusters=clusters,
            predictions=predictions,
            seeds=seeds,
            models=MODELS,
            comparisons=comparisons,
            replicates=int(protocol["statistics"]["replicates"]),
            seed=int(protocol["statistics"]["seed"]),
        )
        replicates = int(protocol["statistics"]["replicates"])

        partition_rows = []
        for left, right in comparisons:
            for metric in METRICS:
                point_delta = float(np.mean([
                    metric_value(partition_metrics[str(seed)][left], metric) - metric_value(partition_metrics[str(seed)][right], metric)
                    for seed in seeds
                ]))
                samples = np.asarray(boot[(left, right, metric)], float)
                valid = samples[np.isfinite(samples)]
                benefit = samples if metric == "spearman" else -samples
                valid_benefit = benefit[np.isfinite(benefit)]
                pvalue = float(min(1.0, 2.0 * min(np.mean(valid_benefit <= 0), np.mean(valid_benefit >= 0)))) if len(valid_benefit) else 1.0
                row = {
                    "partition": partition,
                    "left": left,
                    "right": right,
                    "metric": metric,
                    "point_delta_mean_per_seed": finite(point_delta),
                    "ci95_low": finite(np.quantile(valid, 0.025)) if len(valid) else None,
                    "ci95_high": finite(np.quantile(valid, 0.975)) if len(valid) else None,
                    "sign_pvalue": pvalue,
                    "bootstrap_valid": int(len(valid)),
                    "bootstrap_requested": replicates,
                }
                partition_rows.append(row)
                for replicate, value in enumerate(samples):
                    bootstrap_rows.append({
                        "partition": partition, "left": left, "right": right, "metric": metric,
                        "replicate": replicate, "mean_per_seed_delta": value,
                    })
        adjusted = holm_adjust([row["sign_pvalue"] for row in partition_rows])
        for row, adjusted_p in zip(partition_rows, adjusted):
            row["holm_pvalue_within_partition"] = float(adjusted_p)
            row["direction_pass"] = bool(
                (row["metric"] == "spearman" and row["ci95_low"] is not None and row["ci95_low"] > 0)
                or (row["metric"] == "cluster_balanced_mse" and row["ci95_high"] is not None and row["ci95_high"] < 0)
            )
            comparison_rows.append(row)

    gate_rows = [row for row in comparison_rows if row["partition"] == protocol["data"]["primary_partition"]]
    robustness_pass = bool(len(gate_rows) == 8 and all(
        row["direction_pass"] and row["holm_pvalue_within_partition"] < 0.05 for row in gate_rows
    ))
    costs = []
    for run in execution["runs"]:
        if run["execution"] == "reused_frozen_output":
            continue
        costs.append({
            "seed": run["seed"], "model": run["model"], "execution": run["execution"],
            "training_seconds": run.get("training_seconds"),
            "selected_epoch_by_dev_only": run.get("selected_epoch_by_dev_only"),
            "forward_passes": run.get("forward_passes"),
            "checkpoint_sha256": run.get("checkpoint_sha256"),
        })
    summary = {
        "schema": "a8-rk20-functional-multiseed-comparison-v1",
        "status": "PASS_PENDING_INDEPENDENT_VERIFICATION",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sha256(protocol_path),
        "scientific_scope": protocol["scope"],
        "selection": "All four seeds retained; checkpoint selection used dev only; no test/OOD seed, arm, checkpoint, or model selection.",
        "primary_endpoint": protocol["endpoints"]["primary"],
        "secondary_endpoint": protocol["endpoints"]["secondary"],
        "estimand": protocol["statistics"]["estimand"],
        "prediction_ensemble_evaluated": False,
        "functional_robustness_pass": robustness_pass,
        "rk_g1_pass": False,
        "expensive_generation_authorized": False,
        "functional_untouched_evaluated": False,
        "sota_claimed": False,
        "metrics": all_metrics,
        "comparisons": comparison_rows,
        "per_seed_comparisons": per_seed_comparison_rows,
        "costs": {
            "new_neural_runs": costs,
            "total_new_training_seconds": float(sum(item["training_seconds"] for item in costs)),
            "baseline_predictions": "reused_frozen_not_retrained",
            "timing_scope": protocol["cost_contract"]["gpu_cotenancy"],
        },
        "bootstrap": protocol["statistics"],
        "inputs": {
            "data_sha256": protocol["data"]["functional_csv_sha256"],
            "baseline_predictions_sha256": protocol["data"]["baseline_predictions_sha256"],
            "manifest_sha256": sha256(manifest_path),
            "execution_sha256": sha256(execution_path),
            "comparison_script_sha256": sha256(Path(__file__).resolve()),
            "predictions": prediction_hashes,
        },
        "limitations": [
            "The test and sequence-OOD partitions were already observed in RK08; this is robustness evidence, not untouched confirmation.",
            "Cross-protein nonsynonymous Boel prediction does not establish fixed-protein synonymous mechanism or function improvement.",
            "Four-seed hierarchical bootstrap quantifies variability but does not replace an independent held-out study.",
            "A positive functional result alone would not override the failed velocity or fixed-GFP structure mechanisms.",
            "No CodonFlow-RK generator, time-matched SOTA, wet-lab, or external dense-trajectory result is provided."
        ],
        "elapsed_seconds": time.time() - started,
    }
    pd.DataFrame(metric_rows).to_csv(out / "metrics.csv", index=False)
    pd.DataFrame(comparison_rows).to_csv(out / "paired_comparisons.csv", index=False)
    pd.DataFrame(per_seed_comparison_rows).to_csv(out / "per_seed_comparisons.csv", index=False)
    pd.DataFrame(bootstrap_rows).to_csv(out / "bootstrap_deltas.csv.gz", index=False, compression="gzip")
    save_json(out / "comparison_summary.json", summary)
    print(json.dumps({
        "status": summary["status"], "functional_robustness_pass": robustness_pass,
        "rk_g1_pass": False, "output_dir": str(out), "elapsed_seconds": summary["elapsed_seconds"],
    }, indent=2))
    if not robustness_pass:
        print("RK20_FUNCTIONAL_ROBUSTNESS_NOT_PASSED: negative or uncertain results retained; no generator launch.")


if __name__ == "__main__":
    main()
