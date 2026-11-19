from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
from scipy import stats


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compare = load_module("rk08_compare", ROOT / "scripts" / "a8_rk08_compare_full_function.py")


def test_constant_prediction_spearman_is_null():
    result = compare.point_metrics(np.array([0.0, 1.0, 2.0]), np.ones(3), np.array(["a", "b", "c"]))
    assert result["row_spearman"] is None


def test_cluster_balanced_mse_is_not_row_weighted():
    y = np.array([0.0, 0.0, 0.0])
    pred = np.array([1.0, 1.0, 3.0])
    clusters = np.array(["small", "small", "large"])
    result = compare.point_metrics(y, pred, clusters)
    assert np.isclose(result["row_mse"], 11.0 / 3.0)
    assert np.isclose(result["cluster_balanced_mse"], 5.0)


def test_fast_spearman_handles_ties():
    rng = np.random.default_rng(7)
    y = rng.integers(0, 4, 40).astype(float)
    pred = rng.integers(0, 5, 40).astype(float)
    assert np.isclose(compare.fast_spearman(y, pred), stats.spearmanr(y, pred).statistic)


def test_holm_adjustment_is_monotone_and_bounded():
    p = np.array([0.01, 0.04, 0.03, 0.20])
    adjusted = compare.holm_adjust(p)
    assert np.all((adjusted >= p) & (adjusted <= 1.0))
    assert np.allclose(adjusted, [0.04, 0.09, 0.09, 0.20])


def test_full_configs_use_ood_assignment_and_only_ablation_differs():
    all_config = json.loads((ROOT / "configs" / "a8_rk08_full_function_all_config.json").read_text())
    none_config = json.loads((ROOT / "configs" / "a8_rk08_full_function_none_config.json").read_text())
    assert all_config["columns"]["split_column"] == "ood_assignment"
    assert none_config["columns"]["split_column"] == "ood_assignment"
    assert all_config["include_splits"] == ["train", "dev", "test", "sequence_ood"]
    assert all_config["max_rows_per_split"] is None
    assert all_config["model"]["max_len"] >= 1000
    assert {k: v for k, v in all_config.items() if k != "ablation"} == {k: v for k, v in none_config.items() if k != "ablation"}


def test_training_enables_deterministic_math_attention():
    text = (ROOT / "scripts" / "a8_rk08_train_ribokinetic.py").read_text()
    assert "torch.use_deterministic_algorithms(True, warn_only=True)" in text
    assert "torch.backends.cuda.enable_flash_sdp(False)" in text
    assert "torch.backends.cuda.enable_mem_efficient_sdp(False)" in text
    assert "torch.backends.cuda.enable_math_sdp(True)" in text


def test_preregistered_gate_is_not_generator_authorization():
    text = (ROOT / "scripts" / "a8_rk08_compare_full_function.py").read_text()
    assert '"primary_endpoint": "sequence_ood cluster_balanced_mse"' in text
    assert '"expensive_generation_authorized": False' in text
    assert '"sota_claimed": False' in text
    assert "test and sequence-OOD were excluded" in text
