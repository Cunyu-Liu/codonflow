#!/usr/bin/env python3
"""Independent recomputation for the frozen RK08 constant velocity-field control.

This file intentionally does not import the production comparator. It validates
raw targets, refits the field, recomputes every metric and bootstrap comparison,
then compares the scientific payload with the production report.
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
COMPARISON_NAMES = ("model_minus_constant", "ridge_minus_constant", "model_minus_ridge")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def read_raw(path: Path) -> dict[str, dict]:
    output = {}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for order, line in enumerate(handle):
            item = json.loads(line)
            rid = item["record_id"]
            target = tuple(np.nan if value is None else float(value) for value in item["velocity_target"])
            if len(target) != len(item["cds"]) // 3:
                raise AssertionError(f"target/codon mismatch: {rid}")
            output[rid] = {
                "order": order,
                "split": item["split"],
                "dataset": item["dataset"],
                "codon_count": len(target),
                "target": target,
            }
    return output


def independent_metrics(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    rows = []
    pooled = {}
    for rid, indices in frame.groupby("record_id", sort=False).indices.items():
        group = frame.iloc[indices]
        y = group["target"].to_numpy(dtype=np.float64)
        row = {
            "record_id": rid,
            "dataset": group["dataset"].iloc[0],
            "split": group["split"].iloc[0],
            "n_observed": len(group),
        }
        for name in MODELS:
            prediction = group[name].to_numpy(dtype=np.float64)
            row[f"{name}_mse"] = float(np.square(y - prediction).mean())
            if len(y) >= 3 and y.std() > 0 and prediction.std() > 0:
                row[f"{name}_pearson"] = float(np.corrcoef(y, prediction)[0, 1])
            else:
                row[f"{name}_pearson"] = float("nan")
        rows.append(row)
    per = pd.DataFrame(rows)
    y_all = frame["target"].to_numpy(dtype=np.float64)
    for name in MODELS:
        p_all = frame[name].to_numpy(dtype=np.float64)
        correlations = per[f"{name}_pearson"].to_numpy(dtype=np.float64)
        valid = np.isfinite(correlations)
        pooled[name] = {
            "n_transcripts": int(len(per)),
            "n_observed_positions": int(len(frame)),
            "n_transcripts_with_pearson": int(valid.sum()),
            "transcript_balanced_mse": float(per[f"{name}_mse"].mean()),
            "median_transcript_mse": float(per[f"{name}_mse"].median()),
            "mean_transcript_pearson": float(correlations[valid].mean()) if valid.any() else None,
            "median_transcript_pearson": float(np.median(correlations[valid])) if valid.any() else None,
            "position_mse": float(np.square(y_all - p_all).mean()),
            "position_pearson": float(pearsonr(y_all, p_all).statistic),
            "position_spearman": float(spearmanr(y_all, p_all).statistic),
        }
    return per, pooled


def independent_bootstrap(per: pd.DataFrame, left: str, right: str, seed: int, draws: int) -> dict:
    lm = per[f"{left}_mse"].to_numpy(dtype=np.float64)
    rm = per[f"{right}_mse"].to_numpy(dtype=np.float64)
    lr = per[f"{left}_pearson"].to_numpy(dtype=np.float64)
    rr = per[f"{right}_pearson"].to_numpy(dtype=np.float64)
    keep = np.isfinite(lr) & np.isfinite(rr)
    random = np.random.default_rng(seed)
    mse_draws = np.empty(draws, dtype=np.float64)
    pearson_draws = np.empty(draws, dtype=np.float64)
    for draw in range(draws):
        indices = random.integers(0, len(per), len(per))
        mse_draws[draw] = (lm[indices] - rm[indices]).mean()
        valid_draw = keep[indices]
        pearson_draws[draw] = (lr[indices][valid_draw] - rr[indices][valid_draw]).mean()
    return {
        "delta_transcript_balanced_mse": float((lm - rm).mean()),
        "delta_mean_transcript_pearson": float((lr[keep] - rr[keep]).mean()),
        "n_pearson_transcripts": int(keep.sum()),
        "bootstrap_replicates": int(draws),
        "bootstrap_seed": int(seed),
        "transcript_balanced_mse": {
            "ci95": [float(x) for x in np.quantile(mse_draws, [0.025, 0.975])],
            "bootstrap_mean_delta": float(mse_draws.mean()),
            "pvalue_two_sided": float(min(1.0, 2.0 * min((mse_draws <= 0).mean(), (mse_draws >= 0).mean()))),
        },
        "mean_transcript_pearson": {
            "ci95": [float(x) for x in np.quantile(pearson_draws, [0.025, 0.975])],
            "bootstrap_mean_delta": float(pearson_draws.mean()),
            "pvalue_two_sided": float(min(1.0, 2.0 * min((pearson_draws <= 0).mean(), (pearson_draws >= 0).mean()))),
        },
    }


def independent_holm(rows: list[dict]) -> None:
    raw = []
    for row in rows:
        raw.extend([
            row["transcript_balanced_mse"]["pvalue_two_sided"],
            row["mean_transcript_pearson"]["pvalue_two_sided"],
        ])
    indexed = sorted(enumerate(raw), key=lambda item: item[1])
    adjusted = [0.0] * len(raw)
    previous = 0.0
    for rank, (original, pvalue) in enumerate(indexed):
        previous = max(previous, (len(raw) - rank) * pvalue)
        adjusted[original] = min(1.0, previous)
    for index, row in enumerate(rows):
        row["transcript_balanced_mse"]["holm_pvalue"] = adjusted[2 * index]
        row["mean_transcript_pearson"]["holm_pvalue"] = adjusted[2 * index + 1]


def independent_support(row: dict) -> bool:
    sensitivity = row["sensitivity_bootstrap_mean_deltas"]
    return bool(
        row["transcript_balanced_mse"]["holm_pvalue"] < 0.05
        and row["mean_transcript_pearson"]["holm_pvalue"] < 0.05
        and row["transcript_balanced_mse"]["ci95"][1] < 0
        and row["mean_transcript_pearson"]["ci95"][0] > 0
        and all(x["transcript_balanced_mse"] < 0 for x in sensitivity)
        and all(x["mean_transcript_pearson"] > 0 for x in sensitivity)
    )


def run(root: Path, protocol_path: Path) -> dict:
    started = time.perf_counter()
    protocol = json.loads(protocol_path.read_text())
    output = Path(protocol["independent_output"])
    if output.exists():
        raise FileExistsError(f"refusing to overwrite independent report: {output}")
    production_path = Path(protocol["audit_output"])
    if not production_path.exists():
        raise FileNotFoundError("production report must exist before independent verification")

    raw_path = Path(protocol["velocity_records"]["path"])
    prediction_path = Path(protocol["frozen_predictions"]["path"])
    original_path = root / protocol["source_run_summary"]["path"]
    for path, expected in (
        (raw_path, protocol["velocity_records"]["sha256"]),
        (prediction_path, protocol["frozen_predictions"]["sha256"]),
        (original_path, protocol["source_run_summary"]["sha256"]),
    ):
        if digest(path) != expected:
            raise AssertionError(f"input digest mismatch: {path}")

    raw = read_raw(raw_path)
    frame = pd.read_csv(prediction_path)
    if len(frame) != protocol["frozen_predictions"]["expected_rows"]:
        raise AssertionError("prediction row mismatch")
    raw_target = np.empty(len(frame), dtype=np.float64)
    raw_count = np.empty(len(frame), dtype=np.int64)
    raw_order = np.empty(len(frame), dtype=np.int64)
    raw_split = []
    raw_dataset = []
    for index, (rid, position) in enumerate(zip(frame["record_id"], frame["codon_position"])):
        item = raw[rid]
        raw_target[index] = item["target"][int(position)]
        raw_count[index] = item["codon_count"]
        raw_order[index] = item["order"]
        raw_split.append(item["split"])
        raw_dataset.append(item["dataset"])
    if not np.array_equal(raw_target, frame["target"].to_numpy(dtype=np.float64)):
        raise AssertionError("prediction target differs from raw target")
    if raw_split != frame["split"].tolist() or raw_dataset != frame["dataset"].tolist():
        raise AssertionError("prediction partition differs from raw partition")
    positions = frame["codon_position"].to_numpy(dtype=np.int64)
    relative = positions / (raw_count - 1)
    bins = np.minimum(19, np.floor(relative * 20).astype(np.int64))
    if np.any(positions < 1) or np.any(positions > raw_count - 2):
        raise AssertionError("invalid observed codon position")
    frame["independent_bin"] = bins

    train_mask = (frame["split"] == "train") & (frame["dataset"] == "Mohammad16")
    train = frame.loc[train_mask].copy()
    # Independent implementation: pivot within-transcript bin means, then average columns.
    train["bin"] = bins[train_mask.to_numpy()]
    transcript_bin = train.pivot_table(
        index="record_id", columns="bin", values="target", aggfunc="mean", observed=True
    )
    global_transcript_means = train.groupby("record_id", sort=False)["target"].mean()
    fallback = float(global_transcript_means.mean())
    field = np.full(20, fallback, dtype=np.float64)
    counts = np.zeros(20, dtype=np.int64)
    for column in transcript_bin.columns:
        field[int(column)] = float(transcript_bin[column].mean())
        counts[int(column)] = int(transcript_bin[column].count())
    field_summary = {
        "fit_rows": int(len(train)),
        "fit_transcripts": int(train["record_id"].nunique()),
        "bin_values": [float(x) for x in field],
        "transcripts_per_bin": [int(x) for x in counts],
        "missing_bin_fallback": fallback,
        "missing_bins": [int(x) for x in np.flatnonzero(counts == 0)],
        "estimator": "equal-weight mean of within-transcript bin means",
    }
    frame["constant"] = field[bins]

    metrics = {}
    primary_per = None
    for split, datasets in protocol["partitions"].items():
        for dataset in datasets:
            key = f"{split}|{dataset}"
            selected = (frame["split"] == split) & (frame["dataset"] == dataset)
            per, group_metrics = independent_metrics(frame.loc[selected])
            metrics[key] = group_metrics
            if key == protocol["primary_partition"]:
                primary_per = per
    if primary_per is None:
        raise AssertionError("primary partition missing")

    comparison_rows = []
    for name in COMPARISON_NAMES:
        left, right = name.split("_minus_")
        row = independent_bootstrap(
            primary_per, left, right,
            int(protocol["comparison_rules"]["bootstrap_seed"]),
            int(protocol["comparison_rules"]["bootstrap_replicates"]),
        )
        sensitivity = []
        for seed in protocol["comparison_rules"]["sensitivity_bootstrap_seeds"]:
            alternate = independent_bootstrap(
                primary_per, left, right, int(seed),
                int(protocol["comparison_rules"]["bootstrap_replicates"]),
            )
            sensitivity.append({
                "seed": int(seed),
                "transcript_balanced_mse": alternate["transcript_balanced_mse"]["bootstrap_mean_delta"],
                "mean_transcript_pearson": alternate["mean_transcript_pearson"]["bootstrap_mean_delta"],
            })
        row["sensitivity_bootstrap_mean_deltas"] = sensitivity
        comparison_rows.append(row)
    independent_holm(comparison_rows)
    comparisons = dict(zip(COMPARISON_NAMES, comparison_rows))
    support = {f"{name}_supported": independent_support(row) for name, row in comparisons.items()}
    gates = {
        "constant_field_diagnostic_complete": True,
        "velocity_mechanism_pass": False,
        "rk_g1_pass": False,
        "functional_untouched_evaluated": False,
        "generator_training_authorized": False,
        "external_sota_claim_authorized": False,
    }
    recomputed = {
        "constant_field": field_summary,
        "metrics": metrics,
        "primary_comparisons": comparisons,
        "support": support,
        "gates": gates,
    }

    production = json.loads(production_path.read_text())
    checks = []
    numeric_deltas = []

    def record_check(name: str, passed: bool, detail) -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    def compare(path: str, actual, expected) -> None:
        if isinstance(expected, dict):
            record_check(path + "/keys", isinstance(actual, dict) and set(actual) == set(expected), sorted(expected))
            if isinstance(actual, dict):
                for key in expected:
                    compare(f"{path}/{key}", actual.get(key), expected[key])
        elif isinstance(expected, list):
            record_check(path + "/length", isinstance(actual, list) and len(actual) == len(expected), len(expected))
            if isinstance(actual, list):
                for index, value in enumerate(expected):
                    compare(f"{path}/{index}", actual[index] if index < len(actual) else None, value)
        elif isinstance(expected, (float, int)) and not isinstance(expected, bool):
            try:
                delta = abs(float(actual) - float(expected))
                passed = math.isclose(float(actual), float(expected), rel_tol=0, abs_tol=1e-12)
                numeric_deltas.append(delta)
            except (TypeError, ValueError):
                delta = float("inf")
                passed = False
            record_check(path, passed, {"production": actual, "independent": expected, "abs_delta": delta})
        else:
            record_check(path, actual == expected, {"production": actual, "independent": expected})

    for key, value in recomputed.items():
        compare(key, production.get(key), value)
    record_check("input/raw_record_count", len(raw) == 7788, len(raw))
    record_check("input/prediction_rows", len(frame) == 2628306, len(frame))
    record_check("input/raw_targets_exact", True, "all 2,628,306 prediction targets matched raw records")
    record_check("input/production_protocol_hash", production["protocol_sha256"] == digest(protocol_path), production["protocol_sha256"])
    team_report = Path(protocol["artifact_root"]) / "production_report.json"
    record_check("artifact/team_report_byte_identical", team_report.read_bytes() == production_path.read_bytes(), str(team_report))
    for key in ("per_transcript_metrics", "constant_field"):
        artifact = Path(production["artifacts"][key])
        record_check(f"artifact/{key}_hash", digest(artifact) == production["artifacts"][f"{key}_sha256"], str(artifact))
    original = json.loads(original_path.read_text())
    record_check(
        "gate/original_velocity_negative_preserved",
        original["velocity_mechanism_pass"] is False and production["gates"]["velocity_mechanism_pass"] is False,
        False,
    )
    record_check(
        "gate/no_functional_or_generator_access",
        not production["gates"]["functional_untouched_evaluated"] and not production["gates"]["generator_training_authorized"],
        production["gates"],
    )
    failed = [row for row in checks if not row["pass"]]
    report = {
        "schema_version": "a8-rk08-constant-velocity-field-independent-v1",
        "status": "PASS_CONSTANT_VELOCITY_INDEPENDENT" if not failed else "FAIL_CONSTANT_VELOCITY_INDEPENDENT",
        "protocol_sha256": digest(protocol_path),
        "production_sha256": digest(production_path),
        "check_count": len(checks),
        "passed_count": len(checks) - len(failed),
        "failed_count": len(failed),
        "failed_checks": failed,
        "max_numeric_delta": max(numeric_deltas, default=0.0),
        "checks": checks,
        "recomputed_support": support,
        "recomputed_primary_comparisons": comparisons,
        "gates": gates,
        "elapsed_seconds": time.perf_counter() - started,
    }
    save(output, report)
    team_output = Path(protocol["artifact_root"]) / "independent_report.json"
    team_output.write_bytes(output.read_bytes())
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.root.resolve(), args.protocol.resolve())
    print(json.dumps({key: report[key] for key in (
        "status", "check_count", "passed_count", "failed_count", "max_numeric_delta", "recomputed_support", "elapsed_seconds"
    )}, indent=2))
    if report["failed_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
