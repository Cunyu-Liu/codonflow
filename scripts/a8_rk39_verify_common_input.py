#!/usr/bin/env python3
"""Independently verify RK39 raw runs, metrics, and paired inference.

This script deliberately does not import the RK39 production implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codonflow.core.codon import STANDARD_TABLE_1, SYNONYMOUS_CODONS, gc_fraction, split_codons
from codonflow.core.motifs import motif_penalty_score
from codonflow.data.dataset import read_fasta
from codonflow.eval.actual_set import summarize_actual_set
from codonflow.eval.anytime import FrozenReference
from codonflow.eval.metrics import cai, cai_weights_from_rscu, mfe, pairwise_ned


def sha(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", text)


def atomic_json(path: Path, payload: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def translate(sequence: str) -> str:
    codons = split_codons(sequence)
    if not codons:
        raise ValueError("empty CDS")
    aas = [STANDARD_TABLE_1[codon] for codon in codons]
    if aas[-1] != "*" or aas.count("*") != 1:
        raise ValueError("invalid stop structure")
    return "".join(aas)


def expected_template(source: str) -> str:
    return "".join("TAA" if aa == "*" else SYNONYMOUS_CODONS[aa][0]
                   for aa in translate(source))


def expected_initial(source: str, seed: int) -> tuple[str, str]:
    template = expected_template(source)
    rng = np.random.default_rng(seed * 1009)
    codons = split_codons(template)
    output = []
    for codon in codons:
        aa = STANDARD_TABLE_1[codon]
        if aa == "*":
            output.append("TAA")
        else:
            options = list(SYNONYMOUS_CODONS[aa])
            output.append(options[int(rng.integers(0, len(options)))])
    return template, "".join(output)


def actual_metrics(points: Sequence[Mapping], frozen: FrozenReference) -> dict:
    rows = [{"output_id": str(index), "sequence": point["sequence"],
             "objectives": point["objectives"]} for index, point in enumerate(points)]
    result = summarize_actual_set(rows, frozen)
    return {
        "n_actual_outputs": len(rows),
        "n_unique_objective_vectors": result["n_unique_objective_vectors"],
        "n_pareto_points": result["n_pareto_points"],
        "hypervolume_normalized": float(result["hypervolume_normalized"]),
        "pairwise_ned": float(pairwise_ned([row["sequence"] for row in rows],
                                            rng=np.random.default_rng(0))),
    }


def holm(p_values: Sequence[float]) -> list[float]:
    order = np.argsort(np.asarray(p_values, dtype=float))
    result = np.empty(len(p_values), dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(p_values) - rank) * p_values[index]))
        result[index] = running
    return result.tolist()


def paired(delta: np.ndarray, protocol: Mapping) -> dict:
    observed = float(np.mean(delta))
    cfg = protocol["statistics"]
    rng = np.random.default_rng(cfg["bootstrap_seed"])
    indices = rng.integers(0, len(delta), size=(cfg["paired_bootstrap_resamples"], len(delta)))
    boots = delta[indices].mean(axis=1)
    rng = np.random.default_rng(cfg["permutation_seed"])
    flips = rng.choice(np.asarray([-1.0, 1.0]),
                       size=(cfg["paired_sign_flip_permutations"], len(delta)))
    null = (flips * delta).mean(axis=1)
    p = min(1.0, (1 + int(np.sum(np.abs(null) >= abs(observed) - 1e-15))) / (len(null) + 1))
    return {"effect": observed, "ci95": np.quantile(boots, [0.025, 0.975]).tolist(),
            "sign_flip_p": float(p), "per_record_effects": delta.tolist()}


def close(a, b, tolerance=1e-11) -> bool:
    return math.isfinite(float(a)) and math.isfinite(float(b)) and abs(float(a) - float(b)) <= tolerance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", default="audits/20261122/RK39/rk39_common_input_actual_set_v1.json")
    parser.add_argument("--output", default="audits/20261122/RK39/rk39_common_input_actual_set_independent_v1.json")
    args = parser.parse_args()
    summary_path = ROOT / args.summary if not Path(args.summary).is_absolute() else Path(args.summary)
    output_path = ROOT / args.output if not Path(args.output).is_absolute() else Path(args.output)
    summary = json.loads(summary_path.read_text())
    protocol_path = Path(summary["protocol_path"])
    protocol = json.loads(protocol_path.read_text())
    matrix_path = Path(protocol["external_matrix"])
    matrix = json.loads(matrix_path.read_text())
    benchmark = dict((header.split()[0], sequence)
                     for header, sequence in read_fasta(protocol["benchmark_fasta"]))
    matrix_records = {row["record_id"]: row for row in matrix["records"]}
    cai_weights = cai_weights_from_rscu(json.loads(Path(protocol["rscu_json"]).read_text()))

    checks = []

    def add(name: str, passed: bool, detail="") -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": str(detail)})

    add("summary_schema", summary.get("schema") == "a8-rk39-common-input-actual-set-summary-v1")
    add("summary_complete", summary.get("status") == "PASS_COMPLETE_COMMON_INPUT_EVALUATION")
    add("not_smoke", summary.get("smoke") is False)
    add("protocol_identity", sha(protocol_path) == summary.get("protocol_sha256"), sha(protocol_path))
    add("protocol_frozen", protocol.get("status") == "FROZEN_BEFORE_PRODUCTION")
    add("benchmark_identity", sha(protocol["benchmark_fasta"]) == protocol["benchmark_sha256"] == summary.get("benchmark_sha256"))
    add("matrix_identity", sha(matrix_path) == protocol["external_matrix_sha256"] == summary.get("external_matrix_sha256"))
    add("rscu_identity", sha(protocol["rscu_json"]) == protocol["rscu_sha256"] == summary.get("rscu_sha256"))
    add("calibration_acceptance_identity", sha(protocol["calibration_acceptance"]) == protocol["calibration_acceptance_sha256"])
    add("clean_launch", summary.get("code_tracked_dirty_at_launch") is False)
    add("code_commit_shape", bool(re.fullmatch(r"[0-9a-f]{40}", summary.get("code_commit", ""))))
    add("run_count", summary.get("n_runs") == len(summary.get("runs", [])) == protocol["expected_run_count"] == 162)
    add("population", set(benchmark) == set(matrix_records) and len(benchmark) == 18)
    add("no_functional_labels", summary.get("new_functional_labels_read") is False and summary.get("functional_untouched_evaluated") is False)
    add("no_sota_or_rkg1", summary.get("sota_claim") is False and summary.get("external_sota_authorized") is False and summary.get("rk_g1_pass") is False)
    add("no_time_matched_claim", summary.get("time_matched_comparison") is False)
    add("no_dense_inference", summary.get("dense_external_curve_inferred") is False)

    cache = {}
    objective_errors = []

    def rescored(sequence: str) -> list[float]:
        if sequence not in cache:
            cache[sequence] = [
                float(cai(sequence, cai_weights)),
                float(-mfe(sequence)),
                float(-abs(gc_fraction(sequence) - protocol["gc_target"])),
                float(-motif_penalty_score(sequence) / len(split_codons(sequence))),
            ]
        return cache[sequence]

    raw = {}
    total_calls = 0
    for descriptor in summary["runs"]:
        record_id = descriptor["record_id"]
        seed = int(descriptor["seed"])
        method = descriptor["method"]
        key = (record_id, seed, method)
        path = Path(descriptor["path"])
        run = json.loads(path.read_text())
        raw[key] = run
        source = benchmark[record_id]
        template, initial = expected_initial(source, seed)
        add(f"{key}_descriptor_identity", sha(path) == descriptor["sha256"] and
            run.get("protocol_sha256") == summary["protocol_sha256"] and
            run.get("code_commit") == summary["code_commit"])
        add(f"{key}_protein_only_input", run.get("protein_only_template") == template and
            run.get("initial_state") == initial and run.get("initial_state_sha256") == text_sha(initial) and
            run.get("protein_sha256") == text_sha(translate(template)) and
            run.get("source_sha256") == text_sha(source))
        add(f"{key}_search_isolation", run.get("search_input_semantics") == "protein_plus_fixed_TAA_only" and
            run.get("native_source_used_in_search") is False and
            run.get("native_derived_normalization_in_search") is False and
            run.get("search_normalization") is None and run.get("terminal_stop") == "TAA" and
            run.get("native_calibration_read_after_search") is True)
        points = run.get("points", [])
        budgets_ok = [point.get("budget") for point in points] == list(range(1, 12))
        identity_ok = all(translate(point["sequence"]) == translate(template) and
                          point["sequence"].endswith("TAA") for point in points)
        unique_ok = len({point["sequence"] for point in points}) == 11
        add(f"{key}_budgets_identity", len(points) == 11 and budgets_ok and identity_ok and unique_ok and
            run.get("unique_scorer_calls") == 11)
        costs_ok = (run.get("terminal_evaluations") == run.get("proposal_attempts") + 1 and
                    run.get("cache_hits") == run.get("terminal_evaluations") - 11 and
                    0 <= run.get("proposal_attempts", -1) <= run.get("max_attempts", -1) and
                    all(math.isfinite(float(run.get(field, float("nan")))) and float(run.get(field, -1)) >= 0
                        for field in ["objective_scoring_seconds", "residual_generation_cache_proposal_seconds",
                                      "search_wall_seconds", "run_wall_seconds_including_evaluation"]))
        add(f"{key}_cost_accounting", costs_ok)
        max_error = 0.0
        objectives_ok = True
        for point in points:
            expected = rescored(point["sequence"])
            observed = point["objectives"]
            if len(observed) != 4 or not np.isfinite(observed).all():
                objectives_ok = False
                continue
            errors = np.abs(np.asarray(observed, dtype=float) - np.asarray(expected, dtype=float))
            max_error = max(max_error, float(errors.max()))
            if not np.allclose(observed, expected, rtol=0, atol=1e-11):
                objectives_ok = False
        objective_errors.append(max_error)
        add(f"{key}_raw_objectives", objectives_ok, f"max_abs_error={max_error}")
        total_calls += int(run.get("unique_scorer_calls", 0))

    add("total_unique_scorer_calls", total_calls == summary.get("n_unique_scorer_calls") == protocol["expected_unique_scorer_calls"] == 1782,
        total_calls)

    external = {}
    for record_id, record in matrix_records.items():
        calibration_path = Path(protocol["calibration_dir"]) / f"{safe_name(record_id)}.json"
        calibration = json.loads(calibration_path.read_text())
        add(f"{record_id}_calibration", sha(calibration_path) == record["calibration_sha256"] and
            calibration["source_sha256"] == text_sha(benchmark[record_id]) and
            calibration["rscu_sha256"] == protocol["rscu_sha256"])
        frozen = FrozenReference.from_dict(calibration)
        method = record["methods"][protocol["primary_external_method"]]
        points = method["points"]
        metrics = actual_metrics(points, frozen)
        external[record_id] = {**metrics, "k": len(points)}
        add(f"{record_id}_external_raw_metrics", close(metrics["hypervolume_normalized"], method["actual_set"]["hypervolume_normalized"]) and
            close(metrics["pairwise_ned"], method["ned"]))
        stop_ok = all(point["sequence"].endswith("TAA") for point in points)
        add(f"{record_id}_external_cardinality", 1 <= len(points) <= 11 and
            len({point["sequence"] for point in points}) == len(points) and stop_ok)
        for (rid, seed, method_name), run in raw.items():
            if rid != record_id:
                continue
            k = len(points)
            matched = actual_metrics(run["points"][:k], frozen)
            stored = run["matched_actual_set"]
            add(f"{record_id}_{seed}_{method_name}_matched_metrics", run["matched_linear_design_k"] == k and
                close(matched["hypervolume_normalized"], stored["hypervolume_normalized"]) and
                close(matched["pairwise_ned"], stored["pairwise_ned"]))

    records = sorted(benchmark)
    recomputed_tests = []
    for method in protocol["methods"]:
        for endpoint in protocol["primary_endpoints"]:
            values = np.empty((18, 3), dtype=float)
            baseline = np.asarray([external[record][endpoint] for record in records])
            for i, record in enumerate(records):
                for j, seed in enumerate(protocol["seeds"]):
                    values[i, j] = raw[(record, seed, method)]["matched_actual_set"][endpoint]
            delta_by_seed = values - baseline[:, None]
            test = paired(delta_by_seed.mean(axis=1), protocol)
            test.update({"method": method, "comparator": protocol["primary_external_method"],
                         "endpoint": endpoint, "seed_mean_effects": delta_by_seed.mean(axis=0).tolist(),
                         "all_seed_effects_positive": bool(np.all(delta_by_seed.mean(axis=0) > 0))})
            recomputed_tests.append(test)
    primary = [row for row in recomputed_tests if row["method"] == protocol["primary_method"]]
    adjustments = holm([row["sign_flip_p"] for row in primary])
    for row, adjusted in zip(primary, adjustments):
        row["holm_p"] = adjusted
        row["supported_advantage"] = bool(row["ci95"][0] > 0 and adjusted < 0.05 and row["all_seed_effects_positive"])
    gate = all(row["supported_advantage"] for row in primary)

    stored_tests = {(row["method"], row["endpoint"]): row for row in summary["tests"]}
    for expected in recomputed_tests:
        key = (expected["method"], expected["endpoint"])
        stored = stored_tests[key]
        numeric_ok = (close(expected["effect"], stored["effect"]) and
                      np.allclose(expected["ci95"], stored["ci95"], rtol=0, atol=1e-11) and
                      expected["sign_flip_p"] == stored["sign_flip_p"] and
                      np.allclose(expected["per_record_effects"], stored["per_record_effects"], rtol=0, atol=1e-11) and
                      np.allclose(expected["seed_mean_effects"], stored["seed_mean_effects"], rtol=0, atol=1e-11))
        if key[0] == protocol["primary_method"]:
            numeric_ok = numeric_ok and expected["holm_p"] == stored["holm_p"] and expected["supported_advantage"] == stored["supported_advantage"]
        else:
            numeric_ok = numeric_ok and stored["holm_p"] is None and stored["supported_advantage"] is None
        add(f"inference_{key[0]}_{key[1]}", numeric_ok)
    add("primary_gate_recomputed", gate == summary.get("primary_gate_passed") == summary.get("common_input_proxy_task_resolved"), gate)
    expected_decision = "PRIMARY_COMMON_INPUT_PROXY_PASS_DEVELOPMENT_ONLY" if gate else "COMMON_INPUT_ACTUAL_SET_TASK_UNRESOLVED"
    add("decision_recomputed", summary.get("decision") == expected_decision, summary.get("decision"))
    add("global_scientific_gate_remains_closed", summary.get("scientific_gate_passed") is False)
    add("manuscript_remains_unsubmittable", summary.get("manuscript_submittable") is False)

    n_pass = sum(row["passed"] for row in checks)
    payload = {
        "schema": "a8-rk39-common-input-independent-verification-v1",
        "summary": str(summary_path),
        "summary_sha256": sha(summary_path),
        "protocol_sha256": summary["protocol_sha256"],
        "production_code_commit": summary["code_commit"],
        "status": "PASS" if n_pass == len(checks) else "FAIL",
        "n_pass": int(n_pass),
        "n_checks": int(len(checks)),
        "n_runs": len(raw),
        "n_raw_points": int(total_calls),
        "n_unique_sequences_independently_rescored": len(cache),
        "max_objective_abs_error": float(max(objective_errors, default=0.0)),
        "primary_gate_passed": bool(gate),
        "decision": expected_decision,
        "scientific_gate_passed": False,
        "external_sota_authorized": False,
        "functional_untouched_evaluated": False,
        "checks": checks,
    }
    atomic_json(output_path, payload)
    print(json.dumps({key: payload[key] for key in ["status", "n_pass", "n_checks", "n_runs", "n_raw_points",
                      "n_unique_sequences_independently_rescored", "max_objective_abs_error", "primary_gate_passed", "decision"]}, indent=2))
    if payload["status"] != "PASS":
        failed = [row for row in checks if not row["passed"]]
        print(json.dumps(failed[:30], indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
