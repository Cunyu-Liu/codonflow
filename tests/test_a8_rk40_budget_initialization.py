#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import a8_rk40_budget_initialization as rk40
from codonflow.eval.anytime import FrozenReference


class RK40BudgetInitializationTests(unittest.TestCase):
    def setUp(self):
        self.frozen = FrozenReference.from_dict({"reference": [0.0, 0.0], "scale": [1.0, 2.0]})

    def test_best_single_metrics(self):
        points = [
            {"budget": 1, "sequence": "AAA", "objectives": [1.0, 2.0]},
            {"budget": 2, "sequence": "AAT", "objectives": [2.0, 2.0]},
        ]
        result = rk40.best_single_metrics(points, self.frozen, [1.0, 1.0])
        self.assertEqual(result["best_normalized_weighted_utility"], 3.0)
        self.assertEqual(result["best_normalized_weighted_utility_budget"], 2)
        self.assertEqual(result["best_single_point_normalized_hv"], 2.0)
        self.assertEqual(result["best_single_point_normalized_hv_budget"], 2)

    def test_additional_bad_points_cannot_reduce_best(self):
        points = [{"budget": 1, "sequence": "AAA", "objectives": [1.0, 2.0]}]
        before = rk40.best_single_metrics(points, self.frozen, [1.0, 1.0])
        points.append({"budget": 2, "sequence": "AAT", "objectives": [-10.0, -10.0]})
        after = rk40.best_single_metrics(points, self.frozen, [1.0, 1.0])
        self.assertEqual(before["best_normalized_weighted_utility"], after["best_normalized_weighted_utility"])
        self.assertEqual(before["best_single_point_normalized_hv"], after["best_single_point_normalized_hv"])

    def test_random_initialization_exactly_reuses_rk39(self):
        source = "ATGGCTGCTTAA"
        first = rk40.initial_for_arm("raw_random_b101", source, 7, [])
        second = rk40.rk39.protein_only_initial(source, 7)
        self.assertEqual(first, second)
        self.assertTrue(first.endswith("TAA"))

    def test_external_initialization_is_frozen_first_point(self):
        points = [{"sequence": "ATGGCTGCTTAA"}, {"sequence": "ATGGCCGCCTAA"}]
        for arm in ("raw_external_b11", "calibrated_external_b11"):
            self.assertEqual(rk40.initial_for_arm(arm, "ATGGCCGCCTAA", 0, points), points[0]["sequence"])

    def test_protocol_counts_and_boundaries(self):
        protocol = json.loads((ROOT / "configs/a8_rk40_budget_initialization_protocol_v1.json").read_text())
        self.assertEqual(len(protocol["new_arms"]), 5)
        self.assertEqual(protocol["expected_new_run_count"], 18 * 3 * 5)
        self.assertEqual(protocol["expected_new_unique_scorer_calls"], 18 * 3 * (101 + 11 + 101 + 11 + 11))
        self.assertEqual(protocol["execution"]["smoke_expected_new_unique_scorer_calls"], 235)
        self.assertFalse(protocol["external_sota_authorized"])
        self.assertFalse(protocol["functional_untouched_used"])

    def test_decision_labels_are_fixed(self):
        self.assertEqual(rk40.decision_label(True, True), "NORMALIZATION_AND_SHORT_BUDGET_BOTH_CONTRIBUTE")
        self.assertEqual(rk40.decision_label(True, False), "SEARCH_SCALE_MISMATCH_SUPPORTED_AT_SHORT_BUDGET")
        self.assertEqual(rk40.decision_label(False, True), "SHORT_BUDGET_LIMIT_SUPPORTED_WITHIN_RAW_SEARCH")
        self.assertEqual(rk40.decision_label(False, False), "NO_RESCUE_FROM_NORMALIZATION_OR_RAW_BUDGET")


if __name__ == "__main__":
    unittest.main()
