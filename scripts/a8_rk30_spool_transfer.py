#!/usr/bin/env python3
"""Temporary local-to-server HeLa R1 spool with two-sided MD5 gates.

--local-only permits label-free acquisition during a server outage; a later
default run performs the unchanged remote precheck, upload and atomic rename.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time

TITLES = {
    "Illumina MiSeq sequencing: Flow-Seq of GFP library without intron in HeLa cells",
    "Illumina MiSeq sequencing: Flow-Seq of GFP library with intron in HeLa cells",
}
SSH_BASE = ["ssh", "-o", "ControlPath=/tmp/codonflow_px2_root.sock", "-p", "29375", "root@px2-jcy.matpool.com"]
SCP_BASE = ["scp", "-o", "ControlPath=/tmp/codonflow_px2_root.sock", "-P", "29375"]
REMOTE_ROOT = "/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional/mordstein2020/raw"
PRINT_LOCK = threading.Lock()


def digest(path: Path, algorithm="md5") -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def log(value: dict) -> None:
    with PRINT_LOCK:
        print(json.dumps(value, sort_keys=True), flush=True)


def remote_formal_record(job: dict, remote: str) -> dict | None:
    remote_code = r'''
import hashlib, json, sys
from pathlib import Path
p=Path(sys.argv[1]); expected_md5=sys.argv[2]; expected_bytes=int(sys.argv[3]); run=sys.argv[4]
if not p.exists():
 print(json.dumps({"status":"missing"}))
else:
 if p.stat().st_size!=expected_bytes: raise RuntimeError("unexpected formal size")
 md5=hashlib.md5(); sha256=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(8*1024*1024),b""): md5.update(b); sha256.update(b)
 if md5.hexdigest()!=expected_md5: raise RuntimeError("unexpected formal MD5")
 print(json.dumps({"status":"remote_verified","run":run,"bytes":expected_bytes,"md5":expected_md5,"sha256":sha256.hexdigest(),"remote":str(p),"remote_action":"existing_precheck"}))
'''
    completed = subprocess.run(
        SSH_BASE + ["python3", "-", remote, job["md5"], str(job["bytes"]), job["run"]],
        input=remote_code,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"remote formal precheck failed for {job['run']}: {completed.stderr[-1000:]}")
    record = json.loads(completed.stdout.strip().splitlines()[-1])
    return None if record["status"] == "missing" else record


def transfer(job: dict, spool: Path, attempts: int, local_only: bool = False) -> dict:
    run = job["run"]
    local = spool / f"{run}_1.fastq.gz"
    remote = f"{REMOTE_ROOT}/{run}/{run}_1.fastq.gz"
    temporary = remote + ".upload-local"
    record = None if local_only else remote_formal_record(job, remote)
    if record is not None:
        if local.exists() and local.stat().st_size == job["bytes"] and digest(local, "md5") == job["md5"]:
            local.unlink()
        log(record)
        return record
    error = "not started"
    local_already_verified = (
        local.exists()
        and local.stat().st_size == job["bytes"]
        and digest(local, "md5") == job["md5"]
    )
    if local_already_verified:
        log({"status": "local_reused_verified", "run": run, "bytes": job["bytes"]})
    else:
        for attempt in range(1, attempts + 1):
            if local.exists() and local.stat().st_size > job["bytes"]:
                raise RuntimeError(f"local spool exceeds expected bytes: {local}")
            command = [
                "curl", "-L", "--fail", "--silent", "--show-error", "--connect-timeout", "30",
                "--speed-limit", "1024", "--speed-time", "90", "--max-time", "900",
                "-C", "-", "-o", str(local), job["url"],
            ]
            completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            size = local.stat().st_size if local.exists() else 0
            if completed.returncode == 0 and size == job["bytes"]:
                break
            error = f"curl={completed.returncode}; bytes={size}/{job['bytes']}; {completed.stderr.decode(errors='replace')[-500:]}"
            log({"status": "local_retry", "run": run, "attempt": attempt, "error": error})
            if attempt < attempts:
                time.sleep(min(5 * attempt, 30))
        else:
            raise RuntimeError(f"{run}: {error}")
    if local.stat().st_size != job["bytes"] or digest(local, "md5") != job["md5"]:
        raise RuntimeError(f"local MD5/size mismatch: {run}")
    local_sha256 = digest(local, "sha256")
    log({"status": "local_verified", "run": run, "bytes": job["bytes"], "md5": job["md5"], "sha256": local_sha256})
    if local_only:
        return {"status": "local_only_verified", "run": run, "bytes": job["bytes"], "md5": job["md5"], "sha256": local_sha256, "local": str(local)}
    record = remote_formal_record(job, remote)
    if record is not None:
        local.unlink()
        log(record)
        return record
    destination = f"root@px2-jcy.matpool.com:{temporary}"
    subprocess.run(SCP_BASE + [str(local), destination], check=True)
    remote_code = r'''
import hashlib, os, sys
from pathlib import Path
p=Path(sys.argv[1]); t=Path(sys.argv[2]); expected_md5=sys.argv[3]; expected_bytes=int(sys.argv[4])
def md5(q):
 h=hashlib.md5()
 with q.open("rb") as f:
  for b in iter(lambda:f.read(8*1024*1024),b""): h.update(b)
 return h.hexdigest()
if p.exists():
 if p.stat().st_size!=expected_bytes or md5(p)!=expected_md5: raise RuntimeError("unexpected formal file")
 if t.exists(): t.unlink()
 print("existing_verified")
else:
 if not t.exists() or t.stat().st_size!=expected_bytes or md5(t)!=expected_md5: raise RuntimeError("uploaded MD5/size mismatch")
 os.replace(t,p)
 print("uploaded_verified")
'''
    completed = subprocess.run(
        SSH_BASE + ["python3", "-", remote, temporary, job["md5"], str(job["bytes"])],
        input=remote_code,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"remote verification failed for {run}: {completed.stderr[-1000:]}")
    local.unlink()
    record = {"status": "remote_verified", "run": run, "bytes": job["bytes"], "md5": job["md5"], "sha256": local_sha256, "remote": remote, "remote_action": completed.stdout.strip()}
    log(record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--spool", type=Path, required=True)
    parser.add_argument("--only", nargs="*", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--local-only", action="store_true", help="Download and verify locally without contacting the server")
    args = parser.parse_args()
    if not 1 <= args.workers <= 6 or not 1 <= args.attempts <= 20:
        raise ValueError("worker/attempt bounds")
    args.spool.mkdir(parents=True, exist_ok=True)
    selected = set(args.only)
    jobs = []
    with args.metadata.open(newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            run = row["run_accession"]
            if row["experiment_title"] not in TITLES or run not in selected:
                continue
            jobs.append({"run": run, "url": "https://" + row["fastq_ftp"].split(";")[0], "md5": row["fastq_md5"].split(";")[0], "bytes": int(row["fastq_bytes"].split(";")[0])})
    if {j["run"] for j in jobs} != selected or len(jobs) != len(selected):
        raise ValueError("selected runs do not match HeLa metadata")
    records = []
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(transfer, job, args.spool, args.attempts, args.local_only): job["run"] for job in sorted(jobs, key=lambda x: x["run"])}
        for future in concurrent.futures.as_completed(futures):
            try:
                records.append(future.result())
            except Exception as exc:
                failures.append({"run": futures[future], "error": str(exc)})
                log({"status": "FAIL_RUN", **failures[-1]})
    report = {"status": "PASS" if not failures and len(records) == len(jobs) else "FAIL", "expected": len(jobs), "passed": len(records), "failures": failures, "files": records}
    log(report)
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
