#!/usr/bin/env python3
"""Independently recompute RK06 sequences, objectives, dense curves and inference."""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import RNA
from pymoo.indicators.hv import HV
from rapidfuzz.distance import Levenshtein

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from codonflow.core.codon import STANDARD_TABLE_1
from codonflow.models.guided_sampler import synonymous_x0

# The frozen v4 oracle calls motif_penalty_score(sequence) without an override
# map, so every catalog entry has weight 1.0.  Do not substitute the nominal
# DEFAULT_MOTIFS weights here: independent verification must reproduce the
# actual production objective, including CAGG, T7 and SP6.
MOTIFS = (("AATAAA", 1.0), ("ATTAAA", 1.0), ("GTGAGT", 1.0), ("CAGG", 1.0),
          ("TAATACGACTCACTATA", 1.0), ("ATTTAGGTGACACTAT", 1.0))


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def text_sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text)
    os.replace(temp, path)


def read_fasta_simple(path):
    records = []
    header = None
    chunks = []
    for line in Path(path).read_text().splitlines():
        if line.startswith(">"):
            if header is not None:
                records.append((header.split()[0], "".join(chunks)))
            header = line[1:]
            chunks = []
        elif line.strip():
            chunks.append(line.strip())
    if header is not None:
        records.append((header.split()[0], "".join(chunks)))
    return records


def cai_weights(rscu):
    groups = {}
    for codon, aa in STANDARD_TABLE_1.items():
        if aa != "*":
            groups.setdefault(aa, []).append(codon)
    weights = {}
    for group in groups.values():
        maximum = max(float(rscu.get(codon, 0.0)) for codon in group)
        for codon in group:
            weights[codon] = float(rscu.get(codon, 0.0)) / maximum if maximum > 0 else 0.0
    return weights


def independent_cai(sequence, weights):
    values = []
    for index in range(0, len(sequence), 3):
        codon = sequence[index:index + 3]
        if STANDARD_TABLE_1.get(codon) == "*":
            continue
        weight = weights.get(codon, 0.0)
        if weight > 0:
            values.append(math.log(weight))
    return math.exp(sum(values) / len(values)) if values else 0.0


@functools.lru_cache(maxsize=131072)
def independent_mfe(sequence):
    structure, energy = RNA.fold_compound(sequence.replace("T", "U")).mfe()
    return float(energy)


def independent_motif(sequence):
    total = 0.0
    for pattern, weight in MOTIFS:
        total += weight * len(re.findall(f"(?={pattern})", sequence))
    for base in "ACGT":
        total += sum(len(run) for run in re.findall(f"{base}{{6,}}", sequence))
    return float(total)


def independent_objectives(sequence, weights, gc_target):
    codons = len(sequence) // 3
    return np.array([
        independent_cai(sequence, weights),
        -independent_mfe(sequence),
        -abs((sequence.count("G") + sequence.count("C")) / len(sequence) - gc_target),
        -independent_motif(sequence) / codons,
    ], dtype=float)


def independent_hv(points, reference, scale):
    normalized = (np.asarray(points, dtype=float) - reference) / scale
    keep = np.all(normalized >= -1e-12, axis=1)
    normalized = normalized[keep]
    if not len(normalized):
        return 0.0
    return float(HV(ref_point=np.zeros(normalized.shape[1]))(-normalized))


def independent_pareto(points):
    points = np.asarray(points, dtype=float)
    ge = np.all(points[None, :, :] >= points[:, None, :], axis=2)
    gt = np.any(points[None, :, :] > points[:, None, :], axis=2)
    dominated = np.any(ge & gt, axis=1)
    return np.flatnonzero(~dominated).tolist()


def independent_ned(sequences):
    if len(sequences) < 2:
        return 0.0
    rng = np.random.default_rng(0)
    if len(sequences) > 200:
        indices = rng.choice(len(sequences), size=200, replace=False)
        sequences = [sequences[i] for i in indices]
    values = []
    for i in range(len(sequences)):
        for j in range(i + 1, len(sequences)):
            values.append(Levenshtein.distance(sequences[i], sequences[j]) / max(len(sequences[i]), len(sequences[j])))
    return float(np.mean(values)) if values else 0.0


