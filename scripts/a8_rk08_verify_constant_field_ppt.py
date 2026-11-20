#!/usr/bin/env python3
"""Verify the RK08 constant-field slide candidate and its online readback."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.a8_rk08_make_constant_field_ppt import (
    MARKER, NS, display_comparison, semantic_signature, visible_text,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def paragraphs(slide, container):
    parent = next(e for e in slide if e.tag.rsplit("}", 1)[-1] == container)
    return ["".join(p.itertext()).strip() for p in parent.iter() if p.tag.rsplit("}", 1)[-1] == "p"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["candidate", "final"], required=True)
    for name in ["production", "independent", "finalization", "postpush", "recheck",
                 "candidate", "candidate-report", "output"]:
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--baseline-xml")
    ap.add_argument("--after-xml")
    ap.add_argument("--add-response")
    ap.add_argument("--after-response")
    args = ap.parse_args()
    paths = {name: Path(getattr(args, name.replace("-", "_"))) for name in
             ["production", "independent", "finalization", "postpush", "recheck", "candidate", "candidate_report"]}
    production = load(paths["production"])
    independent = load(paths["independent"])
    finalization = load(paths["finalization"])
    postpush = load(paths["postpush"])
    recheck = load(paths["recheck"])
    candidate_report = load(paths["candidate_report"])
    candidate = ET.parse(paths["candidate"]).getroot()
    data = candidate.find(f"{{{NS}}}data")
    note = candidate.find(f"{{{NS}}}note")
    visible = visible_text(data)
    notes = visible_text(note)
    checks = []

    def check(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("candidate_accepted", candidate_report.get("overall_pass") is True)
    check("candidate_hash_binding", candidate_report.get("candidate_sha256") == sha(paths["candidate"]))
    check("single_slide_root", candidate.tag == f"{{{NS}}}slide")
    check("no_candidate_ids", all("id" not in e.attrib for e in candidate.iter()))
    check("no_unknown_media", all(e.tag.rsplit("}", 1)[-1] not in {"img", "embed", "undefined"} for e in candidate.iter()))
    check("no_emoji", not re.search(r"[\U0001F300-\U0001FAFF]", visible + notes))
    check("page_and_marker", "A8-RK · 109" in visible and visible.count(MARKER) == 1)
    check("primary_partition", production["primary_partition"] == "study_ood|Subtelny14" and "3,630 Subtelny14 transcripts" in visible)
    check("bootstrap_contract", "2,000 bootstraps × 3 seeds" in visible and "6 Holm-adjusted tests" in visible)
    metrics = production["metrics"][production["primary_partition"]]
    for name in ["model", "ridge", "constant"]:
        for metric in ["transcript_balanced_mse", "mean_transcript_pearson", "position_mse"]:
            check(f"note_metric_{name}_{metric}", repr(metrics[name][metric]) in notes)
    check("constant_metric_display", f"{metrics['constant']['transcript_balanced_mse']:.6f}" in visible and f"{metrics['constant']['mean_transcript_pearson']:+.6f}".replace("-", "−") in visible)
    for key in ["model_minus_constant", "ridge_minus_constant", "model_minus_ridge"]:
        row = production["primary_comparisons"][key]
        values = display_comparison(row)
        for label, value in values.items():
            check(f"display_{key}_{label}", value in visible, value)
        for field in ["delta_transcript_balanced_mse", "delta_mean_transcript_pearson"]:
            check(f"note_{key}_{field}", repr(row[field]) in notes)
        for metric in ["transcript_balanced_mse", "mean_transcript_pearson"]:
            for value in row[metric]["ci95"]:
                check(f"note_{key}_{metric}_ci_{value}", repr(value) in notes)
            check(f"note_{key}_{metric}_holm", repr(row[metric]["holm_pvalue"]) in notes)
        check(f"unsupported_{key}", production["support"][key + "_supported"] is False)
    check("independent_counts", independent["check_count"] == independent["passed_count"] == 361 and "361 / 361" in visible)
    check("independent_delta", independent["max_numeric_delta"] == 6.245004513516506e-17 and repr(independent["max_numeric_delta"]) in notes)
    check("finalization_counts", finalization["check_count"] == finalization["passed_count"] == 37 and "37/37" in notes)
    check("postpush_counts", postpush["check_count"] == postpush["passed_count"] == 361 and "361/361" in notes)
    check("fresh_recheck", recheck["check_count"] == recheck["passed_count"] == 361 and repr(recheck["max_numeric_delta"]) in notes)
    check("unit_tests", "10/10" in visible and "10/10" in notes)
    for phrase in ["Velocity mechanism = false", "RK-G1 = false", "functional untouched not evaluated",
                   "generator training unauthorized", "No causal, functional, protein-OOD, external-SOTA, or readiness claim"]:
        check(f"boundary_{phrase}", phrase in visible)
    for key in ["velocity_mechanism_pass", "rk_g1_pass", "functional_untouched_evaluated", "generator_training_authorized", "external_sota_claim_authorized"]:
        check(f"gate_{key}", production["gates"][key] is False)
    check("table_shape", len(candidate.findall(f".//{{{NS}}}tr")) == 4 and len(candidate.findall(f".//{{{NS}}}col")) == 5)
    check("speaker_notes", 3 <= len(paragraphs(candidate, "note")) <= 5)

    if args.mode == "final":
        required = [args.baseline_xml, args.after_xml, args.add_response, args.after_response]
        check("final_inputs_present", all(required))
        if all(required):
            baseline_path = Path(args.baseline_xml)
            after_path = Path(args.after_xml)
            add = load(Path(args.add_response))
            after_response = load(Path(args.after_response))
            before = ET.parse(baseline_path).getroot()
            after = ET.parse(after_path).getroot()
            before_slides = [e for e in list(before) if e.tag.rsplit("}", 1)[-1] == "slide"]
            after_slides = [e for e in list(after) if e.tag.rsplit("}", 1)[-1] == "slide"]
            new_id = add.get("data", {}).get("slide_id")
            revision = add.get("data", {}).get("revision_id")
            check("add_success", add.get("ok") is True and bool(new_id))
            check("readback_success", after_response.get("ok") is True and after_response.get("data", {}).get("revision_id") == revision)
            check("page_count", len(before_slides) == 108 and len(after_slides) == 109)
            check("new_last_page", after_slides[-1].get("id") == new_id)
            check("old_page_ids", [s.get("id") for s in before_slides] == [s.get("id") for s in after_slides[:108]])
            for index, (old, new) in enumerate(zip(before_slides, after_slides[:108]), 1):
                check(f"old_page_{index}_full_semantics_unchanged", semantic_signature(old) == semantic_signature(new))
            check("new_page_visible_text", paragraphs(after_slides[-1], "data") == paragraphs(candidate, "data"))
            check("new_page_notes", paragraphs(after_slides[-1], "note") == paragraphs(candidate, "note"))
            marker_pages = [i + 1 for i, slide in enumerate(after_slides) if MARKER in visible_text(slide)]
            check("single_online_page", marker_pages == [109], marker_pages)
            check("new_page_negative_gates", "Velocity mechanism = false" in visible_text(after_slides[-1]) and "RK-G1 = false" in visible_text(after_slides[-1]))

    passed = sum(c["pass"] for c in checks)
    result = {
        "schema": "a8-rk08-constant-field-ppt-verification-v1",
        "mode": args.mode,
        "status": "PASS_CONSTANT_FIELD_PPT" if passed == len(checks) else "FAIL_CONSTANT_FIELD_PPT",
        "overall_pass": passed == len(checks),
        "check_counts": {"passed": passed, "total": len(checks)},
        "candidate_sha256": sha(paths["candidate"]),
        "production_sha256": sha(paths["production"]),
        "independent_sha256": sha(paths["independent"]),
        "finalization_sha256": sha(paths["finalization"]),
        "postpush_sha256": sha(paths["postpush"]),
        "recheck_sha256": sha(paths["recheck"]),
        "velocity_mechanism_pass": False,
        "rk_g1_pass": False,
        "functional_untouched_evaluated": False,
        "generator_training_authorized": False,
        "checks": checks,
    }
    if args.mode == "final" and all([args.baseline_xml, args.after_xml, args.add_response]):
        result["slide_id"] = load(Path(args.add_response)).get("data", {}).get("slide_id")
        result["revision_id"] = load(Path(args.add_response)).get("data", {}).get("revision_id")
        result["baseline_xml_sha256"] = sha(Path(args.baseline_xml))
        result["after_xml_sha256"] = sha(Path(args.after_xml))
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "check_counts": result["check_counts"]}, indent=2))
    if passed != len(checks):
        for check_ in checks:
            if not check_["pass"]:
                print("FAIL", check_)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
