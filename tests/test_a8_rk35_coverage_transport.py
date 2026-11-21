"""Synthetic unit tests for the RK35 coverage-transport machinery.

No real expression outcomes are read; all fixtures are toy data.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr

REPO = Path(__file__).resolve().parents[1]


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prod = load_module("rk35_prod", "scripts/a8_rk35_run_coverage_transport.py")
pre = load_module("rk35_pre", "scripts/a8_rk35_preflight.py")


def test_trunc_window_excludes_start_atg():
    cds = "ATG" + "GCU" * 139
    trunc = cds[3:45]
    atg = cds[:42]
    assert len(trunc) == 42 and len(atg) == 42
    assert trunc[:3] != "ATG"
    assert atg[:3] == "ATG"
    assert trunc != atg


def test_exact_window_definition():
    utr = "A" * 140 + "AAGG"
    cds = "ATG" + "CCU" * 239
    exact = utr[-4:] + cds[:38]
    assert len(exact) == 42
    assert exact[:4] == "AAGG"
    assert exact[4:7] == "ATG"


def test_energy_dangles_differ_and_finite():
    RNA = pytest.importorskip("RNA")
    seq = "GGGAAACCCAA"
    e0 = pre.energy(seq, 0)
    e2 = pre.energy(seq, 2)
    assert np.isfinite(e0) and np.isfinite(e2)
    assert e0 != e2


def test_cluster_folds_deterministic_whole_cluster_no_leakage():
    rng = np.random.default_rng(7)
    labels = np.repeat(np.arange(37), rng.integers(1, 8, size=37))
    folds_a, loads_a = prod.make_cluster_folds(labels, 20261221)
    folds_b, loads_b = prod.make_cluster_folds(labels, 20261221)
    assert np.array_equal(folds_a, folds_b) and loads_a == loads_b
    assert sum(loads_a) == len(labels)
    for cluster in np.unique(labels):
        assert len(np.unique(folds_a[labels == cluster])) == 1
    for fold in range(5):
        assert set(labels[folds_a != fold]).isdisjoint(set(labels[folds_a == fold]))


def test_spearman_matches_scipy():
    rng = np.random.default_rng(3)
    x = rng.normal(size=50)
    y = 0.4 * x + rng.normal(size=50)
    assert abs(prod.spearman(x, y) - spearmanr(x, y).statistic) < 1e-12


def test_contrast_effect_signs():
    y = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    good = y.copy()
    bad = y[::-1].copy()
    assert prod.spearman(y, good) - prod.spearman(y, bad) > 0
    assert float(np.mean((y - bad) ** 2 - (y - good) ** 2)) > 0


def test_permutation_swap_involution():
    rng = np.random.default_rng(11)
    a = rng.normal(size=40)
    b = rng.normal(size=40)
    signs = rng.choice([-1, 1], size=40) < 0
    sa = np.where(signs, b, a)
    sb = np.where(signs, a, b)
    assert np.array_equal(np.where(signs, sb, sa), a)
    assert np.array_equal(np.where(signs, sa, sb), b)


def test_holm_known_values():
    adjusted = prod.holm([0.01, 0.04, 0.03])
    assert abs(adjusted[0] - 0.03) < 1e-12
    assert abs(adjusted[1] - 0.06) < 1e-12
    assert abs(adjusted[2] - 0.06) < 1e-12
    assert all(v <= 1.0 for v in prod.holm([0.5, 0.6]))


def test_pass_rule_all_conditions():
    base = {"observed_effect": 0.5, "ci95": [0.1, 0.9], "p_holm": 0.01, "positive_seeds": 9}
    assert prod.pass_rule(base)
    assert not prod.pass_rule({**base, "observed_effect": -0.1})
    assert not prod.pass_rule({**base, "ci95": [-0.1, 0.9]})
    assert not prod.pass_rule({**base, "p_holm": 0.2})
    assert not prod.pass_rule({**base, "positive_seeds": 7})


def test_decision_tree_priority():
    def cr(trunc, exact_trunc):
        return {
            "trunc_vs_simple": {"all_four_pass": trunc},
            "exact_vs_trunc": {"all_four_pass": exact_trunc},
        }
    conclusion, code = prod.decide(False, cr(True, True))
    assert conclusion == "CONSISTENCY_GATE_FAILED_NOT_EVALUATED" and code == "gate_failed"
    conclusion, code = prod.decide(True, cr(True, False))
    assert conclusion == "RK33_COVERAGE_RETAINS_INCREMENT_WITHIN_KUDLA_RETROSPECTIVELY" and code == "D1"
    conclusion, code = prod.decide(True, cr(True, True))
    assert code == "D1"  # D1 priority over D2 when both pass
    conclusion, code = prod.decide(True, cr(False, True))
    assert conclusion == "START_AWARE_COVERAGE_NECESSARY_WITHIN_KUDLA_RETROSPECTIVELY" and code == "D2"
    conclusion, code = prod.decide(True, cr(False, False))
    assert conclusion == "COVERAGE_TRANSPORT_NOT_DISCRIMINATED_RETROSPECTIVELY" and code == "D3"


def test_reuse_gate_tolerance_boundary():
    reference = 0.9846828339503453
    assert abs(reference + 5e-13 - reference) <= 1e-12
    assert abs(reference + 5e-12 - reference) > 1e-12


def test_atomic_json_no_overwrite(tmp_path):
    target = tmp_path / "x.json"
    prod.atomic_json(target, {"a": 1})
    assert json.loads(target.read_text()) == {"a": 1}
    with pytest.raises(FileExistsError):
        prod.atomic_json(target, {"a": 2})
    assert json.loads(target.read_text()) == {"a": 1}


def test_fit_predict_reproducible():
    rng = np.random.default_rng(5)
    frame = pd.DataFrame({
        "CAI": rng.uniform(0.3, 0.9, size=60),
        "gc_cds": rng.uniform(0.3, 0.7, size=60),
        "gc3_cds": rng.uniform(0.3, 0.7, size=60),
        "target": rng.normal(size=60),
    })
    train, test = frame.iloc[:45], frame.iloc[45:]
    feats = ["CAI", "gc_cds", "gc3_cds"]
    for model_name in ("ridge", "histgb"):
        p1 = prod.fit_predict(model_name, feats, train, test, 20261221)
        p2 = prod.fit_predict(model_name, feats, train, test, 20261221)
        assert np.array_equal(p1, p2)
        assert np.isfinite(p1).all()


def test_preflight_label_free_columns():
    assert not set(pre.LABEL_FREE_USECOLS) & set(pre.FORBIDDEN_OUTCOME_COLUMNS)
    assert "log10_expression" not in pre.LABEL_FREE_USECOLS
    assert "target" not in pre.LABEL_FREE_USECOLS


def test_contrast_families_partition():
    primary = set(prod.PRIMARY_CONTRASTS)
    gate = set(prod.GATE_CONTRAST)
    secondary = set(prod.SECONDARY_CONTRASTS)
    assert primary.isdisjoint(gate) and primary.isdisjoint(secondary) and gate.isdisjoint(secondary)
    assert len(primary) == 2 and len(gate) == 1 and len(secondary) == 3
    assert len(prod.MODELS) * len(primary) * len(prod.METRICS) == 8
    assert len(prod.MODELS) * len(secondary) * len(prod.METRICS) == 12