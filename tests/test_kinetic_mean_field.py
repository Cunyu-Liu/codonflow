"""Targeted numerical tests for the deterministic kinetic mean-field solve."""
import math

import numpy as np
import pytest
import torch

import codonflow.models.kinetic_mean_field as kinetic_mean_field
from codonflow.models.kinetic_mean_field import solve_kinetic_mean_field


def test_half_density_solution_matches_the_exact_boundary_rate_case():
    rate = 2.0
    length = 5
    rho, flux, normalized_residual = solve_kinetic_mean_field(
        rate / 2.0, torch.full((length - 1,), rate, dtype=torch.float64), rate / 2.0
    )

    assert rho.dtype == torch.float64
    assert rho.shape == (length,)
    assert flux.shape == ()
    assert normalized_residual.shape == (length + 1,)
    torch.testing.assert_close(rho, torch.full((length,), 0.5, dtype=torch.float64))
    torch.testing.assert_close(flux, torch.tensor(rate / 4.0, dtype=torch.float64))
    assert torch.max(torch.abs(normalized_residual)) < 1e-10


def test_equal_rates_match_the_two_site_analytical_solution():
    rate = 2.0
    rho, flux, normalized_residual = solve_kinetic_mean_field(rate, [rate], rate)

    first = (math.sqrt(5.0) - 1.0) / 2.0
    expected_rho = torch.tensor([first, 1.0 - first], dtype=torch.float64)
    torch.testing.assert_close(rho, expected_rho, rtol=1e-10, atol=1e-12)
    torch.testing.assert_close(
        flux, torch.tensor(rate * (1.0 - first), dtype=torch.float64),
        rtol=1e-10, atol=1e-12,
    )
    assert torch.max(torch.abs(normalized_residual)) < 1e-10


def test_flux_conservation_and_normalized_residual():
    alpha = 0.7
    k = torch.tensor([1.2, 0.4, 2.1], dtype=torch.float64)
    beta = 1.5
    rho, flux, normalized_residual = solve_kinetic_mean_field(alpha, k, beta)

    equation_fluxes = torch.cat((
        (alpha * (1.0 - rho[:1])),
        k * rho[:-1] * (1.0 - rho[1:]),
        beta * rho[-1:],
    ))
    torch.testing.assert_close(
        equation_fluxes, flux.expand_as(equation_fluxes), rtol=1e-9, atol=1e-11
    )
    torch.testing.assert_close(
        normalized_residual,
        (equation_fluxes - flux) / flux,
        rtol=1e-8,
        atol=1e-11,
    )
    assert bool(((rho >= 0.0) & (rho <= 1.0)).all())
    assert flux > 0.0


@pytest.mark.parametrize("alpha,beta", [(1e6, 1.0), (1.0, 1e6)])
def test_single_site_boundaries_match_the_analytical_solution(alpha, beta):
    rho, flux, normalized_residual = solve_kinetic_mean_field(alpha, [], beta)

    expected_rho = alpha / (alpha + beta)
    expected_flux = alpha * beta / (alpha + beta)
    assert float(rho[0]) == pytest.approx(expected_rho, rel=1e-11, abs=1e-14)
    assert float(flux) == pytest.approx(expected_flux, rel=1e-11, abs=1e-14)
    assert 0.0 <= float(rho[0]) <= 1.0
    assert torch.max(torch.abs(normalized_residual)) < 1e-10


@pytest.mark.parametrize(
    "alpha,k,beta",
    [
        (0.0, [1.0], 1.0),
        (-1.0, [1.0], 1.0),
        (1.0, [0.0], 1.0),
        (1.0, [-1.0], 1.0),
        (1.0, [1.0], 0.0),
        (np.nan, [1.0], 1.0),
        (1.0, [np.inf], 1.0),
        (1.0, [1.0], -np.inf),
    ],
)
def test_rejects_nonpositive_or_nonfinite_rates(alpha, k, beta):
    with pytest.raises(ValueError, match="strictly positive"):
        solve_kinetic_mean_field(alpha, k, beta)


