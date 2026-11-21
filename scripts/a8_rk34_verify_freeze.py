#!/usr/bin/env python3
"""Independent RK34 freeze audit; never reads expression or fits a model."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from a8_rk34_run_start_context import ARMS, COMPARISONS, TEST_ORDER, context_sequences

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--test-log", type=Path, default=Path("audits/20261121/RK34/rk34_synthetic_tests_v1.log"))
    parser.add_argument("--expected-test-count", type=int, default=8)
    parser.add_argument("--production-result", type=Path, default=Path("audits/20261121/RK34/rk34_start_context_result_v1.json"))
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    protocol = json.loads(args.protocol.read_text())
    checks = []

    def check(name, ok, details=None):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    check("frozen_status", protocol["status"] == "FROZEN_BEFORE_RK34_EXPRESSION_ASSOCIATION_OR_MODEL_FIT")
    check("no_rk34_expression_or_fit_before_freeze", protocol["expression_association_or_model_fit_performed_before_freeze"] is False)
    check("retrospective_boundary", protocol["analysis_type"] == "retrospective_outcome_known_coverage_followup_not_independent_confirmation")
    check("preparation_commit", subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == protocol["preparation_commit"])
    tracked_dirty = subprocess.run(["git", "diff", "--quiet"], cwd=ROOT).returncode != 0
    check("no_tracked_dirty_edits", not tracked_dirty, {"tracked_dirty": tracked_dirty})
    for key, record in protocol["inputs"].items():
        path = Path(record["path"])
        if not path.is_absolute():
            path = ROOT / path
        check(f"input_{key}", path.is_file() and sha256(path) == record["sha256"], str(path))
    for key in ("production_script", "preflight_script"):
        path = ROOT / protocol["code"][key]
        check(f"code_{key}", sha256(path) == protocol["code"][f"{key}_sha256"], sha256(path))
    prereg = ROOT / protocol["preregistration"]["path"]
    check("preregistration_hash", sha256(prereg) == protocol["preregistration"]["sha256"])
    preflight_path = ROOT / protocol["inputs"]["preflight_report"]["path"]
    preflight = json.loads(preflight_path.read_text())
    check("label_free_preflight", preflight["status"] == "PASS_LABEL_FREE_START_CONTEXT_PREFLIGHT" and preflight["checks_passed"] == preflight["checks_total"] == 12)
    check("preflight_did_not_read_expression_or_fit", preflight["expression_columns_read"] is False and preflight["model_fit_performed"] is False)
    check("preflight_functional_untouched_not_read", preflight["functional_untouched_read"] is False)
    check("candidate_identity", preflight["candidate_csv_sha256"] == protocol["inputs"]["candidate_csv"]["sha256"])
    check("arms_match_implementation", protocol["factorial_contexts"]["arms"] == ARMS)
    check("families_match_implementation", protocol["comparisons"]["families"] == list(dict.fromkeys(spec["family"] for spec in COMPARISONS if spec["analysis"] == "primary")))
    check("test_count_and_order", len(TEST_ORDER) == len(set(TEST_ORDER)) == 40 and sum(x.startswith("primary__") for x in TEST_ORDER) == 20)
    check("fit_accounting", protocol["fit_accounting"]["new_model_fits"] == 700 and protocol["fit_accounting"]["reused_rk32_model_fits"] == 200 and protocol["fit_accounting"]["evaluated_model_fits"] == 900)
    contexts = context_sequences("ACGU" * 36, "ATG" + "C" * 717)
    check("matched_42nt_factorial", all(len(x) == 42 for x in contexts.values()) and contexts["exact_real"][4:] == contexts["start_only"][4:] and contexts["exact_real"][7:] == contexts["upstream_only"][7:] and contexts["start_only"][7:] == contexts["neither"][7:])
    check("confirmatory_dangles2", all(spec["dangles"] == "2" for spec in COMPARISONS if spec["analysis"] == "primary"))
    check("sensitivity_dangles0", all(spec["dangles"] == "0" for spec in COMPARISONS if spec["analysis"] == "sensitivity_d0"))
    check("sensitivity_cannot_upgrade", protocol["scientific_boundaries"]["sensitivity_can_upgrade_failed_primary"] is False)
    check("functional_and_generator_boundaries", not protocol["scientific_boundaries"]["functional_untouched_read"] and not protocol["scientific_boundaries"]["generator_training_authorized"])
    check("no_untouched_protein_sota_rkg1_claim", all(not protocol["scientific_boundaries"][key] for key in ("independent_untouched_confirmation", "protein_ood", "full_external_sota", "rk_g1_complete")))
    test_log_path = args.test_log if args.test_log.is_absolute() else ROOT / args.test_log
    test_log = test_log_path.read_text()
    check("synthetic_tests_pass", f"{args.expected_test_count} passed" in test_log, {"test_log": str(test_log_path), "expected_test_count": args.expected_test_count})
    result_path = args.production_result if args.production_result.is_absolute() else ROOT / args.production_result
    check("no_production_result_before_freeze", not result_path.exists(), str(result_path))
    payload = {
        "schema": "a8-rk34-freeze-verification-v1",
        "status": "PASS" if all(row["pass"] for row in checks) else "FAIL",
        "protocol": str(args.protocol), "protocol_sha256": sha256(args.protocol),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "checks": checks, "checks_passed": sum(row["pass"] for row in checks), "checks_total": len(checks),
        "expression_columns_read": False, "model_fit_performed": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2))
    if payload["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
