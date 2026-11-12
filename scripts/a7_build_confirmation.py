"""Freeze an untouched, stratified confirmation set without model objectives."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.core.codon import is_valid_cds, normalize_to_dna, protein_of_cds
from codonflow.data.dataset import read_fasta


def length_bin(length):
    return "short" if length < 600 else "mid" if length < 1200 else "long"


def gc_bin(value):
    return "low" if value < 0.45 else "mid" if value <= 0.55 else "high"


def read_cluster_tsv(path):
    mapping = {}
    with open(path) as handle:
        for line in handle:
            fields = line.rstrip().split("\t")
            if len(fields) >= 2:
                mapping[fields[1]] = fields[0]
    return mapping


def build_confirmation(test_path, exclusion_paths, cluster_path, n=24):
    test = [(header, normalize_to_dna(sequence)) for header, sequence in read_fasta(test_path)]
    if len({header for header, _ in test}) != len(test):
        raise ValueError("test identifiers must be unique")
    excluded_ids, excluded_cds, excluded_proteins = set(), set(), set()
    for path in exclusion_paths:
        for header, sequence in read_fasta(path):
            sequence = normalize_to_dna(sequence)
            excluded_ids.update((header, header.split()[0]))
            excluded_cds.add(sequence)
            if is_valid_cds(sequence):
                excluded_proteins.add(protein_of_cds(sequence))
    cluster_map = read_cluster_tsv(cluster_path)
    unmapped = [header for header, _ in test if header not in cluster_map]
    if unmapped:
        raise ValueError(f"test records missing cluster mapping: {unmapped[:5]}")
    excluded_reps = {cluster_map[identifier] for identifier in excluded_ids if identifier in cluster_map}
    candidates = []
    seen_cds, seen_proteins = set(), set()
    for header, sequence in test:
        if not is_valid_cds(sequence):
            continue
        protein = protein_of_cds(sequence)
        if (header in excluded_ids or header.split()[0] in excluded_ids
                or sequence in excluded_cds or protein in excluded_proteins
                or cluster_map.get(header) in excluded_reps
                or sequence in seen_cds or protein in seen_proteins):
            continue
        seen_cds.add(sequence)
        seen_proteins.add(protein)
        gc = (sequence.count("G") + sequence.count("C")) / len(sequence)
        candidates.append({"header": header, "sequence": sequence,
                           "length_bin": length_bin(len(sequence)), "gc_bin": gc_bin(gc)})
    if len(candidates) < n:
        raise ValueError(f"only {len(candidates)} eligible candidates for {n} confirmation records")
    selected = []
    gc_counts = Counter()
    for length in ("short", "mid", "long"):
        pool = [row for row in candidates if row["length_bin"] == length]
        quota = n // 3 + (1 if ("short", "mid", "long").index(length) < n % 3 else 0)
        for _ in range(quota):
            if not pool:
                raise ValueError(f"insufficient candidates in length stratum {length}")
            row = min(pool, key=lambda item: (
                gc_counts[item["gc_bin"]],
                hashlib.sha256((item["header"] + item["sequence"]).encode()).hexdigest(),
            ))
            pool.remove(row)
            selected.append(row)
            gc_counts[row["gc_bin"]] += 1
    return selected, {
        "n_test": len(test),
        "n_exclusion_fastas": len(exclusion_paths),
        "n_excluded_ids": len(excluded_ids),
        "n_excluded_cluster_representatives": len(excluded_reps),
        "n_eligible": len(candidates),
        "gc_strata": dict(gc_counts),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-fasta", required=True)
    parser.add_argument("--exclusion-fasta", action="append", default=[])
    parser.add_argument("--cluster-tsv", required=True)
    parser.add_argument("--n", type=int, default=24)
    parser.add_argument("--out-fasta", required=True)
    parser.add_argument("--out-manifest", required=True)
    args = parser.parse_args()
    selected, audit = build_confirmation(args.test_fasta, args.exclusion_fasta,
                                         args.cluster_tsv, args.n)
    out_fasta = Path(args.out_fasta)
    out_fasta.parent.mkdir(parents=True, exist_ok=True)
    out_fasta.write_text("".join(f">{row['header']}\n{row['sequence']}\n" for row in selected))
    manifest = {
        "protocol": "a7_confirmation_stratified_v1",
        "access": "untouched_final_evaluation_only",
        "selection_uses": ["length_nt", "gc", "identifier", "cluster_membership"],
        "selection_does_not_use": ["model_outputs", "cai", "mfe", "hypervolume"],
        "test_sha256": hashlib.sha256(Path(args.test_fasta).read_bytes()).hexdigest(),
        "exclusion_sha256": {path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                             for path in args.exclusion_fasta},
        "cluster_sha256": hashlib.sha256(Path(args.cluster_tsv).read_bytes()).hexdigest(),
        "audit": audit,
        "records": [{"header": row["header"], "length_nt": len(row["sequence"]),
                     "length_bin": row["length_bin"], "gc_bin": row["gc_bin"],
                     "cds_sha256": hashlib.sha256(row["sequence"].encode()).hexdigest()}
                    for row in selected],
        "confirmation_sha256": hashlib.sha256(out_fasta.read_bytes()).hexdigest(),
    }
    Path(args.out_manifest).write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"n": len(selected), "confirmation_sha256": manifest["confirmation_sha256"]}))


if __name__ == "__main__":
    main()
