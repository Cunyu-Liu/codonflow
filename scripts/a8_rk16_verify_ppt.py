#!/usr/bin/env python3
"""Verify the final online RK16 slide and preservation of the 111-page baseline."""
from __future__ import annotations

import hashlib
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(os.environ.get("RK16_PPT_WORK_DIR", Path(__file__).resolve().parent)).resolve()
OUT = ROOT / "rk16_ppt_verification_v1.json"
local = lambda node: node.tag.rsplit("}", 1)[-1]
checks: list[dict[str, object]] = []


def record(name: str, passed: bool, evidence: object = None) -> None:
    checks.append({"check": name, "pass": bool(passed), "evidence": evidence})


def load_json(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def semantic(node: ET.Element) -> tuple:
    return (
        local(node),
        tuple(sorted(node.attrib.items())),
        (node.text or "").strip(),
        tuple(semantic(child) for child in list(node)),
    )


add = load_json("rk16_ppt_add_response_v1.json")
note_fix = load_json("rk16_ppt_note_fix_response_v1.json")
final_response = load_json("rk16_ppt_final_response_v1.json")
content = load_json("rk16_ppt_content_verification_v1.json")
raw = load_json("rk16_ppt_slide112_final_raw_v1.json")
record("initial_add_confirmed", add.get("ok") is True and add.get("data", {}).get("slide_id") == "pZo" and add.get("data", {}).get("revision_id") == 74, add.get("data"))
record("note_fix_confirmed", note_fix.get("ok") is True and note_fix.get("data", {}).get("slide_id") == "pZo" and note_fix.get("data", {}).get("revision_id") == 75, note_fix.get("data"))
record("final_readback_confirmed", final_response.get("ok") is True and final_response.get("data", {}).get("revision_id") == 75, final_response.get("data", {}).get("revision_id"))
record("scientific_content_bound", content["status"] == "PASS" and content["checks_passed"] == content["checks_total"] == 28, f"{content['checks_passed']}/{content['checks_total']}")

before = ET.parse(ROOT / "rk16_ppt_before_write_v1.xml").getroot()
after = ET.parse(ROOT / "rk16_ppt_final_v1.xml").getroot()
before_slides = [node for node in list(before) if local(node) == "slide"]
after_slides = [node for node in list(after) if local(node) == "slide"]
record("canvas_unchanged", (after.get("width"), after.get("height")) == ("960", "540"), [after.get("width"), after.get("height")])
record("page_count_and_order", len(before_slides) == 111 and len(after_slides) == 112 and after_slides[-1].get("id") == "pZo" and after_slides[-2].get("id") == "pZn", {"before": len(before_slides), "after": len(after_slides), "last": after_slides[-1].get("id")})
record("old_slide_ids_preserved", [s.get("id") for s in before_slides] == [s.get("id") for s in after_slides[:111]])
exact_differences = [i for i, (a, b) in enumerate(zip(before_slides, after_slides), 1) if ET.tostring(a) != ET.tostring(b)]
semantic_differences = [i for i, (a, b) in enumerate(zip(before_slides, after_slides), 1) if semantic(a) != semantic(b)]
record("first_110_exact_xml_preserved", not [i for i in exact_differences if i <= 110], exact_differences)
record("all_111_old_pages_semantically_preserved", not semantic_differences, {"exact_difference_pages": exact_differences, "semantic_difference_pages": semantic_differences})

new_slide = after_slides[-1]
data = next(node for node in list(new_slide) if local(node) == "data")
elements = list(data)
record("new_page_element_count", len(elements) == 34, len(elements))
record("new_page_supported_elements", not any(local(node) == "undefined" for node in new_slide.iter()) and not any(local(node) in {"image", "video"} for node in data.iter()))
record("new_page_single_native_table", sum(local(node) == "table" for node in elements) == 1)

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
record("new_page_inside_canvas", not geometry_errors, geometry_errors)

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
record("new_page_no_unintended_overlap", not overlap_errors, overlap_errors)

text = "\n".join("".join(node.itertext()).strip() for node in data.iter() if local(node) == "content")
required_texts = (
    "LinearDesign leads the frozen dense-prefix comparison", "18 UNIQUE18", "792", "6 / 6 PASS", "88 / 88",
    "22.794606", "29.972887", "14.896234", "16.693982", "5.205444", "7.989211", "0.702952", "0.966618",
    "+7.898372 AUC", "+13.278905 B11 HV", "Holm p = 0.00059997", "+ 53 / 53 FINALIZATION",
    "No wall-time, functional, CodonFlow-RK or SOTA claim.", "Time-matched = false",
    "functional OOD / untouched = false", "RK-G1 = false", "generator training unauthorized", "112 · RK16",
)
record("new_page_required_claims", all(token in text for token in required_texts), [token for token in required_texts if token not in text])
font_errors = [node for node in data.iter() if local(node) == "content" and "".join(node.itertext()).strip() and node.get("fontFamily") != "Inter"]
record("new_page_inter_font", not font_errors, len(font_errors))

tables = [node for node in elements if local(node) == "table"]
table = tables[0]
cols_parent = next((node for node in list(table) if local(node) in {"colgroup", "tblGrid"}), None)
cols = list(cols_parent) if cols_parent is not None else []
rows = [node for node in list(table) if local(node) == "tr"]
widths = [float(node.get("width")) * int(node.get("span", "1")) for node in cols]
heights = [float(node.get("height")) for node in rows]
record("final_table_dimensions", sum(widths) == float(table.get("width")) == 864 and sum(heights) == float(table.get("height")) == 140, {"widths": widths, "heights": heights})
record("final_table_shape", len(rows) == 5 and all(len([cell for cell in list(row) if local(cell) == "td"]) == 3 for row in rows), [len(list(row)) for row in rows])
record("final_table_header_fill", all(any(local(child) == "fill" for child in list(cell)) for cell in list(rows[0])))

notes = [node for node in list(new_slide) if local(node) == "note"]
note = notes[0]
paragraphs = ["".join(node.itertext()).strip() for node in note.iter() if local(node) == "p"]
note_text = "\n".join(paragraphs)
record("speaker_notes_five_paragraphs", len(paragraphs) == 5 and all(paragraphs), [len(p) for p in paragraphs])
required_note_tokens = ("88/88", "53/53", "59/59", "347 passed and 1 skipped", "is not time-matched", "functional OOD and untouched remain unevaluated", "full seven-method dense coverage", "external SOTA", "RK-G1 remains false", "generator training remains unauthorized", "4115d281abe4a798b05525dff43f751460ee03a3")
record("speaker_notes_complete", all(token in note_text for token in required_note_tokens), [token for token in required_note_tokens if token not in note_text])

update_source = ET.parse(ROOT / "rk16_ppt_slide112_note_fix_v1.xml").getroot()
update_data = next(node for node in list(update_source) if local(node) == "data")
record("final_visible_data_matches_approved_update", semantic(update_data) == semantic(data))
record("official_final_raw_inspection", raw["presentation"]["slide_count"] == 112 and raw["selection"]["output_slide_count"] == 1 and raw["slides"][0]["index"] == 112 and raw["slides"][0]["slide_id"] == "pZo" and "LinearDesign leads the frozen dense-prefix comparison" in raw["slides"][0]["raw_xml"], {"slides": raw["presentation"]["slide_count"], "selected": raw["slides"][0]["slide_id"]})

passed = sum(bool(check["pass"]) for check in checks)
report = {
    "schema": "a8-rk16-ppt-verification-v1",
    "status": "PASS" if passed == len(checks) else "FAIL",
    "presentation_id": "WB1KsYGualerMUddEzMcCw1En0g",
    "url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
    "slide_number": 112,
    "slide_id": "pZo",
    "revision_id": 75,
    "baseline_pages": 111,
    "final_pages": 112,
    "old_page_exact_difference_pages": exact_differences,
    "old_page_semantic_difference_pages": semantic_differences,
    "before_sha256": hashlib.sha256((ROOT / "rk16_ppt_before_write_v1.xml").read_bytes()).hexdigest(),
    "after_sha256": hashlib.sha256((ROOT / "rk16_ppt_final_v1.xml").read_bytes()).hexdigest(),
    "checks_passed": passed,
    "checks_total": len(checks),
    "checks": checks,
}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "slide": "112:pZo", "revision": 75, "old_page_semantic_differences": semantic_differences, "output": str(OUT)}, ensure_ascii=False))
raise SystemExit(0 if report["status"] == "PASS" else 1)
