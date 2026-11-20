#!/usr/bin/env python3
"""Insertion-only RK28 manuscript update with exact source reconstruction."""
from pathlib import Path
import argparse
import hashlib
import json

ORIGINAL_SHA256 = "1a4f84e16179d6ef7d4d7d59dd1f21f7d5313635e6e3d27f31ec6f7e2149bc5c"
HEADING = "### 6.39 Observed-R1 structure did not support fixed-GFP cross-study sequence-cluster transport"


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
    assert "| RK28 " not in original
    assert original.count("\n## 7. Discussion") == 1
    assert original.count("\nA7 is retained as the prior manuscript snapshot.") == 1
    assert result["scientific_conclusion"] == "FIXED_GFP_HEK293_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED"
    assert result["n_variants"] == 152 and result["n_sequence_clusters"] == 74
    assert result["total_model_fits"] == 300 and len(result["primary_tests"]) == 4
    assert all(not test["pass"] and test["ci95"][0] < 0 < test["ci95"][1] and test["p_holm"] > 0.05 for test in result["primary_tests"])
    assert [test["positive_seeds"] for test in result["primary_tests"]] == [0, 0, 3, 5]
    assert coverage["status"] == "PASS_LABEL_FREE_COVERAGE_AUDIT_FEASIBLE" and coverage["expression_or_model_fit_performed"] is False
    assert independent["status"] == "PASS" and independent["n_checks"] == independent["n_passed"] == 54
    assert closeout["status"] == "PASS" and closeout["n_checks"] == closeout["n_passed"] == 101
    assert closeout["result_sha256"] == sha(args.result)
    assert closeout["independent_report_sha256"] == sha(args.independent)
    assert independent["production_summary_sha256"] == sha(args.result)
    assert meta["mode"] == "draft" and meta["output_target"] == "markdown_only" and meta["needs_citation"] == "no"
    assert prepare["status"] == "pass" and draft["status"] == "pass" and workflow_status["status"] == "PASS"
    assert draft["result"]["input_sha256"] == sha(args.section) and draft["result"]["word_count"] == 603
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
    manuscript = original.replace("\n## 7. Discussion", "\n" + section.strip() + "\n\n## 7. Discussion", 1)
    rows = "".join(f"| {name} | `{digest}` |\n" for name, digest in evidence.items())
    manuscript = manuscript.replace("\nA7 is retained as the prior manuscript snapshot.", rows + "\nA7 is retained as the prior manuscript snapshot.", 1)
    without_section = manuscript.replace("\n" + section.strip() + "\n\n## 7. Discussion", "\n## 7. Discussion", 1)
    ledger_rows = [line for line in without_section.splitlines() if line.startswith("| RK28 ")]
    recovered = "\n".join(line for line in without_section.splitlines() if not line.startswith("| RK28 ")) + "\n"
    assert len(ledger_rows) == len(evidence) == 12
    assert recovered == original
    assert manuscript.count(section.strip()) == 1
    assert manuscript.count(HEADING) == 1
    args.output.write_text(manuscript)
    report = {
        "schema": "a8-rk28-manuscript-update-v1",
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
