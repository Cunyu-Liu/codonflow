#!/usr/bin/env python3
"""Frozen RiboMIMO Mohammad16 -> Subtelny14 study-OOD evaluation.

The official architecture, loss, optimizer and validation-R2 checkpoint rule are
kept. A protocol wrapper supplies a source-only train/validation split and does
not evaluate the target study during training. A source-fitted ridge and a
constant baseline are evaluated on exactly the same target positions.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import time
from types import SimpleNamespace

import numpy as np

SOURCE_FILES = ("runRiboMIMO.py", "model.py", "utils.py", "getSaliency.py")
REPLACEMENTS = [
    ("model.py", "list_seq = np.array(list_seq)", "list_seq = np.array(list_seq, dtype=object)", "NumPy >=2 rejects ragged codon lists"),
    ("model.py", "list_density = np.array(list_density)", "list_density = np.array(list_density, dtype=object)", "NumPy >=2 rejects ragged density lists"),
    ("model.py", "self.density = np.array(density)", "self.density = np.array(density, dtype=object)", "evaluation/training densities are ragged before padding"),
    ("model.py", "self.x_input = np.array(x_input)", "self.x_input = np.array(x_input, dtype=object)", "model inputs are ragged before padding"),
    ("model.py", "self.density_level = np.array(density_level)", "self.density_level = np.array(density_level, dtype=object)", "classification targets are ragged before padding"),
    ("runRiboMIMO.py", "data_pad = np.array(data_pad)", "data_pad = np.array(data_pad, dtype=float)", "ragged compatibility containers require explicit numeric dtype after padding"),
    ("model.py", "x = pack_padded_sequence(x, length, batch_first=True)", "x = pack_padded_sequence(x, length.cpu(), batch_first=True)", "modern PyTorch requires a CPU int64 lengths tensor"),
]


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def dump_json(path: str | Path, value: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def finite_or_none(value: float) -> float | None:
    value = float(value)
    return value if math.isfinite(value) else None


def aggregate_or_none(values: np.ndarray, statistic: str) -> float | None:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if not len(values):
        return None
    if statistic == "mean":
        return float(np.mean(values))
    if statistic == "median":
        return float(np.median(values))
    raise ValueError(statistic)


def apply_replacements(source: Path, destination: Path) -> list[dict]:
    destination.mkdir(parents=True, exist_ok=False)
    for filename in SOURCE_FILES:
        shutil.copy2(source / filename, destination / filename)
    applied = []
    for filename, old, new, reason in REPLACEMENTS:
        path = destination / filename
        text = path.read_text()
        if text.count(old) != 1:
            raise ValueError(f"Expected exactly one compatibility target in {filename}: {old!r}")
        path.write_text(text.replace(old, new))
        applied.append({"file": filename, "old": old, "new": new, "reason": reason})
    return applied


def unified_diff(source: Path, runtime: Path) -> str:
    chunks = []
    for filename in SOURCE_FILES:
        before = (source / filename).read_text().splitlines(keepends=True)
        after = (runtime / filename).read_text().splitlines(keepends=True)
        chunks.extend(difflib.unified_diff(before, after, fromfile=f"official/{filename}", tofile=f"study_ood/{filename}"))
    return "".join(chunks)


def parse_three_line_matrix(path: str | Path, study: str) -> list[tuple[str, str, str]]:
    lines = Path(path).read_text().splitlines()
    if len(lines) % 3:
        raise ValueError(f"Matrix line count is not divisible by three: {path}")
    rows = []
    seen = set()
    for index in range(len(lines) // 3):
        header, sequence, counts = lines[3 * index:3 * index + 3]
        if not header.startswith(">"):
            raise ValueError(f"Invalid header at record {index}: {path}")
        original_id = header[1:].split()[0]
        record_id = f"{study}|{original_id}"
        if record_id in seen:
            raise ValueError(f"Duplicate prefixed raw record ID: {record_id}")
        seen.add(record_id)
        codons = sequence.split()
        if not codons or any(len(codon) != 3 for codon in codons):
            raise ValueError(f"Invalid codon row: {record_id}")
        if len(counts.split()) != len(codons):
            raise ValueError(f"Count/codon length mismatch: {record_id}")
        rows.append((record_id, " ".join(codons), " ".join(counts.split())))
    return rows


def build_combined_matrix(protocol: dict, destination: Path) -> dict:
    rows = []
    per_study = {}
    for key, role in (("source_matrix", "source"), ("target_matrix", "target")):
        spec = protocol["studies"][key]
        path = Path(spec["path"])
        if sha256(path) != spec["sha256"]:
            raise ValueError(f"Raw matrix hash mismatch: {path}")
        study = protocol["studies"][role]
        study_rows = parse_three_line_matrix(path, study)
        if len(study_rows) != spec["raw_records"]:
            raise ValueError(f"Raw count mismatch for {study}: {len(study_rows)}")
        per_study[study] = len(study_rows)
        rows.extend(study_rows)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w") as handle:
        for record_id, sequence, counts in rows:
            handle.write(f">{record_id}\n{sequence}\n{counts}\n")
    return {"records": per_study, "path": str(destination), "sha256": sha256(destination)}


def source_train_valid(source_ids: list[str], seed: int) -> tuple[list[str], list[str], int]:
    """Reproduce the official random seed/split and 10% source validation rule."""
    ids = np.array(sorted(source_ids), dtype=object)
    np.random.seed(seed)
    split_seed = int(np.random.randint(0, 1024, 1)[0])
    np.random.seed(split_seed)
    np.random.shuffle(ids)
    n_valid = len(ids) // 10
    valid = ids[:n_valid].tolist()
    train = ids[n_valid:].tolist()
    if not train or not valid or set(train) & set(valid):
        raise AssertionError("Invalid source train/validation split")
    return train, valid, split_seed


def official_masked_values(density: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(density, dtype=np.float64).copy()
    values[:5] = 0
    values[-4:] = 0
    mask = values > 0
    return values[mask].astype(np.float32), np.flatnonzero(mask).astype(np.int32)


def position_features(codon_onehot: np.ndarray) -> np.ndarray:
    codon_onehot = np.asarray(codon_onehot, dtype=np.float64)
    if codon_onehot.ndim != 2 or codon_onehot.shape[1] != 64:
        raise ValueError(f"Expected [n,64] codon one-hot, got {codon_onehot.shape}")
    n = codon_onehot.shape[0]
    if n < 1:
        raise ValueError("Empty sequence")
    bins = np.minimum((np.arange(n) * 20) // max(n - 1, 1), 19)
    relative_position = np.arange(n, dtype=np.float64) / max(n - 1, 1)
    relative = np.eye(20, dtype=np.float64)[bins]
    log_length = np.full((n, 1), math.log(n) / 7.0, dtype=np.float64)
    return np.concatenate([codon_onehot, relative, relative_position[:, None], log_length], axis=1)


def labels_for_ids(data, record_ids: list[str]) -> dict[str, np.ndarray]:
    offsets = [0]
    positions, targets, hashes = [], [], []
    for record_id in record_ids:
        target, position = official_masked_values(data.dict_density[record_id])
        positions.append(position)
        targets.append(target)
        hashes.append(text_sha256(data.dict_seq[record_id]))
        offsets.append(offsets[-1] + len(target))
    return {
        "record_ids": np.asarray(record_ids),
        "cds_sha256": np.asarray(hashes),
        "offsets": np.asarray(offsets, dtype=np.int64),
        "positions": np.concatenate(positions).astype(np.int32),
        "target": np.concatenate(targets).astype(np.float32),
    }


def fit_ridge_on_source(data, train_ids: list[str], valid_ids: list[str], alpha_grid: list[float]) -> dict:
    from sklearn.linear_model import Ridge

    x_parts, y_parts = [], []
    for record_id in train_ids:
        features = position_features(data.dict_seq_codon[record_id])
        target, positions = official_masked_values(data.dict_density[record_id])
        x_parts.append(features[positions])
        y_parts.append(target.astype(np.float64))
    x_train = np.concatenate(x_parts)
    y_train = np.concatenate(y_parts)
    valid_labels = labels_for_ids(data, valid_ids)
    selection = []
    fitted = {}
    for alpha in alpha_grid:
        model = Ridge(alpha=float(alpha), fit_intercept=True, solver="lsqr", tol=1e-8, max_iter=10000)
        model.fit(x_train, y_train)
        prediction = np.empty(valid_labels["target"].shape, dtype=np.float64)
        for index, record_id in enumerate(valid_ids):
            start, end = valid_labels["offsets"][index:index + 2]
            positions = valid_labels["positions"][start:end]
            prediction[start:end] = model.predict(position_features(data.dict_seq_codon[record_id])[positions])
        metrics = regression_metrics(valid_labels["record_ids"], valid_labels["offsets"], valid_labels["target"], prediction)
        selection.append({"alpha": float(alpha), "validation": metrics})
        fitted[float(alpha)] = (model, prediction)
    chosen = min(range(len(alpha_grid)), key=lambda i: (selection[i]["validation"]["transcript_balanced_mse"], i))
    alpha = float(alpha_grid[chosen])
    return {
        "model": fitted[alpha][0],
        "selected_alpha": alpha,
        "selection": selection,
        "validation_prediction": fitted[alpha][1],
        "validation_labels": valid_labels,
        "train_masked_positions": int(len(y_train)),
        "constant": float(np.mean(y_train, dtype=np.float64)),
    }


def regression_metrics(record_ids: np.ndarray, offsets: np.ndarray, target: np.ndarray, prediction: np.ndarray) -> dict:
    from scipy.stats import pearsonr, spearmanr
    from sklearn.metrics import mean_squared_error, r2_score

    target = np.asarray(target, dtype=np.float64)
    prediction = np.asarray(prediction, dtype=np.float64)
    per_mse, per_pearson, per_spearman = [], [], []
    for index in range(len(record_ids)):
        start, end = int(offsets[index]), int(offsets[index + 1])
        y, p = target[start:end], prediction[start:end]
        per_mse.append(float(np.mean((y - p) ** 2)) if len(y) else float("nan"))
        if len(y) >= 2 and np.std(y) > 0 and np.std(p) > 0:
            per_pearson.append(float(pearsonr(y, p).statistic))
            per_spearman.append(float(spearmanr(y, p).statistic))
        else:
            per_pearson.append(float("nan"))
            per_spearman.append(float("nan"))
    per_mse = np.asarray(per_mse)
    per_pearson = np.asarray(per_pearson)
    per_spearman = np.asarray(per_spearman)
    return {
        "n_transcripts": int(len(record_ids)),
        "n_masked_positions": int(len(target)),
        "n_transcripts_with_pearson": int(np.isfinite(per_pearson).sum()),
        "n_transcripts_with_spearman": int(np.isfinite(per_spearman).sum()),
        "transcript_balanced_mse": aggregate_or_none(per_mse, "mean"),
        "mean_transcript_pearson": aggregate_or_none(per_pearson, "mean"),
        "median_transcript_pearson": aggregate_or_none(per_pearson, "median"),
        "mean_transcript_spearman": aggregate_or_none(per_spearman, "mean"),
        "global_r2": finite_or_none(r2_score(target, prediction)),
        "global_mse": finite_or_none(mean_squared_error(target, prediction)),
        "global_pearson": finite_or_none(pearsonr(target, prediction).statistic) if np.std(target) > 0 and np.std(prediction) > 0 else None,
    }


def transcript_rows(labels: dict[str, np.ndarray], model_prediction: np.ndarray, ridge_prediction: np.ndarray) -> list[dict]:
    from scipy.stats import pearsonr, spearmanr

    rows = []
    for index, record_id in enumerate(labels["record_ids"]):
        start, end = labels["offsets"][index:index + 2]
        y = labels["target"][start:end].astype(np.float64)
        m = model_prediction[start:end].astype(np.float64)
        r = ridge_prediction[start:end].astype(np.float64)
        row = {
            "record_id": str(record_id),
            "cds_sha256": str(labels["cds_sha256"][index]),
            "n_masked_positions": int(end - start),
            "model_mse": float(np.mean((y - m) ** 2)),
            "ridge_mse": float(np.mean((y - r) ** 2)),
            "model_pearson": float("nan"),
            "ridge_pearson": float("nan"),
            "model_spearman": float("nan"),
            "ridge_spearman": float("nan"),
        }
        for name, prediction in (("model", m), ("ridge", r)):
            if len(y) >= 2 and np.std(y) > 0 and np.std(prediction) > 0:
                row[f"{name}_pearson"] = float(pearsonr(y, prediction).statistic)
                row[f"{name}_spearman"] = float(spearmanr(y, prediction).statistic)
        rows.append(row)
    return rows


def paired_inference(rows: list[dict], bootstrap_seed: int, permutation_seed: int, resamples: int) -> list[dict]:
    endpoints = [
        ("transcript_balanced_mse", "model_mse", "ridge_mse", "negative_favors_ribomimo"),
        ("mean_transcript_pearson", "model_pearson", "ridge_pearson", "positive_favors_ribomimo"),
    ]
    boot_rng = np.random.default_rng(bootstrap_seed)
    perm_rng = np.random.default_rng(permutation_seed)
    results = []
    for metric, model_key, ridge_key, direction in endpoints:
        pairs = [(row[model_key], row[ridge_key]) for row in rows if math.isfinite(row[model_key]) and math.isfinite(row[ridge_key])]
        differences = np.asarray([float(a) - float(b) for a, b in pairs], dtype=np.float64)
        n = len(differences)
        if n < 2:
            raise ValueError(f"Insufficient paired transcripts for {metric}")
        observed = float(np.mean(differences))
        boot = np.empty(resamples, dtype=np.float64)
        for index in range(resamples):
            boot[index] = float(np.mean(differences[boot_rng.integers(0, n, n)]))
        absolute = np.abs(differences)
        nonzero = differences != 0
        perm = np.empty(resamples, dtype=np.float64)
        for index in range(resamples):
            flips = perm_rng.choice(np.asarray([-1.0, 1.0]), size=n)
            perm[index] = float(np.mean(differences * flips))
        pvalue = float((1 + np.count_nonzero(np.abs(perm) >= abs(observed))) / (resamples + 1))
        results.append({
            "metric": metric,
            "direction": direction,
            "n_pairs": n,
            "point_delta_ribomimo_minus_ridge": observed,
            "ci95_low": float(np.quantile(boot, 0.025)),
            "ci95_high": float(np.quantile(boot, 0.975)),
            "bootstrap_requested": resamples,
            "bootstrap_valid": resamples,
            "sign_flip_pvalue": pvalue,
            "nonzero_pairs": int(np.count_nonzero(nonzero)),
            "mean_absolute_pair_difference": float(np.mean(absolute)),
        })
    ordered = sorted(range(len(results)), key=lambda i: results[i]["sign_flip_pvalue"])
    running = 0.0
    for rank, index in enumerate(ordered):
        running = max(running, min(1.0, (len(results) - rank) * results[index]["sign_flip_pvalue"]))
        results[index]["holm_pvalue"] = running
    return results


def canonical_arrays_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with np.load(path, allow_pickle=False) as arrays:
        for name in sorted(arrays.files):
            array = np.ascontiguousarray(arrays[name])
            digest.update(name.encode())
            digest.update(array.dtype.str.encode())
            digest.update(json.dumps(array.shape).encode())
            digest.update(array.tobytes())
    return digest.hexdigest()


def checkpoint_tensor_sha256(path: str | Path) -> str:
    import torch
    state = torch.load(path, map_location="cpu", weights_only=True)
    digest = hashlib.sha256()
    for name in sorted(state):
        array = np.ascontiguousarray(state[name].detach().cpu().numpy())
        digest.update(name.encode())
        digest.update(array.dtype.str.encode())
        digest.update(json.dumps(array.shape).encode())
        digest.update(array.tobytes())
    return digest.hexdigest()


def clear_logging() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        handler.close()
        root.removeHandler(handler)


def reset_target_evaluation_logging(path: Path) -> None:
    text = path.read_text()
    if re.search(r", Test,", text):
        raise AssertionError(f"Target/Test was evaluated during source training: {path}")


def execute_seed(protocol: dict, runner, source_ids: list[str], target_ids: list[str], seed: int, output: Path) -> dict:
    import torch

    train_ids, valid_ids, split_seed = source_train_valid(source_ids, seed)
    runner.index_train = np.asarray(train_ids, dtype=object)
    runner.index_valid = np.asarray(valid_ids, dtype=object)
    runner.num_train = len(train_ids)
    runner.get_thresh()
    runner.load_model()
    best_score = -np.inf
    best_epoch = None
    no_improve = 0
    history = []
    training_start = time.perf_counter()
    for epoch in range(protocol["official_model"]["max_epoch"]):
        no_improve += 1
        runner.train_one_epoch(0, 0, epoch)
        runner.scheduler.step()
        valid = runner.evaluate("Valid")
        r2, mse, pearson, auc, aupr, loss_cls = [float(value) for value in valid]
        improved = r2 > best_score
        if improved:
            best_score = r2
            best_epoch = epoch + 1
            runner.save(0, 0)
            no_improve = 0
        history.append({"epoch": epoch + 1, "valid_r2": r2, "valid_mse": mse, "valid_pearson": pearson, "valid_auc": auc, "valid_aupr": aupr, "valid_classification_loss": loss_cls, "checkpoint_saved": improved})
        if no_improve >= protocol["official_model"]["early_stop"]:
            break
    training_seconds = time.perf_counter() - training_start
    if best_epoch is None:
        raise RuntimeError("No source-validation checkpoint was saved")
    checkpoint = Path(runner.save_path) / "best_model_0_0.pth"
    if not checkpoint.is_file():
        raise FileNotFoundError(checkpoint)
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    runner.model.load_state_dict(state)
    reset_target_evaluation_logging(Path(runner.save_path) / "logging.log")

    ridge_start = time.perf_counter()
    ridge = fit_ridge_on_source(runner.data, train_ids, valid_ids, protocol["ridge_baseline"]["alpha_grid"])
    ridge_seconds = time.perf_counter() - ridge_start

    target_start = time.perf_counter()
    runner.index_test = np.asarray(target_ids, dtype=object)
    labels = labels_for_ids(runner.data, target_ids)
    runner.data.get_data_pack(runner.index_test, runner.add_nt, runner.add_aa)
    runner.data.get_data_pack_cls(runner.index_test, runner.threshs)
    model_prediction = np.empty(labels["target"].shape, dtype=np.float32)
    n_batch = int(np.ceil(len(target_ids) / float(runner.batch_size)))
    with torch.no_grad():
        for batch in range(n_batch):
            index = np.arange(batch * runner.batch_size, min((batch + 1) * runner.batch_size, len(target_ids)))
            x_input, length, density, mask_density, _level, batch_index = runner.get_data_batch(index)
            pred_reg, _pred_cls, _ = runner.model(x_input, length)
            pred_np = pred_reg.detach().cpu().numpy()
            density_np = density.detach().cpu().numpy()
            mask_np = mask_density.detach().cpu().numpy()
            for row, original_index in enumerate(batch_index):
                start, end = labels["offsets"][original_index:original_index + 2]
                expected_positions = labels["positions"][start:end]
                observed_positions = np.flatnonzero(mask_np[row]).astype(np.int32)
                if not np.array_equal(expected_positions, observed_positions):
                    raise AssertionError(f"Target mask mismatch for {target_ids[original_index]}")
                expected_target = labels["target"][start:end]
                if not np.array_equal(expected_target, density_np[row][mask_np[row]].astype(np.float32)):
                    raise AssertionError(f"Target density mismatch for {target_ids[original_index]}")
                model_prediction[start:end] = pred_np[row][mask_np[row]].astype(np.float32)
    ridge_prediction = np.empty(labels["target"].shape, dtype=np.float64)
    for index, record_id in enumerate(target_ids):
        start, end = labels["offsets"][index:index + 2]
        positions = labels["positions"][start:end]
        ridge_prediction[start:end] = ridge["model"].predict(position_features(runner.data.dict_seq_codon[record_id])[positions])
    target_seconds = time.perf_counter() - target_start

    model_metrics = regression_metrics(labels["record_ids"], labels["offsets"], labels["target"], model_prediction)
    ridge_metrics = regression_metrics(labels["record_ids"], labels["offsets"], labels["target"], ridge_prediction)
    constant_prediction = np.full(labels["target"].shape, ridge["constant"], dtype=np.float64)
    constant_metrics = regression_metrics(labels["record_ids"], labels["offsets"], labels["target"], constant_prediction)
    rows = transcript_rows(labels, model_prediction, ridge_prediction)
    seed_dir = output / "predictions"
    seed_dir.mkdir(parents=True, exist_ok=True)
    prediction_path = seed_dir / f"subtelny14_seed{seed}.npz"
    np.savez_compressed(prediction_path, **labels, model_prediction=model_prediction, ridge_prediction=ridge_prediction)
    metrics_path = seed_dir / f"subtelny14_seed{seed}_transcript_metrics.csv"
    fieldnames = list(rows[0])
    with metrics_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: ("" if isinstance(value, float) and not math.isfinite(value) else value) for key, value in row.items()})
    official_log = Path(runner.save_path) / "logging.log"
    result = {
        "seed": seed,
        "split_seed": split_seed,
        "source_train_records": len(train_ids),
        "source_validation_records": len(valid_ids),
        "target_records": len(target_ids),
        "source_train_masked_positions_ridge": ridge["train_masked_positions"],
        "best_epoch": best_epoch,
        "epochs_completed": len(history),
        "best_validation_r2": best_score,
        "validation_history": history,
        "training_seconds": training_seconds,
        "ridge_selection_seconds": ridge_seconds,
        "target_evaluation_seconds": target_seconds,
        "ridge_selected_alpha": ridge["selected_alpha"],
        "ridge_validation_selection": ridge["selection"],
        "constant_source_train_mean_density": ridge["constant"],
        "target_metrics": {"ribomimo": model_metrics, "ridge": ridge_metrics, "constant": constant_metrics},
        "official_result_dir": runner.save_path,
        "official_log": str(official_log),
        "official_log_sha256": sha256(official_log),
        "official_config": str(Path(runner.save_path) / "config"),
        "official_config_sha256": sha256(Path(runner.save_path) / "config"),
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": sha256(checkpoint),
        "checkpoint_tensor_sha256": checkpoint_tensor_sha256(checkpoint),
        "checkpoint_parameter_count": int(sum(value.numel() for value in state.values())),
        "target_predictions": str(prediction_path),
        "target_predictions_file_sha256": sha256(prediction_path),
        "target_predictions_arrays_sha256": canonical_arrays_sha256(prediction_path),
        "transcript_metrics_csv": str(metrics_path),
        "transcript_metrics_csv_sha256": sha256(metrics_path),
        "target_evaluated_after_training_and_ridge_selection": True,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    protocol_path = Path(args.protocol).resolve()
    protocol = json.loads(protocol_path.read_text())
    if protocol["status"] != "FROZEN_BEFORE_TRAINING":
        raise ValueError("Protocol is not frozen")
    output = Path(args.output_dir).resolve()
    report_path = Path(args.report).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output directory must be empty: {output}")
    if report_path.exists():
        raise FileExistsError(f"Report exists: {report_path}")
    output.mkdir(parents=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    source = Path(protocol["source"]["path"]).resolve()
    for filename, expected in protocol["source"]["file_sha256"].items():
        if sha256(source / "src" / filename) != expected:
            raise ValueError(f"Official source hash mismatch: {filename}")
    runtime = output / "src"
    replacements = apply_replacements(source / "src", runtime)
    diff_path = output / "official_to_study_ood.diff"
    diff_path.write_text(unified_diff(source / "src", runtime))
    driver_snapshot = output / "driver.py"
    shutil.copy2(Path(__file__).resolve(), driver_snapshot)
    protocol_copy = output / "protocol.copy.json"
    shutil.copy2(protocol_path, protocol_copy)
    combined_path = output / "data" / "StudyOOD_Mohammad16_Subtelny14.txt"
    combined = build_combined_matrix(protocol, combined_path)
    dump_json(output / "compatibility_replacements.json", replacements)
    prepare = {
        "schema_version": "a8-rk05-ribomimo-study-ood-prepare-v1",
        "status": "PREPARED_NOT_TRAINED",
        "protocol": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "combined_matrix": combined,
        "runtime_file_sha256": {name: sha256(runtime / name) for name in SOURCE_FILES},
        "diff_sha256": sha256(diff_path),
        "driver_sha256": sha256(driver_snapshot),
        "replacement_count": len(replacements),
    }
    dump_json(output / "prepare_report.json", prepare)
    print(json.dumps(prepare, indent=2), flush=True)
    if args.prepare_only:
        return

    os.environ.update({
        "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
        "CUDA_VISIBLE_DEVICES": protocol["official_model"]["gpu"],
        "PYTHONHASHSEED": str(protocol["split"]["primary_seed"]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
    })
    import scipy
    import sklearn
    import torch
    sys.path.insert(0, str(runtime))
    previous_cwd = Path.cwd()
    os.chdir(runtime)
    from runRiboMIMO import RiboMIMOModel

    all_seeds = [protocol["split"]["primary_seed"]] + list(protocol["split"]["sensitivity_seeds"])
    runs = []
    execution_start = time.perf_counter()
    try:
        for seed in all_seeds:
            clear_logging()
            np.random.seed(seed)
            torch.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            torch.use_deterministic_algorithms(True)
            torch.set_num_threads(1)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
            official = protocol["official_model"]
            model_args = SimpleNamespace(
                RNN_model=official["RNN_model"], RNN_hidden_dims=official["RNN_hidden_dims"], RNN_depth=official["RNN_depth"],
                add_nt=official["add_nt"], add_aa=official["add_aa"], threshold=official["threshold"], alpha=official["alpha"],
                sim=official["sim"], use_median=official["use_median"], batch_size=official["batch_size"], max_epoch=official["max_epoch"],
                early_stop=official["early_stop"], learning_rate=official["learning_rate"], weight_decay=official["weight_decay"],
                seed=seed, info=f"studyood_seed{seed}", gpu=official["gpu"], dataset=combined_path.stem,
                num_repeat=official["num_repeat"], num_fold=official["num_fold"],
            )
            runner = RiboMIMOModel(model_args)
            source_prefix = protocol["studies"]["source"] + "|"
            target_prefix = protocol["studies"]["target"] + "|"
            source_ids = sorted(str(value) for value in runner.data.list_gene if str(value).startswith(source_prefix))
            target_ids = sorted(str(value) for value in runner.data.list_gene if str(value).startswith(target_prefix))
            if len(source_ids) != protocol["studies"]["source_matrix"]["official_loader_eligible_records"]:
                raise AssertionError(f"Source eligible count mismatch: {len(source_ids)}")
            if len(target_ids) != protocol["studies"]["target_matrix"]["official_loader_eligible_records"]:
                raise AssertionError(f"Target eligible count mismatch: {len(target_ids)}")
            if len(source_ids) + len(target_ids) != len(runner.data.list_gene):
                raise AssertionError("Unexpected records in combined eligible set")
            source_cds = {runner.data.dict_seq[value] for value in source_ids}
            target_cds = {runner.data.dict_seq[value] for value in target_ids}
            overlap = len(source_cds & target_cds)
            if overlap != protocol["studies"]["exact_cds_overlap_required"]:
                raise AssertionError(f"Exact CDS overlap between studies: {overlap}")
            run = execute_seed(protocol, runner, source_ids, target_ids, seed, output)
            run["exact_cds_overlap_source_target"] = overlap
            run["source_unique_cds"] = len(source_cds)
            run["target_unique_cds"] = len(target_cds)
            runs.append(run)
            dump_json(output / f"seed{seed}_report.json", run)
            print(json.dumps({"seed": seed, "status": "COMPLETED", "best_epoch": run["best_epoch"], "target_metrics": run["target_metrics"]}, indent=2), flush=True)
            del runner
            torch.cuda.empty_cache()
    finally:
        clear_logging()
        os.chdir(previous_cwd)
    elapsed = time.perf_counter() - execution_start
    primary_run = runs[0]
    primary_rows = []
    with Path(primary_run["transcript_metrics_csv"]).open(newline="") as handle:
        for raw in csv.DictReader(handle):
            row = dict(raw)
            for key in ("n_masked_positions",):
                row[key] = int(row[key])
            for key in ("model_mse", "ridge_mse", "model_pearson", "ridge_pearson", "model_spearman", "ridge_spearman"):
                row[key] = float(row[key]) if row[key] else float("nan")
            primary_rows.append(row)
    primary_inference = paired_inference(primary_rows, protocol["evaluation"]["bootstrap"]["seed"], protocol["evaluation"]["permutation"]["seed"], protocol["evaluation"]["bootstrap"]["resamples"])
    environment = {
        "python_executable": sys.executable,
        "python": platform.python_version(),
        "torch": torch.__version__, "numpy": np.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__,
        "cuda_available": torch.cuda.is_available(), "cuda_device_count": torch.cuda.device_count(),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "gpu_names": [torch.cuda.get_device_name(index) for index in range(torch.cuda.device_count())],
        "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "cudnn_deterministic": torch.backends.cudnn.deterministic,
        "cudnn_benchmark": torch.backends.cudnn.benchmark,
        "torch_num_threads": torch.get_num_threads(),
    }
    dump_json(output / "environment.json", environment)
    freeze = subprocess_run_pip_freeze(sys.executable)
    (output / "pip_freeze.txt").write_text(freeze)
    report = {
        "schema_version": "a8-rk05-ribomimo-study-ood-v1",
        "task": protocol["task"],
        "status": "PASS_STUDY_OOD_PENDING_INDEPENDENT",
        "source": protocol["source"],
        "studies": protocol["studies"],
        "protocol": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "prepare": prepare,
        "compatibility": {**protocol["compatibility"], "diff_path": str(diff_path), "diff_sha256": sha256(diff_path)},
        "runs": runs,
        "primary_seed": protocol["split"]["primary_seed"],
        "primary_comparisons": primary_inference,
        "execution": {**protocol["execution"], "wall_seconds_all_seeds": elapsed},
        "environment": environment,
        "artifacts": {
            "driver": {"path": str(driver_snapshot), "sha256": sha256(driver_snapshot)},
            "protocol_copy": {"path": str(protocol_copy), "sha256": sha256(protocol_copy)},
            "combined_matrix": {"path": str(combined_path), "sha256": sha256(combined_path)},
            "prepare_report": {"path": str(output / "prepare_report.json"), "sha256": sha256(output / "prepare_report.json")},
            "environment": {"path": str(output / "environment.json"), "sha256": sha256(output / "environment.json")},
            "pip_freeze": {"path": str(output / "pip_freeze.txt"), "sha256": sha256(output / "pip_freeze.txt")},
        },
        "scientific_scope": protocol["scientific_scope"],
        "limitations": [
            "Official normalized ribosome occupancy is not a direct physical elongation-rate measurement.",
            "Mohammad16 to Subtelny14 is an exact-CDS-disjoint cross-study evaluation, not a homology-aware protein OOD claim.",
            "The primary result uses the official default seed; the two additional seeds are sensitivity analyses and are not selected by target performance.",
            "Subtelny14 was used in prior RiboKinetic/ridge experiments, so this is not a globally untouched confirmatory dataset.",
            "Shared-GPU wall times are recorded but do not constitute unified time-matched cost evidence.",
            "No functional OOD, generator authorization, RK-G1 change or SOTA conclusion follows from this baseline evaluation."
        ],
    }
    dump_json(report_path, report)
    dump_json(output / "production_report.copy.json", report)
    print(json.dumps({"status": report["status"], "report": str(report_path), "primary_comparisons": primary_inference, "wall_seconds": elapsed}, indent=2), flush=True)


def subprocess_run_pip_freeze(python: str) -> str:
    import subprocess
    return subprocess.run([python, "-m", "pip", "freeze"], check=True, capture_output=True, text=True).stdout


if __name__ == "__main__":
    main()
