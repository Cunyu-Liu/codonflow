#!/usr/bin/env python3
"""Independently verify the exact A8 v16 -> v17 RK-11-only manuscript delta."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    names = ("v16-paper", "v16-audit", "a7", "paper", "audit", "update-report", "protocol", "production", "retrain", "independent", "finalization", "unit-test-log", "initial-failure", "second-failure", "independent-initial-failure", "independent-second-failure", "development", "report")
    parser = argparse.ArgumentParser()
    for name in names:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    update = json.loads(args.update_report.read_text())
    old_paper = args.v16_paper.read_text(); old_audit = json.loads(args.v16_audit.read_text())
    paper = args.paper.read_text(); audit = json.loads(args.audit.read_text())
    production = json.loads(args.production.read_text()); retrain = json.loads(args.retrain.read_text())
    independent = json.loads(args.independent.read_text()); finalization = json.loads(args.finalization.read_text())
    checks = []
    def check(name, condition, detail):
        checks.append({"id": name, "pass": bool(condition), "detail": detail})

    check("v16_paper_gate", sha(args.v16_paper) == update["input_paper_sha256"], "snapshot matches update input")
    check("v16_audit_gate", sha(args.v16_audit) == update["input_audit_sha256"] and old_audit["schema_version"] == "a8-rk-paper-sync-v16", "v16 audit matched")
    check("paper_output_hash", sha(args.paper) == update["output_paper_sha256"] == audit["output_sha256"], "v17 paper hash agrees")
    check("audit_output_hash", sha(args.audit) == update["output_audit_sha256"], "v17 audit hash matched")
    check("a7_unchanged", sha(args.a7) == update["a7_sha256"] == "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423", "A7 unchanged")
    check("production_complete", production["status"] == "PASS_MINIMAL_NEURAL_SYNTHETIC_CUDA_CONTRACT" and production["checks_passed"] == production["checks_total"] == 14, "14/14")
    check("retrain_complete", retrain["status"] == "PASS_MINIMAL_NEURAL_SYNTHETIC_CUDA_CONTRACT" and retrain["checks_passed"] == retrain["checks_total"] == 14, "14/14")
    check("independent_complete", independent["status"] == "PASS_INDEPENDENT_MINIMAL_NEURAL" and independent["checks_passed"] == independent["checks_total"] == 27, "27/27")
    check("finalization_complete", finalization["status"] == "PASS_COMPLETE_WITH_INDEPENDENT_RETRAIN_AND_CUDA_CONTRACT" and finalization["checks_passed"] == finalization["checks_total"] == 25, "25/25")
    section = update["section"]
    check("single_rk11_section", paper.count("### 6.13 Minimal neural legal-kernel synthetic CUDA contract") == 1 and paper.count(section) == 1, "one exact Section 6.13")
    inverse = paper.replace(section, "").replace(update["evidence_rows"], "")
    check("exact_paper_delta", inverse == old_paper, "removing authorized additions restores v16")
    check("parameter_and_candidates_exact", all(value in section for value in [f"{production['parameter_count']:,}-parameter", f"{production['candidate_count']} unique legal candidates", f"{production['budget_allowed']} candidates and hard-masks {production['budget_masked']}"]), "architecture and state counts visible")
    check("loss_metrics_exact", all(value in section for value in [f"{production['initial_eval_loss']:.9f} to {production['final_eval_loss']:.9f}", f"{production['initial_unmasked_mse']:.9f} to {production['final_unmasked_mse']:.9f}"]), "teacher loss and MSE exact")
    check("kernel_metrics_exact", all(value in section for value in [f"{production['probability_sum']:.1f}", f"{production['masked_probability']:.1f}", f"{production['kernel_gradient_max_abs']:.6e}"]), "normalization, mask and gradient visible")
    check("zero_independent_errors", all(value == 0.0 for value in independent["array_abs_errors"].values()) and "zero error" in section, independent["array_abs_errors"])
    check("bitwise_retrain_visible", independent["tensor_bitwise_equal"] and independent["array_bitwise_equal"] and independent["history_numeric_equal"] and "Checkpoint bytes" in section and "deterministic numeric history" in section, "bitwise state and numeric history")
    check("verification_counts_visible", all(value in section for value in ["14/14 checks", f"{independent['checks_passed']}/{independent['checks_total']}", f"{finalization['checks_passed']}/{finalization['checks_total']}"]), "all counts visible")
    check("unit_failure_history_visible", "6 failed" in args.initial_failure.read_text() and "1 failed" in args.second_failure.read_text() and "failed 6 tests" in section and "failed 1 test" in section, "unit failures retained")
    first = json.loads(args.independent_initial_failure.read_text()); second = json.loads(args.independent_second_failure.read_text())
    check("independent_failure_history_visible", first["checks_passed"] == 24 and second["checks_passed"] == 25 and "24/27 and 25/27" in section, "independent failures retained")
    check("bounded_scope_visible", "synthetic neural contract and CUDA backward smoke" in section and "not biological mechanism validation" in section and "RK-G1 passage" in section and "full-generator training" in section, "scientific boundary visible")
    sources = {"rk11_protocol": args.protocol, "rk11_production": args.production, "rk11_retrain": args.retrain, "rk11_independent": args.independent, "rk11_finalization": args.finalization, "rk11_unit_tests": args.unit_test_log, "rk11_initial_failure": args.initial_failure, "rk11_second_failure": args.second_failure, "rk11_independent_initial_failure": args.independent_initial_failure, "rk11_independent_second_failure": args.independent_second_failure, "rk11_development": args.development}
    check("evidence_hashes", all(audit["source_sha256"][key] == sha(path) == update["evidence_sha256"][key] for key, path in sources.items()), "eleven RK-11 source hashes")
    check("evidence_rows", all(sha(path) in update["evidence_rows"] and sha(path) in paper for path in sources.values()), "all evidence hashes in paper")
    check("audit_schema", audit["schema_version"] == "a8-rk-paper-sync-v17", "schema advanced to v17")
    check("generated_sections_delta", audit["generated_sections"][:-2] == old_audit["generated_sections"] and audit["generated_sections"][-2:] == ["6.13 RK-11 minimal neural legal-kernel synthetic CUDA contract", "8.1 RK-11 synthetic neural evidence anchors"], "exactly two records appended")
    check("old_source_hashes_unchanged", all(audit["source_sha256"][key] == value for key, value in old_audit["source_sha256"].items()), "pre-v17 source hashes unchanged")
    check("old_source_paths_unchanged", all(audit["source_paths"][key] == value for key, value in old_audit["source_paths"].items()), "pre-v17 source paths unchanged")
    check("old_scientific_scope_unchanged", all(audit["scientific_scope"][key] == value for key, value in old_audit["scientific_scope"].items()), "pre-v17 scientific boundaries unchanged")
    check("pending_preserved", audit["pending_preserved"] == old_audit["pending_preserved"] and "[Pending. Retrospective held-out measurements first; prospective design–build–test–learn results only when actually completed.]" in paper, "pending work retained")
    snapshot = update["snapshot"]
    check("snapshot_integrity", sha(Path(snapshot["paper"])) == snapshot["paper_sha256"] == update["input_paper_sha256"] and sha(Path(snapshot["audit"])) == snapshot["audit_sha256"] == update["input_audit_sha256"] and sha(Path(snapshot["a7"])) == snapshot["a7_sha256"], "v16 snapshot verified")
    check("non_submittable_retained", "non-submittable working manuscript" in paper and audit["scientific_scope"]["submittable"] is False, "working manuscript only")
    check("authorization_unchanged", all(value is False for value in update["scientific_scope_unchanged"].values()) and "RK-G1" in finalization["not_closed"] and "SOTA" in finalization["not_closed"], "no gate or SOTA change")
    check("unit_tests_finalized", "10 passed" in args.unit_test_log.read_text(), "final unit-test log present")
    check("development_complete", json.loads(args.development.read_text())["status"] == "PASS_MINIMAL_NEURAL_SYNTHETIC_CUDA_CONTRACT", "development smoke retained")

    result = {"schema": "a8-rk11-minimal-neural-paper-verification-v17", "paper_sha256": sha(args.paper), "audit_sha256": sha(args.audit), "a7_sha256": sha(args.a7), "checks": checks, "checks_passed": sum(row["pass"] for row in checks), "checks_total": len(checks), "all_pass": all(row["pass"] for row in checks), "status": "PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE" if all(row["pass"] for row in checks) else "FAIL", "paper_update_module_imported": False}
    if args.report.exists():
        raise FileExistsError(f"Refusing to overwrite: {args.report}")
    temporary = args.report.with_name(args.report.name + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.report)
    print(json.dumps({"all_pass": result["all_pass"], "checks": f"{result['checks_passed']}/{result['checks_total']}", "paper_sha256": result["paper_sha256"]}))
    if not result["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
