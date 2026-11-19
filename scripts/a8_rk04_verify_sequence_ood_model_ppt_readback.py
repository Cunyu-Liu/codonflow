#!/usr/bin/env python3
import copy
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def slides_and_ns(path):
    root = ET.parse(path).getroot()
    ns = root.tag[1:].split("}")[0]
    return root.findall(f"{{{ns}}}slide"), ns


def canonical(element):
    element = copy.deepcopy(element)
    for node in element.iter():
        node.attrib.pop("id", None)
        if node.text is not None and not node.text.strip():
            node.text = None
        if node.tail is not None and not node.tail.strip():
            node.tail = None
    return ET.tostring(element, encoding="utf-8")


def main():
    directory = Path(sys.argv[1]).resolve()
    before_path = directory / "rk04_model_before_v01.xml"
    after_path = directory / "rk04_model_after_v01.xml"
    candidate_path = directory / "rk04_sequence_ood_model_page81_v01.xml"
    add_response_path = directory / "rk04_model_add_response_v01.json"
    candidate_report_path = directory / "rk04_model_ppt_candidate_verification.json"
    output_path = directory / "rk04_model_ppt_verification.json"
    before, before_ns = slides_and_ns(before_path)
    after, after_ns = slides_and_ns(after_path)
    candidate = ET.parse(candidate_path).getroot()
    candidate_ns = candidate.tag[1:].split("}")[0]
    add_response = json.loads(add_response_path.read_text())
    candidate_report = json.loads(candidate_report_path.read_text())
    new_slide_id = add_response["data"]["slide_id"]
    new_slide = after[-1]
    checks = []

    def check(name, condition, detail):
        checks.append({"name": name, "status": "PASS" if condition else "FAIL", "detail": detail})

    check("write_response", add_response.get("ok") is True and add_response["data"]["revision_id"] == 43 and bool(new_slide_id), add_response["data"])
    check("candidate_precheck", candidate_report["status"] == "PASS" and candidate_report["summary"]["checks"] == "21/21", candidate_report["summary"])
    check("slide_count_81", len(before) == 80 and len(after) == 81, {"before": len(before), "after": len(after)})
    check("new_slide_id", new_slide.attrib.get("id") == new_slide_id, new_slide.attrib.get("id"))
    check("previous_slide_ids_unchanged", [s.attrib.get("id") for s in before] == [s.attrib.get("id") for s in after[:80]], "80/80")
    semantic_differences = [index + 1 for index in range(80) if canonical(before[index]) != canonical(after[index])]
    check("previous_semantic_xml_unchanged", not semantic_differences, semantic_differences)
    candidate_paragraphs = [p.text or "" for p in candidate.iter(f"{{{candidate_ns}}}p")]
    actual_paragraphs = [p.text or "" for p in new_slide.iter(f"{{{after_ns}}}p")]
    check("candidate_paragraphs_preserved", all(text in actual_paragraphs for text in candidate_paragraphs), {"candidate": len(candidate_paragraphs), "actual": len(actual_paragraphs)})
    candidate_notes = [p.text or "" for p in candidate.findall(f"{{{candidate_ns}}}note/{{{candidate_ns}}}content/{{{candidate_ns}}}p")]
    actual_notes = [p.text or "" for p in new_slide.findall(f"{{{after_ns}}}note/{{{after_ns}}}content/{{{after_ns}}}p")]
    check("speaker_notes_preserved", candidate_notes == actual_notes and len(actual_notes) == 4, len(actual_notes))
    check("no_undefined_objects", not list(new_slide.iter(f"{{{after_ns}}}undefined")), "none")
    check("single_result_title", actual_paragraphs.count("sequence-OOD：组合代理特征优于 GC-only") == 1, "unique")
    check("result_and_boundary_visible", "+0.146000" in actual_paragraphs and any("Test 增量 CI 跨 0" in text and "不支持机制、生成器或 SOTA 声称" in text for text in actual_paragraphs), "gain and limitation")
    in_bounds = True
    for element in new_slide.iter():
        attrs = element.attrib
        if all(key in attrs for key in ["topLeftX", "topLeftY", "width", "height"]):
            in_bounds &= float(attrs["topLeftX"]) >= 0 and float(attrs["topLeftY"]) >= 0
            in_bounds &= float(attrs["topLeftX"]) + float(attrs["width"]) <= 960
            in_bounds &= float(attrs["topLeftY"]) + float(attrs["height"]) <= 540
    check("new_elements_in_canvas", in_bounds, "960x540")
    failed = [c for c in checks if c["status"] == "FAIL"]
    report = {
        "protocol_id": "a8_rk04_model_ppt_readback_verification_v1",
        "status": "PASS" if not failed else "FAIL",
        "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "presentation_id": "WB1KsYGualerMUddEzMcCw1En0g",
        "new_slide_id": new_slide_id,
        "new_slide_number": 81,
        "revision_id": add_response["data"]["revision_id"],
        "checks": checks,
        "summary": {"checks": f"{len(checks)-len(failed)}/{len(checks)}", "failed": [c["name"] for c in failed]},
        "evidence": {
            "before_xml": str(before_path), "before_xml_sha256": sha(before_path),
            "after_xml": str(after_path), "after_xml_sha256": sha(after_path),
            "candidate_xml": str(candidate_path), "candidate_xml_sha256": sha(candidate_path),
            "add_response": str(add_response_path), "add_response_sha256": sha(add_response_path),
            "candidate_verification": str(candidate_report_path), "candidate_verification_sha256": sha(candidate_report_path),
        },
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({**report["summary"], "status": report["status"], "new_slide_id": new_slide_id, "after_xml_sha256": sha(after_path)}, ensure_ascii=False))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
