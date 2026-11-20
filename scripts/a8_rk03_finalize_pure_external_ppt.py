#!/usr/bin/env python3
"""Finalize the pure-external-RCS online slide after semantic and visual acceptance."""
from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def slides(root: ET.Element) -> list[ET.Element]:
    return [el for el in root.iter() if local(el.tag) == "slide"]


def paragraphs(slide: ET.Element, container: str) -> list[str]:
    parent = next(el for el in slide if local(el.tag) == container)
    return ["".join(p.itertext()).strip() for p in parent.iter() if local(p.tag) == "p"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    w = Path(args.work_dir)
    candidate = load(w / "pure_rcs_slide_candidate_verification_v01.json")
    candidate_visual = load(w / "pure_rcs_candidate_visual_review_v01.json")
    verification = load(w / "pure_rcs_slide_postwrite_verification_v01.json")
    visual = load(w / "pure_rcs_online_visual_review_v01.json")
    add = load(w / "pure_rcs_native_add_response_v01.json")
    request = load(w / "pure_rcs_native_add_request_v01.json")
    dry_run = load(w / "pure_rcs_add_dry_run_v01.json")
    after_response = load(w / "pure_rcs_after_response_v01.json")
    shot_response = load(w / "pure_rcs_screenshot_response_v01.json")
    science_postpush = load(w / "postpush_independent.json")
    paper_postpush = load(w / "paper_postpush_verification_v32.json")
    before = ET.parse(w / "pure_rcs_before_v02.xml").getroot()
    after = ET.parse(w / "pure_rcs_after_v01.xml").getroot()
    candidate_root = ET.parse(w / "pure_rcs_slide_candidate_v01.xml").getroot()
    old_pages = slides(before)
    pages = slides(after)
    checks = []

    def ck(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    ck("candidate_acceptance", candidate["overall_pass"] is True and candidate["checks_passed"] == 227 and candidate["checks_failed"] == 0)
    ck("candidate_hash", candidate["candidate_sha256"] == sha(w / "pure_rcs_slide_candidate_v01.xml"))
    ck("candidate_visual_acceptance", candidate_visual["status"] == "PASS_PREWRITE_VISUAL_REVIEW")
    ck("postwrite_acceptance", verification["overall_pass"] is True and verification["checks_passed"] == 553 and verification["checks_failed"] == 0)
    ck("postwrite_hash_bindings", verification["candidate_sha256"] == sha(w / "pure_rcs_slide_candidate_v01.xml") and verification["before_xml_sha256"] == sha(w / "pure_rcs_before_v02.xml") and verification["after_xml_sha256"] == sha(w / "pure_rcs_after_v01.xml"))
    ck("online_visual_acceptance", visual["visual_pass"] is True and visual["slide_id"] == "pZS" and visual["slide_number"] == 108 and visual["canvas"] == [960, 540])
    ck("online_visual_boundaries", all(visual[key] for key in ["no_overflow", "no_overlap", "legible", "negative_gate_visible", "table_aligned"]))
    ck("native_add_success", add.get("ok") is True and add.get("data", {}).get("slide_id") == "pZS" and add.get("data", {}).get("revision_id") == 70)
    ck("native_idempotency", request["params"]["idempotency_key"] == "codonflow-pure-rcs-20261120-v01" and request["candidate_sha256"] == sha(w / "pure_rcs_slide_candidate_v01.xml"))
    ck("dry_run_payload_matches_candidate", dry_run["data"]["api"][0]["body"]["slide"]["content"].rstrip("\n") == (w / "pure_rcs_slide_candidate_v01.xml").read_text().rstrip("\n"))
    ck("readback_success", after_response.get("ok") is True and after_response.get("data", {}).get("revision_id") == 70)
    ck("page_count", len(old_pages) == 107 and len(pages) == 108 and pages[-1].get("id") == "pZS")
    ck("old_page_ids", [s.get("id") for s in old_pages] == [s.get("id") for s in pages[:107]])
    old_semantic = [c for c in verification["checks"] if c["name"].startswith("old_page_") and c["name"].endswith("_full_semantics_unchanged")]
    ck("old_page_semantics", len(old_semantic) == 107 and all(c["pass"] for c in old_semantic))
    ck("new_page_visible_text", paragraphs(pages[-1], "data") == paragraphs(candidate_root, "data"))
    ck("new_page_notes", paragraphs(pages[-1], "note") == paragraphs(candidate_root, "note"))
    pure_hits = [i + 1 for i, s in enumerate(pages) if "Pure external RCS cannot replace intrinsic features" in " ".join(paragraphs(s, "data"))]
    ck("single_new_page", pure_hits == [108])
    shots = shot_response.get("data", {}).get("screenshots", [])
    ck("screenshot_response", shot_response.get("ok") is True and len(shots) == 1 and shots[0].get("slide_id") == "pZS" and shots[0].get("slide_number") == 108)
    screenshot = w / "pure_rcs_screenshots_v01" / Path(shots[0]["path"]).name
    ck("screenshot_file", screenshot.is_file() and screenshot.stat().st_size > 10000, screenshot.name)
    ck("screenshot_hash_binding", visual["screenshot_sha256"] == sha(screenshot))
    for name, key in [
        ("mage_pure_external_nested_cv_v1.json", "production_sha256"),
        ("mage_pure_external_nested_cv_independent_v1.json", "independent_sha256"),
        ("mage_pure_external_nested_cv_finalization_v1.json", "finalization_sha256"),
        ("postpush_independent.json", "science_postpush_sha256"),
        ("paper_postpush_verification_v32.json", "paper_postpush_sha256"),
    ]:
        ck(f"science_hash_{name}", verification[key] == candidate[key] == sha(w / name))
    ck("science_postpush", science_postpush["overall_pass"] is True and science_postpush["checks_passed"] == 174 and science_postpush["max_numeric_delta"] == 0.0)
    ck("paper_postpush", paper_postpush["overall_pass"] is True and paper_postpush["checks_passed"] == 100)
    for attempt in ("v01", "v02"):
        error = load(w / f"pure_rcs_add_error_{attempt}.json")
        state = load(w / f"pure_rcs_timeout_readback_state_{attempt}.json")
        ck(f"shortcut_{attempt}_timeout", error["ok"] is False and error["error"]["subtype"] == "timeout")
        ck(f"shortcut_{attempt}_not_landed", state["slide_count"] == 107 and state["last_slide_id"] == "pZZ" and state["pure_page_hits"] == [])
    ck("negative_gates", all(verification[key] is False for key in ["rk_g1_pass", "generator_training_authorized"]) and visual["test_authorized"] is False and visual["generator_training_authorized"] is False)
    passed = sum(c["pass"] for c in checks)
    result = {
        "schema": "a8-rk03-pure-external-ppt-finalization-v1",
        "status": "PASS_PURE_EXTERNAL_PPT_CLOSEOUT" if passed == len(checks) else "FAIL_PURE_EXTERNAL_PPT_CLOSEOUT",
        "overall_pass": passed == len(checks),
        "check_counts": {"passed": passed, "total": len(checks)},
        "presentation_id": "WB1KsYGualerMUddEzMcCw1En0g",
        "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "slide_id": "pZS",
        "page": 108,
        "revision_id": 70,
        "candidate_verification_sha256": sha(w / "pure_rcs_slide_candidate_verification_v01.json"),
        "postwrite_verification_sha256": sha(w / "pure_rcs_slide_postwrite_verification_v01.json"),
        "online_visual_review_sha256": sha(w / "pure_rcs_online_visual_review_v01.json"),
        "screenshot_sha256": sha(screenshot),
        "candidate_xml_sha256": sha(w / "pure_rcs_slide_candidate_v01.xml"),
        "before_xml_sha256": sha(w / "pure_rcs_before_v02.xml"),
        "after_xml_sha256": sha(w / "pure_rcs_after_v01.xml"),
        "native_request_sha256": sha(w / "pure_rcs_native_add_request_v01.json"),
        "native_response_sha256": sha(w / "pure_rcs_native_add_response_v01.json"),
        "scientific_head_at_record": "d5959f73ac4f4812d614eee6d6c04d320dff38fc",
        "pure_external_replacement_supported_development_only": False,
        "mechanism_increment_pass": False,
        "rk_g1_pass": False,
        "test_authorized": False,
        "functional_untouched_evaluated": False,
        "generator_training_authorized": False,
        "checks": checks,
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "check_counts": result["check_counts"], "slide_id": "pZS", "page": 108}, indent=2))
    if passed != len(checks):
        for c in checks:
            if not c["pass"]:
                print("FAIL", c)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
