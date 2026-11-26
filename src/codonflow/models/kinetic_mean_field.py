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
from scipy.linalg import solve_banded


_RANK_ONE_DENOMINATOR_TOLERANCE = 64.0 * np.finfo(np.float64).eps
_LINEAR_REFINEMENT_STEPS = 4


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


def _banded_jacobian_numpy(state, alpha, rates, beta):
    rho = state[:-1]
    length = rho.size
    lower = np.empty(length, dtype=np.float64)
    diagonal = np.zeros(length + 1, dtype=np.float64)
    upper = np.zeros(length, dtype=np.float64)
    diagonal[0] = -alpha
    if rates.size:
        lower[:-1] = rates * (1.0 - rho[1:])
        diagonal[1:-1] = -rates * rho[:-1]
    lower[-1] = beta
    flux_column = -np.ones(length + 1, dtype=np.float64)
    return lower, diagonal, upper, flux_column


def _jacobian_numpy(
    state: np.ndarray, alpha: float, rates: np.ndarray, beta: float
) -> np.ndarray:
    return _banded_to_dense_numpy(_banded_jacobian_numpy(state, alpha, rates, beta))


def _banded_to_dense_numpy(bands):
    lower, diagonal, upper, flux_column = bands
    matrix = np.diag(diagonal)
    matrix += np.diag(lower, k=-1)
    matrix += np.diag(upper, k=1)
    matrix[:, -1] = flux_column
    return matrix


def _banded_matvec_numpy(bands, vector, *, transpose=False):
    lower, diagonal, upper, flux_column = bands
    dtype = np.result_type(diagonal, vector)
    lower = np.asarray(lower, dtype=dtype)
    diagonal = np.asarray(diagonal, dtype=dtype)
    upper = np.asarray(upper, dtype=dtype)
    flux_column = np.asarray(flux_column, dtype=dtype)
    vector = np.asarray(vector, dtype=dtype)
    if vector.ndim == 2 and vector.shape[1] == 1:
        vector = vector[:, 0]
    result = diagonal * vector
    if transpose:
        result[:-1] += lower * vector[1:]
        result[1:] += upper * vector[:-1]
        result[-1] += np.dot(flux_column[:-1], vector[:-1])
        result[-1] += flux_column[-1] * vector[-1]
    else:
        result[1:] += lower * vector[:-1]
        result[:-1] += upper * vector[1:]
        result += flux_column * vector[-1]
    return result


def _banded_recovery_numpy(bands, solution, rhs, *, transpose=False):
    extended_bands = tuple(
        np.asarray(value, dtype=np.longdouble) for value in bands
    )
    solution = np.asarray(solution, dtype=np.longdouble)
    rhs = np.asarray(rhs, dtype=np.longdouble)
    recovery = _banded_matvec_numpy(
        extended_bands, solution, transpose=transpose
    ) - rhs
    absolute_bands = tuple(np.abs(value) for value in extended_bands)
    denominator = _banded_matvec_numpy(
        absolute_bands, np.abs(solution), transpose=transpose
    ) + np.abs(rhs)
    relative = np.abs(recovery).copy()
    np.divide(np.abs(recovery), denominator, out=relative, where=denominator > 0)
    return recovery, denominator, relative


def _banded_lu_once_numpy(bands, rhs, *, transpose=False):
    lower, diagonal, upper, flux_column = bands
    size = diagonal.size
    if transpose:
        scales = np.abs(flux_column)
        scales[0] = max(scales[0], abs(diagonal[0]))
        scales[1:] = np.maximum(scales[1:], np.abs(diagonal[1:]))
        scales[:-1] = np.maximum(scales[:-1], np.abs(lower))
        scales[1:] = np.maximum(scales[1:], np.abs(upper))
        lower = lower / scales[:-1]
        diagonal = diagonal / scales
        upper = upper / scales[1:]
        flux_column = flux_column / scales[-1]
    else:
        scales = np.abs(diagonal)
        scales[1:] = np.maximum(scales[1:], np.abs(lower))
        scales[:-1] = np.maximum(scales[:-1], np.abs(upper))
        scales = np.maximum(scales, np.abs(flux_column))
        lower = lower / scales[1:]
        diagonal = diagonal / scales
        upper = upper / scales[:-1]
        flux_column = flux_column / scales
    if np.any(scales <= 0) or not np.all(np.isfinite(scales)):
        raise ValueError("banded matrix has invalid equilibration scales")
    rhs = rhs / scales
    base_diagonal = diagonal.copy()
    base_diagonal[-1] = -flux_column[-1]
    rank_vector = -flux_column.copy()
    rank_vector[-1] = -2.0 * flux_column[-1]
    if transpose:
        band_lower, band_upper = upper, lower
        second_rhs = np.zeros(size, dtype=np.float64)
        second_rhs[-1] = 1.0
    else:
        band_lower, band_upper = lower, upper
        second_rhs = rank_vector
    ab = np.zeros((3, size), dtype=np.float64)
    ab[0, 1:] = band_upper
    ab[1] = base_diagonal
    ab[2, :-1] = band_lower
    solutions = solve_banded(
        (1, 1),
        ab,
        np.column_stack((rhs, second_rhs)),
        overwrite_ab=True,
        overwrite_b=True,
        check_finite=False,
    )
    first, second = solutions[:, 0], solutions[:, 1]
    if transpose:
        denominator = 1.0 - np.dot(rank_vector, second)
        numerator = np.dot(rank_vector, first)
    else:
        denominator = 1.0 - second[-1]
        numerator = first[-1]
    solution = first + second * (numerator / denominator)
    return solution, float(denominator)


