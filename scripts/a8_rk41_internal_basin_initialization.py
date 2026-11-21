#!/usr/bin/env python3
"""RK41 fixed-budget internal multistart basin-initialization discrimination."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import sys
import time
from typing import Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import a8_rk39_common_input_actual_set as rk39
import a8_rk40_budget_initialization as rk40
from codonflow.data.dataset import read_fasta
from codonflow.eval.anytime import FrozenReference
from codonflow.eval.metrics import cai_weights_from_rscu
from codonflow.models.simple_search import single_codon_proposal

EXTERNAL = "lineardesign_lambda11"
RAW_POOL = {"raw_pool_first_b11", "raw_pool_best_b11"}
CALIBRATED_POOL = {"calibrated_pool_first_b11", "calibrated_pool_best_b11"}
NEW_ARMS = ["raw_pool_first_b11", "raw_pool_best_b11", "calibrated_pool_first_b11", "calibrated_pool_best_b11"]
BEST_ENDPOINTS = ["best_normalized_weighted_utility", "best_single_point_normalized_hv"]
ACTUAL_ENDPOINTS = ["first_k_hv", "first_k_ned"]
DIAGNOSTIC_CONTRASTS = [
    ("calibrated_basin_selection_within_matched_pool", "calibrated_pool_best_b11", "calibrated_pool_first_b11", BEST_ENDPOINTS),
    ("calibrated_multistart_vs_sequential", "calibrated_pool_best_b11", "calibrated_random_b11", BEST_ENDPOINTS),
    ("normalization_within_best_multistart", "calibrated_pool_best_b11", "raw_pool_best_b11", BEST_ENDPOINTS),
    ("raw_multistart_vs_external_best_single", "raw_pool_best_b11", EXTERNAL, BEST_ENDPOINTS),
    ("raw_basin_selection_actual_set", "raw_pool_best_b11", "raw_pool_first_b11", ACTUAL_ENDPOINTS),
]


def run_path(output_root: Path, record_id: str, seed: int, arm: str) -> Path:
    return output_root / "runs" / rk39.safe_name(record_id) / f"seed{seed}" / f"{arm}.json"


def generate_pool(source: str, seed: int, pool_size: int = 8, max_attempts: int = 1000) -> tuple[list[str], list[int]]:
    """Generate a fixed protein-only pool without external or native synonymous sequences."""
    sequences = [rk39.protein_only_initial(source, seed)]
    generation_seeds = [seed]
    candidate_seed = seed
    attempts = 0
    while len(sequences) < pool_size and attempts < max_attempts:
        attempts += 1
        candidate_seed += 1000
        candidate = rk39.protein_only_initial(source, candidate_seed)
        if candidate not in sequences:
            sequences.append(candidate)
            generation_seeds.append(candidate_seed)
    if len(sequences) != pool_size or len(set(sequences)) != pool_size:
        raise ValueError("unable to construct the frozen unique initialization pool")
    return sequences, generation_seeds


def utility(objectives: Sequence[float], weights: Sequence[float],
            normalization: tuple[Sequence[float], Sequence[float]] | None) -> float:
    values = np.asarray(objectives, dtype=float)
    if normalization is not None:
        reference, scale = (np.asarray(item, dtype=float) for item in normalization)
        values = (values - reference) / scale
    return float(values @ np.asarray(weights, dtype=float))


def select_pool_index(arm: str, pool_objectives: Sequence[Sequence[float]], weights: Sequence[float],
                      normalization: tuple[Sequence[float], Sequence[float]] | None) -> int:
    if arm.endswith("first_b11"):
        return 0
    if not arm.endswith("best_b11"):
        raise ValueError(f"unknown pool-selection arm: {arm}")
    values = [utility(row, weights, normalization) for row in pool_objectives]
    return int(np.argmax(np.asarray(values, dtype=float)))


def descriptor(path: Path, payload: Mapping) -> dict:
    base = rk40.descriptor(path, payload)
    evaluation = payload["evaluation"]
    base.update({
        "initial_normalized_weighted_utility": evaluation["initial_normalized_weighted_utility"],
        "initial_single_point_normalized_hv": evaluation["initial_single_point_normalized_hv"],
        "pool_selection_index": payload["pool_selection_index"],
        "pool_selection_rule": payload["pool_selection_rule"],
    })
    return base


def accepted_baseline(job: Mapping, arm: str) -> dict:
    if arm not in {"raw_random_b11", "calibrated_random_b11"}:
        raise ValueError("only frozen RK40 short random arms may be accepted")
    summary_path = Path(job["rk40_summary"])
    if rk39.sha(summary_path) != job["rk40_summary_sha256"]:
        raise ValueError("RK40 summary identity mismatch")
    summary = json.loads(summary_path.read_text())
    row = next(row for row in summary["runs"]
               if row["record_id"] == job["record_id"] and row["seed"] == job["seed"] and row["arm"] == arm)
    path = Path(row["path"])
    if rk39.sha(path) != row["sha256"]:
        raise ValueError(f"accepted RK40 run identity mismatch: {path}")
    payload = json.loads(path.read_text())
    if len(payload["points"]) != 11 or payload.get("arm", arm) != arm or payload["unique_scorer_calls"] != 11:
        raise ValueError("accepted RK40 arm is not the frozen B11 arm")
    calibration_path = Path(job["calibration_dir"]) / f"{rk39.safe_name(job['record_id'])}.json"
    calibration = json.loads(calibration_path.read_text())
    if rk39.sha(calibration_path) != job["calibration_sha256"]:
        raise ValueError("accepted-arm calibration identity mismatch")
    accepted = dict(payload)
    accepted["arm"] = arm
    accepted["budget"] = 11
    accepted["evaluation"] = rk40.evaluate_payload(payload, calibration, job["k"], job["weights"])
    return rk40.descriptor(path, accepted)


def valid_existing(path: Path, job: Mapping) -> dict | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    checks = [
        payload.get("schema") == "a8-rk41-internal-basin-run-v1", payload.get("status") == "done",
        payload.get("protocol_sha256") == job["protocol_sha256"], payload.get("code_commit") == job["code_commit"],
        payload.get("arm") == job["arm"], payload.get("record_id") == job["record_id"],
        payload.get("seed") == job["seed"], payload.get("source_sha256") == job["source_sha256"],
        payload.get("budget") == 11, len(payload.get("points", [])) == 11,
        payload.get("unique_scorer_calls") == 11, payload.get("terminal_stop") == "TAA",
        payload.get("initialization_pool") == job["pool"],
        payload.get("pool_generation_seeds") == job["pool_generation_seeds"],
    ]
    if not all(checks):
        raise ValueError(f"incomplete or mismatched existing run: {path}")
    calibration = None
    normalization = None
    if job["arm"] in CALIBRATED_POOL:
        calibration = json.loads((Path(job["calibration_dir"]) / f"{rk39.safe_name(job['record_id'])}.json").read_text())
        normalization = (calibration["reference"], calibration["scale"])
    selected = select_pool_index(job["arm"], [p["objectives"] for p in payload["points"][:8]], job["weights"], normalization)
    if payload["pool_selection_index"] != selected or payload["initial_state"] != job["pool"][selected]:
        raise ValueError(f"existing-run pool selection mismatch: {path}")
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
    source_protein = rk39.protein_from_cds(job["source"])
    calibration_path = Path(job["calibration_dir"]) / f"{rk39.safe_name(job['record_id'])}.json"
    if rk39.sha(calibration_path) != job["calibration_sha256"]:
        raise ValueError("calibration artifact identity mismatch")
    calibration = None
    normalization = None
    if arm in CALIBRATED_POOL:
        calibration = json.loads(calibration_path.read_text())
        normalization = (calibration["reference"], calibration["scale"])
    rscu_path = Path(job["rscu_json"])
    if rk39.sha(rscu_path) != job["rscu_sha256"]:
        raise ValueError("RSCU identity mismatch")
    cai_weights = cai_weights_from_rscu(json.loads(rscu_path.read_text()))
    cache: dict[str, tuple[float, ...]] = {}
    ordered: list[dict] = []
    terminal_evaluations = [0]
    scoring_seconds = [0.0]

    def objectives(sequence: str) -> tuple[float, ...]:
        terminal_evaluations[0] += 1
        if sequence not in cache:
            before = time.perf_counter()
            values = tuple(float(v) for v in rk39.objective_vector(sequence, cai_weights, job["gc_target"]))
            scoring_seconds[0] += time.perf_counter() - before
            if not np.isfinite(values).all():
                raise ValueError("non-finite objective")
            cache[sequence] = values
            ordered.append({"budget": len(ordered) + 1, "sequence": sequence, "objectives": list(values)})
        return cache[sequence]

    pool_started = time.perf_counter()
    pool_objectives = [objectives(sequence) for sequence in job["pool"]]
    pool_seconds = time.perf_counter() - pool_started
    selected_index = select_pool_index(arm, pool_objectives, job["weights"], normalization)
    selected = job["pool"][selected_index]
    if rk39.protein_from_cds(selected) != source_protein or not selected.endswith("TAA"):
        raise ValueError("pool initialization changed protein or fixed stop")
    rng = np.random.default_rng(job["seed"])
    current = selected
    current_objectives = objectives(current)  # shared-cache hit, never an extra unique call
    attempts = 0
    local_started = time.perf_counter()
    while len(ordered) < 11 and attempts < job["max_attempts"]:
        attempts += 1
        candidate = single_codon_proposal(current, rng)
        if rk39.protein_from_cds(candidate) != source_protein or not candidate.endswith("TAA"):
            raise ValueError("non-synonymous or changed-stop proposal")
        candidate_objectives = objectives(candidate)
        delta = utility(candidate_objectives, job["weights"], normalization) - utility(current_objectives, job["weights"], normalization)
        if delta >= 0:
            current, current_objectives = candidate, candidate_objectives
    local_seconds = time.perf_counter() - local_started
    if len(ordered) != 11 or len(cache) != 11:
        raise ValueError(f"shared-cache search budget not completed: {job['record_id']} seed{job['seed']} {arm}")
    if [point["budget"] for point in ordered] != list(range(1, 12)):
        raise ValueError("non-contiguous search budgets")
    for point in ordered:
        if not point["sequence"].endswith("TAA") or rk39.protein_from_cds(point["sequence"]) != source_protein:
            raise ValueError("non-synonymous or changed-stop search output")
    if calibration is None:
        calibration = json.loads(calibration_path.read_text())
        native_calibration_read_after_search = True
    else:
        native_calibration_read_after_search = False
    if calibration["source_sha256"] != job["source_sha256"] or calibration["record_id"] != job["record_id"]:
        raise ValueError("calibration source or record mismatch")
    frozen = FrozenReference.from_dict(calibration)
    selected_normalized = frozen.normalize(np.asarray(cache[selected], dtype=float))
    payload = {
        "schema": "a8-rk41-internal-basin-run-v1", "status": "done",
        "protocol_id": job["protocol_id"], "protocol_sha256": job["protocol_sha256"],
        "code_commit": job["code_commit"], "record_id": job["record_id"], "seed": job["seed"], "arm": arm,
        "source_sha256": job["source_sha256"], "rscu_sha256": job["rscu_sha256"],
        "calibration_sha256": job["calibration_sha256"], "initialization_pool": job["pool"],
        "pool_generation_seeds": job["pool_generation_seeds"], "pool_size": 8,
        "pool_selection_index": selected_index,
        "pool_selection_rule": "first_pool_member" if arm.endswith("first_b11") else "maximum_search_weighted_utility",
        "initial_state": selected, "initial_state_sha256": rk39.text_sha(selected),
        "external_initialization": False, "external_initialization_rule": None,
        "search_normalization": "frozen_native_development_calibration" if normalization is not None else None,
        "native_calibration_read_before_search": normalization is not None,
        "native_calibration_read_after_search": native_calibration_read_after_search,
        "common_input": arm in RAW_POOL, "terminal_stop": "TAA", "budget": 11, "points": ordered,
        "unique_scorer_calls": len(ordered), "max_attempts": job["max_attempts"],
        "proposal_attempts": attempts, "terminal_evaluations": terminal_evaluations[0],
        "cache_hits": terminal_evaluations[0] - len(ordered), "model_forward_calls": 0,
        "objective_scoring_seconds": float(scoring_seconds[0]), "pool_scoring_wall_seconds": float(pool_seconds),
        "local_search_wall_seconds": float(local_seconds),
        "search_wall_seconds": float(pool_seconds + local_seconds),
        "run_wall_seconds_including_evaluation": float(time.perf_counter() - started),
        "time_matched_comparison": False, "functional_untouched_evaluated": False, "sota_claim": False,
    }
    payload["evaluation"] = rk40.evaluate_payload(payload, calibration, job["k"], job["weights"])
    payload["evaluation"].update({
        "initial_normalized_weighted_utility": float(selected_normalized @ np.asarray(job["weights"], dtype=float)),
        "initial_single_point_normalized_hv": float(np.prod(np.maximum(selected_normalized, 0.0))),
    })
    rk39.atomic_json(path, payload)
    return descriptor(path, payload)


def contrast(data: Mapping, external: Mapping, records: Sequence[str], seeds: Sequence[int],
             left: str, right: str, endpoint: str, protocol: Mapping,
             family: str, confirmatory: bool) -> dict:
    def value(record: str, seed: int, arm: str) -> float:
        if arm == EXTERNAL:
            return float(external[record][endpoint])
        return float(data[(record, seed, arm)][endpoint])
    values = np.asarray([[value(record, seed, left) - value(record, seed, right) for seed in seeds]
                         for record in records], dtype=float)
    test = rk39.paired_test(values.mean(axis=1), protocol)
    test.update({"family": family, "contrast": f"{left} minus {right}", "left": left, "right": right,
                 "endpoint": endpoint, "seed_mean_effects": values.mean(axis=0).tolist(),
                 "all_seed_effects_positive": bool(np.all(values.mean(axis=0) > 0)),
                 "confirmatory": confirmatory, "supported_advantage": None, "holm_p": None})
    return test


def decision_label(selection: bool, sequential: bool, external: bool) -> str:
    if external:
        return "INTERNAL_MULTISTART_AND_COMMON_INPUT_PROXY_COMPARISON_SUPPORTED" if selection and sequential else "COMMON_INPUT_PROXY_COMPARISON_SUPPORTED_MECHANISM_PARTIAL"
    if selection and sequential:
        return "INTERNAL_MULTISTART_SUPPORTED_COMMON_INPUT_TASK_UNRESOLVED"
    if selection:
        return "BASIN_SELECTION_ONLY_SUPPORTED_COMMON_INPUT_TASK_UNRESOLVED"
    if sequential:
        return "BUDGET_REALLOCATION_ONLY_SUPPORTED_COMMON_INPUT_TASK_UNRESOLVED"
    return "INTERNAL_MULTISTART_NOT_SUPPORTED_COMMON_INPUT_TASK_UNRESOLVED"


def inference(descriptors: Sequence[Mapping], external: Mapping, records: Sequence[str], protocol: Mapping) -> dict:
    data = {(row["record_id"], row["seed"], row["arm"]): row for row in descriptors}
    tests = []
    for family in protocol["primary_families"]:
        for endpoint in family["endpoints"]:
            tests.append(contrast(data, external, records, protocol["seeds"], family["left"], family["right"],
                                  endpoint, protocol, family["family"], True))
    for family, left, right, endpoints in DIAGNOSTIC_CONTRASTS:
        for endpoint in endpoints:
            tests.append(contrast(data, external, records, protocol["seeds"], left, right, endpoint,
                                  protocol, family, False))
    family_pass = {}
    for family in protocol["primary_families"]:
        name = family["family"]
        primary = [row for row in tests if row["family"] == name and row["confirmatory"]]
        for row, adjusted in zip(primary, rk39.holm_adjust([row["sign_flip_p"] for row in primary])):
            row["holm_p"] = float(adjusted)
            row["supported_advantage"] = bool(row["ci95"][0] > 0 and adjusted < 0.05 and row["all_seed_effects_positive"])
        family_pass[name] = bool(all(row["supported_advantage"] for row in primary))
    endpoints = BEST_ENDPOINTS + ACTUAL_ENDPOINTS + ["initial_normalized_weighted_utility", "initial_single_point_normalized_hv"]
    absolute = {}
    for arm in protocol["all_analysis_arms"]:
        first_row = data[(records[0], protocol["seeds"][0], arm)]
        absolute[arm] = {endpoint: float(np.mean([data[(record, seed, arm)][endpoint]
                                                  for record in records for seed in protocol["seeds"]]))
                         for endpoint in endpoints if endpoint in first_row}
    per_record = []
    for record in records:
        arms = {}
        for arm in protocol["all_analysis_arms"]:
            first_row = data[(record, protocol["seeds"][0], arm)]
            arms[arm] = {str(seed): {endpoint: data[(record, seed, arm)][endpoint]
                                     for endpoint in endpoints if endpoint in first_row}
                         for seed in protocol["seeds"]}
        per_record.append({"record_id": record, "arms": arms})
    selection = family_pass["raw_common_input_basin_selection"]
    sequential = family_pass["raw_common_input_sequential_advantage"]
    external_pass = family_pass["common_input_actual_set_versus_linear_design"]
    return {"tests": tests, "primary_family_pass": family_pass,
            "primary_gate_passed": bool(all(family_pass.values())),
            "common_input_actual_set_gate_passed": external_pass,
            "decision": decision_label(selection, sequential, external_pass),
            "per_record": per_record, "absolute_performance": absolute}


def pool_identity(raw: Mapping, records: Sequence[str], seeds: Sequence[int]) -> dict:
    checks = []
    for record in records:
        for seed in seeds:
            for arm in NEW_ARMS[1:]:
                reference = raw[(record, seed, NEW_ARMS[0])]
                current = raw[(record, seed, arm)]
                checks.extend(a["sequence"] == b["sequence"] for a, b in zip(reference["points"][:8], current["points"][:8]))
    return {"n_checks": len(checks), "n_pass": sum(checks), "status": "PASS" if all(checks) else "FAIL"}


def external_reference(matrix_records: Mapping, records: Sequence[str], protocol: Mapping) -> dict:
    output = {}
    for record in records:
        row = matrix_records[record]
        calibration_path = Path(protocol["calibration_dir"]) / f"{rk39.safe_name(record)}.json"
        calibration = json.loads(calibration_path.read_text())
        if rk39.sha(calibration_path) != row["calibration_sha256"]:
            raise ValueError("external-reference calibration identity mismatch")
        points = row["methods"][EXTERNAL]["points"]
        payload = {"points": [{"budget": index + 1, "sequence": point["sequence"], "objectives": point["objectives"]}
                              for index, point in enumerate(points)]}
        evaluation = rk40.evaluate_payload(payload, calibration, len(points), protocol["weights"])
        output[record] = {**evaluation, "k": len(points),
                          "first_k_hv": evaluation["matched_first_k_actual_set"]["hypervolume_normalized"],
                          "first_k_ned": evaluation["matched_first_k_actual_set"]["pairwise_ned"]}
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/a8_rk41_internal_basin_protocol_v1.json")
    parser.add_argument("--output-root")
    parser.add_argument("--summary")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    protocol_path = ROOT / args.protocol
    protocol = json.loads(protocol_path.read_text())
    if protocol["status"] != "FROZEN_BEFORE_PRODUCTION":
        raise ValueError("protocol is not frozen")
    protocol_sha = rk39.sha(protocol_path)
    benchmark = {header.split()[0]: sequence for header, sequence in read_fasta(protocol["benchmark_fasta"])}
    matrix_path = Path(protocol["external_matrix"])
    if rk39.sha(matrix_path) != protocol["external_matrix_sha256"]:
        raise ValueError("external matrix identity mismatch")
    matrix_records = {row["record_id"]: row for row in json.loads(matrix_path.read_text())["records"]}
    if set(benchmark) != set(matrix_records) or len(benchmark) != 18:
        raise ValueError("benchmark/external population mismatch")
    for key, hash_field in {"benchmark_fasta": "benchmark_sha256", "rscu_json": "rscu_sha256",
                            "calibration_acceptance": "calibration_acceptance_sha256",
                            "rk40_summary": "rk40_summary_sha256"}.items():
        if rk39.sha(protocol[key]) != protocol[hash_field]:
            raise ValueError(f"input identity mismatch: {key}")
    code_commit, dirty = rk39.git_state()
    if not args.smoke and dirty:
        raise ValueError("formal production requires a clean worktree")
    output_root = Path(args.output_root or protocol["artifact_root"])
    summary_path = Path(args.summary or protocol["summary"])
    records = [protocol["execution"]["smoke_record"]] if args.smoke else list(benchmark)
    seeds = [protocol["execution"]["smoke_seed"]] if args.smoke else protocol["seeds"]
    jobs, accepted = [], []
    for record in records:
        source = benchmark[record]
        external_row = matrix_records[record]
        points = external_row["methods"][EXTERNAL]["points"]
        for seed in seeds:
            pool, generation_seeds = generate_pool(source, seed, protocol["pool_size"], protocol["pool_max_attempts"])
            base = {**protocol, "protocol_path": str(protocol_path), "protocol_sha256": protocol_sha,
                    "code_commit": code_commit, "output_root": str(output_root), "record_id": record,
                    "source": source, "source_sha256": rk39.text_sha(source), "seed": seed, "k": len(points),
                    "calibration_sha256": external_row["calibration_sha256"], "pool": pool,
                    "pool_generation_seeds": generation_seeds}
            for arm in ("raw_random_b11", "calibrated_random_b11"):
                accepted.append(accepted_baseline(base, arm))
            for arm in protocol["new_arms"]:
                jobs.append({**base, "arm": arm, "budget": 11})
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
    raw_by_key = {}
    for row in new_descriptors:
        raw_by_key[(row["record_id"], row["seed"], row["arm"])] = json.loads(Path(row["path"]).read_text())
    identity = pool_identity(raw_by_key, records, seeds)
    if identity["status"] != "PASS":
        raise ValueError("matched initialization pools differ across arms")
    base = {
        "schema": "a8-rk41-internal-basin-summary-v1", "protocol_id": protocol["protocol_id"],
        "protocol_path": str(protocol_path), "protocol_sha256": protocol_sha, "code_commit": code_commit,
        "code_tracked_dirty_at_launch": dirty,
        "status": "PASS_SMOKE" if args.smoke else "PASS_COMPLETE_MECHANISM_EVALUATION", "smoke": bool(args.smoke),
        "artifact_root": str(output_root), "benchmark_sha256": protocol["benchmark_sha256"],
        "external_matrix_sha256": protocol["external_matrix_sha256"], "rk40_summary_sha256": protocol["rk40_summary_sha256"],
        "rk40_independent_sha256": protocol["rk40_independent_sha256"], "n_new_runs": len(new_descriptors),
        "n_new_unique_scorer_calls": sum(row["unique_scorer_calls"] for row in new_descriptors),
        "n_accepted_rk40_runs": len(accepted), "runs": all_descriptors, "pool_identity": identity,
        "wall_seconds": float(time.perf_counter() - started), "functional_untouched_evaluated": False,
        "untouched24_evaluated": False, "new_functional_labels_read": False, "dense_external_curve_inferred": False,
        "time_matched_comparison": False, "external_sota_authorized": False, "scientific_gate_passed": False,
        "sota_claim": False, "rk_g1_pass": False, "manuscript_submittable": False,
    }
    if base["n_new_unique_scorer_calls"] != expected_calls:
        raise ValueError("unique-scorer total mismatch")
    if args.smoke:
        base["smoke_gate_passed"] = True
    else:
        external = external_reference(matrix_records, records, protocol)
        base["external_reference"] = external
        base.update(inference(all_descriptors, external, records, protocol))
        base["allowed_conclusion"] = protocol["allowed_conclusion"]
        base["forbidden_conclusion"] = protocol["forbidden_conclusion"]
    rk39.atomic_json(summary_path, base)
    print(json.dumps({"summary": str(summary_path), "summary_sha256": rk39.sha(summary_path),
                      "n_new_runs": base["n_new_runs"], "n_new_unique_scorer_calls": base["n_new_unique_scorer_calls"],
                      "pool_identity": identity, "decision": base.get("decision", "SMOKE_ONLY")}, indent=2))


if __name__ == "__main__":
    main()
