import numpy as np
import pytest

from scripts.recompute_s3_full_adaptive import (
    REQUIRED_METHODS,
    objective_pool,
    pooled_reference,
    recompute_group,
)
from scripts.verdict_355m_and_rloo import paired_deltas


def row(offset=0.0, legacy_name=False):
    result = {}
    for method in REQUIRED_METHODS:
        name = "uniform_edit_flow" if legacy_name and method == "uniform_synonymous" else method
        points = np.array([[0.7, -20.0, -0.1, -2.0],
                           [0.8, -30.0, -0.05, -1.0]]) + offset
        result[f"S3_quad/{name}/obj_vectors"] = points.tolist()
    return result


def test_complete_joint_reference_is_shared_and_normalized():
    first, second = row(legacy_name=True), row(0.1)
    result = recompute_group([first, second])
    assert result["n_models"] == 2
    assert result["scale"][0] > 0
    for model in result["models"]:
        assert model["codonflow/hv"] >= 0
        assert set(model["n_solutions"]) == set(REQUIRED_METHODS)
    deltas = paired_deltas(result, ["base", "treatment"])
    assert len(deltas) == 1 and deltas[0] > 0


def test_incomplete_pool_is_rejected_not_silently_excluded():
    incomplete = row()
    del incomplete["S3_quad/codongpt/obj_vectors"]
    with pytest.raises(ValueError, match="incomplete"):
        pooled_reference([incomplete])


def test_missing_entire_method_not_treated_as_empty_solution_set():
    incomplete = row()
    del incomplete["S3_quad/lineardesign_scan/obj_vectors"]
    with pytest.raises(ValueError, match="lineardesign"):
        recompute_group([incomplete])


def test_nonfinite_pool_fails():
    invalid = row()
    invalid["S3_quad/codonflow/obj_vectors"][0][0] = float("nan")
    with pytest.raises(ValueError, match="NaN"):
        pooled_reference([invalid])
