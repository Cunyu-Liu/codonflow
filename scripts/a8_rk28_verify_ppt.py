#!/usr/bin/env python3
"""Evidence-bound candidate and online verification for the single RK28 slide."""
from pathlib import Path
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET

SCIENCE_COMMIT = "71d27dd7610559c2781849c2be7b2a26933c3d0e"
CLOSEOUT_COMMIT = "868cdb1d47d71c1a266d783628e047d41ba007e0"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local(tag):
    return tag.rsplit("}", 1)[-1]


def children(element, name):
    return [child for child in element.iter() if local(child.tag) == name]


def direct(element, name):
    return next((child for child in list(element) if local(child.tag) == name), None)


def paragraph_texts(element):
    if element is None:
        return []
    return ["".join(p.itertext()).strip() for p in children(element, "p") if "".join(p.itertext()).strip()]


def visible_text(slide):
    return paragraph_texts(direct(slide, "data"))


def note_text(slide):
    return paragraph_texts(direct(slide, "note"))


def fmt(value, digits=5):
    return f"{value:.{digits}f}".replace("-", "−")


def geometry(slide):
    records = []
    for element in children(direct(slide, "data"), "shape") + children(direct(slide, "data"), "table"):
        records.append((local(element.tag), element.attrib.get("type"), element.attrib.get("topLeftX"), element.attrib.get("topLeftY"), element.attrib.get("width"), element.attrib.get("height")))
    return records


def semantic(element):
    text = element.text if element.text and element.text.strip() else ""
    return (local(element.tag), tuple(sorted((k, v) for k, v in element.attrib.items() if k != "id")), text, tuple(semantic(child) for child in list(element)))


