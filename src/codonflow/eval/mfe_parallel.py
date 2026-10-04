"""Parallel MFE folding with a process pool (ViennaRNA releases the GIL).

RNA.fold_compound is pure C; a ThreadPoolExecutor achieves near-linear
speedup for folding workloads. Fallback: serial mfe_batch.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Sequence

_THREADS = 16


def mfe_batch_parallel(seqs: Sequence[str], n_threads: int = _THREADS) -> List[float]:
    import RNA

    def fold(s: str) -> float:
        fc = RNA.fold_compound(s.upper().replace("T", "U"))
        _struct, m = fc.mfe()
        return float(m)

    if len(seqs) < 8:
        return [fold(s) for s in seqs]
    with ThreadPoolExecutor(max_workers=n_threads) as ex:
        return list(ex.map(fold, seqs))
