import pytest

from codonflow.eval.paired_stats import holm_adjust, paired_gene_effects


def test_holm_adjustment_is_monotone_in_original_order():
    assert holm_adjust([0.01, 0.02, 0.03]) == [0.03, 0.04, 0.04]


def test_paired_effects_average_seeds_within_gene():
    rows = []
    for gene, learned in [("g1", 1.2), ("g2", 1.4), ("g3", 1.1)]:
        for seed in [0, 1]:
            rows.extend([
                {"gene": gene, "seed": seed, "method": "learned", "auc": learned},
                {"gene": gene, "seed": seed, "method": "uniform", "auc": 0.9},
                {"gene": gene, "seed": seed, "method": "hill_climbing", "auc": 1.0},
            ])
    result = paired_gene_effects(rows, ["uniform", "hill_climbing"], n_bootstrap=100)
    assert result["n_genes"] == 3
    assert all(row["strongest_simple_auc"] == 1.0 for row in result["per_gene"])
    assert all(row["n_seeds"] == 2 for row in result["per_gene"])
    assert result["paired_bootstrap_95ci"][0] > 0
    assert result["median_relative_improvement"] > 0


def test_relative_effect_rejects_zero_simple_auc():
    rows = [
        {"gene": "g1", "seed": 0, "method": "learned", "auc": 1.0},
        {"gene": "g1", "seed": 0, "method": "uniform", "auc": 0.0},
    ]
    with pytest.raises(ValueError, match="positive simple AUC"):
        paired_gene_effects(rows, ["uniform"], n_bootstrap=10)
