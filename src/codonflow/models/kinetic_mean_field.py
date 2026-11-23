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


def _validate_batch_inputs(alpha, k, lengths, beta):
    alpha = _validate_rate("alpha", alpha)
    k = _validate_rate("k", k)
    beta = _validate_rate("beta", beta)
    if alpha.ndim != 1 or beta.ndim != 1:
        raise ValueError("alpha and beta must be one-dimensional batch vectors")
    if k.ndim != 2:
        raise ValueError("k must be a two-dimensional padded batch of internal rates")
    batch_size = alpha.numel()
    if batch_size == 0:
        raise ValueError("the batch must contain at least one sample")
    if beta.shape != alpha.shape or k.shape[0] != batch_size:
        raise ValueError("alpha, k, and beta must have the same batch size")
    if alpha.device != k.device or alpha.device != beta.device:
        raise ValueError("alpha, k, and beta must be on the same device")

    try:
        lengths_tensor = torch.as_tensor(lengths)
    except (TypeError, ValueError) as error:
        raise ValueError("lengths must be a one-dimensional integer sequence") from error
    if lengths_tensor.ndim != 1 or lengths_tensor.numel() != batch_size:
        raise ValueError("lengths must contain one integer per batch sample")
    if lengths_tensor.dtype == torch.bool or lengths_tensor.is_floating_point() or lengths_tensor.is_complex():
        raise ValueError("lengths must contain integers")
    if isinstance(lengths, torch.Tensor) and lengths.device != alpha.device:
        raise ValueError("lengths must be on the same device as alpha, k, and beta")
    lengths_tensor = lengths_tensor.to(device=alpha.device, dtype=torch.int64)

    max_length = k.shape[1] + 1
    if bool((lengths_tensor < 1).any()) or bool((lengths_tensor > max_length).any()):
        raise ValueError(f"lengths must be between 1 and {max_length}")
    if int(lengths_tensor.max()) != max_length:
        raise ValueError("max(lengths) must equal k.shape[1] + 1")
    for name, tensor in (("alpha", alpha), ("beta", beta)):
        if not bool(torch.isfinite(tensor).all()) or not bool((tensor > 0).all()):
            raise ValueError(f"{name} must contain only finite, strictly positive rates")
    if not bool(torch.isfinite(k).all()):
        raise ValueError("k must contain only finite rates")
    internal_positions = torch.arange(k.shape[1], device=k.device)
    valid_k = internal_positions.unsqueeze(0) < (lengths_tensor - 1).unsqueeze(1)
    if not bool((k[valid_k] > 0).all()):
        raise ValueError("k must contain strictly positive rates at positions selected by lengths")
    return alpha, k, lengths_tensor, beta


def _validate_solver_controls(root_tolerance, residual_tolerance, maxfev):
    if not math.isfinite(root_tolerance) or root_tolerance <= 0:
        raise ValueError("root_tolerance must be finite and positive")
    if not math.isfinite(residual_tolerance) or residual_tolerance <= 0:
        raise ValueError("residual_tolerance must be finite and positive")
    if isinstance(maxfev, bool) or not isinstance(maxfev, int) or maxfev < 1:
        raise ValueError("maxfev must be a positive integer")


def _jacobian_condition_number(state, alpha, rates, beta) -> float:
    condition = float(np.linalg.cond(_jacobian_numpy(state, alpha, rates, beta)))
    if not math.isfinite(condition) or condition <= 0.0:
        raise RuntimeError("Kinetic mean-field Jacobian condition number is non-finite")
    return condition


def _solve_adjoint_system(jacobian, output_gradient, residual_tolerance, diagnostics):
    matrix = jacobian.transpose(-1, -2)
    row_scale = matrix.abs().amax(dim=-1, keepdim=True)
    if not bool(torch.isfinite(row_scale).all()) or not bool((row_scale > 0).all()):
        raise RuntimeError("Kinetic mean-field backward Jacobian has invalid row scales")
    multiplier = torch.linalg.solve(
        matrix / row_scale, output_gradient.unsqueeze(-1) / row_scale
    ).squeeze(-1)
    recovery = torch.matmul(matrix, multiplier.unsqueeze(-1)).squeeze(-1) - output_gradient
    denominator = (
        torch.matmul(matrix.abs(), multiplier.abs().unsqueeze(-1)).squeeze(-1)
        + output_gradient.abs()
    )
    relative_recovery = torch.where(
        denominator > 0, recovery.abs() / denominator, recovery.abs()
    )
    if relative_recovery.ndim == 1:
        reported_recovery = relative_recovery.max()
    else:
        reported_recovery = relative_recovery.amax(dim=-1)
    if diagnostics is not None:
        diagnostics["backward_recovery_residual"].copy_(reported_recovery)
    if not bool(torch.isfinite(multiplier).all()) or not bool(
        torch.isfinite(reported_recovery).all()
    ):
        raise RuntimeError("Kinetic mean-field backward solve returned non-finite values")
    if bool((reported_recovery > residual_tolerance).any()):
        if relative_recovery.ndim == 1:
            detail = f"{float(reported_recovery):.3e}"
        else:
            index = int((reported_recovery > residual_tolerance).nonzero()[0, 0])
            detail = f"batch sample {index}: {float(reported_recovery[index]):.3e}"
        raise RuntimeError(
            "Kinetic mean-field backward solve exceeded the recovery residual tolerance: "
            f"{detail} > {residual_tolerance:.3e}"
        )
    return multiplier


