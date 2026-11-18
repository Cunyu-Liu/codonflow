#!/usr/bin/env python3
"""Independently verify the RiboMIMO candidate slide or its server readback."""
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


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--baseline-xml", type=Path)
    parser.add_argument("--baseline-response", type=Path)
    parser.add_argument("--readback-xml", type=Path)
    parser.add_argument("--readback-response", type=Path)
    parser.add_argument("--add-response", type=Path)
    parser.add_argument("--expected-new-slide-id")
    parser.add_argument("--evidence-commit", default="a6e119650c4dd52110849b43aa377cbbd1e422b0")
    parser.add_argument("--paper-commit", default="56f9c4d559dc29f94b295f2500f7c0a3af1410e4")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.candidate) == bool(args.readback_xml):
        raise ValueError("choose exactly one mode: --candidate or --readback-xml")

    evidence = args.evidence_dir.resolve()
    paths = {
        "production": evidence / "ribomimo_official_smoke_v2.json",
        "independent": evidence / "ribomimo_independent_verification_v1.json",
        "finalization": evidence / "ribomimo_finalization_v1.json",
    }
    data = {name: load(path) for name, path in paths.items()}
    p, ind, fin = data["production"], data["independent"], data["finalization"]
    metrics = p["official_result"]["metrics"]
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    check("frozen_scientific_evidence", p["status"] == "BOUNDED_OFFICIAL_TRAINING_COMPLETE" and ind["status"] == "PASS" and ind["passed_checks"] == ind["check_count"] == 17 and fin["status"] == "CLOSED_BOUNDED_OFFICIAL_SMOKE" and fin["passed_checks"] == fin["check_count"] == 13 and "Only the bounded official RiboMIMO training smoke is closed." in fin["scope"] and "remain open" in fin["scope"], {"independent": "17/17", "finalization": "13/13"})

    fold_details = []
    for fold in (0, 1):
        item = next(c for c in ind["checks"] if c["name"] == f"fold_{fold}_checkpoint_metrics_match")["detail"]["independent"]
        fold_details.append(item)

    visible_required = [
        "RiboMIMO Bounded Official Training Verified",
        p["source"]["commit"][:7],
        f"{metrics['r2_mean']:.6f}", f"{metrics['r2_std']:.6f}",
        f"{metrics['mse_mean']:.6f}", f"{metrics['mse_std']:.6f}",
        f"{metrics['pearson_mean']:.6f}", f"{metrics['pearson_std']:.6f}",
        "17/17", "13/13", "20 genes", "9/1/10 per fold", "batch 4",
        f"{p['official_result']['checkpoint_parameter_count']:,} parameters",
        "exact 6 NumPy edits", args.evidence_commit[:8], args.paper_commit[:8], "tests 10/10",
        "Bounded execution closes; small-subset metrics are not predictive evidence",
    ]
    for item in fold_details:
        visible_required.extend([
            f"Fold {item['fold']} · {item['positive_masked_positions']} masked positions",
            f"{item['r2']:.6f}", f"{item['mse']:.6f}", f"{item['pearson']:.6f}",
        ])
    aggregate_rows = [
        f"{metrics['r2_mean']:.6f} ± {metrics['r2_std']:.6f}",
        f"{metrics['mse_mean']:.6f} ± {metrics['mse_std']:.6f}",
        f"{metrics['pearson_mean']:.6f} ± {metrics['pearson_std']:.6f}",
    ]
    visible_required.extend(aggregate_rows)
    scope_required = [
        "Bounded official training only", "no full 10-fold/100-epoch",
        "OOD", "main matrix", "SOTA", "Negative R-squared and near-zero Pearson are diagnostics",
        "max metric delta 4.10e-07",
    ]

    if args.candidate:
        slide = ET.parse(args.candidate).getroot()
        data_element = next((e for e in children(slide, "data")), None)
        visible = normalized_text(data_element)
        notes = descendants(slide, "note")
        note_paragraphs = descendants(notes[0], "p") if notes else []
        note_text = normalized_text(notes[0]) if notes else ""
        check("candidate_values_match_frozen_json", all(s in visible for s in visible_required), {"required_strings": len(visible_required)})
        check("candidate_scope_and_no_overclaim", all(s in visible for s in scope_required) and not any(s in visible for s in ["SOTA achieved", "main baseline closed", "functional OOD closed", "publication performance reproduced"]), scope_required)
        check("candidate_table_structure", len(descendants(slide, "table")) == 1 and len(descendants(slide, "tr")) == 4 and len(descendants(slide, "col")) == 5, {"rows": len(descendants(slide, "tr")), "columns": len(descendants(slide, "col"))})
        check("candidate_speaker_notes", len(note_paragraphs) == 4 and all(s in note_text for s in [str(p["protocol"]["seed"]), "LongTensor", "19/19", "10-fold/100-epoch", "prediction pickle"]), {"paragraphs": len(note_paragraphs)})
        bounds_ok = True
        for element in slide.iter():
            if all(k in element.attrib for k in ("topLeftX", "topLeftY", "width", "height")):
                x, y, w, h = (float(element.get(k)) for k in ("topLeftX", "topLeftY", "width", "height"))
                bounds_ok &= x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= 960 and y + h <= 540
            if element.tag.endswith("line"):
                bounds_ok &= all(0 <= float(element.get(k)) <= (960 if k.endswith("X") else 540) for k in ("startX", "startY", "endX", "endY"))
        check("candidate_canvas_bounds", bounds_ok, {"width": 960, "height": 540})
        check("candidate_page_number", any(normalized_text(e) == "76" for e in descendants(slide, "p")), "76")
        check("candidate_no_handwritten_ids", all("id" not in e.attrib for e in slide.iter()), None)
        report = {
            "schema_version": "a8-rk05-ribomimo-ppt-candidate-verification-v1",
            "mode": "candidate_only_no_server_write",
            "candidate": str(args.candidate),
            "candidate_sha256": sha256(args.candidate),
            "source_sha256": {name: sha256(path) for name, path in paths.items()},
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
        check("baseline_identity", baseline_response.get("ok") is True and len(old_slides) == 75 and old_slides[-1].get("id") == "pgh", {"slides": len(old_slides), "revision": baseline_response.get("data", {}).get("revision_id")})
        check("exactly_one_slide_appended", readback_response.get("ok") is True and len(new_slides) == len(old_slides) + 1 == 76, {"before": len(old_slides), "after": len(new_slides)})
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
        check("readback_notes_bounds_and_page", len(note_paragraphs) == 4 and any(normalized_text(e) == "76" for e in descendants(appended, "p")) and all(float(e.get("topLeftX", "0")) >= 0 and float(e.get("topLeftY", "0")) >= 0 and float(e.get("topLeftX", "0")) + float(e.get("width", "0")) <= 960 and float(e.get("topLeftY", "0")) + float(e.get("height", "0")) <= 540 for e in appended.iter() if all(k in e.attrib for k in ("topLeftX", "topLeftY", "width", "height"))), {"note_paragraphs": len(note_paragraphs)})
        check("readback_scope_preserved", all(s in visible for s in scope_required) and not any(s in visible for s in ["SOTA achieved", "main baseline closed", "functional OOD closed", "publication performance reproduced"]), scope_required)
        report = {
            "schema_version": "a8-rk05-ribomimo-ppt-independent-verification-v1",
            "mode": "post_write_server_readback",
            "baseline_xml": str(args.baseline_xml),
            "readback_xml": str(args.readback_xml),
            "baseline_xml_sha256": sha256(args.baseline_xml),
            "readback_xml_sha256": sha256(args.readback_xml),
            "new_slide_id": new_id,
            "slide_count": len(new_slides),
            "revision_id": readback_response["data"]["revision_id"],
            "source_sha256": {name: sha256(path) for name, path in paths.items()},
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
        "scope": "Bounded RiboMIMO official training record only; no full protocol, OOD, main matrix or SOTA closure.",
    })
    atomic_json(args.output, report)
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "output": str(args.output)}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
