#!/usr/bin/env python3
"""Independent verifier for the frozen CDGB source audit.

The production module is never imported. All bibliographic and repository facts
are recomputed from the frozen raw API responses and their byte hashes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

EXPECTED_QUERIES = {
    "crossref_candidate_title",
    "crossref_cdgb_title",
    "crossref_candidate_doi",
    "openalex_cdgb_title",
    "europepmc_cdgb_title",
    "europepmc_deoptimization_title",
    "github_cdgb_codon",
    "github_codon_deoptimization",
    "github_cdgb_protein_representation",
}
EXPECTED_DOI_TITLE = "Multimodal zero-shot learning of previously unseen epitranscriptomes from RNA-seq data"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    return re.sub(r"[^a-z0-9]+", "", value)


def titles_for(name: str, payload: dict[str, Any]) -> list[str]:
    if name.startswith("crossref_") and name != "crossref_candidate_doi":
        return [title for item in payload.get("message", {}).get("items", []) for title in item.get("title", [])]
    if name == "openalex_cdgb_title":
        return [item.get("display_name") or item.get("title") or "" for item in payload.get("results", [])]
    if name.startswith("europepmc_"):
        return [item.get("title") or "" for item in payload.get("resultList", {}).get("result", [])]
    if name.startswith("github_"):
        return [item.get("full_name") or "" for item in payload.get("items", [])]
    return list(payload.get("message", {}).get("title", []))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    production = json.loads(args.audit.read_text(encoding="utf-8"))
    candidate_title = production["candidate"]["title"]
    target = norm(candidate_title)
    manifest = production.get("raw_response_manifest", [])
    by_name = {entry["name"]: entry for entry in manifest}

    raw: dict[str, dict[str, Any]] = {}
    integrity_rows: list[dict[str, Any]] = []
    for entry in manifest:
        path = Path(entry["path"])
        exists = path.is_file()
        actual_bytes = path.stat().st_size if exists else None
        actual_sha = sha256(path) if exists else None
        matches = exists and actual_bytes == entry["bytes"] and actual_sha == entry["sha256"]
        integrity_rows.append({"name": entry["name"], "matches": matches, "bytes": actual_bytes, "sha256": actual_sha})
        if matches:
            raw[entry["name"]] = json.loads(path.read_text(encoding="utf-8"))

    identity_payload = raw.get("crossref_candidate_doi", {}).get("message", {})
    actual_title_values = identity_payload.get("title", [])
    actual_title = actual_title_values[0] if actual_title_values else None
    identity_conflict = (
        (identity_payload.get("DOI") or "").casefold() == production["candidate"]["doi_embedded_in_url"].casefold()
        and norm(actual_title or "") == norm(EXPECTED_DOI_TITLE)
        and norm(actual_title or "") != target
    )

    exact_matches: dict[str, list[str]] = {}
    for name, payload in raw.items():
        if name == "crossref_candidate_doi" or name.startswith("github_"):
            continue
        matches = [title for title in titles_for(name, payload) if norm(title) == target]
        if matches:
            exact_matches[name] = matches

    github_counts = {
        name: payload.get("total_count")
        for name, payload in raw.items() if name.startswith("github_")
    }
    assessment = production.get("source_assessment", {})
    conclusion = production.get("bounded_conclusion", "")
    expected_status = "SOURCE_IDENTITY_UNRESOLVED_OFFICIAL_EXECUTION_NOT_AUTHORIZED"

    checks: dict[str, dict[str, Any]] = {}
    checks["all_expected_queries_complete"] = {
        "pass": (
            production.get("query_count_expected") == len(EXPECTED_QUERIES)
            and production.get("query_count_succeeded") == len(EXPECTED_QUERIES)
            and set(by_name) == EXPECTED_QUERIES
            and not production.get("query_failures")
            and all(entry.get("http_status") == 200 for entry in manifest)
        ),
        "expected": sorted(EXPECTED_QUERIES),
        "observed": sorted(by_name),
    }
    checks["raw_response_hashes"] = {
        "pass": len(integrity_rows) == len(EXPECTED_QUERIES) and all(row["matches"] for row in integrity_rows),
        "verified_files": sum(row["matches"] for row in integrity_rows),
        "details": integrity_rows,
    }
    checks["candidate_doi_identity_conflict"] = {
        "pass": identity_conflict,
        "candidate_title": candidate_title,
        "doi_resolves_to_title": actual_title,
        "doi": identity_payload.get("DOI"),
    }
    checks["no_exact_scholarly_title_match"] = {
        "pass": not exact_matches,
        "exact_matches": exact_matches,
        "searched_sources": sorted(name for name in raw if name != "crossref_candidate_doi" and not name.startswith("github_")),
    }
    checks["no_official_repository_or_commit"] = {
        "pass": assessment.get("official_repository_verified") is False and assessment.get("official_source_commit") is None,
        "github_total_counts": github_counts,
        "note": "Repository search results cannot establish official ownership while the bibliographic identity itself is unresolved.",
    }
    checks["build_and_execution_blocked"] = {
        "pass": (
            assessment.get("official_build_performed") is False
            and assessment.get("official_execution_performed") is False
            and assessment.get("build_or_execution_authorized") is False
            and assessment.get("official_sequence_output_count") == 0
            and assessment.get("performance_result_count") == 0
        ),
        "official_build_performed": assessment.get("official_build_performed"),
        "official_execution_performed": assessment.get("official_execution_performed"),
        "official_sequence_output_count": assessment.get("official_sequence_output_count"),
        "performance_result_count": assessment.get("performance_result_count"),
    }
    checks["bounded_negative_wording"] = {
        "pass": (
            assessment.get("method_invalid_claim") is False
            and assessment.get("implementation_nonexistence_claim") is False
            and "not evidence that the method is invalid or that no implementation exists" in conclusion
        ),
        "method_invalid_claim": assessment.get("method_invalid_claim"),
        "implementation_nonexistence_claim": assessment.get("implementation_nonexistence_claim"),
    }
    checks["production_status_consistent"] = {
        "pass": (
            production.get("status") == expected_status
            and production.get("candidate_doi_identity", {}).get("conflict") is True
            and production.get("source_assessment", {}).get("exact_candidate_title_match_count") == 0
            and production.get("source_assessment", {}).get("ppt_record_ready") is False
        ),
        "observed_status": production.get("status"),
        "expected_status": expected_status,
    }

    report = {
        "protocol": "a8_rk05_cdgb_source_independent_verification_v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS" if all(item["pass"] for item in checks.values()) else "FAIL",
        "checks_passed": sum(item["pass"] for item in checks.values()),
        "checks_total": len(checks),
        "checks": checks,
        "independent_production_import": False,
        "independent_recomputation_from_frozen_raw_responses": True,
        "production_audit": str(args.audit),
        "production_audit_sha256": sha256(args.audit),
        "official_execution_authorized": False,
        "main_baseline_comparison": False,
        "functional_ood": False,
        "sota_claim": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}",
        "output": str(args.output), "sha256": sha256(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