def _rank_one_denominator_is_safe(denominator):
    return math.isfinite(denominator) and abs(denominator) > _RANK_ONE_DENOMINATOR_TOLERANCE


def _banded_qr_once_numpy(bands, rhs, *, transpose=False):
    lower, diagonal, upper, flux_column = bands
    size = diagonal.size
    diagonal = diagonal.copy()
    upper = upper.copy()
    second_upper = np.zeros(max(size - 2, 0), dtype=np.float64)
    flux_column = flux_column.copy()
    transformed_rhs = rhs.copy()
    rotations = []
    for index in range(size - 1):
        norm = math.hypot(diagonal[index], lower[index])
        if norm == 0.0 or not math.isfinite(norm):
            raise np.linalg.LinAlgError("singular banded QR pivot")
        cosine = diagonal[index] / norm
        sine = lower[index] / norm
        rotations.append((cosine, sine))
        if index < size - 2:
            current_upper = upper[index]
            next_diagonal = diagonal[index + 1]
            next_upper = upper[index + 1]
            upper[index] = cosine * current_upper + sine * next_diagonal
            diagonal[index + 1] = -sine * current_upper + cosine * next_diagonal
            second_upper[index] = sine * next_upper
            upper[index + 1] = cosine * next_upper
        first_flux = flux_column[index]
        second_flux = flux_column[index + 1]
        flux_column[index] = cosine * first_flux + sine * second_flux
        flux_column[index + 1] = -sine * first_flux + cosine * second_flux
        first_rhs = transformed_rhs[index]
        second_rhs = transformed_rhs[index + 1]
        transformed_rhs[index] = cosine * first_rhs + sine * second_rhs
        transformed_rhs[index + 1] = -sine * first_rhs + cosine * second_rhs
        diagonal[index] = norm
    diagonal[-1] = flux_column[-1]

    solution = rhs.copy() if transpose else transformed_rhs
    if transpose:
        for index in range(size):
            value = solution[index]
            if index > 0:
                value -= upper[index - 1] * solution[index - 1]
            if index > 1:
                value -= second_upper[index - 2] * solution[index - 2]
            if index == size - 1:
                value -= np.dot(flux_column[:-1], solution[:-1])
            solution[index] = value / diagonal[index]
        for index in range(size - 2, -1, -1):
            cosine, sine = rotations[index]
            first = solution[index]
            second = solution[index + 1]
            solution[index] = cosine * first - sine * second
            solution[index + 1] = sine * first + cosine * second
        return solution

    for index in range(size - 1, -1, -1):
        value = solution[index]
        if index < size - 1:
            value -= upper[index] * solution[index + 1]
            value -= flux_column[index] * solution[-1]
        if index < size - 2:
            value -= second_upper[index] * solution[index + 2]
        solution[index] = value / diagonal[index]
    return solution


def _rank_one_banded_solve_numpy(
    bands, rhs, residual_tolerance=1e-10, *, transpose=False
):
    denominator = float("nan")
    refinement_steps = 0
    qr_fallback = False
    qr_error = None
    solution = np.full_like(rhs, np.nan, dtype=np.float64)
    recovery, component_denominator, relative = _banded_recovery_numpy(
        bands, solution, rhs, transpose=transpose
    )
    converged = False
    try:
        solution, denominator = _banded_lu_once_numpy(
            bands, rhs, transpose=transpose
        )
        recovery, component_denominator, relative = _banded_recovery_numpy(
            bands, solution, rhs, transpose=transpose
        )
        converged = bool(
            _rank_one_denominator_is_safe(denominator)
            and np.all(np.isfinite(solution))
            and np.all(np.isfinite(relative))
            and np.max(relative) <= residual_tolerance
        )
        while (
            not converged
            and refinement_steps < _LINEAR_REFINEMENT_STEPS
            and _rank_one_denominator_is_safe(denominator)
            and np.all(np.isfinite(relative))
        ):
            correction, correction_denominator = _banded_lu_once_numpy(
                bands,
                recovery.astype(np.float64),
                transpose=transpose,
            )
            if not _rank_one_denominator_is_safe(correction_denominator):
                break
            solution = solution - correction
            refinement_steps += 1
            recovery, component_denominator, relative = _banded_recovery_numpy(
                bands, solution, rhs, transpose=transpose
            )
            converged = bool(
                np.all(np.isfinite(solution))
                and np.all(np.isfinite(relative))
                and np.max(relative) <= residual_tolerance
            )
    except (ValueError, np.linalg.LinAlgError) as error:
        qr_error = str(error)

    if not converged:
        qr_fallback = True
        try:
            solution = _banded_qr_once_numpy(bands, rhs, transpose=transpose)
            recovery, component_denominator, relative = _banded_recovery_numpy(
                bands, solution, rhs, transpose=transpose
            )
            converged = bool(
                np.all(np.isfinite(solution))
                and np.all(np.isfinite(relative))
                and np.max(relative) <= residual_tolerance
            )
            qr_steps = 0
            while not converged and qr_steps < _LINEAR_REFINEMENT_STEPS:
                correction = _banded_qr_once_numpy(
                    bands, recovery.astype(np.float64), transpose=transpose
                )
                solution = solution - correction
                refinement_steps += 1
                qr_steps += 1
                recovery, component_denominator, relative = _banded_recovery_numpy(
                    bands, solution, rhs, transpose=transpose
                )
                converged = bool(
                    np.all(np.isfinite(solution))
                    and np.all(np.isfinite(relative))
                    and np.max(relative) <= residual_tolerance
                )
        except (ValueError, np.linalg.LinAlgError) as error:
            qr_error = str(error)
            converged = False
    info = {
        "rank_one_denominator": denominator,
        "refinement_steps": refinement_steps,
        "qr_fallback": qr_fallback,
        "qr_error": qr_error,
        "recovery_extended": recovery,
        "denominator_extended": component_denominator,
        "relative_recovery_extended": relative,
    }
    if not converged:
        detail = float(np.max(relative))
        error = RuntimeError(
            "Banded rank-one linear solve exceeded the recovery residual tolerance "
            f"after LU and QR refinement: {detail:.3e} > {residual_tolerance:.3e}"
        )
        error.linear_solver_info = info
        raise error
    return solution, info


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
    bands = _banded_jacobian_numpy(state, alpha, rates, beta)
    lower, diagonal, upper, flux_column = bands
    column_sums = np.abs(flux_column)
    column_sums[0] += abs(diagonal[0])
    column_sums[1:] += np.abs(diagonal[1:])
    column_sums[:-1] += np.abs(lower)
    column_sums[1:] += np.abs(upper)
    matrix_norm = float(np.max(column_sums))
    size = state.size
    vector = np.full(size, 1.0 / size, dtype=np.float64)
    inverse_norm = 0.0
    for _ in range(5):
        vector = _rank_one_banded_solve_numpy(bands, vector)[0]
        inverse_norm = float(np.sum(np.abs(vector)))
        signs = np.where(vector >= 0.0, 1.0, -1.0)
        dual = _rank_one_banded_solve_numpy(
            bands, signs, transpose=True
        )[0]
        dual_norm = float(np.max(np.abs(dual)))
        if dual_norm <= float(np.dot(dual, vector)):
            break
        next_vector = np.zeros(size, dtype=np.float64)
        next_vector[int(np.argmax(np.abs(dual)))] = 1.0
        vector = next_vector
    condition = matrix_norm * inverse_norm
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


