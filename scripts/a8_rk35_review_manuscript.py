#!/usr/bin/env python3
"""Independent audit of the RK35 manuscript section against the frozen result JSON
and actual artifact hashes. Verifies every rendered primary/absolute value, the
decision string, SHAs, section ordering and prior-content integrity."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

LABEL = {"trunc_vs_simple": "trunc−simple", "exact_vs_trunc": "exact−trunc"}
MODEL = {"ridge": "Ridge", "histgb": "HistGB"}
METRIC = {"spearman_effect": "Spearman", "mse_improvement": "MSE improvement"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manuscript", type=Path, required=True)
    ap.add_argument("--result", type=Path, required=True)
    ap.add_argument("--protocol", type=Path, required=True)
    ap.add_argument("--independent", type=Path, required=True)
    ap.add_argument("--comparison", type=Path, required=True)
    ap.add_argument("--closeout", type=Path, required=True)
    ap.add_argument("--preflight", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    text = args.manuscript.read_text()
    result = json.loads(args.result.read_text())
    checks = []

    def check(name, ok, details=None):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    start = text.index("### 6.46")
    end = text.index("## 7. Discussion")
    section = text[start:end]

    for t in result["primary_tests"]:
        m, c, met = t["test"].split("__")
        row = f"| {LABEL[c]} | {MODEL[m]} | {METRIC[met]} | {t['observed_effect']:.6f} | [{t['ci95'][0]:.6f}, {t['ci95'][1]:.6f}] | {t['p_cluster_swap']:.6f} | {t['p_holm']:.6f} | {t['positive_seeds']}/10 | {'Yes' if t['pass'] else 'No'} |"
        check(f"primary_row_{t['test']}", row in section, row if row not in section else None)

    absperf = result["primary_absolute_performance"]
    armlabel = {"simple": "simple", "exact_local": "exact local d2", "cds_start_local": "CDS-start d2", "trunc_local": "trunc CDS4-45 d2", "trunc_local_d0": "trunc CDS4-45 d0"}
    for m in ("ridge", "histgb"):
        for a, lab in armlabel.items():
            v = absperf[m][a]
            row = f"| {MODEL[m]} | {lab} | {v['spearman']:.6f} | {v['mse']:.6f} |"
            check(f"abs_row_{m}_{a}", row in section, row if row not in section else None)

    check("decision_string", result["scientific_conclusion"] in section)
    check("decision_code_D1", result["decision_code"] == "D1" and "D1:" in section)
    check("gate_pass", result["consistency_gate"]["pass"] is True)
    check("fit_accounting_text", "300 new fits" in section and "500 evaluated fits" in section)
    check("table25", "**Table 25**" in section)
    check("table26", "**Table 26**" in section)
    check("anchor", "#sec-6-46" in section)
    check("no_chinese_in_section", not any("\u4e00" <= ch <= "\u9fff" for ch in section))

    sha_map = {
        "protocol": (args.protocol, "a26ec02a1f5a7fd8b83f9764ed98ac30c50a71a79d39bb4b27e082d2216b1f7b"),
        "result": (args.result, "c811bb6e3481f8450b600687e9bb9f9fa849f8d8c3c3c71b55d44ed71f4d5651"),
        "independent": (args.independent, "d037542df5ee40e47e26f1c368acb5eb5070c6d23f18c168503b609487d820a6"),
        "reproduction": (args.comparison, "f8faf2b693924a45d4d8222d5eab2c4ad50c8e7033a3d77e9ea7fa2c07f9989f"),
        "closeout": (args.closeout, "99308d7fad5411f84e4a9c816622c0742e3899bc7a895118b53afc31d459f96b"),
        "preflight": (args.preflight, "0847653d4060e8016cf39384951c055445ea68cb5a049fc57d25cf4ea0e6be5c"),
    }
    for label, (path, expected) in sha_map.items():
        actual = sha256(path)
        check(f"sha_{label}_matches_file", actual == expected, {"actual": actual, "expected": expected})
        check(f"sha_{label}_in_manuscript", expected in section)

    check("section_order", text.index("### 6.44") < text.index("### 6.45") < text.index("### 6.46") < text.index("## 7. Discussion"))
    check("prior_6_45_anchor_intact", "#sec-6-45" in text)
    check("independent_pass_39", json.loads(args.independent.read_text())["checks_passed"] == 39)
    check("comparison_pass_12", json.loads(args.comparison.read_text())["checks_passed"] == 12)
    check("closeout_pass_21", json.loads(args.closeout.read_text())["checks_passed"] == 21)

    report = {
        "schema": "a8-rk35-manuscript-review-v1",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "manuscript_sha256": sha256(args.manuscript),
        "manuscript_lines": len(text.splitlines()),
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