#!/usr/bin/env python3
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from scripts.a8_rk03_ribomimo_qc import (
    normalize_counts,
    process_dataset,
    read_fasta,
    replicate_qc,
    source_key,
)


class RiboMIMOQCTests(unittest.TestCase):
    def test_official_positive_threshold_and_normalization(self):
        density, mean = normalize_counts([0.5, 1.0, 3.0, 0.0])
        self.assertEqual(mean, 2.0)
        self.assertEqual(density, [0.0, 0.5, 1.5, 0.0])
        empty, empty_mean = normalize_counts([0.0, 0.5])
        self.assertEqual(empty, [None, None])
        self.assertIsNone(empty_mean)

    def test_source_key_supports_versioned_np_yp_wp_accessions(self):
        self.assertEqual(source_key(">YP_025292.1", "ecoli"), "YP_025292.1")
        self.assertEqual(
            source_key(">lcl|NC_000913.3_cds_WP_001234567.1_1 [gene=x]", "ecoli"),
            "WP_001234567.1",
        )
        self.assertEqual(source_key(">YAL001C", "yeast"), "YAL001C")

    def test_fasta_gzip_and_translation_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proteins.fasta.gz"
            with gzip.open(path, "wt") as handle:
                handle.write(">NP_1.1 description\nMK\n>NP_2.1\nMG*\n")
            self.assertEqual(read_fasta(path), {"NP_1.1": "MK", "NP_2.1": "MG"})

    def test_clean_gates_preserve_alternative_start_and_reject_duplicates(self):
        rows = [
            (">NP_valid.1", "ATG AAA TGA", "1 1 1"),
            (">NP_alt.1", "GTG AAA TGA", "1 0 1"),
            (">NP_dup.1", "ATG AAA TGA", "1 1 1"),
            (">NP_dup.1", "ATG GGG TGA", "1 1 1"),
            (">NP_stop.1", "ATG TAA AAA TGA", "1 1 1 1"),
            (">NP_low.1", "ATG AAA TGA", "0 0 0"),
            (">NP_mismatch.1", "ATG AAA", "1 1 1"),
        ]
        references = {
            "NP_valid.1": "MK", "NP_alt.1": "MK", "NP_dup.1": "MK",
            "NP_stop.1": "M*K", "NP_low.1": "MK", "NP_mismatch.1": "MK",
        }
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "Mohammad19-1.txt"
            raw.write_text("\n".join("\n".join(row) for row in rows) + "\n")
            records, summary = process_dataset("Mohammad19-1", raw, references)
        by_id = {record["record_id"]: record for record in records}
        self.assertTrue(by_id["Mohammad19-1:000000"]["clean_eligible"])
        self.assertTrue(by_id["Mohammad19-1:000001"]["clean_eligible"])
        self.assertEqual(by_id["Mohammad19-1:000001"]["translated_protein"], "MK")
        self.assertIn("duplicate_source_key", by_id["Mohammad19-1:000002"]["exclusion_reasons"])
        self.assertIn("duplicate_source_key", by_id["Mohammad19-1:000003"]["exclusion_reasons"])
        self.assertIn("internal_stop", by_id["Mohammad19-1:000004"]["exclusion_reasons"])
        self.assertIn("coverage_not_strictly_gt_0_6", by_id["Mohammad19-1:000005"]["exclusion_reasons"])
        self.assertIn("codon_count_length_mismatch", by_id["Mohammad19-1:000006"]["exclusion_reasons"])
        self.assertEqual(summary["records"], 7)
        self.assertEqual(summary["clean_records"], 2)
        self.assertEqual(summary["alternative_start_records"], 1)

    def test_replicate_qc_uses_only_nonduplicated_identical_cds_pairs(self):
        base = {
            "source_key": "NP_1.1", "cds_dna": "ATGAAATGA", "clean_eligible": True,
            "density_normalized": [0.0, 1.0, 2.0], "total_count": 3.0,
            "exclusion_reasons": [],
        }
        left = [dict(base)]
        right = [dict(base, density_normalized=[0.0, 2.0, 1.0], total_count=4.0)]
        result = replicate_qc({"Mohammad19-1": left, "Mohammad19-2": right})
        self.assertEqual(result["both_clean_pairs"], 1)
        self.assertEqual(result["both_clean_pairs_metrics"]["valid_profile_correlations"], 1)
        self.assertAlmostEqual(result["both_clean_pairs_metrics"]["profile_pearson"]["median"], 0.5)


if __name__ == "__main__":
    unittest.main()
