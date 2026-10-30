import numpy as np
import pytest

from scripts.recompute_s3_full_adaptive import (
    REQUIRED_METHODS,
    joint_range_reference,
    objective_pool,
    pooled_reference,
    recompute_group,
)
from scripts.verdict_355m_and_rloo import paired_deltas


def summarize_pilot_arms(output):
    """Recompute normalized pilot HV without rerunning model inference."""
    from scripts.run_a6_rollout_pilot import summarize_arms
    return summarize_arms(output)


def test_pilot_summary_is_normalized_and_recomputable():
    output = {"arms": {
        "a": {"objectives": [[1.0, 10.0, -1.0, 0.0]]},
        "b": {"objectives": [[3.0, 20.0, -1.0, 2.0]]},
    }}
    assert summarize_pilot_arms(output) == summarize_pilot_arms(output)
    assert output["reference_protocol"].endswith("q95_scale_v3")
    assert len(output["normalization_scale"]) == 4
    assert all(value > 0 for value in output["normalization_scale"])
    # canonical A6 scale is the robust q95 - min range (matches pooled_reference),
    # not the full peak-to-peak range used by the retired v2 protocol.
    import numpy as _np
    unique_points = _np.asarray([[1.0, 10.0, -1.0, 0.0], [3.0, 20.0, -1.0, 2.0]])
    raw_scale = _np.quantile(unique_points, 0.95, axis=0) - unique_points.min(axis=0)
    expected_scale = _np.where(raw_scale > 0, raw_scale, 1.0)   # degenerate axes use unit scale
    assert _np.allclose(output["normalization_scale"], expected_scale)
    reference = output["arms"]["a"]["reference"]
    output["arms"]["duplicate_b"] = {"objectives": [[3.0, 20.0, -1.0, 2.0]]}
    summarize_pilot_arms(output)
    assert output["arms"]["a"]["reference"] == reference


def test_a6_pilot_cost_aggregation_uses_only_final_cumulative_rows():
    from scripts.run_a6_rollout_pilot import aggregate_trace_costs

    # T=4, C=4, R=2: the first and final rows are cumulative within one path.
    first = {
        "forward_calls": 17,
        "base_state_evaluations": 1,
        "rollout_batch_forwards": 16,
        "rollout_trajectories": 10,
        "rollout_state_transitions": 32,
        "terminal_reward_evaluations": 10,
    }
    final = {
        "forward_calls": 38,
        "base_state_evaluations": 4,
        "rollout_batch_forwards": 34,
        "rollout_trajectories": 32,
        "rollout_state_transitions": 68,
        "terminal_reward_evaluations": 37,
    }
    costs = aggregate_trace_costs([[first, final], [first, final]])
    assert costs["forward_calls"] == 76
    assert costs["base_state_evaluations"] == 8
    assert costs["rollout_batch_forwards"] == 68
    assert costs["rollout_trajectories"] == 64
    assert costs["rollout_state_transitions"] == 136
    assert costs["terminal_reward_evaluations"] == 74  # Not 194 from summing every row.


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


def test_joint_range_reference_normalizes_each_axis_and_handles_constant_pilot_axes():
    points = [[1.0, 10.0, -1.0], [3.0, 20.0, -1.0]]
    reference, scale = joint_range_reference(points, allow_degenerate=True)
    assert np.allclose(reference, [0.9, 9.5, -1.000001])
    assert np.allclose(scale, [2.0, 10.0, 1.0])
    with pytest.raises(ValueError, match="degenerate"):
        joint_range_reference(points)


def test_a6_baseline_counts_only_valid_unique_solutions(monkeypatch):
    from scripts.run_a6_baselines import score_method
    monkeypatch.setattr("scripts.run_a6_baselines.mfe_batch_parallel", lambda seqs: [-10.0] * len(seqs))
    weights = {codon: 1.0 for codon in ("TTT", "TTC", "GCT", "GCC", "GCA", "GCG")}
    result = score_method(
        "uniform_synonymous", ["TTTGCTTAA", "TTTGCT", "TTTGCTTAA", "ATGAAATAA"],
        "TTTGCTTAA", weights, {"elapsed_s": 0.1, "forward_calls": 0},
    )
    assert result["n_solutions"] == result["n_unique"] == 1
    assert result["n_invalid_identity"] == 1
    assert result["unique_terminal_reward_calls"] == 1
    assert result["identity_rate"] == 1.0


def test_a6_ld_and_official_generator_keep_real_budget(monkeypatch):
    from scripts.run_a6_baselines import generate_method
    source = "TTTGCTTAA"
    monkeypatch.setattr("scripts.run_a6_baselines.lineardesign_scan", lambda *args: [source] * 7)
    raw, generation = generate_method("lineardesign_scan", source, {}, 100, 0, "cpu")
    assert len(raw) == 7 and generation["generator_calls"] == 7
    assert generation["forward_calls"] is None
    monkeypatch.setattr("scripts.run_a6_baselines.run_generate", lambda protein: (source, 0.0))
    raw, generation = generate_method("gemorna", source, {}, 2, 0, "cpu")
    assert raw == [source, source] and generation["generator_calls"] == 2
    assert generation["forward_calls"] is None


def test_a6_codongpt_context_limit_is_explicit_exclusion():
    from scripts.run_a6_baselines import generate_method
    source = "ATG" + "GCT" * 1024 + "TAA"
    raw, generation = generate_method("codongpt", source, {}, 2, 0, "cpu", gpt=object())
    assert raw == [] and generation["status"] == "architectural_exclusion"
    assert generation["n_requested"] == 0


def test_a6_nested_baseline_protocol_loads_and_shared_baselines_do_not_shift_reference():
    nested = {
        "protocol": "a6_baselines_v1",
        "methods": {
            method: {"status": "done", "obj_vectors": row()[f"S3_quad/{method}/obj_vectors"]}
            for method in REQUIRED_METHODS if method != "codonflow"
        },
    }
    model = {"S3_quad/codonflow/obj_vectors": row()["S3_quad/codonflow/obj_vectors"]}
    first = pooled_reference([model, nested])
    repeated = pooled_reference([model, nested, nested])
    assert np.allclose(first[0], repeated[0])
    assert np.allclose(first[1], repeated[1])
    assert "gemorna" in objective_pool(nested)
    nested["methods"]["gemorna"]["status"] = "architectural_exclusion"
    with pytest.raises(ValueError, match="incomplete"):
        pooled_reference([model, nested])


def test_nonfinite_pool_fails():
    invalid = row()
    invalid["S3_quad/codonflow/obj_vectors"][0][0] = float("nan")
    with pytest.raises(ValueError, match="NaN"):
        pooled_reference([invalid])
