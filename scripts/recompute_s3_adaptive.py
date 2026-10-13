#!/usr/bin/env python3
"""Offline S3 recomputation with per-gene adaptive HV reference points.

Reads S3R_*.json (obj_vectors stored per method/scenario), computes HV
with a per-gene reference = (per-axis worst across ALL methods' pooled
solutions) - margin, and reports the S3 table that the fixed-ref scheme
zeroed out (Cas9/fly/yeast).

Usage: python3 recompute_s3_adaptive.py
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/cunyuliu/codonflow/src")
from codonflow.eval.metrics import hypervolume  # noqa: E402

DATA = Path("/mnt/cunyuliu/codonflow/eval_outputs")
OUT = Path("/mnt/cunyuliu/codonflow/eval_outputs/S3R_adaptive_summary.json")

METHODS = ["codonflow", "lineardesign_scan", "codongpt", "cai_greedy", "uniform_edit_flow"]


def load_arm(path):
    d = json.loads(path.read_text())
    for gene_rows in d.values():
        return gene_rows[0]
    return None


def main():
    results = {}
    print("=" * 88)
    print("S3 ADAPTIVE-REF RECOMPUTATION  (per-gene ref = pooled per-axis min - 5% margin)")
    print("=" * 88)
    for p in sorted(DATA.glob("S3R_*.json")):
        tag = p.stem.replace("S3R_", "")
        row = load_arm(p)
        if row is None or "S3_quad/codonflow/obj_vectors" not in row:
            print(f"[{tag}] no obj_vectors — skipped")
            continue
        # gather all methods' S3 objective vectors (axes: cai, neg_mfe, neg_gc_dev, neg_motif)
        pool = {}
        for m in METHODS:
            k = f"S3_quad/{m}/obj_vectors"
            if k in row:
                pool[m] = np.asarray(row[k], dtype=float)
        if "codonflow" not in pool:
            continue
        allpts = np.vstack([v for v in pool.values() if len(v)])
        ref = np.array([allpts[:, i].min() - 0.05 * abs(allpts[:, i].min()) - 1e-6 for i in range(allpts.shape[1])])
        line = {"n_methods": len(pool), "ref": [float(r) for r in ref]}
        for m, v in pool.items():
            hv = hypervolume(v.tolist(), ref) if len(v) else 0.0
            line[f"{m}/hv"] = float(hv)
        results[tag] = line
        cf = line.get("codonflow/hv", 0.0)
        ld = line.get("lineardesign_scan/hv", 0.0)
        gp = line.get("codongpt/hv", 0.0)
        print(f"[{tag:12s}] CF {cf:12.2f} | LD {ld:12.2f} | GPT {gp:12.2f} (ref={np.round(ref, 2).tolist()})")

    OUT.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT}")

    if results:
        print("\n=== summary (mean over arms) ===")
        for m in METHODS:
            vals = [r.get(f"{m}/hv") for r in results.values() if r.get(f"{m}/hv") is not None]
            if vals:
                print(f"  {m:22s} {np.mean(vals):12.2f} (n={len(vals)})")


if __name__ == "__main__":
    main()
