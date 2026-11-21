#!/usr/bin/env python3
"""RK40 preregistered search-scale, budget, and initialization discrimination."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import os
from pathlib import Path
import sys
import time
from typing import Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import a8_rk39_common_input_actual_set as rk39
from codonflow.data.dataset import read_fasta
from codonflow.eval.anytime import FrozenReference, dense_budget_step_auc_v2
from codonflow.eval.metrics import cai_weights_from_rscu
from codonflow.models.simple_search import SimpleSearch

ARM_BUDGET = {
    "raw_random_b11": 11,
    "raw_random_b101": 101,
    "calibrated_random_b11": 11,
    "calibrated_random_b101": 101,
    "raw_external_b11": 11,
    "calibrated_external_b11": 11,
}
CALIBRATED = {"calibrated_random_b11", "calibrated_random_b101", "calibrated_external_b11"}
EXTERNAL = {"raw_external_b11", "calibrated_external_b11"}
PRIMARY_CONTRASTS = [
    ("normalization_at_short_budget", "calibrated_random_b11", "raw_random_b11"),
    ("budget_within_raw_search", "raw_random_b101", "raw_random_b11"),
]
DIAGNOSTIC_CONTRASTS = [
    ("normalization_at_long_budget", "calibrated_random_b101", "raw_random_b101"),
    ("budget_within_calibrated_search", "calibrated_random_b101", "calibrated_random_b11"),
    ("external_initialization_raw", "raw_external_b11", "raw_random_b11"),
    ("external_initialization_calibrated", "calibrated_external_b11", "calibrated_random_b11"),
]


def run_path(output_root: Path, record_id: str, seed: int, arm: str) -> Path:
    return output_root / "runs" / rk39.safe_name(record_id) / f"seed{seed}" / f"{arm}.json"


def initial_for_arm(arm: str, source: str, seed: int, external_points: Sequence[Mapping]) -> str:
    if arm in EXTERNAL:
        if not external_points:
            raise ValueError("external initialization requires a frozen actual point")
        return rk39.normalize_to_dna(external_points[0]["sequence"])
    return rk39.protein_only_initial(source, seed)


def best_single_metrics(points: Sequence[Mapping], frozen: FrozenReference,
                        weights: Sequence[float]) -> dict:
    objectives = np.asarray([point["objectives"] for point in points], dtype=float)
    normalized = frozen.normalize(objectives)
    utilities = normalized @ np.asarray(weights, dtype=float)
    single_hv = np.prod(np.maximum(normalized, 0.0), axis=1)
    utility_index = int(np.argmax(utilities))
    hv_index = int(np.argmax(single_hv))
    return {
        "best_normalized_weighted_utility": float(utilities[utility_index]),
        "best_normalized_weighted_utility_budget": int(points[utility_index]["budget"]),
        "best_normalized_weighted_utility_sequence": points[utility_index]["sequence"],
        "best_single_point_normalized_hv": float(single_hv[hv_index]),
        "best_single_point_normalized_hv_budget": int(points[hv_index]["budget"]),
        "best_single_point_normalized_hv_sequence": points[hv_index]["sequence"],
    }


def evaluate_payload(payload: Mapping, calibration: Mapping, k: int,
                     weights: Sequence[float]) -> dict:
    frozen = FrozenReference.from_dict(calibration)
    points = payload["points"]
    first_k = [{
        "output_id": point["budget"], "sequence": point["sequence"],
        "objectives": point["objectives"],
    } for point in points[:k]]
    full = [{
        "output_id": point["budget"], "sequence": point["sequence"],
        "objectives": point["objectives"],
    } for point in points]
    return {
        **best_single_metrics(points, frozen, weights),
        "matched_first_k_actual_set": rk39.evaluate_actual_set(first_k, frozen),
        "terminal_full_actual_set": rk39.evaluate_actual_set(full, frozen),
        "dense_internal_auc": dense_budget_step_auc_v2(points, frozen, max_budget=len(points)),
        "matched_linear_design_k": int(k),
    }


def descriptor(path: Path, payload: Mapping) -> dict:
    evaluation = payload["evaluation"]
    return {
        "record_id": payload["record_id"], "seed": payload["seed"],
        "arm": payload["arm"], "path": str(path), "sha256": rk39.sha(path),
        "initial_state_sha256": payload["initial_state_sha256"],
        "budget": payload["budget"], "unique_scorer_calls": payload["unique_scorer_calls"],
        "best_normalized_weighted_utility": evaluation["best_normalized_weighted_utility"],
        "best_single_point_normalized_hv": evaluation["best_single_point_normalized_hv"],
        "first_k_hv": evaluation["matched_first_k_actual_set"]["hypervolume_normalized"],
        "first_k_ned": evaluation["matched_first_k_actual_set"]["pairwise_ned"],
        "terminal_full_hv": evaluation["terminal_full_actual_set"]["hypervolume_normalized"],
        "terminal_full_ned": evaluation["terminal_full_actual_set"]["pairwise_ned"],
        "dense_internal_auc": evaluation["dense_internal_auc"]["auc"],
        "objective_scoring_seconds": payload.get("objective_scoring_seconds", 0.0),
    }


def accepted_raw_b11(job: Mapping) -> dict:
    summary_path = Path(job["rk39_summary"])
    if rk39.sha(summary_path) != job["rk39_summary_sha256"]:
        raise ValueError("RK39 summary identity mismatch")
    summary = json.loads(summary_path.read_text())
    row = next(row for row in summary["runs"]
               if row["record_id"] == job["record_id"] and row["seed"] == job["seed"]
               and row["method"] == "hill_climbing")
    path = Path(row["path"])
    if rk39.sha(path) != row["sha256"]:
        raise ValueError(f"accepted RK39 raw run identity mismatch: {path}")
    payload = json.loads(path.read_text())
    if len(payload["points"]) != 11 or payload["search_normalization"] is not None:
        raise ValueError("accepted RK39 arm is not raw random B11")
    calibration_path = Path(job["calibration_dir"]) / f"{rk39.safe_name(job['record_id'])}.json"
    calibration = json.loads(calibration_path.read_text())
    if rk39.sha(calibration_path) != job["calibration_sha256"]:
        raise ValueError("accepted-arm calibration identity mismatch")
    accepted = dict(payload)
    accepted["arm"] = "raw_random_b11"
    accepted["budget"] = 11
    accepted["evaluation"] = evaluate_payload(payload, calibration, job["k"], job["weights"])
    return descriptor(path, accepted)


def valid_existing(path: Path, job: Mapping) -> dict | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    checks = [
        payload.get("schema") == "a8-rk40-budget-initialization-run-v1",
        payload.get("status") == "done", payload.get("protocol_sha256") == job["protocol_sha256"],
        payload.get("code_commit") == job["code_commit"], payload.get("arm") == job["arm"],
        payload.get("record_id") == job["record_id"], payload.get("seed") == job["seed"],
        payload.get("source_sha256") == job["source_sha256"],
        payload.get("initial_state_sha256") == rk39.text_sha(job["initial"]),
        payload.get("budget") == job["budget"], len(payload.get("points", [])) == job["budget"],
        payload.get("unique_scorer_calls") == job["budget"],
        payload.get("terminal_stop") == "TAA",
    ]
    if not all(checks):
        raise ValueError(f"incomplete or mismatched existing run: {path}")
    return payload


def execute_job(job: Mapping) -> dict:
    started = time.perf_counter()
    path = run_path(Path(job["output_root"]), job["record_id"], job["seed"], job["arm"])
    if path.exists():
        if not job.get("resume"):
            raise ValueError(f"refuse to overwrite existing run: {path}")
        existing = valid_existing(path, job)
        assert existing is not None
        return descriptor(path, existing)
    arm = job["arm"]
    initial = job["initial"]
    source_protein = rk39.protein_from_cds(job["source"])
    if rk39.protein_from_cds(initial) != source_protein or not initial.endswith("TAA"):
        raise ValueError("initialization changed protein or fixed stop")
    calibration_path = Path(job["calibration_dir"]) / f"{rk39.safe_name(job['record_id'])}.json"
    if rk39.sha(calibration_path) != job["calibration_sha256"]:
        raise ValueError("calibration artifact identity mismatch")
    calibration = None
    if arm in CALIBRATED:
        calibration = json.loads(calibration_path.read_text())
        normalization = (calibration["reference"], calibration["scale"])
    else:
        normalization = None
    rscu = json.loads(Path(job["rscu_json"]).read_text())
    if rk39.sha(job["rscu_json"]) != job["rscu_sha256"]:
        raise ValueError("RSCU identity mismatch")
    cai_weights = cai_weights_from_rscu(rscu)
    scoring_seconds = [0.0]

    def objectives(sequence):
        before = time.perf_counter()
        values = rk39.objective_vector(sequence, cai_weights, job["gc_target"])
        scoring_seconds[0] += time.perf_counter() - before
        return values

    search = SimpleSearch(initial, objectives, job["weights"], seed=job["seed"],
                          initial_temperature=job["initial_temperature"],
                          final_temperature=job["final_temperature"], rho=job["rho"],
                          uniform_operator=job["uniform_operator"], normalization=normalization)
    result = search.run("hill_climbing", max_unique_scorer=job["budget"],
                        max_attempts=job["max_attempts"])
    if result.status != "done" or len(result.points) != job["budget"]:
        raise ValueError(f"search budget not completed: {job['record_id']} seed{job['seed']} {arm}")
    if [point["budget"] for point in result.points] != list(range(1, job["budget"] + 1)):
        raise ValueError("non-contiguous search budgets")
    for point in result.points:
        if not point["sequence"].endswith("TAA") or rk39.protein_from_cds(point["sequence"]) != source_protein:
            raise ValueError("non-synonymous or changed-stop search output")
        if not np.isfinite(point["objectives"]).all():
            raise ValueError("non-finite objective")
    if calibration is None:
        calibration = json.loads(calibration_path.read_text())
        native_calibration_read_after_search = True
    else:
        native_calibration_read_after_search = False
    if calibration["source_sha256"] != job["source_sha256"] or calibration["record_id"] != job["record_id"]:
        raise ValueError("calibration source or record mismatch")
    payload = {
        "schema": "a8-rk40-budget-initialization-run-v1", "status": "done",
        "protocol_id": job["protocol_id"], "protocol_sha256": job["protocol_sha256"],
        "code_commit": job["code_commit"], "record_id": job["record_id"],
        "seed": job["seed"], "arm": arm, "source_sha256": job["source_sha256"],
        "rscu_sha256": job["rscu_sha256"], "calibration_sha256": job["calibration_sha256"],
        "initial_state": initial, "initial_state_sha256": rk39.text_sha(initial),
        "external_initialization": arm in EXTERNAL,
        "external_initialization_rule": "first_frozen_matrix_point" if arm in EXTERNAL else None,
        "search_normalization": "frozen_native_development_calibration" if arm in CALIBRATED else None,
        "native_calibration_read_before_search": arm in CALIBRATED,
        "native_calibration_read_after_search": native_calibration_read_after_search,
        "common_input": arm in {"raw_random_b11", "raw_random_b101"},
        "terminal_stop": "TAA", "budget": job["budget"],
        "points": [{"budget": p["budget"], "sequence": p["sequence"], "objectives": p["objectives"]}
                   for p in result.points],
        "unique_scorer_calls": len(result.points), "max_attempts": job["max_attempts"],
        "proposal_attempts": result.attempts, "terminal_evaluations": result.terminal_evaluations,
        "cache_hits": result.terminal_evaluations - len(result.points),
        "model_forward_calls": 0, "cache_before_requests": 0,
        "objective_scoring_seconds": float(scoring_seconds[0]),
        "residual_generation_cache_proposal_seconds": float(max(0.0, result.elapsed_s - scoring_seconds[0])),
        "search_wall_seconds": float(result.elapsed_s),
        "run_wall_seconds_including_evaluation": float(time.perf_counter() - started),
        "time_matched_comparison": False, "functional_untouched_evaluated": False,
        "sota_claim": False,
    }
    payload["evaluation"] = evaluate_payload(payload, calibration, job["k"], job["weights"])
    rk39.atomic_json(path, payload)
    return descriptor(path, payload)


def contrast(data: Mapping, records: Sequence[str], seeds: Sequence[int],
             left: str, right: str, endpoint: str, protocol: Mapping,
             family: str, confirmatory: bool) -> dict:
    values = np.asarray([[data[(record, seed, left)][endpoint] - data[(record, seed, right)][endpoint]
                          for seed in seeds] for record in records], dtype=float)
    test = rk39.paired_test(values.mean(axis=1), protocol)
    test.update({"family": family, "contrast": f"{left} minus {right}", "left": left,
                 "right": right, "endpoint": endpoint, "seed_mean_effects": values.mean(axis=0).tolist(),
                 "all_seed_effects_positive": bool(np.all(values.mean(axis=0) > 0)),
                 "confirmatory": confirmatory, "supported_advantage": None, "holm_p": None})
    return test


def decision_label(n_normalization: bool, n_budget: bool) -> str:
    if n_normalization and n_budget:
        return "NORMALIZATION_AND_SHORT_BUDGET_BOTH_CONTRIBUTE"
    if n_normalization:
        return "SEARCH_SCALE_MISMATCH_SUPPORTED_AT_SHORT_BUDGET"
    if n_budget:
        return "SHORT_BUDGET_LIMIT_SUPPORTED_WITHIN_RAW_SEARCH"
    return "NO_RESCUE_FROM_NORMALIZATION_OR_RAW_BUDGET"


def inference(descriptors: Sequence[Mapping], records: Sequence[str], protocol: Mapping) -> dict:
    data = {(row["record_id"], row["seed"], row["arm"]): row for row in descriptors}
    tests = []
    for family, left, right in PRIMARY_CONTRASTS:
        for endpoint in protocol["primary_endpoints"]:
            tests.append(contrast(data, records, protocol["seeds"], left, right, endpoint,
                                  protocol, family, True))
    for family, left, right in DIAGNOSTIC_CONTRASTS:
        for endpoint in protocol["primary_endpoints"]:
            tests.append(contrast(data, records, protocol["seeds"], left, right, endpoint,
                                  protocol, family, False))
    family_pass = {}
    for family, _, _ in PRIMARY_CONTRASTS:
        primary = [row for row in tests if row["family"] == family and row["confirmatory"]]
        for row, adjusted in zip(primary, rk39.holm_adjust([row["sign_flip_p"] for row in primary])):
            row["holm_p"] = float(adjusted)
            row["supported_advantage"] = bool(row["ci95"][0] > 0 and adjusted < 0.05
                                                and row["all_seed_effects_positive"])
        family_pass[family] = bool(all(row["supported_advantage"] for row in primary))
    per_record = []
    for record in records:
        arms = {}
        for arm in protocol["all_analysis_arms"]:
            arms[arm] = {str(seed): {endpoint: data[(record, seed, arm)][endpoint]
                                     for endpoint in protocol["primary_endpoints"]}
                         for seed in protocol["seeds"]}
        per_record.append({"record_id": record, "arms": arms})
    absolute = {}
    for arm in protocol["all_analysis_arms"]:
        absolute[arm] = {endpoint: float(np.mean([data[(record, seed, arm)][endpoint]
                                                  for record in records for seed in protocol["seeds"]]))
                         for endpoint in protocol["primary_endpoints"]}
    return {"tests": tests, "primary_family_pass": family_pass,
            "primary_gate_passed": bool(all(family_pass.values())),
            "decision": decision_label(family_pass["normalization_at_short_budget"],
                                       family_pass["budget_within_raw_search"]),
            "per_record": per_record, "absolute_performance": absolute}


def trajectory_identity(descriptors: Sequence[Mapping], records: Sequence[str], seeds: Sequence[int]) -> dict:
    paths = {(row["record_id"], row["seed"], row["arm"]): Path(row["path"]) for row in descriptors}
    checks = []
    for record in records:
        for seed in seeds:
            for long_arm, short_arm in (("raw_random_b101", "raw_random_b11"),
                                        ("calibrated_random_b101", "calibrated_random_b11")):
                long = json.loads(paths[(record, seed, long_arm)].read_text())
                short = json.loads(paths[(record, seed, short_arm)].read_text())
                for index in range(11):
                    a, b = long["points"][index], short["points"][index]
                    checks.append(bool(a["budget"] == b["budget"] == index + 1
                                       and a["sequence"] == b["sequence"]
                                       and np.allclose(a["objectives"], b["objectives"], rtol=0, atol=0)))
    return {"n_checks": len(checks), "n_pass": sum(checks), "status": "PASS" if all(checks) else "FAIL"}


def external_reference(matrix_records: Mapping, records: Sequence[str], protocol: Mapping) -> dict:
    output = {}
    for record in records:
        row = matrix_records[record]
        calibration_path = Path(protocol["calibration_dir"]) / f"{rk39.safe_name(record)}.json"
        calibration = json.loads(calibration_path.read_text())
        if rk39.sha(calibration_path) != row["calibration_sha256"]:
            raise ValueError("external-reference calibration identity mismatch")
        method = row["methods"]["lineardesign_lambda11"]
        payload = {"points": [{"budget": index + 1, "sequence": point["sequence"],
                               "objectives": point["objectives"]} for index, point in enumerate(method["points"])]}
        evaluation = evaluate_payload(payload, calibration, len(method["points"]), protocol["weights"])
        output[record] = {**evaluation, "k": len(method["points"])}
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/a8_rk40_budget_initialization_protocol_v1.json")
    parser.add_argument("--output-root")
    parser.add_argument("--summary")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    protocol_path = ROOT / args.protocol
    protocol = json.loads(protocol_path.read_text())
    if protocol["status"] != "FROZEN_BEFORE_PRODUCTION":
        raise ValueError("protocol is not frozen")
    protocol_sha = rk39.sha(protocol_path)
    benchmark = dict((header.split()[0], sequence)
                     for header, sequence in read_fasta(protocol["benchmark_fasta"]))
    matrix_path = Path(protocol["external_matrix"])
    if rk39.sha(matrix_path) != protocol["external_matrix_sha256"]:
        raise ValueError("external matrix identity mismatch")
    matrix_records = {row["record_id"]: row for row in json.loads(matrix_path.read_text())["records"]}
    if set(benchmark) != set(matrix_records) or len(benchmark) != 18:
        raise ValueError("benchmark/external population mismatch")
    for key in ("benchmark_fasta", "rscu_json", "calibration_acceptance", "rk39_summary"):
        if rk39.sha(protocol[key]) != protocol[key + "_sha256"]:
            raise ValueError(f"input identity mismatch: {key}")
    code_commit, dirty = rk39.git_state()
    if not args.smoke and dirty:
        raise ValueError("formal production requires a clean worktree")
    output_root = Path(args.output_root or protocol["artifact_root"])
    summary_path = Path(args.summary or protocol["summary"])
    records = [protocol["execution"]["smoke_record"]] if args.smoke else list(benchmark)
    seeds = [protocol["execution"]["smoke_seed"]] if args.smoke else protocol["seeds"]
    jobs = []
    accepted = []
    for record in records:
        source = benchmark[record]
        external_row = matrix_records[record]
        points = external_row["methods"]["lineardesign_lambda11"]["points"]
        k = len(points)
        for seed in seeds:
            base = {**protocol, "protocol_path": str(protocol_path), "protocol_sha256": protocol_sha,
                    "code_commit": code_commit, "output_root": str(output_root), "record_id": record,
                    "source": source, "source_sha256": rk39.text_sha(source), "seed": seed, "k": k,
                    "calibration_sha256": external_row["calibration_sha256"]}
            accepted.append(accepted_raw_b11(base))
            for arm in protocol["new_arms"]:
                jobs.append({**base, "arm": arm, "budget": ARM_BUDGET[arm],
                             "initial": initial_for_arm(arm, source, seed, points)})
    expected_runs = protocol["execution"]["smoke_expected_new_runs"] if args.smoke else protocol["expected_new_run_count"]
    expected_calls = protocol["execution"]["smoke_expected_new_unique_scorer_calls"] if args.smoke else protocol["expected_new_unique_scorer_calls"]
    if len(jobs) != expected_runs or sum(job["budget"] for job in jobs) != expected_calls:
        raise ValueError("job or scorer-call count mismatch")
    for job in jobs:
        if run_path(output_root, job["record_id"], job["seed"], job["arm"]).exists() and not args.resume:
            raise ValueError("output already exists; use a new root or explicit validated resume")
    started = time.perf_counter()
    if args.workers == 1:
        new_descriptors = [execute_job(job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            new_descriptors = list(pool.map(execute_job, jobs))
    all_descriptors = accepted + new_descriptors
    trajectory = trajectory_identity(all_descriptors, records, seeds)
    if trajectory["status"] != "PASS":
        raise ValueError("long/short trajectory identity failed")
    base = {
        "schema": "a8-rk40-budget-initialization-summary-v1", "protocol_id": protocol["protocol_id"],
        "protocol_path": str(protocol_path), "protocol_sha256": protocol_sha,
        "code_commit": code_commit, "code_tracked_dirty_at_launch": dirty,
        "status": "PASS_SMOKE" if args.smoke else "PASS_COMPLETE_MECHANISM_EVALUATION",
        "smoke": bool(args.smoke), "artifact_root": str(output_root),
        "benchmark_sha256": protocol["benchmark_sha256"], "external_matrix_sha256": protocol["external_matrix_sha256"],
        "rk39_summary_sha256": protocol["rk39_summary_sha256"], "rk39_independent_sha256": protocol["rk39_independent_sha256"],
        "n_new_runs": len(new_descriptors), "n_new_unique_scorer_calls": sum(row["unique_scorer_calls"] for row in new_descriptors),
        "n_accepted_rk39_runs": len(accepted), "runs": all_descriptors,
        "trajectory_identity": trajectory, "wall_seconds": float(time.perf_counter() - started),
        "functional_untouched_evaluated": False, "untouched24_evaluated": False,
        "new_functional_labels_read": False, "dense_external_curve_inferred": False,
        "time_matched_comparison": False, "external_sota_authorized": False,
        "scientific_gate_passed": False, "sota_claim": False, "rk_g1_pass": False,
        "manuscript_submittable": False,
    }
    if base["n_new_unique_scorer_calls"] != expected_calls:
        raise ValueError("unique-scorer total mismatch")
    if args.smoke:
        base["smoke_gate_passed"] = True
    else:
        external = external_reference(matrix_records, records, protocol)
        base["external_reference"] = external
        base.update(inference(all_descriptors, records, protocol))
        base["allowed_conclusion"] = protocol["allowed_conclusion"]
        base["forbidden_conclusion"] = protocol["forbidden_conclusion"]
    rk39.atomic_json(summary_path, base)
    print(json.dumps({"summary": str(summary_path), "summary_sha256": rk39.sha(summary_path),
                      "n_new_runs": base["n_new_runs"], "n_new_unique_scorer_calls": base["n_new_unique_scorer_calls"],
                      "trajectory_identity": trajectory, "decision": base.get("decision", "SMOKE_ONLY")}, indent=2))


if __name__ == "__main__":
    main()
