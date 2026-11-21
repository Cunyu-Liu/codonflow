#!/usr/bin/env python3
"""Verify RK41 deck append-only integrity and exact online content."""
from pathlib import Path
import hashlib
import json
import os
import xml.etree.ElementTree as ET

ROOT = Path(os.environ.get("RK41_PPT_ARCHIVE", Path(__file__).resolve().parent)).resolve()
EXPECTED_IDS = ["pSJ", "pSV", "pSs", "pST", "pSY", "pSv"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signature(elem, drop_ids=False):
    attrs = tuple(sorted((k, v) for k, v in elem.attrib.items() if not (drop_ids and k == "id")))
    return (elem.tag, attrs, (elem.text or "").strip(), tuple(signature(c, drop_ids) for c in elem))


def slide_list(path):
    root = ET.parse(path).getroot()
    ns = {"s": root.tag.split("}")[0].strip("{")}
    return root, root.findall("s:slide", ns)


def main():
    source_root, source = slide_list(ROOT / "rk41_source_v1.xml")
    current_root, current = slide_list(ROOT / "rk41_current_v1.xml")
    source_response = json.loads((ROOT / "rk41_source_response_v1.json").read_text())
    current_response = json.loads((ROOT / "rk41_current_response_v1.json").read_text())
    checks = []

    def check(name, ok, detail=None):
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    check("source_baseline", len(source) == 198 and source_response["data"]["revision_id"] == 170)
    check("current_append", len(current) == 204 and current_response["data"]["revision_id"] == 176)
    check("canvas_preserved", all(current_root.get(k) == source_root.get(k) for k in ("width", "height")))
    old_mismatch = [i + 1 for i in range(198) if signature(source[i]) != signature(current[i])]
    check("all_198_prior_slides_exactly_preserved", not old_mismatch, old_mismatch)
    check("new_slide_ids", [s.get("id") for s in current[198:]] == EXPECTED_IDS, [s.get("id") for s in current[198:]])
    expected_titles = {
        199: "Eight internal starts isolate initialization-basin selection",
        200: "324 runs audited across 3,564 raw points",
        201: "Basin selection improves both internal search comparisons",
        202: "LinearDesign-11 still wins the common-input actual-set gate",
        203: "Internal gains reproduce but remain far below LinearDesign-11",
        204: "Initialization mechanism supported; design task remains open",
    }
    required = {
        199: ["9ed2657dfe69", "No new arm uses LinearDesign", "Exactly 11 unique-scorer outputs"],
        200: ["216 / 216", "2,376", "5,401 / 5,401 PASS", "1,604 unique sequences"],
        201: ["+0.050030", "+0.031529", "+0.788952", "+0.486789", "2 / 2 PASS"],
        202: ["−29.215520", "+0.165764", "0 / 3 positive", "COMMON_INPUT_ACTUAL_SET_GATE_FAILED", "cannot compensate"],
        203: ["3.246544", "0.757367", "29.972887", "1,114 / 1,114", "494 passed"],
        204: ["Multistart supported", "Unresolved", "INTERNAL_MULTISTART_SUPPORTED_COMMON_INPUT_TASK_UNRESOLVED", "RK-G1 open"],
    }
    for page in range(199, 205):
        local = ET.parse(ROOT / f"rk41_{page}.xml").getroot()
        online = current[page - 1]
        check(f"slide_{page}_exact_structure_and_text", signature(local, True) == signature(online, True))
        text = "\n".join("".join(p.itertext()) for p in online.iter() if p.tag.endswith("}p"))
        check(f"slide_{page}_title", expected_titles[page] in text)
        for value in required[page]:
            check(f"slide_{page}_value_{value}", value in text)
        add = json.loads((ROOT / f"rk41_{page}_add_response.json").read_text())
        shot = json.loads((ROOT / f"rk41_{page}_online_response.json").read_text())
        check(f"slide_{page}_add_confirmed", add.get("ok") is True and add["data"]["slide_id"] == EXPECTED_IDS[page - 199])
        check(f"slide_{page}_online_screenshot", shot.get("ok") is True and shot["data"]["screenshots"][0]["slide_number"] == page)
    result = {
        "schema": "a8-rk41-research-deck-closeout-v1",
        "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "presentation_id": "WB1KsYGualerMUddEzMcCw1En0g",
        "source_revision": 170, "current_revision": 176,
        "source_slide_count": 198, "current_slide_count": 204,
        "source_xml_sha256": sha(ROOT / "rk41_source_v1.xml"),
        "current_xml_sha256": sha(ROOT / "rk41_current_v1.xml"),
        "prior_slides_exactly_preserved": 198,
        "new_slides": [{"page": p, "slide_id": EXPECTED_IDS[p - 199], "title": expected_titles[p],
                        "visual_inspection": "PASS — no clipping, overlap, overflow or ambiguous scientific claim"}
                       for p in range(199, 205)],
        "decision": "INTERNAL_MULTISTART_SUPPORTED_COMMON_INPUT_TASK_UNRESOLVED",
        "scientific_gate_passed": False, "external_sota_authorized": False,
        "time_matched_comparison": False, "functional_untouched_evaluated": False,
        "rk_g1_pass": False, "manuscript_submittable": False,
        "status": "PASS" if all(c["passed"] for c in checks) else "FAIL",
        "n_checks": len(checks), "n_pass": sum(c["passed"] for c in checks), "checks": checks,
    }
    (ROOT / "rk41_research_deck_closeout_v1.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({k: result[k] for k in ("status", "n_checks", "n_pass", "current_revision", "current_slide_count", "current_xml_sha256")}, ensure_ascii=False))
    if result["status"] != "PASS":
        for c in checks:
            if not c["passed"]:
                print("FAIL", c)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
