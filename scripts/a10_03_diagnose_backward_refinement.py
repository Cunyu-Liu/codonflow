#!/usr/bin/env python3
"""Independently validate long-sequence CUDA implicit backward refinement."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
import scipy
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from codonflow.models.kinetic_mean_field import solve_kinetic_mean_field

SCHEMA = "a10-03-backward-refinement-cuda-v1"
STEPS = (1e-3, 1e-4, 1e-5, 1e-6)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def independent_sparse_jacobian(rho, alpha, rates, beta):
    length = rho.size
    rows = [0, length]
    columns = [0, length - 1]
    values = [-alpha, beta]
    if length > 1:
        indices = np.arange(1, length)
        rows.extend(indices)
        columns.extend(indices - 1)
        rows.extend(indices)
        columns.extend(indices)
        values.extend(rates * (1.0 - rho[1:]))
        values.extend(-rates * rho[:-1])
    rows.extend(np.arange(length + 1))
    columns.extend(np.full(length + 1, length))
    values.extend(-np.ones(length + 1))
    return coo_matrix(
        (values, (rows, columns)), shape=(length + 1, length + 1)
    ).tocsc()


def extended_recovery(matrix_transpose, multiplier, gradient):
    matrix = np.asarray(matrix_transpose.toarray(), dtype=np.longdouble)
    multiplier = np.asarray(multiplier, dtype=np.longdouble)
    gradient = np.asarray(gradient, dtype=np.longdouble)
    recovery = matrix @ multiplier - gradient
    denominator = np.abs(matrix) @ np.abs(multiplier) + np.abs(gradient)
    relative = np.abs(recovery).copy()
    np.divide(np.abs(recovery), denominator, out=relative, where=denominator > 0)
    return recovery, denominator, relative


def objective_value(alpha, rates, beta, weights, flux_weight):
    with torch.no_grad():
        rho, flux, residual = solve_kinetic_mean_field(alpha, rates, beta)
    if not bool(torch.isfinite(residual).all()) or float(residual.abs().max()) > 1e-10:
        raise RuntimeError("finite-difference forward solve failed its strict residual")
    return float(torch.dot(weights, rho) + flux_weight * flux)


def validate(snapshot, device):
    if device.type != "cuda" or not torch.cuda.is_available():
        raise RuntimeError("explicit CUDA is required; refusing CPU fallback")
    with np.load(snapshot, allow_pickle=False) as data:
        alpha_value = float(data["alpha"])
        rates_value = np.asarray(data["rates"], dtype=np.float64).copy()
        beta_value = float(data["beta"])
    alpha = torch.tensor(alpha_value, dtype=torch.float64, device=device, requires_grad=True)
    rates = torch.tensor(rates_value, dtype=torch.float64, device=device, requires_grad=True)
    beta = torch.tensor(beta_value, dtype=torch.float64, device=device, requires_grad=True)
    rho, flux, residual, diagnostics = solve_kinetic_mean_field(
        alpha, rates, beta, return_diagnostics=True
    )
    length = rho.numel()
    positions = torch.arange(length, dtype=torch.float64, device=device)
    weights = torch.sin(0.17 * positions) + 0.2 * torch.cos(0.031 * positions)
    flux_weight = torch.tensor(0.37, dtype=torch.float64, device=device)
    objective = torch.dot(weights, rho) + flux_weight * flux
    gradients = torch.autograd.grad(objective, (alpha, rates, beta))
    torch.cuda.synchronize(device)
    gradient_vector = torch.cat((gradients[0].reshape(1), gradients[1], gradients[2].reshape(1)))
    direction_np = np.cos(0.113 * np.arange(length + 1))
    direction_np /= np.linalg.norm(direction_np)
    direction = torch.as_tensor(direction_np, dtype=torch.float64, device=device)
    analytic_directional = float(torch.dot(gradient_vector, direction))

    finite_differences = []
    for step in STEPS:
        shifted = direction * step
        plus = objective_value(
            alpha.detach() + shifted[0],
            rates.detach() + shifted[1:-1],
            beta.detach() + shifted[-1],
            weights,
            flux_weight,
        )
        minus = objective_value(
            alpha.detach() - shifted[0],
            rates.detach() - shifted[1:-1],
            beta.detach() - shifted[-1],
            weights,
            flux_weight,
        )
        numeric = (plus - minus) / (2.0 * step)
        finite_differences.append({
            "step": step,
            "plus": plus,
            "minus": minus,
            "directional_derivative": numeric,
            "absolute_error": abs(numeric - analytic_directional),
            "scaled_error": abs(numeric - analytic_directional) / max(1.0, abs(analytic_directional)),
        })

    rho_np = rho.detach().cpu().numpy()
    gradient_np = torch.cat((weights, flux_weight.reshape(1))).detach().cpu().numpy()
    sparse_jacobian = independent_sparse_jacobian(rho_np, alpha_value, rates_value, beta_value)
    independent_multiplier = spsolve(sparse_jacobian.transpose().tocsc(), gradient_np)
    recovery, denominator, relative = extended_recovery(
        sparse_jacobian.transpose(), independent_multiplier, gradient_np
    )
    independent_gradients = np.concatenate((
        [-independent_multiplier[0] * (1.0 - rho_np[0])],
        -independent_multiplier[1:-1] * rho_np[:-1] * (1.0 - rho_np[1:]),
        [-independent_multiplier[-1] * rho_np[-1]],
    ))
    production_gradients = gradient_vector.detach().cpu().numpy()
    independent_condition = float(np.linalg.cond(sparse_jacobian.toarray()))
    production_condition = float(diagnostics["jacobian_condition_number"].detach().cpu())
    refined_differences = [item for item in finite_differences if item["step"] <= 1e-4]
    max_finite_difference_error = max(item["scaled_error"] for item in refined_differences)
    independent_gradient_error = float(np.max(np.abs(
        production_gradients - independent_gradients
    )))
    independent_recovery = float(np.max(relative))
    passed = bool(
        device.type == "cuda"
        and all(item.device.type == "cuda" for item in (rho, flux, *gradients))
        and float(residual.abs().max()) <= 1e-10
        and float(diagnostics["backward_recovery_residual"]) <= 1e-10
        and max_finite_difference_error <= 2e-6
        and independent_gradient_error <= 2e-7
        and independent_recovery <= 1e-10
        and np.isfinite(independent_condition)
        and np.isfinite(production_condition)
    )
    arrays = {
        "alpha": np.asarray(alpha_value),
        "rates": rates_value,
        "beta": np.asarray(beta_value),
        "rho": rho_np,
        "flux": flux.detach().cpu().numpy(),
        "weights": weights.detach().cpu().numpy(),
        "flux_weight": flux_weight.detach().cpu().numpy(),
        "direction": direction_np,
        "production_gradients": production_gradients,
        "independent_gradients": independent_gradients,
        "independent_multiplier": independent_multiplier,
        "independent_recovery_extended": recovery,
        "independent_denominator_extended": denominator,
        "independent_relative_extended": relative,
    }
    return {
        "schema": SCHEMA,
        "passed": passed,
        "scope": {
            "real_training_snapshot_reused": True,
            "v8_sample_13_recovered_or_claimed_fixed": False,
            "training_executed": False,
            "H2_or_G1_validation_claimed": False,
            "untouched24_or_MAGE_untouched_read": False,
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "cuda_device": str(device),
            "cuda_name": torch.cuda.get_device_name(device),
            "cuda_capability": list(torch.cuda.get_device_capability(device)),
            "longdouble_eps": str(np.finfo(np.longdouble).eps),
        },
        "case": {
            "length": length,
            "alpha": alpha_value,
            "beta": beta_value,
            "rate_min": float(rates_value.min()),
            "rate_max": float(rates_value.max()),
            "forward_max_normalized_residual": float(residual.abs().max()),
            "production_backward_recovery": float(diagnostics["backward_recovery_residual"]),
            "production_refinement_steps": int(diagnostics["backward_refinement_steps"]),
            "production_qr_fallback": bool(diagnostics["backward_qr_fallback"]),
            "production_jacobian_condition": production_condition,
            "independent_jacobian_condition": independent_condition,
            "condition_absolute_difference": abs(production_condition - independent_condition),
            "analytic_directional_derivative": analytic_directional,
            "max_finite_difference_scaled_error": max_finite_difference_error,
            "independent_gradient_max_absolute_error": independent_gradient_error,
            "independent_sparse_recovery_max": independent_recovery,
            "independent_sparse_denominator_min": float(np.min(denominator)),
        },
        "finite_differences": finite_differences,
        "tolerances": {
            "forward_and_sparse_component_recovery": 1e-10,
            "finite_difference_scaled_error_for_step_at_most_1e-4": 2e-6,
            "independent_gradient_absolute_error": 2e-7,
        },
        "artifact_sha256": {
            "solver": sha256_file(ROOT / "src" / "codonflow" / "models" / "kinetic_mean_field.py"),
            "diagnostic_script": sha256_file(__file__),
            "input_snapshot": sha256_file(snapshot),
        },
    }, arrays


def write_json_exclusive(path, payload):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    device = torch.device(args.device)
    try:
        report, arrays = validate(args.snapshot, device)
    except Exception as error:
        report = {
            "schema": SCHEMA,
            "passed": False,
            "environment": {
                "requested_device": str(device),
                "cuda_available": torch.cuda.is_available(),
            },
            "error": {"type": type(error).__name__, "message": str(error)},
            "artifact_sha256": {
                "solver": sha256_file(ROOT / "src" / "codonflow" / "models" / "kinetic_mean_field.py"),
                "diagnostic_script": sha256_file(__file__),
                "input_snapshot": sha256_file(args.snapshot),
            },
        }
        write_json_exclusive(args.output, report)
        print(json.dumps({"passed": False, "output": str(args.output)}))
        return 1
    write_json_exclusive(args.output, report)
    array_output = args.output.with_suffix(".npz")
    with array_output.open("xb") as handle:
        np.savez(handle, **arrays)
    report["output_sha256"] = sha256_file(args.output)
    report["array_output_sha256"] = sha256_file(array_output)
    print(json.dumps({
        "passed": report["passed"],
        "output": str(args.output),
        "output_sha256": report["output_sha256"],
        "array_output": str(array_output),
        "array_output_sha256": report["array_output_sha256"],
    }))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
