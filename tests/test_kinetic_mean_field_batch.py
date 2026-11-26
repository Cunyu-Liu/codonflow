"""Synthetic tests for padded batched kinetic mean-field solves."""
import numpy as np
import pytest
import torch

import codonflow.models.kinetic_mean_field as kinetic_mean_field
from codonflow.models.kinetic_mean_field import (
    solve_kinetic_mean_field,
    solve_kinetic_mean_field_batch,
)


def test_batch_of_one_matches_single_sample_forward_and_backward():
    alpha = torch.tensor([1.3], dtype=torch.float64, requires_grad=True)
    k = torch.tensor([[0.8, 1.7, 1.1]], dtype=torch.float64, requires_grad=True)
    beta = torch.tensor([0.9], dtype=torch.float64, requires_grad=True)
    single_alpha = alpha.detach().clone()[0].requires_grad_(True)
    single_k = k.detach().clone()[0].requires_grad_(True)
    single_beta = beta.detach().clone()[0].requires_grad_(True)

    rho, flux, residual = solve_kinetic_mean_field_batch(alpha, k, [4], beta)
    single_rho, single_flux, single_residual = solve_kinetic_mean_field(
        single_alpha, single_k, single_beta
    )

    assert rho.shape == (1, 4)
    assert flux.shape == (1,)
    assert residual.shape == (1, 5)
    assert rho.dtype == flux.dtype == residual.dtype == torch.float64
    assert not residual.requires_grad
    torch.testing.assert_close(rho[0], single_rho, rtol=0.0, atol=0.0)
    torch.testing.assert_close(flux[0], single_flux, rtol=0.0, atol=0.0)
    torch.testing.assert_close(residual[0], single_residual, rtol=0.0, atol=0.0)

    weights = torch.tensor([0.2, -0.4, 0.7, 0.3], dtype=torch.float64)
    batch_objective = (weights * rho[0]).sum() + 0.37 * flux[0]
    single_objective = (weights * single_rho).sum() + 0.37 * single_flux
    batch_gradients = torch.autograd.grad(batch_objective, (alpha, k, beta))
    single_gradients = torch.autograd.grad(single_objective, (single_alpha, single_k, single_beta))
    torch.testing.assert_close(batch_gradients[0][0], single_gradients[0])
    torch.testing.assert_close(batch_gradients[1][0], single_gradients[1])
    torch.testing.assert_close(batch_gradients[2][0], single_gradients[2])


def test_variable_lengths_match_independent_solves_and_zero_padding():
    alpha = torch.tensor([1.3, 0.7, 1.1, 0.9], dtype=torch.float64)
    k = torch.tensor(
        [
            [0.8, 1.7, 1.1],
            [0.0, 0.0, 0.0],
            [1.4, 0.6, 0.0],
            [0.5, 0.0, 0.0],
        ],
        dtype=torch.float64,
    )
    lengths = [4, 1, 3, 2]
    beta = torch.tensor([0.9, 1.5, 0.8, 1.2], dtype=torch.float64)

    rho, flux, residual = solve_kinetic_mean_field_batch(alpha, k, lengths, beta)

    assert rho.shape == (4, 4)
    assert flux.shape == (4,)
    assert residual.shape == (4, 5)
    for index, length in enumerate(lengths):
        expected_rho, expected_flux, expected_residual = solve_kinetic_mean_field(
            alpha[index], k[index, : length - 1], beta[index]
        )
        torch.testing.assert_close(rho[index, :length], expected_rho)
        torch.testing.assert_close(flux[index], expected_flux)
        torch.testing.assert_close(residual[index, : length + 1], expected_residual)
        assert torch.count_nonzero(rho[index, length:]) == 0
        assert torch.count_nonzero(residual[index, length + 1 :]) == 0


