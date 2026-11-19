#!/usr/bin/env python3
"""Independently verify the exact A8 v13 -> v14 RK09-only manuscript delta."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--v13-paper", type=Path, required=True)
    parser.add_argument("--v13-audit", type=Path, required=True)
    parser.add_argument("--a7", type=Path, required=True)
    parser.add_argument("--paper", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--update-report", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--finalization", type=Path, required=True)
    parser.add_argument("--initial-production-failure", type=Path, required=True)
    parser.add_argument("--initial-independent-failure", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    update = json.loads(args.update_report.read_text())
    old_paper = args.v13_paper.read_text()
    old_audit = json.loads(args.v13_audit.read_text())
    paper = args.paper.read_text()
    audit = json.loads(args.audit.read_text())
    production = json.loads(args.production.read_text())
    independent = json.loads(args.independent.read_text())
    finalization = json.loads(args.finalization.read_text())
    checks = []

    def check(name, condition, detail):
        checks.append({"id": name, "pass": bool(condition), "detail": detail})

    check("v13_paper_gate", sha(args.v13_paper) == update["input_paper_sha256"] == "cd2c74ef1b093bb0ce5d3bfce5d0bb26939367c6d0fa5269361096c7f5aa8f0d", "actual v13 paper hash matched")
    check("v13_audit_gate", sha(args.v13_audit) == update["input_audit_sha256"] == "4b562b630bb0344a0b862fcdb03894f96ac4c533bf2aaa1cc1d5a259f0d911ef", "actual v13 audit hash matched")
    check("paper_output_hash", sha(args.paper) == update["output_paper_sha256"] == audit["output_sha256"], "v14 paper hash agrees everywhere")
    check("audit_output_hash", sha(args.audit) == update["output_audit_sha256"], "v14 audit hash matched")
    check("a7_unchanged", sha(args.a7) == update["a7_sha256"] == old_audit["template_sha256"], "A7 remains byte-identical")
    check("rk09_production_complete", production["all_pass"] and production["checks_passed"] == production["checks_total"] == 22, "22/22 production")
    check("rk09_independent_complete", independent["all_pass"] and independent["checks_passed"] == independent["checks_total"] == 16, "16/16 independent")
    check("rk09_finalization_complete", finalization["all_pass"] and finalization["checks_passed"] == finalization["checks_total"] == 14, "14/14 finalization")
    section = update["section"]
    check("single_rk09_section", paper.count("### 6.11 Minimal CodonFlow-RK mathematical kernel") == 1 and paper.count(section) == 1, "one exact Section 6.11 insertion")
    inverse = paper.replace(section, "").replace(update["evidence_rows"], "")
    check("exact_paper_delta", inverse == old_paper, "removing only the authorized section and evidence rows restores v13 byte-for-byte")
    check("state_counts_exact", f"{production['counts']['kernel_valid_states']:,} valid states" in section and f"{production['counts']['two_step_reachable_states']:,} states reachable" in section, "valid and reachable state counts rendered from production")
    check("naive_tv_exact", f"{production['metrics']['naive_two_step_total_variation_vs_uniform']:.12f}" in section, "naive random-walk TV rendered exactly")
    telescope = production["metrics"]["telescope"]
    check("path_counts_exact", f"{telescope['path_count']:,} paths" in section and f"{telescope['endpoint_count']:,} endpoints" in section, "14,641 paths and 3,721 endpoints present")
    check("telescope_errors_exact", all(f"{telescope[key]:.3e}" in section for key in ["max_backward_normalization_error", "max_telescope_error", "max_endpoint_reconstruction_error"]), "all three numerical errors present")
    check("event_mean_corrected", "1/(kappa+1)" in section and "not `kappa/(kappa+1)`" in section, "correct analytic event-time mean and retained correction")
    check("failure_history_visible", "19/22" in section and "15/16" in section and not json.loads(args.initial_production_failure.read_text())["all_pass"] and not json.loads(args.initial_independent_failure.read_text())["all_pass"], "both initial failures retained and cited")
    check("verification_counts_visible", all(value in section for value in ["22/22", "16/16", "14/14", "10 unit tests"]), "all verification counts present")
    check("bounded_scope_visible", "mathematical-kernel verification only" in section and "not trained CodonFlow-RK" in section and "RK-G1 closure" in section, "no training/function/generation/gate claim")
    sources = {
        "rk09_protocol": args.protocol,
        "rk09_production": args.production,
        "rk09_independent": args.independent,
        "rk09_finalization": args.finalization,
        "rk09_initial_production_failure": args.initial_production_failure,
        "rk09_initial_independent_failure": args.initial_independent_failure,
    }
    check("evidence_hashes", all(audit["source_sha256"][key] == sha(path) == update["evidence_sha256"][key] for key, path in sources.items()), "six RK09 source hashes independently recomputed")
    check("evidence_rows", all(sha(path) in update["evidence_rows"] and sha(path) in paper for path in sources.values()), "all six evidence hashes appear in the paper")
    check("audit_schema", audit["schema_version"] == "a8-rk-paper-sync-v14", "schema advanced only to v14")
    check("generated_sections_delta", audit["generated_sections"][:-2] == old_audit["generated_sections"] and audit["generated_sections"][-2:] == ["6.11 RK09 minimal CodonFlow-RK mathematical kernel", "8.1 RK09 mathematical-kernel evidence anchors"], "exactly two generated-section records appended")
    check("old_source_hashes_unchanged", all(audit["source_sha256"][key] == value for key, value in old_audit["source_sha256"].items()), "every pre-v14 source hash unchanged")
    check("old_source_paths_unchanged", all(audit["source_paths"][key] == value for key, value in old_audit["source_paths"].items()), "every pre-v14 source path unchanged")
    check("old_scientific_scope_unchanged", all(audit["scientific_scope"][key] == value for key, value in old_audit["scientific_scope"].items()), "every pre-v14 scientific boundary unchanged")
    check("pending_preserved", audit["pending_preserved"] == old_audit["pending_preserved"] and "[Pending. Retrospective held-out measurements first; prospective design–build–test–learn results only when actually completed.]" in paper, "pending functional and other scientific work retained")
    snapshot = update["snapshot"]
    check("snapshot_integrity", sha(Path(snapshot["paper"])) == snapshot["paper_sha256"] == update["input_paper_sha256"] and sha(Path(snapshot["audit"])) == snapshot["audit_sha256"] == update["input_audit_sha256"] and sha(Path(snapshot["a7"])) == snapshot["a7_sha256"], "v13 paper, audit and A7 snapshot hashes verified")
    check("non_submittable_retained", "non-submittable working manuscript" in paper and audit["scientific_scope"]["submittable"] is False, "manuscript remains non-submittable")
    check("authorization_unchanged", all(value is False for value in update["scientific_scope_unchanged"].values()) and not finalization["rk_g1_gate_modified"] and not finalization["expensive_generation_authorized"], "no model, function, generation, gate, SOTA or expensive-training authorization")
    check("unit_tests_finalized", "10 unittest tests passed" in next(row["detail"] for row in finalization["checks"] if row["id"] == "unit_tests"), "10-test evidence is present in finalization")

    result = {
        "schema": "a8-rk09-minimal-paper-verification-v14",
        "paper_sha256": sha(args.paper),
        "audit_sha256": sha(args.audit),
        "a7_sha256": sha(args.a7),
        "checks": checks,
        "checks_passed": sum(row["pass"] for row in checks),
        "checks_total": len(checks),
        "all_pass": all(row["pass"] for row in checks),
        "status": "PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE" if all(row["pass"] for row in checks) else "FAIL",
    }
    temporary = args.report.with_name(args.report.name + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.report)
    print(json.dumps({"all_pass": result["all_pass"], "checks": f"{result['checks_passed']}/{result['checks_total']}", "paper_sha256": result["paper_sha256"]}))
    if not result["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
