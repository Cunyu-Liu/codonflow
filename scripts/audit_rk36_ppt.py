#!/usr/bin/env python3
"""Audit RK36 PPT pages 170-173 against the frozen feasibility result.
Parses the readback content extract; checks Table 27 matrix cell-by-cell,
counts, page numbers, nav labels, SHA anchors and absence of emoji."""
from __future__ import annotations
import json, re
from pathlib import Path

HERE = Path(__file__).parent
REQ_ORDER = ["R1_independent_study_host", "R2_full_cds_per_variant", "R3_native_variant_specific_5utr",
             "R4_fixed_protein_synonymous_library", "R5_protein_identity_family_map",
             "R6_fresh_continuous_outcome", "R7_isolation_and_provenance"]
DS_LABEL = {"kudla_2009_gfp": "Kudla 2009 GFP (E. coli)", "boel_2016_nesg6348": "Boel 2016 (E. coli BL21)",
            "mordstein_2020_hek293": "Mordstein 2020 (HEK293)", "kelsic_2016_mage_infA": "Kelsic 2016 MAGE infA"}


def parse_slides(txt):
    slides = {}
    cur = None
    for line in txt.splitlines():
        m = re.match(r'## slide (\d+) id="(\w+)"', line)
        if m:
            cur = m.group(2)
            slides[cur] = {"num": int(m.group(1)), "lines": []}
        elif cur:
            slides[cur]["lines"].append(line)
    return slides


def table_matrix(lines):
    rows = {}
    for line in lines:
        m = re.search(r'r(\d+)c(\d+) id="\w+"[^:]*: "(.*)"', line)
        if m:
            r, c, v = int(m.group(1)), int(m.group(2)), m.group(3)
            rows.setdefault(r, {})[c] = v
    return rows


def all_text(lines):
    return "\n".join(re.findall(r'"([^"]*)"', "\n".join(lines)))


def main():
    res = json.loads((HERE / "rk36_feasibility_result_v1.json").read_text())
    indep = json.loads((HERE / "rk36_feasibility_independent_v1.json").read_text())
    slides = parse_slides((HERE / "rk36_content.txt").read_text())
    checks = []

    def ck(name, ok, details=None):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    ck("four_pages_present", set(slides) >= {"pSL", "pSy", "pSC", "pSx"}, {"ids": list(slides)})
    ck("page_numbers", [slides[s]["num"] for s in ("pSL", "pSy", "pSC", "pSx")] == [170, 171, 172, 173])

    # Table 27 matrix on pSy (slide 171)
    mat = table_matrix(slides["pSy"]["lines"])
    body_rows = {r: mat[r] for r in mat if r >= 2}
    ck("matrix_row_count", len(body_rows) == 4, {"rows": len(body_rows)})
    label_to_row = {body_rows[r][1]: r for r in body_rows}
    for ds, label in DS_LABEL.items():
        d = res["datasets"][ds]
        expected = ["Pass" if d["requirements"][rq]["verdict"] == "PASS" else "Fail" for rq in REQ_ORDER]
        expected.append("Yes" if d["qualifying"] else "No")
        r = label_to_row.get(label)
        rendered = [body_rows[r][c] for c in range(2, 10)] if r else None
        ck(f"matrix_match_{ds}", rendered == expected, {"rendered": rendered, "expected": expected})

    t170 = all_text(slides["pSL"]["lines"])
    t171 = all_text(slides["pSy"]["lines"])
    t172 = all_text(slides["pSC"]["lines"])
    t173 = all_text(slides["pSx"]["lines"])
    ck("p170_zero_qualifying", '"0"' in "\n".join(slides["pSL"]["lines"]) and "QUALIFYING" in t170)
    ck("p170_decision_3_2", "3 → 2" in t170)
    ck("p171_title_0_4", "0 / 4" in t171)
    ck("p171_no_utr_column", "no 5'UTR column" in t171)
    ck("p172_rk37", "RK37" in t172 and "RiboMIMO" in t172)
    ck("p172_branch_pivot", "branch 3 → branch 2" in t172)
    ck("p172_rk_g1_false", "RK-G1" in t172 and "false" in t172)
    ck("p173_independent_24_24", "24 / 24" in t173 and indep["checks_passed"] == 24)
    ck("p173_manuscript_32_32", "32 / 32" in t173)
    ck("p173_project_455", "455" in t173 and "455 / 1 / 0" in t173)
    ck("p173_freeze_commit", "7942d6a9" in t173)
    ck("p173_result_sha", "9b02373b460a" in t173)
    ck("p173_boundary", "no transport effect, SOTA or mechanism claim" in t173)
    # nav labels + no emoji across all four
    joined = t170 + t171 + t172 + t173
    ck("nav_label_present", joined.count("A8 / RK36 / FEASIBILITY & PIVOT") == 4)
    emoji = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF]")
    ck("no_emoji", not emoji.search(joined))
    ck("no_chinese", not any("\u4e00" <= ch <= "\u9fff" for ch in joined))

    report = {
        "schema": "a8-rk36-ppt-audit-v1",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "pages": {"pSL": 170, "pSy": 171, "pSC": 172, "pSx": 173},
        "checks_passed": sum(c["pass"] for c in checks), "checks_total": len(checks), "checks": checks,
    }
    (HERE / "rk36_ppt_audit_v1.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, indent=2))
    if report["status"] != "PASS":
        print(json.dumps([c for c in checks if not c["pass"]], indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()