def test_batched_implicit_gradients_match_central_finite_differences():
    alpha = torch.tensor([1.3, 0.7, 1.1], dtype=torch.float64, requires_grad=True)
    k = torch.tensor(
        [[0.8, 1.7, 1.1], [1.4, 0.6, 0.0], [0.5, 0.0, 0.0]],
        dtype=torch.float64,
        requires_grad=True,
    )
    lengths = [4, 3, 2]
    beta = torch.tensor([0.9, 1.5, 0.8], dtype=torch.float64, requires_grad=True)
    rho_weights = torch.tensor(
        [
            [0.2, -0.4, 0.7, 0.3],
            [-0.1, 0.5, 0.2, 0.0],
            [0.6, -0.3, 0.0, 0.0],
        ],
        dtype=torch.float64,
    )
    flux_weights = torch.tensor([0.37, -0.2, 0.41], dtype=torch.float64)

    def objective_value(alpha_value, k_value, beta_value):
        rho, flux, _ = solve_kinetic_mean_field_batch(alpha_value, k_value, lengths, beta_value)
        return (rho_weights * rho).sum() + (flux_weights * flux).sum()

    objective = objective_value(alpha, k, beta)
    gradients = torch.autograd.grad(objective, (alpha, k, beta))
    assert torch.count_nonzero(gradients[1][1, 2]) == 0
    assert torch.count_nonzero(gradients[1][2, 1:]) == 0

    alpha_value = alpha.detach()
    k_value = k.detach()
    beta_value = beta.detach()
    epsilon = 1e-5

    numeric_alpha = []
    numeric_k = np.zeros_like(k_value.numpy())
    numeric_beta = []
    for index in range(alpha_value.numel()):
        plus = alpha_value.clone()
        minus = alpha_value.clone()
        plus[index] += epsilon
        minus[index] -= epsilon
        with torch.no_grad():
            numeric_alpha.append(float(
                (objective_value(plus, k_value, beta_value)
                 - objective_value(minus, k_value, beta_value)) / (2.0 * epsilon)
            ))
        plus_beta = beta_value.clone()
        minus_beta = beta_value.clone()
        plus_beta[index] += epsilon
        minus_beta[index] -= epsilon
        with torch.no_grad():
            numeric_beta.append(float(
                (objective_value(alpha_value, k_value, plus_beta)
                 - objective_value(alpha_value, k_value, minus_beta)) / (2.0 * epsilon)
            ))
        for internal_index in range(lengths[index] - 1):
            plus_k = k_value.clone()
            minus_k = k_value.clone()
            plus_k[index, internal_index] += epsilon
            minus_k[index, internal_index] -= epsilon
            with torch.no_grad():
                numeric_k[index, internal_index] = float(
                    (objective_value(alpha_value, plus_k, beta_value)
                     - objective_value(alpha_value, minus_k, beta_value)) / (2.0 * epsilon)
                )

    np.testing.assert_allclose(gradients[0].numpy(), numeric_alpha, rtol=1e-6, atol=1e-8)
    np.testing.assert_allclose(gradients[1].numpy(), numeric_k, rtol=1e-6, atol=1e-8)
    np.testing.assert_allclose(gradients[2].numpy(), numeric_beta, rtol=1e-6, atol=1e-8)


@pytest.mark.parametrize(
    "alpha,k,lengths,beta,match",
    [
        (1.0, [[1.0]], [2], 1.0, "one-dimensional batch vectors"),
        ([1.0], [1.0], [2], [1.0], "two-dimensional"),
        ([1.0, 1.0], [[1.0], [1.0]], [2], [1.0, 1.0], "one integer per batch sample"),
        ([1.0], [[1.0]], [2.0], [1.0], "integers"),
        ([1.0], [[1.0]], [0], [1.0], "between 1 and"),
        ([1.0], [[1.0]], [3], [1.0], "between 1 and"),
        ([1.0], [[1.0, 0.0]], [1], [1.0], "max\\(lengths\\)"),
        ([1.0], [[0.0]], [2], [1.0], "strictly positive"),
        ([1.0], [[1.0, np.nan]], [3], [1.0], "finite"),
        ([0.0], [[1.0]], [2], [1.0], "strictly positive"),
        ([1.0], [[1.0]], [2], [np.inf], "strictly positive"),
    ],
)
def test_batch_rejects_invalid_shapes_lengths_and_rates(alpha, k, lengths, beta, match):
    with pytest.raises(ValueError, match=match):
        solve_kinetic_mean_field_batch(alpha, k, lengths, beta)


def test_batch_rejects_invalid_solver_controls():
    with pytest.raises(ValueError, match="root_tolerance"):
        solve_kinetic_mean_field_batch([1.0], [[1.0]], [2], [1.0], root_tolerance=0.0)
    with pytest.raises(ValueError, match="residual_tolerance"):
        solve_kinetic_mean_field_batch([1.0], [[1.0]], [2], [1.0], residual_tolerance=-1.0)
    with pytest.raises(ValueError, match="maxfev"):
        solve_kinetic_mean_field_batch([1.0], [[1.0]], [2], [1.0], maxfev=1.5)


