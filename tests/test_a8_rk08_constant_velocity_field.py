from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/a8_rk08_constant_velocity_field.py"
SPEC = importlib.util.spec_from_file_location("a8_rk08_constant_velocity_field", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def training_frame() -> pd.DataFrame:
    frame = pd.DataFrame({
        "record_id": ["t1", "t1", "t2"],
        "dataset": ["Mohammad16"] * 3,
        "split": ["train"] * 3,
        "codon_position": [1, 2, 1],
        "codon_count": [100, 100, 100],
        "target": [0.0, 2.0, 10.0],
    })
    frame["position_bin"] = MODULE.position_bins(frame["codon_position"], frame["codon_count"])
    return frame


def test_relative_position_uses_codon_count_minus_one():
    bins = MODULE.position_bins(np.array([1, 5, 9]), np.array([11, 11, 11]), 20)
    np.testing.assert_array_equal(bins, np.array([2, 10, 18]))


def test_invalid_terminal_or_initiation_positions_fail():
    with pytest.raises(ValueError, match="observed position"):
        MODULE.position_bins(np.array([0]), np.array([11]))
    with pytest.raises(ValueError, match="observed position"):
        MODULE.position_bins(np.array([10]), np.array([11]))


def test_field_is_transcript_balanced_not_position_weighted():
    field, summary = MODULE.fit_constant_field(training_frame())
    assert summary["fit_rows"] == 3
    assert summary["fit_transcripts"] == 2
    assert field[0] == pytest.approx(5.5)
    assert field[0] != pytest.approx(4.0)


def test_missing_bin_uses_equal_weight_global_transcript_fallback():
    field, summary = MODULE.fit_constant_field(training_frame())
    assert summary["missing_bin_fallback"] == pytest.approx(5.5)
    assert np.all(field[summary["missing_bins"]] == pytest.approx(5.5))


def test_evaluation_targets_cannot_change_fitted_field():
    baseline = training_frame()
    extended = pd.concat([
        baseline,
        pd.DataFrame({
            "record_id": ["eval"],
            "dataset": ["Subtelny14"],
            "split": ["study_ood"],
            "codon_position": [1],
            "codon_count": [100],
            "target": [1e9],
            "position_bin": [0],
        }),
    ], ignore_index=True)
    first, _ = MODULE.fit_constant_field(baseline)
    second, _ = MODULE.fit_constant_field(extended)
    np.testing.assert_array_equal(first, second)


def test_constant_within_transcript_pearson_is_nan():
    frame = pd.DataFrame({
        "record_id": ["t"] * 3,
        "dataset": ["Mohammad16"] * 3,
        "split": ["train"] * 3,
        "target": [1.0, 2.0, 3.0],
        "constant": [4.0, 4.0, 4.0],
    })
    per = MODULE.per_transcript_table(frame, models=("constant",))
    assert np.isnan(per.loc[0, "constant_pearson"])
    assert per.loc[0, "constant_mse"] == pytest.approx(14.0 / 3.0)


def test_paired_bootstrap_recovers_clear_benefit():
    rng = np.random.default_rng(7)
    n = 100
    arrays = {
        "left_mse": rng.uniform(0.1, 0.2, n),
        "right_mse": rng.uniform(0.8, 1.0, n),
        "left_pearson": rng.uniform(0.7, 0.9, n),
        "right_pearson": rng.uniform(0.1, 0.3, n),
    }
    result = MODULE.paired_bootstrap(arrays, replicates=200, seed=11)
    assert result["transcript_balanced_mse"]["ci95"][1] < 0
    assert result["mean_transcript_pearson"]["ci95"][0] > 0


def test_holm_adjustment_is_monotone_and_correct():
    adjusted = MODULE.holm_adjust([0.01, 0.02, 0.5])
    np.testing.assert_allclose(adjusted, [0.03, 0.04, 0.5])


def test_support_requires_both_endpoints_and_sensitivity():
    result = {
        "transcript_balanced_mse": {"holm_pvalue": 0.0, "ci95": [-0.2, -0.1]},
        "mean_transcript_pearson": {"holm_pvalue": 0.0, "ci95": [0.1, 0.2]},
        "sensitivity_bootstrap_mean_deltas": [
            {"transcript_balanced_mse": -0.1, "mean_transcript_pearson": 0.1},
            {"transcript_balanced_mse": -0.1, "mean_transcript_pearson": 0.1},
        ],
    }
    assert MODULE.supported(result)
    result["transcript_balanced_mse"]["ci95"] = [-0.2, 0.0]
    assert not MODULE.supported(result)


def test_prediction_schema_and_raw_partition_alignment(tmp_path):
    records = {"Study:r": {"codon_count": 11, "split": "dev", "dataset": "Study"}}
    path = tmp_path / "predictions.csv"
    pd.DataFrame({
        "record_id": ["Study:r"],
        "dataset": ["Study"],
        "split": ["dev"],
        "codon_position": [1],
        "target": [1.0],
        "model": [1.0],
        "ridge": [1.0],
    }).to_csv(path, index=False)
    frame = MODULE.load_prediction_frame(path, records, 1)
    assert frame.loc[0, "position_bin"] == 2
    records["Study:r"]["split"] = "train"
    with pytest.raises(ValueError, match="split mismatch"):
        MODULE.load_prediction_frame(path, records, 1)
