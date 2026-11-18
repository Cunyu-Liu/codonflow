#!/usr/bin/env python3
"""Independent post-write verification for the EnsembleDesign A8-RK slide."""
import argparse
import copy
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def namespace(root):
    return {"s": root.tag.split("}")[0].strip("{")}


def normalized_text(element):
    return " ".join("".join(element.itertext()).split())


def semantic_xml(element):
    element = copy.deepcopy(element)
    for item in element.iter():
        item.attrib.pop("id", None)
        if item.text is not None:
            item.text = " ".join(item.text.split())
        item.tail = None
    return ET.tostring(element, encoding="unicode")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-xml", required=True)
    parser.add_argument("--baseline-response", required=True)
    parser.add_argument("--readback-xml", required=True)
    parser.add_argument("--readback-response", required=True)
    parser.add_argument("--add-response", required=True)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    evidence = Path(args.evidence_dir)
    names = {
        "example": "ensembledesign_official_example_smoke_v2.json",
        "c01": "ensembledesign_c01_smoke_v1.json",
        "example_independent": "ensembledesign_official_example_independent_v2.json",
        "c01_independent": "ensembledesign_c01_independent_v1.json",
        "finalization": "ensembledesign_finalization.json",
    }
    reports = {key: load_json(evidence / name) for key, name in names.items()}
    example = reports["example"]
    c01 = reports["c01"]
    finalization = reports["finalization"]

    baseline_root = ET.parse(args.baseline_xml).getroot()
    readback_root = ET.parse(args.readback_xml).getroot()
    baseline_ns = namespace(baseline_root)
    readback_ns = namespace(readback_root)
    baseline_slides = baseline_root.findall("s:slide", baseline_ns)
    readback_slides = readback_root.findall("s:slide", readback_ns)
    baseline_response = load_json(args.baseline_response)
    readback_response = load_json(args.readback_response)
    add_response = load_json(args.add_response)
    new_slide_id = add_response.get("data", {}).get("slide_id")

    checks = []

    def check(name, condition, detail):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check(
        "frozen_official_and_finalization_evidence",
        example["status"] == c01["status"] == "BOUNDED_OFFICIAL_EXECUTION_COMPLETE"
        and example["returncode"] == c01["returncode"] == 0
        and example["official_source_unmodified"] and c01["official_source_unmodified"]
        and finalization["status"] == "PASS"
        and finalization["passed_checks"] == finalization["check_count"] == 11
        and finalization["task_completion_authorized"],
        {"commit": example["commit"], "finalization": "11/11"},
    )
    check(
        "two_independent_reports_pass",
        reports["example_independent"]["status"] == "PASS"
        and reports["c01_independent"]["status"] == "PASS"
        and reports["example_independent"]["passed_checks"] == 13
        and reports["c01_independent"]["passed_checks"] == 13,
        {"example": "13/13", "c01": "13/13"},
    )
    check(
        "write_and_revision_confirmed",
        add_response.get("ok") is True
        and bool(new_slide_id)
        and baseline_response.get("ok") is True
        and readback_response.get("ok") is True
        and baseline_response["data"]["revision_id"] == 34
        and add_response["data"]["revision_id"] == 35
        and readback_response["data"]["revision_id"] == 35,
        {"before": 34, "after": readback_response["data"]["revision_id"], "slide_id": new_slide_id},
    )
    check(
        "exactly_one_page_appended",
        len(baseline_slides) == 72
        and len(readback_slides) == 73
        and readback_slides[-1].attrib.get("id") == new_slide_id,
        {"before": len(baseline_slides), "after": len(readback_slides), "last_id": readback_slides[-1].attrib.get("id")},
    )
    baseline_ids = [slide.attrib.get("id") for slide in baseline_slides]
    readback_old_ids = [slide.attrib.get("id") for slide in readback_slides[:-1]]
    check("old_page_ids_and_order_unchanged", baseline_ids == readback_old_ids, {"old_pages": len(baseline_ids)})
    semantic_matches = [semantic_xml(old) == semantic_xml(new) for old, new in zip(baseline_slides, readback_slides[:-1])]
    check(
        "all_72_old_pages_semantically_unchanged",
        len(semantic_matches) == 72 and all(semantic_matches),
        {"unchanged": sum(semantic_matches), "different_pages": [i + 1 for i, value in enumerate(semantic_matches) if not value]},
    )

    slide = readback_slides[-1]
    ns = readback_ns
    text = normalized_text(slide)
    records = example["records"] + c01["records"]
    run_count = sum(len(record["runs"]) for record in records)
    unique_count = sum(len({run["sequence_rna"] for run in record["runs"]}) for record in records)
    check(
        "kpi_protocol_and_cost_match_evidence",
        run_count == 8 and unique_count == 6
        and "8/8" in text and "13/13 ×2" in text and "11/11" in text
        and "Fixed cd9324f" in text
        and "beam=100" in text and "lr=0.03" in text and "epsilon=0.5" in text
        and "3 iterations × 2 runs" in text and "4 threads" in text
        and f"Example {example['total_elapsed_s']:.6f} s" in text
        and f"C01 {c01['total_elapsed_s']:.6f} s" in text
        and "Evidence: GitHub 5ba0a884" in text,
        {"runs": run_count, "unique_cds": unique_count, "example_s": example["total_elapsed_s"], "c01_s": c01["total_elapsed_s"]},
    )

    expected_rows = [
        [
            record["record_id"],
            f"{record['protein_length_aa']} aa",
            str(record["best_run_id"]),
            f"{record['best_official_efe_kcal_mol']:.2f}",
            f"{record['runs'][record['best_run_id'] - 1]['sequence_length_nt']} nt",
        ]
        for record in records
    ]
    table = slide.find(".//s:table", ns)
    actual_rows = []
    if table is not None:
        for row in table.findall("s:tr", ns)[1:]:
            actual_rows.append([normalized_text(cell) for cell in row.findall("s:td", ns)])
    check("table_recomputed_from_frozen_reports", actual_rows == expected_rows, {"rows": actual_rows})

    notes = slide.findall("./s:note/s:content/s:p", ns)
    note_text = " ".join(normalized_text(note) for note in notes)
    check(
        "notes_failure_and_scientific_boundary",
        len(notes) == 4
        and "13/13 PASS" in note_text and "11/11 PASS" in note_text
        and "v1 stop-contract" in note_text
        and "不能直接排名" in note_text
        and "EFE is not LinearDesign MFE" in text
        and "no matched LinearDesign, dense budget, main ranking, OOD or SOTA" in text
        and "no extra stop" in text and "v1 stop-gate failure retained" in text,
        {"note_paragraphs": len(notes), "main_baseline_comparison": False, "functional_ood": False, "sota_claim": False},
    )

    in_bounds = True
    minimum_font = 1000.0
    for element in slide.findall(".//*[@topLeftX]", ns):
        x = float(element.attrib["topLeftX"])
        y = float(element.attrib["topLeftY"])
        width = float(element.attrib["width"])
        height = float(element.attrib["height"])
        in_bounds = in_bounds and x >= 0 and y >= 0 and x + width <= 960 and y + height <= 540
    for content in slide.findall(".//s:content[@fontSize]", ns):
        minimum_font = min(minimum_font, float(content.attrib["fontSize"]))
    check(
        "new_page_geometry_and_readability_structure",
        in_bounds and minimum_font >= 9
        and table is not None and len(table.findall("s:tr", ns)) == 5
        and slide.find(".//s:undefined", ns) is None
        and not slide.findall(".//s:img", ns)
        and normalized_text(slide.findall(".//s:shape", ns)[-1]) == "73",
        {"in_bounds": in_bounds, "minimum_explicit_font_px": minimum_font, "table_rows": 5, "page_number": 73},
    )

    passed = sum(item["pass"] for item in checks)
    report = {
        "protocol": "a8_rk05_ensembledesign_ppt_independent_verification_v1",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "check_count": len(checks),
        "passed_checks": passed,
        "presentation_id": "WB1KsYGualerMUddEzMcCw1En0g",
        "slide_id": new_slide_id,
        "slide_number": 73,
        "baseline_slide_count": len(baseline_slides),
        "readback_slide_count": len(readback_slides),
        "baseline_revision": baseline_response["data"]["revision_id"],
        "readback_revision": readback_response["data"]["revision_id"],
        "old_pages_unchanged": all(semantic_matches),
        "baseline_xml_sha256": sha256(args.baseline_xml),
        "readback_xml_sha256": sha256(args.readback_xml),
        "evidence_sha256": {key: sha256(evidence / name) for key, name in names.items()},
        "checks": checks,
        "scope": {
            "bounded_official_smoke_recorded": True,
            "matched_lineardesign_comparison": False,
            "dense_budget_complete": False,
            "main_baseline_matrix_closed": False,
            "functional_ood": False,
            "sota_claim": False,
        },
    }
    output = Path(args.output)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "slide_id": new_slide_id, "slides": len(readback_slides), "output": str(output)}, ensure_ascii=False))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
