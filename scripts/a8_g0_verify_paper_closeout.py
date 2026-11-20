#!/usr/bin/env python3
"""Independently verify the exact RK-G0 manuscript increment and evidence anchors."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

MARKER = "Bounded RK-G0 readiness and unified cost ledger"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = ap.parse_args()
    root = Path(args.root)
    paper = root / "paper/CodonFlow_preprint_A8.md"
    update_path = root / "paper/a8_g0_closeout_paper_update_v30.json"
    update = load(update_path)
    protocol_path = root / "configs/a8_g0_closeout_protocol_v2.json"
    prod_path = root / "audits/20261120/RK06/g0_unified_cost_closeout_v2.json"
    ind_path = root / "audits/20261120/RK06/g0_unified_cost_closeout_independent_v1.json"
    final_path = root / "audits/20261120/RK06/g0_unified_cost_closeout_finalization_v1.json"
    correction_path = root / "audits/20261120/RK06/g0_closeout_correction_v1.json"
    unit_path = root / "audits/20261120/RK06/g0_closeout_targeted_tests_v1.console.log"
    prod, ind, final, correction = map(load, [prod_path, ind_path, final_path, correction_path])
    new = paper.read_text()
    base_path = Path(update["base_snapshot"])
    base = base_path.read_text()
    section = update["section_markdown"]
    anchors = update["anchor_markdown"]
    checks, facts = [], []

    def check(name, passed, detail=None):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    def fact(name, passed, detail=None):
        facts.append({"name": name, "pass": bool(passed), "detail": detail})

    check("base_snapshot_sha", sha(base_path) == update["base_sha256"])
    check("new_paper_sha", sha(paper) == update["new_sha256"])
    check("production_sha", update["production_sha256"] == sha(prod_path))
    check("independent_sha", update["independent_sha256"] == sha(ind_path))
    check("finalization_sha", update["finalization_sha256"] == sha(final_path))
    check("correction_sha", update["correction_sha256"] == sha(correction_path))
    check("protocol_sha", update["protocol_sha256"] == sha(protocol_path) == prod["protocol_sha256"])
    check("unit_log_sha", update["unit_test_log_sha256"] == sha(unit_path))
    check("independent_binds_production", ind["production_sha256"] == sha(prod_path))
    check("science_pass", prod["overall_pass"] and ind["all_pass"] and final["status"] == "PASS_BOUNDED_G0_CLOSEOUT")
    check("production_179_checks", prod["technical_passed_checks"] == prod["technical_check_count"] == 179)
    check("independent_357_checks", ind["passed_checks"] == ind["check_count"] == 357)
    check("independent_zero_delta", ind["max_numeric_delta"] == 0.0)
    check("finalization_6_checks", final["passed_checks"] == final["check_count"] == 6)
    check("unit_9_tests", "9 passed" in unit_path.read_text())
    check("correction_binds_final", correction["artifacts"]["v2_production"]["sha256"] == sha(prod_path)
          and correction["artifacts"]["independent"]["sha256"] == sha(ind_path)
          and correction["artifacts"]["tests"]["sha256"] == sha(unit_path))
    check("zero_new_compute", correction["side_effects"]["baseline_reruns"] == 0
          and correction["side_effects"]["new_scorer_calls"] == 0
          and not correction["side_effects"]["generator_training_started"])
    check("g0_bounded_only", prod["g0_status"] == "PASS_BOUNDED_DATA_BASELINE_EVALUATION_READY"
          and update["g0_status"] == prod["g0_status"])
    check("scientific_gate_unchanged", not prod["boundaries"]["rk_g1_passed"]
          and not prod["boundaries"]["generator_training_authorized"]
          and not update["rk_g1_passed"] and not update["generator_training_authorized"])
    a7 = root / "paper/CodonFlow_preprint_A7.md"
    check("a7_unchanged", (update["a7_sha256"] is None and not a7.exists())
          or (a7.exists() and sha(a7) == update["a7_sha256"]))
    check("single_section_and_anchors", new.count(MARKER) == 1 and new.count(section) == 1 and new.count(anchors) == 1)
    check("section_sha", hashlib.sha256(section.encode()).hexdigest() == update["section_sha256"])
    restored = new.replace(section, "", 1).replace(anchors, "", 1)
    check("exact_base_restoration", restored == base)
    snapshot = Path(update["snapshot_directory"])
    for label, item in update["evidence"].items():
        original = Path(item["path"])
        copied = snapshot / original.name
        check("evidence_hash_" + label, item["sha256"] == sha(original))
        check("snapshot_hash_" + label, copied.exists() and sha(copied) == item["sha256"])

    fact("source_and_row_counts", str(prod["summary"]["source_count"]) in section
         and str(prod["summary"]["row_count"]) in section and str(len(prod["gate_results"])) in section)
    measured = [row for row in prod["cost_matrix"] if row["metrics"].get("wall_clock_s") is not None]
    fact("thirteen_measured_rows", len(measured) == 13)
    for row in measured:
        prefix = f"| {row['method']} |"
        matching = [line for line in section.splitlines() if line.startswith(prefix)]
        fact(f"row_unique:{row['row_id']}", len(matching) == 1)
        if len(matching) != 1:
            continue
        line = matching[0]
        for metric in ["wall_clock_s", "training_s", "generation_or_inference_s", "scoring_s"]:
            value = row["metrics"].get(metric)
            if value is not None:
                fact(f"value:{row['row_id']}:{metric}", repr(value) in line, repr(value))
        m = row["metrics"]
        extra = m.get("unique_scorer_calls", m.get("actual_outputs", m.get("runs")))
        if extra is not None:
            fact(f"extra:{row['row_id']}", str(extra) in line, str(extra))
    rows = {row["row_id"]: row for row in prod["cost_matrix"]}
    for row_id in ["inherited_codongpt", "inherited_gemorna", "inherited_cai_greedy",
                   "inherited_uniform_synonymous", "inherited_lineardesign_scan"]:
        fact(f"inherited_output:{row_id}", str(rows[row_id]["metrics"]["actual_outputs"]) in section)
        fact(f"inherited_cost_null:{row_id}", rows[row_id]["metrics"]["wall_clock_s"] is None
             and bool(rows[row_id]["unavailable_reasons"]["wall_clock_s"]))
    fact("rnarl_qc_pairs_not_generation", str(rows["rnarl_availability"]["metrics"]["qc_pairs"]) in section
         and "not valid official-model generations" in section)
    fact("not_run_states", "COformer and CHARMING remain explicitly NOT_RUN" in section)
    fact("cdgb_unresolved", "CDGB source identity remains unresolved" in section)
    fact("production_count_visible", "**179/179 checks**" in section)
    fact("independent_count_visible", "**357/357 checks**" in section)
    fact("finalization_count_visible", "**6/6 checks**" in section)
    fact("tests_visible", "**9/9**" in section)
    fact("zero_delta_visible", repr(ind["max_numeric_delta"]) in section)
    fact("v1_failure_retained", "lineardesign_unique_sequences" in section and "ten invalid pointers" in section
         and "v1 protocol/log and correction record are retained" in section)
    fact("zero_compute_visible", "reran no baseline, added zero scorer calls, and started no generator training" in section)
    fact("feasibility_scope", "FEASIBILITY_CLOSED_NOT_FULL_REMAP" in section
         and "full UTR–CDS remap" in section and "five-species VeloHARMO matrices" in section)
    fact("no_global_cost_sum", "not summed or ranked across mixed or overlapping scopes" in section
         and prod["summary"]["global_wall_clock_sum"] is None)
    fact("null_not_zero", "it is never zero" in section)
    fact("open_boundaries", all(text in section for text in [
        "External dense coverage", "time-matched evaluation", "complete SOTA", "RNARL official-model reproduction",
        "functional-untouched evaluation", "wet-lab validation", "RK-G1 remain unclosed",
        "generator training remains unauthorized", "non-submittable"
    ]))
    all_checks = checks + facts
    report = {
        "schema": "a8-g0-closeout-paper-verification-v1",
        "overall_pass": all(c["pass"] for c in all_checks),
        "status": "PASS" if all(c["pass"] for c in all_checks) else "FAIL",
        "base_version": update["base_version"],
        "new_version": update["new_version"],
        "base_sha256": update["base_sha256"],
        "new_sha256": sha(paper),
        "section_heading": update["section_heading"],
        "exact_base_restoration": restored == base,
        "check_counts": {"passed": sum(c["pass"] for c in all_checks), "total": len(all_checks)},
        "checks": checks,
        "candidate_facts": facts,
    }
    output = root / f"paper/a8_g0_closeout_paper_verification_{update['new_version']}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "overall_pass": report["overall_pass"],
                      "check_counts": report["check_counts"], "output": str(output)}, indent=2))
    if not report["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
