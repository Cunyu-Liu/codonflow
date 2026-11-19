#!/usr/bin/env python3
"""Train and evaluate RK08 on occupancy-derived per-codon velocity proxies.

The retained test and all study-OOD partitions are excluded from fitting and
checkpoint selection. The primary OOD comparison is against a ridge using codon,
relative-position and length features only. No generator or RK-G1 authorization
is inferred from this standalone mechanism experiment.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import gzip
import hashlib
import io
import json
import math
import os
import random
import time
from pathlib import Path

import numpy as np
import torch
from scipy import sparse, stats
from sklearn.linear_model import Ridge

from codonflow.core.tokenizer import encode_cds
from codonflow.data.ribokinetic import (
    TargetNormalizer,
    collate_ribokinetic,
    file_sha256,
    fit_host_vocabulary,
    move_batch,
)
from codonflow.data.velocity import dataset_of, read_velocity_jsonl
from codonflow.models.ribokinetic import RiboKineticModel, RiboKineticConfig, ribokinetic_loss


def deterministic_gzip_text(path: Path):
    raw = path.open("wb")
    compressed = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    return io.TextIOWrapper(compressed, encoding="utf-8", newline="")


def save_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def finite(value):
    return None if value is None or not np.isfinite(value) else float(value)


def batches(records, batch_size, order=None):
    indices = list(range(len(records))) if order is None else list(order)
    for start in range(0, len(indices), batch_size):
        yield [records[index] for index in indices[start : start + batch_size]]


@torch.no_grad()
def predict_model(model, records, host_vocabulary, normalizer, batch_size, device):
    model.eval()
    predictions = {}
    forward_passes = 0
    for batch_records in batches(records, batch_size):
        batch = move_batch(collate_ribokinetic(batch_records, host_vocabulary), device)
        output = model(
            batch["codon_ids"], batch["pad_mask"],
            host_ids=batch.get("host_ids"), budget=batch.get("budget"),
            utr_ids=batch.get("utr_ids"),
        )
        forward_passes += 1
        values = output["velocity"].detach().float().cpu().numpy()
        for index, record in enumerate(batch_records):
            length = record.codon_count
            predictions[record.record_id] = values[index, :length] * normalizer.scale + normalizer.mean
    return predictions, forward_passes


def feature_matrix(records, position_bins):
    """Sparse codon + relative-position-bin + relative-position + log-length design."""
    rows, columns, values, targets = [], [], [], []
    row_index = 0
    dimension = 64 + position_bins + 2
    for record in records:
        codons = encode_cds(record.cds, add_special=False)
        n_codons = record.codon_count
        for position in range(1, n_codons - 1):
            target = record.velocity_target[position]
            if not math.isfinite(target):
                continue
            relative = position / max(n_codons - 1, 1)
            position_bin = min(position_bins - 1, int(relative * position_bins))
            entries = [
                (int(codons[position]), 1.0),
                (64 + position_bin, 1.0),
                (64 + position_bins, relative),
                (64 + position_bins + 1, math.log(n_codons) / 7.0),
            ]
            for column, value in entries:
                rows.append(row_index)
                columns.append(column)
                values.append(value)
            targets.append(float(target))
            row_index += 1
    matrix = sparse.csr_matrix((values, (rows, columns)), shape=(row_index, dimension), dtype=np.float64)
    return matrix, np.asarray(targets, dtype=np.float64)


def fit_ridge(records, position_bins, alpha):
    matrix, targets = feature_matrix(records, position_bins)
    model = Ridge(alpha=alpha, fit_intercept=True, solver="lsqr", tol=1e-8, max_iter=10000)
    model.fit(matrix, targets)
    return model


@torch.no_grad()
def predict_ridge(model, records, position_bins):
    predictions = {}
    for record in records:
        matrix, _ = feature_matrix([record], position_bins)
        observed_positions = [i for i in range(1, record.codon_count - 1) if math.isfinite(record.velocity_target[i])]
        values = model.predict(matrix)
        result = np.full(record.codon_count, np.nan, dtype=np.float64)
        for position, value in zip(observed_positions, values):
            result[position] = value
        predictions[record.record_id] = result
    return predictions


def record_statistics(record, prediction):
    target = np.asarray(record.velocity_target, dtype=np.float64)
    pred = np.asarray(prediction, dtype=np.float64)
    mask = np.isfinite(target) & np.isfinite(pred)
    if not mask.any():
        raise ValueError(f"no observed predictions for {record.record_id}")
    y = target[mask]
    p = pred[mask]
    pearson = np.nan
    if len(y) >= 3 and np.std(y) > 0 and np.std(p) > 0:
        pearson = float(np.corrcoef(y, p)[0, 1])
    return {
        "target": y,
        "prediction": p,
        "mse": float(np.mean((p - y) ** 2)),
        "pearson": pearson,
    }


def metrics(records, predictions):
    per_record = [record_statistics(record, predictions[record.record_id]) for record in records]
    y = np.concatenate([row["target"] for row in per_record])
    p = np.concatenate([row["prediction"] for row in per_record])
    transcript_pearson = np.asarray([row["pearson"] for row in per_record], dtype=np.float64)
    valid_pearson = transcript_pearson[np.isfinite(transcript_pearson)]
    return {
        "n_transcripts": len(records),
        "n_observed_positions": int(len(y)),
        "position_mse": float(np.mean((p - y) ** 2)),
        "transcript_balanced_mse": float(np.mean([row["mse"] for row in per_record])),
        "position_pearson": finite(np.corrcoef(y, p)[0, 1] if np.std(y) > 0 and np.std(p) > 0 else np.nan),
        "position_spearman": finite(stats.spearmanr(y, p).statistic),
        "mean_transcript_pearson": finite(np.mean(valid_pearson) if len(valid_pearson) else np.nan),
        "median_transcript_pearson": finite(np.median(valid_pearson) if len(valid_pearson) else np.nan),
        "n_transcripts_with_pearson": int(len(valid_pearson)),
    }


def holm_two(pvalues):
    ordered = sorted((value, index) for index, value in enumerate(pvalues))
    adjusted = [1.0, 1.0]
    running = 0.0
    for rank, (value, index) in enumerate(ordered):
        running = max(running, (2 - rank) * value)
        adjusted[index] = min(1.0, running)
    return adjusted


def paired_bootstrap(records, model_predictions, ridge_predictions, replicates, seed):
    model_stats = [record_statistics(record, model_predictions[record.record_id]) for record in records]
    ridge_stats = [record_statistics(record, ridge_predictions[record.record_id]) for record in records]
    model_mse = np.asarray([row["mse"] for row in model_stats])
    ridge_mse = np.asarray([row["mse"] for row in ridge_stats])
    model_pearson = np.asarray([row["pearson"] for row in model_stats])
    ridge_pearson = np.asarray([row["pearson"] for row in ridge_stats])
    valid = np.isfinite(model_pearson) & np.isfinite(ridge_pearson)
    rng = np.random.default_rng(seed)
    samples = {"transcript_balanced_mse": [], "mean_transcript_pearson": []}
    for _ in range(replicates):
        selected = rng.integers(0, len(records), len(records))
        samples["transcript_balanced_mse"].append(float(np.mean(model_mse[selected] - ridge_mse[selected])))
        chosen = selected[valid[selected]]
        if len(chosen):
            samples["mean_transcript_pearson"].append(float(np.mean(model_pearson[chosen] - ridge_pearson[chosen])))
        else:
            samples["mean_transcript_pearson"].append(np.nan)
    rows = []
    for metric in ["transcript_balanced_mse", "mean_transcript_pearson"]:
        values = np.asarray(samples[metric], dtype=np.float64)
        values = values[np.isfinite(values)]
        point = float(np.mean(model_mse - ridge_mse)) if metric == "transcript_balanced_mse" else float(np.mean(model_pearson[valid] - ridge_pearson[valid]))
        benefit = -values if metric == "transcript_balanced_mse" else values
        pvalue = float(min(1.0, 2.0 * min(np.mean(benefit <= 0), np.mean(benefit >= 0))))
        rows.append({
            "metric": metric,
            "point_delta_model_minus_ridge": point,
            "ci95_low": finite(np.quantile(values, 0.025)),
            "ci95_high": finite(np.quantile(values, 0.975)),
            "sign_pvalue": pvalue,
            "bootstrap_valid": int(len(values)),
            "bootstrap_requested": replicates,
        })
    for row, adjusted in zip(rows, holm_two([row["sign_pvalue"] for row in rows])):
        row["holm_pvalue"] = adjusted
    gate = all(
        row["ci95_low"] is not None
        and row["ci95_high"] is not None
        and row["holm_pvalue"] < 0.05
        and ((row["metric"] == "transcript_balanced_mse" and row["ci95_high"] < 0) or (row["metric"] == "mean_transcript_pearson" and row["ci95_low"] > 0))
        for row in rows
    )
    return rows, bool(gate)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    started = time.time()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    config = json.loads(Path(args.config).read_text())
    if config["protocol"] != "a8_rk08_velocity_proxy_v1_preregistered_before_model_readout":
        raise ValueError("unexpected protocol")
    records = read_velocity_jsonl(args.data, max_records_per_split=config.get("max_records_per_split"))
    train = [record for record in records if record.split == "train"]
    dev = [record for record in records if record.split == "dev"]
    if not train or not dev:
        raise ValueError("train and dev must be nonempty")
    if any(dataset_of(record) != config["train_study"] for record in train + dev):
        raise ValueError("train/dev contain a non-training study")

    seed = int(config["training"]["seed"])
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    if hasattr(torch.backends.cuda, "enable_flash_sdp"):
        torch.backends.cuda.enable_flash_sdp(False)
        torch.backends.cuda.enable_mem_efficient_sdp(False)
        torch.backends.cuda.enable_math_sdp(True)
    device = torch.device(args.device)

    normalizer = TargetNormalizer.fit(train, "velocity")
    normalized = normalizer.apply(records)
    normalized_by_id = {record.record_id: record for record in normalized}
    train_normalized = [normalized_by_id[record.record_id] for record in train]
    dev_normalized = [normalized_by_id[record.record_id] for record in dev]
    host_vocabulary = fit_host_vocabulary(train)
    model_config = RiboKineticConfig(**config["model"])
    model = RiboKineticModel(model_config).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(config["training"]["lr"]),
        weight_decay=float(config["training"]["weight_decay"]),
    )
    batch_size = int(config["training"]["batch_size"])
    best_loss = float("inf")
    best_epoch = 0
    stale_epochs = 0
    history = []
    forward_passes = 0
    checkpoint_path = out / "best.pt"

    for epoch in range(1, int(config["training"]["epochs"]) + 1):
        model.train()
        generator = torch.Generator().manual_seed(seed + epoch)
        order = torch.randperm(len(train_normalized), generator=generator).tolist()
        train_losses = []
        for batch_records in batches(train_normalized, batch_size, order):
            batch = move_batch(collate_ribokinetic(batch_records, host_vocabulary), device)
            optimizer.zero_grad(set_to_none=True)
            output = model(
                batch["codon_ids"], batch["pad_mask"],
                host_ids=batch.get("host_ids"), budget=batch.get("budget"),
                utr_ids=batch.get("utr_ids"),
            )
            forward_passes += 1
            loss, _ = ribokinetic_loss(output, batch, {"velocity": 1.0})
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), float(config["training"]["gradient_clip"]))
            optimizer.step()
            train_losses.append(float(loss.detach().cpu()))
        dev_predictions, used = predict_model(model, dev_normalized, host_vocabulary, normalizer, batch_size, device)
        forward_passes += used
        dev_raw_predictions = {
            record.record_id: dev_predictions[record.record_id]
            for record in dev
        }
        dev_metrics = metrics(dev, dev_raw_predictions)
        train_loss = float(np.mean(train_losses))
        selection_loss = dev_metrics["transcript_balanced_mse"]
        history.append({"epoch": epoch, "train_normalized_masked_mse": train_loss, "dev": dev_metrics})
        print(json.dumps({"epoch": epoch, "train_loss": train_loss, "dev_transcript_balanced_mse": selection_loss}), flush=True)
        if selection_loss < best_loss:
            best_loss = selection_loss
            best_epoch = epoch
            stale_epochs = 0
            torch.save(
                {
                    "model_config": dataclasses.asdict(model_config),
                    "ablation": "all",
                    "state_dict": model.state_dict(),
                    "normalizer": normalizer.to_dict(),
                    "host_vocabulary": host_vocabulary,
                    "epoch": epoch,
                    "config_sha256": file_sha256(args.config),
                    "data_sha256": file_sha256(args.data),
                },
                checkpoint_path,
            )
        else:
            stale_epochs += 1
        if stale_epochs >= int(config["training"]["early_stopping_patience"]):
            break

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["state_dict"])
    model.to(device)
    model_predictions, used = predict_model(model, normalized, host_vocabulary, normalizer, batch_size, device)
    forward_passes += used
    baseline_config = config["baseline"]
    ridge = fit_ridge(train, int(baseline_config["relative_position_bins"]), float(baseline_config["alpha"]))
    ridge_predictions = predict_ridge(ridge, records, int(baseline_config["relative_position_bins"]))
    np.savez(
        out / "baseline.npz",
        coef=np.asarray(ridge.coef_, dtype=np.float64),
        intercept=np.asarray([ridge.intercept_], dtype=np.float64),
        relative_position_bins=np.asarray([baseline_config["relative_position_bins"]], dtype=np.int64),
        alpha=np.asarray([baseline_config["alpha"]], dtype=np.float64),
    )

    candidate_groups = {
        "train": [record for record in records if record.split == "train"],
        "dev": [record for record in records if record.split == "dev"],
        "test": [record for record in records if record.split == "test"],
    }
    groups = {name: group for name, group in candidate_groups.items() if group}
    if not config.get("smoke", False) and len(groups) != 3:
        raise ValueError("formal data require nonempty train/dev/test groups")
    for dataset in sorted({dataset_of(record) for record in records if record.split == "study_ood"}):
        groups[f"study_ood:{dataset}"] = [record for record in records if record.split == "study_ood" and dataset_of(record) == dataset]
    all_metrics = {}
    for name, group in groups.items():
        all_metrics[name] = {
            "ribokinetic_velocity": metrics(group, model_predictions),
            "ridge_codon_position_length": metrics(group, ridge_predictions),
        }

    primary_name = f"study_ood:{config['primary_ood_study']}"
    primary_records = groups[primary_name]
    comparisons, mechanism_pass = paired_bootstrap(
        primary_records,
        model_predictions,
        ridge_predictions,
        int(config["bootstrap"]["replicates"]),
        int(config["bootstrap"]["seed"]),
    )

    predictions_path = out / "predictions.csv.gz"
    with deterministic_gzip_text(predictions_path) as handle:
        writer = csv.writer(handle)
        writer.writerow(["record_id", "dataset", "split", "codon_position", "target", "model_prediction", "ridge_prediction"])
        for record in records:
            model_values = model_predictions[record.record_id]
            ridge_values = ridge_predictions[record.record_id]
            for position in range(1, record.codon_count - 1):
                target = record.velocity_target[position]
                if not math.isfinite(target):
                    continue
                writer.writerow([
                    record.record_id,
                    dataset_of(record),
                    record.split,
                    position,
                    format(float(target), ".17g"),
                    format(float(model_values[position]), ".17g"),
                    format(float(ridge_values[position]), ".17g"),
                ])

    elapsed = time.time() - started
    summary = {
        "protocol": config["protocol"],
        "status": "PASS_PENDING_INDEPENDENT_VERIFICATION",
        "scientific_scope": "Occupancy-derived elongation-speed proxy; not a physical velocity assay and not functional-OOD evidence.",
        "selection": "Mohammad16 dev transcript-balanced MSE only; test and study-OOD excluded from fitting and checkpoint selection.",
        "primary_endpoint": f"{primary_name} transcript-balanced MSE and mean transcript Pearson versus ridge",
        "velocity_mechanism_pass": mechanism_pass,
        "rk_g1_pass": False,
        "expensive_generation_authorized": False,
        "cross_head_consistency_closed": False,
        "functional_transfer_closed": False,
        "selected_epoch": best_epoch,
        "metrics": all_metrics,
        "primary_comparisons": comparisons,
        "training": {
            **config["training"],
            "epochs_completed": len(history),
            "elapsed_seconds": elapsed,
            "forward_passes": forward_passes,
            "parameter_count": int(sum(parameter.numel() for parameter in model.parameters())),
        },
        "normalizer": normalizer.to_dict(),
        "host_vocabulary": host_vocabulary,
        "baseline": baseline_config,
        "environment": {
            "python": os.sys.version,
            "torch": torch.__version__,
            "device": str(device),
            "gpu": torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu",
            "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
            "sdp_backends": "math_only",
        },
        "hashes": {
            "data_sha256": file_sha256(args.data),
            "config_sha256": file_sha256(args.config),
            "checkpoint_sha256": file_sha256(str(checkpoint_path)),
            "predictions_sha256": file_sha256(str(predictions_path)),
            "baseline_sha256": file_sha256(str(out / "baseline.npz")),
            "train_script_sha256": file_sha256(__file__),
        },
    }
    save_json(out / "history.json", history)
    save_json(out / "run_summary.json", summary)
    print(json.dumps({
        "status": summary["status"],
        "velocity_mechanism_pass": mechanism_pass,
        "selected_epoch": best_epoch,
        "primary_metrics": all_metrics[primary_name],
        "primary_comparisons": comparisons,
        "elapsed_seconds": elapsed,
        "output_dir": str(out),
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
