#!/usr/bin/env python3
import csv
import gzip
import json
from pathlib import Path
import tempfile
import unittest

try:
    from scripts.a8_rk03_rnarl_qc import (
        QCError, digest_file, qc_row, run_qc, structure_is_balanced, translate_dna,
    )
except ModuleNotFoundError:
    from a8_rk03_rnarl_qc import (
        QCError, digest_file, qc_row, run_qc, structure_is_balanced, translate_dna,
    )

BASE_COLUMNS = [
    "Protein_ID", "Protein_Sequence", "Protein_Length", "CDS_Sequence",
    "CDS_Length", "CDS_Structure", "CDS_MFE", "CDS_CAI",
]


def make_row(pid="p1", protein="ML*", cds="AUGCUGUAA", mfe="-2.5", cai="0.8",
             structure=None, lambda_value=None):
    row = {
        "Protein_ID": pid, "Protein_Sequence": protein, "Protein_Length": str(len(protein)),
        "CDS_Sequence": cds, "CDS_Length": str(len(cds)),
        "CDS_Structure": structure if structure is not None else "." * len(cds),
        "CDS_MFE": mfe, "CDS_CAI": cai,
    }
    if lambda_value is not None:
        row["Lambda"] = str(lambda_value)
    return row


def write_csv(path, rows, include_lambda=False):
    columns = BASE_COLUMNS + (["Lambda"] if include_lambda else [])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def make_config(tmp, raw, filenames):
    files = []
    for name in filenames:
        path = raw / name
        files.append({
            "filename": name, "url": "https://example.invalid/" + name,
            "bytes": path.stat().st_size, "md5": digest_file(path, "md5"),
            "expected_md5": digest_file(path, "md5"),
        })
    config = {"sources": [{
        "source_id": "rnarl_v1", "record": "https://zenodo.org/records/15486992",
        "license": "CC-BY-4.0", "repository_commit": "test-commit", "files": files,
    }]}
    path = tmp / "sources.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def valid_pair(pid="p1", protein="ML*", left="AUGCUGUAA", right="AUGCUUUAA"):
    return [make_row(pid, protein, left), make_row(pid, protein, right)]


