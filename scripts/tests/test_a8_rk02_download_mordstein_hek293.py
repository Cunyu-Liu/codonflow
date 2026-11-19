#!/usr/bin/env python3
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
MODULE_PATH = next(path for path in [HERE / "a8_rk02_download_mordstein_hek293.py", HERE.parent / "a8_rk02_download_mordstein_hek293.py"] if path.exists())
SPEC = importlib.util.spec_from_file_location("mordstein_download", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def job_for(path, payload=b"abcdef"):
    return {
        "run": "SRR10714593", "mate": 1, "url": "https://example.invalid/file",
        "md5": hashlib.md5(payload).hexdigest(), "bytes": len(payload), "path": path,
    }


class DownloadTests(unittest.TestCase):
    def test_select_jobs(self):
        jobs = [
            {"run": "SRR1", "mate": 1}, {"run": "SRR1", "mate": 2},
            {"run": "SRR2", "mate": 1}, {"run": "SRR2", "mate": 2},
        ]
        self.assertEqual(MODULE.select_jobs(jobs, ["SRR1_2", "SRR2"]), jobs[1:])
        self.assertEqual(MODULE.select_jobs(jobs, []), jobs)
        with self.assertRaises(ValueError):
            MODULE.select_jobs(jobs, ["UNKNOWN"])
        with self.assertRaises(ValueError):
            MODULE.select_jobs(jobs, ["SRR3_1"])

    def test_resume_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.fastq.gz"
            part = path.with_suffix(".gz.part")
            part.write_bytes(b"abc")
            calls = []
            def fake_run(command, check):
                calls.append(command)
                self.assertIn("--continue-at", command)
                self.assertNotIn("--retry-all-errors", command)  # curl 7.68 compatibility
                self.assertIn("--speed-time", command)
                with part.open("ab") as handle:
                    handle.write(b"def")
                return SimpleNamespace(returncode=0)
            with mock.patch.object(MODULE.subprocess, "run", side_effect=fake_run):
                record = MODULE.download(job_for(path), max_rounds=2, retry_delay=0)
            self.assertEqual(path.read_bytes(), b"abcdef")
            self.assertFalse(part.exists())
            self.assertEqual(record["status"], "downloaded_verified")
            self.assertEqual(len(calls), 1)

    def test_retry_after_partial_transfer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.fastq.gz"
            part = path.with_suffix(".gz.part")
            part.write_bytes(b"a")
            calls = []
            def fake_run(command, check):
                calls.append(len(calls))
                with part.open("ab") as handle:
                    handle.write(b"bc" if len(calls) == 1 else b"def")
                return SimpleNamespace(returncode=18 if len(calls) == 1 else 0)
            with mock.patch.object(MODULE.subprocess, "run", side_effect=fake_run), \
                 mock.patch.object(MODULE.time, "sleep", return_value=None) as sleep:
                MODULE.download(job_for(path), max_rounds=3, retry_delay=0)
            self.assertEqual(path.read_bytes(), b"abcdef")
            self.assertEqual(len(calls), 2)
            sleep.assert_called_once_with(0)

    def test_complete_partial_after_http_416(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.fastq.gz"
            part = path.with_suffix(".gz.part")
            part.write_bytes(b"abcdef")
            with mock.patch.object(MODULE.subprocess, "run", return_value=SimpleNamespace(returncode=22)):
                record = MODULE.download(job_for(path), max_rounds=2, retry_delay=0)
            self.assertEqual(path.read_bytes(), b"abcdef")
            self.assertEqual(record["bytes"], 6)

    def test_complete_partial_md5_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.fastq.gz"
            part = path.with_suffix(".gz.part")
            part.write_bytes(b"abcdef")
            with mock.patch.object(MODULE.subprocess, "run") as run:
                with self.assertRaisesRegex(RuntimeError, "MD5 mismatch"):
                    MODULE.download(job_for(path, b"ghijkl"), max_rounds=2, retry_delay=0)
            run.assert_not_called()
            self.assertFalse(path.exists())

    def test_existing_verified_skips_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.fastq.gz"
            path.write_bytes(b"abcdef")
            with mock.patch.object(MODULE.subprocess, "run") as run:
                record = MODULE.download(job_for(path), max_rounds=2, retry_delay=0)
            run.assert_not_called()
            self.assertEqual(record["status"], "existing_verified")


if __name__ == "__main__":
    unittest.main(verbosity=2)
