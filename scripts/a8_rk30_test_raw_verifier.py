#!/usr/bin/env python3
"""Exercise the independent raw verifier on a tiny, explicitly synthetic 64-run fixture."""
import copy
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "configs" / "a8-rk30-mordstein-matched-context-v1.json"
VERIFIER = ROOT / "scripts" / "a8_rk30_verify_raw_counts.py"


def digest(path, algorithm="sha256"):
    value = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def make_fixture(tmp_path):
    protocol = json.loads(PROTOCOL.read_text())
    with Path(protocol["inputs"]["reference_csv"]["path"]).open(newline="") as handle:
        references = list(csv.DictReader(handle))
    variant_ids = [row["variant_id"] for row in references]
    sequence = references[0]["sequence_5prime_300nt"].upper()
    raw_root = tmp_path / "raw"
    metadata_path = tmp_path / "metadata.tsv"
    per_run = tmp_path / "artifacts" / "per_run"
    per_run.mkdir(parents=True)
    metadata_rows = []
    count_rows = []
    run_records = []
    index = 0
    for context, definition in protocol["contexts"].items():
        for replicate in definition["replicates"]:
            for bin_id in range(1, 9):
                index += 1
                run = f"SRR90{index:04d}"
                run_dir = raw_root / run
                run_dir.mkdir(parents=True)
                fastq = run_dir / f"{run}_1.fastq.gz"
                with gzip.GzipFile(filename=str(fastq), mode="wb", mtime=0) as handle:
                    handle.write(f"@{run}\n{sequence}\n+\n{'I' * 300}\n".encode())
                md5 = digest(fastq, "md5")
                metadata_rows.append({"run_accession": run, "fastq_md5": f"{md5};{md5}"})
                for variant_id in variant_ids:
                    count_rows.append([run, context, replicate, variant_id, bin_id, 125])
                audit = [{"read_index": j, "r1_sequence": sequence,
                          "r1_centroid_index": 0, "r1_distance_nt": 0} for j in range(100)]
                record = {"run": run, "input_path": str(fastq), "expected_md5": md5,
                          "input_sha256": digest(fastq), "counts": [125] * len(variant_ids),
                          "metrics": {"r1_assigned": 125 * len(variant_ids)}, "audit_samples": audit}
                (per_run / f"{run}.json").write_text(json.dumps(record))
                run_records.append((run, context, replicate))
    with metadata_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["run_accession", "fastq_md5"], delimiter="\t")
        writer.writeheader()
        writer.writerows(metadata_rows)
    protocol["inputs"]["metadata_tsv"]["path"] = str(metadata_path)
    protocol["inputs"]["metadata_tsv"]["sha256"] = digest(metadata_path)
    protocol["inputs"]["raw_r1_root"] = str(raw_root)
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol))
    counts_path = tmp_path / "artifacts" / "fixed_reference_r1_counts.csv"
    with counts_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["run", "context", "replicate", "variant_id", "bin", "count"])
        writer.writerows(count_rows)
    outcomes_path = tmp_path / "artifacts" / "matched_context_outcomes.csv"
    with outcomes_path.open("w", newline="") as handle:
        fields = ["variant_id"] + [f"target__{name}" for name in protocol["contexts"]]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for variant_id in variant_ids:
            writer.writerow({"variant_id": variant_id, **{name: 4.5 for name in fields[1:]}})
    return protocol_path, tmp_path / "artifacts", per_run


def run_verifier(protocol, artifacts, report):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
               MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1")
    return subprocess.run([sys.executable, str(VERIFIER), "--protocol", str(protocol),
                           "--artifact-root", str(artifacts), "--report", str(report)],
                          text=True, capture_output=True, env=env)


def test_raw_verifier_pass_and_audit_count_negative(tmp_path):
    protocol, artifacts, per_run = make_fixture(tmp_path)
    report = artifacts / "raw.json"
    completed = run_verifier(protocol, artifacts, report)
    assert completed.returncode == 0, completed.stderr + completed.stdout
    result = json.loads(report.read_text())
    assert result["status"] == "PASS_INDEPENDENT_RAW_COUNT_VERIFICATION"
    assert result["checkpoints"] == 64
    assert result["audit_reads_reassigned_by_brute_force"] == 6400
    assert result["audit_read_count_pass"] is True
    assert result["protocol_sha256"] == digest(protocol)
    assert result["cost_seconds"] >= 0
    first = sorted(per_run.glob("SRR*.json"))[0]
    record = json.loads(first.read_text())
    record["audit_samples"].pop()
    first.write_text(json.dumps(record))
    negative = artifacts / "raw_negative.json"
    completed = run_verifier(protocol, artifacts, negative)
    assert completed.returncode == 1
    result = json.loads(negative.read_text())
    assert result["status"] == "FAIL_INDEPENDENT_RAW_COUNT_VERIFICATION"
    assert result["audit_reads_reassigned_by_brute_force"] == 6399
    assert result["audit_read_count_pass"] is False
