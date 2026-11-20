from __future__ import annotations

import csv
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

ROOT = Path(os.environ.get("CODONFLOW_ROOT", Path(__file__).resolve().parents[1]))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load("channel_prepare", ROOT / "scripts/a8_rk08_prepare_channel_screen.py")
select = load("channel_select", ROOT / "scripts/a8_rk08_select_channel_screen.py")
evaluate = load("channel_evaluate", ROOT / "scripts/a8_rk08_eval_channel_screen.py")
verify = load("channel_verify", ROOT / "scripts/a8_rk08_verify_channel_screen.py")


class ChannelScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = json.loads((ROOT / "configs/a8_rk08_channel_screen_protocol_v1.json").read_text())
        cls.preparation = json.loads((ROOT / "audits/20261118/RK08/channel_screen_preparation_v1.json").read_text())
        cls.arms = cls.protocol["arms_in_tie_break_order"]

    def test_active_maps_are_consistent(self):
        for arm in self.arms:
            expected = prepare.active_map(arm)
            self.assertEqual(expected, select.active_map(arm))
            self.assertEqual(expected, verify.active_map(arm))
            self.assertEqual(expected, self.preparation["active_mechanisms"][arm])

    def test_single_and_leave_one_out_cardinality(self):
        for mechanism in ("initiation", "velocity", "decay", "pair"):
            self.assertEqual(sum(prepare.active_map(f"{mechanism}_only").values()), 1)
            self.assertEqual(sum(prepare.active_map(f"no_{mechanism}").values()), 3)

    def test_selection_minimum_and_tie_break(self):
        values = {arm: float(index) for index, arm in enumerate(self.arms)}
        self.assertEqual(select.choose_arm(values, self.arms), "all")
        tied = {arm: 1.0 for arm in self.arms}
        self.assertEqual(select.choose_arm(tied, self.arms), "all")
        reversed_order = list(reversed(self.arms))
        self.assertEqual(select.choose_arm(tied, reversed_order), "no_pair")

    def test_cluster_balancing_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.csv"
            fields = ["record_id", "split", "cluster_id", "target", "prediction"]
            rows = [
                {"record_id": "a", "split": "dev", "cluster_id": "A", "target": 0, "prediction": 1},
                {"record_id": "b1", "split": "dev", "cluster_id": "B", "target": 0, "prediction": 2},
                {"record_id": "b2", "split": "dev", "cluster_id": "B", "target": 0, "prediction": 2},
                {"record_id": "b3", "split": "dev", "cluster_id": "B", "target": 0, "prediction": 2},
            ]
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            result = select.recompute_partition_metrics(path, "dev")
            self.assertAlmostEqual(result["cluster_balanced_mse"], 2.5)
            self.assertEqual(result["n_rows"], 4)
            self.assertEqual(result["n_clusters"], 2)
            rows[0]["prediction"] = 0
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            changed = select.recompute_partition_metrics(path, "dev")
            self.assertAlmostEqual(changed["cluster_balanced_mse"], 2.0)
            self.assertNotEqual(result["cluster_balanced_mse"], changed["cluster_balanced_mse"])

    def test_holm_reference(self):
        expected = np.array([0.03, 0.04, 0.04])
        np.testing.assert_allclose(evaluate.holm_adjust([0.01, 0.02, 0.03]), expected)
        np.testing.assert_allclose(verify.holm([0.01, 0.02, 0.03]), expected)

    def test_gate_direction_multiplicity_and_none(self):
        rows = []
        for right in ("ribokinetic_none", "ridge_all", "ridge_gc"):
            for metric in ("spearman", "cluster_balanced_mse"):
                rows.append({
                    "partition": "sequence_ood",
                    "right": right,
                    "metric": metric,
                    "ci95_low": 0.1 if metric == "spearman" else -0.2,
                    "ci95_high": 0.2 if metric == "spearman" else -0.1,
                    "holm_pvalue_within_partition": 0.01,
                })
        self.assertTrue(evaluate.channel_gate(rows, "velocity_only"))
        self.assertFalse(evaluate.channel_gate(rows, "none"))
        tampered = [dict(row) for row in rows]
        tampered[0]["holm_pvalue_within_partition"] = 0.05
        self.assertFalse(evaluate.channel_gate(tampered, "velocity_only"))
        self.assertFalse(evaluate.channel_gate(rows[:-1], "velocity_only"))

    def test_state_dict_tamper_is_detected(self):
        left = {"x": torch.ones(2), "y": torch.zeros(1)}
        right = {"x": torch.ones(2), "y": torch.zeros(1)}
        self.assertTrue(select.state_equal(left, right))
        right["x"][0] = 0
        self.assertFalse(select.state_equal(left, right))

    def test_frozen_screen_and_boundary_contract(self):
        self.assertEqual(self.protocol["screen"]["include_splits"], ["train", "dev"])
        self.assertEqual(len(self.arms), 10)
        self.assertFalse(self.protocol["functional_untouched_evaluated"])
        self.assertFalse(self.protocol["velocity_mechanism_pass"])
        self.assertFalse(self.protocol["rk_g1_pass"])
        self.assertFalse(self.protocol["expensive_generation_authorized"])
        for arm in self.arms:
            item = self.preparation["config_hashes"][arm]
            path = ROOT / item["path"]
            config = json.loads(path.read_text())
            self.assertEqual(config["include_splits"], ["train", "dev"])
            self.assertEqual(prepare.sha256(path), item["sha256"])


if __name__ == "__main__":
    unittest.main()
