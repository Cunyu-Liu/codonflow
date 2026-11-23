import importlib.util
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("diagnose_kinetic", ROOT / "scripts" / "a10_03_diagnose_kinetic_solver.py")
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


def test_case_recorder_preserves_real_inputs_before_solver_call(tmp_path, monkeypatch):
    observed = []

    def fake_solver(alpha, rates, beta, root_tolerance, residual_tolerance, maxfev):
        observed.append((alpha, rates.copy(), beta))
        return np.asarray([0.5, 0.25]), np.zeros(2)

    monkeypatch.setattr(diagnostic.kinetic_mean_field, "_solve_state_numpy", fake_solver)
    state = diagnostic.install_case_recorder(tmp_path / "diagnostic")
    rates = np.asarray([0.8, 1.1])
    diagnostic.kinetic_mean_field._solve_state_numpy(1.2, rates, 0.9, 1e-12, 1e-10, 1000)
    with np.load(tmp_path / "diagnostic" / "current_case.npz") as saved:
        assert float(saved["alpha"]) == 1.2
        assert float(saved["beta"]) == 0.9
        np.testing.assert_array_equal(saved["rates"], rates)
        assert int(saved["call"]) == 1
    assert state["calls"] == 1
    assert observed[0][0] == 1.2 and observed[0][2] == 0.9
    np.testing.assert_array_equal(observed[0][1], rates)
