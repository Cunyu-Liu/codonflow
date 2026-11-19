#!/usr/bin/env python3
"""Resume Mordstein FASTQ files with verified parallel HTTP byte ranges.

Existing .part bytes are retained as a prefix in a separate staging file. No
formal FASTQ is created unless the complete staged file matches ENA byte size
and MD5. Range requests, retries, failures and SHA256 are recorded.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time

TITLE = "Illumina MiSeq sequencing: Flow-Seq of GFP library without intron in HEK293 cells"


def digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def jobs_from_metadata(metadata: Path, root: Path, only: list[str]) -> list[dict]:
    tokens = set(only)
    jobs = []
    with metadata.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["experiment_title"] != TITLE:
                continue
            run = row["run_accession"]
            for mate, (url, md5, size) in enumerate(zip(
                row["fastq_ftp"].split(";"), row["fastq_md5"].split(";"), row["fastq_bytes"].split(";")
            ), 1):
                token = f"{run}_{mate}"
                if tokens and run not in tokens and token not in tokens:
                    continue
                jobs.append({
                    "run": run, "mate": mate, "token": token, "url": "https://" + url,
                    "expected_md5": md5, "expected_bytes": int(size),
                    "path": root / run / f"{token}.fastq.gz",
                })
    if not jobs:
        raise ValueError("no jobs selected")
    return sorted(jobs, key=lambda job: (job["run"], job["mate"]))


def ranges_for(prefix: int, total: int, chunk: int) -> list[tuple[int, int]]:
    if not (0 <= prefix <= total and chunk > 0):
        raise ValueError("invalid prefix/total/chunk")
    return [(start, min(start + chunk, total) - 1) for start in range(prefix, total, chunk)]


def atomic_json(path: Path, value: dict) -> None:
    if path.exists():
        raise FileExistsError(path)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--chunk-mib", type=int, default=8)
    parser.add_argument("--attempts", type=int, default=8)
    parser.add_argument("--retry-delay", type=int, default=5)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    if not (1 <= args.workers <= 32 and 1 <= args.chunk_mib <= 64 and 1 <= args.attempts <= 20 and 0 <= args.retry_delay <= 30):
        raise ValueError("worker/chunk/attempt/retry-delay bounds")
    jobs = jobs_from_metadata(args.metadata, args.root, args.only)
    chunk_bytes = args.chunk_mib * 1024 * 1024
    print_lock = threading.Lock()

    def log(value: dict) -> None:
        with print_lock:
            print(json.dumps(value, sort_keys=True, default=str), flush=True)

    pending = []
    records = []
    for job in jobs:
        path = job["path"]
        if path.exists():
            if path.stat().st_size != job["expected_bytes"] or digest(path, "md5") != job["expected_md5"]:
                raise RuntimeError(f"formal file fails verification: {path}")
            records.append({**job, "status": "existing_verified", "bytes": path.stat().st_size,
                            "md5": job["expected_md5"], "sha256": digest(path, "sha256")})
            log(records[-1])
            continue
        part = path.with_suffix(path.suffix + ".part")
        prefix = part.stat().st_size if part.exists() else 0
        if prefix > job["expected_bytes"]:
            raise RuntimeError(f"partial exceeds expected size: {part}")
        staging = path.with_name(path.name + f".range-stage-{os.getpid()}")
        if staging.exists():
            raise FileExistsError(staging)
        with part.open("rb") as source, staging.open("xb") as target:
            remaining = prefix
            while remaining:
                block = source.read(min(8 * 1024 * 1024, remaining))
                if not block:
                    raise RuntimeError(f"partial changed while copying: {part}")
                target.write(block)
                remaining -= len(block)
            target.truncate(job["expected_bytes"])
        state = {**job, "part": part, "prefix_bytes": prefix, "staging": staging,
                 "fd": os.open(staging, os.O_RDWR), "ranges": ranges_for(prefix, job["expected_bytes"], chunk_bytes)}
        pending.append(state)
        log({"status": "staged_prefix", "token": job["token"], "prefix_bytes": prefix,
             "expected_bytes": job["expected_bytes"], "range_count": len(state["ranges"])})

    failures = []
    def fetch(state: dict, start: int, end: int) -> None:
        next_start = start
        last_error = "not started"
        for attempt in range(1, args.attempts + 1):
            remaining = end - next_start + 1
            command = [
                "curl", "-L", "--fail", "--silent", "--show-error",
                "--connect-timeout", "30", "--speed-limit", "1024", "--speed-time", "90",
                "--max-time", "900", "--range", f"{next_start}-{end}", state["url"],
            ]
            completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            data = completed.stdout
            if data and completed.returncode in {0, 18, 28, 56} and len(data) <= remaining:
                view = memoryview(data)
                offset = next_start
                while view:
                    written = os.pwrite(state["fd"], view, offset)
                    if written <= 0:
                        raise OSError("pwrite made no progress")
                    offset += written
                    view = view[written:]
                next_start += len(data)
                if next_start > end:
                    log({"status": "range_complete", "token": state["token"], "start": start, "end": end, "attempt": attempt})
                    return
                log({"status": "range_partial", "token": state["token"], "start": start,
                     "resume_from": next_start, "end": end, "received": len(data), "attempt": attempt})
            last_error = f"curl={completed.returncode}; bytes={len(data)}/{remaining}; resume_from={next_start}; stderr={completed.stderr.decode(errors='replace')[-500:]}"
            log({"status": "range_retry", "token": state["token"], "start": start, "end": end,
                 "attempt": attempt, "error": last_error})
            if attempt < args.attempts:
                time.sleep(min(args.retry_delay * attempt, 30))
        raise RuntimeError(f"{state['token']} range {start}-{end}: {last_error}")

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(fetch, state, start, end) for state in pending for start, end in state["ranges"]]
            for future in concurrent.futures.as_completed(futures):
                future.result()
        for state in pending:
            os.fsync(state["fd"])
            os.close(state["fd"])
            state["fd"] = -1
            staging = state["staging"]
            actual_bytes = staging.stat().st_size
            actual_md5 = digest(staging, "md5")
            if actual_bytes != state["expected_bytes"] or actual_md5 != state["expected_md5"]:
                raise RuntimeError(f"staged MD5/size mismatch for {state['token']}: {actual_bytes}, {actual_md5}")
            actual_sha256 = digest(staging, "sha256")
            if state["path"].exists():
                if state["path"].stat().st_size != state["expected_bytes"] or digest(state["path"], "md5") != state["expected_md5"]:
                    raise RuntimeError(f"refusing to replace unexpected formal file: {state['path']}")
                staging.unlink()
                status = "existing_verified"
            else:
                os.replace(staging, state["path"])
                status = "range_downloaded_verified"
            record = {key: value for key, value in state.items() if key not in {"fd", "ranges", "staging", "part"}}
            record.update({"status": status, "bytes": actual_bytes, "md5": actual_md5, "sha256": actual_sha256})
            records.append(record)
            log(record)
    except Exception as exc:
        failures.append({"error": str(exc)})
        log({"status": "FAIL", "error": str(exc)})
    finally:
        for state in pending:
            if state["fd"] >= 0:
                os.close(state["fd"])

    report = {
        "schema": "a8.rk02.mordstein_hek293_download.v1",
        "transport": "parallel_http_ranges_with_complete_file_md5_gate",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_metadata": str(args.metadata), "output_root": str(args.root),
        "requested_only": args.only, "workers": args.workers, "chunk_mib": args.chunk_mib,
        "expected_runs": len({job["run"] for job in jobs}), "expected_files": len(jobs),
        "passed_files": len(records), "failures": failures,
        "status": "PASS" if not failures and len(records) == len(jobs) else "FAIL",
        "files": sorted(records, key=lambda row: (row["run"], row["mate"])),
    }
    atomic_json(args.report, report)
    log({"status": report["status"], "passed_files": len(records), "failed_files": len(jobs) - len(records), "report": str(args.report)})
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
