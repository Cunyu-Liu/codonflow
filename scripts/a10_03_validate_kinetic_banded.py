#!/usr/bin/env python3
"""Validate and benchmark the A10 E2 banded kinetic solve without training."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import sys
import time
from pathlib import Path

import numpy as np
import scipy
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import codonflow.models.kinetic_mean_field as banded

SCHEMA = "a10-e2-kinetic-banded-validation-v1"
RESIDUAL_TOL = 1e-10
LINEAR_SCALED_TOL = 2e-11
SOLUTION_EQUIVALENCE_TOL = 2e-8
GRADIENT_EQUIVALENCE_TOL = 2e-7
FINITE_DIFFERENCE_TOL = 2e-6


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_baseline(path):
    spec = importlib.util.spec_from_file_location("a10_e2_baseline_dense", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def random_spec(seed, length):
    rng = np.random.default_rng(seed)
    return {
        "name": f"random_l{length}_s{seed}",
        "length": length,
        "alpha": float(rng.uniform(0.4, 1.8)),
        "rates": np.exp(rng.uniform(-2.0, 2.0, length - 1)),
        "beta": float(rng.uniform(0.4, 1.8)),
    }


def real_spec(path):
    with np.load(path, allow_pickle=False) as data:
        return {
            "name": "real_solver_diagnostic_snapshot",
            "length": int(data["rates"].size + 1),
            "alpha": float(data["alpha"]),
            "rates": np.asarray(data["rates"], dtype=np.float64).copy(),
            "beta": float(data["beta"]),
        }


def objective_weights(length, device):
    positions = torch.arange(length, dtype=torch.float64, device=device)
    return torch.sin(0.013 * positions) + 0.2 * torch.cos(0.031 * positions), 0.37


def make_inputs(spec, device):
    alpha = torch.tensor(
        spec["alpha"], dtype=torch.float64, device=device, requires_grad=True
    )
    rates = torch.tensor(
        spec["rates"], dtype=torch.float64, device=device, requires_grad=True
    )
    beta = torch.tensor(
        spec["beta"], dtype=torch.float64, device=device, requires_grad=True
    )
    return alpha, rates, beta


def synchronize(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def run_single(module, spec, device):
    alpha, rates, beta = make_inputs(spec, device)
    synchronize(device)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    start = time.perf_counter()
    rho, flux, residual = module.solve_kinetic_mean_field(alpha, rates, beta)
    synchronize(device)
    forward_seconds = time.perf_counter() - start
    forward_peak = (
        torch.cuda.max_memory_allocated(device) if device.type == "cuda" else 0
    )
    weights, flux_weight = objective_weights(rho.numel(), device)
    objective = torch.dot(weights, rho) + flux_weight * flux
    before_backward = torch.cuda.memory_allocated(device) if device.type == "cuda" else 0
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    synchronize(device)
    start = time.perf_counter()
    gradients = torch.autograd.grad(objective, (alpha, rates, beta))
    synchronize(device)
    backward_seconds = time.perf_counter() - start
    backward_peak = (
        torch.cuda.max_memory_allocated(device) if device.type == "cuda" else 0
    )
    return {
        "rho": rho.detach().cpu().numpy(),
        "flux": float(flux.detach().cpu()),
        "residual": residual.detach().cpu().numpy(),
        "gradients": torch.cat((
            gradients[0].detach().reshape(1),
            gradients[1].detach(),
            gradients[2].detach().reshape(1),
        )).cpu().numpy(),
        "device_tensors": [
            str(value.device) for value in (rho, flux, *gradients)
        ],
        "forward_seconds": forward_seconds,
        "backward_seconds": backward_seconds,
        "forward_peak_allocated_bytes": int(forward_peak),
        "backward_peak_allocated_bytes": int(backward_peak),
        "backward_incremental_peak_bytes": int(backward_peak - before_backward),
    }


def independent_residual_jacobian(spec, rho, flux):
    rates = spec["rates"]
    length = rates.size + 1
    local_flux = np.concatenate((
        [spec["alpha"] * (1.0 - rho[0])],
        rates * rho[:-1] * (1.0 - rho[1:]),
        [spec["beta"] * rho[-1]],
    ))
    jacobian = np.zeros((length + 1, length + 1), dtype=np.float64)
    jacobian[0, 0] = -spec["alpha"]
    if length > 1:
        indices = np.arange(1, length)
        jacobian[indices, indices - 1] = rates * (1.0 - rho[1:])
        jacobian[indices, indices] = -rates * rho[:-1]
    jacobian[-1, -2] = spec["beta"]
    jacobian[:, -1] = -1.0
    return local_flux - flux, jacobian, local_flux


def extended_conservation(spec, rho, flux):
    alpha = np.longdouble(spec["alpha"])
    beta = np.longdouble(spec["beta"])
    rates = np.asarray(spec["rates"], dtype=np.longdouble)
    rho = np.asarray(rho, dtype=np.longdouble)
    flux_extended = np.longdouble(flux)
    local = np.concatenate((
        [alpha * (1.0 - rho[0])],
        rates * rho[:-1] * (1.0 - rho[1:]),
        [beta * rho[-1]],
    ))
    return float(np.max(np.abs(local - flux_extended) / abs(flux_extended)))


def independent_dense_gradient(spec, rho, flux, device):
    _, jacobian, _ = independent_residual_jacobian(spec, rho, flux)
    weights, flux_weight = objective_weights(rho.size, device)
    gradient = np.concatenate((
        weights.detach().cpu().numpy(), [flux_weight]
    ))
    adjoint = np.linalg.solve(jacobian.T, gradient)
    recovery = jacobian.T @ adjoint - gradient
    denominator = np.abs(jacobian.T) @ np.abs(adjoint) + np.abs(gradient)
    relative = np.abs(recovery) / np.where(denominator > 0, denominator, 1.0)
    rates = spec["rates"]
    parameters = np.concatenate((
        [-adjoint[0] * (1.0 - rho[0])],
        -adjoint[1:-1] * rho[:-1] * (1.0 - rho[1:]),
        [-adjoint[-1] * rho[-1]],
    ))
    return parameters, float(np.max(relative))


def directional_finite_difference(spec, analytic_gradient, device):
    length = spec["length"]
    rng = np.random.default_rng(5519 + length)
    direction = rng.normal(size=length + 1)
    direction /= np.linalg.norm(direction)
    analytic = float(np.dot(analytic_gradient, direction))
    records = []
    for step in (1e-4, 1e-5):
        values = []
        for sign in (1.0, -1.0):
            shifted = {
                "alpha": spec["alpha"] + sign * step * direction[0],
                "rates": spec["rates"] + sign * step * direction[1:-1],
                "beta": spec["beta"] + sign * step * direction[-1],
            }
            with torch.no_grad():
                rho, flux, residual = banded.solve_kinetic_mean_field(
                    torch.tensor(shifted["alpha"], dtype=torch.float64, device=device),
                    torch.tensor(shifted["rates"], dtype=torch.float64, device=device),
                    torch.tensor(shifted["beta"], dtype=torch.float64, device=device),
                )
            if float(residual.abs().max()) > RESIDUAL_TOL:
                raise RuntimeError("finite-difference forward violated strict residual")
            weights, flux_weight = objective_weights(length, device)
            values.append(float(torch.dot(weights, rho) + flux_weight * flux))
        numeric = (values[0] - values[1]) / (2.0 * step)
        records.append({
            "step": step,
            "analytic": analytic,
            "numeric": numeric,
            "scaled_error": abs(numeric - analytic) / max(1.0, abs(analytic)),
        })
    return records


def max_absolute(left, right):
    return float(np.max(np.abs(np.asarray(left) - np.asarray(right))))


def summarize_single(spec, baseline_result, banded_result, device):
    independent_error = independent_dense_gradient(
        spec,
        banded_result["rho"],
        banded_result["flux"],
        device,
    ) if spec["length"] <= 128 else (None, None)
    independent_gradient, independent_recovery = independent_error
    finite_differences = directional_finite_difference(
        spec, banded_result["gradients"], device
    )
    result = {
        "name": spec["name"],
        "length": spec["length"],
        "forward_max_normalized_residual": float(np.max(np.abs(banded_result["residual"]))),
        "independent_extended_conservation": extended_conservation(
            spec, banded_result["rho"], banded_result["flux"]
        ),
        "baseline_solution_max_absolute_error": max_absolute(
            baseline_result["rho"], banded_result["rho"]
        ),
        "baseline_flux_absolute_error": abs(
            baseline_result["flux"] - banded_result["flux"]
        ),
        "baseline_gradient_max_absolute_error": max_absolute(
            baseline_result["gradients"], banded_result["gradients"]
        ),
        "independent_dense_gradient_max_absolute_error": (
            max_absolute(independent_gradient, banded_result["gradients"])
            if independent_gradient is not None else None
        ),
        "independent_dense_adjoint_recovery": independent_recovery,
        "finite_differences": finite_differences,
        "max_finite_difference_scaled_error": max(
            item["scaled_error"] for item in finite_differences
        ),
        "baseline": {key: value for key, value in baseline_result.items() if key not in {"rho", "flux", "residual", "gradients"}},
        "banded": {key: value for key, value in banded_result.items() if key not in {"rho", "flux", "residual", "gradients"}},
    }
    result["forward_speedup_baseline_over_banded"] = (
        baseline_result["forward_seconds"] / banded_result["forward_seconds"]
    )
    result["backward_speedup_baseline_over_banded"] = (
        baseline_result["backward_seconds"] / banded_result["backward_seconds"]
    )
    result["backward_peak_ratio_banded_over_baseline"] = (
        banded_result["backward_peak_allocated_bytes"]
        / max(1, baseline_result["backward_peak_allocated_bytes"])
    )
    result["passed"] = bool(
        result["forward_max_normalized_residual"] <= RESIDUAL_TOL
        and result["independent_extended_conservation"] <= RESIDUAL_TOL
        and result["baseline_solution_max_absolute_error"] <= SOLUTION_EQUIVALENCE_TOL
        and result["baseline_flux_absolute_error"] <= SOLUTION_EQUIVALENCE_TOL
        and result["baseline_gradient_max_absolute_error"] <= GRADIENT_EQUIVALENCE_TOL
        and (independent_gradient is None or (
            result["independent_dense_gradient_max_absolute_error"] <= GRADIENT_EQUIVALENCE_TOL
            and independent_recovery <= RESIDUAL_TOL
        ))
        and result["max_finite_difference_scaled_error"] <= FINITE_DIFFERENCE_TOL
        and all(value.startswith(str(device)) for value in banded_result["device_tensors"])
    )
    return result, independent_gradient


def run_mixed_batch(baseline_module, device):
    lengths = [1, 2, 17, 128, 513]
    rng = np.random.default_rng(771)
    alpha_np = rng.uniform(0.6, 1.5, len(lengths))
    beta_np = rng.uniform(0.5, 1.7, len(lengths))
    rates_np = np.zeros((len(lengths), max(lengths) - 1), dtype=np.float64)
    for index, length in enumerate(lengths):
        rates_np[index, : length - 1] = np.exp(rng.uniform(-1.5, 1.5, length - 1))
    results = {}
    for name, module in (("baseline", baseline_module), ("banded", banded)):
        alpha = torch.tensor(alpha_np, dtype=torch.float64, device=device, requires_grad=True)
        rates = torch.tensor(rates_np, dtype=torch.float64, device=device, requires_grad=True)
        beta = torch.tensor(beta_np, dtype=torch.float64, device=device, requires_grad=True)
        lengths_tensor = torch.tensor(lengths, dtype=torch.int64, device=device)
        synchronize(device)
        if device.type == "cuda":
            torch.cuda.reset_peak_memory_stats(device)
        start = time.perf_counter()
        rho, flux, residual = module.solve_kinetic_mean_field_batch(
            alpha, rates, lengths_tensor, beta
        )
        synchronize(device)
        forward_seconds = time.perf_counter() - start
        weights = torch.sin(torch.arange(max(lengths), dtype=torch.float64, device=device) * 0.017)
        objective = (rho * weights).sum() + 0.29 * flux.sum()
        if device.type == "cuda":
            torch.cuda.reset_peak_memory_stats(device)
        start = time.perf_counter()
        gradients = torch.autograd.grad(objective, (alpha, rates, beta))
        synchronize(device)
        backward_seconds = time.perf_counter() - start
        results[name] = {
            "rho": rho.detach().cpu().numpy(),
            "flux": flux.detach().cpu().numpy(),
            "residual": residual.detach().cpu().numpy(),
            "gradients": [value.detach().cpu().numpy() for value in gradients],
            "devices": [str(value.device) for value in (rho, flux, *gradients)],
            "forward_seconds": forward_seconds,
            "backward_seconds": backward_seconds,
            "backward_peak_allocated_bytes": int(torch.cuda.max_memory_allocated(device)) if device.type == "cuda" else 0,
        }
    errors = {
        "rho": max_absolute(results["baseline"]["rho"], results["banded"]["rho"]),
        "flux": max_absolute(results["baseline"]["flux"], results["banded"]["flux"]),
        "alpha_gradient": max_absolute(results["baseline"]["gradients"][0], results["banded"]["gradients"][0]),
        "rates_gradient": max_absolute(results["baseline"]["gradients"][1], results["banded"]["gradients"][1]),
        "beta_gradient": max_absolute(results["baseline"]["gradients"][2], results["banded"]["gradients"][2]),
    }
    valid = results["banded"]["residual"]
    max_residual = 0.0
    for index, length in enumerate(lengths):
        max_residual = max(max_residual, float(np.max(np.abs(valid[index, : length + 1]))))
        if np.any(valid[index, length + 1 :] != 0.0):
            raise RuntimeError("mixed batch residual padding is not zero")
    passed = bool(
        max_residual <= RESIDUAL_TOL
        and errors["rho"] <= SOLUTION_EQUIVALENCE_TOL
        and errors["flux"] <= SOLUTION_EQUIVALENCE_TOL
        and all(errors[key] <= GRADIENT_EQUIVALENCE_TOL for key in ("alpha_gradient", "rates_gradient", "beta_gradient"))
        and all(value.startswith(str(device)) for value in results["banded"]["devices"])
    )
    return {
        "lengths": lengths,
        "max_normalized_residual": max_residual,
        "errors": errors,
        "baseline": {key: value for key, value in results["baseline"].items() if key not in {"rho", "flux", "residual", "gradients"}},
        "banded": {key: value for key, value in results["banded"].items() if key not in {"rho", "flux", "residual", "gradients"}},
        "passed": passed,
    }


def validate_linear_algebra(device):
    rng = np.random.default_rng(20261126)
    max_errors = {"numpy_forward": 0.0, "numpy_transpose": 0.0, "torch_forward": 0.0, "torch_transpose": 0.0}
    max_recovery = 0.0
    qr_count = 0
    cases = 0
    for size in range(2, 21):
        for _ in range(10):
            lower = rng.normal(size=size - 1)
            diagonal = rng.normal(size=size)
            diagonal[-1] = 0.0
            upper = rng.normal(size=size - 1)
            upper[-1] = 0.0
            flux = rng.normal(size=size)
            rhs = rng.normal(size=size)
            matrix = np.zeros((size, size), dtype=np.float64)
            matrix[np.arange(size), np.arange(size)] = diagonal
            matrix[np.arange(1, size), np.arange(size - 1)] = lower
            matrix[np.arange(size - 1), np.arange(1, size)] = upper
            matrix[:, -1] = flux
            bands_np = (lower, diagonal, upper, flux)
            bands_torch = tuple(torch.as_tensor(value, dtype=torch.float64, device=device).unsqueeze(0) for value in bands_np)
            rhs_torch = torch.as_tensor(rhs, dtype=torch.float64, device=device).unsqueeze(0)
            for transpose in (False, True):
                expected = np.linalg.solve(matrix.T if transpose else matrix, rhs)
                actual, info = banded._rank_one_banded_solve_numpy(
                    bands_np, rhs, transpose=transpose
                )
                qr_count += int(info["qr_fallback"])
                key = "numpy_transpose" if transpose else "numpy_forward"
                max_errors[key] = max(max_errors[key], max_absolute(actual, expected) / max(1.0, float(np.max(np.abs(expected)))))
                max_recovery = max(max_recovery, float(np.max(info["relative_recovery_extended"])))
                actual_torch, _ = banded._banded_rank_one_solve_torch(
                    bands_torch, rhs_torch, transpose=transpose
                )
                key = "torch_transpose" if transpose else "torch_forward"
                torch_error = max_absolute(actual_torch[0].detach().cpu().numpy(), expected) / max(1.0, float(np.max(np.abs(expected))))
                max_errors[key] = max(max_errors[key], torch_error)
                recovery = banded._banded_matvec_torch(bands_torch, actual_torch, transpose=transpose) - rhs_torch
                denominator = banded._banded_matvec_torch(tuple(value.abs() for value in bands_torch), actual_torch.abs(), transpose=transpose) + rhs_torch.abs()
                relative = recovery.abs() / torch.where(denominator > 0, denominator, torch.ones_like(denominator))
                max_recovery = max(max_recovery, float(relative.max()))
                cases += 1
    return {
        "cases_per_path": cases,
        "max_scaled_errors": max_errors,
        "max_component_recovery": max_recovery,
        "numpy_qr_fallback_count": qr_count,
        "passed": bool(
            max(max_errors.values()) <= LINEAR_SCALED_TOL
            and max_recovery <= RESIDUAL_TOL
            and qr_count == 0
        ),
    }


def near_singular_status():
    bands = (
        np.asarray([0.5]), np.asarray([-1.0, 0.0]), np.asarray([0.0]),
        np.asarray([-1.0, 0.5 - 1e-15]),
    )
    try:
        _, info = banded._rank_one_banded_solve_numpy(bands, np.asarray([0.2, -0.1]))
    except RuntimeError as error:
        return {"outcome": "fail_closed", "qr_fallback": bool(error.linear_solver_info["qr_fallback"]), "passed": bool(error.linear_solver_info["qr_fallback"])}
    return {"outcome": "strict_qr_solution", "qr_fallback": info["qr_fallback"], "max_recovery": float(np.max(info["relative_recovery_extended"])), "passed": bool(info["qr_fallback"] and np.max(info["relative_recovery_extended"]) <= RESIDUAL_TOL)}


def validate(output, array_output, baseline_path, snapshot_path, device):
    if device.type != "cuda" or not torch.cuda.is_available():
        raise RuntimeError("real CUDA is explicitly required; refusing CPU fallback")
    baseline_module = load_baseline(baseline_path)
    linear = validate_linear_algebra(device)
    cases = []
    real_arrays = None
    specs = [random_spec(1000 + length, length) for length in (2, 3, 17, 128, 512, 4096)]
    specs.append(real_spec(snapshot_path))
    for spec in specs:
        baseline_result = run_single(baseline_module, spec, device)
        banded_result = run_single(banded, spec, device)
        summary, independent_gradient = summarize_single(
            spec, baseline_result, banded_result, device
        )
        cases.append(summary)
        if spec["name"] == "real_solver_diagnostic_snapshot":
            real_arrays = {
                "alpha": np.asarray(spec["alpha"]),
                "rates": spec["rates"],
                "beta": np.asarray(spec["beta"]),
                "rho": banded_result["rho"],
                "flux": np.asarray(banded_result["flux"]),
                "production_gradients": banded_result["gradients"],
                "baseline_gradients": baseline_result["gradients"],
                "normalized_residual": banded_result["residual"],
            }
    mixed = run_mixed_batch(baseline_module, device)
    singular = near_singular_status()
    passed = bool(linear["passed"] and mixed["passed"] and singular["passed"] and all(case["passed"] for case in cases))
    report = {
        "schema": SCHEMA,
        "passed": passed,
        "scope": {
            "training_executed": False,
            "scientific_gate_claimed": False,
            "H2_or_G1_evaluated": False,
            "untouched24_or_MAGE_untouched_read": False,
            "historical_artifacts_overwritten": False,
            "real_snapshot_name": "kinetic_solver_diagnostic_v1/current_case.npz",
            "exact_v7_or_v8_failure_state_claimed": False,
            "forward_cpu_path": "explicit scipy LAPACK banded partial pivoting",
            "adjoint_device": str(device),
            "adjoint_cpu_fallback": False,
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "torch_cuda": torch.version.cuda,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "device": str(device),
            "device_name": torch.cuda.get_device_name(device),
            "longdouble_eps": str(np.finfo(np.longdouble).eps),
        },
        "tolerances": {
            "forward_and_component_recovery": RESIDUAL_TOL,
            "linear_scaled_error": LINEAR_SCALED_TOL,
            "baseline_solution_absolute": SOLUTION_EQUIVALENCE_TOL,
            "gradient_absolute": GRADIENT_EQUIVALENCE_TOL,
            "central_finite_difference_scaled": FINITE_DIFFERENCE_TOL,
        },
        "linear_algebra": linear,
        "single_cases": cases,
        "mixed_batch": mixed,
        "near_singular_rank_one": singular,
        "artifact_sha256": {
            "solver": sha256_file(ROOT / "src" / "codonflow" / "models" / "kinetic_mean_field.py"),
            "validation_script": sha256_file(__file__),
            "baseline_solver": sha256_file(baseline_path),
            "real_snapshot": sha256_file(snapshot_path),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    if real_arrays is not None:
        with array_output.open("xb") as handle:
            np.savez(handle, **real_arrays)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--array-output", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--real-snapshot", required=True, type=Path)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args(argv)
    if args.output.exists() or args.array_output.exists():
        raise FileExistsError("refusing to overwrite existing validation artifacts")
    try:
        report = validate(
            args.output, args.array_output, args.baseline, args.real_snapshot,
            torch.device(args.device),
        )
    except Exception as error:
        failure = {
            "schema": SCHEMA,
            "passed": False,
            "scope": {"training_executed": False, "scientific_gate_claimed": False},
            "error": {"type": type(error).__name__, "message": str(error)},
            "artifact_sha256": {
                "solver": sha256_file(ROOT / "src" / "codonflow" / "models" / "kinetic_mean_field.py"),
                "validation_script": sha256_file(__file__),
                "baseline_solver": sha256_file(args.baseline),
                "real_snapshot": sha256_file(args.real_snapshot),
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(failure, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
        print(json.dumps(failure, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({
        "passed": report["passed"],
        "single_cases": len(report["single_cases"]),
        "max_forward_speedup": max(case["forward_speedup_baseline_over_banded"] for case in report["single_cases"]),
        "max_backward_speedup": max(case["backward_speedup_baseline_over_banded"] for case in report["single_cases"]),
        "output": str(args.output),
    }, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
