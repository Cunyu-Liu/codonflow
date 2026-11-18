import json
import math
import unittest
from pathlib import Path

import numpy as np

from codonflow.eval.actual_set import summarize_actual_set
from codonflow.eval.anytime import FrozenReference, dense_budget_step_auc_v2


class DenseBudgetStepAucTests(unittest.TestCase):
    def setUp(self):
        self.ref1 = FrozenReference(reference=np.array([0.0]), scale=np.array([1.0]))
        self.ref2 = FrozenReference(reference=np.array([0.0, 0.0]), scale=np.array([1.0, 1.0]))

    def test_hand_calculated_auc_excludes_endpoint_and_origin(self):
        records = [
            {"budget": 3, "objectives": [2.0]},
            {"budget": 1, "objectives": [1.0]},
            {"budget": 2, "objectives": [3.0]},
        ]
        result = dense_budget_step_auc_v2(records, self.ref1, max_budget=3)
        self.assertEqual([row["hv"] for row in result["curve"]], [1.0, 3.0, 3.0])
        self.assertEqual(result["area"], 4.0)  # HV_1 + HV_2; no (0, 0), no trapezoids.
        self.assertEqual(result["auc"], 2.0)
        self.assertEqual(result["endpoint_hv"], 3.0)
        self.assertEqual(result["denominator"], 2)
        self.assertFalse(result["synthetic_origin_added"])

    def test_b500_uses_exactly_499_real_budgets(self):
        records = [{"budget": budget, "objectives": [2.0]} for budget in range(1, 501)]
        result = dense_budget_step_auc_v2(records, self.ref1)
        self.assertEqual(len(result["curve"]), 500)
        self.assertEqual(result["area"], 2.0 * 499)
        self.assertEqual(result["auc"], 2.0)
        self.assertEqual(result["curve"][0]["budget"], 1)
        self.assertEqual(result["curve"][-1]["budget"], 500)
        self.assertFalse(result["curve"][-1]["used_in_auc"])

    def test_shuffled_records_are_invariant(self):
        forward = [{"budget": b, "objectives": [float(b % 4)]} for b in range(1, 6)]
        shuffled = [forward[index] for index in [3, 0, 4, 1, 2]]
        a = dense_budget_step_auc_v2(forward, self.ref1, max_budget=5)
        b = dense_budget_step_auc_v2(shuffled, self.ref1, max_budget=5)
        self.assertEqual(a["curve"], b["curve"])
        self.assertEqual(a["auc"], b["auc"])

    def test_duplicate_budget_is_rejected(self):
        records = [{"budget": 1, "objectives": [1.0]}, {"budget": 1, "objectives": [2.0]}]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            dense_budget_step_auc_v2(records, self.ref1, max_budget=2)

    def test_missing_budget_is_not_zero_filled(self):
        records = [{"budget": 1, "objectives": [1.0]}, {"budget": 3, "objectives": [2.0]}]
        with self.assertRaisesRegex(ValueError, "missing real-scorer budgets"):
            dense_budget_step_auc_v2(records, self.ref1, max_budget=3)

    def test_noninteger_and_zero_budgets_are_rejected(self):
        for bad_budget in [0, 1.5, True, "1"]:
            with self.subTest(bad_budget=bad_budget):
                with self.assertRaises(ValueError):
                    dense_budget_step_auc_v2([{"budget": bad_budget, "objectives": [1.0]}], self.ref1, max_budget=1)

    def test_invalid_max_budget_is_rejected(self):
        for bad_max in [1, 0, 2.5, True]:
            with self.subTest(bad_max=bad_max):
                with self.assertRaises(ValueError):
                    dense_budget_step_auc_v2([], self.ref1, max_budget=bad_max)

    def test_nan_and_wrong_dimension_are_rejected(self):
        with self.assertRaises(ValueError):
            dense_budget_step_auc_v2([
                {"budget": 1, "objectives": [np.nan]},
                {"budget": 2, "objectives": [1.0]},
            ], self.ref1, max_budget=2)
        with self.assertRaisesRegex(ValueError, "dimension"):
            dense_budget_step_auc_v2([
                {"budget": 1, "objectives": [1.0, 2.0]},
                {"budget": 2, "objectives": [1.0, 2.0]},
            ], self.ref1, max_budget=2)

    def test_degenerate_calibration_axis_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "degenerate"):
            FrozenReference.from_calibration([[1.0, 2.0], [3.0, 2.0]])


class ActualSetTests(unittest.TestCase):
    def setUp(self):
        self.ref2 = FrozenReference(reference=np.array([0.0, 0.0]), scale=np.array([1.0, 1.0]))

    def test_actual_set_has_pareto_and_hv_but_null_dense_auc(self):
        result = summarize_actual_set([
            {"output_id": "a", "objectives": [1.0, 0.0]},
            {"output_id": "b", "objectives": [0.0, 1.0]},
            {"output_id": "c", "objectives": [2.0, 2.0]},
        ], self.ref2)
        self.assertEqual(result["evaluation_mode"], "actual_set_only")
        self.assertEqual(result["n_actual_outputs"], 3)
        self.assertEqual(result["n_pareto_points"], 1)
        self.assertEqual(result["pareto"][0]["record_ids"], ["c"])
        self.assertEqual(result["hypervolume_normalized"], 4.0)
        self.assertIsNone(result["dense_budget_step_auc_v2"])
        self.assertIsNone(result["curve"])
        self.assertIsNone(result["area"])

    def test_duplicate_objectives_do_not_create_extra_pareto_points(self):
        result = summarize_actual_set([
            {"output_id": "a", "objectives": [1.0, 1.0]},
            {"output_id": "b", "objectives": [1.0, 1.0]},
        ], self.ref2)
        self.assertEqual(result["n_actual_outputs"], 2)
        self.assertEqual(result["n_unique_objective_vectors"], 1)
        self.assertEqual(result["n_pareto_points"], 1)
        self.assertEqual(result["pareto"][0]["record_ids"], ["a", "b"])
        self.assertEqual(result["hypervolume_normalized"], 1.0)

    def test_actual_set_rejects_empty_and_duplicate_ids(self):
        with self.assertRaises(ValueError):
            summarize_actual_set([], self.ref2)
        with self.assertRaisesRegex(ValueError, "unique"):
            summarize_actual_set([
                {"output_id": "a", "objectives": [1.0, 1.0]},
                {"output_id": "a", "objectives": [2.0, 2.0]},
            ], self.ref2)

    def test_schema_requires_null_dense_auc_and_explicit_costs(self):
        root = Path(__file__).resolve().parents[2]
        schema = json.loads((root / "configs/a8/actual_set_schema.json").read_text())
        self.assertEqual(schema["properties"]["trajectory"]["properties"]["dense_budget_step_auc_v2"]["type"], "null")
        for field in ["cache_before_requests", "unique_scorer_calls", "model_forward_calls", "generation_seconds", "scoring_seconds", "wall_clock_seconds"]:
            self.assertIn(field, schema["properties"]["cost"]["required"])
        self.assertIn("outputs", schema["required"])
        self.assertIn("comparability", schema["required"])


if __name__ == "__main__":
    unittest.main()
