#!/usr/bin/env python3
"""Read-back verification for the RK08 velocity result slide and unchanged deck prefix."""
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

NS_URI = "https://www.larkoffice.com/sml/2.0"
NS = {"s": NS_URI}


def load(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local(name):
    return name.rsplit("}", 1)[-1]


def semantic(element):
    """Namespace-independent semantic XML; discard formatting-only tail whitespace."""
    text = element.text if element.text and element.text.strip() else None
    return (
        local(element.tag),
        tuple(sorted((local(key), value) for key, value in element.attrib.items())),
        text,
        tuple(semantic(child) for child in list(element)),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--after-response", required=True)
    parser.add_argument("--add-response", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--preflight", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    before_root = ET.parse(args.before).getroot()
    after_root = ET.parse(args.after).getroot()
    before = before_root.findall("s:slide", NS)
    after = after_root.findall("s:slide", NS)
    add = load(args.add_response)
    after_response = load(args.after_response)
    preflight = load(args.preflight)
    new_slide = after[-1]
    visible = " ".join("".join(p.itertext()) for p in new_slide.findall(".//s:data//s:p", NS))
    notes = ["".join(p.itertext()).strip() for p in new_slide.findall(".//s:note//s:p", NS)]
    table_rows = new_slide.findall(".//s:table/s:tr", NS)
    prefix_semantic_matches = [semantic(old) == semantic(new) for old, new in zip(before, after[:len(before)])]
    old_ids = [slide.get("id") for slide in before]
    new_prefix_ids = [slide.get("id") for slide in after[:len(before)]]
    required_text = [
        "占据衍生速度代理：主 OOD 显著落后 ridge",
        "+0.0546", "95% CI [+0.0540, +0.0552]",
        "−0.0705", "95% CI [−0.0732, −0.0678]",
        "0.2306 / 0.1759", "−0.0088 / 0.0617",
        "VELOCITY GATE = FALSE", "RK-G1 未通过",
        "非物理速度 / homology OOD / 功能迁移",
        "26/26 + 12/12 · VERIFIED",
    ]
    missing_text = [text for text in required_text if text not in visible]
    checks = {
        "preflight_19_pass": preflight["status"] == "PASS" and preflight["checks_passed"] == preflight["checks_total"] == 19,
        "candidate_hash_matches_preflight": sha256(args.candidate) == preflight["candidate_sha256"],
        "add_response_success": add.get("ok") is True and bool(add.get("data", {}).get("slide_id")),
        "readback_response_success": after_response.get("ok") is True,
        "slide_count_84_to_85": len(before) == 84 and len(after) == 85,
        "new_slide_is_last_and_id_matches": new_slide.get("id") == add["data"]["slide_id"],
        "revision_advanced_to_47": add["data"].get("revision_id") == 47 and after_response.get("data", {}).get("revision_id") == 47,
        "all_84_slide_ids_unchanged": old_ids == new_prefix_ids,
        "all_84_semantic_xml_unchanged": all(prefix_semantic_matches),
        "new_slide_required_results_present": not missing_text,
        "new_slide_has_header_plus_five_rows": len(table_rows) == 6,
        "new_slide_has_four_note_sentences": len(notes) == 4 and all(notes),
        "new_slide_has_no_undefined_objects": not new_slide.findall(".//s:undefined", NS),
        "negative_gate_not_changed": "VELOCITY GATE = TRUE" not in visible and "RK-G1 = TRUE" not in visible,
    }
    failures = [name for name, passed in checks.items() if not passed]
    report = {
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "checks_passed": len(checks) - len(failures),
        "checks_total": len(checks),
        "failures": failures,
        "missing_required_text": missing_text,
        "prefix_semantic_mismatch_indices": [index + 1 for index, passed in enumerate(prefix_semantic_matches) if not passed],
        "preexisting_slide_count": len(before),
        "final_slide_count": len(after),
        "new_slide_id": new_slide.get("id"),
        "revision_id": after_response.get("data", {}).get("revision_id"),
        "before_sha256": sha256(args.before),
        "after_sha256": sha256(args.after),
        "candidate_sha256": sha256(args.candidate),
        "new_slide_semantic_sha256": hashlib.sha256(repr(semantic(new_slide)).encode()).hexdigest(),
        "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "velocity_mechanism_pass": False,
        "rk_g1_pass": False,
        "expensive_generation_authorized": False,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
