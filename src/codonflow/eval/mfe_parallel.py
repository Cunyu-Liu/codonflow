"""Parallel MFE folding with a process pool.

ViennaRNA's Python binding does NOT release the GIL (threads are slower
than serial - measured 63.6s vs 55.7s on 200 seqs); processes achieve
12x speedup (4.6s vs 55.7s with 16 workers, results bit-identical).
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from typing import List, Sequence

_N_PROC = 16


def _fold_one(s: str) -> float:
    import RNA

    fc = RNA.fold_compound(s.upper().replace("T", "U"))
    _struct, m = fc.mfe()
    return float(m)


def mfe_batch_parallel(seqs: Sequence[str], n_procs: int = _N_PROC) -> List[float]:
    if len(seqs) < 8:
        return [_fold_one(s) for s in seqs]
    if __name__ == "__main__":
        return [_fold_one(s) for s in seqs]
    with ProcessPoolExecutor(max_workers=n_procs) as ex:
        return list(ex.map(_fold_one, seqs))
