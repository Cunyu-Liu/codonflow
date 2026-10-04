"""Amendment A2 calibration: measure 5/95 quantiles of the four ATC axes
from the Task 1.2 baseline solution set (A1's prescribed procedure).

Baseline solution set per source gene:
  - codonGPT constrained samples (AR preference, n=100/gene)
  - LinearDesign solution (balanced DP optimum)
  - uniform synonymous samples (unconstrained diversity, n=100/gene)
This mixes strong and weak solutions so the quantiles span the reachable
range (A1: 'calibration stats from Task 1.2 baseline solutions').

Writes configs/atc_norm.yaml (v2) with SIGNED quantiles for the negative
axes (the v1 file stored magnitudes, which clamped f3/f4 to 0 forever —
the bug this amendment fixes).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.core.codon import (
    SYNONYMOUS_CODONS,
    gc_fraction,
    normalize_to_dna,
    protein_of_cds,
    split_codons,
    translate,
)
from codonflow.data.dataset import read_fasta
from codonflow.eval.metrics import cai, cai_weights_from_rscu
from codonflow.eval.mfe_parallel import mfe_batch_parallel
from codonflow.core.motifs import motif_penalty_score


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark-fasta", required=True)
    ap.add_argument("--codongpt-json", default="/mnt/cunyuliu/codonflow/eval_outputs/E1_codongpt.json")
    ap.add_argument("--ld-json", default="/mnt/cunyuliu/codonflow/eval_outputs/E1_lineardesign_bench.json")
    ap.add_argument("--rscu-json", default="/home/cunyuliu/codonflow/configs/cai_ref_train.json")
    ap.add_argument("--n-uniform", type=int, default=100)
    ap.add_argument("--out", default="/home/cunyuliu/codonflow/configs/atc_norm.yaml")
    args = ap.parse_args()

    weights = cai_weights_from_rscu(json.loads(Path(args.rscu_json).read_text()))

    sols: list[str] = []

    cg = json.loads(Path(args.codongpt_json).read_text())
    for r in cg.get("results", []):
        sols.extend(r.get("samples_head", []))

    ld = json.loads(Path(args.ld_json).read_text())
    for r in ld:
        if "solution" in r:
            sols.append(r["solution"])

    rng = np.random.default_rng(0)
    for header, cds in read_fasta(args.benchmark_fasta):
        for _ in range(args.n_uniform):
            out = []
            for c in split_codons(normalize_to_dna(cds)):
                from codonflow.core.codon import STANDARD_TABLE_1

                aa = STANDARD_TABLE_1[c]
                if aa == "*":
                    out.append(c)
                    continue
                group = list(SYNONYMOUS_CODONS[aa])
                out.append(group[int(rng.integers(0, len(group)))])
            sols.append("".join(out))

    sols = [s for s in sols if len(s) >= 60 and set(s.upper()) <= set("ACGT")]
    print(f"baseline solution set: {len(sols)} sequences")

    cais = np.array([cai(s, weights) for s in sols])
    mfes = np.array(mfe_batch_parallel(sols, n_procs=16))
    neg_mfes = -mfes
    neg_gc_devs = np.array([-abs(gc_fraction(s) - 0.55) for s in sols])
    neg_motifs = np.array([-motif_penalty_score(s) for s in sols])

    def q(vals, p):
        return float(np.quantile(vals, p))

    stats = {
        "cai": {"q5": q(cais, 0.05), "q95": q(cais, 0.95)},
        "neg_mfe": {"q5": q(neg_mfes, 0.05), "q95": q(neg_mfes, 0.95)},
        "neg_gc_dev": {"q5": q(neg_gc_devs, 0.05), "q95": q(neg_gc_devs, 0.95)},
        "neg_motif": {"q5": q(neg_motifs, 0.05), "q95": q(neg_motifs, 0.95)},
    }
    print(json.dumps(stats, indent=2))

    lines = [
        "# ATC normalization stats v2 (Amendment A2, 2026-10-05):",
        "# measured 5/95 quantiles from the Task 1.2 baseline solution set",
        "# (codonGPT constrained + LinearDesign + uniform synonymous samples).",
        "# v1 stored MAGNITUDES for neg_gc_dev/neg_motif which clamped both axes",
        "# to 0 (dead axes, U collapsed to ~0.01, Doob-h guidance ineffective).",
        "# v2 stores SIGNED quantiles so normalization maps the true reachable",
        "# range onto [0,1] as A1 intended. Editing requires an amendment.",
    ]
    for axis in ("cai", "neg_mfe", "neg_gc_dev", "neg_motif"):
        lines.append(f"{axis}:")
        lines.append(f"  q5: {stats[axis]['q5']:.6g}")
        lines.append(f"  q95: {stats[axis]['q95']:.6g}")
    lines.append("omega: [1.0, 1.0, 1.0, 0.5]")
    lines.append("rho: 0.01")
    lines.append("beta: 1.0")
    lines.append("gc_target: 0.55")
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
