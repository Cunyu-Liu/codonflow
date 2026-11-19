#!/usr/bin/env python3
import importlib.util
import math
import unittest
from pathlib import Path

import numpy as np

MODULE_PATH = Path(__file__).resolve().parents[1] / "a8_rk03_mage_development_nested_cv.py"
SPEC = importlib.util.spec_from_file_location("mage_dev_v2", MODULE_PATH)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def synthetic_records(n=40):
    records = []
    for i in range(n):
        wt = ["CTT", "GCT", "TTT", "GGT"][i % 4]
        mutant = ["TTA", "GCC", "TTC", "GGC"][i % 4]
        position = 10 + i % 10
        r = {
            "construct_id": f"C{i:03d}",
            "split": "train" if i % 3 else "dev",
            "position": str(position),
            "wt_codon": wt,
            "mutant_codon": mutant,
            "amino_acid": "L",
            "position_scaled": position / 71.0,
            "wt_gc_fraction": m.gc(wt),
            "mutant_gc_fraction": m.gc(mutant),
            "delta_gc_fraction": m.gc(mutant) - m.gc(wt),
            "wt_gc3": float(wt[2] in "GC"),
            "mutant_gc3": float(mutant[2] in "GC"),
            "nt_changes": float(m.nt_changes(wt, mutant)),
            "is_transition": 0.0,
            "mfe_ddG_43nt_sliding": -10.0 - i % 7,
            "delta_mfe_vs_wt": (i % 5) * 0.2,
            "abs_delta_mfe_vs_wt": (i % 5) * 0.2,
            "mfe_x_position_scaled": (-10.0 - i % 7) * position / 71.0,
            "RCS": (i % 9) * 0.1,
            "delta_rcs_vs_wt": (i % 4) * 0.05,
            "abs_delta_rcs_vs_wt": (i % 4) * 0.05,
            "rcs_x_position_scaled": (i % 9) * 0.1 * position / 71.0,
        }
        r["expression_value"] = 0.9 + 0.01 * (i % 9) + 0.001 * i
        records.append(r)
    return records


class MAGEDevelopmentV2Tests(unittest.TestCase):
    def test_numeric_feature_definitions(self):
        self.assertEqual(m.numeric_for("intrinsic"), m.INTRINSIC_NUM)
        self.assertEqual(m.numeric_for("local_mfe"), m.INTRINSIC_NUM + m.MFE_NUM)
        self.assertEqual(m.numeric_for("full_mechanism"), m.INTRINSIC_NUM + m.MFE_NUM + m.RCS_NUM)
        with self.assertRaises(KeyError):
            m.numeric_for("unknown")

    def test_fold_assignment_is_deterministic_and_balanced(self):
        ids = [f"C{i}" for i in range(131)]
        a = m.assign_folds(ids, 5, "40261119")
        b = m.assign_folds(list(reversed(ids)), 5, "40261119")
        self.assertEqual(a, b)
        self.assertEqual(sorted(np.bincount(list(a.values())).tolist()), [26, 26, 26, 26, 27])
        self.assertEqual(set(a), set(ids))

    def test_fold_assignment_rejects_duplicates(self):
        with self.assertRaises(ValueError):
            m.assign_folds(["A", "A", "B"], 2, "x")

    def test_test_record_cannot_reach_feature_matrix(self):
        records = synthetic_records(8)
        records[0]["split"] = "test"
        with self.assertRaisesRegex(AssertionError, "Frozen test"):
            m.xy(records, "intrinsic")

    def test_metrics_hand_example(self):
        y = np.array([1.0, 2.0, 3.0])
        pred = np.array([1.0, 2.0, 4.0])
        result = m.metrics(y, pred)
        self.assertAlmostEqual(result["rmse"], math.sqrt(1.0 / 3.0))
        self.assertAlmostEqual(result["mae"], 1.0 / 3.0)
        self.assertAlmostEqual(result["spearman"], 1.0)

    def test_effect_direction(self):
        y = np.array([1.0, 2.0, 3.0])
        candidate = np.array([1.0, 2.0, 3.0])
        reference = np.array([3.0, 2.0, 1.0])
        result = m.effect(y, candidate, reference)
        self.assertAlmostEqual(result["delta_spearman"], 2.0)
        self.assertLess(result["delta_rmse"], 0)

    def test_holm_known_values(self):
        adjusted = m.holm([0.01, 0.04, 0.03])
        self.assertEqual(adjusted, [0.03, 0.06, 0.06])

    def test_nested_cv_complete_and_disjoint(self):
        records = synthetic_records(40)
        result = m.nested_cv(records, "full_mechanism", [0.1, 1.0], "synthetic", 5, 4)
        self.assertEqual(set(result["predictions"]), {r["construct_id"] for r in records})
        self.assertEqual(len(result["selections"]), 5)
        self.assertTrue(all(len(s["inner_alpha_grid"]) == 2 for s in result["selections"]))
        for fold in range(5):
            held_out = {c for c, f in result["outer_folds"].items() if f == fold}
            self.assertTrue(held_out)
            self.assertTrue(held_out.issubset(result["predictions"]))

    def test_nested_cv_is_deterministic(self):
        records = synthetic_records(40)
        a = m.nested_cv(records, "intrinsic", [0.1, 1.0], "synthetic", 5, 4)
        b = m.nested_cv(records, "intrinsic", [0.1, 1.0], "synthetic", 5, 4)
        self.assertEqual(a["outer_folds"], b["outer_folds"])
        self.assertEqual(a["predictions"], b["predictions"])
        self.assertEqual(a["selections"], b["selections"])

    def test_paired_analysis_contract(self):
        records = synthetic_records(20)
        y = np.array([r["expression_value"] for r in records])
        candidate = y + np.linspace(-0.001, 0.001, len(y))
        reference = np.roll(y, 1)
        result = m.paired_analysis(y, candidate, reference, 11, 12, 100)
        self.assertEqual(result["bootstrap_replicates"], 100)
        self.assertEqual(result["permutation_replicates"], 100)
        self.assertEqual(len(result["delta_spearman_ci95"]), 2)
        self.assertEqual(len(result["delta_rmse_ci95"]), 2)
        self.assertGreaterEqual(result["permutation_p_spearman"], 1 / 101)
        self.assertLessEqual(result["permutation_p_rmse"], 1.0)

    def test_all_feature_sets_fit_synthetic(self):
        records = synthetic_records(30)
        for name in m.BASE:
            pred = m.fit_ridge(records[:24], records[24:], name, 1.0)
            self.assertEqual(pred.shape, (6,))
            self.assertTrue(np.isfinite(pred).all())

    def test_no_test_prediction_schema(self):
        source = MODULE_PATH.read_text()
        self.assertIn('"test_predictions_generated": False', source)
        self.assertIn('"test_metrics_generated": False', source)
        self.assertIn('if split not in {"train", "dev"}:', source)
        self.assertIn("continue", source.split('if split not in {"train", "dev"}:')[1][:80])


if __name__ == "__main__":
    unittest.main(verbosity=2)
