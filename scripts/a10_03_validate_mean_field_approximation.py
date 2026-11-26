#!/usr/bin/env python3
"""Compare the A10 mean field with exact enumerable exclusion-process CTMCs."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from codonflow.models.kinetic_mean_field import solve_kinetic_mean_field

SCHEMA = "a10-03-exact-ctmc-mean-field-validation-v1"
GRID_VALUES = (0.05, 1.0, 20.0)
RANDOM_CASES_PER_LENGTH = 128
RANDOM_SEED = 20261125
SENSITIVITY_STEP = 1e-4
EXACT_STATIONARY_TOL = 1e-9
SENSITIVITY_TOL = 2e-6
CUDA_SENSITIVITY_TOL = 2e-6


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json_exclusive(path, payload):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def case_specs():
    cases = []
    for alpha, beta in itertools.product(GRID_VALUES, repeat=2):
        cases.append({
            "name": f"single_L1_a{alpha:g}_b{beta:g}",
            "group": "single_site_grid",
            "length": 1,
            "theta": [alpha, beta],
        })
    for length in range(2, 7):
        for alpha, internal, beta in itertools.product(GRID_VALUES, repeat=3):
            cases.append({
                "name": f"constant_L{length}_a{alpha:g}_k{internal:g}_b{beta:g}",
                "group": "constant_rate_grid",
                "length": length,
                "theta": [alpha] + [internal] * (length - 1) + [beta],
            })
    for alpha, beta in itertools.product(GRID_VALUES, repeat=2):
        for position in range(4):
            for bottleneck in (0.05, 20.0):
                rates = np.ones(4)
                rates[position] = bottleneck
                cases.append({
                    "name": f"local_L5_a{alpha:g}_b{beta:g}_p{position}_k{bottleneck:g}",
                    "group": "localized_rate_grid",
                    "length": 5,
                    "theta": [alpha, *rates.tolist(), beta],
                    "perturbed_internal_position": position,
                })
    rng = np.random.default_rng(RANDOM_SEED)
    for length in range(2, 7):
        for index in range(RANDOM_CASES_PER_LENGTH):
            theta = np.exp(rng.uniform(-2.0, 2.0, length + 1))
            cases.append({
                "name": f"random_L{length}_{index:03d}",
                "group": "log_uniform_random",
                "length": length,
                "theta": theta.tolist(),
                "random_index": index,
            })
    base = np.asarray([0.7, 1.2, 0.4, 2.1, 1.5], dtype=np.float64)
    for scale in (0.01, 1.0, 100.0):
        cases.append({
            "name": f"time_scale_L4_s{scale:g}",
            "group": "common_time_scale",
            "length": 4,
            "theta": (scale * base).tolist(),
            "common_scale": scale,
        })
    return cases


def protocol_payload(device):
    return {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scientific_question": (
            "Where does the deterministic occupancy mean field depart from the exact "
            "stationary exclusion-process CTMC, and which rate combinations are locally "
            "identifiable from density with or without absolute flux?"
        ),
        "reference": {
            "state_space": "all 2^L binary occupancy states, with site 0 as the entrance",
            "transitions": (
                "empty site 0 is filled at alpha; occupied i hops to empty i+1 at k_i; "
                "occupied last site exits at beta"
            ),
            "stationary_solver": "dense linear solve of the column generator with one row replaced by normalization",
            "simulation_or_gillespie": False,
        },
        "mean_field": {
            "equation": "J_i=k_i*rho_i*(1-rho_{i+1}), with alpha entrance and beta exit",
            "pair_factorization": "E[n_i*n_{i+1}] is approximated by rho_i*rho_{i+1}",
            "exact_stochastic_simulation": False,
        },
        "cases": {
            "lengths": [1, 2, 3, 4, 5, 6],
            "constant_grid_values": list(GRID_VALUES),
            "localized_grid": "L=5; every internal position; internal rate 0.05 or 20; alpha/beta grid",
            "random_per_length_L2_through_L6": RANDOM_CASES_PER_LENGTH,
            "random_log_rates": "independent uniform(log(rate)) on [-2,2]",
            "random_seed": RANDOM_SEED,
            "common_time_scales": [0.01, 1.0, 100.0],
            "expected_total": len(case_specs()),
        },
        "sensitivity": {
            "parameterization": "log(alpha), log(k_0..k_{L-2}), log(beta)",
            "outputs": "log(rho_0..rho_{L-1}), log(J)",
            "exact_reference": "central differences of independently recomputed CTMC stationary states",
            "mean_field_reference": "independent NumPy implicit solve at the converged mean-field state",
            "finite_difference_step": SENSITIVITY_STEP,
            "cuda_autograd_cases": "all L=2 constant-grid cases, first two random cases per length, and all common-scale cases",
        },
        "identifiability": {
            "density_only": "singular values of d(log rho)/d(log theta); global time scale is unidentifiable",
            "density_plus_absolute_flux": "singular values of d(log rho,log J)/d(log theta); absolute J fixes global time scale",
            "rank_tolerance": "max(matrix_shape)*eps(float64)*largest_singular_value",
            "interpretation": "local sensitivity rank and conditioning, not posterior uncertainty or biological validation",
        },
        "tolerances": {
            "exact_stationary_probability_and_flux": EXACT_STATIONARY_TOL,
            "mean_field_production_normalized_residual": 1e-10,
            "mean_field_sensitivity_crosscheck": SENSITIVITY_TOL,
            "cuda_autograd_crosscheck": CUDA_SENSITIVITY_TOL,
        },
        "requested_device": str(device),
        "cpu_fallback_allowed_for_explicit_cuda": False,
        "external_or_frozen_data_read": False,
        "gate_or_training_or_generator_execution": False,
        "implementation_sha256": sha256_file(__file__),
    }


def exact_ctmc_stationary(theta, length):
    theta = np.asarray(theta, dtype=np.float64)
    if theta.shape != (length + 1,) or np.any(theta <= 0.0) or not np.all(np.isfinite(theta)):
        raise ValueError("theta must contain finite positive alpha, internal rates, and beta")
    state_count = 1 << length
    generator = np.zeros((state_count, state_count), dtype=np.float64)
    for state in range(state_count):
        transitions = []
        if not state & 1:
            transitions.append((state | 1, theta[0]))
        for position in range(length - 1):
            current_bit = 1 << position
            next_bit = 1 << (position + 1)
            if state & current_bit and not state & next_bit:
                transitions.append((state ^ current_bit ^ next_bit, theta[position + 1]))
        last_bit = 1 << (length - 1)
        if state & last_bit:
            transitions.append((state ^ last_bit, theta[-1]))
        for destination, rate in transitions:
            generator[destination, state] += rate
            generator[state, state] -= rate
    normalized = generator.copy()
    normalized[-1, :] = 1.0
    rhs = np.zeros(state_count, dtype=np.float64)
    rhs[-1] = 1.0
    probability = np.linalg.solve(normalized, rhs)
    residual = generator @ probability
    if (
        not np.all(np.isfinite(probability))
        or np.min(probability) < -EXACT_STATIONARY_TOL
        or abs(np.sum(probability) - 1.0) > EXACT_STATIONARY_TOL
        or np.max(np.abs(residual)) > EXACT_STATIONARY_TOL
    ):
        raise RuntimeError("exact CTMC stationary solve failed its probability or residual check")
    probability = np.clip(probability, 0.0, None)
    probability /= probability.sum()
    occupancies = ((np.arange(state_count)[:, None] >> np.arange(length)[None, :]) & 1).astype(float)
    density = probability @ occupancies
    flux = float(theta[0] * (1.0 - density[0]))
    pair_joint = probability @ (occupancies[:, :-1] * occupancies[:, 1:])
    local_flux = np.concatenate((
        [flux],
        theta[1:-1] * (density[:-1] - pair_joint),
        [theta[-1] * density[-1]],
    ))
    covariance = pair_joint - density[:-1] * density[1:]
    conservation_error = float(np.max(np.abs(local_flux - flux)) / flux)
    if conservation_error > EXACT_STATIONARY_TOL:
        raise RuntimeError("exact CTMC flux conservation check failed")
    return {
        "density": density,
        "flux": flux,
        "covariance": covariance,
        "probability": probability,
        "stationary_residual_inf": float(np.max(np.abs(residual))),
        "conservation_relative_error": conservation_error,
    }


def exact_log_sensitivity(theta, length, step=SENSITIVITY_STEP):
    theta = np.asarray(theta, dtype=np.float64)
    jacobian = np.empty((length + 1, length + 1), dtype=np.float64)
    for parameter in range(length + 1):
        plus = theta.copy()
        minus = theta.copy()
        plus[parameter] *= math.exp(step)
        minus[parameter] *= math.exp(-step)
        plus_state = exact_ctmc_stationary(plus, length)
        minus_state = exact_ctmc_stationary(minus, length)
        plus_output = np.log(np.concatenate((plus_state["density"], [plus_state["flux"]])))
        minus_output = np.log(np.concatenate((minus_state["density"], [minus_state["flux"]])))
        jacobian[:, parameter] = (plus_output - minus_output) / (2.0 * step)
    return jacobian


def mean_field_log_sensitivity(theta, density, flux):
    theta = np.asarray(theta, dtype=np.float64)
    density = np.asarray(density, dtype=np.float64)
    length = density.size
    state = np.concatenate((density, [flux]))
    local_flux = np.concatenate((
        [theta[0] * (1.0 - density[0])],
        theta[1:-1] * density[:-1] * (1.0 - density[1:]),
        [theta[-1] * density[-1]],
    ))
    jacobian = np.zeros((length + 1, length + 1), dtype=np.float64)
    jacobian[:, -1] = -1.0
    jacobian[0, 0] = -theta[0]
    if length > 1:
        indices = np.arange(length - 1)
        jacobian[indices + 1, indices] = theta[1:-1] * (1.0 - density[1:])
        jacobian[indices + 1, indices + 1] = -theta[1:-1] * density[:-1]
    jacobian[-1, -2] = theta[-1]
    forcing = np.zeros((length + 1, length + 1), dtype=np.float64)
    forcing[0, 0] = local_flux[0]
    if length > 1:
        forcing[np.arange(1, length), np.arange(1, length)] = local_flux[1:-1]
    forcing[-1, -1] = local_flux[-1]
    derivative = np.linalg.solve(jacobian, -forcing)
    output = np.concatenate((density, [flux]))
    if not np.all(np.isfinite(derivative)) or np.any(output <= 0.0):
        raise RuntimeError("mean-field implicit sensitivity is non-finite or outside the log domain")
    if np.max(np.abs(local_flux - flux)) / flux > 2e-9:
        raise RuntimeError("mean-field state is insufficiently converged for implicit sensitivity")
    del state
    return derivative / output[:, None]


def production_mean_field(theta, device, autograd=False):
    log_theta = torch.tensor(
        np.log(np.asarray(theta, dtype=np.float64)),
        dtype=torch.float64,
        device=device,
        requires_grad=autograd,
    )
    rates = torch.exp(log_theta)
    alpha = rates[0]
    internal = rates[1:-1]
    beta = rates[-1]
    density, flux, residual = solve_kinetic_mean_field(alpha, internal, beta)
    output = torch.cat((density, flux.reshape(1)))
    sensitivity = None
    if autograd:
        rows = []
        for index in range(output.numel()):
            rows.append(torch.autograd.grad(
                torch.log(output[index]), log_theta, retain_graph=True,
            )[0])
        sensitivity = torch.stack(rows)
        if sensitivity.device != device:
            raise RuntimeError("mean-field autograd left the explicitly requested device")
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    if any(value.device != device for value in (density, flux, residual)):
        raise RuntimeError("mean-field forward left the explicitly requested device")
    return {
        "density": density.detach().cpu().numpy(),
        "flux": float(flux.detach().cpu()),
        "normalized_residual_inf": float(residual.detach().abs().max().cpu()),
        "sensitivity": None if sensitivity is None else sensitivity.detach().cpu().numpy(),
        "device": str(device),
    }


def identifiability_metrics(sensitivity, length):
    sensitivity = np.asarray(sensitivity, dtype=np.float64)
    density = sensitivity[:length]
    full = sensitivity
    parameter_count = length + 1

    def metrics(matrix, expected_rank):
        singular = np.linalg.svd(matrix, compute_uv=False)
        threshold = max(matrix.shape) * np.finfo(np.float64).eps * singular[0]
        rank = int(np.sum(singular > threshold))
        used = singular[:rank]
        return {
            "singular_values": singular.tolist(),
            "rank": rank,
            "expected_rank": expected_rank,
            "null_dimension": parameter_count - rank,
            "nonzero_condition_number": float(used[0] / used[-1]),
            "rank_matches_scale_contract": rank == expected_rank,
        }

    return {
        "density_only": metrics(density, length),
        "density_plus_absolute_flux": metrics(full, parameter_count),
        "common_scale_density_sum_inf": float(np.max(np.abs(density.sum(axis=1)))),
        "common_scale_log_flux_sum": float(full[-1].sum()),
    }


def max_abs(value):
    value = np.asarray(value, dtype=np.float64)
    return float(np.max(np.abs(value))) if value.size else 0.0


def needs_cuda_autograd(case):
    if case["group"] == "constant_rate_grid" and case["length"] == 2:
        return True
    if case["group"] == "log_uniform_random" and case["random_index"] < 2:
        return True
    return case["group"] == "common_time_scale"


def evaluate_case(case, device):
    length = case["length"]
    theta = np.asarray(case["theta"], dtype=np.float64)
    exact = exact_ctmc_stationary(theta, length)
    exact_sensitivity = exact_log_sensitivity(theta, length)
    record = {
        "name": case["name"],
        "group": case["group"],
        "length": length,
        "theta": theta.tolist(),
        "exact": {
            "density": exact["density"].tolist(),
            "flux": exact["flux"],
            "nearest_neighbor_covariance": exact["covariance"].tolist(),
            "stationary_residual_inf": exact["stationary_residual_inf"],
            "conservation_relative_error": exact["conservation_relative_error"],
        },
        "exact_sensitivity": exact_sensitivity.tolist(),
        "exact_identifiability": identifiability_metrics(exact_sensitivity, length),
        "cuda_autograd_requested": needs_cuda_autograd(case) and device.type == "cuda",
    }
    try:
        production = production_mean_field(
            theta, device, autograd=record["cuda_autograd_requested"],
        )
        mean_field_sensitivity = mean_field_log_sensitivity(
            theta, production["density"], production["flux"],
        )
        mf_identifiability = identifiability_metrics(mean_field_sensitivity, length)
        sensitivity_error = max_abs(
            production["sensitivity"] - mean_field_sensitivity
        ) if production["sensitivity"] is not None else None
        record.update({
            "mean_field": {
                "density": production["density"].tolist(),
                "flux": production["flux"],
                "normalized_residual_inf": production["normalized_residual_inf"],
                "device": production["device"],
            },
            "mean_field_sensitivity": mean_field_sensitivity.tolist(),
            "mean_field_identifiability": mf_identifiability,
            "approximation_error": {
                "density_max_abs": max_abs(production["density"] - exact["density"]),
                "density_rmse": float(np.sqrt(np.mean((production["density"] - exact["density"]) ** 2))),
                "flux_abs": abs(production["flux"] - exact["flux"]),
                "flux_relative": abs(production["flux"] - exact["flux"]) / exact["flux"],
                "sensitivity_max_abs": max_abs(mean_field_sensitivity - exact_sensitivity),
                "nearest_neighbor_covariance_max_abs": max_abs(exact["covariance"]),
            },
            "cuda_autograd_max_abs_error_vs_independent_implicit": sensitivity_error,
        })
        checks = [
            production["normalized_residual_inf"] <= 1e-10,
            np.all(np.isfinite(mean_field_sensitivity)),
            mf_identifiability["density_only"]["rank_matches_scale_contract"],
            mf_identifiability["density_plus_absolute_flux"]["rank_matches_scale_contract"],
            record["exact_identifiability"]["density_only"]["rank_matches_scale_contract"],
            record["exact_identifiability"]["density_plus_absolute_flux"]["rank_matches_scale_contract"],
            sensitivity_error is None or sensitivity_error <= CUDA_SENSITIVITY_TOL,
        ]
        record["passed"] = bool(all(checks))
        if not record["passed"]:
            record["failure"] = {"type": "NumericalCheckFailure", "checks": checks}
    except Exception as error:
        record["passed"] = False
        record["failure"] = {"type": type(error).__name__, "message": str(error)}
    return record


def aggregate_records(records, key):
    groups = {}
    for record in records:
        groups.setdefault(str(record[key]), []).append(record)
    result = {}
    for name, group in sorted(groups.items()):
        successful = [record for record in group if "approximation_error" in record]
        aggregate = {
            "count": len(group),
            "passed_count": sum(record["passed"] for record in group),
            "failure_names": [record["name"] for record in group if not record["passed"]],
        }
        for metric in (
            "density_max_abs", "density_rmse", "flux_relative",
            "sensitivity_max_abs", "nearest_neighbor_covariance_max_abs",
        ):
            values = [record["approximation_error"][metric] for record in successful]
            aggregate[metric] = {
                "quantile_0_50_90_95_100": np.quantile(values, [0.0, 0.5, 0.9, 0.95, 1.0]).tolist(),
            } if values else None
        result[name] = aggregate
    return result


def time_scale_checks(records):
    scaled = [record for record in records if record["group"] == "common_time_scale"]
    if len(scaled) != 3 or any("mean_field" not in record for record in scaled):
        return {"passed": False, "reason": "common-scale cases are incomplete or failed"}
    base = next(record for record in scaled if record["name"] == "time_scale_L4_s1")
    checks = []
    for record in scaled:
        scale = record["theta"][0] / base["theta"][0]
        checks.append({
            "name": record["name"],
            "scale": scale,
            "exact_density_max_abs": max_abs(np.asarray(record["exact"]["density"]) - base["exact"]["density"]),
            "mean_field_density_max_abs": max_abs(np.asarray(record["mean_field"]["density"]) - base["mean_field"]["density"]),
            "exact_flux_scaling_relative_error": abs(record["exact"]["flux"] / base["exact"]["flux"] / scale - 1.0),
            "mean_field_flux_scaling_relative_error": abs(record["mean_field"]["flux"] / base["mean_field"]["flux"] / scale - 1.0),
        })
    return {
        "passed": all(
            max(check[key] for key in (
                "exact_density_max_abs", "mean_field_density_max_abs",
                "exact_flux_scaling_relative_error", "mean_field_flux_scaling_relative_error",
            )) <= 1e-8
            for check in checks
        ),
        "interpretation": "density identifies relative rates only; absolute flux additionally identifies the common time scale",
        "cases": checks,
    }


def git_metadata():
    def run(*arguments):
        return subprocess.run(
            ["git", *arguments], cwd=ROOT, check=True, text=True, capture_output=True,
        ).stdout.strip()
    return {"head": run("rev-parse", "HEAD"), "status_porcelain": run("status", "--porcelain")}


def environment(device):
    cuda = {
        "requested": device.type == "cuda",
        "available": torch.cuda.is_available(),
        "cpu_fallback": False,
    }
    if device.type == "cuda":
        if not cuda["available"]:
            raise RuntimeError("CUDA was explicitly requested; refusing CPU fallback")
        cuda.update({
            "device": str(device),
            "name": torch.cuda.get_device_name(device),
            "capability": list(torch.cuda.get_device_capability(device)),
            "torch_cuda_version": torch.version.cuda,
        })
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "torch": torch.__version__,
        "cuda": cuda,
    }


def summarize(records, device, cases_path, command):
    successful = [record for record in records if "approximation_error" in record]
    worst = sorted(
        successful,
        key=lambda record: record["approximation_error"]["density_max_abs"],
        reverse=True,
    )[:25]
    return {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "git": git_metadata(),
        "environment": environment(device),
        "passed": bool(records) and all(record["passed"] for record in records) and time_scale_checks(records)["passed"],
        "numerical_pass_meaning": "all reference, conservation, rank, sensitivity, and CUDA checks passed; not an approximation-accuracy gate",
        "case_count": len(records),
        "failure_count": sum(not record["passed"] for record in records),
        "failures": [
            {"name": record["name"], "failure": record.get("failure")}
            for record in records if not record["passed"]
        ],
        "by_group": aggregate_records(records, "group"),
        "by_length": aggregate_records(records, "length"),
        "common_time_scale": time_scale_checks(records),
        "worst_density_cases": [
            {
                "name": record["name"],
                "group": record["group"],
                "length": record["length"],
                "theta": record["theta"],
                "approximation_error": record["approximation_error"],
            }
            for record in worst
        ],
        "scope": {
            "synthetic_small_state_only": True,
            "exact_stochastic_simulation_performed": False,
            "exact_stationary_ctmc_reference_performed": True,
            "biological_or_functional_claim": False,
            "gate_decision_or_E2_performance_claim": False,
            "external_or_frozen_data_read": False,
        },
        "artifact_sha256": {
            "implementation": sha256_file(__file__),
            "production_mean_field": sha256_file(ROOT / "src/codonflow/models/kinetic_mean_field.py"),
            "cases_jsonl": sha256_file(cases_path),
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    device = torch.device("cuda:0" if args.device == "cuda" else "cpu")
    command = f"PYTHONPATH=src:. python {Path(__file__).name} --output-dir {args.output_dir} --device {args.device}"
    write_json_exclusive(args.output_dir / "protocol.json", protocol_payload(device))
    records = []
    cases_path = args.output_dir / "cases.jsonl"
    try:
        with cases_path.open("x", encoding="utf-8", newline="\n") as handle:
            for index, case in enumerate(case_specs()):
                record = evaluate_case(case, device)
                records.append(record)
                handle.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
                handle.flush()
                if (index + 1) % 100 == 0:
                    print(f"evaluated {index + 1}/{len(case_specs())} cases", flush=True)
        report = summarize(records, device, cases_path, command)
        write_json_exclusive(args.output_dir / "validation.json", report)
    except Exception as error:
        write_json_exclusive(args.output_dir / "failure.json", {
            "schema": SCHEMA,
            "passed": False,
            "completed_case_count": len(records),
            "error": {"type": type(error).__name__, "message": str(error)},
            "command": command,
            "git": git_metadata(),
        })
        raise
    print(json.dumps({
        "passed": report["passed"],
        "case_count": report["case_count"],
        "failure_count": report["failure_count"],
        "output": str(args.output_dir / "validation.json"),
        "output_sha256": sha256_file(args.output_dir / "validation.json"),
    }))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
