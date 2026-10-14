"""Evaluate GEMORNA solutions on our objective axes (protocol parity with E5).

Appends terminal stop codon (GEMORNA CDS omits it; our legality requires single
terminal stop), then computes CAI (train RSCU ref), MFE (ViennaRNA), GC.
Writes GEMORNA_{gene}_s0_scored.json with per-solution objective vectors,
plus a compact summary ready for the benchmark master table.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/cunyuliu/codonflow/src")
from codonflow.eval.metrics import cai_weights_from_rscu, cai, mfe_batch

RSCU = json.loads(Path("/home/cunyuliu/codonflow/configs/cai_ref_train.json").read_text())
W = cai_weights_from_rscu(RSCU)

for gene in ("egfp", "nluc"):
    src = Path(f"/mnt/cunyuliu/codonflow/eval_outputs/GEMORNA_{gene}_s0.json")
    d = json.loads(src.read_text())
    sols = d["solutions"]
    # append canonical terminal stop (TAA) to match our legality frame
    seqs = [s["seq"] + "TAA" for s in sols]
    cais = [cai(x, W) for x in seqs]
    mfes = mfe_batch(seqs)
    gcs = [(x.count("G") + x.count("C")) / len(x) for x in seqs]
    scored = [
        {"seq": x, "naturalness": s["naturalness"], "cai": c, "mfe": m, "gc": g}
        for x, s, c, m, g in zip(seqs, sols, cais, mfes, gcs)
    ]
    out = {
        "gene": gene,
        "method": "gemorna",
        "n": len(scored),
        "note": "terminal TAA appended (GEMORNA omits stop); objectives identical pipeline to E5",
        "cai_mean": sum(cais) / len(cais),
        "mfe_mean": sum(mfes) / len(mfes),
        "gc_mean": sum(gcs) / len(gcs),
        "cai_best": max(cais),
        "mfe_best": min(mfes),
        "solutions": scored,
    }
    dst = Path(f"/mnt/cunyuliu/codonflow/eval_outputs/GEMORNA_{gene}_s0_scored.json")
    dst.write_text(json.dumps(out, indent=1))
    print(f"[{gene}] n={len(scored)} cai={out['cai_mean']:.3f} mfe={out['mfe_mean']:.1f} gc={out['gc_mean']:.3f} -> {dst.name}")