def _extended_banded_backward_recovery(bands, multiplier, output_gradient):
    numpy_bands = tuple(
        np.asarray(value.detach().cpu().numpy(), dtype=np.longdouble)
        for value in bands
    )
    return _banded_recovery_numpy(
        numpy_bands,
        multiplier.detach().cpu().numpy(),
        output_gradient.detach().cpu().numpy(),
        transpose=True,
    )


def _set_backward_diagnostic(diagnostics, name, index, value, single):
    if diagnostics is None or name not in diagnostics:
        return
    target = diagnostics[name]
    if single:
        target.fill_(value)
    else:
        target[index].fill_(value)


def _dense_to_banded(matrix):
    diagonal = torch.diagonal(matrix, dim1=-2, dim2=-1).clone()
    upper = torch.diagonal(matrix, dim1=-2, dim2=-1, offset=1).clone()
    diagonal[..., -1] = 0
    if upper.shape[-1]:
        upper[..., -1] = 0
    return (
        torch.diagonal(matrix, dim1=-2, dim2=-1, offset=-1).clone(),
        diagonal,
        upper,
        matrix[..., :, -1].clone(),
    )


def _banded_to_dense_torch(bands):
    lower, diagonal, upper, flux_column = bands
    size = diagonal.shape[-1]
    matrix = torch.diag_embed(diagonal)
    if size > 1:
        matrix = matrix + torch.diag_embed(lower, offset=-1)
        matrix = matrix + torch.diag_embed(upper, offset=1)
    matrix[..., :, -1] = flux_column
    return matrix


def _tridiagonal_factor_torch(lower, diagonal, upper):
    lower = lower.clone()
    diagonal = diagonal.clone()
    upper = upper.clone()
    batch_size, size = diagonal.shape
    second_upper = diagonal.new_zeros((batch_size, max(size - 2, 0)))
    pivots = []
    for index in range(size - 1):
        current_diagonal = diagonal[:, index]
        current_lower = lower[:, index]
        current_upper = upper[:, index]
        next_diagonal = diagonal[:, index + 1]
        interchange = current_lower.abs() > current_diagonal.abs()
        pivot = torch.where(interchange, current_lower, current_diagonal)
        safe_pivot = torch.where(pivot != 0, pivot, torch.ones_like(pivot))
        multiplier = torch.where(
            interchange, current_diagonal, current_lower
        ) / safe_pivot
        no_swap_next = next_diagonal - multiplier * current_upper
        swapped_next = current_upper - multiplier * next_diagonal
        diagonal[:, index] = torch.where(
            interchange, current_lower, current_diagonal
        )
        upper[:, index] = torch.where(
            interchange, next_diagonal, current_upper
        )
        diagonal[:, index + 1] = torch.where(
            interchange, swapped_next, no_swap_next
        )
        lower[:, index] = multiplier
        pivots.append(interchange)
        if index < size - 2:
            following_upper = upper[:, index + 1].clone()
            second_upper[:, index] = torch.where(
                interchange, following_upper, torch.zeros_like(multiplier)
            )
            upper[:, index + 1] = torch.where(
                interchange,
                -multiplier * following_upper,
                following_upper,
            )
    return lower, diagonal, upper, second_upper, pivots


