#!/usr/bin/env python3
"""Freeze exact RNARL source bytes from official download HEAD responses."""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path, value):
    if path.exists():
        raise RuntimeError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + f".part.{os.getpid()}")
    part.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(part, path)


def probe(spec):
    last_error = None
    for attempt in range(1, 5):
        completed = subprocess.run(["curl", "-sSIL", "--max-time", "120", spec["download_url"]],
                                   capture_output=True, text=True)
        blocks = re.split(r"\r?\n\r?\n", completed.stdout.strip())
        candidates = []
        for block in blocks:
            status = re.search(r"^HTTP/\S+\s+(\d+)", block, re.MULTILINE)
            length = re.search(r"^content-length:\s*(\d+)\s*$", block, re.MULTILINE | re.IGNORECASE)
            modified = re.search(r"^last-modified:\s*(.+?)\s*$", block, re.MULTILINE | re.IGNORECASE)
            if status and length:
                candidates.append((int(status.group(1)), int(length.group(1)), modified.group(1) if modified else None))
        if completed.returncode == 0 and candidates and candidates[-1][0] == 200:
            status, size, modified = candidates[-1]
            return {"file_id": spec["file_id"], "filename": spec["filename"], "download_url": spec["download_url"],
                    "expected_md5": spec["expected_md5"], "expected_bytes": size, "byte_source": "official_head_content_length",
                    "http_status": status, "last_modified": modified, "head_attempts": attempt}
        last_error = f"returncode={completed.returncode}; stderr={completed.stderr[-500:]}; stdout={completed.stdout[-500:]}"
        time.sleep(attempt * 2)
    raise RuntimeError(f"HEAD failed for {spec['filename']}: {last_error}")


def resolve(spec, raw_dir):
    if raw_dir is not None:
        path = raw_dir / spec["filename"]
        if path.is_file() and hashlib.md5(path.read_bytes()).hexdigest().lower() == spec["expected_md5"].lower():
            return {"file_id": spec["file_id"], "filename": spec["filename"], "download_url": spec["download_url"],
                    "expected_md5": spec["expected_md5"], "expected_bytes": path.stat().st_size,
                    "byte_source": "verified_local_final_md5_matched", "http_status": None, "last_modified": None,
                    "head_attempts": 0}
    return probe(spec)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--write-config", action="store_true")
    parser.add_argument("--raw-dir", type=Path)
    args = parser.parse_args()
    before = sha256(args.config)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    source = next(item for item in config["sources"] if item["source_id"] == "rnarl_v1")
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        records = list(pool.map(lambda spec: resolve(spec, args.raw_dir), source["files"]))
    by_id = {record["file_id"]: record for record in records}
    if args.write_config:
        for spec in source["files"]:
            spec["expected_bytes"] = by_id[spec["file_id"]]["expected_bytes"]
        part = args.config.with_name(args.config.name + f".part.{os.getpid()}")
        part.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(part, args.config)
    report = {"schema_version": "a8-rk03-rnarl-official-file-sizes-v1",
              "created_at": datetime.now(timezone.utc).isoformat(), "source_record": source["record"],
              "method": "Verified local final bytes when official MD5 matches; otherwise curl HEAD final HTTP 200 Content-Length with ordered retries",
              "config_updated": args.write_config, "config_sha256_before": before,
              "config_sha256_after": sha256(args.config), "files": records}
    atomic_json(args.output, report)
    print(json.dumps({"files": len(records), "total_bytes": sum(item["expected_bytes"] for item in records),
                      "config_updated": args.write_config, "config_sha256_after": report["config_sha256_after"]}, sort_keys=True))


if __name__ == "__main__":
    main()