def test_batch_nonconvergence_is_not_returned_as_a_success(monkeypatch):
    monkeypatch.setattr(kinetic_mean_field, "solve_ivp", lambda *args, **kwargs: type("FailedIntegration", (), {"success": False, "message": "did not converge", "y": np.zeros((4, 1))})())
    with pytest.raises(RuntimeError, match="batch sample 0.*did not converge"):
        solve_kinetic_mean_field_batch(
            [1.3], [[0.8, 1.7, 1.1]], [4], [0.9], maxfev=1
        )


def test_scaled_root_retry_recovers_physical_solution_with_strict_residual():
    alpha = torch.tensor([0.5758134585874211], dtype=torch.float64, requires_grad=True)
    k = torch.tensor(
        [[
            0.57581346, 0.49779555, 0.87104251, 0.84131219,
            0.98747267, 1.11069650, 0.81354675, 1.46932356,
            1.35651825, 1.12130915, 0.18789925,
        ]],
        dtype=torch.float64,
        requires_grad=True,
    )
    beta = torch.tensor([0.8173197878778484], dtype=torch.float64, requires_grad=True)

    rho, flux, residual, diagnostics = solve_kinetic_mean_field_batch(
        alpha, k, [12], beta, return_diagnostics=True
    )

    assert bool(((rho >= 0.0) & (rho <= 1.0)).all())
    assert flux > 0.0
    assert residual.abs().max() < 1e-10
    gradients = torch.autograd.grad(rho.sum() + flux.sum(), (alpha, k, beta))
    assert all(bool(torch.isfinite(gradient).all()) for gradient in gradients)
    assert diagnostics["backward_recovery_residual"] <= 1e-10


def test_long_half_density_batch_backward_is_stable_and_audited():
    lengths = [128, 65, 1]
    max_length = max(lengths)
    alpha = torch.ones(3, dtype=torch.float64, requires_grad=True)
    beta = torch.ones(3, dtype=torch.float64, requires_grad=True)
    k = torch.zeros((3, max_length - 1), dtype=torch.float64, requires_grad=True)
    with torch.no_grad():
        for index, length in enumerate(lengths):
            k[index, : length - 1] = 2.0

    rho, flux, residual, diagnostics = solve_kinetic_mean_field_batch(
        alpha, k, lengths, beta, return_diagnostics=True
    )

    for index, length in enumerate(lengths):
        torch.testing.assert_close(
            rho[index, :length],
            torch.full((length,), 0.5, dtype=torch.float64),
            rtol=1e-10,
            atol=1e-12,
        )
        torch.testing.assert_close(
            flux[index], torch.tensor(0.5, dtype=torch.float64), rtol=1e-10, atol=1e-12
        )
    assert residual.abs().max() < 1e-10
    condition = diagnostics["jacobian_condition_number"]
    assert condition.shape == (3,)
    assert bool(torch.isfinite(condition).all()) and bool((condition > 1.0).all())
    assert bool(torch.isnan(diagnostics["backward_recovery_residual"]).all())

    rho_weights = torch.linspace(-0.4, 0.4, max_length, dtype=torch.float64).repeat(3, 1)
    flux_weights = torch.tensor([0.2, -0.3, 0.4], dtype=torch.float64)
    objective = (rho_weights * rho).sum() + (flux_weights * flux).sum()
    gradients = torch.autograd.grad(objective, (alpha, k, beta))

    assert all(bool(torch.isfinite(gradient).all()) for gradient in gradients)
    for index, length in enumerate(lengths):
        assert torch.count_nonzero(gradients[1][index, length - 1 :]) == 0
    recovery = diagnostics["backward_recovery_residual"]
    assert bool(torch.isfinite(recovery).all())
    assert bool((recovery <= 1e-10).all())

    single_alpha = alpha.detach().clone()[0].requires_grad_(True)
    single_k = k.detach().clone()[0].requires_grad_(True)
    single_beta = beta.detach().clone()[0].requires_grad_(True)
    single_rho, single_flux, _ = solve_kinetic_mean_field(
        single_alpha, single_k, single_beta
    )
    single_objective = (
        (rho_weights[0] * single_rho).sum() + flux_weights[0] * single_flux
    )
    single_gradients = torch.autograd.grad(
        single_objective, (single_alpha, single_k, single_beta)
    )
    torch.testing.assert_close(gradients[0][0], single_gradients[0], rtol=1e-9, atol=1e-11)
    torch.testing.assert_close(gradients[1][0], single_gradients[1], rtol=1e-9, atol=1e-11)
    torch.testing.assert_close(gradients[2][0], single_gradients[2], rtol=1e-9, atol=1e-11)