def _tridiagonal_solve_torch(factor, rhs, *, transpose=False):
    lower, diagonal, upper, second_upper, pivots = factor
    size = diagonal.shape[1]
    safe_diagonal = torch.where(
        diagonal != 0, diagonal, torch.ones_like(diagonal)
    )
    solution = rhs.clone()
    if transpose:
        for index in range(size):
            value = solution[:, index]
            if index > 0:
                value = value - upper[:, index - 1].unsqueeze(-1) * solution[:, index - 1]
            if index > 1:
                value = value - second_upper[:, index - 2].unsqueeze(-1) * solution[:, index - 2]
            solution[:, index] = value / safe_diagonal[:, index].unsqueeze(-1)
        for index in range(size - 2, -1, -1):
            solution[:, index] = (
                solution[:, index] - lower[:, index].unsqueeze(-1) * solution[:, index + 1]
            )
            interchange = pivots[index].unsqueeze(-1)
            current = solution[:, index].clone()
            following = solution[:, index + 1]
            solution[:, index] = torch.where(interchange, following, current)
            solution[:, index + 1] = torch.where(interchange, current, following)
        return solution

    for index in range(size - 1):
        interchange = pivots[index].unsqueeze(-1)
        current = solution[:, index].clone()
        following = solution[:, index + 1]
        no_swap = following - lower[:, index].unsqueeze(-1) * current
        swapped_current = following
        swapped_next = current - lower[:, index].unsqueeze(-1) * following
        solution[:, index] = torch.where(interchange, swapped_current, current)
        solution[:, index + 1] = torch.where(interchange, swapped_next, no_swap)
    solution[:, -1] = solution[:, -1] / safe_diagonal[:, -1].unsqueeze(-1)
    if size > 1:
        solution[:, -2] = (
            solution[:, -2] - upper[:, -1].unsqueeze(-1) * solution[:, -1]
        ) / safe_diagonal[:, -2].unsqueeze(-1)
    for index in range(size - 3, -1, -1):
        solution[:, index] = (
            solution[:, index]
            - upper[:, index].unsqueeze(-1) * solution[:, index + 1]
            - second_upper[:, index].unsqueeze(-1) * solution[:, index + 2]
        ) / safe_diagonal[:, index].unsqueeze(-1)
    return solution


def _banded_rank_one_solve_cuda(bands, rhs, *, transpose=False, diagnostics=None):
    if rhs.device.type == "cuda":
        try:
            from codonflow.models import kinetic_banded_cuda

            result = kinetic_banded_cuda.rank_one(bands, rhs, transpose=transpose)
            if diagnostics is not None:
                diagnostics["backward_cuda_kernel_backend"] = "triton"
            return result
        except (ImportError, RuntimeError) as error:
            if diagnostics is not None:
                diagnostics["backward_cuda_kernel_backend"] = "torch_after_triton_error"
                diagnostics["backward_cuda_accelerator_error"] = str(error)
    return _banded_rank_one_solve_torch(bands, rhs, transpose=transpose)


def _banded_qr_once_cuda(bands, rhs, *, transpose=False, diagnostics=None):
    if rhs.device.type == "cuda":
        try:
            from codonflow.models import kinetic_banded_cuda

            result = kinetic_banded_cuda.qr(bands, rhs, transpose=transpose)
            if diagnostics is not None:
                diagnostics["backward_cuda_kernel_backend"] = "triton"
            return result
        except (ImportError, RuntimeError) as error:
            if diagnostics is not None:
                diagnostics["backward_cuda_kernel_backend"] = "torch_after_triton_error"
                diagnostics["backward_cuda_accelerator_error"] = str(error)
    return _banded_qr_once_torch(bands, rhs, transpose=transpose)


def _banded_rank_one_solve_torch(bands, rhs, *, transpose=False):
    lower, diagonal, upper, flux_column = bands
    size = diagonal.shape[1]
    base_diagonal = diagonal.clone()
    base_diagonal[:, -1] = -flux_column[:, -1]
    rank_vector = -flux_column.clone()
    rank_vector[:, -1] = -2.0 * flux_column[:, -1]
    factor = _tridiagonal_factor_torch(lower, base_diagonal, upper)
    if transpose:
        second_rhs = rhs.new_zeros((rhs.shape[0], size))
        second_rhs[:, -1] = 1.0
    else:
        second_rhs = rank_vector
    solutions = _tridiagonal_solve_torch(
        factor,
        torch.stack((rhs, second_rhs), dim=-1),
        transpose=transpose,
    )
    first, second = solutions[..., 0], solutions[..., 1]
    if transpose:
        denominator = 1.0 - (rank_vector * second).sum(dim=-1)
        numerator = (rank_vector * first).sum(dim=-1)
    else:
        denominator = 1.0 - second[:, -1]
        numerator = first[:, -1]
    safe_denominator = torch.where(
        denominator.abs() > _RANK_ONE_DENOMINATOR_TOLERANCE,
        denominator,
        torch.ones_like(denominator),
    )
    solution = first + second * (numerator / safe_denominator).unsqueeze(-1)
    return solution, denominator