def table_matrix(slide):
    table = children(direct(slide, "data"), "table")[0]
    return [["".join(td.itertext()).strip() for td in list(row) if local(td.tag) == "td"] for row in list(table) if local(row.tag) == "tr"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["candidate", "online"], required=True)
    parser.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-xml", type=Path)
    parser.add_argument("--online-xml", type=Path)
    parser.add_argument("--add-response", type=Path)
    args = parser.parse_args()
    audit = args.repo / "audits/20261121/RK28"
    result_path = audit / "rk28_sequence_cluster_ood_result_v1.json"
    independent_path = audit / "rk28_sequence_cluster_ood_independent_v1.json"
    closeout_path = audit / "rk28_closeout_verification_v1.json"
    result = json.loads(result_path.read_text())
    independent = json.loads(independent_path.read_text())
    closeout = json.loads(closeout_path.read_text())
    candidate = ET.parse(args.candidate).getroot()
    checks = []

    def check(name, condition, details=None):
        checks.append({"name": name, "pass": bool(condition), "details": details})

    check("candidate_root_slide", local(candidate.tag) == "slide", candidate.tag)
    check("candidate_namespace", candidate.tag.startswith("{https://www.larkoffice.com/sml/2.0}"), candidate.tag)
    check("candidate_has_no_manual_ids", all("id" not in element.attrib for element in candidate.iter()), "server assigns IDs")
    data = direct(candidate, "data")
    check("candidate_single_table", len(children(data, "table")) == 1, len(children(data, "table")))
    check("candidate_five_note_paragraphs", len(note_text(candidate)) == 5, len(note_text(candidate)))
    check("candidate_no_external_images", not children(data, "img"), "native text/shapes/table only")
    for index, element in enumerate(children(data, "shape") + children(data, "table")):
        try:
            x, y = float(element.attrib["topLeftX"]), float(element.attrib["topLeftY"])
            w, h = float(element.attrib["width"]), float(element.attrib["height"])
            valid = x >= 0 and y >= 0 and x + w <= 960 and y + h <= 540 and w > 0 and h > 0
        except (KeyError, ValueError):
            valid = False
        check(f"canvas_bounds_{index}", valid, element.attrib)
    for index, content in enumerate(children(candidate, "content")):
        if "fontFamily" in content.attrib:
            check(f"inter_font_{index}", content.attrib["fontFamily"] == "Inter", content.attrib["fontFamily"])
        if "fontSize" in content.attrib:
            check(f"explicit_font_size_{index}", float(content.attrib["fontSize"]) >= 8.0, content.attrib["fontSize"])
        if "lineSpacing" in content.attrib:
            check(f"line_spacing_format_{index}", content.attrib["lineSpacing"].startswith(("multiple:", "fixed:")), content.attrib["lineSpacing"])

    text = "\n".join(visible_text(candidate))
    notes = "\n".join(note_text(candidate))
    required = [
        "RK28 · MORDSTEIN HEK293 · OBSERVED-R1 SEQUENCE-CLUSTER OOD",
        "Observed-R1 structure does not transport to HEK293 expression",
        "152 fixed-GFP variants · 74 clusters · 10 seeds / 5 folds",
        "20,000 bootstrap + 20,000 cluster-swap permutations",
        "4/4 endpoints FAIL; no positive transport increment.",
        "Independent 54/54 · closeout 101/101 · 300 real CPU fits.",
        "300 nt observed R1; no complete CDS, measured MFE or protein OOD.",
        "No velocity/decay; RK-G1 false; generator unauthorized.",
        "CROSS-STUDY STRUCTURE TRANSPORT NOT SUPPORTED · 4/4 ENDPOINTS FAIL · independent 54/54 · closeout 101/101",
        f"science {SCIENCE_COMMIT[:8]}", f"closeout {CLOSEOUT_COMMIT[:8]}", "120 · RK28",
    ]
    for token in required:
        check(f"visible_{token}", token in text, token)
    for test in result["primary_tests"]:
        effect = fmt(test["observed_effect"])
        ci = f"95% CI [{fmt(test['ci95'][0])}, {fmt(test['ci95'][1])}]"
        inference = f"Holm p {test['p_holm']:.6f} · {test['positive_seeds']}/10 seeds"
        check(f"{test['test']}_effect_card", effect in text, effect)
        check(f"{test['test']}_ci_card", ci in text, ci)
        check(f"{test['test']}_inference_card", inference in text, inference)
        check(f"{test['test']}_negative_and_fail", test["observed_effect"] < 0 and test["pass"] is False, test["observed_effect"])
        check(f"{test['test']}_full_effect_in_notes", str(abs(test["observed_effect"])) in notes, test["observed_effect"])
        check(f"{test['test']}_full_holm_in_notes", str(test["p_holm"]) in notes, test["p_holm"])
        for bound in test["ci95"]:
            check(f"{test['test']}_full_ci_{bound}", str(abs(bound)) in notes, bound)
    performance = {row["arm"]: row for row in result["primary_absolute_performance"]}
    matrix = table_matrix(candidate)
    check("table_7_by_4", len(matrix) == 7 and all(len(row) == 4 for row in matrix), {"rows": len(matrix)})
    expected_rows = ["ridge_simple", "ridge_structure", "ridge_mfe_only", "histgb_simple", "histgb_structure", "histgb_mfe_only"]
    for row_index, arm in enumerate(expected_rows, start=1):
        metric = performance[arm]
        check(f"table_{arm}_spearman", matrix[row_index][2] == f"{metric['spearman']:.5f}", matrix[row_index])
        check(f"table_{arm}_mse", matrix[row_index][3] == f"{metric['mse']:.5f}", matrix[row_index])
    check("independent_54", independent["status"] == "PASS" and independent["n_passed"] == 54 and independent["n_checks"] == 54, independent["n_passed"])
    check("closeout_101", closeout["status"] == "PASS" and closeout["n_passed"] == 101 and closeout["n_checks"] == 101, closeout["n_passed"])
    check("science_commit_binding", closeout["science_commit"] == SCIENCE_COMMIT, closeout["science_commit"])
    check("result_hash_binding", closeout["result_sha256"] == sha256(result_path), closeout["result_sha256"])
    check("independent_hash_binding", closeout["independent_report_sha256"] == sha256(independent_path), closeout["independent_report_sha256"])
    check("result_hash_in_notes", sha256(result_path) in notes, sha256(result_path))
    check("independent_hash_in_notes", sha256(independent_path) in notes, sha256(independent_path))
    check("science_commit_in_notes", SCIENCE_COMMIT in notes, SCIENCE_COMMIT)
    check("closeout_commit_in_notes", CLOSEOUT_COMMIT in notes, CLOSEOUT_COMMIT)
    check("negative_conclusion", result["scientific_conclusion"] == "FIXED_GFP_HEK293_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED" and result["sequence_cluster_ood_structure_increment_pass"] is False, result["scientific_conclusion"])
    check("sample_and_training_record", result["n_variants"] == 152 and result["n_sequence_clusters"] == 74 and result["total_model_fits"] == 300 and len(result["seeds"]) == 10 and result["folds_per_seed"] == 5, {"variants": 152, "clusters": 74, "fits": 300})
    flags = result["scientific_flags"]
    check("scientific_boundaries", not flags["rk_g1_complete"] and not flags["generator_training_authorized"] and not flags["functional_untouched_read"] and not flags["complete_cds_observed"] and not flags["measured_structure"] and not flags["protein_ood"] and not flags["velocity_or_decay_measured"], flags)
    for token in ["not an independent untouched confirmation", "not an independent untouched confirmation or a protein-OOD experiment", "previously been used in RK02 development", "does not observe the complete CDS", "use measured structure", "measure velocity or decay", "authorize generator training or complete RK-G1"]:
        check(f"note_boundary_{token}", token in notes, token)

    online_revision = None
    new_slide_id = None
    old_pages_preserved = None
    if args.mode == "online":
        if not all([args.source_xml, args.online_xml, args.add_response]):
            raise ValueError("online mode requires source XML, online XML and add response")
        source = ET.parse(args.source_xml).getroot()
        online = ET.parse(args.online_xml).getroot()
        source_slides = [child for child in list(source) if local(child.tag) == "slide"]
        online_slides = [child for child in list(online) if local(child.tag) == "slide"]
        add = json.loads(args.add_response.read_text())
        new_slide_id = add["data"]["slide_id"]
        check("add_response_ok", add["ok"] is True and bool(new_slide_id), add.get("data"))
        check("source_119_pages", len(source_slides) == 119, len(source_slides))
        check("online_120_pages", len(online_slides) == 120, len(online_slides))
        check("one_new_rk28_page", sum("RK28" in "\n".join(visible_text(slide)) for slide in online_slides) == 1, "exactly one")
        check("new_page_at_end", online_slides[-1].attrib.get("id") == new_slide_id, new_slide_id)
        check("canvas_960_540", source.attrib.get("width") == online.attrib.get("width") == "960" and source.attrib.get("height") == online.attrib.get("height") == "540", online.attrib)
        old_pages_preserved = True
        for index, (before, after) in enumerate(zip(source_slides, online_slides[:119]), start=1):
            same_id = before.attrib.get("id") == after.attrib.get("id")
            same_semantic = semantic(before) == semantic(after)
            before_ids = [element.attrib["id"] for element in before.iter() if "id" in element.attrib]
            after_ids = [element.attrib["id"] for element in after.iter() if "id" in element.attrib]
            same_element_ids = before_ids == after_ids
            check(f"old_page_{index}_id", same_id, before.attrib.get("id"))
            check(f"old_page_{index}_semantic", same_semantic, "all visible content, notes, geometry and styles")
            check(f"old_page_{index}_element_ids", same_element_ids, len(before_ids))
            old_pages_preserved = old_pages_preserved and same_id and same_semantic and same_element_ids
        written = online_slides[-1]
        check("online_visible_matches_candidate", visible_text(written) == visible_text(candidate), new_slide_id)
        check("online_notes_match_candidate", note_text(written) == note_text(candidate), new_slide_id)
        check("online_table_matches_candidate", table_matrix(written) == table_matrix(candidate), new_slide_id)
        check("online_geometry_matches_candidate", geometry(written) == geometry(candidate), new_slide_id)
        check("online_has_assigned_id", bool(written.attrib.get("id")), written.attrib.get("id"))

    passed = all(row["pass"] for row in checks)
    report = {
        "schema": f"a8-rk28-slide-{args.mode}-verification-v1", "status": "PASS" if passed else "FAIL",
        "n_checks": len(checks), "n_passed": int(sum(row["pass"] for row in checks)), "checks": checks,
        "science_commit": SCIENCE_COMMIT, "closeout_commit": CLOSEOUT_COMMIT,
        "candidate_sha256": sha256(args.candidate), "result_sha256": sha256(result_path),
        "independent_report_sha256": sha256(independent_path), "closeout_report_sha256": sha256(closeout_path),
        "new_slide_id": new_slide_id, "old_pages_preserved": old_pages_preserved,
        "rk_g1_complete": False, "generator_training_authorized": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "n_checks": len(checks), "n_passed": report["n_passed"], "failed": [row for row in checks if not row["pass"]], "new_slide_id": new_slide_id, "old_pages_preserved": old_pages_preserved}, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
