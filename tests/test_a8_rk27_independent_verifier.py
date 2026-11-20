from __future__ import annotations

import importlib.util
import io
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "a8_rk27_verify_sequence_cluster_ood.py"
SPEC = importlib.util.spec_from_file_location("rk27_independent", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_independent_spearman_known_answer() -> None:
    assert MODULE.corr_spearman(np.array([1, 2, 3]), np.array([1, 5, 4])) == 0.5


def test_independent_holm_known_answer() -> None:
    np.testing.assert_allclose(MODULE.independent_holm([0.01, 0.02, 0.03, 0.04]), [0.04, 0.06, 0.06, 0.06])


def test_independent_assignment_is_deterministic_and_grouped() -> None:
    labels = np.repeat(np.arange(1, 12), [61, 20, 15, 12, 10, 8, 7, 6, 5, 4, 2])
    first, loads = MODULE.assign_independent(labels, 20261221)
    second, loads2 = MODULE.assign_independent(labels, 20261221)
    np.testing.assert_array_equal(first, second)
    assert loads == loads2 and sum(loads) == len(labels)
    for cluster in np.unique(labels):
        assert len(set(first[labels == cluster])) == 1


def test_independent_assignment_balances_equal_clusters() -> None:
    labels = np.repeat(np.arange(1, 11), 3)
    _, loads = MODULE.assign_independent(labels, 99)
    assert loads == [6, 6, 6, 6, 6]


def synthetic_primary(identical: bool) -> tuple[pd.DataFrame, np.ndarray]:
    rng = np.random.default_rng(44)
    y = rng.normal(size=150)
    noise = rng.normal(size=150)
    structure = y + noise if identical else y
    clusters = np.concatenate([np.repeat(np.arange(1, 38), 4), [1, 2]])
    frame = pd.DataFrame({
        "target": y,
        "ridge_simple": y + noise,
        "ridge_structure": structure,
        "histgb_simple": y + noise,
        "histgb_structure": structure,
    })
    return frame, clusters


def test_independent_statistics_zero_effect_has_zero_null_and_p_one() -> None:
    frame, clusters = synthetic_primary(identical=True)
    tests, arrays = MODULE.independent_statistics(frame, clusters, 100, 101, 102)
    for test in tests:
        assert test["observed_effect"] == 0.0
        assert test["p_cluster_swap"] == 1.0
        assert np.all(arrays[f"bootstrap__{test['test']}"] == 0)
        assert np.all(arrays[f"permutation__{test['test']}"] == 0)


def test_independent_statistics_detects_positive_synthetic_increment() -> None:
    frame, clusters = synthetic_primary(identical=False)
    tests, arrays = MODULE.independent_statistics(frame, clusters, 100, 103, 104)
    assert all(test["observed_effect"] > 0 for test in tests)
    assert arrays["bootstrap_cluster_indices"].shape == (100, 37)
    assert arrays["permutation_cluster_signs"].shape == (100, 37)


def test_verifier_does_not_import_production_or_coverage_modules() -> None:
    text = SCRIPT.read_text()
    assert "import a8_rk27_run_sequence_cluster_ood" not in text
    assert "import a8_rk27_audit_sequence_coverage" not in text
    assert "production_module_imported\": False" in text


def test_production_metric_reader_preserves_literal_null_arm() -> None:
    text = SCRIPT.read_text()
    assert 'production_root / "seed_metrics.csv", keep_default_na=False' in text
    frame = pd.read_csv(io.StringIO("seed,arm,spearman,mse\n1,null,0.1,0.2\n"), keep_default_na=False)
    assert frame.loc[0, "arm"] == "null"
