#!/usr/bin/env python3
"""Append verified EnsembleDesign actual sets to the frozen RK-12 matrix."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from scripts.a8_rk06_recompute_actual_set import recompute_actual_set
from scripts.a8_rk12_score_actual_set_matrix import holm_adjust, paired_effect


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--ensemble-protocol", type=Path, required=True)
    parser.add_argument("--ensemble-report", type=Path, required=True)
    parser.add_argument("--ensemble-independent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--allow-uncommitted", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or args.audit.exists():
        raise FileExistsError("refusing to overwrite RK-13 matrix or audit")
    protocol = json.loads(args.protocol.read_text())
    ensemble_protocol = json.loads(args.ensemble_protocol.read_text())
    ensemble = json.loads(args.ensemble_report.read_text())
    independent = json.loads(args.ensemble_independent.read_text())
    if protocol["schema"] != "a8-rk13-seven-method-actual-set-matrix-v1":
        raise ValueError("unexpected seven-method protocol")
    if ensemble["status"] != "COMPLETE_UNIQUE18_OFFICIAL_ENSEMBLEDESIGN_11RUN":
        raise ValueError("complete EnsembleDesign generation required")
    if independent["status"] != "PASS" or independent["report_sha256"] != sha256(args.ensemble_report):
        raise ValueError("independent EnsembleDesign PASS bound to the current report is required")
    if ensemble["protocol_sha256"] != sha256(args.ensemble_protocol):
        raise ValueError("EnsembleDesign protocol hash mismatch")
    base_path = Path(protocol["base_matrix"])
    base = json.loads(base_path.read_text())
    if sha256(base_path) != protocol["base_matrix_sha256"]:
        raise ValueError("base matrix hash mismatch")
    base_independent_path = Path(protocol["base_independent"])
    base_finalization_path = Path(protocol["base_finalization"])
    base_independent = json.loads(base_independent_path.read_text())
    base_finalization = json.loads(base_finalization_path.read_text())
    if sha256(base_independent_path) != protocol["base_independent_sha256"] or base_independent["status"] != "PASS":
        raise ValueError("base independent PASS mismatch")
    if sha256(base_finalization_path) != protocol["base_finalization_sha256"] or base_finalization["status"] != "PASS":
        raise ValueError("base finalization PASS mismatch")
    if base_independent.get("matrix_sha256") != protocol["base_matrix_sha256"]:
        raise ValueError("base independent report is not bound to the frozen matrix")
    tracked_dirty = subprocess.check_output(["git", "diff", "--name-only", "HEAD"], cwd=REPO, text=True).splitlines()
    script_tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(Path(__file__).resolve().relative_to(REPO))], cwd=REPO, capture_output=True).returncode == 0
    if (tracked_dirty or not script_tracked) and not args.allow_uncommitted:
        raise ValueError("matrix scorer requires committed clean tracked code")
    code_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    benchmark = Path(protocol["benchmark_fasta"])
    if sha256(benchmark) != protocol["benchmark_sha256"] or ensemble["benchmark_sha256"] != protocol["benchmark_sha256"]:
        raise ValueError("benchmark hash mismatch")
    rscu_path = Path(protocol["rscu_json"])
    acceptance_path = Path(protocol["calibration_acceptance"])
    if sha256(rscu_path) != protocol["rscu_sha256"] or sha256(acceptance_path) != protocol["calibration_acceptance_sha256"]:
        raise ValueError("RSCU or calibration acceptance mismatch")
    rscu = json.loads(rscu_path.read_text())
    if json.loads(acceptance_path.read_text()).get("passed") is not True:
        raise ValueError("calibration pool is not accepted")
    from codonflow.data.dataset import read_fasta
    source_records = {header.split()[0]: sequence for header, sequence in read_fasta(benchmark)}
    if list(source_records) != ensemble_protocol["record_order"]:
        raise ValueError("record order mismatch")
    if [r["record_id"] for r in base["records"]] != ensemble_protocol["record_order"] or [r["record_id"] for r in ensemble["records"]] != ensemble_protocol["record_order"]:
        raise ValueError("base or EnsembleDesign record order mismatch")

    started = time.perf_counter()
    result = {
        "schema": protocol["schema"],
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sha256(args.protocol),
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "RUNNING",
        "scope": protocol["decision_boundary"],
        "population": protocol["population"],
        "benchmark_sha256": protocol["benchmark_sha256"],
        "rscu_sha256": protocol["rscu_sha256"],
        "calibration_acceptance_sha256": protocol["calibration_acceptance_sha256"],
        "base_matrix": str(base_path),
        "base_matrix_sha256": protocol["base_matrix_sha256"],
        "base_independent_sha256": protocol["base_independent_sha256"],
        "base_finalization_sha256": protocol["base_finalization_sha256"],
        "base_methods_copied_without_modification": True,
        "ensemble_protocol_sha256": sha256(args.ensemble_protocol),
        "ensemble_report": str(args.ensemble_report),
        "ensemble_report_sha256": sha256(args.ensemble_report),
        "ensemble_independent_sha256": sha256(args.ensemble_independent),
        "scorer_code_commit": code_commit,
        "scorer_tracked_dirty": bool(tracked_dirty),
        "scorer_script_tracked": script_tracked,
        "development_uncommitted_allowed": args.allow_uncommitted,
        "objectives_recomputed_from_raw_sequences": True,
        "added_method_objectives_recomputed_from_raw_sequences": True,
        "base_method_objectives_inherited_from_independently_verified_matrix": True,
        "stored_objectives_used_for_added_method_scoring": False,
        "dense_budget_step_auc_v2": None,
        "time_matched_comparison": False,
        "scientific_gate_passed": False,
        "sota_claim": False,
        "records": [],
    }
    progress = args.audit.with_name(args.audit.stem + "_in_progress.json")
    added = protocol["added_method"]
    for record_id, base_record, ensemble_record in zip(ensemble_protocol["record_order"], base["records"], ensemble["records"]):
        source = source_records[record_id]
        calibration_path = Path(protocol["calibration_dir"]) / f"{record_id}.json"
        calibration = json.loads(calibration_path.read_text())
        source_sha256 = hashlib.sha256(source.encode()).hexdigest()
        if calibration["source_sha256"] != source_sha256 or base_record["source_sha256"] != source_sha256 or ensemble_record["source_cds_sha256"] != source_sha256:
            raise ValueError(f"source or calibration mismatch: {record_id}")
        solutions = list(dict.fromkeys(run["evaluation_sequence_dna"] for run in ensemble_record["runs"]))
        payload = {
            "status": "done",
            "record_id": record_id,
            "seed": 0,
            "benchmark_sha256": protocol["benchmark_sha256"],
            "source_sha256": source_sha256,
            "rscu_sha256": protocol["rscu_sha256"],
            "code_commit": code_commit,
            "methods": {
                added: {
                    "status": "done",
                    "solutions": solutions,
                    "n_unique": len(solutions),
                    "obj_vectors": None,
                    "elapsed_s": ensemble_record["elapsed_s"],
                    "generator_calls": len(ensemble_record["runs"]),
                }
            },
        }
        added_method = recompute_actual_set(payload, source, calibration, rscu)[added]
        added_method["measured_generation_cost"] = {
            "wall_clock_seconds": ensemble_record["elapsed_s"],
            "official_process_calls": 1,
            "official_generator_runs": len(ensemble_record["runs"]),
            "external_process_workers": 1,
            "internal_threads": ensemble_protocol["parameters"]["num_threads"],
            "lineardesign_initialization_calls": len(ensemble_record["runs"]),
            "linearpartition_scoring_calls": len(ensemble_record["runs"]),
            "hardware": ensemble["platform"],
            "forward_calls": None,
            "time_semantics": "one end-to-end official process per record, including generation, internal initialization/scoring, startup and I/O; independent shared scoring excluded",
        }
        methods = copy.deepcopy(base_record["methods"])
        methods[added] = added_method
        if list(methods) != protocol["method_order"]:
            raise ValueError(f"method order mismatch: {record_id}")
        record_result = {
            "record_id": record_id,
            "source_sha256": source_sha256,
            "calibration": str(calibration_path),
            "calibration_sha256": sha256(calibration_path),
            "base_record_methods_copied_without_modification": True,
            "ensemble_record_best_run_id": ensemble_record["best_run_id"],
            "ensemble_record_unique_official_outputs": ensemble_record["unique_output_sequences"],
            "methods": methods,
        }
        result["records"].append(record_result)
        compact = {
            "record_id": record_id,
            "completed_records": len(result["records"]),
            "added_method": added,
            "hypervolume_normalized": added_method["actual_set"]["hypervolume_normalized"],
            "ned": added_method["ned"],
            "n_actual_outputs": added_method["actual_set"]["n_actual_outputs"],
            "n_pareto_points": added_method["actual_set"]["n_pareto_points"],
        }
        atomic_json(progress, compact)
        print(json.dumps(compact), flush=True)
    if len(result["records"]) != 18:
        raise ValueError("seven-method matrix requires 18 records")

    comparisons = {}
    raw_p = {}
    reference = protocol["reference_method"]
    for comparator_index, comparator in enumerate(protocol["primary_comparators"]):
        for metric_index, metric in enumerate(["hypervolume_normalized", "ned"]):
            key = f"{reference}_minus_{comparator}:{metric}"
            new_values = []
            comparator_values = []
            for record in result["records"]:
                ref_method = record["methods"][reference]
                old_method = record["methods"][comparator]
                new_values.append(ref_method["actual_set"]["hypervolume_normalized"] if metric == "hypervolume_normalized" else ref_method["ned"])
                comparator_values.append(old_method["actual_set"]["hypervolume_normalized"] if metric == "hypervolume_normalized" else old_method["ned"])
            effect = paired_effect(new_values, comparator_values, protocol["statistics"]["paired_bootstrap_resamples"],
                                   protocol["statistics"]["bootstrap_seed"] + 100 * comparator_index + metric_index)
            effect["comparator"] = comparator
            effect["metric"] = metric
            comparisons[key] = effect
            raw_p[key] = effect["bootstrap_p_two_sided"]
    adjusted = holm_adjust(raw_p)
    for key in comparisons:
        comparisons[key]["holm_p_twelve_primary"] = adjusted[key]
        comparisons[key]["ci_excludes_zero"] = comparisons[key]["ci95"][0] * comparisons[key]["ci95"][1] > 0
    result["primary_comparisons"] = comparisons
    result["method_summary"] = {}
    for name in protocol["method_order"]:
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
    ld_costs = [record["methods"][reference]["measured_generation_cost"]["wall_clock_seconds"] for record in result["records"]]
    ensemble_costs = [record["methods"][added]["measured_generation_cost"]["wall_clock_seconds"] for record in result["records"]]
    result["generation_cost_descriptive_not_time_matched"] = {
        "lineardesign_lambda11": {"total_seconds": float(sum(ld_costs)), "mean_seconds_per_record": float(np.mean(ld_costs)), "external_workers": 1, "internal_threads": 1},
        "ensembledesign_11run": {"total_seconds": float(sum(ensemble_costs)), "mean_seconds_per_record": float(np.mean(ensemble_costs)), "external_workers": 1, "internal_threads": ensemble_protocol["parameters"]["num_threads"]},
        "lineardesign_minus_ensembledesign_seconds_per_record": [float(a - b) for a, b in zip(ld_costs, ensemble_costs)],
        "lineardesign_divided_by_ensembledesign_per_record": [float(a / b) for a, b in zip(ld_costs, ensemble_costs)],
        "note": "different internal threading and algorithms; descriptive measured cost only, not a unified time-matched comparison",
    }
    result["reanalysis_elapsed_s_not_generation_cost"] = time.perf_counter() - started
    result["status"] = "COMPLETE_UNIQUE18_SEVEN_METHOD_ACTUAL_SET_MATRIX_DEVELOPMENT_ONLY"
    atomic_json(args.output, result)
    audit = {
        "schema": "a8-rk13-seven-method-actual-set-matrix-audit-v1",
        "status": "PASS",
        "output": str(args.output),
        "output_sha256": sha256(args.output),
        "protocol_sha256": sha256(args.protocol),
        "base_matrix_sha256": protocol["base_matrix_sha256"],
        "ensemble_report_sha256": sha256(args.ensemble_report),
        "ensemble_independent_sha256": sha256(args.ensemble_independent),
        "record_count": len(result["records"]),
        "method_summary": result["method_summary"],
        "primary_comparisons": result["primary_comparisons"],
        "descriptive_highest_mean_hv_method": result["descriptive_highest_mean_hv_method"],
        "generation_cost_descriptive_not_time_matched": result["generation_cost_descriptive_not_time_matched"],
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