def test_extreme_legal_rate_scales_have_stable_density_gradients():
    length = 32
    scales = torch.tensor([1e-8, 1e8], dtype=torch.float64)
    alpha = scales.clone().requires_grad_(True)
    beta = scales.clone().requires_grad_(True)
    k = scales[:, None].expand(-1, length - 1).clone().requires_grad_(True)

    rho, flux, residual, diagnostics = solve_kinetic_mean_field_batch(
        alpha, k, [length, length], beta, return_diagnostics=True
    )

    torch.testing.assert_close(rho[0], rho[1], rtol=1e-9, atol=1e-12)
    torch.testing.assert_close(flux[1] / flux[0], torch.tensor(1e16, dtype=torch.float64))
    assert residual.abs().max() < 1e-10
    assert diagnostics["jacobian_condition_number"][0] > 1e6

    weights = torch.linspace(-0.3, 0.5, length, dtype=torch.float64)
    gradients = torch.autograd.grad((weights * rho).sum(), (alpha, k, beta))
    assert all(bool(torch.isfinite(gradient).all()) for gradient in gradients)
    for gradient in gradients:
        torch.testing.assert_close(
            gradient[1] * 1e16, gradient[0], rtol=1e-6, atol=1e-8
        )
    recovery = diagnostics["backward_recovery_residual"]
    assert bool(torch.isfinite(recovery).all()) and bool((recovery <= 1e-10).all())


def test_single_sample_opt_in_diagnostics_preserves_legacy_interface():
    legacy_outputs = solve_kinetic_mean_field(1.0, [2.0, 2.0], 1.0)
    assert len(legacy_outputs) == 3

    alpha = torch.tensor(1.0, dtype=torch.float64, requires_grad=True)
    k = torch.tensor([2.0, 2.0], dtype=torch.float64, requires_grad=True)
    beta = torch.tensor(1.0, dtype=torch.float64, requires_grad=True)
    rho, flux, _, diagnostics = solve_kinetic_mean_field(
        alpha, k, beta, return_diagnostics=True
    )
    assert diagnostics["jacobian_condition_number"].ndim == 0
    assert torch.isnan(diagnostics["backward_recovery_residual"])
    torch.autograd.grad(rho.sum() + flux, (alpha, k, beta))
    assert diagnostics["backward_recovery_residual"] <= 1e-10


def test_backward_refinement_repairs_deterministic_1070e_10_residual(monkeypatch):
    alpha = torch.tensor([1.0], dtype=torch.float64, requires_grad=True)
    k = torch.empty((1, 0), dtype=torch.float64, requires_grad=True)
    beta = torch.tensor([1.0], dtype=torch.float64, requires_grad=True)
    rho, flux, _, diagnostics = solve_kinetic_mean_field_batch(
        alpha, k, [1], beta, return_diagnostics=True
    )
    real_lu_solve = torch.linalg.lu_solve
    target_recovery = 1.070e-10
    perturbation = target_recovery * 1.2 / (1.0 - target_recovery)
    solve_calls = 0

    def perturb_initial_solve(factor, pivots, rhs):
        nonlocal solve_calls
        solve_calls += 1
        result = real_lu_solve(factor, pivots, rhs)
        if solve_calls == 1:
            result = result.clone()
            result[0, 0, 0] -= perturbation
        return result

    monkeypatch.setattr(torch.linalg, "lu_solve", perturb_initial_solve)
    gradients = torch.autograd.grad(rho.sum() + 0.2 * flux.sum(), (alpha, k, beta))

    assert perturbation / (1.2 + perturbation) == pytest.approx(target_recovery)
    assert solve_calls == 2
    assert diagnostics["backward_refinement_steps"].item() == 1
    assert not diagnostics["backward_qr_fallback"].item()
    assert all(bool(torch.isfinite(gradient).all()) for gradient in gradients)
    assert diagnostics["backward_recovery_residual"] <= 1e-10


