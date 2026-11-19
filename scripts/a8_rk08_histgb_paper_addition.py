#!/usr/bin/env python3
"""Add the verified retrospective HistGB diagnostic to A8 as v13."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signed(value: float) -> str:
    return f"{value:+.6f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="/home/codonflow-a8-rk")
    parser.add_argument("--snapshot-dir", required=True)
    args = parser.parse_args()
    repo = Path(args.repo)
    paper = repo / "paper/CodonFlow_preprint_A8.md"
    a7 = repo / "paper/CodonFlow_preprint_A7.md"
    audit_path = repo / "paper/a8_rk_paper_sync_audit.json"
    summary_path = repo / "audits/20261118/RK08/full_function_histgb_diagnostic_summary_v1.json"
    verification_path = repo / "audits/20261118/RK08/full_function_histgb_diagnostic_verification_v1.json"
    finalization_path = repo / "audits/20261118/RK08/full_function_histgb_diagnostic_finalization_v1.json"
    summary = json.loads(summary_path.read_text())
    verification = json.loads(verification_path.read_text())
    finalization = json.loads(finalization_path.read_text())
    audit = json.loads(audit_path.read_text())
    if sha256(paper) != audit["output_sha256"]:
        raise ValueError("Current A8 differs from the v12 audit; refusing uncoordinated overwrite")
    if audit["schema_version"] != "a8-rk-paper-sync-v12":
        raise ValueError("HistGB addition requires A8 v12")
    if verification["status"] != "PASS" or verification["checks_passed"] != verification["checks_total"] or verification["failures"]:
        raise ValueError("Independent HistGB verification is not complete")
    if finalization["status"] != "PASS_COMPLETE_RETROSPECTIVE_HISTGB_DIAGNOSTIC" or finalization["failures"]:
        raise ValueError("HistGB finalization is not complete")
    if summary["diagnostic_favors_ribokinetic_all"] or summary["original_rk_g1_pass"]:
        raise ValueError("Unexpected scientific gate")

    rows = {row["metric"]: row for row in summary["comparisons"] if row["partition"] == "sequence_ood"}
    spearman = rows["spearman"]
    mse = rows["cluster_balanced_mse"]
    old_note = "*Note.* CB-MSE denotes cluster-balanced mean squared error; lower values are better. Spearman and row R² were computed on the same 1,336 OOD constructs. The full-proxy ridge remained the development-selected primary baseline. HistGB is reported descriptively and was not used for post hoc primary-model selection."
    new_note = "*Note.* CB-MSE denotes cluster-balanced mean squared error; lower values are better. Spearman and row R² were computed on the same 1,336 OOD constructs. The full-proxy ridge remained the development-selected primary baseline. A separate retrospective paired diagnostic against HistGB is reported below and does not replace the preregistered gate or select a new primary model."
    old_paragraph = "The all-channel model did not outperform the full-proxy ridge on either OOD endpoint. Its Spearman difference was -0.025779 (95% CI [-0.071103, 0.019376]; Holm-adjusted p = 0.522), and its CB-MSE difference was -0.025572 (95% CI [-0.124069, 0.076207]; Holm-adjusted p = 0.595). Thus, the preregistered RK-G1 criterion was not met. The low absolute R² values and the more favorable HistGB point estimates further preclude an SOTA or broad superiority claim."
    diagnostic_paragraph = (
        old_paragraph
        + "\n\n**Retrospective HistGB fairness diagnostic.** The frozen HistGB predictions had been computed but omitted from the original paired gate. Without refitting, changing splits or selecting a checkpoint, we therefore added the all-channel-minus-HistGB comparison and explicitly label it retrospective rather than preregistered. On sequence-OOD, the Spearman difference was **"
        + signed(spearman["point_delta"]) + "** (95% CI **[" + signed(spearman["ci95_low"]) + ", " + signed(spearman["ci95_high"]) + "]**; Holm-adjusted p = "
        + f"{spearman['holm_pvalue_within_partition']:.3f}" + "), and the CB-MSE difference was **"
        + signed(mse["point_delta"]) + "** (95% CI **[" + signed(mse["ci95_low"]) + ", " + signed(mse["ci95_high"]) + "]**; Holm-adjusted p = "
        + f"{mse['holm_pvalue_within_partition']:.3f}" + "). HistGB retained the more favorable point estimates, but both intervals include zero: neither a mechanism advantage nor a statistically resolved HistGB win is supported. The original RK-G1 remains false. Independent raw-input verification passed **84/84 checks**, finalization passed **33/33 checks**, and the retained functional-comparison tests passed **7/7**."
    )
    text = paper.read_text()
    if text.count(old_note) != 1 or text.count(old_paragraph) != 1:
        raise ValueError("Expected v12 section 6.8 anchors not found exactly once")
    text = text.replace(old_note, new_note).replace(old_paragraph, diagnostic_paragraph)
    evidence_rows = (
        "| RK08 HistGB diagnostic summary | `" + sha256(summary_path) + "` |\n"
        "| RK08 HistGB diagnostic independent verifier | `" + sha256(verification_path) + "` |\n"
        "| RK08 HistGB diagnostic finalization | `" + sha256(finalization_path) + "` |\n"
    )
    anchor = "| RK08 full artifact manifest | `dce4cbc03c826124de3706222bd844495250fc3da19a2ef42512043124c16f4b` |\n"
    if text.count(anchor) != 1:
        raise ValueError("Evidence anchor missing")
    text = text.replace(anchor, anchor + evidence_rows)

    snapshot = Path(args.snapshot_dir)
    snapshot.mkdir(parents=True, exist_ok=True)
    snapshot_paper = snapshot / "CodonFlow_preprint_A8_pre_histgb.md"
    snapshot_audit = snapshot / "a8_rk_paper_sync_audit_pre_histgb.json"
    snapshot_a7 = snapshot / "CodonFlow_preprint_A7_pre_histgb.md"
    for source, destination in [(paper, snapshot_paper), (audit_path, snapshot_audit), (a7, snapshot_a7)]:
        if destination.exists():
            if sha256(destination) != sha256(source):
                raise ValueError(f"Snapshot collision: {destination}")
        else:
            shutil.copy2(source, destination)
    pre_paper_hash = sha256(paper)
    pre_audit_hash = sha256(audit_path)
    a7_hash = sha256(a7)
    paper.write_text(text)
    audit["base_v12_paper_sha256"] = pre_paper_hash
    audit["base_v12_audit_sha256"] = pre_audit_hash
    for section in ["6.8 RK08 retrospective HistGB fairness diagnostic", "8.1 RK08 HistGB evidence anchors"]:
        if section not in audit["generated_sections"]:
            audit["generated_sections"].append(section)
    audit["pre_histgb_snapshot"] = {
        "paper": str(snapshot_paper), "paper_sha256": pre_paper_hash,
        "audit": str(snapshot_audit), "audit_sha256": pre_audit_hash,
        "a7": str(snapshot_a7), "a7_sha256": a7_hash,
    }
    audit["schema_version"] = "a8-rk-paper-sync-v13"
    audit["scientific_scope"]["rk08_histgb"] = "Retrospective paired fairness diagnostic on frozen predictions: HistGB had better sequence-OOD point estimates but both intervals crossed zero; no mechanism superiority, resolved HistGB win, new preregistered gate or generator authorization."
    audit["source_paths"].update({
        "rk08_histgb_summary": str(summary_path),
        "rk08_histgb_independent": str(verification_path),
        "rk08_histgb_finalization": str(finalization_path),
    })
    audit["source_sha256"].update({
        "rk08_histgb_summary": sha256(summary_path),
        "rk08_histgb_independent": sha256(verification_path),
        "rk08_histgb_finalization": sha256(finalization_path),
    })
    audit["output_sha256"] = sha256(paper)
    audit_path.write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n")
    update = {
        "schema_version": "a8-rk-paper-sync-v13",
        "status": "PASS_PENDING_INDEPENDENT_VERIFICATION",
        "paper_sha256": sha256(paper),
        "audit_sha256": sha256(audit_path),
        "pre_paper_sha256": pre_paper_hash,
        "pre_audit_sha256": pre_audit_hash,
        "a7_sha256": a7_hash,
        "sequence_ood_comparisons": [spearman, mse],
        "original_rk_g1_pass": False,
        "submittable": False,
    }
    update_path = repo / "paper/a8_rk08_histgb_paper_update.json"
    update_path.write_text(json.dumps(update, indent=2, allow_nan=False) + "\n")
    print(json.dumps(update, indent=2))


if __name__ == "__main__":
    main()
