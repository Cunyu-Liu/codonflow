#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

MODULE_PATH = os.path.join(os.path.dirname(__file__), "a8_rk05_ixnos_official_smoke.py")
spec = importlib.util.spec_from_file_location("ixnos_smoke", MODULE_PATH)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class IxnosSmokeUnitTests(unittest.TestCase):
    def test_pinned_source_identity(self):
        self.assertEqual(smoke.SOURCE_COMMIT, "1ea2337dd24d1e6fa3859f08573e99f02512810f")
        self.assertEqual(smoke.SOURCE_SHA, "523e6105acdf52d792d96c272594655b2765a9c369892f78bac9452f7d20c1c8")
        self.assertIn("SRR1049521.fastq.gz", smoke.FASTQ_URL)

    def test_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x")
            with open(path, "wb") as handle:
                handle.write(b"abc")
            self.assertEqual(smoke.sha256(path), hashlib.sha256(b"abc").hexdigest())

    def test_fastq_qc_complete_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.fastq")
            with open(path, "w") as handle:
                handle.write("@r1\nACGT\n+\nFFFF\n@r2\nAAA\n+\nFFF\n")
            qc = smoke.fastq_qc(path)
            self.assertEqual(qc["records"], 2)
            self.assertEqual(qc["unique_read_names"], 2)
            self.assertEqual(qc["read_length_counts"], {"3": 1, "4": 1})

    def test_fastq_qc_duplicate_names_are_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.fastq")
            with open(path, "w") as handle:
                handle.write("@r1\nAC\n+\nFF\n@r1\nGT\n+\nFF\n")
            qc = smoke.fastq_qc(path)
            self.assertEqual(qc["records"], 2)
            self.assertEqual(qc["unique_read_names"], 1)

    def test_fastq_qc_rejects_truncated_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.fastq")
            with open(path, "w") as handle:
                handle.write("@r1\nACGT\n+\n")
            with self.assertRaises(ValueError):
                smoke.fastq_qc(path)

    def test_fastq_qc_rejects_sequence_quality_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.fastq")
            with open(path, "w") as handle:
                handle.write("@r1\nACGT\n+\nFFF\n")
            with self.assertRaises(ValueError):
                smoke.fastq_qc(path)

    def test_run_logged_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "ok.log")
            smoke.run_logged([sys.executable, "-c", "print('ok')"], log)
            with open(log) as handle:
                content = handle.read()
            self.assertIn("COMMAND", content)
            self.assertIn("ok", content)

    def test_run_logged_failure_preserves_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "fail.log")
            with self.assertRaises(RuntimeError):
                smoke.run_logged([sys.executable, "-c", "import sys; sys.stderr.write('bad'); sys.exit(3)"], log)
            with open(log) as handle:
                self.assertIn("bad", handle.read())

    def test_existing_run_directory_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            cmd = [sys.executable, MODULE_PATH, "--run-dir", tmp, "--source-root", tmp,
                   "--source-archive", tmp, "--py27-site-packages", tmp, "--driver", tmp]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("already exists", result.stderr)

    def test_source_archive_hash_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = os.path.join(tmp, "wrong.zip")
            with open(archive, "wb") as handle:
                handle.write(b"not the pinned archive")
            run_dir = os.path.join(tmp, "new-run")
            cmd = [sys.executable, MODULE_PATH, "--run-dir", run_dir, "--source-root", tmp,
                   "--source-archive", archive, "--py27-site-packages", tmp, "--driver", __file__]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SHA256 mismatch", result.stderr)
            self.assertFalse(os.path.exists(run_dir))


if __name__ == "__main__":
    unittest.main(verbosity=2)
