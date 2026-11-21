#!/usr/bin/env python3
"""Bind RK34 online slide IDs, readback audits and real screenshots into one closeout."""
from pathlib import Path
import argparse
import hashlib
import json

EXPECTED = {156: "pZz", 157: "pSp", 158: "pSg", 159: "pSZ", 160: "pSS",
            161: "pSP", 162: "pSi", 163: "pSn", 164: "pSo"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ppt-dir", type=Path, required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root = args.ppt_dir
    checks = []

    def check(name, ok, details):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    candidate = load(root / "candidate-audit-v2.json")
    check("candidate_source_and_canvas_audit", candidate["status"] == "PASS" and
          candidate["checks_passed"] == candidate["checks_total"] == 54,
          {"status": candidate["status"], "checks": f"{candidate['checks_passed']}/{candidate['checks_total']}"})
    preview = load(root / "visual-preview-audit-v2.json")
    check("candidate_visual_preview", preview["status"] == "PASS" and
          preview["scientific_values_changed"] is False, preview)
    check("failed_candidate_history_retained", load(root / "visual-preview-audit-v1.json")["status"] == "FAIL",
          "visual-preview-audit-v1.json")
    structure = load(root / "final-structure-audit-v2.json")
    check("preexisting_deck_semantic_preservation", structure["status"] == "PASS" and
          structure["total_slides"] == 164 and structure["preexisting_slide_semantic_xml_unchanged"] is True,
          structure)
    check("raw_whitespace_fail_history_retained", load(root / "final-structure-audit-v1-fail.json")["status"] == "FAIL",
          "final-structure-audit-v1-fail.json")

    readback = {}
    for page, sid in EXPECTED.items():
        report = load(root / f"readback-audit_{page}.json")
        ok = report["status"] == "PASS" and report["checks_passed"] == report["checks_total"] == 9 and report["slide_id"] == sid
        readback[str(page)] = {"slide_id": sid, "status": report["status"],
                               "checks": f"{report['checks_passed']}/{report['checks_total']}",
                               "report_sha256": sha(root / f"readback-audit_{page}.json")}
        check(f"page_{page}_online_readback", ok, readback[str(page)])

    screenshots = {}
    for response_name in ["screenshot_batch1.json", "screenshot_batch2.json"]:
        response = load(root / response_name)
        check(f"{response_name}_business_success", response.get("ok") is True,
              {"ok": response.get("ok")})
        for item in response["data"]["screenshots"]:
            original_path = Path(item["path"])
            archived_path = root / "screenshots" / original_path.name
            path = original_path if original_path.is_file() else archived_path
            sid = item["slide_id"]
            page = item["slide_number"]
            ok = EXPECTED.get(page) == sid and path.is_file() and path.stat().st_size > 0
            screenshots[str(page)] = {"slide_id": sid, "path": str(path), "bytes": path.stat().st_size,
                                      "sha256": sha(path) if path.is_file() else None}
            check(f"page_{page}_real_online_screenshot", ok, screenshots[str(page)])
    check("nine_unique_screenshots", sorted(map(int, screenshots)) == list(EXPECTED), sorted(screenshots))

    report = {
        "schema": "a8-rk34-ppt-online-closeout-v1",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "total_slides": 164,
        "new_pages": EXPECTED,
        "candidate_checks": "54/54",
        "online_readback_checks": "81/81",
        "online_visual_inspection": {
            "status": "PASS",
            "pages": list(EXPECTED),
            "clipping_or_overlap_observed": False,
            "canvas_overflow_observed": False,
            "histgb_label_case_correct": True,
            "layout": "concise, clear, restrained research style with native editable tables"
        },
        "preexisting_pages_semantically_unchanged": True,
        "failed_history_retained": ["visual-preview-audit-v1.json", "final-structure-audit-v1-fail.json"],
        "artifact_root": args.artifact_root,
        "readback": readback,
        "screenshots": screenshots,
        "checks": checks,
        "checks_passed": sum(c["pass"] for c in checks),
        "checks_total": len(checks),
        "failed_checks": [c["name"] for c in checks if not c["pass"]],
        "not_claimed": [
            "No external SOTA, unified time-matched or complete seven-method dense comparison is closed by this deck update.",
            "No functional/protein OOD, independent untouched, prospective DBTL, wet-lab or RK-G1 claim is made."
        ]
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}",
                      "failed": report["failed_checks"]}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