def verify_run(job):
    protocol, protocol_sha, descriptor, source, source_sha, weights, output_root, resume = job
    record = descriptor["record_id"]
    method = descriptor["method"]
    seed = descriptor["seed"]
    production_path = Path(descriptor["path"])
    production_sha = sha256(production_path)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", record)
    output = Path(output_root) / "independent_checks" / safe / f"{method}_s{seed}.json"
    array_path = Path(output_root) / "independent_arrays" / safe / f"{method}_s{seed}.npy"
    if output.exists() and resume:
        existing = json.loads(output.read_text())
        if existing.get("production_sha256") == production_sha and existing.get("protocol_sha256") == protocol_sha and existing.get("pass"):
            return existing
    errors = []
    payload = json.loads(production_path.read_text())
    points = payload.get("points", [])
    if production_sha != descriptor["sha256"]:
        errors.append("production run hash differs from descriptor")
    if payload.get("protocol_sha256") != protocol_sha:
        errors.append("run protocol hash mismatch")
    if payload.get("source_sha256") != source_sha:
        errors.append("run source hash mismatch")
    if payload.get("status") != "done" or len(points) != 500:
        errors.append("run is not a complete 500-point trajectory")
    if [row.get("budget") for row in points] != list(range(1, 501)):
        errors.append("budgets are not exactly 1..500")
    sequences = [row.get("sequence", "") for row in points]
    if len(set(sequences)) != 500:
        errors.append("scored sequences are not unique")
    source_protein = [STANDARD_TABLE_1.get(source[i:i + 3]) for i in range(0, len(source), 3)]
    for sequence in sequences:
        if len(sequence) != len(source):
            errors.append("sequence length mismatch")
            break
        protein = [STANDARD_TABLE_1.get(sequence[i:i + 3]) for i in range(0, len(sequence), 3)]
        if protein != source_protein:
            errors.append("non-synonymous or invalid sequence")
            break
    expected_initial = synonymous_x0(source, np.random.default_rng(seed * 1009))
    if not sequences or sequences[0] != expected_initial:
        errors.append("initial sequence does not match frozen deterministic initialization")
    if payload.get("initial_sha256") != text_sha(expected_initial):
        errors.append("initial sequence hash mismatch")
    calibration_path = Path(protocol["calibration_dir"]) / f"{safe}.json"
    calibration = json.loads(calibration_path.read_text())
    reference = np.asarray(calibration["reference"], dtype=float)
    scale = np.asarray(calibration["scale"], dtype=float)
    if sha256(calibration_path) != payload.get("calibration_sha256"):
        errors.append("calibration hash mismatch")
    if calibration.get("source_sha256") != source_sha:
        errors.append("calibration source mismatch")

    objectives = np.asarray([independent_objectives(sequence, weights, protocol["gc_target"]) for sequence in sequences])
    array_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_array = array_path.with_suffix(".tmp.npy")
    np.save(temporary_array, objectives)
    os.replace(temporary_array, array_path)
    production_objectives = np.asarray([row["objectives"] for row in points], dtype=float)
    objective_max_diff = float(np.max(np.abs(objectives - production_objectives))) if objectives.shape == production_objectives.shape else float("inf")
    if not np.isfinite(objectives).all() or objective_max_diff > 1e-9:
        errors.append(f"independent objective mismatch {objective_max_diff}")
    curve = []
    for budget in range(1, 501):
        curve.append(independent_hv(objectives[:budget], reference, scale))
    production_curve = [float(row["hv"]) for row in payload["dense"]["curve"]]
    curve_max_diff = float(np.max(np.abs(np.asarray(curve) - np.asarray(production_curve))))
    area = float(sum(curve[:499]))
    auc = area / 499.0
    auc_diff = abs(auc - float(payload["dense"]["auc"]))
    descriptor_auc_diff = abs(auc - float(descriptor["dense_budget_step_auc_v2"]))
    descriptor_hv_diff = abs(curve[-1] - float(descriptor["endpoint_hv_B500"]))
    if curve_max_diff > 1e-9 or auc_diff > 1e-9 or descriptor_auc_diff > 1e-9 or descriptor_hv_diff > 1e-9:
        errors.append(f"dense curve/AUC/descriptor mismatch curve={curve_max_diff} auc={auc_diff} descriptor_auc={descriptor_auc_diff} descriptor_hv={descriptor_hv_diff}")
    if payload["dense"].get("denominator") != 499 or payload["dense"].get("endpoint_budget") != 500:
        errors.append("dense denominator or endpoint mismatch")
    if any(row.get("used_in_auc") != (row.get("budget") < 500) for row in payload["dense"]["curve"]):
        errors.append("AUC inclusion flags mismatch")
    secondary = {}
    secondary_max_diff = 0.0
    for budget in [50, 100, 500]:
        selected = objectives[:budget]
        pareto = independent_pareto(selected)
        row = {
            "hypervolume_normalized": curve[budget - 1],
            "n_scored": budget,
            "n_pareto_points": len(pareto),
            "per_axis_best": np.max(selected, axis=0).tolist(),
            "pairwise_ned": independent_ned(sequences[:budget]),
        }
        production_row = next(item for item in payload["secondary_budgets"] if item["budget"] == budget)
        for key in ["hypervolume_normalized", "n_pareto_points", "pairwise_ned"]:
            secondary_max_diff = max(secondary_max_diff, abs(float(row[key]) - float(production_row[key])))
        secondary_max_diff = max(secondary_max_diff, float(np.max(np.abs(np.asarray(row["per_axis_best"]) - np.asarray(production_row["per_axis_best"])))) )
        secondary[str(budget)] = row
    if secondary_max_diff > 1e-9:
        errors.append(f"secondary budget mismatch {secondary_max_diff}")
    costs = payload["cost"]
    if costs["unique_scorer_calls"] != 500 or costs["cache_before_requests"] != 0 or costs["model_forward_calls"] != 0:
        errors.append("real-budget cost semantics mismatch")
    if any(float(costs[key]) < 0 for key in ["wall_clock_seconds", "scoring_seconds", "generation_cache_proposal_seconds", "dense_metric_and_audit_seconds"]):
        errors.append("negative time cost")
    result = {
        "schema": "a8-rk06-independent-run-v1",
        "protocol_sha256": protocol_sha,
        "production_sha256": production_sha,
        "production_path": str(production_path),
        "record_id": record,
        "seed": seed,
        "method": method,
        "pass": not errors,
        "errors": errors,
        "n_points": len(points),
        "n_unique_sequences": len(set(sequences)),
        "protein_identity_pass": not any("non-synonymous" in error or "length mismatch" in error for error in errors),
        "objective_max_abs_diff": objective_max_diff,
        "dense_curve_max_abs_diff": curve_max_diff,
        "dense_auc_abs_diff": auc_diff,
        "descriptor_auc_abs_diff": descriptor_auc_diff,
        "descriptor_hv_abs_diff": descriptor_hv_diff,
        "secondary_max_abs_diff": secondary_max_diff,
        "independent_dense_auc": auc,
        "independent_dense_area": area,
        "independent_hv_B500": curve[-1],
        "independent_secondary": secondary,
        "independent_objectives_path": str(array_path),
        "independent_objectives_sha256": sha256(array_path),
        "cost": costs,
    }
    atomic_json(output, result)
    return result


