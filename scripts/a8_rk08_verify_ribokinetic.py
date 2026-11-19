#!/usr/bin/env python3
"""Independently verify an RK-08 supervised training smoke and optional retrain."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
import torch
from scipy.stats import pearsonr, spearmanr

from codonflow.data.ribokinetic import (
    collate_ribokinetic,
    file_sha256,
    fit_host_vocabulary,
    read_functional_csv,
)
from codonflow.models.ribokinetic import RiboKineticConfig, RiboKineticModel


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--retrain-dir")
    p.add_argument("--cuda-dir")
    p.add_argument("--data", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--script", required=True)
    p.add_argument("--output", required=True)
    return p.parse_args()


def read_json(path):
    return json.loads(Path(path).read_text())


def read_predictions(path):
    with Path(path).open(newline="") as handle:
        return list(csv.DictReader(handle))


def close(a, b, tolerance=1e-10):
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tolerance


def correlation(x, y, method):
    if len(x) < 2 or len(set(x)) < 2 or len(set(y)) < 2:
        return None
    result = pearsonr(x, y).statistic if method == "pearson" else spearmanr(x, y).statistic
    return float(result) if math.isfinite(result) else None


def recompute(rows):
    target = np.array([float(r["target"]) for r in rows])
    pred = np.array([float(r["prediction"]) for r in rows])
    errors = pred - target
    clusters = sorted({r["cluster_id"] for r in rows})
    cluster_mse = []
    for cluster in clusters:
        indices = [i for i, row in enumerate(rows) if row["cluster_id"] == cluster]
        cluster_mse.append(float(np.mean(errors[indices] ** 2)))
    return {
        "n": len(rows),
        "mse": float(np.mean(errors ** 2)),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
        "mae": float(np.mean(np.abs(errors))),
        "pearson": correlation(target.tolist(), pred.tolist(), "pearson"),
        "spearman": correlation(target.tolist(), pred.tolist(), "spearman"),
        "cluster_balanced_mse": float(np.mean(cluster_mse)) if cluster_mse else float(np.mean(errors ** 2)),
        "cluster_count": len(clusters),
    }


def main():
    args = parse_args()
    run = Path(args.run_dir)
    summary = read_json(run / "run_summary.json")
    metrics = read_json(run / "metrics.json")
    history = read_json(run / "history.json")
    predictions = read_predictions(run / "predictions.csv")
    resolved = read_json(run / "resolved_config.json")
    config = read_json(args.config)
    checks = []

    def check(name, condition, detail):
        checks.append({"name": name, "status": "PASS" if condition else "FAIL", "detail": detail})

    check("production_pending_preserved", summary["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION", summary["status"])
    check("smoke_scope", summary["scope"] == "REAL_DATA_SMOKE_NOT_MECHANISM_VALIDATION", summary["scope"])
    for name, path in (("data", args.data), ("config", args.config), ("script", args.script)):
        expected = summary["hashes"][f"{name}_sha256"]
        observed = file_sha256(path)
        check(f"{name}_sha256", observed == expected, {"observed": observed, "expected": expected})
    checkpoint_path = run / "best.pt"
    checkpoint_hash = file_sha256(str(checkpoint_path))
    check("checkpoint_sha256", checkpoint_hash == summary["hashes"]["checkpoint_sha256"], checkpoint_hash)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    check("checkpoint_not_generator", checkpoint["scope"] == "SUPERVISED_RK08_NOT_GENERATOR", checkpoint["scope"])
    check("no_functional_untouched_rows", set(summary["rows"]) == set(config["include_splits"]), summary["rows"])
    check("no_functional_untouched_predictions", all(r["split"] != "functional_untouched" for r in predictions), len(predictions))
    records = read_functional_csv(
        args.data,
        include_splits=config["include_splits"],
        max_rows_per_split=config.get("max_rows_per_split"),
        **config.get("columns", {}),
    )
    expected_counts = {split: sum(r.split == split for r in records) for split in config["include_splits"]}
    check("row_counts", summary["rows"] == expected_counts, {"observed": summary["rows"], "expected": expected_counts})
    host_vocab = fit_host_vocabulary(records)
    check("host_vocabulary_train_only", resolved["host_vocabulary"] == host_vocab == checkpoint["host_vocabulary"], host_vocab)
    selection_metric = config["training"].get("selection_metric", "cluster_balanced_mse")
    best = min(history, key=lambda row: row["dev"][selection_metric])
    check("dev_only_epoch_selection", best["epoch"] == summary["selected_epoch"], {"selected": summary["selected_epoch"], "recomputed": best["epoch"]})
    check("history_has_no_test_metrics", all(set(row) == {"epoch", "train_loss", "dev", "seconds"} for row in history), len(history))
    for split in config["include_splits"]:
        rows = [r for r in predictions if r["split"] == split]
        recomputed = recompute(rows)
        ok = all(close(metrics[split][key], value, 1e-9) for key, value in recomputed.items())
        check(f"recompute_metrics_{split}", ok, recomputed)
    if config["task"] != "function":
        raise NotImplementedError("this smoke verifier currently targets function predictions")
    model = RiboKineticModel(RiboKineticConfig(**checkpoint["model_config"]))
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    by_id = {r["record_id"]: r for r in predictions}
    check("unique_prediction_ids", len(by_id) == len(predictions), len(by_id))
    max_error = 0.0
    batch_size = int(config["training"].get("batch_size", 8))
    with torch.no_grad():
        for start in range(0, len(records), batch_size):
            group = records[start : start + batch_size]
            raw = collate_ribokinetic(group, host_vocab)
            out = model(
                raw["codon_ids"], raw["pad_mask"],
                host_ids=raw["host_ids"], active_mechanisms=checkpoint["active_mechanisms"],
            )
            mean = out["function"].numpy()
            scale = out["function_log_scale"].exp().numpy()
            for i, record in enumerate(group):
                row = by_id[record.record_id]
                expected = [float(row["prediction"]), float(row["lower_95"]), float(row["upper_95"])]
                observed = [float(mean[i]), float(mean[i] - 1.96 * scale[i]), float(mean[i] + 1.96 * scale[i])]
                max_error = max(max_error, max(abs(a - b) for a, b in zip(expected, observed)))
    check("independent_forward_predictions", max_error <= 1e-5, {"max_abs_error": max_error})
    artifact_hashes = {}
    for name in ("metrics.json", "history.json", "predictions.csv", "resolved_config.json", "best.pt"):
        artifact_hashes[name] = file_sha256(str(run / name))
    retrain_report = None
    if args.retrain_dir:
        other = Path(args.retrain_dir)
        other_metrics = read_json(other / "metrics.json")
        other_predictions = read_predictions(other / "predictions.csv")
        other_checkpoint = torch.load(other / "best.pt", map_location="cpu", weights_only=False)
        metric_equal = metrics == other_metrics
        prediction_equal = predictions == other_predictions
        state_equal = set(checkpoint["state_dict"]) == set(other_checkpoint["state_dict"]) and all(
            torch.equal(checkpoint["state_dict"][key], other_checkpoint["state_dict"][key])
            for key in checkpoint["state_dict"]
        )
        check("retrain_metrics_identical", metric_equal, metric_equal)
        check("retrain_predictions_identical", prediction_equal, prediction_equal)
        check("retrain_state_tensors_bitwise_identical", state_equal, state_equal)
        retrain_report = {"metrics_equal": metric_equal, "predictions_equal": prediction_equal, "state_tensors_bitwise_equal": state_equal}
    cuda_report = None
    if args.cuda_dir:
        cuda_dir = Path(args.cuda_dir)
        cuda_summary = read_json(cuda_dir / "run_summary.json")
        cuda_metrics = read_json(cuda_dir / "metrics.json")
        cuda_predictions = read_predictions(cuda_dir / "predictions.csv")
        cuda_checkpoint = torch.load(cuda_dir / "best.pt", map_location="cpu", weights_only=False)
        check("cuda_execution_confirmed", cuda_summary["environment"]["device"] == "cuda" and bool(cuda_summary["environment"]["gpu"]), cuda_summary["environment"])
        check("cuda_pending_preserved", cuda_summary["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION", cuda_summary["status"])
        check("cuda_input_hashes_match", all(cuda_summary["hashes"][key] == summary["hashes"][key] for key in ("data_sha256", "config_sha256", "script_sha256")), cuda_summary["hashes"])
        check("cuda_checkpoint_hash", file_sha256(str(cuda_dir / "best.pt")) == cuda_summary["hashes"]["checkpoint_sha256"], cuda_summary["hashes"]["checkpoint_sha256"])
        check("cuda_model_config_match", cuda_checkpoint["model_config"] == checkpoint["model_config"], "same model configuration")
        cuda_by_id = {r["record_id"]: r for r in cuda_predictions}
        check("cuda_unique_prediction_ids", len(cuda_by_id) == len(cuda_predictions), len(cuda_by_id))
        for split in config["include_splits"]:
            rows = [r for r in cuda_predictions if r["split"] == split]
            recomputed = recompute(rows)
            ok = all(close(cuda_metrics[split][key], value, 1e-8) for key, value in recomputed.items())
            check(f"cuda_recompute_metrics_{split}", ok, recomputed)
        cuda_model = RiboKineticModel(RiboKineticConfig(**cuda_checkpoint["model_config"]))
        cuda_model.load_state_dict(cuda_checkpoint["state_dict"])
        cuda_model.eval()
        cuda_error = 0.0
        with torch.no_grad():
            for start in range(0, len(records), batch_size):
                group = records[start : start + batch_size]
                raw = collate_ribokinetic(group, host_vocab)
                out = cuda_model(
                    raw["codon_ids"], raw["pad_mask"],
                    host_ids=raw["host_ids"], active_mechanisms=cuda_checkpoint["active_mechanisms"],
                )
                mean = out["function"].numpy()
                scale = out["function_log_scale"].exp().numpy()
                for i, record in enumerate(group):
                    row = cuda_by_id[record.record_id]
                    expected = [float(row["prediction"]), float(row["lower_95"]), float(row["upper_95"])]
                    observed = [float(mean[i]), float(mean[i] - 1.96 * scale[i]), float(mean[i] + 1.96 * scale[i])]
                    cuda_error = max(cuda_error, max(abs(a - b) for a, b in zip(expected, observed)))
        check("cuda_independent_forward_predictions", cuda_error <= 1e-4, {"max_abs_error": cuda_error})
        cuda_report = {"device": cuda_summary["environment"]["device"], "gpu": cuda_summary["environment"]["gpu"], "forward_max_abs_error": cuda_error}
    failed = [c for c in checks if c["status"] != "PASS"]
    report = {
        "status": "PASS" if not failed else "FAIL",
        "checks_passed": len(checks) - len(failed),
        "checks_total": len(checks),
        "checks": checks,
        "artifact_hashes": artifact_hashes,
        "retrain": retrain_report,
        "cuda": cuda_report,
        "scope": "independent verification of a real-data smoke; not mechanism validation or SOTA",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "passed": report["checks_passed"], "total": report["checks_total"], "output": str(output)}))


if __name__ == "__main__":
    main()
