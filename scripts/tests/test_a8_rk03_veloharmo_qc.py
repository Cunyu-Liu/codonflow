#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
CANDIDATES = [HERE.with_name("a8_rk03_veloharmo_qc.py"), HERE.parent.parent / "a8_rk03_veloharmo_qc.py"]
MODULE = next(path for path in CANDIDATES if path.is_file())
spec = importlib.util.spec_from_file_location("veloharmo_qc", MODULE)
qc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qc)


def matrix_text(records):
    lines = []
    for gene, declared, codons, speeds, features in records:
        lines.extend([f">{gene} {declared}", "\t".join(codons), "\t".join(str(x) for x in speeds), "\t".join(features)])
    return "\n".join(lines) + "\n"


def valid_record(gene="g1", dim=1):
    codons = ["ATG", "GAG", "GAA"]
    return gene, len(codons), codons, [1.0, 0.0, 2.0], [",".join(["0.1"] * dim + ["H"])] * 3


class VeloHarmoQCTests(unittest.TestCase):
    def parse(self, records):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "matrix.txt"
            path.write_text(matrix_text(records))
            return qc.parse_records(path)

    def test_valid_record_and_density(self):
        records, _ = self.parse([valid_record()])
        self.assertEqual(records[0]["normalized_density"], [2 / 3, 0.0, 4 / 3])
        self.assertEqual(records[0]["base_exclusion_reasons"], [])

    def test_duplicate_ids_are_counted(self):
        records, _ = self.parse([valid_record("g1"), valid_record("g1")])
        self.assertEqual(len(records), 2)
        # Duplicate exclusion is applied in run_qc; the parser preserves both IDs.
        self.assertEqual({r["gene_id"] for r in records}, {"g1"})

    def test_four_track_length_mismatch(self):
        gene, declared, codons, speeds, features = valid_record()
        records, _ = self.parse([(gene, declared, codons, speeds[:-1], features)])
        self.assertIn("four_track_length_mismatch", records[0]["base_exclusion_reasons"])

    def test_declared_count_mismatch(self):
        gene, _, codons, speeds, features = valid_record()
        records, _ = self.parse([(gene, 99, codons, speeds, features)])
        self.assertIn("declared_codon_count_mismatch", records[0]["base_exclusion_reasons"])

    def test_invalid_codon(self):
        gene, declared, codons, speeds, features = valid_record()
        codons[1] = "NNN"
        records, _ = self.parse([(gene, declared, codons, speeds, features)])
        self.assertIn("invalid_codon_alphabet", records[0]["base_exclusion_reasons"])

    def test_negative_velocity(self):
        gene, declared, codons, speeds, features = valid_record()
        speeds[1] = -1
        records, _ = self.parse([(gene, declared, codons, speeds, features)])
        self.assertIn("invalid_or_negative_velocity", records[0]["base_exclusion_reasons"])

    def test_no_normalization_coverage(self):
        gene, declared, codons, speeds, features = valid_record()
        records, _ = self.parse([(gene, declared, codons, [0, 0.5, 0.2], features)])
        self.assertIn("normalization_no_velocity_above_0_5", records[0]["base_exclusion_reasons"])

    def test_invalid_numeric_feature(self):
        gene, declared, codons, speeds, features = valid_record()
        features[0] = "bad,H"
        records, _ = self.parse([(gene, declared, codons, speeds, features)])
        self.assertIn("invalid_numeric_structure_feature", records[0]["base_exclusion_reasons"])

    def test_invalid_secondary_structure(self):
        gene, declared, codons, speeds, features = valid_record()
        features[0] = "0.1,X"
        records, _ = self.parse([(gene, declared, codons, speeds, features)])
        self.assertIn("invalid_secondary_structure_symbol", records[0]["base_exclusion_reasons"])

    def test_within_record_feature_dimension_mismatch(self):
        gene, declared, codons, speeds, features = valid_record()
        features[1] = "0.1,0.2,H"
        records, _ = self.parse([(gene, declared, codons, speeds, features)])
        self.assertIn("within_record_feature_dim_mismatch", records[0]["base_exclusion_reasons"])

    def test_feature_dimension_counts(self):
        records, dims = self.parse([valid_record("g1", 1), valid_record("g2", 2)])
        self.assertEqual(dims[1], 1)
        self.assertEqual(dims[2], 1)

    def test_archive_path_safety(self):
        with self.assertRaises(RuntimeError):
            qc.safe_relative(qc.ARCHIVE_ROOT + "/../escape")
        with self.assertRaises(RuntimeError):
            qc.safe_relative("other/escape")

    def test_numeric_summary(self):
        result = qc.numeric_summary([1, 2, 3, 4])
        self.assertEqual(result["median"], 2.5)
        self.assertEqual(result["mean"], 2.5)


if __name__ == "__main__":
    unittest.main()
