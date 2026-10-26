"""Parse GEMORNA OOD raw outputs and score only benchmark-identical CDS.

Input raw lines contain "<CDS> <naturalness>". References are resolved from
an explicit benchmark FASTA rather than temporary, hardcoded paths.
"""
import argparse
import json
from pathlib import Path

try:
    from .gemorna_arm import load_benchmark_protein, protein_sha256, score_solutions
except ImportError:
    from gemorna_arm import load_benchmark_protein, protein_sha256, score_solutions

DEFAULT_RAW_DIR = Path("/mnt/cunyuliu/gemorna")
DEFAULT_EVAL_DIR = Path("/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs")


def parse_raw_solutions(text: str):
    solutions = []
    for line in text.splitlines():
        parts = line.split()
        if parts:
            solutions.append({
                "seq": parts[0],
                "naturalness": float(parts[1]) if len(parts) > 1 else None,
            })
    return solutions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark-fasta", required=True)
    ap.add_argument("--rscu-json", default="/home/codonflow/configs/cai_ref_train.json")
    ap.add_argument("--genes", nargs="+", default=["mouse", "fly"])
    ap.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_EVAL_DIR)
    args = ap.parse_args()

    from codonflow.eval.metrics import cai_weights_from_rscu, mfe_batch

    weights = cai_weights_from_rscu(json.loads(Path(args.rscu_json).read_text()))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for gene in args.genes:
        raw = args.raw_dir / f"gemorna_{gene}_raw.txt"
        if not raw.exists():
            print(f"[{gene}] raw missing, skip")
            continue
        benchmark_header, protein = load_benchmark_protein(args.benchmark_fasta, gene)
        raw_solutions = parse_raw_solutions(raw.read_text())
        summary, scored = score_solutions(
            raw_solutions, protein, weights, mfe_batch, deduplicate=True
        )
        out = {
            "gene": gene,
            "method": "gemorna",
            "benchmark_header": benchmark_header,
            "expected_protein_sha256": protein_sha256(protein),
            "n_samples": len(raw_solutions),
            "note": "identity checked against benchmark FASTA; missing terminal stop replaced by TAA",
            **summary,
            "n_invalid": summary["n_invalid_identity"],
            "solutions": scored,
        }
        dst = args.out_dir / f"GEMORNA_{gene}_s0_scored.json"
        dst.write_text(json.dumps(out, indent=1))
        print(f"[{gene}] identity={out['n_identity_pass']} unique={out['n_unique']} "
              f"invalid_identity={out['n_invalid_identity']} -> {dst}")


if __name__ == "__main__":
    main()
