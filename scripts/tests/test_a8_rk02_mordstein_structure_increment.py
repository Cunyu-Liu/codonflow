import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "a8_rk02_mordstein_structure_increment.py"
spec = importlib.util.spec_from_file_location("mordstein_structure_increment", MODULE_PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_standard_genetic_code_is_complete():
    assert len(m.CODON_TABLE) == 64
    assert len(m.SYNONYMS) == 61
    assert m.translate("ATGGCTTAA") == "MA*"
    assert m.STOPS == {"TAA", "TAG", "TGA"}


def test_cai_reference_weights_and_atg_tgg_exclusion():
    weights = m.reference_weights(["AAAGAA"])
    assert weights["AAG"] == pytest.approx(0.5)
    assert m.cai_from_weights("ATGAAGTGG", weights) == pytest.approx(0.5)


def test_cai_rejects_invalid_weight():
    with pytest.raises(ValueError):
        m.cai_from_weights("AAG", {"AAG": 0.0})


def test_flowseq_score_and_count_validation():
    assert m.flowseq_score([1, 0, 0, 0, 0, 0, 0, 1]) == 4.5
    with pytest.raises(ValueError):
        m.flowseq_score([0] * 8)


def test_simple_feature_formulas():
    sequence = "ATG" + "GCT" * 99
    weights = m.reference_weights(["GCTGCC"])
    f = m.simple_features(sequence, 1000, weights)
    assert f["log1p_total_assigned_reads"] == math.log1p(1000)
    assert f["gc3_observed_5prime"] == 0.01
    assert f["gc_observed_5prime"] == pytest.approx(sum(c in "GC" for c in sequence) / 300)
    assert f["cpg_per_100nt_observed_5prime"] == 0.0
    assert 0 < f["cai_human_def_refs_observed_r1"] <= 1


def test_structure_features_finite_on_300nt():
    f = m.structure_features("A" * 300)
    assert set(f) == set(m.STRUCTURE_FEATURES)
    assert all(math.isfinite(v) and abs(v) < 100000 for v in f.values())
    assert f["mfe_observed_r1_window48_min_kcal_mol"] <= f["mfe_observed_r1_window48_mean_kcal_mol"]


def test_folds_are_deterministic_and_cover_every_variant():
    ids = [f"v{i:03d}" for i in range(152)]
    a = m.fold_assignments(ids, 20261120, 5)
    assert a == m.fold_assignments(ids, 20261120, 5)
    assert set(a) == set(ids)
    assert [sum(v == f for v in a.values()) for f in range(5)] == [31, 31, 30, 30, 30]


def test_oof_ridge_is_deterministic_and_finite():
    rng = np.random.default_rng(9)
    rows = []
    for i in range(50):
        a, b = rng.normal(), rng.normal()
        rows.append({"variant_id": f"v{i}", "x": a, "z": b, "flowseq_score_r1_only": 2 * a - b + 0.1})
    folds = m.fold_assignments([r["variant_id"] for r in rows], 20261120, 5)
    p1 = m.cross_validated_predictions(rows, ["x", "z"], folds, 1.0, 5)
    p2 = m.cross_validated_predictions(rows, ["x", "z"], folds, 1.0, 5)
    assert np.array_equal(p1, p2)
    assert np.isfinite(p1).all()


def test_paired_statistics_direction_and_reproducibility():
    rng = np.random.default_rng(11)
    y = rng.normal(size=60)
    simple = y + rng.normal(scale=0.8, size=60)
    structure = y + rng.normal(scale=0.1, size=60)
    a = m.paired_statistics(y, simple, structure, "delta_spearman", 1234, 200)
    b = m.paired_statistics(y, simple, structure, "delta_spearman", 1234, 200)
    c = m.paired_statistics(y, simple, structure, "delta_mse", 5678, 200)
    assert a == b
    assert a["observed"] > 0 and c["observed"] < 0
    assert 0 < a["permutation_p_two_sided"] <= 1


def test_holm_is_monotone():
    items = [{"permutation_p_two_sided": 0.01}, {"permutation_p_two_sided": 0.04}]
    m.holm(items)
    assert items[0]["holm_p"] == pytest.approx(0.02)
    assert items[1]["holm_p"] == pytest.approx(0.04)


def test_protocol_does_not_authorize_untouched_or_generator():
    protocol = json.loads((Path(__file__).resolve().parents[2] / "configs" / "a8_rk02_mordstein_structure_increment_protocol_v1.json").read_text())
    assert protocol["confirmatory_independent_test"] is False
    assert protocol["boundaries"]["functional_untouched_evaluation"] is False
    assert protocol["boundaries"]["generator_training_authorized"] is False
    assert protocol["statistics"]["bootstrap_resamples"] == 20000
