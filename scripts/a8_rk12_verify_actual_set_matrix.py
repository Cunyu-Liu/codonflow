#!/usr/bin/env python3
"""Independent raw-CDS, hypervolume and paired-statistics verification for RK-12."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import RNA
from pymoo.indicators.hv import HV
from rapidfuzz.distance import Levenshtein

from scripts.a8_rk12_verify_lineardesign_unique18 import CODON_TO_AA, read_fasta, sha256, translate

MOTIFS = ["AATAAA", "ATTAAA", "GTGAGT", "CAGG", "TAATACGACTCACTATA", "ATTTAGGTGACACTAT"]


def motif_penalty(sequence: str) -> float:
    count = 0
    for pattern in MOTIFS:
        count += len(re.findall(f"(?={pattern})", sequence))
    for base in "ACGT":
        count += sum(len(run) for run in re.findall(f"{base}{{6,}}", sequence))
    return float(count)


def cai_weights(rscu: dict) -> dict[str, float]:
    groups = {}
    for codon, aa in CODON_TO_AA.items():
        if aa != "*":
            groups.setdefault(aa, []).append(codon)
    weights = {}
    for group in groups.values():
        best = max(float(rscu.get(codon, 0.0)) for codon in group)
        for codon in group:
            weights[codon] = float(rscu.get(codon, 0.0)) / best if best > 0 else 0.0
    return weights


def cai(sequence: str, weights: dict[str, float]) -> float:
    logs = []
    for index in range(0, len(sequence), 3):
        codon = sequence[index:index+3]
        if CODON_TO_AA[codon] == "*":
            continue
        weight = weights.get(codon, 0.0)
        if weight > 0:
            logs.append(math.log(weight))
    return math.exp(sum(logs) / len(logs)) if logs else 0.0


def pairwise_ned(sequences: list[str]) -> float:
    if len(sequences) < 2:
        return 0.0
    total = 0.0
    pairs = 0
    for i, left in enumerate(sequences):
        for right in sequences[i+1:]:
            total += Levenshtein.distance(left, right) / max(len(left), len(right))
            pairs += 1
    return total / pairs


def fold_sequence(sequence: str) -> float:
    _structure, value = RNA.fold_compound(sequence.replace("T", "U")).mfe()
    return float(value)


def normalized_hv(objectives: np.ndarray, reference: np.ndarray, scale: np.ndarray) -> float:
    normalized = (objectives - reference) / scale
    keep = np.all(normalized >= -1e-12, axis=1)
    normalized = normalized[keep]
    if not len(normalized):
        return 0.0
    return float(HV(ref_point=np.zeros(normalized.shape[1]))(-normalized))


def pareto_count(objectives: np.ndarray, reference: np.ndarray, scale: np.ndarray) -> tuple[int, int]:
    normalized = (objectives - reference) / scale
    unique = np.unique(normalized, axis=0)
    count = 0
    for index, point in enumerate(unique):
        dominated = any(
            other_index != index and np.all(other >= point) and np.any(other > point)
            for other_index, other in enumerate(unique)
        )
        if not dominated:
            count += 1
    return len(unique), count


def bootstrap(values: np.ndarray, resamples: int, seed: int) -> tuple[list[float], float]:
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(resamples, len(values)))
    distribution = values[indices].mean(axis=1)
    ci = np.quantile(distribution, [0.025, 0.975]).tolist()
    p_less = (1 + int(np.sum(distribution <= 0.0))) / (resamples + 1)
    p_greater = (1 + int(np.sum(distribution >= 0.0))) / (resamples + 1)
    return ci, min(1.0, 2.0 * min(p_less, p_greater))


def holm(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values, key=p_values.get)
    result = {}
    running = 0.0
    for index, key in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - index) * p_values[key]))
        result[key] = running
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--grid-report", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mfe-workers", type=int, default=1)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    started = time.perf_counter()
    protocol = json.loads(args.protocol.read_text())
    matrix = json.loads(args.matrix.read_text())
    grid = json.loads(args.grid_report.read_text())
    if matrix["status"] != "COMPLETE_UNIQUE18_ACTUAL_SET_MATRIX_DEVELOPMENT_ONLY":
        raise ValueError("matrix is not complete")
    benchmark = Path(protocol["benchmark_fasta"])
    records = read_fasta(benchmark)
    rscu = json.loads(Path(protocol["rscu_json"]).read_text())
    weights = cai_weights(rscu)
    expected_methods = [protocol["new_method"]] + protocol["legacy_methods"] + [protocol["secondary_legacy_method_not_in_primary"]]
    checks = []
    failures = []
    max_objective_delta = 0.0
    max_hv_delta = 0.0
    max_ned_delta = 0.0
    mfe_cache = {}
    if args.mfe_workers < 1:
        raise ValueError("--mfe-workers must be positive")
    unique_sequences = sorted({
        point["sequence"]
        for record_result in matrix["records"]
        for method in record_result["methods"].values()
        for point in method["points"]
    })
    if args.mfe_workers > 1:
        with ProcessPoolExecutor(max_workers=args.mfe_workers) as pool:
            values = list(pool.map(fold_sequence, unique_sequences, chunksize=8))
        mfe_cache.update(zip(unique_sequences, values))

    def record(name, passed, evidence=None):
        checks.append({"check": name, "pass": bool(passed), "evidence": evidence})
        if not passed:
            failures.append(name)

    def fold(sequence):
        if sequence not in mfe_cache:
            mfe_cache[sequence] = fold_sequence(sequence)
        return mfe_cache[sequence]

    record("matrix_protocol_hash", matrix["protocol_sha256"] == sha256(args.protocol))
    record("matrix_grid_hash", matrix["grid_report_sha256"] == sha256(args.grid_report))
    record("record_order_and_count", len(matrix["records"]) == 18 and [r["record_id"] for r in matrix["records"]] == list(records))
    record("raw_rescoring_declaration", matrix["objectives_recomputed_from_raw_sequences"] is True and matrix["stored_objectives_used_for_scoring"] is False)
    record("excluded_claims", matrix["dense_budget_step_auc_v2"] is None and matrix["time_matched_comparison"] is False and matrix["scientific_gate_passed"] is False and matrix["sota_claim"] is False)
    recomputed_metrics = {r["record_id"]: {} for r in matrix["records"]}
    for record_result in matrix["records"]:
        record_id = record_result["record_id"]
        source = records[record_id]
        source_protein = translate(source)
        calibration_path = Path(record_result["calibration"])
        calibration = json.loads(calibration_path.read_text())
        reference = np.asarray(calibration["reference"], dtype=float)
        scale = np.asarray(calibration["scale"], dtype=float)
        if list(record_result["methods"]) != expected_methods:
            record(f"method_set:{record_id}", False, list(record_result["methods"]))
            continue
        a6 = json.loads(Path(record_result["a6_payload"]).read_text())
        grid_runs = [run for run in grid["runs"] if run["record_id"] == record_id]
        expected_sequences = {
            protocol["new_method"]: list(dict.fromkeys(run["evaluation_sequence_dna"] for run in grid_runs)),
            **{name: a6["methods"][name]["solutions"] for name in protocol["legacy_methods"] + [protocol["secondary_legacy_method_not_in_primary"]]},
        }
        for name, method in record_result["methods"].items():
            points = method["points"]
            sequences = [point["sequence"] for point in points]
            method_ok = sequences == expected_sequences[name]
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
            recomputed_metrics[record_id][name] = {"hypervolume_normalized": hv, "ned": ned}
            record(f"raw_objectives_actual_set:{record_id}:{name}", method_ok, {"hv": hv, "ned": ned, "n": len(sequences)})
        measured = sum(run["elapsed_s"] for run in grid_runs)
        record(f"new_cost:{record_id}", math.isclose(measured, record_result["methods"][protocol["new_method"]]["measured_generation_cost"]["wall_clock_seconds"], rel_tol=0.0, abs_tol=1e-9), measured)
    recomputed_comparisons = {}
    raw_p = {}
    for comparator_index, comparator in enumerate(protocol["primary_comparators"]):
        for metric_index, metric in enumerate(["hypervolume_normalized", "ned"]):
            key = f"{protocol['new_method']}_minus_{comparator}:{metric}"
            new = np.asarray([recomputed_metrics[r["record_id"]][protocol["new_method"]][metric] for r in matrix["records"]])
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
            recomputed_comparisons[key] = {"ci95": ci, "p": p_value}
            raw_p[key] = p_value
            record(f"paired_effect:{key}", ok, {"mean_effect": float(effects.mean()), "ci95": ci, "p": p_value})
    adjusted = holm(raw_p)
    for key, value in adjusted.items():
        record(f"holm:{key}", math.isclose(value, matrix["primary_comparisons"][key]["holm_p_four_primary"], rel_tol=0.0, abs_tol=1e-12), value)
    report = {
        "schema": "a8-rk12-actual-set-matrix-independent-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "matrix": str(args.matrix),
        "matrix_sha256": sha256(args.matrix),
        "protocol_sha256": sha256(args.protocol),
        "grid_report_sha256": sha256(args.grid_report),
        "checks": checks,
        "checks_passed": sum(x["pass"] for x in checks),
        "checks_total": len(checks),
        "failed_checks": failures,
        "max_objective_recompute_delta": max_objective_delta,
        "max_hypervolume_recompute_delta": max_hv_delta,
        "max_ned_recompute_delta": max_ned_delta,
        "unique_mfe_sequences_recomputed": len(mfe_cache),
        "mfe_workers": args.mfe_workers,
        "motif_semantics": "frozen production default: every catalogue occurrence weight 1; homopolymer score is summed run length",
        "matrix_production_module_imported": False,
        "elapsed_s_not_generation_cost": time.perf_counter() - started,
        "scope": "independent raw-CDS development actual-set verification; not dense AUC, time-matched cost, functional OOD or SOTA",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
