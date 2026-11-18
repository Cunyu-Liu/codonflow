#!/usr/bin/env python3
"""Compute RK07 sequence-only proxies from the frozen RK04 Boel split.

Expression labels are deliberately not copied into the feature artifact.  The
only codon-usage reference is the external, hash-pinned E. coli RefSeq CDS file.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import gzip
import hashlib
import importlib.metadata
import io
import json
import math
import os
import sys
from pathlib import Path
from typing import Iterable

import ViennaRNA

CODONS = [a + b + c for a in "TCAG" for b in "TCAG" for c in "TCAG"]
AAS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
CODON_TABLE = dict(zip(CODONS, AAS))
SENSE_CODONS = [c for c in CODONS if CODON_TABLE[c] != "*"]
SYNONYMS = {aa: [c for c in SENSE_CODONS if CODON_TABLE[c] == aa] for aa in sorted(set(CODON_TABLE.values()) - {"*"})}
FEATURE_FIELDS = [
    "source_id", "source_row", "protein_id", "construct_id",
    "operational_protein_cluster", "split_assignment", "cds_sha256",
    "length_nt", "gc_fraction", "cai", "full_cds_mfe_kcal_mol",
    "full_cds_mfe_per_nt", "mfe_5prime_48_kcal_mol",
    "source_Gave48", "source_Gave96", "source_Gave144", "source_Gz48v",
]
_WORKER_WEIGHTS = None
_WORKER_TEMPERATURE = None
_WORKER_WINDOW = None


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: str | Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(tmp, path)


def translate(cds: str) -> str:
    return "".join(CODON_TABLE.get(cds[i:i + 3], "X") for i in range(0, len(cds), 3))


def canonical_cds(cds: str) -> tuple[str, str]:
    cds = "".join(cds.upper().split())
    if not cds or len(cds) % 3 or len(cds) < 6:
        raise ValueError("CDS length is invalid")
    if set(cds) - set("ACGT"):
        raise ValueError("CDS contains non-ACGT symbols")
    if CODON_TABLE.get(cds[-3:]) != "*":
        raise ValueError("CDS lacks a terminal stop")
    coding = cds[:-3]
    protein = translate(coding)
    if "*" in protein or "X" in protein:
        raise ValueError("CDS contains an internal stop or invalid codon")
    return cds, coding


def iter_fasta(path: str | Path) -> Iterable[tuple[str, str]]:
    opener = gzip.open if str(path).endswith(".gz") else open
    header = None
    chunks: list[str] = []
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith(">"):
                if header is not None:
                    yield header, "".join(chunks)
                header = line[1:]
                chunks = []
            elif line:
                chunks.append(line)
    if header is not None:
        yield header, "".join(chunks)


def build_cai_weights(reference_path: str | Path, exclude_pseudo: bool = True) -> tuple[dict[str, float], dict]:
    counts = {c: 0 for c in SENSE_CODONS}
    stats = {
        "reference_records": 0, "reference_used": 0, "reference_skipped_pseudo": 0,
        "reference_skipped_invalid": 0, "reference_sense_codons": 0,
    }
    for header, sequence in iter_fasta(reference_path):
        stats["reference_records"] += 1
        if exclude_pseudo and "[pseudo=true]" in header:
            stats["reference_skipped_pseudo"] += 1
            continue
        try:
            _, coding = canonical_cds(sequence)
        except ValueError:
            stats["reference_skipped_invalid"] += 1
            continue
        stats["reference_used"] += 1
        for i in range(0, len(coding), 3):
            counts[coding[i:i + 3]] += 1
            stats["reference_sense_codons"] += 1
    missing = [c for c in SENSE_CODONS if counts[c] <= 0]
    if missing:
        raise ValueError(f"reference lacks sense codons: {missing}")
    weights = {}
    for aa, codons in SYNONYMS.items():
        maximum = max(counts[c] for c in codons)
        for codon in codons:
            weights[codon] = counts[codon] / maximum
    if len(weights) != 61 or not all(0 < value <= 1 for value in weights.values()):
        raise ValueError("invalid CAI weights")
    stats["reference_codon_counts"] = counts
    stats["rscu_relative_adaptiveness"] = weights
    return weights, stats


def gc_and_cai(coding: str, weights: dict[str, float]) -> tuple[float, float]:
    if not coding:
        raise ValueError("empty coding region")
    gc = sum(base in "GC" for base in coding) / len(coding)
    logs = [math.log(weights[coding[i:i + 3]]) for i in range(0, len(coding), 3)]
    return gc, math.exp(sum(logs) / len(logs))


def _init_worker(weights: dict[str, float], temperature: float, window: int) -> None:
    global _WORKER_WEIGHTS, _WORKER_TEMPERATURE, _WORKER_WINDOW
    _WORKER_WEIGHTS = weights
    _WORKER_TEMPERATURE = temperature
    _WORKER_WINDOW = window


def _optional_float(value) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def compute_row(row: dict, weights: dict[str, float], temperature: float, window: int) -> dict:
    cds, coding = canonical_cds(row["cds"])
    expected_protein = row["protein_sequence"].rstrip("*")
    if translate(coding) != expected_protein:
        raise ValueError(f"translation mismatch at source_row={row['source_row']}")
    gc, cai = gc_and_cai(coding, weights)
    rna = cds.replace("T", "U")
    md = ViennaRNA.md()
    md.temperature = float(temperature)
    full_mfe = float(ViennaRNA.fold_compound(rna, md).mfe()[1])
    local_mfe = float(ViennaRNA.fold_compound(rna[:window], md).mfe()[1])
    source_features = json.loads(row["features_json"] or "{}")
    result = {
        "source_id": row["source_id"],
        "source_row": row["source_row"],
        "protein_id": row["protein_id"],
        "construct_id": row["construct_id"],
        "operational_protein_cluster": row["operational_protein_cluster"],
        "split_assignment": row["split_assignment"],
        "cds_sha256": hashlib.sha256(cds.encode()).hexdigest(),
        "length_nt": len(coding),
        "gc_fraction": gc,
        "cai": cai,
        "full_cds_mfe_kcal_mol": full_mfe,
        "full_cds_mfe_per_nt": full_mfe / len(cds),
        "mfe_5prime_48_kcal_mol": local_mfe,
    }
    for key in ("Gave48", "Gave96", "Gave144", "Gz48v"):
        result["source_" + key] = _optional_float(source_features.get(key))
    return result


def _compute_row_worker(row: dict) -> dict:
    return compute_row(row, _WORKER_WEIGHTS, _WORKER_TEMPERATURE, _WORKER_WINDOW)


def read_sequence_rows(protocol: dict, limit_per_split: int | None) -> list[dict]:
    rows = []
    seen = set()
    per_split = {split: 0 for split in protocol["allowed_splits"]}
    fields = [
        "source_id", "source_row", "protein_id", "construct_id",
        "operational_protein_cluster", "split_assignment", "cds",
        "protein_sequence", "features_json",
    ]
    with open(protocol["split_file"], newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            if raw["source_id"] != protocol["source_id"]:
                continue
            split = raw["split_assignment"]
            if split == protocol["forbidden_split"]:
                raise ValueError("functional_untouched is forbidden for RK07")
            if split not in per_split:
                raise ValueError(f"unexpected split: {split}")
            if limit_per_split is not None and per_split[split] >= limit_per_split:
                continue
            # Only sequence/metadata fields are retained; expression_value is never read.
            row = {key: raw[key] for key in fields}
            identity = (row["source_row"], row["construct_id"])
            if identity in seen:
                raise ValueError(f"duplicate source identity: {identity}")
            seen.add(identity)
            rows.append(row)
            per_split[split] += 1
    if limit_per_split is None:
        expected = {k: v for k, v in protocol["expected_rows"].items() if k != "total"}
        if per_split != expected or len(rows) != protocol["expected_rows"]["total"]:
            raise ValueError(f"row-count mismatch: {per_split}, total={len(rows)}")
    return rows


def atomic_feature_csv(path: str | Path, rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with open(tmp, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(text, fieldnames=FEATURE_FIELDS, extrasaction="raise", lineterminator="\n")
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
    os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--output-features", required=True)
    parser.add_argument("--output-summary", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit-per-split", type=int, default=None, help="development smoke only; never valid for final evaluation")
    args = parser.parse_args()
    protocol_path = Path(args.protocol).resolve()
    protocol = json.loads(protocol_path.read_text())
    for key, expected in (("split_file", protocol["split_sha256"]), ("reference_cds", protocol["reference_cds_sha256"])):
        actual = sha256_file(protocol[key])
        if actual != expected:
            raise ValueError(f"SHA256 mismatch for {key}: {actual}")
    rows = read_sequence_rows(protocol, args.limit_per_split)
    weights, reference_stats = build_cai_weights(protocol["reference_cds"], protocol["reference_exclude_pseudo"])
    if args.workers < 1:
        raise ValueError("workers must be positive")
    if args.workers == 1:
        computed = [compute_row(row, weights, protocol["fold_temperature_c"], protocol["local_window_nt"]) for row in rows]
    else:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=args.workers,
            initializer=_init_worker,
            initargs=(weights, protocol["fold_temperature_c"], protocol["local_window_nt"]),
        ) as executor:
            computed = list(executor.map(_compute_row_worker, rows, chunksize=8))
    atomic_feature_csv(args.output_features, computed)
    split_counts = {split: sum(row["split_assignment"] == split for row in computed) for split in protocol["allowed_splits"]}
    summary = {
        "status": "smoke_features_only" if args.limit_per_split is not None else "full_features_ready",
        "protocol_id": protocol["protocol_id"],
        "command": [sys.executable, "-m", "scripts.a8_rk07_proxy_features", *sys.argv[1:]],
        "protocol_sha256": sha256_file(protocol_path),
        "production_code_sha256": sha256_file(Path(__file__).resolve()),
        "split_file": protocol["split_file"], "split_sha256": protocol["split_sha256"],
        "reference_cds": protocol["reference_cds"], "reference_cds_sha256": protocol["reference_cds_sha256"],
        "reference_scope": protocol["reference_scope"], "reference_stats": reference_stats,
        "expression_labels_accessed": False,
        "forbidden_split_used": False,
        "row_count": len(computed), "split_counts": split_counts,
        "unique_cds_sha256": len({row["cds_sha256"] for row in computed}),
        "feature_file": str(Path(args.output_features).resolve()),
        "feature_file_sha256": sha256_file(args.output_features),
        "feature_fields": FEATURE_FIELDS,
        "fold_temperature_c": protocol["fold_temperature_c"],
        "local_window_nt": protocol["local_window_nt"],
        "local_window_scope": protocol["local_window_scope"],
        "environment": {
            "python": os.sys.version.split()[0],
            "ViennaRNA": importlib.metadata.version("ViennaRNA"),
        },
        "workers": args.workers,
        "limit_per_split": args.limit_per_split,
        "scientific_scope": protocol["scientific_scope"],
        "prohibited_claims": protocol["prohibited_claims"],
    }
    atomic_json(args.output_summary, summary)
    print(json.dumps({k: summary[k] for k in ("status", "row_count", "split_counts", "feature_file_sha256")}, indent=2))


if __name__ == "__main__":
    main()