def _scaled_residual_numpy(
    state: np.ndarray, alpha: float, rates: np.ndarray, beta: float, flux_scale: float
) -> np.ndarray:
    rho = state[:-1]
    scaled_flux = state[-1]
    residual = np.empty_like(state)
    residual[0] = 1.0 - rho[0] - scaled_flux * flux_scale / alpha
    residual[1:-1] = (
        rho[:-1] * (1.0 - rho[1:]) - scaled_flux * flux_scale / rates
    )
    residual[-1] = rho[-1] - scaled_flux * flux_scale / beta
    return residual


def _scaled_jacobian_numpy(
    state: np.ndarray, alpha: float, rates: np.ndarray, beta: float, flux_scale: float
) -> np.ndarray:
    rho = state[:-1]
    length = rho.size
    jacobian = np.zeros((length + 1, length + 1), dtype=np.float64)
    jacobian[0, 0] = -1.0
    if rates.size:
        rows = np.arange(1, length)
        jacobian[rows, rows - 1] = 1.0 - rho[1:]
        jacobian[rows, rows] = -rho[:-1]
    jacobian[-1, -2] = 1.0
    jacobian[:, -1] = -flux_scale / np.concatenate(([alpha], rates, [beta]))
    return jacobian


def _checked_root_state(result, state, initial_shape, alpha, rates, beta, residual_tolerance):
    if not result.success:
        raise RuntimeError(f"Kinetic mean-field root solve did not converge: {result.message}")

    state = np.asarray(state, dtype=np.float64).copy()
    if state.shape != initial_shape or not np.all(np.isfinite(state)):
        raise RuntimeError("Kinetic mean-field root solve returned a non-finite state")
    rho = state[:-1]
    if np.any(rho < -1e-10) or np.any(rho > 1.0 + 1e-10):
        raise RuntimeError("Kinetic mean-field root solve returned densities outside [0, 1]")
    state[:-1] = np.clip(rho, 0.0, 1.0)
    flux = state[-1]
    if not math.isfinite(flux) or flux <= 0.0:
        raise RuntimeError("Kinetic mean-field root solve returned a non-positive flux")

    residual = _residual_numpy(state, alpha, rates, beta) / flux
    if not np.all(np.isfinite(residual)):
        raise RuntimeError("Kinetic mean-field normalized residual is non-finite")
    if np.max(np.abs(residual)) > residual_tolerance:
        raise RuntimeError(
            "Kinetic mean-field root solve exceeded the normalized residual tolerance: "
            f"{np.max(np.abs(residual)):.3e} > {residual_tolerance:.3e}"
        )
    return state, residual


def _solve_state_numpy(
    alpha: float,
    rates: np.ndarray,
    beta: float,
    root_tolerance: float,
    residual_tolerance: float,
    maxfev: int,
) -> tuple[np.ndarray, np.ndarray]:
    length = rates.size + 1
    flux_scale = min(alpha, beta) if length == 1 else min(alpha, beta, float(rates.min()))
    if length == 1:
        initial_rho = np.array([alpha / (alpha + beta)])
        initial_flux = alpha * beta / (alpha + beta)
    else:
        initial_flux = flux_scale / 4.0
        initial_rho = np.linspace(
            1.0 - initial_flux / alpha,
            initial_flux / beta,
            length,
        )
    initial = np.concatenate((initial_rho, [initial_flux]))
    result = root(
        _residual_numpy,
        initial,
        args=(alpha, rates, beta),
        jac=_jacobian_numpy,
        method="hybr",
        options={"xtol": root_tolerance, "maxfev": maxfev},
    )
    try:
        return _checked_root_state(
            result, result.x, initial.shape, alpha, rates, beta, residual_tolerance
        )
    except RuntimeError as original_error:
        scaled_initial = initial.copy()
        scaled_initial[-1] /= flux_scale
        scaled_result = root(
            _scaled_residual_numpy,
            scaled_initial,
            args=(alpha, rates, beta, flux_scale),
            jac=_scaled_jacobian_numpy,
            method="hybr",
            options={"xtol": root_tolerance, "maxfev": maxfev},
        )
        try:
            scaled_state = np.asarray(scaled_result.x, dtype=np.float64).copy()
            if scaled_state.shape == initial.shape:
                scaled_state[-1] *= flux_scale
            return _checked_root_state(
                scaled_result,
                scaled_state,
                initial.shape,
                alpha,
                rates,
                beta,
                residual_tolerance,
            )
        except RuntimeError as scaled_error:
            raise scaled_error from original_error


