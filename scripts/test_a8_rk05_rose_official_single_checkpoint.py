#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

SCRIPT = Path(__file__).with_name("a8_rk05_rose_official_single_checkpoint.py")
SPEC = importlib.util.spec_from_file_location("rose_driver", SCRIPT)
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)
ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "audits/20261118/RK05/rose_official_single_checkpoint_protocol_v1.json"
PRODUCTION = ROOT / "audits/20261118/RK05/rose_official_single_checkpoint_v1.json"


class RoseOfficialDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        cls.production = json.loads(PRODUCTION.read_text(encoding="utf-8"))

    def test_01_codon_channel_order(self):
        sequence = ("AAA" + "TTT" + "GGG") + "AAA" * 58
        encoded = DRIVER.encode_sequences(np.array([sequence]))
        self.assertEqual(encoded.shape, (1, 64, 1, 61))
        self.assertEqual(encoded[0, 0, 0, 0], 1.0)
        self.assertEqual(encoded[0, 21, 0, 1], 1.0)
        self.assertEqual(encoded[0, 63, 0, 2], 1.0)
        self.assertEqual(np.count_nonzero(encoded), 61)

    def test_02_all_aaa(self):
        encoded = DRIVER.encode_sequences(np.array(["AAA" * 61]))
        self.assertTrue(np.all(encoded[0, 0, 0, :] == 1.0))
        self.assertEqual(np.count_nonzero(encoded), 61)

    def test_03_rejects_wrong_length(self):
        with self.assertRaisesRegex(ValueError, "183"):
            DRIVER.encode_sequences(np.array(["AAA"]))

    def test_04_rejects_unknown_codon(self):
        with self.assertRaisesRegex(ValueError, "Unknown codons"):
            DRIVER.encode_sequences(np.array(["NNN" + "AAA" * 60]))

    def test_05_official_probability_expression(self):
        probabilities = DRIVER.official_probabilities(np.array([[0, 0], [0, 1]], dtype=np.float32))
        np.testing.assert_allclose(probabilities, [0.5, 1.0 / (1.0 + np.exp(-1.0))], rtol=1e-7)

    def test_06_perfect_classification_metrics(self):
        labels = np.array([0, 0, 1, 1])
        probabilities = np.array([0.1, 0.2, 0.8, 0.9])
        metrics = DRIVER.classification_metrics(labels, probabilities)
        self.assertEqual(metrics["roc_auc"], 1.0)
        self.assertEqual(metrics["average_precision"], 1.0)
        self.assertEqual(metrics["accuracy_at_0.5"], 1.0)

    def test_07_constant_baseline(self):
        labels = np.array([0, 0, 1, 1])
        metrics = DRIVER.classification_metrics(labels, np.full(4, 0.5))
        self.assertEqual(metrics["constant_prevalence_baseline"]["roc_auc"], 0.5)
        self.assertAlmostEqual(metrics["constant_prevalence_baseline"]["log_loss"], np.log(2.0))

    def test_08_network_adaptation_is_limited(self):
        template = 'layer {\n  source: "/old/train.txt"\n  batch_size: 10000\n}\nlayer {\n  source: "/old/test.txt"\n}\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "network.prototxt"
            path.write_text(template, encoding="utf-8")
            original, adapted, replacements = DRIVER.adapt_network(path, "/new/test.txt", 10000, 1902)
        self.assertEqual(original, template)
        self.assertEqual(replacements, 2)
        self.assertEqual(adapted.count('source: "/new/test.txt"'), 2)
        self.assertIn("batch_size: 1902", adapted)
        self.assertNotIn("batch_size: 10000", adapted)

    def test_09_protocol_is_single_checkpoint_not_ensemble(self):
        self.assertFalse(self.protocol["training"])
        self.assertFalse(self.protocol["ensemble"])
        self.assertEqual(self.protocol["checkpoint_count_per_study"], 1)
        self.assertEqual(self.protocol["forward_passes_per_study"], 1)

    def test_10_protocol_covers_complete_released_arrays(self):
        self.assertEqual(self.protocol["studies"]["Pop14"]["expected_records"], 1902)
        self.assertEqual(self.protocol["studies"]["Battle15"]["expected_records"], 9980)
        self.assertEqual(sum(s["expected_records"] for s in self.protocol["studies"].values()), 11882)

    def test_11_production_used_full_arrays_and_expected_parameters(self):
        self.assertEqual(self.production["studies"]["Pop14"]["records"], 1902)
        self.assertEqual(self.production["studies"]["Battle15"]["records"], 9980)
        self.assertEqual(self.production["studies"]["Pop14"]["parameter_count"], 128834)
        self.assertEqual(self.production["studies"]["Battle15"]["parameter_count"], 265858)

    def test_12_scientific_scope_is_not_overclaimed(self):
        scope = self.production["scientific_scope"]
        self.assertTrue(scope["not_continuous_velocity_regression"])
        self.assertTrue(scope["not_training"])
        self.assertTrue(scope["not_64_checkpoint_ensemble"])
        self.assertTrue(scope["not_protein_or_study_or_functional_ood"])
        self.assertTrue(scope["not_matched_cost_or_sota"])
        self.assertEqual(self.production["status"], "PASS_COMPLETE_RELEASED_TEST_SINGLE_CHECKPOINT_INFERENCE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
