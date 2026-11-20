import json
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import spearmanr

from scripts import a8_rk23_run_boel_uh as rk23


ROOT = Path(__file__).resolve().parents[1]


def protocol():
    return json.loads((ROOT / "audits/20261121/RK23/a8_rk23_boel_uh_protocol_v1.json").read_text())


def test_gc3_excludes_terminal_stop():
    assert rk23.gc3_fraction("ATGGCTAAAGGCTAA") == pytest.approx(0.5)


def test_gc3_requires_terminal_stop():
    with pytest.raises(ValueError, match="terminal stop"):
        rk23.gc3_fraction("ATGGCTAAA")


def test_feature_matrix_uses_log_length_and_source_uh():
    rows = [{"length_nt": 100, "source_Gz48v": -20.0}, {"length_nt": 200, "source_Gz48v": -10.0}]
    x = rk23.feature_matrix(rows, ["log_length_nt", "source_Gz48v"])
    np.testing.assert_allclose(x, [[np.log(100), -20], [np.log(200), -10]])


def test_regression_metrics_and_effect_sign():
    y = np.array([0, 1, 2, 3, 4, 5], dtype=float)
    base = 5 - y
    augmented = y.copy()
    b = rk23.regression_metrics(y, base, np.arange(6), 0.2, 5)
    a = rk23.regression_metrics(y, augmented, np.arange(6), 0.2, 5)
    assert b["mse"] == pytest.approx(70 / 6) and a["mse"] == 0
    assert b["mse"] - a["mse"] > 0
    assert a["spearman"] - b["spearman"] > 0


def test_fast_spearman_matches_scipy_with_ties():
    rng = np.random.default_rng(23)
    for _ in range(20):
        y = rng.integers(0, 6, 90)
        p = np.round(rng.normal(size=90), 1)
        assert rk23.fast_spearman(y, p) == pytest.approx(spearmanr(y, p).statistic, abs=1e-14)


def test_holm_monotonic_adjustment():
    adjusted = rk23.holm_adjust({"a": 0.01, "b": 0.02, "c": 0.5})
    assert adjusted == {"a": pytest.approx(0.03), "b": pytest.approx(0.04), "c": pytest.approx(0.5)}


def test_paired_resampling_shapes_and_point_effects(tmp_path):
    rng = np.random.default_rng(23)
    clusters = np.repeat(np.arange(8), 8)
    y = np.tile(np.arange(8) % 6, 8).astype(float)
    base = y + rng.normal(scale=1.0, size=len(y))
    augmented = y + rng.normal(scale=0.2, size=len(y))
    cfg = protocol()
    cfg["bootstrap"]["replicates"] = 40
    cfg["permutation"]["replicates"] = 40
    contrast = cfg["primary_contrast"]["name"]
    predictions = {f"{contrast}_base_logistic": base, f"{contrast}_augmented_logistic": augmented,
                   f"{contrast}_base_histgb": base, f"{contrast}_augmented_histgb": augmented}
    out = rk23.resample_primary(y, predictions, clusters, cfg, 0, tmp_path / "arrays.npz")
    arrays = np.load(tmp_path / "arrays.npz")
    assert arrays["bootstrap_effects"].shape == (40, 2, 2)
    assert arrays["permutation_effects"].shape == (40, 2, 2)
    expected = np.mean((y - base) ** 2) - np.mean((y - augmented) ** 2)
    assert out["comparisons"]["logistic_mse_improvement"]["effect"] == pytest.approx(expected)


def test_primary_features_only_add_uh_to_rk07():
    cfg = protocol()["primary_contrast"]
    assert cfg["augmented_features"] == cfg["base_features"] + ["source_Gz48v"]


def test_secondary_features_only_add_uh_to_simple():
    cfg = protocol()["secondary_descriptive_contrast"]
    assert cfg["augmented_features"] == cfg["base_features"] + ["source_Gz48v"]


def test_functional_untouched_and_generator_are_closed():
    cfg = protocol()
    assert cfg["forbidden_split"] == "functional_untouched"
    assert cfg["gate"]["generator_training_authorized"] is False
    assert cfg["gate"]["rk_g1_remains_false_even_if_pass"] is True


def test_optimized_prediction_quantiles_are_not_expression_ground_truth():
    cfg = protocol()["optimized_construct_boundary"]
    assert cfg["measured_expression_numeric_table_available"] is False
    assert cfg["fixed_protein_functional_test_performed"] is False
    assert cfg["image_digitization_allowed"] is False


def test_input_hash_field_mapping_is_explicit():
    cfg = protocol()
    assert rk23.INPUT_HASH_KEYS == {
        "split_file": "split_sha256",
        "feature_file": "feature_file_sha256",
        "feature_summary": "feature_summary_sha256",
    }
    for path_key, digest_key in rk23.INPUT_HASH_KEYS.items():
        assert path_key in cfg and digest_key in cfg


def test_fixed_model_and_four_endpoint_contract():
    cfg = protocol()
    assert len(cfg["primary_endpoints"]) == 4
    assert cfg["models"]["histgb"]["selection"].startswith("fixed")
    assert cfg["models"]["logistic"]["selection"].startswith("fixed")
    assert cfg["multiple_testing"].startswith("Holm across exactly four")
