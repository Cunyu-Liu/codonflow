#!/usr/bin/env python3
"""Verify the online RiboMIMO study-OOD slide and preservation of the prior deck."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text())


def slides(path: Path):
    root = ET.parse(path).getroot()
    return [element for element in root if element.tag.split("}")[-1] == "slide"]


def semantic(element, exclude_ids=False):
    text = element.text if element.text and element.text.strip() else None
    attrs = dict(element.attrib)
    if exclude_ids:
        attrs.pop("id", None)
    local_name = element.tag.split("}")[-1]
    if local_name == "col" and attrs.get("span") in {None, "1"}:
        attrs["span"] = "1"
    if local_name == "content" and attrs.get("textType") == "body" and attrs.get("fontSize") == "12" and attrs.get("fontFamily") == "思源黑体":
        for key in ("textType", "fontSize", "fontFamily"):
            attrs.pop(key, None)
    attrs = tuple(sorted(attrs.items()))
    return element.tag, attrs, text, tuple(semantic(child, exclude_ids) for child in element)


def semantic_strict(element, exclude_ids=False):
    text = element.text if element.text and element.text.strip() else None
    attrs = tuple(sorted((key, value) for key, value in element.attrib.items() if not (exclude_ids and key == "id")))
    return element.tag, attrs, text, tuple(semantic_strict(child, exclude_ids) for child in element)


def strict_differences(candidate, online):
    differences = []

    def walk(left, right, path=""):
        local_name = left.tag.split("}")[-1]
        here = path + "/" + local_name
        if left.tag != right.tag:
            differences.append({"path": here, "kind": "tag"})
            return
        left_attrs = {key: value for key, value in left.attrib.items() if key != "id"}
        right_attrs = {key: value for key, value in right.attrib.items() if key != "id"}
        if left_attrs != right_attrs:
            differences.append({"path": here, "kind": "attributes", "candidate": left_attrs, "online": right_attrs})
        left_text = left.text.strip() if left.text and left.text.strip() else None
        right_text = right.text.strip() if right.text and right.text.strip() else None
        if left_text != right_text:
            differences.append({"path": here, "kind": "text", "candidate": left_text, "online": right_text})
        if len(left) != len(right):
            differences.append({"path": here, "kind": "child_count", "candidate": len(left), "online": len(right)})
        for index, (left_child, right_child) in enumerate(zip(left, right)):
            walk(left_child, right_child, here + f"[{index}]")

    walk(candidate, online)
    return differences


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--finalization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.work_dir.resolve()
    checks = []

    def check(name, passed, detail=None):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    def local(name):
        return root / name

    before_response = load(local("rk05-live-before-response.json"))
    add_response = load(local("rk05-add-response.json"))
    after_response = load(local("rk05-after-response.json"))
    candidate_facts = load(local("candidate-verification.json"))
    candidate_path = local("candidate-v1.xml")
    before = slides(local("rk05-live-before.xml"))
    after = slides(local("rk05-after.xml"))
    candidate = ET.parse(candidate_path).getroot()
    production = load(args.production)
    independent = load(args.independent)
    final = load(args.finalization)
    new_slide = after[-1]

    check("baseline_read_ok", before_response.get("ok") is True)
    check("baseline_revision_62", before_response.get("data", {}).get("revision_id") == 62)
    check("baseline_page_count_100", len(before) == 100)
    check("add_ok", add_response.get("ok") is True)
    check("add_revision_63", add_response.get("data", {}).get("revision_id") == 63)
    check("add_slide_id_pgI", add_response.get("data", {}).get("slide_id") == "pgI")
    check("readback_ok", after_response.get("ok") is True)
    check("readback_revision_63", after_response.get("data", {}).get("revision_id") == 63)
    check("readback_page_count_101", len(after) == 101)
    check("new_slide_is_last", new_slide.get("id") == "pgI")
    check("existing_structure_slide_kept_at_100", after[99].get("id") == "pgv")
    check("existing_cagfn_slide_kept_at_99", after[98].get("id") == "pgY")
    check("existing_rk13_slides_kept_at_96_98", [slide.get("id") for slide in after[95:98]] == ["pgV", "pgs", "pgT"])
    check("slide_ids_unique", len({slide.get("id") for slide in after}) == 101)
    check("candidate_fact_check_33_of_33", candidate_facts["status"] == "PASS_RK05_RIBOMIMO_STUDY_OOD_PPT_CANDIDATE" and candidate_facts["n_passed"] == candidate_facts["n_checks"] == 33)
    check("candidate_hash_matches_fact_check", candidate_facts["candidate_sha256"] == sha256(candidate_path))
    check("scientific_production_complete", production["status"] == "PASS_STUDY_OOD_PENDING_INDEPENDENT" and len(production["runs"]) == 3)
    check("scientific_independent_pass", independent["status"] == "PASS_RK05_RIBOMIMO_STUDY_OOD_INDEPENDENT" and independent["n_passed"] == independent["n_checks"] == 203)
    check("scientific_finalization_pass", final["status"] == "PASS_RK05_RIBOMIMO_STUDY_OOD" and final["n_passed"] == final["n_checks"] == 30)
    check("scientific_outcome_bound", final["scientific_outcome"] == "RIBOMIMO_STUDY_OOD_NO_UNIFORM_SIGNIFICANT_ADVANTAGE_OVER_RIDGE")
    check("candidate_commit_bound", candidate_facts["commit"] == "ee580a7f9bbc8104b37341b7749403338e9e6257")

    unchanged = 0
    for index, (old, new) in enumerate(zip(before, after[:100]), start=1):
        passed = old.get("id") == new.get("id") and semantic(old) == semantic(new)
        unchanged += int(passed)
        check(f"prior_slide_{index:03d}_{old.get('id')}_semantic_xml_unchanged", passed)
    check("candidate_online_semantic_xml_equal_excluding_server_ids_and_declared_defaults", semantic(candidate, True) == semantic(new_slide, True), {"server_normalization": ["table col span=1", "speaker-note body default textType/fontSize/fontFamily removed"]})

    visible_text = "\n".join(text.strip() for text in new_slide.itertext() if text.strip())
    required_texts = [
        "203/203 + 30/30 · VERIFIED",
        "RK05 · RIBOMIMO CROSS-STUDY TRANSFER",
        "RiboMIMO 跨研究迁移：ridge 两项主终点均更优",
        "Mohammad16 → Subtelny14 · source 1,062/117 · target 3,921 · exact CDS overlap = 0",
        "primary seed 1234 · sensitivity 2345/3456 · 2,000 bootstrap + 2,000 sign flips · Holm across 2",
        "2.186608", "1.006967", "TB-MSE · mean r = −0.001008", "TB-MSE · mean r = +0.037500",
        "RIDGE 2/2", "constant TB-MSE = 0.966916",
        "delta +1.179642", "[+1.162687, +1.196288]",
        "delta −0.038508", "[−0.041406, −0.035536]",
        "2.074145", "1.006788", "constant 0.966910",
        "2.040441", "1.005552", "constant 0.966907",
        "official 094c693d · target readout last", "source-only early stop · alpha = 100 all seeds",
        "RiboMIMO r range −0.001008…+0.011053", "ridge r range +0.037489…+0.038321",
        "model/checkpoint exact · ridge max 1.51e−7", "3/3 retrains · paper 44/44 + facts 20/20",
        "结论 · ridge 两项主终点均显著优于 RiboMIMO", "常数 MSE 更低 · 不能解释为强绝对迁移",
        "边界 · occupancy-derived study-OOD · 非全局 untouched", "非物理速度/功能或蛋白 OOD · RK-G1 未关闭",
        "Evidence: independent 203/203 · finalization 30/30 · paper 44/44 · GitHub ee580a7f9bbc",
        "RK05 · 2026-11-20",
    ]
    for index, value in enumerate(required_texts, start=1):
        check(f"new_slide_required_text_{index:02d}", value in visible_text, value)
    for index, value in enumerate(["12/12 + 21/21", "18/18 + 8/8", "NO-GO", "FIXED_GFP_OBSERVED_R1_STRUCTURE_INCREMENT_NO_GO_DEVELOPMENT_ONLY"], start=1):
        check(f"new_slide_avoids_stale_text_{index:02d}", value not in visible_text, value)

    tables = [element for element in new_slide.iter() if element.tag.split("}")[-1] == "table"]
    check("new_slide_has_one_native_table", len(tables) == 1)
    if tables:
        rows = [element for element in tables[0] if element.tag.split("}")[-1] == "tr"]
        check("new_slide_table_has_six_rows", len(rows) == 6)
        for index, row in enumerate(rows, start=1):
            cells = [element for element in row if element.tag.split("}")[-1] == "td"]
            check(f"new_slide_table_row_{index}_has_five_cells", len(cells) == 5)

    notes = [element for element in new_slide if element.tag.split("}")[-1] == "note"]
    check("new_slide_has_speaker_notes", len(notes) == 1)
    if notes:
        paragraphs = [element for element in notes[0].iter() if element.tag.split("}")[-1] == "p"]
        note_text = "\n".join("".join(paragraph.itertext()) for paragraph in paragraphs)
        check("new_slide_notes_have_four_paragraphs", len(paragraphs) == 4)
        for key, value in {
            "full_mse_effect": "1.179641679101714",
            "full_mse_ci": "[1.1626865486921758, 1.1962882037490148]",
            "full_correlation_effect": "-0.03850771646224459",
            "full_correlation_ci": "[-0.04140616194511709, -0.03553605212612245]",
            "full_holm_p": "0.0009995002498750624",
            "ridge_tolerance": "1.508439275710316e-07",
            "rk_g1_open": "不关闭 RK-G1",
            "no_generation_or_sota": "不授权生成训练或 SOTA 声明",
        }.items():
            check(f"new_slide_notes_{key}", value in note_text)

    check("new_slide_has_no_undefined_objects", not any(element.tag.split("}")[-1] == "undefined" for element in new_slide.iter()))
    for element in new_slide.iter():
        if element.tag.split("}")[-1] in {"shape", "table", "img", "icon", "embed"}:
            x = float(element.get("topLeftX", "0")); y = float(element.get("topLeftY", "0"))
            width = float(element.get("width", "0")); height = float(element.get("height", "0"))
            check(f"new_slide_{element.get('id')}_within_canvas", x >= 0 and y >= 0 and x + width <= 960 and y + height <= 540, [x, y, width, height])

    status = "PASS_RK05_RIBOMIMO_STUDY_OOD_PPT_ONLINE_READBACK" if all(row["pass"] for row in checks) else "FAIL_RK05_RIBOMIMO_STUDY_OOD_PPT_ONLINE_READBACK"
    report = {
        "schema_version": "a8-rk05-ribomimo-study-ood-ppt-online-readback-v1",
        "status": status,
        "n_checks": len(checks),
        "n_passed": sum(row["pass"] for row in checks),
        "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "presentation_id": "WB1KsYGualerMUddEzMcCw1En0g",
        "baseline_revision": 62,
        "final_revision": after_response.get("data", {}).get("revision_id"),
        "baseline_pages": len(before),
        "final_pages": len(after),
        "new_slide_id": new_slide.get("id"),
        "new_slide_number": 101,
        "prior_slides_semantic_xml_unchanged": unchanged,
        "candidate_sha256": sha256(candidate_path),
        "baseline_xml_sha256": sha256(local("rk05-live-before.xml")),
        "readback_xml_sha256": sha256(local("rk05-after.xml")),
        "add_response_sha256": sha256(local("rk05-add-response.json")),
        "readback_response_sha256": sha256(local("rk05-after-response.json")),
        "candidate_fact_check_sha256": sha256(local("candidate-verification.json")),
        "production_sha256": sha256(args.production),
        "independent_sha256": sha256(args.independent),
        "finalization_sha256": sha256(args.finalization),
        "scientific_outcome": final["scientific_outcome"],
        "strict_candidate_comparison": {
            "semantic_equal_excluding_server_ids": semantic_strict(candidate, True) == semantic_strict(new_slide, True),
            "differences": strict_differences(candidate, new_slide),
            "interpretation": "The strict comparison retains the observed 205/206 engineering failure: six non-content server defaults differ. The normalized 206/206 comparison permits only these declared defaults and no other semantic difference."
        },
        "scope": "One online page appended after live baseline and 33/33 candidate fact verification; all 100 prior slides required to remain semantically unchanged.",
        "server_normalization": {
            "table_columns": "A missing candidate span and the server-returned span=1 are treated as the same default.",
            "speaker_notes": "The candidate note body textType=body, fontSize=12 and fontFamily=思源黑体 are removed by the server; the note paragraphs and text are unchanged.",
            "other_semantic_differences_allowed": False
        },
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "n_passed", "n_checks", "final_pages", "final_revision", "new_slide_id", "prior_slides_semantic_xml_unchanged")}, ensure_ascii=False))
    if not status.startswith("PASS"):
        for row in checks:
            if not row["pass"]:
                print("FAILED", row)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
