import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scripts import a8_rk04_sequence_ood_model as production


ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = json.loads((ROOT / "configs" / "a8_rk04_sequence_ood_model_protocol.json").read_text())


def rows():
    return [
        {"cluster_id": "a", "expression": 1.0, "x": 1.0},
        {"cluster_id": "a", "expression": 3.0, "x": 2.0},
        {"cluster_id": "b", "expression": 10.0, "x": None},
    ]


class SequenceOODModelTests(unittest.TestCase):
    def test_cluster_weights_equalize_cluster_total(self):
        weights = production.cluster_weights(rows())
        self.assertAlmostEqual(weights[0] + weights[1], 1.0)
        self.assertAlmostEqual(weights[2], 1.0)

    def test_transform_uses_frozen_mean_and_missing_indicator(self):
        norm = {"x": {"mean": 4.0, "scale_ddof0": 2.0}}
        transform = production.make_transform(["x"], norm, ["x"])
        matrix, names = transform(rows())
        self.assertEqual(names, ["x", "x__missing"])
        np.testing.assert_allclose(matrix[:, 0], [-1.5, -1.0, 0.0])
        np.testing.assert_allclose(matrix[:, 1], [0.0, 0.0, 1.0])

    def test_metric_block_perfect_prediction(self):
        result = production.metric_block(rows(), np.asarray([1.0, 3.0, 10.0]))
        self.assertAlmostEqual(result["row_mse"], 0.0)
        self.assertAlmostEqual(result["row_r2"], 1.0)
        self.assertAlmostEqual(result["row_spearman"], 1.0)
        self.assertAlmostEqual(result["cluster_balanced_mse"], 0.0)

    def test_constant_correlation_is_null_not_nan(self):
        result = production.metric_block(rows(), np.asarray([2.0, 2.0, 2.0]))
        self.assertIsNone(result["row_spearman"])
        self.assertIsNone(result["cluster_mean_spearman"])
        self.assertIsNone(result["within_cluster_centered_spearman"])

    def test_cluster_balanced_mse(self):
        result = production.metric_block(rows(), np.asarray([0.0, 0.0, 0.0]))
        expected = ((1.0 + 9.0) / 2.0 + 100.0) / 2.0
        self.assertAlmostEqual(result["cluster_balanced_mse"], expected)

    def test_within_cluster_centered_spearman(self):
        result = production.metric_block(rows(), np.asarray([0.0, 2.0, 9.0]))
        self.assertAlmostEqual(result["within_cluster_centered_spearman"], 1.0)
        self.assertEqual(result["within_cluster_eligible_clusters"], 1)
        self.assertEqual(result["within_cluster_eligible_rows"], 2)

    def test_bootstrap_is_deterministic(self):
        primary = np.asarray([1.0, 3.0, 10.0])
        reference = np.asarray([2.0, 2.0, 2.0])
        a = production.bootstrap_comparison(rows(), primary, reference, 20, 7, [2.5, 97.5])
        b = production.bootstrap_comparison(rows(), primary, reference, 20, 7, [2.5, 97.5])
        self.assertEqual(a, b)
        self.assertLess(a["statistics"]["cluster_balanced_mse_delta"]["median"], 0.0)

    def test_prediction_gzip_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.csv.gz"
            b = Path(tmp) / "b.csv.gz"
            full_rows = [{**row, "source_row": str(i), "construct_id": f"c{i}", "protein_id": "p", "ood_assignment": "test", "origin_split": "test"} for i, row in enumerate(rows())]
            predictions = {"constant": np.asarray([1.0, 2.0, 3.0])}
            production.write_predictions(a, full_rows, predictions)
            production.write_predictions(b, full_rows, predictions)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            with gzip.open(a, "rt") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 3)

    def test_protocol_selection_and_final_partitions_are_frozen(self):
        self.assertEqual(PROTOCOL["data"]["fit_assignment"], "train")
        self.assertEqual(PROTOCOL["data"]["selection_assignment"], "dev")
        self.assertEqual(PROTOCOL["data"]["final_assignments"], ["test", "sequence_ood"])
        self.assertFalse(PROTOCOL["data"]["untouched_label_access"])

    def test_protocol_scope_does_not_authorize_generator_or_sota(self):
        self.assertFalse(PROTOCOL["scope"]["codonflow_rk_generator_claim"])
        self.assertFalse(PROTOCOL["scope"]["sota_claim"])
        self.assertFalse(PROTOCOL["scope"]["fixed_protein_synonymous_mechanism_claim"])

    def test_histgb_is_fixed_and_deterministic(self):
        self.assertFalse(PROTOCOL["histgb_fixed"]["early_stopping"])
        self.assertEqual(PROTOCOL["histgb_fixed"]["random_state"], 20261119)
        spec = next(f for f in PROTOCOL["families"] if f["family"] == "histgb_all")
        model = production.make_model(spec, spec["candidates"][0], PROTOCOL["histgb_fixed"])
        self.assertFalse(model.early_stopping)
        self.assertEqual(model.random_state, 20261119)

    def test_production_source_does_not_evaluate_untouched(self):
        source = (ROOT / "scripts" / "a8_rk04_sequence_ood_model.py").read_text()
        self.assertIn('if assignment == untouched:\n                untouched_count += 1\n                continue', source)
        self.assertNotIn('by_partition["functional_untouched"]', source)
        self.assertIn('raw["expression_value"]', source)
        self.assertIn('raw["operational_protein_cluster"]', source)
        self.assertNotIn('raw["expression_label"], "feature expression"', source)


if __name__ == "__main__":
    unittest.main()
