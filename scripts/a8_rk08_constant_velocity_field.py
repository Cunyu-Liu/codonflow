#!/usr/bin/env python3
"""Frozen RK08 train-only constant relative-position velocity-field comparator.

The comparator uses only Mohammad16 training targets. It never fits on evaluation
rows and never changes the original velocity/RK-G1 gates.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

MODELS = ("model", "ridge", "constant")
COMPARISONS = ("model_minus_constant", "ridge_minus_constant", "model_minus_ridge")
METRICS = ("transcript_balanced_mse", "mean_transcript_pearson")
ORIGINAL_MODEL_NAMES = {
    "ribokinetic_velocity": "model",
    "ridge_codon_position_length": "ridge",
}


def original_group_key(group: str) -> str:
    if group in {"train", "dev", "test"}:
        return f"{group}|Mohammad16"
    if group.startswith("study_ood:"):
        return group.replace("study_ood:", "study_ood|", 1)
    raise ValueError(f"unknown original metric group: {group}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dump_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")


def holm_adjust(pvalues: list[float]) -> list[float]:
    order = sorted(range(len(pvalues)), key=lambda index: pvalues[index])
    adjusted = [0.0] * len(pvalues)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(pvalues) - rank) * pvalues[index])
        adjusted[index] = min(1.0, running)
    return adjusted


def position_bins(codon_position, codon_count, n_bins: int = 20):
    """Map observed codon positions to the inherited relative-position bins."""
    position = np.asarray(codon_position, dtype=np.int64)
    count = np.asarray(codon_count, dtype=np.int64)
    if np.any(count < 3):
        raise ValueError("codon_count must be at least three")
    if np.any(position < 1) or np.any(position > count - 2):
        raise ValueError("observed position outside codons 1..n-2")
    relative = position / (count - 1)
    return np.minimum(n_bins - 1, np.floor(relative * n_bins).astype(np.int64))


def load_codon_counts(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            row = json.loads(line)
            record_id = str(row["record_id"])
            if record_id in records:
                raise ValueError(f"duplicate raw record: {record_id}")
            codon_count = len(row["cds"]) // 3
            if len(row["velocity_target"]) != codon_count:
                raise ValueError(f"raw target length mismatch at line {line_number}")
            if record_id != f"{row['dataset']}:{row['source_record_id']}":
                raise ValueError(f"raw record/study mismatch at line {line_number}")
            records[record_id] = {
                "codon_count": codon_count,
                "split": str(row["split"]),
                "dataset": str(row["dataset"]),
                "raw_order": line_number - 1,
            }
    if not records:
        raise ValueError("no velocity records")
    return records


def load_prediction_frame(path: Path, records: dict[str, dict], expected_rows: int) -> pd.DataFrame:
    frame = pd.read_csv(path, float_precision="round_trip")
    required = {"record_id", "dataset", "split", "codon_position", "target", "model_prediction", "ridge_prediction"}
    if set(frame.columns) != required:
        raise ValueError(f"unexpected prediction columns: {sorted(frame.columns)}")
    frame = frame.rename(columns={"model_prediction": "model", "ridge_prediction": "ridge"})
    if len(frame) != expected_rows:
        raise ValueError(f"prediction row count {len(frame)} != {expected_rows}")
    if frame[["record_id", "codon_position"]].duplicated().any():
        raise ValueError("duplicate record/position prediction")
    numeric = ["codon_position", "target", "model", "ridge"]
    if not np.isfinite(frame[numeric].to_numpy(dtype=np.float64)).all():
        raise ValueError("non-finite prediction input")
    mapped_count = frame["record_id"].map(lambda key: records.get(key, {}).get("codon_count", np.nan))
    if mapped_count.isna().any():
        raise ValueError("prediction record absent from raw records")
    frame["codon_count"] = mapped_count.astype(np.int64)
    for column in ("split", "dataset"):
        expected = frame["record_id"].map(lambda key: records[key][column])
        if not frame[column].equals(expected):
            raise ValueError(f"prediction/raw {column} mismatch")
    frame["position_bin"] = position_bins(frame["codon_position"], frame["codon_count"])
    return frame


def fit_constant_field(frame: pd.DataFrame, n_bins: int = 20) -> tuple[np.ndarray, dict]:
    """Fit transcript-balanced bin means using training rows only."""
    train = frame.loc[(frame["split"] == "train") & (frame["dataset"] == "Mohammad16")]
    if train.empty:
        raise ValueError("empty Mohammad16 training partition")
    transcript_bins = (
        train.groupby(["record_id", "position_bin"], sort=True, observed=True)["target"]
        .mean()
        .rename("target")
        .reset_index()
    )
    by_bin = transcript_bins.groupby("position_bin", sort=True)["target"]
    global_by_transcript = train.groupby("record_id", sort=True)["target"].mean()
    fallback = float(global_by_transcript.mean())
    field = np.full(n_bins, fallback, dtype=np.float64)
    counts = np.zeros(n_bins, dtype=np.int64)
    for bin_index, values in by_bin:
        field[int(bin_index)] = float(values.mean())
        counts[int(bin_index)] = len(values)
    summary = {
        "fit_rows": int(len(train)),
        "fit_transcripts": int(train["record_id"].nunique()),
        "bin_values": [float(value) for value in field],
        "transcripts_per_bin": [int(value) for value in counts],
        "missing_bin_fallback": fallback,
        "missing_bins": [int(index) for index in np.flatnonzero(counts == 0)],
        "estimator": "equal-weight mean of within-transcript bin means",
    }
    return field, summary


def per_transcript_table(frame: pd.DataFrame, models=MODELS) -> pd.DataFrame:
    """Compute per-record metrics in frozen prediction/raw record order."""
    rows = []
    for record_id, group in frame.groupby("record_id", sort=False):
        target = group["target"].to_numpy(dtype=np.float64)
        row = {
            "record_id": record_id,
            "dataset": str(group["dataset"].iloc[0]),
            "split": str(group["split"].iloc[0]),
            "n_observed": int(len(group)),
        }
        for model in models:
            prediction = group[model].to_numpy(dtype=np.float64)
            row[f"{model}_mse"] = float(np.mean((target - prediction) ** 2))
            if len(target) >= 3 and np.std(target) > 0 and np.std(prediction) > 0:
                row[f"{model}_pearson"] = float(np.corrcoef(target, prediction)[0, 1])
            else:
                row[f"{model}_pearson"] = float("nan")
        rows.append(row)
    return pd.DataFrame(rows)


def metrics_block(frame: pd.DataFrame, per: pd.DataFrame, model: str) -> dict:
    pearson = per[f"{model}_pearson"].to_numpy(dtype=np.float64)
    valid = np.isfinite(pearson)
    target = frame["target"].to_numpy(dtype=np.float64)
    prediction = frame[model].to_numpy(dtype=np.float64)
    return {
        "n_transcripts": int(len(per)),
        "n_observed_positions": int(len(frame)),
        "n_transcripts_with_pearson": int(valid.sum()),
        "transcript_balanced_mse": float(per[f"{model}_mse"].mean()),
        "median_transcript_mse": float(per[f"{model}_mse"].median()),
        "mean_transcript_pearson": float(np.mean(pearson[valid])) if valid.any() else None,
        "median_transcript_pearson": float(np.median(pearson[valid])) if valid.any() else None,
        "position_mse": float(np.mean((target - prediction) ** 2)),
        "position_pearson": float(pearsonr(target, prediction).statistic),
        "position_spearman": float(spearmanr(target, prediction).statistic),
    }


def comparison_arrays(per: pd.DataFrame, left: str, right: str) -> dict[str, np.ndarray]:
    return {
        "left_mse": per[f"{left}_mse"].to_numpy(dtype=np.float64),
        "right_mse": per[f"{right}_mse"].to_numpy(dtype=np.float64),
        "left_pearson": per[f"{left}_pearson"].to_numpy(dtype=np.float64),
        "right_pearson": per[f"{right}_pearson"].to_numpy(dtype=np.float64),
    }


def paired_bootstrap(arrays: dict[str, np.ndarray], replicates: int, seed: int) -> dict:
    valid = np.isfinite(arrays["left_pearson"]) & np.isfinite(arrays["right_pearson"])
    point_mse = float(np.mean(arrays["left_mse"] - arrays["right_mse"]))
    point_pearson = float(
        np.mean(arrays["left_pearson"][valid] - arrays["right_pearson"][valid])
    )
    rng = np.random.default_rng(seed)
    samples = np.empty((replicates, 2), dtype=np.float64)
    n = len(arrays["left_mse"])
    for index in range(replicates):
        selected = rng.integers(0, n, size=n)
        samples[index, 0] = np.mean(arrays["left_mse"][selected] - arrays["right_mse"][selected])
        keep = valid[selected]
        samples[index, 1] = np.mean(
            arrays["left_pearson"][selected][keep] - arrays["right_pearson"][selected][keep]
        )
    return {
        "delta_transcript_balanced_mse": point_mse,
        "delta_mean_transcript_pearson": point_pearson,
        "n_pearson_transcripts": int(valid.sum()),
        "bootstrap_replicates": int(replicates),
        "bootstrap_seed": int(seed),
        "transcript_balanced_mse": {
            "ci95": [float(value) for value in np.quantile(samples[:, 0], [0.025, 0.975])],
            "bootstrap_mean_delta": float(np.mean(samples[:, 0])),
            "pvalue_two_sided": float(min(1.0, 2 * min(np.mean(samples[:, 0] <= 0), np.mean(samples[:, 0] >= 0)))),
        },
        "mean_transcript_pearson": {
            "ci95": [float(value) for value in np.quantile(samples[:, 1], [0.025, 0.975])],
            "bootstrap_mean_delta": float(np.mean(samples[:, 1])),
            "pvalue_two_sided": float(min(1.0, 2 * min(np.mean(samples[:, 1] <= 0), np.mean(samples[:, 1] >= 0)))),
        },
    }


def supported(comparison: dict) -> bool:
    mse = comparison["transcript_balanced_mse"]
    pearson = comparison["mean_transcript_pearson"]
    sensitivity = comparison["sensitivity_bootstrap_mean_deltas"]
    return bool(
        mse["holm_pvalue"] < 0.05
        and pearson["holm_pvalue"] < 0.05
        and mse["ci95"][1] < 0
        and pearson["ci95"][0] > 0
        and all(row["transcript_balanced_mse"] < 0 for row in sensitivity)
        and all(row["mean_transcript_pearson"] > 0 for row in sensitivity)
    )


def run(root: Path, protocol_path: Path) -> dict:
    started = time.perf_counter()
    protocol = json.loads(protocol_path.read_text())
    if protocol["status"] != "FROZEN_BEFORE_CONSTANT_FIELD_READOUT":
        raise ValueError("protocol is not frozen")
    audit_output = Path(protocol["audit_output"])
    if audit_output.exists():
        raise FileExistsError(f"refusing to overwrite production audit: {audit_output}")
    artifact_root = Path(protocol["artifact_root"])
    artifact_root.mkdir(parents=True, exist_ok=True)

    source_summary_path = root / protocol["source_run_summary"]["path"]
    records_path = Path(protocol["velocity_records"]["path"])
    predictions_path = Path(protocol["frozen_predictions"]["path"])
    for path, expected in (
        (source_summary_path, protocol["source_run_summary"]["sha256"]),
        (records_path, protocol["velocity_records"]["sha256"]),
        (predictions_path, protocol["frozen_predictions"]["sha256"]),
    ):
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"input hash mismatch for {path}: {actual}")
    source_summary = json.loads(source_summary_path.read_text())

    records = load_codon_counts(records_path)
    frame = load_prediction_frame(
        predictions_path, records, int(protocol["frozen_predictions"]["expected_rows"])
    )
    field, field_summary = fit_constant_field(
        frame, int(protocol["constant_field"]["relative_position_bins"])
    )
    frame["constant"] = frame["position_bin"].map(dict(enumerate(field))).astype(np.float64)
    if not np.isfinite(frame["constant"]).all():
        raise ValueError("non-finite constant-field prediction")

    all_metrics = {}
    per_tables = []
    for split, datasets in protocol["partitions"].items():
        for dataset in datasets:
            key = f"{split}|{dataset}"
            partition = frame.loc[(frame["split"] == split) & (frame["dataset"] == dataset)]
            per = per_transcript_table(partition)
            per.insert(0, "partition", key)
            per_tables.append(per)
            all_metrics[key] = {model: metrics_block(partition, per, model) for model in MODELS}

    # Reproduction guards run before any new paired-bootstrap readout.
    for group, original_group in source_summary["metrics"].items():
        new_group = original_group_key(group)
        for original_model, new_model in ORIGINAL_MODEL_NAMES.items():
            for metric, original_value in original_group[original_model].items():
                new_value = all_metrics[new_group][new_model][metric]
                if original_value is None:
                    if new_value is not None:
                        raise AssertionError(f"metric changed {group}/{new_model}/{metric}")
                elif not math.isclose(float(new_value), float(original_value), rel_tol=0, abs_tol=1e-12):
                    raise AssertionError(f"metric changed {group}/{new_model}/{metric}: {new_value} vs {original_value}")

    primary = protocol["primary_partition"]
    primary_per = per_transcript_table(
        frame.loc[(frame["split"] == primary.split("|")[0]) & (frame["dataset"] == primary.split("|")[1])]
    )
    comparison_results = {}
    pvalue_rows = []
    for comparison_name in COMPARISONS:
        left, right = comparison_name.replace("_minus_", "|").split("|")
        arrays = comparison_arrays(primary_per, left, right)
        result = paired_bootstrap(
            arrays,
            int(protocol["comparison_rules"]["bootstrap_replicates"]),
            int(protocol["comparison_rules"]["bootstrap_seed"]),
        )
        sensitivity = []
        for seed in protocol["comparison_rules"]["sensitivity_bootstrap_seeds"]:
            row = paired_bootstrap(arrays, int(protocol["comparison_rules"]["bootstrap_replicates"]), int(seed))
            sensitivity.append({
                "seed": int(seed),
                "transcript_balanced_mse": row["transcript_balanced_mse"]["bootstrap_mean_delta"],
                "mean_transcript_pearson": row["mean_transcript_pearson"]["bootstrap_mean_delta"],
            })
        result["sensitivity_bootstrap_mean_deltas"] = sensitivity
        comparison_results[comparison_name] = result
        pvalue_rows.extend([
            result["transcript_balanced_mse"]["pvalue_two_sided"],
            result["mean_transcript_pearson"]["pvalue_two_sided"],
        ])
    adjusted = holm_adjust(pvalue_rows)
    for index, comparison_name in enumerate(COMPARISONS):
        comparison_results[comparison_name]["transcript_balanced_mse"]["holm_pvalue"] = adjusted[2 * index]
        comparison_results[comparison_name]["mean_transcript_pearson"]["holm_pvalue"] = adjusted[2 * index + 1]
    support = {f"{name}_supported": supported(result) for name, result in comparison_results.items()}

    original_primary = source_summary["primary_comparisons"]["model_minus_ridge"]
    new_primary = comparison_results["model_minus_ridge"]
    for metric in METRICS:
        for field_name in ("ci95", "bootstrap_mean_delta", "pvalue_two_sided"):
            if not np.allclose(new_primary[metric][field_name], original_primary[metric][field_name], rtol=0, atol=1e-12):
                raise AssertionError(f"original primary comparison changed: {metric}/{field_name}")
        if new_primary[f"delta_{metric}"] != original_primary[f"delta_{metric}"]:
            raise AssertionError(f"original point delta changed: {metric}")
        if new_primary[metric]["holm_pvalue"] != original_primary[metric]["holm_pvalue"]:
            raise AssertionError(f"original Holm result changed: {metric}")

    per_output = artifact_root / "per_transcript_metrics.csv.gz"
    pd.concat(per_tables, ignore_index=True).to_csv(per_output, index=False, compression="gzip")
    field_output = artifact_root / "constant_field.json"
    dump_json(field_output, field_summary)
    report = {
        "schema_version": "a8-rk08-constant-velocity-field-production-v1",
        "status": "PASS_CONSTANT_VELOCITY_FIELD_PRODUCTION",
        "protocol_sha256": sha256(protocol_path),
        "inputs": {
            "source_run_summary": str(source_summary_path),
            "source_run_summary_sha256": protocol["source_run_summary"]["sha256"],
            "velocity_records": str(records_path),
            "velocity_records_sha256": protocol["velocity_records"]["sha256"],
            "frozen_predictions": str(predictions_path),
            "frozen_predictions_sha256": protocol["frozen_predictions"]["sha256"],
            "prediction_rows": int(len(frame)),
            "raw_records": int(len(records)),
        },
        "constant_field": field_summary,
        "metrics": all_metrics,
        "primary_partition": primary,
        "primary_comparisons": comparison_results,
        "support": support,
        "gates": {
            "constant_field_diagnostic_complete": True,
            "velocity_mechanism_pass": False,
            "rk_g1_pass": False,
            "functional_untouched_evaluated": False,
            "generator_training_authorized": False,
            "external_sota_claim_authorized": False,
        },
        "cost": {
            "new_model_training_runs": 0,
            "new_checkpoint_selection_runs": 0,
            "model_forward_passes": 0,
            "unique_scorer_calls": 0,
            "elapsed_seconds": time.perf_counter() - started,
        },
        "artifacts": {
            "audit_output": str(audit_output),
            "team_report": str(artifact_root / "production_report.json"),
            "per_transcript_metrics": str(per_output),
            "per_transcript_metrics_sha256": sha256(per_output),
            "constant_field": str(field_output),
            "constant_field_sha256": sha256(field_output),
        },
        "interpretation_boundary": "A sequence-independent position-field comparator on occupancy-derived speed proxies. No causal, functional, protein-OOD, external-SOTA, or generation-readiness claim.",
    }
    dump_json(audit_output, report)
    team_report = artifact_root / "production_report.json"
    team_report.write_bytes(audit_output.read_bytes())
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.root.resolve(), args.protocol.resolve())
    print(json.dumps({
        "status": report["status"],
        "support": report["support"],
        "gates": report["gates"],
        "audit_output": report["artifacts"]["audit_output"],
        "elapsed_seconds": report["cost"]["elapsed_seconds"],
    }, indent=2))


if __name__ == "__main__":
    main()
