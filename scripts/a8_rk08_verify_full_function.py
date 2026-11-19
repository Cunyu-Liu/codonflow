#!/usr/bin/env python3
"""Independent verification of the full RK08 all/none comparison and retrains."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def metric_values(y, pred, clusters):
    y = np.asarray(y, float)
    pred = np.asarray(pred, float)
    squared = (pred - y) ** 2
    cb = pd.DataFrame({"cluster": clusters, "squared": squared}).groupby("cluster")["squared"].mean().mean()
    return {
        "mse": float(np.mean(squared)),
        "spearman": float(stats.spearmanr(y, pred).statistic),
        "cluster_balanced_mse": float(cb),
    }


def close(actual, expected, tolerance=1e-10):
    return actual is not None and expected is not None and abs(float(actual) - float(expected)) <= tolerance


def holm(values):
    order = np.argsort(values)
    out = np.zeros(len(values), float)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (len(values) - rank) * values[idx])
        out[idx] = min(1.0, running)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--all-dir", required=True)
    parser.add_argument("--none-dir", required=True)
    parser.add_argument("--all-retrain-dir", required=True)
    parser.add_argument("--none-retrain-dir", required=True)
    parser.add_argument("--comparison-dir", required=True)
    parser.add_argument("--baseline-predictions", required=True)
    parser.add_argument("--train-script", required=True)
    parser.add_argument("--all-config", required=True)
    parser.add_argument("--none-config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    checks = {}
    failures = []

    def check(name, condition):
        checks[name] = bool(condition)
        if not condition:
            failures.append(name)

    root = Path(args.comparison_dir)
    summary = json.loads((root / "comparison_summary.json").read_text())
    source = pd.read_csv(args.data, usecols=["source_row", "construct_id", "ood_assignment", "operational_protein_cluster", "expression_value", "cds"])
    source = source[source["ood_assignment"].isin(["train", "dev", "test", "sequence_ood"])].reset_index(drop=True)
    check("source_rows_6348", len(source) == 6348)
    check("source_hash_matches", sha256(args.data) == summary["inputs"]["data_sha256"])
    check("train_script_hash_matches", sha256(args.train_script) == summary["inputs"]["train_script_sha256"])
    check("all_config_hash_matches", json.loads(Path(args.all_dir, "run_summary.json").read_text())["hashes"]["config_sha256"] == sha256(args.all_config))
    check("none_config_hash_matches", json.loads(Path(args.none_dir, "run_summary.json").read_text())["hashes"]["config_sha256"] == sha256(args.none_config))

    expected_rows = {"train": 4019, "dev": 503, "test": 490, "sequence_ood": 1336}
    dirs = {
        "all": Path(args.all_dir),
        "none": Path(args.none_dir),
        "all_retrain": Path(args.all_retrain_dir),
        "none_retrain": Path(args.none_retrain_dir),
    }
    runs = {}
    predictions = {}
    for name, directory in dirs.items():
        run = json.loads((directory / "run_summary.json").read_text())
        runs[name] = run
        check(f"{name}_rows", run["rows"] == expected_rows)
        check(f"{name}_full_scope", run["scope"] == "FULL_DATA_MECHANISM_ABLATION_PENDING_PAIRED_COMPARISON")
        check(f"{name}_six_epochs", run["training"]["epochs_completed"] == 6)
        check(f"{name}_deterministic", run["environment"]["deterministic_algorithms"] is True)
        check(f"{name}_math_attention_only", run["environment"]["sdp_backends"] == {"flash": False, "mem_efficient": False, "math": True})
        check(f"{name}_data_hash", run["hashes"]["data_sha256"] == sha256(args.data))
        check(f"{name}_script_hash", run["hashes"]["script_sha256"] == sha256(args.train_script))
        history = json.loads((directory / "history.json").read_text())
        best = min(range(len(history)), key=lambda i: history[i]["dev"]["cluster_balanced_mse"])
        check(f"{name}_dev_only_best_epoch", run["selected_epoch"] == history[best]["epoch"])
        raw = pd.read_csv(directory / "predictions.csv").rename(columns={"record_id": "construct_id", "split": "ood_assignment", "cluster_id": "cluster", "prediction": "pred", "target": "prediction_target"})
        check(f"{name}_prediction_rows", len(raw) == 6348)
        check(f"{name}_prediction_keys_unique", not raw[["construct_id", "ood_assignment"]].duplicated().any())
        check(f"{name}_finite_intervals", np.isfinite(raw[["pred", "lower_95", "upper_95"]].to_numpy()).all())
        pred = source[["construct_id", "ood_assignment", "operational_protein_cluster", "expression_value"]].merge(
            raw[["construct_id", "ood_assignment", "cluster", "prediction_target", "pred", "lower_95", "upper_95"]],
            on=["construct_id", "ood_assignment"], how="left", validate="one_to_one"
        )
        predictions[name] = pred
        check(f"{name}_prediction_key_coverage", len(pred) == 6348 and pred["pred"].notna().all())
        check(f"{name}_cluster_match", pred["cluster"].tolist() == pred["operational_protein_cluster"].tolist())
        check(f"{name}_target_match", np.array_equal(pred["prediction_target"].to_numpy(), pred["expression_value"].to_numpy()))
        for partition in ["dev", "test", "sequence_ood"]:
            idx = np.flatnonzero(source["ood_assignment"].to_numpy() == partition)
            actual = metric_values(source["expression_value"].to_numpy()[idx], pred["pred"].to_numpy()[idx], source["operational_protein_cluster"].to_numpy()[idx])
            for metric, value in actual.items():
                check(f"{name}_{partition}_{metric}", close(value, run["metrics"][partition][metric]))

    for side in ["all", "none"]:
        primary = predictions[side]
        retrain = predictions[f"{side}_retrain"]
        difference = np.abs(primary["pred"].to_numpy() - retrain["pred"].to_numpy())
        check(f"{side}_retrain_predictions_bitwise", np.array_equal(primary["pred"].to_numpy(), retrain["pred"].to_numpy()))
        check(f"{side}_retrain_intervals_bitwise", np.array_equal(primary[["lower_95", "upper_95"]].to_numpy(), retrain[["lower_95", "upper_95"]].to_numpy()))
        check(f"{side}_retrain_checkpoint_hash", runs[side]["hashes"]["checkpoint_sha256"] == runs[f"{side}_retrain"]["hashes"]["checkpoint_sha256"])
        checks[f"{side}_retrain_max_abs_prediction"] = float(difference.max())

    check("all_none_same_parameter_count", summary["costs"]["ribokinetic_all"]["parameters"] == summary["costs"]["ribokinetic_none"]["parameters"])
    all_config = json.loads(Path(args.all_config).read_text())
    none_config = json.loads(Path(args.none_config).read_text())
    check("only_ablation_differs", {k: v for k, v in all_config.items() if k != "ablation"} == {k: v for k, v in none_config.items() if k != "ablation"})
    check("all_active_channels", runs["all"]["active_mechanisms"] == {"initiation": True, "velocity": True, "decay": True, "pair": True})
    check("none_inactive_channels", runs["none"]["active_mechanisms"] == {"initiation": False, "velocity": False, "decay": False, "pair": False})
    check("all_retrain_config_identical", runs["all"]["hashes"]["config_sha256"] == runs["all_retrain"]["hashes"]["config_sha256"])
    check("none_retrain_config_identical", runs["none"]["hashes"]["config_sha256"] == runs["none_retrain"]["hashes"]["config_sha256"])

    baseline = pd.read_csv(args.baseline_predictions)
    merged = source.merge(baseline[["source_row", "pred_ridge_all", "pred_ridge_gc", "pred_histgb_all"]], on="source_row", validate="one_to_one")
    model_predictions = {
        "ribokinetic_all": predictions["all"]["pred"].to_numpy(),
        "ribokinetic_none": predictions["none"]["pred"].to_numpy(),
        "ridge_all": merged["pred_ridge_all"].to_numpy(),
        "ridge_gc": merged["pred_ridge_gc"].to_numpy(),
        "histgb_all": merged["pred_histgb_all"].to_numpy(),
    }
    comparison_metrics = pd.read_csv(root / "metrics.csv")
    for partition in ["dev", "test", "sequence_ood"]:
        idx = np.flatnonzero(source["ood_assignment"].to_numpy() == partition)
        for model, pred in model_predictions.items():
            actual = metric_values(source["expression_value"].to_numpy()[idx], pred[idx], source["operational_protein_cluster"].to_numpy()[idx])
            row = comparison_metrics[(comparison_metrics["partition"] == partition) & (comparison_metrics["model"] == model)].iloc[0]
            check(f"comparison_{partition}_{model}_mse", close(actual["mse"], row["row_mse"]))
            check(f"comparison_{partition}_{model}_spearman", close(actual["spearman"], row["row_spearman"]))
            check(f"comparison_{partition}_{model}_cbmse", close(actual["cluster_balanced_mse"], row["cluster_balanced_mse"]))

    comparisons = pd.read_csv(root / "paired_comparisons.csv")
    boot = pd.read_csv(root / "bootstrap_deltas.csv.gz")
    check("comparison_row_count_12", len(comparisons) == 12)
    check("bootstrap_row_count_24000", len(boot) == 24000)
    for partition in ["test", "sequence_ood"]:
        part = comparisons[comparisons["partition"] == partition].reset_index(drop=True)
        adjusted = holm(part["sign_pvalue"].to_numpy())
        check(f"{partition}_holm_recomputed", np.allclose(adjusted, part["holm_pvalue_within_partition"].to_numpy()))
        for _, row in part.iterrows():
            selected = boot[(boot["partition"] == partition) & (boot["left"] == row["left"]) & (boot["right"] == row["right"]) & (boot["metric"] == row["metric"])]["delta"].to_numpy()
            valid = selected[np.isfinite(selected)]
            key = f"{partition}_{row['right']}_{row['metric']}"
            check(f"{key}_bootstrap_n", len(selected) == 2000)
            if len(valid):
                check(f"{key}_ci_low", close(np.quantile(valid, 0.025), row["ci95_low"], 1e-9))
                check(f"{key}_ci_high", close(np.quantile(valid, 0.975), row["ci95_high"], 1e-9))
                benefit = valid if row["metric"] == "spearman" else -valid
                pvalue = min(1.0, 2.0 * min(np.mean(benefit <= 0), np.mean(benefit >= 0)))
                check(f"{key}_sign_p", close(pvalue, row["sign_pvalue"], 1e-12))
            left_metrics = comparison_metrics[(comparison_metrics["partition"] == partition) & (comparison_metrics["model"] == row["left"])].iloc[0]
            right_metrics = comparison_metrics[(comparison_metrics["partition"] == partition) & (comparison_metrics["model"] == row["right"])].iloc[0]
            column = "row_spearman" if row["metric"] == "spearman" else "cluster_balanced_mse"
            check(f"{key}_point_delta", close(left_metrics[column] - right_metrics[column], row["point_delta"], 1e-9))

    gate_rows = [r for r in summary["comparisons"] if r["partition"] == "sequence_ood"]
    gate = all(
        r["ci95_low"] is not None and r["ci95_high"] is not None and r["holm_pvalue_within_partition"] < 0.05
        and ((r["metric"] == "spearman" and r["ci95_low"] > 0) or (r["metric"] == "cluster_balanced_mse" and r["ci95_high"] < 0))
        for r in gate_rows
    )
    check("rk_g1_gate_recomputed", gate == summary["rk_g1_pass"])
    check("generation_not_authorized", summary["expensive_generation_authorized"] is False)
    check("no_sota_claim", summary["sota_claimed"] is False)
    check("baseline_hash", sha256(args.baseline_predictions) == summary["inputs"]["baseline_predictions_sha256"])
    check("all_predictions_hash", sha256(Path(args.all_dir) / "predictions.csv") == summary["inputs"]["all_predictions_sha256"])
    check("none_predictions_hash", sha256(Path(args.none_dir) / "predictions.csv") == summary["inputs"]["none_predictions_sha256"])

    report = {
        "status": "PASS" if not failures else "FAIL",
        "checks_passed": sum(v is True for v in checks.values()),
        "checks_total": len([v for v in checks.values() if isinstance(v, bool)]),
        "failures": failures,
        "checks": checks,
        "rk_g1_pass": gate,
        "scientific_scope": summary["scientific_scope"],
    }
    Path(args.output).write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "checks_passed": report["checks_passed"], "checks_total": report["checks_total"], "failures": failures, "rk_g1_pass": gate}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
