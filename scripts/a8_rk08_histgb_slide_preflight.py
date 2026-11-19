#!/usr/bin/env python3
"""Preflight the single retrospective HistGB slide against verified evidence."""
from __future__ import annotations

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    root_dir = Path(__file__).resolve().parent
    source_path = root_dir / "source-v1.xml"
    candidate_path = root_dir / "slide-86-histgb-v1.xml"
    response_path = root_dir / "source-response-v1.json"
    summary = json.loads((root_dir / "full_function_histgb_diagnostic_summary_v1.json").read_text())
    independent = json.loads((root_dir / "full_function_histgb_diagnostic_verification_v1.json").read_text())
    finalization = json.loads((root_dir / "full_function_histgb_diagnostic_finalization_v1.json").read_text())
    paper = json.loads((root_dir / "a8_rk08_histgb_paper_verification.json").read_text())
    response = json.loads(response_path.read_text())
    source = ET.parse(source_path).getroot()
    source_ns = source.tag.split("}")[0] + "}"
    slides = source.findall(source_ns + "slide")
    candidate = ET.parse(candidate_path).getroot()
    candidate_text = " ".join("".join(p.itertext()) for p in candidate.iter() if p.tag.endswith("}p") or p.tag == "p")
    source_text = " ".join("".join(p.itertext()) for p in source.iter() if p.tag.endswith("}p") or p.tag == "p")
    rows = {row["metric"]: row for row in summary["comparisons"] if row["partition"] == "sequence_ood"}
    checks = []

    def check(name, passed, detail):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    check("live_source_ok", response.get("ok") is True, response.get("data", {}).get("revision_id"))
    check("baseline_85_pages", len(slides) == 85 and slides[-1].attrib.get("id") == "pgH", len(slides))
    check("new_page_not_duplicate", "HistGB 点估计更好，但 paired 差异未显著" not in source_text, True)
    check("candidate_single_slide", candidate.tag.endswith("}slide") or candidate.tag == "slide", candidate.tag)
    check("no_manual_ids", all("id" not in element.attrib for element in candidate.iter()), True)
    check("independent_84", independent["status"] == "PASS" and independent["checks_passed"] == independent["checks_total"] == 84 and not independent["failures"], f"{independent['checks_passed']}/{independent['checks_total']}")
    check("finalization_33", finalization["status"] == "PASS_COMPLETE_RETROSPECTIVE_HISTGB_DIAGNOSTIC" and finalization["checks_passed"] == finalization["checks_total"] == 33 and not finalization["failures"], f"{finalization['checks_passed']}/{finalization['checks_total']}")
    check("paper_35", paper["status"] == "PASS" and paper["checks_passed"] == paper["checks_total"] == 35 and not paper["failures"], f"{paper['checks_passed']}/{paper['checks_total']}")
    check("negative_gate", summary["original_rk_g1_pass"] is False and summary["diagnostic_favors_ribokinetic_all"] is False, False)
    check("title", "HistGB 点估计更好，但 paired 差异未显著" in candidate_text, True)
    check("retrospective", "RETROSPECTIVE HISTGB PAIRED DIAGNOSTIC" in candidate_text and "非新预注册门禁" in candidate_text and "ORIGINAL GATE · UNCHANGED" in candidate_text, True)
    check("uncertainty", "2/2 CI 跨零 · 不宣称任一方显著胜出" in candidate_text and "统计上未分辨胜负" in candidate_text, True)
    check("no_generator", "生成器未授权" in candidate_text and "SOTA 未支持" in candidate_text, True)
    check("spearman_value", "−0.0273" in candidate_text, rows["spearman"]["point_delta"])
    check("spearman_ci", "95% CI [−0.0905, +0.0326] · Holm p=0.405" in candidate_text, [rows["spearman"]["ci95_low"], rows["spearman"]["ci95_high"], rows["spearman"]["holm_pvalue_within_partition"]])
    check("mse_value", "+0.0988" in candidate_text, rows["cluster_balanced_mse"]["point_delta"])
    check("mse_ci", "95% CI [−0.0510, +0.2521] · Holm p=0.396" in candidate_text, [rows["cluster_balanced_mse"]["ci95_low"], rows["cluster_balanced_mse"]["ci95_high"], rows["cluster_balanced_mse"]["holm_pvalue_within_partition"]])
    for value in ["4.0887", "0.1921", "0.0103", "3.9900", "0.2194", "0.0324", "4.1143", "0.2179", "0.0117"]:
        check(f"metric:{value}", value in candidate_text, value)
    check("verification_badge", "84/84 + 33/33 · VERIFIED" in candidate_text and "paper 35/35" in candidate_text, True)
    check("github_reference", "GitHub 3742a843" in candidate_text, "3742a843df63cf5783ea75a68dccf0fe3c63760f")
    note = next((element for element in candidate.iter() if element.tag.endswith("}note") or element.tag == "note"), None)
    note_paragraphs = len([element for element in note.iter() if element.tag.endswith("}p") or element.tag == "p"]) if note is not None else 0
    check("speaker_note", 3 <= note_paragraphs <= 5, note_paragraphs)
    check("no_external_media", not any(element.tag.endswith("}img") or element.tag == "img" for element in candidate.iter()) and "http" not in candidate_text, True)
    in_bounds = True
    for element in candidate.iter():
        if all(key in element.attrib for key in ["topLeftX", "topLeftY", "width", "height"]):
            x, y, w, h = (float(element.attrib[key]) for key in ["topLeftX", "topLeftY", "width", "height"])
            in_bounds = in_bounds and x >= 0 and y >= 0 and x + w <= 960 and y + h <= 540
    check("canvas_bounds", in_bounds, "960x540")
    failures = [row for row in checks if not row["pass"]]
    report = {
        "protocol": "a8_rk08_histgb_slide_preflight_v1",
        "status": "PASS" if not failures else "FAIL",
        "presentation": "WB1KsYGualerMUddEzMcCw1En0g",
        "baseline_revision": response.get("data", {}).get("revision_id"),
        "baseline_pages": len(slides),
        "source_sha256": sha256(source_path),
        "candidate_sha256": sha256(candidate_path),
        "checks": checks,
        "checks_passed": len(checks) - len(failures),
        "checks_total": len(checks),
        "failures": failures,
    }
    (root_dir / "slide-preflight-v1.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "candidate_sha256": report["candidate_sha256"]}, indent=2))
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
