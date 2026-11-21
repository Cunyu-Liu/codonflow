#!/usr/bin/env python3
"""Evidence-bound RK37 scientific closeout; reporting is handled separately."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    audit = root / "audits/20261122/RK37"
    paths = {
        "protocol": root / "configs/a8_rk37_translation_pivot_protocol_v1.json",
        "production": audit / "rk37_translation_pivot_result_v1.json",
        "independent": audit / "rk37_translation_pivot_independent_v1.json",
        "clean_result": audit / "rk37_translation_pivot_clean_result_v1.json",
        "comparison": audit / "rk37_clean_reproduction_comparison_v1.json",
        "contract_log": audit / "rk37_contract_tests_v1.log",
        "failed_contract_log": audit / "rk37_contract_tests_failure_v1.log",
        "project_test_log": audit / "rk37_project_tests_v1.log",
    }
    data = {key: json.loads(path.read_text()) for key, path in paths.items() if key in ("protocol", "production", "independent", "clean_result", "comparison")}
    checks = []

    def check(name, condition, evidence=None):
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})

    for key, path in paths.items():
        check(f"exists_{key}", path.is_file() and path.stat().st_size > 0)
    production = data["production"]
    independent = data["independent"]
    clean = data["clean_result"]
    comparison = data["comparison"]
    protocol = data["protocol"]
    check("protocol_sha", sha256(paths["protocol"]) == production["protocol_sha256"] == clean["protocol_sha256"])
    check("production_status", production["status"] == "PASS_RK37_PRODUCTION_PENDING_INDEPENDENT")
    check("independent_status", independent["status"] == "PASS_RK37_INDEPENDENT")
    check("independent_all_checks", independent["checks_passed"] == independent["checks_total"] and not independent["failures"])
    check("independent_production_hash_binding", independent["production_report"]["sha256"] == sha256(paths["production"]))
    check("clean_comparison_status", comparison["status"] == "PASS_RK37_CLEAN_REPRODUCTION")
    check("clean_comparison_all_checks", comparison["checks_passed"] == comparison["checks_total"] and not comparison["failures"])
    check("clean_array_accounting", comparison["exact_arrays_compared"] == 111)
    check("clean_production_hash_binding", comparison["production"]["sha256"] == sha256(paths["production"]))
    check("clean_result_hash_binding", comparison["clean"]["sha256"] == sha256(paths["clean_result"]))
    check("clean_decision", clean["scientific_decision"] == production["scientific_decision"] == independent["independent_decision"] == comparison["scientific_decision"])
    check("fit_accounting", production["fit_accounting"]["actual_unique_fits"] == independent["independent_fit_count"] == clean["fit_accounting"]["actual_unique_fits"] == 48)
    check("target_after_source_gate", production["target_outcomes_accessed_after_all_source_fits"] is True and clean["target_outcomes_accessed_after_all_source_fits"] is True)
    check("distribution_metrics_present", all(s["target_evaluation"]["distribution_metrics_present"] for s in production["source_reports"] + clean["source_reports"]))
    check("source_target_disjoint", production["target_identity"]["exact_cds_overlap"] == 0)
    check("negative_decision", production["scientific_decision"] == "CROSS_STUDY_TRANSLATION_TASK_UNRESOLVED_COMPONENT_DIAGNOSIS_REQUIRED")
    check("two_endpoints", len(production["primary_endpoints"]) == 2)
    for i, endpoint in enumerate(production["primary_endpoints"]):
        check(f"primary_{i}_negative_effect", endpoint["effect"] < 0)
        check(f"primary_{i}_gate_false", endpoint["gate_pass"] is False and endpoint["primary_pass"] is False and endpoint["sensitivity_pass"] is False)
        check(f"primary_{i}_ci_excludes_zero", endpoint["ci95_high"] < 0)
        check(f"primary_{i}_independent_match", independent["independent_primary_endpoints"][i]["gate_pass"] is False)
    expected_alpha = {1234: 0.1, 2345: 100.0, 3456: 100.0}
    for source in production["source_reports"]:
        seed = source["seed"]
        check(f"seed_{seed}_local_alpha", source["selected_alpha"]["local_centered_anchored"] == expected_alpha[seed])
        check(f"seed_{seed}_position_alpha", source["selected_alpha"]["position_raw_unanchored"] == 100.0)
        metrics = source["target_evaluation"]["target_metrics"]
        constant = metrics["constant"]["transcript_balanced_mse"]
        for arm in ("ribomimo_raw", "ribomimo_anchored", "position_raw_unanchored", "position_raw_anchored", "position_centered_anchored", "local_raw_anchored", "local_centered_anchored"):
            check(f"seed_{seed}_{arm}_does_not_beat_constant_mse", metrics[arm]["transcript_balanced_mse"] > constant)
        check(f"seed_{seed}_local_r_below_position", metrics["local_centered_anchored"]["mean_transcript_pearson"] < metrics["position_raw_unanchored"]["mean_transcript_pearson"])
        for artifact in source["target_evaluation"]["artifacts"].values():
            check(f"artifact_sha_{seed}_{Path(artifact['path']).name}", sha256(artifact["path"]) == artifact["sha256"])
    for artifact in independent["artifacts"]["predictions"] + independent["artifacts"]["models"] + [independent["artifacts"]["inference"]]:
        check(f"independent_artifact_{Path(artifact['path']).name}", sha256(artifact["path"]) == artifact["sha256"])
    check("inference_artifact_sha", sha256(production["artifacts"]["primary_inference_arrays"]["path"]) == production["artifacts"]["primary_inference_arrays"]["sha256"])
    contract = paths["contract_log"].read_text()
    check("contract_11_pass", "11 passed" in contract and "failed" not in contract.lower())
    check("initial_contract_failure_retained", "2 failed" in paths["failed_contract_log"].read_text())
    project = paths["project_test_log"].read_text()
    check("project_tests_pass", re.search(r"\d+ passed", project) is not None and not re.search(r"\d+ failed", project))
    for key in ("functional_untouched_read", "generator_training_authorized", "rk_g1_complete", "sota_claim_authorized", "wet_lab_or_prospective_dbtl"):
        check(f"boundary_{key}", production["scientific_scope"][key] is False)
    check("retrospective_boundary", production["scientific_scope"]["retrospective_followup_not_untouched"] is True)
    check("large_artifacts_outside_git", "/teams/HoulabData_1788502323/liucunyu/" in production["artifacts"]["output_directory"])
    passed = sum(item["pass"] for item in checks)
    report = {
        "schema": "a8-rk37-science-closeout-v1",
        "status": "PASS_RK37_SCIENCE_CLOSEOUT" if passed == len(checks) else "FAIL",
        "checks_passed": passed, "checks_total": len(checks), "failures": [c for c in checks if not c["pass"]],
        "checks": checks,
        "evidence": {key: {"path": str(path), "sha256": sha256(path)} for key, path in paths.items()},
        "scientific_decision": production["scientific_decision"],
        "primary_endpoints": production["primary_endpoints"],
        "verification": {"independent": f"{independent['checks_passed']}/{independent['checks_total']}", "clean": f"{comparison['checks_passed']}/{comparison['checks_total']}", "exact_clean_arrays": comparison["exact_arrays_compared"]},
        "scientific_boundaries": "RK37 is a retrospective cross-study translation-occupancy diagnostic with a negative dual gate. It is not protein OOD, physical velocity, untouched confirmation, SOTA, wet-lab/prospective DBTL or RK-G1.",
        "reporting_status": "Manuscript, online slides and documentation are separate pending closeout steps.",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "failures": report["failures"][:5]}, indent=2))
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
