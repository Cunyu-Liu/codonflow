#!/usr/bin/env python3
"""Build and preflight one evidence-bound RK19 CPU-reproduction slide."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "https://www.larkoffice.com/sml/2.0"
ET.register_namespace("", NS)
MARKER = "RK19 · CPU REPRODUCTION"
PAGE = 110
COMMIT = "1368c544"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def element(parent, tag, **attrs):
    return ET.SubElement(parent, f"{{{NS}}}{tag}", {k: str(v) for k, v in attrs.items()})


def fill(parent, color):
    node = element(parent, "fill")
    element(node, "fillColor", color=color)


def text(parent, x, y, w, h, value, size=10, color="rgba(71, 85, 105, 1)",
         bold=False, align="left", wrap=True, line="multiple:1.15", text_type=None):
    shape = element(parent, "shape", type="text", topLeftX=x, topLeftY=y, width=w, height=h)
    attrs = dict(fontSize=size, fontFamily="Inter", color=color,
                 bold=str(bool(bold)).lower(), lineSpacing=line,
                 textAlign=align, wrap=str(bool(wrap)).lower())
    if text_type:
        attrs["textType"] = text_type
    content = element(shape, "content", **attrs)
    for line_value in str(value).split("\n"):
        p = element(content, "p")
        p.text = line_value
    return shape


def card(parent, x, y, w, h, color="rgba(255, 255, 255, 1)", border="rgba(226, 232, 240, 1)"):
    shape = element(parent, "shape", type="round-rect", topLeftX=x, topLeftY=y,
                    width=w, height=h, presetHandlers=10)
    fill(shape, color)
    element(shape, "border", color=border, width=1)
    element(shape, "content", fontSize=16, fontFamily="Inter", color="rgba(31, 35, 41, 1)")


def visible_text(root):
    if root is None:
        return ""
    return "\n".join("".join(p.itertext()) for p in root.iter()
                     if p.tag.rsplit("}", 1)[-1] == "p")


def outcome(report):
    tests = report["tests"]
    return (f"{tests['passed']} passed · {tests['skipped']} skipped · "
            f"{tests['failed']} failed · {tests['errors']} errors")


def semantic_signature(element_):
    tail = element_.tail if element_.tail and element_.tail.strip() else None
    return (element_.tag, tuple(sorted(element_.attrib.items())), element_.text, tail,
            tuple(semantic_signature(child) for child in element_))


def build_slide(existing, clean, postpush):
    tests = clean["tests"]
    slide = ET.Element(f"{{{NS}}}slide")
    style = element(slide, "style")
    fill(style, "rgba(248, 250, 252, 1)")
    data = element(slide, "data")

    text(data, 48, 20, 640, 16, "A8-RK · REPRODUCIBILITY · 20 NOV 2026",
         10, "rgba(100, 116, 139, 1)", wrap=False, line="multiple:1", text_type="caption")
    text(data, 724, 20, 188, 16, MARKER, 10, "rgba(15, 118, 110, 1)", True,
         "right", False, "multiple:1", "caption")
    text(data, 48, 43, 864, 38, "Fresh clean prefix reproduces the full CPU suite",
         28, "rgba(15, 23, 42, 1)", True, wrap=False, line="multiple:1", text_type="title")
    accent = element(data, "shape", type="rect", topLeftX=48, topLeftY=87, width=56, height=4, presetHandlers=2)
    fill(accent, "rgba(15, 118, 110, 1)")
    element(accent, "content", fontSize=16, fontFamily="Inter", color="rgba(31, 35, 41, 1)")
    text(data, 116, 82, 796, 18,
         "Isolated Python 3.10.22 · no external PYTHONPATH · pip check clean · scientific imports passed",
         11, wrap=False, line="multiple:1")

    cards = [
        (48, "FRESH CLEAN PREFIX", f"{tests['passed']} PASS", f"{tests['failed']} FAILED · {tests['errors']} ERRORS"),
        (270, "INDEPENDENT ACCEPTANCE", f"{clean['passed_count']} / {clean['check_count']}", "PASS · POSTPUSH RECHECKED"),
        (492, "CLEAN-SUITE RUNTIME", "15.91 s", "331 TESTS COLLECTED"),
        (714, "EXPLICIT OPT-IN SKIP", f"{tests['skipped']} SKIP", "TMUX / GPU NOT EXECUTED"),
    ]
    for x, label, value, sub in cards:
        card(data, x, 110, 198, 66)
        text(data, x + 16, 119, 166, 12, label, 8.5, "rgba(100, 116, 139, 1)",
             wrap=False, line="multiple:1", text_type="caption")
        text(data, x + 16, 134, 166, 27, value, 22, "rgba(15, 23, 42, 1)", True,
             wrap=False, line="multiple:1", text_type="headline")
        text(data, x + 16, 162, 166, 10, sub, 8, "rgba(15, 118, 110, 1)", True,
             wrap=False, line="multiple:1", text_type="caption")

    text(data, 48, 194, 620, 20, "Two environment paths · same complete CPU-test outcome",
         14, "rgba(15, 23, 42, 1)", True, wrap=False, line="multiple:1", text_type="headline")
    text(data, 700, 196, 212, 16, "Compatible ranges, not an exact stack copy", 9,
         "rgba(100, 116, 139, 1)", align="right", wrap=False, line="multiple:1", text_type="caption")
    table = element(data, "table", topLeftX=48, topLeftY=222, width=864, height=100)
    colgroup = element(table, "colgroup")
    for width in [174, 270, 280, 140]:
        element(colgroup, "col", width=width)
    headers = ["Environment", "Torch / Transformers", "CPU-suite outcome", "Acceptance"]
    row = element(table, "tr", height=28)
    for header in headers:
        td = element(row, "td")
        fill(td, "rgba(15, 118, 110, 1)")
        content = element(td, "content", fontSize=10, fontFamily="Inter",
                          color="rgba(255, 255, 255, 1)", bold="true", textAlign="center")
        p = element(content, "p")
        p.text = header
    rows = [
        ("Repaired existing", "2.14.1+cu132 / 5.20.2", outcome(existing), f"{existing['passed_count']}/{existing['check_count']} · 27.12 s"),
        ("Fresh clean prefix", f"{clean['package_versions']['torch']} / 4.46.3", outcome(clean), f"{clean['passed_count']}/{clean['check_count']} · 15.91 s"),
    ]
    for row_values in rows:
        row = element(table, "tr", height=36)
        for j, value in enumerate(row_values):
            td = element(row, "td")
            if j in (2, 3):
                fill(td, "rgba(240, 253, 250, 1)")
            content = element(td, "content", fontSize=9.5, fontFamily="Inter",
                              color="rgba(15, 118, 110, 1)" if j in (2, 3) else "rgba(30, 41, 59, 1)",
                              bold="true" if j in (0, 3) else "false",
                              textAlign="left" if j == 0 else "center")
            p = element(content, "p")
            p.text = value

    card(data, 48, 338, 420, 102, "rgba(240, 253, 250, 1)", "rgba(94, 234, 212, 1)")
    text(data, 64, 348, 388, 18, "Reproduced, with an explicit scope", 13,
         "rgba(15, 118, 110, 1)", True, wrap=False, line="multiple:1", text_type="headline")
    text(data, 64, 371, 388, 58,
         "Fresh conda transaction · official package URLs · isolated site-packages\nExisting suite also passed 15/15 independent checks\nManuscript §8.1 and finalization passed 22/22 checks.",
         10.5, "rgba(30, 41, 59, 1)", line="multiple:1.15")

    card(data, 492, 338, 420, 102, "rgba(255, 247, 237, 1)", "rgba(253, 186, 116, 1)")
    text(data, 508, 348, 388, 18, "Still open; no broader claim", 13,
         "rgba(154, 52, 18, 1)", True, wrap=False, line="multiple:1", text_type="headline")
    text(data, 508, 371, 388, 58,
         "Full experimental regeneration = false\nOpt-in tmux/GPU integration was not executed\nJUnit header 336 vs 331 testcase elements is retained, not hidden.",
         10.5, "rgba(30, 41, 59, 1)", line="multiple:1.15")

    card(data, 48, 455, 864, 36, "rgba(255, 247, 237, 1)", "rgba(253, 186, 116, 1)")
    text(data, 64, 461, 832, 24,
         "RK-G1 = false · functional untouched not evaluated · generator training unauthorized · manuscript non-submittable",
         11, "rgba(154, 52, 18, 1)", True, wrap=False, line="multiple:1")
    text(data, 48, 505, 720, 13,
         f"Source: manuscript §8.1 · existing 15/15 · clean + postpush 24/24 · evidence {COMMIT}",
         9, "rgba(100, 116, 139, 1)", wrap=False, line="multiple:1", text_type="caption")
    text(data, 800, 505, 112, 13, f"A8-RK · {PAGE}", 9, "rgba(100, 116, 139, 1)",
         align="right", wrap=False, line="multiple:1", text_type="caption")

    note = element(slide, "note")
    content = element(note, "content")
    paragraphs = [
        f"The repaired existing environment completed {outcome(existing)} from {existing['tests']['collected']} collected tests in 27.12 seconds and passed {existing['passed_count']}/{existing['check_count']} independent checks; the sole skip was tests/test_gpu_queue_integration.py::test_queue_lifecycle_in_isolated_tmux with reason explicit tmux integration opt-in.",
        f"The fresh clean prefix {clean['environment_prefix']} used {clean['python_executable']}, Python 3.10.22, torch {clean['package_versions']['torch']}, transformers 4.46.3, numpy {clean['package_versions']['numpy']}, scipy {clean['package_versions']['scipy']}, pandas {clean['package_versions']['pandas']}, scikit-learn {clean['package_versions']['scikit-learn']}, pytest {clean['package_versions']['pytest']}, ViennaRNA 2.7.2, pymoo {clean['package_versions']['pymoo']}, and RapidFuzz {clean['package_versions']['rapidfuzz']}; it reproduced {outcome(clean)} in 15.91 seconds with no external PYTHONPATH, clean pip check, successful scientific imports, and {clean['passed_count']}/{clean['check_count']} independent checks.",
        "The clean environment is a fresh reproduction within declared compatible dependency ranges, not an exact copy of the repaired environment's torch 2.14.1+cu132 / transformers 5.20.2 stack. Both JUnit files contained 331 testcase elements but had a tests=336 header; this five-count metadata discrepancy is retained, and acceptance relies on the console summary and independently enumerated cases.",
        f"The postpush independent verifier again passed {postpush['passed_count']}/{postpush['check_count']}; manuscript finalization passed 22/22 and the English writing workflow returned PASS. Evidence commit {COMMIT} is 1368c5443ef11916fc9ec417d7dfb9052ce9ea32. Failed conda/pip attempts, the /teams archive-seek limitation, the successful /home package-cache transaction, and the initial verifier input-schema failure remain preserved in the audit directory.",
        "These results close repaired-existing and fresh-clean CPU test suites only: full experimental regeneration is false, opt-in tmux/GPU integration was not executed, RK-G1 remains false, functional untouched data were not evaluated, generator training remains unauthorized, external-SOTA authorization remains false, and the working manuscript remains non-submittable.",
    ]
    for paragraph in paragraphs:
        p = element(content, "p")
        p.text = paragraph
    return slide


def main():
    ap = argparse.ArgumentParser()
    for name in ["existing", "clean", "postpush", "console", "manuscript-section",
                 "writing-status", "finalization-log", "baseline-xml", "baseline-response",
                 "output", "report"]:
        ap.add_argument("--" + name, required=True)
    args = ap.parse_args()
    paths = {name: Path(getattr(args, name.replace("-", "_"))) for name in
             ["existing", "clean", "postpush", "console", "manuscript_section",
              "writing_status", "finalization_log", "baseline_xml", "baseline_response"]}
    existing = load(paths["existing"])
    clean = load(paths["clean"])
    postpush = load(paths["postpush"])
    baseline_response = load(paths["baseline_response"])
    baseline = ET.parse(paths["baseline_xml"]).getroot()
    baseline_slides = [e for e in list(baseline) if e.tag.rsplit("}", 1)[-1] == "slide"]

    if existing.get("status") != "PASS_FULL_CPU_SUITE_EXISTING_ENV" or not existing.get("overall_pass"):
        raise SystemExit("Refusing PPT: existing-environment verification is not passed")
    if existing["check_count"] != existing["passed_count"] or existing["tests"] != {"collected": 331, "passed": 330, "skipped": 1, "failed": 0, "errors": 0}:
        raise SystemExit("Refusing PPT: existing-environment outcome changed")
    for name, report in [("clean", clean), ("postpush", postpush)]:
        if report.get("status") != "PASS_CLEAN_CPU_SUITE" or not report.get("overall_pass"):
            raise SystemExit(f"Refusing PPT: {name} verification is not passed")
        if report["check_count"] != report["passed_count"] or report["tests"] != existing["tests"]:
            raise SystemExit(f"Refusing PPT: {name} outcome changed")
        if report["input_sha256"]["console"] != sha(paths["console"]):
            raise SystemExit(f"Refusing PPT: {name} does not bind the console log")
        if report["input_sha256"]["existing_env_report"] != sha(paths["existing"]):
            raise SystemExit(f"Refusing PPT: {name} does not bind the existing-environment report")
        if report["full_experimental_clean_reproduction"] or report["gpu_integration_executed"] or report["rk_g1_pass"] or report["generator_training_authorized"] or report["functional_untouched_evaluated"]:
            raise SystemExit(f"Refusing PPT: {name} scientific boundary changed")
    if "330 passed, 1 skipped, 11 warnings in 15.91s" not in paths["console"].read_text(encoding="utf-8"):
        raise SystemExit("Refusing PPT: clean console summary is not passing")
    if load(paths["writing_status"]).get("status") != "PASS":
        raise SystemExit("Refusing PPT: manuscript writing status is not PASS")
    finalization = load(paths["finalization_log"])
    if finalization != {"passed": 22, "total": 22, "failed": []}:
        raise SystemExit("Refusing PPT: manuscript finalization is not 22/22")
    section = paths["manuscript_section"].read_text(encoding="utf-8")
    for phrase in ["331 collected tests: 330 passed, 1 skipped, 0 failed, 0 errors", "24/24 independent checks", "full experimental regeneration"]:
        if phrase not in section:
            raise SystemExit(f"Refusing PPT: manuscript section lacks {phrase}")
    if not baseline_response.get("ok") or len(baseline_slides) != 109:
        raise SystemExit("Refusing PPT: expected a readable 109-page baseline")
    if baseline_slides[-1].get("id") != "pZP" or MARKER in visible_text(baseline):
        raise SystemExit("Refusing PPT: baseline anchor changed or duplicate marker exists")

    slide = build_slide(existing, clean, postpush)
    ET.indent(slide, space="  ")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(ET.tostring(slide, encoding="utf-8", xml_declaration=False) + b"\n")
    parsed = ET.parse(output).getroot()
    data = parsed.find(f"{{{NS}}}data")
    visible = visible_text(data)
    checks = []

    def check(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})
        if not condition:
            raise SystemExit(f"PPT preflight failed: {name}: {detail}")

    check("single_slide", parsed.tag == f"{{{NS}}}slide")
    check("no_preassigned_ids", all("id" not in e.attrib for e in parsed.iter()))
    check("no_external_or_unknown_media", all(e.tag.rsplit("}", 1)[-1] not in {"img", "embed", "undefined"} for e in parsed.iter()))
    check("no_emoji", not re.search(r"[\U0001F300-\U0001FAFF]", visible_text(parsed)))
    check("single_marker", visible.count(MARKER) == 1)
    for i, e in enumerate(data.findall(".//*[@topLeftX]")):
        x, y, w, h = (float(e.get(k)) for k in ["topLeftX", "topLeftY", "width", "height"])
        check(f"canvas_bounds_{i}", 0 <= x and 0 <= y and x + w <= 960 and y + h <= 540, [x, y, w, h])
    boxes = [(float(e.get("topLeftX")), float(e.get("topLeftY")), float(e.get("width")), float(e.get("height")))
             for e in data if e.tag == f"{{{NS}}}shape" and e.get("type") == "text"]
    overlaps = []
    for i, (x1, y1, w1, h1) in enumerate(boxes):
        for x2, y2, w2, h2 in boxes[i + 1:]:
            ix = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
            iy = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
            if ix * iy > 0.01:
                overlaps.append([x1, y1, w1, h1, x2, y2, w2, h2])
    check("no_text_text_overlap", not overlaps, overlaps)
    check("native_table", len(data.findall(f".//{{{NS}}}tr")) == 3 and len(data.findall(f".//{{{NS}}}col")) == 4)
    check("speaker_notes", len(parsed.findall(f".//{{{NS}}}note/{{{NS}}}content/{{{NS}}}p")) == 5)
    for phrase in ["330 PASS", "24 / 24", "15.91 s", "1 SKIP", "Full experimental regeneration = false",
                   "Opt-in tmux/GPU integration was not executed", "JUnit header 336 vs 331 testcase elements",
                   "RK-G1 = false", "functional untouched not evaluated", "generator training unauthorized",
                   "manuscript non-submittable", "A8-RK · 110"]:
        check(f"boundary_{phrase}", phrase in visible, phrase)
    report = {
        "schema": "a8-rk19-reproduction-ppt-candidate-v1",
        "status": "PASS_RK19_REPRODUCTION_PPT_CANDIDATE",
        "overall_pass": True,
        "check_counts": {"passed": len(checks), "total": len(checks)},
        "candidate_sha256": sha(output),
        "baseline_xml_sha256": sha(paths["baseline_xml"]),
        "baseline_slide_count": len(baseline_slides),
        "baseline_revision_id": baseline_response.get("data", {}).get("revision_id"),
        "baseline_last_slide_id": baseline_slides[-1].get("id"),
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
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks),
                      "candidate_sha256": report["candidate_sha256"],
                      "baseline_slides": len(baseline_slides),
                      "baseline_revision": report["baseline_revision_id"]}, indent=2))


if __name__ == "__main__":
    main()
