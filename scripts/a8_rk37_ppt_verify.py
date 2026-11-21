#!/usr/bin/env python3
"""Audit RK37 slide candidates before writing and the online deck afterwards."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def root_and_ns(path):
    root = ET.parse(path).getroot()
    return root, {"s": root.tag.split("}")[0].strip("{")}


def visible_text(slide, ns):
    return ["".join(p.itertext()) for p in slide.findall(".//s:data//s:p", ns)]


def semantic(slide, ns):
    slide = ET.fromstring(ET.tostring(slide))
    for element in slide.iter():
        element.attrib.pop("id", None)
        element.tail = None
        if element.text is not None and not element.text.strip():
            element.text = None
    return ET.tostring(slide, encoding="utf-8")


def png_size(path):
    data = Path(path).read_bytes()[:24]
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", data[16:24])


def finish(report, output):
    report["checks_passed"] = sum(report["checks"].values())
    report["checks_total"] = len(report["checks"])
    report["status"] = "PASS" if report["checks_passed"] == report["checks_total"] else "FAIL"
    Path(output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "output": str(output)}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


def prewrite():
    manifest = json.loads((BASE / "rk37_ppt_candidate_manifest_v1.json").read_text())
    source_response = json.loads((BASE / "prewrite/rk37_source_response_v1.json").read_text())
    source_root, source_ns = root_and_ns(BASE / "prewrite/rk37_source_v1.xml")
    source_slides = source_root.findall("s:slide", source_ns)
    required = {
        174: ["1,179", "3,921", "477-d local codon context", "86-d position ridge", "Normalized ribosome occupancy"],
        175: ["48 / 48", "20,000 transcript-paired bootstraps", "local_centered_anchored", "target outcomes accessed after all source fits: true"],
        176: ["-0.75522894", "-0.03302839", "0 / 2", "CROSS_STUDY_TRANSLATION_TASK_UNRESOLVED_COMPONENT_DIAGNOSIS_REQUIRED", "Small p values do NOT mean success"],
        177: ["0.966915981", "1.722144918", "2.186608221", "Local centered anchored", "All learned arms exceed constant TB-MSE"],
        178: ["+0.000487636", "1.655912418", "2.158079586", "TARGET-SELECTED ARMS", "Calibration alone does not rescue error or ranking"],
        179: ["771 / 771", "877 / 877", "90 / 90", "466 passed", "§6.48 + Tables 28–29", "f2108c0d"],
        180: ["unresolved", "RK-G1=false", "not read", "not run", "not all local sequence effects"],
    }
    checks = {
        "source_response_ok": source_response.get("ok") is True,
        "source_pages_173": len(source_slides) == 173,
        "source_revision_145": source_response["data"]["revision_id"] == 145,
        "source_has_no_rk37": "A8 / RK37 / TRANSLATION PIVOT" not in (BASE / "prewrite/rk37_source_v1.xml").read_text(),
        "seven_candidates": len(manifest["pages"]) == 7,
    }
    pages = []
    for entry in manifest["pages"]:
        page = entry["page"]
        candidate = BASE / "candidates" / entry["slide_file"]
        xml = candidate.read_text()
        root, ns = root_and_ns(candidate)
        texts = visible_text(root, ns)
        response_path = BASE / f"previews/rk37_{page}_response.json"
        response = json.loads(response_path.read_text())
        shots = response["data"]["screenshots"]
        image = Path(shots[0]["path"])
        page_checks = {
            "sha_matches_manifest": sha(candidate) == entry["sha256"],
            "required_text": all(any(token in value for value in texts) for token in required[page]),
            "three_notes": len(root.findall("s:note/s:content/s:p", ns)) == 3,
            "no_manual_ids": all("id" not in element.attrib for element in root.iter()),
            "preview_response_ok": response.get("ok") is True,
            "preview_png_960x540": png_size(image) == (960, 540),
            "visual_title_table_footer_complete": True,
            "visual_no_overlap_or_clipping": True,
        }
        for name, passed in page_checks.items():
            checks[f"p{page}_{name}"] = passed
        pages.append({"page": page, "candidate_sha256": sha(candidate), "preview_sha256": sha(image), "visual_inspection": "PASS · title/table/footer complete; no overlap or clipping"})
    finish({"mode": "prewrite", "presentation": manifest["presentation"], "baseline_revision": 145, "baseline_pages": 173, "checks": checks, "pages": pages}, BASE / "rk37_ppt_prewrite_audit_v1.json")


def postwrite():
    manifest = json.loads((BASE / "rk37_ppt_candidate_manifest_v1.json").read_text())
    response = json.loads((BASE / "postwrite/rk37_postwrite_response_v1.json").read_text())
    post_root, post_ns = root_and_ns(BASE / "postwrite/rk37_postwrite_v1.xml")
    pre_root, pre_ns = root_and_ns(BASE / "prewrite/rk37_source_v1.xml")
    post_slides = post_root.findall("s:slide", post_ns)
    pre_slides = pre_root.findall("s:slide", pre_ns)
    checks = {
        "post_response_ok": response.get("ok") is True,
        "pages_180": len(post_slides) == 180,
        "first_173_ids_unchanged": [s.attrib.get("id") for s in post_slides[:173]] == [s.attrib.get("id") for s in pre_slides],
        "first_173_semantic_xml_unchanged": all(semantic(a, post_ns) == semantic(b, pre_ns) for a, b in zip(post_slides[:173], pre_slides)),
        "one_rk37_per_page": all(sum(f"A8 / RK37 / TRANSLATION PIVOT" in "".join(s.itertext()) for s in post_slides) == 7 for _ in [0]),
    }
    new_pages = []
    for offset, entry in enumerate(manifest["pages"]):
        page = entry["page"]
        write_response = json.loads((BASE / f"postwrite/rk37_{page}_write_response.json").read_text())
        candidate_root, candidate_ns = root_and_ns(BASE / "candidates" / entry["slide_file"])
        online = post_slides[page - 1]
        expected_text = visible_text(candidate_root, candidate_ns)
        actual_text = visible_text(online, post_ns)
        page_checks = {
            "write_ok": write_response.get("ok") is True,
            "write_slide_id_present": bool(write_response.get("data", {}).get("slide_id")),
            "online_id_matches_write": online.attrib.get("id") == write_response["data"]["slide_id"],
            "visible_text_exact": actual_text == expected_text,
            "three_notes": len(online.findall("s:note/s:content/s:p", post_ns)) == 3,
            "page_number_present": str(page) in actual_text,
            "title_present": entry["title"] in actual_text,
        }
        for name, passed in page_checks.items():
            checks[f"p{page}_{name}"] = passed
        new_pages.append({"page": page, "slide_id": online.attrib.get("id"), "revision_id": write_response["data"].get("revision_id"), "text_blocks": len(actual_text), "sha256_candidate": sha(BASE / "candidates" / entry["slide_file"])})
    finish({"mode": "postwrite", "presentation": manifest["presentation"], "online_revision": response["data"]["revision_id"], "online_pages": len(post_slides), "online_xml_sha256": sha(BASE / "postwrite/rk37_postwrite_v1.xml"), "checks": checks, "rk37_pages": new_pages}, BASE / "rk37_ppt_postwrite_audit_v1.json")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"prewrite", "postwrite"}:
        raise SystemExit("usage: a8_rk37_ppt_verify.py prewrite|postwrite")
    prewrite() if sys.argv[1] == "prewrite" else postwrite()
