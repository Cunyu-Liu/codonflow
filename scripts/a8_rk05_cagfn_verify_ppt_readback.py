#!/usr/bin/env python3
"""Verify the real online CAGFN slide append against frozen baseline and scientific evidence."""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

NS = "https://www.larkoffice.com/sml/2.0"
N = "{" + NS + "}"
PRESENTATION = "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g"
TITLE = "RK-05 | CAGFN Official Bounded Smoke Verified; Scope Stays Bounded"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalized(element: ET.Element) -> bytes:
    """Remove server-assigned ids/whitespace and only two observed benign defaults."""
    e = copy.deepcopy(element)
    for node in e.iter():
        node.attrib.pop("id", None)
        node.tail = None
        if node.text is not None:
            node.text = node.text.strip()
        if node.tag == N + "col" and "span" not in node.attrib:
            node.set("span", "1")
        if node.tag == N + "line":
            for key in ("startX", "startY", "endX", "endY"):
                value = float(node.get(key))
                nearest = round(value)
                if abs(value - nearest) <= 0.001:
                    node.set(key, str(nearest))
        ordered_attributes = sorted(node.attrib.items())
        node.attrib.clear()
        node.attrib.update(ordered_attributes)
    return ET.tostring(e, encoding="utf-8")


def paragraphs(element: ET.Element, xpath: str) -> list[str]:
    return ["".join(p.itertext()) for p in element.findall(xpath)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence-dir", required=True, type=Path)
    ap.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    ev = args.evidence_dir
    repo = args.repo
    paths = {
        "baseline_xml": ev / "baseline98.xml",
        "baseline_response": ev / "baseline98-response.json",
        "candidate_xml": ev / "slide99-cagfn-v1.xml",
        "add_response": ev / "slide99-add-response.json",
        "readback_xml": ev / "readback99.xml",
        "readback_response": ev / "readback99-response.json",
        "production": repo / "audits/20261118/RK05/cagfn_official_smoke_v4.json",
        "independent": repo / "audits/20261118/RK05/cagfn_official_smoke_independent_v4.json",
        "finalization": repo / "audits/20261118/RK05/cagfn_official_smoke_finalization_v1.json",
        "paper_verification": repo / "paper/a8_rk05_cagfn_paper_verification.json",
        "paper": repo / "paper/CodonFlow_preprint_A8.md",
        "paper_audit": repo / "paper/a8_rk_paper_sync_audit.json",
    }
    baseline_response = load_json(paths["baseline_response"])
    add_response = load_json(paths["add_response"])
    readback_response = load_json(paths["readback_response"])
    production = load_json(paths["production"])
    independent = load_json(paths["independent"])
    finalization = load_json(paths["finalization"])
    paper_verification = load_json(paths["paper_verification"])
    baseline_root = ET.parse(paths["baseline_xml"]).getroot()
    readback_root = ET.parse(paths["readback_xml"]).getroot()
    candidate = ET.parse(paths["candidate_xml"]).getroot()
    baseline = baseline_root.findall(N + "slide")
    readback = readback_root.findall(N + "slide")
    new_slide = readback[-1]
    checks = []

    def check(name: str, condition: bool, details=None):
        checks.append({"name": name, "pass": bool(condition), "details": details})

    check("baseline_read_ok", baseline_response.get("ok") is True)
    check("baseline_revision_60", baseline_response.get("data", {}).get("revision_id") == 60)
    check("single_append_ok", add_response.get("ok") is True)
    check("single_append_revision_61", add_response.get("data", {}).get("revision_id") == 61)
    check("server_slide_id_pgY", add_response.get("data", {}).get("slide_id") == "pgY")
    check("readback_ok", readback_response.get("ok") is True)
    check("readback_revision_61", readback_response.get("data", {}).get("revision_id") == 61)
    check("baseline_has_98_slides", len(baseline) == 98, len(baseline))
    check("readback_has_99_slides", len(readback) == 99, len(readback))
    ids = [s.get("id") for s in readback]
    check("readback_ids_unique", len(ids) == len(set(ids)) == 99)
    check("legacy_id_sequence_unchanged", ids[:98] == [s.get("id") for s in baseline])
    check("new_slide_is_last_pgY", ids[-1] == "pgY")
    check("new_title_occurs_exactly_once", sum(TITLE in "".join(s.itertext()) for s in readback) == 1)
    for i, (before, after) in enumerate(zip(baseline, readback[:98]), start=1):
        check(f"legacy_slide_{i:02d}_semantic_xml_unchanged", normalized(before) == normalized(after), before.get("id"))
    check("new_style_semantic_match", normalized(candidate.find(N + "style")) == normalized(new_slide.find(N + "style")))
    check("new_data_semantic_match_with_server_defaults", normalized(candidate.find(N + "data")) == normalized(new_slide.find(N + "data")))
    check("new_notes_semantic_match", normalized(candidate.find(N + "note")) == normalized(new_slide.find(N + "note")))
    candidate_visible = paragraphs(candidate, ".//" + N + "data//" + N + "p")
    readback_visible = paragraphs(new_slide, ".//" + N + "data//" + N + "p")
    candidate_notes = paragraphs(candidate, ".//" + N + "note//" + N + "p")
    readback_notes = paragraphs(new_slide, ".//" + N + "note//" + N + "p")
    check("visible_paragraphs_exact", candidate_visible == readback_visible, {"count": len(readback_visible)})
    check("four_notes_exact", candidate_notes == readback_notes and len(readback_notes) == 4)
    check("candidate_data_child_count", len(list(candidate.find(N + "data"))) == len(list(new_slide.find(N + "data"))) == 23)

    text = "\n".join(readback_visible + readback_notes)
    result = finalization["scientific_result"]
    cost = finalization["cost"]
    expected_text = {
        "source_commit_prefix": "952ccf9",
        "sequence_legality": "20 unique · protein identity 20/20",
        "length": "99 nt",
        "independent_checks": "33/33",
        "finalization_checks": "22/22",
        "mean_gc": f'{result["mean_gc_percent"]:.6f}%',
        "mean_mfe": f'{result["mean_official_rnafolder_mfe_kcal_mol"]:.6f}',
        "mean_cai": f'{result["mean_cai"]:.6f}',
        "mean_ned": f'{result["mean_pairwise_normalized_edit_distance"]:.6f}',
        "training_seconds": f'{cost["training_seconds"]:.2f}',
        "sampling_seconds": f'{cost["inference_seconds"]:.2f}',
        "total_wall_clock": f'{cost["total_wall_clock_seconds"]:.6f}',
        "openreview_status": "OpenReview rejected",
        "bounded_boundary": "no convergence, full reproduction, matrix, OOD or SOTA",
        "paper_version": "A8 v23",
        "evidence_commit": "39f7febf",
    }
    for name, value in expected_text.items():
        check("slide_contains_" + name, value in text, value)
    for forbidden in ("SOTA achieved", "converged model claim=true", "full CAGFN reproduction completed", "functional OOD closed", "time-matched comparison completed"):
        check("forbidden_claim_absent_" + forbidden, forbidden not in text)

    check("production_process_completed", production.get("status") == "COMPLETED_PROCESS" and production.get("returncode") == 0)
    check("independent_33_of_33_pass", independent.get("status") == "PASS" and independent.get("checks_passed") == independent.get("checks_total") == 33)
    check("finalization_22_of_22_pass", finalization.get("status") == "PASS_RK05_CAGFN_OFFICIAL_BOUNDED_SMOKE" and finalization.get("checks_passed") == finalization.get("checks_total") == 22)
    check("paper_91_of_91_pass", paper_verification.get("status") == "PASS" and paper_verification.get("checks_passed") == paper_verification.get("checks_total") == 91)
    check("paper_hash_matches_verified_v23", sha256(paths["paper"]) == paper_verification.get("paper_sha256"))
    check("paper_audit_hash_matches_verified_v23", sha256(paths["paper_audit"]) == paper_verification.get("audit_sha256"))
    check("finalization_source_commit_exact", finalization["publication_boundary"]["source_commit"] == "952ccf9682988ef88cf1251877e918b85fbee9e9")
    check("finalization_openreview_rejected", finalization["publication_boundary"]["openreview_status"] == "rejected")
    check("no_public_pretrained_weights", finalization["publication_boundary"]["pretrained_weights_available"] is False)
    expected_false = ["full_cagfn_reproduction", "converged_model_claim", "main_model_baseline_matrix_closed", "time_matched_comparison", "functional_ood_closed", "sota_claim"]
    check("scientific_completion_boundaries_preserved", all(finalization["completion"].get(k) is False for k in expected_false), {k: finalization["completion"].get(k) for k in expected_false})
    expected_true = ["bounded_official_smoke_closed", "actual_training_completed", "actual_generation_completed", "actual_checkpoint_saved", "independent_raw_output_verification_completed", "ppt_update_authorized"]
    check("authorized_bounded_smoke_complete", all(finalization["completion"].get(k) is True for k in expected_true))
    check("source_specific_metric_engines_stated", "Bundled RNAFolder · human def_refs" in text and "not time-matched" in text)
    check("failure_chain_retained_on_slide", "v1 wrapper / v2 estimator / v3 import failures retained" in text)
    check("ned_not_functional_claim", "Sequence diversity only · not functional gain" in text)

    bounds_failures = []
    for element in new_slide.find(N + "data"):
        if all(element.get(k) is not None for k in ("topLeftX", "topLeftY", "width", "height")):
            x, y, w, h = (float(element.get(k)) for k in ("topLeftX", "topLeftY", "width", "height"))
            if x < 0 or y < 0 or x + w > 960 or y + h > 540:
                bounds_failures.append({"tag": element.tag, "box": [x, y, w, h]})
        if element.tag == N + "line":
            coords = [float(element.get(k)) for k in ("startX", "startY", "endX", "endY")]
            if not (0 <= coords[0] <= 960 and 0 <= coords[2] <= 960 and 0 <= coords[1] <= 540 and 0 <= coords[3] <= 540):
                bounds_failures.append({"tag": "line", "coordinates": coords})
    check("all_new_slide_geometry_inside_canvas", not bounds_failures, bounds_failures)
    tables = new_slide.findall(".//" + N + "table")
    check("one_result_table", len(tables) == 1)
    if len(tables) == 1:
        rows = tables[0].findall(N + "tr")
        check("result_table_5_rows_3_columns", len(rows) == 5 and all(len(r.findall(N + "td")) == 3 for r in rows))
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, capture_output=True, check=True).stdout.strip()
    check("ppt_evidence_commit_matches_pre_report_head", head == "39f7febf65c2cd9b9aa8ff769945a88ff849dd2f", head)
    passed = sum(c["pass"] for c in checks)
    report = {
        "schema": "a8.rk05.cagfn.ppt_online_readback.v1",
        "task_id": "RK05_CAGFN_PPT_ONLINE_READBACK",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS_RK05_CAGFN_PPT_ONLINE_READBACK" if passed == len(checks) else "FAILED",
        "checks_passed": passed,
        "checks_total": len(checks),
        "presentation_url": PRESENTATION,
        "baseline_revision": 60,
        "write_revision": 61,
        "readback_revision": readback_response.get("data", {}).get("revision_id"),
        "slide_id": new_slide.get("id"),
        "slide_number": 99,
        "slide_count": len(readback),
        "legacy_semantic_xml_unchanged": all(c["pass"] for c in checks if c["name"].startswith("legacy_slide_")),
        "server_normalization": ["server-assigned ids ignored", "XML whitespace and attribute order ignored", "missing col span normalized to 1", "line endpoints within 0.001 px of integer normalized"],
        "pre_report_git_head": head,
        "evidence_sha256": {name: sha256(path) for name, path in paths.items()},
        "checks": checks,
        "claim_boundaries": {
            "bounded_dependency_recovery_smoke_only": True,
            "full_cagfn_reproduction": False,
            "converged_model_claim": False,
            "main_model_baseline_matrix_closed": False,
            "time_matched_comparison": False,
            "functional_ood_closed": False,
            "sota_claim": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks_passed": passed, "checks_total": len(checks), "slide_id": report["slide_id"], "slide_count": len(readback), "output": str(args.output)}, ensure_ascii=False, indent=2))
    if passed != len(checks):
        for c in checks:
            if not c["pass"]:
                print("FAIL", c["name"], c.get("details"))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
