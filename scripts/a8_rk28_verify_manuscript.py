#!/usr/bin/env python3
"""Independently verify the RK28 section and insertion-only manuscript update."""
from pathlib import Path
import argparse
import hashlib
import json

ORIGINAL_SHA256 = "1a4f84e16179d6ef7d4d7d59dd1f21f7d5313635e6e3d27f31ec6f7e2149bc5c"
HEADING = "### 6.39 Observed-R1 structure did not support fixed-GFP cross-study sequence-cluster transport"
SCIENCE_COMMIT = "71d27dd7610559c2781849c2be7b2a26933c3d0e"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for name in ["original", "manuscript", "section", "paper-final", "result", "coverage", "independent", "independent-initial", "production-synthetic", "production-synthetic-initial-log", "closeout", "meta", "prepare", "draft", "status", "deliver-log", "update-report", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    original = args.original.read_text()
    manuscript = args.manuscript.read_text()
    section = args.section.read_text()
    paper_final = args.paper_final.read_text()
    result = json.loads(args.result.read_text())
    coverage = json.loads(args.coverage.read_text())
    independent = json.loads(args.independent.read_text())
    independent_initial = json.loads(args.independent_initial.read_text())
    production_synthetic = json.loads(args.production_synthetic.read_text())
    production_synthetic_initial_log = args.production_synthetic_initial_log.read_text()
    closeout = json.loads(args.closeout.read_text())
    meta = json.loads(args.meta.read_text())
    prepare = json.loads(args.prepare.read_text())
    draft = json.loads(args.draft.read_text())
    workflow_status = json.loads(args.status.read_text())
    update_report = json.loads(args.update_report.read_text())
    deliver_log = args.deliver_log.read_text()
    checks = []

    def check(name, condition):
        checks.append({"name": name, "pass": bool(condition)})

    check("original frozen hash", sha(args.original) == ORIGINAL_SHA256)
    check("section occurs once", manuscript.count(section.strip()) == 1)
    check("section heading once", manuscript.count(HEADING) == 1)
    check("RK28 follows RK27 and precedes Discussion", manuscript.index("### 6.38 ") < manuscript.index(HEADING) < manuscript.index("## 7. Discussion"))
    without_section = manuscript.replace("\n" + section.strip() + "\n\n## 7. Discussion", "\n## 7. Discussion", 1)
    ledger_rows = [line for line in without_section.splitlines() if line.startswith("| RK28 ")]
    recovered = "\n".join(line for line in without_section.splitlines() if not line.startswith("| RK28 ")) + "\n"
    check("twelve RK28 evidence rows", len(ledger_rows) == 12)
    check("all prior manuscript text unchanged", recovered == original)
    check("paper final byte text equals section", paper_final == section)
    check("paper final hash binds section", sha(args.paper_final) == sha(args.section))
    check("draft mode", meta["mode"] == "draft")
    check("section task scope", meta["task_scope"] == "section")
    check("Markdown-only target", meta["output_target"] == "markdown_only")
    check("no citation task", meta["needs_citation"] == "no")
    check("prepare pass", prepare["status"] == "pass")
    check("draft pass", draft["status"] == "pass")
    check("draft section hash", draft["result"]["input_sha256"] == sha(args.section))
    check("draft 603 words", draft["result"]["word_count"] == 603)
    check("three-state PASS", workflow_status["status"] == "PASS" and workflow_status["stage"] == "deliver")
    check("Markdown-only delivery reason", workflow_status.get("reason", "").startswith("写作检查通过") and workflow_status.get("lark") == "skipped_by_user")
    check("delivery shell failure retained", "finish_with_status: command not found" in deliver_log)
    check("update report pass", update_report["status"] == "PASS" and update_report["insertion_only"] is True)
    check("update report manuscript hash", update_report["manuscript_sha256"] == sha(args.manuscript))
    check("update report reconstruction", update_report["old_manuscript_reconstruction_exact"] is True)
    check("production synthetic 20/20", production_synthetic["status"] == "PASS" and production_synthetic["passed"] == 20 and production_synthetic["failed"] == 0 and production_synthetic["model_fit_on_study_data"] is False and production_synthetic["study_outcomes_read"] is False)
    check("initial synthetic ridge misconception retained", "1e-08" in production_synthetic_initial_log or "1e-8" in production_synthetic_initial_log)
    check("initial independent 53/54", independent_initial["status"] == "FAIL" and independent_initial["n_checks"] == 54 and independent_initial["n_passed"] == 53)
    check("independent OOD 54/54", independent["status"] == "PASS" and independent["n_checks"] == independent["n_passed"] == 54 and all(item["pass"] for item in independent["checks"]))
    check("closeout 101/101", closeout["status"] == "PASS" and closeout["n_checks"] == closeout["n_passed"] == 101 and all(item["pass"] for item in closeout["checks"]))
    check("production result bound", independent["production_summary_sha256"] == sha(args.result) == closeout["result_sha256"])
    check("independent report bound", closeout["independent_report_sha256"] == sha(args.independent))
    check("science commit bound", closeout["science_commit"] == SCIENCE_COMMIT)
    check("scientific conclusion exact", result["scientific_conclusion"] == "FIXED_GFP_HEK293_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED")
    check("retrospective cross-study analysis role", result["analysis_type"] == "retrospective_cross_study_fixed_gfp_observed_r1_structure_increment_sequence_cluster_transport_validation")
    check("sample chain", result["n_variants"] == 152 and result["n_sequence_clusters"] == 74)
    check("300 fits over 10 seeds and 5 folds", result["total_model_fits"] == 300 and len(result["seeds"]) == 10 and result["folds_per_seed"] == 5)
    check("label-free coverage", coverage["expression_or_model_fit_performed"] is False and coverage["outcome_or_model_feature_read"] is False and coverage["columns_read"] == ["variant_id", "sequence_5prime_300nt"])
    check("selected 90 percent clustering", coverage["selected_min_identity"] == 0.9 and coverage["selected_coverage"]["clusters"] == 74 and coverage["selected_coverage"]["largest_cluster"] == 12 and coverage["selected_coverage"]["singleton_clusters"] == 35)
    check("primary fold sizes", coverage["selected_coverage"]["primary_seed_fold_sizes"] == [30, 31, 31, 30, 30])
    check("primary fold cluster counts", coverage["selected_coverage"]["primary_seed_fold_cluster_counts"] == [15, 15, 16, 15, 13])
    check("all four primary gates failed", len(result["primary_tests"]) == 4 and all(not test["pass"] and test["ci95"][0] < 0 < test["ci95"][1] and test["p_holm"] > 0.05 for test in result["primary_tests"]))
    check("positive seed counts", [test["positive_seeds"] for test in result["primary_tests"]] == [0, 0, 3, 5])
    flags = result["scientific_flags"]
    check("fixed-protein sequence-cluster scope", flags["fixed_protein"] is True and flags["protein_ood"] is False and flags["external_study_relative_to_RK27"] is True)
    check("retrospective label boundary", flags["labels_previously_used_in_RK02_development"] is True and flags["independent_untouched_confirmation"] is False)
    check("observed-R1 not complete measured structure", flags["complete_cds_observed"] is False and flags["measured_structure"] is False and flags["author_gfp_identity_mapping"] is False)
    check("no full mechanism or velocity decay", flags["full_spatial_coupling_established"] is False and flags["velocity_or_decay_measured"] is False)
    check("science no authorization", flags["rk_g1_complete"] is False and flags["generator_training_authorized"] is False and flags["functional_untouched_read"] is False)
    check("table caption once", section.count("**Table 11**") == 1)
    check("prior table retained", manuscript.count("**Table 10**") == 1)
    model_names = {"ridge": "Ridge", "histgb": "HistGB"}
    endpoint_names = {"spearman_effect": "ΔSpearman", "mse_improvement": "MSE improvement"}
    for test in result["primary_tests"]:
        model, endpoint = test["test"].split("_", 1)
        effect = f"{test['observed_effect']:.6f}".replace("-", "−")
        low = f"{test['ci95'][0]:.6f}".replace("-", "−")
        high = f"{test['ci95'][1]:.6f}".replace("-", "−")
        row = f"| {model_names[model]} | {endpoint_names[endpoint]} | {effect} | [{low}, {high}] | {test['p_holm']:.8f} | {test['positive_seeds']}/10 |"
        check("manuscript primary row " + test["test"], row in section)
    absolute = {item["arm"]: item for item in result["primary_absolute_performance"]}
    for model in ["ridge", "histgb"]:
        for arm in ["simple", "structure", "mfe_only"]:
            item = absolute[f"{model}_{arm}"]
            value = f"{item['spearman']:.6f}/{item['mse']:.6f}".replace("-", "−")
            check(f"primary absolute {model} {arm}", value in section)
    required = [
        "retrospective cross-study observed-R1 sequence-cluster transport analysis, not independent untouched confirmation",
        "The RK04 functional-untouched split was not read.",
        "The 152 unique identifiers corresponded to 152 unique 300-nucleotide ACGT sequences.",
        "giving 300 CPU model fits",
        "All four frozen endpoints failed",
        "Both ridge effects were negative in all 10 seeds",
        "these arms did not replace the confirmatory structure-versus-simple comparison",
        "the revised test passed 20/20 checks without changing the production model, protocol, or thresholds",
        "Its retained initial report passed 53/54 checks",
        "Only CSV parsing was corrected",
        "final independent acceptance passed 54/54 checks",
        "Scientific closeout and registry binding passed 101/101 checks",
        "do not directly contradict RK27",
        "reject a strong claim that the structure increment transports generally across studies",
        "do not establish that structure is universally harmful",
        "The unobserved central 138 nucleotides, corresponding to 46 codons, could not be restored",
        "author-level GFP identity mapping was unavailable",
        "not independent untouched or protein-OOD confirmation",
        "provides no complete-CDS measured structure, translation velocity, mRNA decay, or complete spatial-coupling evidence",
        "It does not establish CodonFlow-RK superiority, external SOTA, or functional untouched performance",
        "RK-G1 remains false and expensive generator training remains unauthorized",
        "the manuscript remains a non-submittable working draft",
    ]
    for text in required:
        check("required statement: " + text, text in section)
    check("no full-mechanism success claim", "complete spatial coupling was established" not in section and "RK-G1 passed" not in section)
    evidence = {
        "RK28 frozen observed-R1 sequence-cluster protocol": result["protocol_sha256"],
        "RK28 Mordstein source CSV": coverage["source_sha256"],
        "RK28 label-free observed-R1 coverage": result["coverage_report_sha256"],
        "RK28 observed-R1 sequence-cluster facts": coverage["facts_sha256"],
        "RK28 observed-R1 OOF predictions": result["outputs"]["oof_predictions.csv"]["sha256"],
        "RK28 observed-R1 training log": result["outputs"]["training_log.csv"]["sha256"],
        "RK28 observed-R1 sequence-cluster OOD result": sha(args.result),
        "RK28 independent observed-R1 OOD verification": sha(args.independent),
        "RK28 scientific closeout": closeout["closeout_sha256"],
        "RK28 closeout verification": sha(args.closeout),
        "RK28 manuscript section": sha(args.section),
        "RK28 manuscript writing status": sha(args.status),
    }
    for name, digest in evidence.items():
        check("evidence row " + name, f"| {name} | `{digest}` |" in ledger_rows)
    failed = [item["name"] for item in checks if not item["pass"]]
    report = {
        "schema": "a8-rk28-manuscript-verification-v1",
        "status": "PASS" if not failed else "FAIL",
        "original_sha256": sha(args.original),
        "manuscript_sha256": sha(args.manuscript),
        "section_sha256": sha(args.section),
        "paper_final_sha256": sha(args.paper_final),
        "result_sha256": sha(args.result),
        "coverage_sha256": sha(args.coverage),
        "independent_sha256": sha(args.independent),
        "independent_initial_sha256": sha(args.independent_initial),
        "production_synthetic_sha256": sha(args.production_synthetic),
        "closeout_sha256": sha(args.closeout),
        "prepare_sha256": sha(args.prepare),
        "draft_sha256": sha(args.draft),
        "status_sha256": sha(args.status),
        "update_report_sha256": sha(args.update_report),
        "workflow_status": workflow_status["status"],
        "mode": "draft",
        "output_target": "markdown_only",
        "delivery_shell_failure_retained": True,
        "initial_synthetic_failure_retained": True,
        "initial_independent_failure_retained": True,
        "checks_total": len(checks),
        "checks_passed": len(checks) - len(failed),
        "failed_checks": failed,
        "checks": checks,
        "old_manuscript_preserved_exactly": recovered == original,
        "functional_untouched_evaluated": False,
        "rk_g1": False,
        "generator_training_authorized": False,
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({key: report[key] for key in ["status", "checks_total", "checks_passed", "failed_checks", "manuscript_sha256"]}, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
