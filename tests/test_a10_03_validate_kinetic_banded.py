"""CLI safety tests for the independent banded kinetic validation."""
import json

import numpy as np
import pytest
import torch

from scripts import a10_03_review_kinetic_banded as reviewer
from scripts import a10_03_validate_kinetic_banded as validator


def input_paths(tmp_path):
    baseline = tmp_path / "baseline.py"
    baseline.write_text("# test input\n", encoding="utf-8")
    snapshot = tmp_path / "snapshot.npz"
    np.savez(snapshot, alpha=np.asarray(1.0), rates=np.asarray([1.0]), beta=np.asarray(1.0))
    return baseline, snapshot


def test_explicit_cuda_unavailability_is_fail_closed_without_cpu_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    baseline, snapshot = input_paths(tmp_path)
    output = tmp_path / "validation.json"
    arrays = tmp_path / "arrays.npz"
    code = validator.main([
        "--output", str(output),
        "--array-output", str(arrays),
        "--baseline", str(baseline),
        "--real-snapshot", str(snapshot),
        "--device", "cuda:0",
    ])
    assert code == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["passed"] is False
    assert "refusing CPU fallback" in report["error"]["message"]
    assert report["scope"]["training_executed"] is False
    assert report["scope"]["scientific_gate_claimed"] is False
    assert not arrays.exists()


def test_existing_validation_artifacts_are_never_overwritten(tmp_path):
    baseline, snapshot = input_paths(tmp_path)
    output = tmp_path / "validation.json"
    arrays = tmp_path / "arrays.npz"
    output.write_text("historical result\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        validator.main([
            "--output", str(output),
            "--array-output", str(arrays),
            "--baseline", str(baseline),
            "--real-snapshot", str(snapshot),
        ])
    assert output.read_text(encoding="utf-8") == "historical result\n"
    assert not arrays.exists()


def test_independent_dense_gradient_matches_direct_adjoint():
    spec = {
        "name": "small",
        "length": 3,
        "alpha": 1.2,
        "rates": np.asarray([0.8, 1.7]),
        "beta": 0.65,
    }
    rho = np.asarray([0.55, 0.45, 0.35])
    flux = 0.3
    _, jacobian, _ = validator.independent_residual_jacobian(spec, rho, flux)
    gradient, recovery = validator.independent_dense_gradient(
        spec, rho, flux, torch.device("cpu")
    )
    weights, flux_weight = validator.objective_weights(3, torch.device("cpu"))
    adjoint = np.linalg.solve(
        jacobian.T,
        np.concatenate((weights.numpy(), [flux_weight])),
    )
    expected = np.concatenate((
        [-adjoint[0] * (1.0 - rho[0])],
        -adjoint[1:-1] * rho[:-1] * (1.0 - rho[1:]),
        [-adjoint[-1] * rho[-1]],
    ))
    np.testing.assert_allclose(gradient, expected, rtol=0.0, atol=0.0)
    assert recovery <= validator.RESIDUAL_TOL


def test_independent_review_reconstructs_real_case_gradient(tmp_path):
    rho = np.asarray([0.5, 0.5, 0.5])
    alpha = beta = 1.0
    rates = np.asarray([2.0, 2.0])
    flux = 0.5
    jacobian = np.asarray([
        [-1.0, 0.0, 0.0, -1.0],
        [1.0, -1.0, 0.0, -1.0],
        [0.0, 1.0, -1.0, -1.0],
        [0.0, 0.0, 1.0, -1.0],
    ])
    positions = np.arange(3, dtype=np.float64)
    output_gradient = np.concatenate((
        np.sin(0.013 * positions) + 0.2 * np.cos(0.031 * positions), [0.37]
    ))
    adjoint = np.linalg.solve(jacobian.T, output_gradient)
    gradient = np.concatenate((
        [-adjoint[0] * 0.5],
        -adjoint[1:3] * 0.25,
        [-adjoint[3] * 0.5],
    ))
    arrays = tmp_path / "real.npz"
    np.savez(
        arrays,
        alpha=np.asarray(alpha),
        rates=rates,
        beta=np.asarray(beta),
        rho=rho,
        flux=np.asarray(flux),
        production_gradients=gradient,
        baseline_gradients=gradient,
        normalized_residual=np.zeros(4),
    )
    result, expected = reviewer.independent_real_case(arrays)
    assert result["passed"]
    np.testing.assert_allclose(expected, gradient, rtol=0.0, atol=0.0)
    assert result["errors"]["adjoint_component_recovery_max"] <= 1e-10
