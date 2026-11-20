#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

import numpy as np

from scripts.a8_rk03_mage_oof_comparator_closure import (
    effect, holm, metrics, outer_train_mean, paired_analysis,
)


class MAGEOOFComparatorClosureTests(unittest.TestCase):
    def test_perfect_prediction_metrics(self):
        y = np.array([1.0, 2.0, 3.0])
        m = metrics(y, y)
        self.assertEqual(m["rmse"], 0.0)
        self.assertEqual(m["mae"], 0.0)
        self.assertEqual(m["spearman"], 1.0)

    def test_constant_prediction_spearman_is_null_not_zero(self):
        m = metrics(np.array([1.0, 2.0, 3.0]), np.ones(3))
        self.assertIsNone(m["spearman"])
        self.assertEqual(m["spearman_null_reason"], "undefined_for_constant_prediction_not_zero")

    def test_outer_train_mean_excludes_each_evaluation_fold(self):
        y = np.arange(10, dtype=float)
        folds = np.arange(10) % 5
        pred = outer_train_mean(y, folds)
        for fold in range(5):
            expected = y[folds != fold].mean()
            np.testing.assert_allclose(pred[folds == fold], expected, rtol=0, atol=0)
        self.assertNotEqual(pred[0], y[0])

    def test_outer_train_mean_rejects_non_five_fold_input(self):
        with self.assertRaises(AssertionError):
            outer_train_mean(np.arange(4, dtype=float), np.array([0, 1, 2, 3]))

    def test_paired_rmse_analysis_is_seed_deterministic(self):
        y = np.array([0.9, 1.0, 1.1, 0.8, 1.2, 0.95])
        candidate = y + np.array([0.01, -0.02, 0.0, 0.03, -0.01, 0.02])
        reference = y + np.array([0.04, 0.01, -0.03, 0.02, 0.05, -0.02])
        a = paired_analysis(y, candidate, reference, ["delta_rmse"], 17, 23, 100)
        b = paired_analysis(y, candidate, reference, ["delta_rmse"], 17, 23, 100)
        self.assertEqual(a, b)
        self.assertEqual(a["bootstrap_replicates"], 100)

    def test_holm_known_values(self):
        adjusted = holm([0.01, 0.04, 0.03])
        np.testing.assert_allclose(adjusted, [0.03, 0.06, 0.06], rtol=0, atol=1e-15)

    def test_effect_direction(self):
        y = np.array([1.0, 2.0, 4.0, 3.0])
        candidate = y.copy()
        reference = y[::-1].copy()
        e = effect(y, candidate, reference, ["delta_spearman", "delta_rmse"])
        self.assertGreater(e["delta_spearman"], 0)
        self.assertLess(e["delta_rmse"], 0)

    def test_fold_varying_mean_spearman_is_descriptive_not_primary(self):
        y = np.arange(10, dtype=float)
        folds = np.arange(10) % 5
        pred = outer_train_mean(y, folds)
        self.assertFalse(np.all(pred == pred[0]))
        self.assertIsNotNone(metrics(y, pred)["spearman"])
        cfg = json.loads(Path("configs/a8_rk03_mage_oof_comparator_closure_protocol_v2.json").read_text())
        self.assertEqual(cfg["outer_training_mean_baseline"]["metrics"], ["delta_rmse"])

    def test_protocol_retains_no_go_and_arm_disclosure(self):
        cfg = json.loads(Path("configs/a8_rk03_mage_oof_comparator_closure_protocol_v2.json").read_text())
        self.assertFalse(cfg["development_data"]["frozen_test_constructs_used"])
        self.assertEqual(cfg["development_data"]["new_model_fits"], 0)
        self.assertIn("not a pure external", cfg["feature_arm_interpretation"]["rcs_only"])
        self.assertIn("No significance", cfg["inference"]["no_gate_rule"])


if __name__ == "__main__":
    unittest.main()
