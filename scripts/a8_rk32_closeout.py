#!/usr/bin/env python3
"""Release gate for independently verified and clean-reproduced RK32 packaging."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ["protocol", "preflight", "result", "independent", "reproduction", "test-log", "artifact-root", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    preflight = json.loads(args.preflight.read_text())
    result = json.loads(args.result.read_text())
    independent = json.loads(args.independent.read_text())
    reproduction = json.loads(args.reproduction.read_text())
    test_text = args.test_log.read_text()
    checks = []

    def check(name: str, condition: bool, evidence=None) -> None:
        checks.append({"check": name, "pass": bool(condition), "evidence": evidence})

    check("label_free_preflight", preflight.get("status") == "PASS_LABEL_FREE_STRUCTURE_PREFLIGHT" and
          preflight.get("expression_columns_read") is False and preflight.get("model_fit_performed") is False and
          sha256(args.preflight) == protocol["inputs"]["preflight_report"]["sha256"])
    check("frozen_before_expression_association", protocol.get("status") == "FROZEN_BEFORE_RK32_EXPRESSION_ASSOCIATION_OR_MODEL_FIT" and
          protocol.get("expression_association_or_model_fit_performed_before_freeze") is False)
    check("protocol_result_binding", result.get("protocol_sha256") == sha256(args.protocol) and
          independent.get("protocol_sha256") == sha256(args.protocol))
    check("independent_result_binding", independent.get("production_result_sha256") == sha256(args.result))
    check("independent_pass", independent.get("status") == "PASS" and len(independent.get("checks", [])) == 23 and
          all(x.get("pass") for x in independent["checks"]))
    check("fit_and_endpoint_accounting", result.get("total_model_fits") == 700 and len(result.get("primary_tests", [])) == 24)
    check("conclusion_exact", independent.get("scientific_conclusion") == result.get("scientific_conclusion") ==
          "STRUCTURE_INCREMENT_DEFINITION_DEPENDENT_RETROSPECTIVELY")
    check("arm_decisions", len(result.get("arm_results", [])) == 6 and
          sum(x["all_four_pass"] for x in result["arm_results"]) == 2 and
          sum(x["n_pass"] for x in result["arm_results"]) == 9)
    check("numeric_tolerances", all(float(v) <= 1e-10 for v in independent["max_deltas"].values()), independent["max_deltas"])
    for name, item in result["outputs"].items():
        path = args.artifact_root / name
        check(f"artifact_{name}", path.is_file() and sha256(path) == item["sha256"])
    check("clean_reproduction", reproduction.get("status") == "PASS_RK32_CLEAN_CHECKOUT_REPRODUCTION" and
          reproduction.get("checks_passed") == reproduction.get("checks_total") and
          reproduction.get("clean_clone_head") == "469b30e4604f3545157c299b18ab24a3713cf322")
    check("clean_artifact_equality", reproduction.get("csv_count") == 6 and reproduction.get("csv_byte_equal_count") == 6 and
          reproduction.get("npz_array_count") == reproduction.get("npz_exact_equal_count") and reproduction.get("npz_array_count", 0) > 0)
    passed = re.search(r"(\d+) passed", test_text)
    skipped = re.search(r"(\d+) skipped", test_text)
    failed = re.search(r"(\d+) failed", test_text)
    errors = re.search(r"(\d+) errors?", test_text)
    n_passed = int(passed.group(1)) if passed else 0
    n_skipped = int(skipped.group(1)) if skipped else 0
    check("project_tests", passed is not None and n_passed >= 423 and
          (failed is None or int(failed.group(1)) == 0) and (errors is None or int(errors.group(1)) == 0),
          {"passed": n_passed, "skipped": n_skipped})
    check("failure_evidence_preserved", (args.result.parent / "rk32_structure_definition_console_v1.log").is_file() and
          (args.result.parent / "rk32_structure_definition_independent_console_v2.log").is_file() and
          (args.result.parent / "rk32_structure_definition_independent_console_v3.log").is_file() and
          (args.result.parent / "a8_rk32_structure_definition_protocol_v1.json").is_file())
    check("functional_untouched_closed", protocol.get("functional_untouched_read") is False and
          independent.get("functional_untouched_read") is False and reproduction.get("functional_untouched_read") is False)
    check("generator_not_authorized", protocol.get("generator_training_authorized") is False)
    check("remaining_tasks_not_misrepresented", independent.get("independent_confirmation") is False and
          independent.get("RK_G1_complete") is False and reproduction.get("RK_G1_complete") is False)

    failed_checks = [x for x in checks if not x["pass"]]
    report = {
        "schema": "a8-rk32-closeout-v1",
        "status": "PASS_RK32_VERIFIED_RESULT_PACKAGING" if not failed_checks else "FAIL_RK32_VERIFIED_RESULT_PACKAGING",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1], text=True).strip(),
        "protocol_sha256": sha256(args.protocol), "preflight_sha256": sha256(args.preflight),
        "result_sha256": sha256(args.result), "independent_sha256": sha256(args.independent),
        "reproduction_sha256": sha256(args.reproduction), "test_log_sha256": sha256(args.test_log),
        "artifact_root": str(args.artifact_root), "checks_total": len(checks),
        "checks_passed": len(checks) - len(failed_checks), "failed_checks": failed_checks, "checks": checks,
        "scientific_conclusion": result["scientific_conclusion"], "arm_results": result["arm_results"],
        "primary_tests": result["primary_tests"], "primary_absolute_performance": result["primary_absolute_performance"],
        "total_model_fits": result["total_model_fits"], "pytest_passed": n_passed, "pytest_skipped": n_skipped,
        "production_elapsed_seconds": result["component_wall_seconds"],
        "independent_elapsed_seconds": independent["component_wall_seconds"],
        "remaining_gates": [
            "Retrospective fixed-GFP sequence-cluster OOD is not independent untouched confirmation or protein OOD.",
            "The Mordstein observed-R1 fragment cannot reconstruct the exact start-aware minus4-to-37 local window.",
            "Complete external SOTA, unified time-matched comparison and complete seven-method dense generation-call AUC remain open.",
            "Functional untouched remains unread; generator training remains unauthorized; RK-G1 remains false.",
            "Wet-lab and prospective DBTL were not performed."
        ]
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (args.artifact_root / "RK32_CLOSEOUT.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}",
                      "conclusion": report["scientific_conclusion"], "output": str(args.output)}, indent=2))
    if failed_checks:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
