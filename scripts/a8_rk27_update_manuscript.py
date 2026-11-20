#!/usr/bin/env python3
"""Insertion-only RK27 manuscript update with exact source reconstruction."""
from pathlib import Path
import argparse
import hashlib
import json

ORIGINAL_SHA256 = "91e8bf226225d6d621617128618012b9333086646af9cd315b34be156f130f9a"
HEADING = "### 6.38 Measured 5′ MFE improved fixed-GFP sequence-cluster transport in a retrospective analysis"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for name in ["original", "section", "result", "coverage", "independent", "closeout", "meta", "prepare", "draft", "status", "output", "report"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    original = args.original.read_text()
    section = args.section.read_text()
    result = json.loads(args.result.read_text())
    coverage = json.loads(args.coverage.read_text())
    independent = json.loads(args.independent.read_text())
    closeout = json.loads(args.closeout.read_text())
    meta = json.loads(args.meta.read_text())
    prepare = json.loads(args.prepare.read_text())
    draft = json.loads(args.draft.read_text())
    workflow_status = json.loads(args.status.read_text())
    assert sha(args.original) == ORIGINAL_SHA256
    assert section.startswith(HEADING + "\n")
    assert HEADING not in original
    assert "| RK27 " not in original
    assert original.count("\n## 7. Discussion") == 1
    assert original.count("\nA7 is retained as the prior manuscript snapshot.") == 1
    assert result["scientific_conclusion"] == "FIXED_PROTEIN_SEQUENCE_CLUSTER_OOD_MFE_INCREMENT_SUPPORTED_RETROSPECTIVELY"
    assert result["n_measurement_rows"] == 154 and result["n_exact_cds_groups"] == 150 and result["n_sequence_clusters"] == 37
    assert result["total_model_fits"] == 300 and len(result["primary_tests"]) == 4
    assert all(test["pass"] and test["positive_seeds"] == 10 and test["ci95"][0] > 0 and test["p_holm"] < 0.05 for test in result["primary_tests"])
    assert coverage["status"] == "PASS_LABEL_FREE_COVERAGE_AUDIT" and coverage["expression_or_model_fit_performed"] is False
    assert independent["status"] == "PASS" and independent["n_checks"] == independent["n_passed"] == 47
    assert closeout["status"] == "PASS" and closeout["n_checks"] == closeout["n_passed"] == 97
    assert closeout["result_sha256"] == sha(args.result)
    assert closeout["independent_report_sha256"] == sha(args.independent)
    assert independent["production_summary_sha256"] == sha(args.result)
    assert meta["mode"] == "draft" and meta["output_target"] == "markdown_only" and meta["needs_citation"] == "no"
    assert prepare["status"] == "pass" and draft["status"] == "pass" and workflow_status["status"] == "PASS"
    assert draft["result"]["input_sha256"] == sha(args.section) and draft["result"]["word_count"] == 519
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
    manuscript = original.replace("\n## 7. Discussion", "\n" + section.strip() + "\n\n## 7. Discussion", 1)
    rows = "".join(f"| {name} | `{digest}` |\n" for name, digest in evidence.items())
    manuscript = manuscript.replace("\nA7 is retained as the prior manuscript snapshot.", rows + "\nA7 is retained as the prior manuscript snapshot.", 1)
    without_section = manuscript.replace("\n" + section.strip() + "\n\n## 7. Discussion", "\n## 7. Discussion", 1)
    ledger_rows = [line for line in without_section.splitlines() if line.startswith("| RK27 ")]
    recovered = "\n".join(line for line in without_section.splitlines() if not line.startswith("| RK27 ")) + "\n"
    assert len(ledger_rows) == len(evidence) == 12
    assert recovered == original
    assert manuscript.count(section.strip()) == 1
    assert manuscript.count(HEADING) == 1
    args.output.write_text(manuscript)
    report = {
        "schema": "a8-rk27-manuscript-update-v1",
        "status": "PASS",
        "original_sha256": sha(args.original),
        "section_sha256": sha(args.section),
        "manuscript_sha256": sha(args.output),
        "result_sha256": sha(args.result),
        "coverage_sha256": sha(args.coverage),
        "independent_sha256": sha(args.independent),
        "closeout_sha256": sha(args.closeout),
        "prepare_sha256": sha(args.prepare),
        "draft_sha256": sha(args.draft),
        "status_sha256": sha(args.status),
        "inserted_heading": HEADING,
        "evidence_rows": evidence,
        "evidence_row_count": len(ledger_rows),
        "old_manuscript_reconstruction_exact": True,
        "insertion_only": True,
        "functional_untouched_evaluated": False,
        "rk_g1": False,
        "generator_training_authorized": False,
    }
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({key: report[key] for key in ["status", "manuscript_sha256", "section_sha256", "evidence_row_count", "old_manuscript_reconstruction_exact"]}, indent=2))


if __name__ == "__main__":
    main()
