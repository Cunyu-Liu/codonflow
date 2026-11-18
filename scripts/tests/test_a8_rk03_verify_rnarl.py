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
    from scripts.a8_rk03_rnarl_qc import run_qc
    from scripts.a8_rk03_verify_rnarl import verify
except ModuleNotFoundError:
    from a8_rk03_rnarl_qc import run_qc
    from a8_rk03_verify_rnarl import verify

COLUMNS = ["Protein_ID", "Protein_Sequence", "Protein_Length", "CDS_Sequence", "CDS_Length", "CDS_Structure", "CDS_MFE", "CDS_CAI"]


def build_dataset(tmp):
    raw = tmp / "raw"; raw.mkdir()
    files = []
    index = 0
    for organism_index in range(1, 8):
        for split in ("train", "val", "test"):
            index += 1
            protein = "M" + "L" * index
            left = "ATG" + "CTG" * index + "TAA"
            right = "ATG" + "CTT" * index + "TAA"
            name = f"Org{organism_index}_{split}.csv"
            path = raw / name
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=COLUMNS); writer.writeheader()
                for cds in (left, right):
                    writer.writerow({"Protein_ID": f"p{index}", "Protein_Sequence": protein,
                                     "Protein_Length": len(protein), "CDS_Sequence": cds,
                                     "CDS_Length": len(cds), "CDS_Structure": "." * len(cds),
                                     "CDS_MFE": -index, "CDS_CAI": 0.8})
            files.append({"filename": name, "url": "https://example.invalid/" + name,
                          "bytes": path.stat().st_size,
                          "expected_md5": hashlib.md5(path.read_bytes()).hexdigest()})
    config = tmp / "config.json"
    config.write_text(json.dumps({"sources": [{"source_id": "rnarl_v1",
        "record": "https://zenodo.org/records/15486992", "license": "CC-BY-4.0",
        "repository_commit": "test", "files": files}]}), encoding="utf-8")
    out = tmp / "qc"
    summary = run_qc(config, raw, out)
    return config, raw, out, summary


class RNARLIndependentVerifierTests(unittest.TestCase):
    def test_twenty_one_file_closed_loop_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            config, raw, out, summary = build_dataset(tmp)
            self.assertEqual(summary["clean_rows"], 42)
            report = verify(config, raw, out, tmp / "verify.json")
            self.assertEqual(report["status"], "PASS", report["checks"])
            self.assertEqual(report["passed_checks"], report["check_count"])
            self.assertEqual(report["check_count"], 8)
            self.assertEqual(report["recomputed"]["clean_pairs"], 21)
            self.assertEqual(report["max_numeric_delta"], 0)

    def test_clean_row_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            config, raw, out, _ = build_dataset(tmp)
            clean = out / "rnarl_clean.jsonl.gz"
            with gzip.open(clean, "rt", encoding="utf-8") as handle:
                lines = handle.readlines()
            part = out / "clean.tampered.part"
            with gzip.open(part, "wt", encoding="utf-8") as handle:
                handle.writelines(lines[1:])
            os.replace(part, clean)
            report = verify(config, raw, out, tmp / "verify.json")
            self.assertEqual(report["status"], "FAIL")
            failed = {check["name"] for check in report["checks"] if not check["pass"]}
            self.assertIn("clean_artifact_exact_set", failed)
            self.assertIn("artifact_manifest_sha256", failed)

    def test_raw_post_qc_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            config, raw, out, _ = build_dataset(tmp)
            target = raw / "Org1_train.csv"
            with target.open("a", encoding="utf-8") as handle:
                handle.write("\n")
            report = verify(config, raw, out, tmp / "verify.json")
            self.assertEqual(report["status"], "FAIL")
            self.assertFalse(next(check for check in report["checks"] if check["name"] == "raw_hash_header_translation")["pass"])


if __name__ == "__main__":
    unittest.main()
