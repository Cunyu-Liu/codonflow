#!/usr/bin/env python3
"""Finalize RK-12 only after grid, matrix and independent checks all pass."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

from scripts.a8_rk12_verify_lineardesign_unique18 import sha256


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid-protocol", type=Path, required=True)
    parser.add_argument("--grid", type=Path, required=True)
    parser.add_argument("--grid-independent", type=Path, required=True)
    parser.add_argument("--matrix-protocol", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--matrix-independent", type=Path, required=True)
    parser.add_argument("--prior-smoke", type=Path, required=True)
    parser.add_argument("--tests-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    grid = json.loads(args.grid.read_text())
    grid_independent = json.loads(args.grid_independent.read_text())
    matrix = json.loads(args.matrix.read_text())
    matrix_independent = json.loads(args.matrix_independent.read_text())
    prior = json.loads(args.prior_smoke.read_text())
    checks = []

    def record(name, passed, evidence=None):
        checks.append({"check": name, "pass": bool(passed), "evidence": evidence})

    record("grid_complete", grid["status"] == "COMPLETE_UNIQUE18_OFFICIAL_LINEARDESIGN_LAMBDA_GRID" and grid["run_count"] == 198 and grid["record_count"] == 18)
    record("grid_independent", grid_independent["status"] == "PASS" and grid_independent["checks_passed"] == grid_independent["checks_total"] == 35 and grid_independent["production_sha256"] == sha256(args.grid), grid_independent["checks_total"])
    record("grid_numeric_exact", grid_independent["max_independent_cai_recompute_delta"] == 0.0 and grid_independent["max_independent_mfe_recompute_delta"] == 0.0 and grid_independent["structure_mismatch_count"] == 0)
    raw_paths = [Path(run[key]) for run in grid["runs"] for key in ["stdout_path", "stderr_path"]]
    record("grid_raw_outputs", len(raw_paths) == 396 and all(path.exists() and path.stat().st_size >= 0 for path in raw_paths))
    current = {(run["record_id"], run["lambda"]): run for run in grid["runs"]}
    compatibility = []
    for previous_run in prior["runs"]:
        run = current[("C01H6.8b.1", previous_run["lambda"])]
        compatibility.append(
            run["sequence_dna"] == previous_run["sequence_dna"]
            and run["official_mfe_kcal_mol"] == previous_run["official_mfe_kcal_mol"]
            and run["official_cai"] == previous_run["official_cai"]
        )
    record("prior_c01_smoke_bitwise_sequence_compatibility", len(compatibility) == 3 and all(compatibility), compatibility)
    record("matrix_complete", matrix["status"] == "COMPLETE_UNIQUE18_ACTUAL_SET_MATRIX_DEVELOPMENT_ONLY" and len(matrix["records"]) == 18)
    record("matrix_independent", matrix_independent["status"] == "PASS" and matrix_independent["checks_passed"] == matrix_independent["checks_total"] == 139 and matrix_independent["matrix_sha256"] == sha256(args.matrix), matrix_independent["checks_total"])
    record("matrix_numeric_recompute", matrix_independent["max_objective_recompute_delta"] <= 1e-9 and matrix_independent["max_hypervolume_recompute_delta"] <= 1e-9 and matrix_independent["max_ned_recompute_delta"] <= 1e-9, {"objective": matrix_independent["max_objective_recompute_delta"], "hv": matrix_independent["max_hypervolume_recompute_delta"], "ned": matrix_independent["max_ned_recompute_delta"]})
    record("matrix_clean_scorer_provenance", matrix["scorer_tracked_dirty"] is False and matrix["scorer_script_tracked"] is True and matrix["development_uncommitted_allowed"] is False, matrix["scorer_code_commit"])
    record("matrix_identity", all(summary["min_identity_rate"] == 1.0 for summary in matrix["method_summary"].values()))
    record("matrix_finite_summary", all(math.isfinite(summary["mean_hypervolume_normalized"]) and math.isfinite(summary["mean_ned"]) for summary in matrix["method_summary"].values()))
    record("four_primary_comparisons", len(matrix["primary_comparisons"]) == 4 and all(item["n_records"] == 18 and len(item["ci95"]) == 2 and math.isfinite(item["holm_p_four_primary"]) for item in matrix["primary_comparisons"].values()))
    record("measured_new_cost_linked", math.isclose(matrix["new_lineardesign_total_generation_seconds"], grid["total_generation_elapsed_s"], rel_tol=0.0, abs_tol=1e-9), grid["total_generation_elapsed_s"])
    record("tests", "10 passed" in args.tests_log.read_text())
    record("excluded_claims", matrix["dense_budget_step_auc_v2"] is None and matrix["time_matched_comparison"] is False and matrix["scientific_gate_passed"] is False and matrix["sota_claim"] is False and matrix["descriptive_ranking_not_sota"] is True)
    passed = sum(item["pass"] for item in checks)
    report = {
        "schema": "a8-rk12-finalization-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS_COMPLETE_RK12_UNIQUE18_LINEARDESIGN_AND_ACTUAL_SET_MATRIX" if passed == len(checks) else "FAIL",
        "checks": checks,
        "checks_passed": passed,
        "checks_total": len(checks),
        "grid_sha256": sha256(args.grid),
        "grid_independent_sha256": sha256(args.grid_independent),
        "matrix_sha256": sha256(args.matrix),
        "matrix_independent_sha256": sha256(args.matrix_independent),
        "grid_protocol_sha256": sha256(args.grid_protocol),
        "matrix_protocol_sha256": sha256(args.matrix_protocol),
        "run_count": grid["run_count"],
        "record_count": grid["record_count"],
        "unique_output_sequences_global": grid["unique_output_sequences_global"],
        "lineardesign_generation_seconds": grid["total_generation_elapsed_s"],
        "method_summary": matrix["method_summary"],
        "primary_comparisons": matrix["primary_comparisons"],
        "descriptive_highest_mean_hv_method": matrix["descriptive_highest_mean_hv_method"],
        "scientific_gate_passed": False,
        "main_model_comparison": False,
        "time_matched_comparison": False,
        "dense_budget_step_auc_v2": None,
        "sota_claim": False,
        "remaining_gates": [
            "CodonFlow-RK model outputs are not part of this external-method matrix",
            "real dense budget-step AUC and time-matched cross-method costs remain unavailable",
            "untouched24, functional untouched, wet-lab and final SOTA decisions remain closed",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ["checks", "method_summary", "primary_comparisons"]}, indent=2))
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
