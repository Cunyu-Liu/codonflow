from __future__ import annotations

import importlib.util
import math
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "a8_rk05_ensembledesign_official_smoke.py"
SPEC = importlib.util.spec_from_file_location("a8_rk05_ensembledesign_official_smoke", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class EnsembleDesignHelpersTest(unittest.TestCase):
    def test_fixed_commit_and_protocol(self):
        self.assertEqual(MODULE.COMMIT, "cd9324f9574a754063d421e76670bc9fd7555324")
        self.assertEqual(MODULE.PROTOCOL, "a8_rk05_ensembledesign_official_smoke_v2")

    def test_parse_readme_stdout(self):
        stdout = "".join(f">{key}|Ensemble Free Energy: {value['efe']} kcal/mol\n{value['sequence_rna']}\n" for key, value in MODULE.EXPECTED_EXAMPLE.items())
        parsed = MODULE.parse_official_stdout(stdout)
        self.assertEqual([r["record_id"] for r in parsed], ["seq1", "seq2", "seq3"])
        self.assertEqual(parsed[0]["official_efe_kcal_mol"], -18.0)
        self.assertEqual(parsed[2]["sequence_rna"], MODULE.EXPECTED_EXAMPLE["seq3"]["sequence_rna"])

    def test_parse_rejects_unmatched_header(self):
        with self.assertRaises(ValueError):
            MODULE.parse_official_stdout(">seq1|Ensemble Free Energy: -18.0 kcal/mol\nAUG\n>broken\n")

    def test_parse_results_and_best(self):
        text = "[ 1] AUGAAA | Ensemble Free Energy: -2.0 kcal/mol\n[ 2] AUGAAG | Ensemble Free Energy: -3.0 kcal/mol\n[Best] AUGAAG | Ensemble Free Energy: -3.0 kcal/mol\n"
        runs, best = MODULE.parse_results(text)
        self.assertEqual([r["run_id"] for r in runs], [1, 2])
        self.assertEqual(min(runs, key=lambda r: (r["official_efe_kcal_mol"], r["run_id"]))["sequence_rna"], "AUGAAG")
        self.assertEqual(best["official_efe_kcal_mol"], -3.0)

    def test_parse_results_rejects_missing_best(self):
        with self.assertRaises(ValueError):
            MODULE.parse_results("[1] AUGAAA | Ensemble Free Energy: -2.0 kcal/mol\n")

    def test_translate_readme_sequence_without_appended_stop(self):
        sequence = MODULE.EXPECTED_EXAMPLE["seq1"]["sequence_rna"]
        self.assertEqual(MODULE.translate(sequence), "MNTYHITLPWPPSNNRY")
        self.assertEqual(len(sequence), 3 * len("MNTYHITLPWPPSNNRY"))
        self.assertNotIn("*", MODULE.translate(sequence))

    def test_translate_rejects_partial_codon(self):
        with self.assertRaises(ValueError):
            MODULE.translate("ATGAA")

    def test_fasta_preserves_order_and_exact_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.fasta"
            path.write_text(">a description\nMNT\n>b\nYYI\n")
            self.assertEqual(MODULE.read_fasta(path), [("a", "MNT"), ("b", "YYI")])

    def test_fasta_rejects_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.fasta"
            path.write_text(">a\nM\n>a\nN\n")
            with self.assertRaises(ValueError):
                MODULE.read_fasta(path)

    def test_vienna_efe_matches_readme_rounding(self):
        value = MODULE.vienna_efe(MODULE.EXPECTED_EXAMPLE["seq1"]["sequence_rna"])
        self.assertAlmostEqual(value, -18.002363204956055, delta=1e-9)
        self.assertAlmostEqual(value, -18.0, delta=0.051)

    def test_expected_example_contract(self):
        self.assertEqual(list(MODULE.EXPECTED_EXAMPLE), ["seq1", "seq2", "seq3"])
        self.assertEqual([MODULE.EXPECTED_EXAMPLE[f"seq{i}"]["efe"] for i in range(1, 4)], [-18.0, -43.71, -70.29])
        self.assertTrue(all(math.isfinite(MODULE.vienna_efe(item["sequence_rna"])) for item in MODULE.EXPECTED_EXAMPLE.values()))


if __name__ == "__main__":
    unittest.main()
