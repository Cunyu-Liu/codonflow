"""Independently verify A10-02/E1 outputs from the frozen RK37 development NPZ files.

No CodonFlow production module is imported. The verifier rebuilds the split,
calibration, predictions, transcript effects, inference, Gate and artifact hashes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np


PROTOCOL = "a10_02_e1_observation_protocol_v1"
PROTOCOL_SCHEMA = "a10-02-e1-observation-protocol-v1"
REPORT_SCHEMA = "a10-02-e1-observation-report-v1"
SUMMARY_SCHEMA = "a10-02-e1-observation-summary-v1"
VERIFICATION_SCHEMA = "a10-02-e1-observation-independent-verification-v1"
EXPECTED_TRANSCRIPTS = 3921
EXPECTED_INPUT_SHA256 = {
    1234: "dc3f06a2df0114f3bf02ccad37018e9d1c0654b0e87ebed1bd9292cd14edcfc8",
    2345: "896489c8774216b7667dd7a203f6219f2aa8a1bcc777f02bc838638e0c1048ef",
    3456: "79d35876312778d6497db1cf085496e8ef9de326605b39707674e3f8baf5ce31",
}
SEEDS = (1234, 2345, 3456)
SPLIT_SEED = 9100201
INFERENCE_SEED = 9100202
RESAMPLING_BATCH = 512
RESAMPLES = 20000
INPUT_KEYS = {
    "raw_unanchored": "prediction_position_raw_unanchored",
    "raw_anchored": "prediction_position_raw_anchored",
    "constant": "prediction_constant",
}
REQUIRED_ARRAYS = ["offsets", "positions", "target", *INPUT_KEYS.values()]
ENDPOINTS = (
    "raw_unanchored_minus_calibrated_tb_mse",
    "raw_anchored_minus_calibrated_tb_mse",
)
ENDPOINT_EFFECT_FIELDS = {
    ENDPOINTS[0]: "effect_unanchored",
    ENDPOINTS[1]: "effect_anchored",
}
PREDICTOR_NAMES = [
    "raw_unanchored", "raw_anchored", "constant",
    "calibrated_unanchored", "calibrated_anchored",
]
CSV_FIELDS = [
    "seed", "transcript_index", "n_positions",
    "mse_raw_unanchored", "mse_calibrated_unanchored", "effect_unanchored",
    "mse_raw_anchored", "mse_calibrated_anchored", "effect_anchored", "mse_constant",
    "pearson_raw_unanchored", "pearson_calibrated_unanchored",
    "spearman_raw_unanchored", "spearman_calibrated_unanchored",
    "pearson_raw_anchored", "pearson_calibrated_anchored",
    "spearman_raw_anchored", "spearman_calibrated_anchored",
    "pearson_constant", "spearman_constant",
]
POINT_ARRAYS = [
    "offsets", "transcript_indices", "transcript_index", "positions", "target",
    *INPUT_KEYS, "calibrated_unanchored", "calibrated_anchored",
]
SUMMARY_KEYS = {
    "schema", "protocol", "scope", "status", "h1_development_positive",
    "decision_rule", "across_seeds", "seeds", "input_access_log", "cost",
    "environment", "sha256", "limitations",
}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(payload):
    return (json.dumps(
        payload, indent=2, ensure_ascii=False, allow_nan=False,
    ) + "\n").encode("utf-8")


def write_json_exclusive(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(canonical_json_bytes(payload))


def reject_nonfinite_json(value):
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="strict") as handle:
        payload = json.load(handle, parse_constant=reject_nonfinite_json)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def load_protocol(path, allow_synthetic=False):
    protocol = load_json(path)
    if protocol.get("schema") != PROTOCOL_SCHEMA or protocol.get("protocol") != PROTOCOL:
        raise ValueError("observation protocol identity mismatch")
    inputs = protocol.get("inputs", {})
    if inputs.get("required_arrays") != REQUIRED_ARRAYS or inputs.get("allow_pickle") is not False:
        raise ValueError("protocol must freeze the RK37 arrays and forbid pickle")
    count = inputs.get("expected_transcripts")
    if isinstance(count, bool) or not isinstance(count, int) or count < 2:
        raise ValueError("protocol expected_transcripts must be an integer >=2")
    if inputs.get("expected_offsets_length") != count + 1:
        raise ValueError("protocol offsets length must equal transcript count + 1")
    specs = inputs.get("seeds", [])
    seeds = [item.get("seed") for item in specs]
    if not specs or len(set(seeds)) != len(seeds):
        raise ValueError("protocol seeds must be nonempty and unique")
    for item in specs:
        if isinstance(item["seed"], bool) or not isinstance(item["seed"], int):
            raise ValueError("protocol seed must be an integer")
        if re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")) is None:
            raise ValueError("protocol input SHA256 must be lowercase hexadecimal")
    split = protocol.get("split", {})
    if any((
        split.get("unit") != "transcript",
        split.get("method") != "numpy_default_rng_permutation_then_sorted_exact_allocation",
        split.get("calibration_fraction") != 0.5,
        split.get("calibration_count") != count // 2,
        split.get("test_count") != count - count // 2,
        split.get("shared_across_model_seeds") is not True,
        split.get("test_targets_used_for_fitting") is not False,
    )):
        raise ValueError("protocol transcript split does not match the frozen contract")
    model = protocol.get("observation_model", {})
    if any((
        model.get("formula") != "y = a + b * x",
        model.get("fit_split") != "calibration_only",
        model.get("slope_constraint") != "b >= 0",
        model.get("transcript_point_weight") != "1 / n_i",
    )):
        raise ValueError("protocol observation map does not match the frozen contract")
    evaluation = protocol.get("evaluation", {})
    if any((
        evaluation.get("split") != "test_only",
        evaluation.get("co_primary_endpoints") != list(ENDPOINTS),
        evaluation.get("correlation_invariance_required_for_positive_slope") is not True,
        evaluation.get("correlation_gain_claim_allowed") is not False,
    )):
        raise ValueError("protocol evaluation contract mismatch")
    inference = protocol.get("inference", {})
    for name in ("bootstrap", "signflip"):
        value = inference.get(name, {}).get("n_resamples")
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"protocol {name} count must be positive")
    batch = inference.get("batch_size")
    if isinstance(batch, bool) or not isinstance(batch, int) or batch < 1:
        raise ValueError("protocol inference batch_size must be positive")
    scope = protocol.get("scope", {})
    if any((
        scope.get("development_only") is not True,
        scope.get("studies") != {"Mohammad": "development_only", "Subtelny": "development_only"},
        scope.get("untouched") is not False,
        scope.get("absolute_elongation_rates") is not False,
        scope.get("cross_study_final_confirmation") is not False,
        scope.get("sota_claim") is not False,
    )):
        raise ValueError("protocol must preserve development-only claim boundaries")
    if protocol.get("outputs", {}).get("overwrite") != "forbidden":
        raise ValueError("protocol outputs must forbid overwrite")
    if not allow_synthetic:
        observed_hashes = {item["seed"]: item["sha256"] for item in specs}
        if any((
            count != EXPECTED_TRANSCRIPTS,
            observed_hashes != EXPECTED_INPUT_SHA256,
            split.get("seed") != SPLIT_SEED,
            inference.get("seed") != INFERENCE_SEED,
            inference.get("batch_size") != RESAMPLING_BATCH,
            inference["bootstrap"]["n_resamples"] != RESAMPLES,
            inference["signflip"]["n_resamples"] != RESAMPLES,
        )):
            raise ValueError("real verification requires the frozen three-seed RK37 protocol")
    return protocol


def deterministic_split(count, seed):
    permutation = np.random.default_rng(seed).permutation(count)
    calibration = np.sort(permutation[:count // 2]).astype(np.int64)
    test = np.sort(permutation[count // 2:]).astype(np.int64)
    return calibration, test


def read_input(path, expected_transcripts):
    with np.load(path, allow_pickle=False) as archive:
        missing = [name for name in REQUIRED_ARRAYS if name not in archive.files]
        if missing:
            raise ValueError(f"{path} missing arrays: {missing}")
        offsets = np.asarray(archive["offsets"])
        positions = np.asarray(archive["positions"]).copy()
        target = np.asarray(archive["target"], dtype=np.float64).copy()
        predictions = {
            name: np.asarray(archive[key], dtype=np.float64).copy()
            for name, key in INPUT_KEYS.items()
        }
    if offsets.ndim != 1 or not np.issubdtype(offsets.dtype, np.integer):
        raise ValueError("offsets must be a one-dimensional integer array")
    if len(offsets) != expected_transcripts + 1:
        raise ValueError("offsets length does not match expected_transcripts + 1")
    if offsets[0] != 0 or np.any(np.diff(offsets) <= 0):
        raise ValueError("offsets must start at zero and strictly increase")
    point_count = int(offsets[-1])
    if positions.ndim != 1 or len(positions) != point_count:
        raise ValueError("positions must match offsets[-1]")
    if target.ndim != 1 or len(target) != point_count or not np.all(np.isfinite(target)):
        raise ValueError("target must be finite and match offsets[-1]")
    for values in predictions.values():
        if values.ndim != 1 or len(values) != point_count or not np.all(np.isfinite(values)):
            raise ValueError("predictions must be finite and match offsets[-1]")
    return {
        "offsets": offsets.astype(np.int64, copy=False), "positions": positions,
        "target": target, **predictions,
    }


def fit_affine(x, y, transcript_ids):
    _, inverse, counts = np.unique(transcript_ids, return_inverse=True, return_counts=True)
    weights = 1.0 / counts[inverse]
    sw = float(np.sum(weights))
    sx = float(np.sum(weights * x))
    sy = float(np.sum(weights * y))
    mean_x = sx / sw
    mean_y = sy / sw
    denominator = float(np.sum(weights * (x - mean_x) ** 2))
    numerator = float(np.sum(weights * (x - mean_x) * (y - mean_y)))
    slope = max(0.0, numerator / denominator if denominator > 0 else 0.0)
    return {
        "a": float(mean_y - slope * mean_x), "b": float(slope),
        "n_transcripts": int(len(counts)), "n_positions": int(len(x)),
        "sum_transcript_weights": sw,
    }


def average_ranks(values):
    order = np.argsort(values, kind="mergesort")
    ordered = values[order]
    ranks = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        stop = start + 1
        while stop < len(values) and ordered[stop] == ordered[start]:
            stop += 1
        ranks[order[start:stop]] = (start + stop - 1) / 2.0 + 1.0
        start = stop
    return ranks


def correlation(x, y):
    if len(x) < 2 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    centered_x = x - np.mean(x)
    centered_y = y - np.mean(y)
    denominator = math.sqrt(float(np.sum(centered_x ** 2) * np.sum(centered_y ** 2)))
    if denominator == 0:
        return None
    value = float(np.sum(centered_x * centered_y) / denominator)
    return value if math.isfinite(value) else None


def transcript_records(data, predictions, transcript_indices):
    records = []
    offsets = data["offsets"]
    for transcript_index in transcript_indices:
        index = int(transcript_index)
        start, stop = int(offsets[index]), int(offsets[index + 1])
        y = data["target"][start:stop]
        record = {"transcript_index": index, "n_positions": stop - start}
        for name, values in predictions.items():
            prediction = values[start:stop]
            record[f"mse_{name}"] = float(np.mean((y - prediction) ** 2))
            record[f"pearson_{name}"] = correlation(prediction, y)
            ranked_prediction = average_ranks(prediction)
            ranked_target = average_ranks(y)
            record[f"spearman_{name}"] = (
                correlation(ranked_prediction, ranked_target)
                if record[f"pearson_{name}"] is not None else None
            )
        record["effect_unanchored"] = record["mse_raw_unanchored"] - record["mse_calibrated_unanchored"]
        record["effect_anchored"] = record["mse_raw_anchored"] - record["mse_calibrated_anchored"]
        records.append(record)
    return records


def mean_or_none(values):
    defined = [float(value) for value in values if value is not None]
    return float(np.mean(defined)) if defined else None


def summarize_metrics(records):
    return {
        "n_transcripts": len(records),
        "n_positions": int(sum(record["n_positions"] for record in records)),
        "tb_mse": {
            name: float(np.mean([record[f"mse_{name}"] for record in records]))
            for name in PREDICTOR_NAMES
        },
        "mean_per_transcript_pearson": {
            name: mean_or_none([record[f"pearson_{name}"] for record in records])
            for name in PREDICTOR_NAMES
        },
        "mean_per_transcript_spearman": {
            name: mean_or_none([record[f"spearman_{name}"] for record in records])
            for name in PREDICTOR_NAMES
        },
        "defined_correlation_counts": {
            name: {
                "pearson": sum(record[f"pearson_{name}"] is not None for record in records),
                "spearman": sum(record[f"spearman_{name}"] is not None for record in records),
            }
            for name in PREDICTOR_NAMES
        },
    }


def correlation_invariance(records, raw_name, calibrated_name, slope):
    if slope <= 0:
        return {
            "status": "not_applicable_b_zero", "passed": None, "n_compared": 0,
            "pearson_max_abs_difference": None, "spearman_max_abs_difference": None,
            "gain_claim_allowed": False,
        }
    differences = {"pearson": [], "spearman": []}
    matched = True
    for record in records:
        for metric in differences:
            raw = record[f"{metric}_{raw_name}"]
            calibrated = record[f"{metric}_{calibrated_name}"]
            if (raw is None) != (calibrated is None):
                matched = False
            elif raw is not None:
                differences[metric].append(abs(raw - calibrated))
    pearson_max = max(differences["pearson"], default=0.0)
    spearman_max = max(differences["spearman"], default=0.0)
    passed = (
        matched and math.isclose(pearson_max, 0.0, rel_tol=0.0, abs_tol=1e-12)
        and math.isclose(spearman_max, 0.0, rel_tol=0.0, abs_tol=1e-12)
    )
    return {
        "status": "verified" if passed else "failed", "passed": passed,
        "n_compared": len(differences["pearson"]),
        "pearson_max_abs_difference": pearson_max,
        "spearman_max_abs_difference": spearman_max,
        "gain_claim_allowed": False,
    }


def paired_inference(effects, n_bootstrap, n_signflip, seed, batch_size):
    effects = np.asarray(effects, dtype=np.float64)
    rng = np.random.default_rng(seed)
    count = len(effects)
    bootstrap = np.empty(n_bootstrap, dtype=np.float64)
    for start in range(0, n_bootstrap, batch_size):
        stop = min(start + batch_size, n_bootstrap)
        indices = rng.integers(0, count, size=(stop - start, count))
        bootstrap[start:stop] = np.mean(effects[indices], axis=1)
    observed = float(np.mean(effects))
    exceedances = 0
    for start in range(0, n_signflip, batch_size):
        stop = min(start + batch_size, n_signflip)
        signs = rng.integers(0, 2, size=(stop - start, count), dtype=np.int8) * 2 - 1
        null = np.mean(signs * effects, axis=1)
        exceedances += int(np.count_nonzero(np.abs(null) >= abs(observed)))
    return {
        "effect": observed,
        "bootstrap_95ci": [float(np.quantile(bootstrap, 0.025)), float(np.quantile(bootstrap, 0.975))],
        "signflip_p_two_sided": float((exceedances + 1) / (n_signflip + 1)),
        "n_bootstrap": n_bootstrap, "n_signflip": n_signflip, "n_transcripts": count,
    }


def holm_adjust(p_values):
    order = np.argsort(p_values)
    adjusted = np.empty(len(p_values), dtype=np.float64)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p_values) - rank) * p_values[index])
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def expected_points(data, calibrated, transcript_indices, point_transcript):
    transcript_indices = np.asarray(transcript_indices, dtype=np.int64)
    mask = np.isin(point_transcript, transcript_indices)
    counts = np.diff(data["offsets"])[transcript_indices]
    return {
        "offsets": np.concatenate(([0], np.cumsum(counts))).astype(np.int64),
        "transcript_indices": transcript_indices,
        "transcript_index": point_transcript[mask],
        "positions": data["positions"][mask],
        "target": data["target"][mask],
        **{name: data[name][mask] for name in INPUT_KEYS},
        **{name: values[mask] for name, values in calibrated.items()},
    }


def recompute_seed(protocol, seed, input_path, input_sha, calibration_indices, test_indices):
    data = read_input(input_path, protocol["inputs"]["expected_transcripts"])
    point_transcript = np.repeat(
        np.arange(protocol["inputs"]["expected_transcripts"], dtype=np.int64),
        np.diff(data["offsets"]),
    )
    calibration_mask = np.isin(point_transcript, calibration_indices)
    parameters = {}
    calibrated = {}
    for raw_name, calibrated_name in (
        ("raw_unanchored", "calibrated_unanchored"),
        ("raw_anchored", "calibrated_anchored"),
    ):
        parameters[raw_name] = fit_affine(
            data[raw_name][calibration_mask], data["target"][calibration_mask],
            point_transcript[calibration_mask],
        )
        calibrated[calibrated_name] = (
            parameters[raw_name]["a"] + parameters[raw_name]["b"] * data[raw_name]
        )
    predictions = {**{name: data[name] for name in INPUT_KEYS}, **calibrated}
    calibration_records = transcript_records(data, predictions, calibration_indices)
    test_records = transcript_records(data, predictions, test_indices)
    calibration_metrics = summarize_metrics(calibration_records)
    test_metrics = summarize_metrics(test_records)
    invariance = {
        "unanchored": correlation_invariance(
            test_records, "raw_unanchored", "calibrated_unanchored",
            parameters["raw_unanchored"]["b"],
        ),
        "anchored": correlation_invariance(
            test_records, "raw_anchored", "calibrated_anchored",
            parameters["raw_anchored"]["b"],
        ),
    }
    inference = protocol["inference"]
    endpoint_results = {}
    for endpoint_index, endpoint in enumerate(ENDPOINTS):
        effects = np.asarray([record[ENDPOINT_EFFECT_FIELDS[endpoint]] for record in test_records])
        endpoint_results[endpoint] = paired_inference(
            effects, inference["bootstrap"]["n_resamples"], inference["signflip"]["n_resamples"],
            [inference["seed"], seed, endpoint_index], inference["batch_size"],
        )
    adjusted = holm_adjust([endpoint_results[endpoint]["signflip_p_two_sided"] for endpoint in ENDPOINTS])
    for endpoint, holm_p in zip(ENDPOINTS, adjusted):
        result = endpoint_results[endpoint]
        result["holm_p"] = holm_p
        result["effect_positive"] = result["effect"] > 0.0
        result["bootstrap_ci_lower_positive"] = result["bootstrap_95ci"][0] > 0.0
        result["holm_significant"] = holm_p < inference["holm"]["alpha"]
        result["passes"] = all((
            result["effect_positive"], result["bootstrap_ci_lower_positive"],
            result["holm_significant"],
        ))
    result = {
        "schema": REPORT_SCHEMA, "protocol": PROTOCOL, "seed": seed,
        "scope": protocol["scope"],
        "input": {"path": str(input_path), "sha256": input_sha},
        "split": {
            "seed": protocol["split"]["seed"],
            "calibration_transcript_indices": calibration_indices.tolist(),
            "test_transcript_indices": test_indices.tolist(),
            "calibration_count": len(calibration_indices), "test_count": len(test_indices),
            "test_targets_used_for_fitting": False,
        },
        "calibration": {"parameters": parameters, "metrics": calibration_metrics},
        "test": {
            "metrics": test_metrics, "correlation_invariance": invariance,
            "correlation_gain_claim_allowed": False, "endpoints": endpoint_results,
            "all_co_primary_pass": all(endpoint_results[endpoint]["passes"] for endpoint in ENDPOINTS),
        },
    }
    summary_seed = {
        "calibration_parameters": parameters, "test_metrics": test_metrics,
        "correlation_invariance": invariance, "endpoints": endpoint_results,
        "all_co_primary_pass": result["test"]["all_co_primary_pass"],
        "result_json": f"seed_{seed}/result.json",
    }
    artifacts = {
        "calibration_points.npz": expected_points(data, calibrated, calibration_indices, point_transcript),
        "test_points.npz": expected_points(data, calibrated, test_indices, point_transcript),
    }
    access = {
        "seed": seed, "path": str(input_path), "sha256_verified": True,
        "calibration_transcripts_used_for_fit": len(calibration_indices),
        "test_transcripts_used_only_for_final_evaluation": len(test_indices),
        "test_targets_used_for_fitting": False,
    }
    return result, summary_seed, test_records, artifacts, access, calibration_metrics["n_positions"], test_metrics["n_positions"]


def value_mismatches(observed, expected, path=""):
    if expected is None:
        return [] if observed is None else [path]
    if isinstance(expected, bool):
        return [] if observed is expected else [path]
    if isinstance(expected, int):
        return [] if isinstance(observed, int) and not isinstance(observed, bool) and observed == expected else [path]
    if isinstance(expected, float):
        if isinstance(observed, bool) or not isinstance(observed, (int, float)):
            return [path]
        return [] if math.isfinite(observed) and math.isclose(
            observed, expected, rel_tol=1e-9, abs_tol=1e-11,
        ) else [path]
    if isinstance(expected, str):
        return [] if observed == expected else [path]
    if isinstance(expected, list):
        if not isinstance(observed, list) or len(observed) != len(expected):
            return [path]
        return [
            mismatch for index, (left, right) in enumerate(zip(observed, expected))
            for mismatch in value_mismatches(left, right, f"{path}[{index}]")
        ]
    if isinstance(expected, dict):
        if not isinstance(observed, dict) or set(observed) != set(expected):
            return [path]
        return [
            mismatch for key, value in expected.items()
            for mismatch in value_mismatches(observed[key], value, f"{path}.{key}")
        ]
    return [path]


def compare_points(observed, expected):
    if set(observed) != set(expected):
        return ["point_arrays.keys"]
    mismatches = []
    exact = {"offsets", "transcript_indices", "transcript_index", "positions", "target", *INPUT_KEYS}
    for name, expected_values in expected.items():
        observed_values = observed[name]
        if observed_values.shape != expected_values.shape:
            mismatches.append(f"{name}.shape")
        elif name in exact:
            if not np.array_equal(observed_values, expected_values):
                mismatches.append(name)
        elif not np.allclose(observed_values, expected_values, rtol=1e-9, atol=1e-11):
            mismatches.append(name)
    return mismatches


def compare_csv(path, seed, expected_records):
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != CSV_FIELDS:
            return ["CSV header"]
        rows = list(reader)
    if len(rows) != len(expected_records):
        return ["CSV row count"]
    mismatches = []
    for index, (observed, expected) in enumerate(zip(rows, expected_records)):
        for field in CSV_FIELDS:
            if field == "seed":
                valid = observed[field] == str(seed)
            elif field in ("transcript_index", "n_positions"):
                try:
                    valid = int(observed[field]) == expected[field]
                except ValueError:
                    valid = False
            elif expected[field] is None:
                valid = observed[field] == ""
            else:
                try:
                    value = float(observed[field])
                    valid = math.isfinite(value) and math.isclose(
                        value, expected[field], rel_tol=1e-9, abs_tol=1e-11,
                    )
                except ValueError:
                    valid = False
            if not valid:
                mismatches.append(f"row[{index}].{field}")
    return mismatches


def valid_result_cost(cost, calibration_positions, test_positions):
    if not isinstance(cost, dict) or set(cost) != {
        "wall_clock_seconds", "calibration_positions", "test_positions",
    }:
        return False
    wall = cost["wall_clock_seconds"]
    return (
        isinstance(wall, (int, float)) and not isinstance(wall, bool)
        and math.isfinite(wall) and wall >= 0
        and cost["calibration_positions"] == calibration_positions
        and cost["test_positions"] == test_positions
    )


def valid_summary_cost(cost, seed_results):
    if not isinstance(cost, dict) or set(cost) != {
        "started_utc", "finished_utc", "wall_clock_seconds", "per_seed_wall_clock_seconds",
    }:
        return False
    try:
        datetime.fromisoformat(cost["started_utc"])
        datetime.fromisoformat(cost["finished_utc"])
    except (TypeError, ValueError):
        return False
    wall = cost["wall_clock_seconds"]
    per_seed = cost["per_seed_wall_clock_seconds"]
    return (
        isinstance(wall, (int, float)) and not isinstance(wall, bool)
        and math.isfinite(wall) and wall >= 0 and isinstance(per_seed, dict)
        and set(per_seed) == {str(seed) for seed in seed_results}
        and all(
            isinstance(per_seed[str(seed)], (int, float))
            and math.isclose(per_seed[str(seed)], result["cost"]["wall_clock_seconds"], rel_tol=0, abs_tol=0)
            for seed, result in seed_results.items()
        )
    )


def verify_e1_observation(protocol_path, inputs, output_dir, allow_synthetic_protocol=False):
    protocol_path = Path(protocol_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    protocol = load_protocol(protocol_path, allow_synthetic=allow_synthetic_protocol)
    inputs = {int(seed): Path(path).expanduser().resolve() for seed, path in inputs.items()}
    specs = protocol["inputs"]["seeds"]
    if set(inputs) != {item["seed"] for item in specs}:
        raise ValueError("input seeds must exactly match the protocol")
    actual_input_sha = {seed: sha256_file(path) for seed, path in inputs.items()}
    calibration_indices, test_indices = deterministic_split(
        protocol["inputs"]["expected_transcripts"], protocol["split"]["seed"],
    )
    expected_results = {}
    summary_seeds = {}
    expected_records = {}
    expected_points_by_seed = {}
    access_log = []
    position_counts = {}
    for item in specs:
        seed = item["seed"]
        (
            expected_results[seed], summary_seeds[str(seed)], expected_records[seed],
            expected_points_by_seed[seed], access, calibration_positions, test_positions,
        ) = recompute_seed(
            protocol, seed, inputs[seed], item["sha256"], calibration_indices, test_indices,
        )
        access_log.append(access)
        position_counts[seed] = (calibration_positions, test_positions)
    across_seeds = {}
    for endpoint in ENDPOINTS:
        effects = [expected_results[seed]["test"]["endpoints"][endpoint]["effect"] for seed in expected_results]
        across_seeds[endpoint] = {
            "effects": effects,
            "same_nonzero_sign": all(value > 0 for value in effects) or all(value < 0 for value in effects),
        }
    h1_positive = all(
        result["test"]["all_co_primary_pass"] for result in expected_results.values()
    ) and all(item["same_nonzero_sign"] for item in across_seeds.values())
    expected_summary_sections = {
        "schema": SUMMARY_SCHEMA, "protocol": PROTOCOL, "scope": protocol["scope"],
        "status": "h1_development_positive" if h1_positive else "h1_development_not_positive",
        "h1_development_positive": h1_positive,
        "decision_rule": protocol["inference"]["h1_development_positive_rule"],
        "across_seeds": across_seeds, "seeds": summary_seeds,
        "input_access_log": access_log, "limitations": protocol["limitations"],
    }
    relative_files = ["summary.json"] + [
        f"seed_{seed}/{name}" for seed in expected_results for name in (
            "result.json", "calibration_points.npz", "test_points.npz", "test_transcript_effects.csv",
        )
    ]
    actual_artifact_hashes = {
        relative: sha256_file(output_dir / relative) for relative in relative_files if relative != "summary.json"
    }
    expected_sha = {
        "protocol": sha256_file(protocol_path),
        "implementation": sha256_file(Path(__file__).with_name("a10_02_e1_observation.py")),
        "inputs": {str(seed): str(inputs[seed]) for seed in sorted(inputs)},
        "input_files": {str(item["seed"]): item["sha256"] for item in specs},
        "artifacts": actual_artifact_hashes,
    }
    summary = load_json(output_dir / "summary.json")
    checks = {
        f"input_{seed}_sha256": actual_input_sha[seed] == next(
            item["sha256"] for item in specs if item["seed"] == seed
        ) for seed in inputs
    }
    details = {}
    observed_files = sorted(
        str(path.relative_to(output_dir)) for path in output_dir.rglob("*") if path.is_file()
    )
    checks["output_files_exact"] = observed_files == sorted(relative_files)
    for section, expected in expected_summary_sections.items():
        mismatches = value_mismatches(summary.get(section), expected, f"summary.{section}")
        checks[f"summary_{section}"] = not mismatches
        details[f"summary_{section}"] = mismatches[:100]
    checks["summary_top_level_keys"] = set(summary) == SUMMARY_KEYS
    sha_mismatches = value_mismatches(summary.get("sha256"), expected_sha, "summary.sha256")
    checks["summary_sha256"] = not sha_mismatches
    details["summary_sha256"] = sha_mismatches[:100]
    checks["summary_environment"] = (
        isinstance(summary.get("environment"), dict)
        and set(summary["environment"]) == {"python", "platform", "machine", "numpy", "scipy"}
        and all(isinstance(value, str) and bool(value) for value in summary["environment"].values())
    )
    observed_results = {}
    for seed in expected_results:
        result_path = output_dir / f"seed_{seed}" / "result.json"
        observed = load_json(result_path)
        observed_results[seed] = observed
        scientific = {key: value for key, value in observed.items() if key != "cost"}
        mismatches = value_mismatches(scientific, expected_results[seed], f"seed_{seed}.result")
        checks[f"result_{seed}_values"] = not mismatches
        details[f"result_{seed}"] = mismatches[:100]
        checks[f"result_{seed}_cost"] = valid_result_cost(observed.get("cost"), *position_counts[seed])
        checks[f"correlation_invariance_{seed}"] = all(
            item["passed"] is not False
            for item in expected_results[seed]["test"]["correlation_invariance"].values()
        )
        for name, expected in expected_points_by_seed[seed].items():
            with np.load(output_dir / f"seed_{seed}" / name, allow_pickle=False) as archive:
                observed_points = {key: np.asarray(archive[key]).copy() for key in archive.files}
            mismatches = compare_points(observed_points, expected)
            checks[f"{name}_{seed}_values"] = not mismatches
            details[f"{name}_{seed}"] = mismatches[:100]
        mismatches = compare_csv(
            output_dir / f"seed_{seed}" / "test_transcript_effects.csv", seed, expected_records[seed],
        )
        checks[f"test_transcript_effects_{seed}_values"] = not mismatches
        details[f"test_transcript_effects_{seed}"] = mismatches[:100]
    checks["summary_cost"] = valid_summary_cost(summary.get("cost"), observed_results)
    return {
        "schema": VERIFICATION_SCHEMA, "protocol": PROTOCOL,
        "passed": bool(all(checks.values())), "scope": protocol["scope"],
        "output_dir": str(output_dir), "summary_sha256": sha256_file(output_dir / "summary.json"),
        "protocol_sha256": sha256_file(protocol_path),
        "verification_script_sha256": sha256_file(__file__),
        "input_sha256": {str(seed): value for seed, value in actual_input_sha.items()},
        "checks": checks, "mismatches": details,
        "recomputed": {
            "h1_development_positive": h1_positive,
            "status": expected_summary_sections["status"], "across_seeds": across_seeds,
        },
    }


def parse_input(value):
    seed, separator, path = value.partition("=")
    if not separator or not path:
        raise argparse.ArgumentTypeError("input must use SEED=PATH")
    try:
        return int(seed), path
    except ValueError as exc:
        raise argparse.ArgumentTypeError("input seed must be an integer") from exc


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--input", dest="inputs", action="append", type=parse_input, required=True, metavar="SEED=PATH")
    parser.add_argument("--output-dir", required=True, help="Existing production output directory")
    parser.add_argument("--output", required=True, help="New exclusive verification JSON")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    try:
        result = verify_e1_observation(args.protocol, dict(args.inputs), args.output_dir)
    except Exception as exc:
        result = {
            "schema": VERIFICATION_SCHEMA, "protocol": PROTOCOL, "passed": False,
            "output_dir": args.output_dir,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    write_json_exclusive(output, result)
    print(json.dumps({"output": str(output), "passed": result["passed"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
