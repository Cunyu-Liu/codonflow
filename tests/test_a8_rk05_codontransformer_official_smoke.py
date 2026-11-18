import json
import tempfile
import unittest
from pathlib import Path

from scripts.a8_rk05_codontransformer_official_smoke import (
    BENCHMARK_SHA256,
    atomic_json,
    design_qc,
    protein_from_cds,
    read_fasta_record,
    readme_example,
    translate,
)


class CodonTransformerHelpersTest(unittest.TestCase):
    def test_standard_translation_and_stop(self):
        self.assertEqual(translate("ATGGCTTAA"), "MA*")
        self.assertEqual(protein_from_cds("ATGGCTTAA"), "MA")

    def test_protein_requires_single_terminal_stop(self):
        with self.assertRaises(ValueError):
            protein_from_cds("ATGTAAGCT")
        with self.assertRaises(ValueError):
            protein_from_cds("ATGGCT")

    def test_fasta_exact_id_and_duplicate_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.fasta"
            path.write_text(">C01 extra\nATGGCT\nTAA\n>C02\nATGTTT\nTAA\n")
            self.assertEqual(read_fasta_record(path, "C01"), "ATGGCTTAA")
            path.write_text(">C01\nATG\n>C01\nATG\n")
            with self.assertRaises(ValueError):
                read_fasta_record(path, "C01")

    def test_readme_example_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "README.md"
            path.write_text('protein = "MA"\norganism = "Escherichia coli general"\n'
                            '|          Predicted DNA       |\n'
                            '-----------------------------\nATGGCTTAA\n')
            self.assertEqual(readme_example(directory),
                             ("MA", "Escherichia coli general", "ATGGCTTAA"))

    def test_legal_design_qc(self):
        qc = design_qc("ATGGCTTAA", "MA")
        self.assertTrue(qc["legal_synonymous_cds"])
        self.assertEqual(qc["dna_nt"], 9)
        self.assertEqual(qc["protein_aa"], 2)

    def test_default_failure_is_not_hidden(self):
        self.assertFalse(design_qc("ATGTTTTAA", "MA")["legal_synonymous_cds"])
        self.assertFalse(design_qc("ATGGCT", "MA")["legal_synonymous_cds"])
        self.assertFalse(design_qc("ATGTAATAA", "MA")["legal_synonymous_cds"])
        self.assertFalse(design_qc("ATGGCTTAN", "MA")["legal_synonymous_cds"])

    def test_atomic_json_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            atomic_json(path, {"status": "PASS"})
            self.assertEqual(json.loads(path.read_text())["status"], "PASS")
            with self.assertRaises(FileExistsError):
                atomic_json(path, {"status": "FAIL"})

    def test_frozen_benchmark_identity(self):
        self.assertEqual(BENCHMARK_SHA256,
                         "30e3dbbfc3480287b1f87177fe476d7ca283219f08949476da6d08555d0ab4e0")


if __name__ == "__main__":
    unittest.main()
