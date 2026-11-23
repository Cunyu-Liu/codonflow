"""Differentiable steady states for the deterministic kinetic mean-field system.

For densities ``rho[0:L]`` and flux ``J``, the solved equations are
``alpha * (1 - rho[0]) = J``, ``k[i] * rho[i] * (1 - rho[i + 1]) = J``
for ``i = 0..L-2``, and ``beta * rho[L-1] = J``.  This is an algebraic
mean-field model, not an exact stochastic simulation.
"""
from __future__ import annotations

import math

import numpy as np
import torch
from scipy.optimize import root


def _residual_numpy(
    state: np.ndarray, alpha: float, rates: np.ndarray, beta: float
) -> np.ndarray:
    rho = state[:-1]
    flux = state[-1]
    residual = np.empty_like(state)
    residual[0] = alpha * (1.0 - rho[0]) - flux
    residual[1:-1] = rates * rho[:-1] * (1.0 - rho[1:]) - flux
    residual[-1] = beta * rho[-1] - flux
    return residual


def _jacobian_numpy(
    state: np.ndarray, alpha: float, rates: np.ndarray, beta: float
) -> np.ndarray:
    rho = state[:-1]
    length = rho.size
    jacobian = np.zeros((length + 1, length + 1), dtype=np.float64)
    jacobian[0, 0] = -alpha
    if rates.size:
        rows = np.arange(1, length)
        jacobian[rows, rows - 1] = rates * (1.0 - rho[1:])
        jacobian[rows, rows] = -rates * rho[:-1]
    jacobian[-1, -2] = beta
    jacobian[:, -1] = -1.0
    return jacobian


def _validate_rate(name: str, value) -> torch.Tensor:
    if isinstance(value, torch.Tensor):
        if value.is_complex():
            raise ValueError(f"{name} must be real")
    elif np.iscomplexobj(value):
        raise ValueError(f"{name} must be real")
    try:
        tensor = torch.as_tensor(value, dtype=torch.float64)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a real numeric tensor") from error
    return tensor


def _validate_inputs(alpha, k, beta) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    alpha = _validate_rate("alpha", alpha)
    k = _validate_rate("k", k)
    beta = _validate_rate("beta", beta)
    if alpha.ndim != 0 or beta.ndim != 0:
        raise ValueError("alpha and beta must be scalars")
    if k.ndim != 1:
        raise ValueError("k must be a one-dimensional sequence of internal rates")
    if alpha.device != k.device or alpha.device != beta.device:
        raise ValueError("alpha, k, and beta must be on the same device")
    for name, tensor in (("alpha", alpha), ("k", k), ("beta", beta)):
        if not bool(torch.isfinite(tensor).all()) or not bool((tensor > 0).all()):
            raise ValueError(f"{name} must contain only finite, strictly positive rates")
    return alpha, k, beta


