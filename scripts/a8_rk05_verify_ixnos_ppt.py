#!/usr/bin/env python3
"""Independently verify the iXnos candidate slide or its server readback."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def namespace(root: ET.Element) -> str:
    return root.tag[1:].split("}")[0] if root.tag.startswith("{") else ""


def children(root: ET.Element, name: str) -> list[ET.Element]:
    ns = namespace(root)
    return root.findall(f"{{{ns}}}{name}") if ns else root.findall(name)


def descendants(root: ET.Element, name: str) -> list[ET.Element]:
    ns = namespace(root)
    return root.findall(f".//{{{ns}}}{name}") if ns else root.findall(f".//{name}")


def normalized_text(root: ET.Element | None) -> str:
    if root is None:
        return ""
    return " ".join("".join(root.itertext()).split())


def semantic_xml(slide: ET.Element) -> str:
    value = copy.deepcopy(slide)
    for element in value.iter():
        element.attrib.pop("id", None)
        element.tail = None
    return ET.tostring(value, encoding="unicode")


def inside_canvas(slide: ET.Element) -> bool:
    ok = True
    for element in slide.iter():
        if all(k in element.attrib for k in ("topLeftX", "topLeftY", "width", "height")):
            x, y, w, h = (float(element.get(k)) for k in ("topLeftX", "topLeftY", "width", "height"))
            ok &= x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= 960 and y + h <= 540
        if element.tag.endswith("line"):
            ok &= all(0 <= float(element.get(k)) <= (960 if k.endswith("X") else 540) for k in ("startX", "startY", "endX", "endY"))
    return ok


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--paper-report", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--baseline-xml", type=Path)
    parser.add_argument("--baseline-response", type=Path)
    parser.add_argument("--readback-xml", type=Path)
    parser.add_argument("--readback-response", type=Path)
    parser.add_argument("--add-response", type=Path)
    parser.add_argument("--expected-new-slide-id")
    parser.add_argument("--evidence-commit", default="645bc22f179dabc35f74f43144f0462de8f4a228")
    parser.add_argument("--paper-commit", default="12d044d69519ffad8127cc9642372624b4c0a153")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.candidate) == bool(args.readback_xml):
        raise ValueError("choose exactly one mode: --candidate or --readback-xml")

    evidence = args.evidence_dir.resolve()
    paths = {
        "production": evidence / "ixnos_official_smoke_v1.json",
        "independent": evidence / "ixnos_independent_verification_v1.json",
        "finalization": evidence / "ixnos_finalization_v1.json",
    }
    data = {name: load(path) for name, path in paths.items()}
    p, ind, fin = data["production"], data["independent"], data["finalization"]
    paper = load(args.paper_report)
    unit_log = (evidence / "ixnos_unit_tests_v2.log").read_text(encoding="utf-8")
    metrics = p["training"]["test_metrics"]
    baseline = p["training"]["train_mean_baseline_metrics"]
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    repeat = next(c for c in fin["checks"] if c["name"] == "independent_pipeline_rerun_content_identity_before_training")["details"]
    sam = repeat["footprints_sam"]
    repeat_ok = (
        repeat["prefix"]["byte_identical"] and repeat["trimmed"]["byte_identical"]
        and sam["canonical_content_identical"] and not sam["raw_byte_identical"]
        and sam["failed_run"]["alignment_records"] == sam["production_run"]["alignment_records"] == 1255357
        and sam["failed_run"]["canonical_sorted_alignment_sha256"] == sam["production_run"]["canonical_sorted_alignment_sha256"]
        and sam["failed_run"]["normalized_pg_sha256"] == sam["production_run"]["normalized_pg_sha256"]
    )
    frozen_ok = (
        p["status"] == "BOUNDED_OFFICIAL_SMOKE_COMPLETE_PENDING_INDEPENDENT_VERIFICATION"
        and p["config"]["source_commit"] == "1ea2337dd24d1e6fa3859f08573e99f02512810f"
        and p["prefix_qc"]["records"] == 1000000 and p["trimmed_qc"]["records"] == 864464
        and p["training"]["train_shape"] == [3816, 760] and p["training"]["test_shape"] == [1963, 760]
        and p["training"]["parameter_count"] == 152401
        and ind["status"] == "PASS" and ind["checks_passed"] == ind["checks_total"] == 27
        and ind["max_prediction_abs_delta"] == 0.0 and ind["max_checkpoint_abs_delta"] == 0.0
        and fin["status"] == "CLOSED_BOUNDED_OFFICIAL_SMOKE" and fin["checks_passed"] == fin["checks_total"] == 16
        and paper["status"] == "PASS" and paper["passed_checks"] == paper["check_count"] == 20
        and "Ran 10 tests" in unit_log and "OK\n" in unit_log and repeat_ok
    )
    check("frozen_scientific_evidence", frozen_ok, {"independent": "27/27", "finalization": "16/16", "paper": "20/20", "canonical_sam": repeat_ok})

    visible_required = [
        "iXnos Bounded Official Training Verified", p["config"]["source_commit"][:7],
        "SRR1049521 first-1M reads", "20/10 genes", "2 epochs", "CPU single thread",
        f"{metrics['r2']:.6f}", f"{metrics['mse']:.6f}", f"{metrics['pearson']:.6f}", f"{metrics['spearman']:.6f}",
        f"{baseline['mse']:.6f}", "27/27", "16/16", "864,464 trimmed", "3,816/1,963 codons",
        "760 features", f"{p['training']['parameter_count']:,} parameters", "Final epoch only",
        "canonical Bowtie records match", "raw SAM order differs", args.evidence_commit[:8], args.paper_commit[:8],
        "tests 10/10", "bounded metrics are not paper performance", "Production final epoch · n=1,963",
        "Independent retrain · n=1,963", "Train-mean constant · n=1,963", "exact diff 0",
    ]
    scope_required = [
        "Bounded official training only", "no full run", "RSEM", "OOD", "main matrix", "SOTA",
        "bounded metrics are not paper performance",
    ]
    note_required = [
        str(p["config"]["seed"]), "_tkinter", "MPLBACKEND=Agg", "1,255,357", "20/20", "10/10",
        "333/167-gene 60-epoch", "RSEM", "独立 verifier 没有重新执行 Bowtie mapping",
    ]

    if args.candidate:
        slide = ET.parse(args.candidate).getroot()
        data_element = next((e for e in children(slide, "data")), None)
        visible = normalized_text(data_element)
        notes = descendants(slide, "note")
        note_paragraphs = descendants(notes[0], "p") if notes else []
        note_text = normalized_text(notes[0]) if notes else ""
        check("candidate_values_match_frozen_json", all(s in visible for s in visible_required), {"required_strings": len(visible_required), "missing": [s for s in visible_required if s not in visible]})
        check("candidate_scope_and_no_overclaim", all(s in visible for s in scope_required) and not any(s in visible for s in ["SOTA achieved", "main baseline closed", "functional OOD closed", "publication performance reproduced"]), scope_required)
        check("candidate_table_structure", len(descendants(slide, "table")) == 1 and len(descendants(slide, "tr")) == 4 and len(descendants(slide, "col")) == 6 and len(descendants(slide, "td")) == 24, {"rows": len(descendants(slide, "tr")), "columns": len(descendants(slide, "col"))})
        check("candidate_speaker_notes", len(note_paragraphs) == 4 and all(s in note_text for s in note_required), {"paragraphs": len(note_paragraphs)})
        check("candidate_canvas_bounds", inside_canvas(slide), {"width": 960, "height": 540})
        check("candidate_page_number", any(normalized_text(e) == "77" for e in descendants(slide, "p")), "77")
        check("candidate_no_handwritten_ids", all("id" not in e.attrib for e in slide.iter()), None)
        report = {
            "schema_version": "a8-rk05-ixnos-ppt-candidate-verification-v1",
            "mode": "candidate_only_no_server_write",
            "candidate": str(args.candidate),
            "candidate_sha256": sha256(args.candidate),
            "source_sha256": {name: sha256(path) for name, path in paths.items()},
            "paper_report_sha256": sha256(args.paper_report),
        }
    else:
        required_paths = [args.baseline_xml, args.baseline_response, args.readback_xml, args.readback_response, args.add_response]
        if any(path is None for path in required_paths):
            raise ValueError("post-write mode requires baseline/readback XML, responses and add response")
        baseline_root = ET.parse(args.baseline_xml).getroot()
        readback_root = ET.parse(args.readback_xml).getroot()
        old_slides = children(baseline_root, "slide")
        new_slides = children(readback_root, "slide")
        baseline_response = load(args.baseline_response)
        readback_response = load(args.readback_response)
        add_response = load(args.add_response)
        add_data = add_response.get("data", {})
        new_id = add_data.get("slide_id")
        if args.expected_new_slide_id:
            check("add_response_slide_id", add_response.get("ok") is True and new_id == args.expected_new_slide_id, new_id)
        else:
            check("add_response_slide_id", add_response.get("ok") is True and bool(new_id), new_id)
        check("baseline_identity", baseline_response.get("ok") is True and len(old_slides) == 76 and old_slides[-1].get("id") == "pgG", {"slides": len(old_slides), "revision": baseline_response.get("data", {}).get("revision_id")})
        check("exactly_one_slide_appended", readback_response.get("ok") is True and len(new_slides) == len(old_slides) + 1 == 77, {"before": len(old_slides), "after": len(new_slides)})
        check("previous_slide_ids_and_order_unchanged", [s.get("id") for s in new_slides[:len(old_slides)]] == [s.get("id") for s in old_slides], None)
        changed = [old.get("id") for old, new in zip(old_slides, new_slides) if semantic_xml(old) != semantic_xml(new)]
        check("previous_semantic_xml_unchanged", not changed, {"changed_slide_ids": changed})
        appended = new_slides[-1]
        check("new_slide_is_last_and_matches_response", appended.get("id") == new_id and new_id not in [s.get("id") for s in old_slides], appended.get("id"))
        check("revision_advanced", int(readback_response["data"]["revision_id"]) > int(baseline_response["data"]["revision_id"]), {"before": baseline_response["data"]["revision_id"], "after": readback_response["data"]["revision_id"]})
        visible = normalized_text(next((e for e in children(appended, "data")), None))
        check("readback_values_match_frozen_json", all(s in visible for s in visible_required), {"required_strings": len(visible_required)})
        notes = descendants(appended, "note")
        note_paragraphs = descendants(notes[0], "p") if notes else []
        note_text = normalized_text(notes[0]) if notes else ""
        check("readback_notes_bounds_and_page", len(note_paragraphs) == 4 and all(s in note_text for s in note_required) and any(normalized_text(e) == "77" for e in descendants(appended, "p")) and inside_canvas(appended), {"note_paragraphs": len(note_paragraphs)})
        check("readback_scope_preserved", all(s in visible for s in scope_required) and not any(s in visible for s in ["SOTA achieved", "main baseline closed", "functional OOD closed", "publication performance reproduced"]), scope_required)
        report = {
            "schema_version": "a8-rk05-ixnos-ppt-independent-verification-v1",
            "mode": "post_write_server_readback",
            "baseline_xml": str(args.baseline_xml),
            "readback_xml": str(args.readback_xml),
            "baseline_xml_sha256": sha256(args.baseline_xml),
            "readback_xml_sha256": sha256(args.readback_xml),
            "new_slide_id": new_id,
            "slide_count": len(new_slides),
            "revision_id": readback_response["data"]["revision_id"],
            "source_sha256": {name: sha256(path) for name, path in paths.items()},
            "paper_report_sha256": sha256(args.paper_report),
            "evidence_commit": args.evidence_commit,
            "paper_commit": args.paper_commit,
        }

    passed = sum(c["pass"] for c in checks)
    report.update({
        "status": "PASS" if passed == len(checks) else "FAIL",
        "checks": checks,
        "passed_checks": passed,
        "check_count": len(checks),
        "production_module_imported": False,
        "scope": "Bounded iXnos official training record only; no full run, RSEM, paper protocol, OOD, main matrix or SOTA closure.",
    })
    atomic_json(args.output, report)
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "output": str(args.output)}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
