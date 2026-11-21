#!/usr/bin/env python3
"""RK37 frozen Mohammad16 -> Subtelny14 local-sequence/calibration diagnostic."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

import numpy as np
from scipy import sparse
from scipy.stats import rankdata
from sklearn.linear_model import Ridge

OFFSETS = (-3, -2, -1, 0, 1, 2, 3)
CODON_TO_INDEX = {
    first + second + third: index
    for index, (first, second, third) in enumerate(
        (a, b, c) for a in "ATCG" for b in "ATCG" for c in "ATCG"
    )
}
ARM_NAMES = (
    "constant",
    "ribomimo_raw",
    "ribomimo_anchored",
    "position_raw_unanchored",
    "position_raw_anchored",
    "position_centered_anchored",
    "local_raw_anchored",
    "local_centered_anchored",
)


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dump_json(path: str | Path, value: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def finite(value: float) -> float | None:
    value = float(value)
    return value if math.isfinite(value) else None


def parse_matrix(path: Path, study: str) -> tuple[dict, int]:
    """Parse sequence and coverage metadata; normalized density is materialized separately."""
    lines = path.read_text().splitlines()
    if len(lines) % 3:
        raise ValueError(f"Matrix line count is not divisible by three: {path}")
    records = {}
    for index in range(len(lines) // 3):
        header, sequence_row, count_row = lines[3 * index:3 * index + 3]
        if not header.startswith(">"):
            raise ValueError(f"Invalid header at record {index}")
        record_id = f"{study}|{header[1:].split()[0]}"
        if record_id in records:
            raise ValueError(f"Duplicate ID: {record_id}")
        codons = tuple(sequence_row.split())
        counts = np.asarray([float(value) for value in count_row.split()], dtype=np.float64)
        if not codons or any(len(codon) != 3 for codon in codons) or len(codons) != len(counts):
            raise ValueError(f"Invalid sequence/count row: {record_id}")
        positive = counts > 0.5
        coverage = float(np.mean(positive))
        cds = "".join(codons)
        if coverage <= 0.6 or "N" in cds:
            continue
        records[record_id] = {
            "codons": codons,
            "cds": cds,
            "counts": counts,
            "coverage": coverage,
            "density": None,
        }
    return records, len(lines) // 3


def materialize_density(records: dict) -> None:
    for record_id, record in records.items():
        counts = record["counts"]
        positive = counts > 0.5
        if not np.any(positive):
            raise ValueError(f"Eligible record has empty normalization: {record_id}")
        average = float(np.mean(counts[positive]))
        record["density"] = positive * counts / average


def masked(record: dict) -> tuple[np.ndarray, np.ndarray]:
    if record["density"] is None:
        raise AssertionError("Normalized outcome accessed before materialization phase")
    density = record["density"].copy()
    density[:5] = 0
    density[-4:] = 0
    positions = np.flatnonzero(density > 0).astype(np.int32)
    return density[positions].astype(np.float32), positions


def feature_matrix(codons: list[str] | tuple[str, ...], kind: str) -> sparse.csr_matrix:
    n = len(codons)
    if n < 1:
        raise ValueError("Empty CDS")
    if kind == "position":
        result = np.zeros((n, 86), dtype=np.float64)
        for position, codon in enumerate(codons):
            result[position, CODON_TO_INDEX[codon]] = 1.0
        position_offset = 64
    elif kind == "local":
        result = np.zeros((n, 477), dtype=np.float64)
        for position in range(n):
            for offset_index, offset in enumerate(OFFSETS):
                source = position + offset
                if 0 <= source < n:
                    result[position, offset_index * 64 + CODON_TO_INDEX[codons[source]]] = 1.0
                    result[position, 448 + offset_index] = 1.0
        position_offset = 455
    else:
        raise ValueError(kind)
    for position in range(n):
        relative = position / max(n - 1, 1)
        position_bin = min(19, int(relative * 20))
        result[position, position_offset + position_bin] = 1.0
        result[position, position_offset + 20] = relative
        result[position, position_offset + 21] = math.log(n) / 7.0
    return sparse.csr_matrix(result)


def split_source(ids: list[str], seed: int) -> tuple[list[str], list[str], int]:
    ordered = np.asarray(sorted(ids), dtype=object)
    np.random.seed(seed)
    split_seed = int(np.random.randint(0, 1024, 1)[0])
    np.random.seed(split_seed)
    np.random.shuffle(ordered)
    n_valid = len(ordered) // 10
    train, valid = ordered[n_valid:].tolist(), ordered[:n_valid].tolist()
    if not train or not valid or set(train) & set(valid):
        raise AssertionError("Invalid source split")
    return train, valid, split_seed


def labels_for_ids(records: dict, ids: list[str]) -> dict[str, np.ndarray]:
    offsets = [0]
    position_arrays, target_arrays = [], []
    for record_id in ids:
        target, positions = masked(records[record_id])
        target_arrays.append(target)
        position_arrays.append(positions)
        offsets.append(offsets[-1] + len(target))
    return {
        "record_ids": np.asarray(ids),
        "offsets": np.asarray(offsets, dtype=np.int64),
        "positions": np.concatenate(position_arrays).astype(np.int32),
        "target": np.concatenate(target_arrays).astype(np.float32),
    }


def center_labels(labels: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    centered = labels["target"].astype(np.float64).copy()
    for index in range(len(labels["record_ids"])):
        start, end = labels["offsets"][index:index + 2]
        centered[start:end] -= float(np.mean(centered[start:end], dtype=np.float64))
    return {**labels, "target": centered}


def anchor_prediction(labels: dict[str, np.ndarray], prediction: np.ndarray, source_mean: float) -> np.ndarray:
    anchored = np.asarray(prediction, dtype=np.float64).copy()
    if anchored.shape != labels["target"].shape:
        raise ValueError("Prediction/label shape mismatch")
    for index in range(len(labels["record_ids"])):
        start, end = labels["offsets"][index:index + 2]
        anchored[start:end] += float(source_mean) - float(np.mean(anchored[start:end], dtype=np.float64))
    return anchored


def design_for_ids(records: dict, labels: dict[str, np.ndarray], kind: str) -> sparse.csr_matrix:
    blocks = []
    for index, record_id in enumerate(labels["record_ids"]):
        start, end = labels["offsets"][index:index + 2]
        positions = labels["positions"][start:end]
        blocks.append(feature_matrix(records[str(record_id)]["codons"], kind)[positions])
    return sparse.vstack(blocks, format="csr", dtype=np.float64)


def per_transcript(labels: dict[str, np.ndarray], prediction: np.ndarray) -> dict[str, np.ndarray]:
    target = labels["target"].astype(np.float64)
    prediction = np.asarray(prediction, dtype=np.float64)
    if prediction.shape != target.shape or not np.all(np.isfinite(prediction)):
        raise ValueError("Invalid predictions")
    mse, pearson, spearman = [], [], []
    for index in range(len(labels["record_ids"])):
        start, end = labels["offsets"][index:index + 2]
        y, p = target[start:end], prediction[start:end]
        mse.append(float(np.mean((y - p) ** 2)))
        if len(y) >= 2 and np.std(y) > 0 and np.std(p) > 0:
            pearson.append(float(np.mean((y - np.mean(y)) * (p - np.mean(p))) / (np.std(y) * np.std(p))))
            ry, rp = rankdata(y), rankdata(p)
            spearman.append(float(np.mean((ry - np.mean(ry)) * (rp - np.mean(rp))) / (np.std(ry) * np.std(rp))))
        else:
            pearson.append(float("nan"))
            spearman.append(float("nan"))
    return {"mse": np.asarray(mse), "pearson": np.asarray(pearson), "spearman": np.asarray(spearman)}


def summarize(labels: dict[str, np.ndarray], per: dict[str, np.ndarray]) -> dict:
    y = labels["target"].astype(np.float64)
    # Reconstructing predictions is unnecessary; global metrics are added by summarize_prediction.
    def aggregate(values, statistic="mean"):
        values = values[np.isfinite(values)]
        if not len(values):
            return None
        return float(np.mean(values) if statistic == "mean" else np.median(values))
    return {
        "n_transcripts": int(len(labels["record_ids"])),
        "n_masked_positions": int(len(y)),
        "n_transcripts_with_pearson": int(np.isfinite(per["pearson"]).sum()),
        "n_transcripts_with_spearman": int(np.isfinite(per["spearman"]).sum()),
        "transcript_balanced_mse": aggregate(per["mse"]),
        "mean_transcript_pearson": aggregate(per["pearson"]),
        "median_transcript_pearson": aggregate(per["pearson"], "median"),
        "mean_transcript_spearman": aggregate(per["spearman"]),
    }


def summarize_prediction(labels: dict[str, np.ndarray], prediction: np.ndarray) -> tuple[dict, dict]:
    per = per_transcript(labels, prediction)
    result = summarize(labels, per)
    y = labels["target"].astype(np.float64)
    p = np.asarray(prediction, dtype=np.float64)
    result["global_mse"] = float(np.mean((y - p) ** 2))
    result["global_r2"] = float(1 - np.sum((y - p) ** 2) / np.sum((y - np.mean(y)) ** 2))
    result["global_pearson"] = finite(np.mean((y - np.mean(y)) * (p - np.mean(p))) / (np.std(y) * np.std(p))) if np.std(y) > 0 and np.std(p) > 0 else None
    return result, per


def select_candidate(candidates: list[dict], deployment: str) -> dict:
    if deployment not in {"raw", "anchored"}:
        raise ValueError(deployment)
    key = "validation_raw" if deployment == "raw" else "validation_anchored"
    index = min(range(len(candidates)), key=lambda i: (candidates[i][key]["transcript_balanced_mse"], i))
    return candidates[index]


def paired_effect(candidate_per: dict, baseline_per: dict, metric: str, improvement: bool) -> tuple[np.ndarray, int]:
    valid = np.isfinite(candidate_per[metric]) & np.isfinite(baseline_per[metric])
    if improvement:
        effect = baseline_per[metric][valid] - candidate_per[metric][valid]
    else:
        effect = candidate_per[metric][valid] - baseline_per[metric][valid]
    return np.asarray(effect, dtype=np.float64), int(len(effect))


def endpoint_pass(endpoint: dict) -> bool:
    return bool(endpoint["effect"] > 0 and endpoint["ci95_low"] > 0 and endpoint["holm_pvalue"] < 0.05)


def apply_holm(endpoints: list[dict]) -> list[dict]:
    adjusted = [dict(endpoint) for endpoint in endpoints]
    order = sorted(range(len(adjusted)), key=lambda i: adjusted[i]["sign_flip_pvalue"])
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(adjusted) - rank) * adjusted[index]["sign_flip_pvalue"]))
        adjusted[index]["holm_pvalue"] = running
    return adjusted


def sensitivity_pass(*effect_lists: list[float]) -> bool:
    return bool(effect_lists) and all(float(value) > 0 for values in effect_lists for value in values)


def infer_endpoint(name: str, effect: np.ndarray, bootstrap_seed: int, permutation_seed: int, resamples: int) -> tuple[dict, dict]:
    if len(effect) < 2 or not np.all(np.isfinite(effect)):
        raise ValueError(f"Insufficient finite effects for {name}")
    boot_rng = np.random.default_rng(bootstrap_seed)
    perm_rng = np.random.default_rng(permutation_seed)
    boot = np.empty(resamples, dtype=np.float64)
    perm = np.empty(resamples, dtype=np.float64)
    for index in range(resamples):
        boot[index] = float(np.mean(effect[boot_rng.integers(0, len(effect), len(effect))]))
        perm[index] = float(np.mean(effect * perm_rng.choice(np.asarray([-1.0, 1.0]), size=len(effect))))
    observed = float(np.mean(effect))
    pvalue = float((1 + np.count_nonzero(np.abs(perm) >= abs(observed))) / (resamples + 1))
    report = {
        "name": name,
        "n_pairs": int(len(effect)),
        "effect": observed,
        "ci95_low": float(np.quantile(boot, 0.025)),
        "ci95_high": float(np.quantile(boot, 0.975)),
        "sign_flip_pvalue": pvalue,
        "resamples": int(resamples),
    }
    arrays = {
        f"{name}_effect": effect,
        f"{name}_bootstrap": boot,
        f"{name}_sign_flip": perm,
    }
    return report, arrays


def assert_fit_accounting(actual: int, planned: int) -> None:
    if actual != planned:
        raise ValueError(f"Fit accounting failed: actual={actual}, planned={planned}")


def public_candidate(candidate: dict) -> dict:
    return {
        "alpha": candidate["alpha"],
        "validation_raw": candidate["validation_raw"],
        "validation_anchored": candidate["validation_anchored"],
        "fit_seconds": candidate["fit_seconds"],
    }


def fit_source_seed(protocol: dict, source_records: dict, seed: int, output: Path) -> tuple[dict, dict, int]:
    source_ids = sorted(source_records)
    train_ids, valid_ids, split_seed = split_source(source_ids, seed)
    if len(train_ids) != protocol["split"]["expected_train_records"] or len(valid_ids) != protocol["split"]["expected_validation_records"]:
        raise AssertionError("Source split size mismatch")
    train_labels = labels_for_ids(source_records, train_ids)
    valid_labels = labels_for_ids(source_records, valid_ids)
    train_centered = center_labels(train_labels)
    source_mean = float(np.mean(train_labels["target"], dtype=np.float64))
    split_record = {
        "seed": seed,
        "split_seed": split_seed,
        "train_ids": train_ids,
        "validation_ids": valid_ids,
        "train_masked_positions": int(len(train_labels["target"])),
        "validation_masked_positions": int(len(valid_labels["target"])),
        "source_train_raw_masked_mean": source_mean,
    }
    split_path = output / "splits" / f"source_split_seed{seed}.json"
    dump_json(split_path, split_record)
    split_record["split_report_sha256"] = sha256(split_path)

    fits = {}
    candidate_reports = {}
    fit_count = 0
    for kind in ("position", "local"):
        x_train = design_for_ids(source_records, train_labels, kind)
        x_valid = design_for_ids(source_records, valid_labels, kind)
        for target_mode, current_train in (("raw", train_labels), ("centered", train_centered)):
            candidates = []
            for alpha in protocol["models"]["alpha_grid"]:
                start = time.perf_counter()
                model = Ridge(alpha=float(alpha), fit_intercept=True, solver="lsqr", tol=1e-8, max_iter=10000)
                model.fit(x_train, current_train["target"].astype(np.float64))
                raw_prediction = model.predict(x_valid)
                anchored_prediction = anchor_prediction(valid_labels, raw_prediction, source_mean)
                raw_metrics, _ = summarize_prediction(valid_labels, raw_prediction)
                anchored_metrics, _ = summarize_prediction(valid_labels, anchored_prediction)
                candidates.append({
                    "alpha": float(alpha),
                    "model": model,
                    "validation_raw_prediction": raw_prediction,
                    "validation_anchored_prediction": anchored_prediction,
                    "validation_raw": raw_metrics,
                    "validation_anchored": anchored_metrics,
                    "fit_seconds": time.perf_counter() - start,
                })
                fit_count += 1
            fits[(kind, target_mode)] = candidates
            candidate_reports[f"{kind}_{target_mode}"] = [public_candidate(value) for value in candidates]
        del x_train, x_valid

    selected = {
        "position_raw_unanchored": select_candidate(fits[("position", "raw")], "raw"),
        "position_raw_anchored": select_candidate(fits[("position", "raw")], "anchored"),
        "position_centered_anchored": select_candidate(fits[("position", "centered")], "anchored"),
        "local_raw_anchored": select_candidate(fits[("local", "raw")], "anchored"),
        "local_centered_anchored": select_candidate(fits[("local", "centered")], "anchored"),
    }
    expected_alpha = float(protocol["models"]["expected_position_raw_unanchored_alpha"][str(seed)])
    if selected["position_raw_unanchored"]["alpha"] != expected_alpha:
        raise AssertionError(f"RK05 baseline alpha mismatch for seed {seed}")
    state = {
        "seed": seed,
        "split": split_record,
        "source_mean": source_mean,
        "train_labels": train_labels,
        "selected": selected,
        "candidate_reports": candidate_reports,
        "fit_count": fit_count,
    }
    report = {
        "seed": seed,
        "split": split_record,
        "fit_count": fit_count,
        "candidates": candidate_reports,
        "selected_alpha": {name: value["alpha"] for name, value in selected.items()},
    }
    return state, report, fit_count


def arrays_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with np.load(path, allow_pickle=False) as arrays:
        for name in sorted(arrays.files):
            array = np.ascontiguousarray(arrays[name])
            digest.update(name.encode())
            digest.update(array.dtype.str.encode())
            digest.update(json.dumps(array.shape).encode())
            digest.update(array.tobytes())
    return digest.hexdigest()


def evaluate_seed(protocol: dict, state: dict, target_records: dict, target_labels: dict, target_design: dict, output: Path) -> tuple[dict, dict]:
    seed = state["seed"]
    selected = state["selected"]
    source_mean = state["source_mean"]
    predictions = {"constant": np.full(target_labels["target"].shape, source_mean, dtype=np.float64)}
    raw_new = {}
    for name in ARM_NAMES[3:]:
        candidate = selected[name]
        kind = "position" if name.startswith("position") else "local"
        raw = candidate["model"].predict(target_design[kind])
        raw_new[name] = raw
        predictions[name] = raw if name == "position_raw_unanchored" else anchor_prediction(target_labels, raw, source_mean)

    old_path = Path(protocol["frozen_external_predictions"]["prediction_template"].format(seed=seed))
    with np.load(old_path, allow_pickle=False) as old:
        for key in ("record_ids", "offsets", "positions", "target"):
            if not np.array_equal(old[key], target_labels[key]):
                raise AssertionError(f"RK05 target identity mismatch: {key}")
        ribomimo = old[protocol["frozen_external_predictions"]["arrays"]["ribomimo"]].astype(np.float64)
        old_ridge = old[protocol["frozen_external_predictions"]["arrays"]["position_ridge"]].astype(np.float64)
    baseline_difference = float(np.max(np.abs(predictions["position_raw_unanchored"] - old_ridge)))
    if baseline_difference > 1e-6:
        raise AssertionError(f"RK05 ridge prediction fidelity failed: {baseline_difference}")
    predictions["ribomimo_raw"] = ribomimo
    predictions["ribomimo_anchored"] = anchor_prediction(target_labels, ribomimo, source_mean)

    metrics, per_arm = {}, {}
    for name in ARM_NAMES:
        metrics[name], per_arm[name] = summarize_prediction(target_labels, predictions[name])
    candidate_per = per_arm["local_centered_anchored"]
    mse_effect, n_mse = paired_effect(candidate_per, per_arm["constant"], "mse", True)
    pearson_effect, n_pearson = paired_effect(candidate_per, per_arm["position_raw_unanchored"], "pearson", False)
    effects = {
        "tb_mse_improvement_over_constant": float(np.mean(mse_effect)),
        "mean_pearson_improvement_over_position_raw": float(np.mean(pearson_effect)),
    }
    seed_dir = output / "predictions"
    seed_dir.mkdir(parents=True, exist_ok=True)
    prediction_path = seed_dir / f"subtelny14_seed{seed}.npz"
    np.savez_compressed(
        prediction_path,
        **target_labels,
        **{f"prediction_{name}": predictions[name] for name in ARM_NAMES},
        **{f"raw_new_{name}": value for name, value in raw_new.items()},
        effect_tb_mse_improvement=mse_effect,
        effect_mean_pearson_improvement=pearson_effect,
    )
    model_path = seed_dir / f"source_models_seed{seed}.npz"
    model_arrays = {}
    for name, candidate in selected.items():
        model_arrays[f"coef_{name}"] = np.asarray(candidate["model"].coef_, dtype=np.float64)
        model_arrays[f"intercept_{name}"] = np.asarray(candidate["model"].intercept_, dtype=np.float64)
        model_arrays[f"alpha_{name}"] = np.asarray(candidate["alpha"], dtype=np.float64)
    model_arrays["source_train_raw_masked_mean"] = np.asarray(source_mean, dtype=np.float64)
    np.savez_compressed(model_path, **model_arrays)

    csv_path = seed_dir / f"subtelny14_seed{seed}_transcript_metrics.csv"
    fieldnames = ["record_id", "n_masked_positions"]
    for name in ARM_NAMES:
        fieldnames.extend([f"{name}_mse", f"{name}_pearson", f"{name}_spearman"])
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, record_id in enumerate(target_labels["record_ids"]):
            start, end = target_labels["offsets"][index:index + 2]
            row = {"record_id": str(record_id), "n_masked_positions": int(end - start)}
            for name in ARM_NAMES:
                for metric in ("mse", "pearson", "spearman"):
                    value = float(per_arm[name][metric][index])
                    row[f"{name}_{metric}"] = value if math.isfinite(value) else ""
            writer.writerow(row)
    report = {
        "seed": seed,
        "selected_alpha": {name: value["alpha"] for name, value in selected.items()},
        "source_train_raw_masked_mean": source_mean,
        "target_metrics": metrics,
        "primary_effects": effects,
        "primary_effect_n": {"tb_mse": n_mse, "mean_pearson": n_pearson},
        "rk05_baseline_max_absolute_prediction_difference": baseline_difference,
        "rk05_prediction_file": str(old_path),
        "rk05_prediction_file_sha256": sha256(old_path),
        "artifacts": {
            "predictions": {"path": str(prediction_path), "sha256": sha256(prediction_path), "arrays_sha256": arrays_sha256(prediction_path)},
            "source_models": {"path": str(model_path), "sha256": sha256(model_path), "arrays_sha256": arrays_sha256(model_path)},
            "transcript_metrics": {"path": str(csv_path), "sha256": sha256(csv_path)},
        },
    }
    return report, {"effects": effects, "mse_effect": mse_effect, "pearson_effect": pearson_effect}


def frozen_git_commit(paths: list[Path]) -> tuple[str, str]:
    root = Path.cwd()
    relative = [str(path.resolve().relative_to(root)) for path in paths]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    for path, rel in zip(paths, relative):
        committed = subprocess.check_output(["git", "show", f"{commit}:{rel}"])
        if committed != path.read_bytes():
            raise AssertionError(f"Frozen file differs from HEAD: {rel}")
    dirty = subprocess.check_output(["git", "diff", "HEAD", "--"] + relative)
    if dirty:
        raise AssertionError("Frozen scientific paths have a dirty diff")
    all_dirty = subprocess.check_output(["git", "diff", "HEAD"])
    return commit, hashlib.sha256(all_dirty).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    start_all = time.perf_counter()
    protocol_path = Path(args.protocol).resolve()
    protocol = json.loads(protocol_path.read_text())
    if protocol["status"] != "FROZEN_BEFORE_RK37_TARGET_EVALUATION":
        raise ValueError("Protocol is not frozen")
    output = Path(args.output_dir).resolve()
    report_path = Path(args.report).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output directory must be empty: {output}")
    if report_path.exists():
        raise FileExistsError(f"Report exists: {report_path}")
    output.mkdir(parents=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    script_path = Path(__file__).resolve()
    test_path = script_path.parents[1] / "tests" / "test_a8_rk37_translation_pivot.py"
    commit, dirty_hash = frozen_git_commit([protocol_path, script_path, test_path])

    source_spec = protocol["studies"]["source_matrix"]
    target_spec = protocol["studies"]["target_matrix"]
    if sha256(source_spec["path"]) != source_spec["sha256"] or sha256(target_spec["path"]) != target_spec["sha256"]:
        raise AssertionError("Raw matrix SHA mismatch")
    source_records, source_raw = parse_matrix(Path(source_spec["path"]), protocol["studies"]["source"])
    target_records, target_raw = parse_matrix(Path(target_spec["path"]), protocol["studies"]["target"])
    if source_raw != source_spec["raw_records"] or target_raw != target_spec["raw_records"]:
        raise AssertionError("Raw record count mismatch")
    if len(source_records) != source_spec["eligible_records"] or len(target_records) != target_spec["eligible_records"]:
        raise AssertionError("Eligible record count mismatch")
    overlap = set(value["cds"] for value in source_records.values()) & set(value["cds"] for value in target_records.values())
    if len(overlap) != protocol["studies"]["exact_cds_overlap_required"]:
        raise AssertionError("Exact CDS overlap mismatch")
    materialize_density(source_records)

    seeds = [protocol["split"]["primary_seed"]] + list(protocol["split"]["sensitivity_seeds"])
    states, source_reports = [], []
    actual_fits = 0
    for seed in seeds:
        state, source_report, count = fit_source_seed(protocol, source_records, seed, output)
        states.append(state)
        source_reports.append(source_report)
        actual_fits += count
        print(json.dumps({"phase": "SOURCE_FITS_COMPLETE_NO_TARGET_OUTCOME", "seed": seed, "fits": count, "selected_alpha": source_report["selected_alpha"]}), flush=True)
    assert_fit_accounting(actual_fits, protocol["models"]["planned_unique_fits"])

    # All source fits and deployment choices are complete before this target-outcome phase.
    materialize_density(target_records)
    target_ids = sorted(target_records)
    target_labels = labels_for_ids(target_records, target_ids)
    target_design = {kind: design_for_ids(target_records, target_labels, kind) for kind in ("position", "local")}
    target_distribution = {
        "n_transcripts": int(len(target_ids)),
        "n_masked_positions": int(len(target_labels["target"])),
        "min": float(np.min(target_labels["target"])),
        "max": float(np.max(target_labels["target"])),
        "mean": float(np.mean(target_labels["target"], dtype=np.float64)),
        "std": float(np.std(target_labels["target"], dtype=np.float64)),
        "quantiles": {str(q): float(np.quantile(target_labels["target"], q)) for q in (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)},
    }
    run_reports, effect_records = [], []
    for state in states:
        run_report, effects = evaluate_seed(protocol, state, target_records, target_labels, target_design, output)
        run_reports.append(run_report)
        effect_records.append(effects)
        print(json.dumps({"phase": "TARGET_EVALUATED_AFTER_ALL_48_SOURCE_FITS", "seed": state["seed"], "primary_effects": run_report["primary_effects"]}), flush=True)

    bootstrap_cfg = protocol["evaluation"]["bootstrap"]
    permutation_cfg = protocol["evaluation"]["permutation"]
    endpoints, inference_arrays = [], {}
    for index, name in enumerate(("tb_mse_improvement_over_constant", "mean_pearson_improvement_over_position_raw")):
        effect = effect_records[0]["mse_effect" if index == 0 else "pearson_effect"]
        endpoint, arrays = infer_endpoint(name, effect, bootstrap_cfg["seed"], permutation_cfg["seed"], bootstrap_cfg["resamples"])
        endpoint["sensitivity_effects"] = [record["effects"][name] for record in effect_records[1:]]
        endpoints.append(endpoint)
        inference_arrays.update(arrays)
    endpoints = apply_holm(endpoints)
    for endpoint in endpoints:
        endpoint["primary_pass"] = endpoint_pass(endpoint)
        endpoint["sensitivity_pass"] = sensitivity_pass(endpoint["sensitivity_effects"])
        endpoint["gate_pass"] = endpoint["primary_pass"] and endpoint["sensitivity_pass"]
    inference_path = output / "inference" / "primary_inference_arrays.npz"
    inference_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(inference_path, **inference_arrays)
    dual_pass = all(endpoint["gate_pass"] for endpoint in endpoints)
    decision = "DUAL_DIAGNOSTIC_PASS_REQUIRES_INDEPENDENT_CONFIRMATION" if dual_pass else "CROSS_STUDY_TRANSLATION_TASK_UNRESOLVED_COMPONENT_DIAGNOSIS_REQUIRED"
    for index, source_report in enumerate(source_reports):
        source_report["target_evaluation"] = run_reports[index]

    environment = {
        "python_executable": sys.executable,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": __import__("scipy").__version__,
        "sklearn": __import__("sklearn").__version__,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "numeric_threads": {key: os.environ.get(key) for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")},
    }
    report = {
        "schema": "a8-rk37-translation-pivot-result-v1",
        "status": "PASS_RK37_PRODUCTION_PENDING_INDEPENDENT",
        "scientific_decision": decision,
        "dual_diagnostic_pass": dual_pass,
        "protocol": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "frozen_git_commit": commit,
        "dirty_diff_sha256": dirty_hash,
        "fit_accounting": {"planned_unique_fits": protocol["models"]["planned_unique_fits"], "actual_unique_fits": actual_fits, "families_per_seed": 4, "alphas_per_family": 4, "seeds": 3},
        "target_outcomes_accessed_after_all_source_fits": True,
        "source_reports": source_reports,
        "primary_seed": protocol["split"]["primary_seed"],
        "primary_endpoints": endpoints,
        "target_distribution": target_distribution,
        "target_identity": {"raw_records": target_raw, "eligible_records": len(target_records), "exact_cds_overlap": len(overlap)},
        "source_identity": {"raw_records": source_raw, "eligible_records": len(source_records)},
        "execution": {"wall_seconds": time.perf_counter() - start_all, "cost_claim": protocol["execution"]["cost_claim"]},
        "environment": environment,
        "artifacts": {
            "primary_inference_arrays": {"path": str(inference_path), "sha256": sha256(inference_path), "arrays_sha256": arrays_sha256(inference_path)},
        },
        "scientific_scope": protocol["scientific_scope"],
        "non_claims": [
            "Retrospective Subtelny14 follow-up, not untouched or independent confirmation.",
            "Normalized ribosome occupancy proxy, not direct physical elongation rate.",
            "Exact-CDS-disjoint study OOD, not homology/protein OOD.",
            "No SOTA, functional untouched, generator authorization, RK-G1, wet-lab or prospective DBTL claim.",
        ],
    }
    dump_json(report_path, report)
    dump_json(output / "result.copy.json", report)
    print(json.dumps({"status": report["status"], "scientific_decision": decision, "fits": actual_fits, "primary_endpoints": endpoints, "wall_seconds": report["execution"]["wall_seconds"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
