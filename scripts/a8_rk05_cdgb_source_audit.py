#!/usr/bin/env python3
"""Evidence-bound CDGB source-identity and official-code availability audit.

This script deliberately does not implement or execute CDGB. It freezes scholarly
and repository API responses, checks the supplied candidate identity, and blocks
build/execution until an authoritative source is established.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PROTOCOL = "a8_rk05_cdgb_source_audit_v1"
CANDIDATE_TITLE = (
    "CDGB: a deep learning framework for codon de-optimization directed by "
    "the protein representation model"
)
CANDIDATE_URL = "https://academic.oup.com/bib/article/27/4/bbaf332/8199205"
CANDIDATE_DOI = "10.1093/bib/bbaf332"
USER_AGENT = "CodonFlow-A8-RK-source-audit/1.0"
SELECT_CROSSREF = "DOI,title,author,published,URL,container-title,volume,issue"


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = value.replace("de–optimization", "de-optimization").replace("de—optimization", "de-optimization")
    return re.sub(r"[^a-z0-9]+", "", value)


def crossref_url(params: dict[str, Any]) -> str:
    return "https://api.crossref.org/works?" + urllib.parse.urlencode(params)


def query_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "crossref_candidate_title",
            "kind": "crossref_search",
            "url": crossref_url({
                "query.bibliographic": CANDIDATE_TITLE,
                "rows": 20,
                "select": SELECT_CROSSREF,
            }),
        },
        {
            "name": "crossref_cdgb_title",
            "kind": "crossref_search",
            "url": crossref_url({
                "query.title": "CDGB",
                "filter": "from-pub-date:2020-01-01",
                "rows": 50,
                "select": SELECT_CROSSREF,
            }),
        },
        {
            "name": "crossref_candidate_doi",
            "kind": "crossref_doi",
            "url": "https://api.crossref.org/works/" + CANDIDATE_DOI,
        },
        {
            "name": "openalex_cdgb_title",
            "kind": "openalex_search",
            "url": "https://api.openalex.org/works?" + urllib.parse.urlencode({
                "filter": "title.search:CDGB", "per-page": 50,
            }),
        },
        {
            "name": "europepmc_cdgb_title",
            "kind": "europepmc_search",
            "url": "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode({
                "query": "TITLE:CDGB", "format": "json", "pageSize": 100, "resultType": "lite",
            }),
        },
        {
            "name": "europepmc_deoptimization_title",
            "kind": "europepmc_search",
            "url": "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode({
                "query": 'TITLE:"codon de-optimization"', "format": "json", "pageSize": 100, "resultType": "lite",
            }),
        },
        {
            "name": "github_cdgb_codon",
            "kind": "github_search",
            "url": "https://api.github.com/search/repositories?" + urllib.parse.urlencode({
                "q": '"CDGB" codon in:name,description,readme', "per_page": 50,
            }),
        },
        {
            "name": "github_codon_deoptimization",
            "kind": "github_search",
            "url": "https://api.github.com/search/repositories?" + urllib.parse.urlencode({
                "q": '"codon de-optimization" in:name,description,readme', "per_page": 50,
            }),
        },
        {
            "name": "github_cdgb_protein_representation",
            "kind": "github_search",
            "url": "https://api.github.com/search/repositories?" + urllib.parse.urlencode({
                "q": '"CDGB" "protein representation" in:name,description,readme', "per_page": 50,
            }),
        },
    ]


def fetch_json(url: str, timeout: int = 60, attempts: int = 3) -> tuple[dict[str, Any], dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json, application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                status = response.status
                final_url = response.geturl()
            payload = json.loads(raw.decode("utf-8"))
            return payload, {"http_status": status, "final_url": final_url, "attempt": attempt}
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            retryable = not isinstance(exc, urllib.error.HTTPError) or exc.code in {429, 500, 502, 503, 504}
            if attempt >= attempts or not retryable:
                break
            time.sleep(3 * attempt)
    raise RuntimeError(f"query failed after {attempts} attempts: {url}: {last_error}")


def extract_titles(name: str, kind: str, payload: dict[str, Any]) -> list[str]:
    if kind == "crossref_search":
        return [title for item in payload.get("message", {}).get("items", []) for title in item.get("title", [])]
    if kind == "crossref_doi":
        return list(payload.get("message", {}).get("title", []))
    if kind == "openalex_search":
        return [item.get("display_name") or item.get("title") or "" for item in payload.get("results", [])]
    if kind == "europepmc_search":
        return [item.get("title") or "" for item in payload.get("resultList", {}).get("result", [])]
    if kind == "github_search":
        return [item.get("full_name") or "" for item in payload.get("items", [])]
    raise ValueError(f"unsupported query kind: {kind}")


def summarize_query(name: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    titles = extract_titles(name, kind, payload)
    target = normalize_title(CANDIDATE_TITLE)
    exact = [title for title in titles if normalize_title(title) == target]
    summary: dict[str, Any] = {
        "returned_title_or_repository_count": len(titles),
        "exact_candidate_title_matches": exact,
    }
    if kind == "github_search":
        summary["total_count_reported_by_github"] = payload.get("total_count")
        summary["repositories"] = [
            {
                "full_name": item.get("full_name"),
                "html_url": item.get("html_url"),
                "description": item.get("description"),
                "owner": (item.get("owner") or {}).get("login"),
            }
            for item in payload.get("items", [])
        ]
    elif kind == "crossref_search":
        summary["returned_records"] = [
            {"DOI": item.get("DOI"), "title": item.get("title"), "URL": item.get("URL")}
            for item in payload.get("message", {}).get("items", [])
        ]
    elif kind == "openalex_search":
        summary["returned_records"] = [
            {"doi": item.get("doi"), "title": item.get("display_name"), "id": item.get("id")}
            for item in payload.get("results", [])
        ]
    elif kind == "europepmc_search":
        summary["hit_count"] = payload.get("hitCount")
        summary["returned_records"] = [
            {key: item.get(key) for key in ("title", "authorString", "journalTitle", "pubYear", "doi", "pmid", "pmcid")}
            for item in payload.get("resultList", {}).get("result", [])
        ]
    return summary


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, Any]] = []
    summaries: dict[str, Any] = {}
    failures: list[dict[str, str]] = []
    for definition in query_definitions():
        name, kind, url = definition["name"], definition["kind"], definition["url"]
        try:
            payload, transport = fetch_json(url)
        except Exception as exc:
            failures.append({"name": name, "url": url, "error": str(exc)})
            continue
        raw_path = args.output_dir / f"{name}.json"
        raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest.append({
            "name": name, "kind": kind, "url": url, **transport,
            "path": str(raw_path), "bytes": raw_path.stat().st_size, "sha256": sha256(raw_path),
        })
        summaries[name] = summarize_query(name, kind, payload)
        print(json.dumps({"query": name, "status": transport["http_status"], "bytes": raw_path.stat().st_size}, ensure_ascii=False), flush=True)

    identity: dict[str, Any] = {"resolved": False}
    doi_entry = next((entry for entry in manifest if entry["name"] == "crossref_candidate_doi"), None)
    if doi_entry is not None:
        payload = json.loads(Path(doi_entry["path"]).read_text(encoding="utf-8"))
        message = payload.get("message", {})
        actual_titles = message.get("title", [])
        actual_title = actual_titles[0] if actual_titles else None
        identity = {
            "candidate_url": CANDIDATE_URL,
            "doi_embedded_in_candidate_url": CANDIDATE_DOI,
            "crossref_doi": message.get("DOI"),
            "crossref_title": actual_title,
            "crossref_container_title": message.get("container-title"),
            "crossref_volume": message.get("volume"),
            "crossref_issue": message.get("issue"),
            "resolved": normalize_title(actual_title or "") == normalize_title(CANDIDATE_TITLE),
            "conflict": bool(actual_title) and normalize_title(actual_title or "") != normalize_title(CANDIDATE_TITLE),
        }

    all_exact_matches = {
        name: summary["exact_candidate_title_matches"]
        for name, summary in summaries.items()
        if summary["exact_candidate_title_matches"]
    }
    complete = not failures and len(manifest) == len(query_definitions())
    no_exact_title_match = not all_exact_matches
    identity_conflict = identity.get("conflict") is True
    status = (
        "SOURCE_IDENTITY_UNRESOLVED_OFFICIAL_EXECUTION_NOT_AUTHORIZED"
        if complete and no_exact_title_match and identity_conflict
        else "SOURCE_AUDIT_INCOMPLETE_OR_IDENTITY_REQUIRES_REVIEW"
    )
    report = {
        "protocol": PROTOCOL,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": status,
        "candidate": {"title": CANDIDATE_TITLE, "url": CANDIDATE_URL, "doi_embedded_in_url": CANDIDATE_DOI},
        "query_count_expected": len(query_definitions()),
        "query_count_succeeded": len(manifest),
        "query_failures": failures,
        "raw_response_manifest": manifest,
        "query_summaries": summaries,
        "candidate_doi_identity": identity,
        "exact_candidate_title_matches": all_exact_matches,
        "source_assessment": {
            "candidate_bibliographic_identity_resolved": identity.get("resolved") is True,
            "candidate_doi_title_conflict": identity_conflict,
            "exact_candidate_title_match_count": sum(len(value) for value in all_exact_matches.values()),
            "official_repository_verified": False,
            "official_source_commit": None,
            "official_build_performed": False,
            "official_execution_performed": False,
            "official_sequence_output_count": 0,
            "performance_result_count": 0,
            "build_or_execution_authorized": False,
            "method_invalid_claim": False,
            "implementation_nonexistence_claim": False,
            "ppt_record_ready": False,
        },
        "bounded_conclusion": (
            "The supplied CDGB candidate could not be resolved to an authoritative bibliographic record or official repository. "
            "The DOI embedded in the candidate URL resolves to a different paper. No CDGB build or execution is authorized. "
            "This is a source-reproducibility finding, not evidence that the method is invalid or that no implementation exists."
        ),
        "search_limits": (
            "Crossref, OpenAlex, Europe PMC, and GitHub repository search are non-exhaustive and time-dependent. "
            "Without verified authors, DOI, journal metadata, or an author/publisher code link, an author-homepage search cannot be assigned reliably."
        ),
        "required_next_evidence": [
            "authoritative DOI or publisher record whose title and authors match CDGB",
            "author- or publisher-linked official repository and immutable commit",
            "official environment/build instructions and a documented minimal input",
        ],
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status, "queries": f"{len(manifest)}/{len(query_definitions())}",
        "identity_conflict": identity_conflict, "exact_title_matches": all_exact_matches,
        "report": str(args.report), "report_sha256": sha256(args.report),
    }, ensure_ascii=False, indent=2))
    return 0 if status == "SOURCE_IDENTITY_UNRESOLVED_OFFICIAL_EXECUTION_NOT_AUTHORIZED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
