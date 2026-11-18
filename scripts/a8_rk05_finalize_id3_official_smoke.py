#!/usr/bin/env python3
"""Finalize the bounded ID3 official quick-test evidence without hiding failed checks."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ALLOWED_INDEPENDENT = {
    "PASS_OFFICIAL_QUICK_TEST_INDEPENDENT_VERIFICATION",
    "BOUNDED_OFFICIAL_EXECUTION_COMPLETE_WITH_CPC_STE_TRAJECTORY_DEFECT",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-report", type=Path, required=True)
    parser.add_argument("--verification-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    production_path = args.production_report.resolve()
    verification_path = args.verification_report.resolve()
    production = json.loads(production_path.read_text())
    independent = json.loads(verification_path.read_text())
    report = {
        "schema_version": "a8-rk05-id3-official-quick-test-finalization-v1",
        "status": "FAIL_FINALIZATION",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "checks": [],
    }

    def check(name: str, passed: bool, detail=None) -> None:
        report["checks"].append({"name": name, "pass": bool(passed), "detail": detail})

    command = production.get("official_command", [])
    output_dir = Path(command[command.index("--output-dir") + 1]) if "--output-dir" in command else None
    summary_path = output_dir / "summary.json" if output_dir else None
    summary = json.loads(summary_path.read_text()) if summary_path and summary_path.is_file() else {}
    rows = independent.get("per_run_score_recomputation", [])
    final_values = [float(row["recomputed_final_accessibility"]) for row in rows]
    bounded = independent.get("bounded_acceptance", {})
    failed_names = set(independent.get("failed_check_names", []))
    expected_failures = {
        f"{kind}_score_recompute_{filename}"
        for filename in bounded.get("final_only_runs", [])
        for kind in ("initial", "best")
    }

    check("official_execution_and_production_checks", production.get("status") == "PASS_OFFICIAL_QUICK_TEST_SMOKE" and production.get("official_returncode") == 0 and all(x.get("pass") for x in production.get("checks", [])), {"status": production.get("status"), "checks": f"{production.get('checks_passed')}/{production.get('checks_total')}"})
    check("independent_status_allowed", independent.get("status") in ALLOWED_INDEPENDENT, independent.get("status"))
    check("production_report_hash_linked", independent.get("production_report_sha256") == sha256(production_path), None)
    check("official_12_success_zero_failure", summary.get("experiment_overview", {}).get("total_experiments") == 12 and summary.get("experiment_overview", {}).get("successful") == 12 and summary.get("experiment_overview", {}).get("failed") == 0, summary.get("experiment_overview"))
    check("12_independent_final_scores", len(rows) == 12 and len(final_values) == 12 and all(math.isfinite(x) for x in final_values) and bounded.get("final_sequence_score_accepted_runs") == 12, len(rows))
    check("24_discrete_candidates_recomputed", independent.get("score_recomputation", {}).get("discrete_trajectory_records_scored") == 24, independent.get("score_recomputation"))
    check("best_sequences_match_posthoc_argmin", bounded.get("official_best_sequences_match_recomputed_argmin_for_all_runs") is True, None)
    if independent.get("status") == "BOUNDED_OFFICIAL_EXECUTION_COMPLETE_WITH_CPC_STE_TRAJECTORY_DEFECT":
        check("exact_four_red_metric_checks_retained", failed_names == expected_failures and len(failed_names) == 4, sorted(failed_names))
        check("ten_full_two_final_only", bounded.get("full_metric_payload_accepted_runs") == 10 and len(bounded.get("final_only_runs", [])) == 2, bounded)
        defect = independent.get("upstream_cpc_ste_defect", {})
        check("fixed_source_defect_evidence", defect.get("cpc_forward", {}).get("detected") is True and defect.get("runner", {}).get("detected") is True, defect)
        final_status = "BOUNDED_OFFICIAL_QUICK_TEST_COMPLETE_WITH_CPC_STE_TRAJECTORY_DEFECT"
    elif independent.get("status") == "PASS_OFFICIAL_QUICK_TEST_INDEPENDENT_VERIFICATION":
        check("full_independent_pass", not failed_names and bounded.get("full_metric_payload_accepted_runs") == 12, independent.get("status"))
        final_status = "PASS_OFFICIAL_QUICK_TEST_INDEPENDENTLY_VERIFIED"
    else:
        check("recognized_independent_outcome", False, independent.get("status"))

    final_stats = {
        "count": len(final_values),
        "mean": sum(final_values) / len(final_values) if final_values else None,
        "min": min(final_values) if final_values else None,
        "max": max(final_values) if final_values else None,
    }
    saved_stats = summary.get("statistics", {}).get("accessibility", {})
    stats_match = bool(final_values) and (
        abs(float(saved_stats.get("average")) - final_stats["mean"]) <= 2e-5
        and abs(float(saved_stats.get("best")) - final_stats["min"]) <= 2e-5
        and abs(float(saved_stats.get("worst")) - final_stats["max"]) <= 2e-5
    )
    check("official_final_statistics_recomputed", stats_match, {"saved": saved_stats, "independent": final_stats})

    report["checks_passed"] = sum(x["pass"] for x in report["checks"])
    report["checks_total"] = len(report["checks"])
    all_pass = bool(report["checks"]) and all(x["pass"] for x in report["checks"])
    if all_pass:
        report["status"] = final_status
    report["source"] = {
        "id3_commit": production.get("source", {}).get("id3_commit"),
        "deepraccess_commit": production.get("source", {}).get("deepraccess_commit"),
        "id3_zip_sha256": production.get("source", {}).get("id3_zip_sha256"),
        "output_dir": str(output_dir) if output_dir else None,
    }
    report["execution"] = {
        "preset": "quick-test",
        "protein": "O15263",
        "constraints": ["lagrangian", "ams", "cpc"],
        "variants": ["00", "01", "10", "11"],
        "iterations": 2,
        "seed": 42,
        "device": "cpu",
        "successful": 12,
        "failed": 0,
        "official_total_wall_time_s": summary.get("experiment_overview", {}).get("total_time"),
        "orchestration_wall_time_s": production.get("orchestration_wall_time_s"),
        "recorded_discrete_candidates": 24,
    }
    report["independent_acceptance"] = {
        "verification_status": independent.get("status"),
        "verification_checks_passed": independent.get("checks_passed"),
        "verification_checks_total": independent.get("checks_total"),
        "failed_check_names_retained": sorted(failed_names),
        "fully_verified_metric_payload_runs": bounded.get("full_metric_payload_accepted_runs"),
        "final_sequence_score_verified_runs": bounded.get("final_sequence_score_accepted_runs"),
        "final_only_runs": bounded.get("final_only_runs", []),
        "excluded_official_outputs": [
            "For cpc-01 and cpc-11: initial_accessibility, best_accessibility, best_seq_design.accessibility, improvement and trajectory.accessibility.",
            "summary.performance_table, summary.constraint_comparison and summary.variant_comparison because they aggregate affected best metrics.",
            "Any method ranking, full-12x12 interpretation, multi-seed statistics, dense-budget claim, functional expression claim or SOTA claim.",
        ],
        "accepted_final_statistics": final_stats,
        "official_statistics_std_not_used": True,
        "posthoc_recomputed_rows": [
            {
                "file": row["file"],
                "acceptance": row["acceptance"],
                "recorded_initial_accessibility": row["recorded_initial_accessibility"],
                "recomputed_initial_accessibility": row["recomputed_initial_accessibility"],
                "recorded_best_accessibility": row["recorded_best_accessibility"],
                "recomputed_official_best_sequence_accessibility": row["recomputed_official_best_sequence_accessibility"],
                "recorded_final_accessibility": row["recorded_final_accessibility"],
                "recomputed_final_accessibility": row["recomputed_final_accessibility"],
                "recomputed_best_iteration": row["recomputed_best_iteration"],
                "official_best_sequence_matches_recomputed_best": row["official_best_sequence_matches_recomputed_best"],
            }
            for row in rows
        ],
    }
    report["upstream_defect"] = independent.get("upstream_cpc_ste_defect")
    report["artifacts"] = {
        "production_report": {"path": str(production_path), "sha256": sha256(production_path), "bytes": production_path.stat().st_size},
        "independent_report": {"path": str(verification_path), "sha256": sha256(verification_path), "bytes": verification_path.stat().st_size},
        "official_summary": {"path": str(summary_path) if summary_path else None, "sha256": sha256(summary_path) if summary_path and summary_path.is_file() else None},
    }
    report["science_flags"] = {
        "bounded_quick_test_record_ready": all_pass,
        "ppt_record_ready": all_pass,
        "official_12_run_execution_complete": True,
        "all_final_sequence_scores_verified": len(final_values) == 12,
        "all_payload_metrics_verified": independent.get("status") == "PASS_OFFICIAL_QUICK_TEST_INDEPENDENT_VERIFICATION",
        "main_baseline_comparison": False,
        "full_12x12_executed": False,
        "multi_seed_evaluation": False,
        "dense_budget_evaluation": False,
        "functional_expression_claim": False,
        "sota_claim": False,
    }
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(args.output, report)
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "output": str(args.output)}, indent=2))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
