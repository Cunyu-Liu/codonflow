#!/usr/bin/env python3
"""Independent post-write semantic audit for the single pure-RCS slide append."""
from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def slides_of(root: ET.Element) -> list[ET.Element]:
    return [el for el in root.iter() if local(el.tag) == "slide"]


def child(node: ET.Element, name: str) -> ET.Element:
    return next(el for el in node if local(el.tag) == name)


def paragraphs(node: ET.Element, container: str) -> list[str]:
    parent = child(node, container)
    return ["".join(el.itertext()).strip() for el in parent.iter() if local(el.tag) == "p"]


def signature(el: ET.Element) -> tuple:
    return (local(el.tag), tuple(sorted(el.attrib.items())), (el.text or "").strip(), tuple(signature(c) for c in el))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=".")
    parser.add_argument("--output", default="pure_rcs_slide_postwrite_verification_v01.json")
    args = parser.parse_args()
    base = Path(args.base)
    before_bytes = (base / "pure_rcs_before_v02.xml").read_bytes()
    after_bytes = (base / "pure_rcs_after_v01.xml").read_bytes()
    before = ET.fromstring(before_bytes)
    after = ET.fromstring(after_bytes)
    old_slides = slides_of(before)
    new_slides = slides_of(after)
    candidate_path = base / "pure_rcs_slide_candidate_v01.xml"
    candidate_bytes = candidate_path.read_bytes()
    candidate = ET.fromstring(candidate_bytes)
    candidate_report = json.loads((base / "pure_rcs_slide_candidate_verification_v01.json").read_text())
    before_response = json.loads((base / "pure_rcs_before_response_v02.json").read_text())
    after_response = json.loads((base / "pure_rcs_after_response_v01.json").read_text())
    native_response = json.loads((base / "pure_rcs_native_add_response_v01.json").read_text())
    native_request = json.loads((base / "pure_rcs_native_add_request_v01.json").read_text())
    production = json.loads((base / "mage_pure_external_nested_cv_v1.json").read_text())
    independent = json.loads((base / "mage_pure_external_nested_cv_independent_v1.json").read_text())
    finalization = json.loads((base / "mage_pure_external_nested_cv_finalization_v1.json").read_text())
    science_postpush = json.loads((base / "postpush_independent.json").read_text())
    paper_postpush = json.loads((base / "paper_postpush_verification_v32.json").read_text())
    checks = []

    def check(name: str, condition: bool, detail: object = None) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("before_read_ok", before_response["ok"] is True and before_response["data"]["revision_id"] == 69)
    check("after_read_ok", after_response["ok"] is True and after_response["data"]["revision_id"] == 70)
    check("after_scope_presentation", after_response["data"]["scope"] == "presentation")
    check("native_create_ok", native_response["ok"] is True)
    check("native_create_revision_70", native_response["data"]["revision_id"] == 70)
    check("native_create_slide_pZS", native_response["data"]["slide_id"] == "pZS")
    check("native_idempotency_key_recorded", native_request["params"]["idempotency_key"] == "codonflow-pure-rcs-20261120-v01")
    check("candidate_report_pass", candidate_report["overall_pass"] is True and candidate_report["checks_passed"] == 227 and candidate_report["checks_failed"] == 0)
    check("candidate_hash_matches_prereport", sha_bytes(candidate_bytes) == candidate_report["candidate_sha256"])
    check("baseline_v01_v02_identical", sha(base / "pure_rcs_before_v01.xml") == sha_bytes(before_bytes))
    check("before_107_pages", len(old_slides) == 107)
    check("after_108_pages", len(new_slides) == 108)
    check("old_page_order_preserved", [s.get("id") for s in new_slides[:107]] == [s.get("id") for s in old_slides])
    check("new_page_is_last_pZS", new_slides[-1].get("id") == "pZS")
    check("previous_last_remains_pZZ", new_slides[-2].get("id") == "pZZ")
    check("canvas_unchanged", before.get("width") == after.get("width") == "960" and before.get("height") == after.get("height") == "540")
    old_non_slides = [signature(el) for el in before if local(el.tag) != "slide"]
    new_non_slides = [signature(el) for el in after if local(el.tag) != "slide"]
    check("presentation_non_slide_content_unchanged", old_non_slides == new_non_slides)
    for i, (old_slide, new_slide) in enumerate(zip(old_slides, new_slides[:107]), start=1):
        check(f"old_page_{i}_id_unchanged", old_slide.get("id") == new_slide.get("id"))
        check(f"old_page_{i}_full_semantics_unchanged", signature(old_slide) == signature(new_slide))
        check(f"old_page_{i}_visible_text_unchanged", paragraphs(old_slide, "data") == paragraphs(new_slide, "data"))
        old_notes = paragraphs(old_slide, "note") if any(local(el.tag) == "note" for el in old_slide) else []
        new_notes = paragraphs(new_slide, "note") if any(local(el.tag) == "note" for el in new_slide) else []
        check(f"old_page_{i}_notes_unchanged", old_notes == new_notes)

    pure_hits = [i + 1 for i, slide in enumerate(new_slides) if "Pure external RCS cannot replace intrinsic features" in " ".join(paragraphs(slide, "data"))]
    check("exactly_one_pure_page_at_108", pure_hits == [108], pure_hits)
    new_page = new_slides[-1]
    check("new_visible_paragraphs_equal_candidate", paragraphs(new_page, "data") == paragraphs(candidate, "data"))
    check("new_notes_equal_candidate", paragraphs(new_page, "note") == paragraphs(candidate, "note"))
    new_data = child(new_page, "data")
    candidate_data = child(candidate, "data")
    new_shapes = [el for el in new_data if local(el.tag) == "shape"]
    new_tables = [el for el in new_data if local(el.tag) == "table"]
    check("new_29_shapes", len(new_shapes) == 29, len(new_shapes))
    check("new_one_table", len(new_tables) == 1)
    check("new_no_external_media", not any(local(el.tag) in {"img", "embed", "undefined"} for el in new_page.iter()))
    for i, el in enumerate(new_shapes + new_tables):
        x, y, w, h = (float(el.get(k)) for k in ("topLeftX", "topLeftY", "width", "height"))
        check(f"new_element_{i}_inside_canvas", x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= 960 and y + h <= 540)
    candidate_table = next(el for el in candidate_data if local(el.tag) == "table")
    new_table = new_tables[0]
    candidate_cells = [["".join(p.itertext()).strip() for p in td.iter() if local(p.tag) == "p"] for td in new_table.iter() if local(td.tag) == "td"]
    expected_cells = [["".join(p.itertext()).strip() for p in td.iter() if local(p.tag) == "p"] for td in candidate_table.iter() if local(td.tag) == "td"]
    check("new_table_20_cells", len(candidate_cells) == 20)
    check("new_table_text_equals_candidate", candidate_cells == expected_cells)

    def signed(value: float, digits: int) -> str:
        return f"{value:+.{digits}f}".replace("-", "−")

    def p_display(value: float) -> str:
        return "<0.001" if value < 0.001 else f"{value:.5f}"

    row_map = [
        ("pure_external_rcs_minus_intrinsic", "pure − intrinsic"),
        ("full_mechanism_minus_pure_external_rcs", "full − pure"),
        ("rcs_only_minus_pure_external_rcs", "intrinsic+RCS − pure"),
    ]
    rows = [el for el in new_table if local(el.tag) == "tr"]
    for row_index, (key, label) in enumerate(row_map, start=1):
        values = production["primary_comparisons"][key]
        cells = [el for el in rows[row_index] if local(el.tag) == "td"]
        actual = ["".join(td.itertext()).strip() for td in cells]
        expected = [
            label,
            f"{signed(values['delta_spearman'], 3)} [{signed(values['delta_spearman_ci95'][0], 3)}, {signed(values['delta_spearman_ci95'][1], 3)}]",
            p_display(values["holm_p_spearman"]),
            f"{signed(values['delta_rmse'], 4)} [{signed(values['delta_rmse_ci95'][0], 4)}, {signed(values['delta_rmse_ci95'][1], 4)}]",
            p_display(values["holm_p_rmse"]),
        ]
        for col, (a, e) in enumerate(zip(actual, expected)):
            check(f"new_table_{key}_{col}_matches_evidence", a == e, {"actual": a, "expected": e})

    note_text = " ".join(paragraphs(new_page, "note"))
    for arm, values in production["primary_models"].items():
        for metric in ("rmse", "mae", "spearman"):
            check(f"new_note_primary_{arm}_{metric}", str(values[metric]) in note_text)
    for key, _ in row_map:
        values = production["primary_comparisons"][key]
        for field in ("delta_spearman", "delta_rmse", "holm_p_spearman", "holm_p_rmse", "delta_spearman_ci95", "delta_rmse_ci95"):
            value = values[field]
            for j, token in enumerate([str(v) for v in value] if isinstance(value, list) else [str(value)]):
                check(f"new_note_{key}_{field}_{j}", token in note_text)
    check("science_independent_still_pass", independent["overall_pass"] is True and independent["checks_passed"] == 174 and independent["max_numeric_delta"] == 0.0)
    check("science_finalization_still_pass", finalization["overall_pass"] is True and finalization["checks_passed"] == 43)
    check("science_postpush_still_pass", science_postpush["overall_pass"] is True and science_postpush["checks_passed"] == 174 and science_postpush["max_numeric_delta"] == 0.0)
    check("paper_postpush_still_pass", paper_postpush["overall_pass"] is True and paper_postpush["checks_passed"] == 100)
    for name, key in [
        ("mage_pure_external_nested_cv_v1.json", "production_sha256"),
        ("mage_pure_external_nested_cv_independent_v1.json", "independent_sha256"),
        ("mage_pure_external_nested_cv_finalization_v1.json", "finalization_sha256"),
        ("postpush_independent.json", "science_postpush_sha256"),
        ("paper_postpush_verification_v32.json", "paper_postpush_sha256"),
    ]:
        check(f"evidence_hash_stable_{name}", sha(base / name) == candidate_report[key])
    for attempt in ("v01", "v02"):
        error = json.loads((base / f"pure_rcs_add_error_{attempt}.json").read_text())
        state = json.loads((base / f"pure_rcs_timeout_readback_state_{attempt}.json").read_text())
        check(f"shortcut_{attempt}_timeout_retained", error["ok"] is False and error["error"]["subtype"] == "timeout")
        check(f"shortcut_{attempt}_confirmed_not_landed", state["slide_count"] == 107 and state["pure_page_hits"] == [] and state["last_slide_id"] == "pZZ")
    visible = " ".join(paragraphs(new_page, "data"))
    check("new_replacement_false", "Replacement = false" in visible and production["pure_external_replacement_supported_development_only"] is False)
    check("new_mechanism_false", "mechanism increment = false" in visible and production["mechanism_increment_pass"] is False)
    check("new_rk_g1_false", "RK-G1 = false" in visible and production["rk_g1_pass"] is False)
    check("new_test_generator_unauthorized", "test + generator remain unauthorized" in visible and production["test_authorized"] is False and production["generator_training_authorized"] is False)
    check("new_old_full_intrinsic_caveat", "Old full−intrinsic: both CIs cross zero · both Holm p = 1." in visible)
    check("new_source_manuscript_v32", "manuscript v32 §6.28" in visible and "GitHub d5959f73" in visible)

    passed = sum(row["pass"] for row in checks)
    failed = len(checks) - passed
    report = {
        "schema": "a8-rk03-pure-external-slide-postwrite-verification-v01",
        "status": "PASS_POSTWRITE_SEMANTIC_PENDING_VISUAL" if failed == 0 else "FAIL_POSTWRITE_SEMANTIC",
        "overall_pass": failed == 0,
        "checks_total": len(checks),
        "checks_passed": passed,
        "checks_failed": failed,
        "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "before_revision": 69,
        "after_revision": after_response["data"]["revision_id"],
        "before_slide_count": len(old_slides),
        "after_slide_count": len(new_slides),
        "new_slide_id": new_page.get("id"),
        "new_slide_number": 108,
        "old_pages_semantically_unchanged": 107,
        "candidate_sha256": sha_bytes(candidate_bytes),
        "before_xml_sha256": sha_bytes(before_bytes),
        "after_xml_sha256": sha_bytes(after_bytes),
        "native_response_sha256": sha(base / "pure_rcs_native_add_response_v01.json"),
        "native_request_sha256": sha(base / "pure_rcs_native_add_request_v01.json"),
        "production_sha256": sha(base / "mage_pure_external_nested_cv_v1.json"),
        "independent_sha256": sha(base / "mage_pure_external_nested_cv_independent_v1.json"),
        "finalization_sha256": sha(base / "mage_pure_external_nested_cv_finalization_v1.json"),
        "science_postpush_sha256": sha(base / "postpush_independent.json"),
        "paper_postpush_sha256": sha(base / "paper_postpush_verification_v32.json"),
        "idempotency_key": native_request["params"]["idempotency_key"],
        "rk_g1_pass": False,
        "generator_training_authorized": False,
        "checks": checks,
    }
    output = base / args.output
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: report[k] for k in ("status", "checks_total", "checks_passed", "checks_failed", "after_slide_count", "new_slide_id", "after_revision")}, indent=2))
    if failed:
        for row in checks:
            if not row["pass"]:
                print(json.dumps(row, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
