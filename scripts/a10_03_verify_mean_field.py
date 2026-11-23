#!/usr/bin/env python3
"""Audit the A10-03 mean-field solver with independent SciPy recomputation."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
import scipy
import torch
from scipy import optimize

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from codonflow.models.kinetic_mean_field import solve_kinetic_mean_field

SCHEMA = "a10-03-mean-field-independent-audit-v1"
SOLUTION_TOL = 2e-7
RESIDUAL_TOL = 2e-7
GRADIENT_TOL = 2e-6


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def case_specs():
    return [
        {"name": "single_site_equal", "alpha": 2.0, "k": [], "beta": 2.0},
        {"name": "four_site_equal", "alpha": 0.7, "k": [0.7] * 3, "beta": 0.7},
        {"name": "three_site_heterogeneous", "alpha": 1.2, "k": [0.8, 1.7], "beta": 0.65},
        {
            "name": "six_site_heterogeneous",
            "alpha": 0.4,
            "k": [1.3, 0.6, 2.1, 0.9, 1.1],
            "beta": 1.8,
        },
        {"name": "two_site_scaled_equal", "alpha": 3.2, "k": [3.2], "beta": 3.2},
    ]


def independent_residual_jacobian(state, alpha, k, beta):
    length = k.size + 1
    rho = state[:length]
    local_flux = np.concatenate((
        [alpha * (1.0 - rho[0])],
        k * rho[:-1] * (1.0 - rho[1:]),
        [beta * rho[-1]],
    ))
    residual = local_flux - state[-1]
    jacobian = np.zeros((length + 1, length + 1), dtype=np.float64)
    jacobian[:, -1] = -1.0
    jacobian[0, 0] = -alpha
    if length > 1:
        indices = np.arange(length - 1)
        jacobian[indices + 1, indices] = k * (1.0 - rho[1:])
        jacobian[indices + 1, indices + 1] = -k * rho[:-1]
    jacobian[-1, -2] = beta
    return residual, jacobian, local_flux


def independent_least_squares(alpha, k, beta):
    k = np.asarray(k, dtype=np.float64)
    length = k.size + 1
    initial_rho = np.linspace(0.35, 0.65, length)
    initial_flux = 0.1 * min(alpha, beta, *(k.tolist() if k.size else []))
    initial = np.concatenate((initial_rho, [initial_flux]))

    def residual(state):
        return independent_residual_jacobian(state, alpha, k, beta)[0]

    def jacobian(state):
        return independent_residual_jacobian(state, alpha, k, beta)[1]

    result = optimize.least_squares(
        residual,
        initial,
        jac=jacobian,
        bounds=(np.zeros(length + 1), np.concatenate((np.ones(length), [np.inf]))),
        method="trf",
        ftol=1e-13,
        xtol=1e-13,
        gtol=1e-13,
        max_nfev=1000,
    )
    if not result.success:
        raise RuntimeError(f"independent least_squares did not converge: {result.message}")
    state = np.asarray(result.x, dtype=np.float64)
    if not np.all(np.isfinite(state)):
        raise RuntimeError("independent least_squares returned non-finite values")
    residual_values, jacobian_values, local_flux = independent_residual_jacobian(
        state, alpha, k, beta,
    )
    if state[-1] <= 0.0 or np.any(state[:-1] < 0.0) or np.any(state[:-1] > 1.0):
        raise RuntimeError("independent least_squares left the physical domain")
    relative_residual = residual_values / state[-1]
    if np.max(np.abs(relative_residual)) > RESIDUAL_TOL:
        raise RuntimeError("independent least_squares failed its relative residual check")
    return {
        "state": state,
        "relative_residual": relative_residual,
        "local_flux": local_flux,
        "jacobian": jacobian_values,
        "message": str(result.message),
        "nfev": int(result.nfev),
    }


def objective_weights(length):
    return np.linspace(0.3, 0.9, length), 0.7


def independent_gradients(state, jacobian, k):
    length = k.size + 1
    rho = state[:length]
    rho_weights, flux_weight = objective_weights(length)
    adjoint = np.linalg.solve(
        jacobian.T, np.concatenate((rho_weights, [flux_weight])),
    )
    return np.concatenate((
        [-adjoint[0] * (1.0 - rho[0])],
        -adjoint[1:length] * rho[:-1] * (1.0 - rho[1:]),
        [-adjoint[length] * rho[-1]],
    ))


def production_values(spec, device):
    alpha = torch.tensor(spec["alpha"], dtype=torch.float64, device=device, requires_grad=True)
    k = torch.tensor(spec["k"], dtype=torch.float64, device=device, requires_grad=True)
    beta = torch.tensor(spec["beta"], dtype=torch.float64, device=device, requires_grad=True)
    rho, flux, relative_residual = solve_kinetic_mean_field(alpha, k, beta)
    rho_weights, flux_weight = objective_weights(k.numel() + 1)
    weights = torch.as_tensor(rho_weights, dtype=torch.float64, device=device)
    objective = torch.dot(weights, rho) + flux_weight * flux
    objective.backward()
    if any(value.device != device for value in (rho, flux, alpha.grad, k.grad, beta.grad)):
        raise RuntimeError("production forward/backward left the explicitly requested device")
    gradients = torch.cat((alpha.grad.reshape(1), k.grad, beta.grad.reshape(1)))
    return {
        "rho": rho.detach().cpu().numpy(),
        "J": float(flux.detach().cpu()),
        "relative_residual": relative_residual.detach().cpu().numpy(),
        "gradients": gradients.detach().cpu().numpy(),
    }


def max_difference(left, right):
    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    if left.shape != right.shape:
        raise ValueError(f"comparison shape mismatch: {left.shape} versus {right.shape}")
    return float(np.max(np.abs(left - right))) if left.size else 0.0


def audit_case(spec, device):
    alpha = float(spec["alpha"])
    k = np.asarray(spec["k"], dtype=np.float64)
    beta = float(spec["beta"])
    production = production_values(spec, device)
    independent = independent_least_squares(alpha, k, beta)
    independent_gradient = independent_gradients(
        independent["state"], independent["jacobian"], k,
    )
    independent_rho = independent["state"][:-1]
    independent_flux = float(independent["state"][-1])
    production_conservation = np.concatenate((
        [alpha * (1.0 - production["rho"][0])],
        k * production["rho"][:-1] * (1.0 - production["rho"][1:]),
        [beta * production["rho"][-1]],
    ))
    errors = {
        "rho": max_difference(production["rho"], independent_rho),
        "J": abs(production["J"] - independent_flux),
        "relative_residual": max_difference(
            production["relative_residual"], independent["relative_residual"],
        ),
        "gradient": max_difference(production["gradients"], independent_gradient),
        "production_max_abs_residual_over_J": float(np.max(np.abs(
            production["relative_residual"],
        ))),
        "independent_max_abs_residual_over_J": float(np.max(np.abs(
            independent["relative_residual"],
        ))),
        "production_conservation": max_difference(
            production_conservation, np.full(k.size + 2, production["J"]),
        ) / production["J"],
        "independent_conservation": max_difference(
            independent["local_flux"], np.full(k.size + 2, independent_flux),
        ) / independent_flux,
    }
    passed = (
        errors["rho"] <= SOLUTION_TOL
        and errors["J"] <= SOLUTION_TOL
        and errors["relative_residual"] <= RESIDUAL_TOL
        and errors["gradient"] <= GRADIENT_TOL
        and errors["production_max_abs_residual_over_J"] <= RESIDUAL_TOL
        and errors["independent_max_abs_residual_over_J"] <= RESIDUAL_TOL
        and errors["production_conservation"] <= RESIDUAL_TOL
        and errors["independent_conservation"] <= RESIDUAL_TOL
    )
    return {
        "name": spec["name"],
        "input": spec,
        "production": {
            "rho": production["rho"].tolist(),
            "J": production["J"],
            "relative_residual": production["relative_residual"].tolist(),
            "objective_gradients_alpha_k_beta": production["gradients"].tolist(),
        },
        "independent_least_squares": {
            "rho": independent_rho.tolist(),
            "J": independent_flux,
            "relative_residual": independent["relative_residual"].tolist(),
            "local_flux": independent["local_flux"].tolist(),
            "objective_gradients_alpha_k_beta": independent_gradient.tolist(),
            "nfev": independent["nfev"],
            "message": independent["message"],
        },
        "max_errors": errors,
        "passed": bool(passed),
    }


def cuda_matrix_forward_backward():
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA was explicitly requested; refusing CPU fallback")
    device = torch.device("cuda:0")
    spec = case_specs()[2]
    independent = independent_least_squares(spec["alpha"], spec["k"], spec["beta"])
    jacobian = independent["jacobian"]
    matrix = torch.as_tensor(jacobian, dtype=torch.float64, device=device).requires_grad_()
    rhs = torch.linspace(
        0.2, 1.1, jacobian.shape[0], dtype=torch.float64, device=device,
    ).requires_grad_()
    solution = torch.linalg.solve(matrix, rhs)
    loss = torch.sum(solution ** 2) + torch.sum(solution)
    loss.backward()
    torch.cuda.synchronize(device)
    if any(value.device.type != "cuda" for value in (solution, matrix.grad, rhs.grad)):
        raise RuntimeError("CUDA matrix forward/backward produced a non-CUDA result")
    solution_np = solution.detach().cpu().numpy()
    rhs_np = rhs.detach().cpu().numpy()
    expected_solution = np.linalg.solve(jacobian, rhs_np)
    adjoint = np.linalg.solve(jacobian.T, 2.0 * expected_solution + 1.0)
    expected_matrix_gradient = -np.outer(adjoint, expected_solution)
    return {
        "device": str(device),
        "operator": "torch.linalg.solve",
        "forward_and_backward_executed": True,
        "cpu_fallback": False,
        "max_errors": {
            "solution": max_difference(solution_np, expected_solution),
            "matrix_gradient": max_difference(
                matrix.grad.detach().cpu().numpy(), expected_matrix_gradient,
            ),
            "rhs_gradient": max_difference(rhs.grad.detach().cpu().numpy(), adjoint),
        },
    }


def environment(device):
    cuda = {"requested": device.type == "cuda", "available": torch.cuda.is_available()}
    if device.type == "cuda" and cuda["available"]:
        cuda.update({
            "device": str(device),
            "name": torch.cuda.get_device_name(device),
            "capability": list(torch.cuda.get_device_capability(device)),
            "torch_cuda_version": torch.version.cuda,
        })
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "torch": torch.__version__,
        "production_root_device": "cpu",
        "autograd_device": str(device),
        "cuda": cuda,
    }


def audit_mean_field(device="cpu"):
    device = torch.device(device)
    if device.type not in {"cpu", "cuda"}:
        raise ValueError("audit device must be CPU or explicit CUDA")
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was explicitly requested; refusing CPU fallback")
    cases = [audit_case(spec, device) for spec in case_specs()]
    max_errors = {
        key: max(case["max_errors"][key] for case in cases)
        for key in cases[0]["max_errors"]
    }
    gpu_validation = {"requested": False}
    if device.type == "cuda":
        gpu_validation = cuda_matrix_forward_backward()
        gpu_validation["requested"] = True
        gpu_validation["passed"] = all(
            value <= 1e-8 for value in gpu_validation["max_errors"].values()
        )
    return {
        "schema": SCHEMA,
        "passed": all(case["passed"] for case in cases) and gpu_validation.get("passed", True),
        "scope": {
            "model": "deterministic_mean_field_steady_state",
            "exact_stochastic_simulation": False,
            "training_or_generator_execution": False,
            "data_or_untouched_files_read": False,
        },
        "tolerances": {
            "solution": SOLUTION_TOL,
            "relative_residual_and_conservation": RESIDUAL_TOL,
            "gradient": GRADIENT_TOL,
        },
        "environment": environment(device),
        "cases": cases,
        "max_errors": max_errors,
        "gpu_validation": gpu_validation,
        "artifact_sha256": {
            "production_implementation": sha256_file(
                ROOT / "src" / "codonflow" / "models" / "kinetic_mean_field.py",
            ),
            "verification_script": sha256_file(__file__),
            "case_inputs": hashlib.sha256(json.dumps(
                case_specs(), sort_keys=True, allow_nan=False,
            ).encode("utf-8")).hexdigest(),
        },
    }


def write_json_exclusive(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New exclusive audit JSON")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {args.output}")
    device = torch.device("cuda:0" if args.device == "cuda" else "cpu")
    try:
        report = audit_mean_field(device)
    except Exception as error:
        report = {
            "schema": SCHEMA,
            "passed": False,
            "environment": environment(device),
            "error": {"type": type(error).__name__, "message": str(error)},
            "artifact_sha256": {
                "production_implementation": sha256_file(
                    ROOT / "src" / "codonflow" / "models" / "kinetic_mean_field.py",
                ),
                "verification_script": sha256_file(__file__),
            },
        }
    write_json_exclusive(args.output, report)
    output_sha = sha256_file(args.output)
    print(json.dumps({
        "passed": report["passed"], "output": str(args.output), "output_sha256": output_sha,
    }))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