def test_backward_refinement_can_require_three_correction_steps(monkeypatch):
    alpha = torch.tensor([1.0], dtype=torch.float64, requires_grad=True)
    k = torch.empty((1, 0), dtype=torch.float64, requires_grad=True)
    beta = torch.tensor([1.0], dtype=torch.float64, requires_grad=True)
    rho, flux, _, diagnostics = solve_kinetic_mean_field_batch(
        alpha, k, [1], beta, return_diagnostics=True
    )
    real_lu_solve = torch.linalg.lu_solve
    solve_calls = 0

    def delay_convergence(factor, pivots, rhs):
        nonlocal solve_calls
        solve_calls += 1
        result = real_lu_solve(factor, pivots, rhs)
        if solve_calls == 1:
            result = result.clone()
            result[0, 0, 0] -= 1e-6
        elif solve_calls in (2, 3):
            result = torch.zeros_like(rhs)
        return result

    monkeypatch.setattr(torch.linalg, "lu_solve", delay_convergence)
    gradients = torch.autograd.grad(rho.sum() + 0.2 * flux.sum(), (alpha, k, beta))

    assert solve_calls == 4
    assert diagnostics["backward_refinement_steps"].item() == 3
    assert not diagnostics["backward_qr_fallback"].item()
    assert diagnostics["backward_recovery_residual"].item() <= 1e-10
    assert all(bool(torch.isfinite(gradient).all()) for gradient in gradients)


def test_persistent_lu_failure_uses_qr_fallback(monkeypatch):
    alpha = torch.tensor([1.0], dtype=torch.float64, requires_grad=True)
    k = torch.tensor([[2.0, 2.0]], dtype=torch.float64, requires_grad=True)
    beta = torch.tensor([1.0], dtype=torch.float64, requires_grad=True)
    rho, flux, _, diagnostics = solve_kinetic_mean_field_batch(
        alpha, k, [3], beta, return_diagnostics=True
    )
    solve_calls = 0

    def fail_every_lu_solve(factor, pivots, rhs):
        nonlocal solve_calls
        solve_calls += 1
        return torch.zeros_like(rhs)

    monkeypatch.setattr(torch.linalg, "lu_solve", fail_every_lu_solve)
    gradients = torch.autograd.grad(rho.sum() + flux.sum(), (alpha, k, beta))

    assert solve_calls == 5
    assert diagnostics["backward_refinement_steps"].item() == 4
    assert diagnostics["backward_qr_fallback"].item()
    assert diagnostics["backward_recovery_residual"].item() <= 1e-10
    assert all(bool(torch.isfinite(gradient).all()) for gradient in gradients)


def test_near_zero_component_denominator_uses_extended_refinement(monkeypatch):
    jacobian = torch.diag(torch.tensor([1e-300, 1.0], dtype=torch.float64))
    output_gradient = torch.tensor([1e-300, 0.0], dtype=torch.float64)
    diagnostics = {
        "backward_recovery_residual": torch.tensor(float("nan"), dtype=torch.float64),
        "backward_refinement_steps": torch.tensor(0, dtype=torch.int64),
        "backward_qr_fallback": torch.tensor(False, dtype=torch.bool),
    }
    real_lu_solve = torch.linalg.lu_solve
    solve_calls = 0

    def perturb_initial_solve(factor, pivots, rhs):
        nonlocal solve_calls
        solve_calls += 1
        if solve_calls == 1:
            return torch.zeros_like(rhs)
        return real_lu_solve(factor, pivots, rhs)

    monkeypatch.setattr(torch.linalg, "lu_solve", perturb_initial_solve)
    multiplier = kinetic_mean_field._solve_adjoint_system(
        jacobian, output_gradient, 1e-10, diagnostics
    )

    torch.testing.assert_close(
        multiplier, torch.tensor([1.0, 0.0], dtype=torch.float64), rtol=0.0, atol=0.0
    )
    _, denominator, relative = kinetic_mean_field._extended_backward_recovery(
        jacobian.transpose(0, 1), multiplier, output_gradient
    )
    assert denominator[0] > 0 and denominator[0] < 1e-200
    assert np.max(relative) <= 1e-10
    assert diagnostics["backward_refinement_steps"].item() == 1