def holm(p_values):
    p = np.asarray(p_values, dtype=float)
    order = np.argsort(p)
    output = np.empty(len(p))
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(p) - rank) * p[index]))
        output[index] = running
    return output


def independent_inference(results, protocol):
    records = sorted({row["record_id"] for row in results})
    seeds = protocol["seeds"]
    methods = protocol["methods"]
    endpoints = ["dense_budget_step_auc_v2", "b500_normalized_hv"]
    lookup = {(row["record_id"], row["seed"], row["method"]): row for row in results}
    values = {}
    for method in methods:
        for endpoint in endpoints:
            matrix = np.zeros((len(records), len(seeds)))
            for i, record in enumerate(records):
                for j, seed in enumerate(seeds):
                    row = lookup[(record, seed, method)]
                    matrix[i, j] = row["independent_dense_auc"] if endpoint == endpoints[0] else row["independent_hv_B500"]
            values[(method, endpoint)] = matrix.mean(axis=1)
    tests = []
    for method in methods[1:]:
        for endpoint in endpoints:
            delta = values[(method, endpoint)] - values[("uniform", endpoint)]
            observed = float(delta.mean())
            rng = np.random.default_rng(protocol["statistics"]["bootstrap_seed"])
            indices = rng.integers(0, len(records), size=(20000, len(records)))
            boot = delta[indices].mean(axis=1)
            rng = np.random.default_rng(protocol["statistics"]["permutation_seed"])
            signs = rng.choice(np.array([-1.0, 1.0]), size=(20000, len(records)))
            null = (signs * delta).mean(axis=1)
            p = (1 + int(np.sum(np.abs(null) >= abs(observed) - 1e-15))) / 20001
            tests.append({"method": method, "endpoint": endpoint, "effect": observed,
                          "ci95": np.quantile(boot, [0.025, 0.975]).tolist(), "sign_flip_p": float(p),
                          "per_record_effects": delta.tolist()})
    adjusted = holm([row["sign_flip_p"] for row in tests])
    for row, value in zip(tests, adjusted):
        row["holm_p"] = float(value)
        row["supported_advantage"] = bool(row["ci95"][0] > 0 and value < 0.05)
    return tests


