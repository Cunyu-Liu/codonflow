#!/usr/bin/env python3
"""Independently verify the exact MAGE OOF comparator manuscript increment."""
import argparse
import hashlib
import json
from pathlib import Path

MARKER = "Development-only MAGE OOF comparator closure"


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path): return json.loads(Path(path).read_text())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    a = ap.parse_args()
    root = Path(a.root)
    paper = root / "paper/CodonFlow_preprint_A8.md"
    update_path = root / "paper/a8_rk03_mage_oof_comparator_paper_update.json"
    update = load(update_path)
    prod_path = root / "audits/20261120/RK03/mage_oof_comparator_closure_v2.json"
    ind_path = root / "audits/20261120/RK03/mage_oof_comparator_closure_independent_v2.json"
    correction_path = root / "audits/20261120/RK03/mage_oof_comparator_closure_correction_v1.json"
    protocol_path = root / "configs/a8_rk03_mage_oof_comparator_closure_protocol_v2.json"
    unit_path = root / "audits/20261120/RK03/mage_oof_comparator_closure_unit_tests_v4_python3.console.log"
    prod, ind, correction = load(prod_path), load(ind_path), load(correction_path)
    new = paper.read_text()
    base_path = Path(update["base_snapshot"])
    base = base_path.read_text()
    section = update["section_markdown"]
    anchors = update["anchor_markdown"]
    checks = []
    facts = []
    def check(name, passed, detail=None): checks.append({"name": name, "pass": bool(passed), "detail": detail})
    def fact(name, passed, detail=None): facts.append({"name": name, "pass": bool(passed), "detail": detail})
    check("base_snapshot_sha", sha(base_path) == update["base_sha256"])
    check("new_paper_sha", sha(paper) == update["new_sha256"])
    check("production_sha", update["production_sha256"] == sha(prod_path))
    check("independent_sha", update["independent_sha256"] == sha(ind_path))
    check("correction_sha", update["correction_sha256"] == sha(correction_path))
    check("protocol_sha", update["protocol_sha256"] == sha(protocol_path) == prod["protocol_sha256"])
    check("unit_log_sha", update["unit_test_log_sha256"] == sha(unit_path) == correction["protocol_v2"]["unit_test_log_sha256"])
    check("independent_binds_production", ind["production_report_sha256"] == sha(prod_path))
    check("production_and_independent_pass", prod["overall_pass"] and ind["overall_pass"] and all(c["pass"] for c in prod["technical_checks"] + ind["checks"]))
    check("independent_24_checks", ind["check_counts"] == {"passed": 24, "total": 24})
    unit_text = unit_path.read_text()
    check("unit_9_tests", "Ran 9 tests" in unit_text and "OK" in unit_text)
    check("correction_retained", correction["protocol_v1"]["production_report_written"] is False and len(correction["retained_implementation_failures"]) >= 4)
    check("scientific_gate_unchanged", prod["scientific_gate"] == "UNCHANGED_DEV_NO_GO_TEST_UNTOUCHED" and not prod["scientific_gate_pass"] and not prod["test_authorized"])
    check("zero_new_compute", prod["new_model_fits"] == 0 and prod["cost"]["new_scorer_calls"] == 0)
    a7 = root / "paper/CodonFlow_preprint_A7.md"
    check("a7_unchanged", (update["a7_sha256"] is None and not a7.exists()) or (a7.exists() and sha(a7) == update["a7_sha256"]))
    check("single_section_and_anchors", new.count(MARKER) == 1 and new.count(section) == 1 and new.count(anchors) == 1)
    first_anchor = "| RK03 MAGE OOF comparator protocol v2 |"
    check("anchor_table_continuous", "\n" + first_anchor in new and "\n\n" + first_anchor not in new and anchors + "\n\nA7 is retained as the prior manuscript snapshot." in new)
    check("section_sha", hashlib.sha256(section.encode()).hexdigest() == update["section_sha256"])
    restored = new.replace(section, "", 1).replace(anchors, "", 1)
    check("exact_base_restoration", restored == base)
    snapshot = Path(update["snapshot_directory"])
    for label, item in update["evidence"].items():
        original = Path(item["path"])
        copied = snapshot / original.name
        check("evidence_hash_" + label, item["sha256"] == sha(original))
        check("snapshot_hash_" + label, copied.exists() and sha(copied) == item["sha256"])
    for cid, row in prod["exploratory_comparisons"].items():
        for metric in ["delta_rmse", "delta_spearman"]:
            if metric not in row: continue
            stem = metric.split("delta_", 1)[1]
            fact(f"{cid}_{metric}_value", repr(row[metric]) in section, repr(row[metric]))
            fact(f"{cid}_{metric}_ci", repr(row[metric + "_ci95"][0]) in section and repr(row[metric + "_ci95"][1]) in section)
            fact(f"{cid}_{metric}_holm", repr(row["holm_p_" + stem]) in section)
    mean_row = prod["exploratory_comparisons"]["full_mechanism_minus_outer_train_mean"]
    fact("raw_permutation_p", repr(mean_row["permutation_p_rmse"]) in section)
    fact("model_rmse_values", repr(prod["primary_models"]["full_mechanism"]["rmse"]) in section and repr(prod["primary_models"]["outer_train_mean"]["rmse"]) in section)
    # Independently recompute the sign strings rather than trusting the updater.
    seeds = list(prod["sensitivity"])
    fact("all_three_seed_ids_present", all(s in section for s in seeds), seeds)
    for cid in ["full_mechanism_minus_rcs_only", "rcs_only_minus_intrinsic", "full_mechanism_minus_outer_train_mean"]:
        for metric in ["delta_spearman", "delta_rmse"]:
            values = [prod["sensitivity"][s]["comparisons"][cid].get(metric) for s in seeds]
            if values[0] is None: continue
            sign = "/".join("+" if v > 0 else "−" if v < 0 else "0" for v in values)
            fact(f"signs_{cid}_{metric}", sign in section, sign)
    fact("independent_count_visible", f"**{ind['check_counts']['passed']}/{ind['check_counts']['total']} checks**" in section)
    fact("unit_count_visible", "**9/9 tests**" in section)
    fact("wall_time_exact", repr(prod["cost"]["wall_seconds"]) in section)
    fact("rcs_scope_visible", "contains intrinsic features plus RCS additions" in section and "not a pure external-pretrained-model replacement" in section)
    fact("mean_spearman_boundary", "descriptive and excluded from paired inference" in section)
    fact("mechanism_boundary", "not a mechanism increment or independent confirmation" in section)
    fact("open_boundaries", all(s in section for s in ["constant-speed arm", "mature external-model replacement", "functional-untouched evaluation", "generator authorization remain open"]))
    fact("retained_v1_failure", "no v1 production report was written" in section)
    fact("non_submittable", "non-submittable working-manuscript status are unchanged" in section and update["manuscript_submittable"] is False)
    all_checks = checks + facts
    report = {
        "schema": "a8-rk03-mage-oof-comparator-paper-verification-v1",
        "overall_pass": all(c["pass"] for c in all_checks),
        "status": "PASS" if all(c["pass"] for c in all_checks) else "FAIL",
        "base_version": update["base_version"], "new_version": update["new_version"],
        "base_sha256": update["base_sha256"], "new_sha256": sha(paper),
        "section_heading": update["section_heading"],
        "exact_base_restoration": restored == base,
        "check_counts": {"passed": sum(c["pass"] for c in all_checks), "total": len(all_checks)},
        "checks": checks, "candidate_facts": facts,
    }
    output = root / f"paper/a8_rk03_mage_oof_comparator_paper_verification_{update['new_version']}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "overall_pass": report["overall_pass"], "check_counts": report["check_counts"], "output": str(output)}, indent=2))
    if not report["overall_pass"]: raise SystemExit(1)


if __name__ == "__main__": main()
