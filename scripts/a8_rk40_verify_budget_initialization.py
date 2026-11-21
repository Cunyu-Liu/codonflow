#!/usr/bin/env python3
"""Independently verify RK40 raw runs, objectives, metrics, and inference.

This verifier deliberately does not import either RK39 or RK40 production code.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from codonflow.core.codon import STANDARD_TABLE_1, SYNONYMOUS_CODONS, gc_fraction, normalize_to_dna, split_codons
from codonflow.core.motifs import motif_penalty_score
from codonflow.data.dataset import read_fasta
from codonflow.eval.actual_set import summarize_actual_set
from codonflow.eval.anytime import FrozenReference, dense_budget_step_auc_v2
from codonflow.eval.metrics import cai, cai_weights_from_rscu, mfe, pairwise_ned
from codonflow.models.guided_sampler import synonymous_x0

_WORKER_WEIGHTS = None
_WORKER_GC_TARGET = None


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text_sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def safe_name(text):
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in text)


def load_benchmark(path):
    pairs = list(read_fasta(path))
    benchmark = {header.split()[0]: sequence for header, sequence in pairs}
    if not benchmark or len(benchmark) != len(pairs):
        raise ValueError("benchmark must contain unique, nonempty record identifiers")
    return benchmark, list(benchmark)


def protein_from_cds(sequence):
    codons = split_codons(normalize_to_dna(sequence))
    aas = []
    for index, codon in enumerate(codons):
        aa = STANDARD_TABLE_1[codon]
        if aa == "*" and index != len(codons) - 1:
            raise ValueError("internal stop")
        aas.append(aa)
    if not aas or aas[-1] != "*" or aas.count("*") != 1:
        raise ValueError("invalid terminal stop")
    return "".join(aas)


def random_initial(source, seed):
    protein = protein_from_cds(source)
    template = "".join("TAA" if aa == "*" else SYNONYMOUS_CODONS[aa][0] for aa in protein)
    initial = synonymous_x0(template, np.random.default_rng(seed * 1009))
    if protein_from_cds(initial) != protein or not initial.endswith("TAA"):
        raise ValueError("random initialization identity failure")
    return initial


def init_worker(rscu_json, gc_target):
    global _WORKER_WEIGHTS, _WORKER_GC_TARGET
    _WORKER_WEIGHTS = cai_weights_from_rscu(json.loads(Path(rscu_json).read_text()))
    _WORKER_GC_TARGET = gc_target


def score_worker(sequence):
    values = [cai(sequence, _WORKER_WEIGHTS), -mfe(sequence),
              -abs(gc_fraction(sequence) - _WORKER_GC_TARGET),
              -motif_penalty_score(sequence) / len(split_codons(sequence))]
    return sequence, values


def best_metrics(points, frozen, weights):
    objectives = np.asarray([point["objectives"] for point in points], dtype=float)
    normalized = frozen.normalize(objectives)
    utility = normalized @ np.asarray(weights, dtype=float)
    single = np.prod(np.maximum(normalized, 0.0), axis=1)
    return {
        "best_normalized_weighted_utility": float(utility.max()),
        "best_single_point_normalized_hv": float(single.max()),
    }


def actual_metrics(points, frozen):
    rows = [{"output_id": str(p["budget"]), "sequence": p["sequence"], "objectives": p["objectives"]}
            for p in points]
    summary = summarize_actual_set(rows, frozen)
    return {
        "n_actual_outputs": len(rows),
        "n_unique_objective_vectors": summary["n_unique_objective_vectors"],
        "n_pareto_points": summary["n_pareto_points"],
        "hypervolume_normalized": float(summary["hypervolume_normalized"]),
        "pairwise_ned": float(pairwise_ned([p["sequence"] for p in points], rng=np.random.default_rng(0))),
        "dense_budget_step_auc_v2": None,
    }


def evaluate(points, calibration, k, weights):
    frozen = FrozenReference.from_dict(calibration)
    return {
        **best_metrics(points, frozen, weights),
        "matched_first_k_actual_set": actual_metrics(points[:k], frozen),
        "terminal_full_actual_set": actual_metrics(points, frozen),
        "dense_internal_auc": dense_budget_step_auc_v2(points, frozen, max_budget=len(points)),
    }


def holm(values):
    order = np.argsort(np.asarray(values, dtype=float))
    adjusted = np.empty(len(values), dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(values) - rank) * values[index]))
        adjusted[index] = running
    return adjusted.tolist()


def paired(delta, protocol):
    delta = np.asarray(delta, dtype=float)
    observed = float(delta.mean())
    stats = protocol["statistics"]
    rng = np.random.default_rng(stats["bootstrap_seed"])
    indices = rng.integers(0, len(delta), size=(stats["paired_bootstrap_resamples"], len(delta)))
    boot = delta[indices].mean(axis=1)
    rng = np.random.default_rng(stats["permutation_seed"])
    flips = rng.choice(np.asarray([-1.0, 1.0]), size=(stats["paired_sign_flip_permutations"], len(delta)))
    null = (flips * delta).mean(axis=1)
    p = (1 + int(np.sum(np.abs(null) >= abs(observed) - 1e-15))) / (len(null) + 1)
    return {"effect": observed, "ci95": np.quantile(boot, [0.025, 0.975]).tolist(),
            "sign_flip_p": float(min(1.0, p)), "per_record_effects": delta.tolist(),
            "n_records": len(delta)}


def independent_inference(data, records, protocol):
    primary = [
        ("normalization_at_short_budget", "calibrated_random_b11", "raw_random_b11"),
        ("budget_within_raw_search", "raw_random_b101", "raw_random_b11"),
    ]
    diagnostic = [
        ("normalization_at_long_budget", "calibrated_random_b101", "raw_random_b101"),
        ("budget_within_calibrated_search", "calibrated_random_b101", "calibrated_random_b11"),
        ("external_initialization_raw", "raw_external_b11", "raw_random_b11"),
        ("external_initialization_calibrated", "calibrated_external_b11", "calibrated_random_b11"),
    ]
    tests = []
    for family, left, right in primary + diagnostic:
        confirmatory = (family, left, right) in primary
        for endpoint in protocol["primary_endpoints"]:
            matrix = np.asarray([[data[(record, seed, left)][endpoint] - data[(record, seed, right)][endpoint]
                                  for seed in protocol["seeds"]] for record in records])
            test = paired(matrix.mean(axis=1), protocol)
            test.update({"family": family, "contrast": f"{left} minus {right}", "left": left,
                         "right": right, "endpoint": endpoint, "seed_mean_effects": matrix.mean(axis=0).tolist(),
                         "all_seed_effects_positive": bool(np.all(matrix.mean(axis=0) > 0)),
                         "confirmatory": confirmatory, "supported_advantage": None, "holm_p": None})
            tests.append(test)
    family_pass = {}
    for family, _, _ in primary:
        selected = [t for t in tests if t["family"] == family and t["confirmatory"]]
        for test, adjusted in zip(selected, holm([t["sign_flip_p"] for t in selected])):
            test["holm_p"] = float(adjusted)
            test["supported_advantage"] = bool(test["ci95"][0] > 0 and adjusted < 0.05
                                                 and test["all_seed_effects_positive"])
        family_pass[family] = bool(all(t["supported_advantage"] for t in selected))
    n_pass = family_pass["normalization_at_short_budget"]
    b_pass = family_pass["budget_within_raw_search"]
    if n_pass and b_pass:
        decision = "NORMALIZATION_AND_SHORT_BUDGET_BOTH_CONTRIBUTE"
    elif n_pass:
        decision = "SEARCH_SCALE_MISMATCH_SUPPORTED_AT_SHORT_BUDGET"
    elif b_pass:
        decision = "SHORT_BUDGET_LIMIT_SUPPORTED_WITHIN_RAW_SEARCH"
    else:
        decision = "NO_RESCUE_FROM_NORMALIZATION_OR_RAW_BUDGET"
    absolute = {arm: {endpoint: float(np.mean([data[(r, s, arm)][endpoint] for r in records for s in protocol["seeds"]]))
                      for endpoint in protocol["primary_endpoints"]} for arm in protocol["all_analysis_arms"]}
    return {"tests": tests, "primary_family_pass": family_pass,
            "primary_gate_passed": bool(all(family_pass.values())), "decision": decision,
            "absolute_performance": absolute}


def close(a, b, tolerance=1e-12):
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=tolerance)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    summary_path = Path(args.summary)
    summary = json.loads(summary_path.read_text())
    protocol_path = Path(summary["protocol_path"])
    protocol = json.loads(protocol_path.read_text())
    checks = []

    def check(name, ok, detail=None):
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    check("summary_sha256_recorded", True, sha(summary_path))
    check("protocol_identity", sha(protocol_path) == summary["protocol_sha256"])
    benchmark, all_records = load_benchmark(protocol["benchmark_fasta"])
    records = [protocol["execution"]["smoke_record"]] if summary["smoke"] else all_records
    seeds = [protocol["execution"]["smoke_seed"]] if summary["smoke"] else protocol["seeds"]
    matrix_path = Path(protocol["external_matrix"])
    matrix_records = {r["record_id"]: r for r in json.loads(matrix_path.read_text())["records"]}
    check("external_matrix_identity", sha(matrix_path) == protocol["external_matrix_sha256"])
    check("summary_run_accounting", len(summary["runs"]) == len(records) * len(seeds) * 6)
    expected_new_calls = protocol["execution"]["smoke_expected_new_unique_scorer_calls"] if summary["smoke"] else protocol["expected_new_unique_scorer_calls"]
    check("new_call_accounting", summary["n_new_unique_scorer_calls"] == expected_new_calls)
    descriptors = {(r["record_id"], r["seed"], r["arm"]): r for r in summary["runs"]}
    expected_keys = {(r, s, a) for r in records for s in seeds for a in protocol["all_analysis_arms"]}
    check("exact_arm_coverage", set(descriptors) == expected_keys)
    calibrations = {}
    for record in records:
        path = Path(protocol["calibration_dir"]) / f"{safe_name(record)}.json"
        calibrations[record] = json.loads(path.read_text())
        check(f"calibration_identity_{record}", sha(path) == matrix_records[record]["calibration_sha256"])
    raw = {}
    all_points = {}
    for key, descriptor in descriptors.items():
        path = Path(descriptor["path"])
        payload = json.loads(path.read_text())
        raw[key] = payload
        check(f"run_sha_{key}", sha(path) == descriptor["sha256"])
        check(f"run_identity_{key}", payload["record_id"] == key[0] and payload["seed"] == key[1]
              and payload["source_sha256"] == text_sha(benchmark[key[0]]))
        for point in payload["points"]:
            sequence = point["sequence"]
            if sequence in all_points:
                check(f"duplicate_objective_consistency_{len(checks)}", np.allclose(all_points[sequence], point["objectives"], rtol=0, atol=0))
            else:
                all_points[sequence] = point["objectives"]
    if not summary["smoke"]:
        for record in records:
            for point in matrix_records[record]["methods"]["lineardesign_lambda11"]["points"]:
                all_points.setdefault(point["sequence"], point["objectives"])
    unique_sequences = sorted(all_points)
    if args.workers == 1:
        init_worker(protocol["rscu_json"], protocol["gc_target"])
        scored = [score_worker(sequence) for sequence in unique_sequences]
    else:
        with ProcessPoolExecutor(max_workers=args.workers, initializer=init_worker,
                                 initargs=(protocol["rscu_json"], protocol["gc_target"])) as pool:
            scored = list(pool.map(score_worker, unique_sequences, chunksize=1))
    recomputed = dict(scored)
    max_objective_error = 0.0
    evaluation_by_key = {}
    for key, payload in raw.items():
        record, seed, arm = key
        descriptor = descriptors[key]
        points = payload["points"]
        legal = len(points) == descriptor["budget"] and [p["budget"] for p in points] == list(range(1, len(points) + 1))
        legal = legal and len({p["sequence"] for p in points}) == len(points)
        legal = legal and all(p["sequence"].endswith("TAA") and protein_from_cds(p["sequence"]) == protein_from_cds(benchmark[record]) for p in points)
        check(f"budget_legality_{key}", legal)
        external_points = matrix_records[record]["methods"]["lineardesign_lambda11"]["points"]
        expected_initial = external_points[0]["sequence"] if arm in {"raw_external_b11", "calibrated_external_b11"} else random_initial(benchmark[record], seed)
        check(f"initialization_{key}", payload["initial_state"] == expected_initial
              and payload["initial_state_sha256"] == text_sha(expected_initial))
        objective_error = max(abs(float(value) - float(recomputed[p["sequence"]][j]))
                              for p in points for j, value in enumerate(p["objectives"]))
        max_objective_error = max(max_objective_error, objective_error)
        check(f"objectives_{key}", objective_error <= 1e-12, objective_error)
        independent_points = [{"budget": p["budget"], "sequence": p["sequence"], "objectives": recomputed[p["sequence"]]}
                              for p in points]
        k = len(external_points)
        evaluation = evaluate(independent_points, calibrations[record], k, protocol["weights"])
        evaluation_by_key[key] = evaluation
        endpoint_ok = all(close(evaluation[e], descriptor[e]) for e in protocol["primary_endpoints"])
        endpoint_ok = endpoint_ok and close(evaluation["matched_first_k_actual_set"]["hypervolume_normalized"], descriptor["first_k_hv"])
        endpoint_ok = endpoint_ok and close(evaluation["matched_first_k_actual_set"]["pairwise_ned"], descriptor["first_k_ned"])
        endpoint_ok = endpoint_ok and close(evaluation["terminal_full_actual_set"]["hypervolume_normalized"], descriptor["terminal_full_hv"])
        endpoint_ok = endpoint_ok and close(evaluation["terminal_full_actual_set"]["pairwise_ned"], descriptor["terminal_full_ned"])
        endpoint_ok = endpoint_ok and close(evaluation["dense_internal_auc"]["auc"], descriptor["dense_internal_auc"])
        check(f"descriptor_metrics_{key}", endpoint_ok)
        if arm != "raw_random_b11":
            stored = payload["evaluation"]
            stored_ok = all(close(evaluation[e], stored[e]) for e in protocol["primary_endpoints"])
            stored_ok = stored_ok and close(evaluation["matched_first_k_actual_set"]["hypervolume_normalized"], stored["matched_first_k_actual_set"]["hypervolume_normalized"])
            stored_ok = stored_ok and close(evaluation["terminal_full_actual_set"]["hypervolume_normalized"], stored["terminal_full_actual_set"]["hypervolume_normalized"])
            stored_ok = stored_ok and close(evaluation["dense_internal_auc"]["auc"], stored["dense_internal_auc"]["auc"])
            check(f"raw_evaluation_{key}", stored_ok)
            check(f"cost_accounting_{key}", payload["unique_scorer_calls"] == len(points))
            check(f"normalization_semantics_{key}", (payload["search_normalization"] is not None) == (arm.startswith("calibrated")))
    check("global_objective_recompute", max_objective_error <= 1e-12, max_objective_error)
    trajectory_checks = 0
    for record in records:
        for seed in seeds:
            for long_arm, short_arm in (("raw_random_b101", "raw_random_b11"), ("calibrated_random_b101", "calibrated_random_b11")):
                long = raw[(record, seed, long_arm)]["points"]
                short = raw[(record, seed, short_arm)]["points"]
                ok = all(long[i]["sequence"] == short[i]["sequence"] and np.allclose(long[i]["objectives"], short[i]["objectives"], rtol=0, atol=0) for i in range(11))
                trajectory_checks += 1
                check(f"trajectory_{record}_{seed}_{long_arm}", ok)
    check("trajectory_summary", summary["trajectory_identity"]["n_checks"] == trajectory_checks * 11
          and summary["trajectory_identity"]["n_pass"] == trajectory_checks * 11)
    result = {
        "schema": "a8-rk40-independent-verification-v1", "summary": str(summary_path),
        "summary_sha256": sha(summary_path), "protocol_sha256": sha(protocol_path),
        "production_code_commit": summary["code_commit"], "smoke": summary["smoke"],
        "n_runs": len(raw), "n_raw_points": sum(len(p["points"]) for p in raw.values()),
        "n_unique_sequences_independently_rescored": len(unique_sequences),
        "max_objective_abs_error": max_objective_error,
    }
    if not summary["smoke"]:
        data = {key: evaluation_by_key[key] for key in expected_keys}
        inference = independent_inference(data, records, protocol)
        reported_by_key = {(t["family"], t["endpoint"]): t for t in summary["tests"]}
        for test in inference["tests"]:
            reported = reported_by_key[(test["family"], test["endpoint"])]
            ok = close(test["effect"], reported["effect"]) and np.allclose(test["ci95"], reported["ci95"], rtol=0, atol=1e-12)
            ok = ok and close(test["sign_flip_p"], reported["sign_flip_p"])
            ok = ok and np.allclose(test["per_record_effects"], reported["per_record_effects"], rtol=0, atol=1e-12)
            ok = ok and np.allclose(test["seed_mean_effects"], reported["seed_mean_effects"], rtol=0, atol=1e-12)
            if test["confirmatory"]:
                ok = ok and close(test["holm_p"], reported["holm_p"]) and test["supported_advantage"] == reported["supported_advantage"]
            check(f"inference_{test['family']}_{test['endpoint']}", ok)
        check("family_decision", inference["primary_family_pass"] == summary["primary_family_pass"]
              and inference["decision"] == summary["decision"])
        check("absolute_performance", all(close(inference["absolute_performance"][arm][endpoint], summary["absolute_performance"][arm][endpoint])
                                            for arm in inference["absolute_performance"] for endpoint in protocol["primary_endpoints"]))
        external_ok = True
        for record in records:
            points = [{"budget": i + 1, "sequence": p["sequence"], "objectives": recomputed[p["sequence"]]}
                      for i, p in enumerate(matrix_records[record]["methods"]["lineardesign_lambda11"]["points"])]
            evaluation = evaluate(points, calibrations[record], len(points), protocol["weights"])
            reported = summary["external_reference"][record]
            external_ok = external_ok and all(close(evaluation[e], reported[e]) for e in protocol["primary_endpoints"])
            external_ok = external_ok and close(evaluation["matched_first_k_actual_set"]["hypervolume_normalized"], reported["matched_first_k_actual_set"]["hypervolume_normalized"])
        check("external_reference_recompute", external_ok)
        result.update({"decision": inference["decision"], "primary_family_pass": inference["primary_family_pass"],
                       "primary_gate_passed": inference["primary_gate_passed"]})
    for field in ("scientific_gate_passed", "external_sota_authorized", "time_matched_comparison",
                  "functional_untouched_evaluated", "rk_g1_pass", "manuscript_submittable"):
        check(f"boundary_{field}", summary[field] is False)
        result[field] = False
    result["status"] = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    result["n_checks"] = len(checks)
    result["n_pass"] = sum(c["passed"] for c in checks)
    result["checks"] = checks
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({k: result[k] for k in ("status", "n_checks", "n_pass", "n_runs", "n_raw_points",
                                              "n_unique_sequences_independently_rescored", "max_objective_abs_error")}))
    if result["status"] != "PASS":
        for item in checks:
            if not item["passed"]:
                print("FAIL", item)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
