#!/usr/bin/env python3
"""Finalize the live five-slide A8-RK reporting sequence (slides 91–95)."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from scripts.a8_rk12_verify_ppt_readback import canonical, sha256, slides


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    repo = args.repository.resolve()
    root = args.artifacts.resolve()
    rk12 = root / "rk12/ppt_online_v1"
    recovery = root / "rk_functional/mordstein2020/recovery_online_v1"
    proxy = root / "rk_functional/mordstein2020/proxy_online_v1"
    mage = root / "rk03/mage_online_v1"
    baseline_path = rk12 / "baseline90.xml"
    final_path = mage / "readback95.xml"
    _, _, baseline = slides(baseline_path)
    _, ns, final = slides(final_path)
    candidate_paths = [
        rk12 / "rk12-slide91-candidate.xml",
        rk12 / "rk12-slide92-candidate.xml",
        recovery / "slide93.xml",
        proxy / "slide94.xml",
        mage / "slide95.xml",
    ]
    response_paths = [
        rk12 / "response91.json",
        rk12 / "response92.json",
        recovery / "response93.json",
        proxy / "response94.json",
        mage / "response95.json",
    ]
    verification_paths = [
        rk12 / "online_readback_v3.json",
        recovery / "online_readback_v1.json",
        proxy / "online_readback_v1.json",
        mage / "online_readback_v1.json",
    ]
    candidates = [ET.parse(path).getroot() for path in candidate_paths]
    responses = [json.loads(path.read_text()) for path in response_paths]
    verifications = [json.loads(path.read_text()) for path in verification_paths]
    readback_response = json.loads((mage / "readback95-response.json").read_text())
    checks = []

    def check(name, condition, evidence):
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})

    check("baseline_exactly_90", len(baseline) == 90, len(baseline))
    check("final_exactly_95", len(final) == 95, len(final))
    check("final_readback_ok", readback_response.get("ok") is True and readback_response["data"].get("scope") == "presentation", readback_response["data"].get("revision_id"))
    check("first_90_ids_unchanged", [s.attrib.get("id") for s in baseline] == [s.attrib.get("id") for s in final[:90]], "ordered IDs")
    changed = [i + 1 for i in range(90) if canonical(baseline[i]) != canonical(final[i])]
    check("first_90_semantic_xml_unchanged", not changed, changed)
    response_ids = [r["data"].get("slide_id") for r in responses]
    final_new_ids = [s.attrib.get("id") for s in final[90:]]
    check("five_response_ids_match_final_pages", response_ids == final_new_ids, final_new_ids)
    all_ids = [s.attrib.get("id") for s in final]
    check("all_95_slide_ids_unique", len(set(all_ids)) == 95 and all(all_ids), len(set(all_ids)))
    check("all_add_responses_ok", all(r.get("ok") is True for r in responses), [r.get("ok") for r in responses])
    revisions = [r["data"].get("revision_id") for r in responses]
    check("five_revisions_consecutive", revisions == list(range(revisions[0], revisions[0] + 5)), revisions)
    check("final_readback_revision_matches_last_add", readback_response["data"].get("revision_id") == revisions[-1], readback_response["data"].get("revision_id"))
    for index, candidate in enumerate(candidates):
        check(f"slide{91 + index}_candidate_semantics", canonical(candidate) == canonical(final[90 + index]), sha256(candidate_paths[index]))
    note_counts = [len(s.findall(f".//{{{ns}}}note/{{{ns}}}content/{{{ns}}}p")) for s in final[90:]]
    check("five_slides_have_four_note_paragraphs", note_counts == [4] * 5, note_counts)
    out_of_bounds = []
    for page, slide in enumerate(final[90:], start=91):
        for node in slide.iter():
            try:
                x, y = float(node.attrib["topLeftX"]), float(node.attrib["topLeftY"])
                w, h = float(node.attrib["width"]), float(node.attrib["height"])
            except (KeyError, ValueError):
                continue
            if x < 0 or y < 0 or w < 0 or h < 0 or x + w > 960.000001 or y + h > 540.000001:
                out_of_bounds.append({"page": page, "tag": node.tag.rsplit("}", 1)[-1], "box": [x, y, w, h]})
    check("five_slides_canvas_bounds", not out_of_bounds, out_of_bounds)
    expected_totals = [16, 11, 13, 13]
    for label, report, total in zip(("rk12", "mordstein", "proxy", "mage"), verifications, expected_totals):
        check(f"{label}_online_report_pass", report["status"] == "PASS" and report["checks_passed"] == report["checks_total"] == total, f'{report["checks_passed"]}/{report["checks_total"]}')
        check(f"{label}_changed_baseline_empty", report.get("changed_baseline_pages") == [], report.get("changed_baseline_pages"))
    candidate_hash_pairs = [
        (candidate_paths[0], verifications[0]["candidate91_sha256"]),
        (candidate_paths[1], verifications[0]["candidate92_sha256"]),
        (candidate_paths[2], verifications[1]["candidate93_sha256"]),
        (candidate_paths[3], verifications[2]["candidate94_sha256"]),
        (candidate_paths[4], verifications[3]["candidate95_sha256"]),
    ]
    check("candidate_hashes_match_online_reports", all(sha256(path) == expected for path, expected in candidate_hash_pairs), "five candidates")
    chain_files = [baseline_path, rk12 / "readback92.xml", recovery / "readback93.xml", proxy / "readback94.xml", final_path]
    chain_hashes = [sha256(path) for path in chain_files]
    expected_chain = [
        (verifications[0]["baseline_sha256"], verifications[0]["readback_sha256"]),
        (verifications[1]["baseline_sha256"], verifications[1]["readback_sha256"]),
        (verifications[2]["baseline_sha256"], verifications[2]["readback_sha256"]),
        (verifications[3]["baseline_sha256"], verifications[3]["readback_sha256"]),
    ]
    check("readback_hash_chain_exact", all(pair == (chain_hashes[i], chain_hashes[i + 1]) for i, pair in enumerate(expected_chain)), chain_hashes)
    evidence_map = {
        "rk12_finalization": (verifications[0]["finalization_sha256"], repo / "audits/20261118/RK12/rk12_finalization_v1.json"),
        "rk12_matrix": (verifications[0]["matrix_sha256"], root / "rk12/actual_set_matrix_v1/unique18_actual_set_matrix.json"),
        "mordstein_summary": (verifications[1]["summary_sha256"], repo / "audits/20261118/RK02/mordstein_recovery_full_summary_v1.json"),
        "mordstein_independent": (verifications[1]["independent_sha256"], repo / "audits/20261118/RK02/mordstein_recovery_full_independent_v1.json"),
        "mordstein_finalization": (verifications[1]["finalization_sha256"], repo / "audits/20261118/RK02/mordstein_recovery_full_finalization_v1.json"),
        "proxy_primary": (verifications[2]["primary_sha256"], repo / "audits/20261118/RK02/mordstein_proxy_diagnostics_v1.json"),
        "proxy_primary_independent": (verifications[2]["primary_independent_sha256"], repo / "audits/20261118/RK02/mordstein_proxy_diagnostics_independent_v1.json"),
        "proxy_primary_finalization": (verifications[2]["primary_finalization_sha256"], repo / "audits/20261118/RK02/mordstein_proxy_diagnostics_finalization_v1.json"),
        "proxy_robustness": (verifications[2]["robustness_sha256"], repo / "audits/20261118/RK02/mordstein_proxy_robustness_v1.json"),
        "proxy_robustness_independent": (verifications[2]["robustness_independent_sha256"], repo / "audits/20261118/RK02/mordstein_proxy_robustness_independent_v1.json"),
        "proxy_robustness_finalization": (verifications[2]["robustness_finalization_sha256"], repo / "audits/20261118/RK02/mordstein_proxy_robustness_finalization_v1.json"),
        "mage_protocol": (verifications[3]["protocol_sha256"], repo / "configs/a8_rk03_mage_synonymous_mechanism_protocol_v1.json"),
        "mage_production": (verifications[3]["production_sha256"], repo / "audits/20261118/RK03/mage_synonymous_mechanism_v1.json"),
        "mage_independent": (verifications[3]["independent_sha256"], repo / "audits/20261118/RK03/mage_synonymous_mechanism_independent_v1.json"),
        "mage_finalization": (verifications[3]["finalization_sha256"], repo / "audits/20261118/RK03/mage_synonymous_mechanism_finalization_v1.json"),
    }
    mismatched_evidence = [name for name, (expected, path) in evidence_map.items() if sha256(path) != expected]
    check("all_scientific_evidence_hashes_current", not mismatched_evidence, mismatched_evidence)
    visible = ["".join(s.itertext()) for s in final[90:]]
    check("development_not_sota_boundary_visible", "dense/time-matched 未完成 · 非功能评价 · 非 SOTA" in visible[1], "slide 92")
    check("mordstein_217_boundary_visible", "152 variants ≠ 217 candidates" in visible[2] and "非完整 CDS · 非作者身份 · 非功能/SOTA 证据" in visible[2], "slide 93")
    check("proxy_noncausal_boundary_visible", "非完整 CDS · 非蛋白 OOD · 非因果 · 非 SOTA" in visible[3], "slide 94")
    check("mage_untouched_test_boundary_visible", "no test predictions" in visible[4] and "no test metrics or paired CIs" in visible[4] and "no N-terminal transport" in visible[4], "slide 95")
    passed = sum(c["pass"] for c in checks)
    report = {
        "schema": "a8-rk-ppt-online-sequence-finalization-v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "presentation_url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "checks_passed": passed,
        "checks_total": len(checks),
        "failed_checks": [c["name"] for c in checks if not c["pass"]],
        "baseline_slide_count": len(baseline),
        "final_slide_count": len(final),
        "new_slide_ids": final_new_ids,
        "add_revisions": revisions,
        "baseline_sha256": chain_hashes[0],
        "final_readback_sha256": chain_hashes[-1],
        "candidate_sha256": {str(91 + i): sha256(path) for i, path in enumerate(candidate_paths)},
        "online_verification_sha256": {name: sha256(path) for name, path in zip(("rk12", "mordstein", "proxy", "mage"), verification_paths)},
        "scientific_evidence_sha256": {name: expected for name, (expected, _) in evidence_map.items()},
        "checks": checks,
        "online_report_sequence_complete": passed == len(checks),
        "scientific_gate_passed": False,
        "sota_claim": False,
        "paper_submittable": False,
        "scientific_boundary": "This finalizes presentation fidelity only. Full generator training, unified time-matched cost, dense budget AUC, CodonFlow-RK main-model comparisons, complete OOD/ablations and SOTA remain open.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
