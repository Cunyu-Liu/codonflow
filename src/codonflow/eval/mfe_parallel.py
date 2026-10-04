"""Parallel MFE folding with a persistent process pool.

ViennaRNA's Python binding does NOT release the GIL (threads are slower
than serial - measured 63.6s vs 55.7s on 200 seqs); processes achieve
12x speedup (4.6s vs 55.7s with 16 workers, results bit-identical).

A module-level persistent pool avoids paying fork+import-RNA startup
(~2-4s) on every batch: EXP-3 issues ~1400 small batches, where a
per-call pool would cost ~80 extra minutes.
"""
from __future__ import annotations

import atexit
import os
from concurrent.futures import ProcessPoolExecutor
from typing import List, Optional, Sequence

_N_PROC = 16
_pool: Optional[ProcessPoolExecutor] = None


def _fold_one(s: str) -> float:
    import RNA

    fc = RNA.fold_compound(s.upper().replace("T", "U"))
    _struct, m = fc.mfe()
    return float(m)


def _get_pool(n_procs: int) -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=n_procs)
        atexit.register(_pool.shutdown, wait=False)
    return _pool


def mfe_batch_parallel(seqs: Sequence[str], n_procs: int = _N_PROC) -> List[float]:
    if len(seqs) < 8:
        return [_fold_one(s) for s in seqs]
    if __name__ == "__main__":
        return [_fold_one(s) for s in seqs]
    try:
        pool = _get_pool(n_procs)
        return list(pool.map(_fold_one, seqs))
    except Exception:
        with ProcessPoolExecutor(max_workers=n_procs) as ex:
            return list(ex.map(_fold_one, seqs))
