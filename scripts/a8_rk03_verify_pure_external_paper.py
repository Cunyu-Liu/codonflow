#!/usr/bin/env python3
"""Independent manuscript-v32 insertion, scientific-content and rollback audit."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

BEFORE_SHA = "9c0b453d5b3fbc0e2672dc776fa718d13cc50dcc072ab654aafdfcbe3e0a3c1a"
BASELINE_COMMIT = "b95e1244537a23c95cdda986cb60e343cfd7e4da"


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="/home/codonflow-a8-rk")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    paper = root / "paper/CodonFlow_preprint_A8.md"
    section_path = root / "paper/a8_rk03_pure_external_rcs_section_v32.md"
    update_path = root / "paper/a8_rk03_pure_external_rcs_paper_update_v32.json"
    preparation_path = root / "paper/a8_rk03_pure_external_rcs_paper_update_preparation_v32.json"
    update = json.loads(update_path.read_text())
    preparation = json.loads(preparation_path.read_text())
    production = json.loads((root / "audits/20261120/RK03/mage_pure_external_nested_cv_v1.json").read_text())
    independent = json.loads((root / "audits/20261120/RK03/mage_pure_external_nested_cv_independent_v1.json").read_text())
    finalization = json.loads((root / "audits/20261120/RK03/mage_pure_external_nested_cv_finalization_v1.json").read_text())
    old = json.loads((root / "audits/20261119/RK03/mage_development_nested_cv_v2.json").read_text())
    current_bytes = paper.read_bytes()
    current = current_bytes.decode()
    numeric_text = current.replace("−", "-")
    baseline_bytes = subprocess.check_output(["git", "show", f"{BASELINE_COMMIT}:paper/CodonFlow_preprint_A8.md"], cwd=root)
    baseline = baseline_bytes.decode()
    checks = []

    def check(name: str, condition: bool, detail: object = None) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    def numeric_literal(name: str, value: float, literal: str | None = None) -> None:
        token = literal if literal is not None else str(value)
        check(name, token in numeric_text, token)

    check("baseline_commit_v31_sha", sha_bytes(baseline_bytes) == BEFORE_SHA, sha_bytes(baseline_bytes))
    check("update_binds_v31", update["before_sha256"] == BEFORE_SHA)
    check("preparation_binds_v31", preparation["before_sha256"] == BEFORE_SHA and preparation["exact_rollback_verified_before_write"] is True)
    check("current_matches_update_after", sha_bytes(current_bytes) == update["after_sha256"], sha_bytes(current_bytes))
    check("section_source_matches_update", sha(section_path) == update["section_sha256"])
    check("one_section_6_28", current.count("### 6.28 Pure external-RCS comparator on reused MAGE development folds") == 1)
    check("section_precedes_discussion", current.index("### 6.28 ") < current.index("## 7. Discussion"))
    check("previous_section_retained", current.count("### 6.27 Development-selected mechanism-channel screen") == 1)
    check("working_manuscript_status_retained", "Status: A8-RK working manuscript — not for submission." in current)
    check("non_submittable_close_retained", "non-submittable working manuscript" in current)

    section_source = section_path.read_text().strip()
    section = section_source.replace("# Pure external-RCS comparator on reused MAGE development folds", "### 6.28 Pure external-RCS comparator on reused MAGE development folds", 1)
    section_insert = "\n" + section + "\n\n## 7. Discussion"
    check("section_insert_hash", sha_bytes(section_insert.encode()) == update["section_insert_sha256"])
    status_path = root / "paper/a8_rk03_pure_external_rcs_workflow_status_v32.json"
    draft_check_path = root / "paper/a8_rk03_pure_external_rcs_draft_check_v32.json"
    prepare_check_path = root / "paper/a8_rk03_pure_external_rcs_prepare_check_v32.json"
    deliver_failure_path = root / "paper/a8_rk03_pure_external_rcs_deliver_failure_v32.log"
    correction_path = root / "paper/a8_rk03_pure_external_rcs_delivery_correction_v32.json"
    anchor_files = [
        ("RK03 pure-external-RCS frozen protocol", root / "configs/a8_rk03_mage_pure_external_nested_cv_protocol_v1.json"),
        ("RK03 pure-external-RCS preparation", root / "audits/20261120/RK03/mage_pure_external_nested_cv_preparation_v1.json"),
        ("RK03 pure-external-RCS production", root / "audits/20261120/RK03/mage_pure_external_nested_cv_v1.json"),
        ("RK03 pure-external-RCS independent verification", root / "audits/20261120/RK03/mage_pure_external_nested_cv_independent_v1.json"),
        ("RK03 pure-external-RCS finalization", root / "audits/20261120/RK03/mage_pure_external_nested_cv_finalization_v1.json"),
        ("RK03 pure-external-RCS 10-test log", root / "audits/20261120/RK03/mage_pure_external_nested_cv_tests_v1.log"),
        ("RK03 pure-external-RCS manuscript source section", section_path),
        ("RK03 pure-external-RCS manuscript prepare check", prepare_check_path),
        ("RK03 pure-external-RCS manuscript draft check", draft_check_path),
        ("RK03 pure-external-RCS manuscript writing status", status_path),
        ("RK03 pure-external-RCS retained delivery failure", deliver_failure_path),
        ("RK03 pure-external-RCS delivery correction", correction_path),
    ]
    anchor_rows = "\n".join(f"| {name} | `{sha(path)}` |" for name, path in anchor_files)
    check("anchor_rows_hash", sha_bytes(anchor_rows.encode()) == update["anchor_rows_sha256"])
    for name, path in anchor_files:
        row = f"| {name} | `{sha(path)}` |"
        check(f"evidence_anchor_{name}", current.count(row) == 1)
    anchor_marker = "\n\nA7 is retained as the prior manuscript snapshot."
    anchor_insert = "\n\n" + anchor_rows + "\n\nA7 is retained as the prior manuscript snapshot."
    expected = baseline.replace("## 7. Discussion", section_insert, 1).replace(anchor_marker, anchor_insert, 1)
    check("exact_reconstruction_from_v31", expected == current)
    restored = current.replace(section_insert, "## 7. Discussion", 1).replace(anchor_insert, anchor_marker, 1)
    check("exact_rollback_to_v31", restored == baseline and sha_bytes(restored.encode()) == BEFORE_SHA)
    check("references_unchanged", current[current.index("## 9. References"):] == baseline[baseline.index("## 9. References"):])
    check("abstract_unchanged", current[current.index("## Abstract"):current.index("## 1. Introduction")] == baseline[baseline.index("## Abstract"):baseline.index("## 1. Introduction")])

    for arm, values in production["primary_models"].items():
        for key in ("rmse", "mae", "spearman"):
            numeric_literal(f"primary_metric_{arm}_{key}", values[key])
    for comparison_id, values in production["primary_comparisons"].items():
        for key in ("delta_spearman", "delta_rmse", "holm_p_spearman", "holm_p_rmse"):
            numeric_literal(f"comparison_{comparison_id}_{key}", values[key])
        for endpoint in ("delta_spearman_ci95", "delta_rmse_ci95"):
            for i, value in enumerate(values[endpoint]):
                numeric_literal(f"comparison_{comparison_id}_{endpoint}_{i}", value)
    old_contrast = old["primary_comparisons"]["full_mechanism_minus_intrinsic"]
    numeric_literal("old_full_intrinsic_spearman", old_contrast["delta_spearman"])
    numeric_literal("old_full_intrinsic_rmse", old_contrast["delta_rmse"], "0.00009492841319608952")
    check("old_full_intrinsic_decimal_exact", float("0.00009492841319608952") == old_contrast["delta_rmse"])
    for endpoint in ("delta_spearman_ci95", "delta_rmse_ci95"):
        for i, value in enumerate(old_contrast[endpoint]):
            numeric_literal(f"old_full_intrinsic_{endpoint}_{i}", value)
    check("old_holm_one_reported", current.count("both Holm-adjusted *p* values were 1") == 1)
    check("pure_replacement_negative_statement", "Pure external replacement was therefore not supported." in current)
    check("pure_significantly_worse_statement", "performed significantly worse than intrinsic on both primary endpoints" in current)
    check("pure_sensitivity_adverse_statement", "adverse point-estimate directions on both sensitivity seeds" in current)
    check("full_pure_not_full_intrinsic", "comparisons against this weak pure predictor do not establish an increment over intrinsic" in current)
    check("naming_ambiguity_closed_without_mechanism_rescue", "closes the naming and feature-composition ambiguity without rescuing the prior non-significant mechanism comparison" in current)
    check("pure_feature_composition_explicit", "only variant RCS, its difference from the matched wild-type control, and the absolute difference" in current)
    check("intrinsic_features_excluded_explicit", "no position, position interaction, codon or amino-acid identity, GC, local-MFE, or other intrinsic feature" in current)
    check("development_reuse_explicit", "131-construct train-plus-development artifact" in current and "development diagnostics, not independent test results" in current)
    check("test_33_excluded_explicit", "33 test constructs were excluded from feature selection, fitting, and evaluation" in current)
    check("nested_cv_contract_explicit", "five outer folds, four inner folds, three outer seeds, and six-value regularization grid" in current)
    check("fit_count_explicit", "375 new fits" in current)
    check("inference_contract_explicit", "20,000 construct-bootstrap replicates" in current and "20,000 within-construct prediction-swap permutations" in current and "Holm correction covered the six tests" in current)
    check("independent_174_reported", "**174/174 checks**" in current and independent["checks_passed"] == 174 and independent["checks_failed"] == 0)
    check("independent_zero_delta_reported", "maximum numeric discrepancy 0" in current and independent["max_numeric_delta"] == 0.0)
    check("finalization_43_reported", "**43/43 checks**" in current and finalization["checks_passed"] == 43 and finalization["checks_failed"] == 0)
    check("no_go_retained", "The original development no-go remains unchanged." in current)
    check("no_test_or_functional_claim", "No test or functional-untouched evaluation was performed" in current)
    check("rk_g1_remains_false", "RK-G1 remains false" in current and production["rk_g1_pass"] is False)
    check("generator_unauthorized", "expensive generator training remains unauthorized" in current and production["generator_training_authorized"] is False)
    check("no_overclaim", "no protein-OOD, causal-mechanism, complete-SOTA, or submittable-manuscript claim is made" in current)

    status = json.loads(status_path.read_text())
    draft_check = json.loads(draft_check_path.read_text())
    prepare_check = json.loads(prepare_check_path.read_text())
    correction = json.loads(correction_path.read_text())
    check("workflow_status_pass", status["status"] == "PASS" and status["lark"] == "skipped_by_user")
    check("workflow_prepare_pass", prepare_check["status"] == "pass")
    check("workflow_draft_pass", draft_check["status"] == "pass" and draft_check["result"]["word_count"] == 476)
    check("workflow_input_binds_section", draft_check["result"]["input_sha256"] == sha(section_path))
    check("delivery_failure_retained", "finish_with_status: command not found" in deliver_failure_path.read_text())
    check("delivery_correction_bounded", correction["status"] == "PASS_MARKDOWN_WITH_RETAINED_DELIVERY_TOOL_FAILURE" and correction["scientific_content_changed_by_correction"] is False and correction["lark_document_created_or_modified"] is False)
    check("update_pending_verification_before_this_report", update["status"] == "PASS_MANUSCRIPT_UPDATED_PENDING_INDEPENDENT_VERIFICATION")
    check("science_commit_bound", update["science_commit"] == BASELINE_COMMIT and preparation["science_commit"] == BASELINE_COMMIT)

    passed = sum(row["pass"] for row in checks)
    failed = len(checks) - passed
    report = {
        "schema": "a8-rk03-pure-external-paper-verification-v32",
        "status": "PASS_PURE_EXTERNAL_PAPER_V32" if failed == 0 else "FAIL_PURE_EXTERNAL_PAPER_V32",
        "overall_pass": failed == 0,
        "checks_total": len(checks),
        "checks_passed": passed,
        "checks_failed": failed,
        "baseline_commit": BASELINE_COMMIT,
        "before_sha256": BEFORE_SHA,
        "after_sha256": sha_bytes(current_bytes),
        "update_report_sha256": sha(update_path),
        "preparation_report_sha256": sha(preparation_path),
        "section_sha256": sha(section_path),
        "exact_rollback_to_v31": True,
        "references_changed": False,
        "scientific_content_source": "audits/20261120/RK03/mage_pure_external_nested_cv_v1.json plus independent and finalization reports",
        "pure_external_replacement_supported": False,
        "mechanism_increment_pass": False,
        "rk_g1_pass": False,
        "generator_training_authorized": False,
        "submittable_manuscript": False,
        "checks": checks,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "before": BEFORE_SHA, "after": report["after_sha256"]}, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
