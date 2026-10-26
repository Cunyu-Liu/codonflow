"""Evaluate GEMORNA solutions after authoritative protein-identity checks.

The benchmark FASTA, not a hardcoded protein, defines the expected translation.
A terminal stop is appended only when GEMORNA omitted it.
"""
import argparse
import json
from pathlib import Path

try:
    from .gemorna_arm import load_benchmark_protein, protein_sha256, score_solutions
except ImportError:
    from gemorna_arm import load_benchmark_protein, protein_sha256, score_solutions

DEFAULT_EVAL_DIR = Path("/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark-fasta", required=True)
    ap.add_argument("--rscu-json", default="/home/codonflow/configs/cai_ref_train.json")
    ap.add_argument("--genes", nargs="+", choices=("egfp", "nluc"), default=["egfp", "nluc"])
    ap.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR)
    ap.add_argument("--out-dir", type=Path, help="defaults to --eval-dir")
    args = ap.parse_args()

    from codonflow.eval.metrics import cai_weights_from_rscu, mfe_batch

    rscu = json.loads(Path(args.rscu_json).read_text())
    weights = cai_weights_from_rscu(rscu)
    out_dir = args.out_dir or args.eval_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    for gene in args.genes:
        benchmark_header, protein = load_benchmark_protein(args.benchmark_fasta, gene)
        expected_sha = protein_sha256(protein)
        src = args.eval_dir / f"GEMORNA_{gene}_s0.json"
        d = json.loads(src.read_text())
        if d.get("expected_protein_sha256", expected_sha) != expected_sha:
            raise ValueError(f"{src}: generation protein differs from {args.benchmark_fasta}")
        summary, scored = score_solutions(d["solutions"], protein, weights, mfe_batch)
        out = {
            "gene": gene,
            "method": "gemorna",
            "benchmark_header": benchmark_header,
            "expected_protein_sha256": expected_sha,
            "n_samples": len(d["solutions"]),
            "note": "identity checked against benchmark FASTA; missing terminal stop replaced by TAA",
            **summary,
            "solutions": scored,
        }
        dst = out_dir / f"GEMORNA_{gene}_s0_scored.json"
        dst.write_text(json.dumps(out, indent=1))
        print(f"[{gene}] n={out['n']} invalid_identity={out['n_invalid_identity']} -> {dst}")


if __name__ == "__main__":
    main()
