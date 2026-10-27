"""Build final training corpus: merge species, cluster-split 80-10-10.

Inputs: cleaned per-species CDS FASTA + GENCODE cluster TSV.
Leakage protection: benchmark sequences' clusters are excluded from train.
Output: splits/{train,val,test}.fasta + audit JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from .gemorna_arm import cds_protein
except ImportError:
    from gemorna_arm import cds_protein


def read_fasta(path: str) -> List[Tuple[str, str]]:
    recs = []
    header = None
    chunks = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header is not None:
                    recs.append((header, "".join(chunks)))
                header = line[1:].split()[0]
                chunks = []
            else:
                chunks.append(line)
        if header is not None:
            recs.append((header, "".join(chunks)))
    return recs


def read_clusters(tsv: str) -> Dict[str, List[str]]:
    clusters = defaultdict(list)
    with open(tsv) as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2:
                clusters[parts[0]].append(parts[1])
    return dict(clusters)


def benchmark_components(clusters: Dict[str, List[str]], seqs: Dict[str, str],
                         benchmark_records: List[Tuple[str, str]]):
    """Return connected MMseqs2 components containing exact benchmark CDS."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for rep, members in clusters.items():
        for member in members:
            union(rep, member)

    seq_to_members = defaultdict(list)
    protein_to_members = defaultdict(list)
    for member, seq in seqs.items():
        seq_to_members[seq.upper().replace("U", "T")].append(member)
        protein = cds_protein(seq)
        if protein is not None:
            protein_to_members[protein].append(member)
    direct, components, matched = set(), set(), {}
    match_kinds = defaultdict(set)
    for header, seq in benchmark_records:
        exact = seq_to_members.get(seq.upper().replace("U", "T"), [])
        identifiers = [header, header.split()[0], f"benchmark__{header.split()[0]}"]
        by_id = [member for member in identifiers if member in parent]
        protein = cds_protein(seq)
        synonymous = protein_to_members.get(protein, []) if protein is not None else []
        members = set(exact) | set(by_id) | set(synonymous)
        if exact:
            match_kinds["exact_cds"].add(header)
        if by_id:
            match_kinds["identifier"].add(header)
        if synonymous:
            match_kinds["exact_protein"].add(header)
        if members:
            matched[header] = sorted(members)
        for member in members:
            if member not in parent:
                raise ValueError(f"benchmark sequence {member!r} is absent from cluster TSV")
            direct.add(member)
            components.add(find(member))
    for node in list(parent):
        find(node)
    member_to_component = {member: find(rep) for rep, members in clusters.items()
                           for member in [rep, *members]}
    affected = {member for member in seqs
                if member in direct or member_to_component.get(member) in components}
    return affected, {
        "n_benchmark_records": len(benchmark_records),
        "n_matched": len(matched),
        "n_unmatched": len(benchmark_records) - len(matched),
        "n_exact_sequence_matched": len(match_kinds["exact_cds"]),
        "n_exact_sequence_unmatched": len(benchmark_records) - len(match_kinds["exact_cds"]),
        "n_exact_protein_matched": len(match_kinds["exact_protein"]),
        "n_identifier_matched": len(match_kinds["identifier"]),
        "unmatched_headers": [h for h, _ in benchmark_records if h not in matched],
        "n_directly_matched_members": len(direct),
        "n_connected_components": len(components),
        "n_excluded_cds": len(affected),
        "n_excluded_input_records": sum(1 for member in seqs if member in affected),
    }


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cleaned", nargs="+", required=True)
    ap.add_argument("--cluster-tsv", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--benchmark-fasta", required=True, nargs="+",
                    help="CDS FASTA files whose sequences and connected clusters are excluded")
    ap.add_argument("--train-frac", type=float, default=0.8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--group-by-protein", action="store_true",
                    help="collapse exact translated-protein groups before cluster splitting")
    ap.add_argument("--excluded-out-fasta", default=None,
                    help="optional FASTA of every record removed by benchmark component exclusion")
    args = ap.parse_args()
    if not 0 < args.train_frac < 1:
        raise ValueError("train-frac must be between zero and one")
    rng = random.Random(args.seed)
    seqs: Dict[str, str] = {}
    for path in args.cleaned:
        for h, s in read_fasta(path):
            seqs[h] = s
    clusters = read_clusters(args.cluster_tsv)
    if len({member for members in clusters.values() for member in members}) != sum(
        len(members) for members in clusters.values()
    ):
        raise ValueError("cluster TSV assigns one identifier to multiple representatives")
    n_clusters_before = len(clusters)
    cluster_members = {member for members in clusters.values() for member in members}
    missing_cluster_members = set(seqs) - cluster_members
    if missing_cluster_members and args.group_by_protein:
        covered_proteins = {
            cds_protein(seqs[member]) for member in cluster_members if member in seqs
        }
        uncovered = {
            member for member in missing_cluster_members
            if cds_protein(seqs[member]) not in covered_proteins
        }
        if uncovered:
            raise ValueError(f"{len(uncovered)} FASTA proteins absent from cluster TSV")
    elif missing_cluster_members:
        raise ValueError(f"{len(missing_cluster_members)} FASTA identifiers absent from cluster TSV")
    benchmark_records = [
        record for path in args.benchmark_fasta for record in read_fasta(path)
    ]
    if not benchmark_records:
        raise ValueError("--benchmark-fasta contains no FASTA records")
    excluded, benchmark_audit = benchmark_components(clusters, seqs, benchmark_records)
    benchmark_audit["enabled"] = True
    if args.excluded_out_fasta:
        Path(args.excluded_out_fasta).parent.mkdir(parents=True, exist_ok=True)
        with open(args.excluded_out_fasta, "w") as handle:
            for member in sorted(excluded):
                if member in seqs:
                    handle.write(f">{member}\n{seqs[member]}\n")
    if args.group_by_protein:
        # Keep the first identifier per exact protein and retain its original
        # cluster membership. Unlisted members are discarded, not regrouped.
        representatives = {}
        for member, seq in seqs.items():
            protein = cds_protein(seq)
            if protein is None:
                raise ValueError(f"invalid CDS translation for {member}")
            representatives.setdefault(protein, member)
        retained = set(representatives.values())
        clusters = {rep: [member for member in members if member in retained]
                    for rep, members in clusters.items()}
        clusters = {rep: members for rep, members in clusters.items() if members}
    if benchmark_audit["n_unmatched"]:
        print("WARNING: benchmark sequences without exact CDS/protein/identifier match: "
              + ", ".join(benchmark_audit["unmatched_headers"]))
    names = sorted(clusters.keys())
    rng.shuffle(names)
    n = len(names)
    n_train = int(n * args.train_frac)
    n_val = max(1, int(n * 0.1))
    splits = {
        "train": names[:n_train],
        "val": names[n_train : n_train + n_val],
        "test": names[n_train + n_val :],
    }
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for split, cluster_names in splits.items():
        count = 0
        with open(out / f"{split}.fasta", "w") as f:
            for rep in cluster_names:
                for member in clusters[rep]:
                    if member in seqs and member not in excluded:
                        f.write(f">{member}\n{seqs[member]}\n")
                        count += 1
        counts[split] = count
    audit = {
        "n_input_seqs": len(seqs),
        "n_clusters": n,
        "n_clusters_before_protein_dedup": n_clusters_before,
        "n_retained_input_records": sum(counts.values()),
        "n_removed_as_protein_duplicates": len(seqs) - sum(counts.values()) - len(excluded) if args.group_by_protein else 0,
        "group_by_protein": args.group_by_protein,
        "n_unlisted_exact_protein_duplicate_ids": len(missing_cluster_members) if args.group_by_protein else 0,
        "split_counts": counts,
        "seed": args.seed,
        "benchmark_exclusion": benchmark_audit,
        "input_sha256": {
            "cleaned": [file_sha256(path) for path in args.cleaned],
            "cluster_tsv": file_sha256(args.cluster_tsv),
            "benchmark_fasta": [file_sha256(path) for path in args.benchmark_fasta],
        },
        "split_sha256": {split: file_sha256(out / f"{split}.fasta") for split in splits},
        "excluded_out_fasta": args.excluded_out_fasta,
        "excluded_out_sha256": file_sha256(args.excluded_out_fasta) if args.excluded_out_fasta else None,
    }
    (out / "split_audit.json").write_text(json.dumps(audit, indent=2))
    print(json.dumps(audit))


if __name__ == "__main__":
    main()
