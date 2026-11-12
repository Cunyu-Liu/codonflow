"""Validate complete paired A7 runs and apply the frozen G2 learning-value gate."""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from codonflow.core.codon import feasible_edit
from codonflow.data.dataset import read_fasta
from codonflow.eval.anytime import FrozenReference, anytime_curve
from codonflow.eval.metrics import pairwise_ned
from codonflow.eval.paired_stats import holm_adjust, paired_gene_effects
from codonflow.eval.protocol import validate_result_payload
from codonflow.models.guided_sampler import synonymous_x0

SIMPLE_METHODS = ("uniform", "hill_climbing", "mh_annealing", "areuredi_style")


def recompute_raw_metrics(payload, source, calibration_dir):
    record_id = payload["record_id"]
    source_sha256 = hashlib.sha256(source.encode()).hexdigest()
    if payload["source_sha256"] != source_sha256:
        raise ValueError(f"natural source mismatch: {record_id}")
    initial = synonymous_x0(source, np.random.default_rng(payload["seed"] * 1009))
    if payload["initial_sha256"] != hashlib.sha256(initial.encode()).hexdigest():
        raise ValueError(f"paired initialization mismatch: {record_id}")
    sequences = [point["sequence"] for point in payload["points"]]
    if len(set(sequences)) != 500 or not all(feasible_edit(sequence, source) for sequence in sequences):
        raise ValueError(f"raw identity or uniqueness failure: {record_id}")
    calibration_path = Path(calibration_dir) / f"{record_id}.json"
    calibration = json.loads(calibration_path.read_text())
    if (calibration["source_sha256"] != source_sha256
            or calibration["rscu_sha256"] != payload["rscu_sha256"]
            or calibration.get("source_role") != "independent_calibration_not_test"):
        raise ValueError(f"calibration provenance mismatch: {record_id}")
    if hashlib.sha256(calibration_path.read_bytes()).hexdigest() != payload["calibration_sha256"]:
        raise ValueError(f"calibration file hash mismatch: {record_id}")
    anytime = anytime_curve(payload["points"], FrozenReference.from_dict(calibration))
    reported_hv = [row["hv"] for row in payload["anytime"]["curve"]]
    recomputed_hv = [row["hv"] for row in anytime["curve"]]
    if not np.allclose(reported_hv, recomputed_hv, rtol=0, atol=1e-12):
        raise ValueError(f"anytime metric mismatch: {record_id}")
    ned = pairwise_ned(sequences)
    if not np.isclose(ned, payload["ned"], rtol=0, atol=1e-12):
        raise ValueError(f"NED mismatch: {record_id}")
    payload["anytime"] = anytime
    payload["ned"] = float(ned)


def load_paired_results(paths, arm, expected_genes, expected_seeds=(0, 1, 2),
                        source_records=None, calibration_dir=None):
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
        if source_records is not None:
            if calibration_dir is None:
                raise ValueError("raw metric verification requires calibration_dir")
            recompute_raw_metrics(payload, source_records[payload["record_id"]], calibration_dir)
        elif calibration_dir is not None:
            raise ValueError("raw metric verification requires source_records")
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


def evaluate_g2(arms, expected_genes, min_genes=18, source_records=None, calibration_dir=None):
    all_statistics = []
    fingerprints = []
    for arm in arms:
        grouped, inputs = load_paired_results(arm["paths"], arm, expected_genes,
                                             source_records=source_records, calibration_dir=calibration_dir)
        rows = [{"gene": gene, "seed": seed, "method": method,
                 "auc": payload["anytime"]["auc"]}
                for (gene, seed, method), payload in grouped.items()]
        fingerprints.append({field: {payload[field] for payload in grouped.values()}
                             for field in ("benchmark_sha256", "rscu_sha256",
                                           "data_split_sha256", "code_commit")})
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
    for fingerprint in fingerprints:
        if any(len(values) != 1 for values in fingerprint.values()):
            raise ValueError("protocol metadata differs across genes")
    if fingerprints and any(fingerprint != fingerprints[0] for fingerprint in fingerprints[1:]):
        raise ValueError("protocol metadata differs across learned arms")
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
    return {"protocol": "a7_g2_gate_v2", "raw_metrics_recomputed": source_records is not None,
            "expected_genes": sorted(expected_genes),
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
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--calibration-dir", required=True)
    args = parser.parse_args()
    source_records = {header.split()[0]: sequence for header, sequence in read_fasta(args.benchmark_fasta)}
    arms = [expand_arm_spec(item) for item in args.arm]
    all_payloads = [json.loads(Path(path).read_text()) for arm in arms for path in arm["paths"]]
    expected_genes = {payload["record_id"] for payload in all_payloads}
    if expected_genes != set(source_records):
        raise ValueError("G2 inputs must cover exactly the benchmark records")
    result = evaluate_g2(arms, expected_genes, source_records=source_records,
                         calibration_dir=args.calibration_dir)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps({"out": str(out), "passed": result["passed"]}))


if __name__ == "__main__":
    main()
