#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve()
SUMMARY = HERE.with_name("a8_rk05_ribomimo_full_four_matrix_summary.py")
VERIFIER = HERE.with_name("a8_rk05_verify_ribomimo_full_four_matrix_summary.py")
if not SUMMARY.exists():
    SUMMARY = HERE.parents[1] / SUMMARY.name
    VERIFIER = HERE.parents[1] / VERIFIER.name
SLUGS = {"Mohammad16": "mohammad16", "Subtelny14": "subtelny14",
         "Mohammad19-1": "mohammad19_1", "Mohammad19-2": "mohammad19_2"}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate(folds, prefix=""):
    result = {}
    for metric in ("r2", "mse", "pearson"):
        values = [fold["metrics"][metric] for fold in folds]
        result[f"{metric}_mean"] = statistics.fmean(values)
        result[f"{metric}_std"] = statistics.pstdev(values)
    return result


def baseline_aggregate(folds):
    result = {}
    for metric in ("r2", "mse"):
        values = [fold["constant_train_mean_baseline"][metric] for fold in folds]
        result[f"{metric}_mean"] = statistics.fmean(values)
        result[f"{metric}_std"] = statistics.pstdev(values)
    return result


def make_fixture(repo):
    root = repo / "audits/20261118/RK05"
    write_json(root / "ribomimo_full_loader_preflight_v1.json", {"status": "PASS"})
    raws = [5000, 5000, 3000, 2669]
    eligible = [2100, 2000, 2024, 2000]
    for dataset_index, (dataset, slug) in enumerate(SLUGS.items()):
        folds = []
        official_folds = []
        independent_folds = []
        for fold_index in range(10):
            metrics = {"r2": 0.1 * dataset_index + 0.001 * fold_index,
                       "mse": 1.0 + 0.1 * dataset_index + 0.002 * fold_index,
                       "pearson": 0.2 + 0.05 * dataset_index + 0.001 * fold_index}
            baseline = {"r2": -0.000001 * fold_index,
                        "mse": metrics["mse"] + 0.5}
            folds.append({"fold": fold_index, "metrics": metrics,
                          "constant_train_mean_baseline": baseline})
            official_folds.append({"fold": fold_index, "best_epoch": fold_index + 1})
            independent_folds.append({"fold": fold_index, "valid_masked_codons": 100 + fold_index,
                                      "sizes": {"train": 100, "valid": 20, "test": 20}})
        agg = aggregate(folds)
        production = {"matrix": {"raw_records": raws[dataset_index],
                                 "official_loader_eligible_records": eligible[dataset_index],
                                 "sha256": f"{dataset_index:064d}"},
                      "official_result": {"aggregate": agg, "folds": official_folds}}
        retrain = json.loads(json.dumps(production))
        independent = {"status": "PASS", "dataset": dataset,
                       "checks_total": 94, "checks_passed": 94,
                       "production_driver_imported": False,
                       "two_forward_passes_per_fold": True,
                       "fold_results": independent_folds}
        production_path = root / f"ribomimo_full_{slug}_v1.json"
        retrain_path = root / f"ribomimo_full_{slug}_retrain_v1.json"
        independent_path = root / f"ribomimo_full_{slug}_independent_v1.json"
        write_json(production_path, production)
        write_json(retrain_path, retrain)
        write_json(independent_path, independent)
        final = {"status": "PASS_COMPLETE_WITH_INDEPENDENT_RETRAIN_AND_INFERENCE",
                 "dataset": dataset, "checks_total": 425, "checks_passed": 425,
                 "production_report": str(production_path),
                 "production_report_sha256": sha256(production_path),
                 "retrain_report": str(retrain_path),
                 "retrain_report_sha256": sha256(retrain_path),
                 "independent_report": str(independent_path),
                 "independent_report_sha256": sha256(independent_path),
                 "all_checkpoints_bitwise_equal": True,
                 "retrain_checkpoint_max_abs_delta": {str(i): 0.0 for i in range(10)},
                 "fold_recalculation": folds,
                 "recomputed_aggregate": agg,
                 "recomputed_constant_train_mean_baseline_aggregate": baseline_aggregate(folds)}
        write_json(root / f"ribomimo_full_{slug}_finalization_v1.json", final)
    return root


class FourMatrixSummaryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "repo"
        self.root = make_fixture(self.repo)

    def tearDown(self):
        self.temporary.cleanup()

    def run_script(self, script):
        return subprocess.run([sys.executable, str(script), "--repo", str(self.repo)],
                              capture_output=True, text=True)

    def test_complete_four_matrix_summary_and_independent_verifier(self):
        produced = self.run_script(SUMMARY)
        self.assertEqual(produced.returncode, 0, produced.stderr)
        summary_path = self.root / "ribomimo_full_four_matrix_summary_v1.json"
        summary = json.loads(summary_path.read_text())
        self.assertEqual(summary["status"], "PASS_COMPLETE_FOUR_MATRIX_OFFICIAL_CV")
        self.assertEqual(len(summary["folds"]), 40)
        self.assertEqual(summary["total_raw_records"], 15669)
        self.assertEqual(summary["total_official_loader_eligible_genes"], 8124)
        self.assertEqual(summary["complete_training_runs"], 8)
        self.assertFalse(summary["sota_claim"])
        verified = self.run_script(VERIFIER)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        report = json.loads((self.root / "ribomimo_full_four_matrix_summary_verification_v1.json").read_text())
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["checks_total"], report["checks_passed"])

    def test_post_summary_evidence_tampering_fails_hash_gate(self):
        self.assertEqual(self.run_script(SUMMARY).returncode, 0)
        target = self.root / "ribomimo_full_mohammad16_independent_v1.json"
        target.write_text(target.read_text() + " \n")
        result = self.run_script(VERIFIER)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("evidence_hashes:Mohammad16", result.stderr)
        self.assertFalse((self.root / "ribomimo_full_four_matrix_summary_verification_v1.json").exists())

    def test_incomplete_finalization_blocks_summary(self):
        target = self.root / "ribomimo_full_subtelny14_finalization_v1.json"
        data = json.loads(target.read_text())
        data["status"] = "INCOMPLETE"
        write_json(target, data)
        result = self.run_script(SUMMARY)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Incomplete finalization: Subtelny14", result.stderr)
        self.assertFalse((self.root / "ribomimo_full_four_matrix_summary_v1.json").exists())

    def test_retrain_aggregate_mismatch_blocks_summary(self):
        target = self.root / "ribomimo_full_mohammad19_1_retrain_v1.json"
        data = json.loads(target.read_text())
        data["official_result"]["aggregate"]["r2_mean"] += 0.1
        write_json(target, data)
        result = self.run_script(SUMMARY)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Training identity mismatch: Mohammad19-1", result.stderr)
        self.assertFalse((self.root / "ribomimo_full_four_matrix_summary_v1.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
