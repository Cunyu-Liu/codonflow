#!/usr/bin/env python3
"""Independently verify the RK-13 seven-method matrix and all new CDS metrics."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.a8_rk12_verify_actual_set_matrix import (
    bootstrap,
    cai,
    cai_weights,
    fold_sequence,
    holm,
    motif_penalty,
    normalized_hv,
    pairwise_ned,
    pareto_count,
)
from scripts.a8_rk12_verify_lineardesign_unique18 import read_fasta, sha256, translate


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--ensemble-protocol", type=Path, required=True)
    parser.add_argument("--ensemble-report", type=Path, required=True)
    parser.add_argument("--ensemble-independent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mfe-workers", type=int, default=1)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if args.mfe_workers < 1:
        raise ValueError("--mfe-workers must be positive")
    started = time.perf_counter()
    protocol = json.loads(args.protocol.read_text())
    matrix = json.loads(args.matrix.read_text())
    ensemble_protocol = json.loads(args.ensemble_protocol.read_text())
    ensemble = json.loads(args.ensemble_report.read_text())
    ensemble_independent = json.loads(args.ensemble_independent.read_text())
    base_path = Path(protocol["base_matrix"])
    base = json.loads(base_path.read_text())
    base_independent_path = Path(protocol["base_independent"])
    base_finalization_path = Path(protocol["base_finalization"])
    base_independent = json.loads(base_independent_path.read_text())
    base_finalization = json.loads(base_finalization_path.read_text())
    records = read_fasta(Path(protocol["benchmark_fasta"]))
    weights = cai_weights(json.loads(Path(protocol["rscu_json"]).read_text()))
    checks = []
    failures = []
    max_objective_delta = 0.0
    max_hv_delta = 0.0
    max_ned_delta = 0.0

    def record(name, passed, evidence=None):
        checks.append({"check": name, "pass": bool(passed), "evidence": evidence})
        if not passed:
            failures.append(name)

    record("matrix_status", matrix["status"] == "COMPLETE_UNIQUE18_SEVEN_METHOD_ACTUAL_SET_MATRIX_DEVELOPMENT_ONLY")
    record("matrix_protocol_hash", matrix["protocol_sha256"] == sha256(args.protocol))
    record("ensemble_protocol_hash", matrix["ensemble_protocol_sha256"] == sha256(args.ensemble_protocol) and ensemble["protocol_sha256"] == sha256(args.ensemble_protocol))
    record("ensemble_report_hash", matrix["ensemble_report_sha256"] == sha256(args.ensemble_report))
    record("ensemble_independent_binding", ensemble_independent["status"] == "PASS" and ensemble_independent["report_sha256"] == sha256(args.ensemble_report) and matrix["ensemble_independent_sha256"] == sha256(args.ensemble_independent))
    record("base_matrix_hash", sha256(base_path) == protocol["base_matrix_sha256"] == matrix["base_matrix_sha256"])
    record("base_independent_binding", sha256(base_independent_path) == protocol["base_independent_sha256"] and base_independent["status"] == "PASS" and base_independent["matrix_sha256"] == protocol["base_matrix_sha256"])
    record("base_finalization_binding", sha256(base_finalization_path) == protocol["base_finalization_sha256"] and base_finalization["status"].startswith("PASS"))
    record("record_order_and_count", len(matrix["records"]) == 18 and [r["record_id"] for r in matrix["records"]] == list(records) == ensemble_protocol["record_order"])
    record("raw_rescoring_declaration", matrix["added_method_objectives_recomputed_from_raw_sequences"] is True and matrix["stored_objectives_used_for_added_method_scoring"] is False and matrix["base_method_objectives_inherited_from_independently_verified_matrix"] is True)
    record("excluded_claims", matrix["dense_budget_step_auc_v2"] is None and matrix["time_matched_comparison"] is False and matrix["scientific_gate_passed"] is False and matrix["sota_claim"] is False)

    added = protocol["added_method"]
    base_methods = [name for name in protocol["method_order"] if name != added]
    added_sequences = sorted({point["sequence"] for result in matrix["records"] for point in result["methods"][added]["points"]})
    mfe_cache = {}
    if args.mfe_workers > 1:
        with ProcessPoolExecutor(max_workers=args.mfe_workers) as pool:
            values = list(pool.map(fold_sequence, added_sequences, chunksize=4))
            mfe_cache.update(zip(added_sequences, values))

    def fold(sequence):
        if sequence not in mfe_cache:
            mfe_cache[sequence] = fold_sequence(sequence)
        return mfe_cache[sequence]

    recomputed_metrics = {r["record_id"]: {} for r in matrix["records"]}
    for result, base_record, ensemble_record in zip(matrix["records"], base["records"], ensemble["records"]):
        record_id = result["record_id"]
        source = records[record_id]
        source_protein = translate(source)
        record(f"base_record_identity:{record_id}", base_record["record_id"] == record_id and ensemble_record["record_id"] == record_id)
        record(f"method_set:{record_id}", list(result["methods"]) == protocol["method_order"], list(result["methods"]))
        for name in base_methods:
            record(f"base_method_exact_copy:{record_id}:{name}", canonical(result["methods"][name]) == canonical(base_record["methods"][name]))
            recomputed_metrics[record_id][name] = {
                "hypervolume_normalized": result["methods"][name]["actual_set"]["hypervolume_normalized"],
                "ned": result["methods"][name]["ned"],
            }
        calibration = json.loads(Path(result["calibration"]).read_text())
        reference = np.asarray(calibration["reference"], dtype=float)
        scale = np.asarray(calibration["scale"], dtype=float)
        method = result["methods"][added]
        points = method["points"]
        sequences = [point["sequence"] for point in points]
        expected_sequences = list(dict.fromkeys(run["evaluation_sequence_dna"] for run in ensemble_record["runs"]))
        method_ok = sequences == expected_sequences
        method_ok = method_ok and len(sequences) == len(set(sequences)) == method["actual_set"]["n_actual_outputs"]
        objective_rows = []
        for point in points:
            sequence = point["sequence"]
            if len(sequence) != len(source) or translate(sequence) != source_protein:
                method_ok = False
            mfe = fold(sequence)
            objectives = [
                cai(sequence, weights),
                -mfe,
                -abs((sequence.count("G") + sequence.count("C")) / len(sequence) - 0.55),
                -motif_penalty(sequence) / (len(sequence) // 3),
            ]
            objective_rows.append(objectives)
            delta = float(np.max(np.abs(np.asarray(objectives) - np.asarray(point["objectives"], dtype=float))))
            max_objective_delta = max(max_objective_delta, delta)
            if delta > 1e-9:
                method_ok = False
        objective_array = np.asarray(objective_rows, dtype=float)
        hv = normalized_hv(objective_array, reference, scale)
        unique_count, pareto = pareto_count(objective_array, reference, scale)
        ned = pairwise_ned(sequences)
        hv_delta = abs(hv - method["actual_set"]["hypervolume_normalized"])
        ned_delta = abs(ned - method["ned"])
        max_hv_delta = max(max_hv_delta, hv_delta)
        max_ned_delta = max(max_ned_delta, ned_delta)
        method_ok = method_ok and hv_delta <= 1e-9 and ned_delta <= 1e-9
        method_ok = method_ok and unique_count == method["actual_set"]["n_unique_objective_vectors"] and pareto == method["actual_set"]["n_pareto_points"]
        method_ok = method_ok and method["actual_set"]["dense_budget_step_auc_v2"] is None
        record(f"raw_objectives_actual_set:{record_id}:{added}", method_ok, {"hv": hv, "ned": ned, "n": len(sequences)})
        record(f"added_cost:{record_id}", math.isclose(ensemble_record["elapsed_s"], method["measured_generation_cost"]["wall_clock_seconds"], rel_tol=0.0, abs_tol=1e-9), ensemble_record["elapsed_s"])
        recomputed_metrics[record_id][added] = {"hypervolume_normalized": hv, "ned": ned}

    recomputed_comparisons = {}
    raw_p = {}
    reference_name = protocol["reference_method"]
    for comparator_index, comparator in enumerate(protocol["primary_comparators"]):
        for metric_index, metric in enumerate(["hypervolume_normalized", "ned"]):
            key = f"{reference_name}_minus_{comparator}:{metric}"
            new = np.asarray([recomputed_metrics[r["record_id"]][reference_name][metric] for r in matrix["records"]])
            old = np.asarray([recomputed_metrics[r["record_id"]][comparator][metric] for r in matrix["records"]])
            effects = new - old
            ci, p_value = bootstrap(effects, protocol["statistics"]["paired_bootstrap_resamples"], protocol["statistics"]["bootstrap_seed"] + 100 * comparator_index + metric_index)
            expected = matrix["primary_comparisons"][key]
            ok = (
                math.isclose(float(new.mean()), expected["new_mean"], rel_tol=0.0, abs_tol=1e-9)
                and math.isclose(float(old.mean()), expected["comparator_mean"], rel_tol=0.0, abs_tol=1e-9)
                and math.isclose(float(effects.mean()), expected["mean_effect"], rel_tol=0.0, abs_tol=1e-9)
                and np.max(np.abs(effects - np.asarray(expected["per_record_effects"]))) <= 1e-9
                and np.max(np.abs(np.asarray(ci) - np.asarray(expected["ci95"]))) <= 1e-9
                and math.isclose(p_value, expected["bootstrap_p_two_sided"], rel_tol=0.0, abs_tol=1e-12)
            )
            recomputed_comparisons[key] = {"mean_effect": float(effects.mean()), "ci95": ci, "p": p_value}
            raw_p[key] = p_value
            record(f"paired_effect:{key}", ok, recomputed_comparisons[key])
    adjusted = holm(raw_p)
    for key, value in adjusted.items():
        record(f"holm:{key}", math.isclose(value, matrix["primary_comparisons"][key]["holm_p_twelve_primary"], rel_tol=0.0, abs_tol=1e-12), value)

    summary_ok = True
    for name in protocol["method_order"]:
        hv = np.asarray([recomputed_metrics[r["record_id"]][name]["hypervolume_normalized"] for r in matrix["records"]])
        ned = np.asarray([recomputed_metrics[r["record_id"]][name]["ned"] for r in matrix["records"]])
        outputs = sum(r["methods"][name]["actual_set"]["n_actual_outputs"] for r in matrix["records"])
        expected = matrix["method_summary"][name]
        summary_ok = summary_ok and math.isclose(float(hv.mean()), expected["mean_hypervolume_normalized"], abs_tol=1e-9)
        summary_ok = summary_ok and math.isclose(float(np.median(hv)), expected["median_hypervolume_normalized"], abs_tol=1e-9)
        summary_ok = summary_ok and math.isclose(float(ned.mean()), expected["mean_ned"], abs_tol=1e-9)
        summary_ok = summary_ok and math.isclose(float(np.median(ned)), expected["median_ned"], abs_tol=1e-9)
        summary_ok = summary_ok and outputs == expected["total_actual_outputs"]
        summary_ok = summary_ok and math.isclose(min(r["methods"][name]["identity_rate"] for r in matrix["records"]), expected["min_identity_rate"], abs_tol=1e-12)
    record("method_summary", summary_ok)
    expected_highest = max(matrix["method_summary"], key=lambda name: matrix["method_summary"][name]["mean_hypervolume_normalized"])
    record("descriptive_highest", matrix["descriptive_highest_mean_hv_method"] == expected_highest and matrix["descriptive_ranking_not_sota"] is True, expected_highest)
    ld_costs = np.asarray([r["methods"][reference_name]["measured_generation_cost"]["wall_clock_seconds"] for r in matrix["records"]])
    ensemble_costs = np.asarray([r["methods"][added]["measured_generation_cost"]["wall_clock_seconds"] for r in matrix["records"]])
    cost = matrix["generation_cost_descriptive_not_time_matched"]
    record("generation_cost_summary", math.isclose(float(ld_costs.sum()), cost[reference_name]["total_seconds"], abs_tol=1e-9) and math.isclose(float(ensemble_costs.sum()), cost[added]["total_seconds"], abs_tol=1e-9) and np.max(np.abs((ld_costs - ensemble_costs) - np.asarray(cost["lineardesign_minus_ensembledesign_seconds_per_record"]))) <= 1e-9 and np.max(np.abs((ld_costs / ensemble_costs) - np.asarray(cost["lineardesign_divided_by_ensembledesign_per_record"]))) <= 1e-9)

    report = {
        "schema": "a8-rk13-seven-method-actual-set-matrix-independent-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "matrix": str(args.matrix),
        "matrix_sha256": sha256(args.matrix),
        "protocol_sha256": sha256(args.protocol),
        "base_matrix_sha256": protocol["base_matrix_sha256"],
        "ensemble_report_sha256": sha256(args.ensemble_report),
        "ensemble_independent_sha256": sha256(args.ensemble_independent),
        "checks": checks,
        "checks_passed": sum(x["pass"] for x in checks),
        "checks_total": len(checks),
        "failed_checks": failures,
        "max_objective_recompute_delta": max_objective_delta,
        "max_hypervolume_recompute_delta": max_hv_delta,
        "max_ned_recompute_delta": max_ned_delta,
        "unique_added_method_mfe_sequences_recomputed": len(mfe_cache),
        "mfe_workers": args.mfe_workers,
        "motif_semantics": "frozen RK-12 production default: every catalogue occurrence weight 1; homopolymer score is summed run length",
        "matrix_production_module_imported": False,
        "base_methods_recomputed_again": False,
        "base_methods_evidence": "exact-field copy from the frozen six-method matrix with separately bound 139/139 independent PASS",
        "elapsed_s_not_generation_cost": time.perf_counter() - started,
        "scope": "independent added-method raw-CDS and seven-method statistics verification; not dense AUC, time-matched cost, functional OOD or SOTA",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