class _KineticMeanFieldFunction(torch.autograd.Function):
    @staticmethod
    def forward(
        ctx, alpha, k, beta, root_tolerance, residual_tolerance, maxfev, diagnostics
    ):
        alpha_numpy = float(alpha.detach().cpu())
        k_numpy = k.detach().cpu().numpy()
        beta_numpy = float(beta.detach().cpu())
        state, residual = _solve_state_numpy(
            alpha_numpy,
            k_numpy,
            beta_numpy,
            root_tolerance,
            residual_tolerance,
            maxfev,
        )
        rho_tensor = alpha.new_tensor(state[:-1])
        flux_tensor = alpha.new_tensor(state[-1])
        residual_tensor = alpha.new_tensor(residual)
        if diagnostics is not None:
            diagnostics["jacobian_condition_number"] = alpha.new_tensor(
                _jacobian_condition_number(state, alpha_numpy, k_numpy, beta_numpy)
            )
            diagnostics["backward_recovery_residual"] = alpha.new_tensor(float("nan"))
        ctx.save_for_backward(alpha, k, beta, rho_tensor)
        ctx.residual_tolerance = residual_tolerance
        ctx.diagnostics = diagnostics
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
        multiplier = _solve_adjoint_system(
            jacobian, output_gradient, ctx.residual_tolerance, ctx.diagnostics
        )
        grad_alpha = -multiplier[0] * (1.0 - rho[0])
        grad_k = -multiplier[1:-1] * rho[:-1] * (1.0 - rho[1:])
        grad_beta = -multiplier[-1] * rho[-1]
        return grad_alpha, grad_k, grad_beta, None, None, None, None


class _KineticMeanFieldBatchFunction(torch.autograd.Function):
    @staticmethod
    def forward(
        ctx, alpha, k, lengths, beta, root_tolerance, residual_tolerance, maxfev, diagnostics
    ):
        batch_size, max_internal = k.shape
        max_length = max_internal + 1
        rho_tensor = alpha.new_zeros((batch_size, max_length))
        flux_tensor = alpha.new_zeros(batch_size)
        residual_tensor = alpha.new_zeros((batch_size, max_length + 1))
        alpha_numpy = alpha.detach().cpu().numpy()
        k_numpy = k.detach().cpu().numpy()
        beta_numpy = beta.detach().cpu().numpy()
        lengths_list = lengths.detach().cpu().tolist()
        condition_numbers = []
        for index, length in enumerate(lengths_list):
            sample_alpha = float(alpha_numpy[index])
            sample_k = k_numpy[index, : length - 1]
            sample_beta = float(beta_numpy[index])
            try:
                state, residual = _solve_state_numpy(
                    sample_alpha,
                    sample_k,
                    sample_beta,
                    root_tolerance,
                    residual_tolerance,
                    maxfev,
                )
            except RuntimeError as error:
                raise RuntimeError(f"Kinetic mean-field batch sample {index} failed: {error}") from error
            rho_tensor[index, :length] = alpha.new_tensor(state[:-1])
            flux_tensor[index] = float(state[-1])
            residual_tensor[index, : length + 1] = alpha.new_tensor(residual)
            if diagnostics is not None:
                condition_numbers.append(
                    _jacobian_condition_number(state, sample_alpha, sample_k, sample_beta)
                )

        if diagnostics is not None:
            diagnostics["jacobian_condition_number"] = alpha.new_tensor(condition_numbers)
            diagnostics["backward_recovery_residual"] = alpha.new_full(
                (batch_size,), float("nan")
            )
        ctx.save_for_backward(alpha, k, lengths, beta, rho_tensor)
        ctx.residual_tolerance = residual_tolerance
        ctx.diagnostics = diagnostics
        ctx.mark_non_differentiable(residual_tensor)
        return rho_tensor, flux_tensor, residual_tensor

    @staticmethod
    def backward(ctx, grad_rho, grad_flux, grad_residual):
        del grad_residual
        alpha, k, lengths, beta, rho = ctx.saved_tensors
        batch_size, max_length = rho.shape
        jacobian = torch.eye(
            max_length + 1, dtype=rho.dtype, device=rho.device
        ).expand(batch_size, -1, -1).clone()
        lengths_list = lengths.detach().cpu().tolist()
        for index, length in enumerate(lengths_list):
            sample_k = k[index, : length - 1]
            sample_rho = rho[index, :length]
            jacobian[index, 0, 0] = -alpha[index]
            if length > 1:
                rows = torch.arange(1, length, device=rho.device)
                jacobian[index, rows, rows - 1] = sample_k * (1.0 - sample_rho[1:])
                jacobian[index, rows, rows] = -sample_k * sample_rho[:-1]
            jacobian[index, length, length - 1] = beta[index]
            jacobian[index, : length + 1, length] = -1.0

        if grad_rho is None:
            grad_rho = torch.zeros_like(rho)
        if grad_flux is None:
            grad_flux = torch.zeros_like(alpha)
        batch_indices = torch.arange(batch_size, device=rho.device)
        output_gradient = rho.new_zeros((batch_size, max_length + 1))
        output_gradient[:, :max_length] = grad_rho
        output_gradient[batch_indices, lengths] = grad_flux
        multiplier = _solve_adjoint_system(
            jacobian, output_gradient, ctx.residual_tolerance, ctx.diagnostics
        )
        grad_alpha = -multiplier[:, 0] * (1.0 - rho[:, 0])
        grad_beta = -multiplier[batch_indices, lengths] * rho[batch_indices, lengths - 1]
        grad_k = torch.zeros_like(k)
        for index, length in enumerate(lengths_list):
            if length > 1:
                sample_rho = rho[index, :length]
                grad_k[index, : length - 1] = (
                    -multiplier[index, 1:length]
                    * sample_rho[:-1]
                    * (1.0 - sample_rho[1:])
                )
        return grad_alpha, grad_k, None, grad_beta, None, None, None, None


