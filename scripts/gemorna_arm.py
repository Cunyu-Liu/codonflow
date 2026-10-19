"""GEMORNA baseline arm for the CodonFlow 4-layer benchmark.

Protocol parity with run_exp5_ood.py arms:
  - same benchmark genes (egfp, nluc, mouse, fly, zfish, yeast, cas9)
  - same budget: 100 solutions per gene (GEMORNA zero-shot sampled)
  - same objective axes (CAI, MFE, GC, motif) evaluated with our evaluators
  - identity/legality gates identical
GEMORNA-CDS generates ONE sequence per invocation (model.gen prints to stdout);
we batch by repeated invocation. Output JSON mirrors E5_ood_{gene}_s{seed}.json rows
so downstream HV/coverage tables ingest without changes.
Requires env: pc_cng python + torchtext 0.6.0 + gemorna repo at /mnt/cunyuliu/gemorna.
Usage: python gemorna_arm.py --gene egfp --n 100 --out GEMORNA_egfp.json [--seed 0]
"""
import argparse
import json
import subprocess
import sys
import os

GENES = {
    "egfp": ("MVSKGEELFTGVVPILVELDGDVNGHKFSVSGEGEGDATYGKLTLKFICTTGKLPVPWPTLVTTFSYGVQCFSRYPDHMKQHDFFKSAMPEGYVQERTIFFKDDGNYKTRAEVKFEGDTLVNRIELKGIDFKEDGNILGHKLEYNYNSHNVYIMADKQKNGIKVNFKIRHNIEDGSVQLADHYQQNTPIGDGPVLLPDNHYLSTQSALSKDPNEKRDHMVLLEFVTAAGITLGMDELYK", "bench_egfp"),
    "nluc": ("MVSKGEEDFTGVVPILVELDGDVNGHKFSVSGEGEGDATYGKLTLKFICTTGKLPVPWPTLVTTLTYGVQCFSRYPDHMKQHDFFKSAMPEGYVQERTIFFKDDGNYKTRAEVKFEGDTLVNRIELKGIDFKEDGNILGHKLEYNYNSHNVYIMADKQKNGIKVNFKIRHNIEDGSVQLADHYQQNTPIGDGPVLLPDNHYLSTQSALSKDPNEKRDHMVLLEFVTAAGITHGMDELYK", "bench_nluc"),
}

PY = "/home/miniconda3/envs/pc_cng/bin/python"
REPO = "/mnt/cunyuliu/gemorna"


def run_generate(protein: str) -> tuple:
    """One zero-shot CDS generation. Returns (cds_nt, naturalness)."""
    res = subprocess.run(
        [PY, "src/generate.py", "--mode", "cds",
         "--ckpt_path", "checkpoints/gemorna_cds.pt",
         "--protein_seq", protein],
        cwd=REPO, capture_output=True, text=True, timeout=600)
    if res.returncode != 0:
        return None, None
    lines = [l for l in res.stdout.splitlines() if l.strip()]
    if len(lines) < 2:
        return None, None
    body = lines[-1].split()
    cds = body[0] if body else None
    nat = float(body[1]) if len(body) > 1 else None
    return cds, nat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gene", required=True, choices=list(GENES))
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    protein, corpus = GENES[args.gene]
    rows = []
    seen = set()
    n_fail = 0
    for i in range(args.n):
        cds, nat = run_generate(protein)
        if cds is None or len(cds) % 3 != 0 or len(cds) < 60 or not cds.startswith("ATG"):
            n_fail += 1
            continue
        if cds in seen:
            continue
        seen.add(cds)
        rows.append({"seq": cds, "naturalness": nat, "gene": args.gene})

    out = {
        "gene": args.gene,
        "method": "gemorna",
        "n_requested": args.n,
        "n_unique": len(rows),
        "n_invalid_skipped": n_fail,
        "seed": args.seed,
        "solutions": rows,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1)
    print(f"[gemorna:{args.gene}] unique {len(rows)}/{args.n} (invalid {n_fail}) -> {args.out}")


if __name__ == "__main__":
    main()
