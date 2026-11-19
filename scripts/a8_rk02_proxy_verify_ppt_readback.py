#!/usr/bin/env python3
"""Verify appended proxy slide 94 and semantic preservation of slides 1–93."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from scripts.a8_rk12_verify_ppt_readback import canonical, sha256, slides


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("baseline", "candidate94", "readback", "response94", "primary", "primary-independent", "primary-finalization", "robustness", "robustness-independent", "robustness-finalization", "report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    primary = json.loads(args.primary.read_text())
    primary_ind = json.loads(args.primary_independent.read_text())
    primary_final = json.loads(args.primary_finalization.read_text())
    robust = json.loads(args.robustness.read_text())
    robust_ind = json.loads(args.robustness_independent.read_text())
    robust_final = json.loads(args.robustness_finalization.read_text())
    _, _, baseline = slides(args.baseline)
    _, rns, readback = slides(args.readback)
    response = json.loads(args.response94.read_text())
    candidate = ET.parse(args.candidate94).getroot()
    checks = []

    def check(name, condition, evidence):
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})

    check("baseline_93", len(baseline) == 93, len(baseline))
    check("readback_94", len(readback) == 94, len(readback))
    check("first_93_ids_unchanged", [s.attrib.get("id") for s in baseline] == [s.attrib.get("id") for s in readback[:93]], "ordered IDs")
    changed = [i + 1 for i in range(93) if canonical(baseline[i]) != canonical(readback[i])]
    check("first_93_semantic_xml_unchanged", not changed, changed)
    new_id = readback[93].attrib.get("id")
    check("new_page_id_present_distinct", bool(new_id) and new_id not in {s.attrib.get("id") for s in baseline}, new_id)
    check("slide94_candidate_semantics", canonical(candidate) == canonical(readback[93]), sha256(args.candidate94))
    notes = readback[93].findall(f".//{{{rns}}}note/{{{rns}}}content/{{{rns}}}p")
    check("slide94_four_note_paragraphs", len(notes) == 4, len(notes))
    out_of_bounds = []
    for node in readback[93].iter():
        if all(key in node.attrib for key in ("topLeftX", "topLeftY", "width", "height")):
            x, y, w, h = (float(node.attrib[key]) for key in ("topLeftX", "topLeftY", "width", "height"))
            if x < 0 or y < 0 or x + w > 960 or y + h > 540:
                out_of_bounds.append(node.attrib)
    check("slide94_canvas_bounds", not out_of_bounds, out_of_bounds)
    check("add_slide94_ok", response.get("ok") is True, response.get("ok"))
    check("add_slide94_id_matches", response.get("data", {}).get("slide_id") == new_id, response.get("data", {}).get("slide_id"))
    page_text = " ".join(readback[93].itertext())
    gc3 = primary["associations"]["gc3_observed_5prime"]["spearman"]
    gc = primary["associations"]["gc_observed_5prime"]["spearman"]
    check("primary_values_visible", f"{gc3['observed']:+.3f}" in page_text and f"{gc['observed']:+.3f}" in page_text and "152" in page_text, "GC3/GC/n")
    check("scientific_boundaries_visible", all(text in page_text for text in ("非完整 CDS", "非蛋白 OOD", "非因果", "非 SOTA")), "four boundaries")
    evidence_ok = (
        primary_ind["status"] == primary_final["status"] == robust_ind["status"] == robust_final["status"] == "PASS"
        and primary_final["production_sha256"] == sha256(args.primary)
        and primary_final["independent_sha256"] == sha256(args.primary_independent)
        and robust_final["production_sha256"] == sha256(args.robustness)
        and robust_final["independent_sha256"] == sha256(args.robustness_independent)
    )
    check("finalized_evidence_hash_binding", evidence_ok, "primary and robustness")
    report = {
        "schema": "a8-rk02-mordstein-proxy-ppt-readback-verification-v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "status": "PASS" if all(item["pass"] for item in checks) else "FAIL",
        "checks_passed": sum(item["pass"] for item in checks), "checks_total": len(checks),
        "baseline_slide_count": len(baseline), "readback_slide_count": len(readback),
        "new_slide_id": new_id, "slide94_add_revision": response.get("data", {}).get("revision_id"),
        "baseline_sha256": sha256(args.baseline), "readback_sha256": sha256(args.readback),
        "candidate94_sha256": sha256(args.candidate94),
        "primary_sha256": sha256(args.primary), "primary_independent_sha256": sha256(args.primary_independent),
        "primary_finalization_sha256": sha256(args.primary_finalization),
        "robustness_sha256": sha256(args.robustness), "robustness_independent_sha256": sha256(args.robustness_independent),
        "robustness_finalization_sha256": sha256(args.robustness_finalization),
        "changed_baseline_pages": changed, "checks": checks,
        "scientific_boundary": "PPT readback verifies presentation fidelity only; fixed-GFP observed-end association is not causal, protein OOD, mechanism increment or SOTA evidence.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
