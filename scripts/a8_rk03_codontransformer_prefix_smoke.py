#!/usr/bin/env python3
"""Real-prefix smoke for CodonTransformer QC; never a full-dataset result."""
import argparse
import hashlib
import itertools
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from scripts.a8_rk03_codontransformer_qc import run_qc
from scripts.a8_rk03_verify_codontransformer import verify


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, value):
    if path.exists(): raise RuntimeError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + f".part.{os.getpid()}")
    part.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(part, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--part", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.rows < 1: raise ValueError("rows must be positive")
    if args.work_dir.exists() and any(args.work_dir.iterdir()): raise RuntimeError("nonempty work dir")
    raw_dir = args.work_dir / "raw"; raw_dir.mkdir(parents=True, exist_ok=True)
    sample = raw_dir / "dataset.csv"
    with args.part.open("rb") as source, sample.open("xb") as target:
        for line in itertools.islice(source, args.rows + 1): target.write(line)
    original = json.loads(args.config.read_text(encoding="utf-8"))
    registered = next(item for item in original["sources"] if item["source_id"] == "codontransformer_training")
    source = dict(registered)
    full_spec = next(item for item in source["files"] if item["filename"] == "dataset.csv")
    spec = dict(full_spec); spec["expected_bytes"] = sample.stat().st_size; spec["expected_sha256"] = sha256(sample)
    source["files"] = [spec]
    smoke_config = args.audit_dir / "codontransformer_prefix_smoke_config.json"
    atomic_json(smoke_config, {"sources": [source]})
    qc_dir = args.work_dir / "qc"
    summary = run_qc(smoke_config, sample, qc_dir)
    verification_path = args.audit_dir / "codontransformer_prefix_smoke_verification.json"
    verification = verify(smoke_config, sample, qc_dir, verification_path)
    report = {"schema_version": "a8-rk03-codontransformer-prefix-smoke-v1",
              "created_at": datetime.now(timezone.utc).isoformat(), "status": "PREFIX_SMOKE_ONLY",
              "requested_data_rows": args.rows, "source_part": str(args.part),
              "source_part_bytes_at_read": args.part.stat().st_size,
              "full_dataset_bytes_frozen": full_spec["expected_bytes"], "full_dataset_sha256_frozen": full_spec["expected_sha256"],
              "full_dataset_hash_verified": False, "sample_path": str(sample), "sample_bytes": sample.stat().st_size,
              "sample_sha256": sha256(sample), "summary": {key: summary[key] for key in ("raw_rows", "clean_rows",
              "raw_organism_count", "clean_organism_count", "exclusion_reason_counts", "duplicate_dna_rows_after_first")},
              "independent_verification": {"status": verification["status"], "passed_checks": verification["passed_checks"],
              "check_count": verification["check_count"], "audit": str(verification_path)},
              "scope": "Real prefix only; no full row count, organism count, final distribution, functional, OOD, or model claim."}
    atomic_json(args.audit_dir / "codontransformer_prefix_smoke.json", report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
