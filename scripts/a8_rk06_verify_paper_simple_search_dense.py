#!/usr/bin/env python3
"""Verify the exact v27 to v28 RK06 manuscript increment and all inserted values."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper/CodonFlow_preprint_A8.md"
AUDIT = ROOT / "audits/20261120/RK06"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fmt(value):
    return f"{float(value):.9f}"


def pfmt(value):
    return f"{float(value):.8f}"


def main():
    update_path = ROOT / "paper/a8_rk06_simple_search_dense_paper_update.json"
    update = json.loads(update_path.read_text())
    claims_path = AUDIT / "simple_search_dense_claims_v1.json"
    finalization_path = AUDIT / "simple_search_dense_finalization_v1.json"
    independent_path = AUDIT / "simple_search_dense_independent_v1.json"
    production_path = AUDIT / "simple_search_dense_unique18_v1.json"
    protocol_path = ROOT / "configs/a8_rk06_simple_search_dense_unique18_protocol_v1.json"
    claims = json.loads(claims_path.read_text())
    finalization = json.loads(finalization_path.read_text())
    independent = json.loads(independent_path.read_text())
    text = PAPER.read_text()
    base_path = ROOT / "paper/snapshots/rk06_simple_search_dense_v28/CodonFlow_preprint_A8_v27.md"
    base = base_path.read_text()
    checks = []
    facts = []

    def check(name, condition, detail=None):
        row = {"check": name, "pass": bool(condition)}
        if detail is not None:
            row["detail"] = detail
        checks.append(row)

    def fact(name, condition):
        facts.append({"fact": name, "pass": bool(condition)})

    check("base_v27_sha", sha256(base_path) == update["base_sha256"] == "c745b3e73b7d9f380f7c0ce326cc5fba2cfae769273b2e58f606a73dba9e0952")
    check("new_v28_sha", sha256(PAPER) == update["new_sha256"])
    check("claims_sha", update["claims_sha256"] == sha256(claims_path))
    check("finalization_sha", update["finalization_sha256"] == sha256(finalization_path))
    check("independent_sha", update["independent_sha256"] == sha256(independent_path))
    check("finalization_pass", finalization["overall_pass"] and claims["finalization_overall_pass"])
    check("independent_pass", independent["overall_pass"])
    check("single_section", text.count(update["section_heading"]) == 1 and text.count("### 6.24 ") == 1)
    start = text.index(update["section_heading"])
    end = text.index("## 7. Discussion", start)
    section = text[start:end]
    check("section_sha", hashlib.sha256(section.encode()).hexdigest() == update["section_sha256"])
    restored = text[:start] + text[end:]
    marker = "A7 is retained as the prior manuscript snapshot."
    inserted_anchor_block = update["anchor_rows"] + marker
    check("anchor_block_present_once", restored.count(inserted_anchor_block) == 1)
    restored = restored.replace(inserted_anchor_block, "\n" + marker, 1)
    check("exact_v27_restoration", restored == base)
    for label, path in [
        ("protocol", protocol_path), ("production", production_path), ("independent", independent_path),
        ("finalization", finalization_path), ("claims", claims_path),
    ]:
        check(f"evidence_anchor_{label}", f"`{sha256(path)}`" in text)
    snapshot = Path(update["snapshot"])
    for path in [claims_path, finalization_path, production_path, independent_path, protocol_path]:
        check(f"snapshot_{path.name}", sha256(snapshot / path.name) == sha256(path))
    check("non_submittable_status", "non-submittable working manuscript" in text and not update["manuscript_submittable"])
    check("scientific_gate_open", not update["scientific_gate_passed"] and not update["rk_g1_closed"])

    fact("216_runs", "216 runs" in section)
    fact("108000_scored", "108,000 scored sequences" in section)
    fact("dense_formula", "sum(HV_b for b=1,...,499)/499" in section and "B=500" in section)
    fact("normalized_hv_unclipped", "not clipped to [0,1]" in section)
    fact("no_synthetic_origin", "No synthetic origin" in section and "zero-filled missing budget" in section)
    fact("statistical_unit", "The record was the statistical unit" in section)
    fact("resampling_counts", "20,000 resamples" in section and "20,000 draws" in section)
    fact("six_primary_rows", sum(1 for row in claims["primary_tests"] if f"| {row['method']} |" in section) >= 6)
    for index, row in enumerate(claims["method_summary"]):
        for key in ["mean_dense_auc", "mean_hv_B50", "mean_hv_B100", "mean_hv_B500", "sum_wall_clock_seconds"]:
            fact(f"method_{index}_{key}", fmt(row[key]) in section)
    for index, row in enumerate(claims["primary_tests"]):
        ci = f"[{fmt(row['ci95'][0])}, {fmt(row['ci95'][1])}]"
        fact(f"primary_{index}_effect", fmt(row["effect"]) in section)
        fact(f"primary_{index}_ci", ci in section)
        fact(f"primary_{index}_holm", pfmt(row["holm_p"]) in section)
        fact(f"primary_{index}_decision", f"| {'yes' if row['supported_advantage'] else 'no'} |" in section)
    for index, row in enumerate(claims["bidirectional_strict_dominance_B500"]):
        fact(f"dominance_{index}_a", fmt(row["mean_fraction_a_strictly_dominated_by_b"]) in section)
        fact(f"dominance_{index}_b", fmt(row["mean_fraction_b_strictly_dominated_by_a"]) in section)
    fact("independent_counts", f"**{independent['check_counts']['passed']}/{independent['check_counts']['total']} checks**" in section)
    fact("finalization_counts", f"**{finalization['check_counts']['passed']}/{finalization['check_counts']['total']} checks**" in section)
    fact("external_dense_null", "dense AUC remains null" in section)
    fact("no_time_matched_external", "not time-matched" in section)
    fact("no_untouched", "no untouched24 record" in section)
    fact("no_functional", "functional-untouched assay row" in section and "functional label" in section)
    fact("no_generator_training", "it trained no generator" in section.lower())
    fact("explicit_boundaries", "does not establish functional effectiveness, CodonFlow-RK improvement, external SOTA, RK-G1 closure or generator-training readiness" in section)
    fact("manuscript_remains_non_submittable", "The manuscript remains non-submittable" in section)
    overall = all(row["pass"] for row in checks) and all(row["pass"] for row in facts)
    report = {
        "schema": "a8-rk06-simple-search-dense-paper-verification-v28",
        "overall_pass": overall,
        "status": "PAPER_V28_PASS" if overall else "PAPER_V28_FAIL",
        "manuscript": str(PAPER),
        "manuscript_sha256": sha256(PAPER),
        "base_sha256": sha256(base_path),
        "section_sha256": hashlib.sha256(section.encode()).hexdigest(),
        "checks": checks,
        "candidate_facts": facts,
        "check_counts": {"total": len(checks), "passed": sum(row["pass"] for row in checks), "failed": sum(not row["pass"] for row in checks)},
        "candidate_fact_counts": {"total": len(facts), "passed": sum(row["pass"] for row in facts), "failed": sum(not row["pass"] for row in facts)},
        "exact_v27_restoration": restored == base,
        "manuscript_submittable": False,
        "scientific_gate_passed": False,
        "rk_g1_closed": False,
    }
    output = ROOT / "paper/a8_rk06_simple_search_dense_paper_verification_v28.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "overall_pass": overall, "check_counts": report["check_counts"],
                      "candidate_fact_counts": report["candidate_fact_counts"], "manuscript_sha256": report["manuscript_sha256"]}))
    if not overall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
