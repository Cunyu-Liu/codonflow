from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import spearmanr


ROOT = Path(__file__).resolve().parents[2]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


production = load("mordstein_proxy_production", ROOT / "scripts/a8_rk02_mordstein_proxy_diagnostics.py")
independent = load("mordstein_proxy_independent", ROOT / "scripts/a8_rk02_verify_mordstein_proxy.py")


def test_flowseq_score_hand_example_and_input_gate():
    assert production.flowseq_score([1, 1, 0, 0, 0, 0, 0, 0]) == 1.5
    assert production.flowseq_score([0, 0, 0, 0, 0, 0, 0, 9]) == 8.0
    with pytest.raises(ValueError):
        production.flowseq_score([0] * 8)
    with pytest.raises(ValueError):
        production.flowseq_score([1] * 7)


def test_observed_codon_frame_gc_gc3_and_cpg():
    sequence = list("AAA" * 100)
    sequence[2] = "G"
    sequence[3:6] = list("CGT")
    sequence = "".join(sequence)
    features = production.feature_values(sequence)
    assert features["gc3_observed_5prime"] == pytest.approx(0.01)
    assert features["gc_observed_5prime"] == pytest.approx(3 / 300)
    assert features["cpg_per_100nt_observed_5prime"] == pytest.approx(100 / 299)


def test_observed_sequence_validation():
    with pytest.raises(ValueError):
        production.feature_values("AAA")
    with pytest.raises(ValueError):
        production.feature_values("N" * 300)


def test_correlation_direction_and_ties_match_scipy():
    x = np.asarray([1.0, 2.0, 2.0, 4.0, 5.0])
    y = np.asarray([2.0, 3.0, 3.0, 7.0, 9.0])
    assert production.correlation("spearman", x, y) == pytest.approx(1.0)
    assert production.correlation("pearson", x, -(2.0 * x + 1.0)) == pytest.approx(-1.0)
    assert independent.corr(x, -y, "spearman") == pytest.approx(float(spearmanr(x, -y).statistic))


def test_bootstrap_permutation_is_deterministic():
    x = np.asarray([0.1, 0.4, 0.2, 0.8, 0.5, 0.9, 0.3, 0.7])
    y = np.asarray([0.2, 0.3, 0.1, 0.7, 0.6, 0.8, 0.4, 0.9])
    first = production.association(x, y, "spearman", 19, 200)
    second = production.association(x, y, "spearman", 19, 200)
    independent_result = independent.recompute_association(x, y, "spearman", 19, 200)
    assert first == second
    assert first["observed"] == pytest.approx(independent_result["observed"])
    assert first["ci95_percentile"] == pytest.approx(independent_result["ci95_percentile"])
    assert first["permutation_p_two_sided"] == pytest.approx(independent_result["permutation_p_two_sided"])


def test_holm_and_frozen_scientific_boundaries():
    items = [{"permutation_p_two_sided": 0.04}, {"permutation_p_two_sided": 0.01}]
    production.holm(items)
    assert items[0]["holm_p"] == pytest.approx(0.04)
    assert items[1]["holm_p"] == pytest.approx(0.02)
    protocol = json.loads((ROOT / "configs/a8_rk02_mordstein_proxy_protocol_v1.json").read_text())
    assert protocol["created_before_production"] is True
    assert protocol["statistics"]["bootstrap_resamples"] == 20000
    assert protocol["statistics"]["permutation_resamples"] == 20000
    assert protocol["boundaries"]["protein_ood_evaluation"] is False
    assert protocol["boundaries"]["simple_proxy_failure_test"] is False
    assert protocol["boundaries"]["generator_training_authorized"] is False
