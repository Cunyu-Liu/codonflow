#!/usr/bin/env python3
import csv
import json
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts.a8_rk_functional_data import (
    DataValidationError,
    audit_boel_records,
    audit_mage_pairs,
    audit_mage_single,
    audit_mage_utr,
    download_file,
    download_priority_one,
    looks_like_html,
    read_csv_records,
    read_xlsx_sheets,
    register_browser_downloads,
    sha256_file,
    validate_payload,
    write_download_outputs,
)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ok.csv":
            payload = b"sequence,expression\nATG,1.25\n"
            content_type = "text/csv"
        elif self.path == "/challenge.csv":
            payload = b"<!doctype html><title>Preparing to download</title><p>challenge</p>"
            content_type = "text/html"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def make_xlsx(path: Path) -> None:
    files = {
        "[Content_Types].xml": "<Types/>",
        "xl/workbook.xml": """<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>""",
        "xl/_rels/workbook.xml.rels": """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/></Relationships>""",
        "xl/sharedStrings.xml": """<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>sequence</t></si><si><r><t>ATG</t></r><r><t>AAA</t></r></si></sst>""",
        "xl/worksheets/sheet1.xml": """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="inlineStr"><is><t>expression</t></is></c></row><row r="2"><c r="A2" t="s"><v>1</v></c><c r="C2"><v>2.5</v></c></row></sheetData></worksheet>""",
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


class FunctionalDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_html_detection(self):
        self.assertTrue(looks_like_html(b"  <!doctype html><html>"))
        self.assertTrue(looks_like_html(b"Preparing to download..."))
        self.assertFalse(looks_like_html(b"sequence,expression\nATG,2\n"))

    def test_download_and_hash(self):
        destination = self.root / "ok.csv"
        result = download_file(self.base + "/ok.csv", destination, "text/csv")
        self.assertEqual(result["status"], "downloaded")
        self.assertEqual(len(result["sha256"]), 64)
        self.assertEqual(sha256_file(destination), result["sha256"])
        reused = download_file(self.base + "/ok.csv", destination, "text/csv")
        self.assertEqual(reused["status"], "reused")

    def test_html_200_is_rejected_atomically(self):
        destination = self.root / "challenge.csv"
        with self.assertRaises(DataValidationError):
            download_file(self.base + "/challenge.csv", destination, "text/csv", retries=1)
        self.assertFalse(destination.exists())
        self.assertEqual(list(self.root.glob("*.part.*")), [])

    def test_xlsx_shared_inline_and_sparse_cells(self):
        path = self.root / "fixture.xlsx"
        make_xlsx(path)
        validate_payload(path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        rows = read_xlsx_sheets(path)["Data"]
        self.assertEqual(rows[0], ["sequence", "expression"])
        self.assertEqual(rows[1], ["ATGAAA", "", "2.5"])

    def test_csv_bom_and_blank_values(self):
        path = self.root / "bom.csv"
        path.write_bytes(b"\xef\xbb\xbfsequence,expression\r\nATG,\r\n")
        headers, records = read_csv_records(path)
        self.assertEqual(headers, ["sequence", "expression"])
        self.assertEqual(records, [{"sequence": "ATG", "expression": ""}])

    def test_manifest_records_failures(self):
        config = self.root / "sources.json"
        config.write_text(json.dumps({"sources": [{
            "source_id": "fixture", "priority": 1, "files": [
                {"file_id": "ok", "url": self.base + "/ok.csv", "media_type": "text/csv", "required": True},
                {"file_id": "bad", "url": self.base + "/challenge.csv", "media_type": "text/csv", "required": True},
            ]
        }]}))
        manifest = download_priority_one(config, self.root / "data")
        self.assertEqual(manifest["status"], "partial")
        self.assertEqual(len(manifest["records"]), 2)
        self.assertEqual(len(manifest["failures"]), 1)
        write_download_outputs(manifest, self.root / "audit")
        with (self.root / "audit" / "download_failures.csv").open(newline="") as handle:
            failures = list(csv.DictReader(handle))
        self.assertEqual(failures[0]["file_id"], "bad")
        self.assertIn("HTML/challenge", failures[0]["error"])

    def test_boel_translation_and_internal_stop_exclusion(self):
        valid = "ATGAAACTCGAG" + "CAC" * 6 + "TGA"
        records = [
            {"name": "ok", "E": "5", "seq": valid, "Gz48v": "-1"},
            {"name": "bad", "E": "0", "seq": "ATGAAATAATGA"},
        ]
        clean, exclusions, summary = audit_boel_records(records, "fixture.xlsx")
        self.assertEqual(len(clean), 1)
        self.assertEqual(clean[0]["protein_sequence"], "MKLEHHHHHH")
        self.assertEqual(summary["expression_distribution"], {"5": 1})
        self.assertEqual(exclusions[0]["reason"], "internal stop codon")

    def test_mage_single_long_format_and_wt(self):
        records = [
            {"pos": "1", "codon": "AAA", "aa": "K", "is_wt": "1", "fitness_min": "1", "fitness_rich": "1", "fitness_stdev_min": "0", "fitness_stdev_rich": "0"},
            {"pos": "1", "codon": "AAG", "aa": "K", "is_wt": "0", "fitness_min": "0.5", "fitness_rich": "0.6", "fitness_stdev_min": "0.1", "fitness_stdev_rich": "0.1"},
        ]
        clean, exclusions, summary = audit_mage_single(records, "s1.csv")
        self.assertEqual(len(clean), 4)
        self.assertFalse(exclusions)
        self.assertEqual(summary["single_codon_variants"], 1)
        self.assertEqual(summary["wild_type_controls"], 1)
        self.assertEqual(clean[2]["mutation_signature"], "1:AAA>AAG")

    def test_mage_pair_cross_window_signature_deduplication(self):
        records = [
            {"pos1": "1", "codon1": "AAA", "aa1": "K", "pos2": "2", "codon2": "AAA", "aa2": "K", "is_wt": "1", "fitness_rich": "1", "fitness_stdev_rich": "0"},
            {"pos1": "1", "codon1": "AAA", "aa1": "K", "pos2": "2", "codon2": "AAG", "aa2": "K", "is_wt": "0", "fitness_rich": "0.8", "fitness_stdev_rich": "0.1"},
            {"pos1": "2", "codon1": "AAA", "aa1": "K", "pos2": "3", "codon2": "AAA", "aa2": "K", "is_wt": "1", "fitness_rich": "1", "fitness_stdev_rich": "0"},
            {"pos1": "2", "codon1": "AAG", "aa1": "K", "pos2": "3", "codon2": "AAA", "aa2": "K", "is_wt": "0", "fitness_rich": "0.8", "fitness_stdev_rich": "0.1"},
        ]
        clean, exclusions, summary = audit_mage_pairs(records, "s2.csv")
        self.assertEqual(len(clean), 4)
        self.assertFalse(exclusions)
        self.assertEqual(summary["unique_nonwt_mutation_signatures"], 1)
        self.assertEqual(summary["cross_window_duplicate_signature_rows"], 1)

    def test_mage_utr_trims_tabs(self):
        records = [{"replica": "replica_A", "nt12": "\tAA", "nt34": "\tCC", "5prime_index": "\t1", "3prime_index": "\t1", "oligo_index": "\t1", "is_wt": "\t0", "num_mismatches": "\t2", "f": "\t1.0", "f_std": "\t0.1"}]
        clean, exclusions, summary = audit_mage_utr(records, "s3.csv")
        self.assertEqual(len(clean), 1)
        self.assertFalse(exclusions)
        self.assertIn(":AA:CC", clean[0]["construct_id"])

    def test_browser_registration_resolves_failure(self):
        data_root = self.root / "data"
        raw = data_root / "raw" / "fixture" / "data.csv"
        raw.parent.mkdir(parents=True)
        raw.write_text("codon,fitness\nAAA,1\n")
        manifest = {"records": [{"source_id": "fixture", "file_id": "data", "status": "failed", "error": "challenge", "relative_path": "raw/fixture/data.csv", "expected_media_type": "text/csv", "url": "https://example.invalid/data"}], "failures": [{"file_id": "data"}], "status": "partial"}
        audit = self.root / "audit"
        audit.mkdir()
        (audit / "download_manifest.json").write_text(json.dumps(manifest))
        resolved = register_browser_downloads(audit / "download_manifest.json", data_root, audit, [("fixture", "data", "test_browser")])
        self.assertEqual(resolved["records"][0]["status"], "browser_downloaded")
        self.assertEqual(resolved["failures"], [])
        self.assertEqual(len(resolved["resolved_failures"]), 1)


if __name__ == "__main__":
    unittest.main()
