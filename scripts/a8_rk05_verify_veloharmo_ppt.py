#!/usr/bin/env python3
"""Independently verify the VeloHARMO A8-RK online-PPT append and readback."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    p.add_argument("--raw-dir", type=Path, default=Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ppt_veloharmo_v1"))
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    repo, raw = a.repo, a.raw_dir
    output = a.output or repo / "audits/20261118/RK05/veloharmo_ppt_independent_verification.json"
    before_path = raw / "veloharmo-before-v1.xml"
    after_path = raw / "veloharmo-after-v1.xml"
    before_response = load(raw / "veloharmo-before-response-v1.json")
    after_response = load(raw / "veloharmo-after-response-v1.json")
    add_response = load(raw / "veloharmo-add-response-v1.json")
    evidence_paths = {
        "production": repo / "audits/20261118/RK05/veloharmo_official_smoke_v1.json",
        "independent": repo / "audits/20261118/RK05/veloharmo_independent_verification_v1.json",
        "finalization": repo / "audits/20261118/RK05/veloharmo_finalization_v1.json",
    }
    production, independent, finalization = (load(path) for path in evidence_paths.values())
    before_root = ET.parse(before_path).getroot()
    after_root = ET.parse(after_path).getroot()
    uri = after_root.tag[1:].split("}")[0]
    ns = "{" + uri + "}"
    before = before_root.findall(ns + "slide")
    after = after_root.findall(ns + "slide")
    new = after[-1]
    text = "\n".join(t.strip() for t in new.itertext() if t.strip())
    checks = []

    def check(name: str, passed: bool, detail) -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    test = production["official_velogru_test"]
    ga = production["bounded_ga"]
    check("frozen_official_and_finalization_evidence",
          production["status"] == "BOUNDED_OFFICIAL_ALGORITHM_EXECUTION_COMPLETE"
          and production["source_commit"] == "38b48079856aeb9d33a1b10844d77aa8f6640032"
          and finalization["status"] == "CLOSED_BOUNDED_OFFICIAL_SMOKE"
          and finalization["passed_checks"] == finalization["check_count"] == 13,
          {"source_commit": production["source_commit"], "finalization": "13/13"})
    check("independent_reexecution_pass",
          independent["status"] == "PASS" and independent["passed_checks"] == independent["check_count"] == 17
          and independent["max_numeric_delta"] == 0.0 and independent["ga_best_equals_start"],
          {"independent": "17/17", "max_numeric_delta": independent["max_numeric_delta"]})
    check("write_and_revision_confirmed",
          add_response.get("ok") is True and add_response["data"]["slide_id"] == "pgh"
          and before_response["data"]["revision_id"] == 36
          and add_response["data"]["revision_id"] == after_response["data"]["revision_id"] == 37
          and after_response.get("ok") is True,
          {"before": 36, "after": 37, "slide_id": "pgh"})
    check("exactly_one_page_appended", len(before) == 74 and len(after) == 75 and after[-1].get("id") == "pgh",
          {"before": len(before), "after": len(after), "last_id": after[-1].get("id")})
    old_ids_same = [s.get("id") for s in before] == [s.get("id") for s in after[:74]]
    check("old_page_ids_and_order_unchanged", old_ids_same, {"old_pages": 74, "previous_last_id": after[-2].get("id")})
    for old_page in before + after[:74]:
        old_page.tail = None
    different = [i + 1 for i, (x, y) in enumerate(zip(before, after[:74])) if ET.tostring(x, encoding="unicode") != ET.tostring(y, encoding="unicode")]
    check("all_74_old_pages_semantically_unchanged", not different, {"unchanged": 74 - len(different), "different_pages": different})
    required_kpi = ["0.604403", "0.172683", "0.000000", "17/17", "13/13", "4.673605 s", "1.272917 s", "+0.371594", "7-item compatibility patch"]
    kpi_ok = all(s in text for s in required_kpi) and test["mean_pearson"] == 0.6044025421142578 and test["std_pearson"] == 0.17268328368663788 and ga["best_minus_start"] == 0 and ga["population_size"] == 8 and ga["generations"] == 2 and ga["seed"] == 20261118
    check("kpi_protocol_and_cost_match_evidence", kpi_ok,
          {"mean_pearson": test["mean_pearson"], "std_pearson": test["std_pearson"], "ga_best_minus_start": ga["best_minus_start"], "test_s": test["wall_seconds"], "ga_s": ga["wall_seconds"], "population": ga["population_size"], "generations": ga["generations"]})
    table = new.find(".//" + ns + "table")
    rows = [["".join(td.itertext()).strip() for td in tr.findall(ns + "td")] for tr in table.findall(ns + "tr")]
    expected_rows = [
        ["Official VeloGRU test", "E. coli / cuda:0", "7 selected records", "0.604403 mean Pearson", "PASS"],
        ["Native reference", "E. coli / CPU", "C1P620 · 36 codons", "-0.025608 fitness", "reference"],
        ["GA start", "yeast / CPU", "pop 8 · gen 2 · fixed seed", "0.345986 fitness", "legal CDS"],
        ["GA best", "yeast / CPU", "identical to start", "0.000000 change", "legal CDS"],
    ]
    table_ok = rows[1:] == expected_rows and ga["target_record"] == "C1P620" and ga["target_codons"] == 36 and ga["legal_synonymous_count"] == ga["candidate_count"] == 2 and not ga["start_to_best_improved"]
    check("table_recomputed_from_frozen_reports", table_ok, {"rows": rows[1:]})
    notes = new.findall("./" + ns + "note/" + ns + "content/" + ns + "p")
    boundary_ok = len(notes) == 4 and "Best candidate is identical to start" in text and "no five-species closure, main matrix, functional OOD or SOTA" in text and not production["main_baseline_comparison"] and not production["functional_ood"] and not production["sota_claim"]
    check("notes_and_scientific_boundary", boundary_ok, {"note_paragraphs": len(notes), "main_baseline_comparison": False, "functional_ood": False, "sota_claim": False})
    in_bounds = True
    for element in new.find(ns + "data"):
        tag = element.tag.split("}")[-1]
        if tag in {"shape", "table", "img", "embed"}:
            x, y = float(element.get("topLeftX")), float(element.get("topLeftY"))
            w, h = float(element.get("width")), float(element.get("height"))
            in_bounds &= x >= 0 and y >= 0 and x + w <= 960 and y + h <= 540
        elif tag == "line":
            in_bounds &= all(0 <= float(element.get(k)) <= (960 if k.endswith("X") else 540) for k in ("startX", "startY", "endX", "endY"))
    font_sizes = [float(c.get("fontSize")) for c in new.findall(".//" + ns + "content") if c.get("fontSize")]
    check("new_page_geometry_and_readability_structure", in_bounds and min(font_sizes) >= 9 and len(rows) == 5 and "75" in text,
          {"in_bounds": in_bounds, "minimum_explicit_font_px": min(font_sizes), "table_rows": len(rows), "page_number": 75})
    passed = sum(c["pass"] for c in checks)
    report = {
        "protocol": "a8_rk05_veloharmo_ppt_independent_verification_v1",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "check_count": len(checks), "passed_checks": passed,
        "presentation_id": "WB1KsYGualerMUddEzMcCw1En0g",
        "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "slide_id": "pgh", "slide_number": 75,
        "baseline_slide_count": len(before), "readback_slide_count": len(after),
        "baseline_revision": before_response["data"]["revision_id"], "readback_revision": after_response["data"]["revision_id"],
        "old_pages_unchanged": not different and old_ids_same,
        "baseline_xml_sha256": sha256(before_path), "readback_xml_sha256": sha256(after_path),
        "evidence_sha256": {name: sha256(path) for name, path in evidence_paths.items()},
        "checks": checks,
        "scope": {"bounded_official_smoke_recorded": True, "ga_iterative_improvement": False, "five_species_processed_matrices_complete": False, "main_baseline_matrix_closed": False, "functional_ood": False, "sota_claim": False},
    }
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "slide_id": "pgh", "output": str(output)}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
