#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

import a8_rk28_run_sequence_cluster_ood as rk28
import a8_rk30_run_matched_context as model

PROTOCOL = json.loads(Path(os.environ["RK30_PROTOCOL"]).read_text())


def synthetic_analysis(n=100):
    rng = np.random.default_rng(7)
    frame = pd.DataFrame({"variant_id": [f"v{i}" for i in range(n)],
                          "sequence_cluster_id": np.arange(n) % 60})
    for name in PROTOCOL["features"]["simple"] + PROTOCOL["features"]["structure_addition"]:
        frame[name] = rng.normal(size=n)
    for context in PROTOCOL["contexts"]:
        frame[f"target__{context}"] = rng.normal(size=n)
    return frame


def test_transport_frame_excludes_target_outcome_and_cluster_overlap():
    analysis = synthetic_analysis()
    folds, _ = rk28.make_cluster_folds(analysis["sequence_cluster_id"].to_numpy(int), 20261222)
    pair = {"source": "hela_no_intron", "target": "hek293_no_intron"}
    train, test = model.transport_train_test(analysis, pair, folds, 0)
    assert "target__hek293_no_intron" not in train.columns
    assert "target__hela_no_intron" not in train.columns
    assert train["target"].equals(analysis.loc[folds != 0, "target__hela_no_intron"])
    assert test["target"].equals(analysis.loc[folds == 0, "target__hek293_no_intron"])
    assert set(train["sequence_cluster_id"]).isdisjoint(test["sequence_cluster_id"])


def test_transport_metrics_direction_and_absolute_arms():
    rng = np.random.default_rng(11)
    y = rng.normal(size=100)
    simple = y + rng.normal(scale=2, size=100)
    frame = pd.DataFrame({"target": y, "null": np.zeros(100),
                          "ridge_simple": simple, "ridge_structure": y,
                          "histgb_simple": simple, "histgb_structure": y})
    rows, effects = model.transport_metrics(frame)
    assert len(rows) == 5
    assert 0.4 < effects["ridge_spearman_effect"] < 0.7
    assert effects["ridge_mse_improvement"] > 0
    assert 0.4 < effects["histgb_spearman_effect"] < 0.7
    assert effects["histgb_mse_improvement"] > 0


def test_general_holm_is_monotone_and_exact_on_small_case():
    assert model.holm_adjust([0.01, 0.02, 0.03]) == [0.03, 0.04, 0.04]
    assert len(model.holm_adjust([0.05] * 16)) == 16
    assert model.holm_adjust([0.05] * 16) == [0.8] * 16


def test_real_label_free_features_remain_finite_and_depth_free():
    features = model.build_feature_table(PROTOCOL)
    assert len(features) == 152
    assert features["sequence_cluster_id"].nunique() == 74
    names = PROTOCOL["features"]["simple"] + PROTOCOL["features"]["structure_addition"]
    assert np.isfinite(features[names].to_numpy(float)).all()
    assert "log1p_total_assigned_reads" not in PROTOCOL["features"]["simple"]


def test_primary_fold_coverage_and_cluster_exclusivity():
    analysis = synthetic_analysis()
    loads = model.check_primary_folds(analysis, PROTOCOL)
    assert sum(loads) == len(analysis)
    folds, _ = rk28.make_cluster_folds(analysis["sequence_cluster_id"].to_numpy(int), 20261222)
    for fold in range(5):
        assert set(analysis.loc[folds == fold, "sequence_cluster_id"]).isdisjoint(
            analysis.loc[folds != fold, "sequence_cluster_id"])


def test_frozen_fit_budget_and_primary_family_size():
    assert len(PROTOCOL["primary_transport"]["ordered_pairs"]) * 4 == 16
    assert PROTOCOL["models"]["expected_transport_fits"] == 800
    assert PROTOCOL["models"]["expected_within_context_fits"] == 900
    assert PROTOCOL["models"]["expected_total_fits"] == 1700


def test_secondary_cannot_redefine_primary_gate():
    text = Path(model.__file__).read_text()
    assert "family_pass = all(row[\"pass\"] for row in primary_rows)" in text
    assert "Secondary within-context results cannot rescue primary transport failure" in text


def test_all_contexts_have_predeclared_replicates_and_targets():
    analysis = synthetic_analysis()
    for context, definition in PROTOCOL["contexts"].items():
        assert f"target__{context}" in analysis
        assert len(definition["replicates"]) * 8 == definition["expected_runs"]
