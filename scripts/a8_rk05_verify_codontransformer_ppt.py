#!/usr/bin/env python3
"""Independent post-write verification for the CodonTransformer A8-RK slide."""
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
        "production": "codontransformer_official_smoke_v1.json",
        "independent": "codontransformer_independent_verification_v1.json",
        "finalization": "codontransformer_finalization_v1.json",
        "materialization": "codontransformer_materialization.json",
    }
    reports = {key: load_json(evidence / name) for key, name in names.items()}
    production = reports["production"]
    independent = reports["independent"]
    finalization = reports["finalization"]
    materialization = reports["materialization"]
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

    check("frozen_official_and_finalization_evidence", production["status"] == "BOUNDED_OFFICIAL_EXECUTION_COMPLETE" and production["official_example_pass"] and production["source_commit"] == "4a447b01dab860feb81b647ff1ff88ad598517f4" and production["model_commit"] == "9744dcc920d813066391fc828d7a590207f148e8" and finalization["status"] == "CLOSED_BOUNDED_OFFICIAL_SMOKE" and finalization["passed_checks"] == finalization["check_count"] == 10 and materialization["status"] == "COMPLETE" and len(materialization["model"]["files"]) == 8, {"source_commit": production["source_commit"], "model_commit": production["model_commit"], "finalization": "10/10"})
    check("independent_reexecution_pass", independent["status"] == "PASS" and independent["passed_checks"] == independent["check_count"] == 13 and independent["max_numeric_delta"] == 0.0, {"independent": "13/13", "max_numeric_delta": independent["max_numeric_delta"]})
    check("write_and_revision_confirmed", add_response.get("ok") is True and bool(new_slide_id) and baseline_response.get("ok") is True and readback_response.get("ok") is True and baseline_response["data"]["revision_id"] == 35 and add_response["data"]["revision_id"] == 36 and readback_response["data"]["revision_id"] == 36, {"before": 35, "after": readback_response["data"]["revision_id"], "slide_id": new_slide_id})
    check("exactly_one_page_appended", len(baseline_slides) == 73 and len(readback_slides) == 74 and readback_slides[-1].attrib.get("id") == new_slide_id, {"before": len(baseline_slides), "after": len(readback_slides), "last_id": readback_slides[-1].attrib.get("id")})
    baseline_ids = [slide.attrib.get("id") for slide in baseline_slides]
    readback_old_ids = [slide.attrib.get("id") for slide in readback_slides[:-1]]
    check("old_page_ids_and_order_unchanged", baseline_ids == readback_old_ids, {"old_pages": len(baseline_ids)})
    semantic_matches = [semantic_xml(old) == semantic_xml(new) for old, new in zip(baseline_slides, readback_slides[:-1])]
    check("all_73_old_pages_semantically_unchanged", len(semantic_matches) == 73 and all(semantic_matches), {"unchanged": sum(semantic_matches), "different_pages": [i + 1 for i, value in enumerate(semantic_matches) if not value]})

    slide = readback_slides[-1]
    ns = readback_ns
    text = normalized_text(slide)
    check("kpi_protocol_and_cost_match_evidence", len(production["runs"]) == 4 and production["default_legal_count"] == production["default_run_count"] == 2 and production["constrained_legal_count"] == production["constrained_run_count"] == 2 and production["unique_sequence_count"] == 2 and production["official_example_readme_exact_match"] and "4/4" in text and "13/13" in text and "10/10" in text and "Fixed 4a447b0" in text and "model 9744dcc" in text and "deterministic" in text and "original_full" in text and "E. coli general" in text and "2 proteins × 2 modes" in text and f"Model load {production['model_load_seconds']:.6f} s" in text and f"inference total {production['total_inference_seconds']:.6f} s" in text and "Evidence: GitHub 210d2f4c" in text, {"runs": len(production["runs"]), "unique_cds": production["unique_sequence_count"], "load_s": production["model_load_seconds"], "inference_s": production["total_inference_seconds"]})
    expected_rows = [[run["record_id"], run["mode"], f"{run['qc']['protein_aa']} aa", f"{run['qc']['dna_nt']} nt", "PASS"] for run in production["runs"]]
    table = slide.find(".//s:table", ns)
    actual_rows = [] if table is None else [[normalized_text(cell) for cell in row.findall("s:td", ns)] for row in table.findall("s:tr", ns)[1:]]
    check("table_recomputed_from_frozen_reports", actual_rows == expected_rows, {"rows": actual_rows})
    notes = slide.findall("./s:note/s:content/s:p", ns)
    note_text = " ".join(normalized_text(note) for note in notes)
    check("notes_and_scientific_boundary", len(notes) == 4 and "13/13 PASS" in note_text and "10/10 PASS" in note_text and "8/8 PASS" in note_text and "不能声称 match_protein 带来额外收益" in note_text and "不是 time-matched 成本比较" in note_text and "no matched MFE/EFE, dense budget, main ranking, OOD or SOTA" in text and "outputs are unchanged per protein" in text and "default = constrained for both proteins" in text and "includes warmup" in text, {"note_paragraphs": len(notes), "main_baseline_comparison": False, "functional_ood": False, "sota_claim": False})
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
    check("new_page_geometry_and_readability_structure", in_bounds and minimum_font >= 9 and table is not None and len(table.findall("s:tr", ns)) == 5 and slide.find(".//s:undefined", ns) is None and not slide.findall(".//s:img", ns) and normalized_text(slide.findall(".//s:shape", ns)[-1]) == "74", {"in_bounds": in_bounds, "minimum_explicit_font_px": minimum_font, "table_rows": 5, "page_number": 74})

    passed = sum(item["pass"] for item in checks)
    report = {
        "protocol": "a8_rk05_codontransformer_ppt_independent_verification_v1",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "check_count": len(checks),
        "passed_checks": passed,
        "presentation_id": "WB1KsYGualerMUddEzMcCw1En0g",
        "slide_id": new_slide_id,
        "slide_number": 74,
        "baseline_slide_count": len(baseline_slides),
        "readback_slide_count": len(readback_slides),
        "baseline_revision": baseline_response["data"]["revision_id"],
        "readback_revision": readback_response["data"]["revision_id"],
        "old_pages_unchanged": all(semantic_matches),
        "baseline_xml_sha256": sha256(args.baseline_xml),
        "readback_xml_sha256": sha256(args.readback_xml),
        "evidence_sha256": {key: sha256(evidence / name) for key, name in names.items()},
        "checks": checks,
        "scope": {"bounded_official_smoke_recorded": True, "matched_mfe_efe_comparison": False, "dense_budget_complete": False, "main_baseline_matrix_closed": False, "functional_ood": False, "sota_claim": False},
    }
    output = Path(args.output)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "slide_id": new_slide_id, "slides": len(readback_slides), "output": str(output)}, ensure_ascii=False))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
