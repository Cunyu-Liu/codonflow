"""Data pipeline: download, clean, cluster, and split CDS corpora (Task 1.1).

Steps (each counted into docs/data_audit/pipeline_counts.md):
  1. length % 3 == 0, terminal stop present, no internal stops
  2. length filter [300, 6000] nt
  3. MMseqs2 easy-cluster 0.8 identity, keep one representative per cluster
  4. cluster-level 80-10-10 split (whole clusters go to one split only)

Sources: Ensembl BioMart / RefSeq; GENCODE FASTA when available.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from typing import Dict, Iterable, List, Optional, Tuple

from codonflow.core.codon import (
    STOP_CODONS,
    is_valid_cds,
    normalize_to_dna,
    split_codons,
)
from codonflow.data.dataset import read_fasta

STEP_HEADER = (
    "# Pipeline counts (auto-generated)\n\n"
    "| step | description | kept | dropped |\n|---|---|---|---|\n"
)


def clean_cds(seq: str) -> Tuple[Optional[str], str]:
    """Return (cleaned_seq, drop_reason); reason empty string if kept."""
    s = normalize_to_dna(seq)
    if len(s) == 0:
        return None, "empty"
    if len(s) % 3 != 0:
        return None, "frame"
    if len(s) < 300:
        return None, "too_short"
    if len(s) > 6000:
        return None, "too_long"
    if s[-3:] not in STOP_CODONS:
        return None, "no_terminal_stop"
    body = s[:-3]
    for i in range(0, len(body), 3):
        if body[i : i + 3] in STOP_CODONS:
            return None, "internal_stop"
    if not all(c in "ACGT" for c in s):
        return None, "alphabet"
    return s, ""


def clean_fasta(in_path: str, out_path: str) -> Dict[str, int]:
    counts = Counter()
    kept: List[Tuple[str, str]] = []
    for header, seq in read_fasta(in_path):
        cleaned, reason = clean_cds(seq)
        if cleaned is None:
            counts[reason] += 1
            continue
        counts["kept"] += 1
        kept.append((header, cleaned))
    with open(out_path, "w") as f:
        for h, s in kept:
            f.write(f">{h}\n{s}\n")
    return dict(counts)


def mmseqs_cluster(
    fasta: str, workdir: str, identity: float = 0.8, threads: int = 32
) -> str:
    """MMseqs2 easy-cluster; returns TSV (representative\\tmember) path."""
    os.makedirs(workdir, exist_ok=True)
    tsv = os.path.join(workdir, "cluster.tsv")
    if os.path.exists(tsv):
        return tsv
    cmd = [
        "mmseqs", "easy-cluster", fasta,
        os.path.join(workdir, "cluster"), tsv,
        "--min-seq-id", str(identity), "--threads", str(threads),
    ]
    subprocess.run(cmd, check=True)
    return tsv


def load_clusters(tsv: str) -> List[str]:
    reps = {}
    with open(tsv) as f:
        for line in f:
            parts = line.rstrip("\\n").split("\\t")
            if len(parts) >= 2:
                reps.setdefault(parts[0], []).append(parts[1])
    return reps


def split_by_cluster(
    fasta: str, clusters: Dict[str, List[str]], out_dir: str,
    train_frac: float = 0.8, seed: int = 0,
) -> Dict[str, int]:
    import random

    rng = random.Random(seed)
    headers = {h: s for h, s in read_fasta(fasta)}
    names = list(clusters.keys())
    rng.shuffle(names)
    n = len(names)
    n_train = int(n * train_frac)
    n_val = int(n * 0.1)
    splits = {
        "train": names[:n_train],
        "val": names[n_train : n_train + n_val],
        "test": names[n_train + n_val :],
    }
    os.makedirs(out_dir, exist_ok=True)
    counts = {}
    for split, cluster_names in splits.items():
        count = 0
        with open(os.path.join(out_dir, f"{split}.fasta"), "w") as f:
            for rep in cluster_names:
                for member in clusters[rep]:
                    if member in headers:
                        f.write(f">{member}\\n{headers[member]}\\n")
                        count += 1
        counts[split] = count
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-fasta", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--identity", type=float, default=0.8)
    ap.add_argument("--threads", type=int, default=32)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    wd = args.workdir
    os.makedirs(wd, exist_ok=True)
    cleaned_path = os.path.join(wd, "cleaned.fasta")
    counts = clean_fasta(args.input_fasta, cleaned_path)
    tsv = mmseqs_cluster(cleaned_path, os.path.join(wd, "mmseqs"), args.identity, args.threads)
    clusters = load_clusters(tsv)
    split_counts = split_by_cluster(cleaned_path, clusters, os.path.join(wd, "splits"), seed=args.seed)
    audit = {
        "input": args.input_fasta,
        "clean_counts": counts,
        "n_clusters": len(clusters),
        "split_counts": split_counts,
    }
    with open(os.path.join(wd, "audit.json"), "w") as f:
        json.dump(audit, f, indent=2)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