class _KineticMeanFieldFunction(torch.autograd.Function):
    @staticmethod
    def forward(ctx, alpha, k, beta, root_tolerance, residual_tolerance, maxfev):
        alpha_numpy = float(alpha.detach().cpu())
        k_numpy = k.detach().cpu().numpy()
        beta_numpy = float(beta.detach().cpu())
        length = k_numpy.size + 1
        if length == 1:
            initial_rho = np.array([alpha_numpy / (alpha_numpy + beta_numpy)])
            initial_flux = alpha_numpy * beta_numpy / (alpha_numpy + beta_numpy)
        else:
            initial_flux = min(alpha_numpy, beta_numpy, float(k_numpy.min())) / 4.0
            initial_rho = np.linspace(
                1.0 - initial_flux / alpha_numpy,
                initial_flux / beta_numpy,
                length,
            )
        initial = np.concatenate((initial_rho, [initial_flux]))
        result = root(
            _residual_numpy,
            initial,
            args=(alpha_numpy, k_numpy, beta_numpy),
            jac=_jacobian_numpy,
            method="hybr",
            options={"xtol": root_tolerance, "maxfev": maxfev},
        )
        if not result.success:
            raise RuntimeError(f"Kinetic mean-field root solve did not converge: {result.message}")

        state = np.asarray(result.x, dtype=np.float64)
        if state.shape != initial.shape or not np.all(np.isfinite(state)):
            raise RuntimeError("Kinetic mean-field root solve returned a non-finite state")
        rho = state[:-1]
        if np.any(rho < -1e-10) or np.any(rho > 1.0 + 1e-10):
            raise RuntimeError("Kinetic mean-field root solve returned densities outside [0, 1]")
        state[:-1] = np.clip(rho, 0.0, 1.0)
        flux = state[-1]
        if not math.isfinite(flux) or flux <= 0.0:
            raise RuntimeError("Kinetic mean-field root solve returned a non-positive flux")

        residual = _residual_numpy(state, alpha_numpy, k_numpy, beta_numpy) / flux
        if not np.all(np.isfinite(residual)):
            raise RuntimeError("Kinetic mean-field normalized residual is non-finite")
        if np.max(np.abs(residual)) > residual_tolerance:
            raise RuntimeError(
                "Kinetic mean-field root solve exceeded the normalized residual tolerance: "
                f"{np.max(np.abs(residual)):.3e} > {residual_tolerance:.3e}"
            )

        rho_tensor = alpha.new_tensor(state[:-1])
        flux_tensor = alpha.new_tensor(state[-1])
        residual_tensor = alpha.new_tensor(residual)
        ctx.save_for_backward(alpha, k, beta, rho_tensor)
        ctx.mark_non_differentiable(residual_tensor)
        return rho_tensor, flux_tensor, residual_tensor

    @staticmethod
    def backward(ctx, grad_rho, grad_flux, grad_residual):
        del grad_residual
        alpha, k, beta, rho = ctx.saved_tensors
        length = rho.numel()
        jacobian = rho.new_zeros((length + 1, length + 1))
        jacobian[0, 0] = -alpha
        if k.numel():
            rows = torch.arange(1, length, device=rho.device)
            jacobian[rows, rows - 1] = k * (1.0 - rho[1:])
            jacobian[rows, rows] = -k * rho[:-1]
        jacobian[-1, -2] = beta
        jacobian[:, -1] = -1.0

        if grad_rho is None:
            grad_rho = torch.zeros_like(rho)
        if grad_flux is None:
            grad_flux = torch.zeros_like(alpha)
        output_gradient = torch.cat((grad_rho, grad_flux.reshape(1)))
        multiplier = torch.linalg.solve(jacobian.transpose(0, 1), output_gradient)
        grad_alpha = -multiplier[0] * (1.0 - rho[0])
        grad_k = -multiplier[1:-1] * rho[:-1] * (1.0 - rho[1:])
        grad_beta = -multiplier[-1] * rho[-1]
        return grad_alpha, grad_k, grad_beta, None, None, None


def solve_kinetic_mean_field(
    alpha,
    k,
    beta,
    *,
    root_tolerance: float = 1e-12,
    residual_tolerance: float = 1e-10,
    maxfev: int = 1000,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Solve one mean-field steady state and return ``rho, J, residual / J``.

    ``k`` contains the ``L - 1`` internal rates and may be empty when ``L=1``.
    All computations use float64.  The forward solve uses SciPy with an analytic
    Jacobian; PyTorch gradients for ``rho`` and ``J`` use implicit differentiation.
    The normalized residual is a non-differentiable convergence diagnostic.
    Root failures, excessive residuals, and states outside physical bounds raise
    an exception instead of returning an unconverged result.
    """
    alpha, k, beta = _validate_inputs(alpha, k, beta)
    if not math.isfinite(root_tolerance) or root_tolerance <= 0:
        raise ValueError("root_tolerance must be finite and positive")
    if not math.isfinite(residual_tolerance) or residual_tolerance <= 0:
        raise ValueError("residual_tolerance must be finite and positive")
    if isinstance(maxfev, bool) or not isinstance(maxfev, int) or maxfev < 1:
        raise ValueError("maxfev must be a positive integer")
    return _KineticMeanFieldFunction.apply(
        alpha, k, beta, root_tolerance, residual_tolerance, maxfev
    )
