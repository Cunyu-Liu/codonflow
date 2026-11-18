#!/usr/bin/env python3
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

try:
    from scripts.a8_rk03_codontransformer_qc import qc_row, run_qc, QCError
    from scripts.a8_rk03_verify_codontransformer import verify
except ModuleNotFoundError:
    from a8_rk03_codontransformer_qc import qc_row, run_qc, QCError
    from a8_rk03_verify_codontransformer import verify

COLUMNS = ["dna", "protein", "organism", "GeneID", "description", "tokenized", "fine_tuned", "len"]


def make_row(dna="ATGCTGTAA", protein="ML_", organism="Arabidopsis thaliana",
             gene_id="831142.0", accession="NM_000001.1", tokens="M_ATG L_CTG __TAA",
             fine="True", length=None):
    return {"dna": dna, "protein": protein, "organism": organism, "GeneID": gene_id,
            "description": f"example {accession}:101-{100 + len(dna)} product",
            "tokenized": tokens, "fine_tuned": fine, "len": str(len(protein) if length is None else length)}


def build_dataset(tmp):
    raw = tmp / "dataset.csv"
    rows = [make_row(),
            make_row(organism="Escherichia coli", accession="NM_000002.1"),
            make_row(dna="ATGAAATAG", protein="MK_", accession="NM_000003.1",
                     tokens="M_ATG K_AAG __TAG", fine="False")]
    with raw.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS); writer.writeheader(); writer.writerows(rows)
    config = tmp / "config.json"
    config.write_text(json.dumps({"sources": [{"source_id": "codontransformer_training",
        "record": "https://zenodo.org/records/12509224", "mirror_dataset": "adibvafa/CodonTransformer",
        "mirror_commit": "29e564325d09a650b59f061a4e69a13d8e3ea1e4", "license": "CC-BY-NC-4.0",
        "files": [{"filename": "dataset.csv", "expected_bytes": raw.stat().st_size,
                   "expected_sha256": hashlib.sha256(raw.read_bytes()).hexdigest()}]}]}), encoding="utf-8")
    out = tmp / "qc"
    summary = run_qc(config, raw, out)
    return config, raw, out, summary


class CodonTransformerQCTests(unittest.TestCase):
    def test_valid_row_reconstructs_translation_tokens_and_coordinates(self):
        record = qc_row(make_row())
        self.assertTrue(record["valid"], record["reasons"])
        self.assertEqual(record["translated"], "ML_")
        self.assertTrue(record["terminal_stop"])
        self.assertTrue(record["coordinate_match"])
        self.assertEqual(record["accession"], "NM_000001.1")

    def test_row_level_exclusion_reasons_are_explicit(self):
        record = qc_row(make_row(dna="ATGTGATAA", protein="M_", tokens="M_ATG __TGA __TAA"))
        for reason in ("internal_stop", "translation_protein_mismatch"):
            self.assertIn(reason, record["reasons"])
        internal_protein = qc_row(make_row(dna="ATGTGATAA", protein="M__", tokens="M_ATG __TGA __TAA"))
        self.assertIn("internal_protein_stop_symbol", internal_protein["reasons"])
        bad_coordinate = make_row(); bad_coordinate["description"] = "NM_000001.1:101-999"
        self.assertIn("accession_coordinate_length_mismatch", qc_row(bad_coordinate)["reasons"])
        self.assertIn("invalid_gene_id", qc_row(make_row(gene_id="not-a-gene"))["reasons"])
        self.assertIn("protein_length_field_mismatch", qc_row(make_row(length=99))["reasons"])
        self.assertIn("invalid_fine_tuned", qc_row(make_row(fine="yes"))["reasons"])

    def test_streaming_qc_counts_duplicates_without_dropping_valid_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, out, summary = build_dataset(Path(directory))
            self.assertEqual(summary["raw_rows"], 3)
            self.assertEqual(summary["clean_rows"], 2)
            self.assertEqual(summary["raw_organism_count"], 2)
            self.assertEqual(summary["duplicate_dna_rows_after_first"], 1)
            self.assertEqual(summary["cross_organism_duplicate_dna_rows_after_first"], 1)
            self.assertEqual(summary["exclusion_reason_counts"], {"tokenized_sequence_mismatch": 1})
            self.assertFalse(summary["publisher_scope_matches_independent_count"])
            self.assertFalse(summary["natural_distribution_eligible"])

    def test_independent_verifier_closed_loop_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory); config, raw, out, _ = build_dataset(tmp)
            report = verify(config, raw, out, tmp / "verify.json")
            self.assertEqual(report["status"], "PASS", report["checks"])
            self.assertEqual(report["check_count"], 8)
            self.assertEqual(report["passed_checks"], 8)
            self.assertEqual(report["recomputed"]["clean_rows"], 2)
            self.assertEqual(report["max_numeric_delta"], 0)

    def test_clean_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory); config, raw, out, _ = build_dataset(tmp)
            clean = out / "codontransformer_clean.csv.gz"
            with gzip.open(clean, "rt", encoding="utf-8") as handle: lines = handle.readlines()
            part = out / "clean.tampered.part"
            with gzip.open(part, "wt", encoding="utf-8") as handle: handle.writelines(lines[:-1])
            os.replace(part, clean)
            report = verify(config, raw, out, tmp / "verify.json")
            self.assertEqual(report["status"], "FAIL")
            failed = {check["name"] for check in report["checks"] if not check["pass"]}
            self.assertIn("clean_artifact_exact_set", failed)
            self.assertIn("artifact_manifest_sha256", failed)

    def test_raw_hash_gate_and_post_qc_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory); config, raw, out, _ = build_dataset(tmp)
            with raw.open("a", encoding="utf-8") as handle: handle.write("\n")
            report = verify(config, raw, out, tmp / "verify.json")
            self.assertEqual(report["status"], "FAIL")
            self.assertFalse(next(check for check in report["checks"] if check["name"] == "raw_hash_header_translation")["pass"])
            with self.assertRaises(QCError):
                run_qc(config, raw, tmp / "new-qc")


if __name__ == "__main__":
    unittest.main()
