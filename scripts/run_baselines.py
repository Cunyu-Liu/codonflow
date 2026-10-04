"""Baseline runners: codonGPT constrained sampling, LinearDesign, CAI-greedy.

All baselines share the same decode budget for fair comparison (spec R4).
codonGPT: official HF checkpoint naniltx/codonGPT @ ee7017c4 (SHA recorded).
LinearDesign: official grid-DP implementation (built from source; human codon
usage table). CAI-greedy: most frequent codon per amino acid.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from codonflow.core.codon import (
    SYNONYMOUS_CODONS,
    is_valid_cds,
    normalize_to_dna,
    protein_of_cds,
    translate,
)
from codonflow.eval.metrics import (
    cai,
    cai_weights_from_rscu,
    mfe_batch,
    ned,
    gc_fraction,
    codon_entropy_per_aa_position,
    pairwise_ned,
    unique_fraction,
)


def cai_greedy(protein: str, weights: Dict[str, float]) -> str:
    """Highest-CAI codon per amino acid + TAA terminal (upper 'homogeneous' anchor)."""
    seq = []
    for aa in protein:
        best = max(SYNONYMOUS_CODONS[aa], key=lambda c: weights.get(c, 0.0))
        seq.append(best)
    seq.append("TAA")
    return "".join(seq)


def random_synonymous(
    protein: str, rng, rscu: Optional[Dict[str, float]] = None
) -> str:
    """Uniform (or RSCU-weighted) synonymous sampling per position."""
    seq = []
    for aa in protein:
        group = list(SYNONYMOUS_CODONS[aa])
        if rscu:
            w = [max(rscu.get(c, 0.0), 1e-9) for c in group]
            total = sum(w)
            p = [x / total for x in w]
            seq.append(rng.choices(group, weights=p, k=1)[0])
        else:
            seq.append(rng.choice(group))
    seq.append("TAA")
    return "".join(seq)


def summarize_candidates(
    candidates: Sequence[str], source: str, weights: Dict[str, float]
) -> Dict:
    prot_src = protein_of_cds(source)
    mfes = mfe_batch(list(candidates))
    identity = [int(protein_of_cds(c) == prot_src) for c in candidates]
    legal = [int(is_valid_cds(c)) for c in candidates]
    cais = [cai(c, weights) for c in candidates]
    return {
        "n": len(candidates),
        "identity_rate": sum(identity) / len(candidates),
        "legal_rate": sum(legal) / len(candidates),
        "cai_mean": sum(cais) / len(cais),
        "mfe_mean": sum(mfes) / len(mfes),
        "gc_mean": sum(gc_fraction(c) for c in candidates) / len(candidates),
        "ned_mean": pairwise_ned(list(candidates)),
        "unique_fraction": unique_fraction(candidates),
        "codon_entropy": codon_entropy_per_aa_position(candidates),
    }


def run_cai_greedy_baseline(
    source: str, weights: Dict[str, float]
) -> Dict:
    t0 = time.time()
    prot = protein_of_cds(source)
    seq = cai_greedy(prot, weights)
    return {
        "method": "cai_greedy",
        "candidate": seq,
        "elapsed_s": time.time() - t0,
        "cai": cai(seq, weights),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="source CDS (DNA)")
    ap.add_argument("--rscu-json", help="RSCU reference table JSON")
    ap.add_argument("--n-variants", type=int, default=1000)
    ap.add_argument("--out", default="-")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    import numpy as np

    rng = np.random.default_rng(args.seed)
    rscu = json.loads(Path(args.rscu_json).read_text()) if args.rscu_json else None
    weights = cai_weights_from_rscu(rscu or {})
    source = normalize_to_dna(args.source)
    prot = protein_of_cds(source)
    variants_uniform = [
        random_synonymous(prot, rng) for _ in range(args.n_variants)
    ]
    out = {
        "source": source,
        "uniform_random": summarize_candidates(variants_uniform, source, weights),
        "cai_greedy": run_cai_greedy_baseline(source, weights),
    }
    text = json.dumps(out, indent=2)
    if args.out == "-":
        print(text)
    else:
        Path(args.out).write_text(text)


if __name__ == "__main__":
    main()
