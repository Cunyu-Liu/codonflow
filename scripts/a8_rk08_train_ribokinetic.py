#!/usr/bin/env python3
"""Train/evaluate the RK-08 supervised ribokinetic backbone.

Train-only fitting and dev-only checkpoint selection are enforced. Test/OOD
metrics are computed only after the selected checkpoint is frozen. This script
is a prediction workflow; it does not authorize or launch generator training.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import random
import time
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

import numpy as np
import torch
from scipy.stats import pearsonr, spearmanr

from codonflow.data.ribokinetic import (
    TargetNormalizer,
    VariantRecord,
    collate_ribokinetic,
    file_sha256,
    fit_host_vocabulary,
    move_batch,
    read_functional_csv,
    read_velocity_long_csv,
)
from codonflow.models.ribokinetic import (
    MECHANISMS,
    RiboKineticConfig,
    RiboKineticModel,
    ribokinetic_loss,
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default=None)
    return parser.parse_args()


def atomic_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)


def active_from_name(name: str) -> Dict[str, bool]:
    active = {key: True for key in MECHANISMS}
    if name == "all":
        return active
    if name == "none":
        return {key: False for key in MECHANISMS}
    if name.startswith("no_"):
        target = name[3:]
        if target not in active:
            raise ValueError(f"unknown ablation {name}")
        active[target] = False
        return active
    if name.endswith("_only"):
        target = name[:-5]
        if target not in active:
            raise ValueError(f"unknown ablation {name}")
        return {key: key == target for key in MECHANISMS}
    raise ValueError(f"unknown ablation {name}")


def load_records(data: str, config: Mapping) -> List[VariantRecord]:
    columns = dict(config.get("columns", {}))
    include = config.get("include_splits", ["train", "dev", "test"])
    limit = config.get("max_rows_per_split")
    if config["task"] == "function":
        return read_functional_csv(
            data,
            include_splits=include,
            max_rows_per_split=limit,
            **columns,
        )
    if config["task"] == "velocity":
        records = read_velocity_long_csv(data, **columns)
        records = [r for r in records if r.split in include]
        if limit is not None:
            counts = {}
            selected = []
            for record in records:
                if counts.get(record.split, 0) >= limit:
                    continue
                selected.append(record)
                counts[record.split] = counts.get(record.split, 0) + 1
            records = selected
        if not records:
            raise ValueError("no velocity records remain after split filtering")
        return records
    raise ValueError(f"unsupported task {config['task']}")


def batches(records: Sequence[VariantRecord], batch_size: int):
    for start in range(0, len(records), batch_size):
        yield records[start : start + batch_size]


def safe_correlation(x: Sequence[float], y: Sequence[float], method: str):
    if len(x) < 2 or len(set(x)) < 2 or len(set(y)) < 2:
        return None
    value = pearsonr(x, y).statistic if method == "pearson" else spearmanr(x, y).statistic
    return float(value) if math.isfinite(value) else None


def evaluate(
    model: RiboKineticModel,
    records: Sequence[VariantRecord],
    host_vocab: Mapping[str, int],
    active: Mapping[str, bool],
    task: str,
    batch_size: int,
    device: torch.device,
) -> Tuple[dict, List[dict], int]:
    model.eval()
    predictions: List[dict] = []
    forwards = 0
    with torch.no_grad():
        for group in batches(records, batch_size):
            raw = collate_ribokinetic(group, host_vocab)
            batch = move_batch(raw, device)
            out = model(
                batch["codon_ids"], batch["pad_mask"],
                host_ids=batch.get("host_ids"), budget=batch.get("budget"),
                utr_ids=batch.get("utr_ids"), active_mechanisms=active,
            )
            forwards += 1
            if task == "function":
                mean = out["function"].cpu().numpy()
                scale = out["function_log_scale"].exp().cpu().numpy()
                for i, record in enumerate(group):
                    predictions.append({
                        "record_id": record.record_id,
                        "split": record.split,
                        "cluster_id": record.cluster_id,
                        "target": float(record.function_target),
                        "prediction": float(mean[i]),
                        "lower_95": float(mean[i] - 1.96 * scale[i]),
                        "upper_95": float(mean[i] + 1.96 * scale[i]),
                    })
            else:
                values = out["velocity"].cpu().numpy()
                for i, record in enumerate(group):
                    for position, target in enumerate(record.velocity_target):
                        if math.isfinite(target):
                            predictions.append({
                                "record_id": record.record_id,
                                "split": record.split,
                                "cluster_id": record.cluster_id,
                                "position": position,
                                "target": float(target),
                                "prediction": float(values[i, position]),
                            })
    if not predictions:
        raise ValueError("evaluation produced no finite targets")
    target = [p["target"] for p in predictions]
    predicted = [p["prediction"] for p in predictions]
    errors = np.asarray(predicted) - np.asarray(target)
    metrics = {
        "n": len(predictions),
        "mse": float(np.mean(errors ** 2)),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
        "mae": float(np.mean(np.abs(errors))),
        "pearson": safe_correlation(target, predicted, "pearson"),
        "spearman": safe_correlation(target, predicted, "spearman"),
    }
    clusters = sorted({p["cluster_id"] for p in predictions})
    if clusters:
        cluster_mse = []
        for cluster in clusters:
            indices = [i for i, p in enumerate(predictions) if p["cluster_id"] == cluster]
            cluster_mse.append(float(np.mean(errors[indices] ** 2)))
        metrics["cluster_balanced_mse"] = float(np.mean(cluster_mse))
        metrics["cluster_count"] = len(clusters)
    else:
        metrics["cluster_balanced_mse"] = metrics["mse"]
        metrics["cluster_count"] = 0
    return metrics, predictions, forwards


def write_predictions(path: Path, rows: Sequence[dict]) -> None:
    fields = ["record_id", "split", "cluster_id"]
    if rows and "position" in rows[0]:
        fields += ["position"]
    fields += ["target", "prediction"]
    if rows and "lower_95" in rows[0]:
        fields += ["lower_95", "upper_95"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    started = time.time()
    config_path = Path(args.config).resolve()
    config = json.loads(config_path.read_text())
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    task = config["task"]
    training = config["training"]
    seed = int(training.get("seed", 0))
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.set_float32_matmul_precision("highest")
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_math_sdp(True)
    device = torch.device(args.device or training.get("device", "cpu"))
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    records = load_records(args.data, config)
    host_vocab = fit_host_vocabulary(records)
    normalizer = None
    normalization = config.get("target_normalization")
    if normalization:
        normalizer = TargetNormalizer.fit(
            records, task, bool(normalization.get("log1p", False))
        )
        records = normalizer.apply(records)
    model_config = RiboKineticConfig(**config.get("model", {}))
    if len(host_vocab) + 1 > model_config.num_hosts:
        raise ValueError("train host vocabulary exceeds configured num_hosts")
    active = active_from_name(config.get("ablation", "all"))
    model = RiboKineticModel(model_config).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(training.get("lr", 1e-3)),
        weight_decay=float(training.get("weight_decay", 0.0)),
    )
    batch_size = int(training.get("batch_size", 8))
    epochs = int(training.get("epochs", 2))
    selection_metric = training.get("selection_metric", "cluster_balanced_mse")
    train_records = [r for r in records if r.split == "train"]
    dev_records = [r for r in records if r.split == "dev"]
    if not train_records or not dev_records:
        raise ValueError("both train and dev records are required")
    best_value = float("inf")
    best_epoch = -1
    best_state = None
    history = []
    forward_count = 0
    for epoch in range(epochs):
        epoch_started = time.time()
        model.train()
        shuffled = list(train_records)
        random.Random(seed + epoch).shuffle(shuffled)
        losses = []
        for group in batches(shuffled, batch_size):
            raw = collate_ribokinetic(group, host_vocab)
            batch = move_batch(raw, device)
            optimizer.zero_grad(set_to_none=True)
            out = model(
                batch["codon_ids"], batch["pad_mask"],
                host_ids=batch.get("host_ids"), budget=batch.get("budget"),
                utr_ids=batch.get("utr_ids"), active_mechanisms=active,
            )
            loss, _ = ribokinetic_loss(out, batch, config.get("loss_weights"))
            if not torch.isfinite(loss):
                raise RuntimeError(f"non-finite loss at epoch {epoch}")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), float(training.get("gradient_clip", 1.0)))
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
            forward_count += 1
        dev_metrics, _, dev_forwards = evaluate(
            model, dev_records, host_vocab, active, task, batch_size, device
        )
        forward_count += dev_forwards
        selected = float(dev_metrics[selection_metric])
        row = {
            "epoch": epoch,
            "train_loss": float(np.mean(losses)),
            "dev": dev_metrics,
            "seconds": time.time() - epoch_started,
        }
        history.append(row)
        if selected < best_value:
            best_value = selected
            best_epoch = epoch
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    if best_state is None:
        raise RuntimeError("no checkpoint selected")
    model.load_state_dict(best_state)
    model.to(device)
    checkpoint_path = output / "best.pt"
    checkpoint = {
        "state_dict": best_state,
        "model_config": vars(model_config),
        "active_mechanisms": active,
        "host_vocabulary": host_vocab,
        "normalizer": normalizer.to_dict() if normalizer else None,
        "selected_epoch": best_epoch,
        "selection_metric": selection_metric,
        "selected_dev_value": best_value,
        "data_sha256": file_sha256(args.data),
        "config_sha256": file_sha256(str(config_path)),
        "task": task,
        "scope": "SUPERVISED_RK08_NOT_GENERATOR",
    }
    torch.save(checkpoint, checkpoint_path)
    metrics = {}
    predictions = []
    final_forwards = 0
    for split in config.get("include_splits", ["train", "dev", "test"]):
        split_records = [r for r in records if r.split == split]
        if not split_records:
            continue
        split_metrics, split_predictions, count = evaluate(
            model, split_records, host_vocab, active, task, batch_size, device
        )
        metrics[split] = split_metrics
        predictions.extend(split_predictions)
        final_forwards += count
    forward_count += final_forwards
    atomic_json(output / "history.json", history)
    atomic_json(output / "metrics.json", metrics)
    write_predictions(output / "predictions.csv", predictions)
    resolved = dict(config)
    resolved["active_mechanisms"] = active
    resolved["host_vocabulary"] = host_vocab
    resolved["normalizer"] = normalizer.to_dict() if normalizer else None
    resolved["data_sha256"] = file_sha256(args.data)
    resolved["config_sha256"] = file_sha256(str(config_path))
    atomic_json(output / "resolved_config.json", resolved)
    elapsed = time.time() - started
    summary = {
        "status": "PASS_PENDING_INDEPENDENT_VERIFICATION",
        "scope": "FULL_DATA_MECHANISM_ABLATION_PENDING_PAIRED_COMPARISON" if config.get("max_rows_per_split") is None else "REAL_DATA_SMOKE_NOT_MECHANISM_VALIDATION",
        "task": task,
        "ablation": config.get("ablation", "all"),
        "active_mechanisms": active,
        "rows": {split: sum(r.split == split for r in records) for split in sorted({r.split for r in records})},
        "selected_epoch": best_epoch,
        "selection_rule": f"minimum dev {selection_metric}; no test/OOD selection",
        "metrics": metrics,
        "training": {
            "epochs_completed": epochs,
            "batch_size": batch_size,
            "optimizer": "AdamW",
            "lr": float(training.get("lr", 1e-3)),
            "weight_decay": float(training.get("weight_decay", 0.0)),
            "seed": seed,
            "forward_passes": forward_count,
            "elapsed_seconds": elapsed,
        },
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "device": str(device),
            "cuda_available": torch.cuda.is_available(),
            "gpu": torch.cuda.get_device_name(0) if device.type == "cuda" else None,
            "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
            "matmul_precision": torch.get_float32_matmul_precision(),
            "sdp_backends": {
                "flash": torch.backends.cuda.flash_sdp_enabled(),
                "mem_efficient": torch.backends.cuda.mem_efficient_sdp_enabled(),
                "math": torch.backends.cuda.math_sdp_enabled(),
            },
        },
        "hashes": {
            "data_sha256": file_sha256(args.data),
            "config_sha256": file_sha256(str(config_path)),
            "script_sha256": file_sha256(str(Path(__file__).resolve())),
            "checkpoint_sha256": file_sha256(str(checkpoint_path)),
        },
        "artifacts": {
            "checkpoint": str(checkpoint_path),
            "metrics": str(output / "metrics.json"),
            "history": str(output / "history.json"),
            "predictions": str(output / "predictions.csv"),
        },
        "forbidden_claims": [
            "no mechanism increment or SOTA claim from a smoke run",
            "no fixed-protein synonymous mechanism claim from cross-protein data",
            "no CodonFlow-RK generator or flow validation",
            "functional untouched was not read or evaluated",
        ],
    }
    atomic_json(output / "run_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
