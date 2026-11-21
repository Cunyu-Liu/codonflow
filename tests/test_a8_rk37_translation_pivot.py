import importlib.util
from pathlib import Path
import unittest

import numpy as np


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "a8_rk37_run_translation_pivot.py"
SPEC = importlib.util.spec_from_file_location("rk37_production_under_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RK37ContractTests(unittest.TestCase):
    def test_codon_mapping_and_position_dimension(self):
        self.assertEqual(len(MODULE.CODON_TO_INDEX), 64)
        self.assertEqual(MODULE.CODON_TO_INDEX["AAA"], 0)
        self.assertEqual(MODULE.CODON_TO_INDEX["TTT"], 21)
        self.assertEqual(MODULE.CODON_TO_INDEX["GGG"], 63)
        x = MODULE.feature_matrix(["ATG", "GCC", "TTT"], "position")
        self.assertEqual(x.shape, (3, 86))
        self.assertEqual(x.nnz, 11)

    def test_local_boundaries_and_offsets(self):
        x = MODULE.feature_matrix(["ATG", "GCC"], "local").toarray()
        self.assertEqual(x.shape, (2, 477))
        for row in range(2):
            for offset_index, offset in enumerate(MODULE.OFFSETS):
                source = row + offset
                valid = 0 <= source < 2
                self.assertEqual(x[row, 448 + offset_index], float(valid))
                block = x[row, offset_index * 64:(offset_index + 1) * 64]
                self.assertEqual(int(block.sum()), int(valid))
        self.assertEqual(x[0, 3 * 64 + MODULE.CODON_TO_INDEX["ATG"]], 1)
        self.assertEqual(x[0, 4 * 64 + MODULE.CODON_TO_INDEX["GCC"]], 1)
        self.assertEqual(x[1, 2 * 64 + MODULE.CODON_TO_INDEX["ATG"]], 1)
        self.assertEqual(x[1, 3 * 64 + MODULE.CODON_TO_INDEX["GCC"]], 1)

    def test_centering_uses_each_transcript_only(self):
        labels = {
            "record_ids": np.asarray(["a", "b"]),
            "offsets": np.asarray([0, 2, 5]),
            "positions": np.asarray([0, 1, 0, 1, 2]),
            "target": np.asarray([1, 3, 2, 4, 9], dtype=np.float32),
        }
        centered = MODULE.center_labels(labels)
        np.testing.assert_allclose(centered["target"], [-1, 1, -3, -1, 4])
        self.assertAlmostEqual(float(centered["target"][:2].mean()), 0)
        self.assertAlmostEqual(float(centered["target"][2:].mean()), 0)

    def test_anchor_is_target_label_free_and_correlation_invariant(self):
        labels = {
            "record_ids": np.asarray(["a", "b"]),
            "offsets": np.asarray([0, 3, 6]),
            "positions": np.asarray([0, 1, 2] * 2),
            "target": np.asarray([100, 200, 300, -5, 0, 5], dtype=np.float32),
        }
        prediction = np.asarray([1, 2, 4, 2, 4, 8], dtype=float)
        anchored = MODULE.anchor_prediction(labels, prediction, 7.5)
        np.testing.assert_allclose(anchored[:3].mean(), 7.5)
        np.testing.assert_allclose(anchored[3:].mean(), 7.5)
        for start, end in ((0, 3), (3, 6)):
            before = np.corrcoef(prediction[start:end], labels["target"][start:end])[0, 1]
            after = np.corrcoef(anchored[start:end], labels["target"][start:end])[0, 1]
            self.assertAlmostEqual(before, after)

    def test_split_reproduces_rk05_contract(self):
        ids = [f"g{index:03d}" for index in range(1179)]
        train, valid, split_seed = MODULE.split_source(ids, 1234)
        self.assertEqual(len(train), 1062)
        self.assertEqual(len(valid), 117)
        self.assertFalse(set(train) & set(valid))
        self.assertIsInstance(split_seed, int)
        train2, valid2, split_seed2 = MODULE.split_source(ids, 1234)
        self.assertEqual((train, valid, split_seed), (train2, valid2, split_seed2))

    def test_alpha_selection_never_uses_target(self):
        candidates = [
            {"alpha": 0.1, "validation_raw": {"transcript_balanced_mse": 3.0}, "validation_anchored": {"transcript_balanced_mse": 2.5}},
            {"alpha": 1.0, "validation_raw": {"transcript_balanced_mse": 2.0}, "validation_anchored": {"transcript_balanced_mse": 2.0}},
            {"alpha": 10.0, "validation_raw": {"transcript_balanced_mse": 1.0}, "validation_anchored": {"transcript_balanced_mse": 4.0}},
        ]
        self.assertEqual(MODULE.select_candidate(candidates, "raw")["alpha"], 10.0)
        self.assertEqual(MODULE.select_candidate(candidates, "anchored")["alpha"], 1.0)

    def test_holm_and_positive_effect_gate(self):
        endpoints = [
            {"name": "a", "effect": 1.0, "ci95_low": 0.2, "sign_flip_pvalue": 0.01},
            {"name": "b", "effect": 2.0, "ci95_low": 0.1, "sign_flip_pvalue": 0.04},
        ]
        adjusted = MODULE.apply_holm(endpoints)
        self.assertAlmostEqual(adjusted[0]["holm_pvalue"], 0.02)
        self.assertAlmostEqual(adjusted[1]["holm_pvalue"], 0.04)
        self.assertTrue(MODULE.endpoint_pass(adjusted[0]))
        self.assertTrue(MODULE.endpoint_pass(adjusted[1]))

    def test_holm_orders_adjusted_values_back_to_input(self):
        endpoints = [
            {"name": "a", "effect": 1, "ci95_low": 0.1, "sign_flip_pvalue": 0.04},
            {"name": "b", "effect": 1, "ci95_low": 0.1, "sign_flip_pvalue": 0.01},
        ]
        adjusted = MODULE.apply_holm(endpoints)
        self.assertAlmostEqual(adjusted[0]["holm_pvalue"], 0.04)
        self.assertAlmostEqual(adjusted[1]["holm_pvalue"], 0.02)

    def test_pair_exclusion_is_finite_and_paired(self):
        labels = {
            "record_ids": np.asarray(["a", "b", "c"]),
            "offsets": np.asarray([0, 2, 4, 6]),
            "positions": np.asarray([0, 1] * 3),
            "target": np.asarray([1, 2, 1, 2, 1, 2], dtype=np.float32),
        }
        candidate = np.asarray([1, 2, 1, 1, 1, 1], dtype=float)
        baseline = np.asarray([2, 1, 1, 2, 1, 2], dtype=float)
        candidate_per = MODULE.per_transcript(labels, candidate)
        baseline_per = MODULE.per_transcript(labels, baseline)
        effect, count = MODULE.paired_effect(candidate_per, baseline_per, "pearson", False)
        self.assertEqual(count, 1)
        self.assertEqual(len(effect), 1)
        self.assertTrue(np.isfinite(effect[0]))

    def test_incomplete_fit_accounting_fails_closed(self):
        with self.assertRaises(ValueError):
            MODULE.assert_fit_accounting(47, 48)

    def test_sensitivity_gate_requires_all_positive(self):
        self.assertTrue(MODULE.sensitivity_pass([0.1, 0.2], [0.3, 0.4]))
        self.assertFalse(MODULE.sensitivity_pass([0.1, -0.2], [0.3, 0.4]))


if __name__ == "__main__":
    unittest.main()
