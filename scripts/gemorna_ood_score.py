"""Parse GEMORNA OOD raw generation outputs (mouse/fly) and score them.

Input: gemorna_{gene}_raw.txt — one "<CDS> <naturalness>" line per zero-shot sample.
Output: GEMORNA_{gene}_s0_scored.json (same schema as egfp/nluc scored files).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/codonflow/src")
from codonflow.eval.metrics import cai_weights_from_rscu, cai, mfe_batch

RSCU = json.loads(Path("/home/codonflow/configs/cai_ref_train.json").read_text())
W = cai_weights_from_rscu(RSCU)

REF = {
    "mouse": "/tmp/gene_mouse.fasta",
    "fly": "/tmp/gene_fly.fasta",
}

bases = "TCAG"
aas = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
CODON = {}
_i = 0
for b1 in bases:
    for b2 in bases:
        for b3 in bases:
            CODON[b1 + b2 + b3] = aas[_i]; _i += 1


def translate(nt):
    return "".join(CODON.get(nt[k:k+3], "X") for k in range(0, len(nt), 3))


for gene in ("mouse", "fly"):
    raw = Path(f"/mnt/cunyuliu/gemorna/gemorna_{gene}_raw.txt")
    if not raw.exists():
        print(f"[{gene}] raw missing, skip")
        continue
    ref_nt = "".join(l for l in Path(REF[gene]).read_text().splitlines() if not l.startswith(">"))
    ref_prot = translate(ref_nt)
    if ref_prot.endswith("*"):
        ref_prot = ref_prot[:-1]

    sols, n_ident, n_bad = [], 0, 0
    seen = set()
    for line in raw.read_text().splitlines():
        parts = line.split()
        if not parts:
            continue
        seq, nat = parts[0], (float(parts[1]) if len(parts) > 1 else None)
        if len(seq) % 3 != 0 or not seq.startswith("ATG") or len(seq) < 60:
            n_bad += 1
            continue
        prot = translate(seq)
        if prot != ref_prot:
            n_bad += 1
            continue
        n_ident += 1
        if seq in seen:
            continue
        seen.add(seq)
        sols.append({"seq": seq, "naturalness": nat})

    seqs = [s["seq"] + "TAA" for s in sols]
    cais = [cai(x, W) for x in seqs]
    mfes = mfe_batch(seqs)
    gcs = [(x.count("G") + x.count("C")) / len(x) for x in seqs]
    out = {
        "gene": gene,
        "method": "gemorna",
        "n_samples": sum(1 for l in raw.read_text().splitlines() if l.strip()),
        "n_identity_pass": n_ident,
        "n_unique": len(sols),
        "n_invalid": n_bad,
        "cai_mean": sum(cais) / len(cais) if cais else None,
        "cai_best": max(cais) if cais else None,
        "mfe_mean": sum(mfes) / len(mfes) if mfes else None,
        "gc_mean": sum(gcs) / len(gcs) if gcs else None,
        "solutions": [
            {"seq": x, "naturalness": s["naturalness"], "cai": c, "mfe": m, "gc": g}
            for x, s, c, m, g in zip(seqs, sols, cais, mfes, gcs)
        ],
    }
    dst = Path(f"/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs/GEMORNA_{gene}_s0_scored.json")
    dst.write_text(json.dumps(out, indent=1))
    print(f"[{gene}] identity {n_ident} | unique {len(sols)} | bad {n_bad} | "
          f"CAI {out['cai_mean']:.3f}/{out['cai_best']:.3f} | GC {out['gc_mean']:.3f}" if sols else f"[{gene}] no valid sols")
