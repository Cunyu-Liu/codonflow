import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scripts import a8_rk06_simple_search_dense_unique18 as production


class DenseSearchHelperTests(unittest.TestCase):
    def test_pareto_indices_strict_dominance(self):
        points = np.array([[1.0, 0.0], [0.0, 1.0], [2.0, 2.0], [0.5, 0.5]])
        self.assertEqual(production.pareto_indices(points), [2])

    def test_pareto_ties_are_not_strictly_dominated(self):
        points = np.array([[1.0, 1.0], [1.0, 1.0]])
        self.assertEqual(production.pareto_indices(points), [0, 1])

    def test_budget_summary_uses_real_prefix_and_curve(self):
        points = [
            {"budget": 1, "sequence": "ATGAAATAG", "objectives": [1.0, 0.0]},
            {"budget": 2, "sequence": "ATGAAGTAG", "objectives": [0.0, 1.0]},
        ]
        curve = [{"hv": 1.0}, {"hv": 2.0}]
        row = production.summarize_budget(points, curve, 2)
        self.assertEqual(row["n_scored"], 2)
        self.assertEqual(row["n_pareto_points"], 2)
        self.assertEqual(row["hypervolume_normalized"], 2.0)
        self.assertEqual(row["per_axis_best"], [1.0, 1.0])

    def test_budget_summary_rejects_incomplete_prefix(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            production.summarize_budget([], [], 1)

    def test_ned_is_deterministic(self):
        points = [
            {"budget": index + 1, "sequence": "ATG" + ("AAA" if index % 2 else "AAG") + "TAG", "objectives": [float(index)]}
            for index in range(5)
        ]
        curve = [{"hv": float(index)} for index in range(5)]
        first = production.summarize_budget(points, curve, 5)
        second = production.summarize_budget(points, curve, 5)
        self.assertEqual(first["pairwise_ned"], second["pairwise_ned"])

    def test_holm_adjustment(self):
        adjusted = production.holm_adjust([0.01, 0.02, 0.5])
        np.testing.assert_allclose(adjusted, [0.03, 0.04, 0.5])

    def test_holm_is_capped_and_monotone_in_sorted_p(self):
        adjusted = production.holm_adjust([0.2, 0.01, 0.02])
        self.assertTrue(np.all(adjusted <= 1.0))
        self.assertLessEqual(adjusted[1], adjusted[2])
        self.assertLessEqual(adjusted[2], adjusted[0])

    def test_resume_rejects_wrong_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.json"
            path.write_text(json.dumps({"protocol_sha256": "old"}))
            with self.assertRaisesRegex(ValueError, "protocol_sha256"):
                production.valid_existing(path, "new", "r", "ATGAAATAG", "ATGAAATAG", "uniform", 0, 2, "c", "r")

    def test_resume_rejects_non_dense_budgets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.json"
            source = "ATGAAATAG"
            payload = {
                "protocol_sha256": "p", "record_id": "r", "source_sha256": production.text_sha256(source),
                "initial_sha256": production.text_sha256(source), "method": "uniform", "seed": 0,
                "status": "done", "n_points": 2, "calibration_sha256": "c", "rscu_sha256": "r",
                "points": [{"budget": 1}, {"budget": 2}], "dense": {"auc": None},
            }
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "dense AUC"):
                production.valid_existing(path, "p", "r", source, source, "uniform", 0, 2, "c", "r")


class PairedInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        cls.protocol = json.loads((root / "configs/a8_rk06_simple_search_dense_unique18_protocol_v1.json").read_text())

    def descriptors(self):
        rows = []
        offsets = {"uniform": 0.0, "hill_climbing": 1.0, "mh_annealing": -1.0, "areuredi_style": 0.5}
        for record_index in range(18):
            for seed in [0, 1, 2]:
                for method, offset in offsets.items():
                    rows.append({
                        "record_id": f"r{record_index}", "seed": seed, "method": method,
                        "dense_budget_step_auc_v2": 2.0 + offset,
                        "secondary_budgets": {"500": {"hypervolume_normalized": 3.0 + offset}},
                    })
        return rows

    def test_six_frozen_tests(self):
        result = production.paired_inference(self.descriptors(), self.protocol)
        self.assertEqual(len(result), 6)
        self.assertEqual({row["comparator"] for row in result}, {"uniform"})

    def test_positive_direction_and_gate(self):
        result = production.paired_inference(self.descriptors(), self.protocol)
        hill = [row for row in result if row["method"] == "hill_climbing"]
        self.assertTrue(all(row["effect"] == 1.0 and row["supported_advantage"] for row in hill))

    def test_negative_direction_not_a_win(self):
        result = production.paired_inference(self.descriptors(), self.protocol)
        mh = [row for row in result if row["method"] == "mh_annealing"]
        self.assertTrue(all(row["effect"] == -1.0 and not row["supported_advantage"] for row in mh))

    def test_statistical_unit_is_record_mean_over_seeds(self):
        result = production.paired_inference(self.descriptors(), self.protocol)
        self.assertTrue(all(row["n_records"] == 18 and len(row["per_record_effects"]) == 18 for row in result))


if __name__ == "__main__":
    unittest.main()
