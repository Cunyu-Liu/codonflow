#!/usr/bin/env python3
"""Independent manuscript-v33 insertion, scientific-content and rollback audit."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

BEFORE_SHA = "6c3d2a0329a46ca70d4dd782748a06c60fbecbf91fd8d8fe5d7ea1c42e2b73f0"
BASELINE_COMMIT = "d5959f73ac4f4812d614eee6d6c04d320dff38fc"
SCIENCE_COMMIT = "7f38432203d3af0b2b6c0bb8d29138684f8ad953"
TITLE = "A train-only constant relative-position field outperforms both velocity predictors on Subtelny14"


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
    section_path = root / "paper/a8_rk08_constant_velocity_field_section_v33.md"
    update_path = root / "paper/a8_rk08_constant_velocity_field_paper_update_v33.json"
    preparation_path = root / "paper/a8_rk08_constant_velocity_field_paper_update_preparation_v33.json"
    update = json.loads(update_path.read_text())
    preparation = json.loads(preparation_path.read_text())
    production = json.loads((root / "audits/20261120/RK08/constant_velocity_field_v1.json").read_text())
    independent = json.loads((root / "audits/20261120/RK08/constant_velocity_field_independent_v1.json").read_text())
    finalization = json.loads((root / "audits/20261120/RK08/constant_velocity_field_finalization_v1.json").read_text())
    postpush = json.loads((root / "audits/20261120/RK08/constant_velocity_field_postpush_independent_v1.json").read_text())
    current_bytes = paper.read_bytes()
    current = current_bytes.decode()
    baseline_bytes = subprocess.check_output(["git", "show", f"{BASELINE_COMMIT}:paper/CodonFlow_preprint_A8.md"], cwd=root)
    baseline = baseline_bytes.decode()
    checks = []

    def check(name: str, condition: bool, detail: object = None) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("baseline_commit_v32_sha", sha_bytes(baseline_bytes) == BEFORE_SHA, sha_bytes(baseline_bytes))
    check("update_binds_v32", update["before_sha256"] == BEFORE_SHA)
    check("preparation_binds_v32", preparation["before_sha256"] == BEFORE_SHA and preparation["exact_rollback_verified_before_write"] is True)
    check("current_matches_update_after", sha_bytes(current_bytes) == update["after_sha256"], sha_bytes(current_bytes))
    check("section_source_matches_update", sha(section_path) == update["section_sha256"])
    check("one_section_6_29", current.count(f"### 6.29 {TITLE}") == 1)
    check("section_precedes_discussion", current.index("### 6.29 ") < current.index("## 7. Discussion"))
    check("previous_section_retained", current.count("### 6.28 Pure external-RCS comparator on reused MAGE development folds") == 1)
    check("working_manuscript_status_retained", "Status: A8-RK working manuscript — not for submission." in current)
    check("non_submittable_close_retained", "non-submittable working manuscript" in current)

    section_source = section_path.read_text().strip()
    section = section_source.replace(f"# {TITLE}", f"### 6.29 {TITLE}", 1)
    section_numeric = section.replace("−", "-")
    section_insert = "\n" + section + "\n\n## 7. Discussion"
    check("section_insert_hash", sha_bytes(section_insert.encode()) == update["section_insert_sha256"])

    def numeric_literal(name: str, value: float, literal: str | None = None) -> None:
        token = literal if literal is not None else str(value)
        check(name, token in section_numeric, token)

    status_path = root / "paper/a8_rk08_constant_velocity_field_workflow_status_v33.json"
    draft_check_path = root / "paper/a8_rk08_constant_velocity_field_draft_check_v33.json"
    prepare_check_path = root / "paper/a8_rk08_constant_velocity_field_prepare_check_v33.json"
    deliver_failure_path = root / "paper/a8_rk08_constant_velocity_field_deliver_failure_v33.log"
    correction_path = root / "paper/a8_rk08_constant_velocity_field_delivery_correction_v33.json"
    anchor_files = [
        ("RK08 constant-field frozen protocol", root / "configs/a8_rk08_constant_velocity_field_protocol_v1.json"),
        ("RK08 constant-field preparation", root / "audits/20261120/RK08/constant_velocity_field_preparation_v5.json"),
        ("RK08 constant-field production", root / "audits/20261120/RK08/constant_velocity_field_v1.json"),
        ("RK08 constant-field independent verification", root / "audits/20261120/RK08/constant_velocity_field_independent_v1.json"),
        ("RK08 constant-field finalization", root / "audits/20261120/RK08/constant_velocity_field_finalization_v1.json"),
        ("RK08 constant-field exact-commit post-push verification", root / "audits/20261120/RK08/constant_velocity_field_postpush_independent_v1.json"),
        ("RK08 constant-field 10-test log", root / "audits/20261120/RK08/constant_velocity_field_unit_tests_v5.log"),
        ("RK08 constant-field manuscript source section", section_path),
        ("RK08 constant-field manuscript prepare check", prepare_check_path),
        ("RK08 constant-field manuscript draft check", draft_check_path),
        ("RK08 constant-field manuscript writing status", status_path),
        ("RK08 constant-field retained delivery failure", deliver_failure_path),
        ("RK08 constant-field delivery correction", correction_path),
    ]
    anchor_rows = "\n".join(f"| {name} | `{sha(path)}` |" for name, path in anchor_files)
    check("anchor_rows_hash", sha_bytes(anchor_rows.encode()) == update["anchor_rows_sha256"])
    for name, path in anchor_files:
        row = f"| {name} | `{sha(path)}` |"
        check(f"evidence_anchor_{name}", current.count(row) == 1)
    anchor_marker = "\n\nA7 is retained as the prior manuscript snapshot."
    anchor_insert = "\n\n" + anchor_rows + "\n\nA7 is retained as the prior manuscript snapshot."
    expected = baseline.replace("## 7. Discussion", section_insert, 1).replace(anchor_marker, anchor_insert, 1)
    check("exact_reconstruction_from_v32", expected == current)
    restored = current.replace(section_insert, "## 7. Discussion", 1).replace(anchor_insert, anchor_marker, 1)
    check("exact_rollback_to_v32", restored == baseline and sha_bytes(restored.encode()) == BEFORE_SHA)
    check("references_unchanged", current[current.index("## 9. References"):] == baseline[baseline.index("## 9. References"):])
    check("abstract_unchanged", current[current.index("## Abstract"):current.index("## 1. Introduction")] == baseline[baseline.index("## Abstract"):baseline.index("## 1. Introduction")])

    metrics = production["metrics"][production["primary_partition"]]
    for arm in ("model", "ridge", "constant"):
        for key in ("transcript_balanced_mse", "mean_transcript_pearson"):
            numeric_literal(f"primary_metric_{arm}_{key}", metrics[arm][key])
    for comparison_id, values in production["primary_comparisons"].items():
        numeric_literal(f"comparison_{comparison_id}_delta_mse", values["delta_transcript_balanced_mse"])
        numeric_literal(f"comparison_{comparison_id}_delta_pearson", values["delta_mean_transcript_pearson"])
        for endpoint in ("transcript_balanced_mse", "mean_transcript_pearson"):
            for i, value in enumerate(values[endpoint]["ci95"]):
                numeric_literal(f"comparison_{comparison_id}_{endpoint}_ci_{i}", value)
            check(f"comparison_{comparison_id}_{endpoint}_holm_zero", values[endpoint]["holm_pvalue"] == 0.0)
        check(f"comparison_{comparison_id}_bootstrap", values["bootstrap_replicates"] == 2000 and values["bootstrap_seed"] == 20261120)
        check(f"comparison_{comparison_id}_sensitivity_adverse", len(values["sensitivity_bootstrap_mean_deltas"]) == 2 and all(row["transcript_balanced_mse"] > 0 and row["mean_transcript_pearson"] < 0 for row in values["sensitivity_bootstrap_mean_deltas"]))
    check("constant_best_mse", metrics["constant"]["transcript_balanced_mse"] < min(metrics["model"]["transcript_balanced_mse"], metrics["ridge"]["transcript_balanced_mse"]))
    check("constant_best_pearson", metrics["constant"]["mean_transcript_pearson"] > max(metrics["model"]["mean_transcript_pearson"], metrics["ridge"]["mean_transcript_pearson"]))
    check("train_fit_explicit", production["constant_field"]["fit_transcripts"] == 933 and production["constant_field"]["fit_rows"] == 267800 and "933 transcripts and 267,800 observed codon positions" in section)
    check("evaluation_size_explicit", metrics["constant"]["n_transcripts"] == 3630 and metrics["constant"]["n_observed_positions"] == 1444596 and "3,630 transcripts and 1,444,596 observed positions" in section)
    check("zero_exact_cds_overlap_explicit", "zero exact-CDS overlap with all Mohammad16 splits" in section)
    check("equal_weight_estimator_explicit", production["constant_field"]["estimator"] == "equal-weight mean of within-transcript bin means" and "averaged with equal transcript weight" in section)
    check("no_evaluation_target_fit", "No sequence, codon identity, host, evaluation target, new model fit, or checkpoint selection entered the comparator." in section)
    check("inference_contract_explicit", "2,000 transcript-bootstrap replicates" in section and "Six endpoint-wise tests were corrected together by the Holm method." in section)
    check("both_learned_predictors_unsupported", "neither the model–constant nor the ridge–constant comparison met the support rule" in section)
    check("original_model_ridge_negative", "The original model–ridge comparison also remained unfavorable" in section)
    check("cross_study_negative_strengthened", "strengthen the prior negative cross-study mechanism conclusion" in section)
    check("proxy_not_physical_velocity", "occupancy-derived speed proxy rather than a physical velocity measurement" in section)
    check("independent_361_reported", "**361/361 checks**" in section and independent["passed_count"] == 361 and independent["failed_count"] == 0)
    check("independent_delta_reported", "6.245004513516506 × 10⁻¹⁷" in section and independent["max_numeric_delta"] == 6.245004513516506e-17)
    check("finalization_37_reported", "**37/37 checks**" in section and finalization["passed_count"] == 37 and finalization["failed_count"] == 0)
    check("postpush_361_reported", "exact-commit post-push rerun again passed **361/361 checks**" in section and postpush["status"] == "PASS_CONSTANT_VELOCITY_INDEPENDENT" and postpush["passed_count"] == 361 and postpush["failed_count"] == 0)
    check("postpush_binds_production", postpush["production_sha256"] == sha(root / "audits/20261120/RK08/constant_velocity_field_v1.json"))
    numeric_literal("production_elapsed", production["cost"]["elapsed_seconds"])
    check("zero_new_training_cost", all(production["cost"][key] == 0 for key in ("new_model_training_runs", "new_checkpoint_selection_runs", "model_forward_passes", "unique_scorer_calls")) and "no new training, model forward pass, checkpoint selection, or scorer call" in section)
    check("all_support_false", all(value is False for value in production["support"].values()))
    check("functional_untouched", "Functional-untouched data were not accessed" in section and production["gates"]["functional_untouched_evaluated"] is False)
    check("rk_g1_remains_false", "RK-G1 remains false" in section and production["gates"]["rk_g1_pass"] is False)
    check("generator_unauthorized", "generator training remains unauthorized" in section and production["gates"]["generator_training_authorized"] is False)
    check("no_overclaim", "does not establish homology-cluster OOD, causal velocity regulation, biological function, or external SOTA" in section and production["gates"]["external_sota_claim_authorized"] is False)

    status = json.loads(status_path.read_text())
    draft_check = json.loads(draft_check_path.read_text())
    prepare_check = json.loads(prepare_check_path.read_text())
    correction = json.loads(correction_path.read_text())
    check("workflow_status_pass", status["status"] == "PASS" and status["lark"] == "skipped_by_user")
    check("workflow_prepare_pass", prepare_check["status"] == "pass")
    check("workflow_draft_pass", draft_check["status"] == "pass" and draft_check["result"]["word_count"] == 513)
    check("workflow_input_binds_section", draft_check["result"]["input_sha256"] == sha(section_path))
    check("delivery_failure_retained", "finish_with_status: command not found" in deliver_failure_path.read_text())
    check("delivery_correction_bounded", correction["status"] == "PASS_MARKDOWN_WITH_RETAINED_DELIVERY_TOOL_FAILURE" and correction["scientific_content_changed_by_correction"] is False and correction["lark_document_created_or_modified"] is False)
    check("update_pending_verification_before_this_report", update["status"] == "PASS_MANUSCRIPT_UPDATED_PENDING_INDEPENDENT_VERIFICATION")
    check("science_commit_bound", update["science_commit"] == SCIENCE_COMMIT and preparation["science_commit"] == SCIENCE_COMMIT)

    passed = sum(row["pass"] for row in checks)
    failed = len(checks) - passed
    report = {
        "schema": "a8-rk08-constant-field-paper-verification-v33",
        "status": "PASS_CONSTANT_FIELD_PAPER_V33" if failed == 0 else "FAIL_CONSTANT_FIELD_PAPER_V33",
        "overall_pass": failed == 0,
        "checks_total": len(checks),
        "checks_passed": passed,
        "checks_failed": failed,
        "baseline_commit": BASELINE_COMMIT,
        "science_commit": SCIENCE_COMMIT,
        "before_sha256": BEFORE_SHA,
        "after_sha256": sha_bytes(current_bytes),
        "update_report_sha256": sha(update_path),
        "preparation_report_sha256": sha(preparation_path),
        "section_sha256": sha(section_path),
        "exact_rollback_to_v32": True,
        "references_changed": False,
        "scientific_content_source": "audits/20261120/RK08/constant_velocity_field_v1.json plus independent, finalization, and exact-commit post-push reports",
        "constant_field_best_on_primary_proxy": failed == 0,
        "velocity_mechanism_pass": False,
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
