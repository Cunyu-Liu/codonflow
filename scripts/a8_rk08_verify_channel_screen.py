#!/usr/bin/env python3
"""Independent recomputation of the RK08 channel screen and paired evaluation."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from scipy import stats


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def active_map(arm: str) -> dict[str, bool]:
    names = ("initiation", "velocity", "decay", "pair")
    if arm == "all":
        return {name: True for name in names}
    if arm == "none":
        return {name: False for name in names}
    if arm.endswith("_only") and arm[:-5] in names:
        return {name: name == arm[:-5] for name in names}
    if arm.startswith("no_") and arm[3:] in names:
        return {name: name != arm[3:] for name in names}
    raise ValueError(arm)


def cluster_mse_from_rows(rows: list[dict], partition: str) -> tuple[float, int, int, set[str]]:
    grouped = {}
    splits = set()
    count = 0
    for row in rows:
        splits.add(row["split"])
        if row["split"] != partition:
            continue
        value = (float(row["prediction"]) - float(row["target"])) ** 2
        assert math.isfinite(value)
        grouped.setdefault(row["cluster_id"], []).append(value)
        count += 1
    per_cluster = [sum(values) / len(values) for _, values in sorted(grouped.items())]
    return sum(per_cluster) / len(per_cluster), count, len(per_cluster), splits


def point_metrics(y, prediction, clusters) -> dict:
    y = np.asarray(y, float)
    prediction = np.asarray(prediction, float)
    error = prediction - y
    frame = pd.DataFrame({"cluster": clusters, "error2": error * error})
    per_cluster = frame.groupby("cluster")["error2"].mean().to_numpy()
    variance = float(np.sum((y - y.mean()) ** 2))
    return {
        "n_rows": int(len(y)),
        "n_clusters": int(len(per_cluster)),
        "row_mse": float(np.mean(error * error)),
        "row_r2": None if variance == 0 else float(1 - np.sum(error * error) / variance),
        "row_spearman": float(stats.spearmanr(y, prediction).statistic),
        "row_pearson": float(stats.pearsonr(y, prediction).statistic),
        "cluster_balanced_mse": float(np.mean(per_cluster)),
    }


def rank_correlation(y, prediction) -> float:
    if np.std(y) <= 0 or np.std(prediction) <= 0:
        return float("nan")
    return float(np.corrcoef(stats.rankdata(y), stats.rankdata(prediction))[0, 1])


def holm(pvalues) -> np.ndarray:
    pvalues = np.asarray(pvalues, float)
    result = np.empty(len(pvalues), float)
    running = 0.0
    for rank, index in enumerate(np.argsort(pvalues)):
        running = max(running, (len(pvalues) - rank) * pvalues[index])
        result[index] = min(1.0, running)
    return result


def state_equal(left: dict, right: dict) -> bool:
    return left.keys() == right.keys() and all(torch.equal(left[key], right[key]) for key in left)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    protocol = json.loads(args.protocol.read_text())
    preparation = json.loads(args.preparation.read_text())
    selection = json.loads(args.selection.read_text())
    evaluation = json.loads(args.evaluation.read_text())
    checks = []
    failures = []
    max_delta = 0.0

    def check(name: str, condition: bool, detail=None) -> None:
        passed = bool(condition)
        checks.append({"check_id": name, "passed": passed, "detail": detail})
        if not passed:
            failures.append(name)

    def close(name: str, left, right, tolerance=1e-12) -> None:
        nonlocal max_delta
        if left is None or right is None:
            check(name, left is right, {"left": left, "right": right})
            return
        delta = abs(float(left) - float(right))
        max_delta = max(max_delta, delta)
        check(name, delta <= tolerance, {"delta": delta, "tolerance": tolerance})

    check("protocol_frozen", protocol["status"] == "FROZEN_BEFORE_CHANNEL_TRAINING_AND_TEST_READOUT")
    check("preparation_pass", preparation["status"] == "PASS_CHANNEL_SCREEN_PREPARATION")
    check("selection_pass", selection["status"] == "PASS_CHANNEL_SELECTION_FROZEN")
    check("evaluation_pending_independent", evaluation["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION")
    check("protocol_hash_preparation", preparation["protocol_sha256"] == sha256(args.protocol))
    check("protocol_hash_selection", selection["protocol_sha256"] == sha256(args.protocol))
    check("protocol_hash_evaluation", evaluation["protocol_sha256"] == sha256(args.protocol))
    check("preparation_hash_selection", selection["preparation_sha256"] == sha256(args.preparation))
    check("preparation_hash_evaluation", evaluation["preparation_sha256"] == sha256(args.preparation))
    check("selection_hash_evaluation", evaluation["selection_sha256"] == sha256(args.selection))
    check("evaluation_script_hash", evaluation["inputs"]["evaluation_script_sha256"] == sha256(root / "scripts/a8_rk08_eval_channel_screen.py"))
    arms = protocol["arms_in_tie_break_order"]
    check("ten_unique_arms", len(arms) == len(set(arms)) == 10)
    screen_root = Path(protocol["output_root"]) / "screen"
    dev_values = {}
    for arm in arms:
        config_path = root / preparation["config_hashes"][arm]["path"]
        config = json.loads(config_path.read_text())
        check(f"config_hash:{arm}", sha256(config_path) == preparation["config_hashes"][arm]["sha256"])
        check(f"config_screen_only:{arm}", config["include_splits"] == ["train", "dev"])
        check(f"config_arm:{arm}", config["ablation"] == arm)
        run_dir = screen_root / arm
        run = json.loads((run_dir / "run_summary.json").read_text())
        check(f"run_hash:{arm}", sha256(run_dir / "run_summary.json") == selection["artifact_hashes"][arm]["run_summary"])
        check(f"prediction_hash:{arm}", sha256(run_dir / "predictions.csv") == selection["artifact_hashes"][arm]["predictions"])
        check(f"checkpoint_hash:{arm}", sha256(run_dir / "best.pt") == selection["artifact_hashes"][arm]["checkpoint"])
        check(f"active:{arm}", run["active_mechanisms"] == active_map(arm))
        check(f"rows:{arm}", run["rows"] == {"train": 4019, "dev": 503})
        check(f"metric_partitions:{arm}", set(run["metrics"]) == {"train", "dev"})
        with (run_dir / "predictions.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        dev_value, dev_n, dev_clusters, splits = cluster_mse_from_rows(rows, "dev")
        train_value, train_n, _, _ = cluster_mse_from_rows(rows, "train")
        check(f"no_test_ood_screen:{arm}", splits == {"train", "dev"})
        check(f"dev_rows:{arm}", dev_n == 503 and dev_clusters == 447)
        check(f"train_rows:{arm}", train_n == 4019)
        close(f"dev_cb_mse:{arm}", dev_value, run["metrics"]["dev"]["cluster_balanced_mse"])
        dev_values[arm] = dev_value
        checkpoint = torch.load(run_dir / "best.pt", map_location="cpu", weights_only=False)
        check(f"parameters:{arm}", sum(t.numel() for t in checkpoint["state_dict"].values()) == 4997)
        check(f"not_generator:{arm}", checkpoint["scope"] == "SUPERVISED_RK08_NOT_GENERATOR")
    selected_expected = min(arms, key=lambda arm: (dev_values[arm], arms.index(arm)))
    check("selected_arm_recomputed", selection["selected_arm"] == selected_expected, {"expected": selected_expected, "reported": selection["selected_arm"]})
    close("selected_dev_recomputed", dev_values[selected_expected], selection["selected_dev_cluster_balanced_mse"])
    check("evaluation_selected_arm", evaluation["selected_arm"] == selected_expected)
    for arm in ("all", "none"):
        prior_path = Path(protocol["prior_checkpoint_equivalence"][arm]["path"])
        prior = torch.load(prior_path, map_location="cpu", weights_only=False)
        current = torch.load(screen_root / arm / "best.pt", map_location="cpu", weights_only=False)
        check(f"prior_state_equal:{arm}", state_equal(prior["state_dict"], current["state_dict"]))
        check(f"selection_prior_flag:{arm}", selection["prior_checkpoint_equivalence"][arm]["state_dict_bitwise_equal"] is True)

    selected_arm = selected_expected
    eval_root = Path(protocol["output_root"]) / "evaluation"
    eval_arms = [selected_arm] if selected_arm == "none" else [selected_arm, "none"]
    for arm in eval_arms:
        screen_checkpoint = torch.load(screen_root / arm / "best.pt", map_location="cpu", weights_only=False)
        eval_checkpoint = torch.load(eval_root / arm / "best.pt", map_location="cpu", weights_only=False)
        check(f"eval_screen_state_equal:{arm}", state_equal(screen_checkpoint["state_dict"], eval_checkpoint["state_dict"]))
        with (screen_root / arm / "predictions.csv").open(newline="") as handle:
            screen_rows = [row for row in csv.DictReader(handle) if row["split"] in {"train", "dev"}]
        with (eval_root / arm / "predictions.csv").open(newline="") as handle:
            all_eval_rows = list(csv.DictReader(handle))
        eval_rows = [row for row in all_eval_rows if row["split"] in {"train", "dev"}]
        check(f"eval_train_dev_exact:{arm}", screen_rows == eval_rows)
        check(f"eval_no_untouched:{arm}", all(row["split"] in {"train", "dev", "test", "sequence_ood"} for row in all_eval_rows))
        check(f"eval_prediction_hash:{arm}", sha256(eval_root / arm / "predictions.csv") == evaluation["evaluation_runs"][arm]["predictions_sha256"])

    data_path = Path(protocol["data"]["path"])
    check("data_hash", sha256(data_path) == protocol["data"]["sha256"])
    baseline_path = Path(protocol["baseline_predictions"]["path"])
    check("baseline_hash", sha256(baseline_path) == protocol["baseline_predictions"]["sha256"])
    source = pd.read_csv(data_path, usecols=["source_row", "construct_id", "ood_assignment", "operational_protein_cluster", "expression_value"])
    source = source[source["ood_assignment"].isin(["train", "dev", "test", "sequence_ood"])].reset_index(drop=True)
    check("source_6348", len(source) == 6348)
    check("source_no_untouched", "functional_untouched" not in set(source["ood_assignment"]))

    def model_array(arm: str) -> np.ndarray:
        frame = pd.read_csv(eval_root / arm / "predictions.csv").rename(columns={"record_id": "construct_id", "split": "ood_assignment", "prediction": "pred"})
        aligned = source[["construct_id", "ood_assignment"]].merge(frame[["construct_id", "ood_assignment", "pred"]], on=["construct_id", "ood_assignment"], validate="one_to_one")
        check(f"aligned_rows:{arm}", len(aligned) == 6348)
        return aligned["pred"].to_numpy(float)

    predictions = {"ribokinetic_selected": model_array(selected_arm)}
    predictions["ribokinetic_none"] = predictions["ribokinetic_selected"].copy() if selected_arm == "none" else model_array("none")
    baseline = pd.read_csv(baseline_path)
    merged = source.merge(baseline[["source_row", "construct_id", "ood_assignment", "pred_ridge_all", "pred_ridge_gc"]], on=["source_row", "construct_id", "ood_assignment"], validate="one_to_one")
    predictions["ridge_all"] = merged["pred_ridge_all"].to_numpy(float)
    predictions["ridge_gc"] = merged["pred_ridge_gc"].to_numpy(float)
    model_names = ["ribokinetic_selected", "ribokinetic_none", "ridge_all", "ridge_gc"]
    comparators = ["ribokinetic_none", "ridge_all", "ridge_gc"]
    rng = np.random.default_rng(20261120)
    recomputed_comparisons = []
    for partition in ("test", "sequence_ood"):
        indices = np.flatnonzero(source["ood_assignment"].to_numpy() == partition)
        y = source["expression_value"].to_numpy(float)[indices]
        clusters = source["operational_protein_cluster"].to_numpy()[indices]
        for name in model_names:
            metrics = point_metrics(y, predictions[name][indices], clusters)
            for metric, value in metrics.items():
                reported = evaluation["metrics"][partition][name][metric]
                if isinstance(value, (int, float)) and value is not None:
                    close(f"metric:{partition}:{name}:{metric}", value, reported)
                else:
                    check(f"metric_null:{partition}:{name}:{metric}", value == reported)
        frame = pd.DataFrame({"cluster": clusters, "row": np.arange(len(indices))})
        groups = [group["row"].to_numpy() for _, group in frame.groupby("cluster", sort=True)]
        cluster_mse = {name: np.array([np.mean(((predictions[name][indices] - y) ** 2)[group]) for group in groups]) for name in model_names}
        samples = {(right, metric): [] for right in comparators for metric in ("spearman", "cluster_balanced_mse")}
        for _ in range(2000):
            chosen = rng.integers(0, len(groups), len(groups))
            rows = np.concatenate([groups[index] for index in chosen])
            values = {}
            for name in model_names:
                values[(name, "spearman")] = rank_correlation(y[rows], predictions[name][indices][rows])
                values[(name, "cluster_balanced_mse")] = float(np.mean(cluster_mse[name][chosen]))
            for right in comparators:
                for metric in ("spearman", "cluster_balanced_mse"):
                    samples[(right, metric)].append(values[("ribokinetic_selected", metric)] - values[(right, metric)])
        partition_rows = []
        for right in comparators:
            for metric in ("spearman", "cluster_balanced_mse"):
                values = np.asarray(samples[(right, metric)], float)
                valid = values[np.isfinite(values)]
                benefit = values if metric == "spearman" else -values
                valid_benefit = benefit[np.isfinite(benefit)]
                key = "row_spearman" if metric == "spearman" else "cluster_balanced_mse"
                point = point_metrics(y, predictions["ribokinetic_selected"][indices], clusters)[key] - point_metrics(y, predictions[right][indices], clusters)[key]
                row = {
                    "partition": partition,
                    "left": "ribokinetic_selected",
                    "right": right,
                    "metric": metric,
                    "point_delta": float(point),
                    "ci95_low": float(np.quantile(valid, 0.025)),
                    "ci95_high": float(np.quantile(valid, 0.975)),
                    "sign_pvalue": float(min(1.0, 2.0 * min(np.mean(valid_benefit <= 0), np.mean(valid_benefit >= 0)))),
                    "bootstrap_valid": int(len(valid)),
                    "bootstrap_requested": 2000,
                }
                partition_rows.append(row)
        adjusted = holm([row["sign_pvalue"] for row in partition_rows])
        for row, pvalue in zip(partition_rows, adjusted):
            row["holm_pvalue_within_partition"] = float(pvalue)
            recomputed_comparisons.append(row)
            reported = next(item for item in evaluation["comparisons"] if item["partition"] == partition and item["right"] == row["right"] and item["metric"] == row["metric"])
            for key in ("point_delta", "ci95_low", "ci95_high", "sign_pvalue", "holm_pvalue_within_partition"):
                close(f"comparison:{partition}:{row['right']}:{row['metric']}:{key}", row[key], reported[key], 1e-12)
            check(f"bootstrap_count:{partition}:{row['right']}:{row['metric']}", row["bootstrap_valid"] == row["bootstrap_requested"] == reported["bootstrap_valid"] == reported["bootstrap_requested"] == 2000)

    gate_rows = [row for row in recomputed_comparisons if row["partition"] == "sequence_ood"]
    gate = selected_arm != "none" and all(row["holm_pvalue_within_partition"] < 0.05 and ((row["metric"] == "spearman" and row["ci95_low"] > 0) or (row["metric"] == "cluster_balanced_mse" and row["ci95_high"] < 0)) for row in gate_rows)
    check("channel_gate_matches", gate == evaluation["channel_screen_gate_pass"], {"independent": gate, "reported": evaluation["channel_screen_gate_pass"]})
    check("overall_g1_remains_false", evaluation["rk_g1_pass"] is False and protocol["rk_g1_pass"] is False)
    check("untouched_remains_false", evaluation["functional_untouched_evaluated"] is False)
    check("velocity_negative_retained", evaluation["velocity_mechanism_pass"] is False)
    check("generator_not_authorized", evaluation["expensive_generation_authorized"] is False)
    check("no_sota", evaluation["complete_sota"] is False)
    check("no_wet_lab", evaluation["wet_lab_validation_complete"] is False)
    paired = pd.read_csv(root / protocol["audit_root"] / "channel_screen_paired_comparisons_v1.csv")
    check("paired_csv_rows", len(paired) == 12)
    metrics_csv = pd.read_csv(root / protocol["audit_root"] / "channel_screen_metrics_v1.csv")
    check("metrics_csv_rows", len(metrics_csv) == 8)
    report = {
        "schema": "a8-rk08-channel-screen-independent-v1",
        "status": "PASS_CHANNEL_SCREEN_INDEPENDENT" if not failures else "FAIL_CHANNEL_SCREEN_INDEPENDENT",
        "overall_pass": not failures,
        "check_counts": {"passed": len(checks) - len(failures), "total": len(checks)},
        "failures": failures,
        "max_numeric_delta": max_delta,
        "selected_arm": selected_arm,
        "selected_dev_cluster_balanced_mse": dev_values[selected_arm],
        "channel_screen_gate_pass": gate,
        "rk_g1_pass": False,
        "functional_untouched_evaluated": False,
        "velocity_mechanism_pass": False,
        "expensive_generation_authorized": False,
        "independent_comparisons": recomputed_comparisons,
        "hashes": {
            "protocol": sha256(args.protocol),
            "preparation": sha256(args.preparation),
            "selection": sha256(args.selection),
            "evaluation": sha256(args.evaluation),
        },
        "checks": checks,
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "check_counts": report["check_counts"], "max_numeric_delta": max_delta, "selected_arm": selected_arm, "channel_screen_gate_pass": gate, "failures": failures}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
