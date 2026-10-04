"""Standalone MFE benchmark: threads vs processes for ViennaRNA folding."""
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

sys.path.insert(0, "src")
import numpy as np

from codonflow.core.codon import SYNONYMOUS_CODONS, STANDARD_TABLE_1

src = open("/mnt/cunyuliu/codonflow/corpora/nanoluc_cds.fasta").read().split("\n")[1]
rng = np.random.default_rng(1)
codons = [src[i : i + 3] for i in range(0, len(src), 3)]
seqs = []
for _ in range(200):
    out = []
    for c in codons:
        aa = STANDARD_TABLE_1[c]
        if aa == "*":
            out.append(c)
        else:
            opts = list(SYNONYMOUS_CODONS[aa])
            out.append(opts[rng.integers(0, len(opts))])
    seqs.append("".join(out))


def fold(s: str) -> float:
    import RNA

    fc = RNA.fold_compound(s.upper().replace("T", "U"))
    _st, m = fc.mfe()
    return float(m)


t0 = time.time()
serial = [fold(s) for s in seqs]
print("serial: %.1f s" % (time.time() - t0))

t0 = time.time()
with ThreadPoolExecutor(max_workers=16) as ex:
    th = list(ex.map(fold, seqs))
print("threads16: %.1f s, same=%s" % (time.time() - t0, th == serial))

if __name__ == "__main__":
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=16) as ex:
        pr = list(ex.map(fold, seqs))
    print("procs16: %.1f s, same=%s" % (time.time() - t0, pr == serial))
