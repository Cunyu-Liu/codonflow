#!/usr/bin/env python3
"""Independent raw-count and outcome verification; no RK30 production imports."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd


def digest(path: Path, algorithm="sha256"):
    value = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def brute_force_assignment(sequence: str, references: list[str], max_error=8):
    if len(sequence) != 300:
        return None, None
    query = np.frombuffer(sequence.encode(), dtype=np.uint8)
    matrix = np.frombuffer("".join(references).encode(), dtype=np.uint8).reshape(len(references), 300)
    distances = (matrix != query).sum(axis=1)
    best = int(distances.min())
    if best > max_error or int((distances == best).sum()) != 1:
        return None, best
    return int(distances.argmin()), best


def independent_outcomes(counts: pd.DataFrame, protocol: dict):
    per_replicate = {}
    for (variant, context, replicate), group in counts.groupby(["variant_id", "context", "replicate"]):
        group = group.sort_values("bin")
        values = group["count"].to_numpy(dtype=np.int64)
        if group["bin"].tolist() != list(range(1, 9)) or values.sum() < 1000:
            continue
        per_replicate[(variant, context, replicate)] = float(np.dot(np.arange(1, 9), values) / values.sum())
    context_scores = {}
    for context, definition in protocol["contexts"].items():
        scores = {}
        variants = counts["variant_id"].drop_duplicates()
        for variant in variants:
            values = [per_replicate.get((variant, context, replicate)) for replicate in definition["replicates"]]
            if all(value is not None for value in values):
                scores[variant] = float(np.mean(values))
        context_scores[context] = scores
    common = set(counts["variant_id"].unique())
    for scores in context_scores.values():
        common &= set(scores)
    rows = []
    for variant in sorted(common):
        row = {"variant_id": variant}
        for context, scores in context_scores.items():
            row[f"target__{context}"] = scores[variant]
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    wall_start = time.perf_counter()
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    references_frame = pd.read_csv(protocol["inputs"]["reference_csv"]["path"],
                                   usecols=["variant_id", "sequence_5prime_300nt"])
    variant_ids = references_frame["variant_id"].tolist()
    references = references_frame["sequence_5prime_300nt"].str.upper().tolist()
    metadata_rows = {}
    with Path(protocol["inputs"]["metadata_tsv"]["path"]).open(newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            metadata_rows[row["run_accession"]] = row
    checkpoints = sorted((args.artifact_root / "per_run").glob("SRR*.json"))
    checks = []
    mismatches = []
    md5_mismatches = []
    audit_total = 0
    for checkpoint in checkpoints:
        record = json.loads(checkpoint.read_text())
        run = record["run"]
        path = Path(record["input_path"])
        actual_md5 = digest(path, "md5")
        expected_md5 = metadata_rows[run]["fastq_md5"].split(";")[0]
        if actual_md5 != expected_md5 or actual_md5 != record["expected_md5"]:
            md5_mismatches.append(run)
        checks.append({"run": run, "md5_pass": actual_md5 == expected_md5,
                       "sha256_pass": digest(path) == record["input_sha256"],
                       "count_sum_pass": sum(record["counts"]) == record["metrics"]["r1_assigned"],
                       "count_length_pass": len(record["counts"]) == 152})
        for sample in record["audit_samples"]:
            expected_id, expected_distance = brute_force_assignment(sample["r1_sequence"], references)
            produced_id = sample["r1_centroid_index"]
            produced_distance = sample["r1_distance_nt"]
            if expected_id != produced_id or (expected_id is not None and expected_distance != produced_distance):
                mismatches.append({"run": run, "read_index": sample["read_index"],
                                   "expected_id": expected_id, "produced_id": produced_id,
                                   "expected_distance": expected_distance,
                                   "produced_distance": produced_distance})
            audit_total += 1
    counts = pd.read_csv(args.artifact_root / "fixed_reference_r1_counts.csv")
    long_mismatches = []
    for record in checkpoints:
        data = json.loads(record.read_text())
        current = (counts[counts["run"] == data["run"]]
                   .groupby("variant_id", as_index=False)["count"].sum()
                   .sort_values("variant_id"))
        expected = pd.DataFrame({"variant_id": variant_ids, "expected": data["counts"]}).sort_values("variant_id")
        if current["variant_id"].tolist() != expected["variant_id"].tolist() or not np.array_equal(current["count"].to_numpy(), expected["expected"].to_numpy()):
            long_mismatches.append(data["run"])
    produced = pd.read_csv(args.artifact_root / "matched_context_outcomes.csv")
    independent = independent_outcomes(counts, protocol)
    merged = produced.merge(independent, on="variant_id", how="outer", suffixes=("_production", "_independent"), indicator=True)
    outcome_ok = len(merged) == len(produced) == len(independent) and merged["_merge"].eq("both").all()
    max_outcome_difference = 0.0
    for context in protocol["contexts"]:
        a = merged[f"target__{context}_production"].to_numpy(float)
        b = merged[f"target__{context}_independent"].to_numpy(float)
        if len(a):
            max_outcome_difference = max(max_outcome_difference, float(np.max(np.abs(a - b))))
    outcome_ok = outcome_ok and max_outcome_difference <= 1e-12
    expected_audit_total = 64 * int(protocol["fixed_reference_counting"]["audit_reservoir_reads_per_run"])
    audit_read_count_pass = audit_total == expected_audit_total
    report = {
        "schema": "a8.rk30.independent_raw_count_verification.v1",
        "status": "PASS_INDEPENDENT_RAW_COUNT_VERIFICATION" if (
            len(checkpoints) == 64 and audit_read_count_pass and not mismatches and not md5_mismatches and not long_mismatches and
            all(all(value for key, value in row.items() if key != "run") for row in checks) and outcome_ok
        ) else "FAIL_INDEPENDENT_RAW_COUNT_VERIFICATION",
        "production_module_imported": False,
        "rk28_model_module_imported": False,
        "protocol_sha256": digest(args.protocol),
        "counting_summary_sha256": digest(args.artifact_root / "RK30_COUNTING.json"),
        "cost_seconds": time.perf_counter() - wall_start,
        "checkpoints": len(checkpoints), "expected_checkpoints": 64,
        "audit_reads_reassigned_by_brute_force": audit_total,
        "expected_audit_reads": expected_audit_total,
        "audit_read_count_pass": audit_read_count_pass,
        "assignment_mismatches": mismatches, "md5_mismatches": md5_mismatches,
        "long_count_mismatches": long_mismatches,
        "checkpoint_checks": checks,
        "production_outcome_rows": len(produced), "independent_outcome_rows": len(independent),
        "max_outcome_absolute_difference": max_outcome_difference,
        "outcome_recalculation_pass": bool(outcome_ok),
        "fixed_reference_counts_sha256": digest(args.artifact_root / "fixed_reference_r1_counts.csv"),
        "matched_context_outcomes_sha256": digest(args.artifact_root / "matched_context_outcomes.csv"),
        "note": "Every read is covered by production checkpoints and file hashes; a frozen reservoir of 100 reads/run is independently brute-force reassigned. Outcomes are independently recomputed from every long-format count."
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key not in {"checkpoint_checks", "assignment_mismatches"}}, indent=2))
    raise SystemExit(0 if report["status"].startswith("PASS") else 1)


if __name__ == "__main__":
    main()
