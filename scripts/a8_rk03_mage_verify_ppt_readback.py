#!/usr/bin/env python3
"""Verify appended MAGE slide 95 and semantic preservation of slides 1–94."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from scripts.a8_rk12_verify_ppt_readback import canonical, sha256, slides


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("baseline", "candidate95", "readback", "response95", "protocol", "production", "independent", "finalization", "report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    production = json.loads(args.production.read_text())
    independent = json.loads(args.independent.read_text())
    final = json.loads(args.finalization.read_text())
    _, _, baseline = slides(args.baseline)
    _, rns, readback = slides(args.readback)
    response = json.loads(args.response95.read_text())
    candidate = ET.parse(args.candidate95).getroot()
    checks = []

    def check(name, condition, evidence):
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})

    check("baseline_94", len(baseline) == 94, len(baseline))
    check("readback_95", len(readback) == 95, len(readback))
    check("first_94_ids_unchanged", [s.attrib.get("id") for s in baseline] == [s.attrib.get("id") for s in readback[:94]], "ordered IDs")
    changed = [i + 1 for i in range(94) if canonical(baseline[i]) != canonical(readback[i])]
    check("first_94_semantic_xml_unchanged", not changed, changed)
    new_id = readback[94].attrib.get("id") if len(readback) == 95 else None
    check("new_page_id_present_distinct", bool(new_id) and new_id not in {s.attrib.get("id") for s in baseline}, new_id)
    check("slide95_candidate_semantics", len(readback) == 95 and canonical(candidate) == canonical(readback[94]), sha256(args.candidate95))
    notes = readback[94].findall(f".//{{{rns}}}note/{{{rns}}}content/{{{rns}}}p") if len(readback) == 95 else []
    check("slide95_four_note_paragraphs", len(notes) == 4, len(notes))
    out_of_bounds = []
    if len(readback) == 95:
        for node in readback[94].iter():
            if all(key in node.attrib for key in ("topLeftX", "topLeftY", "width", "height")):
                x, y, w, h = (float(node.attrib[key]) for key in ("topLeftX", "topLeftY", "width", "height"))
                if x < 0 or y < 0 or x + w > 960 or y + h > 540:
                    out_of_bounds.append(node.attrib)
    check("slide95_canvas_bounds", not out_of_bounds, out_of_bounds)
    check("add_slide95_ok", response.get("ok") is True, response.get("ok"))
    check("add_slide95_id_matches", response.get("data", {}).get("slide_id") == new_id, response.get("data", {}).get("slide_id"))
    page_text = " ".join(readback[94].itertext()) if len(readback) == 95 else ""
    full = production["rich_dev_selection"]["models"]["full_mechanism"]["dev"]["rmse"]
    check("dev_values_visible", f"{full:.6f}" in page_text and "NO-GO" in page_text and "164" in page_text, "full RMSE/gate/n")
    check("scientific_boundaries_visible", all(text in page_text for text in ("TEST UNTOUCHED", "不是普遍机制证伪", "非 SOTA")), "test and scope")
    evidence_ok = independent["status"] == final["status"] == "PASS" and independent["checks_passed"] == independent["checks_total"] == 39 and final["checks_passed"] == final["checks_total"] == 12 and final["protocol_sha256"] == sha256(args.protocol) and final["production_sha256"] == sha256(args.production) and final["independent_sha256"] == sha256(args.independent)
    check("finalized_evidence_hash_binding", evidence_ok, "protocol/production/independent")
    report = {
        "schema": "a8-rk03-mage-ppt-readback-verification-v1", "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "status": "PASS" if all(item["pass"] for item in checks) else "FAIL",
        "checks_passed": sum(item["pass"] for item in checks), "checks_total": len(checks),
        "baseline_slide_count": len(baseline), "readback_slide_count": len(readback),
        "new_slide_id": new_id, "slide95_add_revision": response.get("data", {}).get("revision_id"),
        "baseline_sha256": sha256(args.baseline), "readback_sha256": sha256(args.readback), "candidate95_sha256": sha256(args.candidate95),
        "protocol_sha256": sha256(args.protocol), "production_sha256": sha256(args.production),
        "independent_sha256": sha256(args.independent), "finalization_sha256": sha256(args.finalization),
        "changed_baseline_pages": changed, "checks": checks,
        "scientific_boundary": "PPT readback verifies fidelity only; the MAGE result is a frozen dev no-go with test untouched, not universal mechanism falsification or SOTA.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
