"""Metrics: CAI (Sharp & Li 1987), MFE (ViennaRNA), GC, NED, hypervolume.

CAI/NED implementations follow Sharp & Li 1987 and the Levenshtein-based
normalized edit distance definition in the spec (R2). Hypervolume uses pymoo
when available with a pure-python fallback for tests.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from ..core.codon import CODONS, STANDARD_TABLE_1, gc_fraction, split_codons, translate

EPS = 1e-12


def compute_rscu(cds_list: Iterable[str]) -> Dict[str, float]:
    """Relative Synonymous Codon Usage over a corpus of CDS."""
    counts = {c: 0 for c in CODONS}
    n_seq = 0
    for seq in cds_list:
        s = seq.upper().replace("U", "T")
        if len(s) % 3 != 0:
            continue
        n_seq += 1
        for i in range(0, len(s), 3):
            c = s[i : i + 3]
            if c in counts:
                counts[c] += 1
    aa_groups: Dict[str, List[str]] = {}
    for codon, aa in STANDARD_TABLE_1.items():
        if aa != "*":
            aa_groups.setdefault(aa, []).append(codon)
    rscu: Dict[str, float] = {}
    for aa, group in aa_groups.items():
        total = sum(counts[c] for c in group)
        for c in group:
            rscu[c] = (counts[c] * len(group) / total) if total > 0 else 0.0
    return rscu


def cai_weights_from_rscu(rscu: Mapping[str, float]) -> Dict[str, float]:
    """Sharp & Li relative adaptiveness w_i = RSCU_i / max RSCU of the AA."""
    aa_groups: Dict[str, List[str]] = {}
    for codon, aa in STANDARD_TABLE_1.items():
        if aa != "*":
            aa_groups.setdefault(aa, []).append(codon)
    weights: Dict[str, float] = {}
    for aa, group in aa_groups.items():
        best = max(rscu.get(c, 0.0) for c in group)
        for c in group:
            weights[c] = rscu.get(c, 0.0) / best if best > 0 else 0.0
    return weights


def cai(cds: str, weights: Mapping[str, float]) -> float:
    """CAI = geometric mean of w_i over codons of amino acids (stops and
    unknown codons skipped)."""
    s = cds.upper().replace("U", "T")
    if len(s) < 3 or len(s) % 3 != 0:
        raise ValueError("CAI needs a frame-aligned CDS")
    log_w = []
    for i in range(0, len(s), 3):
        c = s[i : i + 3]
        aa = STANDARD_TABLE_1.get(c)
        if aa is None or aa == "*" or c == "ATG" and False:
            continue
        w = weights.get(c, 0.0)
        if w <= 0:
            continue
        log_w.append(math.log(w))
    if not log_w:
        return 0.0
    return math.exp(sum(log_w) / len(log_w))


@lru_cache(maxsize=65536)
def mfe(seq: str) -> float:
    """Minimum free energy via ViennaRNA; returns +inf on import failure so
    callers can detect the missing dependency explicitly."""
    try:
        import RNA
    except ImportError:
        return float("inf")
    s = seq.upper().replace("T", "U")
    fc = RNA.fold_compound(s)
    struct, m = fc.mfe()
    return float(m)


def mfe_batch(seqs: Sequence[str]) -> List[float]:
    try:
        import RNA
    except ImportError:
        return [float("inf")] * len(seqs)
    rna_seqs = [s.upper().replace("T", "U") for s in seqs]
    return [float(RNA.fold(s)[1]) for s in rna_seqs]


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def ned(a: str, b: str) -> float:
    """Normalized edit distance = Levenshtein / max(len) (spec R2)."""
    if not a and not b:
        return 0.0
    return levenshtein(a, b) / max(len(a), len(b))


def pairwise_ned(seqs: Sequence[str], sample_limit: int = 200,
                 rng: Optional[np.random.Generator] = None) -> float:
    """Mean pairwise NED over a sample of pairs (diversity metric).

    Uses rapidfuzz's C++ Levenshtein when available (~1000x faster than the
    pure-Python loop); synonymous variants are same-length so this equals
    the Hamming-based NED.
    """
    n = len(seqs)
    if n < 2:
        return 0.0
    if rng is None:
        rng = np.random.default_rng(0)
    if n > sample_limit:
        sel = rng.choice(n, size=sample_limit, replace=False)
        seqs = [seqs[i] for i in sel]
        n = sample_limit
    try:
        from rapidfuzz.distance import Levenshtein

        total = 0.0
        pairs = 0
        for i in range(n):
            si = seqs[i]
            li = len(si)
            for j in range(i + 1, n):
                sj = seqs[j]
                total += Levenshtein.distance(si, sj) / max(li, len(sj))
                pairs += 1
        return total / max(pairs, 1)
    except ImportError:
        total = 0.0
        pairs = 0
        for i in range(n):
            for j in range(i + 1, n):
                total += ned(seqs[i], seqs[j])
                pairs += 1
        return total / max(pairs, 1)


def unique_fraction(seqs: Sequence[str]) -> float:
    if not seqs:
        return 0.0
    return len(set(seqs)) / len(seqs)


def codon_entropy_per_aa_position(seqs: Sequence[str]) -> float:
    """Mean Shannon entropy of codon choice per amino-acid position
    (EXP-1 'legal but homogeneous' diagnostic)."""
    if not seqs:
        return 0.0
    n = len(seqs)
    codon_lists = [split_codons(s) for s in seqs]
    L = min(len(c) for c in codon_lists)
    total_h = 0.0
    positions = 0
    for i in range(L):
        counts: Dict[str, int] = {}
        for cl in codon_lists:
            c = cl[i]
            counts[c] = counts.get(c, 0) + 1
        if len(counts) < 2:
            continue
        h = -sum((v / n) * math.log(v / n) for v in counts.values())
        total_h += h
        positions += 1
    return total_h / max(positions, 1)


def hypervolume(points: Sequence[Sequence[float]],
                reference_point: Sequence[float]) -> float:
    """Hypervolume of a set of objective vectors to be maximized, with a
    worst-case reference point. Uses pymoo if installed (4-D exact via WFG);
    otherwise a Monte-Carlo estimate (1e6 samples) for tests."""
    pts = np.asarray(points, dtype=float)
    ref = np.asarray(reference_point, dtype=float)
    if pts.size == 0:
        return 0.0
    # Points worse than the reference point on any axis have zero
    # hypervolume contribution by definition; filter instead of raising.
    if not np.all(pts >= ref - 1e-12):
        keep = np.all(pts >= ref - 1e-12, axis=1)
        pts = pts[keep]
        if pts.size == 0:
            return 0.0
    try:
        from pymoo.indicators.hv import HV

        return float(HV(ref_point=-ref)(-pts))
    except ImportError:
        rng = np.random.default_rng(0)
        n_samples = 1_000_000
        lo = ref
        hi = pts.max(axis=0)
        samples = rng.uniform(lo, hi, size=(n_samples, len(ref)))
        dominated = np.zeros(n_samples, dtype=bool)
        for p in pts:
            dominated |= np.all(samples <= p, axis=1) & np.all(samples > ref, axis=1)
        box = np.prod(hi - lo)
        return float(dominated.mean() * box)
