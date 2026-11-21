#!/usr/bin/env python3
"""Release gate for independently verified RK31 result packaging."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--freeze-report", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--test-log", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    freeze = json.loads(args.freeze_report.read_text())
    result = json.loads(args.result.read_text())
    independent = json.loads(args.independent.read_text())
    test_text = args.test_log.read_text()
    checks = []

    def check(name: str, condition: bool, evidence=None) -> None:
        checks.append({"check": name, "pass": bool(condition), "evidence": evidence})

    check("freeze", freeze.get("status") == "PASS_RK31_PREEXPERIMENT_FREEZE" and
          freeze.get("protocol_sha256") == sha256(args.protocol) and
          freeze.get("production_script_sha256") == result.get("analysis_script_sha256"))
    check("result_pending_then_independently_verified", result.get("status") == "ANALYSIS_COMPLETE_PENDING_INDEPENDENT_VERIFICATION" and
          independent.get("status") == "PASS_INDEPENDENT_VERIFICATION")
    check("result_binding", independent.get("result_sha256") == sha256(args.result) and
          result.get("protocol_sha256") == sha256(args.protocol))
    check("independent_fit_count", independent.get("independent_fit_count") == 450 and result.get("ridge_fit_count") == 450)
    check("all_primary_endpoints", len(result.get("primary_endpoints", [])) == 24)
    check("conclusion_exact", independent.get("scientific_conclusion") == result.get("scientific_conclusion") and
          independent.get("known_context_applicability_pass") == result.get("known_context_applicability_pass") and
          independent.get("gating_over_shared_full_pass") == result.get("gating_over_shared_full_pass"))
    check("no_failed_independent_checks", not independent.get("failed_checks"))
    check("no_production_import", independent.get("production_module_imported") is False and
          independent.get("rk28_production_helper_imported") is False)
    differences = independent.get("max_abs_differences", {})
    check("numeric_tolerances", differences.get("prediction", 1) < 1e-9 and differences.get("metric", 1) < 1e-9 and
          differences.get("effect", 1) < 1e-9 and differences.get("inference", 1) < 1e-8 and
          differences.get("fold", 1) == 0, differences)
    for name, item in result["outputs"].items():
        path = args.artifact_root / "model" / name
        check(f"artifact_{name}", path.exists() and sha256(path) == item["sha256"])
    passed = re.search(r"(\d+) passed", test_text)
    failed = re.search(r"(\d+) failed", test_text)
    check("project_tests", passed is not None and int(passed.group(1)) >= 423 and
          (failed is None or int(failed.group(1)) == 0), passed.group(0) if passed else None)
    check("failure_evidence_preserved", (args.result.parent / "rk31_production_console_v1.log").exists() and
          (args.result.parent / "rk31_independent_verification_v1.json").exists())
    check("functional_untouched_closed", protocol["scientific_boundaries"]["functional_untouched_read"] is False and
          independent.get("functional_untouched_read") is False)
    check("generator_not_authorized", protocol["scientific_boundaries"]["generator_training_authorized"] is False and
          independent.get("generator_training_authorized") is False)
    check("remaining_tasks_not_misrepresented", protocol["scientific_boundaries"]["complete_external_sota"] is False and
          protocol["scientific_boundaries"]["rk_g1_complete"] is False)
    failed_checks = [c for c in checks if not c["pass"]]
    report = {
        "schema": "a8-rk31-closeout-v1",
        "status": "PASS_RK31_VERIFIED_RESULT_PACKAGING" if not failed_checks else "FAIL_RK31_VERIFIED_RESULT_PACKAGING",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "code_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1],
                                      capture_output=True, text=True, check=True).stdout.strip(),
        "protocol_sha256": sha256(args.protocol), "freeze_sha256": sha256(args.freeze_report),
        "result_sha256": sha256(args.result), "independent_sha256": sha256(args.independent),
        "test_log_sha256": sha256(args.test_log),
        "artifact_root": str(args.artifact_root),
        "checks_total": len(checks), "checks_passed": len(checks) - len(failed_checks), "failed_checks": failed_checks,
        "checks": checks,
        "scientific_conclusion": result["scientific_conclusion"],
        "known_context_applicability_pass": result["known_context_applicability_pass"],
        "gating_over_shared_full_pass": result["gating_over_shared_full_pass"],
        "context_status": result["context_status"],
        "ridge_fit_count": result["ridge_fit_count"],
        "production_elapsed_seconds": result["elapsed_seconds"],
        "independent_elapsed_seconds": independent["elapsed_seconds"],
        "primary_endpoints": result["primary_endpoints"],
        "primary_absolute_performance": result["primary_absolute_performance"],
        "remaining_gates": [
            "This retrospective known-context analysis does not close unseen-context transport or protein-OOD.",
            "Complete external SOTA, dense budget-step AUC, unified time-matched cost and functional OOD remain separate tasks.",
            "RK-G1 remains false; generator training remains unauthorized and functional untouched remains unread.",
            "Wet-lab and prospective DBTL were not performed."
        ]
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (args.artifact_root / "RK31_CLOSEOUT.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}",
                      "conclusion": report["scientific_conclusion"], "output": str(args.output)}, indent=2))
    if failed_checks:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
