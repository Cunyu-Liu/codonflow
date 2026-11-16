"""Independently verify proposal-in-the-loop diagnostics without a Go/No-Go claim."""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.data.dataset import read_fasta
from codonflow.eval.paired_stats import holm_adjust, paired_gene_effects
from scripts.a7_g2_gate import recompute_raw_metrics
from scripts.a7_provenance import resolve_accepted_code_commits
from scripts.a7_run_proposal_in_loop import validate_baseline
from scripts.a7_summarize_g2 import BUDGETS, point_at_budget

DIAGNOSTIC_GENES = ("C31E10.3b.1", "C14A6.7.1", "C01H6.8b.1")


def select_genes(records, excluded):
    if len(set(excluded)) != len(excluded):
        raise ValueError("excluded record IDs must be unique")
    unknown = set(excluded) - set(records)
    if unknown:
        raise ValueError(f"unknown excluded record IDs: {sorted(unknown)}")
    genes = tuple(gene for gene in records if gene not in set(excluded))
    if not genes:
        raise ValueError("record selection cannot be empty")
    return genes


def evaluate_diagnostic(arms, source_records, calibration_dir, accepted_code_commits,
                        expected_genes=DIAGNOSTIC_GENES, expected_seeds=(0, 1, 2)):
    results = []
    for arm in arms:
        grouped = {}
        inputs = []
        baseline_paths = [str(Path(arm["baseline_dir"]) / f"{gene}_hill_climbing_s{seed}.json")
                          for gene in expected_genes for seed in expected_seeds]
        paths = list(arm["paths"]) + [path for path in baseline_paths if path not in arm["paths"]]
        for path in paths:
            payload = json.loads(Path(path).read_text())
            method = payload["method"]
            if method not in ("learned_hill", "hill_climbing"):
                raise ValueError(f"unexpected diagnostic method: {path}")
            expected = {
                "record_id": payload["record_id"], "seed": payload["seed"], "method": method,
                "code_commit": accepted_code_commits,
                "checkpoint_sha256": arm["checkpoint_sha256"] if method == "learned_hill" else None,
            }
            validate_baseline(path, expected)
            if payload["record_id"] not in expected_genes or payload["seed"] not in expected_seeds:
                raise ValueError(f"unexpected diagnostic gene or seed: {path}")
            if method == "learned_hill":
                if (payload.get("device") != "cuda:0" or payload.get("terminal_step") != 1
                        or payload.get("path_batch_size") != 1):
                    raise ValueError(f"learned diagnostic lacks T=1 CUDA provenance: {path}")
                baseline_path = Path(arm["baseline_dir"]) / f"{payload['record_id']}_hill_climbing_s{payload['seed']}.json"
                if (payload.get("baseline_path") != str(baseline_path)
                        or payload.get("baseline_sha256") != hashlib.sha256(baseline_path.read_bytes()).hexdigest()):
                    raise ValueError(f"baseline link mismatch: {path}")
            key = (payload["record_id"], payload["seed"], method)
            if key in grouped:
                raise ValueError(f"duplicate diagnostic result: {key}")
            recompute_raw_metrics(payload, source_records[payload["record_id"]], calibration_dir)
            grouped[key] = payload
            inputs.append({"path": str(path), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()})
        expected_keys = {(gene, seed, method) for gene in expected_genes for seed in expected_seeds
                         for method in ("learned_hill", "hill_climbing")}
        if set(grouped) != expected_keys:
            raise ValueError(f"incomplete diagnostic observations: {arm['name']}")
        per_gene = []
        statistical_rows = []
        for gene in expected_genes:
            seed_rows = []
            for seed in expected_seeds:
                learned = grouped[(gene, seed, "learned_hill")]
                simple = grouped[(gene, seed, "hill_climbing")]
                for field in ("initial_sha256", "source_sha256", "benchmark_sha256",
                              "data_split_sha256", "calibration_sha256", "rscu_sha256"):
                    if learned[field] != simple[field]:
                        raise ValueError(f"unmatched {field}: {gene}, seed={seed}")
                seed_rows.append({
                    "seed": seed,
                    "learned_auc": learned["anytime"]["auc"],
                    "simple_auc": simple["anytime"]["auc"],
                    "learned_ned": learned["ned"], "simple_ned": simple["ned"],
                    "learned_elapsed_s": learned["costs"]["elapsed_s"],
                    "simple_elapsed_s": simple["costs"]["elapsed_s"],
                    "learned_forward_calls": learned["costs"]["forward_calls"],
                    "simple_forward_calls": simple["costs"]["forward_calls"],
                    "learned_terminal_requests": learned["costs"]["terminal_reward_evaluations"],
                    "simple_terminal_requests": simple["costs"]["terminal_reward_evaluations"],
                    "learned_best_at_budget": {str(budget): point_at_budget(
                        learned["points"], budget)["best_by_objective"] for budget in BUDGETS},
                    "simple_best_at_budget": {str(budget): point_at_budget(
                        simple["points"], budget)["best_by_objective"] for budget in BUDGETS},
                })
                for method, payload in (("learned_hill", learned), ("hill_climbing", simple)):
                    statistical_rows.append({"gene": gene, "seed": seed, "method": method,
                                             "auc": payload["anytime"]["auc"]})
            def mean(field):
                return float(np.mean([row[field] for row in seed_rows]))
            learned_elapsed = mean("learned_elapsed_s")
            simple_elapsed = mean("simple_elapsed_s")
            learned_ned = mean("learned_ned")
            simple_ned = mean("simple_ned")
            per_gene.append({
                "gene": gene, "seeds": seed_rows,
                "learned_auc": mean("learned_auc"), "simple_auc": mean("simple_auc"),
                "absolute_improvement": mean("learned_auc") - mean("simple_auc"),
                "relative_improvement": (mean("learned_auc") - mean("simple_auc")) / mean("simple_auc"),
                "learned_ned": learned_ned, "simple_ned": simple_ned,
                "ned_ratio": learned_ned / simple_ned,
                "learned_elapsed_s": learned_elapsed, "simple_elapsed_s": simple_elapsed,
                "elapsed_ratio": learned_elapsed / simple_elapsed,
                "learned_forward_calls": mean("learned_forward_calls"),
                "simple_forward_calls": mean("simple_forward_calls"),
                "learned_terminal_requests": mean("learned_terminal_requests"),
                "simple_terminal_requests": mean("simple_terminal_requests"),
            })
        statistics = paired_gene_effects(statistical_rows, ("hill_climbing",),
                                         learned_method="learned_hill", n_bootstrap=10000, seed=0)
        results.append({"arm": arm["name"], "checkpoint_sha256": arm["checkpoint_sha256"],
                        "per_gene": per_gene, "inputs": inputs, "statistics": statistics,
                        "median_elapsed_ratio": float(np.median([row["elapsed_ratio"] for row in per_gene]))})
    return {
        "protocol": "a7_proposal_in_loop_diagnostic_v1",
        "exploratory_not_gate": True,
        "scientific_gate_passed": False,
        "diagnostic_complete": True,
        "raw_metrics_recomputed": True,
        "accepted_code_commits": sorted(accepted_code_commits),
        "expected_genes": list(expected_genes),
        "seeds": list(expected_seeds),
        "holm_adjusted_wilcoxon_p": dict(zip(
            [arm["arm"] for arm in results],
            holm_adjust([arm["statistics"]["wilcoxon_greater_p"] for arm in results]))),
        "arms": results,
        "interpretation": "Positive associations form hypotheses only; negative associations support the existing No-Go. Neither overturns G2.",
    }


