#!/usr/bin/env python3
"""Audit RK35 online/candidate slides directly against frozen scientific JSON."""
from pathlib import Path
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET

IDS = ["pSw", "pSl", "pSN", "pSt", "pSX"]


def local(tag):
    return tag.rsplit("}", 1)[-1]


def text(node):
    return " ".join("".join(node.itertext()).split())


def children(node, name):
    return [x for x in node.iter() if local(x.tag) == name]


def rows(table):
    return [[text(td) for td in list(tr) if local(td.tag) == "td"] for tr in list(table) if local(tr.tag) == "tr"]


def find_table(slide, header):
    for table in children(slide, "table"):
        rr = rows(table)
        if rr and rr[0] == header:
            return rr
    raise AssertionError((slide.get("id"), header))


def split_test(name):
    model, rest = name.split("__", 1)
    comparison, metric = rest.rsplit("__", 1)
    return model, comparison, metric


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--closeout", type=Path, required=True)
    parser.add_argument("--manuscript-review", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--slides-dir", type=Path)
    parser.add_argument("--deck", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert bool(args.slides_dir) != bool(args.deck)
    result = json.loads(args.result.read_text())
    independent = json.loads(args.independent.read_text())
    comparison = json.loads(args.comparison.read_text())
    closeout = json.loads(args.closeout.read_text())
    manuscript = json.loads(args.manuscript_review.read_text())
    if args.deck:
        root = ET.parse(args.deck).getroot()
        slides = {s.get("id"): s for s in children(root, "slide")}
    else:
        slides = {}
        for sid in IDS:
            slides[sid] = ET.parse(args.slides_dir / ("rk35_" + sid + ".xml")).getroot()
    checks = []

    def check(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    for sid in IDS:
        check("presence:" + sid, sid in slides)
        check("notes:" + sid, len(children(slides[sid], "note")) == 1 and len(children(children(slides[sid], "note")[0], "p")) == 3)

    if args.source:
        source_root = ET.parse(args.source).getroot()
        source_slides = {s.get("id"): s for s in children(source_root, "slide")}
        for sid in IDS:
            a = list(source_slides[sid].iter())
            b = list(slides[sid].iter())
            check("element_count:" + sid, len(a) == len(b), [len(a), len(b)])
            check("element_identity:" + sid, [(local(x.tag), x.get("id")) for x in a] == [(local(x.tag), x.get("id")) for x in b])
            check("geometry_and_attributes:" + sid, all(x.attrib == y.attrib for x, y in zip(a, b)))

    all_text = {sid: text(slides[sid]) for sid in IDS}
    check("arm_count_label", "EVALUATED ARMS 6" in all_text["pSw"] and "STRUCTURE ARMS" not in all_text["pSw"])
    check("fit_accounting", "500 300 new + 200 reused" in all_text["pSw"] and "NEW REAL FITS 300" in all_text["pSl"] and "REUSED FITS 200" in all_text["pSl"])
    gate_max_delta = max(abs(float(value)) for detail in result["consistency_gate"]["details"] for value in detail["deltas"].values())
    check("gate_delta", "GATE MAX Δ 0" in all_text["pSl"] and result["consistency_gate"]["pass"] and gate_max_delta <= 1e-12, gate_max_delta)

    gate_rows = find_table(slides["pSl"], ["Model", "Metric", "Δ effect", "95% CI", "Holm p", "Pass"])
    check("gate_row_count", len(gate_rows) == 5, len(gate_rows))
    for i, test in enumerate(result["gate_tests"], 1):
        model, contrast, metric = split_test(test["test"])
        expected = ["Ridge" if model == "ridge" else "HistGB", "Spearman" if metric.startswith("spearman") else "MSE improve",
                    f"{test['observed_effect']:+.6f}", f"[{test['ci95'][0]:.6f}, {test['ci95'][1]:.6f}]", f"{test['p_holm']:.6f}", "Yes" if test["pass"] else "No"]
        check("gate_row:" + test["test"], gate_rows[i] == expected, {"expected": expected, "observed": gate_rows[i]})

    primary_rows = find_table(slides["pSN"], ["Comparison", "Model", "Metric", "Δ effect", "95% CI", "Holm p", "Seeds", "Pass"])
    check("primary_row_count", len(primary_rows) == 9, len(primary_rows))
    for i, test in enumerate(result["primary_tests"], 1):
        model, contrast, metric = split_test(test["test"])
        expected = ["trunc − simple" if contrast == "trunc_vs_simple" else "exact − trunc",
                    "Ridge" if model == "ridge" else "HistGB", "Spearman" if metric.startswith("spearman") else "MSE improve",
                    f"{test['observed_effect']:+.6f}", f"[{test['ci95'][0]:.6f}, {test['ci95'][1]:.6f}]", f"{test['p_holm']:.6f}",
                    f"{test['positive_seeds']}/10", "Yes" if test["pass"] else "No"]
        check("primary_row:" + test["test"], primary_rows[i] == expected, {"expected": expected, "observed": primary_rows[i]})
    check("failed_rows_keep_seed_counts", primary_rows[7][6] == "10/10" and primary_rows[8][6] == "10/10")
    check("decision", "PRIMARY DECISION D1" in all_text["pSN"] and result["decision_code"] == "D1")
    check("primary_conclusion", result["scientific_conclusion"] in all_text["pSN"])
    check("c1_c2_counts", "C1 trunc − simple 4 / 4" in all_text["pSN"] and "C2 exact − trunc 2 / 4" in all_text["pSN"])
    check("bounded_title", "Natural window retains the increment within Kudla" in all_text["pSN"] and "coverage is not necessary" not in all_text["pSN"])
    check("unidentified_cross_study", "cross-study mechanisms remain unidentified" in all_text["pSN"] and "HOST / ASSAY / STUDY EFFECTS REMAIN UNIDENTIFIED" in all_text["pSN"])

    absolute_rows = find_table(slides["pSt"], ["Model", "Arm", "Spearman ρ", "MSE"])
    check("absolute_row_count", len(absolute_rows) == 11, len(absolute_rows))
    arm_labels = {"simple": "simple", "exact_local": "exact local d2", "cds_start_local": "CDS-start d2", "trunc_local": "trunc CDS4-45 d2", "trunc_local_d0": "trunc CDS4-45 d0"}
    index = 1
    for model in ["ridge", "histgb"]:
        for arm in ["simple", "exact_local", "cds_start_local", "trunc_local", "trunc_local_d0"]:
            record = result["primary_absolute_performance"][model][arm]
            expected = ["Ridge" if model == "ridge" else "HistGB", arm_labels[arm], f"{record['spearman']:+.6f}", f"{record['mse']:.6f}"]
            check("absolute_row:" + model + ":" + arm, absolute_rows[index] == expected, {"expected": expected, "observed": absolute_rows[index]})
            index += 1
    check("secondary_descriptive", "Secondary (descriptive · body-shift confounded)" in all_text["pSt"])
    check("no_gradient_claim", "coverage gradient" not in all_text["pSt"] and "prevent a mechanistic gradient claim" in all_text["pSt"])

    check("independent_summary", independent["checks_passed"] == 39 and independent["checks_total"] == 39 and "INDEPENDENT 39 / 39" in all_text["pSX"])
    check("clean_summary", comparison["checks_passed"] == 12 and comparison["checks_total"] == 12 and "CLEAN COMPARE 12 / 12" in all_text["pSX"])
    check("closeout_summary", closeout["checks_passed"] == 21 and closeout["checks_total"] == 21 and "CLOSEOUT 21 / 21" in all_text["pSX"])
    check("manuscript_summary", manuscript["checks_passed"] == 43 and manuscript["checks_total"] == 43 and "review 43/43" in all_text["pSX"])
    check("test_summary", "PROJECT TESTS 453 passed · 1 skipped · 0 failed" in all_text["pSX"])
    check("next_gate", "independent complete-CDS validation or a data-supported pivot" in all_text["pSX"] and "no more window ablation" in all_text["pSX"])
    check("not_pending_user", "pending user" not in all_text["pSX"] and "left to the user" not in all_text["pSX"])
    check("rk_g1_boundary", "RK-G1=false" in all_text["pSX"] and result["scientific_flags"]["RK_G1_complete"] is False)
    check("independent_boundary", "not independent confirmation" in all_text["pSX"] and result["scientific_flags"]["independent_confirmation"] is False)

    passed = sum(x["pass"] for x in checks)
    report = {"status": "PASS" if passed == len(checks) else "FAIL", "summary": {"checks_total": len(checks), "checks_passed": passed, "checks_failed": len(checks) - passed},
              "result_sha256": hashlib.sha256(args.result.read_bytes()).hexdigest(), "checks": checks}
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "summary": report["summary"], "failures": [x for x in checks if not x["pass"]]}, indent=2))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
