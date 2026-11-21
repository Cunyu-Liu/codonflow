#!/usr/bin/env python3
"""Pre-write RK34 candidate audit: source-bound tables, notes, XML and canvas."""
from pathlib import Path
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET

PAGES = list(range(156, 165))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cells(table):
    return [["".join(td.itertext()) for td in tr.findall("{*}td")]
            for tr in table.findall("{*}tr")]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--ppt-dir", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    b, d = args.base, args.ppt_dir
    r = json.loads((b / "rk34_start_context_result_v2.json").read_text())
    ind = json.loads((b / "rk34_start_context_independent_v2.json").read_text())
    ind1 = json.loads((b / "rk34_start_context_independent_v1.json").read_text())
    repro = json.loads((b / "rk34_clean_reproduction_comparison_v1.json").read_text())
    close = json.loads((b / "rk34_closeout_v2.json").read_text())
    audit = json.loads((b / "rk34_manuscript_audit_v1.json").read_text())
    roots = {n: ET.parse(d / f"rk34_{n}.xml").getroot() for n in PAGES}
    checks = []

    def check(name, ok, details):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    check("nine_candidate_pages", sorted(roots) == PAGES, sorted(roots))
    check("accepted_evidence", ind["status"] == repro["status"] == close["status"] == audit["status"] == "PASS" and ind1["status"] == "FAIL", {
        "independent_v2": ind["status"], "independent_v1": ind1["status"], "reproduction": repro["status"], "closeout": close["status"], "manuscript": audit["status"]})
    for n, root in roots.items():
        check(f"page_{n}_single_slide", root.tag.endswith("slide"), root.tag)
        check(f"page_{n}_no_undefined", not root.findall(".//{*}undefined"), len(root.findall(".//{*}undefined")))
        notes = ["".join(x.itertext()) for x in root.findall(".//{*}note//{*}p")]
        check(f"page_{n}_speaker_notes", 3 <= len(notes) <= 5, notes)
        visible = "".join(root.find(".//{*}data").itertext())
        check(f"page_{n}_number_visible", str(n) in visible, n)
        bounds = []
        for element in list(root.find(".//{*}data")):
            try:
                x, y = float(element.attrib["topLeftX"]), float(element.attrib["topLeftY"])
                w, h = float(element.attrib["width"]), float(element.attrib["height"])
            except (KeyError, ValueError):
                continue
            bounds.append({"id": element.attrib.get("id"), "x": x, "y": y, "width": w, "height": h,
                           "inside": x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= 960 and y + h <= 540})
        check(f"page_{n}_canvas", bool(bounds) and all(x["inside"] for x in bounds), bounds)

    primary = [t for t in r["primary_tests"] if t["analysis"] == "primary"]
    fams = [("exact_vs_simple", "exact − simple"), ("upstream_given_start", "upstream | start"),
            ("start_given_upstream", "start | upstream"), ("start_without_upstream", "start | no upstream"),
            ("upstream_without_start", "upstream | no start")]
    for page, model in [(159, "ridge"), (160, "histgb")]:
        expected = [["Comparison", "Metric", "Effect", "95% CI", "Raw p", "Holm p", "Seeds", "Pass"]]
        for t in primary:
            if t["model"] != model:
                continue
            expected.append([dict(fams)[t["family"]], "Spearman" if t["metric"] == "spearman_effect" else "MSE impr.",
                             f"{t['observed_effect']:+.5f}", f"[{t['ci95'][0]:+.4f},{t['ci95'][1]:+.4f}]",
                             f"{t['p_cluster_swap']:.4f}", f"{t['p_holm']:.4f}", f"{t['positive_seeds']}/10", "Y" if t["pass"] else "N"])
        tables = roots[page].findall(".//{*}table")
        actual = cells(tables[0]) if len(tables) == 1 else []
        check(f"page_{page}_all_10_source_endpoints_exact", actual == expected, {"expected": expected, "actual": actual})

    expected_abs = [["Model", "Arm", "Spearman", "MSE"]]
    labels = {"simple": "simple", "exact_real_d2": "exact d2", "start_only_d2": "start only d2",
              "upstream_only_d2": "upstream only d2", "neither_d2": "neither d2"}
    for row in r["primary_absolute_performance"]:
        if row["arm"] == "null":
            expected_abs.append(["Intercept", "null", f"{row['spearman']:.6f}", f"{row['mse']:.6f}"])
            continue
        model, arm = row["arm"].split("_", 1)
        if arm in labels:
            expected_abs.append([{"ridge": "Ridge", "histgb": "HistGB"}[model], labels[arm], f"{row['spearman']:.6f}", f"{row['mse']:.6f}"])
    actual_abs = cells(roots[161].findall(".//{*}table")[0])
    check("page_161_all_11_absolute_rows_exact", actual_abs == expected_abs, {"expected": expected_abs, "actual": actual_abs})

    text158 = "".join(roots[158].find(".//{*}data").itertext())
    check("page_158_decision_and_boundaries", all(x in text158 for x in ["12 / 20", "4 / 4", "0 / 2", "JOINT_EXACT_CONTEXT_WITHOUT_SEPARABLE_CONTRIBUTIONS_RETROSPECTIVELY"]), text158)
    text162 = "".join(roots[162].find(".//{*}data").itertext())
    check("page_162_reproduction_counts", all(x in text162 for x in ["155 / 155", f"{repro['checks_passed']} / {repro['checks_total']}", "455 PASS", f"{close['checks_passed']} / {close['checks_total']}"]), text162)
    text164 = "".join(roots[164].find(".//{*}data").itertext())
    check("page_164_open_gates_not_completed", all(x in text164 for x in ["EXTERNAL / TIME-MATCHED", "OPEN", "FUNCTIONAL UNTOUCHED", "UNREAD", "RK-G1 = FALSE", "Complete seven-method dense generation calls"]), text164)
    all_text = "".join("".join(root.find(".//{*}data").itertext()) for root in roots.values())
    check("histgb_model_label_case", "Histgb" not in all_text and "HistGB" in "".join(roots[160].find(".//{*}data").itertext()) and "HistGB" in "".join(roots[161].find(".//{*}data").itertext()), {"forbidden": "Histgb", "required": "HistGB"})
    report = {
        "schema": "a8-rk34-ppt-candidate-audit-v1",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "pages": PAGES,
        "checks": checks,
        "checks_passed": sum(c["pass"] for c in checks),
        "checks_total": len(checks),
        "failed_checks": [c["name"] for c in checks if not c["pass"]],
        "source_sha256": {name: sha(b / name) for name in [
            "rk34_start_context_result_v2.json", "rk34_start_context_independent_v2.json",
            "rk34_clean_reproduction_comparison_v1.json", "rk34_closeout_v2.json", "rk34_manuscript_audit_v1.json"]},
        "candidate_sha256": {str(n): sha(d / f"rk34_{n}.xml") for n in PAGES},
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "failed": report["failed_checks"]}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
