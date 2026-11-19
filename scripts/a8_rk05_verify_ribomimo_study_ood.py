#!/usr/bin/env python3
"""Independent raw-data/statistical verifier for frozen RiboMIMO study OOD.

This module deliberately does not import the production driver. It reconstructs
official eligibility/normalization/masks, source splits, ridge models, target
metrics and paired inference; it also compares independent-retrain arrays and
checkpoint tensors exactly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re

import numpy as np
from scipy.stats import rankdata
from sklearn.linear_model import Ridge


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dump_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def parse_official_matrix(path: Path, study: str) -> tuple[dict, int]:
    lines = path.read_text().splitlines()
    if len(lines) % 3:
        raise ValueError(f"Bad matrix: {path}")
    records = {}
    raw_count = len(lines) // 3
    for index in range(raw_count):
        header, sequence_row, count_row = lines[3 * index:3 * index + 3]
        raw_id = header[1:].split()[0]
        record_id = f"{study}|{raw_id}"
        codons = sequence_row.split()
        cds = "".join(codons)
        counts = np.asarray([float(value) for value in count_row.split()], dtype=np.float64)
        if len(codons) != len(counts):
            raise ValueError(f"Length mismatch: {record_id}")
        positive = counts > 0.5
        coverage = float(np.mean(positive))
        if coverage <= 0.6 or "N" in cds:
            continue
        if not np.any(positive):
            raise ValueError(f"Eligible record has empty normalization: {record_id}")
        average = float(np.mean(counts[positive]))
        density = positive * counts / average
        records[record_id] = {"cds": cds, "codons": codons, "density": density}
    return records, raw_count


def masked(density: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    modified = density.copy()
    modified[:5] = 0
    modified[-4:] = 0
    positions = np.flatnonzero(modified > 0).astype(np.int32)
    return modified[positions].astype(np.float32), positions


def features(codons: list[str]) -> np.ndarray:
    nts = "ATCG"
    mapping = {}
    for first in nts:
        for second in nts:
            for third in nts:
                mapping[first + second + third] = len(mapping)
    n = len(codons)
    result = np.zeros((n, 86), dtype=np.float64)
    for position, codon in enumerate(codons):
        result[position, mapping[codon]] = 1.0
        relative = position / max(n - 1, 1)
        position_bin = min(19, int(relative * 20))
        result[position, 64 + position_bin] = 1.0
        result[position, 84] = relative
        result[position, 85] = math.log(n) / 7.0
    return result


def split_source(ids: list[str], seed: int) -> tuple[list[str], list[str], int]:
    ordered = np.array(sorted(ids), dtype=object)
    np.random.seed(seed)
    split_seed = int(np.random.randint(0, 1024, 1)[0])
    np.random.seed(split_seed)
    np.random.shuffle(ordered)
    n_valid = len(ordered) // 10
    return ordered[n_valid:].tolist(), ordered[:n_valid].tolist(), split_seed


def labels(records: dict, ids: list[str]) -> dict[str, np.ndarray]:
    offsets = [0]
    position_arrays, target_arrays = [], []
    for record_id in ids:
        target, positions = masked(records[record_id]["density"])
        target_arrays.append(target)
        position_arrays.append(positions)
        offsets.append(offsets[-1] + len(target))
    return {
        "record_ids": np.asarray(ids),
        "offsets": np.asarray(offsets, dtype=np.int64),
        "positions": np.concatenate(position_arrays),
        "target": np.concatenate(target_arrays),
    }


def per_transcript(labels_dict: dict[str, np.ndarray], prediction: np.ndarray) -> dict[str, np.ndarray]:
    mse, pearson, spearman = [], [], []
    target_all = labels_dict["target"].astype(np.float64)
    prediction = np.asarray(prediction, dtype=np.float64)
    for index in range(len(labels_dict["record_ids"])):
        start, end = labels_dict["offsets"][index:index + 2]
        y, p = target_all[start:end], prediction[start:end]
        mse.append(float(np.mean((y - p) ** 2)))
        if len(y) >= 2 and np.std(y) > 0 and np.std(p) > 0:
            pearson.append(float(np.mean((y - np.mean(y)) * (p - np.mean(p))) / (np.std(y) * np.std(p))))
            ry, rp = rankdata(y), rankdata(p)
            spearman.append(float(np.mean((ry - np.mean(ry)) * (rp - np.mean(rp))) / (np.std(ry) * np.std(rp))))
        else:
            pearson.append(float("nan"))
            spearman.append(float("nan"))
    return {"mse": np.asarray(mse), "pearson": np.asarray(pearson), "spearman": np.asarray(spearman)}


def summarize(labels_dict: dict[str, np.ndarray], prediction: np.ndarray) -> dict:
    per = per_transcript(labels_dict, prediction)
    y = labels_dict["target"].astype(np.float64)
    p = np.asarray(prediction, dtype=np.float64)
    global_pearson = None
    if np.std(y) > 0 and np.std(p) > 0:
        global_pearson = float(np.mean((y - np.mean(y)) * (p - np.mean(p))) / (np.std(y) * np.std(p)))
    def finite_stat(values, kind="mean"):
        values = values[np.isfinite(values)]
        if not len(values):
            return None
        return float(np.mean(values) if kind == "mean" else np.median(values))
    return {
        "n_transcripts": int(len(y) * 0 + len(labels_dict["record_ids"])),
        "n_masked_positions": int(len(y)),
        "n_transcripts_with_pearson": int(np.isfinite(per["pearson"]).sum()),
        "n_transcripts_with_spearman": int(np.isfinite(per["spearman"]).sum()),
        "transcript_balanced_mse": finite_stat(per["mse"]),
        "mean_transcript_pearson": finite_stat(per["pearson"]),
        "median_transcript_pearson": finite_stat(per["pearson"], "median"),
        "mean_transcript_spearman": finite_stat(per["spearman"]),
        "global_r2": float(1 - np.sum((y - p) ** 2) / np.sum((y - np.mean(y)) ** 2)),
        "global_mse": float(np.mean((y - p) ** 2)),
        "global_pearson": global_pearson,
    }, per


def fit_independent_ridge(records: dict, train_ids: list[str], valid_ids: list[str], target_ids: list[str], alphas: list[float]) -> dict:
    x_parts, y_parts = [], []
    for record_id in train_ids:
        target, positions = masked(records[record_id]["density"])
        x_parts.append(features(records[record_id]["codons"])[positions])
        y_parts.append(target.astype(np.float64))
    x_train, y_train = np.concatenate(x_parts), np.concatenate(y_parts)
    valid_labels = labels(records, valid_ids)
    target_labels = labels(records, target_ids)
    candidates = []
    models = []
    for alpha in alphas:
        model = Ridge(alpha=float(alpha), fit_intercept=True, solver="lsqr", tol=1e-8, max_iter=10000)
        model.fit(x_train, y_train)
        valid_prediction = np.empty(valid_labels["target"].shape, dtype=np.float64)
        for index, record_id in enumerate(valid_ids):
            start, end = valid_labels["offsets"][index:index + 2]
            positions = valid_labels["positions"][start:end]
            valid_prediction[start:end] = model.predict(features(records[record_id]["codons"])[positions])
        valid_metrics, _ = summarize(valid_labels, valid_prediction)
        candidates.append(valid_metrics)
        models.append(model)
    chosen = min(range(len(alphas)), key=lambda index: (candidates[index]["transcript_balanced_mse"], index))
    model = models[chosen]
    target_prediction = np.empty(target_labels["target"].shape, dtype=np.float64)
    for index, record_id in enumerate(target_ids):
        start, end = target_labels["offsets"][index:index + 2]
        positions = target_labels["positions"][start:end]
        target_prediction[start:end] = model.predict(features(records[record_id]["codons"])[positions])
    return {
        "selected_alpha": float(alphas[chosen]),
        "validation_metrics": candidates,
        "target_prediction": target_prediction,
        "target_labels": target_labels,
        "constant": float(np.mean(y_train)),
        "train_positions": int(len(y_train)),
    }


def inference(model_per: dict[str, np.ndarray], ridge_per: dict[str, np.ndarray], bootstrap_seed: int, permutation_seed: int, resamples: int) -> list[dict]:
    boot_rng = np.random.default_rng(bootstrap_seed)
    perm_rng = np.random.default_rng(permutation_seed)
    results = []
    for metric, direction in (("mse", "negative_favors_ribomimo"), ("pearson", "positive_favors_ribomimo")):
        valid = np.isfinite(model_per[metric]) & np.isfinite(ridge_per[metric])
        differences = model_per[metric][valid] - ridge_per[metric][valid]
        n = len(differences)
        observed = float(np.mean(differences))
        boot = []
        for _ in range(resamples):
            boot.append(float(np.mean(differences[boot_rng.integers(0, n, n)])))
        perm = []
        for _ in range(resamples):
            perm.append(float(np.mean(differences * perm_rng.choice(np.asarray([-1.0, 1.0]), size=n))))
        results.append({
            "metric": "transcript_balanced_mse" if metric == "mse" else "mean_transcript_pearson",
            "direction": direction,
            "n_pairs": int(n),
            "point_delta_ribomimo_minus_ridge": observed,
            "ci95_low": float(np.quantile(boot, 0.025)),
            "ci95_high": float(np.quantile(boot, 0.975)),
            "sign_flip_pvalue": float((1 + np.count_nonzero(np.abs(perm) >= abs(observed))) / (resamples + 1)),
        })
    order = sorted(range(2), key=lambda index: results[index]["sign_flip_pvalue"])
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (2 - rank) * results[index]["sign_flip_pvalue"]))
        results[index]["holm_pvalue"] = running
    return results


def arrays_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with np.load(path, allow_pickle=False) as data:
        for name in sorted(data.files):
            array = np.ascontiguousarray(data[name])
            digest.update(name.encode())
            digest.update(array.dtype.str.encode())
            digest.update(json.dumps(array.shape).encode())
            digest.update(array.tobytes())
    return digest.hexdigest()


def resolve_run_path(report: dict, value: str | Path) -> Path:
    """Resolve official-runner paths against that run's frozen runtime root."""
    path = Path(value)
    if path.is_absolute():
        return path
    runtime = Path(report["artifacts"]["driver"]["path"]).resolve().parent / "src"
    return (runtime / path).resolve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--production-report", required=True)
    parser.add_argument("--independent-report", "--independent-retrain-report", dest="independent_report", required=True)
    parser.add_argument("--driver", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    protocol_path = Path(args.protocol).resolve()
    protocol = json.loads(protocol_path.read_text())
    production_path = Path(args.production_report).resolve()
    independent_path = Path(args.independent_report).resolve()
    production = json.loads(production_path.read_text())
    independent = json.loads(independent_path.read_text())
    checks = []
    details = {"seeds": [], "max_differences": {}}

    def check(name: str, condition: bool, evidence=None) -> None:
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})

    def close_enough(left, right, tolerance=1e-10) -> bool:
        if left is None or right is None:
            return left is right
        return math.isfinite(float(left)) and math.isfinite(float(right)) and abs(float(left) - float(right)) <= tolerance

    check("production_status", production["status"] == "PASS_STUDY_OOD_PENDING_INDEPENDENT", production["status"])
    check("independent_status", independent["status"] == "PASS_STUDY_OOD_PENDING_INDEPENDENT", independent["status"])
    check("production_protocol_hash", production["protocol_sha256"] == sha256(protocol_path))
    check("independent_protocol_hash", independent["protocol_sha256"] == sha256(protocol_path))
    check("frozen_driver_hash_production", production["prepare"]["driver_sha256"] == sha256(args.driver))
    check("frozen_driver_hash_independent", independent["prepare"]["driver_sha256"] == sha256(args.driver))
    check("driver_identical_across_runs", production["prepare"]["driver_sha256"] == independent["prepare"]["driver_sha256"])
    check("primary_seed_frozen", production["primary_seed"] == 1234 and independent["primary_seed"] == 1234)
    check("two_primary_endpoints", len(production["primary_comparisons"]) == 2)
    check("no_functional_ood_claim", production["scientific_scope"]["functional_ood_claim"] is False)
    check("no_homology_ood_claim", production["scientific_scope"]["homology_ood_claim"] is False)
    check("no_generation_authorization", production["scientific_scope"]["generation_authorized"] is False)

    source_records, source_raw = parse_official_matrix(Path(protocol["studies"]["source_matrix"]["path"]), protocol["studies"]["source"])
    target_records, target_raw = parse_official_matrix(Path(protocol["studies"]["target_matrix"]["path"]), protocol["studies"]["target"])
    check("source_raw_count", source_raw == protocol["studies"]["source_matrix"]["raw_records"], source_raw)
    check("target_raw_count", target_raw == protocol["studies"]["target_matrix"]["raw_records"], target_raw)
    check("source_eligible_count", len(source_records) == 1179, len(source_records))
    check("target_eligible_count", len(target_records) == 3921, len(target_records))
    overlap = set(value["cds"] for value in source_records.values()) & set(value["cds"] for value in target_records.values())
    check("exact_cds_disjoint", len(overlap) == 0, len(overlap))
    source_ids, target_ids = sorted(source_records), sorted(target_records)
    seeds = [1234, 2345, 3456]
    check("run_count_three", len(production["runs"]) == 3 and len(independent["runs"]) == 3)
    max_model_difference = 0.0
    max_ridge_difference = 0.0
    max_ridge_refit_difference = 0.0
    max_metric_difference = 0.0
    primary_recomputed = None
    for run_index, seed in enumerate(seeds):
        prod = production["runs"][run_index]
        ind = independent["runs"][run_index]
        train_ids, valid_ids, split_seed = split_source(source_ids, seed)
        check(f"seed{seed}_identity", prod["seed"] == seed and ind["seed"] == seed)
        check(f"seed{seed}_split_seed", prod["split_seed"] == split_seed == ind["split_seed"], split_seed)
        check(f"seed{seed}_split_sizes", (len(train_ids), len(valid_ids), len(target_ids)) == (prod["source_train_records"], prod["source_validation_records"], prod["target_records"]) == (1062, 117, 3921))
        check(f"seed{seed}_best_epoch_reproduced", prod["best_epoch"] == ind["best_epoch"], {"production": prod["best_epoch"], "independent": ind["best_epoch"]})
        check(f"seed{seed}_epochs_reproduced", prod["epochs_completed"] == ind["epochs_completed"])
        check(f"seed{seed}_best_validation_reproduced", prod["best_validation_r2"] == ind["best_validation_r2"])
        import torch
        prod_checkpoint = resolve_run_path(production, prod["checkpoint"])
        ind_checkpoint = resolve_run_path(independent, ind["checkpoint"])
        prod_state = torch.load(prod_checkpoint, map_location="cpu", weights_only=True)
        ind_state = torch.load(ind_checkpoint, map_location="cpu", weights_only=True)
        expected_state_shapes = {
            "rnn.weight_ih_l0": (768, 97), "rnn.weight_hh_l0": (768, 256),
            "rnn.bias_ih_l0": (768,), "rnn.bias_hh_l0": (768,),
            "rnn.weight_ih_l0_reverse": (768, 97), "rnn.weight_hh_l0_reverse": (768, 256),
            "rnn.bias_ih_l0_reverse": (768,), "rnn.bias_hh_l0_reverse": (768,),
            "rnn.weight_ih_l1": (768, 512), "rnn.weight_hh_l1": (768, 256),
            "rnn.bias_ih_l1": (768,), "rnn.bias_hh_l1": (768,),
            "rnn.weight_ih_l1_reverse": (768, 512), "rnn.weight_hh_l1_reverse": (768, 256),
            "rnn.bias_ih_l1_reverse": (768,), "rnn.bias_hh_l1_reverse": (768,),
            "fc.0.weight": (256, 512), "fc.0.bias": (256,),
            "fc_reg.weight": (1, 256), "fc_reg.bias": (1,),
            "fc_cla.weight": (3, 256), "fc_cla.bias": (3,),
        }
        check(f"seed{seed}_checkpoint_parameter_schema", set(prod_state) == set(expected_state_shapes) and all(tuple(prod_state[key].shape) == shape for key, shape in expected_state_shapes.items()))
        trainable_parameter_count = int(sum(value.numel() for value in prod_state.values()))
        check(f"seed{seed}_trainable_parameter_count", trainable_parameter_count == 1860356, trainable_parameter_count)
        check(f"seed{seed}_checkpoint_state_value_count", prod["checkpoint_parameter_count"] == ind["checkpoint_parameter_count"] == trainable_parameter_count, trainable_parameter_count)
        check(f"seed{seed}_checkpoint_tensor_hash", prod["checkpoint_tensor_sha256"] == ind["checkpoint_tensor_sha256"])
        check(f"seed{seed}_checkpoint_tensors_exact", set(ind_state) == set(prod_state) and all(torch.equal(prod_state[key], ind_state[key]) for key in prod_state))
        prod_predictions = resolve_run_path(production, prod["target_predictions"])
        ind_predictions = resolve_run_path(independent, ind["target_predictions"])
        check(f"seed{seed}_prediction_array_hashes_bound", prod["target_predictions_arrays_sha256"] == arrays_digest(prod_predictions) and ind["target_predictions_arrays_sha256"] == arrays_digest(ind_predictions))
        check(f"seed{seed}_ridge_alpha_reproduced", prod["ridge_selected_alpha"] == ind["ridge_selected_alpha"])
        check(f"seed{seed}_constant_reproduced", prod["constant_source_train_mean_density"] == ind["constant_source_train_mean_density"])
        log_text = resolve_run_path(production, prod["official_log"]).read_text()
        check(f"seed{seed}_no_epoch_target_evaluation", not re.search(r", Test,", log_text))
        check(f"seed{seed}_target_after_checkpoint", prod_predictions.stat().st_mtime >= prod_checkpoint.stat().st_mtime)
        with np.load(prod_predictions, allow_pickle=False) as p_arrays, np.load(ind_predictions, allow_pickle=False) as i_arrays:
            check(f"seed{seed}_array_names", sorted(p_arrays.files) == sorted(i_arrays.files))
            for name in p_arrays.files:
                same_schema = p_arrays[name].shape == i_arrays[name].shape and p_arrays[name].dtype == i_arrays[name].dtype
                if name == "ridge_prediction":
                    difference = float(np.max(np.abs(p_arrays[name] - i_arrays[name])))
                    check(f"seed{seed}_independent_array_{name}", same_schema and difference <= 1e-6, {"max_abs_difference": difference, "absolute_tolerance": 1e-6, "reason": "independent LSQR/BLAS floating-point reduction; scientific metrics are recomputed independently"})
                else:
                    check(f"seed{seed}_independent_array_{name}", same_schema and np.array_equal(p_arrays[name], i_arrays[name]))
            target_label = labels(target_records, target_ids)
            check(f"seed{seed}_record_ids_raw", np.array_equal(p_arrays["record_ids"], target_label["record_ids"]))
            check(f"seed{seed}_offsets_raw", np.array_equal(p_arrays["offsets"], target_label["offsets"]))
            check(f"seed{seed}_positions_raw", np.array_equal(p_arrays["positions"], target_label["positions"]))
            check(f"seed{seed}_targets_raw", np.array_equal(p_arrays["target"], target_label["target"]))
            expected_hashes = np.asarray([hashlib.sha256(target_records[record_id]["cds"].encode()).hexdigest() for record_id in target_ids])
            check(f"seed{seed}_cds_hashes_raw", np.array_equal(p_arrays["cds_sha256"], expected_hashes))
            check(f"seed{seed}_finite_model_predictions", bool(np.isfinite(p_arrays["model_prediction"]).all()))
            check(f"seed{seed}_finite_ridge_predictions", bool(np.isfinite(p_arrays["ridge_prediction"]).all()))
            model_diff = float(np.max(np.abs(p_arrays["model_prediction"] - i_arrays["model_prediction"])))
            ridge_diff = float(np.max(np.abs(p_arrays["ridge_prediction"] - i_arrays["ridge_prediction"])))
            max_model_difference = max(max_model_difference, model_diff)
            max_ridge_difference = max(max_ridge_difference, ridge_diff)
            ridge_fit = fit_independent_ridge({**source_records, **target_records}, train_ids, valid_ids, target_ids, protocol["ridge_baseline"]["alpha_grid"])
            check(f"seed{seed}_ridge_alpha_raw_refit", ridge_fit["selected_alpha"] == prod["ridge_selected_alpha"], ridge_fit["selected_alpha"])
            check(f"seed{seed}_ridge_train_positions_raw", ridge_fit["train_positions"] == prod["source_train_masked_positions_ridge"])
            refit_diff = float(np.max(np.abs(ridge_fit["target_prediction"] - p_arrays["ridge_prediction"])))
            max_ridge_refit_difference = max(max_ridge_refit_difference, refit_diff)
            check(f"seed{seed}_ridge_predictions_raw_refit_within_solver_tolerance", refit_diff <= 1e-6, {"max_abs_difference": refit_diff, "absolute_tolerance": 1e-6, "reason": "independent raw-data LSQR/BLAS floating-point reduction; scientific metrics are recomputed independently"})
            model_metrics, model_per = summarize(target_label, p_arrays["model_prediction"])
            ridge_metrics, ridge_per = summarize(target_label, p_arrays["ridge_prediction"])
            for method, recomputed in (("ribomimo", model_metrics), ("ridge", ridge_metrics)):
                for metric, value in recomputed.items():
                    expected = prod["target_metrics"][method][metric]
                    if isinstance(value, (int, float)) and value is not None and expected is not None:
                        max_metric_difference = max(max_metric_difference, abs(float(value) - float(expected)))
                    check(f"seed{seed}_{method}_{metric}_raw", close_enough(value, expected, 1e-9), {"recomputed": value, "reported": expected})
            if seed == 1234:
                primary_recomputed = inference(model_per, ridge_per, protocol["evaluation"]["bootstrap"]["seed"], protocol["evaluation"]["permutation"]["seed"], protocol["evaluation"]["bootstrap"]["resamples"])
        details["seeds"].append({"seed": seed, "trainable_parameter_count": trainable_parameter_count, "checkpoint_state_value_count": prod["checkpoint_parameter_count"], "model_independent_max_abs": model_diff, "ridge_independent_max_abs": ridge_diff, "ridge_raw_refit_max_abs": refit_diff, "ridge_alpha": ridge_fit["selected_alpha"]})
    check("primary_inference_recomputed", primary_recomputed is not None)
    if primary_recomputed is not None:
        for expected, observed in zip(production["primary_comparisons"], primary_recomputed):
            for key in ("metric", "direction", "n_pairs"):
                check(f"primary_{expected['metric']}_{key}", expected[key] == observed[key], {"reported": expected[key], "recomputed": observed[key]})
            for key in ("point_delta_ribomimo_minus_ridge", "ci95_low", "ci95_high", "sign_flip_pvalue", "holm_pvalue"):
                check(f"primary_{expected['metric']}_{key}", close_enough(expected[key], observed[key], 1e-12), {"reported": expected[key], "recomputed": observed[key]})
    details["max_differences"] = {
        "model_independent_retrain": max_model_difference,
        "ridge_independent_retrain": max_ridge_difference,
        "ridge_raw_refit": max_ridge_refit_difference,
        "metrics_raw_recompute": max_metric_difference,
        "ridge_independent_absolute_tolerance": 1e-6,
        "ridge_raw_refit_absolute_tolerance": 1e-6,
    }
    details["numerical_comparison_policy"] = {
        "model_predictions_and_checkpoint_tensors": "exact_equality_required",
        "ridge_predictions": "absolute_tolerance_1e-6_for_independent_LSQR_BLAS_floating_point_reductions",
        "record_identity_offsets_positions_targets": "exact_equality_required",
        "primary_statistics": "recomputed_from_raw_predictions_and_compared_with_declared_metric_tolerances",
    }
    passed = sum(item["pass"] for item in checks)
    report = {
        "schema_version": "a8-rk05-ribomimo-study-ood-independent-v1",
        "status": "PASS_RK05_RIBOMIMO_STUDY_OOD_INDEPENDENT" if passed == len(checks) else "FAIL",
        "n_checks": len(checks),
        "n_passed": passed,
        "checks": checks,
        "details": details,
        "primary_comparisons_recomputed": primary_recomputed,
        "production_report": {"path": str(production_path), "sha256": sha256(production_path)},
        "independent_report": {"path": str(independent_path), "sha256": sha256(independent_path)},
        "protocol": {"path": str(protocol_path), "sha256": sha256(protocol_path)},
        "driver": {"path": str(Path(args.driver).resolve()), "sha256": sha256(args.driver)},
        "scientific_scope": "Independent numerical verification of an occupancy-derived cross-study baseline; not physical velocity, functional OOD, homology OOD, generation authorization or SOTA evidence.",
    }
    dump_json(Path(args.output), report)
    print(json.dumps({"status": report["status"], "passed": passed, "total": len(checks), "details": details, "primary": primary_recomputed}, indent=2))
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