class RNARLQCTests(unittest.TestCase):
    def test_standard_translation_and_structure(self):
        self.assertEqual(translate_dna("ATGCTGTAA"), "ML*")
        self.assertTrue(structure_is_balanced("(.[...])"))
        self.assertFalse(structure_is_balanced("((...)"))
        self.assertFalse(structure_is_balanced("(...&...)"))

    def test_base_qc_accepts_valid_synonymous_row(self):
        record = qc_row(make_row(), "Toy_train.csv", "Toy", "train", 1, None)
        self.assertTrue(record["base_qc_pass"], record["base_exclusion_reasons"])
        self.assertEqual(record["translated_protein"], "ML")
        self.assertTrue(record["terminal_stop"])
        self.assertEqual(record["source_cds_rna"], "AUGCUGUAA")
        self.assertEqual(record["cds_dna"], "ATGCTGTAA")
        self.assertEqual(record["protein_length"], 2)
        self.assertEqual(record["reported_protein_length"], 3)

    def test_internal_stop_and_translation_mismatch_are_retained(self):
        record = qc_row(make_row(cds="AUGUGAUAA"), "Toy_train.csv", "Toy", "train", 1, None)
        self.assertIn("internal_stop", record["base_exclusion_reasons"])
        self.assertIn("translation_protein_mismatch", record["base_exclusion_reasons"])
        self.assertFalse(record["base_qc_pass"])

    def test_length_and_structure_failures_are_explicit(self):
        raw = make_row(structure="(((...")
        record = qc_row(raw, "Toy_train.csv", "Toy", "train", 1, None)
        self.assertIn("structure_length_mismatch", record["base_exclusion_reasons"])
        self.assertIn("structure_unbalanced_or_unsupported", record["base_exclusion_reasons"])
        raw = make_row()
        raw["CDS_Length"] = "8"
        record = qc_row(raw, "Toy_train.csv", "Toy", "train", 1, None)
        self.assertIn("cds_length_mismatch", record["base_exclusion_reasons"])

    def test_valid_two_file_run_preserves_official_split_and_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            raw = tmp / "raw"; raw.mkdir()
            write_csv(raw / "Toy_train.csv", valid_pair())
            write_csv(raw / "Toy_val.csv", valid_pair("p2", "MK*", "AUGAAAUAG", "AUGAAGUAA"))
            config = make_config(tmp, raw, ["Toy_train.csv", "Toy_val.csv"])
            summary = run_qc(config, raw, tmp / "out", tmp / "audit.json")
            self.assertEqual(summary["status"], "COMPLETE_QC_PENDING_INDEPENDENT_VERIFICATION")
            self.assertEqual(summary["clean_rows"], 4)
            self.assertEqual(summary["clean_pairs"], 2)
            self.assertTrue(summary["long_format_two_distinct_cds_pattern_observed"])
            self.assertFalse(summary["lambda_label_recoverable"])
            self.assertFalse(summary["natural_distribution_eligible"])
            self.assertFalse(summary["functional_ood_claim_authorized"])
            self.assertTrue((tmp / "audit.json").is_file())
            with gzip.open(tmp / "out" / "rnarl_clean.jsonl.gz", "rt") as handle:
                clean = [json.loads(line) for line in handle]
            self.assertEqual({row["split"] for row in clean}, {"train", "val"})
            self.assertTrue(all(row["clean_eligible"] for row in clean))

    def test_identical_pair_is_not_two_distinct_designs(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory); raw = tmp / "raw"; raw.mkdir()
            write_csv(raw / "Toy_train.csv", [make_row(), make_row()])
            config = make_config(tmp, raw, ["Toy_train.csv"])
            summary = run_qc(config, raw, tmp / "out")
            self.assertEqual(summary["clean_rows"], 0)
            self.assertFalse(summary["long_format_two_distinct_cds_pattern_observed"])

    def test_cross_split_identity_and_cds_overlap_excludes_clean_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory); raw = tmp / "raw"; raw.mkdir()
            rows = valid_pair()
            write_csv(raw / "Toy_train.csv", rows)
            write_csv(raw / "Toy_test.csv", rows)
            config = make_config(tmp, raw, ["Toy_train.csv", "Toy_test.csv"])
            summary = run_qc(config, raw, tmp / "out")
            self.assertEqual(summary["clean_rows"], 0)
            self.assertEqual(summary["split_overlaps"]["protein_id"]["overlapping_keys"], 1)
            self.assertEqual(summary["split_overlaps"]["protein_sequence"]["overlapping_keys"], 1)
            self.assertEqual(summary["split_overlaps"]["exact_cds"]["overlapping_keys"], 2)
            self.assertFalse(summary["bounded_lineardesign_pair_table_ready_pending_verifier"])

    def test_one_member_cds_overlap_excludes_the_whole_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory); raw = tmp / "raw"; raw.mkdir()
            write_csv(raw / "Toy_train.csv", valid_pair("p1"))
            write_csv(raw / "Other_test.csv", valid_pair("p2", left="AUGCUGUAA", right="AUGUUGUAA"))
            config = make_config(tmp, raw, ["Toy_train.csv", "Other_test.csv"])
            summary = run_qc(config, raw, tmp / "out")
            self.assertEqual(summary["clean_rows"], 0)
            self.assertEqual(summary["split_overlaps"]["exact_cds"]["overlapping_keys"], 1)
            self.assertEqual(summary["split_overlaps"]["protein_sequence"]["overlapping_keys"], 0)
            with gzip.open(tmp / "out" / "rnarl_all_qc.jsonl.gz", "rt") as handle:
                rows = [json.loads(line) for line in handle]
            self.assertTrue(all(row["pair_cross_split_overlap"] for row in rows))
            self.assertEqual(sum("pair_member_cross_split_overlap" in row["exclusion_reasons"] for row in rows), 2)

    def test_explicit_lambda_column_is_required_for_lambda_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory); raw = tmp / "raw"; raw.mkdir()
            rows = [make_row(lambda_value=0), make_row(cds="AUGCUUUAA", lambda_value=1)]
            write_csv(raw / "Toy_train.csv", rows, include_lambda=True)
            config = make_config(tmp, raw, ["Toy_train.csv"])
            summary = run_qc(config, raw, tmp / "out")
            self.assertTrue(summary["lambda_label_recoverable"])
            self.assertFalse(summary["row_order_or_mfe_lambda_assignment_allowed"])
            self.assertFalse(summary["lambda_stratified_analysis_ready"])

    def test_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory); raw = tmp / "raw"; raw.mkdir()
            write_csv(raw / "Toy_train.csv", valid_pair())
            config = make_config(tmp, raw, ["Toy_train.csv"])
            value = json.loads(config.read_text())
            value["sources"][0]["files"][0]["expected_md5"] = "0" * 32
            config.write_text(json.dumps(value))
            with self.assertRaises(QCError):
                run_qc(config, raw, tmp / "out")

    def test_partial_smoke_is_never_bounded_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory); raw = tmp / "raw"; raw.mkdir()
            write_csv(raw / "Toy_train.csv", valid_pair())
            config = make_config(tmp, raw, ["Toy_train.csv"])
            value = json.loads(config.read_text())
            missing = dict(value["sources"][0]["files"][0])
            missing["filename"] = "Toy_test.csv"
            value["sources"][0]["files"].append(missing)
            config.write_text(json.dumps(value))
            summary = run_qc(config, raw, tmp / "out", allow_partial=True)
            self.assertEqual(summary["status"], "PARTIAL_SMOKE_ONLY")
            self.assertEqual(summary["processed_file_count"], 1)
            self.assertFalse(summary["bounded_lineardesign_pair_table_ready_pending_verifier"])

    def test_nonempty_output_directory_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory); raw = tmp / "raw"; raw.mkdir()
            write_csv(raw / "Toy_train.csv", valid_pair())
            config = make_config(tmp, raw, ["Toy_train.csv"])
            out = tmp / "out"; out.mkdir(); (out / "keep.txt").write_text("keep")
            with self.assertRaises(QCError):
                run_qc(config, raw, out)
            self.assertEqual((out / "keep.txt").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
