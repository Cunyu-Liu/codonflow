#!/usr/bin/env python3
"""Independent verification for the RK08 velocity-proxy experiment."""
from __future__ import annotations

import argparse
import collections
import csv
import dataclasses
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import torch

from codonflow.data.ribokinetic import TargetNormalizer, collate_ribokinetic, file_sha256
from codonflow.data.velocity import read_velocity_jsonl
from codonflow.models.ribokinetic import RiboKineticConfig, RiboKineticModel


def expected_split(record_id, dataset, seed):
    if dataset != "Mohammad16":
        return "study_ood"
    value = int.from_bytes(hashlib.sha256(f"{seed}:{record_id}".encode()).digest()[:8], "big") / 2**64
    return "train" if value < 0.8 else ("dev" if value < 0.9 else "test")


def close(left, right, tolerance=1e-9):
    if left is None or right is None:
        return left is None and right is None
    return bool(np.isclose(left, right, rtol=tolerance, atol=tolerance))


def online_record(target, model, ridge):
    result = []
    for prediction in (model, ridge):
        y = np.asarray(target, dtype=np.float64)
        p = np.asarray(prediction, dtype=np.float64)
        pearson = np.nan
        if len(y) >= 3 and np.std(y) > 0 and np.std(p) > 0:
            pearson = float(np.corrcoef(y, p)[0, 1])
        result.append({"mse": float(np.mean((p - y) ** 2)), "pearson": pearson})
    return result


def summarize_records(records):
    y = np.concatenate([row[0] for row in records])
    p = np.concatenate([row[1] for row in records])
    per_record = [online_record(row[0], row[1], row[1])[0] for row in records]
    pearsons = np.asarray([row["pearson"] for row in per_record])
    valid = pearsons[np.isfinite(pearsons)]
    return {
        "n_transcripts": len(records),
        "n_observed_positions": len(y),
        "position_mse": float(np.mean((p - y) ** 2)),
        "transcript_balanced_mse": float(np.mean([row["mse"] for row in per_record])),
        "position_pearson": float(np.corrcoef(y, p)[0, 1]),
        "mean_transcript_pearson": float(np.mean(valid)) if len(valid) else None,
        "median_transcript_pearson": float(np.median(valid)) if len(valid) else None,
        "n_transcripts_with_pearson": len(valid),
    }


