#!/usr/bin/env python3
"""Finalize the independently verified CDGB negative source audit."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--verification", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    verify = json.loads(args.verification.read_text(encoding="utf-8"))
    assessment = audit.get("source_assessment", {})
    identity = audit.get("candidate_doi_identity", {})

    checks = {
        "production_source_audit_complete": (
            audit.get("status") == "SOURCE_IDENTITY_UNRESOLVED_OFFICIAL_EXECUTION_NOT_AUTHORIZED"
            and audit.get("query_count_succeeded") == audit.get("query_count_expected") == 9
            and not audit.get("query_failures")
        ),
        "independent_verification_pass": (
            verify.get("status") == "PASS"
            and verify.get("checks_passed") == verify.get("checks_total") == 8
            and verify.get("independent_production_import") is False
            and verify.get("independent_recomputation_from_frozen_raw_responses") is True
        ),
        "candidate_identity_conflict_preserved": (
            identity.get("conflict") is True
            and identity.get("resolved") is False
            and assessment.get("candidate_bibliographic_identity_resolved") is False
            and assessment.get("exact_candidate_title_match_count") == 0
        ),
        "official_execution_not_authorized_or_performed": (
            assessment.get("official_repository_verified") is False
            and assessment.get("official_source_commit") is None
            and assessment.get("build_or_execution_authorized") is False
            and assessment.get("official_build_performed") is False
            and assessment.get("official_execution_performed") is False
            and assessment.get("official_sequence_output_count") == 0
            and assessment.get("performance_result_count") == 0
        ),
        "bounded_scientific_wording": (
            assessment.get("method_invalid_claim") is False
            and assessment.get("implementation_nonexistence_claim") is False
            and verify.get("main_baseline_comparison") is False
            and verify.get("functional_ood") is False
            and verify.get("sota_claim") is False
        ),
        "evidence_hashes_current": (
            verify.get("production_audit_sha256") == sha256(args.audit)
        ),
    }
    status = "SOURCE_IDENTITY_UNRESOLVED_OFFICIAL_EXECUTION_NOT_AUTHORIZED" if all(checks.values()) else "FINALIZATION_FAILED"
    report = {
        "protocol": "a8_rk05_cdgb_source_finalization_v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": status,
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "science_flags": {
            "source_audit_complete": status != "FINALIZATION_FAILED",
            "candidate_bibliographic_identity_resolved": False,
            "candidate_doi_title_conflict": True,
            "official_repository_verified": False,
            "official_fixed_commit": None,
            "official_build_complete": False,
            "official_execution_complete": False,
            "official_sequence_output_count": 0,
            "performance_result_count": 0,
            "main_baseline_comparison": False,
            "functional_ood": False,
            "sota_claim": False,
            "method_invalid_claim": False,
            "implementation_nonexistence_claim": False,
            "ppt_record_ready": status != "FINALIZATION_FAILED",
            "paper_sync_ready": status != "FINALIZATION_FAILED",
        },
        "evidence": {
            "audit": {"path": str(args.audit), "sha256": sha256(args.audit)},
            "independent_verification": {"path": str(args.verification), "sha256": sha256(args.verification)},
        },
        "conclusion": (
            "CDGB remains excluded from official execution because the candidate bibliographic identity is unresolved and its embedded DOI resolves to another paper. "
            "This bounded source audit is complete; no official CDGB sequence, runtime, quality metric, main-baseline comparison, OOD result, or SOTA claim was produced."
        ),
        "next_gate": "Obtain an authoritative CDGB citation and author/publisher-linked official repository with an immutable commit before build or execution.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status, "checks": f"{report['checks_passed']}/{report['checks_total']}",
        "ppt_record_ready": report["science_flags"]["ppt_record_ready"],
        "output": str(args.output), "sha256": sha256(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if status != "FINALIZATION_FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
