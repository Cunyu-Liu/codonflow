"""Contract tests for the A6 joint-hypervolume aggregator (scripts/a6_joint_hv.py)."""
import json

import numpy as np

from scripts.a6_joint_hv import BASELINE_METHODS, build_group, joint_reference


def _pilot(gene, seed, arms):
    return {
        "gene": gene,
        "seed": seed,
        "source_file": "pilot.json",
        "methods": {
            f"cf_{name}": {
                "status": "done",
                "points": np.asarray(points, dtype=float),
                "n_solutions": len(points),
                "n_unique": len(points),
                "identity_rate": 1.0,
                "ned": 0.1,
            }
            for name, points in arms.items()
        },
    }


def _baseline(gene, seed, methods):
    return {
        "gene": gene,
        "seed": seed,
        "source_file": "base.json",
        "methods": {
            name: {
                "status": status,
                "points": np.asarray(points, dtype=float),
                "n_solutions": len(points),
                "identity_rate": 1.0 if status == "done" else None,
            }
            for name, (status, points) in methods.items()
        },
    }


def test_joint_reference_uses_q95_scale_and_ptp_offset():
    rng = np.random.default_rng(0)
    pts = rng.uniform(0.2, 0.8, size=(32, 4))
    reference, scale, degenerate = joint_reference(pts, allow_degenerate=False)
    assert degenerate == []
    assert np.allclose(scale, np.quantile(pts, 0.95, axis=0) - pts.min(axis=0))
    assert np.allclose(reference, pts.min(axis=0) - 0.05 * np.ptp(pts, axis=0))


def test_joint_reference_rejects_degenerate_axes():
    pts = np.column_stack([np.linspace(0, 1, 8), np.linspace(0, 1, 8), np.full(8, 5.0)])
    pts = np.column_stack([pts, np.linspace(0, 1, 8)])
    try:
        joint_reference(pts, allow_degenerate=False)
        raise AssertionError("degenerate axis must be rejected")
    except ValueError:
        pass
    _, _, degenerate = joint_reference(pts, allow_degenerate=True)
    assert degenerate == [2]


def test_build_group_lists_missing_methods_and_never_scores_zero():
    pilot = _pilot("egfp", 0, {
        "base": [[0.5, 100, -0.1, -3], [0.6, 120, -0.2, -1]],
        "immediate": [[0.55, 110, -0.15, -2], [0.65, 130, -0.05, -4]],
        "short_rollout": [[0.52, 105, -0.12, -2.5], [0.62, 125, -0.08, -3.5]],
    })
    baseline = _baseline("egfp", 0, {
        "lineardesign_scan": ("done", [[0.45, 90, -0.3, -5], [0.7, 140, -0.4, -6]]),
        "gemorna": ("done", [[0.6, 115, -0.2, -2]]),
        "codongpt": ("architectural_exclusion", []),
        "cai_greedy": ("done", [[0.8, 150, -0.5, -8]]),
        "uniform_synonymous": ("done", [[0.35, 80, -0.25, -1]]),
    })
    group = build_group(pilot, [baseline], allow_degenerate=False)
    assert group["missing_methods"] == ["codongpt"]
    assert "codongpt" not in group["methods"]
    assert len(group["methods"]) == 7
    assert len(group["reference"]) == 4 and len(group["scale"]) == 4
    # every reported method is inside the joint reference box
    for entry in group["methods"].values():
        assert entry["hv"] >= 0.0
    assert group["n_union_points"] <= 3 * 2 + 2 + 1 + 1 + 1


def test_build_group_deduplicates_shared_baselines():
    pilot = _pilot("nluc", 0, {"base": [[0.5, 100, -0.1, -3]]})
    shared = _baseline("nluc", 0, {
        "lineardesign_scan": ("done", [[0.5, 100, -0.1, -3], [0.6, 110, -0.2, -2]]),
    })
    group = build_group(pilot, [shared], allow_degenerate=False)
    assert group["n_union_points"] == 2       # the duplicated vector counted once
    assert group["missing_methods"] == sorted(
        ["cai_greedy", "cf_immediate", "cf_short_rollout", "codongpt", "gemorna", "uniform_synonymous"])


def test_output_is_json_serialisable():
    pilot = _pilot("egfp", 0, {"base": [[0.5, 100, -0.1, -3], [0.6, 120, -0.2, -1]]})
    baseline = _baseline("egfp", 0, {
        "lineardesign_scan": ("done", [[0.7, 140, -0.4, -6]]),
    })
    group = build_group(pilot, [baseline], allow_degenerate=False)
    json.dumps(group)   # raises if any numpy scalar leaked into the payload
