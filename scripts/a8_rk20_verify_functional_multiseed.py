#!/usr/bin/env python3
"""Independent read-only verification of the frozen RK20 comparison artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


MODELS = ["ribokinetic_all", "ribokinetic_none", "ridge_all", "ridge_gc", "histgb_all"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def close(left, right, tolerance=1e-10) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)


def metrics(y, prediction, clusters):
    error = np.asarray(prediction, float) - np.asarray(y, float)
    frame = pd.DataFrame({"cluster": clusters, "se": error ** 2})
    per_cluster = frame.groupby("cluster")["se"].mean()
    variance = np.sum((y - np.mean(y)) ** 2)
    return {
        "n_rows": int(len(y)),
        "n_clusters": int(frame["cluster"].nunique()),
        "row_mse": float(np.mean(error ** 2)),
        "row_r2": None if variance <= 0 else float(1.0 - np.sum(error ** 2) / variance),
        "row_spearman": float(stats.spearmanr(y, prediction).statistic),
        "row_pearson": float(stats.pearsonr(y, prediction).statistic),
        "cluster_balanced_mse": float(per_cluster.mean()),
    }


def holm(values):
    p = np.asarray(values, float)
    order = np.argsort(p)
    result = np.empty(len(p), float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p) - rank) * p[index])
        result[index] = min(1.0, running)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--preparation", required=True)
    parser.add_argument("--execution", required=True)
    parser.add_argument("--comparison-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repo-root", default="/home/codonflow-a8-rk")
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    protocol_path = Path(args.protocol).resolve()
    preparation_path = Path(args.preparation).resolve()
    execution_path = Path(args.execution).resolve()
    comparison_dir = Path(args.comparison_dir).resolve()
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    summary = json.loads((comparison_dir / "comparison_summary.json").read_text(encoding="utf-8"))
    metric_table = pd.read_csv(comparison_dir / "metrics.csv")
    paired = pd.read_csv(comparison_dir / "paired_comparisons.csv")
    per_seed_pairs = pd.read_csv(comparison_dir / "per_seed_comparisons.csv")
    bootstrap = pd.read_csv(comparison_dir / "bootstrap_deltas.csv.gz")
    checks = []

    def check(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("protocol_schema", protocol["schema"] == "a8-rk20-functional-multiseed-protocol-v1")
    check("protocol_hash_preparation", sha256(protocol_path) == preparation["protocol_sha256"])
    check("protocol_hash_execution", preparation["protocol_sha256"] == execution["protocol_sha256"])
    check("manifest_hash_execution", sha256(preparation_path) == execution["manifest_sha256"])
    check("execution_complete", execution["status"] == "PASS_ALL_FROZEN_RUNS_COMPLETE_PENDING_COMPARISON")
    check("comparison_pending_independent", summary["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION")
    check("comparison_protocol_hash", summary["protocol_sha256"] == sha256(protocol_path))
    check("comparison_manifest_hash", summary["inputs"]["manifest_sha256"] == sha256(preparation_path))
    check("comparison_execution_hash", summary["inputs"]["execution_sha256"] == sha256(execution_path))
    check("comparison_script_hash", summary["inputs"]["comparison_script_sha256"] == sha256(repo / "scripts" / "a8_rk20_compare_functional_multiseed.py"))
    check("functional_data_hash", sha256(Path(protocol["data"]["functional_csv"])) == protocol["data"]["functional_csv_sha256"])
    check("baseline_hash", sha256(Path(protocol["data"]["baseline_predictions"])) == protocol["data"]["baseline_predictions_sha256"])
    check("train_script_hash", sha256(repo / protocol["training_contract"]["script"]) == protocol["training_contract"]["script_sha256"])
    check("four_fixed_seeds", protocol["seeds"] == [20261119, 20261120, 20261121, 20261122])
    check("all_eight_primary_tests", len(protocol["comparisons"]) == 4 and protocol["statistics"]["replicates"] == 2000)
    check("global_gate_remains_closed", summary["rk_g1_pass"] is False and summary["expensive_generation_authorized"] is False)
    check("untouched_not_evaluated", summary["functional_untouched_evaluated"] is False and execution["functional_untouched_evaluated"] is False)
    check("no_ensemble", summary["prediction_ensemble_evaluated"] is False)
    check("no_sota", summary["sota_claimed"] is False)

    source = pd.read_csv(protocol["data"]["functional_csv"], usecols=[
        "source_row", "construct_id", "ood_assignment", "operational_protein_cluster", "expression_value", "cds",
    ])
    source = source[source["ood_assignment"].isin(protocol["data"]["partitions"])].reset_index(drop=True)
    check("source_rows", len(source) == 6348, len(source))
    check("source_unique", not source[["construct_id", "ood_assignment"]].duplicated().any())
    check("no_untouched_rows", not source["ood_assignment"].isin(["untouched", "functional_untouched"]).any())

    baseline = pd.read_csv(protocol["data"]["baseline_predictions"])
    merged = source.merge(
        baseline[["source_row", "construct_id", "ood_assignment", "expression", "pred_ridge_all", "pred_ridge_gc", "pred_histgb_all"]],
        on=["source_row", "construct_id", "ood_assignment"], how="left", validate="one_to_one",
    )
    check("baseline_alignment", len(merged) == len(source) and np.allclose(merged["expression_value"], merged["expression"]))
    baseline_arrays = {
        "ridge_all": merged["pred_ridge_all"].to_numpy(float),
        "ridge_gc": merged["pred_ridge_gc"].to_numpy(float),
        "histgb_all": merged["pred_histgb_all"].to_numpy(float),
    }

    recomputed = {}
    for entry in preparation["entries"]:
        seed = int(entry["seed"])
        model = entry["model"]
        prediction_path = Path(entry["output_dir"]) / "predictions.csv"
        observed_prediction_hash = sha256(prediction_path)
        check(f"prediction_hash_{model}_{seed}", observed_prediction_hash == summary["inputs"]["predictions"][f"{model}_seed{seed}"])
        frame = pd.read_csv(prediction_path).rename(columns={
            "record_id": "construct_id", "split": "ood_assignment", "cluster_id": "cluster",
            "prediction": "pred", "target": "prediction_target",
        })
        aligned = source[["construct_id", "ood_assignment", "operational_protein_cluster", "expression_value"]].merge(
            frame[["construct_id", "ood_assignment", "cluster", "prediction_target", "pred"]],
            on=["construct_id", "ood_assignment"], how="left", validate="one_to_one",
        )
        check(f"prediction_rows_{model}_{seed}", len(aligned) == len(source) and aligned["pred"].notna().all())
        check(f"prediction_clusters_{model}_{seed}", aligned["cluster"].tolist() == aligned["operational_protein_cluster"].tolist())
        check(f"prediction_targets_{model}_{seed}", np.array_equal(aligned["prediction_target"], aligned["expression_value"]))
        recomputed[(seed, model)] = aligned["pred"].to_numpy(float)
        if seed != protocol["existing_seed"]:
            config = json.loads(Path(entry["config"]).read_text(encoding="utf-8"))
            base = json.loads((repo / protocol["base_configs"][entry["arm"]]).read_text(encoding="utf-8"))
            config["training"].pop("seed")
            base["training"].pop("seed")
            check(f"only_seed_changed_{model}_{seed}", config == base)

    for seed in protocol["seeds"]:
        for model, values in baseline_arrays.items():
            recomputed[(seed, model)] = values
    check("metric_row_count", len(metric_table) == 3 * 4 * 5, len(metric_table))
    check("per_seed_comparison_count", len(per_seed_pairs) == 3 * 4 * 4 * 2, len(per_seed_pairs))
    check("paired_comparison_count", len(paired) == 2 * 4 * 2, len(paired))
    check("bootstrap_row_count", len(bootstrap) == 2 * 4 * 2 * 2000, len(bootstrap))

    all_close = True
    mean_close = True
    per_seed_delta_close = True
    for partition in ("dev", "test", "sequence_ood"):
        indices = np.flatnonzero(source["ood_assignment"].to_numpy() == partition)
        y = source["expression_value"].to_numpy(float)[indices]
        clusters = source["operational_protein_cluster"].to_numpy()[indices]
        for seed in protocol["seeds"]:
            for model in MODELS:
                observed = metrics(y, recomputed[(seed, model)][indices], clusters)
                stored = summary["metrics"][partition]["per_seed"][str(seed)][model]
                for key, value in observed.items():
                    if key in ("n_rows", "n_clusters"):
                        all_close = all_close and int(stored[key]) == value
                    else:
                        all_close = all_close and close(stored[key], value)
                for left, right in protocol["comparisons"]:
                    for metric_name in ("spearman", "cluster_balanced_mse"):
                        key = "row_spearman" if metric_name == "spearman" else metric_name
                        expected = observed[key] - metrics(y, recomputed[(seed, right)][indices], clusters)[key] if left == model else None
                        if expected is not None:
                            row = per_seed_pairs[
                                (per_seed_pairs["partition"] == partition) & (per_seed_pairs["seed"] == seed)
                                & (per_seed_pairs["left"] == left) & (per_seed_pairs["right"] == right)
                                & (per_seed_pairs["metric"] == metric_name)
                            ]
                            per_seed_delta_close = per_seed_delta_close and len(row) == 1 and close(row.iloc[0]["delta"], expected)
        for model in MODELS:
            stored_mean = summary["metrics"][partition]["mean_across_seeds"][model]
            for key in ("row_mse", "row_r2", "row_spearman", "row_pearson", "cluster_balanced_mse"):
                expected = float(np.mean([
                    summary["metrics"][partition]["per_seed"][str(seed)][model][key] for seed in protocol["seeds"]
                ]))
                mean_close = mean_close and close(stored_mean[key], expected)
            for key, source_key in (("seed_sd_cluster_balanced_mse", "cluster_balanced_mse"), ("seed_sd_row_spearman", "row_spearman")):
                expected = float(np.std([
                    summary["metrics"][partition]["per_seed"][str(seed)][model][source_key] for seed in protocol["seeds"]
                ], ddof=1))
                mean_close = mean_close and close(stored_mean[key], expected)
    check("independent_point_metrics", all_close)
    check("independent_seed_means_and_sd", mean_close)
    check("independent_per_seed_deltas", per_seed_delta_close)

    intervals_close = True
    point_delta_close = True
    holm_close = True
    direction_close = True
    for partition in ("test", "sequence_ood"):
        subset = paired[paired["partition"] == partition].reset_index(drop=True)
        adjusted = holm(subset["sign_pvalue"].to_numpy(float))
        for index, row in subset.iterrows():
            samples = bootstrap[
                (bootstrap["partition"] == partition) & (bootstrap["left"] == row["left"])
                & (bootstrap["right"] == row["right"]) & (bootstrap["metric"] == row["metric"])
            ]["mean_per_seed_delta"].to_numpy(float)
            intervals_close = intervals_close and len(samples) == 2000
            intervals_close = intervals_close and close(row["ci95_low"], np.quantile(samples, 0.025))
            intervals_close = intervals_close and close(row["ci95_high"], np.quantile(samples, 0.975))
            benefit = samples if row["metric"] == "spearman" else -samples
            pvalue = min(1.0, 2.0 * min(np.mean(benefit <= 0), np.mean(benefit >= 0)))
            intervals_close = intervals_close and close(row["sign_pvalue"], pvalue)
            holm_close = holm_close and close(row["holm_pvalue_within_partition"], adjusted[index])
            expected_delta = float(np.mean([
                summary["metrics"][partition]["per_seed"][str(seed)][row["left"]]["row_spearman" if row["metric"] == "spearman" else "cluster_balanced_mse"]
                - summary["metrics"][partition]["per_seed"][str(seed)][row["right"]]["row_spearman" if row["metric"] == "spearman" else "cluster_balanced_mse"]
                for seed in protocol["seeds"]
            ]))
            point_delta_close = point_delta_close and close(row["point_delta_mean_per_seed"], expected_delta)
            expected_direction = (row["ci95_low"] > 0) if row["metric"] == "spearman" else (row["ci95_high"] < 0)
            direction_close = direction_close and bool(row["direction_pass"]) == bool(expected_direction)
    check("independent_bootstrap_intervals_and_pvalues", intervals_close)
    check("independent_mean_point_deltas", point_delta_close)
    check("independent_holm", holm_close)
    check("independent_direction_flags", direction_close)

    gate = paired[paired["partition"] == "sequence_ood"]
    expected_pass = bool(len(gate) == 8 and ((gate["direction_pass"]) & (gate["holm_pvalue_within_partition"] < 0.05)).all())
    check("independent_functional_gate", summary["functional_robustness_pass"] == expected_pass, expected_pass)
    new_costs = summary["costs"]["new_neural_runs"]
    check("six_new_cost_records", len(new_costs) == 6, len(new_costs))
    check("total_new_cost", close(summary["costs"]["total_new_training_seconds"], sum(item["training_seconds"] for item in new_costs)))
    check("baseline_reuse_disclosed", summary["costs"]["baseline_predictions"] == "reused_frozen_not_retrained")
    check("no_complete_experiment_claim", any("not untouched confirmation" in item for item in summary["limitations"]))

    passed = sum(item["pass"] for item in checks)
    report = {
        "schema": "a8-rk20-functional-multiseed-independent-v1",
        "status": "PASS_INDEPENDENT_VERIFICATION" if passed == len(checks) else "FAIL_INDEPENDENT_VERIFICATION",
        "checks_passed": passed,
        "checks_total": len(checks),
        "checks": checks,
        "functional_robustness_pass": expected_pass,
        "rk_g1_pass": False,
        "expensive_generation_authorized": False,
        "functional_untouched_evaluated": False,
        "comparison_summary_sha256": sha256(comparison_dir / "comparison_summary.json"),
        "metrics_sha256": sha256(comparison_dir / "metrics.csv"),
        "paired_comparisons_sha256": sha256(comparison_dir / "paired_comparisons.csv"),
        "bootstrap_sha256": sha256(comparison_dir / "bootstrap_deltas.csv.gz"),
    }
    output = Path(args.output)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "functional_robustness_pass": expected_pass}, indent=2))
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