def _banded_qr_once_torch(bands, rhs, *, transpose=False):
    vector_rhs = rhs.ndim == 2
    if vector_rhs:
        rhs = rhs.unsqueeze(-1)
    lower, diagonal, upper, flux_column = bands
    size = diagonal.shape[1]
    diagonal = diagonal.clone()
    upper = upper.clone()
    second_upper = diagonal.new_zeros((diagonal.shape[0], max(size - 2, 0)))
    flux_column = flux_column.clone()
    transformed_rhs = rhs.clone()
    rotations = []
    for index in range(size - 1):
        norm = torch.hypot(diagonal[:, index], lower[:, index])
        safe_norm = torch.where(norm > 0, norm, torch.ones_like(norm))
        cosine = diagonal[:, index] / safe_norm
        sine = lower[:, index] / safe_norm
        rotations.append((cosine, sine))
        if index < size - 2:
            current_upper = upper[:, index].clone()
            next_diagonal = diagonal[:, index + 1].clone()
            next_upper = upper[:, index + 1].clone()
            upper[:, index] = cosine * current_upper + sine * next_diagonal
            diagonal[:, index + 1] = -sine * current_upper + cosine * next_diagonal
            second_upper[:, index] = sine * next_upper
            upper[:, index + 1] = cosine * next_upper
        first_flux = flux_column[:, index].clone()
        second_flux = flux_column[:, index + 1].clone()
        flux_column[:, index] = cosine * first_flux + sine * second_flux
        flux_column[:, index + 1] = -sine * first_flux + cosine * second_flux
        first_rhs = transformed_rhs[:, index].clone()
        second_rhs = transformed_rhs[:, index + 1]
        transformed_rhs[:, index] = (
            cosine.unsqueeze(-1) * first_rhs + sine.unsqueeze(-1) * second_rhs
        )
        transformed_rhs[:, index + 1] = (
            -sine.unsqueeze(-1) * first_rhs + cosine.unsqueeze(-1) * second_rhs
        )
        diagonal[:, index] = norm
    diagonal[:, -1] = flux_column[:, -1]
    safe_diagonal = torch.where(
        diagonal != 0, diagonal, torch.ones_like(diagonal)
    )

    solution = rhs.clone() if transpose else transformed_rhs
    if transpose:
        for index in range(size):
            value = solution[:, index]
            if index > 0:
                value = value - upper[:, index - 1].unsqueeze(-1) * solution[:, index - 1]
            if index > 1:
                value = value - second_upper[:, index - 2].unsqueeze(-1) * solution[:, index - 2]
            if index == size - 1:
                value = value - (
                    flux_column[:, :-1].unsqueeze(-1) * solution[:, :-1]
                ).sum(dim=1)
            solution[:, index] = value / safe_diagonal[:, index].unsqueeze(-1)
        for index in range(size - 2, -1, -1):
            cosine, sine = rotations[index]
            first = solution[:, index].clone()
            second = solution[:, index + 1]
            solution[:, index] = (
                cosine.unsqueeze(-1) * first - sine.unsqueeze(-1) * second
            )
            solution[:, index + 1] = (
                sine.unsqueeze(-1) * first + cosine.unsqueeze(-1) * second
            )
        return solution[..., 0] if vector_rhs else solution

    for index in range(size - 1, -1, -1):
        value = solution[:, index]
        if index < size - 1:
            value = value - upper[:, index].unsqueeze(-1) * solution[:, index + 1]
            value = value - flux_column[:, index].unsqueeze(-1) * solution[:, -1]
        if index < size - 2:
            value = value - second_upper[:, index].unsqueeze(-1) * solution[:, index + 2]
        solution[:, index] = value / safe_diagonal[:, index].unsqueeze(-1)
    return solution[..., 0] if vector_rhs else solution


def _banded_matvec_torch(bands, vector, *, transpose=False):
    lower, diagonal, upper, flux_column = bands
    result = diagonal * vector
    if transpose:
        result[..., :-1] += lower * vector[..., 1:]
        result[..., 1:] += upper * vector[..., :-1]
        result[..., -1] += (flux_column[..., :-1] * vector[..., :-1]).sum(dim=-1)
        result[..., -1] += flux_column[..., -1] * vector[..., -1]
    else:
        result[..., 1:] += lower * vector[..., :-1]
        result[..., :-1] += upper * vector[..., 1:]
        result += flux_column * vector[..., -1:]
    return result


def _banded_column_scales(bands):
    lower, diagonal, upper, flux_column = bands
    scales = flux_column.abs().clone()
    scales[..., 0] = torch.maximum(scales[..., 0], diagonal[..., 0].abs())
    scales[..., 1:] = torch.maximum(scales[..., 1:], diagonal[..., 1:].abs())
    if diagonal.shape[-1] > 1:
        scales[..., :-1] = torch.maximum(scales[..., :-1], lower.abs())
        scales[..., 1:] = torch.maximum(scales[..., 1:], upper.abs())
    return scales


