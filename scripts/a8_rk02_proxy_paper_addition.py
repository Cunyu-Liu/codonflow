#!/usr/bin/env python3
"""Append the finalized fixed-GFP observed-end proxy analysis to A8 after v19."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path

HEADING = "### 6.16 Fixed-GFP observed-end proxy associations and robustness"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_final(production, independent, finalization, production_path, independent_path, independent_checks, final_checks):
    if independent["status"] != "PASS" or not (independent["checks_total"] == independent["checks_passed"] == independent_checks):
        raise ValueError("independent gate mismatch")
    if finalization["status"] != "PASS" or not (finalization["checks_total"] == finalization["checks_passed"] == final_checks):
        raise ValueError("finalization gate mismatch")
    if finalization["production_sha256"] != sha256(production_path) or finalization["independent_sha256"] != sha256(independent_path):
        raise ValueError("evidence hash mismatch")
    if production.get("scientific_interpretation", {}).get("protein_ood_evaluation", False):
        raise ValueError("OOD scope must remain false")


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("paper", "audit", "a7", "base-update-report", "primary", "primary-independent", "primary-finalization", "robustness", "robustness-independent", "robustness-finalization", "snapshot-dir", "update-report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    base = json.loads(args.base_update_report.read_text())
    if sha256(args.paper) != base["paper_sha256"] or sha256(args.audit) != base["audit_sha256"]:
        raise ValueError("paper/audit do not match the v19 base update")
    if HEADING in args.paper.read_text():
        raise ValueError("section already exists")
    primary = json.loads(args.primary.read_text())
    primary_ind = json.loads(args.primary_independent.read_text())
    primary_final = json.loads(args.primary_finalization.read_text())
    robust = json.loads(args.robustness.read_text())
    robust_ind = json.loads(args.robustness_independent.read_text())
    robust_final = json.loads(args.robustness_finalization.read_text())
    require_final(primary, primary_ind, primary_final, args.primary, args.primary_independent, 18, 12)
    if not (robust_ind["status"] == "PASS" and robust_ind["checks_total"] == robust_ind["checks_passed"] == 8):
        raise ValueError("robustness independent gate is not 8/8")
    if not (robust_final["status"] == "PASS" and robust_final["checks_total"] == robust_final["checks_passed"] == 8):
        raise ValueError("robustness finalization is not 8/8")
    if robust_final["production_sha256"] != sha256(args.robustness) or robust_final["independent_sha256"] != sha256(args.robustness_independent):
        raise ValueError("robustness hash mismatch")
    if robust["boundaries"]["causal_inference"] or robust["boundaries"]["protein_ood_evaluation"] or robust["boundaries"]["generator_training_authorized"]:
        raise ValueError("post-hoc scope was upgraded")
    args.snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_paper = args.snapshot_dir / "CodonFlow_preprint_A8_v19.md"
    snapshot_audit = args.snapshot_dir / "a8_rk_paper_sync_audit_v19.json"
    snapshot_a7 = args.snapshot_dir / "CodonFlow_preprint_A7_v19base.md"
    for source, target in ((args.paper, snapshot_paper), (args.audit, snapshot_audit), (args.a7, snapshot_a7)):
        if target.exists():
            raise FileExistsError(target)
        shutil.copy2(source, target)
    gc3 = primary["associations"]["gc3_observed_5prime"]
    gc = primary["associations"]["gc_observed_5prime"]
    cpg = primary["associations"]["cpg_per_100nt_observed_5prime"]["spearman"]
    support = robust["support_sensitivity"]
    partial = robust["partial_spearman_controlling_depth"]
    depth_score = robust["depth_associations"]["flowseq_score_r1_only"]

    def row(label, item, p):
        return f"| {label} | {item['observed']:.9f} | [{item['ci95_percentile'][0]:.9f}, {item['ci95_percentile'][1]:.9f}] | {p} |"

    support_lines = []
    for feature, label in (("gc3_observed_5prime", "GC3"), ("gc_observed_5prime", "GC")):
        values = [item["features"][feature]["observed"] for item in support]
        part = partial[feature]
        support_lines.append(
            f"| {label} | {min(values):.9f} to {max(values):.9f} | {str(robust['positive_ci_all_thresholds'][feature]).lower()} | "
            f"{part['observed']:.9f} [{part['ci95_percentile'][0]:.9f}, {part['ci95_percentile'][1]:.9f}] |"
        )
    section = f"""{HEADING}

I next asked whether the recovered observed ends contain any simple sequence signal at all. The frozen primary analysis used the {primary['n_variants']} R1 variants passing the original total-read support threshold of at least 1,000 and the R1-assigned HEK293 intronless Flow-seq score, defined as the read-count-weighted mean of fluorescence-bin indices 1–8. The feature window was observed CDS 4–303 only. Two primary hypotheses tested Spearman associations for GC3 and GC, using 20,000 paired-variant bootstraps for percentile 95% CIs, 20,000 label permutations for two-sided p values, and Holm correction across exactly those two hypotheses. Pearson correlations and CpG density were secondary.

