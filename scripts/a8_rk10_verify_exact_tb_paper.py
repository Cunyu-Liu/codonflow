#!/usr/bin/env python3
"""Independently verify the exact A8 v15 -> v16 RK10-only manuscript delta."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for name in ("v15-paper", "v15-audit", "a7", "paper", "audit", "update-report", "protocol", "production", "retrain", "independent", "finalization", "unit-test-log", "initial-failure", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    update = json.loads(args.update_report.read_text())
    old_paper = args.v15_paper.read_text()
    old_audit = json.loads(args.v15_audit.read_text())
    paper = args.paper.read_text()
    audit = json.loads(args.audit.read_text())
    production = json.loads(args.production.read_text())
    retrain = json.loads(args.retrain.read_text())
    independent = json.loads(args.independent.read_text())
    finalization = json.loads(args.finalization.read_text())
    checks = []

    def check(name, condition, detail):
        checks.append({"id": name, "pass": bool(condition), "detail": detail})

    check("v15_paper_gate", sha(args.v15_paper) == update["input_paper_sha256"], "snapshot matches update input")
    check("v15_audit_gate", sha(args.v15_audit) == update["input_audit_sha256"] and old_audit["schema_version"] == "a8-rk-paper-sync-v15", "v15 audit matched")
    check("paper_output_hash", sha(args.paper) == update["output_paper_sha256"] == audit["output_sha256"], "v16 paper hash agrees")
    check("audit_output_hash", sha(args.audit) == update["output_audit_sha256"], "v16 audit hash matched")
    check("a7_unchanged", sha(args.a7) == update["a7_sha256"] == "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423", "A7 unchanged")
    check("production_complete", production["status"] == "PASS" and production["checks_passed"] == production["checks_total"], f"{production['checks_passed']}/{production['checks_total']}")
    check("retrain_complete", retrain["status"] == "PASS" and retrain["checks_passed"] == retrain["checks_total"], f"{retrain['checks_passed']}/{retrain['checks_total']}")
    check("independent_complete", independent["status"] == "PASS" and independent["checks_passed"] == independent["checks_total"] and independent["production_driver_imported"] is False, f"{independent['checks_passed']}/{independent['checks_total']}")
    check("finalization_complete", finalization["status"] == "PASS_COMPLETE_WITH_INDEPENDENT_RETRAIN_AND_ANALYTIC_ORACLE" and finalization["checks_passed"] == finalization["checks_total"], f"{finalization['checks_passed']}/{finalization['checks_total']}")
    section = update["section"]
    check("single_rk10_section", paper.count("### 6.12 Exact preference-conditioned trajectory-balance optimization") == 1 and paper.count(section) == 1, "one exact Section 6.12")
    inverse = paper.replace(section, "").replace(update["evidence_rows"], "")
    check("exact_paper_delta", inverse == old_paper, "removing only authorized section and evidence restores v15")
    metrics = independent["metrics"]
    check("geometry_exact", all(value in section for value in [f"{production['geometry']['states']:,} endpoint states", f"{production['geometry']['actions_per_state']} legal actions", f"{production['geometry']['paths']:,} enumerated paths"]), production["geometry"])
    check("metrics_exact", all(f"{metrics[key]:.3e}" in section for key in ["loss", "max_abs_path_residual", "max_abs_forward_target_error", "forward_target_kl", "max_abs_endpoint_reconstruction_error"]), metrics)
    weight_error = max(abs(a - b) for a, b in zip(production["theta"], production["target_weights"]))
    check("weight_error_exact", f"{weight_error:.3e}" in section, weight_error)
    oracle = independent["analytic_oracle"]
    check("analytic_oracle_exact", all(f"{oracle[key]:.3e}" in section for key in ["max_abs_residual", "max_abs_forward_target_error", "max_abs_backward_normalization_error"]), oracle)
    check("bitwise_retrain_visible", finalization["theta_bitwise_equal"] and finalization["backward_logits_bitwise_equal"] and "bitwise-identical" in section, "both tensors bitwise equal")
    check("verification_counts_visible", all(value in section for value in [f"{independent['checks_passed']}/{independent['checks_total']} checks", f"{finalization['checks_passed']}/{finalization['checks_total']}", "10 unit tests"]), "all counts visible")
    failure_text = args.initial_failure.read_text()
    check("failure_history_visible", "2 failed" in failure_text and "8 passed" in failure_text and "failed 2 of 10 tests" in section, "initial failure retained")
    check("bounded_scope_visible", "exact synthetic trajectory-balance optimization check" in section and "not biological reward learning" in section and "RK-G1 closure" in section, "scientific boundary visible")
    sources = {"rk10_protocol": args.protocol, "rk10_production": args.production, "rk10_retrain": args.retrain, "rk10_independent": args.independent, "rk10_finalization": args.finalization, "rk10_unit_tests": args.unit_test_log, "rk10_initial_failure": args.initial_failure}
    check("evidence_hashes", all(audit["source_sha256"][key] == sha(path) == update["evidence_sha256"][key] for key, path in sources.items()), "seven RK10 source hashes")
    check("evidence_rows", all(sha(path) in update["evidence_rows"] and sha(path) in paper for path in sources.values()), "all evidence hashes in paper")
    check("audit_schema", audit["schema_version"] == "a8-rk-paper-sync-v16", "schema advanced to v16")
    check("generated_sections_delta", audit["generated_sections"][:-2] == old_audit["generated_sections"] and audit["generated_sections"][-2:] == ["6.12 RK10 exact preference-conditioned trajectory-balance optimization", "8.1 RK10 exact trajectory-balance evidence anchors"], "exactly two records appended")
    check("old_source_hashes_unchanged", all(audit["source_sha256"][key] == value for key, value in old_audit["source_sha256"].items()), "pre-v16 source hashes unchanged")
    check("old_source_paths_unchanged", all(audit["source_paths"][key] == value for key, value in old_audit["source_paths"].items()), "pre-v16 source paths unchanged")
    check("old_scientific_scope_unchanged", all(audit["scientific_scope"][key] == value for key, value in old_audit["scientific_scope"].items()), "pre-v16 scientific boundaries unchanged")
    check("pending_preserved", audit["pending_preserved"] == old_audit["pending_preserved"] and "[Pending. Retrospective held-out measurements first; prospective design–build–test–learn results only when actually completed.]" in paper, "pending work retained")
    snapshot = update["snapshot"]
    check("snapshot_integrity", sha(Path(snapshot["paper"])) == snapshot["paper_sha256"] == update["input_paper_sha256"] and sha(Path(snapshot["audit"])) == snapshot["audit_sha256"] == update["input_audit_sha256"] and sha(Path(snapshot["a7"])) == snapshot["a7_sha256"], "v15 snapshot verified")
    check("non_submittable_retained", "non-submittable working manuscript" in paper and audit["scientific_scope"]["submittable"] is False, "working manuscript only")
    check("authorization_unchanged", all(value is False for value in update["scientific_scope_unchanged"].values()) and not finalization["rk_g1_gate_modified"] and not finalization["expensive_generation_authorized"] and not finalization["sota_claimed"], "no gate or SOTA change")
    check("unit_tests_finalized", "10 passed" in args.unit_test_log.read_text(), "final unit-test log present")

    result = {
        "schema": "a8-rk10-exact-tb-paper-verification-v16",
        "paper_sha256": sha(args.paper), "audit_sha256": sha(args.audit), "a7_sha256": sha(args.a7),
        "checks": checks, "checks_passed": sum(row["pass"] for row in checks), "checks_total": len(checks),
        "all_pass": all(row["pass"] for row in checks),
        "status": "PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE" if all(row["pass"] for row in checks) else "FAIL",
        "paper_update_module_imported": False,
    }
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