@pytest.mark.parametrize(
    "alpha,k,beta,match",
    [
        ([1.0], [1.0], 1.0, "scalars"),
        (1.0, 1.0, 1.0, "one-dimensional"),
        (1.0, [[1.0]], 1.0, "one-dimensional"),
        (1.0, [1.0], [1.0], "scalars"),
    ],
)
def test_rejects_invalid_input_shapes(alpha, k, beta, match):
    with pytest.raises(ValueError, match=match):
        solve_kinetic_mean_field(alpha, k, beta)


def test_nonconvergence_is_not_returned_as_a_success(monkeypatch):
    monkeypatch.setattr(kinetic_mean_field, "solve_ivp", lambda *args, **kwargs: type("FailedIntegration", (), {"success": False, "message": "did not converge", "y": np.zeros((4, 1))})())
    with pytest.raises(RuntimeError, match="did not converge"):
        solve_kinetic_mean_field(1.3, [0.8, 1.7, 1.1], 0.9, maxfev=1)


def test_scipy_exceptions_are_preserved(monkeypatch):
    class ExpectedRootError(Exception):
        pass

    def failing_root(*args, **kwargs):
        raise ExpectedRootError("root failure")

    monkeypatch.setattr(kinetic_mean_field, "root", failing_root)
    with pytest.raises(ExpectedRootError, match="root failure"):
        solve_kinetic_mean_field(1.0, [1.0], 1.0)


def test_implicit_gradients_match_central_finite_differences():
    alpha = torch.tensor(1.3, dtype=torch.float64, requires_grad=True)
    k = torch.tensor([0.8, 1.7, 1.1], dtype=torch.float64, requires_grad=True)
    beta = torch.tensor(0.9, dtype=torch.float64, requires_grad=True)
    weights = torch.tensor([0.2, -0.4, 0.7, 0.3], dtype=torch.float64)

    rho, flux, normalized_residual = solve_kinetic_mean_field(alpha, k, beta)
    assert rho.requires_grad and flux.requires_grad
    assert not normalized_residual.requires_grad
    objective = (weights * rho).sum() + 0.37 * flux
    gradients = torch.autograd.grad(objective, (alpha, k, beta))

    def objective_value(alpha_value, k_value, beta_value):
        with torch.no_grad():
            rho_value, flux_value, _ = solve_kinetic_mean_field(
                alpha_value, k_value, beta_value
            )
        return float((weights * rho_value).sum() + 0.37 * flux_value)

    epsilon = 1e-5
    alpha_value = alpha.detach()
    k_value = k.detach()
    beta_value = beta.detach()
    numeric_alpha = (
        objective_value(alpha_value + epsilon, k_value, beta_value)
        - objective_value(alpha_value - epsilon, k_value, beta_value)
    ) / (2.0 * epsilon)
    numeric_beta = (
        objective_value(alpha_value, k_value, beta_value + epsilon)
        - objective_value(alpha_value, k_value, beta_value - epsilon)
    ) / (2.0 * epsilon)
    numeric_k = []
    for index in range(k_value.numel()):
        k_plus = k_value.clone()
        k_minus = k_value.clone()
        k_plus[index] += epsilon
        k_minus[index] -= epsilon
        numeric_k.append((
            objective_value(alpha_value, k_plus, beta_value)
            - objective_value(alpha_value, k_minus, beta_value)
        ) / (2.0 * epsilon))

    np.testing.assert_allclose(float(gradients[0]), numeric_alpha, rtol=1e-6, atol=1e-8)
    np.testing.assert_allclose(gradients[1].numpy(), numeric_k, rtol=1e-6, atol=1e-8)
    np.testing.assert_allclose(float(gradients[2]), numeric_beta, rtol=1e-6, atol=1e-8)