def independent_dominance(results):
    lookup = {(row["record_id"], row["seed"], row["method"]): row for row in results}
    methods = sorted({row["method"] for row in results})
    output = []
    for a_method in methods:
        for b_method in methods:
            if a_method >= b_method:
                continue
            fractions = []
            for row in results:
                if row["method"] != a_method:
                    continue
                a = np.load(row["independent_objectives_path"])
                b = np.load(lookup[(row["record_id"], row["seed"], b_method)]["independent_objectives_path"])
                a = a[independent_pareto(a)]
                b = b[independent_pareto(b)]
                a_dominated = np.any(np.all(b[None, :, :] >= a[:, None, :], axis=2)
                                     & np.any(b[None, :, :] > a[:, None, :], axis=2), axis=1)
                b_dominated = np.any(np.all(a[None, :, :] >= b[:, None, :], axis=2)
                                     & np.any(a[None, :, :] > b[:, None, :], axis=2), axis=1)
                fractions.append([np.mean(a_dominated), np.mean(b_dominated)])
            means = np.mean(fractions, axis=0)
            output.append({"method_a": a_method, "method_b": b_method,
                           "mean_fraction_a_strictly_dominated_by_b": float(means[0]),
                           "mean_fraction_b_strictly_dominated_by_a": float(means[1])})
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--production", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--independent-root", help="Separate root for independent arrays/checks; preserves earlier failed evidence")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    protocol_path = Path(args.protocol)
    production_path = Path(args.production)
    protocol = json.loads(protocol_path.read_text())
    production = json.loads(production_path.read_text())
    protocol_sha = sha256(protocol_path)
    code_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if production["protocol_sha256"] != protocol_sha:
        raise ValueError("production protocol hash mismatch")
    if not production.get("overall_pass") or not production.get("formal_full_panel"):
        raise ValueError("production is not a passing formal full panel")
    records = dict(read_fasta_simple(protocol["benchmark_fasta"]))
    rscu = json.loads(Path(protocol["rscu_json"]).read_text())
    weights = cai_weights(rscu)
    output_root = Path(args.independent_root) if args.independent_root else Path(protocol["artifact_root"])
    jobs = [(protocol, protocol_sha, descriptor, records[descriptor["record_id"]], text_sha(records[descriptor["record_id"]]),
             weights, str(output_root), args.resume) for descriptor in production["runs"]]
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(verify_run, job) for job in jobs]
        for future in as_completed(futures):
            row = future.result()
            results.append(row)
            print(json.dumps({"record_id": row["record_id"], "seed": row["seed"], "method": row["method"],
                              "pass": row["pass"], "objective_max_abs_diff": row["objective_max_abs_diff"]}), flush=True)
    results.sort(key=lambda row: (row["record_id"], row["seed"], row["method"]))
    tests = independent_inference(results, protocol) if all(row["pass"] for row in results) else []
    dominance = independent_dominance(results) if all(row["pass"] for row in results) else []
    checks = []
    def check(name, condition, detail=None):
        row = {"check": name, "pass": bool(condition)}
        if detail is not None:
            row["detail"] = detail
        checks.append(row)
    check("216_independent_runs", len(results) == 216)
    check("all_independent_runs_pass", all(row["pass"] for row in results))
    check("108000_unique_scorer_calls", sum(row["n_points"] for row in results) == 108000)
    check("all_protein_identical", all(row["protein_identity_pass"] for row in results))
    check("environment_viennarna", RNA.__version__ == production["environment"]["ViennaRNA"])
    check("production_formal_status", production["status"] == "DONE_SIMPLE_SEARCH_DENSE_DEVELOPMENT")
    check("production_six_tests", len(production["primary_tests"]) == 6)
    check("independent_six_tests", len(tests) == 6)
    for field in ["objective_max_abs_diff", "dense_curve_max_abs_diff", "dense_auc_abs_diff", "descriptor_auc_abs_diff", "descriptor_hv_abs_diff", "secondary_max_abs_diff"]:
        maximum = max(row[field] for row in results)
        check(field, maximum <= 1e-9, maximum)
    test_differences = []
    for independent in tests:
        candidate = next(row for row in production["primary_tests"] if row["method"] == independent["method"]
                         and row["endpoint"] == independent["endpoint"])
        for key in ["effect", "sign_flip_p", "holm_p"]:
            test_differences.append(abs(float(independent[key]) - float(candidate[key])))
        test_differences.append(float(np.max(np.abs(np.asarray(independent["ci95"]) - np.asarray(candidate["ci95"])))) )
        test_differences.append(float(np.max(np.abs(np.asarray(independent["per_record_effects"]) - np.asarray(candidate["per_record_effects"])))) )
        if independent["supported_advantage"] != candidate["supported_advantage"]:
            test_differences.append(float("inf"))
    maximum_test_difference = max(test_differences) if test_differences else float("inf")
    check("paired_inference_recomputed", maximum_test_difference <= 1e-12, maximum_test_difference)
    dominance_differences = []
    for independent in dominance:
        candidate = next(row for row in production["bidirectional_strict_dominance_B500"]
                         if row["method_a"] == independent["method_a"] and row["method_b"] == independent["method_b"])
        for key in ["mean_fraction_a_strictly_dominated_by_b", "mean_fraction_b_strictly_dominated_by_a"]:
            dominance_differences.append(abs(independent[key] - candidate[key]))
    maximum_dominance_difference = max(dominance_differences) if dominance_differences else float("inf")
    check("bidirectional_dominance_recomputed", len(dominance) == 6 and maximum_dominance_difference <= 1e-12, maximum_dominance_difference)
    method_summary_differences = []
    for candidate in production["method_summary"]:
        rows = [row for row in results if row["method"] == candidate["method"]]
        recomputed = {
            "n_runs": len(rows),
            "mean_dense_auc": float(np.mean([row["independent_dense_auc"] for row in rows])),
            "mean_hv_B500": float(np.mean([row["independent_hv_B500"] for row in rows])),
            "mean_hv_B50": float(np.mean([row["independent_secondary"]["50"]["hypervolume_normalized"] for row in rows])),
            "mean_hv_B100": float(np.mean([row["independent_secondary"]["100"]["hypervolume_normalized"] for row in rows])),
            "sum_unique_scorer_calls": sum(row["n_points"] for row in rows),
            "sum_terminal_requests": sum(row["cost"]["terminal_reward_evaluations"] for row in rows),
            "sum_wall_clock_seconds": sum(row["cost"]["wall_clock_seconds"] for row in rows),
            "sum_scoring_seconds": sum(row["cost"]["scoring_seconds"] for row in rows),
            "sum_generation_cache_proposal_seconds": sum(row["cost"]["generation_cache_proposal_seconds"] for row in rows),
            "sum_dense_metric_and_audit_seconds": sum(row["cost"]["dense_metric_and_audit_seconds"] for row in rows),
        }
        for key, value in recomputed.items():
            method_summary_differences.append(abs(float(value) - float(candidate[key])))
    maximum_method_summary_difference = max(method_summary_differences) if method_summary_differences else float("inf")
    check("method_summary_recomputed", len(production["method_summary"]) == 4 and maximum_method_summary_difference <= 1e-9, maximum_method_summary_difference)
    check("production_total_counts", production["n_runs"] == 216 and production["n_unique_scorer_calls"] == 108000)
    manifest_path = ROOT / "audits/20261120/RK06/simple_search_dense_artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    check("artifact_manifest_summary_hash", manifest["summary_sha256"] == sha256(production_path))
    check("artifact_summary_hash", manifest["artifact_summary_sha256"] == sha256(manifest["artifact_summary_path"]))
    check("artifact_manifest_run_count", manifest["run_count"] == 216)
    manifest_lookup = {row["path"]: row["sha256"] for row in manifest["run_files"]}
    check("artifact_manifest_run_hashes", all(manifest_lookup.get(row["production_path"]) == row["production_sha256"] for row in results))
    check("external_dense_remains_null", production["external_actual_set_dense_policy"]["dense_budget_step_auc_v2"] is None)
    check("no_untouched_or_functional_use", not production["untouched24_used"] and not production["functional_untouched_used"] and not production["functional_labels_used"])
    check("no_scientific_gate_or_sota_claim", not production["scientific_gate_passed"] and not production["rk_g1_closed"] and not production["sota_claim"])
    array_manifest = {
        "schema": "a8-rk06-independent-objectives-manifest-v1",
        "protocol_sha256": protocol_sha,
        "production_sha256": sha256(production_path),
        "files": [{"path": row["independent_objectives_path"], "sha256": row["independent_objectives_sha256"]} for row in results],
    }
    array_manifest_path = output_root / "independent_objectives_manifest.json"
    atomic_json(array_manifest_path, array_manifest)
    check("independent_array_manifest", len(array_manifest["files"]) == 216 and all(sha256(row["path"]) == row["sha256"] for row in array_manifest["files"]))
    report = {
        "schema": "a8-rk06-simple-search-dense-independent-v1",
        "code_commit": code_commit,
        "verifier_sha256": sha256(Path(__file__).resolve()),
        "independent_root": str(output_root),
        "protocol_sha256": protocol_sha,
        "production_path": str(production_path),
        "production_sha256": sha256(production_path),
        "overall_pass": all(row["pass"] for row in checks),
        "status": "INDEPENDENT_PASS" if all(row["pass"] for row in checks) else "INDEPENDENT_FAIL",
        "n_independent_runs": len(results),
        "n_recomputed_objectives": sum(row["n_points"] for row in results),
        "checks": checks,
        "check_counts": {"total": len(checks), "passed": sum(row["pass"] for row in checks), "failed": sum(not row["pass"] for row in checks)},
        "maximum_differences": {
            "objectives": max(row["objective_max_abs_diff"] for row in results),
            "dense_curve": max(row["dense_curve_max_abs_diff"] for row in results),
            "dense_auc": max(row["dense_auc_abs_diff"] for row in results),
            "descriptor_auc": max(row["descriptor_auc_abs_diff"] for row in results),
            "descriptor_hv": max(row["descriptor_hv_abs_diff"] for row in results),
            "secondary": max(row["secondary_max_abs_diff"] for row in results),
            "paired_inference": maximum_test_difference,
            "dominance": maximum_dominance_difference,
            "method_summary": maximum_method_summary_difference,
        },
        "independent_primary_tests": tests,
        "independent_dominance": dominance,
        "independent_run_results": results,
        "independent_objectives_manifest": str(array_manifest_path),
        "independent_objectives_manifest_sha256": sha256(array_manifest_path),
        "scope": "Independent development proxy-search recomputation only; no untouched or functional evaluation, external actual-set dense conversion, generator training, RK-G1 closure, or SOTA claim.",
    }
    atomic_json(args.output, report)
    print(json.dumps({"status": report["status"], "overall_pass": report["overall_pass"],
                      "check_counts": report["check_counts"], "maximum_differences": report["maximum_differences"]}), flush=True)
    if not report["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
