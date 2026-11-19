#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import types
import unittest

import numpy as np

MODULE_PATH = Path(__file__).resolve().parents[1] / "a8_rk05_ribomimo_study_ood.py"
SPEC = importlib.util.spec_from_file_location("ribomimo_study_ood", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class StudyOODUnitTests(unittest.TestCase):
    def test_source_split_is_deterministic_and_90_10(self):
        ids = [f"Gene|{index:04d}" for index in range(1179)]
        train1, valid1, split_seed1 = MODULE.source_train_valid(ids, 1234)
        train2, valid2, split_seed2 = MODULE.source_train_valid(list(reversed(ids)), 1234)
        self.assertEqual((len(train1), len(valid1)), (1062, 117))
        self.assertEqual(split_seed1, split_seed2)
        self.assertEqual(train1, train2)
        self.assertEqual(valid1, valid2)
        self.assertFalse(set(train1) & set(valid1))
        self.assertEqual(set(train1 + valid1), set(ids))

    def test_official_mask(self):
        density = np.ones(16)
        density[5] = 0
        density[7] = 0
        target, positions = MODULE.official_masked_values(density)
        np.testing.assert_array_equal(positions, np.array([6, 8, 9, 10, 11], dtype=np.int32))
        np.testing.assert_array_equal(target, np.ones(5, dtype=np.float32))

    def test_position_features(self):
        onehot = np.eye(64)[:12]
        features = MODULE.position_features(onehot)
        self.assertEqual(features.shape, (12, 86))
        np.testing.assert_array_equal(features[:, :64], onehot)
        self.assertEqual(int(features[0, 64:84].sum()), 1)
        self.assertAlmostEqual(features[3, 85], math.log(12) / 7.0)
        self.assertAlmostEqual(features[-1, 84], 1.0)
        self.assertEqual(int(np.argmax(features[0, 64:84])), 0)
        self.assertEqual(int(np.argmax(features[-1, 64:84])), 19)

    def test_regression_metrics_transcript_balancing(self):
        record_ids = np.array(["a", "b"])
        offsets = np.array([0, 2, 5])
        target = np.array([0, 2, 1, 2, 3], dtype=np.float32)
        prediction = np.array([0, 1, 1, 2, 4], dtype=np.float64)
        metrics = MODULE.regression_metrics(record_ids, offsets, target, prediction)
        self.assertAlmostEqual(metrics["transcript_balanced_mse"], (0.5 + 1 / 3) / 2)
        self.assertEqual(metrics["n_transcripts"], 2)
        self.assertEqual(metrics["n_masked_positions"], 5)
        self.assertIsNotNone(metrics["mean_transcript_pearson"])

    def test_constant_prediction_has_no_transcript_pearson(self):
        metrics = MODULE.regression_metrics(np.array(["a"]), np.array([0, 3]), np.array([1, 2, 3]), np.array([2, 2, 2]))
        self.assertIsNone(metrics["mean_transcript_pearson"])
        self.assertIsNone(metrics["global_pearson"])
        self.assertEqual(metrics["n_transcripts_with_pearson"], 0)

    def test_paired_inference_zero_differences(self):
        rows = [{"model_mse": 1.0, "ridge_mse": 1.0, "model_pearson": 0.2, "ridge_pearson": 0.2} for _ in range(8)]
        result = MODULE.paired_inference(rows, 10, 20, 100)
        for endpoint in result:
            self.assertEqual(endpoint["point_delta_ribomimo_minus_ridge"], 0)
            self.assertEqual(endpoint["ci95_low"], 0)
            self.assertEqual(endpoint["ci95_high"], 0)
            self.assertEqual(endpoint["sign_flip_pvalue"], 1)
            self.assertEqual(endpoint["holm_pvalue"], 1)

    def test_paired_inference_reproducible(self):
        rng = np.random.default_rng(42)
        rows = []
        for _ in range(40):
            m, r = rng.normal(size=2)
            rows.append({"model_mse": float(m), "ridge_mse": float(r), "model_pearson": float(m / 2), "ridge_pearson": float(r / 3)})
        first = MODULE.paired_inference(rows, 123, 456, 200)
        second = MODULE.paired_inference(rows, 123, 456, 200)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        self.assertTrue(all(0 <= item["holm_pvalue"] <= 1 for item in first))

    def test_ridge_uses_source_train_and_validation_only(self):
        data = types.SimpleNamespace(dict_seq_codon={}, dict_density={}, dict_seq={})
        for index in range(12):
            record_id = f"G{index}"
            onehot = np.eye(64)[(np.arange(16) + index) % 64]
            data.dict_seq_codon[record_id] = onehot
            data.dict_density[record_id] = np.linspace(0.5, 2.0, 16) * (1 + index / 100)
            data.dict_seq[record_id] = "ATG" * 16
        result = MODULE.fit_ridge_on_source(data, [f"G{i}" for i in range(8)], [f"G{i}" for i in range(8, 12)], [0.1, 1.0])
        self.assertIn(result["selected_alpha"], [0.1, 1.0])
        self.assertEqual(result["validation_labels"]["target"].shape, result["validation_prediction"].shape)
        self.assertEqual(len(result["selection"]), 2)
        self.assertGreater(result["train_masked_positions"], 0)

    def test_combined_matrix_roundtrip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = {}
            for study, count in (("Mohammad16", 2), ("Subtelny14", 1)):
                path = root / f"{study}.txt"
                rows = []
                for index in range(count):
                    rows.extend([f">raw{index} extra", "ATG GCT TAA", "1 2 3"])
                path.write_text("\n".join(rows) + "\n")
                paths[study] = path
            protocol = {
                "studies": {
                    "source": "Mohammad16", "target": "Subtelny14",
                    "source_matrix": {"path": str(paths["Mohammad16"]), "sha256": MODULE.sha256(paths["Mohammad16"]), "raw_records": 2},
                    "target_matrix": {"path": str(paths["Subtelny14"]), "sha256": MODULE.sha256(paths["Subtelny14"]), "raw_records": 1},
                }
            }
            destination = root / "combined.txt"
            result = MODULE.build_combined_matrix(protocol, destination)
            self.assertEqual(result["records"], {"Mohammad16": 2, "Subtelny14": 1})
            lines = destination.read_text().splitlines()
            self.assertEqual(lines[0], ">Mohammad16|raw0")
            self.assertEqual(lines[6], ">Subtelny14|raw0")
            self.assertEqual(result["sha256"], hashlib.sha256(destination.read_bytes()).hexdigest())

    def test_training_block_has_no_target_evaluation(self):
        source = MODULE_PATH.read_text()
        function = source.split("def execute_seed", 1)[1].split("def main", 1)[0]
        before_target = function.split("target_start =", 1)[0]
        self.assertNotIn('evaluate("Test")', before_target)
        self.assertNotIn("index_test", before_target)
        self.assertIn('runner.evaluate("Valid")', before_target)


if __name__ == "__main__":
    unittest.main(verbosity=2)
