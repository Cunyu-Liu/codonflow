from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load_module("rk20_prepare", ROOT / "scripts" / "a8_rk20_prepare_functional_multiseed.py")
compare = load_module("rk20_compare", ROOT / "scripts" / "a8_rk20_compare_functional_multiseed.py")
PROTOCOL = json.loads((ROOT / "configs" / "a8_rk20_functional_multiseed_protocol_v1.json").read_text())


def test_protocol_freezes_all_seeds_and_strong_controls():
    assert PROTOCOL["seeds"] == [20261119, 20261120, 20261121, 20261122]
    assert PROTOCOL["new_seeds"] == [20261120, 20261121, 20261122]
    assert PROTOCOL["training_contract"]["only_allowed_config_change"] == "training.seed"
    assert PROTOCOL["comparisons"] == [
        ["ribokinetic_all", "ribokinetic_none"],
        ["ribokinetic_all", "ridge_all"],
        ["ribokinetic_all", "ridge_gc"],
        ["ribokinetic_all", "histgb_all"],
    ]
    assert PROTOCOL["statistics"]["replicates"] == 2000
    assert PROTOCOL["data"]["functional_untouched_evaluated"] is False


def test_functional_robustness_cannot_open_global_gates():
    decision = PROTOCOL["decision"]
    assert decision["global_rk_g1_pass_remains_false"] is True
    assert decision["expensive_generation_authorized"] is False
    assert decision["functional_untouched_evaluation_authorized"] is False
    assert decision["sota_claim_authorized"] is False


def test_generated_config_changes_only_seed():
    base = {"training": {"seed": 1, "lr": 0.001}, "model": {"width": 16}}
    generated = {"training": {"seed": 2, "lr": 0.001}, "model": {"width": 16}}
    assert prepare.only_seed_changed(base, generated, 2)
    generated["model"]["width"] = 32
    assert not prepare.only_seed_changed(base, generated, 2)


def test_hierarchical_bootstrap_is_reproducible_and_paired():
    y = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
    clusters = np.array(["a", "a", "b", "b", "c", "c", "d", "d"])
    indices = np.arange(len(y))
    predictions = {
        seed: {
            "left": y.copy(),
            "right": 7.0 - y,
        }
        for seed in (10, 20)
    }
    kwargs = dict(
        y=y, indices=indices, clusters=clusters, predictions=predictions,
        seeds=[10, 20], models=["left", "right"], comparisons=[("left", "right")],
        replicates=50, seed=99,
    )
    first = compare.hierarchical_bootstrap_deltas(**kwargs)
    second = compare.hierarchical_bootstrap_deltas(**kwargs)
    assert first == second
    assert np.allclose(first[("left", "right", "spearman")], 2.0)
    mse_samples = first[("left", "right", "cluster_balanced_mse")]
    assert set(mse_samples).issubset({-37.0, -29.0, -21.0, -13.0, -5.0})
    assert abs(float(np.mean(mse_samples)) + 21.0) < 5.0


def test_bootstrap_seed_changes_finite_sample_not_contract():
    rng = np.random.default_rng(4)
    y = rng.normal(size=40)
    clusters = np.repeat(np.arange(10).astype(str), 4)
    indices = np.arange(len(y))
    predictions = {
        seed: {"left": y + rng.normal(scale=0.2, size=40), "right": y + rng.normal(scale=1.0, size=40)}
        for seed in (10, 20)
    }
    kwargs = dict(
        y=y, indices=indices, clusters=clusters, predictions=predictions,
        seeds=[10, 20], models=["left", "right"], comparisons=[("left", "right")],
        replicates=20,
    )
    first = compare.hierarchical_bootstrap_deltas(**kwargs, seed=1)
    second = compare.hierarchical_bootstrap_deltas(**kwargs, seed=2)
    assert first[("left", "right", "cluster_balanced_mse")] != second[("left", "right", "cluster_balanced_mse")]


def test_holm_and_constant_prediction_contracts():
    adjusted = compare.holm_adjust([0.01, 0.04, 0.03, 0.20])
    assert np.allclose(adjusted, [0.04, 0.09, 0.09, 0.20])
    assert np.isnan(compare.fast_spearman(np.arange(4.0), np.ones(4)))


def test_comparison_does_not_create_or_authorize_an_ensemble():
    text = (ROOT / "scripts" / "a8_rk20_compare_functional_multiseed.py").read_text()
    assert '"prediction_ensemble_evaluated": False' in text
    assert '"rk_g1_pass": False' in text
    assert '"expensive_generation_authorized": False' in text
    assert "Mean per-seed" in PROTOCOL["statistics"]["estimand"]
