import numpy as np
import pytest

from codonflow.eval.anytime import FrozenReference, anytime_curve


def test_reference_is_frozen_from_calibration_not_test_points():
    calibration = [[0, 0], [1, 1], [2, 2], [3, 3]]
    frozen = FrozenReference.from_calibration(calibration)
    before = frozen.to_dict()
    curve = anytime_curve([
        {"budget": 50, "objectives": [100, 100]},
    ], frozen, budgets=[50])
    assert curve["reference"] == before
    assert curve["curve"][0]["hv"] > 0


def test_anytime_auc_integrates_early_and_late_quality():
    frozen = FrozenReference.from_dict({"reference": [0, 0], "scale": [1, 1]})
    result = anytime_curve([
        {"budget": 50, "objectives": [1, 1]},
        {"budget": 100, "objectives": [2, 1]},
        {"budget": 500, "objectives": [2, 2]},
    ], frozen)
    assert [row["n_scored"] for row in result["curve"]] == [1, 2, 3]
    assert [row["hv"] for row in result["curve"]] == [1.0, 2.0, 4.0]
    expected_area = 50 * 0.5 + 50 * 1.5 + 400 * 3.0
    assert result["area"] == expected_area
    assert result["auc"] == expected_area / 500


def test_empty_early_budget_has_zero_area():
    frozen = FrozenReference.from_dict({"reference": [0, 0], "scale": [1, 1]})
    result = anytime_curve([{"budget": 100, "objectives": [1, 1]}], frozen)
    assert result["curve"][0]["hv"] == 0
    assert result["curve"][0]["n_scored"] == 0


def test_degenerate_calibration_axis_is_rejected():
    with pytest.raises(ValueError, match="degenerate"):
        FrozenReference.from_calibration([[0, 1], [1, 1], [2, 1]])


def test_duplicate_or_invalid_budget_is_rejected():
    frozen = FrozenReference.from_dict({"reference": [0], "scale": [1]})
    with pytest.raises(ValueError, match="unique positive budget"):
        anytime_curve([
            {"budget": 50, "objectives": [1]},
            {"budget": 50, "objectives": [2]},
        ], frozen)
