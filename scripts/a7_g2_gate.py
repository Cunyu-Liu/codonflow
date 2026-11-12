"""Validate complete paired A7 runs and apply the frozen G2 learning-value gate."""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from codonflow.eval.paired_stats import holm_adjust, paired_gene_effects
from codonflow.eval.protocol import validate_result_payload

SIMPLE_METHODS = ("uniform", "hill_climbing", "mh_annealing", "areuredi_style")


def load_paired_results(paths, arm, expected_genes, expected_seeds=(0, 1, 2)):
    grouped = defaultdict(dict)
    inputs = []
    for path in paths:
        payload = json.loads(Path(path).read_text())
        validate_result_payload(payload)
        if payload["status"] != "done":
            raise ValueError(f"incomplete result cannot enter G2: {path}")
        if payload["code_dirty"] is not False:
            raise ValueError(f"G2 requires a clean source-controlled commit: {path}")
        if payload["seed"] not in expected_seeds or payload["record_id"] not in expected_genes:
            raise ValueError(f"unexpected gene or seed: {path}")
        if not payload.get("initial_sha256") or len(payload["points"]) != 500:
            raise ValueError(f"missing paired initialization or budget: {path}")
        if payload["identity_rate"] != 1.0:
            raise ValueError(f"protein identity failure: {path}")
        if payload["method"] == "learned":
            if not payload.get("checkpoint_sha256") or payload.get("device") != "cuda:0":
                raise ValueError(f"learned result lacks frozen CUDA provenance: {path}")
        elif payload["method"] in SIMPLE_METHODS:
            if payload.get("checkpoint_sha256") is not None:
                raise ValueError(f"simple baseline unexpectedly uses a checkpoint: {path}")
        else:
            raise ValueError(f"unknown method: {path}")
        key = (payload["record_id"], payload["seed"], payload["method"])
        if key in grouped:
            raise ValueError(f"duplicate gene/seed/method: {key}")
        grouped[key] = payload
        inputs.append({"path": str(path), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()})
    expected = {(gene, seed, method) for gene in expected_genes for seed in expected_seeds
                for method in ("learned", *SIMPLE_METHODS)}
    missing = sorted(expected - set(grouped))
    if missing:
        raise ValueError(f"incomplete G2 observations: {missing[:10]}")
    observations = {(gene, seed): grouped[(gene, seed, "learned")]
                    for gene in expected_genes for seed in expected_seeds}
    for (gene, seed), learned in observations.items():
        rows = [grouped[(gene, seed, method)] for method in ("learned", *SIMPLE_METHODS)]
        for field in ("initial_sha256", "source_sha256", "benchmark_sha256",
                      "data_split_sha256", "calibration_sha256", "rscu_sha256", "code_commit"):
            if len({row[field] for row in rows}) != 1:
                raise ValueError(f"unmatched {field}: {gene}, seed={seed}")
        if rows[0]["checkpoint_sha256"] != arm["checkpoint_sha256"]:
            raise ValueError(f"checkpoint mismatch: {gene}, seed={seed}")
    return grouped, inputs


def evaluate_g2(arms, expected_genes, min_genes=18):
    all_statistics = []
    for arm in arms:
        grouped, inputs = load_paired_results(arm["paths"], arm, expected_genes)
        rows = [{"gene": gene, "seed": seed, "method": method,
                 "auc": payload["anytime"]["auc"]}
                for (gene, seed, method), payload in grouped.items()]
        statistics = paired_gene_effects(rows, SIMPLE_METHODS, n_bootstrap=10000, seed=0)
        diversity = []
        for gene_row in statistics["per_gene"]:
            gene = gene_row["gene"]
            learned_ned = sum(grouped[(gene, seed, "learned")]["ned"] for seed in (0, 1, 2)) / 3
            baseline = gene_row["strongest_simple_method"]
            simple_ned = sum(grouped[(gene, seed, baseline)]["ned"] for seed in (0, 1, 2)) / 3
            ratio = float("inf") if simple_ned == 0 and learned_ned == 0 else learned_ned / simple_ned
            diversity.append({"gene": gene, "baseline": baseline, "learned_ned": learned_ned,
                              "simple_ned": simple_ned, "ratio": ratio})
        arm_result = {"arm": arm["name"], "checkpoint_sha256": arm["checkpoint_sha256"],
                      "statistics": statistics, "diversity": diversity, "inputs": inputs}
        all_statistics.append(statistics)
        arm["result"] = arm_result
    adjusted = holm_adjust([row["wilcoxon_greater_p"] for row in all_statistics])
    checks = {}
    for arm, p_adjusted in zip(arms, adjusted):
        result = arm["result"]
        statistics = result["statistics"]
        checks[arm["name"]] = {
            "enough_genes": statistics["n_genes"] >= min_genes,
            "median_relative_improvement_at_least_10pct": statistics["median_relative_improvement"] >= 0.1,
            "bootstrap_lower_bound_positive": statistics["paired_bootstrap_95ci"][0] > 0,
            "holm_p_below_0.05": p_adjusted < 0.05,
            "ned_ratio_at_least_0.7": all(row["ratio"] >= 0.7 for row in result["diversity"]),
            "identity_legal": True,
        }
        result["holm_adjusted_p"] = p_adjusted
        result["checks"] = checks[arm["name"]]
        result["passed"] = all(checks[arm["name"]].values())
    return {"protocol": "a7_g2_gate_v1", "expected_genes": sorted(expected_genes),
            "seeds": [0, 1, 2], "budgets": [50, 100, 500], "arms": [arm["result"] for arm in arms],
            "passed": bool(arms) and all(arm["result"]["passed"] for arm in arms)}


def expand_arm_spec(item):
    name, checkpoint_sha256, *patterns = item.split(",")
    if not name or len(checkpoint_sha256) != 64 or not patterns:
        raise ValueError("each arm requires name, checkpoint SHA256 and at least one glob")
    paths = []
    for pattern in patterns:
        matched = sorted(glob.glob(pattern))
        if not matched:
            raise ValueError(f"empty input glob: {pattern}")
        paths.extend(matched)
    return {"name": name, "checkpoint_sha256": checkpoint_sha256, "paths": paths}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", action="append", required=True,
                        help="name,checkpoint_sha256,learned_glob,simple_glob (repeat per learned arm)")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    arms = [expand_arm_spec(item) for item in args.arm]
    all_payloads = [json.loads(Path(path).read_text()) for arm in arms for path in arm["paths"]]
    expected_genes = {payload["record_id"] for payload in all_payloads}
    result = evaluate_g2(arms, expected_genes)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps({"out": str(out), "passed": result["passed"]}))


if __name__ == "__main__":
    main()
