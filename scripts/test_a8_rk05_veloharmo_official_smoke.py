#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.stats import pearsonr

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/home/codonflow-a8-rk-external/VeloHARMO-38b48079856aeb9d33a1b10844d77aa8f6640032")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VeloHarmoSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.production_module = load("veloharmo_production", ROOT / "scripts/a8_rk05_veloharmo_official_smoke.py")
        cls.finalizer = load("veloharmo_finalizer", ROOT / "scripts/a8_rk05_finalize_veloharmo_official_smoke.py")
        cls.production = json.loads((ROOT / "audits/20261118/RK05/veloharmo_official_smoke_v1.json").read_text())
        cls.independent = json.loads((ROOT / "audits/20261118/RK05/veloharmo_independent_verification_v1.json").read_text())

    def legal(self, candidate, native):
        return self.production_module.synonymous_qc(candidate, native)["legal_synonymous_cds"]

    def test_density_formula(self):
        observed = self.production_module.normalized_density([0, 0.5, 1, 2, 3])
        self.assertTrue(np.allclose(observed, [0, 0, 0.5, 1, 1.5]))

    def test_synonymous_and_native_stop_contract(self):
        self.assertTrue(self.legal("ATGAAGTAA", "ATGAAATAA"))
        self.assertTrue(self.legal("ATGAAG", "ATGAAA"))
        self.assertFalse(self.legal("ATGAAG", "ATGAAATAA"))
        self.assertFalse(self.legal("ATGTAA", "ATGAAA"))
        self.assertFalse(self.legal("ATGAAA", "ATGAAATAA"))

    def test_deterministic_short_record_selection(self):
        records = []
        for index, length in enumerate([45, 31, 30, 40, 32, 33, 34, 35, 36]):
            records.append({"name": f"R{index}", "source_index": index,
                            "codons": ["AAA"] * length, "count": [0.0] * (length - 1) + [1.0],
                            "features": ["0"] * length})
        selected = self.production_module.select_bounded_records(records, 7)
        self.assertEqual([x["name"] for x in selected], ["R2", "R1", "R4", "R5", "R6", "R7", "R8"])
        self.assertNotIn("R0", [x["name"] for x in selected])

    def test_exact_seven_item_ga_patch(self):
        source = (SOURCE / "Genetic_algorithm/ga_velocity_pattern.add.time.pearson.ss.py").read_text()
        patched, metadata = self.production_module.build_ga_runtime(
            source, "/tmp/subset.txt", "/tmp/e.pth", "/tmp/y.pth", "/tmp/out.jpg", 8, 2)
        self.assertEqual(len(metadata), 7)
        self.assertIn("POPULATION_SIZE = 8", patched)
        self.assertIn("MAX_GENERATIONS = 2", patched)
        self.assertNotIn("Mimo_data", patched)
        self.assertNotIn("/Your/work/path", patched)
        compile(patched, "bounded_ga.py", "exec")

    def test_official_float32_pearson_aggregation(self):
        x = np.asarray([1, 2, 4, 8], dtype=np.float32)
        y = np.asarray([2, 1, 5, 7], dtype=np.float32)
        score = pearsonr(x, y)[0]
        self.assertEqual(getattr(score, "dtype", None), np.dtype("float32"))
        self.assertEqual(np.mean([score, score]).dtype, np.dtype("float32"))

    def test_scope_gate(self):
        production = {"status": "BOUNDED_OFFICIAL_ALGORITHM_EXECUTION_COMPLETE",
                      "official_ga_unmodified": {"executed_successfully": False},
                      "bounded_ga": {"start_to_best_improved": False}}
        production.update({name: False for name in self.finalizer.FALSE_FIELDS})
        independent = {"status": "PASS", "passed_checks": 17, "check_count": 17,
                       "max_numeric_delta": 0.0, "ga_best_equals_start": True}
        independent.update({name: False for name in self.finalizer.FALSE_FIELDS})
        self.assertEqual(self.finalizer.scope_failures(production, independent), [])
        production["main_baseline_comparison"] = True
        self.assertIn("main_baseline_comparison", self.finalizer.scope_failures(production, independent))

    def test_frozen_reports_reconcile(self):
        self.assertEqual(self.production["status"], "BOUNDED_OFFICIAL_ALGORITHM_EXECUTION_COMPLETE")
        self.assertEqual(self.independent["status"], "PASS")
        self.assertEqual(self.independent["check_count"], 17)
        self.assertEqual(self.independent["passed_checks"], 17)
        self.assertEqual(self.independent["max_numeric_delta"], 0.0)

    def test_dual_devices_and_negative_optimization_retained(self):
        self.assertEqual(self.production["official_velogru_test"]["device"], "cuda:0")
        self.assertEqual(self.production["bounded_ga"]["device"], "cpu")
        self.assertFalse(self.production["bounded_ga"]["start_to_best_improved"])
        self.assertEqual(self.production["bounded_ga"]["best_minus_start"], 0.0)
        self.assertEqual(self.production["bounded_ga"]["start_sequence"],
                         self.production["bounded_ga"]["best_sequence"])

    def test_official_metric_reconciliation(self):
        test = self.production["official_velogru_test"]
        self.assertLessEqual(test["metric_delta"], 1e-7)
        self.assertEqual(test["feature_dimension"], 105)
        self.assertEqual(test["model_parameter_count"], 477185)

    def test_no_overwrite_finalizer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            self.finalizer.write_text(path, "first")
            with self.assertRaises(FileExistsError):
                self.finalizer.write_text(path, "second")
            self.assertEqual(path.read_text(), "first")


if __name__ == "__main__":
    unittest.main(verbosity=2)
