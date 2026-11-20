#!/usr/bin/env python3
"""Offline schema, geometry and claim checks for the RK16 slide candidate."""
from __future__ import annotations

import hashlib
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(os.environ.get("RK16_PPT_WORK_DIR", Path(__file__).resolve().parent)).resolve()
CANDIDATE = ROOT / "rk16_ppt_slide112_v1.xml"
CONTENT = ROOT / "rk16_ppt_content_verification_v1.json"
BASELINE = ROOT / "rk16_ppt_before_v1.xml"
OUT = ROOT / "rk16_ppt_slide112_candidate_verification_v1.json"
NS = "https://www.larkoffice.com/sml/2.0"
local = lambda node: node.tag.rsplit("}", 1)[-1]
checks: list[dict[str, object]] = []


def record(name: str, passed: bool, evidence: object = None) -> None:
    checks.append({"check": name, "pass": bool(passed), "evidence": evidence})


content = json.loads(CONTENT.read_text(encoding="utf-8"))
record("content_verification_pass", content["status"] == "PASS" and content["checks_passed"] == content["checks_total"], f"{content['checks_passed']}/{content['checks_total']}")
raw_inspect_path = ROOT / "rk16_ppt_candidate_raw_inspect_v1.json"
raw_inspect = json.loads(raw_inspect_path.read_text(encoding="utf-8"))
raw_slide = raw_inspect["slides"][0]
record(
    "official_raw_xml_inspection",
    raw_inspect["presentation"]["slide_count"] == 112
    and raw_inspect["selection"]["output_slide_count"] == 1
    and raw_slide["index"] == 112
    and raw_slide["slide_id"] == "rk16candidate"
    and "LinearDesign leads the frozen dense-prefix comparison" in raw_slide["raw_xml"],
    {"presentation_slides": raw_inspect["presentation"]["slide_count"], "selected": raw_slide["slide_id"]},
)
baseline = ET.parse(BASELINE).getroot()
baseline_slides = [node for node in list(baseline) if local(node) == "slide"]
record("baseline_page_count", len(baseline_slides) == 111, len(baseline_slides))
record("baseline_last_page", baseline_slides[-1].get("id") == "pZn", baseline_slides[-1].get("id"))

root = ET.parse(CANDIDATE).getroot()
record("single_slide_root", local(root) == "slide" and root.tag == f"{{{NS}}}slide", root.tag)
record("no_client_ids", not any(node.get("id") for node in root.iter()))
data = next(node for node in list(root) if local(node) == "data")
elements = list(data)
record("expected_element_count", len(elements) == 34, len(elements))
record("one_native_table", sum(local(node) == "table" for node in elements) == 1)
record("no_external_images", not any(local(node) in {"image", "video"} for node in root.iter()))
notes = [node for node in list(root) if local(node) == "note"]
record("speaker_notes_present", len(notes) == 1 and len("".join(notes[0].itertext()).strip()) > 500, len("".join(notes[0].itertext()).strip()) if notes else 0)

geometry_errors: list[str] = []
boxes: list[tuple[int, float, float, float, float, str]] = []
for index, node in enumerate(elements):
    try:
        x, y = float(node.get("topLeftX")), float(node.get("topLeftY"))
        w, h = float(node.get("width")), float(node.get("height"))
    except (TypeError, ValueError):
        geometry_errors.append(f"element {index}: invalid geometry")
        continue
    if min(x, y) < 0 or w <= 0 or h <= 0 or x + w > 960 or y + h > 540:
        geometry_errors.append(f"element {index}: {(x, y, w, h)}")
    boxes.append((index, x, y, w, h, node.get("type") if local(node) == "shape" else local(node)))
record("all_elements_inside_canvas", not geometry_errors, geometry_errors)

containers = {"rect", "round-rect"}
overlap_errors: list[str] = []
for i, a in enumerate(boxes):
    ai, ax, ay, aw, ah, at = a
    for b in boxes[i + 1:]:
        bi, bx, by, bw, bh, bt = b
        overlap = max(0.0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0.0, min(ay + ah, by + bh) - max(ay, by))
        if overlap <= 0:
            continue
        a_contains_b = at in containers and ax <= bx and ay <= by and ax + aw >= bx + bw and ay + ah >= by + bh
        b_contains_a = bt in containers and bx <= ax and by <= ay and bx + bw >= ax + aw and by + bh >= ay + ah
        if not (a_contains_b or b_contains_a):
            overlap_errors.append(f"{ai}:{bi} overlap={overlap}")
record("no_unintended_top_level_overlap", not overlap_errors, overlap_errors)

texts = ["".join(node.itertext()).strip() for node in root.iter() if local(node) == "t"]
joined = "\n".join(texts)
required_texts = (
    "LinearDesign leads the frozen dense-prefix comparison", "18 UNIQUE18", "792", "6 / 6 PASS", "88 / 88",
    "22.794606", "29.972887", "14.896234", "16.693982", "5.205444", "7.989211", "0.702952", "0.966618",
    "+7.898372 AUC", "+13.278905 B11 HV", "Holm p = 0.00059997", "+ 53 / 53 FINALIZATION",
    "No wall-time, functional, CodonFlow-RK or SOTA claim.", "Time-matched = false",
    "functional OOD / untouched = false", "RK-G1 = false", "generator training unauthorized", "112 · RK16",
)
missing = [text for text in required_texts if text not in joined]
record("required_slide_claims", not missing, missing)
note_text = "".join(notes[0].itertext()) if notes else ""
required_note_tokens = ("88/88", "53/53", "59/59", "347 passed and 1 skipped", "is not time-matched", "full seven-method dense coverage", "external SOTA")
record("speaker_note_scope", all(token in note_text for token in required_note_tokens))

font_errors: list[str] = []
for node in data.iter():
    if local(node) == "content" and "".join(node.itertext()).strip():
        if node.get("fontFamily") != "Inter":
            font_errors.append(ET.tostring(node, encoding="unicode")[:120])
record("uniform_inter_font", not font_errors, font_errors)

tables = [node for node in elements if local(node) == "table"]
if tables:
    table = tables[0]
    grid = next(node for node in list(table) if local(node) == "tblGrid")
    widths = [float(node.get("width")) for node in list(grid)]
    rows = [node for node in list(table) if local(node) == "tr"]
    heights = [float(node.get("height")) for node in rows]
    record("table_grid_width", sum(widths) == float(table.get("width")) == 864, widths)
    record("table_row_height", sum(heights) == float(table.get("height")) == 140, heights)
    record("table_shape", len(rows) == 5 and all(len([c for c in list(row) if local(c) == "td"]) == 3 for row in rows), [len(list(row)) for row in rows])
    record("header_has_explicit_fill", all(any(local(c) == "fill" for c in list(cell)) for cell in list(rows[0])))

passed = sum(bool(c["pass"]) for c in checks)
report = {
    "schema": "a8-rk16-ppt-candidate-verification-v1",
    "status": "PASS" if passed == len(checks) else "FAIL",
    "candidate": CANDIDATE.name,
    "candidate_sha256": hashlib.sha256(CANDIDATE.read_bytes()).hexdigest(),
    "baseline_sha256": hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
    "baseline_pages": len(baseline_slides),
    "canvas": [960, 540],
    "checks_passed": passed,
    "checks_total": len(checks),
    "checks": checks,
}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "candidate_sha256": report["candidate_sha256"], "output": str(OUT)}, ensure_ascii=False))
raise SystemExit(0 if report["status"] == "PASS" else 1)
