#!/usr/bin/env python3
"""Validate the pure-RCS slide candidate against frozen evidence before writing."""
from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def node_text(node: ET.Element) -> str:
    return "".join(node.itertext()).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=".")
    parser.add_argument("--candidate", default="pure_rcs_slide_candidate_v01.xml")
    parser.add_argument("--output", default="pure_rcs_slide_candidate_verification_v01.json")
    args = parser.parse_args()
    base = Path(args.base)
    candidate_path = base / args.candidate
    candidate_bytes = candidate_path.read_bytes()
    root = ET.fromstring(candidate_bytes)
    production = json.loads((base / "mage_pure_external_nested_cv_v1.json").read_text())
    independent = json.loads((base / "mage_pure_external_nested_cv_independent_v1.json").read_text())
    finalization = json.loads((base / "mage_pure_external_nested_cv_finalization_v1.json").read_text())
    science_postpush = json.loads((base / "postpush_independent.json").read_text())
    paper_postpush = json.loads((base / "paper_postpush_verification_v32.json").read_text())
    old = json.loads((base / "mage_development_nested_cv_v2.json").read_text())
    before_response = json.loads((base / "pure_rcs_before_response_v01.json").read_text())
    before_root = ET.parse(base / "pure_rcs_before_v01.xml").getroot()
    before_slides = [el for el in before_root.iter() if local(el.tag) == "slide"]
    checks = []

    def check(name: str, condition: bool, detail: object = None) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("candidate_exists_nonempty", len(candidate_bytes) > 1000, len(candidate_bytes))
    check("candidate_root_slide", local(root.tag) == "slide")
    check("candidate_single_slide", sum(local(el.tag) == "slide" for el in root.iter()) == 1)
    check("candidate_no_server_ids", all(el.get("id") is None for el in root.iter()))
    check("candidate_no_external_images", not any(local(el.tag) == "img" for el in root.iter()))
    check("candidate_no_embed_or_undefined", not any(local(el.tag) in {"embed", "undefined"} for el in root.iter()))
    check("candidate_no_emoji", all(ord(ch) <= 0xFFFF for ch in candidate_bytes.decode()))
    check("baseline_read_ok", before_response["ok"] is True)
    check("baseline_revision_69", before_response["data"]["revision_id"] == 69)
    check("baseline_scope_presentation", before_response["data"]["scope"] == "presentation")
    check("baseline_canvas_960_540", before_root.get("width") == "960" and before_root.get("height") == "540")
    check("baseline_107_pages", len(before_slides) == 107, len(before_slides))
    check("baseline_last_rk08", before_slides[-1].get("id") == "pZZ")
    baseline_text = " ".join(node_text(el) for el in before_slides)
    check("baseline_has_no_pure_slide", "Pure external RCS cannot replace intrinsic features" not in baseline_text)

    data = next(el for el in root if local(el.tag) == "data")
    note = next(el for el in root if local(el.tag) == "note")
    visible = " ".join(node_text(el) for el in data.iter() if local(el.tag) == "p")
    note_text = " ".join(node_text(el) for el in note.iter() if local(el.tag) == "p")
    note_paragraphs = [el for el in note.iter() if local(el.tag) == "p"]
    shapes = [el for el in data if local(el.tag) == "shape"]
    tables = [el for el in data if local(el.tag) == "table"]
    check("twenty_nine_native_text_and_background_shapes", len(shapes) == 29, len(shapes))
    check("one_native_table", len(tables) == 1)
    check("four_note_paragraphs", len(note_paragraphs) == 4, len(note_paragraphs))
    for i, el in enumerate(shapes + tables):
        x, y = float(el.get("topLeftX")), float(el.get("topLeftY"))
        w, h = float(el.get("width")), float(el.get("height"))
        check(f"element_{i}_inside_canvas", x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= 960 and y + h <= 540, [x, y, w, h])
    for i, content in enumerate(el for el in root.iter() if local(el.tag) == "content" and el.get("fontSize") is not None):
        check(f"content_{i}_explicit_font", float(content.get("fontSize")) >= 9, content.get("fontSize"))
        check(f"content_{i}_approved_font_family", content.get("fontFamily") in {"Aptos", "思源黑体", None}, content.get("fontFamily"))
    check("main_title", "Pure external RCS cannot replace intrinsic features" in visible)
    check("page_role", "RK03 · PURE RCS" in visible)
    check("page_number_108", "A8-RK · 108" in visible)
    check("protocol_subtitle", "131 reused train+dev constructs" in visible and "5 outer / 4 inner folds" in visible and "3 seeds" in visible and "6 alphas" in visible and "375 fits" in visible and "20,000 paired resamples" in visible and "test 33 excluded" in visible)
    check("development_n_matches", production["development_n"] == 131)
    check("fit_count_matches", sum(production["fit_counts"].values()) == 375 and independent["independent_fit_count"] == 375)
    check("primary_seed_matches", production["primary_seed"] == "40261119")
    check("pure_spearman_visible", "−0.132" in visible and "SPEARMAN" in visible)
    check("pure_rmse_visible", "0.049298" in visible and "RMSE" in visible)
    check("independent_visible", "174 / 174" in visible and independent["checks_passed"] == 174 and independent["checks_total"] == 174 and independent["checks_failed"] == 0)
    check("independent_delta_zero_visible", "MAX DELTA 0" in visible and independent["max_numeric_delta"] == 0.0)
    check("finalization_visible", "43 / 43" in visible and finalization["checks_passed"] == 43 and finalization["checks_total"] == 43 and finalization["checks_failed"] == 0)
    check("postpush_science_visible", "POSTPUSH 174/174" in visible and science_postpush["overall_pass"] is True and science_postpush["checks_passed"] == 174 and science_postpush["checks_total"] == 174 and science_postpush["max_numeric_delta"] == 0.0)
    check("paper_postpush_pass", paper_postpush["overall_pass"] is True and paper_postpush["checks_passed"] == 100 and paper_postpush["checks_total"] == 100)
    check("paper_source_visible", "manuscript v32 §6.28" in visible and "GitHub d5959f73" in visible)

    table = tables[0]
    rows = [el for el in table if local(el.tag) == "tr"]
    check("table_four_rows", len(rows) == 4)
    check("table_geometry", [table.get("topLeftX"), table.get("topLeftY"), table.get("width"), table.get("height")] == ["48", "222", "864", "136"])
    expected_header = ["Comparison", "Spearman delta [95% CI]", "Holm p", "RMSE delta [95% CI]", "Holm p"]
    header_cells = [el for el in rows[0] if local(el.tag) == "td"]
    check("table_header_columns", len(header_cells) == 5)
    for i, expected in enumerate(expected_header):
        check(f"table_header_{i}", node_text(header_cells[i]) == expected, node_text(header_cells[i]))

    def signed(value: float, digits: int) -> str:
        return f"{value:+.{digits}f}".replace("-", "−")

    def p_display(value: float) -> str:
        return "<0.001" if value < 0.001 else f"{value:.5f}"

    comparison_rows = [
        ("pure_external_rcs_minus_intrinsic", "pure − intrinsic"),
        ("full_mechanism_minus_pure_external_rcs", "full − pure"),
        ("rcs_only_minus_pure_external_rcs", "intrinsic+RCS − pure"),
    ]
    for row_index, (key, label) in enumerate(comparison_rows, start=1):
        values = production["primary_comparisons"][key]
        cells = [el for el in rows[row_index] if local(el.tag) == "td"]
        check(f"comparison_{key}_five_cells", len(cells) == 5)
        expected = [
            label,
            f"{signed(values['delta_spearman'], 3)} [{signed(values['delta_spearman_ci95'][0], 3)}, {signed(values['delta_spearman_ci95'][1], 3)}]",
            p_display(values["holm_p_spearman"]),
            f"{signed(values['delta_rmse'], 4)} [{signed(values['delta_rmse_ci95'][0], 4)}, {signed(values['delta_rmse_ci95'][1], 4)}]",
            p_display(values["holm_p_rmse"]),
        ]
        for col_index, expected_text in enumerate(expected):
            actual = node_text(cells[col_index])
            check(f"comparison_{key}_cell_{col_index}", actual == expected_text, {"actual": actual, "expected": expected_text})
        for field in ("delta_spearman", "delta_rmse", "holm_p_spearman", "holm_p_rmse", "delta_spearman_ci95", "delta_rmse_ci95"):
            value = values[field]
            tokens = [str(v) for v in value] if isinstance(value, list) else [str(value)]
            for token_index, token in enumerate(tokens):
                check(f"note_{key}_{field}_{token_index}", token in note_text, token)

    for arm, values in production["primary_models"].items():
        for metric in ("rmse", "mae", "spearman"):
            check(f"note_primary_{arm}_{metric}", str(values[metric]) in note_text, str(values[metric]))
    check("pure_replacement_flag_false", production["pure_external_replacement_supported_development_only"] is False)
    check("mechanism_increment_flag_false", production["mechanism_increment_pass"] is False)
    check("rk_g1_flag_false", production["rk_g1_pass"] is False)
    check("test_and_generator_flags_false", production["test_authorized"] is False and production["generator_training_authorized"] is False and production["test_predictions_generated"] is False and production["test_metrics_generated"] is False)
    check("visible_replacement_negative", "Replacement = false" in visible and "Replacement fails" in visible and "Pure is worse on both endpoints" in visible)
    check("visible_mechanism_negative", "mechanism increment = false" in visible and "Beating pure RCS is not beating intrinsic" in visible)
    check("visible_gates_negative", "RK-G1 = false" in visible and "test + generator remain unauthorized" in visible)
    check("visible_old_full_intrinsic_non_significant", "Old full−intrinsic: both CIs cross zero · both Holm p = 1." in visible)
    check("visible_sensitivity_agreement", "both sensitivity seeds agree" in visible)
    for seed, values in production["sensitivity"].items():
        pure = values["comparisons"]["pure_external_rcs_minus_intrinsic"]
        check(f"sensitivity_{seed}_adverse", pure["delta_spearman"] < 0 and pure["delta_rmse"] > 0, pure)
    old_contrast = old["primary_comparisons"]["full_mechanism_minus_intrinsic"]
    check("old_full_intrinsic_holm_one", old_contrast["holm_p_spearman"] == 1 and old_contrast["holm_p_rmse"] == 1)
    check("old_full_intrinsic_cis_cross_zero", old_contrast["delta_spearman_ci95"][0] < 0 < old_contrast["delta_spearman_ci95"][1] and old_contrast["delta_rmse_ci95"][0] < 0 < old_contrast["delta_rmse_ci95"][1])
    check("note_feature_exclusion", "no position, position interaction, codon or amino-acid identity, GC, local-MFE, or other intrinsic feature" in note_text)
    check("note_test_exclusion", "all 33 test constructs remained excluded" in note_text)
    check("note_science_commit", "b95e1244537a23c95cdda986cb60e343cfd7e4da" in note_text)
    check("note_paper_commit", "d5959f73ac4f4812d614eee6d6c04d320dff38fc" in note_text)
    check("note_final_gates", "replacement, mechanism increment, RK-G1, test authorization, and generator authorization remain false" in note_text)
    check("table_does_not_overlap_bottom_cards", 222 + 136 <= 370)
    check("bottom_cards_do_not_overlap_gate", 370 + 70 <= 455)
    check("gate_does_not_overlap_footer", 455 + 36 < 505)

    passed = sum(row["pass"] for row in checks)
    failed = len(checks) - passed
    report = {
        "schema": "a8-rk03-pure-external-slide-candidate-verification-v01",
        "status": "PASS_CANDIDATE_READY_FOR_SINGLE_APPEND" if failed == 0 else "FAIL_CANDIDATE_NOT_READY",
        "overall_pass": failed == 0,
        "checks_total": len(checks),
        "checks_passed": passed,
        "checks_failed": failed,
        "candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "baseline_xml_sha256": sha(base / "pure_rcs_before_v01.xml"),
        "baseline_revision": before_response["data"]["revision_id"],
        "baseline_slide_count": len(before_slides),
        "baseline_last_slide_id": before_slides[-1].get("id"),
        "production_sha256": sha(base / "mage_pure_external_nested_cv_v1.json"),
        "independent_sha256": sha(base / "mage_pure_external_nested_cv_independent_v1.json"),
        "finalization_sha256": sha(base / "mage_pure_external_nested_cv_finalization_v1.json"),
        "science_postpush_sha256": sha(base / "postpush_independent.json"),
        "paper_postpush_sha256": sha(base / "paper_postpush_verification_v32.json"),
        "write_authorized_by_this_report_only_if_single_append": failed == 0,
        "rk_g1_pass": False,
        "generator_training_authorized": False,
        "checks": checks,
    }
    output = base / args.output
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: report[k] for k in ("status", "checks_total", "checks_passed", "checks_failed", "candidate_sha256")}, indent=2))
    if failed:
        for row in checks:
            if not row["pass"]:
                print(json.dumps(row, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