| Feature / metric | Correlation | 95% CI | Multiplicity |
|---|---:|---:|---:|
{row('GC3 / Spearman', gc3['spearman'], f"Holm p={gc3['spearman']['holm_p']:.9g}")}
{row('GC3 / Pearson', gc3['pearson'], 'secondary')}
{row('GC / Spearman', gc['spearman'], f"Holm p={gc['spearman']['holm_p']:.9g}")}
{row('GC / Pearson', gc['pearson'], 'secondary')}
{row('CpG density / Spearman', cpg, 'secondary; unadjusted')}

Both primary associations were positive with CIs excluding zero. Thus, within this fixed-GFP observed-end dataset, GC3 and GC are **not uninformative proxies**. This is an association result, not evidence that a mechanism model adds predictive value beyond GC/GC3, CAI, folding or other simple features; no such incremental model comparison was performed here.

A separately frozen **post-hoc** robustness analysis repeated the Spearman estimates at total-read thresholds {', '.join(str(item['threshold']) for item in support)}. The corresponding sample sizes were {', '.join(str(item['n']) for item in support)}. It also quantified the association between log10(total reads) and score (Spearman={depth_score['observed']:.9f}, 95% CI [{depth_score['ci95_percentile'][0]:.9f}, {depth_score['ci95_percentile'][1]:.9f}]) and computed descriptive partial Spearman correlations after rank-residual adjustment for read depth.

| Feature | Observed Spearman range across 7 support thresholds | All 7 CI lower bounds > 0 | Depth-adjusted partial Spearman [95% CI] |
|---|---:|---:|---:|
{chr(10).join(support_lines)}

The robustness analysis did not alter the primary endpoints or create a new acceptance gate. All results remain limited to recovered observed ends from one GFP library: they do not establish complete CDS sequence, author `GFP_###` identity, causality, protein/study OOD transfer, functional generation quality or SOTA. They do not close RK-G1 or authorize expensive generator training. Independent recomputation passed {primary_ind['checks_passed']}/{primary_ind['checks_total']} primary checks and {robust_ind['checks_passed']}/{robust_ind['checks_total']} robustness checks; finalization passed {primary_final['checks_passed']}/{primary_final['checks_total']} and {robust_final['checks_passed']}/{robust_final['checks_total']}, respectively.

"""
    text = args.paper.read_text()
    marker = "## 7. Discussion"
    if text.count(marker) != 1:
        raise ValueError("Discussion insertion marker missing")
    text = text.replace(marker, section + marker, 1)
    anchors = f"""| RK02 fixed-GFP proxy primary production | `{sha256(args.primary)}` |
| RK02 fixed-GFP proxy primary independent verification | `{sha256(args.primary_independent)}` |
| RK02 fixed-GFP proxy primary finalization | `{sha256(args.primary_finalization)}` |
| RK02 fixed-GFP proxy robustness production | `{sha256(args.robustness)}` |
| RK02 fixed-GFP proxy robustness independent verification | `{sha256(args.robustness_independent)}` |
| RK02 fixed-GFP proxy robustness finalization | `{sha256(args.robustness_finalization)}` |
"""
    anchor_marker = "\nA7 is retained as the prior manuscript snapshot."
    if text.count(anchor_marker) != 1:
        raise ValueError("Evidence anchor marker missing")
    text = text.replace(anchor_marker, "\n" + anchors + anchor_marker, 1)
    args.paper.write_text(text)
    audit = json.loads(args.audit.read_text())
    audit["output_sha256"] = sha256(args.paper)
    audit["last_increment"] = {
        "section": "6.16 Fixed-GFP observed-end proxy associations and robustness",
        "paper_sha256": sha256(args.paper),
        "primary_sha256": sha256(args.primary), "primary_independent_sha256": sha256(args.primary_independent),
        "primary_finalization_sha256": sha256(args.primary_finalization),
        "robustness_sha256": sha256(args.robustness), "robustness_independent_sha256": sha256(args.robustness_independent),
        "robustness_finalization_sha256": sha256(args.robustness_finalization),
        "scientific_scope": "fixed-GFP observed-end association only; no causal/protein-OOD/mechanism-increment/SOTA claim",
        "submittable": False,
    }
    args.audit.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n")
    report = {
        "schema": "a8-rk02-proxy-paper-update-v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS_PENDING_INDEPENDENT_VERIFICATION",
        "base_update_report_sha256": sha256(args.base_update_report),
        "paper_sha256": sha256(args.paper), "audit_sha256": sha256(args.audit),
        "base_snapshot": {"paper": str(snapshot_paper), "paper_sha256": sha256(snapshot_paper), "audit": str(snapshot_audit), "audit_sha256": sha256(snapshot_audit), "a7": str(snapshot_a7), "a7_sha256": sha256(snapshot_a7)},
        "primary_sha256": sha256(args.primary), "primary_independent_sha256": sha256(args.primary_independent), "primary_finalization_sha256": sha256(args.primary_finalization),
        "robustness_sha256": sha256(args.robustness), "robustness_independent_sha256": sha256(args.robustness_independent), "robustness_finalization_sha256": sha256(args.robustness_finalization),
        "submittable": False,
    }
    args.update_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
