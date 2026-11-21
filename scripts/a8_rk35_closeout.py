#!/usr/bin/env python3
"""RK35 closeout: bind protocol/preflight/production/independent/reproduction/test
evidence by SHA and assert the full evidence chain before registration."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", type=Path, required=True)
    ap.add_argument("--preflight-report", type=Path, required=True)
    ap.add_argument("--production-summary", type=Path, required=True)
    ap.add_argument("--independent-report", type=Path, required=True)
    ap.add_argument("--reproduction-comparison", type=Path, required=True)
    ap.add_argument("--reproduction-summary", type=Path, required=True)
    ap.add_argument("--reproduction-independent", type=Path, required=True)
    ap.add_argument("--project-tests-json", type=Path, required=True)
    ap.add_argument("--rk35-tests-json", type=Path, required=True)
    ap.add_argument("--freeze-commit", required=True)
    ap.add_argument("--clean-commit", required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    checks = []

    def check(name, ok, details=None):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    protocol = json.loads(args.protocol.read_text())
    preflight = json.loads(args.preflight_report.read_text())
    production = json.loads(args.production_summary.read_text())
    independent = json.loads(args.independent_report.read_text())
    comparison = json.loads(args.reproduction_comparison.read_text())
    reproduction = json.loads(args.reproduction_summary.read_text())
    reproduction_independent = json.loads(args.reproduction_independent.read_text())
    project_tests = json.loads(args.project_tests_json.read_text())
    rk35_tests = json.loads(args.rk35_tests_json.read_text())

    check("protocol_frozen_status", protocol["status"] == "FROZEN_BEFORE_RK35_EXPRESSION_ASSOCIATION_OR_MODEL_FIT")
    check("preflight_pass_label_free", preflight["status"] == "PASS_LABEL_FREE_PREFLIGHT" and preflight["outcome_columns_read"] is False)
    check("production_protocol_binding", production["protocol_sha256"] == sha256(args.protocol))
    check("production_script_binding", production["analysis_script_sha256"] == protocol["code"]["production_script_sha256"])
    check("independent_pass", independent["status"] == "PASS", {"passed": independent["checks_passed"], "total": independent["checks_total"]})
    check("reproduction_comparison_pass", comparison["status"] == "PASS")
    check("reproduction_independent_pass", reproduction_independent["status"] == "PASS")
    check("conclusion_consistent", production["scientific_conclusion"] == independent["independent_conclusion"] == reproduction["scientific_conclusion"] == reproduction_independent["independent_conclusion"], production["scientific_conclusion"])
    check("consistency_gate_pass", production["consistency_gate"]["pass"] is True)
    check("fit_accounting", production["new_model_fits"] == 300 and production["reused_model_fits"] == 200 and production["evaluated_model_fits"] == 500)
    check("primary_family_8", len(production["primary_tests"]) == 8)
    check("gate_family_4", len(production["gate_tests"]) == 4)
    check("secondary_family_12", len(production["secondary_tests"]) == 12)
    check("functional_untouched", production["scientific_flags"]["functional_untouched_read"] is False)
    check("no_generator_authorization", production["scientific_flags"]["generator_training_authorized"] is False)
    check("rk_g1_not_complete", production["scientific_flags"]["RK_G1_complete"] is False)
    check("no_host_assay_claim", production["scientific_flags"]["host_assay_identified"] is False)
    check("project_tests_pass", project_tests["failed"] == 0 and project_tests["passed"] >= 429, {"passed": project_tests["passed"], "skipped": project_tests.get("skipped"), "failed": project_tests["failed"]})
    check("rk35_tests_pass", rk35_tests["failed"] == 0 and rk35_tests["passed"] >= 12, {"passed": rk35_tests["passed"], "failed": rk35_tests["failed"]})
    check("freeze_commit_recorded", len(args.freeze_commit) == 40)
    check("clean_commit_recorded", len(args.clean_commit) == 40)

    evidence = {}
    for label, path in (
        ("protocol", args.protocol), ("preflight_report", args.preflight_report),
        ("production_summary", args.production_summary), ("independent_report", args.independent_report),
        ("reproduction_comparison", args.reproduction_comparison), ("reproduction_summary", args.reproduction_summary),
        ("reproduction_independent", args.reproduction_independent),
        ("project_tests", args.project_tests_json), ("rk35_tests", args.rk35_tests_json),
    ):
        evidence[label] = {"path": str(path), "sha256": sha256(path)}
    report = {
        "schema": "a8-rk35-closeout-v1",
        "status": "PASS_RK35_CLOSEOUT" if all(c["pass"] for c in checks) else "FAIL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "freeze_commit": args.freeze_commit, "clean_reproduction_commit": args.clean_commit,
        "scientific_conclusion": production["scientific_conclusion"], "decision_code": production["decision_code"],
        "contrast_results": production["contrast_results"],
        "evidence": evidence,
        "checks_passed": sum(c["pass"] for c in checks), "checks_total": len(checks), "checks": checks,
    }
    atomic_json(args.report, report)
    print(json.dumps({k: v for k, v in report.items() if k not in ("checks", "evidence")}, indent=2))
    if report["status"] != "PASS_RK35_CLOSEOUT":
        print(json.dumps([c for c in checks if not c["pass"]], indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()