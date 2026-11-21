#!/usr/bin/env python3
"""Audit the RK35 PPT append: page count, last-5 slide ids, rendered frozen values,
and prior-164-page content integrity (normalized text equality vs pre-append baseline)."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

D = Path(__file__).parent
NS = {"s": "https://www.larkoffice.com/sml/2.0"}


def slides(path):
    root = ET.parse(path).getroot()
    return root.findall("s:slide", NS)


def slide_text(sl):
    return "\n".join(p.text or "" for p in sl.iter() if p.tag.endswith("}p"))


def norm(sl):
    # normalized visible text (strip ids/geometry; keep text content order)
    return "|".join((p.text or "").strip() for p in sl.iter() if p.tag.endswith("}p"))


base = slides(D / "baseline_v2.xml")   # 164 pages pre-append
cur = slides(D / "readback_v3.xml")     # 169 pages post-append
checks = []


def ck(name, ok, details=None):
    checks.append({"name": name, "pass": bool(ok), "details": details})


ck("page_count_169", len(cur) == 169, {"count": len(cur)})
ck("baseline_164", len(base) == 164, {"count": len(base)})

expected_ids = ["pSw", "pSl", "pSN", "pSt", "pSX"]
last_ids = [sl.get("id") for sl in cur[-5:]]
ck("last5_ids", last_ids == expected_ids, {"last5": last_ids})

# prior 164 pages unchanged
mismatch = []
for i in range(164):
    if norm(base[i]) != norm(cur[i]):
        mismatch.append(i + 1)
ck("prior_164_unchanged", not mismatch, {"mismatch_pages": mismatch})

# RK35 rendered values
texts = {sl.get("id"): slide_text(sl) for sl in cur[-5:]}
required = {
    "pSw": ["01 / TRANSPORT QUESTION", "A8 / RK35 / COVERAGE TRANSPORT", "CDS[3:45]", "500", "GATE", "165"],
    "pSl": ["02 / FROZEN EXECUTION", "+0.984683", "[0.528853, 1.129653]", "0.000200", "+0.402747", "166"],
    "pSN": ["03 / PRIMARY DECISION", "D1", "RK33_COVERAGE_RETAINS_INCREMENT_WITHIN_KUDLA_RETROSPECTIVELY",
            "+0.735912", "[0.269426, 0.883119]", "0.011099", "+0.365595", "0.001750",
            "+0.037152", "0.356982", "4 / 4", "2 / 4", "167"],
    "pSt": ["04 / ABSOLUTE & SECONDARY", "+0.666270", "0.100223", "+0.705171", "0.094394",
            "+0.417499", "+0.668019", "-0.318413", "−0.109689", "168"],
    "pSX": ["05 / EVIDENCE & BOUNDARY", "39 / 39", "12 / 12", "21 / 21", "453",
            "99308d7fad54", "RK-G1=false", "169"],
}
for sid, needles in required.items():
    t = texts.get(sid, "")
    missing = [n for n in needles if n not in t]
    ck(f"values_{sid}", not missing, {"missing": missing})

# no emoji anywhere in RK35 pages
emoji = []
for sid, t in texts.items():
    for ch in t:
        if ord(ch) > 0x2600 and ord(ch) not in (0x2212, 0x2265, 0x2264, 0x2227, 0x2192, 0xB7, 0x2013, 0x2014, 0x394, 0x3C1, 0x2260):
            emoji.append((sid, hex(ord(ch))))
ck("no_emoji_rk35", not emoji, {"emoji": emoji})

report = {
    "schema": "a8-rk35-ppt-audit-v1",
    "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
    "presentation_id": "WB1KsYGualerMUddEzMcCw1En0g",
    "revision_id": 136,
    "page_count": len(cur),
    "rk35_pages": [{"index": 165 + i, "slide_id": sid} for i, sid in enumerate(expected_ids)],
    "checks_passed": sum(c["pass"] for c in checks),
    "checks_total": len(checks),
    "checks": checks,
}
(D / "rk35_ppt_audit_v1.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
print(json.dumps({k: v for k, v in report.items() if k != "checks"}, indent=2, ensure_ascii=False))
if report["status"] != "PASS":
    print(json.dumps([c for c in checks if not c["pass"]], indent=2, ensure_ascii=False))
    raise SystemExit(1)