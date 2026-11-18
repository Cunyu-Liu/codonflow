#!/usr/bin/env python3
import hashlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts.a8_rk03_download import (
    download_config,
    download_verified,
    verify_integrity,
)
from scripts.a8_rk_functional_data import DataValidationError


class RangeHandler(BaseHTTPRequestHandler):
    payload = b"Protein_ID,CDS_Sequence\nP1,ATGAAATAG\n" * 100
    ranges = []
    ignore_range = False
    range_total_override = None
    response_limit = None

    def do_GET(self):
        type(self).ranges.append(self.headers.get("Range"))
        offset = 0
        status = 200
        body = self.payload
        range_header = self.headers.get("Range")
        if range_header and not self.ignore_range:
            offset = int(range_header.removeprefix("bytes=").split("-", 1)[0])
            body = self.payload[offset:]
            status = 206
            self.send_response(status)
            self.send_header(
                "Content-Range", f"bytes {offset}-{len(self.payload)-1}/{type(self).range_total_override or len(self.payload)}"
            )
        else:
            self.send_response(status)
        if type(self).response_limit is not None:
            body = body[:type(self).response_limit]
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "text/csv")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), RangeHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/data.csv"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        RangeHandler.ranges = []
        RangeHandler.ignore_range = False
        RangeHandler.range_total_override = None
        RangeHandler.response_limit = None
        self.spec = {
            "media_type": "text/csv",
            "expected_bytes": len(RangeHandler.payload),
            "expected_sha256": hashlib.sha256(RangeHandler.payload).hexdigest(),
        }

    def test_resume_verify_and_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "data.csv"
            part = destination.with_name("data.csv.part")
            part.write_bytes(RangeHandler.payload[:100])
            result = download_verified(self.url, destination, self.spec, retries=1)
            self.assertEqual(result["status"], "downloaded_verified")
            self.assertEqual(result["resumed_from_bytes"], 100)
            self.assertEqual(destination.read_bytes(), RangeHandler.payload)
            self.assertEqual(RangeHandler.ranges, ["bytes=100-"])
            reused = download_verified(self.url, destination, self.spec, retries=1)
            self.assertEqual(reused["status"], "reused_verified")
            self.assertEqual(RangeHandler.ranges, ["bytes=100-"])

    def test_range_ignored_restarts_instead_of_corrupting(self):
        RangeHandler.ignore_range = True
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "data.csv"
            destination.with_name("data.csv.part").write_bytes(RangeHandler.payload[:100])
            result = download_verified(self.url, destination, self.spec, retries=1)
            self.assertEqual(result["resumed_from_bytes"], 0)
            self.assertEqual(destination.read_bytes(), RangeHandler.payload)

    def test_hash_mismatch_never_promotes_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "data.csv"
            bad_spec = dict(self.spec, expected_sha256="0" * 64)
            with self.assertRaisesRegex(DataValidationError, "sha256 mismatch"):
                download_verified(self.url, destination, bad_spec, retries=1)
            self.assertFalse(destination.exists())
            part = destination.with_name("data.csv.part")
            self.assertFalse(part.exists())
            rejected = list(Path(tmp).glob("data.csv.part.rejected-*"))
            self.assertEqual(len(rejected), 1)
            self.assertEqual(rejected[0].read_bytes(), RangeHandler.payload)

    def test_existing_bad_final_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "data.csv"
            destination.write_bytes(b"do-not-overwrite")
            with self.assertRaises(DataValidationError):
                download_verified(self.url, destination, self.spec, retries=1)
            self.assertEqual(destination.read_bytes(), b"do-not-overwrite")

    def test_complete_verified_part_promotes_without_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "data.csv"
            part = destination.with_name("data.csv.part")
            part.write_bytes(RangeHandler.payload)
            result = download_verified(self.url, destination, self.spec, retries=3)
            self.assertEqual(result["status"], "promoted_verified_part")
            self.assertEqual(result["attempts"], 0)
            self.assertEqual(destination.read_bytes(), RangeHandler.payload)
            self.assertEqual(RangeHandler.ranges, [])

    def test_complete_bad_part_is_quarantined_and_redownloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "data.csv"
            part = destination.with_name("data.csv.part")
            part.write_bytes(b"X" * len(RangeHandler.payload))
            result = download_verified(self.url, destination, self.spec, retries=3)
            self.assertEqual(result["status"], "downloaded_verified")
            self.assertEqual(destination.read_bytes(), RangeHandler.payload)
            self.assertEqual(len(result["quarantined_parts"]), 1)
            rejected = Path(result["quarantined_parts"][0]["path"])
            self.assertEqual(rejected.stat().st_size, len(RangeHandler.payload))
            self.assertFalse(part.exists())
            self.assertEqual(RangeHandler.ranges, [None])

    def test_content_range_total_mismatch_is_rejected_before_append(self):
        RangeHandler.range_total_override = len(RangeHandler.payload) + 1
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "data.csv"
            part = destination.with_name("data.csv.part")
            part.write_bytes(RangeHandler.payload[:100])
            with self.assertRaisesRegex(DataValidationError, "Content-Range total mismatch"):
                download_verified(self.url, destination, self.spec, retries=1)
            self.assertEqual(part.read_bytes(), RangeHandler.payload[:100])

    def test_short_range_response_reports_incomplete_without_expected_bytes(self):
        RangeHandler.response_limit = 25
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "data.csv"
            part = destination.with_name("data.csv.part")
            part.write_bytes(RangeHandler.payload[:100])
            spec = {"media_type": "text/csv"}
            with self.assertRaisesRegex(DataValidationError, "incomplete payload"):
                download_verified(self.url, destination, spec, retries=1)
            self.assertEqual(part.stat().st_size, 125)

    def test_html_is_not_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("<html>challenge</html>", encoding="utf-8")
            with self.assertRaisesRegex(DataValidationError, "HTML"):
                verify_integrity(path, {"media_type": "text/csv"})

    def test_config_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "sources.json"
            config.write_text(json.dumps({"sources": [{
                "source_id": "toy",
                "evidence_class": "synthetic_test_only",
                "files": [
                    dict(self.spec, file_id="toy_csv", filename="toy.csv", download_url=self.url),
                    dict(self.spec, file_id="toy_csv_2", filename="toy2.csv", download_url=self.url),
                ],
            }]}), encoding="utf-8")
            manifest = download_config(config, root / "data", retries=1, workers=2)
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["workers"], 2)
            self.assertEqual(len(manifest["records"]), 2)
            self.assertEqual(manifest["records"][0]["bytes"], len(RangeHandler.payload))
            self.assertTrue((root / "data/raw/toy/toy.csv").is_file())
            self.assertTrue((root / "data/raw/toy/toy2.csv").is_file())


if __name__ == "__main__":
    unittest.main()