def _backward_failure_context(
    index,
    single,
    bands,
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
    size = bands[1].numel()
    dense_transpose = None
    if size <= 512:
        dense_transpose = _banded_to_dense_torch(bands).transpose(0, 1).detach().cpu()
    return {
        "batch_index": None if single else int(index),
        "jacobian_transpose": dense_transpose,
        "jacobian_banded": tuple(value.detach().cpu().clone() for value in bands),
        "output_gradient": output_gradient.detach().cpu().clone(),
        "multiplier": multiplier.detach().cpu().clone(),
        "recovery_extended": recovery,
        "denominator_extended": denominator,
        "relative_recovery_extended": relative_recovery,
        "jacobian_condition_number": condition_number,
        "refinement_steps": int(refinement_steps),
        "qr_fallback": bool(qr_fallback),
        "qr_error": qr_error,
        "extended_precision_device": "cpu",
    }


def _solve_adjoint_system(jacobian, output_gradient, residual_tolerance, diagnostics):
    if isinstance(jacobian, torch.Tensor):
        single = jacobian.ndim == 2
        bands = _dense_to_banded(jacobian)
    else:
        single = jacobian[1].ndim == 1
        bands = jacobian
    if single:
        bands = tuple(value.unsqueeze(0) for value in bands)
        output_gradient = output_gradient.unsqueeze(0)
    row_scale = _banded_column_scales(bands)
    if not bool(torch.isfinite(row_scale).all()) or not bool((row_scale > 0).all()):
        raise RuntimeError("Kinetic mean-field backward Jacobian has invalid row scales")
    lower, diagonal, upper, flux_column = bands
    scaled_bands = (
        lower / row_scale[..., :-1],
        diagonal / row_scale,
        upper / row_scale[..., 1:],
        flux_column / row_scale[..., -1:],
    )
    rhs = output_gradient / row_scale
    multipliers, rank_denominators = _banded_rank_one_solve_cuda(
        scaled_bands, rhs, transpose=True, diagnostics=diagnostics
    )

    recovery = _banded_matvec_torch(
        bands, multipliers, transpose=True
    ) - output_gradient
    denominator = _banded_matvec_torch(
        tuple(value.abs() for value in bands),
        multipliers.abs(),
        transpose=True,
    ) + output_gradient.abs()
    relative_recovery = torch.where(
        denominator > 0, recovery.abs() / denominator, recovery.abs()
    )
    reported_recovery = relative_recovery.amax(dim=-1)
    if diagnostics is not None:
        diagnostics["backward_recovery_residual"].copy_(
            reported_recovery[0] if single else reported_recovery
        )
        if "backward_rank_one_denominator_min" in diagnostics:
            diagnostics["backward_rank_one_denominator_min"].copy_(
                rank_denominators.abs()[0] if single else rank_denominators.abs()
            )
    failed = (
        ~torch.isfinite(multipliers).all(dim=-1)
        | ~torch.isfinite(reported_recovery)
        | (reported_recovery > residual_tolerance)
        | ~torch.isfinite(rank_denominators)
        | (rank_denominators.abs() <= _RANK_ONE_DENOMINATOR_TOLERANCE)
    )
    if not bool(failed.any()):
        return multipliers[0] if single else multipliers

    if diagnostics is None and multipliers.device.type == "cuda":
        warnings.warn(
            "Kinetic backward recovery is using explicitly recorded CPU extended "
            "precision residuals; CUDA model tensors are not moved to CPU.",
            RuntimeWarning,
            stacklevel=2,
        )
    failures = []
    for index in failed.nonzero(as_tuple=False).flatten().tolist():
        sample_bands = tuple(value[index] for value in bands)
        sample_scaled_bands = tuple(value[index].unsqueeze(0) for value in scaled_bands)
        gradient = output_gradient[index]
        multiplier = multipliers[index].clone()
        refinement_steps = 0
        qr_fallback = False
        qr_error = None
        rank_denominator = float(rank_denominators[index].detach().cpu())
        recovery_extended, denominator_extended, relative_extended = (
            _extended_banded_backward_recovery(sample_bands, multiplier, gradient)
        )
        _set_backward_diagnostic(
            diagnostics, "backward_cpu_extended_precision", index, True, single
        )
        converged = bool(
            _rank_one_denominator_is_safe(rank_denominator)
            and np.all(np.isfinite(multiplier.detach().cpu().numpy()))
            and np.all(np.isfinite(relative_extended))
            and np.max(relative_extended) <= residual_tolerance
        )

        while not converged and refinement_steps < _BACKWARD_LU_REFINEMENT_STEPS:
            if not np.all(np.isfinite(relative_extended)) or not _rank_one_denominator_is_safe(
                rank_denominator
            ):
                break
            correction, correction_denominator = _banded_rank_one_solve_cuda(
                sample_scaled_bands,
                torch.as_tensor(
                    recovery_extended.astype(np.float64),
                    dtype=gradient.dtype,
                    device=gradient.device,
                ).unsqueeze(0) / row_scale[index],
                transpose=True,
                diagnostics=diagnostics,
            )
            rank_denominator = float(correction_denominator[0].detach().cpu())
            if not _rank_one_denominator_is_safe(rank_denominator):
                break
            multiplier = multiplier - correction[0]
            refinement_steps += 1
            recovery_extended, denominator_extended, relative_extended = (
                _extended_banded_backward_recovery(sample_bands, multiplier, gradient)
            )
            converged = bool(
                np.all(np.isfinite(multiplier.detach().cpu().numpy()))
                and np.all(np.isfinite(relative_extended))
                and np.max(relative_extended) <= residual_tolerance
            )

        if not converged:
            qr_fallback = True
            try:
                scaled_rhs = (gradient / row_scale[index]).unsqueeze(0)
                multiplier = _banded_qr_once_cuda(
                    sample_scaled_bands,
                    scaled_rhs,
                    transpose=True,
                    diagnostics=diagnostics,
                )[0]
                recovery_extended, denominator_extended, relative_extended = (
                    _extended_banded_backward_recovery(sample_bands, multiplier, gradient)
                )
                converged = bool(
                    np.all(np.isfinite(multiplier.detach().cpu().numpy()))
                    and np.all(np.isfinite(relative_extended))
                    and np.max(relative_extended) <= residual_tolerance
                )
                if not converged and gradient.device.type == "cuda":
                    multiplier = _banded_qr_once_torch(
                        sample_scaled_bands, scaled_rhs, transpose=True
                    )[0]
                    _set_backward_diagnostic(
                        diagnostics,
                        "backward_triton_qr_reference_fallback",
                        index,
                        True,
                        single,
                    )
                    recovery_extended, denominator_extended, relative_extended = (
                        _extended_banded_backward_recovery(sample_bands, multiplier, gradient)
                    )
                    converged = bool(
                        np.all(np.isfinite(multiplier.detach().cpu().numpy()))
                        and np.all(np.isfinite(relative_extended))
                        and np.max(relative_extended) <= residual_tolerance
                    )
                qr_steps = 0
                while not converged and qr_steps < _BACKWARD_QR_REFINEMENT_STEPS:
                    correction = _banded_qr_once_torch(
                        sample_scaled_bands,
                        torch.as_tensor(
                            recovery_extended.astype(np.float64),
                            dtype=gradient.dtype,
                            device=gradient.device,
                        ).unsqueeze(0) / row_scale[index],
                        transpose=True,
                    )[0]
                    multiplier = multiplier - correction
                    refinement_steps += 1
                    qr_steps += 1
                    recovery_extended, denominator_extended, relative_extended = (
                        _extended_banded_backward_recovery(sample_bands, multiplier, gradient)
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
        _set_backward_diagnostic(
            diagnostics,
            "backward_rank_one_denominator_min",
            index,
            abs(rank_denominator),
            single,
        )
        if converged:
            multipliers[index] = multiplier
        else:
            failures.append(
                _backward_failure_context(
                    index,
                    single,
                    sample_bands,
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
    linear_diagnostics=None,
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

        lower = np.empty(length, dtype=np.float64)
        diagonal = np.zeros(length + 1, dtype=np.float64)
        upper = np.zeros(length, dtype=np.float64)
        if normalized:
            diagonal[0] = -alpha / flux
            lower[-1] = beta / flux
            flux_column = -(residual + 1.0) / scaled_flux
        else:
            diagonal[0] = -1.0
            lower[-1] = 1.0
            flux_column = -inverse_rates
        if length > 1:
            if normalized:
                lower[:-1] = rates * (1.0 - rho[1:]) / flux
                diagonal[1:-1] = -rates * rho[:-1] / flux
            else:
                lower[:-1] = 1.0 - rho[1:]
                diagonal[1:-1] = -rho[:-1]
        return residual, (lower, diagonal, upper, flux_column)

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
        step, linear_info = _rank_one_banded_solve_numpy(
            jacobian, -residual, residual_tolerance
        )
        if linear_diagnostics is not None:
            linear_diagnostics.append({
                "rank_one_denominator": linear_info["rank_one_denominator"],
                "refinement_steps": linear_info["refinement_steps"],
                "qr_fallback": linear_info["qr_fallback"],
            })
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
    linear_diagnostics=None,
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
                linear_diagnostics=linear_diagnostics,
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
    linear_diagnostics=None,
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
                linear_diagnostics=linear_diagnostics,
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
                    linear_diagnostics=linear_diagnostics,
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
            linear_diagnostics,
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


def _record_solver_diagnostics(diagnostics, alpha, linear_details):
    if diagnostics is None:
        return
    batch_size = len(linear_details)
    solve_counts = [len(details) for details in linear_details]
    refinement_steps = [
        sum(item["refinement_steps"] for item in details)
        for details in linear_details
    ]
    qr_fallbacks = [
        any(item["qr_fallback"] for item in details)
        for details in linear_details
    ]
    denominator_minima = [
        min((abs(item["rank_one_denominator"]) for item in details), default=-1.0)
        for details in linear_details
    ]
    shape = () if batch_size == 1 and alpha.ndim == 0 else (batch_size,)
    def scalar_or_vector(values, dtype=None):
        tensor = torch.as_tensor(values, dtype=dtype, device=alpha.device)
        return tensor[0] if shape == () else tensor
    diagnostics["forward_linear_solve_count"] = scalar_or_vector(
        solve_counts, dtype=torch.int64
    )
    diagnostics["forward_linear_refinement_steps"] = scalar_or_vector(
        refinement_steps, dtype=torch.int64
    )
    diagnostics["forward_qr_fallback"] = scalar_or_vector(
        qr_fallbacks, dtype=torch.bool
    )
    diagnostics["forward_rank_one_denominator_min"] = scalar_or_vector(
        denominator_minima, dtype=torch.float64
    )
    diagnostics["backward_rank_one_denominator_min"] = alpha.new_full(
        shape, float("nan")
    )
    diagnostics["backward_cpu_extended_precision"] = torch.zeros(
        shape, dtype=torch.bool, device=alpha.device
    )
    diagnostics["backward_triton_qr_reference_fallback"] = torch.zeros(
        shape, dtype=torch.bool, device=alpha.device
    )
    diagnostics["backward_cuda_kernel_backend"] = (
        "not_applicable_cpu" if not alpha.is_cuda else "torch_until_accelerated"
    )
    diagnostics["forward_device"] = "cpu"
    diagnostics["forward_linear_solver"] = (
        "scipy_lapack_banded_partial_pivoting_sherman_morrison_with_givens_qr_fallback"
    )
    diagnostics["forward_cpu_path_explicit"] = True
    diagnostics["backward_device"] = str(alpha.device)
    diagnostics["backward_linear_solver"] = (
        "torch_banded_partial_pivoting_sherman_morrison_with_givens_qr_fallback"
    )
    diagnostics["backward_dense_padded_matrix_constructed"] = False
    diagnostics["jacobian_condition_number_kind"] = (
        "one_norm_times_estimated_inverse_one_norm"
    )


class _KineticMeanFieldFunction(torch.autograd.Function):
    @staticmethod
    def forward(
        ctx, alpha, k, beta, root_tolerance, residual_tolerance, maxfev, diagnostics
    ):
        alpha_numpy = float(alpha.detach().cpu())
        k_numpy = k.detach().cpu().numpy()
        beta_numpy = float(beta.detach().cpu())
        linear_details = []
        state, residual = _solve_state_numpy(
            alpha_numpy,
            k_numpy,
            beta_numpy,
            root_tolerance,
            residual_tolerance,
            maxfev,
            linear_details,
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
        _record_solver_diagnostics(diagnostics, alpha, [linear_details])
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
        lower = rho.new_empty(length)
        diagonal = rho.new_zeros(length + 1)
        upper = rho.new_zeros(length)
        diagonal[0] = -alpha
        if k.numel():
            lower[:-1] = k * (1.0 - rho[1:])
            diagonal[1:-1] = -k * rho[:-1]
        lower[-1] = beta
        jacobian = (lower, diagonal, upper, -rho.new_ones(length + 1))

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
        all_linear_details = []
        for index, length in enumerate(lengths_list):
            sample_alpha = float(alpha_numpy[index])
            sample_k = k_numpy[index, : length - 1]
            sample_beta = float(beta_numpy[index])
            linear_details = []
            all_linear_details.append(linear_details)
            try:
                state, residual = _solve_state_numpy(
                    sample_alpha,
                    sample_k,
                    sample_beta,
                    root_tolerance,
                    residual_tolerance,
                    maxfev,
                    linear_details,
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
        _record_solver_diagnostics(diagnostics, alpha, all_linear_details)
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
        lengths_list = lengths.detach().cpu().tolist()
        lower = rho.new_zeros((batch_size, max_length))
        diagonal = rho.new_ones((batch_size, max_length + 1))
        upper = rho.new_zeros((batch_size, max_length))
        flux_column = rho.new_zeros((batch_size, max_length + 1))
        diagonal[:, -1] = 0.0
        for index, length in enumerate(lengths_list):
            offset = max_length - length
            sample_k = k[index, : length - 1]
            sample_rho = rho[index, :length]
            diagonal[index, offset] = -alpha[index]
            if length > 1:
                diagonal[index, offset + 1 : max_length] = -sample_k * sample_rho[:-1]
                lower[index, offset : max_length - 1] = sample_k * (1.0 - sample_rho[1:])
            lower[index, -1] = beta[index]
            flux_column[index, offset:] = -1.0
        jacobian = (lower, diagonal, upper, flux_column)

        if grad_rho is None:
            grad_rho = torch.zeros_like(rho)
        if grad_flux is None:
            grad_flux = torch.zeros_like(alpha)
        batch_indices = torch.arange(batch_size, device=rho.device)
        output_gradient = rho.new_zeros((batch_size, max_length + 1))
        output_gradient[:, -1] = grad_flux
        for index, length in enumerate(lengths_list):
            offset = max_length - length
            output_gradient[index, offset:max_length] = grad_rho[index, :length]
        multiplier = _solve_adjoint_system(
            jacobian, output_gradient, ctx.residual_tolerance, ctx.diagnostics
        )
        offsets = max_length - lengths
        grad_alpha = -multiplier[batch_indices, offsets] * (1.0 - rho[:, 0])
        grad_beta = -multiplier[:, -1] * rho[batch_indices, lengths - 1]
        grad_k = torch.zeros_like(k)
        for index, length in enumerate(lengths_list):
            if length > 1:
                offset = max_length - length
                sample_rho = rho[index, :length]
                grad_k[index, : length - 1] = (
                    -multiplier[index, offset + 1 : max_length]
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
    All computations use float64. The forward solve explicitly uses CPU SciPy/LAPACK
    Newton iterations with an analytic tridiagonal-plus-rank-one Jacobian and a
    banded transient fallback. PyTorch gradients for ``rho`` and ``J`` use implicit
    differentiation with a pivoted banded solve on the input device; CUDA inputs do
    not silently move the adjoint model computation to CPU.
    The normalized residual is a non-differentiable convergence diagnostic.
    Root failures, excessive residuals, and states outside physical bounds raise
    an exception instead of returning an unconverged result.

    With ``return_diagnostics=True``, a fourth return value contains a deterministic
    one-norm Jacobian condition estimate, forward/backward solver paths, rank-one
    denominators, relative backward recovery residual, refinement counts, and QR
    fallback status. The residual is NaN until backward runs. Backward always checks this residual against
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

    Each forward sample is solved independently by the same strict CPU banded
    Newton/banded-transient solve as :func:`solve_kinetic_mean_field`.
    Gradients for ``rho`` and ``J`` use one O(BL)-storage batched implicit solve over
    left-identity-padded tridiagonal-plus-rank-one Jacobians on the input device.
    Gradients through ``lengths`` and the normalized residual are not defined.
    ``return_diagnostics=True`` adds per-sample Jacobian condition estimates,
    forward/backward solver paths, rank-one denominators, backward recovery residuals,
    refinement counts, and QR fallback statuses. Tensor diagnostics are on the
    requested device. Recovery residuals are NaN until backward runs and are always checked against
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
