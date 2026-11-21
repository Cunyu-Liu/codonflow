#!/usr/bin/env python3
"""Audit one RK40 slide; run from a directory containing its XML and evidence/."""
import argparse
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

NS = {"s": "https://www.larkoffice.com/sml/2.0"}
ROOT = Path.cwd()
EVIDENCE = ROOT / "evidence"


def f6(x):
    return f"{x:.6f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page", type=int)
    args = ap.parse_args()
    page = args.page
    xml_path = ROOT / f"rk40_{page}.xml"
    root = ET.parse(xml_path).getroot()
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "pass": bool(ok), "detail": str(detail)})

    production = json.loads((EVIDENCE / "rk40_budget_initialization_v1.json").read_text())
    independent = json.loads((EVIDENCE / "rk40_budget_initialization_independent_v1.json").read_text())
    clean = json.loads((EVIDENCE / "rk40_budget_initialization_clean_v1.json").read_text())
    closeout = json.loads((EVIDENCE / "rk40_clean_reproduction_closeout_v1.json").read_text())
    test_log = (EVIDENCE / "rk40_full_pytest.log").read_text()
    text = " ".join(root.itertext())
    primary = [t for t in production["tests"] if t["confirmatory"]]
    norm = [t for t in primary if t["family"] == "normalization_at_short_budget"]
    budget = [t for t in primary if t["family"] == "budget_within_raw_search"]
    external = next(t for t in production["tests"] if t["family"] == "external_initialization_raw" and t["endpoint"] == "best_normalized_weighted_utility")
    external_hv = next(t for t in production["tests"] if t["family"] == "external_initialization_raw" and t["endpoint"] == "best_single_point_normalized_hv")
    absolute = production["absolute_performance"]

    check("single_slide_root", root.tag == "{https://www.larkoffice.com/sml/2.0}slide")
    check("page_number_present", str(page) in text)
    check("four_speaker_notes", len(root.findall("s:note/s:content/s:p", NS)) >= 4)
    decision = "NORMALIZATION_AND_SHORT_BUDGET_BOTH_CONTRIBUTE"
    check("mechanism_decision_preserved", all(x["decision"] == decision for x in [production, independent, clean, closeout]))
    check("primary_mechanism_gate_true", all(x["primary_gate_passed"] for x in [production, independent, clean]) and all(closeout["primary_family_pass"].values()))
    check("scientific_gate_false", all(x["scientific_gate_passed"] is False for x in [production, independent, closeout]))
    check("forbidden_victory_language_absent", not any(x in text for x in ["CodonFlow wins", "SOTA achieved", "TASK_RESOLVED", "submission ready", "functional advantage confirmed"]))

    for idx, shape in enumerate(root.findall(".//s:shape", NS)):
        x = float(shape.attrib["topLeftX"]); y = float(shape.attrib["topLeftY"])
        w = float(shape.attrib["width"]); h = float(shape.attrib["height"])
        check(f"shape_{idx}_inside_canvas", x >= 0 and y >= 0 and x + w <= 960 and y + h <= 540, (x, y, w, h))
        content = shape.find("s:content", NS)
        if content is not None and content.attrib.get("wrap") == "false":
            size = float(content.attrib.get("fontSize", "9"))
            for p in content.findall("s:p", NS):
                value = "".join(p.itertext())
                estimated = sum(size * (1.0 if ord(c) > 127 else 0.55) for c in value)
                check(f"shape_{idx}_unwrapped_text_fits", estimated <= w + 0.5, {"estimated": estimated, "width": w, "text": value})
    for idx, tbl in enumerate(root.findall(".//s:table", NS)):
        widths = [float(c.attrib["width"]) for c in tbl.findall("s:colgroup/s:col", NS)]
        rows = tbl.findall("s:tr", NS)
        check(f"table_{idx}_width", math.isclose(sum(widths), float(tbl.attrib["width"])))
        check(f"table_{idx}_height", math.isclose(sum(float(r.attrib["height"]) for r in rows), float(tbl.attrib["height"])))
        check(f"table_{idx}_columns", all(len(r.findall("s:td", NS)) == len(widths) for r in rows))
        check(f"table_{idx}_inside_canvas", float(tbl.attrib["topLeftY"]) + float(tbl.attrib["height"]) <= 540)

    required = {
        193: ["18", "3", "5 new + 1 accepted", "Normalization", "Budget", "Initialization", "20,000", "external-seeded"],
        194: ["270 / 270", "12,690", "324", "13,284", "1188 / 1188", "11,275", "Not inferred"],
        195: [f6(norm[0]["effect"]), f6(norm[1]["effect"]), f6(norm[0]["ci95"][0]), f6(norm[0]["ci95"][1]), f6(norm[1]["ci95"][0]), f6(norm[1]["ci95"][1]), "1.9999e-4", "3 / 3 positive"],
        196: [f6(budget[0]["effect"]), f6(budget[1]["effect"]), f6(budget[0]["ci95"][0]), f6(budget[0]["ci95"][1]), f6(budget[1]["ci95"][0]), f6(budget[1]["ci95"][1]), "9.9995e-5", "3 / 3 positive"],
        197: [f6(external["effect"]), f6(external_hv["effect"]), "5031 / 5031", "948 / 948", "11,275", "0.0", f6(absolute["raw_external_b11"]["best_normalized_weighted_utility"]), f6(absolute["raw_external_b11"]["best_single_point_normalized_hv"])],
        198: ["Both contribute", "Unresolved", "EXTERNAL SOTA", "FUNCTIONAL / SUBMITTABLE", "false / false", "non-submittable", "basin-aware"]}
    for token in required.get(page, []):
        check(f"required_text_{token}", token in text)
    if page == 194:
        check("production_counts", production["n_new_runs"] == clean["n_new_runs"] == 270 and production["n_new_unique_scorer_calls"] == clean["n_new_unique_scorer_calls"] == 12690)
        check("analysis_counts", independent["n_runs"] == 324 and independent["n_raw_points"] == 13284)
        check("trajectory_counts", production["trajectory_identity"]["n_checks"] == production["trajectory_identity"]["n_pass"] == 1188)
        check("independent_unique_sequences", independent["n_unique_sequences_independently_rescored"] == 11275)
    if page in {195, 196}:
        for t in (norm if page == 195 else budget):
            check(f"{t['endpoint']}_all_seeds_positive", len(t["seed_mean_effects"]) == 3 and all(x > 0 for x in t["seed_mean_effects"]))
            check(f"{t['endpoint']}_ci_positive", t["ci95"][0] > 0)
            check(f"{t['endpoint']}_supported", t["supported_advantage"] is True)
    if page == 197:
        check("independent_counts", independent["n_pass"] == independent["n_checks"] == 5031 and independent["n_unique_sequences_independently_rescored"] == 11275 and independent["max_objective_abs_error"] == 0.0)
        check("clean_counts", closeout["n_pass"] == closeout["n_checks"] == 948)
        check("test_log", "484 passed" in test_log and "1 skipped" in test_log and "5 subtests passed" in test_log)
        check("external_diagnostic_not_confirmatory", not external["confirmatory"] and not external_hv["confirmatory"])
    if page == 198:
        for key in ["external_sota_authorized", "time_matched_comparison", "functional_untouched_evaluated", "new_functional_labels_read", "rk_g1_pass", "manuscript_submittable"]:
            check(f"boundary_{key}", production[key] is False)
    report = {"page": page, "xml": xml_path.name, "n_pass": sum(c["pass"] for c in checks), "n_checks": len(checks), "status": "PASS" if all(c["pass"] for c in checks) else "FAIL", "checks": checks}
    (ROOT / f"rk40_{page}_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"page": page, "status": report["status"], "n_pass": report["n_pass"], "n_checks": report["n_checks"], "failures": [c for c in checks if not c["pass"]]}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
