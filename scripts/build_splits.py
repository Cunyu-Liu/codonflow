"""Build final training corpus: merge species, cluster-split 80-10-10.

Inputs: cleaned per-species CDS FASTA + GENCODE cluster TSV.
Leakage protection: benchmark sequences' clusters are excluded from train.
Output: splits/{train,val,test}.fasta + audit JSON.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cleaned", nargs="+", required=True)
    ap.add_argument("--cluster-tsv", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--train-frac", type=float, default=0.8)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    seqs: Dict[str, str] = {}
    for path in args.cleaned:
        for h, s in read_fasta(path):
            seqs[h] = s
    clusters = read_clusters(args.cluster_tsv)
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
                    if member in seqs:
                        f.write(f">{member}\n{seqs[member]}\n")
                        count += 1
        counts[split] = count
    audit = {
        "n_input_seqs": len(seqs),
        "n_clusters": n,
        "split_counts": counts,
        "seed": args.seed,
    }
    (out / "split_audit.json").write_text(json.dumps(audit, indent=2))
    print(json.dumps(audit))


if __name__ == "__main__":
    main()
