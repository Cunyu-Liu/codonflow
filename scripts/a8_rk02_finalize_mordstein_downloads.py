#!/usr/bin/env python3
"""Independently accept all 16 Mordstein HEK293 FASTQ files after resume.

The original and resume workers may have complementary successes and retained
failures. Acceptance therefore depends on fresh per-file size and MD5 checks
against ENA metadata, not on either worker's aggregate status. SHA256 freezes
the exact inputs for observed-end recovery. No CDS or scientific-library claim
is made by this download gate.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path

TITLE = "Illumina MiSeq sequencing: Flow-Seq of GFP library without intron in HEK293 cells"


def digests(path: Path) -> tuple[str, str]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            md5.update(block)
            sha256.update(block)
    return md5.hexdigest(), sha256.hexdigest()


def expected_jobs(metadata: Path, root: Path) -> list[dict]:
    jobs = []
    with metadata.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["experiment_title"] != TITLE:
                continue
            run = row["run_accession"]
            md5s = row["fastq_md5"].split(";")
            sizes = row["fastq_bytes"].split(";")
            if len(md5s) != 2 or len(sizes) != 2:
                raise ValueError(f"Expected two mates for {run}")
            for mate, (md5, size) in enumerate(zip(md5s, sizes), 1):
                jobs.append({
                    "run": run,
                    "mate": mate,
                    "path": root / run / f"{run}_{mate}.fastq.gz",
                    "expected_bytes": int(size),
                    "expected_md5": md5,
                })
    if len(jobs) != 16 or len({job["run"] for job in jobs}) != 8:
        raise ValueError(f"Expected eight runs / sixteen mates, found {len(jobs)} jobs")
    return sorted(jobs, key=lambda job: (job["run"], job["mate"]))


def report_provenance(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "status": data.get("status"),
        "passed_files": data.get("passed_files"),
        "failure_count": len(data.get("failures", [])),
        "failures_retained": data.get("failures", []),
    }


def atomic_json(path: Path, value: dict) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--original-report", type=Path, required=True)
    parser.add_argument("--resume-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    jobs = expected_jobs(args.metadata, args.root)
    records = []
    for job in jobs:
        path = job["path"]
        record = {key: (str(value) if isinstance(value, Path) else value)
                  for key, value in job.items()}
        record["partial_path"] = str(path.with_suffix(path.suffix + ".part"))
        record["partial_exists"] = Path(record["partial_path"]).exists()
        if not path.exists():
            record.update({"status": "MISSING", "pass": False})
        else:
            actual_bytes = path.stat().st_size
            actual_md5, actual_sha256 = digests(path)
            size_ok = actual_bytes == job["expected_bytes"]
            md5_ok = actual_md5 == job["expected_md5"]
            record.update({
                "actual_bytes": actual_bytes,
                "actual_md5": actual_md5,
                "sha256": actual_sha256,
                "size_ok": size_ok,
                "md5_ok": md5_ok,
                "status": "PASS" if size_ok and md5_ok else "FAIL_SIZE_OR_MD5",
                "pass": size_ok and md5_ok,
            })
        records.append(record)

    sources = [report_provenance(path) for path in (args.original_report, args.resume_report)]
    passed = sum(record["pass"] for record in records)
    report = {
        "schema": "a8.rk02.mordstein_hek293_complete_download_finalization.v1",
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "PASS" if passed == 16 else "FAIL",
        "source_metadata": str(args.metadata),
        "output_root": str(args.root),
        "expected_runs": 8,
        "expected_files": 16,
        "passed_files": passed,
        "failed_files": 16 - passed,
        "acceptance_rule": "Fresh size and MD5 equality to ENA metadata for every formal FASTQ; worker aggregate status is provenance, not acceptance.",
        "source_reports": sources,
        "files": records,
        "all_formal_files_verified": passed == 16,
        "observed_end_recovery_authorized": passed == 16,
        "complete_cds_recovered": False,
        "complete_217_library_recovered": False,
        "scientific_model_result": False,
    }
    atomic_json(args.report, report)
    print(json.dumps({
        "status": report["status"],
        "passed_files": passed,
        "failed_files": 16 - passed,
        "report": str(args.report),
    }), flush=True)
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
