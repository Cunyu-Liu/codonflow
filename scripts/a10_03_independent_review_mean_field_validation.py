#!/usr/bin/env python3
"""Independently recompute the synthetic mean-field validation artifacts."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy import linalg, optimize

SCHEMA = "a10-03-exact-ctmc-independent-review-v1"
EXACT_TOL = 2e-9
SENSITIVITY_TOL = 2e-7
MEAN_FIELD_TOL = 2e-7


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def row_generator(theta, length):
    theta = np.asarray(theta)
    configurations = list(itertools.product((0, 1), repeat=length))
    indices = {configuration: index for index, configuration in enumerate(configurations)}
    generator = np.zeros((len(configurations), len(configurations)), dtype=theta.dtype)
    for index, configuration in enumerate(configurations):
        transitions = []
        if configuration[0] == 0:
            target = (1,) + configuration[1:]
            transitions.append((target, theta[0]))
        for site in range(length - 1):
            if configuration[site] == 1 and configuration[site + 1] == 0:
                target = list(configuration)
                target[site] = 0
                target[site + 1] = 1
                transitions.append((tuple(target), theta[site + 1]))
        if configuration[-1] == 1:
            transitions.append((configuration[:-1] + (0,), theta[-1]))
        for target, rate in transitions:
            target_index = indices[target]
            generator[index, target_index] += rate
            generator[index, index] -= rate
    return generator, np.asarray(configurations, dtype=np.float64)


def linear_stationary(theta, length):
    generator, configurations = row_generator(theta, length)
    transpose = generator.T.copy()
    transpose[0, :] = 1.0
    rhs = np.zeros(len(configurations), dtype=theta.dtype)
    rhs[0] = 1.0
    probability = np.linalg.solve(transpose, rhs)
    density = probability @ configurations
    flux = theta[0] * (1.0 - density[0])
    return probability, density, flux


def eigen_stationary(theta, length):
    generator, configurations = row_generator(np.asarray(theta, dtype=np.float64), length)
    eigenvalues, eigenvectors = linalg.eig(generator.T)
    order = np.argsort(np.abs(eigenvalues))
    stationary_index = order[0]
    probability = np.real(eigenvectors[:, stationary_index])
    if probability.sum() < 0.0:
        probability = -probability
    probability /= probability.sum()
    density = probability @ configurations
    flux = float(theta[0] * (1.0 - density[0]))
    pair_joint = probability @ (configurations[:, :-1] * configurations[:, 1:])
    return {
        "probability": probability,
        "density": density,
        "flux": flux,
        "covariance": pair_joint - density[:-1] * density[1:],
        "stationary_residual_inf": float(np.max(np.abs(generator.T @ probability))),
        "stationary_eigenvalue_abs": float(abs(eigenvalues[stationary_index])),
        "spectral_gap": float(abs(eigenvalues[order[1]])) if len(order) > 1 else None,
    }


def complex_step_sensitivity(theta, length, step=1e-20):
    theta = np.asarray(theta, dtype=np.float64)
    result = np.empty((length + 1, length + 1), dtype=np.float64)
    for parameter in range(length + 1):
        perturbed = theta.astype(complex)
        perturbed[parameter] += 1j * step * theta[parameter]
        _, density, flux = linear_stationary(perturbed, length)
        output = np.concatenate((density, [flux]))
        result[:, parameter] = output.imag / step / np.concatenate((
            linear_stationary(theta, length)[1],
            [linear_stationary(theta, length)[2]],
        ))
    return result


def independent_mean_field(theta):
    theta = np.asarray(theta, dtype=np.float64)
    length = len(theta) - 1

    def residual(state):
        density = state[:-1]
        flux = state[-1]
        return np.concatenate((
            [theta[0] * (1.0 - density[0]) - flux],
            theta[1:-1] * density[:-1] * (1.0 - density[1:]) - flux,
            [theta[-1] * density[-1] - flux],
        ))

    def jacobian(state):
        density = state[:-1]
        result = np.zeros((length + 1, length + 1), dtype=np.float64)
        result[:, -1] = -1.0
        result[0, 0] = -theta[0]
        if length > 1:
            indices = np.arange(length - 1)
            result[indices + 1, indices] = theta[1:-1] * (1.0 - density[1:])
            result[indices + 1, indices + 1] = -theta[1:-1] * density[:-1]
        result[-1, -2] = theta[-1]
        return result

    initial = np.concatenate((np.linspace(0.4, 0.6, length), [0.1 * theta.min()]))
    result = optimize.least_squares(
        residual,
        initial,
        bounds=(np.zeros(length + 1), np.concatenate((np.ones(length), [np.inf]))),
        ftol=1e-13,
        xtol=1e-13,
        gtol=1e-13,
        max_nfev=2000,
    )
    if not result.success:
        raise RuntimeError("independent mean-field least_squares failed")
    refined = optimize.root(
        residual,
        result.x,
        jac=jacobian,
        method="hybr",
        options={"xtol": 1e-12, "maxfev": 2000},
    )
    if not refined.success or np.any(refined.x[:-1] < 0.0) or np.any(refined.x[:-1] > 1.0) or refined.x[-1] <= 0.0:
        raise RuntimeError("independent mean-field root refinement failed")
    normalized_residual = np.max(np.abs(residual(refined.x))) / refined.x[-1]
    if normalized_residual > 1e-12:
        raise RuntimeError("independent mean-field root exceeded normalized residual tolerance")
    return refined.x


def max_abs(value):
    value = np.asarray(value, dtype=np.float64)
    return float(np.max(np.abs(value))) if value.size else 0.0


def exact_comparison(record):
    recomputed = eigen_stationary(record["theta"], record["length"])
    return {
        "density_max_abs": max_abs(recomputed["density"] - record["exact"]["density"]),
        "flux_abs": abs(recomputed["flux"] - record["exact"]["flux"]),
        "covariance_max_abs": max_abs(
            recomputed["covariance"] - record["exact"]["nearest_neighbor_covariance"]
        ),
        "stationary_residual_inf": recomputed["stationary_residual_inf"],
        "stationary_eigenvalue_abs": recomputed["stationary_eigenvalue_abs"],
        "spectral_gap": recomputed["spectral_gap"],
    }


def needs_complex_step(record, worst_names):
    return (
        record["name"] in worst_names
        or (record["group"] == "constant_rate_grid" and record["length"] == 2)
        or (record["group"] == "log_uniform_random" and record["name"].endswith(("_000", "_001")))
        or record["group"] == "common_time_scale"
    )


def review(artifacts):
    artifacts = Path(artifacts)
    validation_path = artifacts / "validation.json"
    cases_path = artifacts / "cases.jsonl"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    records = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines()]
    worst_names = {case["name"] for case in validation["worst_density_cases"]}
    exact_errors = []
    sensitivity_checks = []
    mean_field_checks = []
    rank_errors = []
    failures = []
    for record in records:
        try:
            comparison = exact_comparison(record)
            exact_errors.append({"name": record["name"], **comparison})
            if max(
                comparison["density_max_abs"], comparison["flux_abs"],
                comparison["covariance_max_abs"], comparison["stationary_residual_inf"],
            ) > EXACT_TOL:
                failures.append({"name": record["name"], "kind": "exact_eigen_recomputation", **comparison})
            for prefix in ("exact", "mean_field"):
                sensitivity = np.asarray(record[f"{prefix}_sensitivity"])
                identifiability = record[f"{prefix}_identifiability"]
                for observation in ("density_only", "density_plus_absolute_flux"):
                    matrix = sensitivity[:record["length"]] if observation == "density_only" else sensitivity
                    singular = np.linalg.svd(matrix, compute_uv=False)
                    error = max_abs(singular - identifiability[observation]["singular_values"])
                    rank_errors.append(error)
                    if error > 1e-9:
                        failures.append({
                            "name": record["name"], "kind": "singular_value_recomputation",
                            "prefix": prefix, "observation": observation, "error": error,
                        })
            if needs_complex_step(record, worst_names):
                sensitivity = complex_step_sensitivity(record["theta"], record["length"])
                error = max_abs(sensitivity - record["exact_sensitivity"])
                sensitivity_checks.append({"name": record["name"], "max_abs": error})
                if error > SENSITIVITY_TOL:
                    failures.append({"name": record["name"], "kind": "complex_step_sensitivity", "max_abs": error})
            if record["name"] in worst_names and "mean_field" in record:
                state = independent_mean_field(record["theta"])
                error = max(
                    max_abs(state[:-1] - record["mean_field"]["density"]),
                    abs(state[-1] - record["mean_field"]["flux"]),
                )
                mean_field_checks.append({"name": record["name"], "max_abs": error})
                if error > MEAN_FIELD_TOL:
                    failures.append({"name": record["name"], "kind": "independent_mean_field", "max_abs": error})
        except Exception as error:
            failures.append({
                "name": record["name"], "kind": "review_exception",
                "type": type(error).__name__, "message": str(error),
            })
    counts_match = (
        len(records) == validation["case_count"]
        and sum(not record["passed"] for record in records) == validation["failure_count"]
    )
    hashes_match = validation["artifact_sha256"]["cases_jsonl"] == sha256_file(cases_path)
    passed = (
        not failures and counts_match and hashes_match and validation["passed"]
        and len(records) > 0
    )
    return {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "independence": {
            "main_validation_module_imported": False,
            "production_solver_called": False,
            "state_enumeration": "lexicographic occupancy tuples rather than integer bit states",
            "all_case_exact_reference": "row-generator eigendecomposition",
            "selected_exact_sensitivity": "complex-step differentiation of an independent linear stationary solve",
            "worst_case_mean_field": "bounded scipy.optimize.least_squares without production code",
        },
        "case_count": len(records),
        "complex_step_case_count": len(sensitivity_checks),
        "independent_mean_field_case_count": len(mean_field_checks),
        "counts_match": counts_match,
        "cases_hash_matches": hashes_match,
        "max_errors": {
            "exact_density": max((case["density_max_abs"] for case in exact_errors), default=None),
            "exact_flux": max((case["flux_abs"] for case in exact_errors), default=None),
            "exact_covariance": max((case["covariance_max_abs"] for case in exact_errors), default=None),
            "exact_stationary_residual": max((case["stationary_residual_inf"] for case in exact_errors), default=None),
            "complex_step_sensitivity": max((case["max_abs"] for case in sensitivity_checks), default=None),
            "independent_mean_field": max((case["max_abs"] for case in mean_field_checks), default=None),
            "singular_values": max(rank_errors, default=None),
        },
        "tolerances": {
            "exact": EXACT_TOL,
            "sensitivity": SENSITIVITY_TOL,
            "mean_field": MEAN_FIELD_TOL,
        },
        "failures": failures,
        "sensitivity_checks": sensitivity_checks,
        "mean_field_checks": mean_field_checks,
        "artifact_sha256": {
            "validation_json": sha256_file(validation_path),
            "cases_jsonl": sha256_file(cases_path),
            "review_implementation": sha256_file(__file__),
        },
        "scope": {
            "synthetic_artifacts_only": True,
            "external_or_frozen_data_read": False,
            "gate_decision_or_biological_claim": False,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-dir", required=True, type=Path)
    parser.add_argument("--output-name", default="independent_review.json")
    args = parser.parse_args(argv)
    if Path(args.output_name).name != args.output_name:
        raise ValueError("output-name must be a file name inside artifacts-dir")
    output = args.artifacts_dir / args.output_name
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing review: {output}")
    report = review(args.artifacts_dir)
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    print(json.dumps({
        "passed": report["passed"],
        "case_count": report["case_count"],
        "failure_count": len(report["failures"]),
        "max_errors": report["max_errors"],
        "output": str(output),
        "output_sha256": sha256_file(output),
    }))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