def bootstrap(primary, seed, replicates):
    model_mse = np.asarray([row["model_mse"] for row in primary])
    ridge_mse = np.asarray([row["ridge_mse"] for row in primary])
    model_pearson = np.asarray([row["model_pearson"] for row in primary])
    ridge_pearson = np.asarray([row["ridge_pearson"] for row in primary])
    valid = np.isfinite(model_pearson) & np.isfinite(ridge_pearson)
    rng = np.random.default_rng(seed)
    mse_samples, pearson_samples = [], []
    for _ in range(replicates):
        selected = rng.integers(0, len(primary), len(primary))
        mse_samples.append(float(np.mean(model_mse[selected] - ridge_mse[selected])))
        chosen = selected[valid[selected]]
        pearson_samples.append(float(np.mean(model_pearson[chosen] - ridge_pearson[chosen])) if len(chosen) else np.nan)
    rows = []
    for metric, values, point in [
        ("transcript_balanced_mse", np.asarray(mse_samples), float(np.mean(model_mse - ridge_mse))),
        ("mean_transcript_pearson", np.asarray(pearson_samples), float(np.mean(model_pearson[valid] - ridge_pearson[valid]))),
    ]:
        values = values[np.isfinite(values)]
        benefit = -values if metric == "transcript_balanced_mse" else values
        pvalue = float(min(1.0, 2.0 * min(np.mean(benefit <= 0), np.mean(benefit >= 0))))
        rows.append({
            "metric": metric,
            "point_delta_model_minus_ridge": point,
            "ci95_low": float(np.quantile(values, 0.025)),
            "ci95_high": float(np.quantile(values, 0.975)),
            "sign_pvalue": pvalue,
        })
    order = np.argsort([row["sign_pvalue"] for row in rows])
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (2 - rank) * rows[index]["sign_pvalue"])
        rows[index]["holm_pvalue"] = float(min(1.0, running))
    gate = all(
        row["holm_pvalue"] < 0.05
        and ((row["metric"] == "transcript_balanced_mse" and row["ci95_high"] < 0) or (row["metric"] == "mean_transcript_pearson" and row["ci95_low"] > 0))
        for row in rows
    )
    return rows, bool(gate)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-jsonl", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--data-audit", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--retrain-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    checks = {}
    audit = json.loads(Path(args.data_audit).read_text())
    config = json.loads(Path(args.config).read_text())
    run = json.loads((Path(args.run_dir) / "run_summary.json").read_text())
    retrain = json.loads((Path(args.retrain_dir) / "run_summary.json").read_text())
    checks["formal_uncapped_data"] = audit["max_records_per_study"] is None and config["max_records_per_split"] is None
    checks["raw_hash_matches_audit"] = file_sha256(args.raw_jsonl) == audit["input_sha256"]
    checks["data_hash_matches_audit"] = file_sha256(args.data) == audit["output_sha256"]
    checks["data_hash_matches_run"] = audit["output_sha256"] == run["hashes"]["data_sha256"] == retrain["hashes"]["data_sha256"]
    checks["config_hash_matches_run"] = file_sha256(args.config) == run["hashes"]["config_sha256"] == retrain["hashes"]["config_sha256"]
    checks["checkpoint_retrain_identical"] = run["hashes"]["checkpoint_sha256"] == retrain["hashes"]["checkpoint_sha256"] == file_sha256(str(Path(args.retrain_dir) / "best.pt"))
    checks["predictions_retrain_identical"] = run["hashes"]["predictions_sha256"] == retrain["hashes"]["predictions_sha256"] == file_sha256(str(Path(args.retrain_dir) / "predictions.csv.gz"))
    checks["no_generator_authorization"] = not run["expensive_generation_authorized"] and not run["rk_g1_pass"]

    records = read_velocity_jsonl(args.data)
    checks["unique_record_ids"] = len({record.record_id for record in records}) == len(records)
    checks["length_cap_respected"] = all(record.codon_count <= audit["max_codons"] for record in records)
    checks["termini_masked"] = all(math.isnan(record.velocity_target[0]) and math.isnan(record.velocity_target[-1]) for record in records)
    checks["elongation_targets_finite"] = all(all(math.isfinite(value) for value in record.velocity_target[1:-1]) for record in records)
    checks["split_rule_reproduced"] = all(record.split == expected_split(record.record_id, record.record_id.split(":", 1)[0], audit["seed"]) for record in records)
    cds = {split: {record.cds for record in records if record.split == split} for split in ["train", "dev", "test", "study_ood"]}
    checks["train_dev_test_exact_cds_disjoint"] = not (cds["train"] & cds["dev"] or cds["train"] & cds["test"] or cds["dev"] & cds["test"])
    subtelny = {record.cds for record in records if record.record_id.startswith("Subtelny14:")}
    checks["primary_exact_cds_disjoint"] = not (subtelny & (cds["train"] | cds["dev"] | cds["test"]))

    if checks["formal_uncapped_data"]:
        with gzip.open(args.raw_jsonl, "rt", encoding="utf-8") as raw_handle, gzip.open(args.data, "rt", encoding="utf-8") as prepared_handle:
            raw_rows = [json.loads(line) for line in raw_handle if len(json.loads(line)["cds_dna"]) // 3 <= audit["max_codons"]]
            prepared_rows = [json.loads(line) for line in prepared_handle]
        checks["raw_prepared_record_count"] = len(raw_rows) == len(prepared_rows) == len(records)
        raw_match = True
        for raw, prepared in zip(raw_rows, prepared_rows):
            if raw["record_id"] != prepared["record_id"] or raw["cds_dna"] != prepared["cds"] or raw["organism"] != prepared["host"]:
                raw_match = False
                break
            targets = prepared["velocity_target"]
            if targets[0] is not None or targets[-1] is not None:
                raw_match = False
                break
            for position in range(1, len(targets) - 1):
                if not close(targets[position], -math.log1p(float(raw["density_normalized"][position])), 1e-12):
                    raw_match = False
                    break
            if not raw_match:
                break
        checks["raw_targets_independently_recomputed"] = raw_match
    else:
        checks["raw_prepared_record_count"] = False
        checks["raw_targets_independently_recomputed"] = False

    train_values = [value for record in records if record.split == "train" for value in record.velocity_target if math.isfinite(value)]
    mean = float(np.mean(train_values))
    scale = float(np.std(train_values))
    checks["train_only_normalizer"] = close(run["normalizer"]["mean"], mean, 1e-10) and close(run["normalizer"]["scale"], scale, 1e-10) and run["normalizer"]["fit_split"] == "train_only"
    expected_hosts = {host: index + 1 for index, host in enumerate(sorted({record.host for record in records if record.split == "train"}))}
    checks["train_only_host_vocabulary"] = run["host_vocabulary"] == expected_hosts

    history = json.loads((Path(args.run_dir) / "history.json").read_text())
    best = min(history, key=lambda row: row["dev"]["transcript_balanced_mse"])
    checks["checkpoint_selected_by_dev_only"] = best["epoch"] == run["selected_epoch"] and run["selection"].startswith("Mohammad16 dev")

    grouped = collections.defaultdict(list)
    primary_rows = []
    selected_ids = {next(record.record_id for record in records if record.split == "train")}
    for split in ["dev", "test"]:
        selected_ids.add(next(record.record_id for record in records if record.split == split))
    selected_ids.add(next(record.record_id for record in records if record.record_id.startswith("Subtelny14:")))
    selected_predictions = collections.defaultdict(dict)
    with gzip.open(Path(args.run_dir) / "predictions.csv.gz", "rt", newline="") as handle:
        reader = csv.DictReader(handle)
        current_id = None
        current_target, current_model, current_ridge = [], [], []
        current_split = current_dataset = None

        def finish_record():
            if current_id is None:
                return
            name = f"study_ood:{current_dataset}" if current_split == "study_ood" else current_split
            grouped[name].append((np.asarray(current_target), np.asarray(current_model), np.asarray(current_ridge)))
            if name == "study_ood:Subtelny14":
                model_stats, ridge_stats = online_record(current_target, current_model, current_ridge)
                primary_rows.append({
                    "model_mse": model_stats["mse"], "ridge_mse": ridge_stats["mse"],
                    "model_pearson": model_stats["pearson"], "ridge_pearson": ridge_stats["pearson"],
                })

        for row in reader:
            record_id = row["record_id"]
            if current_id is not None and record_id != current_id:
                finish_record()
                current_target, current_model, current_ridge = [], [], []
            current_id = record_id
            current_split = row["split"]
            current_dataset = row["dataset"]
            current_target.append(float(row["target"]))
            current_model.append(float(row["model_prediction"]))
            current_ridge.append(float(row["ridge_prediction"]))
            if record_id in selected_ids:
                selected_predictions[record_id][int(row["codon_position"])] = float(row["model_prediction"])
        finish_record()
    checks["prediction_record_count"] = sum(len(rows) for rows in grouped.values()) == len(records)
    metric_checks = []
    for name, rows in grouped.items():
        for column, model_name in [(1, "ribokinetic_velocity"), (2, "ridge_codon_position_length")]:
            recomputed = summarize_records([(row[0], row[column]) for row in rows])
            expected = run["metrics"][name][model_name]
            for metric in ["n_transcripts", "n_observed_positions", "position_mse", "transcript_balanced_mse", "position_pearson", "mean_transcript_pearson", "median_transcript_pearson", "n_transcripts_with_pearson"]:
                metric_checks.append(close(recomputed[metric], expected[metric], 1e-8))
    checks["all_primary_metrics_recomputed"] = all(metric_checks)

    recomputed_comparisons, recomputed_gate = bootstrap(primary_rows, config["bootstrap"]["seed"], config["bootstrap"]["replicates"])
    comparison_checks = []
    for actual, expected in zip(recomputed_comparisons, run["primary_comparisons"]):
        for key in ["point_delta_model_minus_ridge", "ci95_low", "ci95_high", "sign_pvalue", "holm_pvalue"]:
            comparison_checks.append(close(actual[key], expected[key], 1e-8))
    checks["bootstrap_and_holm_recomputed"] = all(comparison_checks)
    checks["mechanism_gate_matches"] = recomputed_gate == run["velocity_mechanism_pass"]

    checkpoint = torch.load(Path(args.retrain_dir) / "best.pt", map_location="cpu", weights_only=False)
    model = RiboKineticModel(RiboKineticConfig(**checkpoint["model_config"]))
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    normalizer_data = checkpoint["normalizer"]
    normalizer = TargetNormalizer(
        target=normalizer_data["target"], mean=normalizer_data["mean"], scale=normalizer_data["scale"],
        log1p=normalizer_data["log1p"], train_value_count=normalizer_data["train_value_count"],
    )
    selected_records = [record for record in records if record.record_id in selected_ids]
    normalized = normalizer.apply(selected_records)
    batch = collate_ribokinetic(normalized, checkpoint["host_vocabulary"])
    with torch.no_grad():
        output = model(batch["codon_ids"], batch["pad_mask"], host_ids=batch.get("host_ids"))
    differences = []
    for index, record in enumerate(normalized):
        saved = selected_predictions[record.record_id]
        for position, raw_prediction in saved.items():
            normalized_prediction = float(output["velocity"][index, position])
            differences.append(abs((normalized_prediction * normalizer.scale + normalizer.mean) - raw_prediction))
    max_difference = max(differences) if differences else float("inf")
    checks["independent_double_forward"] = bool(differences) and max_difference < 2e-4
    checks["selected_records_cover_all_partitions"] = len(selected_predictions) == 4

    failures = [name for name, passed in checks.items() if not passed]
    report = {
        "status": "PASS" if not failures else "FAIL",
        "checks_passed": len(checks) - len(failures),
        "checks_total": len(checks),
        "checks": checks,
        "failures": failures,
        "velocity_mechanism_pass": recomputed_gate,
        "primary_comparisons_recomputed": recomputed_comparisons,
        "max_double_forward_absolute_error": max_difference,
        "rk_g1_pass": False,
        "expensive_generation_authorized": False,
        "functional_transfer_closed": False,
        "cross_head_consistency_closed": False,
        "source_hashes": {
            "raw_sha256": file_sha256(args.raw_jsonl),
            "data_sha256": file_sha256(args.data),
            "config_sha256": file_sha256(args.config),
            "prepare_script_sha256": file_sha256("scripts/a8_rk08_prepare_velocity.py"),
            "train_script_sha256": file_sha256("scripts/a8_rk08_train_velocity.py"),
            "verify_script_sha256": file_sha256(__file__),
        },
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "failures": failures, "velocity_mechanism_pass": recomputed_gate, "max_double_forward_absolute_error": max_difference}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
