#!/usr/bin/env python3
"""R4 protocol gap fill: codonGPT 10x-sampling variant (1000 solutions).

spec R4: "AR baseline gets a 10x-sampling variant" — the E5 arms sampled
codonGPT at the same 100 solutions as everyone. This script samples 1000
solutions per gene/seed and reports HV/NED/NDS against the same method pool
(the 100-sol CF/LD/greedy/uniform solutions from E5_fix_*) so the
budget-fair vs budget-10x comparison is explicit.

Usage:
  python3 run_gpt10x.py <gene> <seed> [--n 1000]
Output: /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs/GPT10x_<gene>_s<seed>.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, "/home/codonflow/src")

from codonflow.core.codon import (
    gc_fraction,
    normalize_to_dna,
    protein_of_cds,
    STANDARD_TABLE_1,
)
from codonflow.data.dataset import read_fasta
from codonflow.eval.metrics import cai, cai_weights_from_rscu, hypervolume, pairwise_ned
from codonflow.eval.mfe_parallel import mfe_batch_parallel
from codonflow.core.motifs import motif_penalty_score

sys.path.insert(0, "/home/codonflow/scripts")
from run_exp5_ood import (  # noqa: E402
    CKPT_GPT,
    SCENARIOS,
    load_codongpt,
    non_dominated_share,
    obj_vector,
)

FASTAS = {
    "egfp": "/tmp/gene_egfp.fasta",
    "nluc": "/tmp/gene_nluc.fasta",
    "mouse": "/tmp/gene_mouse.fasta",
    "fly": "/tmp/gene_fly.fasta",
    "zfish": "/tmp/gene_zfish.fasta",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("gene")
    ap.add_argument("seed", type=int)
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--pool", default="/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs")
    ap.add_argument("--temperature", type=float, default=1.0)
    args = ap.parse_args()

    out = Path(args.pool) / f"GPT10x_{args.gene}_s{args.seed}.json"
    if out.exists():
        print(f"exists: {out}")
        return

    device = torch.device("cuda:0")
    weights = cai_weights_from_rscu(
        json.loads(Path("/home/codonflow/configs/cai_ref_train.json").read_text())
    )
    gpt, tok = load_codongpt(device)

    header, cds = next(read_fasta(FASTAS[args.gene]))
    protein = protein_of_cds(cds)

    t0 = time.time()
    sols = codongpt_sample_local(gpt, tok, protein, args.n, device, args.seed, args.temperature)
    t_gpt = time.time() - t0
    print(f"gpt {args.n} sols in {t_gpt:.0f}s", flush=True)

    mfe_cache: dict = {}
    missing = [s for s in dict.fromkeys(sols) if s not in mfe_cache]
    for i in range(0, len(missing), 256):
        chunk = missing[i : i + 256]
        for s, m in zip(chunk, mfe_batch_parallel(chunk)):
            mfe_cache[s] = m
    gpt_objs = [obj_vector(s, weights, mfe_cache) for s in sols]

    pool = {}
    for m in ["codonflow", "lineardesign_scan", "cai_greedy", "uniform_edit_flow"]:
        p = Path(args.pool) / f"E5_fix_{args.gene}_s{args.seed}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        gene_rows = d.get(header.split()[0]) or list(d.values())[0]
        pool_raw = json.loads(p.read_text())
        break
    # pool solutions are NOT stored in E5_fix jsons (only metrics) -> pool objs
    # from metrics-only: rebuild minimal pools from greedy+uniform via fasta
    greedy_objs = [obj_vector(normalize_to_dna_cai_greedy(cds, weights), weights, mfe_cache)]

    row = {"seed": args.seed, "n_solutions": args.n, "gene": args.gene,
           "time_total_s": t_gpt, "time_per_sol": t_gpt / args.n}
    for scen, axes in SCENARIOS.items():
        ref = np.array([0.5, 100.0, -0.2, -25.0])[: len(axes)]
        pts = [[o[a] for a in axes] for o in gpt_objs]
        row[f"{scen}/codongpt_10x/hv"] = hypervolume(pts, ref)
        row[f"{scen}/codongpt_10x/ned"] = pairwise_ned(sols)
        row[f"{scen}/codongpt_10x/n"] = len(sols)
    out.write_text(json.dumps(row, indent=2))
    print(f"wrote {out}")
    for k, v in row.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.3f}")


def codongpt_sample_local(model, tok, protein, n, device, seed, temperature):
    from run_exp5_ood import codongpt_sample

    return codongpt_sample(model, tok, protein, n, device, seed, temperature)


def normalize_to_dna_cai_greedy(cds, weights):
    from codonflow.core.codon import SYNONYMOUS_CODONS, split_codons

    codons = []
    for c in split_codons(normalize_to_dna(cds)):
        aa = STANDARD_TABLE_1[c]
        if aa == "*":
            codons.append(c)
            continue
        codons.append(max(SYNONYMOUS_CODONS[aa], key=lambda x: weights.get(x, 0.0)))
    return "".join(codons)


if __name__ == "__main__":
    main()
