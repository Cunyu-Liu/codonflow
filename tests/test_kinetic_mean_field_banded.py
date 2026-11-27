"""Independent structural and numerical tests for the banded kinetic solver."""
import numpy as np
import pytest
import torch

import codonflow.models.kinetic_mean_field as kinetic_mean_field
from codonflow.models.kinetic_mean_field import (
    solve_kinetic_mean_field,
    solve_kinetic_mean_field_batch,
)


def random_arrow_bands(rng, size, device="cpu"):
    lower = torch.as_tensor(
        rng.normal(size=size - 1), dtype=torch.float64, device=device
    )
    diagonal = torch.as_tensor(
        rng.normal(size=size), dtype=torch.float64, device=device
    )
    upper = torch.as_tensor(
        rng.normal(size=size - 1), dtype=torch.float64, device=device
    )
    flux = torch.as_tensor(
        rng.normal(size=size), dtype=torch.float64, device=device
    )
    diagonal[-1] = 0.0
    upper[-1] = 0.0
    return lower, diagonal, upper, flux


@pytest.mark.parametrize("device", ["cpu", pytest.param("cuda", marks=pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is not available"))])
def test_independent_dense_assembly_matches_pivoted_forward_and_transpose(device):
    rng = np.random.default_rng(20261126)
    for size in (2, 3, 4, 9, 20):
        for _ in range(4):
            bands = random_arrow_bands(rng, size, device)
            rhs = torch.as_tensor(
                rng.normal(size=size), dtype=torch.float64, device=device
            )
            matrix = kinetic_mean_field._banded_to_dense_torch(bands)
            for transpose in (False, True):
                expected = torch.linalg.solve(
                    matrix.transpose(0, 1) if transpose else matrix, rhs
                )
                actual, denominator = kinetic_mean_field._banded_rank_one_solve_torch(
                    tuple(value.unsqueeze(0) for value in bands),
                    rhs.unsqueeze(0),
                    transpose=transpose,
                )
                scaled_error = (actual[0] - expected).abs().max() / max(
                    1.0, float(expected.abs().max())
                )
                assert float(scaled_error) < 2e-11
                assert abs(float(denominator[0])) > 0.0
                recovery = kinetic_mean_field._banded_matvec_torch(
                    tuple(value.unsqueeze(0) for value in bands),
                    actual,
                    transpose=transpose,
                ) - rhs
                denominator_recovery = kinetic_mean_field._banded_matvec_torch(
                    tuple(value.abs().unsqueeze(0) for value in bands),
                    actual.abs(),
                    transpose=transpose,
                ) + rhs.abs()
                relative = recovery.abs() / torch.where(
                    denominator_recovery > 0,
                    denominator_recovery,
                    torch.ones_like(denominator_recovery),
                )
                assert float(relative.max()) <= 1e-10


def test_numpy_forward_matches_independent_dense_without_qr():
    rng = np.random.default_rng(907)
    for size in (2, 3, 8, 21):
        bands = random_arrow_bands(rng, size)
        rhs = rng.normal(size=size)
        matrix = kinetic_mean_field._banded_to_dense_numpy(
            tuple(value.numpy() for value in bands)
        )
        expected = np.linalg.solve(matrix, rhs)
        actual, info = kinetic_mean_field._rank_one_banded_solve_numpy(
            tuple(value.numpy() for value in bands), rhs
        )
        np.testing.assert_allclose(actual, expected, rtol=2e-10, atol=2e-11)
        assert not info["qr_fallback"]
        assert np.max(info["relative_recovery_extended"]) <= 1e-10


def test_near_singular_rank_one_denominator_uses_qr_or_fails_closed():
    bands = (
        np.asarray([0.5]),
        np.asarray([-1.0, 0.0]),
        np.asarray([0.0]),
        np.asarray([-1.0, 0.5 - 1e-15]),
    )
    rhs = np.asarray([0.2, -0.1])
    try:
        solution, info = kinetic_mean_field._rank_one_banded_solve_numpy(bands, rhs)
    except RuntimeError as error:
        assert "recovery residual tolerance" in str(error)
        assert error.linear_solver_info["qr_fallback"]
    else:
        assert info["qr_fallback"]
        assert np.max(info["relative_recovery_extended"]) <= 1e-10
        dense = kinetic_mean_field._banded_to_dense_numpy(bands)
        np.testing.assert_allclose(dense @ solution, rhs, rtol=1e-8, atol=1e-8)


def test_exactly_singular_rank_one_denominator_never_returns_a_solution():
    bands = (
        np.asarray([0.5]),
        np.asarray([-1.0, 0.0]),
        np.asarray([0.0]),
        np.asarray([-1.0, 0.5]),
    )
    with pytest.raises(RuntimeError, match="recovery residual tolerance") as caught:
        kinetic_mean_field._rank_one_banded_solve_numpy(
            bands, np.asarray([1.0, -0.5])
        )
    assert caught.value.linear_solver_info["qr_fallback"]


def test_normal_single_backward_never_constructs_dense_or_calls_dense_lu(monkeypatch):
    monkeypatch.setattr(
        kinetic_mean_field,
        "_banded_to_dense_torch",
        lambda bands: (_ for _ in ()).throw(AssertionError("dense backward assembly")),
    )
    monkeypatch.setattr(
        torch.linalg,
        "lu_factor",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dense LU")),
    )
    alpha = torch.tensor(1.3, dtype=torch.float64, requires_grad=True)
    rates = torch.tensor([0.8, 1.7, 0.9], dtype=torch.float64, requires_grad=True)
    beta = torch.tensor(0.65, dtype=torch.float64, requires_grad=True)
    rho, flux, residual, diagnostics = solve_kinetic_mean_field(
        alpha, rates, beta, return_diagnostics=True
    )
    gradients = torch.autograd.grad(
        (torch.sin(rho).sum() + 0.37 * flux), (alpha, rates, beta)
    )
    assert all(bool(torch.isfinite(value).all()) for value in gradients)
    assert float(residual.abs().max()) <= 1e-10
    assert not diagnostics["backward_dense_padded_matrix_constructed"]
    assert diagnostics["forward_device"] == "cpu"
    assert diagnostics["forward_cpu_path_explicit"]
    assert diagnostics["backward_device"] == "cpu"
    assert not bool(diagnostics["backward_cpu_extended_precision"])


def test_mixed_batch_normal_backward_never_constructs_dense(monkeypatch):
    monkeypatch.setattr(
        kinetic_mean_field,
        "_banded_to_dense_torch",
        lambda bands: (_ for _ in ()).throw(AssertionError("dense backward assembly")),
    )
    lengths = [1, 2, 7, 33]
    max_length = max(lengths)
    alpha = torch.linspace(0.7, 1.4, 4, dtype=torch.float64, requires_grad=True)
    beta = torch.linspace(1.1, 0.8, 4, dtype=torch.float64, requires_grad=True)
    rates = torch.zeros(4, max_length - 1, dtype=torch.float64)
    with torch.no_grad():
        for index, length in enumerate(lengths):
            rates[index, : length - 1] = torch.linspace(
                0.5, 1.8, length - 1, dtype=torch.float64
            )
    rates.requires_grad_(True)
    rho, flux, residual = solve_kinetic_mean_field_batch(
        alpha, rates, lengths, beta
    )
    gradients = torch.autograd.grad(
        rho.square().mean() + flux.sum(), (alpha, rates, beta)
    )
    assert all(bool(torch.isfinite(value).all()) for value in gradients)
    assert float(residual.abs().max()) <= 1e-10
    for index, length in enumerate(lengths):
        assert torch.count_nonzero(gradients[1][index, length - 1 :]) == 0


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is not available")
def test_cuda_long_4096_forward_backward_and_conservation():
    device = torch.device("cuda")
    length = 4096
    generator = torch.Generator(device="cpu").manual_seed(781)
    alpha = torch.tensor(1.2, dtype=torch.float64, device=device, requires_grad=True)
    beta = torch.tensor(0.85, dtype=torch.float64, device=device, requires_grad=True)
    rates = torch.exp(
        torch.empty(length - 1, dtype=torch.float64).uniform_(-2.0, 2.0, generator=generator)
    ).to(device).requires_grad_(True)
    rho, flux, residual, diagnostics = solve_kinetic_mean_field(
        alpha, rates, beta, return_diagnostics=True
    )
    positions = torch.arange(length, dtype=torch.float64, device=device)
    objective = (torch.sin(0.013 * positions) * rho).sum() + 0.23 * flux
    gradients = torch.autograd.grad(objective, (alpha, rates, beta))
    torch.cuda.synchronize(device)
    assert rho.device.type == "cuda" and flux.device.type == "cuda"
    assert all(value.device.type == "cuda" for value in gradients)
    assert all(bool(torch.isfinite(value).all()) for value in gradients)
    assert float(residual.abs().max()) <= 1e-10
    assert float(diagnostics["backward_recovery_residual"]) <= 1e-10
    assert diagnostics["backward_device"].startswith("cuda")
    recovery_used_cpu = bool(diagnostics["backward_cpu_extended_precision"])
    strict_recovery_used = bool(
        diagnostics["backward_qr_fallback"]
        or diagnostics["backward_refinement_steps"] > 0
    )
    assert recovery_used_cpu == strict_recovery_used
    local_flux = torch.cat((
        (alpha * (1.0 - rho[:1])),
        rates * rho[:-1] * (1.0 - rho[1:]),
        beta * rho[-1:],
    ))
    assert float((local_flux - flux).abs().max() / flux) <= 1e-10


@pytest.mark.parametrize("device", ["cpu", pytest.param("cuda", marks=pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is not available"))])
def test_batched_banded_givens_qr_matches_independent_dense(device):
    rng = np.random.default_rng(119)
    for size in (2, 3, 8, 21):
        band_rows = [random_arrow_bands(rng, size, device) for _ in range(3)]
        bands = tuple(torch.stack([row[index] for row in band_rows]) for index in range(4))
        rhs = torch.as_tensor(
            rng.normal(size=(3, size, 2)), dtype=torch.float64, device=device
        )
        for transpose in (False, True):
            actual = kinetic_mean_field._banded_qr_once_torch(
                bands, rhs, transpose=transpose
            )
            for batch_index in range(3):
                matrix = kinetic_mean_field._banded_to_dense_torch(band_rows[batch_index])
                expected = torch.linalg.solve(
                    matrix.transpose(0, 1) if transpose else matrix,
                    rhs[batch_index],
                )
                torch.testing.assert_close(
                    actual[batch_index], expected, rtol=2e-10, atol=2e-10
                )


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is not available")
def test_triton_kernels_satisfy_independent_recovery_on_random_arrows():
    pytest.importorskip("triton")
    from codonflow.models import kinetic_banded_cuda

    rng = np.random.default_rng(818)
    for size in (2, 3, 8):
        bands = random_arrow_bands(rng, size, "cuda")
        bands = tuple(value.unsqueeze(0) for value in bands)
        rhs = torch.as_tensor(
            rng.normal(size=(1, size)), dtype=torch.float64, device="cuda"
        )
        for transpose in (False, True):
            rank_solution, _ = kinetic_banded_cuda.rank_one(
                bands, rhs, transpose=transpose
            )
            qr_solution = kinetic_banded_cuda.qr(bands, rhs, transpose=transpose)
            for solution in (rank_solution, qr_solution):
                recovery = kinetic_mean_field._banded_matvec_torch(
                    bands, solution, transpose=transpose
                ) - rhs
                denominator = kinetic_mean_field._banded_matvec_torch(
                    tuple(value.abs() for value in bands),
                    solution.abs(),
                    transpose=transpose,
                ) + rhs.abs()
                relative = recovery.abs() / torch.where(
                    denominator > 0, denominator, torch.ones_like(denominator)
                )
                assert float(relative.max()) <= 1e-10


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is not available")
def test_triton_errors_are_recorded_and_use_torch_cuda_fallback(monkeypatch):
    pytest.importorskip("triton")
    from codonflow.models import kinetic_banded_cuda

    bands = random_arrow_bands(np.random.default_rng(19), 4, "cuda")
    bands = tuple(value.unsqueeze(0) for value in bands)
    rhs = torch.ones(1, 4, dtype=torch.float64, device="cuda")
    expected, expected_denominator = kinetic_mean_field._banded_rank_one_solve_torch(
        bands, rhs, transpose=True
    )
    monkeypatch.setattr(
        kinetic_banded_cuda,
        "rank_one",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("synthetic Triton failure")),
    )
    diagnostics = {}
    actual, denominator = kinetic_mean_field._banded_rank_one_solve_cuda(
        bands, rhs, transpose=True, diagnostics=diagnostics
    )
    torch.testing.assert_close(actual, expected)
    torch.testing.assert_close(denominator, expected_denominator)
    assert diagnostics["backward_cuda_kernel_backend"] == "torch_after_triton_error"
    assert "synthetic Triton failure" in diagnostics["backward_cuda_accelerator_error"]
    assert actual.device.type == "cuda"


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is not available")
def test_p0_triton_rank_one_transpose_batch32_forced_pivot_dense_regression():
    pytest.importorskip("triton")
    from codonflow.models import kinetic_banded_cuda

    rng = np.random.default_rng(20261127)
    size, batch = 8, 32
    bands = tuple(torch.stack([
        random_arrow_bands(rng, size, "cuda")[index] for _ in range(batch)
    ]) for index in range(4))
    with torch.no_grad():
        bands[0][:] = 2.0
        bands[1][:, :-1] = 0.05
        bands[1][:, -1] = 0.0
        bands[2][:, :-1] = 0.2
        bands[2][:, -1] = 0.0
        bands[3][:] = 0.02
    rhs = torch.as_tensor(
        rng.normal(size=(batch, size)), dtype=torch.float64, device="cuda"
    )
    expected, expected_denominator = kinetic_mean_field._banded_rank_one_solve_torch(
        bands, rhs, transpose=True
    )
    for index in range(batch):
        dense = kinetic_mean_field._banded_to_dense_torch(
            tuple(value[index] for value in bands)
        )
        torch.testing.assert_close(
            expected[index], torch.linalg.solve(dense.T, rhs[index]),
            rtol=1e-8, atol=1e-8,
        )
    for _ in range(16):
        actual, denominator = kinetic_banded_cuda.rank_one(bands, rhs, transpose=True)
        torch.cuda.synchronize()
        torch.testing.assert_close(actual, expected, rtol=1e-8, atol=1e-8)
        torch.testing.assert_close(denominator, expected_denominator, rtol=1e-8, atol=1e-8)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is not available")
def test_p1_triton_rank_one_and_qr_layout_and_long_regression():
    pytest.importorskip("triton")
    from codonflow.models import kinetic_banded_cuda

    rng = np.random.default_rng(20261128)
    size, batch = 8, 2
    contiguous = tuple(torch.stack([
        random_arrow_bands(rng, size, "cuda")[index] for _ in range(batch)
    ]) for index in range(4))
    rhs = torch.as_tensor(
        rng.normal(size=(batch, size)), dtype=torch.float64, device="cuda"
    )
    for layout in ("transposed", "padded"):
        if layout == "transposed":
            bands = tuple(
                torch.empty((value.shape[1], value.shape[0]), dtype=value.dtype, device="cuda").T.copy_(value)
                for value in contiguous
            )
            laid_out_rhs = torch.empty((size, batch), dtype=rhs.dtype, device="cuda").T.copy_(rhs)
        else:
            bands = tuple(
                torch.empty((value.shape[0], value.shape[1] + 3), dtype=value.dtype, device="cuda")[:, :-3].copy_(value)
                for value in contiguous
            )
            laid_out_rhs = torch.empty((batch, size + 3), dtype=rhs.dtype, device="cuda")[:, :-3].copy_(rhs)
        for transpose in (False, True):
            expected, expected_denominator = kinetic_mean_field._banded_rank_one_solve_torch(
                contiguous, rhs, transpose=transpose
            )
            actual, denominator = kinetic_banded_cuda.rank_one(bands, laid_out_rhs, transpose=transpose)
            qr_actual = kinetic_banded_cuda.qr(bands, laid_out_rhs, transpose=transpose)
            qr_expected = kinetic_mean_field._banded_qr_once_torch(contiguous, rhs, transpose=transpose)
            torch.cuda.synchronize()
            torch.testing.assert_close(actual, expected, rtol=1e-9, atol=1e-9)
            torch.testing.assert_close(denominator, expected_denominator, rtol=1e-9, atol=1e-9)
            torch.testing.assert_close(qr_actual, qr_expected, rtol=1e-9, atol=1e-9)

    for long_batch in (1, 32):
        for transpose in (False, True):
            bands = tuple(torch.stack([
                random_arrow_bands(rng, 1488, "cuda")[index] for _ in range(long_batch)
            ]) for index in range(4))
            long_rhs = torch.as_tensor(
                rng.normal(size=(long_batch, 1488)), dtype=torch.float64, device="cuda"
            )
            expected, expected_denominator = kinetic_mean_field._banded_rank_one_solve_torch(
                bands, long_rhs, transpose=transpose
            )
            actual, denominator = kinetic_banded_cuda.rank_one(bands, long_rhs, transpose=transpose)
            qr_actual = kinetic_banded_cuda.qr(bands, long_rhs, transpose=transpose)
            qr_expected = kinetic_mean_field._banded_qr_once_torch(bands, long_rhs, transpose=transpose)
            torch.cuda.synchronize()
            torch.testing.assert_close(actual, expected, rtol=1e-8, atol=1e-8)
            torch.testing.assert_close(denominator, expected_denominator, rtol=1e-8, atol=1e-8)
            torch.testing.assert_close(qr_actual, qr_expected, rtol=1e-8, atol=1e-8)