def test_mixed_batch_refines_only_the_failed_sample(monkeypatch):
    jacobian = torch.eye(2, dtype=torch.float64).repeat(3, 1, 1)
    output_gradient = torch.tensor(
        [[1.0, 0.2], [0.3, -0.7], [0.5, 0.4]], dtype=torch.float64
    )
    diagnostics = {
        "jacobian_condition_number": torch.tensor([2.0, 3.0, 4.0]),
        "backward_recovery_residual": torch.full((3,), float("nan")),
        "backward_refinement_steps": torch.zeros(3, dtype=torch.int64),
        "backward_qr_fallback": torch.zeros(3, dtype=torch.bool),
    }
    real_lu_solve = torch.linalg.lu_solve
    solve_calls = 0

    def perturb_middle_sample(factor, pivots, rhs):
        nonlocal solve_calls
        solve_calls += 1
        result = real_lu_solve(factor, pivots, rhs)
        if solve_calls == 1:
            result = result.clone()
            result[1, 0, 0] += 1e-5
        return result

    monkeypatch.setattr(torch.linalg, "lu_solve", perturb_middle_sample)
    multiplier = kinetic_mean_field._solve_adjoint_system(
        jacobian, output_gradient, 1e-10, diagnostics
    )

    torch.testing.assert_close(multiplier, output_gradient, rtol=0.0, atol=0.0)
    assert diagnostics["backward_refinement_steps"].tolist() == [0, 1, 0]
    assert diagnostics["backward_qr_fallback"].tolist() == [False, False, False]
    assert bool((diagnostics["backward_recovery_residual"] <= 1e-10).all())
    assert solve_calls == 2


def test_permanent_backward_failure_is_not_silent_and_has_snapshot_context(monkeypatch):
    alpha = torch.tensor([1.0], dtype=torch.float64, requires_grad=True)
    k = torch.tensor([[2.0, 2.0]], dtype=torch.float64, requires_grad=True)
    beta = torch.tensor([1.0], dtype=torch.float64, requires_grad=True)
    rho, flux, _, diagnostics = solve_kinetic_mean_field_batch(
        alpha, k, [3], beta, return_diagnostics=True
    )
    solve_calls = 0
    qr_calls = 0

    def fail_every_lu_solve(factor, pivots, rhs):
        nonlocal solve_calls
        solve_calls += 1
        return torch.zeros_like(rhs)

    def fail_every_qr_solve(matrix, rhs):
        nonlocal qr_calls
        qr_calls += 1
        return torch.zeros_like(rhs)

    monkeypatch.setattr(torch.linalg, "lu_solve", fail_every_lu_solve)
    monkeypatch.setattr(kinetic_mean_field, "_backward_qr_solve", fail_every_qr_solve)

    with pytest.raises(RuntimeError, match="recovery residual tolerance.*4 LU and 4 QR") as caught:
        torch.autograd.grad(rho.sum() + flux.sum(), (alpha, k, beta))
    assert solve_calls == 5
    assert qr_calls == 5
    assert bool(torch.isfinite(diagnostics["backward_recovery_residual"]).all())
    assert bool((diagnostics["backward_recovery_residual"] > 1e-10).all())
    assert diagnostics["backward_refinement_steps"].item() == 8
    assert diagnostics["backward_qr_fallback"].item()
    context = caught.value.backward_failures[0]
    assert context["batch_index"] == 0
    assert context["jacobian_condition_number"] == pytest.approx(2.613125929752753)
    assert context["refinement_steps"] == 8 and context["qr_fallback"]
    assert context["recovery_extended"].dtype == np.longdouble
    assert context["denominator_extended"].dtype == np.longdouble
    assert np.max(context["relative_recovery_extended"]) > 1e-10
    assert "jacobian_transpose" in caught.value.backward_snapshot_fields
    assert "output_gradient" in caught.value.backward_snapshot_fields


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is not available")
def test_cuda_batch_backward_matches_cpu_and_keeps_diagnostics_on_device():
    lengths = [32, 16]
    scales = torch.tensor([1e-8, 1e8], dtype=torch.float64)
    weights = torch.linspace(-0.2, 0.4, max(lengths), dtype=torch.float64)

    def run(device):
        device_scales = scales.to(device)
        alpha = device_scales.clone().requires_grad_(True)
        beta = device_scales.clone().requires_grad_(True)
        k = torch.zeros((2, max(lengths) - 1), dtype=torch.float64, device=device)
        with torch.no_grad():
            for index, length in enumerate(lengths):
                k[index, : length - 1] = device_scales[index]
        k.requires_grad_(True)
        rho, flux, _, diagnostics = solve_kinetic_mean_field_batch(
            alpha, k, torch.tensor(lengths, device=device), beta, return_diagnostics=True
        )
        objective = (weights.to(device) * rho).sum() + (flux / device_scales).sum()
        gradients = torch.autograd.grad(objective, (alpha, k, beta))
        return (rho, flux, *gradients), diagnostics

    cpu_outputs, _ = run(torch.device("cpu"))
    cuda_outputs, cuda_diagnostics = run(torch.device("cuda"))
    for cuda_output, cpu_output in zip(cuda_outputs, cpu_outputs):
        torch.testing.assert_close(cuda_output.cpu(), cpu_output, rtol=1e-8, atol=1e-8)
    assert cuda_diagnostics["jacobian_condition_number"].device.type == "cuda"
    assert cuda_diagnostics["backward_recovery_residual"].device.type == "cuda"
    assert bool((cuda_diagnostics["backward_recovery_residual"] <= 1e-10).all())


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is not available")
def test_cuda_persistent_lu_failure_uses_cuda_qr(monkeypatch):
    device = torch.device("cuda")
    jacobian = torch.eye(3, dtype=torch.float64, device=device).unsqueeze(0)
    output_gradient = torch.tensor([[0.3, -0.7, 0.5]], dtype=torch.float64, device=device)
    diagnostics = {
        "jacobian_condition_number": torch.ones(1, dtype=torch.float64, device=device),
        "backward_recovery_residual": torch.full((1,), float("nan"), device=device),
        "backward_refinement_steps": torch.zeros(1, dtype=torch.int64, device=device),
        "backward_qr_fallback": torch.zeros(1, dtype=torch.bool, device=device),
    }
    real_qr_solve = kinetic_mean_field._backward_qr_solve
    qr_devices = []

    def record_qr_device(matrix, rhs):
        qr_devices.append(matrix.device)
        assert matrix.device.type == "cuda" and rhs.device.type == "cuda"
        return real_qr_solve(matrix, rhs)

    monkeypatch.setattr(torch.linalg, "lu_solve", lambda factor, pivots, rhs: torch.zeros_like(rhs))
    monkeypatch.setattr(kinetic_mean_field, "_backward_qr_solve", record_qr_device)
    multiplier = kinetic_mean_field._solve_adjoint_system(
        jacobian, output_gradient, 1e-10, diagnostics
    )

    torch.testing.assert_close(multiplier, output_gradient, rtol=1e-12, atol=1e-12)
    assert multiplier.device.type == "cuda"
    assert qr_devices and all(device.type == "cuda" for device in qr_devices)
    assert diagnostics["backward_qr_fallback"].item()
    assert diagnostics["backward_refinement_steps"].item() == 4
    assert diagnostics["backward_recovery_residual"].item() <= 1e-10


