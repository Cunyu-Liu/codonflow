#!/usr/bin/env python3
"""Download and verify the eight public HEK293 Mordstein Flow-seq bins."""
import argparse
import concurrent.futures
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time

TITLE = "Illumina MiSeq sequencing: Flow-Seq of GFP library without intron in HEK293 cells"
RUN_RE = re.compile(r"^SRR\d+$")


def digest(path, algorithm):
    value = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def read_jobs(metadata, root):
    jobs = []
    with metadata.open(newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["experiment_title"] != TITLE:
                continue
            run = row["run_accession"]
            if not RUN_RE.fullmatch(run):
                raise ValueError(f"Unexpected run accession: {run}")
            urls = row["fastq_ftp"].split(";")
            md5s = row["fastq_md5"].split(";")
            sizes = row["fastq_bytes"].split(";")
            if not (len(urls) == len(md5s) == len(sizes) == 2):
                raise ValueError(f"Expected two mates for {run}")
            for mate, (url, md5, size) in enumerate(zip(urls, md5s, sizes), 1):
                jobs.append({
                    "run": run,
                    "mate": mate,
                    "url": "https://" + url,
                    "md5": md5,
                    "bytes": int(size),
                    "path": root / run / f"{run}_{mate}.fastq.gz",
                })
    if len(jobs) != 16 or len({job["run"] for job in jobs}) != 8:
        raise ValueError(f"Expected eight runs / sixteen mates, found {len(jobs)} jobs")
    # R1 alone identifies the randomized 5' haplotype; prioritize all R1 files
    # so that reference recovery and count QC can start before R2 completes.
    return sorted(jobs, key=lambda job: (job["mate"], job["run"]))


def select_jobs(jobs, only):
    """Select run or run_mate tokens without changing the canonical job order."""
    tokens = set(only or [])
    if not tokens:
        return jobs
    selected = [job for job in jobs if job["run"] in tokens or f"{job['run']}_{job['mate']}" in tokens]
    if not selected:
        raise ValueError("The --only filter selected no jobs")
    known = {job["run"] for job in jobs} | {f"{job['run']}_{job['mate']}" for job in jobs}
    unknown = tokens - known
    if unknown:
        raise ValueError(f"Unknown --only tokens: {sorted(unknown)}")
    return selected


def download(job, max_rounds=100, retry_delay=5):
    path = job["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.stat().st_size == job["bytes"] and digest(path, "md5") == job["md5"]:
            status = "existing_verified"
        else:
            raise RuntimeError(f"Existing file fails size/MD5 verification: {path}")
    else:
        part = path.with_suffix(path.suffix + ".part")
        status = "downloaded_verified"
        last_error = "download did not start"
        for attempt in range(1, max_rounds + 1):
            if part.exists():
                partial_bytes = part.stat().st_size
                if partial_bytes > job["bytes"]:
                    raise RuntimeError(f"Partial file exceeds expected size: {part}")
                if partial_bytes == job["bytes"]:
                    if digest(part, "md5") != job["md5"]:
                        raise RuntimeError(f"MD5 mismatch for complete partial file {part}")
                    part.replace(path)
                    break
            command = [
                "curl", "-L", "--fail", "--silent", "--show-error",
                "--retry", "2", "--retry-delay", "5",
                "--connect-timeout", "30", "--speed-limit", "1024", "--speed-time", "60",
                "--continue-at", "-", "--output", str(part), job["url"],
            ]
            completed = subprocess.run(command, check=False)
            partial_bytes = part.stat().st_size if part.exists() else 0
            if completed.returncode == 0 and partial_bytes == job["bytes"]:
                continue
            last_error = f"curl exit={completed.returncode}; partial={partial_bytes}/{job['bytes']}"
            print(json.dumps({
                "status": "resume_retry", "run": job["run"], "mate": job["mate"],
                "attempt": attempt, "max_rounds": max_rounds, "error": last_error,
            }, sort_keys=True), flush=True)
            if attempt < max_rounds:
                time.sleep(min(retry_delay * attempt, 30))
        else:
            raise RuntimeError(f"Exhausted {max_rounds} resume rounds for {part}: {last_error}")
    return {
        "run": job["run"], "mate": job["mate"], "url": job["url"], "path": str(path),
        "bytes": path.stat().st_size, "md5": job["md5"], "sha256": digest(path, "sha256"),
        "status": status,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--only", nargs="*", default=[], help="Optional run or run_mate tokens")
    parser.add_argument("--max-rounds", type=int, default=100)
    args = parser.parse_args()
    jobs = select_jobs(read_jobs(args.metadata, args.root), args.only)
    records = []
    failures = []
    lock = threading.Lock()
    def guarded(job):
        try:
            record = download(job, max_rounds=args.max_rounds)
            with lock:
                records.append(record)
                print(json.dumps(record, sort_keys=True), flush=True)
        except Exception as exc:
            with lock:
                failure = {"run": job["run"], "mate": job["mate"], "path": str(job["path"]), "error": str(exc)}
                failures.append(failure)
                print(json.dumps(failure, sort_keys=True), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(guarded, jobs))
    report = {
        "schema": "a8.rk02.mordstein_hek293_download.v1",
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_metadata": str(args.metadata), "output_root": str(args.root),
        "requested_only": args.only, "max_rounds": args.max_rounds,
        "expected_runs": len({job["run"] for job in jobs}), "expected_files": len(jobs),
        "passed_files": len(records), "failures": failures,
        "status": "PASS" if not failures and len(records) == len(jobs) else "FAIL",
        "files": sorted(records, key=lambda row: (row["run"], row["mate"])),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "passed_files": len(records), "failures": len(failures)}), flush=True)
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
