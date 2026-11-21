#!/usr/bin/env python3
"""Independent contract review for the RK32 manuscript integration."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

START = "<!-- A8_RK32_START -->"
END = "<!-- A8_RK32_END -->"
ANCHOR_START = "<!-- A8_RK32_ANCHORS_START -->"
ANCHOR_END = "<!-- A8_RK32_ANCHORS_END -->"
ARM = {"source_local": "Source local", "vienna_local": "Vienna local", "source_full": "Source full",
       "vienna_full_cds": "Vienna full CDS", "vienna_full_mrna": "Vienna full mRNA", "mordstein_like": "Mordstein-like"}
ABS_ARM = {"null": "Null", "ridge_simple": "Ridge simple", "histgb_simple": "HistGB simple", **{
    f"{model}_{arm}": f"{model_name} {arm_name}" for model, model_name in [("ridge", "Ridge"), ("histgb", "HistGB")] for arm, arm_name in ARM.items()}}
MODEL = {"ridge": "Ridge", "histgb": "HistGB"}
METRIC = {"spearman_effect": "ΔSpearman", "mse_improvement": "MSE improvement"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fmt(v, digits=9) -> str:
    if isinstance(v, bool): return "PASS" if v else "FAIL"
    if isinstance(v, int): return str(v)
    return f"{float(v):.{digits}g}"


def remove_block(text: str, start: str, end: str) -> str:
    pattern = re.escape(start) + r"\n.*?\n" + re.escape(end) + r"\n\n"
    return re.sub(pattern, "", text, count=1, flags=re.S)


def main() -> None:
    p = argparse.ArgumentParser()
    for name in ["original", "manuscript", "section", "writing-final", "result", "protocol", "preflight", "independent", "closeout", "reproduction", "integration", "output"]:
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    original = a.original.read_text()
    text = a.manuscript.read_text()
    section = a.section.read_text()
    result = json.loads(a.result.read_text())
    protocol = json.loads(a.protocol.read_text())
    preflight = json.loads(a.preflight.read_text())
    independent = json.loads(a.independent.read_text())
    closeout = json.loads(a.closeout.read_text())
    reproduction = json.loads(a.reproduction.read_text())
    integration = json.loads(a.integration.read_text())
    checks = []
    def check(name, condition, detail=None): checks.append({"check": name, "pass": bool(condition), "detail": detail})

    check("integration_binding", integration["status"] == "PASS_RK32_MANUSCRIPT_INTEGRATION" and integration["manuscript_sha256"] == sha(a.manuscript) and integration["input_manuscript_sha256"] == sha(a.original))
    canonical_section = section.strip().replace("\n\n" + END, "\n" + END)
    check("single_section", text.count(START) == text.count(END) == 1 and canonical_section in text)
    stripped = remove_block(remove_block(text, START, END), ANCHOR_START, ANCHOR_END)
    check("prior_manuscript_byte_preserved", stripped == original, {"stripped_sha256": hashlib.sha256(stripped.encode()).hexdigest(), "original_sha256": sha(a.original)})
    check("rk31_and_prior_sections_preserved", "### 6.42 Known-context gating did not support broad MFE applicability" in stripped and "### 6.41 Matched host and 5′UTR-intron transport in the Mordstein GFP library" in stripped)
    check("label_free_and_frozen_contract", preflight["expression_columns_read"] is False and preflight["model_fit_performed"] is False and protocol["expression_association_or_model_fit_performed_before_freeze"] is False)
    primary_part = section.split("**Table 19**", 1)[1].split("*Note.*", 1)[0]
    primary_rows = [line for line in primary_part.splitlines() if line.startswith("| Ridge |") or line.startswith("| HistGB |")]
    expected_primary = []
    for row in result["primary_tests"]:
        model, arm, metric = row["test"].split("__")
        expected_primary.append("| " + " | ".join([MODEL[model], ARM[arm], METRIC[metric], fmt(row["observed_effect"]), f"[{fmt(row['ci95'][0])}, {fmt(row['ci95'][1])}]", fmt(row["p_holm"]), f"{row['positive_seeds']}/10", fmt(row["pass"])]) + " |")
    check("table19_exact_24_rows", primary_rows == expected_primary, {"rows": len(primary_rows)})
    check("endpoint_decision_accounting", sum(row["pass"] for row in result["primary_tests"]) == 9 and "| HistGB | Mordstein-like | MSE improvement" in section and "0.929453527" in section)
    abs_part = section.split("**Table 20**", 1)[1].split("*Note.*", 1)[0]
    abs_rows = [line for line in abs_part.splitlines() if line.startswith("| ") and not line.startswith("| Arm") and not line.startswith("|---")]
    expected_abs = ["| " + " | ".join([ABS_ARM[row["arm"]], fmt(row["spearman"]), fmt(row["mse"])]) + " |" for row in result["primary_absolute_performance"]]
    check("table20_exact_15_rows", abs_rows == expected_abs, {"rows": len(abs_rows)})
    check("arm_conclusions_exact", "Source local 4/4; Vienna local 4/4; Source full 0/4; Vienna full CDS 0/4; Vienna full mRNA 0/4; Mordstein-like 1/4" in section and result["scientific_conclusion"] in section)
    check("local_not_universal", "not a universal structure effect or a claim that longer coverage is inherently uninformative" in section)
    check("mordstein_coverage_boundary", "starts at CDS position 4 and lacks the start codon and four upstream nucleotides" in section and "does not close cross-study local-structure transport" in section)
    check("independent_deltas_and_fits", "23/23 checks" in section and "700 model fits" in section and all(fmt(v, 6) in section for v in independent["max_deltas"].values()))
    check("clean_reproduction_exact", f"{reproduction['checks_passed']}/{reproduction['checks_total']} checks" in section and f"all {reproduction['csv_count']} CSV artifacts" in section and f"all {reproduction['npz_array_count']} inference arrays" in section and reproduction["clean_clone_head"] in section)
    check("closeout_and_tests", f"{closeout['checks_passed']}/{closeout['checks_total']} checks" in section and f"passed {closeout['pytest_passed']} tests with {closeout['pytest_skipped']} skipped" in section)
    anchor_part = text.split(ANCHOR_START, 1)[1].split(ANCHOR_END, 1)[0]
    expected_hashes = [sha(a.preflight), sha(a.protocol), sha(a.result), sha(a.independent), sha(a.closeout), sha(a.reproduction)]
    check("evidence_anchor_hashes", all(h in anchor_part for h in expected_hashes) and len(set(expected_hashes)) == 6)
    writing = a.writing_final.read_text().strip()
    section_no_markers = section.replace(START + "\n", "").replace("\n" + END, "").strip()
    check("writing_workflow_final_exact", writing == section_no_markers)
    check("working_draft_and_open_gates", "non-submittable working draft" in section and "does not read functional-untouched data" in section and "complete a seven-method dense generation-call matrix" in section and "or complete RK-G1" in section)
    check("failure_history_retained", "pre-fit v1 stop" in section and "literal `null` parsing" in section and "neither engineering correction changed" in section)
    failed = [x for x in checks if not x["pass"]]
    report = {"status": "PASS_RK32_MANUSCRIPT_REVIEW" if not failed else "FAIL_RK32_MANUSCRIPT_REVIEW",
              "checks_total": len(checks), "checks_passed": len(checks) - len(failed), "failed_checks": failed,
              "checks": checks, "manuscript_sha256": sha(a.manuscript), "section_sha256": sha(a.section),
              "working_draft": True, "independent_confirmation": False, "RK_G1_complete": False}
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, indent=2))
    if failed: raise SystemExit(1)


if __name__ == "__main__": main()
