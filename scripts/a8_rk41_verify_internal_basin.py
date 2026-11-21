#!/usr/bin/env python3
"""Independently reconstruct RK41 pools, search trajectories, objectives, metrics, and inference.

This verifier deliberately does not import RK39/RK40/RK41 production scripts.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import sys

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

EXTERNAL = "lineardesign_lambda11"
NEW_ARMS = ["raw_pool_first_b11", "raw_pool_best_b11", "calibrated_pool_first_b11", "calibrated_pool_best_b11"]
BEST_ENDPOINTS = ["best_normalized_weighted_utility", "best_single_point_normalized_hv"]
ACTUAL_ENDPOINTS = ["first_k_hv", "first_k_ned"]
DIAGNOSTICS = [
    ("calibrated_basin_selection_within_matched_pool", "calibrated_pool_best_b11", "calibrated_pool_first_b11", BEST_ENDPOINTS),
    ("calibrated_multistart_vs_sequential", "calibrated_pool_best_b11", "calibrated_random_b11", BEST_ENDPOINTS),
    ("normalization_within_best_multistart", "calibrated_pool_best_b11", "raw_pool_best_b11", BEST_ENDPOINTS),
    ("raw_multistart_vs_external_best_single", "raw_pool_best_b11", EXTERNAL, BEST_ENDPOINTS),
    ("raw_basin_selection_actual_set", "raw_pool_best_b11", "raw_pool_first_b11", ACTUAL_ENDPOINTS),
]
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


def generate_pool(source, seed, size=8, max_attempts=1000):
    sequences = [random_initial(source, seed)]
    generation_seeds = [seed]
    candidate_seed = seed
    attempts = 0
    while len(sequences) < size and attempts < max_attempts:
        attempts += 1
        candidate_seed += 1000
        candidate = random_initial(source, candidate_seed)
        if candidate not in sequences:
            sequences.append(candidate)
            generation_seeds.append(candidate_seed)
    if len(sequences) != size:
        raise ValueError("independent pool reconstruction failed")
    return sequences, generation_seeds


def single_codon_proposal(source, rng):
    codons = split_codons(source)
    positions = [i for i, codon in enumerate(codons[:-1]) if len(SYNONYMOUS_CODONS[STANDARD_TABLE_1[codon]]) > 1]
    if not positions:
        return source
    position = positions[int(rng.integers(len(positions)))]
    current = codons[position]
    alternatives = [c for c in SYNONYMOUS_CODONS[STANDARD_TABLE_1[current]] if c != current]
    codons[position] = alternatives[int(rng.integers(len(alternatives)))]
    return "".join(codons)


def utility(objectives, weights, normalization=None):
    values = np.asarray(objectives, dtype=float)
    if normalization is not None:
        reference, scale = (np.asarray(item, dtype=float) for item in normalization)
        values = (values - reference) / scale
    return float(values @ np.asarray(weights, dtype=float))


def select_index(arm, pool_objectives, weights, normalization):
    if arm.endswith("first_b11"):
        return 0
    return int(np.argmax([utility(row, weights, normalization) for row in pool_objectives]))


def init_worker(rscu_json, gc_target):
    global _WORKER_WEIGHTS, _WORKER_GC_TARGET
    _WORKER_WEIGHTS = cai_weights_from_rscu(json.loads(Path(rscu_json).read_text()))
    _WORKER_GC_TARGET = gc_target


def score_worker(sequence):
    return sequence, [cai(sequence, _WORKER_WEIGHTS), -mfe(sequence),
                      -abs(gc_fraction(sequence) - _WORKER_GC_TARGET),
                      -motif_penalty_score(sequence) / len(split_codons(sequence))]


def best_metrics(points, frozen, weights):
    objectives = np.asarray([point["objectives"] for point in points], dtype=float)
    normalized = frozen.normalize(objectives)
    utilities = normalized @ np.asarray(weights, dtype=float)
    single = np.prod(np.maximum(normalized, 0.0), axis=1)
    return {"best_normalized_weighted_utility": float(utilities.max()),
            "best_single_point_normalized_hv": float(single.max())}


def actual_metrics(points, frozen):
    rows = [{"output_id": str(p["budget"]), "sequence": p["sequence"], "objectives": p["objectives"]} for p in points]
    summary = summarize_actual_set(rows, frozen)
    return {"n_actual_outputs": len(rows), "n_unique_objective_vectors": summary["n_unique_objective_vectors"],
            "n_pareto_points": summary["n_pareto_points"], "hypervolume_normalized": float(summary["hypervolume_normalized"]),
            "pairwise_ned": float(pairwise_ned([p["sequence"] for p in points], rng=np.random.default_rng(0))),
            "dense_budget_step_auc_v2": None}


def evaluate(points, calibration, k, weights):
    frozen = FrozenReference.from_dict(calibration)
    return {**best_metrics(points, frozen, weights), "matched_first_k_actual_set": actual_metrics(points[:k], frozen),
            "terminal_full_actual_set": actual_metrics(points, frozen),
            "dense_internal_auc": dense_budget_step_auc_v2(points, frozen, max_budget=len(points))}


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
            "sign_flip_p": float(min(1.0, p)), "per_record_effects": delta.tolist(), "n_records": len(delta)}


def decision_label(selection, sequential, external):
    if external:
        return "INTERNAL_MULTISTART_AND_COMMON_INPUT_PROXY_COMPARISON_SUPPORTED" if selection and sequential else "COMMON_INPUT_PROXY_COMPARISON_SUPPORTED_MECHANISM_PARTIAL"
    if selection and sequential:
        return "INTERNAL_MULTISTART_SUPPORTED_COMMON_INPUT_TASK_UNRESOLVED"
    if selection:
        return "BASIN_SELECTION_ONLY_SUPPORTED_COMMON_INPUT_TASK_UNRESOLVED"
    if sequential:
        return "BUDGET_REALLOCATION_ONLY_SUPPORTED_COMMON_INPUT_TASK_UNRESOLVED"
    return "INTERNAL_MULTISTART_NOT_SUPPORTED_COMMON_INPUT_TASK_UNRESOLVED"


def independent_inference(data, external, records, protocol):
    tests = []
    definitions = [(f["family"], f["left"], f["right"], f["endpoints"], True) for f in protocol["primary_families"]]
    definitions += [(family, left, right, endpoints, False) for family, left, right, endpoints in DIAGNOSTICS]
    for family, left, right, endpoints, confirmatory in definitions:
        for endpoint in endpoints:
            def value(record, seed, arm):
                return external[record][endpoint] if arm == EXTERNAL else data[(record, seed, arm)][endpoint]
            matrix = np.asarray([[value(record, seed, left) - value(record, seed, right) for seed in protocol["seeds"]]
                                 for record in records])
            test = paired(matrix.mean(axis=1), protocol)
            test.update({"family": family, "contrast": f"{left} minus {right}", "left": left, "right": right,
                         "endpoint": endpoint, "seed_mean_effects": matrix.mean(axis=0).tolist(),
                         "all_seed_effects_positive": bool(np.all(matrix.mean(axis=0) > 0)),
                         "confirmatory": confirmatory, "supported_advantage": None, "holm_p": None})
            tests.append(test)
    family_pass = {}
    for family in protocol["primary_families"]:
        selected = [t for t in tests if t["family"] == family["family"] and t["confirmatory"]]
        for test, adjusted in zip(selected, holm([t["sign_flip_p"] for t in selected])):
            test["holm_p"] = float(adjusted)
            test["supported_advantage"] = bool(test["ci95"][0] > 0 and adjusted < 0.05 and test["all_seed_effects_positive"])
        family_pass[family["family"]] = bool(all(t["supported_advantage"] for t in selected))
    endpoints = BEST_ENDPOINTS + ACTUAL_ENDPOINTS + ["initial_normalized_weighted_utility", "initial_single_point_normalized_hv"]
    absolute = {}
    for arm in protocol["all_analysis_arms"]:
        first = data[(records[0], protocol["seeds"][0], arm)]
        absolute[arm] = {endpoint: float(np.mean([data[(r, s, arm)][endpoint] for r in records for s in protocol["seeds"]]))
                         for endpoint in endpoints if endpoint in first}
    selection = family_pass["raw_common_input_basin_selection"]
    sequential = family_pass["raw_common_input_sequential_advantage"]
    external_pass = family_pass["common_input_actual_set_versus_linear_design"]
    return {"tests": tests, "primary_family_pass": family_pass, "primary_gate_passed": bool(all(family_pass.values())),
            "common_input_actual_set_gate_passed": external_pass,
            "decision": decision_label(selection, sequential, external_pass), "absolute_performance": absolute}


def close(a, b, tolerance=1e-12):
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=tolerance)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=12)
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
    check("accepted_call_accounting", summary["n_accepted_rk40_runs"] == len(records) * len(seeds) * 2)
    descriptors = {(r["record_id"], r["seed"], r["arm"]): r for r in summary["runs"]}
    expected_keys = {(r, s, a) for r in records for s in seeds for a in protocol["all_analysis_arms"]}
    check("exact_arm_coverage", set(descriptors) == expected_keys)
    calibrations = {}
    for record in records:
        path = Path(protocol["calibration_dir"]) / f"{safe_name(record)}.json"
        calibrations[record] = json.loads(path.read_text())
        check(f"calibration_identity_{record}", sha(path) == matrix_records[record]["calibration_sha256"])
    raw, all_points = {}, {}
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
            for point in matrix_records[record]["methods"][EXTERNAL]["points"]:
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
    reconstructed_new = 0
    for key, payload in raw.items():
        record, seed, arm = key
        descriptor = descriptors[key]
        points = payload["points"]
        legal = len(points) == 11 and [p["budget"] for p in points] == list(range(1, 12))
        legal = legal and len({p["sequence"] for p in points}) == 11
        legal = legal and all(p["sequence"].endswith("TAA") and protein_from_cds(p["sequence"]) == protein_from_cds(benchmark[record]) for p in points)
        check(f"budget_legality_{key}", legal)
        external_points = matrix_records[record]["methods"][EXTERNAL]["points"]
        objective_error = max(abs(float(value) - float(recomputed[p["sequence"]][j]))
                              for p in points for j, value in enumerate(p["objectives"]))
        max_objective_error = max(max_objective_error, objective_error)
        check(f"objectives_{key}", objective_error <= 1e-12, objective_error)
        independent_points = [{"budget": p["budget"], "sequence": p["sequence"], "objectives": recomputed[p["sequence"]]} for p in points]
        evaluation = evaluate(independent_points, calibrations[record], len(external_points), protocol["weights"])
        descriptor_values = {**evaluation, "first_k_hv": evaluation["matched_first_k_actual_set"]["hypervolume_normalized"],
                             "first_k_ned": evaluation["matched_first_k_actual_set"]["pairwise_ned"]}
        if arm in NEW_ARMS:
            pool, generation_seeds = generate_pool(benchmark[record], seed, protocol["pool_size"], protocol["pool_max_attempts"])
            normalization = None
            if arm.startswith("calibrated"):
                normalization = (calibrations[record]["reference"], calibrations[record]["scale"])
            selected = select_index(arm, [recomputed[s] for s in pool], protocol["weights"], normalization)
            expected = [{"budget": i + 1, "sequence": s, "objectives": recomputed[s]} for i, s in enumerate(pool)]
            cache = {s: recomputed[s] for s in pool}
            current = pool[selected]
            current_objectives = cache[current]
            rng = np.random.default_rng(seed)
            attempts = 0
            while len(expected) < 11 and attempts < protocol["max_attempts"]:
                attempts += 1
                candidate = single_codon_proposal(current, rng)
                if candidate not in cache:
                    if candidate not in recomputed:
                        raise ValueError(f"independently reconstructed candidate absent from production points: {key}")
                    cache[candidate] = recomputed[candidate]
                    expected.append({"budget": len(expected) + 1, "sequence": candidate, "objectives": cache[candidate]})
                candidate_objectives = cache[candidate]
                if utility(candidate_objectives, protocol["weights"], normalization) >= utility(current_objectives, protocol["weights"], normalization):
                    current, current_objectives = candidate, candidate_objectives
            trajectory_ok = len(expected) == 11 and [p["sequence"] for p in expected] == [p["sequence"] for p in independent_points]
            check(f"full_trajectory_reconstruction_{key}", trajectory_ok)
            check(f"pool_identity_{key}", payload["initialization_pool"] == pool and payload["pool_generation_seeds"] == generation_seeds)
            check(f"selection_identity_{key}", payload["pool_selection_index"] == selected and payload["initial_state"] == pool[selected]
                  and payload["initial_state_sha256"] == text_sha(pool[selected]))
            expected_terminal = 8 + 1 + attempts
            check(f"shared_cache_cost_{key}", payload["unique_scorer_calls"] == 11
                  and payload["terminal_evaluations"] == expected_terminal
                  and payload["cache_hits"] == expected_terminal - 11)
            check(f"normalization_semantics_{key}", (payload["search_normalization"] is not None) == arm.startswith("calibrated")
                  and payload["common_input"] == (not arm.startswith("calibrated"))
                  and payload["external_initialization"] is False)
            stored = payload["evaluation"]
            stored_ok = all(close(evaluation[e], stored[e]) for e in BEST_ENDPOINTS)
            stored_ok = stored_ok and close(evaluation["matched_first_k_actual_set"]["hypervolume_normalized"], stored["matched_first_k_actual_set"]["hypervolume_normalized"])
            stored_ok = stored_ok and close(evaluation["terminal_full_actual_set"]["hypervolume_normalized"], stored["terminal_full_actual_set"]["hypervolume_normalized"])
            stored_ok = stored_ok and close(evaluation["dense_internal_auc"]["auc"], stored["dense_internal_auc"]["auc"])
            check(f"raw_evaluation_{key}", stored_ok)
            frozen = FrozenReference.from_dict(calibrations[record])
            selected_normalized = frozen.normalize(np.asarray(recomputed[pool[selected]], dtype=float)[None, :])[0]
            descriptor_values["initial_normalized_weighted_utility"] = float(selected_normalized @ np.asarray(protocol["weights"], dtype=float))
            descriptor_values["initial_single_point_normalized_hv"] = float(np.prod(np.maximum(selected_normalized, 0.0)))
            check(f"initial_metrics_{key}", close(descriptor_values["initial_normalized_weighted_utility"], descriptor["initial_normalized_weighted_utility"])
                  and close(descriptor_values["initial_single_point_normalized_hv"], descriptor["initial_single_point_normalized_hv"]))
            reconstructed_new += 1
        else:
            expected_initial = random_initial(benchmark[record], seed)
            check(f"accepted_initialization_{key}", payload["initial_state"] == expected_initial
                  and payload["initial_state_sha256"] == text_sha(expected_initial))
        endpoint_ok = all(close(descriptor_values[e], descriptor[e]) for e in BEST_ENDPOINTS + ACTUAL_ENDPOINTS)
        endpoint_ok = endpoint_ok and close(evaluation["terminal_full_actual_set"]["hypervolume_normalized"], descriptor["terminal_full_hv"])
        endpoint_ok = endpoint_ok and close(evaluation["terminal_full_actual_set"]["pairwise_ned"], descriptor["terminal_full_ned"])
        endpoint_ok = endpoint_ok and close(evaluation["dense_internal_auc"]["auc"], descriptor["dense_internal_auc"])
        check(f"descriptor_metrics_{key}", endpoint_ok)
        evaluation_by_key[key] = descriptor_values
    check("global_objective_recompute", max_objective_error <= 1e-12, max_objective_error)
    check("all_new_trajectories_reconstructed", reconstructed_new == len(records) * len(seeds) * 4, reconstructed_new)
    pool_checks = 0
    for record in records:
        for seed in seeds:
            for arm in NEW_ARMS[1:]:
                a = raw[(record, seed, NEW_ARMS[0])]["points"][:8]
                b = raw[(record, seed, arm)]["points"][:8]
                pool_checks += sum(x["sequence"] == y["sequence"] for x, y in zip(a, b))
    expected_pool_checks = len(records) * len(seeds) * 3 * 8
    check("pool_identity_summary", summary["pool_identity"]["n_checks"] == expected_pool_checks
          and summary["pool_identity"]["n_pass"] == pool_checks == expected_pool_checks)
    result = {"schema": "a8-rk41-independent-verification-v1", "summary": str(summary_path),
              "summary_sha256": sha(summary_path), "protocol_sha256": sha(protocol_path),
              "production_code_commit": summary["code_commit"], "smoke": summary["smoke"],
              "n_runs": len(raw), "n_raw_points": sum(len(p["points"]) for p in raw.values()),
              "n_new_runs_full_trajectory_reconstructed": reconstructed_new,
              "n_unique_sequences_independently_rescored": len(unique_sequences), "max_objective_abs_error": max_objective_error}
    if not summary["smoke"]:
        external = {}
        for record in records:
            points = [{"budget": i + 1, "sequence": p["sequence"], "objectives": recomputed[p["sequence"]]}
                      for i, p in enumerate(matrix_records[record]["methods"][EXTERNAL]["points"])]
            evaluation = evaluate(points, calibrations[record], len(points), protocol["weights"])
            external[record] = {**evaluation, "first_k_hv": evaluation["matched_first_k_actual_set"]["hypervolume_normalized"],
                                "first_k_ned": evaluation["matched_first_k_actual_set"]["pairwise_ned"]}
            reported = summary["external_reference"][record]
            check(f"external_reference_{record}", all(close(evaluation[e], reported[e]) for e in BEST_ENDPOINTS)
                  and close(external[record]["first_k_hv"], reported["first_k_hv"])
                  and close(external[record]["first_k_ned"], reported["first_k_ned"]))
        inference = independent_inference(evaluation_by_key, external, records, protocol)
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
              and inference["decision"] == summary["decision"]
              and inference["common_input_actual_set_gate_passed"] == summary["common_input_actual_set_gate_passed"])
        check("absolute_performance", all(close(inference["absolute_performance"][arm][endpoint], summary["absolute_performance"][arm][endpoint])
                                            for arm in inference["absolute_performance"] for endpoint in inference["absolute_performance"][arm]))
        result.update({"decision": inference["decision"], "primary_family_pass": inference["primary_family_pass"],
                       "primary_gate_passed": inference["primary_gate_passed"],
                       "common_input_actual_set_gate_passed": inference["common_input_actual_set_gate_passed"]})
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
                                              "n_new_runs_full_trajectory_reconstructed", "n_unique_sequences_independently_rescored",
                                              "max_objective_abs_error")}))
    if result["status"] != "PASS":
        for item in checks:
            if not item["passed"]:
                print("FAIL", item)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
