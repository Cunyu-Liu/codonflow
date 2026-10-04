"""Motif catalogue with soft penalties (spec Task 1.4.2).

Default catalogue: polyA signals (AATAAA/ATTAAA), splice donor/acceptor
consensus (GT..AG), T7/SP6 promoters, long homopolymers (>= 6).
"""
from __future__ import annotations

import re
from typing import Dict, Mapping, Tuple

DEFAULT_MOTIFS: Tuple[Tuple[str, str, float], ...] = (
    ("polyA_AATAAA", "AATAAA", 1.0),
    ("polyA_ATTAAA", "ATTAAA", 1.0),
    ("splice_donor_GT", "GTGAGT", 1.0),
    ("splice_acceptor_AG", "CAGG", 0.5),
    ("t7_promoter", "TAATACGACTCACTATA", 2.0),
    ("sp6_promoter", "ATTTAGGTGACACTAT", 2.0),
)

HOMOPOLYMER_RUN = 6

_RNA_TO_DNA = str.maketrans("U", "T")


def _to_dna(seq: str) -> str:
    return seq.upper().translate(_RNA_TO_DNA)


def count_motifs(seq: str) -> Dict[str, int]:
    """Count occurrences of each default motif (overlapping, DNA alphabet)."""
    s = _to_dna(seq)
    counts: Dict[str, int] = {}
    for name, pattern, _w in DEFAULT_MOTIFS:
        p = _to_dna(pattern)
        counts[name] = len(re.findall(f"(?={p})", s))
    for base in "ACGT":
        runs = re.findall(f"{base}{{{HOMOPOLYMER_RUN},}}", s)
        counts[f"homopolymer_{base}"] = sum(len(r) // 1 for r in runs)
    counts = {k: v for k, v in counts.items() if v > 0}
    return counts


def motif_penalty_score(seq: str, weights: Mapping[str, float] = None) -> float:
    """Weighted sum of motif counts; unlisted motifs default to 1.0."""
    counts = count_motifs(seq)
    if not counts:
        return 0.0
    w = weights or {}
    return float(sum(c * float(w.get(name, 1.0)) for name, c in counts.items()))
