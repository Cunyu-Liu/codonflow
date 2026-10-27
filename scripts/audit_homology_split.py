"""Independently audit protein-homology-cluster splits and benchmark exclusion."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.data.dataset import read_fasta
from codonflow.core.codon import protein_of_cds
from scripts.audit_distribution import overlap_audit
from scripts.build_splits import read_clusters
from scripts.gemorna_arm import cds_protein, read_fasta_records


def audit_homology_split(split_dir, cluster_tsv, benchmark_fastas, input_fasta, excluded_fasta):
    split_dir = Path(split_dir)
    metadata = json.loads((split_dir / "split_audit.json").read_text())
    split_fastas = {name: str(split_dir / f"{name}.fasta") for name in ("train", "val", "test")}
    cluster_map = {
        member: rep for rep, members in read_clusters(cluster_tsv).items()
        for member in [rep, *members]
    }
    split_ids, split_reps = {}, {}
    for name, path in split_fastas.items():
        split_ids[name] = {header.split()[0] for header, _ in read_fasta(path)}
        missing = split_ids[name] - set(cluster_map)
        if missing:
            raise ValueError(f"{name}: {len(missing)} retained IDs lack protein-cluster assignments")
        split_reps[name] = {cluster_map[identifier] for identifier in split_ids[name]}
    for left, right in (("train", "val"), ("train", "test"), ("val", "test")):
        shared = split_reps[left] & split_reps[right]
        if shared:
            raise ValueError(f"shared protein clusters between {left} and {right}: {len(shared)}")
    excluded = {header.split()[0] for header, _ in read_fasta(excluded_fasta)}
    retained = set().union(*split_ids.values())
    if retained & excluded:
        raise ValueError("excluded identifiers occur in retained splits")
    if metadata["n_retained_input_records"] != len(retained):
        raise ValueError("retained count disagrees with split_audit.json")
    conserved = (len(retained) + metadata["n_removed_as_protein_duplicates"]
                 + metadata["benchmark_exclusion"]["n_excluded_cds"])
    if conserved != metadata["n_input_seqs"]:
        raise ValueError("input conservation failed")

    benchmark_records = [record for path in benchmark_fastas for record in read_fasta_records(path)]
    benchmark_proteins = {cds_protein(sequence) for _, sequence in benchmark_records}
    benchmark_reps = set()
    for header, sequence in read_fasta(input_fasta):
        identifier = header.split()[0]
        if identifier in cluster_map and cds_protein(sequence) in benchmark_proteins:
            benchmark_reps.add(cluster_map[identifier])
    for header, _ in benchmark_records:
        external = f"benchmark__{header.split()[0]}"
        if external in cluster_map:
            benchmark_reps.add(cluster_map[external])
    retained_reps = set().union(*split_reps.values())
    if benchmark_reps & retained_reps:
        raise ValueError("benchmark protein clusters occur in retained splits")
    if metadata["benchmark_exclusion"]["n_excluded_cds"] != len(excluded):
        raise ValueError("excluded FASTA count disagrees with split_audit.json")

    overlaps = {path: overlap_audit(split_fastas, path) for path in benchmark_fastas}
    for path, result in overlaps.items():
        for pair, overlap in result["overlaps"].items():
            if overlap["n_shared_cds"] or overlap["n_shared_protein"]:
                raise ValueError(f"exact CDS/protein overlap in {path}: {pair}")
    return {
        "protocol": "protein_homology_cluster_independent_audit_v1",
        "scope": "MMseqs2 identity=0.5, bidirectional coverage=0.8; not curated family/species annotation",
        "n_input": metadata["n_input_seqs"],
        "n_retained": len(retained),
        "n_protein_duplicates": metadata["n_removed_as_protein_duplicates"],
        "n_excluded": len(excluded),
        "split_counts": {name: len(split_ids[name]) for name in split_ids},
        "split_cluster_counts": {name: len(split_reps[name]) for name in split_reps},
        "n_benchmark_cluster_representatives": len(benchmark_reps),
        "checks": {
            "split_clusters_disjoint": True,
            "benchmark_clusters_excluded": True,
            "exact_cds_protein_overlap_zero": True,
            "input_conservation": True,
            "excluded_fasta_consistent": True,
        },
        "metadata": metadata,
        "overlap_audits": overlaps,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split-dir", required=True)
    parser.add_argument("--cluster-tsv", required=True)
    parser.add_argument("--benchmark-fasta", nargs="+", required=True)
    parser.add_argument("--input-fasta", required=True)
    parser.add_argument("--excluded-fasta", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = audit_homology_split(
        args.split_dir, args.cluster_tsv, args.benchmark_fasta,
        args.input_fasta, args.excluded_fasta,
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ("metadata", "overlap_audits")}, indent=2))


if __name__ == "__main__":
    main()
