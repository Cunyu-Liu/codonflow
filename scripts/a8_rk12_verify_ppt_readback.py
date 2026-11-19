#!/usr/bin/env python3
"""Independently verify the two appended RK-12 slides and untouched baseline."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def semantic(element: ET.Element) -> bytes:
    item = copy.deepcopy(element)
    for node in item.iter():
        node.attrib.pop("id", None)
        node.text = (node.text or "").strip()
        node.tail = None
    return ET.tostring(item, encoding="utf-8", method="c14n") if hasattr(ET, "canonicalize") else ET.tostring(item, encoding="utf-8")


def canonical(element: ET.Element) -> bytes:
    item = copy.deepcopy(element)
    for node in item.iter():
        node.attrib.pop("id", None)
        node.text = (node.text or "").strip()
        node.tail = None
    ET.register_namespace("", item.tag.split("}")[0][1:])
    return ET.tostring(item, encoding="utf-8")


def slides(path: Path):
    root = ET.parse(path).getroot()
    ns = root.tag.split("}")[0][1:]
    return root, ns, root.findall(f".//{{{ns}}}slide")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate91", type=Path, required=True)
    parser.add_argument("--candidate92", type=Path, required=True)
    parser.add_argument("--readback", type=Path, required=True)
    parser.add_argument("--response91", type=Path, required=True)
    parser.add_argument("--response92", type=Path, required=True)
    parser.add_argument("--finalization", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    final = json.loads(args.finalization.read_text())
    if not final["status"].startswith("PASS_") or final["checks_passed"] != final["checks_total"] == 15:
        raise ValueError("finalization gate is not PASS")
    if final["matrix_sha256"] != sha256(args.matrix):
        raise ValueError("matrix hash mismatch")
    _, bns, baseline = slides(args.baseline)
    _, rns, readback = slides(args.readback)
    response91 = json.loads(args.response91.read_text())
    response92 = json.loads(args.response92.read_text())
    candidate91 = ET.parse(args.candidate91).getroot()
    candidate92 = ET.parse(args.candidate92).getroot()
    checks = []
    def check(name, condition, evidence):
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})
    check("baseline_90", len(baseline) == 90, len(baseline))
    check("readback_92", len(readback) == 92, len(readback))
    check("first_90_ids_unchanged", [s.attrib.get("id") for s in baseline] == [s.attrib.get("id") for s in readback[:90]], "ordered IDs")
    changed = [i + 1 for i in range(90) if canonical(baseline[i]) != canonical(readback[i])]
    check("first_90_semantic_xml_unchanged", not changed, changed)
    new_ids = [readback[90].attrib.get("id"), readback[91].attrib.get("id")]
    check("new_page_ids_present_distinct", all(new_ids) and len(set(new_ids)) == 2 and not set(new_ids) & {s.attrib.get("id") for s in baseline}, new_ids)
    check("slide91_candidate_semantics", canonical(candidate91) == canonical(readback[90]), sha256(args.candidate91))
    check("slide92_candidate_semantics", canonical(candidate92) == canonical(readback[91]), sha256(args.candidate92))
    for page, slide in ((91, readback[90]), (92, readback[91])):
        notes = slide.findall(f".//{{{rns}}}note/{{{rns}}}content/{{{rns}}}p")
        check(f"slide{page}_four_note_paragraphs", len(notes) == 4, len(notes))
        out_of_bounds = []
        for node in slide.iter():
            if all(key in node.attrib for key in ("topLeftX", "topLeftY", "width", "height")):
                x, y, w, h = (float(node.attrib[key]) for key in ("topLeftX", "topLeftY", "width", "height"))
                if x < 0 or y < 0 or x + w > 960 or y + h > 540:
                    out_of_bounds.append(node.attrib)
        check(f"slide{page}_canvas_bounds", not out_of_bounds, out_of_bounds)
    for number, response, slide_id in ((91, response91, new_ids[0]), (92, response92, new_ids[1])):
        check(f"add_slide{number}_ok", response.get("ok") is True, response.get("ok"))
        check(f"add_slide{number}_id_matches", response.get("data", {}).get("slide_id") == slide_id, response.get("data", {}).get("slide_id"))
    check("matrix_hash_matches_finalization", final["matrix_sha256"] == sha256(args.matrix), final["matrix_sha256"])
    report = {
        "schema": "a8-rk12-ppt-readback-verification-v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "status": "PASS" if all(item["pass"] for item in checks) else "FAIL",
        "checks_passed": sum(item["pass"] for item in checks),
        "checks_total": len(checks),
        "baseline_slide_count": len(baseline),
        "readback_slide_count": len(readback),
        "new_slide_ids": new_ids,
        "slide91_add_revision": response91.get("data", {}).get("revision_id"),
        "slide92_add_revision": response92.get("data", {}).get("revision_id"),
        "baseline_sha256": sha256(args.baseline),
        "readback_sha256": sha256(args.readback),
        "candidate91_sha256": sha256(args.candidate91),
        "candidate92_sha256": sha256(args.candidate92),
        "finalization_sha256": sha256(args.finalization),
        "matrix_sha256": sha256(args.matrix),
        "changed_baseline_pages": changed,
        "checks": checks,
        "scientific_boundary": "PPT readback verifies presentation fidelity only; scientific acceptance comes from the frozen RK-12 finalization and independent matrix verifier.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
