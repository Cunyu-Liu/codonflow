#!/usr/bin/env python3
"""Independent exact-increment verification for the A8 proxy-results addition."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

HEADING = "### 6.16 Fixed-GFP observed-end proxy associations and robustness"
ANCHOR_NAMES = [
    "RK02 fixed-GFP proxy primary production",
    "RK02 fixed-GFP proxy primary independent verification",
    "RK02 fixed-GFP proxy primary finalization",
    "RK02 fixed-GFP proxy robustness production",
    "RK02 fixed-GFP proxy robustness independent verification",
    "RK02 fixed-GFP proxy robustness finalization",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("paper", "audit", "update-report", "base-update-report", "primary", "primary-independent", "primary-finalization", "robustness", "robustness-independent", "robustness-finalization", "report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    update = json.loads(args.update_report.read_text())
    base_update = json.loads(args.base_update_report.read_text())
    primary = json.loads(args.primary.read_text())
    primary_ind = json.loads(args.primary_independent.read_text())
    primary_final = json.loads(args.primary_finalization.read_text())
    robust = json.loads(args.robustness.read_text())
    robust_ind = json.loads(args.robustness_independent.read_text())
    robust_final = json.loads(args.robustness_finalization.read_text())
    paper = args.paper.read_text()
    audit = json.loads(args.audit.read_text())
    base_paper = Path(update["base_snapshot"]["paper"])
    base_audit = Path(update["base_snapshot"]["audit"])
    base_a7 = Path(update["base_snapshot"]["a7"])
    checks = []

    def check(name, condition, evidence=None):
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})

    check("update_pending", update["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION")
    check("paper_update_hashes", update["paper_sha256"] == sha256(args.paper) and update["audit_sha256"] == sha256(args.audit))
    check("base_update_binding", update["base_update_report_sha256"] == sha256(args.base_update_report) and base_update["paper_sha256"] == update["base_snapshot"]["paper_sha256"] and base_update["audit_sha256"] == update["base_snapshot"]["audit_sha256"])
    check("base_snapshots_exist_and_hash", sha256(base_paper) == update["base_snapshot"]["paper_sha256"] and sha256(base_audit) == update["base_snapshot"]["audit_sha256"] and sha256(base_a7) == update["base_snapshot"]["a7_sha256"])
    check("a7_unchanged_authoritative_hash", sha256(base_a7) == "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423")
    check("heading_once_before_discussion", paper.count(HEADING) == 1 and paper.index(HEADING) < paper.index("## 7. Discussion"))
    check("primary_gates_18_12", primary_ind["status"] == primary_final["status"] == "PASS" and primary_ind["checks_total"] == primary_ind["checks_passed"] == 18 and primary_final["checks_total"] == primary_final["checks_passed"] == 12)
    check("robustness_gates_8_8", robust_ind["status"] == robust_final["status"] == "PASS" and robust_ind["checks_total"] == robust_ind["checks_passed"] == 8 and robust_final["checks_total"] == robust_final["checks_passed"] == 8)
    check("primary_hash_binding", primary_final["production_sha256"] == sha256(args.primary) and primary_final["independent_sha256"] == sha256(args.primary_independent) and update["primary_sha256"] == sha256(args.primary) and update["primary_independent_sha256"] == sha256(args.primary_independent) and update["primary_finalization_sha256"] == sha256(args.primary_finalization))
    check("robustness_hash_binding", robust_final["production_sha256"] == sha256(args.robustness) and robust_final["independent_sha256"] == sha256(args.robustness_independent) and update["robustness_sha256"] == sha256(args.robustness) and update["robustness_independent_sha256"] == sha256(args.robustness_independent) and update["robustness_finalization_sha256"] == sha256(args.robustness_finalization))
    gc3 = primary["associations"]["gc3_observed_5prime"]
    gc = primary["associations"]["gc_observed_5prime"]
    cpg = primary["associations"]["cpg_per_100nt_observed_5prime"]["spearman"]
    for label, item in (("gc3_spearman", gc3["spearman"]), ("gc3_pearson", gc3["pearson"]), ("gc_spearman", gc["spearman"]), ("gc_pearson", gc["pearson"]), ("cpg_spearman", cpg)):
        check(f"paper_{label}_values", f"{item['observed']:.9f}" in paper and f"{item['ci95_percentile'][0]:.9f}" in paper and f"{item['ci95_percentile'][1]:.9f}" in paper, item["observed"])
    check("paper_primary_holm_values", f"{gc3['spearman']['holm_p']:.9g}" in paper and f"{gc['spearman']['holm_p']:.9g}" in paper)
    support = robust["support_sensitivity"]
    check("paper_support_thresholds_and_n", all(str(item["threshold"]) in paper and str(item["n"]) in paper for item in support))
    for feature, label in (("gc3_observed_5prime", "gc3"), ("gc_observed_5prime", "gc")):
        values = [item["features"][feature]["observed"] for item in support]
        part = robust["partial_spearman_controlling_depth"][feature]
        check(f"paper_{label}_robustness_values", f"{min(values):.9f}" in paper and f"{max(values):.9f}" in paper and f"{part['observed']:.9f}" in paper and f"{part['ci95_percentile'][0]:.9f}" in paper and f"{part['ci95_percentile'][1]:.9f}" in paper)
    depth = robust["depth_associations"]["flowseq_score_r1_only"]
    check("paper_depth_score_values", f"{depth['observed']:.9f}" in paper and f"{depth['ci95_percentile'][0]:.9f}" in paper and f"{depth['ci95_percentile'][1]:.9f}" in paper)
    check("proxy_not_uninformative_but_no_increment", "not uninformative proxies" in paper and "no such incremental model comparison was performed" in paper)
    check("posthoc_not_new_gate", "post-hoc" in paper and "did not alter the primary endpoints or create a new acceptance gate" in paper)
    check("scientific_boundaries", all(text in paper for text in ("do not establish complete CDS sequence", "causality", "protein/study OOD transfer", "SOTA", "do not close RK-G1", "authorize expensive generator training")))
    check("paper_has_no_complete_217_claim", "152 complete CDS" not in paper and "217 recovered" not in paper)
    check("evidence_anchors", all(paper.count(f"| {name} |") == 1 for name in ANCHOR_NAMES))
    stripped = paper
    start = stripped.index(HEADING)
    end = stripped.index("## 7. Discussion", start)
    stripped = stripped[:start] + stripped[end:]
    evidence_anchors = [
        ("primary production", args.primary),
        ("primary independent verification", args.primary_independent),
        ("primary finalization", args.primary_finalization),
        ("robustness production", args.robustness),
        ("robustness independent verification", args.robustness_independent),
        ("robustness finalization", args.robustness_finalization),
    ]
    anchor_block = "\n" + "".join(
        f"| RK02 fixed-GFP proxy {label} | `{sha256(path)}` |\n"
        for label, path in evidence_anchors
    )
    check("proxy_evidence_anchor_count", stripped.count(anchor_block) == 1)
    stripped = stripped.replace(anchor_block, "", 1)
    check("only_section_and_anchors_added_to_paper", stripped == base_paper.read_text())
    base_audit_obj = json.loads(base_audit.read_text())
    reduced_audit = dict(audit)
    reduced_audit.pop("last_increment", None)
    reduced_audit["output_sha256"] = base_audit_obj["output_sha256"]
    check("only_output_and_last_increment_changed_in_audit", reduced_audit == base_audit_obj)
    increment = audit.get("last_increment", {})
    check("audit_increment_hashes_and_scope", increment.get("paper_sha256") == sha256(args.paper) and increment.get("primary_sha256") == sha256(args.primary) and increment.get("robustness_sha256") == sha256(args.robustness) and increment.get("submittable") is False and "no causal/protein-OOD/mechanism-increment/SOTA claim" in increment.get("scientific_scope", ""))
    check("update_not_submittable", update["submittable"] is False)
    failed = [item["name"] for item in checks if not item["pass"]]
    report = {
        "schema": "a8-rk02-proxy-paper-independent-verification-v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS" if not failed else "FAIL",
        "checks_total": len(checks), "checks_passed": len(checks) - len(failed), "failed_checks": failed,
        "paper_sha256": sha256(args.paper), "audit_sha256": sha256(args.audit), "update_report_sha256": sha256(args.update_report),
        "base_update_report_sha256": sha256(args.base_update_report),
        "checks": checks, "submittable": False,
    }
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "failed": failed}, indent=2))
    raise SystemExit(0 if not failed else 1)


if __name__ == "__main__":
    main()
