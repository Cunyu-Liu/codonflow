#!/usr/bin/env python3
"""Independently verify the RK19 reproduction slide and online readback."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.a8_rk19_make_reproduction_ppt import (
    MARKER, NS, outcome, semantic_signature, visible_text,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def paragraphs(slide, container):
    parent = next(e for e in slide if e.tag.rsplit("}", 1)[-1] == container)
    return ["".join(p.itertext()).strip() for p in parent.iter() if p.tag.rsplit("}", 1)[-1] == "p"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["candidate", "final"], required=True)
    for name in ["existing", "clean", "postpush", "console", "manuscript-section",
                 "writing-status", "finalization-log", "candidate", "candidate-report", "output"]:
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--baseline-xml")
    ap.add_argument("--after-xml")
    ap.add_argument("--add-response")
    ap.add_argument("--after-response")
    args = ap.parse_args()
    paths = {name: Path(getattr(args, name.replace("-", "_"))) for name in
             ["existing", "clean", "postpush", "console", "manuscript_section",
              "writing_status", "finalization_log", "candidate", "candidate_report"]}
    existing = load(paths["existing"])
    clean = load(paths["clean"])
    postpush = load(paths["postpush"])
    candidate_report = load(paths["candidate_report"])
    candidate = ET.parse(paths["candidate"]).getroot()
    data = candidate.find(f"{{{NS}}}data")
    note = candidate.find(f"{{{NS}}}note")
    visible = visible_text(data)
    notes = visible_text(note)
    checks = []

    def check(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("candidate_accepted", candidate_report.get("overall_pass") is True)
    check("candidate_hash_binding", candidate_report.get("candidate_sha256") == sha(paths["candidate"]))
    check("single_slide_root", candidate.tag == f"{{{NS}}}slide")
    check("no_candidate_ids", all("id" not in e.attrib for e in candidate.iter()))
    check("no_unknown_media", all(e.tag.rsplit("}", 1)[-1] not in {"img", "embed", "undefined"} for e in candidate.iter()))
    check("no_emoji", not re.search(r"[\U0001F300-\U0001FAFF]", visible + notes))
    check("page_and_marker", "A8-RK · 110" in visible and visible.count(MARKER) == 1)
    expected_tests = {"collected": 331, "passed": 330, "skipped": 1, "failed": 0, "errors": 0}
    check("existing_counts", existing["tests"] == expected_tests and existing["passed_count"] == existing["check_count"] == 15)
    check("clean_counts", clean["tests"] == expected_tests and clean["passed_count"] == clean["check_count"] == 24)
    check("postpush_counts", postpush["tests"] == expected_tests and postpush["passed_count"] == postpush["check_count"] == 24)
    check("clean_console_hash", clean["input_sha256"]["console"] == sha(paths["console"]))
    check("postpush_console_hash", postpush["input_sha256"]["console"] == sha(paths["console"]))
    check("existing_report_hash_clean", clean["input_sha256"]["existing_env_report"] == sha(paths["existing"]))
    check("existing_report_hash_postpush", postpush["input_sha256"]["existing_env_report"] == sha(paths["existing"]))
    check("console_summary", "330 passed, 1 skipped, 11 warnings in 15.91s" in paths["console"].read_text(encoding="utf-8"))
    check("skip_reason", "explicit tmux integration opt-in" in paths["console"].read_text(encoding="utf-8"))
    check("existing_visible", outcome(existing) in visible and "15/15 · 27.12 s" in visible)
    check("clean_visible", outcome(clean) in visible and "24/24 · 15.91 s" in visible)
    check("clean_versions", clean["package_versions"]["torch"] == "2.11.0+cu128" and "2.11.0+cu128 / 4.46.3" in visible)
    check("existing_versions", "2.14.1+cu132 / 5.20.2" in visible)
    check("isolated_prefix", clean["environment_prefix"] == "/home/codonflow-rk19-clean-explicit-v2" and clean["environment_prefix"] in notes)
    check("no_external_pythonpath", clean["external_pythonpath"] is False and "no external PYTHONPATH" in visible)
    for package in ["torch", "numpy", "scipy", "pandas", "scikit-learn", "pytest", "pymoo", "rapidfuzz"]:
        check(f"note_package_{package}", clean["package_versions"][package] in notes)
    check("junit_metadata_existing", existing["junit_metadata_observation"]["tests_attribute"] == 336 and existing["junit_metadata_observation"]["testcase_elements"] == 331)
    check("junit_metadata_clean", clean["junit_metadata_observation"]["tests_attribute"] == 336 and clean["junit_metadata_observation"]["testcase_elements"] == 331)
    check("junit_visible", "JUnit header 336 vs 331 testcase elements" in visible)
    check("junit_note", "tests=336" in notes and "331 testcase elements" in notes)
    check("writing_status", load(paths["writing_status"]).get("status") == "PASS")
    check("finalization", load(paths["finalization_log"]) == {"passed": 22, "total": 22, "failed": []} and "22/22" in visible)
    section = paths["manuscript_section"].read_text(encoding="utf-8")
    check("manuscript_section_scope", "fresh-clean **CPU test suites only**" in section and "full experimental regeneration" in section)
    check("commit", "1368c5443ef11916fc9ec417d7dfb9052ce9ea32" in notes)
    for phrase in ["Full experimental regeneration = false", "Opt-in tmux/GPU integration was not executed",
                   "RK-G1 = false", "functional untouched not evaluated", "generator training unauthorized",
                   "manuscript non-submittable"]:
        check(f"boundary_{phrase}", phrase in visible)
    for key in ["full_experimental_clean_reproduction", "gpu_integration_executed", "rk_g1_pass", "generator_training_authorized", "functional_untouched_evaluated"]:
        check(f"clean_gate_{key}", clean[key] is False)
        check(f"postpush_gate_{key}", postpush[key] is False)
    check("table_shape", len(candidate.findall(f".//{{{NS}}}tr")) == 3 and len(candidate.findall(f".//{{{NS}}}col")) == 4)
    check("speaker_notes", len(paragraphs(candidate, "note")) == 5)

    if args.mode == "final":
        required = [args.baseline_xml, args.after_xml, args.add_response, args.after_response]
        check("final_inputs_present", all(required))
        if all(required):
            baseline_path = Path(args.baseline_xml)
            after_path = Path(args.after_xml)
            add = load(Path(args.add_response))
            after_response = load(Path(args.after_response))
            before = ET.parse(baseline_path).getroot()
            after = ET.parse(after_path).getroot()
            before_slides = [e for e in list(before) if e.tag.rsplit("}", 1)[-1] == "slide"]
            after_slides = [e for e in list(after) if e.tag.rsplit("}", 1)[-1] == "slide"]
            new_id = add.get("data", {}).get("slide_id")
            revision = add.get("data", {}).get("revision_id")
            check("add_success", add.get("ok") is True and bool(new_id))
            check("readback_success", after_response.get("ok") is True and after_response.get("data", {}).get("revision_id") == revision)
            check("page_count", len(before_slides) == 109 and len(after_slides) == 110)
            check("new_last_page", after_slides[-1].get("id") == new_id)
            check("old_page_ids", [s.get("id") for s in before_slides] == [s.get("id") for s in after_slides[:109]])
            for index, (old, new) in enumerate(zip(before_slides, after_slides[:109]), 1):
                check(f"old_page_{index}_full_semantics_unchanged", semantic_signature(old) == semantic_signature(new))
            check("new_page_visible_text", paragraphs(after_slides[-1], "data") == paragraphs(candidate, "data"))
            check("new_page_notes", paragraphs(after_slides[-1], "note") == paragraphs(candidate, "note"))
            marker_pages = [i + 1 for i, slide in enumerate(after_slides) if MARKER in visible_text(slide)]
            check("single_online_page", marker_pages == [110], marker_pages)
            check("new_page_negative_gates", "RK-G1 = false" in visible_text(after_slides[-1]) and "Full experimental regeneration = false" in visible_text(after_slides[-1]))

    passed = sum(c["pass"] for c in checks)
    result = {
        "schema": "a8-rk19-reproduction-ppt-verification-v1",
        "mode": args.mode,
        "status": "PASS_RK19_REPRODUCTION_PPT" if passed == len(checks) else "FAIL_RK19_REPRODUCTION_PPT",
        "overall_pass": passed == len(checks),
        "check_counts": {"passed": passed, "total": len(checks)},
        "candidate_sha256": sha(paths["candidate"]),
        "existing_sha256": sha(paths["existing"]),
        "clean_sha256": sha(paths["clean"]),
        "postpush_sha256": sha(paths["postpush"]),
        "console_sha256": sha(paths["console"]),
        "manuscript_section_sha256": sha(paths["manuscript_section"]),
        "full_experimental_clean_reproduction": False,
        "gpu_integration_executed": False,
        "rk_g1_pass": False,
        "functional_untouched_evaluated": False,
        "generator_training_authorized": False,
        "checks": checks,
    }
    if args.mode == "final" and all([args.baseline_xml, args.after_xml, args.add_response]):
        result["slide_id"] = load(Path(args.add_response)).get("data", {}).get("slide_id")
        result["revision_id"] = load(Path(args.add_response)).get("data", {}).get("revision_id")
        result["baseline_xml_sha256"] = sha(Path(args.baseline_xml))
        result["after_xml_sha256"] = sha(Path(args.after_xml))
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "check_counts": result["check_counts"]}, indent=2))
    if passed != len(checks):
        for check_ in checks:
            if not check_["pass"]:
                print("FAIL", check_)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
