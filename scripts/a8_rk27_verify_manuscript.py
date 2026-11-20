#!/usr/bin/env python3
"""Independently verify the RK27 section and insertion-only manuscript update."""
from pathlib import Path
import argparse
import hashlib
import json

ORIGINAL_SHA256 = "91e8bf226225d6d621617128618012b9333086646af9cd315b34be156f130f9a"
HEADING = "### 6.38 Measured 5′ MFE improved fixed-GFP sequence-cluster transport in a retrospective analysis"
SCIENCE_COMMIT = "8a62836bb73b34bcae529bae6a21f6e3eefc85d1"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for name in ["original", "manuscript", "section", "paper-final", "result", "coverage", "independent", "closeout", "meta", "prepare", "draft", "status", "write-initial-log", "deliver-log", "update-report", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    original = args.original.read_text()
    manuscript = args.manuscript.read_text()
    section = args.section.read_text()
    paper_final = args.paper_final.read_text()
    result = json.loads(args.result.read_text())
    coverage = json.loads(args.coverage.read_text())
    independent = json.loads(args.independent.read_text())
    closeout = json.loads(args.closeout.read_text())
    meta = json.loads(args.meta.read_text())
    prepare = json.loads(args.prepare.read_text())
    draft = json.loads(args.draft.read_text())
    workflow_status = json.loads(args.status.read_text())
    update_report = json.loads(args.update_report.read_text())
    write_initial_log = args.write_initial_log.read_text()
    deliver_log = args.deliver_log.read_text()
    checks = []

    def check(name, condition):
        checks.append({"name": name, "pass": bool(condition)})

    check("original frozen hash", sha(args.original) == ORIGINAL_SHA256)
    check("section occurs once", manuscript.count(section.strip()) == 1)
    check("section heading once", manuscript.count(HEADING) == 1)
    check("RK27 follows RK26 and precedes Discussion", manuscript.index("### 6.37 ") < manuscript.index(HEADING) < manuscript.index("## 7. Discussion"))
    without_section = manuscript.replace("\n" + section.strip() + "\n\n## 7. Discussion", "\n## 7. Discussion", 1)
    ledger_rows = [line for line in without_section.splitlines() if line.startswith("| RK27 ")]
    recovered = "\n".join(line for line in without_section.splitlines() if not line.startswith("| RK27 ")) + "\n"
    check("twelve RK27 evidence rows", len(ledger_rows) == 12)
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
    check("draft 519 words", draft["result"]["word_count"] == 519)
    check("three-state PASS", workflow_status["status"] == "PASS" and workflow_status["stage"] == "deliver")
    check("Markdown-only delivery reason", workflow_status.get("reason", "").startswith("写作检查通过") and workflow_status.get("lark") == "skipped_by_user")
    check("initial shared-module failure retained", "ModuleNotFoundError: No module named 'revision_guard'" in write_initial_log)
    check("delivery shell failure retained", "finish_with_status: command not found" in deliver_log)
    check("update report pass", update_report["status"] == "PASS" and update_report["insertion_only"] is True)
    check("update report manuscript hash", update_report["manuscript_sha256"] == sha(args.manuscript))
    check("update report reconstruction", update_report["old_manuscript_reconstruction_exact"] is True)
    check("independent OOD 47/47", independent["status"] == "PASS" and independent["n_checks"] == independent["n_passed"] == 47 and all(item["pass"] for item in independent["checks"]))
    check("closeout 97/97", closeout["status"] == "PASS" and closeout["n_checks"] == closeout["n_passed"] == 97 and all(item["pass"] for item in closeout["checks"]))
    check("production result bound", independent["production_summary_sha256"] == sha(args.result) == closeout["result_sha256"])
    check("independent report bound", closeout["independent_report_sha256"] == sha(args.independent))
    check("science commit bound", closeout["science_commit"] == SCIENCE_COMMIT)
    check("scientific conclusion exact", result["scientific_conclusion"] == "FIXED_PROTEIN_SEQUENCE_CLUSTER_OOD_MFE_INCREMENT_SUPPORTED_RETROSPECTIVELY")
    check("retrospective analysis role", result["analysis_type"] == "retrospective_fixed_protein_sequence_cluster_transport_validation")
    check("sample chain", result["n_measurement_rows"] == 154 and result["n_exact_cds_groups"] == 150 and result["n_sequence_clusters"] == 37)
    check("300 fits over 10 seeds and 5 folds", result["total_model_fits"] == 300 and len(result["seeds"]) == 10 and result["folds_per_seed"] == 5)
    check("label-free coverage", coverage["expression_or_model_fit_performed"] is False and coverage["columns_read"] == ["source_row", "cds", "protein_aa"])
    check("selected 90 percent clustering", coverage["selected_min_identity"] == 0.9 and coverage["selected_coverage"]["clusters"] == 37 and coverage["selected_coverage"]["largest_cluster"] == 61 and coverage["selected_coverage"]["singleton_clusters"] == 13)
    check("primary fold sizes", coverage["selected_coverage"]["primary_seed_fold_sizes"] == [23, 61, 22, 22, 22])
    check("all four primary gates", len(result["primary_tests"]) == 4 and all(test["pass"] and test["positive_seeds"] == 10 and test["ci95"][0] > 0 and test["p_holm"] < 0.05 for test in result["primary_tests"]))
    flags = result["scientific_flags"]
    check("fixed-protein sequence-cluster scope", flags["fixed_protein"] is True and flags["sequence_cluster_ood"] is True and flags["protein_ood"] is False)
    check("retrospective label boundary", flags["labels_previously_used_in_RK22_development"] is True and flags["independent_untouched_confirmation"] is False)
    check("no full mechanism or velocity decay", flags["full_spatial_coupling_established"] is False and flags["velocity_or_decay_measured"] is False)
    check("science no authorization", flags["RK_G1_complete"] is False and flags["generator_training_authorized"] is False and flags["functional_untouched_read"] is False)
    check("table caption once", section.count("**Table 10**") == 1)
    check("prior table retained", manuscript.count("**Table 9**") == 1)
    model_names = {"ridge": "Ridge", "histgb": "HistGB"}
    endpoint_names = {"spearman_effect": "ΔSpearman", "mse_improvement": "MSE improvement"}
    for test in result["primary_tests"]:
        model, endpoint = test["test"].split("_", 1)
        row = f"| {model_names[model]} | {endpoint_names[endpoint]} | {test['observed_effect']:.6f} | [{test['ci95'][0]:.6f}, {test['ci95'][1]:.6f}] | {test['p_holm']:.8f} | {test['positive_seeds']}/10 |"
        check("manuscript primary row " + test["test"], row in section)
    absolute = {item["arm"]: item for item in result["primary_absolute_performance"]}
    for model in ["ridge", "histgb"]:
        for arm in ["simple", "structure", "mfe_only"]:
            item = absolute[f"{model}_{arm}"]
            check(f"primary absolute {model} {arm}", f"{item['spearman']:.6f}/{item['mse']:.6f}".replace("-", "−") in section or f"{item['spearman']:.6f}/{item['mse']:.6f}" in section)
    required = [
        "retrospective sequence-cluster transport validation, not independent untouched confirmation",
        "The RK04 functional-untouched split was not read.",
        "The 154 measurement rows were aggregated to 150 unique exact CDSs",
        "giving 300 CPU model fits",
        "All four frozen endpoints passed, and each was positive in all 10 seeds",
        "did not replace the confirmatory structure-versus-simple comparison",
        "Production and coverage synthetic tests passed 14/14 checks",
        "independent-implementation synthetic tests passed 8/8",
        "final acceptance passed 47/47 checks",
        "The retained initial report passed 46/47 checks",
        "Only the verifier’s CSV parsing was corrected",
        "Scientific closeout and registry binding passed 97/97 checks",
        "It is not independent external confirmation or protein OOD evidence",
        "provides no measurement of translation velocity, mRNA decay, or complete spatial coupling",
        "It does not establish CodonFlow-RK superiority, external SOTA, or functional untouched performance",
        "RK-G1 remains false and expensive generator training remains unauthorized",
        "the next appropriate test is an independent fixed-protein functional dataset rather than generator training",
        "The manuscript remains a non-submittable working draft",
    ]
    for text in required:
        check("required statement: " + text, text in section)
    check("no full-mechanism success claim", "complete spatial coupling was established" not in section and "RK-G1 passed" not in section)
    evidence = {
        "RK27 frozen sequence-cluster protocol": result["protocol_sha256"],
        "RK27 Kudla main source CSV": coverage["source_sha256"],
        "RK27 label-free sequence-cluster coverage": result["coverage_report_sha256"],
        "RK27 sequence-cluster facts": coverage["facts_sha256"],
        "RK27 sequence-cluster OOF predictions": result["outputs"]["oof_predictions.csv"]["sha256"],
        "RK27 sequence-cluster training log": result["outputs"]["training_log.csv"]["sha256"],
        "RK27 sequence-cluster OOD result": sha(args.result),
        "RK27 independent sequence-cluster OOD verification": sha(args.independent),
        "RK27 scientific closeout": closeout["closeout_sha256"],
        "RK27 closeout verification": sha(args.closeout),
        "RK27 manuscript section": sha(args.section),
        "RK27 manuscript writing status": sha(args.status),
    }
    for name, digest in evidence.items():
        check("evidence row " + name, f"| {name} | `{digest}` |" in ledger_rows)
    failed = [item["name"] for item in checks if not item["pass"]]
    report = {
        "schema": "a8-rk27-manuscript-verification-v1",
        "status": "PASS" if not failed else "FAIL",
        "original_sha256": sha(args.original),
        "manuscript_sha256": sha(args.manuscript),
        "section_sha256": sha(args.section),
        "paper_final_sha256": sha(args.paper_final),
        "result_sha256": sha(args.result),
        "coverage_sha256": sha(args.coverage),
        "independent_sha256": sha(args.independent),
        "closeout_sha256": sha(args.closeout),
        "prepare_sha256": sha(args.prepare),
        "draft_sha256": sha(args.draft),
        "status_sha256": sha(args.status),
        "update_report_sha256": sha(args.update_report),
        "workflow_status": workflow_status["status"],
        "mode": "draft",
        "output_target": "markdown_only",
        "initial_shared_module_failure_retained": True,
        "delivery_shell_failure_retained": True,
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
