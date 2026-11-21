#!/usr/bin/env python3
"""Independent review of RK36 manuscript section 6.47: rendered Table 27 and counts
must match the frozen feasibility result; SHA anchors must match actual files;
section order, prior content and language are checked."""
from __future__ import annotations
import argparse, hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path

REQ_ORDER = ["R1_independent_study_host", "R2_full_cds_per_variant", "R3_native_variant_specific_5utr",
             "R4_fixed_protein_synonymous_library", "R5_protein_identity_family_map",
             "R6_fresh_continuous_outcome", "R7_isolation_and_provenance"]
DS_ORDER = ["kudla_2009_gfp", "boel_2016_nesg6348", "mordstein_2020_hek293", "kelsic_2016_mage_infA"]
DS_LABEL = {"kudla_2009_gfp": "Kudla 2009 GFP (E. coli)", "boel_2016_nesg6348": "Boel 2016 (E. coli BL21)",
            "mordstein_2020_hek293": "Mordstein 2020 (HEK293)", "kelsic_2016_mage_infA": "Kelsic 2016 MAGE infA"}


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manuscript", type=Path, required=True)
    ap.add_argument("--result", type=Path, required=True)
    ap.add_argument("--protocol", type=Path, required=True)
    ap.add_argument("--independent", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    text = args.manuscript.read_text()
    res = json.loads(args.result.read_text())
    sec = text.split("### 6.47", 1)[1].split("## 7. Discussion", 1)[0]
    checks = []

    def ck(name, ok, details=None):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    # parse Table 27 rows
    table_rows = {}
    for line in sec.splitlines():
        if line.startswith("| ") and ("Pass" in line or "Fail" in line) and "Qualifies" not in line and "---" not in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 9:
                table_rows[cells[0]] = cells[1:]
    ck("table27_row_count", len(table_rows) == 4, {"rows": list(table_rows)})
    for ds in DS_ORDER:
        label = DS_LABEL[ds]
        d = res["datasets"][ds]
        expected = ["Pass" if d["requirements"][r]["verdict"] == "PASS" else "Fail" for r in REQ_ORDER]
        expected.append("Yes" if d["qualifying"] else "No")
        ck(f"table27_match_{ds}", table_rows.get(label) == expected, {"rendered": table_rows.get(label), "expected": expected})
    # failed requirements lines
    for ds in DS_ORDER:
        frag = ", ".join(res["datasets"][ds]["failed_requirements"])
        ck(f"failed_line_{ds}", frag in sec)
    # missing dimensions
    for i, m in enumerate(res["missing_dimensions"]):
        ck(f"missing_dim_{i}", m in sec)
    ck("n_qualifying_zero", "0/4" in sec and res["n_qualifying_datasets"] == 0)
    ck("branch3_present", "branch-3" in sec)
    ck("branch2_pivot_present", "branch-2 pivot" in sec)
    ck("rk37_present", "RK37" in sec)
    ck("ribomimo_present", "RiboMIMO" in sec)
    # SHA anchors match actual files
    ck("protocol_sha_in_anchor", sha256(args.protocol) in sec)
    ck("result_sha_in_anchor", sha256(args.result) in sec)
    ck("independent_sha_in_anchor", sha256(args.independent) in sec)
    ck("anchor_present", "#sec-6-47" in sec)
    ck("table27_caption", "**Table 27**" in sec)
    # structure / preservation
    ck("section_order", text.index("### 6.45") < text.index("### 6.46") < text.index("### 6.47") < text.index("## 7. Discussion"))
    ck("sec_6_46_intact", "#sec-6-46" in text and "RK33_COVERAGE_RETAINS_INCREMENT_WITHIN_KUDLA_RETROSPECTIVELY" in text)
    ck("sec_6_45_intact", "#sec-6-45" in text)
    ck("no_chinese_in_section", not any("\u4e00" <= ch <= "\u9fff" for ch in sec))
    ck("non_claim_present", "no transport-effect, SOTA or mechanism claim" in sec)
    ck("rk_g1_false", "RK-G1 remains false" in sec)
    ck("independent_24_24", "24/24" in sec)

    report = {
        "schema": "a8-rk36-manuscript-review-v1",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "manuscript_sha256": sha256(args.manuscript),
        "result_sha256": sha256(args.result),
        "checks_passed": sum(c["pass"] for c in checks), "checks_total": len(checks), "checks": checks,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.report.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    tmp.replace(args.report)
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, indent=2))
    if report["status"] != "PASS":
        print(json.dumps([c for c in checks if not c["pass"]], indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()