#!/usr/bin/env python3
import ast
import math
import unittest
from pathlib import Path

import numpy as np

from scripts import a8_rk04_build_sequence_ood as production
from scripts.a8_rk04_verify_sequence_ood import close_nested


def synthetic_rows():
    rows = []
    for index in range(100):
        split = "train" if index < 80 else ("dev" if index < 90 else "test")
        length = 300 + index
        gc = 0.4 + index / 1000
        row = {
            "source_row": str(index + 1), "construct_id": f"c{index}",
            "split_assignment": split, "operational_protein_cluster": f"cluster{index}",
            "length_nt": length, "gc_fraction": gc,
            "cai": 0.5 + index / 1000, "full_cds_mfe_kcal_mol": -100.0 - index,
            "full_cds_mfe_per_nt": -0.2 - index / 10000,
            "mfe_5prime_48_kcal_mol": -5.0 - index / 100,
            "source_Gave48": -10.0 - index / 10, "source_Gave96": -20.0 - index / 10,
            "source_Gave144": -30.0 - index / 10, "source_Gz48v": -15.0 - index / 10,
        }
        row["log_length_nt"] = math.log(length)
        row["ood_assignment"] = split
        rows.append(row)
    return rows


class SequenceOODTests(unittest.TestCase):
    def test_thresholds_ignore_dev_and_test(self):
        rows = synthetic_rows()
        expected = production.quantile_thresholds(rows, 0.05, 0.95)
        for row in rows:
            if row["split_assignment"] != "train":
                row["length_nt"] = 100000
                row["gc_fraction"] = 0.99
        self.assertEqual(expected, production.quantile_thresholds(rows, 0.05, 0.95))

    def test_threshold_values_match_numpy(self):
        rows = synthetic_rows()
        result = production.quantile_thresholds(rows, 0.05, 0.95)
        values = np.asarray([row["length_nt"] for row in rows[:80]], dtype=float)
        lower, upper = np.quantile(values, [0.05, 0.95])
        self.assertEqual(result["length_nt"]["lower"], float(lower))
        self.assertEqual(result["length_nt"]["upper"], float(upper))
        self.assertEqual(result["length_nt"]["train_rows"], 80)

    def test_any_extreme_member_moves_whole_cluster(self):
        rows = synthetic_rows()[:20]
        for row in rows:
            row["operational_protein_cluster"] = "shared" if row["source_row"] in {"1", "2"} else row["operational_protein_cluster"]
        thresholds = {"length_nt": {"lower": 301.5, "upper": 1000}, "gc_fraction": {"lower": 0.0, "upper": 1.0}}
        result = production.cluster_extremes(rows, thresholds)
        self.assertEqual(result["shared"], ["length_low"])
        self.assertEqual(result["cluster3"], [])

    def test_cluster_can_have_multiple_reasons(self):
        rows = synthetic_rows()[:2]
        for row in rows:
            row["operational_protein_cluster"] = "shared"
        rows[0]["length_nt"] = 1
        rows[1]["length_nt"] = 10000
        rows[0]["gc_fraction"] = 0.01
        rows[1]["gc_fraction"] = 0.99
        thresholds = {"length_nt": {"lower": 100, "upper": 1000}, "gc_fraction": {"lower": 0.1, "upper": 0.9}}
        self.assertEqual(production.cluster_extremes(rows, thresholds)["shared"], ["gc_high", "gc_low", "length_high", "length_low"])

    def test_closed_core_interval(self):
        rows = synthetic_rows()[:2]
        rows[0]["length_nt"] = 100
        rows[1]["length_nt"] = 1000
        rows[0]["gc_fraction"] = 0.1
        rows[1]["gc_fraction"] = 0.9
        thresholds = {"length_nt": {"lower": 100, "upper": 1000}, "gc_fraction": {"lower": 0.1, "upper": 0.9}}
        self.assertEqual(production.cluster_extremes(rows, thresholds)["cluster0"], [])
        self.assertEqual(production.cluster_extremes(rows, thresholds)["cluster1"], [])

    def test_normalization_excludes_nontrain_and_ood(self):
        rows = synthetic_rows()
        rows[0]["ood_assignment"] = "sequence_ood"
        result = production.fit_normalization(rows)
        expected = np.asarray([row["gc_fraction"] for row in rows[1:80]], dtype=float)
        self.assertAlmostEqual(result["gc_fraction"]["mean"], float(expected.mean()))
        self.assertAlmostEqual(result["gc_fraction"]["scale_ddof0"], float(expected.std(ddof=0)))
        self.assertEqual(result["gc_fraction"]["n_observed"], 79)
        self.assertEqual(result["gc_fraction"]["n_missing"], 0)

    def test_missing_values_use_observed_train_mean_and_indicator(self):
        rows = synthetic_rows()
        rows[0]["source_Gave144"] = None
        rows[85]["source_Gave144"] = None
        result = production.fit_normalization(rows)
        expected = np.asarray([row["source_Gave144"] for row in rows[1:80]], dtype=float)
        self.assertEqual(result["source_Gave144"]["n_observed"], 79)
        self.assertEqual(result["source_Gave144"]["n_missing"], 1)
        self.assertAlmostEqual(result["source_Gave144"]["mean"], float(expected.mean()))
        self.assertEqual(result["source_Gave144"]["imputation"], "train_observed_mean")
        self.assertTrue(result["source_Gave144"]["missing_indicator"])

    def test_log_length_normalization(self):
        rows = synthetic_rows()
        result = production.fit_normalization(rows)
        expected = np.asarray([math.log(row["length_nt"]) for row in rows[:80]], dtype=float)
        self.assertAlmostEqual(result["log_length_nt"]["mean"], float(expected.mean()))

    def test_zero_variance_rejected(self):
        rows = synthetic_rows()
        for row in rows:
            row["cai"] = 1.0
        with self.assertRaisesRegex(ValueError, "normalization"):
            production.fit_normalization(rows)

    def test_nonfinite_normalization_rejected(self):
        rows = synthetic_rows()
        rows[3]["cai"] = float("nan")
        with self.assertRaisesRegex(ValueError, "normalization"):
            production.fit_normalization(rows)

    def test_production_source_never_reads_expression_field(self):
        path = Path(production.__file__)
        tree = ast.parse(path.read_text())
        string_constants = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        self.assertNotIn("expression_value", string_constants)
        self.assertNotIn("expression_stdev", string_constants)

    def test_nested_numeric_comparison(self):
        self.assertTrue(close_nested({"x": [1.0]}, {"x": [1.0]}))
        self.assertFalse(close_nested({"x": 1.0}, {"x": 1.1}))
        self.assertTrue(close_nested(1.0, 1.0001, tolerance=0.001))

    def test_protocol_scope_is_not_generator_authorization(self):
        self.assertIn("sequence_ood", production.OOD)
        self.assertEqual(production.UNTOUCHED, "functional_untouched")
        self.assertNotEqual(production.OOD, production.UNTOUCHED)


if __name__ == "__main__":
    unittest.main()
