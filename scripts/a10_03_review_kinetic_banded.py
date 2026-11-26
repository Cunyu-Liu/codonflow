#!/usr/bin/env python3
"""Independently review saved banded validation artifacts without production imports."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "a10-e2-kinetic-banded-independent-review-v1"


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def independent_real_case(arrays_path):
    with np.load(arrays_path, allow_pickle=False) as data:
        alpha = float(data["alpha"])
        rates = np.asarray(data["rates"], dtype=np.float64)
        beta = float(data["beta"])
        rho = np.asarray(data["rho"], dtype=np.float64)
        flux = float(data["flux"])
        production_gradient = np.asarray(data["production_gradients"], dtype=np.float64)
        baseline_gradient = np.asarray(data["baseline_gradients"], dtype=np.float64)
        normalized_residual = np.asarray(data["normalized_residual"], dtype=np.float64)
    length = rho.size
    if rates.shape != (length - 1,) or production_gradient.shape != (length + 1,):
        raise ValueError("real artifact shapes are inconsistent")
    local_flux = np.concatenate((
        [alpha * (1.0 - rho[0])],
        rates * rho[:-1] * (1.0 - rho[1:]),
        [beta * rho[-1]],
    ))
    jacobian = np.zeros((length + 1, length + 1), dtype=np.float64)
    jacobian[0, 0] = -alpha
    if length > 1:
        indices = np.arange(1, length)
        jacobian[indices, indices - 1] = rates * (1.0 - rho[1:])
        jacobian[indices, indices] = -rates * rho[:-1]
    jacobian[-1, -2] = beta
    jacobian[:, -1] = -1.0
    positions = np.arange(length, dtype=np.float64)
    output_gradient = np.concatenate((
        np.sin(0.013 * positions) + 0.2 * np.cos(0.031 * positions), [0.37]
    ))
    adjoint = np.linalg.solve(jacobian.T, output_gradient)
    expected_gradient = np.concatenate((
        [-adjoint[0] * (1.0 - rho[0])],
        -adjoint[1:-1] * rho[:-1] * (1.0 - rho[1:]),
        [-adjoint[-1] * rho[-1]],
    ))
    extended_matrix = np.asarray(jacobian.T, dtype=np.longdouble)
    extended_adjoint = np.asarray(adjoint, dtype=np.longdouble)
    extended_output = np.asarray(output_gradient, dtype=np.longdouble)
    recovery = extended_matrix @ extended_adjoint - extended_output
    denominator = np.abs(extended_matrix) @ np.abs(extended_adjoint) + np.abs(extended_output)
    relative_recovery = np.abs(recovery) / np.where(denominator > 0, denominator, 1.0)
    extended_local = np.asarray(local_flux, dtype=np.longdouble)
    conservation = float(np.max(np.abs(extended_local - np.longdouble(flux))) / abs(np.longdouble(flux)))
    errors = {
        "production_gradient_max_absolute": float(np.max(np.abs(production_gradient - expected_gradient))),
        "baseline_gradient_max_absolute": float(np.max(np.abs(baseline_gradient - expected_gradient))),
        "normalized_residual_max": float(np.max(np.abs(normalized_residual))),
        "conservation_max_relative": conservation,
        "adjoint_component_recovery_max": float(np.max(relative_recovery)),
    }
    passed = bool(
        errors["production_gradient_max_absolute"] <= 2e-7
        and errors["baseline_gradient_max_absolute"] <= 2e-7
        and errors["normalized_residual_max"] <= 1e-10
        and errors["conservation_max_relative"] <= 1e-10
        and errors["adjoint_component_recovery_max"] <= 1e-10
    )
    return {
        "length": length,
        "independent_method": "dense numpy adjoint with long-double component recovery",
        "errors": errors,
        "passed": passed,
    }, expected_gradient


def review(validation_path, arrays_path, baseline_path):
    report = json.loads(validation_path.read_text(encoding="utf-8"))
    real, _ = independent_real_case(arrays_path)
    expected_hashes = report["artifact_sha256"]
    actual_hashes = {
        "solver": sha256_file(ROOT / "src" / "codonflow" / "models" / "kinetic_mean_field.py"),
        "validation_script": sha256_file(ROOT / "scripts" / "a10_03_validate_kinetic_banded.py"),
        "baseline_solver": sha256_file(baseline_path),
        "real_snapshot_arrays": sha256_file(arrays_path),
    }
    hashes_match = all(
        actual_hashes[key] == expected_hashes[key]
        for key in ("solver", "validation_script", "baseline_solver")
    )
    named_cases = {case["name"]: case for case in report["single_cases"]}
    long_case = named_cases.get("random_l4096_s5096", {})
    memory_reduced = bool(
        long_case
        and long_case["banded"]["backward_peak_allocated_bytes"]
        < long_case["baseline"]["backward_peak_allocated_bytes"]
    )
    passed = bool(
        report.get("passed") is True
        and report.get("scope", {}).get("training_executed") is False
        and report.get("scope", {}).get("scientific_gate_claimed") is False
        and report.get("linear_algebra", {}).get("passed") is True
        and report.get("mixed_batch", {}).get("passed") is True
        and report.get("near_singular_rank_one", {}).get("passed") is True
        and all(case.get("passed") is True for case in report.get("single_cases", []))
        and real["passed"]
        and hashes_match
        and memory_reduced
    )
    return {
        "schema": SCHEMA,
        "passed": passed,
        "scope": {
            "production_solver_imported": False,
            "training_executed": False,
            "scientific_gate_claimed": False,
            "untouched24_or_MAGE_untouched_read": False,
        },
        "validation_sha256": sha256_file(validation_path),
        "real_arrays_sha256": actual_hashes["real_snapshot_arrays"],
        "source_hashes_match": hashes_match,
        "long_4096_backward_peak_reduced": memory_reduced,
        "real_independent_case": real,
        "artifact_sha256": actual_hashes,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation", required=True, type=Path)
    parser.add_argument("--arrays", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {args.output}")
    try:
        report = review(args.validation, args.arrays, args.baseline)
    except Exception as error:
        report = {
            "schema": SCHEMA,
            "passed": False,
            "scope": {"production_solver_imported": False, "scientific_gate_claimed": False},
            "error": {"type": type(error).__name__, "message": str(error)},
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"passed": report["passed"], "output": str(args.output)}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
