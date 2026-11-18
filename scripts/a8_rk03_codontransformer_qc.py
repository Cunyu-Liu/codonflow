#!/usr/bin/env python3
"""Streaming, hash-gated row QC for the pinned CodonTransformer training CSV."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

COLUMNS = ["dna", "protein", "organism", "GeneID", "description", "tokenized", "fine_tuned", "len"]
STOPS = {"TAA", "TAG", "TGA"}
BASES = "TCAG"
AMINO_ACIDS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
CODON_TABLE = {
    a + b + c: ("_" if AMINO_ACIDS[i] == "*" else AMINO_ACIDS[i])
    for i, (a, b, c) in enumerate((a, b, c) for a in BASES for b in BASES for c in BASES)
}
ACCESSION_RE = re.compile(r"\b([A-Z]{1,4}_\d+\.\d+):(\d+)-(\d+)\b")
GENE_ID_RE = re.compile(r"\d+(?:\.0+)?")


class QCError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest_file(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def atomic_json(path: Path, value: Mapping[str, object]) -> None:
    if path.exists():
        raise QCError(f"refusing to overwrite JSON: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + f".part.{os.getpid()}")
    part.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(part, path)


def numeric_summary(values: Iterable[float]) -> Dict[str, object]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {"n": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None, "mean": None}
    def quantile(fraction: float) -> float:
        position = (len(ordered) - 1) * fraction
        lower, upper = math.floor(position), math.ceil(position)
        if lower == upper:
            return ordered[lower]
        return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)
    return {"n": len(ordered), "min": ordered[0], "p25": quantile(.25),
            "median": quantile(.5), "p75": quantile(.75), "max": ordered[-1],
            "mean": statistics.fmean(ordered)}


def parse_accession(description: str) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    matched = ACCESSION_RE.search(description)
    if not matched:
        return None, None, None
    return matched.group(1), int(matched.group(2)), int(matched.group(3))


def qc_row(raw: Mapping[str, str]) -> Dict[str, object]:
    dna = str(raw.get("dna", "")).strip().upper()
    protein = str(raw.get("protein", "")).strip().upper()
    organism = " ".join(str(raw.get("organism", "")).split())
    gene_id = str(raw.get("GeneID", "")).strip()
    description = str(raw.get("description", ""))
    tokenized = str(raw.get("tokenized", "")).strip()
    fine_tuned = str(raw.get("fine_tuned", "")).strip()
    reasons: List[str] = []
    if not dna: reasons.append("missing_dna")
    if set(dna) - set("ACGT"): reasons.append("non_acgt_dna")
    if len(dna) % 3: reasons.append("dna_length_not_divisible_by_3")
    if not protein: reasons.append("missing_protein")
    if not protein.endswith("_"): reasons.append("missing_protein_terminal_stop")
    if "_" in protein[:-1]: reasons.append("internal_protein_stop_symbol")
    if set(protein[:-1]) - set("ACDEFGHIKLMNPQRSTVWY"): reasons.append("unsupported_protein_alphabet")
    if not organism: reasons.append("missing_organism")
    if not GENE_ID_RE.fullmatch(gene_id): reasons.append("invalid_gene_id")
    if fine_tuned not in {"True", "False"}: reasons.append("invalid_fine_tuned")
    try:
        reported_length = int(str(raw.get("len", "")).strip())
        if reported_length != len(protein): reasons.append("protein_length_field_mismatch")
    except ValueError:
        reported_length = None
        reasons.append("invalid_length_field")
    accession, start, end = parse_accession(description)
    if accession is None:
        reasons.append("accession_or_coordinates_missing")
        coordinate_match = False
    else:
        coordinate_match = start >= 1 and end >= start and end - start + 1 == len(dna)
        if not coordinate_match: reasons.append("accession_coordinate_length_mismatch")
    translated = None
    terminal_stop = internal_stop = start_atg = False
    if dna and len(dna) % 3 == 0 and not set(dna) - set("ACGT"):
        codons = [dna[index:index + 3] for index in range(0, len(dna), 3)]
        start_atg = codons[0] == "ATG"
        terminal_stop = codons[-1] in STOPS
        internal_stop = any(codon in STOPS for codon in codons[:-1])
        translated = "".join(CODON_TABLE[codon] for codon in codons)
        if translated != protein: reasons.append("translation_protein_mismatch")
        expected_tokens = " ".join(f"{aa}_{codon}" for aa, codon in zip(translated, codons))
        if tokenized != expected_tokens: reasons.append("tokenized_sequence_mismatch")
    if dna and not start_atg: reasons.append("start_not_atg")
    if dna and not terminal_stop: reasons.append("missing_terminal_stop")
    if internal_stop: reasons.append("internal_stop")
    gc = (dna.count("G") + dna.count("C")) / len(dna) if dna else None
    return {"dna": dna, "protein": protein, "organism": organism, "gene_id": gene_id,
            "description": description, "tokenized": tokenized, "fine_tuned": fine_tuned,
            "reported_length": reported_length, "accession": accession,
            "coordinate_match": coordinate_match, "translated": translated,
            "start_atg": start_atg, "terminal_stop": terminal_stop, "internal_stop": internal_stop,
            "gc": gc, "reasons": reasons, "valid": not reasons}


def prepare_output(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise QCError(f"refusing to use nonempty output directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def run_qc(config_path: Path, raw_path: Path, output_dir: Path,
           audit_path: Optional[Path] = None) -> Dict[str, object]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    source = next(item for item in config["sources"] if item["source_id"] == "codontransformer_training")
    spec = next(item for item in source["files"] if item["filename"] == raw_path.name)
    if not raw_path.is_file(): raise QCError(f"missing raw file: {raw_path}")
    actual_bytes = raw_path.stat().st_size
    actual_sha = digest_file(raw_path)
    if actual_bytes != int(spec["expected_bytes"]):
        raise QCError(f"raw byte mismatch: expected={spec['expected_bytes']}, actual={actual_bytes}")
    if actual_sha.lower() != str(spec["expected_sha256"]).lower():
        raise QCError(f"raw SHA256 mismatch: expected={spec['expected_sha256']}, actual={actual_sha}")
    prepare_output(output_dir)
    all_path = output_dir / "codontransformer_all_qc.csv.gz"
    clean_path = output_dir / "codontransformer_clean.csv.gz"
    all_fields = ["source_row_number", "dna_sha256", "protein_sha256", "organism", "GeneID",
                  "accession", "valid", "exclusion_reasons", "gc_fraction", "dna_length",
                  "protein_length", "fine_tuned", "coordinate_length_match"]
    clean_fields = COLUMNS + ["source_row_number", "accession"]
    reason_counts: Counter = Counter()
    raw_organisms: Counter = Counter(); clean_organisms: Counter = Counter(); fine_counts: Counter = Counter()
    dna_first: Dict[str, Tuple[int, str]] = {}; duplicate_keys = set(); cross_organism_keys = set()
    clean_lengths: List[float] = []; clean_gc: List[float] = []
    raw_rows = clean_rows = duplicate_rows = cross_organism_duplicate_rows = 0
    csv.field_size_limit(100_000_000)
    with raw_path.open("r", encoding="utf-8-sig", newline="") as raw_handle, \
            gzip.open(all_path, "wt", encoding="utf-8", newline="", compresslevel=5) as all_handle, \
            gzip.open(clean_path, "wt", encoding="utf-8", newline="", compresslevel=5) as clean_handle:
        reader = csv.DictReader(raw_handle)
        if list(reader.fieldnames or []) != COLUMNS:
            raise QCError(f"unexpected columns: {reader.fieldnames}")
        all_writer = csv.DictWriter(all_handle, fieldnames=all_fields); all_writer.writeheader()
        clean_writer = csv.DictWriter(clean_handle, fieldnames=clean_fields); clean_writer.writeheader()
        for row_number, raw in enumerate(reader, 1):
            record = qc_row(raw); raw_rows += 1
            organism = str(record["organism"]); raw_organisms[organism] += 1
            fine_counts[str(record["fine_tuned"])] += 1
            reason_counts.update(record["reasons"])
            dna_hash = sha256_text(str(record["dna"])); protein_hash = sha256_text(str(record["protein"]))
            if dna_hash in dna_first:
                duplicate_rows += 1; duplicate_keys.add(dna_hash)
                if dna_first[dna_hash][1] != organism:
                    cross_organism_duplicate_rows += 1; cross_organism_keys.add(dna_hash)
            else:
                dna_first[dna_hash] = (row_number, organism)
            all_writer.writerow({"source_row_number": row_number, "dna_sha256": dna_hash,
                "protein_sha256": protein_hash, "organism": organism, "GeneID": record["gene_id"],
                "accession": record["accession"] or "", "valid": int(bool(record["valid"])),
                "exclusion_reasons": ";".join(record["reasons"]),
                "gc_fraction": "" if record["gc"] is None else format(float(record["gc"]), ".17g"),
                "dna_length": len(str(record["dna"])), "protein_length": len(str(record["protein"])),
                "fine_tuned": record["fine_tuned"], "coordinate_length_match": int(bool(record["coordinate_match"]))})
            if record["valid"]:
                clean_rows += 1; clean_organisms[organism] += 1
                clean_lengths.append(len(str(record["protein"]))); clean_gc.append(float(record["gc"]))
                clean_writer.writerow({**{column: raw[column] for column in COLUMNS},
                                       "source_row_number": row_number, "accession": record["accession"]})
    summary: Dict[str, object] = {
        "schema_version": "a8-rk03-codontransformer-qc-v1", "created_at": utc_now(),
        "status": "COMPLETE_QC_PENDING_INDEPENDENT_VERIFICATION",
        "config_path": str(config_path), "config_sha256": digest_file(config_path),
        "raw_path": str(raw_path), "raw_bytes": actual_bytes, "raw_sha256": actual_sha,
        "source_record": source["record"], "mirror_dataset": source["mirror_dataset"],
        "mirror_commit": source["mirror_commit"], "license": source["license"],
        "raw_rows": raw_rows, "clean_rows": clean_rows,
        "raw_organism_count": len(raw_organisms), "clean_organism_count": len(clean_organisms),
        "publisher_reported_rows": 1001197, "publisher_reported_organisms": 164,
        "publisher_scope_matches_independent_count": raw_rows == 1001197 and len(raw_organisms) == 164,
        "exclusion_reason_counts": dict(sorted(reason_counts.items())),
        "fine_tuned_counts": dict(sorted(fine_counts.items())),
        "duplicate_dna_rows_after_first": duplicate_rows, "duplicate_dna_keys": len(duplicate_keys),
        "cross_organism_duplicate_dna_rows_after_first": cross_organism_duplicate_rows,
        "cross_organism_duplicate_dna_keys": len(cross_organism_keys),
        "raw_organism_counts": dict(sorted(raw_organisms.items())),
        "clean_organism_counts": dict(sorted(clean_organisms.items())),
        "clean_distributions": {"protein_length_including_stop": numeric_summary(clean_lengths),
                                 "gc_fraction_full_cds": numeric_summary(clean_gc)},
        "clean_table_ready_pending_verifier": clean_rows > 0,
        "natural_distribution_eligible": False,
        "functional_training_authorized": False, "functional_ood_claim_authorized": False,
        "provenance_boundary": "Publisher-derived NCBI records with versioned accession/coordinate checks; no independent NCBI re-download of every row.",
        "scope": "Natural DNA-protein sequence QC only; not functional labels, host-matched CAI, trained-model, OOD, or SOTA evidence.",
        "artifacts": {"all_qc": all_path.name, "clean": clean_path.name},
    }
    summary_path = output_dir / "qc_summary.json"; atomic_json(summary_path, summary)
    manifest = {"schema_version": "a8-rk03-codontransformer-artifact-manifest-v1",
                "created_at": utc_now(), "raw": {"path": str(raw_path), "bytes": actual_bytes, "sha256": actual_sha},
                "outputs": {path.name: {"bytes": path.stat().st_size, "sha256": digest_file(path)}
                            for path in (all_path, clean_path, summary_path)}}
    atomic_json(output_dir / "artifact_manifest.json", manifest)
    if audit_path is not None: atomic_json(audit_path, summary)
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit", type=Path)
    args = parser.parse_args(argv)
    summary = run_qc(args.config, args.raw, args.output_dir, args.audit)
    print(json.dumps({key: summary[key] for key in ("status", "raw_rows", "clean_rows",
        "raw_organism_count", "clean_organism_count", "publisher_scope_matches_independent_count",
        "clean_table_ready_pending_verifier")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
