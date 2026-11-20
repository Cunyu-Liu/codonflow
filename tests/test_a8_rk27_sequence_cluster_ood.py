from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "a8_rk27_run_sequence_cluster_ood.py"
SPEC = importlib.util.spec_from_file_location("rk27_production", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_cluster_folds_are_deterministic_and_disjoint() -> None:
    labels = np.repeat(np.arange(1, 12), [61, 20, 15, 12, 10, 8, 7, 6, 5, 4, 2])
    first, loads_first = MODULE.make_cluster_folds(labels, 20261221)
    second, loads_second = MODULE.make_cluster_folds(labels, 20261221)
    np.testing.assert_array_equal(first, second)
    assert loads_first == loads_second
    assert sum(loads_first) == len(labels)
    for cluster in np.unique(labels):
        assert len(np.unique(first[labels == cluster])) == 1
    assert set(np.unique(first)) == {0, 1, 2, 3, 4}


def test_equal_cluster_sizes_balance_exactly() -> None:
    labels = np.repeat(np.arange(1, 11), 3)
    folds, loads = MODULE.make_cluster_folds(labels, 7)
    assert loads == [6, 6, 6, 6, 6]
    assert np.bincount(folds).tolist() == loads


def test_holm_adjust_matches_manual_monotonic_correction() -> None:
    adjusted = MODULE.holm_adjust([0.01, 0.02, 0.03, 0.04])
    np.testing.assert_allclose(adjusted, [0.04, 0.06, 0.06, 0.06])


def test_holm_adjust_rejects_nonfinite_input() -> None:
    with pytest.raises(AssertionError):
        MODULE.holm_adjust([0.01, float("nan"), 0.03, 0.04])


def test_spearman_matches_scipy_with_ties() -> None:
    rng = np.random.default_rng(5)
    x = rng.integers(0, 5, size=50)
    y = rng.integers(0, 4, size=50)
    assert MODULE.spearman(x, y) == pytest.approx(float(spearmanr(x, y).statistic))


def test_swap_arms_is_exact_and_cluster_consistent() -> None:
    simple = np.array([1.0, 2.0, 3.0, 4.0])
    structure = np.array([5.0, 6.0, 7.0, 8.0])
    swapped_simple, swapped_structure = MODULE.swap_arms(simple, structure, [True, True, False, False])
    np.testing.assert_array_equal(swapped_simple, [5.0, 6.0, 3.0, 4.0])
    np.testing.assert_array_equal(swapped_structure, [1.0, 2.0, 7.0, 8.0])


def synthetic_source(inconsistent: bool = False) -> pd.DataFrame:
    cds = "ATG" * 240
    digest = hashlib.sha256(cds.encode()).hexdigest()
    return pd.DataFrame({
        "source_row": [9, 4],
        "seqId": ["b", "a"],
        "cds": [cds, cds],
        "protein_aa": ["M", "M"],
        "CAI": [0.5, 0.6 if inconsistent else 0.5],
        "log10_expression": [1.0, 3.0],
        "mfe_5prime_kcal_mol": [-7.0, -7.0],
        "cds_sha256": [digest, digest],
    })


def test_aggregate_source_averages_replicates_and_recomputes_gc() -> None:
    result = MODULE.aggregate_source(synthetic_source())
    assert len(result) == 1
    assert result.loc[0, "target"] == 2.0
    assert result.loc[0, "n_measurements"] == 2
    assert result.loc[0, "first_source_row"] == 4
    assert result.loc[0, "gc_cds"] == pytest.approx(1 / 3)
    assert result.loc[0, "gc3_cds"] == pytest.approx(1.0)  # ATG repeats have G at every third position.


def test_aggregate_source_rejects_within_cds_feature_conflicts() -> None:
    with pytest.raises(AssertionError):
        MODULE.aggregate_source(synthetic_source(inconsistent=True))


def test_primary_inference_detects_synthetic_positive_effects() -> None:
    rng = np.random.default_rng(11)
    n = 150
    y = rng.normal(size=n)
    noise = rng.normal(scale=0.8, size=n)
    clusters = np.repeat(np.arange(1, 38), 4)
    clusters = np.concatenate([clusters, [1, 2]])
    frame = pd.DataFrame({
        "target": y,
        "ridge_simple": y + noise,
        "ridge_structure": y,
        "histgb_simple": y + noise,
        "histgb_structure": y,
    })
    tests, arrays = MODULE.primary_inference(frame, clusters, 101, 102, 100)
    assert len(tests) == 4
    assert all(row["observed_effect"] > 0 for row in tests)
    assert arrays["bootstrap_cluster_indices"].shape == (100, 37)
    assert arrays["permutation_cluster_signs"].shape == (100, 37)
    for row in tests:
        assert arrays[f"bootstrap__{row['test']}"].shape == (100,)
        assert arrays[f"permutation__{row['test']}"].shape == (100,)


def test_metric_effects_have_the_frozen_positive_direction() -> None:
    y = np.array([1.0, 2.0, 3.0, 4.0])
    predictions = pd.DataFrame({
        "target": y,
        "null": [2.5] * 4,
        "ridge_simple": y + np.array([1.0, -1.0, 1.0, -1.0]),
        "ridge_structure": y,
        "ridge_mfe_only": y,
        "histgb_simple": y + np.array([1.0, -1.0, 1.0, -1.0]),
        "histgb_structure": y,
        "histgb_mfe_only": y,
    })
    _, effects = MODULE.metric_rows_for_seed(predictions, 1)
    assert all(value > 0 for value in effects.values())
