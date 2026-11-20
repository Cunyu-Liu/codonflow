import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from codonflow.core.codon import gc_fraction
from codonflow.core.motifs import motif_penalty_score
from codonflow.eval.anytime import FrozenReference, dense_budget_step_auc_v2
from codonflow.eval.metrics import cai, cai_weights_from_rscu, mfe, pairwise_ned
from scripts import a8_rk06_verify_simple_search_dense_unique18 as independent
from scripts import a8_rk06_finalize_simple_search_dense_unique18 as finalizer


class IndependentHelperTests(unittest.TestCase):
    def test_independent_objectives_match_definitions(self):
        root = Path(__file__).resolve().parents[2]
        rscu = json.loads((root / "configs/cai_ref_v4train.json").read_text())
        weights = independent.cai_weights(rscu)
        sequence = "ATGAAATTTGGCTAG"
        actual = independent.independent_objectives(sequence, weights, 0.55)
        expected = np.array([
            cai(sequence, cai_weights_from_rscu(rscu)),
            -mfe(sequence),
            -abs(gc_fraction(sequence) - 0.55),
            -motif_penalty_score(sequence) / (len(sequence) // 3),
        ])
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12)

    def test_dense_hv_matches_frozen_evaluator(self):
        records = [{"budget": i + 1, "objectives": [0.1 * i, 0.2 + 0.05 * i, 0.3, 0.4 + 0.01 * i]} for i in range(5)]
        frozen = FrozenReference(np.zeros(4), np.ones(4))
        expected = dense_budget_step_auc_v2(records, frozen, max_budget=5)
        actual = [independent.independent_hv(np.asarray([row["objectives"] for row in records[:budget]]), np.zeros(4), np.ones(4)) for budget in range(1, 6)]
        np.testing.assert_allclose(actual, [row["hv"] for row in expected["curve"]], rtol=0, atol=1e-12)

    def test_pareto_strict_dominance(self):
        points = np.array([[1.0, 0.0], [0.0, 1.0], [2.0, 2.0], [0.5, 0.5]])
        self.assertEqual(independent.independent_pareto(points), [2])

    def test_ned_matches_metric(self):
        sequences = ["ATGAAATAG", "ATGAAGTAG", "ATGAAATAG"]
        self.assertAlmostEqual(independent.independent_ned(sequences), pairwise_ned(sequences, rng=np.random.default_rng(0)))

    def test_motif_penalty_is_per_codon_input(self):
        sequence = "AATAAACAGGTAATACGACTCACTATAATTTAGGTGACACTATAAAAAAA"
        self.assertEqual(independent.independent_motif(sequence), 11.0)
        self.assertEqual(independent.independent_motif(sequence), motif_penalty_score(sequence))

    def test_production_endpoint_aliases_prevent_aggregation_stopiteration(self):
        production = [
            {"method": "hill_climbing", "endpoint": "dense_budget_step_auc_v2"},
            {"method": "hill_climbing", "endpoint": "hypervolume_normalized_B500"},
        ]
        for endpoint in ["dense_budget_step_auc_v2", "b500_normalized_hv"]:
            candidate = next(row for row in production
                             if row["endpoint"] == independent.production_endpoint_for_independent(endpoint))
            self.assertEqual(candidate["method"], "hill_climbing")
        with self.assertRaises(ValueError):
            independent.production_endpoint_for_independent("unregistered_endpoint")

    def test_external_dense_policy_accepts_only_explicit_null_schemas(self):
        frozen_text = ("LinearDesign/EnsembleDesign and other unordered actual-output sets retain "
                       "dense_budget_step_auc_v2=null; no zero filling or lambda-to-budget conversion")
        cases = [
            (frozen_text, (True, True)),
            ({"dense_budget_step_auc_v2": None, "independent_lambda_run_unordered": True}, (True, True)),
            ("dense_budget_step_auc_v2=null", (False, False)),
            ({"dense_budget_step_auc_v2": 0.0, "independent_lambda_run_unordered": True}, (False, True)),
        ]
        for module in [independent, finalizer]:
            for policy, expected in cases:
                with self.subTest(module=module.__name__, policy=policy):
                    self.assertEqual(module.external_dense_policy_status(policy), expected)

    def test_dominance_uses_independent_arrays(self):
        with tempfile.TemporaryDirectory() as directory:
            a_path = Path(directory) / "a.npy"
            b_path = Path(directory) / "b.npy"
            np.save(a_path, np.array([[1.0, 0.0], [0.0, 0.0]]))
            np.save(b_path, np.array([[2.0, 2.0], [0.0, 1.0]]))
            rows = [
                {"record_id": "r", "seed": 0, "method": "a", "independent_objectives_path": str(a_path)},
                {"record_id": "r", "seed": 0, "method": "b", "independent_objectives_path": str(b_path)},
            ]
            result = independent.independent_dominance(rows)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["mean_fraction_a_strictly_dominated_by_b"], 1.0)
            self.assertEqual(result[0]["mean_fraction_b_strictly_dominated_by_a"], 0.0)


if __name__ == "__main__":
    unittest.main()
