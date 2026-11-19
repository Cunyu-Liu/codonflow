#!/usr/bin/env python3
"""Append only a finalized Mordstein observed-end recovery result to A8."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

HEADING = "### 6.15 Mordstein full eight-bin observed-end recovery"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--a7", type=Path, required=True)
    parser.add_argument("--base-update-report", type=Path, required=True)
    parser.add_argument("--download-finalization", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--finalization", type=Path, required=True)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--update-report", type=Path, required=True)
    args = parser.parse_args()
    if args.update_report.exists():
        raise FileExistsError(args.update_report)
    base = json.loads(args.base_update_report.read_text())
    if sha256(args.paper) != base["paper_sha256"] or sha256(args.audit) != base["audit_sha256"]:
        raise ValueError("A8 base does not match the verified RK-12 update")
    if not base["non_submittable_preserved"] or base["sota_claim"]:
        raise ValueError("Unsafe manuscript base state")
    download = json.loads(args.download_finalization.read_text())
    summary = json.loads(args.summary.read_text())
    independent = json.loads(args.independent.read_text())
    final = json.loads(args.finalization.read_text())
    if not (download["status"] == "PASS" and download["expected_runs"] == 8 and
            download["expected_files"] == download["passed_files"] == 16 and download["failed_files"] == 0):
        raise ValueError("The complete 16-file input gate has not passed")
    if not (summary["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION" and len(summary["runs"]) == 8):
        raise ValueError("Unexpected full-recovery production state")
    if not (independent["status"] == "PASS" and independent["scope"] == "full" and
            independent["passed"] == independent["total"] == len(independent["checks"])):
        raise ValueError("Independent full-recovery verification has not passed")
    if not (final["status"] == "PASS" and final["scope"] == "full" and
            final["passed"] == final["total"] == len(final["checks"])):
        raise ValueError("Full-recovery finalization has not passed")
    if sha256(args.summary) != final["summary_sha256"] or sha256(args.independent) != final["independent_sha256"]:
        raise ValueError("Finalization does not bind the supplied recovery evidence")
    text = args.paper.read_text()
    if HEADING in text:
        raise ValueError("Mordstein full-recovery section already exists")
    args.snapshot_dir.mkdir(parents=True, exist_ok=False)
    snapshot_paper = args.snapshot_dir / "CodonFlow_preprint_A8_v18.md"
    snapshot_audit = args.snapshot_dir / "a8_rk_paper_sync_audit_v18.json"
    snapshot_a7 = args.snapshot_dir / "CodonFlow_preprint_A7.md"
    snapshot_paper.write_bytes(args.paper.read_bytes())
    snapshot_audit.write_bytes(args.audit.read_bytes())
    snapshot_a7.write_bytes(args.a7.read_bytes())

    total_pairs = sum(row["reads_scanned"] for row in summary["exact_collection"])
    r1_valid = sum(row["r1_orf_valid_reads"] for row in summary["exact_collection"])
    r2_valid = sum(row["r2_orf_valid_reads"] for row in summary["exact_collection"])
    input_bytes = sum(row["bytes"] for row in summary["input_files"])
    if independent["raw_pairs_recounted"] != total_pairs:
        raise ValueError("Independent raw-pair total differs from production")
    rows = [
        ("Verified input", f"8 runs / 16 mates / {input_bytes:,} bytes"),
        ("Raw mate pairs recounted", f"{total_pairs:,}"),
        ("ORF-valid R1 / R2 reads", f"{r1_valid:,} / {r2_valid:,}"),
        ("R1 / R2 centroids", f"{summary['r1_centroids']} / {summary['r2_centroids']}"),
        ("R1 variants retained at support >= 1,000", f"{summary['variants_retained']}"),
        ("Mutual-best R1-R2 links", f"{summary['mutual_best_links']}"),
        ("R1 reads assigned to retained variants", f"{summary['selected_r1_assigned_reads']:,}"),
        ("Raw-read audit rows independently reassigned", f"{independent['audit_rows_reassigned']:,}"),
    ]
    table = "\n".join(f"| {name} | {value} |" for name, value in rows)
    sensitivity = summary["support_threshold_sensitivity"]
    sensitivity_text = ", ".join(f"{key}: {sensitivity[key]}" for key in sorted(sensitivity, key=int))
    section = f"""{HEADING}

I completed the authorized full eight-bin HEK293 Flow-seq recovery only after all 16 ENA mates passed exact byte-size and MD5 gates. The calculation used `max_reads=0`, retained every scanned pair, and separately preserved exact-count caches, centroid references, variant counts and a frozen 200-read audit sample per bin. The resulting evidence is an **observed-end recovery**, not a complete-CDS or author-variant identity reconstruction.

