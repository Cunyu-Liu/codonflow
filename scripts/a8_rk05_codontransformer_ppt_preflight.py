#!/usr/bin/env python3
"""Independent preflight for the CodonTransformer A8-RK result slide."""
import argparse
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-xml", required=True)
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
    root = ET.parse(args.candidate_xml).getroot()
    ns = namespace(root)
    text = normalized_text(root)
    table = root.find(".//s:table", ns)
    rows = [] if table is None else [
        [normalized_text(cell) for cell in row.findall("s:td", ns)]
        for row in table.findall("s:tr", ns)[1:]
    ]
    expected_rows = [
        [run["record_id"], run["mode"], f"{run['qc']['protein_aa']} aa", f"{run['qc']['dna_nt']} nt", "PASS"]
        for run in production["runs"]
    ]
    notes = root.findall("./s:note/s:content/s:p", ns)
    note_text = " ".join(normalized_text(note) for note in notes)
    authored_ids = [element.attrib["id"] for element in root.iter() if "id" in element.attrib]
    in_bounds = True
    minimum_font = 1000.0
    for element in root.findall(".//*[@topLeftX]", ns):
        x = float(element.attrib["topLeftX"])
        y = float(element.attrib["topLeftY"])
        width = float(element.attrib["width"])
        height = float(element.attrib["height"])
        in_bounds = in_bounds and x >= 0 and y >= 0 and x + width <= 960 and y + height <= 540
    for content in root.findall(".//s:content[@fontSize]", ns):
        minimum_font = min(minimum_font, float(content.attrib["fontSize"]))
    checks = []

    def check(name, condition):
        checks.append({"name": name, "pass": bool(condition)})

    check("frozen evidence complete", production["status"] == "BOUNDED_OFFICIAL_EXECUTION_COMPLETE" and independent["status"] == "PASS" and independent["passed_checks"] == independent["check_count"] == 13 and finalization["status"] == "CLOSED_BOUNDED_OFFICIAL_SMOKE" and finalization["passed_checks"] == finalization["check_count"] == 10 and materialization["status"] == "COMPLETE" and len(materialization["model"]["files"]) == 8)
    check("four legal runs and two unique CDS", len(production["runs"]) == 4 and production["default_legal_count"] == production["default_run_count"] == 2 and production["constrained_legal_count"] == production["constrained_run_count"] == 2 and production["unique_sequence_count"] == 2 and production["official_example_readme_exact_match"])
    check("table matches four frozen runs", rows == expected_rows)
    check("KPI protocol and costs match evidence", "4/4" in text and "13/13" in text and "10/10" in text and "Fixed 4a447b0" in text and "model 9744dcc" in text and "deterministic" in text and "original_full" in text and "E. coli general" in text and "2 proteins × 2 modes" in text and f"Model load {production['model_load_seconds']:.6f} s" in text and f"inference total {production['total_inference_seconds']:.6f} s" in text and "Evidence: GitHub 210d2f4c" in text)
    check("scope and unchanged-mode boundary", "no matched MFE/EFE, dense budget, main ranking, OOD or SOTA" in text and "outputs are unchanged per protein" in text and "default = constrained for both proteins" in text and "includes warmup" in text)
    check("four evidence-bound speaker notes", len(notes) == 4 and "13/13 PASS" in note_text and "10/10 PASS" in note_text and "8/8 PASS" in note_text and "不能声称 match_protein 带来额外收益" in note_text and "不是 time-matched 成本比较" in note_text)
    check("all elements in canvas and no authored IDs", in_bounds and not authored_ids and table is not None and len(table.findall("s:tr", ns)) == 5 and minimum_font >= 9 and root.find(".//s:undefined", ns) is None and not root.findall(".//s:img", ns))
    check("page number and source provenance", normalized_text(root.findall(".//s:shape", ns)[-1]) == "74" and production["source_commit"].startswith("4a447b0") and production["model_commit"].startswith("9744dcc"))

    passed = sum(item["pass"] for item in checks)
    report = {
        "protocol": "a8_rk05_codontransformer_ppt_preflight_v1",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "check_count": len(checks),
        "passed_checks": passed,
        "candidate_xml_sha256": sha256(args.candidate_xml),
        "evidence_sha256": {key: sha256(evidence / name) for key, name in names.items()},
        "checks": checks,
    }
    output = Path(args.output)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for item in checks:
        print(("PASS " if item["pass"] else "FAIL ") + item["name"])
    print(f"PREFLIGHT {passed}/{len(checks)} {'PASS' if passed == len(checks) else 'FAIL'}")
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
