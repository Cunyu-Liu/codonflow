#!/usr/bin/env python3
"""Rescore RK-12 and frozen external raw CDS sets on unique18 actual sets."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from scripts.a8_rk06_recompute_actual_set import recompute_actual_set


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values, key=p_values.get)
    adjusted = {}
    running = 0.0
    m = len(ordered)
    for index, key in enumerate(ordered):
        running = max(running, min(1.0, (m - index) * p_values[key]))
        adjusted[key] = running
    return adjusted


def paired_effect(new_values, comparator_values, resamples: int, seed: int):
    new = np.asarray(new_values, dtype=float)
    comparator = np.asarray(comparator_values, dtype=float)
    effects = new - comparator
    if effects.shape != (18,) or not np.isfinite(effects).all():
        raise ValueError("primary paired effects require exactly 18 finite records")
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(effects), size=(resamples, len(effects)))
    distribution = effects[indices].mean(axis=1)
    lower, upper = np.quantile(distribution, [0.025, 0.975])
    p_less = (1 + int(np.sum(distribution <= 0.0))) / (resamples + 1)
    p_greater = (1 + int(np.sum(distribution >= 0.0))) / (resamples + 1)
    return {
        "n_records": len(effects),
        "new_mean": float(new.mean()),
        "comparator_mean": float(comparator.mean()),
        "mean_effect": float(effects.mean()),
        "median_effect": float(np.median(effects)),
        "sd_effect": float(effects.std(ddof=1)),
        "ci95": [float(lower), float(upper)],
        "bootstrap_p_two_sided": float(min(1.0, 2.0 * min(p_less, p_greater))),
        "per_record_effects": effects.tolist(),
        "bootstrap_seed": seed,
        "bootstrap_resamples": resamples,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--grid-protocol", type=Path, required=True)
    parser.add_argument("--grid-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--allow-uncommitted", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or args.audit.exists():
        raise FileExistsError("refusing to overwrite an RK-12 actual-set matrix")
    protocol = json.loads(args.protocol.read_text())
    grid_protocol = json.loads(args.grid_protocol.read_text())
    grid = json.loads(args.grid_report.read_text())
    if protocol["schema"] != "a8-rk12-actual-set-matrix-v1":
        raise ValueError("unexpected matrix protocol")
    if grid["status"] != "COMPLETE_UNIQUE18_OFFICIAL_LINEARDESIGN_LAMBDA_GRID":
        raise ValueError("full 198-run LinearDesign grid is required before matrix scoring")
    tracked_dirty = subprocess.check_output(["git", "diff", "--name-only", "HEAD"], cwd=REPO, text=True).splitlines()
    script_tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(Path(__file__).resolve().relative_to(REPO))], cwd=REPO, capture_output=True).returncode == 0
    if (tracked_dirty or not script_tracked) and not args.allow_uncommitted:
        raise ValueError("matrix scorer requires committed clean tracked code; use --allow-uncommitted only for development")
    code_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    benchmark = Path(protocol["benchmark_fasta"])
    rscu_path = Path(protocol["rscu_json"])
    calibration_dir = Path(protocol["calibration_dir"])
    acceptance = Path(protocol["calibration_acceptance"])
    if sha256(benchmark) != protocol["benchmark_sha256"] or grid["benchmark_sha256"] != protocol["benchmark_sha256"]:
        raise ValueError("benchmark hash mismatch")
    if sha256(rscu_path) != protocol["rscu_sha256"] or sha256(acceptance) != protocol["calibration_acceptance_sha256"]:
        raise ValueError("RSCU or calibration acceptance hash mismatch")
    rscu = json.loads(rscu_path.read_text())
    calibration_acceptance = json.loads(acceptance.read_text())
    if calibration_acceptance.get("passed") is not True:
        raise ValueError("calibration pool is not accepted")
    from codonflow.data.dataset import read_fasta
    records = {header.split()[0]: sequence for header, sequence in read_fasta(benchmark)}
    if list(records) != grid_protocol["record_order"]:
        raise ValueError("record order mismatch")
    expected_methods = [protocol["new_method"]] + protocol["legacy_methods"] + [protocol["secondary_legacy_method_not_in_primary"]]
    started = time.perf_counter()
    result = {
        "schema": protocol["schema"],
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sha256(args.protocol),
        "grid_protocol_sha256": sha256(args.grid_protocol),
        "grid_report": str(args.grid_report),
        "grid_report_sha256": sha256(args.grid_report),
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "RUNNING",
        "scope": protocol["decision_boundary"],
        "population": protocol["population"],
        "benchmark_sha256": protocol["benchmark_sha256"],
        "rscu_sha256": protocol["rscu_sha256"],
        "calibration_acceptance_sha256": protocol["calibration_acceptance_sha256"],
        "scorer_code_commit": code_commit,
        "scorer_tracked_dirty": bool(tracked_dirty),
        "scorer_script_tracked": script_tracked,
        "development_uncommitted_allowed": args.allow_uncommitted,
        "objectives_recomputed_from_raw_sequences": True,
        "stored_objectives_used_for_scoring": False,
        "dense_budget_step_auc_v2": None,
        "time_matched_comparison": False,
        "scientific_gate_passed": False,
        "sota_claim": False,
        "records": [],
    }
    progress = args.audit.with_name(args.audit.stem + "_in_progress.json")
    for record_index, record_id in enumerate(grid_protocol["record_order"]):
        a6_path = Path(protocol["a6_payload_root"]) / f"{record_id}_s0.json"
        original = json.loads(a6_path.read_text())
        if original["status"] != "done" or original["record_id"] != record_id or original["benchmark_sha256"] != protocol["benchmark_sha256"]:
            raise ValueError(f"invalid A6 payload: {record_id}")
        source = records[record_id]
        grid_runs = [run for run in grid["runs"] if run["record_id"] == record_id]
        if len(grid_runs) != len(grid_protocol["lambda_grid"]):
            raise ValueError(f"incomplete LinearDesign grid: {record_id}")
        solutions = list(dict.fromkeys(run["evaluation_sequence_dna"] for run in grid_runs))
        new_method = {
            "status": "done",
            "solutions": solutions,
            "n_unique": len(solutions),
            "obj_vectors": None,
            "elapsed_s": sum(run["elapsed_s"] for run in grid_runs),
            "generator_calls": len(grid_runs),
        }
        payload = {
            "status": "done",
            "record_id": record_id,
            "seed": 0,
            "benchmark_sha256": protocol["benchmark_sha256"],
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "rscu_sha256": protocol["rscu_sha256"],
            "code_commit": original.get("code_commit"),
            "methods": {protocol["new_method"]: new_method},
        }
        for name in protocol["legacy_methods"] + [protocol["secondary_legacy_method_not_in_primary"]]:
            payload["methods"][name] = copy.deepcopy(original["methods"][name])
        calibration_path = calibration_dir / f"{record_id}.json"
        calibration = json.loads(calibration_path.read_text())
        if calibration["source_sha256"] != payload["source_sha256"]:
            raise ValueError(f"calibration source mismatch: {record_id}")
        methods = recompute_actual_set(payload, source, calibration, rscu)
        if list(methods) != expected_methods:
            raise ValueError("method order mismatch")
        measured_seconds = sum(run["elapsed_s"] for run in grid_runs)
        methods[protocol["new_method"]]["measured_generation_cost"] = {
            "wall_clock_seconds": measured_seconds,
            "official_process_calls": len(grid_runs),
            "workers": 1,
            "hardware": grid["platform"],
            "forward_calls": None,
            "time_semantics": "sum of per-call end-to-end official-process wall clock; independent rescoring excluded",
        }
        record_result = {
            "record_id": record_id,
            "source_sha256": payload["source_sha256"],
            "a6_payload": str(a6_path),
            "a6_payload_sha256": sha256(a6_path),
            "calibration": str(calibration_path),
            "calibration_sha256": sha256(calibration_path),
            "methods": methods,
        }
        result["records"].append(record_result)
        compact = {
            "record_id": record_id,
            "completed_records": len(result["records"]),
            "methods": {
                name: {
                    "hypervolume_normalized": method["actual_set"]["hypervolume_normalized"],
                    "ned": method["ned"],
                    "n_actual_outputs": method["actual_set"]["n_actual_outputs"],
                    "n_pareto_points": method["actual_set"]["n_pareto_points"],
                }
                for name, method in methods.items()
            },
        }
        atomic_json(progress, compact)
        print(json.dumps(compact), flush=True)
    if len(result["records"]) != 18:
        raise ValueError("matrix requires 18 records")
    comparisons = {}
    raw_p = {}
    for comparator_index, comparator in enumerate(protocol["primary_comparators"]):
        for metric_index, metric in enumerate(["hypervolume_normalized", "ned"]):
            key = f"{protocol['new_method']}_minus_{comparator}:{metric}"
            new_values = []
            comparator_values = []
            for record in result["records"]:
                new_method = record["methods"][protocol["new_method"]]
                old_method = record["methods"][comparator]
                new_values.append(new_method["actual_set"]["hypervolume_normalized"] if metric == "hypervolume_normalized" else new_method["ned"])
                comparator_values.append(old_method["actual_set"]["hypervolume_normalized"] if metric == "hypervolume_normalized" else old_method["ned"])
            effect = paired_effect(
                new_values,
                comparator_values,
                protocol["statistics"]["paired_bootstrap_resamples"],
                protocol["statistics"]["bootstrap_seed"] + 100 * comparator_index + metric_index,
            )
            effect["comparator"] = comparator
            effect["metric"] = metric
            comparisons[key] = effect
            raw_p[key] = effect["bootstrap_p_two_sided"]
    adjusted = holm_adjust(raw_p)
    for key in comparisons:
        comparisons[key]["holm_p_four_primary"] = adjusted[key]
        comparisons[key]["ci_excludes_zero"] = comparisons[key]["ci95"][0] * comparisons[key]["ci95"][1] > 0
    result["primary_comparisons"] = comparisons
    result["method_summary"] = {}
    for name in expected_methods:
        hv = [record["methods"][name]["actual_set"]["hypervolume_normalized"] for record in result["records"]]
        ned = [record["methods"][name]["ned"] for record in result["records"]]
        outputs = [record["methods"][name]["actual_set"]["n_actual_outputs"] for record in result["records"]]
        result["method_summary"][name] = {
            "mean_hypervolume_normalized": float(np.mean(hv)),
            "median_hypervolume_normalized": float(np.median(hv)),
            "mean_ned": float(np.mean(ned)),
            "median_ned": float(np.median(ned)),
            "total_actual_outputs": int(sum(outputs)),
            "min_identity_rate": float(min(record["methods"][name]["identity_rate"] for record in result["records"])),
        }
    result["descriptive_highest_mean_hv_method"] = max(result["method_summary"], key=lambda name: result["method_summary"][name]["mean_hypervolume_normalized"])
    result["descriptive_ranking_not_sota"] = True
    result["new_lineardesign_total_generation_seconds"] = grid["total_generation_elapsed_s"]
    result["reanalysis_elapsed_s_not_generation_cost"] = time.perf_counter() - started
    result["status"] = "COMPLETE_UNIQUE18_ACTUAL_SET_MATRIX_DEVELOPMENT_ONLY"
    atomic_json(args.output, result)
    audit = {
        "schema": "a8-rk12-actual-set-matrix-audit-v1",
        "status": "PASS",
        "output": str(args.output),
        "output_sha256": sha256(args.output),
        "protocol_sha256": sha256(args.protocol),
        "grid_report_sha256": sha256(args.grid_report),
        "record_count": len(result["records"]),
        "method_summary": result["method_summary"],
        "primary_comparisons": result["primary_comparisons"],
        "descriptive_highest_mean_hv_method": result["descriptive_highest_mean_hv_method"],
        "new_lineardesign_total_generation_seconds": result["new_lineardesign_total_generation_seconds"],
        "reanalysis_elapsed_s_not_generation_cost": result["reanalysis_elapsed_s_not_generation_cost"],
        "scorer_code_commit": code_commit,
        "scorer_tracked_dirty": bool(tracked_dirty),
        "scorer_script_tracked": script_tracked,
        "dense_budget_step_auc_v2": None,
        "time_matched_comparison": False,
        "scientific_gate_passed": False,
        "sota_claim": False,
        "scope": protocol["decision_boundary"],
    }
    atomic_json(args.audit, audit)
    print(json.dumps({"status": result["status"], "output": str(args.output), "audit": str(args.audit)}), flush=True)


if __name__ == "__main__":
    main()
