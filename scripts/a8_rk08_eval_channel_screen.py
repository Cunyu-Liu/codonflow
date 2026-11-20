#!/usr/bin/env python3
"""Evaluate the frozen RK08 channel selection on test/sequence-OOD once."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
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


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def state_equal(left: dict, right: dict) -> bool:
    return left.keys() == right.keys() and all(torch.equal(left[key], right[key]) for key in left)


def finite(value):
    return None if value is None or not np.isfinite(value) else float(value)


def point_metrics(y, prediction, cluster) -> dict:
    y = np.asarray(y, float)
    prediction = np.asarray(prediction, float)
    error = prediction - y
    frame = pd.DataFrame({"cluster": cluster, "squared_error": error ** 2})
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


def fast_spearman(y, prediction) -> float:
    if np.std(y) <= 0 or np.std(prediction) <= 0:
        return float("nan")
    return float(np.corrcoef(stats.rankdata(y), stats.rankdata(prediction))[0, 1])


def holm_adjust(pvalues) -> np.ndarray:
    pvalues = np.asarray(pvalues, float)
    order = np.argsort(pvalues)
    adjusted = np.empty(len(pvalues), float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(pvalues) - rank) * pvalues[index])
        adjusted[index] = min(1.0, running)
    return adjusted


def channel_gate(rows: list[dict], selected_arm: str) -> bool:
    gate_rows = [row for row in rows if row["partition"] == "sequence_ood"]
    return selected_arm != "none" and len(gate_rows) == 6 and all(
        row["holm_pvalue_within_partition"] < 0.05
        and ((row["metric"] == "spearman" and row["ci95_low"] > 0) or (row["metric"] == "cluster_balanced_mse" and row["ci95_high"] < 0))
        for row in gate_rows
    )


def screen_train_dev_rows(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return [row for row in csv.DictReader(handle) if row["split"] in {"train", "dev"}]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    args = parser.parse_args()
    started = time.time()
    root = args.root.resolve()
    protocol_path = args.protocol.resolve()
    preparation_path = args.preparation.resolve()
    selection_path = args.selection.resolve()
    protocol = json.loads(protocol_path.read_text())
    preparation = json.loads(preparation_path.read_text())
    selection = json.loads(selection_path.read_text())
    assert selection["status"] == "PASS_CHANNEL_SELECTION_FROZEN"
    assert selection["protocol_sha256"] == sha256(protocol_path)
    assert selection["preparation_sha256"] == sha256(preparation_path)
    assert selection["test_or_ood_used_for_selection"] is False
    assert protocol["functional_untouched_evaluated"] is False
    selected_arm = selection["selected_arm"]
    arms = [selected_arm] if selected_arm == "none" else [selected_arm, "none"]
    output_root = Path(protocol["output_root"]) / "evaluation"
    output_root.mkdir(parents=True, exist_ok=False)
    data = protocol["data"]["path"]
    base = json.loads((root / protocol["base_config"]["path"]).read_text())
    eval_runs = {}
    eval_config_hashes = {}
    for arm in arms:
        config = copy.deepcopy(base)
        config["ablation"] = arm
        config["include_splits"] = ["train", "dev", "test", "sequence_ood"]
        config_path = output_root / f"{arm}_evaluation_config.json"
        dump(config_path, config)
        eval_config_hashes[arm] = sha256(config_path)
        run_dir = output_root / arm
        log_path = output_root / f"{arm}.console.log"
        command = [
            sys.executable,
            str(root / protocol["train_script"]["path"]),
            "--data", data,
            "--config", str(config_path),
            "--output-dir", str(run_dir),
            "--device", "cuda",
        ]
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(root / "src")
        with log_path.open("w") as log:
            subprocess.run(command, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
        screen_checkpoint = torch.load(Path(selection["selected_checkpoint" if arm == selected_arm else "none_checkpoint"]["path"]), map_location="cpu", weights_only=False)
        eval_checkpoint = torch.load(run_dir / "best.pt", map_location="cpu", weights_only=False)
        assert state_equal(screen_checkpoint["state_dict"], eval_checkpoint["state_dict"]), arm
        screen_rows = screen_train_dev_rows(Path(protocol["output_root"]) / "screen" / arm / "predictions.csv")
        eval_rows = screen_train_dev_rows(run_dir / "predictions.csv")
        assert screen_rows == eval_rows, f"train/dev predictions changed for {arm}"
        run = json.loads((run_dir / "run_summary.json").read_text())
        assert set(run["metrics"]) == {"train", "dev", "test", "sequence_ood"}
        assert run["rows"] == {"train": 4019, "dev": 503, "test": 490, "sequence_ood": 1336}
        eval_runs[arm] = {
            "run_dir": str(run_dir),
            "config_sha256": eval_config_hashes[arm],
            "checkpoint_sha256": sha256(run_dir / "best.pt"),
            "predictions_sha256": sha256(run_dir / "predictions.csv"),
            "screen_state_dict_bitwise_equal": True,
            "screen_train_dev_predictions_exact": True,
            "elapsed_seconds": run["training"]["elapsed_seconds"],
            "forward_passes": run["training"]["forward_passes"],
            "selected_epoch": run["selected_epoch"],
            "parameters": sum(t.numel() for t in eval_checkpoint["state_dict"].values()),
            "gpu": run["environment"]["gpu"],
        }

    usecols = ["source_row", "construct_id", "ood_assignment", "operational_protein_cluster", "expression_value", "cds"]
    source = pd.read_csv(data, usecols=usecols)
    source = source[source["ood_assignment"].isin(["train", "dev", "test", "sequence_ood"])].reset_index(drop=True)
    assert len(source) == 6348
    assert not source[["construct_id", "ood_assignment"]].duplicated().any()

    def read_model(arm: str, model_name: str) -> np.ndarray:
        path = output_root / arm / "predictions.csv"
        frame = pd.read_csv(path).rename(columns={"record_id": "construct_id", "split": "ood_assignment", "cluster_id": "cluster", "prediction": "pred", "target": "prediction_target"})
        assert len(frame) == len(source)
        aligned = source[["construct_id", "ood_assignment", "operational_protein_cluster", "expression_value"]].merge(
            frame[["construct_id", "ood_assignment", "cluster", "prediction_target", "pred"]],
            on=["construct_id", "ood_assignment"], how="left", validate="one_to_one"
        )
        assert len(aligned) == len(source)
        assert aligned["cluster"].tolist() == aligned["operational_protein_cluster"].tolist()
        assert np.array_equal(aligned["prediction_target"].to_numpy(), aligned["expression_value"].to_numpy())
        assert np.isfinite(aligned["pred"].to_numpy(float)).all(), model_name
        return aligned["pred"].to_numpy(float)

    predictions = {"ribokinetic_selected": read_model(selected_arm, "selected")}
    if selected_arm == "none":
        predictions["ribokinetic_none"] = predictions["ribokinetic_selected"].copy()
    else:
        predictions["ribokinetic_none"] = read_model("none", "none")
    baseline = pd.read_csv(protocol["baseline_predictions"]["path"])
    baseline = baseline[["source_row", "construct_id", "ood_assignment", "expression", "pred_ridge_all", "pred_ridge_gc"]]
    merged = source.merge(baseline, on=["source_row", "construct_id", "ood_assignment"], how="left", validate="one_to_one")
    assert len(merged) == len(source)
    assert np.allclose(merged["expression_value"], merged["expression"])
    predictions["ridge_all"] = merged["pred_ridge_all"].to_numpy(float)
    predictions["ridge_gc"] = merged["pred_ridge_gc"].to_numpy(float)
    model_names = ["ribokinetic_selected", "ribokinetic_none", "ridge_all", "ridge_gc"]
    comparators = ["ribokinetic_none", "ridge_all", "ridge_gc"]
    metric_names = ["spearman", "cluster_balanced_mse"]
    rng = np.random.default_rng(protocol["evaluation"]["bootstrap"]["seed"])
    all_metrics = {}
    comparison_rows = []
    bootstrap_rows = []
    for partition in ["test", "sequence_ood"]:
        indices = np.flatnonzero(source["ood_assignment"].to_numpy() == partition)
        y = source["expression_value"].to_numpy(float)[indices]
        clusters = source["operational_protein_cluster"].to_numpy()[indices]
        all_metrics[partition] = {name: point_metrics(y, predictions[name][indices], clusters) for name in model_names}
        cluster_frame = pd.DataFrame({"cluster": clusters, "row": np.arange(len(indices))})
        groups = [group["row"].to_numpy() for _, group in cluster_frame.groupby("cluster", sort=True)]
        cluster_mse = {}
        for name in model_names:
            squared = (predictions[name][indices] - y) ** 2
            cluster_mse[name] = np.array([np.mean(squared[group]) for group in groups])
        boot = {(right, metric): [] for right in comparators for metric in metric_names}
        for _ in range(protocol["evaluation"]["bootstrap"]["replicates"]):
            chosen = rng.integers(0, len(groups), len(groups))
            rows = np.concatenate([groups[index] for index in chosen])
            values = {}
            for name in model_names:
                values[(name, "spearman")] = fast_spearman(y[rows], predictions[name][indices][rows])
                values[(name, "cluster_balanced_mse")] = float(np.mean(cluster_mse[name][chosen]))
            for right in comparators:
                for metric in metric_names:
                    boot[(right, metric)].append(values[("ribokinetic_selected", metric)] - values[(right, metric)])
        partition_rows = []
        for right in comparators:
            for metric in metric_names:
                key = "row_spearman" if metric == "spearman" else "cluster_balanced_mse"
                point = all_metrics[partition]["ribokinetic_selected"][key] - all_metrics[partition][right][key]
                samples = np.asarray(boot[(right, metric)], float)
                valid = samples[np.isfinite(samples)]
                benefit = samples if metric == "spearman" else -samples
                valid_benefit = benefit[np.isfinite(benefit)]
                pvalue = float(min(1.0, 2.0 * min(np.mean(valid_benefit <= 0), np.mean(valid_benefit >= 0)))) if len(valid_benefit) else 1.0
                row = {
                    "partition": partition,
                    "left": "ribokinetic_selected",
                    "right": right,
                    "metric": metric,
                    "point_delta": finite(point),
                    "ci95_low": finite(np.quantile(valid, 0.025)) if len(valid) else None,
                    "ci95_high": finite(np.quantile(valid, 0.975)) if len(valid) else None,
                    "sign_pvalue": pvalue,
                    "bootstrap_valid": int(len(valid)),
                    "bootstrap_requested": protocol["evaluation"]["bootstrap"]["replicates"],
                }
                partition_rows.append(row)
                for replicate, value in enumerate(samples):
                    bootstrap_rows.append({"partition": partition, "left": "ribokinetic_selected", "right": right, "metric": metric, "replicate": replicate, "delta": value})
        adjusted = holm_adjust([row["sign_pvalue"] for row in partition_rows])
        for row, adjusted_p in zip(partition_rows, adjusted):
            row["holm_pvalue_within_partition"] = float(adjusted_p)
            comparison_rows.append(row)

    gate_pass = channel_gate(comparison_rows, selected_arm)
    summary = {
        "schema": "a8-rk08-channel-screen-evaluation-v1",
        "status": "PASS_PENDING_INDEPENDENT_VERIFICATION",
        "scientific_scope": protocol["scientific_scope"],
        "protocol_sha256": sha256(protocol_path),
        "preparation_sha256": sha256(preparation_path),
        "selection_sha256": sha256(selection_path),
        "selected_arm": selected_arm,
        "selected_dev_cluster_balanced_mse": selection["selected_dev_cluster_balanced_mse"],
        "selection_rule": selection["selection_rule"],
        "primary_partition": "sequence_ood",
        "metrics": all_metrics,
        "comparisons": comparison_rows,
        "channel_screen_gate_pass": bool(gate_pass),
        "rk_g1_pass": False,
        "overall_gate_reason": "The prior velocity mechanism endpoint failed and functional untouched was not evaluated; this channel screen alone cannot close RK-G1.",
        "functional_untouched_evaluated": False,
        "velocity_mechanism_pass": False,
        "expensive_generation_authorized": False,
        "complete_sota": False,
        "wet_lab_validation_complete": False,
        "evaluation_runs": eval_runs,
        "bootstrap": protocol["evaluation"]["bootstrap"],
        "inputs": {
            "data_sha256": sha256(Path(data)),
            "baseline_predictions_sha256": sha256(Path(protocol["baseline_predictions"]["path"])),
            "train_script_sha256": sha256(root / protocol["train_script"]["path"]),
            "evaluation_script_sha256": sha256(Path(__file__).resolve()),
        },
        "elapsed_seconds": time.time() - started,
    }
    dump(output_root / "comparison_summary.json", summary)
    comparison_path = output_root / "paired_comparisons.csv"
    metrics_path = output_root / "metrics.csv"
    pd.DataFrame(comparison_rows).to_csv(comparison_path, index=False)
    pd.DataFrame(bootstrap_rows).to_csv(output_root / "bootstrap_deltas.csv.gz", index=False, compression="gzip")
    pd.DataFrame([{"partition": partition, "model": model, **values} for partition, part in all_metrics.items() for model, values in part.items()]).to_csv(metrics_path, index=False)
    audit_root = root / protocol["audit_root"]
    audit_summary = audit_root / "channel_screen_evaluation_v1.json"
    if audit_summary.exists():
        raise FileExistsError(audit_summary)
    dump(audit_summary, summary)
    shutil.copyfile(comparison_path, audit_root / "channel_screen_paired_comparisons_v1.csv")
    shutil.copyfile(metrics_path, audit_root / "channel_screen_metrics_v1.csv")
    print(json.dumps({"status": summary["status"], "selected_arm": selected_arm, "channel_screen_gate_pass": gate_pass, "rk_g1_pass": False, "output": str(audit_summary), "elapsed_seconds": summary["elapsed_seconds"]}, indent=2))


if __name__ == "__main__":
    main()