def expand_arm(item):
    name, checkpoint_sha256, learned_pattern, baseline_dir = item.split(",")
    paths = sorted(glob.glob(learned_pattern))
    if not name or len(checkpoint_sha256) != 64 or not paths:
        raise ValueError("each arm requires name, checkpoint SHA and nonempty learned glob")
    return {"name": name, "checkpoint_sha256": checkpoint_sha256,
            "paths": paths, "baseline_dir": baseline_dir}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", action="append", required=True,
                        help="name,checkpoint_sha256,learned_hill_glob,random_hill_dir")
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--calibration-dir", required=True)
    parser.add_argument("--accept-code-commit", action="append", default=[])
    parser.add_argument("--exclude-record-id", action="append", default=[])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    accepted = resolve_accepted_code_commits(args.accept_code_commit)
    arms = [expand_arm(item) for item in args.arm]
    if {arm["name"] for arm in arms} != {"FULL", "EDIT"} or len(arms) != 2:
        raise ValueError("diagnostic requires FULL and EDIT arms")
    source_records = {header.split()[0]: sequence for header, sequence in read_fasta(args.benchmark_fasta)}
    expected_genes = (select_genes(source_records, args.exclude_record_id)
                      if args.exclude_record_id else DIAGNOSTIC_GENES)
    result = evaluate_diagnostic(arms, source_records, args.calibration_dir, accepted,
                                 expected_genes=expected_genes)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(out)
    print(json.dumps({"out": str(out), "diagnostic_complete": True,
                      "scientific_gate_passed": False}))


if __name__ == "__main__":
    main()
