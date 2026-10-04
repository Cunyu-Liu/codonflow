"""LinearDesign benchmark runner (Task 1.2.2): per-sequence timing baseline.

Runs the official binary N times per protein, records wall-clock time and
sequence metrics (CAI/MFE via our ViennaRNA 2.6.4), appends to REGISTRY.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.core.codon import protein_of_cds, translate, normalize_to_dna
from codonflow.eval.metrics import cai, cai_weights_from_rscu, mfe

LD_BIN = "/home/cunyuliu/codonflow/third_party/LinearDesign/bin/LinearDesign_2D"
LD_DIR = "/home/cunyuliu/codonflow/third_party/LinearDesign"
CODON_TABLE = "codon_usage_freq_table_human.csv"

SEQ_RE = re.compile(r"mRNA sequence:\s*([ACGUacgu]+)")
MFE_RE = re.compile(r"mRNA folding free energy:\s*([-+]?\d+(?:\.\d+)?)")
CAI_RE = re.compile(r"mRNA CAI:\s*([-+]?\d+(?:\.\d+)?)")


def run_lineardesign(protein: str, lam: str = "0") -> dict:
    t0 = time.time()
    proc = subprocess.run(
        [LD_BIN, lam, "0", CODON_TABLE],
        input=protein,
        capture_output=True,
        text=True,
        cwd=LD_DIR,
    )
    elapsed = time.time() - t0
    out = proc.stdout
    seq = SEQ_RE.search(out).group(1) if SEQ_RE.search(out) else ""
    mfe_val = float(MFE_RE.search(out).group(1)) if MFE_RE.search(out) else None
    cai_val = float(CAI_RE.search(out).group(1)) if CAI_RE.search(out) else None
    return {
        "elapsed_s": elapsed,
        "seq": seq,
        "ld_mfe": mfe_val,
        "ld_cai": cai_val,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark-fasta", required=True, help="CDS fasta of benchmarks")
    ap.add_argument("--rscu-json", default="/home/cunyuliu/codonflow/configs/cai_ref_train.json")
    ap.add_argument("--n-repeats", type=int, default=3)
    ap.add_argument("--out", default="/mnt/cunyuliu/codonflow/eval_outputs/E1_lineardesign_bench.json")
    args = ap.parse_args()
    rscu = json.loads(Path(args.rscu_json).read_text())
    weights = cai_weights_from_rscu(rscu)
    from codonflow.data.dataset import read_fasta

    results = []
    for header, cds in read_fasta(args.benchmark_fasta):
        protein = protein_of_cds(cds)
        name = header.split()[0]
        times = []
        best = None
        for rep in range(args.n_repeats):
            r = run_lineardesign(protein)
            times.append(r["elapsed_s"])
            if best is None or r["elapsed_s"] < best["elapsed_s"]:
                best = r
        seq_dna = normalize_to_dna(best["seq"]) + "TAA" if best["seq"] else ""
        identity = translate(seq_dna) == translate(cds) if seq_dna else False
        our_mfe = mfe(seq_dna) if seq_dna else None
        our_cai = cai(seq_dna, weights) if seq_dna else None
        entry = {
            "name": name,
            "n_aa": len(protein),
            "times_s": [round(t, 2) for t in times],
            "mean_time_s": round(statistics.mean(times), 2),
            "identity_kept": identity,
            "our_cai": our_cai,
            "our_mfe": our_mfe,
            "ld_reported_cai": best["ld_cai"],
            "ld_reported_mfe": best["ld_mfe"],
        }
        results.append(entry)
        print(json.dumps(entry), flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
