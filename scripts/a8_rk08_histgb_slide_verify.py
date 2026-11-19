#!/usr/bin/env python3
"""Verify the live HistGB slide and byte-preservation of the first 85 pages."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def visible_text(element: ET.Element) -> str:
    return " ".join("".join(p.itertext()) for p in element.iter() if p.tag.endswith("}p") or p.tag == "p")


def main() -> None:
    work = Path(__file__).resolve().parent
    source_response = json.loads((work / "source-response-v1.json").read_text())
    add_response = json.loads((work / "add-response-v1.json").read_text())
    current_response = json.loads((work / "current-response-v1.json").read_text())
    preflight = json.loads((work / "slide-preflight-v1.json").read_text())
    source = ET.parse(work / "source-v1.xml").getroot()
    current = ET.parse(work / "current-v1.xml").getroot()
    source_ns = source.tag.split("}")[0] + "}"
    current_ns = current.tag.split("}")[0] + "}"
    source_slides = source.findall(source_ns + "slide")
    current_slides = current.findall(current_ns + "slide")
    new_slide = current_slides[-1]
    text = visible_text(new_slide)
    all_text = visible_text(current)
    checks = []

    def check(name, passed, detail):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    check("preflight_pass", preflight["status"] == "PASS" and preflight["checks_passed"] == preflight["checks_total"] == 31 and not preflight["failures"], f"{preflight['checks_passed']}/{preflight['checks_total']}")
    check("baseline_revision", source_response.get("data", {}).get("revision_id") == 47, source_response.get("data", {}).get("revision_id"))
    check("write_response", add_response.get("ok") is True and add_response.get("data", {}).get("slide_id") == "pgd" and add_response.get("data", {}).get("revision_id") == 48, add_response.get("data"))
    check("readback_response", current_response.get("ok") is True and current_response.get("data", {}).get("revision_id") == 48, current_response.get("data", {}).get("revision_id"))
    check("page_count_and_id", len(current_slides) == 86 and new_slide.attrib.get("id") == "pgd", {"pages": len(current_slides), "last": new_slide.attrib.get("id")})
    def without_tail(element):
        copied = copy.deepcopy(element)
        copied.tail = None
        return ET.tostring(copied)

    unchanged = len(source_slides) == 85 and all(without_tail(source_slides[i]) == without_tail(current_slides[i]) for i in range(85))
    check("first_85_pages_unchanged", unchanged, 85)
    check("single_title", all_text.count("HistGB 点估计更好，但 paired 差异未显著") == 1, all_text.count("HistGB 点估计更好，但 paired 差异未显著"))
    required = [
        "RK08 · RETROSPECTIVE HISTGB PAIRED DIAGNOSTIC · FROZEN PREDICTIONS",
        "84/84 + 33/33 · VERIFIED",
        "sequence-OOD = 1336 constructs / 1110 clusters · all − histgb_all",
        "frozen predictions · no refit / no selection · 2,000 cluster bootstraps + Holm",
        "−0.0273", "95% CI [−0.0905, +0.0326] · Holm p=0.405",
        "+0.0988", "95% CI [−0.0510, +0.2521] · Holm p=0.396",
        "84/84 · 33/33", "raw-input recompute · paired bootstrap reproduced",
        "4.0887", "0.1921", "0.0103", "3.9900", "0.2194", "0.0324",
        "Full-proxy ridge · primary", "4.1143", "0.2179", "0.0117",
        "HistGB 两项点估计更优；显著性只由上方 paired bootstrap 判断",
        "POINT ESTIMATE · HistGB", "INFERENCE · UNRESOLVED",
        "2/2 CI 跨零 · 不宣称任一方显著胜出", "ORIGINAL GATE · UNCHANGED",
        "retrospective · 非新预注册门禁", "NO MECHANISM WIN",
        "结论 · 强特征 baseline 不可省略", "统计上未分辨胜负",
        "边界 · retrospective，非预注册门禁", "RK-G1 未通过 · 生成器未授权 · SOTA 未支持",
        "Evidence: independent 84/84 + finalization 33/33 + paper 35/35 · GitHub 3742a843",
    ]
    for value in required:
        check(f"visible:{value}", value in text, value)
    note = next((element for element in new_slide.iter() if element.tag.endswith("}note") or element.tag == "note"), None)
    note_text = visible_text(note) if note is not None else ""
    check("speaker_note", "事后公平性诊断" in note_text and "−0.027289" in note_text and "+0.098795" in note_text and "84/84" in note_text and "33/33" in note_text and "35/35" in note_text, len(note_text))
    failures = [row for row in checks if not row["pass"]]
    report = {
        "protocol": "a8_rk08_histgb_slide_verification_v1",
        "status": "PASS" if not failures else "FAIL",
        "presentation": "WB1KsYGualerMUddEzMcCw1En0g",
        "url": "https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g",
        "baseline_revision": 47,
        "current_revision": current_response.get("data", {}).get("revision_id"),
        "baseline_pages": 85,
        "current_pages": len(current_slides),
        "new_slide_id": new_slide.attrib.get("id"),
        "first_85_pages_unchanged": unchanged,
        "source_sha256": sha256(work / "source-v1.xml"),
        "current_sha256": sha256(work / "current-v1.xml"),
        "candidate_sha256": sha256(work / "slide-86-histgb-v1.xml"),
        "checks": checks,
        "checks_passed": len(checks) - len(failures),
        "checks_total": len(checks),
        "failures": failures,
    }
    (work / "slide-verification-v1.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "pages": report["current_pages"], "slide_id": report["new_slide_id"], "first_85_pages_unchanged": unchanged}, indent=2))
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
