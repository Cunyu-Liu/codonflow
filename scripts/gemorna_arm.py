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
import hashlib
import json
import subprocess
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from codonflow.core.codon import normalize_to_dna, translate


def read_fasta_records(path: str):
    """Small standard-library FASTA reader shared by the data-baseline tools."""
    records, header, chunks = [], None, []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header is not None:
                    records.append((header, "".join(chunks)))
                header, chunks = line[1:], []
            elif header is None:
                raise ValueError(f"{path}: sequence encountered before FASTA header")
            else:
                chunks.append(line)
    if header is not None:
        records.append((header, "".join(chunks)))
    return records


GENES = ("egfp", "nluc")


def cds_protein(cds: str, require_terminal_stop: bool = False):
    """Return a stop-free protein, or None for an invalid reading frame/stop."""
    seq = normalize_to_dna(cds.strip())
    if not seq or len(seq) % 3 or any(base not in "ACGT" for base in seq):
        return None
    protein = translate(seq)
    if require_terminal_stop and not protein.endswith("*"):
        return None
    if protein.endswith("*"):
        protein = protein[:-1]
    if not protein or "*" in protein or "X" in protein:
        return None
    return protein


def load_benchmark_protein(path: str, gene: str):
    """Resolve a gene only from its authoritative benchmark FASTA record."""
    aliases = ("nluc", "nanoluc") if gene == "nluc" else (gene,)
    records = read_fasta_records(path)
    if len(records) == 1:
        matches = records
    else:
        matches = [
            (header, cds) for header, cds in records
            if any(alias in header.split()[0].lower() for alias in aliases)
        ]
    if len(matches) != 1:
        raise ValueError(
            f"{path}: expected exactly one FASTA record matching {gene!r}, found {len(matches)}"
        )
    header, cds = matches[0]
    protein = cds_protein(cds, require_terminal_stop=True)
    if protein is None:
        raise ValueError(f"{path}: {header!r} is not a valid CDS with one terminal stop")
    if not normalize_to_dna(cds).startswith("ATG"):
        raise ValueError(f"{path}: {header!r} does not start with ATG")
    return header.split()[0], protein


def protein_sha256(protein: str) -> str:
    return hashlib.sha256(protein.encode("ascii")).hexdigest()


def normalized_identity_pass(cds: str, expected_protein: str):
    """Normalize a GEMORNA CDS and reject every non-identical translation."""
    seq = normalize_to_dna(cds.strip())
    return seq if cds_protein(seq) == expected_protein else None


def score_solutions(solutions, expected_protein: str, weights=None, mfe_fn=None, deduplicate=False):
    """Validate before scoring; never let a wrong protein reach objective metrics."""
    sols, n_invalid, n_identity_pass = [], 0, 0
    seen = set()
    for solution in solutions:
        seq = normalized_identity_pass(solution["seq"], expected_protein)
        if seq is None:
            n_invalid += 1
            continue
        n_identity_pass += 1
        translated = translate(seq)
        if not translated.endswith("*"):
            seq += "TAA"
        if deduplicate and seq in seen:
            continue
        seen.add(seq)
        sols.append({"seq": seq, "naturalness": solution.get("naturalness")})
    if weights is not None:
        from codonflow.eval.metrics import cai
        cais = [cai(s["seq"], weights) for s in sols]
    else:
        cais = [None] * len(sols)
    mfes = mfe_fn([s["seq"] for s in sols]) if mfe_fn is not None else [None] * len(sols)
    gcs = [(s["seq"].count("G") + s["seq"].count("C")) / len(s["seq"]) for s in sols]
    scored = [
        {**s, "cai": c, "mfe": m, "gc": g}
        for s, c, m, g in zip(sols, cais, mfes, gcs)
    ]
    summary = {
        "n": len(scored),
        "n_identity_pass": n_identity_pass,
        "n_unique": len({s["seq"] for s in sols}),
        "n_invalid_identity": n_invalid,
        "cai_mean": sum(cais) / len(cais) if weights is not None and cais else None,
        "mfe_mean": sum(mfes) / len(mfes) if mfe_fn is not None and mfes else None,
        "gc_mean": sum(gcs) / len(gcs) if gcs else None,
        "cai_best": max(cais) if weights is not None and cais else None,
        "mfe_best": min(mfes) if mfe_fn is not None and mfes else None,
    }
    return summary, scored


PY = os.environ.get("CODONFLOW_GEMORNA_PYTHON", "/root/miniconda3/envs/pc_cng/bin/python")
REPO = os.environ.get("CODONFLOW_GEMORNA_REPO", "/teams/HoulabData_1788502323/liucunyu/codonflow/gemorna/gemorna")


def run_generate(protein: str) -> tuple:
    """One zero-shot CDS generation. Returns (cds_nt, naturalness)."""
    res = subprocess.run(
        [PY, "src/generate.py", "--mode", "cds",
         "--ckpt_path", "checkpoints/gemorna_cds.pt",
         "--protein_seq", protein],
        cwd=REPO, capture_output=True, text=True, timeout=600)
    if res.returncode != 0:
        raise RuntimeError(
            f"GEMORNA failed with exit {res.returncode}: "
            f"{res.stderr[-4000:] or res.stdout[-4000:]}"
        )
    lines = [l for l in res.stdout.splitlines() if l.strip()]
    if len(lines) < 2:
        return None, None
    body = lines[-1].split()
    cds = body[0] if body else None
    nat = float(body[1]) if len(body) > 1 else None
    return cds, nat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gene", required=True, choices=GENES)
    ap.add_argument("--benchmark-fasta", required=True,
                    help="authoritative CDS FASTA containing the selected gene")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    benchmark_header, protein = load_benchmark_protein(args.benchmark_fasta, args.gene)
    rows = []
    seen = set()
    n_invalid = 0
    for i in range(args.n):
        cds, nat = run_generate(protein)
        if cds is None:
            n_invalid += 1
            continue
        cds = normalized_identity_pass(cds, protein)
        if cds is None:
            n_invalid += 1
            continue
        if cds in seen:
            continue
        seen.add(cds)
        rows.append({"seq": cds, "naturalness": nat, "gene": args.gene})

    out = {
        "gene": args.gene,
        "method": "gemorna",
        "benchmark_fasta": str(Path(args.benchmark_fasta).resolve()),
        "benchmark_header": benchmark_header,
        "expected_protein_sha256": protein_sha256(protein),
        "expected_protein_length_aa": len(protein),
        "n_requested": args.n,
        "n_unique": len(rows),
        "n_identity_pass": len(rows),
        "n_invalid_identity": n_invalid,
        "n_invalid_skipped": n_invalid,
        "seed": args.seed,
        "reproducibility_note": "arm label only; official generator exposes no seed option",
        "solutions": rows,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1)
    print(f"[gemorna:{args.gene}] unique {len(rows)}/{args.n} (invalid {n_invalid}) -> {args.out}")


if __name__ == "__main__":
    main()
