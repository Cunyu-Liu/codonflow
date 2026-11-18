from __future__ import annotations

import importlib.util
import math
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "a8_rk05_lineardesign_official_smoke.py"
SPEC = importlib.util.spec_from_file_location("a8_rk05_lineardesign_official_smoke", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class LinearDesignHelpersTest(unittest.TestCase):
    def test_parse_official_example(self):
        stdout = "mRNA sequence:  AUGAACGAUACGGAGGCGAUC\nmRNA structure: ......(((.((....)))))\nmRNA folding free energy: -1.10 kcal/mol; mRNA CAI: 0.695\n"
        parsed = MODULE.parse_stdout(stdout)
        self.assertEqual(parsed["sequence_rna"], "AUGAACGAUACGGAGGCGAUC")
        self.assertEqual(parsed["official_mfe_kcal_mol"], -1.10)
        self.assertEqual(parsed["official_cai"], 0.695)

    def test_parse_rejects_missing_payload(self):
        with self.assertRaises(ValueError):
            MODULE.parse_stdout("mRNA sequence: AUG\n")

    def test_parse_rejects_structure_length_mismatch(self):
        stdout = "mRNA sequence: AUG\nmRNA structure: .\nmRNA folding free energy: 0.00 kcal/mol; mRNA CAI: 1.000\n"
        with self.assertRaises(ValueError):
            MODULE.parse_stdout(stdout)

    def test_translate(self):
        self.assertEqual(MODULE.translate("AUGAACGAUACGGAGGCGAUC"), "MNDTEAI")
        self.assertEqual(MODULE.translate("ATGTAA"), "M*")

    def test_translate_rejects_partial_codon(self):
        with self.assertRaises(ValueError):
            MODULE.translate("ATGAA")

    def test_fasta_exact_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.fasta"
            path.write_text(">a description\nATG\n>b\nTAA\n")
            self.assertEqual(MODULE.read_fasta(path), {"a": "ATG", "b": "TAA"})

    def test_fasta_rejects_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.fasta"
            path.write_text(">a\nATG\n>a\nTAA\n")
            with self.assertRaises(ValueError):
                MODULE.read_fasta(path)

    def test_official_cai_matches_rounded_example(self):
        table = Path("/home/codonflow-a8-rk-external/LinearDesign-f0126ca89a8b853088b4bccfd2cc8c378d3678be/codon_usage_freq_table_human.csv")
        if not table.exists():
            self.skipTest("fixed official table not materialized")
        weights = MODULE.load_official_weights(table)
        value = MODULE.cai("AUGAACGAUACGGAGGCGAUC", weights)
        self.assertAlmostEqual(value, 0.695, delta=0.001)

    def test_cai_rejects_zero_weight(self):
        with self.assertRaises(ValueError):
            MODULE.cai("AUG", {"AUG": 0.0})

    def test_commit_is_fixed(self):
        self.assertEqual(MODULE.COMMIT, "f0126ca89a8b853088b4bccfd2cc8c378d3678be")

    def test_fold_dangles_convention_is_explicit(self):
        structure0, energy0 = MODULE.fold_with_dangles("AUGAACGAUACGGAGGCGAUC", 0)
        structure2, energy2 = MODULE.fold_with_dangles("AUGAACGAUACGGAGGCGAUC", 2)
        self.assertEqual(structure0, structure2)
        self.assertAlmostEqual(energy0, -1.1, delta=0.051)
        self.assertTrue(math.isfinite(energy2))


if __name__ == "__main__":
    unittest.main()
