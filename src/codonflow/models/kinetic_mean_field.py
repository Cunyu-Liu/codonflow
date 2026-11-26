"""Differentiable steady states for the deterministic kinetic mean-field system.

For densities ``rho[0:L]`` and flux ``J``, the solved equations are
``alpha * (1 - rho[0]) = J``, ``k[i] * rho[i] * (1 - rho[i + 1]) = J``
for ``i = 0..L-2``, and ``beta * rho[L-1] = J``.  This is an algebraic
mean-field model, not an exact stochastic simulation.
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import torch
from scipy.integrate import solve_ivp
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import MatrixRankWarning, spsolve


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


_BACKWARD_LU_REFINEMENT_STEPS = 4
_BACKWARD_QR_REFINEMENT_STEPS = 4


def _extended_backward_recovery(matrix, multiplier, output_gradient):
    matrix = np.asarray(matrix.detach().cpu().numpy(), dtype=np.longdouble)
    multiplier = np.asarray(multiplier.detach().cpu().numpy(), dtype=np.longdouble)
    output_gradient = np.asarray(
        output_gradient.detach().cpu().numpy(), dtype=np.longdouble
    )
    recovery = np.matmul(matrix, multiplier) - output_gradient
    denominator = np.matmul(np.abs(matrix), np.abs(multiplier)) + np.abs(
        output_gradient
    )
    absolute_recovery = np.abs(recovery)
    relative_recovery = absolute_recovery.copy()
    np.divide(
        absolute_recovery,
        denominator,
        out=relative_recovery,
        where=denominator > 0,
    )
    return recovery, denominator, relative_recovery


def _backward_qr_solve(scaled_matrix, scaled_rhs):
    q, r = torch.linalg.qr(scaled_matrix)
    return torch.linalg.solve_triangular(r, q.transpose(0, 1) @ scaled_rhs, upper=True)


def _set_backward_diagnostic(diagnostics, name, index, value, single):
    if diagnostics is None:
        return
    target = diagnostics[name]
    if single:
        target.fill_(value)
    else:
        target[index].fill_(value)


def _backward_failure_context(
    index,
    single,
    matrix,
    output_gradient,
    multiplier,
    recovery,
    denominator,
    relative_recovery,
    refinement_steps,
    qr_fallback,
    qr_error,
    diagnostics,
):
    condition_number = None
    if diagnostics is not None and "jacobian_condition_number" in diagnostics:
        condition = diagnostics["jacobian_condition_number"]
        condition_number = float((condition if single else condition[index]).detach().cpu())
    return {
        "batch_index": None if single else int(index),
        "jacobian_transpose": matrix.detach().cpu().clone(),
        "output_gradient": output_gradient.detach().cpu().clone(),
        "multiplier": multiplier.detach().cpu().clone(),
        "recovery_extended": recovery,
        "denominator_extended": denominator,
        "relative_recovery_extended": relative_recovery,
        "jacobian_condition_number": condition_number,
        "refinement_steps": int(refinement_steps),
        "qr_fallback": bool(qr_fallback),
        "qr_error": qr_error,
    }


def _solve_adjoint_system(jacobian, output_gradient, residual_tolerance, diagnostics):
    single = jacobian.ndim == 2
    matrices = jacobian.transpose(-1, -2)
    if single:
        matrices = matrices.unsqueeze(0)
        output_gradient = output_gradient.unsqueeze(0)
    row_scale = matrices.abs().amax(dim=-1, keepdim=True)
    if not bool(torch.isfinite(row_scale).all()) or not bool((row_scale > 0).all()):
        raise RuntimeError("Kinetic mean-field backward Jacobian has invalid row scales")
    scaled_matrices = matrices / row_scale
    factor, pivots = torch.linalg.lu_factor(scaled_matrices)
    rhs = output_gradient.unsqueeze(-1) / row_scale
    multipliers = torch.linalg.lu_solve(factor, pivots, rhs).squeeze(-1)

    recovery = torch.matmul(matrices, multipliers.unsqueeze(-1)).squeeze(-1) - output_gradient
    denominator = (
        torch.matmul(matrices.abs(), multipliers.abs().unsqueeze(-1)).squeeze(-1)
        + output_gradient.abs()
    )
    relative_recovery = torch.where(
        denominator > 0, recovery.abs() / denominator, recovery.abs()
    )
    reported_recovery = relative_recovery.amax(dim=-1)
    if diagnostics is not None:
        diagnostics["backward_recovery_residual"].copy_(
            reported_recovery[0] if single else reported_recovery
        )
    failed = ~torch.isfinite(multipliers).all(dim=-1) | ~torch.isfinite(
        reported_recovery
    ) | (reported_recovery > residual_tolerance)
    if not bool(failed.any()):
        return multipliers[0] if single else multipliers

    failures = []
    for index in failed.nonzero(as_tuple=False).flatten().tolist():
        matrix = matrices[index]
        gradient = output_gradient[index]
        multiplier = multipliers[index].clone()
        refinement_steps = 0
        qr_fallback = False
        qr_error = None
        recovery_extended, denominator_extended, relative_extended = (
            _extended_backward_recovery(matrix, multiplier, gradient)
        )
        converged = bool(
            np.all(np.isfinite(multiplier.detach().cpu().numpy()))
            and np.all(np.isfinite(relative_extended))
            and np.max(relative_extended) <= residual_tolerance
        )

        while not converged and refinement_steps < _BACKWARD_LU_REFINEMENT_STEPS:
            if not np.all(np.isfinite(relative_extended)):
                break
            correction = torch.linalg.lu_solve(
                factor[index],
                pivots[index],
                torch.as_tensor(
                    recovery_extended.astype(np.float64),
                    dtype=matrix.dtype,
                    device=matrix.device,
                ).unsqueeze(-1)
                / row_scale[index],
            ).squeeze(-1)
            multiplier = multiplier - correction
            refinement_steps += 1
            recovery_extended, denominator_extended, relative_extended = (
                _extended_backward_recovery(matrix, multiplier, gradient)
            )
            converged = bool(
                np.all(np.isfinite(multiplier.detach().cpu().numpy()))
                and np.all(np.isfinite(relative_extended))
                and np.max(relative_extended) <= residual_tolerance
            )

        if not converged:
            qr_fallback = True
            try:
                multiplier = _backward_qr_solve(scaled_matrices[index], rhs[index]).squeeze(-1)
                recovery_extended, denominator_extended, relative_extended = (
                    _extended_backward_recovery(matrix, multiplier, gradient)
                )
                converged = bool(
                    np.all(np.isfinite(multiplier.detach().cpu().numpy()))
                    and np.all(np.isfinite(relative_extended))
                    and np.max(relative_extended) <= residual_tolerance
                )
                qr_steps = 0
                while not converged and qr_steps < _BACKWARD_QR_REFINEMENT_STEPS:
                    correction = _backward_qr_solve(
                        scaled_matrices[index],
                        torch.as_tensor(
                            recovery_extended.astype(np.float64),
                            dtype=matrix.dtype,
                            device=matrix.device,
                        ).unsqueeze(-1)
                        / row_scale[index],
                    ).squeeze(-1)
                    multiplier = multiplier - correction
                    refinement_steps += 1
                    qr_steps += 1
                    recovery_extended, denominator_extended, relative_extended = (
                        _extended_backward_recovery(matrix, multiplier, gradient)
                    )
                    converged = bool(
                        np.all(np.isfinite(multiplier.detach().cpu().numpy()))
                        and np.all(np.isfinite(relative_extended))
                        and np.max(relative_extended) <= residual_tolerance
                    )
            except RuntimeError as error:
                qr_error = str(error)
                converged = False

        reported = float(np.max(relative_extended))
        _set_backward_diagnostic(
            diagnostics, "backward_recovery_residual", index, reported, single
        )
        _set_backward_diagnostic(
            diagnostics, "backward_refinement_steps", index, refinement_steps, single
        )
        _set_backward_diagnostic(
            diagnostics, "backward_qr_fallback", index, qr_fallback, single
        )
        if converged:
            multipliers[index] = multiplier
        else:
            failures.append(
                _backward_failure_context(
                    index,
                    single,
                    matrix,
                    gradient,
                    multiplier,
                    recovery_extended,
                    denominator_extended,
                    relative_extended,
                    refinement_steps,
                    qr_fallback,
                    qr_error,
                    diagnostics,
                )
            )

    if not failures:
        return multipliers[0] if single else multipliers
    first = failures[0]
    first_index = first["batch_index"]
    location = "single sample" if single else f"batch sample {first_index}"
    detail = float(np.max(first["relative_recovery_extended"]))
    error = RuntimeError(
        "Kinetic mean-field backward solve exceeded the recovery residual tolerance "
        f"after {_BACKWARD_LU_REFINEMENT_STEPS} LU and "
        f"{_BACKWARD_QR_REFINEMENT_STEPS} QR refinement steps: "
        f"{location}: {detail:.3e} > {residual_tolerance:.3e}"
    )
    error.backward_failures = tuple(failures)
    error.backward_snapshot_fields = tuple(failures[0])
    raise error


def _checked_state(state, initial_shape, alpha, rates, beta, residual_tolerance):
    state = np.asarray(state, dtype=np.float64).copy()
    if state.shape != initial_shape or not np.all(np.isfinite(state)):
        raise RuntimeError("Kinetic mean-field solve returned a non-finite state")
    rho = state[:-1]
    if np.any(rho < -1e-10) or np.any(rho > 1.0 + 1e-10):
        raise RuntimeError("Kinetic mean-field solve returned densities outside [0, 1]")
    state[:-1] = np.clip(rho, 0.0, 1.0)
    flux = state[-1]
    if not math.isfinite(flux) or flux <= 0.0:
        raise RuntimeError("Kinetic mean-field solve returned a non-positive flux")

    residual = _residual_numpy(state, alpha, rates, beta) / flux
    if not np.all(np.isfinite(residual)):
        raise RuntimeError("Kinetic mean-field normalized residual is non-finite")
    if np.max(np.abs(residual)) > residual_tolerance:
        raise RuntimeError(
            "Kinetic mean-field solve exceeded the normalized residual tolerance: "
            f"{np.max(np.abs(residual)):.3e} > {residual_tolerance:.3e}"
        )
    return state, residual


def _newton_state_numpy(
    alpha,
    rates,
    beta,
    initial,
    root_tolerance,
    residual_tolerance,
    maxfev,
    normalized,
):
    length = rates.size + 1
    flux_scale = min(alpha, beta, float(rates.min(initial=math.inf)))
    all_rates = np.concatenate(([alpha], rates, [beta]))
    inverse_rates = flux_scale / all_rates
    x = np.asarray(initial, dtype=np.float64).copy()
    x[-1] /= flux_scale
    target_tolerance = 0.1 * min(root_tolerance, residual_tolerance)

    def residual_and_jacobian(state, need_jacobian):
        rho = state[:-1]
        scaled_flux = state[-1]
        flux = scaled_flux * flux_scale
        local_flux = np.empty(length + 1, dtype=np.float64)
        local_flux[0] = alpha * (1.0 - rho[0])
        local_flux[1:-1] = rates * rho[:-1] * (1.0 - rho[1:])
        local_flux[-1] = beta * rho[-1]
        if normalized:
            residual = local_flux / flux - 1.0
        else:
            residual = np.empty(length + 1, dtype=np.float64)
            residual[0] = 1.0 - rho[0] - scaled_flux * inverse_rates[0]
            residual[1:-1] = (
                rho[:-1] * (1.0 - rho[1:]) - scaled_flux * inverse_rates[1:-1]
            )
            residual[-1] = rho[-1] - scaled_flux * inverse_rates[-1]
        if not need_jacobian:
            return residual, None

        rows = [0, length]
        columns = [0, length - 1]
        if normalized:
            values = [-alpha / flux, beta / flux]
        else:
            values = [-1.0, 1.0]
        if length > 1:
            indices = np.arange(1, length)
            rows.extend(indices)
            columns.extend(indices - 1)
            rows.extend(indices)
            columns.extend(indices)
            if normalized:
                values.extend(rates * (1.0 - rho[1:]) / flux)
                values.extend(-rates * rho[:-1] / flux)
            else:
                values.extend(1.0 - rho[1:])
                values.extend(-rho[:-1])
        rows.extend(np.arange(length + 1))
        columns.extend(np.full(length + 1, length))
        if normalized:
            values.extend(-(residual + 1.0) / scaled_flux)
        else:
            values.extend(-inverse_rates)
        jacobian = coo_matrix(
            (values, (rows, columns)), shape=(length + 1, length + 1)
        ).tocsc()
        return residual, jacobian

    residual, _ = residual_and_jacobian(x, False)
    if not np.all(np.isfinite(residual)):
        raise RuntimeError("Kinetic mean-field Newton initial residual is non-finite")
    merit = float(np.dot(residual, residual))
    for iteration in range(maxfev + 1):
        if np.max(np.abs(residual)) <= target_tolerance:
            state = x.copy()
            state[-1] *= flux_scale
            return state
        if iteration == maxfev:
            break
        residual, jacobian = residual_and_jacobian(x, True)
        with warnings.catch_warnings():
            warnings.simplefilter("error", MatrixRankWarning)
            step = spsolve(jacobian, -residual)
        if not np.all(np.isfinite(step)):
            raise RuntimeError("Kinetic mean-field Newton step is non-finite")

        fraction = 1.0
        accepted = False
        for _ in range(55):
            candidate = x + fraction * step
            if (
                np.all(candidate[:-1] > 0.0)
                and np.all(candidate[:-1] < 1.0)
                and 0.0 < candidate[-1] < 1.0
            ):
                candidate_residual, _ = residual_and_jacobian(candidate, False)
                candidate_merit = float(np.dot(candidate_residual, candidate_residual))
                if np.all(np.isfinite(candidate_residual)) and (
                    candidate_merit < merit
                    or np.max(np.abs(candidate_residual)) <= target_tolerance
                ):
                    accepted = True
                    break
            fraction *= 0.5
        if not accepted:
            raise RuntimeError("Kinetic mean-field Newton line search failed")
        x = candidate
        residual = candidate_residual
        merit = candidate_merit
    raise RuntimeError(f"Kinetic mean-field Newton solve exceeded maxfev={maxfev}")


def _transient_state_numpy(
    alpha,
    rates,
    beta,
    initial,
    maxfev,
    residual_tolerance,
    root_tolerance=1e-12,
):
    length = rates.size + 1

    def derivative(_, rho):
        result = np.empty_like(rho)
        result[0] = alpha * (1.0 - rho[0]) - rates[0] * rho[0] * (1.0 - rho[1])
        result[-1] = rates[-1] * rho[-2] * (1.0 - rho[-1]) - beta * rho[-1]
        if length > 2:
            result[1:-1] = (
                rates[:-1] * rho[:-2] * (1.0 - rho[1:-1])
                - rates[1:] * rho[1:-1] * (1.0 - rho[2:])
            )
        return result

    minimum_rate = min(alpha, beta, float(rates.min(initial=math.inf)))
    end_time = max(100.0, 100.0 / minimum_rate)
    state = np.clip(initial, 1e-10, 1.0 - 1e-10)
    last_error = None
    for _ in range(10):
        result = solve_ivp(
            derivative,
            (0.0, end_time),
            state,
            method="LSODA",
            rtol=1e-8,
            atol=1e-10,
            jac=None,
            lband=1,
            uband=1,
            max_step=math.inf,
        )
        if not result.success or not np.all(np.isfinite(result.y)):
            raise RuntimeError(f"transient mean-field integration failed: {result.message}")
        state = result.y[:, -1]
        flux = alpha * (1.0 - state[0])
        candidate = np.concatenate((state, [flux]))
        try:
            return _checked_state(
                candidate, candidate.shape, alpha, rates, beta, residual_tolerance
            )[0]
        except RuntimeError as error:
            last_error = error
        try:
            polished = _newton_state_numpy(
                alpha,
                rates,
                beta,
                candidate,
                root_tolerance,
                residual_tolerance,
                maxfev,
                normalized=True,
            )
            return _checked_state(
                polished, candidate.shape, alpha, rates, beta, residual_tolerance
            )[0]
        except (RuntimeError, ValueError) as error:
            last_error = error
        state = np.clip(state, 1e-10, 1.0 - 1e-10)
        end_time *= 10.0
    raise RuntimeError(f"transient/Newton mean-field solve failed: {last_error}")


def _solve_state_numpy(
    alpha: float,
    rates: np.ndarray,
    beta: float,
    root_tolerance: float,
    residual_tolerance: float,
    maxfev: int,
) -> tuple[np.ndarray, np.ndarray]:
    length = rates.size + 1
    flux_scale = min(alpha, beta, float(rates.min(initial=math.inf)))
    if length == 1:
        initial_rho = np.array([alpha / (alpha + beta)])
        initial_flux = alpha * beta / (alpha + beta)
        initial = np.concatenate((initial_rho, [initial_flux]))
        return _checked_state(
            initial, initial.shape, alpha, rates, beta, residual_tolerance
        )

    half_initial = np.concatenate((np.full(length, 0.5), [0.5 * flux_scale]))
    initial_flux = flux_scale / 4.0
    initial_rho = np.linspace(
        1.0 - initial_flux / alpha,
        initial_flux / beta,
        length,
    )
    linear_initial = np.concatenate((initial_rho, [initial_flux]))
    errors = []
    for initial, normalized in ((half_initial, True), (linear_initial, False)):
        try:
            candidate = _newton_state_numpy(
                alpha,
                rates,
                beta,
                initial,
                root_tolerance,
                residual_tolerance,
                maxfev,
                normalized=normalized,
            )
            if not normalized:
                candidate = _newton_state_numpy(
                    alpha,
                    rates,
                    beta,
                    candidate,
                    root_tolerance,
                    residual_tolerance,
                    maxfev,
                    normalized=True,
                )
            return _checked_state(
                candidate, initial.shape, alpha, rates, beta, residual_tolerance
            )
        except (RuntimeError, ValueError) as error:
            errors.append(error)
    try:
        transient_state = _transient_state_numpy(
            alpha,
            rates,
            beta,
            initial_rho,
            maxfev,
            residual_tolerance,
            root_tolerance,
        )
        return _checked_state(
            transient_state,
            linear_initial.shape,
            alpha,
            rates,
            beta,
            residual_tolerance,
        )
    except (RuntimeError, ValueError) as transient_error:
        raise RuntimeError(
            f"Kinetic mean-field transient solve failed: {transient_error}"
        ) from errors[-1]


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
            diagnostics["backward_refinement_steps"] = alpha.new_tensor(0, dtype=torch.int64)
            diagnostics["backward_qr_fallback"] = alpha.new_tensor(False, dtype=torch.bool)
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
            diagnostics["backward_refinement_steps"] = alpha.new_zeros(
                batch_size, dtype=torch.int64
            )
            diagnostics["backward_qr_fallback"] = alpha.new_zeros(
                batch_size, dtype=torch.bool
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
    All computations use float64. The forward solve uses sparse Newton iterations
    with an analytic Jacobian and a banded transient fallback; PyTorch gradients
    for ``rho`` and ``J`` use implicit differentiation.
    The normalized residual is a non-differentiable convergence diagnostic.
    Root failures, excessive residuals, and states outside physical bounds raise
    an exception instead of returning an unconverged result.

    With ``return_diagnostics=True``, a fourth return value contains the Jacobian
    condition number, relative backward recovery residual, refinement count, and QR
    fallback status.  The residual is NaN until backward runs.  Backward always checks this residual against
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

    Each forward sample is solved independently by the same strict sparse
    Newton/banded-transient solve as :func:`solve_kinetic_mean_field`.
    Gradients for ``rho`` and ``J``
    use one batched implicit solve over the per-sample block Jacobians.
    Gradients through ``lengths`` and the normalized residual are not defined.
    ``return_diagnostics=True`` adds a dictionary with per-sample Jacobian
    condition numbers, backward recovery residuals, refinement counts, and QR fallback
    statuses, on the requested device.  Recovery residuals are NaN until backward runs and are always checked against
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
