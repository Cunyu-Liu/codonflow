#!/usr/bin/env python3
"""Independent verification of the A8 v13 HistGB manuscript addition."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signed(value: float) -> str:
    return f"{value:+.6f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="/home/codonflow-a8-rk")
    args = parser.parse_args()
    repo = Path(args.repo)
    paper = repo / "paper/CodonFlow_preprint_A8.md"
    a7 = repo / "paper/CodonFlow_preprint_A7.md"
    audit_path = repo / "paper/a8_rk_paper_sync_audit.json"
    update_path = repo / "paper/a8_rk08_histgb_paper_update.json"
    summary_path = repo / "audits/20261118/RK08/full_function_histgb_diagnostic_summary_v1.json"
    verification_path = repo / "audits/20261118/RK08/full_function_histgb_diagnostic_verification_v1.json"
    finalization_path = repo / "audits/20261118/RK08/full_function_histgb_diagnostic_finalization_v1.json"
    audit = json.loads(audit_path.read_text())
    update = json.loads(update_path.read_text())
    summary = json.loads(summary_path.read_text())
    verification = json.loads(verification_path.read_text())
    finalization = json.loads(finalization_path.read_text())
    snapshot = audit["pre_histgb_snapshot"]
    pre_paper = Path(snapshot["paper"]).read_text()
    pre_audit = json.loads(Path(snapshot["audit"]).read_text())
    text = paper.read_text()
    checks = []

    def check(name, passed, detail):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    check("paper_hash", sha256(paper) == audit["output_sha256"] == update["paper_sha256"], sha256(paper))
    check("audit_hash", sha256(audit_path) == update["audit_sha256"], sha256(audit_path))
    check("schema_v13", audit["schema_version"] == update["schema_version"] == "a8-rk-paper-sync-v13", audit["schema_version"])
    check("pre_paper_snapshot", sha256(snapshot["paper"]) == snapshot["paper_sha256"] == update["pre_paper_sha256"], snapshot["paper_sha256"])
    check("pre_audit_snapshot", sha256(snapshot["audit"]) == snapshot["audit_sha256"] == update["pre_audit_sha256"], snapshot["audit_sha256"])
    check("a7_unchanged", sha256(a7) == sha256(snapshot["a7"]) == snapshot["a7_sha256"] == update["a7_sha256"], sha256(a7))
    check("independent_complete", verification["status"] == "PASS" and verification["checks_passed"] == verification["checks_total"] == 84 and not verification["failures"], f"{verification['checks_passed']}/{verification['checks_total']}")
    check("finalization_complete", finalization["status"] == "PASS_COMPLETE_RETROSPECTIVE_HISTGB_DIAGNOSTIC" and finalization["checks_passed"] == finalization["checks_total"] == 33 and not finalization["failures"], f"{finalization['checks_passed']}/{finalization['checks_total']}")
    check("negative_gate", summary["original_rk_g1_pass"] is False and summary["diagnostic_favors_ribokinetic_all"] is False and update["original_rk_g1_pass"] is False, False)
    check("non_submittable", audit["scientific_scope"]["submittable"] is False and update["submittable"] is False, False)
    check("heading_order", text.count("### 6.8 Same-backbone") == 1 and text.count("### 6.9 Occupancy-derived") == 1 and text.count("### 6.10 Independent functional") == 1 and text.index("### 6.8") < text.index("### 6.9") < text.index("### 6.10"), True)
    check("retrospective_label", "**Retrospective HistGB fairness diagnostic.**" in text and "explicitly label it retrospective rather than preregistered" in text, True)
    check("uncertainty_language", "HistGB retained the more favorable point estimates, but both intervals include zero" in text and "neither a mechanism advantage nor a statistically resolved HistGB win is supported" in text, True)
    check("original_gate_language", "The original RK-G1 remains false." in text and "Thus, the preregistered RK-G1 criterion was not met." in text, True)
    check("verification_counts", "Independent raw-input verification passed **84/84 checks**, finalization passed **33/33 checks**, and the retained functional-comparison tests passed **7/7**." in text, True)

    rows = {row["metric"]: row for row in summary["comparisons"] if row["partition"] == "sequence_ood"}
    for metric in ["spearman", "cluster_balanced_mse"]:
        row = rows[metric]
        for field in ["point_delta", "ci95_low", "ci95_high"]:
            check(f"number:{metric}:{field}", signed(row[field]) in text, signed(row[field]))
        check(f"holm:{metric}", f"Holm-adjusted p = {row['holm_pvalue_within_partition']:.3f}" in text, row["holm_pvalue_within_partition"])
    for label, path in [
        ("RK08 HistGB diagnostic summary", summary_path),
        ("RK08 HistGB diagnostic independent verifier", verification_path),
        ("RK08 HistGB diagnostic finalization", finalization_path),
    ]:
        check(f"evidence:{label}", f"| {label} | `{sha256(path)}` |" in text, sha256(path))
    for key in ["rk08_histgb_summary", "rk08_histgb_independent", "rk08_histgb_finalization"]:
        path = Path(audit["source_paths"][key])
        check(f"audit_source:{key}", audit["source_sha256"][key] == sha256(path), sha256(path))
    check("generated_sections", audit["generated_sections"][:len(pre_audit["generated_sections"])] == pre_audit["generated_sections"] and audit["generated_sections"][-2:] == ["6.8 RK08 retrospective HistGB fairness diagnostic", "8.1 RK08 HistGB evidence anchors"], audit["generated_sections"][-2:])
    check("pending_preserved", audit["pending_preserved"] == pre_audit["pending_preserved"], True)
    check("old_sources_preserved", all(audit["source_paths"].get(key) == value for key, value in pre_audit["source_paths"].items()) and all(audit["source_sha256"].get(key) == value for key, value in pre_audit["source_sha256"].items()), True)
    check("old_scope_preserved", all(audit["scientific_scope"].get(key) == value for key, value in pre_audit["scientific_scope"].items()), True)

    old_note = "*Note.* CB-MSE denotes cluster-balanced mean squared error; lower values are better. Spearman and row R² were computed on the same 1,336 OOD constructs. The full-proxy ridge remained the development-selected primary baseline. HistGB is reported descriptively and was not used for post hoc primary-model selection."
    new_note = "*Note.* CB-MSE denotes cluster-balanced mean squared error; lower values are better. Spearman and row R² were computed on the same 1,336 OOD constructs. The full-proxy ridge remained the development-selected primary baseline. A separate retrospective paired diagnostic against HistGB is reported below and does not replace the preregistered gate or select a new primary model."
    old_paragraph = "The all-channel model did not outperform the full-proxy ridge on either OOD endpoint. Its Spearman difference was -0.025779 (95% CI [-0.071103, 0.019376]; Holm-adjusted p = 0.522), and its CB-MSE difference was -0.025572 (95% CI [-0.124069, 0.076207]; Holm-adjusted p = 0.595). Thus, the preregistered RK-G1 criterion was not met. The low absolute R² values and the more favorable HistGB point estimates further preclude an SOTA or broad superiority claim."
    spearman = rows["spearman"]
    mse = rows["cluster_balanced_mse"]
    diagnostic = old_paragraph + "\n\n**Retrospective HistGB fairness diagnostic.** The frozen HistGB predictions had been computed but omitted from the original paired gate. Without refitting, changing splits or selecting a checkpoint, we therefore added the all-channel-minus-HistGB comparison and explicitly label it retrospective rather than preregistered. On sequence-OOD, the Spearman difference was **" + signed(spearman["point_delta"]) + "** (95% CI **[" + signed(spearman["ci95_low"]) + ", " + signed(spearman["ci95_high"]) + "]**; Holm-adjusted p = " + f"{spearman['holm_pvalue_within_partition']:.3f}" + "), and the CB-MSE difference was **" + signed(mse["point_delta"]) + "** (95% CI **[" + signed(mse["ci95_low"]) + ", " + signed(mse["ci95_high"]) + "]**; Holm-adjusted p = " + f"{mse['holm_pvalue_within_partition']:.3f}" + "). HistGB retained the more favorable point estimates, but both intervals include zero: neither a mechanism advantage nor a statistically resolved HistGB win is supported. The original RK-G1 remains false. Independent raw-input verification passed **84/84 checks**, finalization passed **33/33 checks**, and the retained functional-comparison tests passed **7/7**."
    evidence = "| RK08 HistGB diagnostic summary | `" + sha256(summary_path) + "` |\n| RK08 HistGB diagnostic independent verifier | `" + sha256(verification_path) + "` |\n| RK08 HistGB diagnostic finalization | `" + sha256(finalization_path) + "` |\n"
    reconstructed = text.replace(new_note, old_note).replace(diagnostic, old_paragraph).replace(evidence, "")
    check("only_authorized_paper_delta", reconstructed == pre_paper, {"reconstructed_sha256": hashlib.sha256(reconstructed.encode()).hexdigest(), "pre_sha256": sha256(snapshot["paper"])})
    check("single_diagnostic", text.count("Retrospective HistGB fairness diagnostic") == 1 and text.count("84/84 checks") == 1, True)
    failures = [row for row in checks if not row["pass"]]
    report = {
        "protocol": "a8_rk08_histgb_paper_verification_v1",
        "status": "PASS" if not failures else "FAIL",
        "paper_sha256": sha256(paper),
        "audit_sha256": sha256(audit_path),
        "checks": checks,
        "checks_passed": len(checks) - len(failures),
        "checks_total": len(checks),
        "failures": failures,
        "original_rk_g1_pass": False,
        "submittable": False,
    }
    output = repo / "paper/a8_rk08_histgb_paper_verification.json"
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "paper_sha256": report["paper_sha256"], "output": str(output)}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
