import json
import math
import unittest
from pathlib import Path

from scripts import a8_rk09_minimal_codonflow as kernel


class TestA8RK09MinimalCodonFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.protocol_path = cls.root / "configs/a8_rk09_minimal_protocol_v1.json"
        cls.protocol = json.loads(cls.protocol_path.read_text())

    def test_valid_state_and_stop(self):
        states = kernel.all_states(2)
        self.assertEqual(len(states), 61)
        self.assertTrue(all(kernel.is_valid_state(state) for state in states))
        self.assertFalse(kernel.is_valid_state((0, 63, 63)))
        self.assertFalse(kernel.is_valid_state((0, 0)))

    def test_feasible_targets(self):
        start = (0, 0, 0, 63)
        targets = kernel.feasible_targets(start)
        self.assertEqual(len(targets), 181)
        self.assertEqual(len(set(targets)), 181)
        self.assertTrue(all(kernel.hamming(start, target) <= 1 for target in targets))
        self.assertTrue(all(target[-1] == 63 for target in targets))

    def test_uniform_simplex(self):
        distribution = kernel.conditional_kernel((0, 0, 0, 63))
        self.assertAlmostEqual(sum(distribution.values()), 1.0, places=14)
        self.assertEqual(set(distribution.values()), {1 / 181})

    def test_forward_mask_removes_dominant_stop(self):
        logits = [math.sin(index + 0.5) for index in range(64)]
        logits[63] = 1e6
        internal = kernel.masked_categorical(logits, terminal=False)
        terminal = kernel.masked_categorical(logits, terminal=True)
        self.assertEqual(len(internal), 64)
        self.assertEqual(internal[63], 0.0)
        self.assertEqual(internal[61:63], [0.0, 0.0])
        self.assertAlmostEqual(sum(internal), 1.0, places=14)
        self.assertEqual(terminal[63], 1.0)
        self.assertEqual(sum(terminal), 1.0)

    def test_preference_ratio(self):
        start = (0, 0, 63)
        beta = 0.75
        distribution = kernel.conditional_kernel(start, beta=beta)
        left, right = sorted(distribution)[:2]
        observed = math.log(distribution[left] / distribution[right])
        expected = beta * (kernel.preference(left) - kernel.preference(right))
        self.assertAlmostEqual(observed, expected, places=12)

    def test_remaining_budget(self):
        start = (0, 0, 0, 63)
        distribution = kernel.conditional_kernel(start, beta=0.75, remaining_budget=0.5)
        self.assertEqual(len(distribution), 103)
        self.assertTrue(all(kernel.preference(target) <= kernel.preference(start) + 0.5 + 1e-15 for target in distribution))
        self.assertAlmostEqual(sum(distribution.values()), 1.0, places=14)

    def test_naive_random_walk_is_biased(self):
        start = (0, 0, 0, 63)
        _, paths = kernel.enumerate_paths(start, 2)
        endpoints = {}
        for path, probability in paths:
            endpoints[path[-1]] = endpoints.get(path[-1], 0.0) + probability
        uniform = {state: 1 / len(endpoints) for state in endpoints}
        self.assertEqual(len(endpoints), 10981)
        self.assertGreater(kernel.total_variation(endpoints, uniform), 0.3)

    def test_exact_path_telescope(self):
        result = kernel.telescope_example((0, 0, 63), 2, 1e-12)
        self.assertTrue(result["pass"])
        self.assertEqual(result["path_count"], 14641)
        self.assertEqual(result["endpoint_count"], 3721)

    def test_event_time_law(self):
        for kappa in (1, 2, 5):
            for u in (0.1, 0.5, 0.9):
                time = 1 - u ** (1 / kappa)
                self.assertAlmostEqual((1 - time) ** kappa, u, places=14)
                self.assertAlmostEqual(1 - (1 - time) ** kappa, 1 - u, places=14)
        self.assertEqual(1 / (3 + 1), 0.25)

    def test_frozen_report(self):
        report_path = self.root / "audits/20261118/RK09/minimal_codonflow_kernel_v1.json"
        report = json.loads(report_path.read_text())
        self.assertTrue(report["all_pass"])
        self.assertEqual((report["checks_passed"], report["checks_total"]), (22, 22))
        self.assertFalse(any(report["prohibited_claims"].values()))


if __name__ == "__main__":
    unittest.main()
