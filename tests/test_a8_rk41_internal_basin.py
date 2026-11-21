#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import tempfile
import unittest
import unittest.mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import a8_rk41_internal_basin_initialization as rk41
import a8_rk41_verify_internal_basin as verify41


class RK41InternalBasinTests(unittest.TestCase):
    def test_pool_first_member_exactly_reuses_rk39(self):
        source = "ATGGCTGCTTAA"
        pool, generation_seeds = rk41.generate_pool(source, 7)
        self.assertEqual(pool[0], rk41.rk39.protein_only_initial(source, 7))
        self.assertEqual(generation_seeds[0], 7)
        self.assertEqual(len(pool), 8)
        self.assertEqual(len(set(pool)), 8)
        self.assertTrue(all(sequence.endswith("TAA") for sequence in pool))
        self.assertTrue(all(rk41.rk39.protein_from_cds(sequence) == "MAA*" for sequence in pool))

    def test_independent_pool_is_byte_identical(self):
        source = "ATGGCTGCTTAA"
        production = rk41.generate_pool(source, 3)
        independent = verify41.generate_pool(source, 3)
        self.assertEqual(production, independent)

    def test_first_and_best_selection_rules(self):
        objectives = [[100.0, 0.0], [90.0, 1.0]]
        self.assertEqual(rk41.select_pool_index("raw_pool_first_b11", objectives, [1.0, 1.0], None), 0)
        self.assertEqual(rk41.select_pool_index("raw_pool_best_b11", objectives, [1.0, 1.0], None), 0)
        normalization = ([0.0, 0.0], [1000.0, 0.1])
        self.assertEqual(rk41.select_pool_index("calibrated_pool_best_b11", objectives, [1.0, 1.0], normalization), 1)
        self.assertEqual(rk41.select_pool_index("calibrated_pool_first_b11", objectives, [1.0, 1.0], normalization), 0)

    def test_budget_partition_is_exact(self):
        protocol = json.loads((ROOT / "configs/a8_rk41_internal_basin_protocol_v1.json").read_text())
        self.assertEqual(protocol["pool_size"] + protocol["local_unique_proposals_after_pool"], protocol["budget"])
        self.assertEqual(protocol["budget"], 11)
        self.assertEqual(protocol["pool_size"], 8)

    def test_protocol_counts_and_no_external_initialization(self):
        protocol = json.loads((ROOT / "configs/a8_rk41_internal_basin_protocol_v1.json").read_text())
        self.assertEqual(len(protocol["new_arms"]), 4)
        self.assertEqual(protocol["expected_new_run_count"], 18 * 3 * 4)
        self.assertEqual(protocol["expected_new_unique_scorer_calls"], 18 * 3 * 4 * 11)
        self.assertEqual(protocol["expected_total_analysis_runs"], 324)
        self.assertEqual(protocol["execution"]["smoke_expected_new_unique_scorer_calls"], 44)
        self.assertNotIn("raw_external_b11", protocol["new_arms"])
        self.assertFalse(protocol["external_sota_authorized"])
        self.assertFalse(protocol["functional_untouched_used"])

    def test_primary_families_include_real_external_actual_set(self):
        protocol = json.loads((ROOT / "configs/a8_rk41_internal_basin_protocol_v1.json").read_text())
        self.assertEqual(len(protocol["primary_families"]), 3)
        external = protocol["primary_families"][-1]
        self.assertEqual(external["right"], "lineardesign_lambda11")
        self.assertEqual(external["endpoints"], ["first_k_hv", "first_k_ned"])
        self.assertEqual(protocol["statistics"]["multiplicity"], "Holm over the two endpoints within each of the three independently named primary families")

    def test_decision_labels_match_across_implementations(self):
        for selection in (False, True):
            for sequential in (False, True):
                for external in (False, True):
                    self.assertEqual(rk41.decision_label(selection, sequential, external),
                                     verify41.decision_label(selection, sequential, external))
        self.assertEqual(rk41.decision_label(True, True, False), "INTERNAL_MULTISTART_SUPPORTED_COMMON_INPUT_TASK_UNRESOLVED")
        self.assertEqual(rk41.decision_label(False, False, False), "INTERNAL_MULTISTART_NOT_SUPPORTED_COMMON_INPUT_TASK_UNRESOLVED")

    def test_independent_benchmark_loader_preserves_all_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "two_records.fasta"
            path.write_text(">first description\nATGGCTTAA\n>second\nATGGCTGCTTAA\n")
            benchmark, records = verify41.load_benchmark(path)
        self.assertEqual(records, ["first", "second"])
        self.assertEqual(len(benchmark), 2)
        self.assertEqual(benchmark["second"], "ATGGCTGCTTAA")

    def test_accepted_rk40_payload_does_not_require_redundant_arm_field(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "accepted.json"
            payload = {"points": [{"budget": i + 1, "sequence": "ATGGCTTAA", "objectives": [0.0] * 4} for i in range(11)],
                       "unique_scorer_calls": 11, "initial_state": "ATGGCTTAA", "initial_state_sha256": "abc",
                       "search_normalization": None, "common_input": True,
                       "evaluation": {"best_normalized_weighted_utility": 1.0, "best_single_point_normalized_hv": 2.0,
                                      "matched_first_k_actual_set": {"hypervolume_normalized": 3.0, "pairwise_ned": 4.0},
                                      "terminal_full_actual_set": {"hypervolume_normalized": 5.0, "pairwise_ned": 6.0},
                                      "dense_internal_auc": {"auc": 7.0}}}
            path.write_text(json.dumps(payload))
            row = {"path": str(path), "arm": "raw_random_b11", "record_id": "r", "seed": 0,
                   "sha256": rk41.rk39.sha(path)}
            summary_path = Path(directory) / "rk40_summary.json"
            summary_path.write_text(json.dumps({"runs": [row]}))
            calibration_dir = Path(directory) / "calibration"
            calibration_dir.mkdir()
            calibration_path = calibration_dir / "r.json"
            calibration_path.write_text("{}")
            descriptor = {"arm": "raw_random_b11", "record_id": "r", "seed": 0,
                          "rk40_summary": str(summary_path), "rk40_summary_sha256": rk41.rk39.sha(summary_path),
                          "calibration_dir": str(calibration_dir), "calibration_sha256": rk41.rk39.sha(calibration_path),
                          "k": 11, "weights": [1.0, 1.0, 1.0, 1.0]}
            with unittest.mock.patch.object(rk41.rk40, "evaluate_payload", side_effect=lambda p, c, k, w: p["evaluation"]), \
                    unittest.mock.patch.object(rk41.rk40, "descriptor", side_effect=lambda p, payload: payload):
                accepted = rk41.accepted_baseline(descriptor, "raw_random_b11")
        self.assertEqual(accepted["unique_scorer_calls"], 11)
        self.assertEqual(len(accepted["points"]), 11)

    def test_independent_single_codon_proposal_is_synonymous(self):
        source = "ATGGCTGCTTAA"
        candidate = verify41.single_codon_proposal(source, np.random.default_rng(5))
        self.assertEqual(verify41.protein_from_cds(candidate), "MAA*")
        self.assertTrue(candidate.endswith("TAA"))
        self.assertEqual(len(candidate), len(source))


if __name__ == "__main__":
    unittest.main()