def test_long_heterogeneous_fallback_and_gradient():
    torch.manual_seed(913)
    length = 512
    alpha = torch.tensor([1.3], dtype=torch.float64, requires_grad=True)
    beta = torch.tensor([0.9], dtype=torch.float64, requires_grad=True)
    rates = torch.exp(torch.empty(1, length - 1, dtype=torch.float64).uniform_(-3.0, 3.0))
    rates.requires_grad_()
    rho, flux, residual = solve_kinetic_mean_field_batch(alpha, rates, torch.tensor([length]), beta)
    assert rho.shape == (1, length)
    assert bool(torch.isfinite(rho).all())
    assert float(residual.abs().max()) < 1e-10
    (rho.square().mean() + flux).backward()
    assert bool(torch.isfinite(alpha.grad))
    assert bool(torch.isfinite(beta.grad))
    assert bool(torch.isfinite(rates.grad).all())


def test_extreme_long_rates_remain_fail_closed():
    torch.manual_seed(917)
    length = 256
    alpha = torch.tensor([1e-4], dtype=torch.float64)
    beta = torch.tensor([1e4], dtype=torch.float64)
    rates = torch.logspace(-8, 8, length - 1, dtype=torch.float64).unsqueeze(0)
    try:
        rho, flux, residual = solve_kinetic_mean_field_batch(alpha, rates, torch.tensor([length]), beta)
    except RuntimeError:
        return
    assert bool(torch.isfinite(rho).all())
    assert float(residual.abs().max()) < 1e-10
