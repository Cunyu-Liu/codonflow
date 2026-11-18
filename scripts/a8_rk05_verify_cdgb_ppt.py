#!/usr/bin/env python3
"""Independently verify the CDGB slide and protection of all previous slides."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def namespace(root):
    return root.tag.split("}")[0].strip("{") if "}" in root.tag else ""


def slides(root):
    ns = namespace(root)
    return root.findall(f"{{{ns}}}slide") if ns else root.findall("slide")


def semantic(element):
    """Return an ID-independent, whitespace-formatting-independent semantic tree."""
    node = copy.deepcopy(element)
    for item in node.iter():
        item.attrib.pop("id", None)
        if item.text is not None and not item.text.strip():
            item.text = None
        if item.tail is not None and not item.tail.strip():
            item.tail = None
    return ET.tostring(node, encoding="utf-8")


def text(element):
    return "\n".join(item.strip() for item in element.itertext() if item.strip())


def load_response(path):
    report = json.loads(Path(path).read_text())
    if not report.get("ok"):
        raise RuntimeError(f"Unsuccessful Slides response: {path}")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-xml", required=True)
    parser.add_argument("--baseline-response", required=True)
    parser.add_argument("--readback-xml", required=True)
    parser.add_argument("--readback-response", required=True)
    parser.add_argument("--audit", required=True)
    parser.add_argument("--verification", required=True)
    parser.add_argument("--finalization", required=True)
    parser.add_argument("--expected-new-slide-id", required=True)
    parser.add_argument("--evidence-commit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    baseline_root = ET.parse(args.baseline_xml).getroot()
    readback_root = ET.parse(args.readback_xml).getroot()
    baseline_slides = slides(baseline_root)
    readback_slides = slides(readback_root)
    baseline_response = load_response(args.baseline_response)
    readback_response = load_response(args.readback_response)
    audit = json.loads(Path(args.audit).read_text())
    verification = json.loads(Path(args.verification).read_text())
    finalization = json.loads(Path(args.finalization).read_text())
    checks = {}

    def check(name, condition, detail):
        checks[name] = {"pass": bool(condition), "detail": detail}

    before_revision = baseline_response["data"]["revision_id"]
    after_revision = readback_response["data"]["revision_id"]
    check("page_count_exactly_one_added", len(baseline_slides) == 71 and len(readback_slides) == 72, {"before": len(baseline_slides), "after": len(readback_slides)})
    check("revision_advanced", after_revision > before_revision, {"before": before_revision, "after": after_revision})
    old_ids_before = [slide.attrib.get("id") for slide in baseline_slides]
    old_ids_after = [slide.attrib.get("id") for slide in readback_slides[:-1]]
    check("previous_slide_ids_unchanged", old_ids_before == old_ids_after, {"previous_count": len(old_ids_before)})
    semantic_differences = [index + 1 for index, (before, after) in enumerate(zip(baseline_slides, readback_slides[:-1])) if semantic(before) != semantic(after)]
    check("previous_semantic_xml_unchanged", not semantic_differences, {"different_pages": semantic_differences})
    new_slide = readback_slides[-1]
    new_id = new_slide.attrib.get("id")
    check("new_slide_identity", new_id == args.expected_new_slide_id and new_id not in old_ids_before, {"expected": args.expected_new_slide_id, "observed": new_id})

    visible_and_notes = text(new_slide)
    source_consistent = (
        audit["query_count_succeeded"] == audit["query_count_expected"] == 9
        and audit["source_assessment"]["exact_candidate_title_match_count"] == 0
        and audit["candidate_doi_identity"]["conflict"]
        and audit["query_summaries"]["github_cdgb_codon"]["total_count_reported_by_github"] == 0
        and audit["query_summaries"]["github_cdgb_protein_representation"]["total_count_reported_by_github"] == 0
        and audit["query_summaries"]["github_codon_deoptimization"]["total_count_reported_by_github"] == 14
        and verification["status"] == "PASS"
        and verification["checks_passed"] == verification["checks_total"] == 8
        and finalization["checks_passed"] == finalization["checks_total"] == 6
        and finalization["science_flags"]["official_sequence_output_count"] == 0
        and finalization["science_flags"]["performance_result_count"] == 0
        and not finalization["science_flags"]["official_execution_complete"]
        and not finalization["science_flags"]["method_invalid_claim"]
        and not finalization["science_flags"]["implementation_nonexistence_claim"]
    )
    check("frozen_source_boundaries", source_consistent, {"queries": "9/9", "independent": "8/8", "finalization": "6/6", "sequence_outputs": 0, "performance_results": 0})
    required_strings = [
        "CDGB Source Identity Unresolved; Execution Correctly Blocked",
        "9/9",
        "exact scholarly title matches",
        "8/8",
        "6/6",
        audit["candidate"]["doi_embedded_in_url"],
        audit["candidate_doi_identity"]["crossref_title"],
        "Briefings in Bioinformatics 26(4)",
        "Exact CDGB queries = 0 + 0 · broad deoptimization = 14",
        "No official commit, build, execution, sequences or metrics",
        "method invalid / nonexistence not claimed",
        "time-dependent and non-exhaustive",
        f"GitHub {args.evidence_commit[:8]}",
        "72",
    ]
    missing = [item for item in required_strings if item not in visible_and_notes]
    check("new_page_required_text", not missing, {"required_count": len(required_strings), "missing": missing})

    ns = namespace(readback_root)
    tables = new_slide.findall(f".//{{{ns}}}table") if ns else new_slide.findall(".//table")
    table_shape = []
    if len(tables) == 1:
        rows = tables[0].findall(f"{{{ns}}}tr") if ns else tables[0].findall("tr")
        for row in rows:
            cells = row.findall(f"{{{ns}}}td") if ns else row.findall("td")
            table_shape.append([text(cell) for cell in cells])
    expected_rows = [
        ["Evidence layer", "Frozen result", "Decision"],
        ["Crossref DOI", "bbaf332 → ExpressRM · Briefings in Bioinformatics 26(4)", "Candidate title conflict"],
        ["Scholarly indexes", "Crossref / OpenAlex / Europe PMC · 0 exact title matches", "Identity unresolved"],
        ["GitHub", "Exact CDGB queries = 0 + 0 · broad deoptimization = 14", "No official repo verified"],
    ]
    check("evidence_table_exact", table_shape == expected_rows, {"rows": len(table_shape), "expected_rows": 4})
    notes = new_slide.find(f"{{{ns}}}note") if ns else new_slide.find("note")
    note_paragraphs = notes.findall(f".//{{{ns}}}p") if notes is not None else []
    note_text = text(notes) if notes is not None else ""
    note_requirements = ["候选文献身份存在直接冲突", "宽查询的十四个结果不能证明官方归属", "8/8 检查通过", "6/6 PASS", "不代表 CDGB 方法无效或实现不存在", "主 baseline、功能 OOD 和 SOTA 均未因此闭合"]
    check("speaker_notes_complete", len(note_paragraphs) == 4 and all(item in note_text for item in note_requirements), {"paragraphs": len(note_paragraphs)})

    out_of_bounds = []
    for element in new_slide.iter():
        if "topLeftX" in element.attrib:
            x = float(element.attrib["topLeftX"])
            y = float(element.attrib["topLeftY"])
            width = float(element.attrib["width"])
            height = float(element.attrib["height"])
            if x < 0 or y < 0 or x + width > 960 or y + height > 540:
                out_of_bounds.append({"tag": element.tag, "box": [x, y, width, height]})
    check("new_page_canvas_bounds", not out_of_bounds, {"canvas": [960, 540], "out_of_bounds": out_of_bounds})

    passed = all(item["pass"] for item in checks.values())
    report = {
        "schema_version": "a8-rk05-cdgb-ppt-verification-v1",
        "status": "PASS" if passed else "FAIL",
        "presentation_id": readback_response["data"]["xml_presentation_id"],
        "baseline_revision": before_revision,
        "readback_revision": after_revision,
        "baseline_slide_count": len(baseline_slides),
        "readback_slide_count": len(readback_slides),
        "new_slide_id": new_id,
        "new_slide_number": 72,
        "previous_slide_ids_unchanged": old_ids_before == old_ids_after,
        "previous_semantic_xml_differences": semantic_differences,
        "evidence_commit": args.evidence_commit,
        "checks_passed": sum(item["pass"] for item in checks.values()),
        "checks_total": len(checks),
        "checks": checks,
        "artifact_sha256": {name: sha256(getattr(args, name)) for name in ["baseline_xml", "baseline_response", "readback_xml", "readback_response", "audit", "verification", "finalization"]},
        "new_slide_text_sha256": hashlib.sha256(visible_and_notes.encode()).hexdigest(),
        "scientific_scope": "Negative source-identity audit only; no CDGB execution, sequence output, performance result, main-baseline, OOD, or SOTA claim.",
        "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "new_slide_id": new_id, "previous_semantic_xml_differences": semantic_differences, "output": str(output)}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
