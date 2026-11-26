"""Exact small-state CTMC tests for the mean-field validation protocol."""
import json

import numpy as np
import pytest
import torch

from codonflow.models.kinetic_mean_field import solve_kinetic_mean_field
from scripts import a10_03_validate_mean_field_approximation as validation


def independent_eigen_stationary(theta, length):
    size = 1 << length
    generator = np.zeros((size, size))
    for state in range(size):
        occupied = [(state >> site) & 1 for site in range(length)]
        moves = []
        if not occupied[0]:
            target = state | 1
            moves.append((target, theta[0]))
        for site in range(length - 1):
            if occupied[site] and not occupied[site + 1]:
                target = state ^ (1 << site) ^ (1 << (site + 1))
                moves.append((target, theta[site + 1]))
        if occupied[-1]:
            moves.append((state ^ (1 << (length - 1)), theta[-1]))
        for target, rate in moves:
            generator[state, target] = rate
            generator[state, state] -= rate
    eigenvalues, eigenvectors = np.linalg.eig(generator.T)
    index = np.argmin(np.abs(eigenvalues))
    probability = np.real(eigenvectors[:, index])
    probability /= probability.sum()
    return probability


def test_exact_single_site_matches_analytical_stationary_state():
    exact = validation.exact_ctmc_stationary([3.0, 2.0], 1)
    np.testing.assert_allclose(exact["density"], [0.6], atol=1e-13, rtol=0.0)
    assert exact["flux"] == pytest.approx(1.2, abs=1e-13)
    assert exact["probability"].shape == (2,)
    assert exact["stationary_residual_inf"] < 1e-13


def test_exact_ctmc_matches_independent_eigenvector_and_detailed_balance_is_not_assumed():
    theta = np.asarray([1.3, 0.8, 1.7, 0.65])
    exact = validation.exact_ctmc_stationary(theta, 3)
    expected = independent_eigen_stationary(theta, 3)
    np.testing.assert_allclose(exact["probability"], expected, atol=2e-12, rtol=0.0)
    assert exact["conservation_relative_error"] < 1e-12
    generator = np.zeros((8, 8))
    for state in range(8):
        if not state & 1:
            generator[state | 1, state] += theta[0]
            generator[state, state] -= theta[0]
        for position in range(2):
            if state & (1 << position) and not state & (1 << (position + 1)):
                target = state ^ (1 << position) ^ (1 << (position + 1))
                generator[target, state] += theta[position + 1]
                generator[state, state] -= theta[position + 1]
        if state & 4:
            generator[state ^ 4, state] += theta[-1]
            generator[state, state] -= theta[-1]
    stationary_flow = generator * exact["probability"][None, :]
    reverse_flow = stationary_flow.T
    assert np.max(np.abs(stationary_flow - reverse_flow)) > 1e-3


def test_mean_field_is_exact_for_one_site_but_not_multisite_exclusion():
    for alpha, beta in ((0.2, 3.0), (1.0, 1.0), (4.0, 0.7)):
        exact = validation.exact_ctmc_stationary([alpha, beta], 1)
        density, flux, residual = solve_kinetic_mean_field(alpha, [], beta)
        np.testing.assert_allclose(density.numpy(), exact["density"], atol=1e-12, rtol=0.0)
        assert flux.item() == pytest.approx(exact["flux"], abs=1e-12)
        assert residual.abs().max().item() < 1e-10

    half_theta = np.asarray([0.5, 1.0, 1.0, 1.0, 0.5])
    half_exact = validation.exact_ctmc_stationary(half_theta, 4)
    half_density, half_flux, _ = solve_kinetic_mean_field(0.5, np.ones(3), 0.5)
    np.testing.assert_allclose(half_exact["density"], np.full(4, 0.5), atol=1e-12, rtol=0.0)
    np.testing.assert_allclose(half_density.numpy(), half_exact["density"], atol=1e-11, rtol=0.0)
    assert half_flux.item() == pytest.approx(half_exact["flux"], abs=1e-11)
    assert validation.max_abs(half_exact["covariance"]) < 1e-12

    exact = validation.exact_ctmc_stationary(np.ones(5), 4)
    density, flux, _ = solve_kinetic_mean_field(1.0, np.ones(3), 1.0)
    assert validation.max_abs(density.numpy() - exact["density"]) > 0.01
    assert abs(flux.item() - exact["flux"]) > 0.01
    assert validation.max_abs(exact["covariance"]) > 0.01