| Quantity | Verified value |
|---|---:|
{table}

The independent verifier re-read every raw mate pair, recounted ORF-valid reads, checked all input and cache hashes, validated the centroid/reference/table relationships and independently reassigned all 1,600 raw-read audit rows. It passed {independent['passed']}/{independent['total']} checks; finalization passed {final['passed']}/{final['total']} checks and reran the 7 contract tests. These passes establish computational consistency, not library completeness.

At the frozen support threshold of 1,000 assigned R1 reads, **{summary['variants_retained']} R1 variants** were retained and **{summary['mutual_best_links']} mutual-best R1-R2 links** were formed. The scientific library status therefore remains `{summary['library_recovery_status']}`; it is not evidence that 217 candidates were recovered. Support-threshold sensitivity (threshold: retained R1 variants) was {sensitivity_text}. Only the observed 5′ 300-nt and linked 3′ 279-nt ends are supported directly. The central **138 nt / 46 codons** remain unobserved and are represented by Ns in paired-end references. Reconstructed `CF_MORD_*` identifiers are not author `GFP_###` identities. This result supplies no complete-CDS claim, independent functional validation, generator-readiness claim or SOTA claim.

"""
    marker = "## 7. Discussion"
    if text.count(marker) != 1:
        raise ValueError("Discussion insertion marker missing")
    text = text.replace(marker, section + marker, 1)
    anchors = f"""| RK02 Mordstein complete 16-file download finalization | `{sha256(args.download_finalization)}` |
| RK02 Mordstein full observed-end production summary | `{sha256(args.summary)}` |
| RK02 Mordstein full observed-end independent verification | `{sha256(args.independent)}` |
| RK02 Mordstein full observed-end finalization | `{sha256(args.finalization)}` |
"""
    anchor_marker = "\nA7 is retained as the prior manuscript snapshot."
    if text.count(anchor_marker) != 1:
        raise ValueError("Evidence anchor marker missing")
    text = text.replace(anchor_marker, "\n" + anchors + anchor_marker, 1)
    audit = json.loads(args.audit.read_text())
    audit["generated_sections"].extend([
        "6.15 Mordstein full eight-bin observed-end recovery",
        "8.1 RK02 Mordstein observed-end evidence anchors",
    ])
    pending = "Mordstein 217-candidate recovery and author-variant identity mapping remain unresolved"
    if pending not in audit["pending_preserved"]:
        audit["pending_preserved"].append(pending)
    audit["pre_rk02_full_snapshot"] = {
        "paper": str(snapshot_paper), "paper_sha256": sha256(snapshot_paper),
        "audit": str(snapshot_audit), "audit_sha256": sha256(snapshot_audit),
        "a7": str(snapshot_a7), "a7_sha256": sha256(snapshot_a7),
    }
    audit["rk02_mordstein_full"] = {
        "download_finalization_sha256": sha256(args.download_finalization),
        "summary_sha256": sha256(args.summary),
        "independent_sha256": sha256(args.independent),
        "finalization_sha256": sha256(args.finalization),
        "raw_pairs": total_pairs,
        "variants_retained": summary["variants_retained"],
        "mutual_best_links": summary["mutual_best_links"],
        "library_recovery_status": summary["library_recovery_status"],
        "central_unobserved_nt": 138,
        "author_identity_recovered": False,
        "complete_cds_recovered": False,
        "sota_claim": False,
    }
    atomic(args.paper, text)
    audit["output_sha256"] = sha256(args.paper)
    atomic(args.audit, json.dumps(audit, indent=2) + "\n")
    report = {
        "schema": "a8-rk02-mordstein-full-paper-update-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS",
        "base_update_report_sha256": sha256(args.base_update_report),
        "paper_sha256": sha256(args.paper), "audit_sha256": sha256(args.audit),
        "summary_sha256": sha256(args.summary), "independent_sha256": sha256(args.independent),
        "finalization_sha256": sha256(args.finalization),
        "section": HEADING, "snapshot": audit["pre_rk02_full_snapshot"],
        "library_recovery_status": summary["library_recovery_status"],
        "variants_retained": summary["variants_retained"],
        "mutual_best_links": summary["mutual_best_links"],
        "non_submittable_preserved": True, "complete_cds_claim": False,
        "author_identity_claim": False, "sota_claim": False,
    }
    args.update_report.parent.mkdir(parents=True, exist_ok=True)
    args.update_report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
