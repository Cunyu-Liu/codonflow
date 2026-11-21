#!/usr/bin/env python3
"""Unit tests for A8-RK29. Synthetic data only; no source outcome access."""
import unittest

import numpy as np
import pandas as pd

import a8_rk29_label_free_coverage as cov
import a8_rk29_run_decay_cluster_ood as prod


class TestRK29(unittest.TestCase):
    def test_holm(self):
        adjusted = prod.holm_adjust([0.01, 0.04, 0.03, 0.20])
        np.testing.assert_allclose(adjusted, [0.04, 0.09, 0.09, 0.20])

    def test_canonical_name_grammar(self):
        self.assertEqual(cov.canonical_metadata("c1-p1-run-r1"), ("c1_p1", "iCodon_1"))
        self.assertEqual(cov.canonical_metadata("c7-p9-run-rIDT_1"), ("c7_p9", "IDT"))
        self.assertEqual(cov.canonical_metadata("c7-p1-run-rGenewiz_1"), ("c7_p1", "Genewiz"))
        with self.assertRaises(AssertionError):
            cov.canonical_metadata("c1-p1-r9")

    def test_synonymous_feature_invariants(self):
        seq1 = "AAA" * 99
        seq2 = "AAG" * 99
        a = prod.simple_features(seq1, "IDT")
        b = prod.simple_features(seq2, "IDT")
        self.assertEqual(a["aa__K"], 1.0)
        self.assertEqual(b["aa__K"], 1.0)
        self.assertEqual(a["codon__AAA"], 1.0)
        self.assertEqual(b["codon__AAG"], 1.0)
        self.assertNotEqual(a["gc3"], b["gc3"])
        self.assertEqual(sum(v for k, v in a.items() if k.startswith("aa__")), 1.0)

    def test_fold_group_isolation(self):
        groups = np.repeat(np.arange(20), 5)
        folds, loads = cov.make_cluster_folds(groups, 20261129)
        self.assertEqual(len(loads), 5)
        self.assertEqual(sum(loads), 100)
        for fold in range(5):
            self.assertTrue(set(groups[folds != fold]).isdisjoint(set(groups[folds == fold])))

    def test_backbones_and_finite_predictions(self):
        rng = np.random.default_rng(7)
        train = pd.DataFrame({"x": rng.normal(size=50), "target": rng.normal(size=50)})
        test = pd.DataFrame({"x": rng.normal(size=9), "target": rng.normal(size=9)})
        for model in ["ridge", "histgb"]:
            prediction = prod.fit_predict(model, ["x"], train, test, 11)
            self.assertEqual(prediction.shape, (9,))
            self.assertTrue(np.isfinite(prediction).all())

    def test_swap_arms(self):
        simple = np.array([1.0, 2.0, 3.0])
        structure = np.array([4.0, 5.0, 6.0])
        a, b = prod.swap_arms(simple, structure, np.array([True, False, True]))
        np.testing.assert_array_equal(a, [4.0, 2.0, 6.0])
        np.testing.assert_array_equal(b, [1.0, 5.0, 3.0])

    def test_measurement_join_deduplicates_geo_rows(self):
        mapping = {f"g{i}": f"o{i}" for i in range(9)}
        outcome = pd.DataFrame([{"Protein_id": "c1_p1", "Group": "IDT", **{f"o{i}": float(i + 1) for i in range(9)}}])
        geo = pd.DataFrame([
            {"Name": "c1-p1-run-rIDT_1", **{f"g{i}": float(i + 1) for i in range(9)}},
            {"Name": "c1-p1-run-rIDT_1", **{f"g{i}": float(i + 1) for i in range(9)}},
        ])
        mapped, diagnostics = prod.assign_outcome_names(outcome, geo, mapping)
        self.assertEqual(mapped["Name"].tolist(), ["c1-p1-run-rIDT_1"])
        self.assertEqual(diagnostics["n_geo_source_rows"], 2)
        self.assertEqual(diagnostics["n_geo_redundant_rows_not_used"], 1)
        self.assertEqual(diagnostics["max_abs_timepoint_difference"], 0.0)

    def test_measurement_join_rejects_ambiguous_names(self):
        mapping = {f"g{i}": f"o{i}" for i in range(9)}
        outcome = pd.DataFrame([{"Protein_id": "c1_p1", "Group": "IDT", **{f"o{i}": float(i + 1) for i in range(9)}}])
        geo = pd.DataFrame([
            {"Name": "c1-p1-run-rIDT_1", **{f"g{i}": float(i + 1) for i in range(9)}},
            {"Name": "c1-p1-run-rIDT_2", **{f"g{i}": float(i + 1) for i in range(9)}},
        ])
        with self.assertRaises(RuntimeError):
            prod.assign_outcome_names(outcome, geo, mapping)

    def test_first_order_estimator_diagnostics(self):
        times = np.array([2.0, 5.0, 8.0])
        # Multi-row deterministic exponential family supplies a nontrivial target correlation.
        rows, targets = [], []
        for rate in [0.1, 0.2, 0.3, 0.4]:
            rows.append(np.exp(-rate * np.repeat(times, 3)))
            targets.append(-rate)
        mapped = pd.DataFrame(np.array(rows), columns=[f"g{i}" for i in range(9)])
        mapped["Decay_rate"] = targets
        protocol = {"outcome_access": {"geo_to_outcome_timepoint_map": {f"g{i}": f"g{i}" for i in range(9)}, "decay_recompute_diagnostic": {"time_hpi": [2, 5, 8], "candidate_estimators": ["all_nine_points_ln", "all_nine_points_log2", "timepoint_mean_abundance_ln", "timepoint_mean_abundance_log2", "timepoint_mean_log_abundance_ln", "timepoint_mean_log_abundance_log2"], "minimum_absolute_pearson_with_published_decay": 0.95}}}
        diagnostics = prod.first_order_diagnostics(mapped, protocol)
        self.assertGreaterEqual(diagnostics["best_absolute_pearson"], 0.999999)
        self.assertTrue(diagnostics["published_target_unchanged"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
