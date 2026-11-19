#!/usr/bin/env python3
"""Prepare the pre-registered RK08 occupancy-derived velocity-proxy dataset.

Protocol (locked before model readout):
- train/dev/test come only from Mohammad16 (80/10/10 by deterministic record hash);
- Mohammad19-1, Mohammad19-2 and Subtelny14 are study-OOD only;
- only CDS <= 1002 codons are retained;
- first and terminal-stop codons are masked, so loss covers elongation positions;
- velocity proxy = -log1p(official normalized ribosome density), hence larger
  values mean lower occupancy / a faster proxy, not a physical velocity assay.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import io
import json
import math
from pathlib import Path

from codonflow.core.codon import is_valid_cds, normalize_to_dna
from codonflow.data.ribokinetic import file_sha256


EXPECTED_DATASETS = {"Mohammad16", "Mohammad19-1", "Mohammad19-2", "Subtelny14"}


def deterministic_gzip_text(path: Path):
    raw = path.open("wb")
    compressed = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    return io.TextIOWrapper(compressed, encoding="utf-8", newline="")


def split_for(record_id: str, seed: int) -> str:
    value = int.from_bytes(hashlib.sha256(f"{seed}:{record_id}".encode()).digest()[:8], "big") / 2**64
    if value < 0.8:
        return "train"
    if value < 0.9:
        return "dev"
    return "test"


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-jsonl", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--audit-json", required=True)
    parser.add_argument("--max-codons", type=int, default=1002)
    parser.add_argument("--seed", type=int, default=20261119)
    parser.add_argument("--max-records-per-study", type=int, default=None, help="Smoke only; null for formal runs")
    args = parser.parse_args()
    if args.max_codons < 3:
        raise ValueError("max_codons must be >=3")

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    destination = out / "velocity_records.jsonl.gz"
    source_hash = file_sha256(args.input_jsonl)
    counts = collections.Counter()
    by_split_study = collections.Counter()
    observed_by_split_study = collections.Counter()
    source_commits = set()
    cds_by_split = collections.defaultdict(set)
    study_cds = collections.defaultdict(set)
    train_dev_test_cds = set()
    primary_overlap = None

    with gzip.open(args.input_jsonl, "rt", encoding="utf-8") as source, deterministic_gzip_text(destination) as target:
        for raw_line in source:
            raw = json.loads(raw_line)
            counts["input_records"] += 1
            dataset = raw["dataset"]
            if dataset not in EXPECTED_DATASETS:
                raise ValueError(f"unexpected dataset {dataset}")
            if not raw.get("clean_eligible"):
                raise ValueError(f"non-clean record in clean input: {raw['record_id']}")
            cds = normalize_to_dna(raw["cds_dna"])
            if not is_valid_cds(cds):
                raise ValueError(f"invalid CDS: {raw['record_id']}")
            n_codons = len(cds) // 3
            density = raw["density_normalized"]
            if n_codons != raw["n_codons"] or len(density) != n_codons:
                raise ValueError(f"length mismatch: {raw['record_id']}")
            if any(not math.isfinite(float(x)) or float(x) < 0 for x in density):
                raise ValueError(f"invalid density: {raw['record_id']}")
            if n_codons > args.max_codons:
                counts["excluded_over_max_codons"] += 1
                continue
            if n_codons < 3:
                counts["excluded_no_elongation_position"] += 1
                continue
            if args.max_records_per_study is not None and counts[f"retained_attempt_{dataset}"] >= args.max_records_per_study:
                counts["excluded_smoke_cap"] += 1
                continue
            counts[f"retained_attempt_{dataset}"] += 1
            record_id = raw["record_id"]
            if not record_id.startswith(dataset + ":"):
                raise ValueError(f"record prefix mismatch: {record_id}")
            split = split_for(record_id, args.seed) if dataset == "Mohammad16" else "study_ood"
            cluster_id = "exact_cds:" + hashlib.sha256(cds.encode()).hexdigest()
            targets = [None] * n_codons
            for position in range(1, n_codons - 1):
                targets[position] = -math.log1p(float(density[position]))
            row = {
                "record_id": record_id,
                "source_record_id": record_id.split(":", 1)[1],
                "dataset": dataset,
                "source_accession": raw["source_accession"],
                "source_commit": raw["source_commit"],
                "source_record_index": int(raw["source_record_index"]),
                "reference_protein_sha256": raw["reference_protein_sha256"],
                "cds": cds,
                "split": split,
                "cluster_id": cluster_id,
                "host": raw["organism"],
                "velocity_target": targets,
            }
            target.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
            source_commits.add(raw["source_commit"])
            counts["retained_records"] += 1
            counts[f"retained_{dataset}"] += 1
            by_split_study[f"{split}|{dataset}"] += 1
            observed_by_split_study[f"{split}|{dataset}"] += n_codons - 2
            cds_by_split[split].add(cds)
            study_cds[dataset].add(cds)
            if split in {"train", "dev", "test"}:
                train_dev_test_cds.add(cds)

    if counts["retained_records"] == 0:
        raise ValueError("no records retained")
    if len(source_commits) != 1:
        raise ValueError(f"expected one source commit, got {sorted(source_commits)}")
    for left, right in [("train", "dev"), ("train", "test"), ("dev", "test")]:
        overlap = len(cds_by_split[left] & cds_by_split[right])
        counts[f"exact_cds_overlap_{left}_{right}"] = overlap
        if overlap:
            raise AssertionError(f"exact CDS leakage between {left} and {right}: {overlap}")
    primary_overlap = len(train_dev_test_cds & study_cds["Subtelny14"])
    if primary_overlap:
        raise AssertionError("Subtelny14 primary OOD has exact CDS overlap with Mohammad16")

    audit = {
        "protocol": "a8_rk08_velocity_proxy_v1_preregistered_before_model_readout",
        "status": "SMOKE_DATA_ONLY" if args.max_records_per_study is not None else "DATA_READY_PENDING_TRAINING",
        "target_semantics": "-log1p(official normalized ribosome density); occupancy-derived speed proxy, not physical velocity",
        "loss_positions": "codons 1..n-2 in zero-based coordinates; first and terminal-stop codons masked",
        "train_dev_test_source": "Mohammad16 only, deterministic record-hash 80/10/10; not homology-cluster OOD",
        "study_ood": ["Mohammad19-1", "Mohammad19-2", "Subtelny14"],
        "primary_ood": "Subtelny14 cross-species/cross-study, exact-CDS-disjoint from all Mohammad16 splits",
        "max_codons": args.max_codons,
        "seed": args.seed,
        "max_records_per_study": args.max_records_per_study,
        "counts": dict(sorted(counts.items())),
        "records_by_split_study": dict(sorted(by_split_study.items())),
        "observed_positions_by_split_study": dict(sorted(observed_by_split_study.items())),
        "exact_cds_overlap_with_mohammad16_train": {
            dataset: len(cds_by_split["train"] & study_cds[dataset])
            for dataset in sorted(EXPECTED_DATASETS - {"Mohammad16"})
        },
        "subtelny14_exact_cds_overlap_with_any_mohammad16_split": primary_overlap,
        "source_commit": next(iter(source_commits)),
        "input_jsonl": args.input_jsonl,
        "input_sha256": source_hash,
        "output_jsonl": str(destination),
        "output_sha256": file_sha256(str(destination)),
        "functional_ood_accessed": False,
        "homology_ood_claimed": False,
    }
    save_json(Path(args.audit_json), audit)
    print(json.dumps({"status": audit["status"], "records": counts["retained_records"], "output": str(destination), "audit": args.audit_json}, indent=2))


if __name__ == "__main__":
    main()
