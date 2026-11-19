#!/usr/bin/env python3
"""Independently verify three appended RK-13 slides and the untouched 95-page baseline."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(element: ET.Element) -> bytes:
    item = copy.deepcopy(element)
    def local(node):
        return node.tag.rsplit("}", 1)[-1]
    for parent in item.iter():
        if local(parent) == "shape" and parent.attrib.get("type") != "text":
            for child in list(parent):
                if local(child) == "content" and not list(child) and not (child.text or "").strip() and child.attrib == {"fontSize": "16", "fontFamily": "思源黑体", "color": "rgba(31, 35, 41, 1)"}:
                    parent.remove(child)
    parent_map = {child: parent for parent in item.iter() for child in parent}
    for node in item.iter():
        node.attrib.pop("id", None)
        node.text = (node.text or "").strip()
        node.tail = None
        if local(node) == "content":
            if node.attrib.get("textType") == "body":
                node.attrib.pop("textType", None)
            if node.attrib.get("wrap") == "true":
                node.attrib.pop("wrap", None)
            if local(parent_map.get(node, node)) == "td" and node.attrib.get("textAlign") == "center":
                node.attrib.pop("textAlign", None)
            spacing = node.attrib.get("lineSpacing")
            if spacing and ":" in spacing:
                kind, value = spacing.split(":", 1)
                try:
                    node.attrib["lineSpacing"] = f"{kind}:{float(value):.12g}"
                except ValueError:
                    pass
        if local(node) == "col" and node.attrib.get("span") == "1":
            node.attrib.pop("span", None)
        node.attrib = dict(sorted(node.attrib.items()))
    ET.register_namespace("", item.tag.split("}")[0][1:])
    return ET.tostring(item, encoding="utf-8")


def slides(path: Path):
    root = ET.parse(path).getroot()
    ns = root.tag.split("}")[0][1:]
    return root, ns, root.findall(f".//{{{ns}}}slide")


def fmt_signed(value):
    return f"{value:+.6f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate96", type=Path, required=True)
    parser.add_argument("--candidate97", type=Path, required=True)
    parser.add_argument("--candidate98", type=Path, required=True)
    parser.add_argument("--readback", type=Path, required=True)
    parser.add_argument("--response96", type=Path, required=True)
    parser.add_argument("--response97", type=Path, required=True)
    parser.add_argument("--response98", type=Path, required=True)
    parser.add_argument("--finalization", type=Path, required=True)
    parser.add_argument("--ensemble", type=Path, required=True)
    parser.add_argument("--ensemble-independent", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--matrix-independent", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    final = json.loads(args.finalization.read_text())
    ensemble = json.loads(args.ensemble.read_text())
    ensemble_ind = json.loads(args.ensemble_independent.read_text())
    matrix = json.loads(args.matrix.read_text())
    matrix_ind = json.loads(args.matrix_independent.read_text())
    if not final["status"].startswith("PASS_") or final["checks_passed"] != final["checks_total"]:
        raise ValueError("finalization gate is not PASS")
    for key, path in (("ensemble_sha256", args.ensemble), ("ensemble_independent_sha256", args.ensemble_independent), ("matrix_sha256", args.matrix), ("matrix_independent_sha256", args.matrix_independent)):
        if final[key] != sha256(path):
            raise ValueError(f"evidence hash mismatch: {key}")
    _, _, baseline = slides(args.baseline)
    _, rns, readback = slides(args.readback)
    responses = {96: json.loads(args.response96.read_text()), 97: json.loads(args.response97.read_text()), 98: json.loads(args.response98.read_text())}
    candidates = {96: ET.parse(args.candidate96).getroot(), 97: ET.parse(args.candidate97).getroot(), 98: ET.parse(args.candidate98).getroot()}
    checks = []
    def check(name, condition, evidence):
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})
    check("baseline_95", len(baseline) == 95, len(baseline))
    check("readback_98", len(readback) == 98, len(readback))
    check("first_95_ids_unchanged", [s.attrib.get("id") for s in baseline] == [s.attrib.get("id") for s in readback[:95]], "ordered IDs")
    changed = [i + 1 for i in range(95) if canonical(baseline[i]) != canonical(readback[i])]
    check("first_95_semantic_xml_unchanged", not changed, changed)
    new_ids = [readback[i].attrib.get("id") for i in (95, 96, 97)]
    check("new_page_ids_present_distinct", all(new_ids) and len(set(new_ids)) == 3 and not set(new_ids) & {s.attrib.get("id") for s in baseline}, new_ids)
    for offset, page in enumerate((96, 97, 98)):
        check(f"slide{page}_candidate_semantics", canonical(candidates[page]) == canonical(readback[95 + offset]), sha256(Path(getattr(args, f"candidate{page}"))))
        notes = readback[95 + offset].findall(f".//{{{rns}}}note/{{{rns}}}content/{{{rns}}}p")
        check(f"slide{page}_four_note_paragraphs", len(notes) == 4, len(notes))
        out_of_bounds = []
        for node in readback[95 + offset].iter():
            if all(key in node.attrib for key in ("topLeftX", "topLeftY", "width", "height")):
                x, y, w, h = (float(node.attrib[key]) for key in ("topLeftX", "topLeftY", "width", "height"))
                if x < 0 or y < 0 or x + w > 960 or y + h > 540:
                    out_of_bounds.append(node.attrib)
        check(f"slide{page}_canvas_bounds", not out_of_bounds, out_of_bounds)
        response = responses[page]
        check(f"add_slide{page}_ok", response.get("ok") is True, response.get("ok"))
        check(f"add_slide{page}_id_matches", response.get("data", {}).get("slide_id") == new_ids[offset], response.get("data", {}).get("slide_id"))
    texts = {page: "".join(readback[95 + offset].itertext()) for offset, page in enumerate((96, 97, 98))}
    record_pairs = sum(r["unique_output_sequences"] for r in ensemble["records"])
    check("slide96_run_count", str(ensemble["run_count"]) in texts[96] and "198/198" in texts[96], ensemble["run_count"])
    check("slide96_unique_pairs", str(record_pairs) in texts[96], record_pairs)
    check("slide96_generation_seconds", f"{ensemble['total_generation_elapsed_s']:.3f} s" in texts[96], ensemble["total_generation_elapsed_s"])
    check("slide96_efe_delta", f"max |Δ| {ensemble_ind['max_efe_abs_delta_from_rounded_official']:.6g}" in texts[96], ensemble_ind["max_efe_abs_delta_from_rounded_official"])
    check("slide96_recovery_disclosure", "v1 pf() sentinel failure preserved" in texts[96] and "25 processes / 209 runs across attempts" in texts[96] and "MFE-rescaled ViennaRNA" in texts[96], "preserved failure and frozen recovery")
    check("slide96_finalization", f"{final['checks_passed']}/{final['checks_total']} PASS" in texts[96], f"{final['checks_passed']}/{final['checks_total']}")
    for name, item in matrix["method_summary"].items():
        for value in (str(item["total_actual_outputs"]), f"{item['mean_hypervolume_normalized']:.6f}", f"{item['mean_ned']:.6f}"):
            check(f"slide97_summary:{name}:{value}", value in texts[97], value)
    for key, item in matrix["primary_comparisons"].items():
        target = texts[97] if item["metric"] == "hypervolume_normalized" else texts[98]
        for value in (fmt_signed(item["mean_effect"]), f"[{fmt_signed(item['ci95'][0])}, {fmt_signed(item['ci95'][1])}]", f"{item['holm_p_twelve_primary']:.4g}"):
            check(f"comparison:{key}:{value}", value in target, value)
    costs = matrix["generation_cost_descriptive_not_time_matched"]
    check("slide98_lineardesign_cost", f"{costs['lineardesign_lambda11']['total_seconds']:.3f} s" in texts[98], costs["lineardesign_lambda11"]["total_seconds"])
    check("slide98_ensemble_cost", f"{costs['ensembledesign_11run']['total_seconds']:.3f} s" in texts[98], costs["ensembledesign_11run"]["total_seconds"])
    check("slide98_scorer_cost", f"{matrix['reanalysis_elapsed_s_not_generation_cost']:.3f} s" in texts[98], matrix["reanalysis_elapsed_s_not_generation_cost"])
    check("scientific_boundaries", "不等于 SOTA" in texts[97] and "dense AUC" in texts[96] and "time-matched" in texts[98] and "功能 OOD" in texts[97], "explicit limitations")
    check("matrix_independent_badge", f"{matrix_ind['checks_passed']}/{matrix_ind['checks_total']}" in texts[97] and f"{matrix_ind['checks_passed']}/{matrix_ind['checks_total']}" in texts[98], matrix_ind["checks_passed"])
    report = {"schema": "a8-rk13-ppt-readback-verification-v1", "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
              "status": "PASS" if all(item["pass"] for item in checks) else "FAIL", "checks_passed": sum(item["pass"] for item in checks), "checks_total": len(checks),
              "baseline_slide_count": len(baseline), "readback_slide_count": len(readback), "new_slide_ids": new_ids,
              "slide96_add_revision": responses[96].get("data", {}).get("revision_id"), "slide97_add_revision": responses[97].get("data", {}).get("revision_id"), "slide98_add_revision": responses[98].get("data", {}).get("revision_id"),
              "baseline_sha256": sha256(args.baseline), "readback_sha256": sha256(args.readback), "candidate96_sha256": sha256(args.candidate96), "candidate97_sha256": sha256(args.candidate97), "candidate98_sha256": sha256(args.candidate98),
              "finalization_sha256": sha256(args.finalization), "ensemble_sha256": sha256(args.ensemble), "matrix_sha256": sha256(args.matrix), "changed_baseline_pages": changed, "checks": checks,
              "scientific_boundary": "PPT readback verifies presentation fidelity and numeric consistency only; scientific acceptance comes from the frozen RK-13 finalization and independent verifiers."}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
