"""Aggregate A7 learned-versus-simple anytime results by gene."""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

from codonflow.eval.paired_stats import holm_adjust, paired_gene_effects


def compare_paths(paths, simple_methods, n_bootstrap=10000, seed=0):
    rows = []
    inputs = []
    for path in paths:
        payload = json.loads(Path(path).read_text())
        if payload.get("protocol_version") != "a7_evaluation_v1":
            raise ValueError(f"not an A7 result: {path}")
        if payload.get("status") != "done":
            continue
        rows.append({
            "gene": payload["record_id"],
            "seed": payload["seed"],
            "method": payload["method"],
            "auc": payload["anytime"]["auc"],
        })
        inputs.append(str(path))
    result = paired_gene_effects(rows, simple_methods, n_bootstrap=n_bootstrap, seed=seed)
    result["holm_adjusted_p"] = holm_adjust([result["wilcoxon_greater_p"]])[0]
    result["inputs"] = inputs
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--simple-methods", nargs="+",
                        default=["uniform", "hill_climbing", "mh_annealing", "areuredi_style"])
    parser.add_argument("--n-bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out")
    args = parser.parse_args()
    paths = []
    for item in args.inputs:
        paths.extend(sorted(glob.glob(item)) if "*" in item else [item])
    result = compare_paths(paths, args.simple_methods, args.n_bootstrap, args.seed)
    text = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
