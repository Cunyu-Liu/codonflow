"""Fit and evaluate the frozen A10-02/E1 development observation maps."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import platform
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
from scipy import stats


PROTOCOL = "a10_02_e1_observation_protocol_v1"
REPORT_SCHEMA = "a10-02-e1-observation-report-v1"
SUMMARY_SCHEMA = "a10-02-e1-observation-summary-v1"
INPUT_KEYS = {
    "raw_unanchored": "prediction_position_raw_unanchored",
    "raw_anchored": "prediction_position_raw_anchored",
    "constant": "prediction_constant",
}
REQUIRED_ARRAYS = [
    "offsets",
    "positions",
    "target",
    *INPUT_KEYS.values(),
]
ENDPOINTS = (
    "raw_unanchored_minus_calibrated_tb_mse",
    "raw_anchored_minus_calibrated_tb_mse",
)
ENDPOINT_EFFECT_FIELDS = {
    ENDPOINTS[0]: "effect_unanchored",
    ENDPOINTS[1]: "effect_anchored",
}
CSV_FIELDS = [
    "seed",
    "transcript_index",
    "n_positions",
    "mse_raw_unanchored",
    "mse_calibrated_unanchored",
    "effect_unanchored",
    "mse_raw_anchored",
    "mse_calibrated_anchored",
    "effect_anchored",
    "mse_constant",
    "pearson_raw_unanchored",
    "pearson_calibrated_unanchored",
    "spearman_raw_unanchored",
    "spearman_calibrated_unanchored",
    "pearson_raw_anchored",
    "pearson_calibrated_anchored",
    "spearman_raw_anchored",
    "spearman_calibrated_anchored",
    "pearson_constant",
    "spearman_constant",
]


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_protocol(path):
    path = Path(path).expanduser().resolve()
    with path.open(encoding="utf-8") as handle:
        protocol = json.load(handle)
    if protocol.get("protocol") != PROTOCOL:
        raise ValueError(f"protocol identity mismatch: expected {PROTOCOL}")
    inputs = protocol.get("inputs", {})
    if inputs.get("required_arrays") != REQUIRED_ARRAYS:
        raise ValueError("protocol required_arrays do not match the frozen RK37 schema")
    if inputs.get("allow_pickle") is not False:
        raise ValueError("protocol must forbid pickle when loading NPZ inputs")
    expected_transcripts = inputs.get("expected_transcripts")
    if isinstance(expected_transcripts, bool) or not isinstance(expected_transcripts, int):
        raise ValueError("expected_transcripts must be an integer")
    if expected_transcripts < 2:
        raise ValueError("at least two transcripts are required")
    if inputs.get("expected_offsets_length") != expected_transcripts + 1:
        raise ValueError("expected_offsets_length must equal expected_transcripts + 1")
    seed_specs = inputs.get("seeds", [])
    seeds = [item.get("seed") for item in seed_specs]
    if not seed_specs or len(set(seeds)) != len(seeds):
        raise ValueError("protocol input seeds must be nonempty and unique")
    for item in seed_specs:
        if isinstance(item["seed"], bool) or not isinstance(item["seed"], int):
            raise ValueError("input seed must be an integer")
        if re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")) is None:
            raise ValueError("every input seed must have a lowercase SHA256")
    split = protocol.get("split", {})
    if split.get("unit") != "transcript" or split.get("calibration_fraction") != 0.5:
        raise ValueError("protocol must freeze a transcript-level 50/50 split")
    if split.get("calibration_count") != expected_transcripts // 2:
        raise ValueError("calibration_count must be floor(expected_transcripts / 2)")
    if split.get("test_count") != expected_transcripts - expected_transcripts // 2:
        raise ValueError("test_count must contain all remaining transcripts")
    if split.get("test_targets_used_for_fitting") is not False:
        raise ValueError("protocol must forbid test targets during fitting")
    model = protocol.get("observation_model", {})
    if model.get("formula") != "y = a + b * x" or model.get("slope_constraint") != "b >= 0":
        raise ValueError("protocol must freeze y = a + b*x with b >= 0")
    if model.get("fit_split") != "calibration_only":
        raise ValueError("observation maps must be fitted on calibration only")
    if model.get("transcript_point_weight") != "1 / n_i":
        raise ValueError("protocol must freeze transcript-balanced fitting weights")
    evaluation = protocol.get("evaluation", {})
    if evaluation.get("split") != "test_only":
        raise ValueError("final evaluation must use test only")
    if evaluation.get("co_primary_endpoints") != list(ENDPOINTS):
        raise ValueError("protocol co-primary endpoints do not match the implementation")
    if evaluation.get("correlation_gain_claim_allowed") is not False:
        raise ValueError("correlation invariance must not be interpreted as gain")
    inference = protocol.get("inference", {})
    for name in ("bootstrap", "signflip"):
        count = inference.get(name, {}).get("n_resamples")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError(f"inference {name} n_resamples must be a positive integer")
    batch_size = inference.get("batch_size")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("inference batch_size must be a positive integer")
    if protocol.get("outputs", {}).get("overwrite") != "forbidden":
        raise ValueError("protocol outputs.overwrite must be forbidden")
    return protocol


def deterministic_split(n_transcripts, split_seed):
    if n_transcripts < 2:
        raise ValueError("at least two transcripts are required")
    permutation = np.random.default_rng(split_seed).permutation(n_transcripts)
    n_calibration = n_transcripts // 2
    calibration = np.sort(permutation[:n_calibration]).astype(np.int64)
    test = np.sort(permutation[n_calibration:]).astype(np.int64)
    return calibration, test


def fit_affine(x, y, transcript_ids):
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    transcript_ids = np.asarray(transcript_ids, dtype=np.int64)
    if x.ndim != 1 or y.ndim != 1 or transcript_ids.ndim != 1:
        raise ValueError("fit inputs must be one-dimensional")
    if not (len(x) == len(y) == len(transcript_ids)) or not len(x):
        raise ValueError("fit inputs must have the same nonzero length")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("fit inputs must be finite")
    _, inverse, counts = np.unique(
        transcript_ids, return_inverse=True, return_counts=True,
    )
    weights = 1.0 / counts[inverse]
    weight_sum = float(np.sum(weights))
    x_mean = float(np.sum(weights * x) / weight_sum)
    y_mean = float(np.sum(weights * y) / weight_sum)
    centered_x = x - x_mean
    denominator = float(np.sum(weights * centered_x * centered_x))
    numerator = float(np.sum(weights * centered_x * (y - y_mean)))
    slope = numerator / denominator if denominator > 0.0 else 0.0
    slope = max(0.0, float(slope))
    intercept = y_mean - slope * x_mean
    return {
        "a": float(intercept),
        "b": slope,
        "n_transcripts": int(len(counts)),
        "n_positions": int(len(x)),
        "sum_transcript_weights": weight_sum,
    }


def load_npz(path, expected_transcripts):
    path = Path(path).expanduser().resolve()
    with np.load(path, allow_pickle=False) as archive:
        missing = [name for name in REQUIRED_ARRAYS if name not in archive.files]
        if missing:
            raise ValueError(f"NPZ missing required arrays: {missing}")
        offsets = np.asarray(archive["offsets"])
        positions = np.asarray(archive["positions"])
        target = np.asarray(archive["target"], dtype=np.float64)
        predictions = {
            name: np.asarray(archive[key], dtype=np.float64)
            for name, key in INPUT_KEYS.items()
        }
    if offsets.ndim != 1 or not np.issubdtype(offsets.dtype, np.integer):
        raise ValueError("offsets must be a one-dimensional integer array")
    if len(offsets) != expected_transcripts + 1:
        raise ValueError(
            f"offsets length {len(offsets)} does not equal {expected_transcripts + 1}",
        )
    if offsets[0] != 0 or np.any(np.diff(offsets) <= 0):
        raise ValueError("offsets must start at zero and strictly increase")
    n_positions = int(offsets[-1])
    if positions.ndim != 1 or len(positions) != n_positions:
        raise ValueError("positions must be flat and match offsets[-1]")
    if target.ndim != 1 or len(target) != n_positions or not np.all(np.isfinite(target)):
        raise ValueError("target must be flat, finite and match offsets[-1]")
    for name, values in predictions.items():
        if values.ndim != 1 or len(values) != n_positions or not np.all(np.isfinite(values)):
            raise ValueError(f"{name} must be flat, finite and match offsets[-1]")
    return {
        "offsets": offsets.astype(np.int64, copy=False),
        "positions": positions,
        "target": target,
        **predictions,
    }


def correlation_values(x, y):
    if len(x) < 2 or np.ptp(x) == 0.0 or np.ptp(y) == 0.0:
        return None, None
    pearson = float(stats.pearsonr(x, y)[0])
    spearman = float(stats.spearmanr(x, y)[0])
    if not math.isfinite(pearson) or not math.isfinite(spearman):
        return None, None
    return pearson, spearman


def per_transcript_metrics(data, predictions, transcript_indices):
    records = []
    offsets = data["offsets"]
    target = data["target"]
    for transcript_index in transcript_indices:
        index = int(transcript_index)
        start, stop = int(offsets[index]), int(offsets[index + 1])
        y = target[start:stop]
        record = {"transcript_index": index, "n_positions": stop - start}
        for name, values in predictions.items():
            prediction = values[start:stop]
            record[f"mse_{name}"] = float(np.mean((y - prediction) ** 2))
            pearson, spearman = correlation_values(prediction, y)
            record[f"pearson_{name}"] = pearson
            record[f"spearman_{name}"] = spearman
        record["effect_unanchored"] = (
            record["mse_raw_unanchored"] - record["mse_calibrated_unanchored"]
        )
        record["effect_anchored"] = (
            record["mse_raw_anchored"] - record["mse_calibrated_anchored"]
        )
        records.append(record)
    return records


def mean_or_none(values):
    defined = [float(value) for value in values if value is not None]
    return float(np.mean(defined)) if defined else None


def summarize_metrics(records, predictor_names):
    return {
        "n_transcripts": len(records),
        "n_positions": int(sum(record["n_positions"] for record in records)),
        "tb_mse": {
            name: float(np.mean([record[f"mse_{name}"] for record in records]))
            for name in predictor_names
        },
        "mean_per_transcript_pearson": {
            name: mean_or_none([record[f"pearson_{name}"] for record in records])
            for name in predictor_names
        },
        "mean_per_transcript_spearman": {
            name: mean_or_none([record[f"spearman_{name}"] for record in records])
            for name in predictor_names
        },
        "defined_correlation_counts": {
            name: {
                "pearson": sum(record[f"pearson_{name}"] is not None for record in records),
                "spearman": sum(record[f"spearman_{name}"] is not None for record in records),
            }
            for name in predictor_names
        },
    }


def correlation_invariance(records, raw_name, calibrated_name, slope):
    if slope <= 0.0:
        return {
            "status": "not_applicable_b_zero",
            "passed": None,
            "n_compared": 0,
            "pearson_max_abs_difference": None,
            "spearman_max_abs_difference": None,
            "gain_claim_allowed": False,
        }
    pearson_differences = []
    spearman_differences = []
    matched_definition = True
    for record in records:
        for metric, differences in (
            ("pearson", pearson_differences),
            ("spearman", spearman_differences),
        ):
            raw = record[f"{metric}_{raw_name}"]
            calibrated = record[f"{metric}_{calibrated_name}"]
            if (raw is None) != (calibrated is None):
                matched_definition = False
            elif raw is not None:
                differences.append(abs(raw - calibrated))
    pearson_max = max(pearson_differences, default=0.0)
    spearman_max = max(spearman_differences, default=0.0)
    passed = (
        matched_definition
        and math.isclose(pearson_max, 0.0, rel_tol=0.0, abs_tol=1e-12)
        and math.isclose(spearman_max, 0.0, rel_tol=0.0, abs_tol=1e-12)
    )
    return {
        "status": "verified" if passed else "failed",
        "passed": passed,
        "n_compared": len(pearson_differences),
        "pearson_max_abs_difference": pearson_max,
        "spearman_max_abs_difference": spearman_max,
        "gain_claim_allowed": False,
    }


def paired_transcript_inference(effects, n_bootstrap, n_signflip, seed, batch_size=512):
    effects = np.asarray(effects, dtype=np.float64)
    if effects.ndim != 1 or not len(effects) or not np.all(np.isfinite(effects)):
        raise ValueError("paired inference effects must be a finite nonempty vector")
    if n_bootstrap < 1 or n_signflip < 1 or batch_size < 1:
        raise ValueError("inference resample counts and batch_size must be positive")
    rng = np.random.default_rng(seed)
    n_transcripts = len(effects)
    bootstrap = np.empty(n_bootstrap, dtype=np.float64)
    for start in range(0, n_bootstrap, batch_size):
        stop = min(start + batch_size, n_bootstrap)
        indices = rng.integers(0, n_transcripts, size=(stop - start, n_transcripts))
        bootstrap[start:stop] = np.mean(effects[indices], axis=1)
    exceedances = 0
    observed = float(np.mean(effects))
    for start in range(0, n_signflip, batch_size):
        stop = min(start + batch_size, n_signflip)
        signs = rng.integers(
            0, 2, size=(stop - start, n_transcripts), dtype=np.int8,
        ) * 2 - 1
        null_effects = np.mean(signs * effects, axis=1)
        exceedances += int(np.count_nonzero(np.abs(null_effects) >= abs(observed)))
    return {
        "effect": observed,
        "bootstrap_95ci": [
            float(np.quantile(bootstrap, 0.025)),
            float(np.quantile(bootstrap, 0.975)),
        ],
        "signflip_p_two_sided": float((exceedances + 1) / (n_signflip + 1)),
        "n_bootstrap": int(n_bootstrap),
        "n_signflip": int(n_signflip),
        "n_transcripts": n_transcripts,
    }


def holm_adjust(p_values):
    p_values = np.asarray(p_values, dtype=np.float64)
    if p_values.ndim != 1 or not len(p_values) or not np.all(np.isfinite(p_values)):
        raise ValueError("Holm input must be a finite nonempty vector")
    order = np.argsort(p_values)
    adjusted = np.empty(len(p_values), dtype=np.float64)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p_values) - rank) * p_values[index])
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def write_json(path, payload):
    path = Path(path)
    serialized = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(serialized)


def export_points(path, data, calibrated, transcript_indices, point_transcript):
    transcript_indices = np.asarray(transcript_indices, dtype=np.int64)
    mask = np.isin(point_transcript, transcript_indices)
    selected_transcripts = point_transcript[mask]
    counts = np.diff(data["offsets"])[transcript_indices]
    arrays = {
        "offsets": np.concatenate(([0], np.cumsum(counts))).astype(np.int64),
        "transcript_indices": transcript_indices,
        "transcript_index": selected_transcripts,
        "positions": data["positions"][mask],
        "target": data["target"][mask],
    }
    for name in INPUT_KEYS:
        arrays[name] = data[name][mask]
    for name, values in calibrated.items():
        arrays[name] = values[mask]
    with Path(path).open("xb") as handle:
        np.savez_compressed(handle, **arrays)


def write_effects_csv(path, seed, records):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for record in records:
        writer.writerow({"seed": seed, **record})
    with Path(path).open("x", encoding="utf-8", newline="") as handle:
        handle.write(buffer.getvalue())


def parse_input(value):
    try:
        seed_text, path_text = value.split("=", 1)
        seed = int(seed_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("input must have the form SEED=PATH") from exc
    if not path_text:
        raise argparse.ArgumentTypeError("input path must not be empty")
    return seed, Path(path_text).expanduser().resolve()


def run_analysis(protocol_path, inputs, output_dir):
    started = time.perf_counter()
    started_utc = datetime.now(timezone.utc).isoformat()
    protocol_path = Path(protocol_path).expanduser().resolve()
    protocol = load_protocol(protocol_path)
    output_dir = Path(output_dir).expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {output_dir}")
    inputs = {int(seed): Path(path).expanduser().resolve() for seed, path in inputs.items()}
    seed_specs = protocol["inputs"]["seeds"]
    expected_seeds = {item["seed"] for item in seed_specs}
    if set(inputs) != expected_seeds:
        raise ValueError(f"input seeds must exactly match protocol seeds: {sorted(expected_seeds)}")
    for item in seed_specs:
        path = inputs[item["seed"]]
        if not path.is_file():
            raise ValueError(f"input NPZ not found or not a regular file: {path}")
        observed = sha256_file(path)
        if observed != item["sha256"]:
            raise ValueError(
                f"seed {item['seed']} NPZ SHA256 mismatch: expected {item['sha256']}, observed {observed}",
            )
    output_dir.mkdir(parents=True, exist_ok=False)
    expected_transcripts = protocol["inputs"]["expected_transcripts"]
    calibration_indices, test_indices = deterministic_split(
        expected_transcripts, protocol["split"]["seed"],
    )
    predictor_names = [
        "raw_unanchored",
        "raw_anchored",
        "constant",
        "calibrated_unanchored",
        "calibrated_anchored",
    ]
    inference_config = protocol["inference"]
    alpha = inference_config["holm"]["alpha"]
    seed_results = []
    artifact_hashes = {}
    input_access_log = []
    for item in seed_specs:
        seed_started = time.perf_counter()
        seed = item["seed"]
        data = load_npz(inputs[seed], expected_transcripts)
        point_transcript = np.repeat(
            np.arange(expected_transcripts, dtype=np.int64), np.diff(data["offsets"]),
        )
        calibration_point_mask = np.isin(point_transcript, calibration_indices)
        calibration_parameters = {}
        calibrated = {}
        for raw_name, calibrated_name in (
            ("raw_unanchored", "calibrated_unanchored"),
            ("raw_anchored", "calibrated_anchored"),
        ):
            parameters = fit_affine(
                data[raw_name][calibration_point_mask],
                data["target"][calibration_point_mask],
                point_transcript[calibration_point_mask],
            )
            calibration_parameters[raw_name] = parameters
            calibrated[calibrated_name] = parameters["a"] + parameters["b"] * data[raw_name]
        predictions = {
            "raw_unanchored": data["raw_unanchored"],
            "raw_anchored": data["raw_anchored"],
            "constant": data["constant"],
            **calibrated,
        }
        calibration_records = per_transcript_metrics(data, predictions, calibration_indices)
        test_records = per_transcript_metrics(data, predictions, test_indices)
        calibration_metrics = summarize_metrics(calibration_records, predictor_names)
        test_metrics = summarize_metrics(test_records, predictor_names)
        invariance = {
            "unanchored": correlation_invariance(
                test_records, "raw_unanchored", "calibrated_unanchored",
                calibration_parameters["raw_unanchored"]["b"],
            ),
            "anchored": correlation_invariance(
                test_records, "raw_anchored", "calibrated_anchored",
                calibration_parameters["raw_anchored"]["b"],
            ),
        }
        if any(check["passed"] is False for check in invariance.values()):
            raise RuntimeError("positive-slope correlation invariance verification failed")
        endpoint_results = {}
        for endpoint_index, endpoint in enumerate(ENDPOINTS):
            effects = np.asarray([
                record[ENDPOINT_EFFECT_FIELDS[endpoint]] for record in test_records
            ])
            endpoint_results[endpoint] = paired_transcript_inference(
                effects,
                inference_config["bootstrap"]["n_resamples"],
                inference_config["signflip"]["n_resamples"],
                [inference_config["seed"], seed, endpoint_index],
                inference_config["batch_size"],
            )
        adjusted = holm_adjust([
            endpoint_results[endpoint]["signflip_p_two_sided"] for endpoint in ENDPOINTS
        ])
        for endpoint, holm_p in zip(ENDPOINTS, adjusted):
            result = endpoint_results[endpoint]
            result["holm_p"] = holm_p
            result["effect_positive"] = result["effect"] > 0.0
            result["bootstrap_ci_lower_positive"] = result["bootstrap_95ci"][0] > 0.0
            result["holm_significant"] = holm_p < alpha
            result["passes"] = all((
                result["effect_positive"],
                result["bootstrap_ci_lower_positive"],
                result["holm_significant"],
            ))
        seed_dir = output_dir / f"seed_{seed}"
        seed_dir.mkdir()
        export_points(
            seed_dir / "calibration_points.npz", data, calibrated,
            calibration_indices, point_transcript,
        )
        export_points(
            seed_dir / "test_points.npz", data, calibrated,
            test_indices, point_transcript,
        )
        write_effects_csv(seed_dir / "test_transcript_effects.csv", seed, test_records)
        result = {
            "schema": REPORT_SCHEMA,
            "protocol": PROTOCOL,
            "seed": seed,
            "scope": protocol["scope"],
            "input": {
                "path": str(inputs[seed]),
                "sha256": item["sha256"],
            },
            "split": {
                "seed": protocol["split"]["seed"],
                "calibration_transcript_indices": calibration_indices.tolist(),
                "test_transcript_indices": test_indices.tolist(),
                "calibration_count": len(calibration_indices),
                "test_count": len(test_indices),
                "test_targets_used_for_fitting": False,
            },
            "calibration": {
                "parameters": calibration_parameters,
                "metrics": calibration_metrics,
            },
            "test": {
                "metrics": test_metrics,
                "correlation_invariance": invariance,
                "correlation_gain_claim_allowed": False,
                "endpoints": endpoint_results,
                "all_co_primary_pass": all(
                    endpoint_results[endpoint]["passes"] for endpoint in ENDPOINTS
                ),
            },
            "cost": {
                "wall_clock_seconds": time.perf_counter() - seed_started,
                "calibration_positions": calibration_metrics["n_positions"],
                "test_positions": test_metrics["n_positions"],
            },
        }
        write_json(seed_dir / "result.json", result)
        seed_results.append(result)
        input_access_log.append({
            "seed": seed,
            "path": str(inputs[seed]),
            "sha256_verified": True,
            "calibration_transcripts_used_for_fit": len(calibration_indices),
            "test_transcripts_used_only_for_final_evaluation": len(test_indices),
            "test_targets_used_for_fitting": False,
        })
        for name in (
            "result.json",
            "calibration_points.npz",
            "test_points.npz",
            "test_transcript_effects.csv",
        ):
            relative = f"seed_{seed}/{name}"
            artifact_hashes[relative] = sha256_file(output_dir / relative)
    across_seeds = {}
    for endpoint in ENDPOINTS:
        effects = [result["test"]["endpoints"][endpoint]["effect"] for result in seed_results]
        across_seeds[endpoint] = {
            "effects": effects,
            "same_nonzero_sign": all(value > 0.0 for value in effects) or all(
                value < 0.0 for value in effects
            ),
        }
    h1_positive = all(
        result["test"]["all_co_primary_pass"] for result in seed_results
    ) and all(item["same_nonzero_sign"] for item in across_seeds.values())
    summary = {
        "schema": SUMMARY_SCHEMA,
        "protocol": PROTOCOL,
        "scope": protocol["scope"],
        "status": "h1_development_positive" if h1_positive else "h1_development_not_positive",
        "h1_development_positive": h1_positive,
        "decision_rule": inference_config["h1_development_positive_rule"],
        "across_seeds": across_seeds,
        "seeds": {
            str(result["seed"]): {
                "calibration_parameters": result["calibration"]["parameters"],
                "test_metrics": result["test"]["metrics"],
                "correlation_invariance": result["test"]["correlation_invariance"],
                "endpoints": result["test"]["endpoints"],
                "all_co_primary_pass": result["test"]["all_co_primary_pass"],
                "result_json": f"seed_{result['seed']}/result.json",
            }
            for result in seed_results
        },
        "input_access_log": input_access_log,
        "cost": {
            "started_utc": started_utc,
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "wall_clock_seconds": time.perf_counter() - started,
            "per_seed_wall_clock_seconds": {
                str(result["seed"]): result["cost"]["wall_clock_seconds"]
                for result in seed_results
            },
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
        "sha256": {
            "protocol": sha256_file(protocol_path),
            "implementation": sha256_file(Path(__file__).resolve()),
            "inputs": {str(seed): str(inputs[seed]) for seed in sorted(inputs)},
            "input_files": {
                str(item["seed"]): item["sha256"] for item in seed_specs
            },
            "artifacts": artifact_hashes,
        },
        "limitations": protocol["limitations"],
    }
    write_json(output_dir / "summary.json", summary)
    print(json.dumps({
        "status": summary["status"],
        "output_dir": str(output_dir),
        "seeds": [result["seed"] for result in seed_results],
    }))
    return summary


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--protocol", required=True, help="Frozen observation protocol JSON")
    parser.add_argument(
        "--input", dest="inputs", action="append", type=parse_input, required=True,
        metavar="SEED=PATH", help="RK37 NPZ for a protocol seed; repeat for every seed",
    )
    parser.add_argument("--output-dir", required=True, help="New output directory")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    run_analysis(args.protocol, dict(args.inputs), args.output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
