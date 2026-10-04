"""Synonymous variant library generation (Task 1.1.7).

Per-position independent sampling of synonymous codons, two modes: uniform
and RSCU-weighted. 1000 variants per benchmark sequence, cached under
/mnt/cunyuliu/codonflow/cache/variants/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from codonflow.core.codon import (
    SYNONYMOUS_CODONS,
    protein_of_cds,
    split_codons,
    normalize_to_dna,
    STOP_CODONS,
)


def variants_for(
    source: str, n: int, rng: np.random.Generator,
    rscu: Optional[Dict[str, float]] = None,
) -> List[str]:
    codons = split_codons(normalize_to_dna(source))
    body = codons[:-1]
    terminal = codons[-1]
    out = []
    for _ in range(n):
        new = []
        for c in body:
            if c == "ATG" or c in STOP_CODONS or c == "TGG":
                new.append(c)
                continue
            aa = None
            from codonflow.core.codon import STANDARD_TABLE_1
            aa = STANDARD_TABLE_1[c]
            group = list(SYNONYMOUS_CODONS[aa])
            if rscu is not None:
                w = np.array([max(rscu.get(g, 0.0), 1e-9) for g in group])
                p = w / w.sum()
                new.append(rng.choice(group, p=p))
            else:
                new.append(group[rng.integers(0, len(group))])
        new.append(terminal)
        out.append("".join(new))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-fasta", required=True)
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--out-dir", default="/mnt/cunyuliu/codonflow/cache/variants")
    ap.add_argument("--mode", choices=["uniform", "rscu"], default="uniform")
    ap.add_argument("--rscu-json")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    rscu = json.loads(Path(args.rscu_json).read_text()) if args.rscu_json else None
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    from codonflow.data.dataset import read_fasta

    for header, seq in read_fasta(args.source_fasta):
        name = header.split()[0].split("|")[-1][:30]
        vs = variants_for(
            seq, args.n, rng, rscu if args.mode == "rscu" else None
        )
        out = out_dir / f"{name}_{args.mode}.fasta"
        with open(out, "w") as f:
            for i, v in enumerate(vs):
                f.write(f">{name}_v{i}\n{v}\n")
        print(f"{name}: {len(vs)} variants -> {out}")


if __name__ == "__main__":
    main()
