import json
import math

import numpy as np
import pytest
import torch

from codonflow.models import kinetic_mean_field
from scripts import a10_03_verify_mean_field as verifier


def test_equal_rates_have_exact_one_and_two_site_solutions():
    single_rho, single_flux, single_residual = kinetic_mean_field.solve_kinetic_mean_field(
        2.0, [], 2.0,
    )
    torch.testing.assert_close(
        single_rho, torch.tensor([0.5], dtype=torch.float64), atol=1e-12, rtol=0.0,
    )
    assert single_flux.item() == pytest.approx(1.0, abs=1e-12)

    rate = 0.7
    q = (3.0 - math.sqrt(5.0)) / 2.0
    double_rho, double_flux, double_residual = kinetic_mean_field.solve_kinetic_mean_field(
        rate, [rate], rate,
    )
    torch.testing.assert_close(
        double_rho,
        torch.tensor([1.0 - q, q], dtype=torch.float64),
        atol=1e-11,
        rtol=0.0,
    )
    assert double_flux.item() == pytest.approx(rate * q, abs=1e-11)
    for rho, residual in ((single_rho, single_residual), (double_rho, double_residual)):
        assert residual.abs().max().item() < 1e-11
        assert torch.all(rho >= 0.0) and torch.all(rho <= 1.0)


def test_all_half_maximal_current_state_does_not_satisfy_full_equations():
    rate = 0.7
    flux = rate / 4.0
    entrance_residual = rate * (1.0 - 0.5) - flux
    exit_residual = rate * 0.5 - flux
    assert entrance_residual == pytest.approx(rate / 4.0)
    assert exit_residual == pytest.approx(rate / 4.0)


def test_heterogeneous_rates_satisfy_residual_and_flux_conservation():
    alpha, beta = 1.2, 0.65
    k = torch.tensor([0.8, 1.7], dtype=torch.float64)
    rho, flux, relative_residual = kinetic_mean_field.solve_kinetic_mean_field(alpha, k, beta)
    local_flux = torch.cat((
        (alpha * (1.0 - rho[:1])).reshape(1),
        k * rho[:-1] * (1.0 - rho[1:]),
        beta * rho[-1:],
    ))
    torch.testing.assert_close(
        local_flux,
        flux.expand_as(local_flux),
        atol=1e-11,
        rtol=0.0,
    )
    assert relative_residual.shape == (4,)
    assert relative_residual.abs().max().item() < 1e-11


def test_first_order_gradcheck_for_density_and_flux():
    alpha = torch.tensor(1.1, dtype=torch.float64, requires_grad=True)
    k = torch.tensor([0.75, 1.4], dtype=torch.float64, requires_grad=True)
    beta = torch.tensor(0.9, dtype=torch.float64, requires_grad=True)
    rho_weights = torch.tensor([0.3, -0.2, 0.6], dtype=torch.float64)

    def objective(alpha_value, k_value, beta_value):
        rho, flux, _ = kinetic_mean_field.solve_kinetic_mean_field(
            alpha_value, k_value, beta_value,
        )
        return torch.dot(rho_weights, rho) + 0.7 * flux

    assert torch.autograd.gradcheck(
        objective, (alpha, k, beta), eps=1e-6, atol=2e-5, rtol=2e-4,
    )


@pytest.mark.parametrize("alpha,k,beta", [
    (0.0, [1.0], 1.0),
    (1.0, [1.0, -0.2], 1.0),
    (1.0, [1.0], float("nan")),
    (float("inf"), [1.0], 1.0),
])
def test_nonpositive_or_nonfinite_rates_are_rejected(alpha, k, beta):
    with pytest.raises(ValueError, match="finite|strictly positive"):
        kinetic_mean_field.solve_kinetic_mean_field(alpha, k, beta)


def test_rate_shapes_and_solver_controls_are_validated():
    with pytest.raises(ValueError, match="one-dimensional"):
        kinetic_mean_field.solve_kinetic_mean_field(1.0, 1.0, 1.0)
    with pytest.raises(ValueError, match="scalar"):
        kinetic_mean_field.solve_kinetic_mean_field([1.0], [1.0], 1.0)
    with pytest.raises(ValueError, match="root_tolerance"):
        kinetic_mean_field.solve_kinetic_mean_field(1.0, [1.0], 1.0, root_tolerance=0.0)
    with pytest.raises(ValueError, match="residual_tolerance"):
        kinetic_mean_field.solve_kinetic_mean_field(1.0, [1.0], 1.0, residual_tolerance=-1.0)
    with pytest.raises(ValueError, match="maxfev"):
        kinetic_mean_field.solve_kinetic_mean_field(1.0, [1.0], 1.0, maxfev=1.5)


