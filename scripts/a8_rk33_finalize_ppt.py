#!/usr/bin/env python3
"""Finalize RK33 slide-delivery evidence after live XML, per-page audits and visual review."""
from pathlib import Path
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET

PAGES = [148, 149, 150, 151, 152, 153, 154, 155]
IDS = ["pZV", "pZs", "pZT", "pZY", "pZv", "pZI", "pZj", "pZM"]
AUDIT_VERSION = {148: 1, 149: 1, 150: 2, 151: 3, 152: 1, 153: 1, 154: 1, 155: 1}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def slides(path):
    root = ET.parse(path).getroot()
    return root, [x for x in list(root) if x.tag.endswith("slide")]


def canonical_slide(slide):
    return ET.tostring(slide, encoding="unicode").strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ppt-dir", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    d = args.ppt_dir
    pre_root, pre = slides(d / "rk33_pre_write_v1.xml")
    final_root, final = slides(d / "rk33_final_v1.xml")
    final_response = json.loads((d / "rk33_final_response_v1.json").read_text())
    checks = []

    def check(name, ok, details):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    check("final_read_success", final_response.get("ok") is True, {"ok": final_response.get("ok")})
    check("155_slides", len(final) == 155, len(final))
    check("new_slide_order", [s.attrib.get("id") for s in final[-8:]] == IDS, [s.attrib.get("id") for s in final[-8:]])
    check("canvas_unchanged", pre_root.attrib.get("width") == final_root.attrib.get("width") == "960" and pre_root.attrib.get("height") == final_root.attrib.get("height") == "540", {"width": final_root.attrib.get("width"), "height": final_root.attrib.get("height")})
    exact = len(pre) == 147 and all(canonical_slide(a) == canonical_slide(b) for a, b in zip(pre, final[:147]))
    check("original_147_content_exact_ignoring_inter_slide_whitespace", exact, {"pre_slides": len(pre), "compared": 147, "note": "The only raw difference is whitespace after former last slide pZJ; slide XML content is identical."})
    page_records = []
    for page, sid in zip(PAGES, IDS):
        version = AUDIT_VERSION[page]
        audit_path = d / f"rk33_{page}_audit_v{version}.json"
        audit = json.loads(audit_path.read_text())
        check(f"page_{page}_readback_pass", audit.get("status") == "PASS" and audit.get("slide_id") == sid, {"status": audit.get("status"), "slide_id": audit.get("slide_id"), "checks": f'{audit.get("checks_passed")}/{audit.get("checks_total")}', "audit": audit_path.name, "audit_sha256": sha(audit_path)})
        if page == 151:
            shot_response_path = d / "rk33_151_screenshot_response_v3.json"
            shot_response = json.loads(shot_response_path.read_text())
            shot = shot_response.get("data", {}).get("screenshots", [])[0]
        else:
            shot_response_path = d / "rk33_screenshots_response_v1.json"
            shot_response = json.loads(shot_response_path.read_text())
            shot = next(x for x in shot_response.get("data", {}).get("screenshots", []) if x.get("slide_number") == page)
        shot_path = Path(shot["path"])
        if not shot_path.is_file():
            shot_path = d / "screenshots" / shot_path.name
        check(f"page_{page}_screenshot_exists", shot_response.get("ok") is True and shot_path.is_file() and shot_path.stat().st_size > 0, {"path": str(shot_path), "bytes": shot_path.stat().st_size if shot_path.is_file() else None, "sha256": sha(shot_path) if shot_path.is_file() else None})
        page_records.append({"page": page, "slide_id": sid, "audit_report": audit_path.name, "audit_status": audit.get("status"), "screenshot": str(shot_path), "visual_review": "PASS", "visual_note": "Full comparison labels restored and column widths verified" if page == 151 else "No clipping, overlap, blank block or visible content error observed"})
    report = {
        "schema": "a8-rk33-research-record-closeout-v1",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "presentation_id": "WB1KsYGualerMUddEzMcCw1En0g",
        "baseline_revision_id": 112,
        "final_revision_id": final_response.get("data", {}).get("revision_id"),
        "baseline_slide_count": len(pre),
        "final_slide_count": len(final),
        "pages": page_records,
        "checks": checks,
        "checks_passed": sum(c["pass"] for c in checks),
        "checks_total": len(checks),
        "failed_checks": [c["name"] for c in checks if not c["pass"]],
        "final_xml_sha256": sha(d / "rk33_final_v1.xml"),
        "final_response_sha256": sha(d / "rk33_final_response_v1.json"),
        "scientific_scope": "RK33 retrospective observed-R1 local-versus-full coverage follow-up only; no independent untouched, functional/protein OOD, external-SOTA, time-matched, full seven-method dense or RK-G1 closure.",
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f'{report["checks_passed"]}/{report["checks_total"]}', "failed": report["failed_checks"], "final_revision": report["final_revision_id"], "slides": report["final_slide_count"]}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
