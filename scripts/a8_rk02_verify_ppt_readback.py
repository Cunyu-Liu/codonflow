#!/usr/bin/env python3
"""Verify the appended Mordstein slide and the untouched prior deck."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from scripts.a8_rk12_verify_ppt_readback import canonical, sha256, slides


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True, help="Live 92-page deck immediately before page 93")
    parser.add_argument("--candidate93", type=Path, required=True)
    parser.add_argument("--readback", type=Path, required=True)
    parser.add_argument("--response93", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--finalization", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    summary = json.loads(args.summary.read_text())
    independent = json.loads(args.independent.read_text())
    final = json.loads(args.finalization.read_text())
    if not (independent["status"] == "PASS" and independent["passed"] == independent["total"]):
        raise ValueError("independent scientific gate is not PASS")
    if not (final["status"] == "PASS" and final["passed"] == final["total"] and
            final["summary_sha256"] == sha256(args.summary) and final["independent_sha256"] == sha256(args.independent)):
        raise ValueError("finalization gate or hash binding is not PASS")
    _, _, baseline = slides(args.baseline)
    _, rns, readback = slides(args.readback)
    response = json.loads(args.response93.read_text())
    candidate = ET.parse(args.candidate93).getroot()
    checks = []

    def check(name, condition, evidence):
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})

    check("baseline_92", len(baseline) == 92, len(baseline))
    check("readback_93", len(readback) == 93, len(readback))
    check("first_92_ids_unchanged", [s.attrib.get("id") for s in baseline] == [s.attrib.get("id") for s in readback[:92]], "ordered IDs")
    changed = [i + 1 for i in range(92) if canonical(baseline[i]) != canonical(readback[i])]
    check("first_92_semantic_xml_unchanged", not changed, changed)
    new_id = readback[92].attrib.get("id")
    check("new_page_id_present_distinct", bool(new_id) and new_id not in {s.attrib.get("id") for s in baseline}, new_id)
    check("slide93_candidate_semantics", canonical(candidate) == canonical(readback[92]), sha256(args.candidate93))
    notes = readback[92].findall(f".//{{{rns}}}note/{{{rns}}}content/{{{rns}}}p")
    check("slide93_four_note_paragraphs", len(notes) == 4, len(notes))
    out_of_bounds = []
    for node in readback[92].iter():
        if all(key in node.attrib for key in ("topLeftX", "topLeftY", "width", "height")):
            x, y, w, h = (float(node.attrib[key]) for key in ("topLeftX", "topLeftY", "width", "height"))
            if x < 0 or y < 0 or x + w > 960 or y + h > 540:
                out_of_bounds.append(node.attrib)
    check("slide93_canvas_bounds", not out_of_bounds, out_of_bounds)
    check("add_slide93_ok", response.get("ok") is True, response.get("ok"))
    check("add_slide93_id_matches", response.get("data", {}).get("slide_id") == new_id, response.get("data", {}).get("slide_id"))
    check("scientific_library_gate_preserved", summary["library_recovery_status"] == "REVIEW_REQUIRED_COUNT_NOT_217" and
          summary["variants_retained"] == 152 and summary["mutual_best_links"] == 17,
          summary["library_recovery_status"])
    report = {
        "schema": "a8-rk02-mordstein-ppt-readback-verification-v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "status": "PASS" if all(item["pass"] for item in checks) else "FAIL",
        "checks_passed": sum(item["pass"] for item in checks), "checks_total": len(checks),
        "baseline_slide_count": len(baseline), "readback_slide_count": len(readback),
        "new_slide_id": new_id, "slide93_add_revision": response.get("data", {}).get("revision_id"),
        "baseline_sha256": sha256(args.baseline), "readback_sha256": sha256(args.readback),
        "candidate93_sha256": sha256(args.candidate93), "summary_sha256": sha256(args.summary),
        "independent_sha256": sha256(args.independent), "finalization_sha256": sha256(args.finalization),
        "changed_baseline_pages": changed, "checks": checks,
        "library_recovery_status": summary["library_recovery_status"],
        "scientific_boundary": "PPT readback verifies presentation fidelity only; computational consistency does not establish complete CDS, author identity or 217-candidate recovery.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
