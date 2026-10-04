"""Three-legged scorers (spec R2-3 / Task 2.2.4): all zero-learning.

  1. CAI calculator (pure table lookup from RSCU reference)
  2. RNAfold 2.6.4 via ViennaRNA Python API (batch folding)
  3. Translation cycle consistency (deterministic codon table)

Interface: scorers.score_batch(seqs) -> dict of metric arrays.
Caching: terminal-sequence SHA1 -> (CAI, MFE, GC, motif) LRU cache for the
RNAfold-heavy guided rollout loop (Task 2.2.3, expected hit rate >= 60%).
"""
from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from typing import Callable, Dict, List, Mapping, Optional, Sequence

from ..core.codon import gc_fraction, is_synonymous, normalize_to_dna, translate
from ..core.motifs import motif_penalty_score
from ..eval.metrics import cai as cai_fn


class LRUCache:
    def __init__(self, capacity: int = 200_000):
        self.capacity = capacity
        self._data: "OrderedDict[str, tuple]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str):
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self.hits += 1
                return self._data[key]
            self.misses += 1
            return None

    def put(self, key: str, value: tuple) -> None:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
            self._data[key] = value
            if len(self._data) > self.capacity:
                self._data.popitem(last=False)

    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def stats(self) -> Dict[str, float]:
        return {"hits": self.hits, "misses": self.misses, "hit_rate": self.hit_rate()}


def _sha1(seq: str) -> str:
    return hashlib.sha1(seq.encode()).hexdigest()


class RNAFoldScorer:
    """ViennaRNA 2.6.4 MFE scorer with strict version assertion."""

    REQUIRED_VERSION = "2.6.4"

    def __init__(self, strict_version: bool = False):
        import RNA

        self._RNA = RNA
        self.version = RNA.__version__
        if strict_version and self.version != self.REQUIRED_VERSION:
            raise RuntimeError(
                f"ViennaRNA version {self.version} != required {self.REQUIRED_VERSION}"
            )

    def fold_batch(self, seqs: Sequence[str]) -> List[float]:
        out: List[float] = []
        for s in seqs:
            rna = normalize_to_dna(s).replace("T", "U")
            fc = self._RNA.fold_compound(rna)
            _struct, m = fc.mfe()
            out.append(float(m))
        return out


class Scorers:
    """Bundle the three zero-learning scorers + metric cache."""

    def __init__(
        self,
        cai_weights: Mapping[str, float],
        rna_scorer: Optional[RNAFoldScorer] = None,
        cache_capacity: int = 200_000,
    ):
        self.cai_weights = dict(cai_weights)
        self.rna = rna_scorer
        self.cache = LRUCache(cache_capacity)
        self._rna_available = self.rna is not None

    def _mfe_batch(self, seqs: Sequence[str]) -> List[float]:
        if self._rna_available:
            return self.rna.fold_batch(seqs)
        from ..eval.metrics import mfe_batch

        return mfe_batch(seqs)

    def score_batch(self, seqs: Sequence[str]) -> Dict[str, List[float]]:
        """Score a batch of CDS sequences; returns CAI/MFE/GC/motif arrays."""
        results: Dict[str, List[float]] = {
            "cai": [0.0] * len(seqs),
            "mfe": [0.0] * len(seqs),
            "gc": [0.0] * len(seqs),
            "motif": [0.0] * len(seqs),
        }
        missing_idx: List[int] = []
        for i, s in enumerate(seqs):
            key = _sha1(s)
            cached = self.cache.get(key)
            if cached is not None:
                c, m, g, mo = cached
                results["cai"][i] = c
                results["mfe"][i] = m
                results["gc"][i] = g
                results["motif"][i] = mo
            else:
                missing_idx.append(i)
        if missing_idx:
            missing_seqs = [seqs[i] for i in missing_idx]
            mfes = self._mfe_batch(missing_seqs)
            for j, i in enumerate(missing_idx):
                s = seqs[i]
                c = cai_fn(s, self.cai_weights)
                g = gc_fraction(s)
                mo = motif_penalty_score(s)
                m = mfes[j]
                results["cai"][i] = c
                results["mfe"][i] = m
                results["gc"][i] = g
                results["motif"][i] = mo
                self.cache.put(_sha1(s), (c, m, g, mo))
        return results

    def translation_consistency(self, y: str, x: str) -> int:
        """Deterministic hard translation cycle check: 1[Trans(y)==Trans(x)]."""
        return int(translate(y) == translate(x))
