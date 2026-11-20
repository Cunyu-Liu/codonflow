#!/usr/bin/env python3
"""Verify the appended MAGE comparator slide against evidence and readback XML."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

MARKER = "RK03 · MAGE OOF COMPARATOR CLOSURE"


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path): return json.loads(Path(path).read_text())
def local(tag): return tag.rsplit("}", 1)[-1]
def text(elem): return "\n".join("".join(p.itertext()) for p in elem.iter() if local(p.tag) == "p")
def child(elem, name): return next(e for e in elem if local(e.tag) == name)


def main():
    ap = argparse.ArgumentParser()
    for name in ["candidate", "baseline-xml", "readback-xml", "readback-response", "add-response", "production", "independent", "preflight", "screenshot-response", "output"]:
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--visual-pass", required=True, choices=["true", "false"])
    ap.add_argument("--screenshot-path", required=False)
    a = ap.parse_args()
    candidate = ET.parse(a.candidate).getroot()
    baseline = ET.parse(a.baseline_xml).getroot()
    readback = ET.parse(a.readback_xml).getroot()
    response = load(a.readback_response)
    added = load(a.add_response)
    prod = load(a.production)
    ind = load(a.independent)
    preflight = load(a.preflight)
    screenshot = load(a.screenshot_response)
    checks = []
    def check(name, passed, detail=None): checks.append({"name": name, "pass": bool(passed), "detail": detail})
    old_pages = [e for e in baseline if local(e.tag) == "slide"]
    new_pages = [e for e in readback if local(e.tag) == "slide"]
    sid = added.get("data", {}).get("slide_id")
    check("add_response_ok", added.get("ok") is True and bool(sid))
    check("readback_response_ok", response.get("ok") is True)
    check("exactly_one_page_appended", len(new_pages) == len(old_pages) + 1, {"baseline": len(old_pages), "readback": len(new_pages)})
    check("all_old_slide_ids_and_order_preserved", [e.attrib.get("id") for e in new_pages[:-1]] == [e.attrib.get("id") for e in old_pages])
    check("appended_slide_id_and_position", new_pages[-1].attrib.get("id") == sid)
    check("single_marker_in_full_deck", text(readback).count(MARKER) == 1)
    page = new_pages[-1]
    check("visible_text_semantic_identity", text(child(page, "data")) == text(child(candidate, "data")))
    check("speaker_notes_semantic_identity", text(child(page, "note")) == text(child(candidate, "note")))
    check("preflight_pass_and_candidate_hash", preflight.get("status") == "PASS" and preflight.get("candidate_sha256") == sha(a.candidate))
    check("independent_binds_production", ind.get("overall_pass") is True and ind.get("production_report_sha256") == sha(a.production))
    notes = text(child(page, "note"))
    for cid, row in prod["exploratory_comparisons"].items():
        for key in ["delta_rmse", "delta_rmse_ci95", "holm_p_rmse"]:
            check(f"notes_exact_{cid}_{key}", repr(row[key]) in notes, repr(row[key]))
        if cid == "full_mechanism_minus_outer_train_mean":
            check(f"notes_exact_{cid}_permutation_p_rmse", repr(row["permutation_p_rmse"]) in notes, repr(row["permutation_p_rmse"]))
        else:
            for key in ["delta_spearman", "delta_spearman_ci95", "holm_p_spearman"]:
                check(f"notes_exact_{cid}_{key}", repr(row[key]) in notes, repr(row[key]))
    check("scientific_gate_unchanged", prod.get("scientific_gate") == "UNCHANGED_DEV_NO_GO_TEST_UNTOUCHED" and "DEV_NO_GO_TEST_UNTOUCHED 不变" in text(page))
    shots = screenshot.get("data", {}).get("screenshots", [])
    shot = next((s for s in shots if s.get("slide_id") == sid), None)
    shot_path = Path(a.screenshot_path) if a.screenshot_path else Path(shot["path"]) if shot else None
    check("real_screenshot_returned", screenshot.get("ok") is True and shot is not None and shot_path is not None and shot_path.is_file() and shot_path.stat().st_size > 0)
    check("visual_review_pass", a.visual_pass == "true" and shot is not None, "Title/cards/table/footer inspected: no clipping, overlap, or missing text" if a.visual_pass == "true" else "visual review not passed")
    report = {
        "schema": "a8-rk03-mage-oof-comparator-ppt-verification-v1",
        "overall_pass": all(c["pass"] for c in checks),
        "presentation_id": response.get("data", {}).get("xml_presentation_id"),
        "revision_id": response.get("data", {}).get("revision_id"),
        "slide_id": sid,
        "slide_number": len(new_pages),
        "candidate_sha256": sha(a.candidate),
        "readback_xml_sha256": sha(a.readback_xml),
        "production_sha256": sha(a.production),
        "independent_sha256": sha(a.independent),
        "screenshot_sha256": sha(shot_path) if shot_path is not None and shot_path.is_file() else None,
        "visual_review": "PASS_no_clipping_overlap_or_missing_text" if a.visual_pass == "true" else "FAIL",
        "check_counts": {"passed": sum(c["pass"] for c in checks), "total": len(checks)},
        "checks": checks,
    }
    Path(a.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"overall_pass": report["overall_pass"], "checks": report["check_counts"], "slide_id": sid, "slide_number": len(new_pages)}, indent=2))
    if not report["overall_pass"]: raise SystemExit(1)


if __name__ == "__main__": main()
