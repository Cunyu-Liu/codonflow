#!/usr/bin/env python3
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("a8_rk02_finalize_mordstein_downloads.py")
if not SCRIPT.exists():
    SCRIPT = Path(__file__).resolve().parents[1] / SCRIPT.name
TITLE = "Illumina MiSeq sequencing: Flow-Seq of GFP library without intron in HEK293 cells"
RUNS = [f"SRR107145{index}" for index in (93, 92, 57, 46, 83, 72, 37, 26)]


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


class DownloadFinalizerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.raw = self.root / "raw"
        self.metadata = self.root / "metadata.tsv"
        rows = []
        self.contents = {}
        for run in RUNS:
            md5s, sizes = [], []
            for mate in (1, 2):
                content = f"{run}:{mate}:verified-content\n".encode()
                self.contents[(run, mate)] = content
                path = self.raw / run / f"{run}_{mate}.fastq.gz"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                md5s.append(hashlib.md5(content).hexdigest())
                sizes.append(str(len(content)))
            rows.append({
                "experiment_title": TITLE,
                "run_accession": run,
                "fastq_md5": ";".join(md5s),
                "fastq_bytes": ";".join(sizes),
            })
        with self.metadata.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
        self.original = self.root / "original.json"
        self.resume = self.root / "resume.json"
        write_json(self.original, {"status": "FAIL", "passed_files": 3, "failures": [{"run": "retained"}]})
        write_json(self.resume, {"status": "PASS", "passed_files": 13, "failures": []})

    def tearDown(self):
        self.temporary.cleanup()

    def run_finalizer(self, name):
        report = self.root / name
        result = subprocess.run([
            sys.executable, str(SCRIPT), "--metadata", str(self.metadata),
            "--root", str(self.raw), "--original-report", str(self.original),
            "--resume-report", str(self.resume), "--report", str(report),
        ], capture_output=True, text=True)
        return result, report

    def test_complementary_worker_failures_do_not_hide_verified_files(self):
        result, report_path = self.run_finalizer("final.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(report_path.read_text())
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["passed_files"], 16)
        self.assertTrue(report["observed_end_recovery_authorized"])
        self.assertEqual(report["source_reports"][0]["status"], "FAIL")
        self.assertEqual(report["source_reports"][0]["failure_count"], 1)
        self.assertFalse(report["complete_cds_recovered"])
        self.assertEqual(len({row["sha256"] for row in report["files"]}), 16)

    def test_same_size_md5_corruption_is_rejected(self):
        run, mate = RUNS[0], 1
        path = self.raw / run / f"{run}_{mate}.fastq.gz"
        original = self.contents[(run, mate)]
        path.write_bytes(b"X" + original[1:])
        result, report_path = self.run_finalizer("corrupt.json")
        self.assertEqual(result.returncode, 1)
        report = json.loads(report_path.read_text())
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["passed_files"], 15)
        bad = next(row for row in report["files"] if row["run"] == run and row["mate"] == mate)
        self.assertTrue(bad["size_ok"])
        self.assertFalse(bad["md5_ok"])
        self.assertFalse(report["observed_end_recovery_authorized"])

    def test_missing_formal_file_is_not_accepted_from_worker_report(self):
        run, mate = RUNS[-1], 2
        (self.raw / run / f"{run}_{mate}.fastq.gz").unlink()
        result, report_path = self.run_finalizer("missing.json")
        self.assertEqual(result.returncode, 1)
        report = json.loads(report_path.read_text())
        self.assertEqual(report["failed_files"], 1)
        bad = next(row for row in report["files"] if row["run"] == run and row["mate"] == mate)
        self.assertEqual(bad["status"], "MISSING")

    def test_refuses_to_overwrite_existing_report(self):
        result, report_path = self.run_finalizer("frozen.json")
        self.assertEqual(result.returncode, 0)
        before = report_path.read_bytes()
        result2, _ = self.run_finalizer("frozen.json")
        self.assertNotEqual(result2.returncode, 0)
        self.assertEqual(report_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
