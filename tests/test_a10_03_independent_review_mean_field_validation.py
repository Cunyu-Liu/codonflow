"""Tests for the independent exact-CTMC artifact recomputation."""
import numpy as np
import pytest

from codonflow.models.kinetic_mean_field import solve_kinetic_mean_field
from scripts import a10_03_independent_review_mean_field_validation as review


def test_tuple_eigen_stationary_matches_independent_linear_stationary():
    theta = np.asarray([1.3, 0.8, 1.7, 0.65])
    eigen = review.eigen_stationary(theta, 3)
    probability, density, flux = review.linear_stationary(theta, 3)
    np.testing.assert_allclose(eigen["probability"], probability, atol=2e-13, rtol=0.0)
    np.testing.assert_allclose(eigen["density"], density, atol=2e-13, rtol=0.0)
    assert eigen["flux"] == pytest.approx(flux, abs=2e-13)
    assert eigen["spectral_gap"] > 0.1


def test_complex_step_sensitivity_obeys_common_time_scale_contract():
    theta = np.asarray([1.1, 0.7, 1.8, 0.9])
    sensitivity = review.complex_step_sensitivity(theta, 3)
    np.testing.assert_allclose(sensitivity[:3].sum(axis=1), 0.0, atol=2e-12, rtol=0.0)
    assert sensitivity[-1].sum() == pytest.approx(1.0, abs=2e-12)


def test_independent_mean_field_least_squares_matches_production_state():
    theta = np.asarray([1.3, 0.8, 1.7, 0.65])
    state = review.independent_mean_field(theta)
    density, flux, residual = solve_kinetic_mean_field(theta[0], theta[1:-1], theta[-1])
    np.testing.assert_allclose(state[:-1], density.numpy(), atol=2e-10, rtol=0.0)
    assert state[-1] == pytest.approx(flux.item(), abs=2e-10)
    assert residual.abs().max().item() < 1e-10


def test_exact_comparison_detects_tampered_saved_density():
    theta = [1.3, 0.8, 0.65]
    exact = review.eigen_stationary(theta, 2)
    record = {
        "theta": theta,
        "length": 2,
        "exact": {
            "density": exact["density"].tolist(),
            "flux": exact["flux"],
            "nearest_neighbor_covariance": exact["covariance"].tolist(),
        },
    }
    comparison = review.exact_comparison(record)
    assert comparison["density_max_abs"] == 0.0
    record["exact"]["density"][0] += 1e-3
    assert review.exact_comparison(record)["density_max_abs"] > 1e-4


def test_stiff_independent_mean_field_refinement_matches_production():
    theta = np.asarray([0.05, 20.0, 20.0, 20.0, 20.0, 0.05])
    state = review.independent_mean_field(theta)
    density, flux, residual = solve_kinetic_mean_field(theta[0], theta[1:-1], theta[-1])
    np.testing.assert_allclose(state[:-1], density.numpy(), atol=2e-10, rtol=0.0)
    assert state[-1] == pytest.approx(flux.item(), abs=2e-10)
    assert residual.abs().max().item() < 1e-10
