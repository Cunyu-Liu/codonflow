#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).with_name("a8_rk02_mordstein_reference_recovery.py")
if not MODULE_PATH.exists():
    MODULE_PATH = Path(__file__).parent.parent / "a8_rk02_mordstein_reference_recovery.py"
SPEC = importlib.util.spec_from_file_location("recovery", MODULE_PATH)
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


def codons(protein):
    result = []
    for aa in protein:
        result.append(next(codon for codon, value in recovery.CODON_TABLE.items() if value == aa))
    return "".join(result)


class RecoveryTests(unittest.TestCase):
    def test_reference_lengths(self):
        self.assertEqual(len(recovery.EGFP_PROTEIN), 239)
        self.assertEqual(len(recovery.R1_PROTEIN), 100)
        self.assertEqual(len(recovery.R2_SEED_PROTEIN), 93)
        self.assertEqual(recovery.GAP_LENGTH, 138)

    def test_r1_translation(self):
        seq = codons(recovery.R1_PROTEIN)
        self.assertEqual(len(seq), 300)
        self.assertEqual(recovery.translate(seq), recovery.R1_PROTEIN)

    def test_r2_boundary_roundtrip(self):
        coding = codons(recovery.R2_SEED_PROTEIN)
        raw = ("A" + coding + "C" * 20).translate(recovery.COMP)[::-1]
        self.assertEqual(len(raw), 300)
        self.assertEqual(recovery.r2_coding(raw), coding)
        self.assertEqual(recovery.translate(recovery.r2_coding(raw)), recovery.R2_SEED_PROTEIN)

    def test_seed_assignment_up_to_eight_errors(self):
        first = "A" * 300
        second = "A" * 150 + "C" * 150
        assigner = recovery.SeedAssigner([first, second], 8)
        query = list(first)
        for index in range(8):
            query[index * 30] = "G"
        self.assertEqual(assigner.assign("".join(query)), 0)
        query[8 * 30] = "G"
        self.assertIsNone(assigner.assign("".join(query)))
        self.assertEqual(assigner.assign(second), 1)

    def test_centroid_selection_collapses_sequencing_errors(self):
        first = "A" * 300
        second = "A" * 150 + "C" * 150
        error = "T" + first[1:]
        centroids, counts = recovery.choose_centroids({first: 100, error: 50, second: 80}, 300, 10, 10, 8)
        self.assertEqual(centroids, [first, second])
        self.assertEqual(counts, [100, 80])


if __name__ == "__main__":
    unittest.main()
