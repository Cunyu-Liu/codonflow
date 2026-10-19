#!/usr/bin/env python3
"""Offline S3 recomputation with per-gene adaptive HV reference points."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/codonflow/src")
from codonflow.eval.metrics import hypervolume  # noqa: E402

DATA = Path("/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs")
OUT = DATA / "S3R_adaptive_summary.json"

METHODS = ["codonflow", "lineardesign_scan", "codongpt", "cai_greedy", "uniform_edit_flow"]
GENE_TAGS = ("cas9", "fly", "yeast")


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
        if not p.stem.replace("S3R_", "").startswith(GENE_TAGS):
            continue  # skip S3R_adaptive_summary and other non-arm files
        tag = p.stem.replace("S3R_", "")
        try:
            row = load_arm(p)
        except Exception:
            continue
        if row is None or "S3_quad/codonflow/obj_vectors" not in row:
            print(f"[{tag}] no obj_vectors — skipped")
            continue
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
        print(f"[{tag:12s}] CF {cf:12.2f} | LD {ld:12.2f} | GPT {gp:12.2f}")

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
