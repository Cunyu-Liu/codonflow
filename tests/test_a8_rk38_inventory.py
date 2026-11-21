#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "a8_rk38_inventory_baselines.py"
SPEC = importlib.util.spec_from_file_location("rk38_inventory", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class RK38InventoryTests(unittest.TestCase):
    def test_unique_sequences_preserves_order_and_detects_duplicates(self):
        self.assertEqual(MODULE.unique_sequences(["AAA", "CCC", "AAA"], 2), ["AAA", "CCC"])
        with self.assertRaises(ValueError):
            MODULE.unique_sequences(["AAA", "CCC", "AAA"], 3)

    def test_sequence_set_requires_exact_cardinality_and_values(self):
        points = [{"sequence": "AAA"}, {"sequence": "CCC"}]
        self.assertTrue(MODULE.sequence_set_exact(["CCC", "AAA"], points))
        self.assertFalse(MODULE.sequence_set_exact(["AAA", "AAA"], points))
        self.assertFalse(MODULE.sequence_set_exact(["AAA", "GGG"], points))

    def make_payload(self):
        return {
            "status": "done", "record_id": "r1", "seed": 0, "n_unique": 2,
            "points": [
                {"budget": 1, "sequence": "AAA"},
                {"budget": 2, "sequence": "CCC"},
                {"budget": 3, "sequence": "AAA"},
            ],
            "costs": {"elapsed_s": 1.25, "generator_calls": 4, "forward_calls": 2,
                      "unique_terminal_reward_calls": 3},
            "source_sha256": "source", "code_commit": "commit", "device": "cuda:0",
        }

    def test_dense_row_keeps_real_duplicate_count_without_padding(self):
        row = MODULE.dense_prefix_row(self.make_payload(), Path("raw.json"), "sha", "test", "FULL", "learned", 3)
        self.assertEqual(row["n_attempts_or_points"], 3)
        self.assertEqual(row["n_unique_outputs"], 2)
        self.assertEqual(row["n_duplicate_or_unreturned"], 1)
        self.assertEqual(row["budget_label"], "B3_ordered_unique_scorer_calls")
        self.assertTrue(row["dense_auc_available"])

    def test_dense_row_rejects_noncontiguous_budget(self):
        payload = self.make_payload()
        payload["points"][2]["budget"] = 4
        with self.assertRaises(ValueError):
            MODULE.dense_prefix_row(payload, Path("raw.json"), "sha", "test", "FULL", "learned", 3)

    def test_dense_row_rejects_missing_or_negative_cost(self):
        payload = self.make_payload()
        payload["costs"]["elapsed_s"] = -1
        with self.assertRaises(ValueError):
            MODULE.dense_prefix_row(payload, Path("raw.json"), "sha", "test", "FULL", "learned", 3)

    def test_frozen_protocol_forbids_untouched_and_sota(self):
        protocol_path = Path(__file__).parents[1] / "configs" / "a8_rk38_baseline_untouched_inventory_protocol_v1.json"
        protocol = json.loads(protocol_path.read_text())
        self.assertFalse(protocol["population"]["functional_untouched_used"])
        self.assertFalse(protocol["inputs"]["functional_untouched_metadata_only"]["new_label_or_outcome_read"])
        self.assertFalse(protocol["decision_boundary"]["sota_claim"])
        self.assertFalse(protocol["decision_boundary"]["time_matched_comparison"])
        self.assertEqual(protocol["output"]["expected_detailed_rows"], 846)


if __name__ == "__main__":
    unittest.main()