def test_exact_log_sensitivity_matches_direct_scaling_and_sum_rules():
    theta = np.asarray([1.1, 0.7, 1.8, 0.9])
    sensitivity = validation.exact_log_sensitivity(theta, 3)
    np.testing.assert_allclose(sensitivity[:3].sum(axis=1), 0.0, atol=2e-8, rtol=0.0)
    assert sensitivity[-1].sum() == pytest.approx(1.0, abs=2e-8)

    scaled = validation.exact_ctmc_stationary(theta * 100.0, 3)
    base = validation.exact_ctmc_stationary(theta, 3)
    np.testing.assert_allclose(scaled["density"], base["density"], atol=2e-13, rtol=0.0)
    assert scaled["flux"] / base["flux"] == pytest.approx(100.0, rel=2e-13)


def test_local_identifiability_contract_for_relative_rates_and_absolute_flux():
    theta = np.asarray([1.1, 0.7, 1.8, 0.9])
    sensitivity = validation.exact_log_sensitivity(theta, 3)
    metrics = validation.identifiability_metrics(sensitivity, 3)
    assert metrics["density_only"]["rank"] == 3
    assert metrics["density_only"]["null_dimension"] == 1
    assert metrics["density_plus_absolute_flux"]["rank"] == 4
    assert metrics["density_plus_absolute_flux"]["null_dimension"] == 0
    assert metrics["density_only"]["nonzero_condition_number"] > 1.0


def test_mean_field_implicit_sensitivity_matches_production_autograd():
    case = next(
        case for case in validation.case_specs()
        if case["name"] == "constant_L2_a1_k1_b0.05"
    )
    theta = np.asarray(case["theta"])
    production = validation.production_mean_field(theta, torch.device("cpu"), autograd=True)
    independent = validation.mean_field_log_sensitivity(
        theta, production["density"], production["flux"],
    )
    np.testing.assert_allclose(production["sensitivity"], independent, atol=2e-8, rtol=2e-8)
    np.testing.assert_allclose(independent[:-1].sum(axis=1), 0.0, atol=2e-11, rtol=0.0)
    assert independent[-1].sum() == pytest.approx(1.0, abs=2e-11)


def test_case_evaluation_preserves_exact_reference_when_production_fails(monkeypatch):
    case = next(case for case in validation.case_specs() if case["length"] == 2)
    monkeypatch.setattr(
        validation, "production_mean_field",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("synthetic solver failure")),
    )
    record = validation.evaluate_case(case, torch.device("cpu"))
    assert record["passed"] is False
    assert record["failure"]["message"] == "synthetic solver failure"
    assert len(record["exact"]["density"]) == 2
    assert "mean_field" not in record


def test_protocol_is_synthetic_seeded_and_fail_closed(tmp_path):
    specs = validation.case_specs()
    protocol = validation.protocol_payload(torch.device("cpu"))
    assert len(specs) == protocol["cases"]["expected_total"] == 859
    assert len({case["name"] for case in specs}) == len(specs)
    assert protocol["cases"]["random_seed"] == validation.RANDOM_SEED
    assert protocol["external_or_frozen_data_read"] is False
    assert protocol["reference"]["simulation_or_gillespie"] is False
    assert protocol["mean_field"]["exact_stochastic_simulation"] is False
    output = tmp_path / "protocol.json"
    validation.write_json_exclusive(output, protocol)
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        validation.write_json_exclusive(output, {"replacement": True})
    assert output.read_bytes() == original
    assert json.loads(original)["schema"] == validation.SCHEMA


def test_explicit_cuda_unavailability_is_not_a_cpu_fallback(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="refusing CPU fallback"):
        validation.environment(torch.device("cuda:0"))


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is not available")
def test_cuda_forward_and_full_log_jacobian_match_independent_implicit_solve():
    theta = np.asarray([1.2, 0.8, 1.7, 0.65])
    production = validation.production_mean_field(
        theta, torch.device("cuda:0"), autograd=True,
    )
    independent = validation.mean_field_log_sensitivity(
        theta, production["density"], production["flux"],
    )
    assert production["device"] == "cuda:0"
    np.testing.assert_allclose(production["sensitivity"], independent, atol=2e-8, rtol=2e-8)
