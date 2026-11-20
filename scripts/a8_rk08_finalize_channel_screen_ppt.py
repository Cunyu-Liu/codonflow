#!/usr/bin/env python3
"""Finalize the RK08 channel-screen slide after online and visual acceptance."""
from __future__ import annotations
import argparse, hashlib, json
import xml.etree.ElementTree as ET
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    w = Path(args.work_dir)
    candidate = load(w / "rk08_candidate_verification_v01.json")
    verification = load(w / "rk08_ppt_verification_v01.json")
    correction = load(w / "rk08_ppt_correction_v01.json")
    visual = load(w / "rk08_ppt_visual_review_v01.json")
    add = load(w / "rk08_add_response_v01.json")
    after_response = load(w / "rk08_after_response_v01.json")
    shot_response = load(w / "rk08_screenshot_response_v01.json")
    before = ET.parse(w / "rk08_source_v02.xml").getroot()
    after = ET.parse(w / "rk08_after_v01.xml").getroot()
    bn = before.tag.split("}")[0] + "}"
    an = after.tag.split("}")[0] + "}"
    old_pages = before.findall(bn + "slide")
    pages = after.findall(an + "slide")
    checks = []
    def ck(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})
    ck("candidate_acceptance", candidate["overall_pass"] is True and candidate["check_counts"] == {"passed": 103, "total": 103})
    ck("final_acceptance", verification["overall_pass"] is True and verification["check_counts"] == {"passed": 223, "total": 223})
    ck("correction_scope", correction["scientific_content_changed"] is False and correction["online_slide_changed_after_failure"] is False and correction["scope"] == "verifier_normalization_only")
    ck("correction_hashes", correction["final_report_sha256"] == sha(w / "rk08_ppt_verification_v01.json"))
    ck("add_success", add.get("ok") is True and add.get("data", {}).get("slide_id") == "pZZ" and add.get("data", {}).get("revision_id") == 69)
    ck("readback_success", after_response.get("ok") is True and after_response.get("data", {}).get("revision_id") == 69)
    ck("page_count", len(old_pages) == 106 and len(pages) == 107 and pages[-1].get("id") == "pZZ")
    ck("old_page_ids", [s.get("id") for s in old_pages] == [s.get("id") for s in pages[:106]])
    old_semantic = [c for c in verification["checks"] if c["name"].startswith("old_page_semantics_")]
    ck("old_page_semantics", len(old_semantic) == 106 and all(c["pass"] for c in old_semantic))
    ck("visual_acceptance", visual["visual_pass"] is True and visual["slide_id"] == "pZZ" and visual["page"] == 107 and visual["canvas"] == [960, 540])
    ck("visual_boundaries", all(visual[key] for key in ["no_overflow", "no_overlap", "legible", "negative_gate_visible", "table_aligned"]))
    shots = shot_response.get("data", {}).get("screenshots", [])
    ck("screenshot_response", shot_response.get("ok") is True and len(shots) == 1 and shots[0].get("slide_id") == "pZZ" and shots[0].get("slide_number") == 107)
    screenshot = w / "rk08_screenshots_v01" / Path(shots[0]["path"]).name
    ck("screenshot_file", screenshot.is_file() and screenshot.stat().st_size > 10000, screenshot.name)
    ck("screenshot_hash_binding", visual["screenshot_sha256"] == sha(screenshot))
    ck("candidate_hash_binding", verification["candidate_sha256"] == sha(w / "rk08_slide_v01.xml"))
    ck("before_after_hash_binding", verification["source_sha256"] == sha(w / "rk08_source_v02.xml") and verification["after_sha256"] == sha(w / "rk08_after_v01.xml"))
    ck("science_hash_binding", verification["evaluation_sha256"] == "825bb36e0f8bc24586f614916a2090dd22d2fe6162d65508dc7d036250ea45ed" and verification["independent_sha256"] == "3a5c0c5342e3421fa81298fc893655055c112425551bcc36c1c1c7f200a8565f")
    ck("negative_gates", all(verification[key] is False for key in ["channel_screen_gate_pass", "rk_g1_pass", "functional_untouched_evaluated", "generator_training_authorized"]))
    passed = sum(c["pass"] for c in checks)
    result = {
        "schema": "a8-rk08-channel-screen-ppt-finalization-v1",
        "status": "PASS_RK08_CHANNEL_SCREEN_PPT_CLOSEOUT" if passed == len(checks) else "FAIL",
        "overall_pass": passed == len(checks),
        "check_counts": {"passed": passed, "total": len(checks)},
        "presentation_id": "WB1KsYGualerMUddEzMcCw1En0g",
        "slide_id": "pZZ", "page": 107, "revision_id": 69,
        "candidate_verification_sha256": sha(w / "rk08_candidate_verification_v01.json"),
        "verification_sha256": sha(w / "rk08_ppt_verification_v01.json"),
        "correction_sha256": sha(w / "rk08_ppt_correction_v01.json"),
        "visual_review_sha256": sha(w / "rk08_ppt_visual_review_v01.json"),
        "screenshot_sha256": sha(screenshot),
        "source_xml_sha256": sha(w / "rk08_source_v02.xml"),
        "after_xml_sha256": sha(w / "rk08_after_v01.xml"),
        "scientific_head_at_record": "7d5e51a17f93218e831bc22b845c030065362a35",
        "channel_screen_gate_pass": False, "rk_g1_pass": False,
        "functional_untouched_evaluated": False, "generator_training_authorized": False,
        "checks": checks,
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "check_counts": result["check_counts"], "slide_id": "pZZ", "page": 107}, indent=2))
    if passed != len(checks):
        for c in checks:
            if not c["pass"]: print("FAIL", c)
        raise SystemExit(1)

if __name__ == "__main__":
    main()
