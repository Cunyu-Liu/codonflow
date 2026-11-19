#!/usr/bin/env python3
"""Independently verify the exact Mordstein full-recovery manuscript increment."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

HEADING = "### 6.15 Mordstein full eight-bin observed-end recovery"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--a7", type=Path, required=True)
    parser.add_argument("--download-finalization", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--finalization", type=Path, required=True)
    parser.add_argument("--update-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    text = args.paper.read_text()
    audit = json.loads(args.audit.read_text())
    summary = json.loads(args.summary.read_text())
    independent = json.loads(args.independent.read_text())
    final = json.loads(args.finalization.read_text())
    update = json.loads(args.update_report.read_text())
    checks = []

    def record(name, passed, evidence=None):
        checks.append({"check": name, "pass": bool(passed), "evidence": evidence})

    snapshot = audit["pre_rk02_full_snapshot"]
    record("snapshot_paper", sha256(Path(snapshot["paper"])) == snapshot["paper_sha256"])
    record("snapshot_audit", sha256(Path(snapshot["audit"])) == snapshot["audit_sha256"])
    record("snapshot_a7", sha256(Path(snapshot["a7"])) == snapshot["a7_sha256"] == sha256(args.a7))
    record("current_output_hash", audit["output_sha256"] == sha256(args.paper))
    record("update_hashes", update["paper_sha256"] == sha256(args.paper) and
           update["audit_sha256"] == sha256(args.audit) and update["summary_sha256"] == sha256(args.summary) and
           update["independent_sha256"] == sha256(args.independent) and update["finalization_sha256"] == sha256(args.finalization))
    record("section_once", text.count(HEADING) == 1)
    record("section_before_discussion", text.index(HEADING) < text.index("## 7. Discussion"))
    record("generated_sections", "6.15 Mordstein full eight-bin observed-end recovery" in audit["generated_sections"] and
           "8.1 RK02 Mordstein observed-end evidence anchors" in audit["generated_sections"])
    record("independent_pass", independent["status"] == "PASS" and independent["passed"] == independent["total"])
    record("finalization_pass", final["status"] == "PASS" and final["passed"] == final["total"])
    record("finalization_binds_evidence", final["summary_sha256"] == sha256(args.summary) and
           final["independent_sha256"] == sha256(args.independent))
    total_pairs = sum(row["reads_scanned"] for row in summary["exact_collection"])
    r1_valid = sum(row["r1_orf_valid_reads"] for row in summary["exact_collection"])
    r2_valid = sum(row["r2_orf_valid_reads"] for row in summary["exact_collection"])
    input_bytes = sum(row["bytes"] for row in summary["input_files"])
    section = text.split(HEADING, 1)[1].split("## 7. Discussion", 1)[0]
    for name, value in [
        ("input", f"8 runs / 16 mates / {input_bytes:,} bytes"),
        ("raw_pairs", f"{total_pairs:,}"),
        ("orf_valid", f"{r1_valid:,} / {r2_valid:,}"),
        ("centroids", f"{summary['r1_centroids']} / {summary['r2_centroids']}"),
        ("retained", str(summary["variants_retained"])),
        ("links", str(summary["mutual_best_links"])),
        ("assigned", f"{summary['selected_r1_assigned_reads']:,}"),
        ("audit_rows", f"{independent['audit_rows_reassigned']:,}"),
    ]:
        record(f"table_{name}", value in section)
    record("raw_pairs_match_independent", independent["raw_pairs_recounted"] == total_pairs)
    record("independent_check_text", f"passed {independent['passed']}/{independent['total']} checks" in section)
    record("finalization_check_text", f"finalization passed {final['passed']}/{final['total']} checks" in section)
    record("library_status_text", f"`{summary['library_recovery_status']}`" in section and
           "not evidence that 217 candidates were recovered" in section)
    record("central_gap_text", "138 nt / 46 codons" in section and "represented by Ns" in section)
    record("identity_boundary", "not author `GFP_###` identities" in section)
    record("scientific_boundaries", "no complete-CDS claim" in section and "independent functional validation" in section and
           "generator-readiness claim" in section and "SOTA claim" in section)
    for label, value in [
        ("RK02 Mordstein complete 16-file download finalization", sha256(args.download_finalization)),
        ("RK02 Mordstein full observed-end production summary", sha256(args.summary)),
        ("RK02 Mordstein full observed-end independent verification", sha256(args.independent)),
        ("RK02 Mordstein full observed-end finalization", sha256(args.finalization)),
    ]:
        record(f"anchor:{label}", f"| {label} | `{value}` |" in text)
    record("audit_recovery_hashes", audit["rk02_mordstein_full"]["summary_sha256"] == sha256(args.summary) and
           audit["rk02_mordstein_full"]["independent_sha256"] == sha256(args.independent) and
           audit["rk02_mordstein_full"]["finalization_sha256"] == sha256(args.finalization))
    record("audit_scientific_gate", audit["rk02_mordstein_full"]["library_recovery_status"] == summary["library_recovery_status"] and
           audit["rk02_mordstein_full"]["central_unobserved_nt"] == 138 and
           audit["rk02_mordstein_full"]["author_identity_recovered"] is False and
           audit["rk02_mordstein_full"]["complete_cds_recovered"] is False and
           audit["rk02_mordstein_full"]["sota_claim"] is False)
    record("pending_preserved", "Mordstein 217-candidate recovery and author-variant identity mapping remain unresolved" in audit["pending_preserved"])
    record("non_submittable", "non-submittable working manuscript" in text and update["non_submittable_preserved"] is True)
    record("a7_unchanged", sha256(args.a7) == "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423")
    passed = sum(item["pass"] for item in checks)
    report = {
        "schema": "a8-rk02-mordstein-full-paper-independent-verification-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS" if passed == len(checks) else "FAIL",
        "checks": checks, "checks_passed": passed, "checks_total": len(checks),
        "paper_sha256": sha256(args.paper), "audit_sha256": sha256(args.audit),
        "summary_sha256": sha256(args.summary), "independent_sha256": sha256(args.independent),
        "finalization_sha256": sha256(args.finalization),
        "library_recovery_status": summary["library_recovery_status"],
        "production_paper_script_imported": False,
        "scope": "exact full observed-end increment, provenance and scientific boundaries; not a full manuscript review",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, indent=2))
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
