from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import spearmanr

from scripts import a8_rk02_mordstein_proxy_robustness as production
from scripts import a8_rk02_verify_mordstein_proxy_robustness as independent


ROOT = Path(__file__).resolve().parents[2]


def test_support_bootstrap_matches_independent_and_is_deterministic():
    x = np.asarray([0.1, 0.4, 0.2, 0.8, 0.5, 0.9, 0.3, 0.7])
    y = np.asarray([0.2, 0.3, 0.1, 0.7, 0.6, 0.8, 0.4, 0.9])
    first = production.bootstrap_only(x, y, 31, 200)
    second = production.bootstrap_only(x, y, 31, 200)
    other = independent.support_recompute(x, y, 31, 200)
    assert first == second
    assert first["observed"] == pytest.approx(other["observed"])
    assert first["ci95_percentile"] == pytest.approx(other["ci95_percentile"])


def test_partial_rank_matches_independent_and_reduces_depth_driven_association():
    depth = np.asarray([1., 2., 3., 4., 5., 6.])
    residual = np.asarray([0., 1., -1., 0., 1., -1.])
    x = depth + residual
    y = 3 * depth - 2 * residual
    partial = production.partial_rank(x, y, depth)
    assert partial == pytest.approx(independent.partial_rank(x, y, depth))
    assert abs(partial) < abs(float(spearmanr(x, y).statistic))


def test_posthoc_protocol_does_not_change_primary_or_scope():
    protocol = json.loads((ROOT / "configs/a8_rk02_mordstein_proxy_robustness_protocol_v1.json").read_text())
    assert protocol["analysis_status"] == "POST_HOC_EXPLORATORY_NOT_PRIMARY_NOT_A_NEW_GATE"
    assert protocol["support_thresholds"] == [1000, 2000, 5000, 10000, 20000, 50000, 100000]
    assert protocol["bootstrap_resamples"] == protocol["permutation_resamples"] == 20000
    assert protocol["boundaries"]["changes_primary_analysis"] is False
    assert protocol["boundaries"]["causal_inference"] is False
    assert protocol["boundaries"]["protein_ood_evaluation"] is False
    assert protocol["boundaries"]["generator_training_authorized"] is False
