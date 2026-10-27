"""Freeze a deduplicated held-out benchmark from the v4 test split only.

The legacy HELD18 list supplies only length-bin targets. Every selected record
must occur in the frozen v4 test FASTA. The closest-length available candidate
fills each stratum without consulting model outputs. This is a new deterministic
length-stratified benchmark, not a retained HELD18 list or a family/species claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.gemorna_arm import cds_protein, read_fasta_records


def length_bin(length_nt: int) -> str:
    if length_nt < 600:
        return "short"
    if length_nt < 1200:
        return "mid"
    return "long"


def build_unique_benchmark(legacy_path: str, test_path: str):
    legacy = read_fasta_records(legacy_path)
    test = read_fasta_records(test_path)
    if len({header for header, _ in test}) != len(test):
        raise ValueError("frozen test FASTA must have unique identifiers")
    test_by_cds = {sequence.upper().replace("U", "T"): header for header, sequence in test}
    if len(test_by_cds) != len(test):
        raise ValueError("frozen test FASTA must have unique CDS")
    seen_cds, seen_protein, seen_headers = set(), set(), set()
    slots = []
    for header, sequence in legacy:
        normalized = sequence.upper().replace("U", "T")
        protein = cds_protein(normalized)
        fields = header.split("|")
        if len(fields) != 4 or not fields[1].isalnum() or fields[-1] != f"{len(normalized)}nt":
            raise ValueError(f"legacy header lacks a valid species/length stratum: {header}")
        reason = None
        if header in seen_headers or normalized in seen_cds or protein in seen_protein:
            reason = "duplicate legacy CDS, protein or identifier"
        elif normalized not in test_by_cds or test_by_cds[normalized] != header:
            reason = "legacy record absent from frozen v4 test"
        if reason is None:
            seen_headers.add(header)
            seen_cds.add(normalized)
            seen_protein.add(protein)
        slots.append({"legacy_header": header, "sequence": normalized, "reason": reason})
    records, audit = [], []
    for slot in slots:
        header, normalized, reason = slot["legacy_header"], slot["sequence"], slot["reason"]
        if reason is None:
            candidate_header, candidate = header, normalized
        else:
            fields = header.split("|")
            candidates = []
            for candidate_header, candidate_sequence in test:
                candidate_sequence = candidate_sequence.upper().replace("U", "T")
                if length_bin(len(candidate_sequence)) != fields[2]:
                    continue
                if (candidate_header in seen_headers or candidate_sequence in seen_cds
                        or cds_protein(candidate_sequence) in seen_protein):
                    continue
                candidates.append((
                    abs(len(candidate_sequence) - len(normalized)), candidate_header,
                    candidate_sequence,
                ))
            if not candidates:
                raise ValueError(f"no unused frozen-test candidate for length bin {fields[2]}")
            _, candidate_header, candidate = min(candidates, key=lambda row: (row[0], row[1]))
            seen_headers.add(candidate_header)
            seen_cds.add(candidate)
            seen_protein.add(cds_protein(candidate))
        audit.append({
            "legacy_header": header, "selected_header": candidate_header,
            "reason": reason or "exact legacy record retained in frozen v4 test",
            "source": "v4_test",
        })
        records.append((candidate_header, candidate))
    return records, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-fasta", required=True)
    parser.add_argument("--test-fasta", required=True)
    parser.add_argument("--out-fasta", required=True)
    parser.add_argument("--out-manifest", required=True)
    args = parser.parse_args()
    records, audit = build_unique_benchmark(args.legacy_fasta, args.test_fasta)
    if (len(records) != 18 or len({h for h, _ in records}) != 18
            or len({s for _, s in records}) != 18
            or len({cds_protein(s) for _, s in records}) != 18):
        raise ValueError("benchmark must contain exactly 18 unique IDs, CDS and proteins")
    test_records = dict(read_fasta_records(args.test_fasta))
    for header, sequence in records:
        if test_records.get(header, "").upper().replace("U", "T") != sequence:
            raise ValueError(f"selected record is not verbatim in frozen v4 test: {header}")
    out_fasta = Path(args.out_fasta)
    out_fasta.parent.mkdir(parents=True, exist_ok=True)
    out_fasta.write_text("".join(f">{header}\n{sequence}\n" for header, sequence in records))
    manifest = {
        "protocol": "v4_test_unique18_length_stratified_v2",
        "scope": "exact-protein and exact-CDS unique, length-stratified test benchmark; species labels unavailable and no family/species disjointness claim",
        "length_bins_nt": {"short": "<600", "mid": "600-1199", "long": ">=1200"},
        "legacy_fasta": str(Path(args.legacy_fasta).resolve()),
        "test_fasta": str(Path(args.test_fasta).resolve()),
        "test_sha256": hashlib.sha256(Path(args.test_fasta).read_bytes()).hexdigest(),
        "n": len(records),
        "selection_audit": audit,
        "legacy_fasta_sha256": hashlib.sha256(Path(args.legacy_fasta).read_bytes()).hexdigest(),
        "input_sha256_invariant": "test_sha256 and legacy_fasta_sha256 must match on regeneration",
        "records": [
            {"header": header, "length_nt": len(sequence),
             "cds_sha256": hashlib.sha256(sequence.encode()).hexdigest()}
            for header, sequence in records
        ],
    }
    manifest["benchmark_sha256"] = hashlib.sha256(out_fasta.read_bytes()).hexdigest()
    Path(args.out_manifest).write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