def solve_kinetic_mean_field(
    alpha,
    k,
    beta,
    *,
    root_tolerance: float = 1e-12,
    residual_tolerance: float = 1e-10,
    maxfev: int = 1000,
    return_diagnostics: bool = False,
):
    """Solve one mean-field steady state and return ``rho, J, residual / J``.

    ``k`` contains the ``L - 1`` internal rates and may be empty when ``L=1``.
    All computations use float64.  The forward solve uses SciPy with an analytic
    Jacobian; PyTorch gradients for ``rho`` and ``J`` use implicit differentiation.
    The normalized residual is a non-differentiable convergence diagnostic.
    Root failures, excessive residuals, and states outside physical bounds raise
    an exception instead of returning an unconverged result.

    With ``return_diagnostics=True``, a fourth return value contains the Jacobian
    condition number and the relative backward recovery residual.  The latter is
    NaN until backward runs.  Backward always checks this residual against
    ``residual_tolerance`` and raises on failure, including for legacy three-output
    calls.
    """
    alpha, k, beta = _validate_inputs(alpha, k, beta)
    _validate_solver_controls(root_tolerance, residual_tolerance, maxfev)
    diagnostics = {} if return_diagnostics else None
    outputs = _KineticMeanFieldFunction.apply(
        alpha, k, beta, root_tolerance, residual_tolerance, maxfev, diagnostics
    )
    if return_diagnostics:
        return *outputs, diagnostics
    return outputs


def solve_kinetic_mean_field_batch(
    alpha,
    k,
    lengths,
    beta,
    *,
    root_tolerance: float = 1e-12,
    residual_tolerance: float = 1e-10,
    maxfev: int = 1000,
    return_diagnostics: bool = False,
):
    """Solve a padded batch and return ``rho, J, residual / J``.

    ``alpha`` and ``beta`` have shape ``[B]``. ``k`` has shape ``[B, L-1]``
    and ``lengths`` has shape ``[B]``, where ``L = max(lengths)``. Row ``b``
    uses ``k[b, :lengths[b]-1]``; later columns are padding. Outputs have
    shapes ``[B, L]``, ``[B]``, and ``[B, L+1]`` respectively, with zero-filled
    padding. Valid internal rates must be finite and strictly positive, while
    padding may be zero but must be finite.

    Each forward sample is solved independently by the same strict SciPy root
    solve as :func:`solve_kinetic_mean_field`. Gradients for ``rho`` and ``J``
    use one batched implicit solve over the per-sample block Jacobians.
    Gradients through ``lengths`` and the normalized residual are not defined.
    ``return_diagnostics=True`` adds a dictionary with per-sample Jacobian
    condition numbers and backward recovery residuals, on the requested device.
    Recovery residuals are NaN until backward runs and are always checked against
    ``residual_tolerance``, including for legacy three-output calls.
    """
    alpha, k, lengths, beta = _validate_batch_inputs(alpha, k, lengths, beta)
    _validate_solver_controls(root_tolerance, residual_tolerance, maxfev)
    diagnostics = {} if return_diagnostics else None
    outputs = _KineticMeanFieldBatchFunction.apply(
        alpha, k, lengths, beta, root_tolerance, residual_tolerance, maxfev, diagnostics
    )
    if return_diagnostics:
        return *outputs, diagnostics
    return outputs
