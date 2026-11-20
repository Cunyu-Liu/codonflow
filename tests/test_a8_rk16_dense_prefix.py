from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from codonflow.eval.anytime import FrozenReference
from scripts.a8_rk16_score_dense_prefix import (
    holm_adjust,
    objective_lookup,
    paired_effect,
    raw_lineardesign,
    raw_ensemble,
    score_trajectory,
    sequence_sha256,
    trajectory_records,
)


class RK16DensePrefixContractTests(unittest.TestCase):
    def test_lineardesign_order_and_duplicate_positions_are_preserved(self):
        sequences = {0.0: "ATGAAA", 0.1: "ATGAAG", 0.2: "ATGAAA"}
        report = {
            "runs": [
                {"record_id": "r", "lambda": value, "returncode": 0, "protein_identity_pass": True, "evaluation_sequence_dna": sequences[value]}
                for value in (0.2, 0.0, 0.1)
            ]
        }
        self.assertEqual(raw_lineardesign(report, "r", [0.0, 0.1, 0.2]), ["ATGAAA", "ATGAAG", "ATGAAA"])

    def test_ensemble_order_and_identity_fields_match_real_report(self):
        report = {"records": [{"record_id": "r", "returncode": 0, "runs": [
            {"run_id": 2, "protein_identity_pass": True, "evaluation_sequence_dna": "ATGAAG"},
            {"run_id": 1, "protein_identity_pass": True, "evaluation_sequence_dna": "ATGAAA"},
            {"run_id": 3, "protein_identity_pass": True, "evaluation_sequence_dna": "ATGAAA"},
        ]}]}
        self.assertEqual(raw_ensemble(report, "r", [1, 2, 3]), ["ATGAAA", "ATGAAG", "ATGAAA"])

    def test_duplicate_objective_reuse_does_not_shift_budget(self):
        sequences = ["ATGAAA", "ATGAAA", "ATGAAG"]
        points = [
            {"sequence": "ATGAAA", "sequence_sha256": sequence_sha256("ATGAAA"), "objectives": [1.0]},
            {"sequence": "ATGAAG", "sequence_sha256": sequence_sha256("ATGAAG"), "objectives": [2.0]},
        ]
        lookup = objective_lookup({"points": points})
        records = trajectory_records(sequences, lookup, 3)
        scored = score_trajectory(records, FrozenReference(np.array([0.0]), np.array([1.0])), 3)
        self.assertEqual([row["n_scored"] for row in scored["curve"]], [1, 2, 3])
        self.assertEqual([row["novel_sequence"] for row in scored["curve"]], [True, False, True])
        self.assertEqual([row["n_unique_so_far"] for row in scored["curve"]], [1, 1, 2])
        self.assertEqual(scored["dense_budget_step_auc_v2"], 1.0)
        self.assertEqual(scored["endpoint_hypervolume_normalized"], 2.0)
        self.assertFalse(scored["padding_used"])

    def test_missing_budget_is_not_padded(self):
        sequence = "ATGAAA"
        lookup = objective_lookup({"points": [{"sequence": sequence, "sequence_sha256": sequence_sha256(sequence), "objectives": [1.0]}]})
        with self.assertRaisesRegex(ValueError, "insufficient real outputs"):
            trajectory_records([sequence], lookup, 2)

    def test_single_output_cannot_become_dense_auc(self):
        sequence = "ATGAAA"
        lookup = objective_lookup({"points": [{"sequence": sequence, "sequence_sha256": sequence_sha256(sequence), "objectives": [1.0]}]})
        records = trajectory_records([sequence], lookup, 1)
        with self.assertRaisesRegex(ValueError, "max_budget must be an integer"):
            score_trajectory(records, FrozenReference(np.array([0.0]), np.array([1.0])), 1)

    def test_paired_effect_and_holm(self):
        result = paired_effect(np.ones(18), np.zeros(18), 1000, 7)
        self.assertEqual(result["mean_effect"], 1.0)
        self.assertEqual(result["ci95"], [1.0, 1.0])
        adjusted = holm_adjust({"a": 0.01, "b": 0.02, "c": 0.5})
        self.assertEqual(adjusted["a"], 0.03)
        self.assertEqual(adjusted["b"], 0.04)
        self.assertEqual(adjusted["c"], 0.5)

    def test_protocol_does_not_authorize_forbidden_claims(self):
        path = Path(__file__).resolve().parents[1] / "configs/a8_rk16_dense_prefix_protocol_v1.json"
        protocol = json.loads(path.read_text())
        self.assertEqual(protocol["status"], "FROZEN_BEFORE_DENSE_PREFIX_SCORING")
        self.assertEqual(protocol["holm_family_size"], 6)
        self.assertFalse(protocol["time_matched_comparison"])
        self.assertFalse(protocol["scientific_gate_passed"])
        self.assertFalse(protocol["codonflow_rk_evaluated"])
        self.assertFalse(protocol["functional_untouched_evaluated"])
        self.assertFalse(protocol["external_sota_authorized"])


if __name__ == "__main__":
    unittest.main()
