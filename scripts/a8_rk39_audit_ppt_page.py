#!/usr/bin/env python3
"""Audit one RK39 slide; run from a directory containing its XML and evidence/."""
import argparse
import json
import math
from pathlib import Path
import statistics
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
    xml_path = ROOT / f"rk39_{page}.xml"
    root = ET.parse(xml_path).getroot()
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "pass": bool(ok), "detail": str(detail)})

    production = json.loads((EVIDENCE / "rk39_common_input_actual_set_v1.json").read_text())
    independent = json.loads((EVIDENCE / "rk39_common_input_actual_set_independent_v1.json").read_text())
    clean = json.loads((EVIDENCE / "rk39_common_input_actual_set_clean_v1.json").read_text())
    closeout = json.loads((EVIDENCE / "rk39_clean_reproduction_closeout_v1.json").read_text())
    test_log = (EVIDENCE / "rk39_full_pytest.log").read_text()
    text = " ".join(root.itertext())
    primary = [t for t in production["tests"] if t["confirmatory"]]
    hv = next(t for t in primary if t["endpoint"] == "hypervolume_normalized")
    ned = next(t for t in primary if t["endpoint"] == "pairwise_ned")
    sensitivity = {(t["method"], t["endpoint"]): t for t in production["tests"] if not t["confirmatory"]}
    abs_values = {"LinearDesign-11": (
        statistics.mean(r["external"]["hypervolume_normalized"] for r in production["per_record"]),
        statistics.mean(r["external"]["pairwise_ned"] for r in production["per_record"]),
    )}
    for method, label in [("hill_climbing", "Hill-climbing"), ("mh_annealing", "MH-annealing"), ("uniform", "Uniform synonymous")]:
        abs_values[label] = tuple(
            statistics.mean(statistics.mean(r["methods"][method][str(s)][endpoint] for s in range(3)) for r in production["per_record"])
            for endpoint in ["hypervolume_normalized", "pairwise_ned"]
        )

    check("single_slide_root", root.tag == "{https://www.larkoffice.com/sml/2.0}slide")
    check("page_number_present", str(page) in text)
    check("four_speaker_notes", len(root.findall("s:note/s:content/s:p", NS)) == 4)
    check("unresolved_decision_preserved", production["decision"] == independent["decision"] == clean["decision"] == closeout["decision"] == "COMMON_INPUT_ACTUAL_SET_TASK_UNRESOLVED")
    check("primary_gate_false_everywhere", not any([production["primary_gate_passed"], independent["primary_gate_passed"], clean["primary_gate_passed"], closeout["primary_gate_passed"]]))
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

    required = {187: ["18", "3", "1,782", "Protein only", "Common initialization", "TAA", "First k real unique outputs", "20,000 paired bootstrap"],
                188: ["162 / 162", "1,782", "342.52 s", "131 total", "mean 7.278", "range 4-11", "No best-k"],
                189: [f6(hv["effect"]), f6(ned["effect"]), f6(hv["ci95"][0]), f6(hv["ci95"][1]), f6(ned["ci95"][0]), f6(ned["ci95"][1]), "9.9995e-5", "0 / 18 positive", "COMMON_INPUT_ACTUAL_SET_TASK_UNRESOLVED"],
                190: [f6(v) for pair in abs_values.values() for v in pair] + [f6(sensitivity[("uniform", "pairwise_ned")]["effect"]), f6(sensitivity[("uniform", "hypervolume_normalized")]["effect"])],
                191: ["1216 / 1216", "830 / 830", "0.0", "1,594", "477 passed", "1 skipped", "5 subtests passed", "b3f89b94", "9bbac1a6"],
                192: ["EXTERNAL SOTA", "TIME-MATCHED", "FUNCTIONAL UNTOUCHED", "RK-G1 / SUBMITTABLE", "false / false", "non-submittable"]}
    for token in required.get(page, []):
        check(f"required_text_{token}", token in text)

    if page == 188:
        ks = [r["external"]["k"] for r in production["per_record"]]
        check("run_count", production["n_runs"] == clean["n_runs"] == 162)
        check("call_count", production["n_unique_scorer_calls"] == clean["n_unique_scorer_calls"] == 1782)
        check("matched_k", sum(ks) == 131 and min(ks) == 4 and max(ks) == 11)
        check("wall_time_rounding", f"{production['wall_seconds']:.2f}" == "342.52")
        check("scoring_sum_rounding", f"{sum(r['objective_scoring_seconds'] for r in production['runs']):.3f}" == "1311.998")
    if page == 189:
        for t in primary:
            check(f"{t['endpoint']}_all_records_negative", len(t["per_record_effects"]) == 18 and all(x < 0 for x in t["per_record_effects"]))
            check(f"{t['endpoint']}_all_seeds_negative", len(t["seed_mean_effects"]) == 3 and all(x < 0 for x in t["seed_mean_effects"]))
            check(f"{t['endpoint']}_ci_negative", t["ci95"][1] < 0)
            check(f"{t['endpoint']}_holm", f"{t['holm_p']:.4e}" == "9.9995e-05")
    if page == 190:
        check("uniform_ned_all_positive", all(x > 0 for x in sensitivity[("uniform", "pairwise_ned")]["per_record_effects"]))
        check("uniform_hv_all_negative", all(x < 0 for x in sensitivity[("uniform", "hypervolume_normalized")]["per_record_effects"]))
        check("mh_both_negative", all(sensitivity[("mh_annealing", e)]["effect"] < 0 for e in ["hypervolume_normalized", "pairwise_ned"]))
    if page == 191:
        check("independent_counts", independent["n_pass"] == independent["n_checks"] == 1216 and independent["n_unique_sequences_independently_rescored"] == 1594 and independent["max_objective_abs_error"] == 0.0)
        check("clean_counts", closeout["n_pass"] == closeout["n_checks"] == 830)
        check("test_log", "477 passed" in test_log and "1 skipped" in test_log and "5 subtests passed" in test_log)
    if page == 192:
        for key in ["external_sota_authorized", "time_matched_comparison", "functional_untouched_evaluated", "new_functional_labels_read", "rk_g1_pass", "manuscript_submittable"]:
            check(f"boundary_{key}", production[key] is False)

    report = {"page": page, "xml": xml_path.name, "n_pass": sum(c["pass"] for c in checks), "n_checks": len(checks), "status": "PASS" if all(c["pass"] for c in checks) else "FAIL", "checks": checks}
    (ROOT / f"rk39_{page}_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"page": page, "status": report["status"], "n_pass": report["n_pass"], "n_checks": report["n_checks"], "failures": [c for c in checks if not c["pass"]]}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