def test_newton_receives_analytic_banded_jacobian(monkeypatch):
    actual_banded_solve = kinetic_mean_field._banded_lu_once_numpy
    observed = {}

    def checked_banded_solve(bands, rhs, **kwargs):
        observed["jacobian"] = kinetic_mean_field._banded_to_dense_numpy(bands)
        return actual_banded_solve(bands, rhs, **kwargs)

    monkeypatch.setattr(kinetic_mean_field, "_banded_lu_once_numpy", checked_banded_solve)
    kinetic_mean_field.solve_kinetic_mean_field(1.0, [1.0], 1.0)
    assert observed["jacobian"].shape == (3, 3)
    assert np.count_nonzero(observed["jacobian"]) == 7


def test_newton_nonconvergence_is_never_silently_accepted(monkeypatch):
    def failed_banded_solve(*args, **kwargs):
        raise RuntimeError("synthetic nonconvergence")

    monkeypatch.setattr(kinetic_mean_field, "_banded_lu_once_numpy", failed_banded_solve)
    monkeypatch.setattr(kinetic_mean_field, "_transient_state_numpy", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("did not converge: synthetic nonconvergence")))
    with pytest.raises(RuntimeError, match="did not converge.*synthetic nonconvergence"):
        kinetic_mean_field.solve_kinetic_mean_field(1.0, [1.0], 1.0)


@pytest.mark.parametrize("state,message", [
    (np.array([1.2, 0.5, 0.25]), "densities outside"),
    (np.array([0.5, 0.5, 1.0]), "residual tolerance"),
])
def test_solver_return_cannot_bypass_domain_or_residual_checks(monkeypatch, state, message):
    monkeypatch.setattr(kinetic_mean_field, "_newton_state_numpy", lambda *args, **kwargs: state)
    monkeypatch.setattr(kinetic_mean_field, "_transient_state_numpy", lambda *args, **kwargs: state)
    with pytest.raises(RuntimeError, match=message):
        kinetic_mean_field.solve_kinetic_mean_field(1.0, [1.0], 1.0)


def test_cpu_independent_audit_records_inputs_outputs_errors_and_hashes():
    report = verifier.audit_mean_field("cpu")
    assert report["passed"] is True
    assert len(report["cases"]) == 5
    assert all(case["passed"] for case in report["cases"])
    assert report["max_errors"]["rho"] <= verifier.SOLUTION_TOL
    assert report["max_errors"]["J"] <= verifier.SOLUTION_TOL
    assert report["max_errors"]["gradient"] <= verifier.GRADIENT_TOL
    assert report["max_errors"]["production_conservation"] <= verifier.RESIDUAL_TOL
    assert report["max_errors"]["independent_conservation"] <= verifier.RESIDUAL_TOL
    assert report["environment"]["autograd_device"] == "cpu"
    assert report["gpu_validation"]["requested"] is False
    assert report["scope"]["exact_stochastic_simulation"] is False
    assert report["scope"]["data_or_untouched_files_read"] is False
    assert report["artifact_sha256"]["production_implementation"] == verifier.sha256_file(
        kinetic_mean_field.__file__,
    )
    for case in report["cases"]:
        assert case["input"]["alpha"] > 0.0
        assert case["input"]["beta"] > 0.0
        assert all(rate > 0.0 for rate in case["input"]["k"])
        assert len(case["production"]["rho"]) == len(case["input"]["k"]) + 1
        assert len(case["independent_least_squares"]["relative_residual"]) == len(case["input"]["k"]) + 2
        assert all(math.isfinite(value) for value in case["max_errors"].values())


def test_cli_writes_exclusive_json_and_preserves_existing_output(tmp_path):
    output = tmp_path / "nested" / "audit.json"
    assert verifier.main(["--output", str(output), "--device", "cpu"]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["passed"] is True
    original = output.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        verifier.main(["--output", str(output), "--device", "cpu"])
    assert output.read_bytes() == original


def test_explicit_cuda_unavailability_writes_failure_without_cpu_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    output = tmp_path / "cuda_failure.json"
    assert verifier.main(["--output", str(output), "--device", "cuda"]) == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["passed"] is False
    assert "refusing CPU fallback" in report["error"]["message"]
    assert report["environment"]["cuda"]["requested"] is True
    assert report["environment"]["cuda"]["available"] is False
