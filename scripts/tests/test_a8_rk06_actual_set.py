import hashlib
import unittest
from unittest.mock import patch

import numpy as np

from codonflow.eval.anytime import FrozenReference
from codonflow.eval.metrics import cai, cai_weights_from_rscu, compute_rscu
from codonflow.core.codon import gc_fraction, split_codons
from codonflow.core.motifs import motif_penalty_score
from scripts.a8_rk06_recompute_actual_set import recompute_actual_set


class RawActualSetRecomputeTests(unittest.TestCase):
    def setUp(self):
        self.source = "ATGCTGTAA"
        self.variant = "ATGCTATAA"
        self.rscu = compute_rscu([self.source])
        self.calibration = FrozenReference(
            reference=np.zeros(4), scale=np.ones(4)
        ).to_dict()

    def payload(self, solutions=None, reported=None):
        solutions = [self.source, self.variant] if solutions is None else solutions
        method = {
            "status": "done",
            "solutions": solutions,
            "n_unique": len(solutions),
            "elapsed_s": 1.25,
            "forward_calls": None,
            "generator_calls": 2,
            "terminal_reward_evaluations": len(solutions),
            "unique_terminal_reward_calls": len(solutions),
        }
        if reported is not None:
            method["obj_vectors"] = reported
        return {
            "status": "done",
            "benchmark_sha256": "0" * 64,
            "source_sha256": hashlib.sha256(self.source.encode()).hexdigest(),
            "methods": {"toy": method},
        }

    def test_recompute_uses_raw_sequences_and_null_dense_auc(self):
        with patch("scripts.a8_rk06_recompute_actual_set.mfe", side_effect=lambda _seq: -12.5):
            result = recompute_actual_set(self.payload(), self.source, self.calibration, self.rscu)["toy"]
        self.assertEqual(result["evaluation_mode"], "actual_set_only")
        self.assertIsNone(result["dense_budget_step_auc_v2"])
        self.assertIsNone(result["actual_set"]["curve"])
        self.assertEqual(result["actual_set"]["n_actual_outputs"], 2)
        self.assertFalse(result["stored_objectives_used_for_scoring"])
        self.assertIsNone(result["reported_objectives_match"])
        self.assertEqual(result["points"][1]["objectives"][1], 12.5)
        self.assertEqual(
            result["points"][0]["sequence_sha256"],
            hashlib.sha256(self.source.encode()).hexdigest(),
        )
        self.assertEqual(result["legacy_generation_costs"]["generation_seconds"], 1.25)
        self.assertIsNone(result["legacy_generation_costs"]["wall_clock_seconds"])

    def test_reported_objectives_are_compared_not_reused(self):
        with patch("scripts.a8_rk06_recompute_actual_set.mfe", side_effect=lambda _seq: -12.5):
            result = recompute_actual_set(
                self.payload(reported=[[0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0]]),
                self.source,
                self.calibration,
                self.rscu,
            )["toy"]
        self.assertFalse(result["reported_objectives_match"])
        self.assertGreater(result["max_abs_reported_objective_difference"], 0.0)
        self.assertEqual(result["points"][0]["objectives"][1], 12.5)

    def test_matching_reported_objectives_are_detected(self):
        weights = cai_weights_from_rscu(self.rscu)
        reported = []
        for sequence in [self.source, self.variant]:
            reported.append([
                cai(sequence, weights),
                12.5,
                -abs(gc_fraction(sequence) - 0.55),
                -motif_penalty_score(sequence) / len(split_codons(sequence)),
            ])
        with patch("scripts.a8_rk06_recompute_actual_set.mfe", side_effect=lambda _seq: -12.5):
            result = recompute_actual_set(
                self.payload(reported=reported), self.source, self.calibration, self.rscu
            )["toy"]
        self.assertTrue(result["reported_objectives_match"])
        self.assertEqual(result["max_abs_reported_objective_difference"], 0.0)

    def test_identity_and_duplicate_failures_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "identity"):
            recompute_actual_set(self.payload(solutions=["ATGAAATAA"]), self.source, self.calibration, self.rscu)
        with self.assertRaisesRegex(ValueError, "count mismatch"):
            recompute_actual_set(
                self.payload(solutions=[self.source, self.source]), self.source, self.calibration, self.rscu
            )


if __name__ == "__main__":
    unittest.main()
