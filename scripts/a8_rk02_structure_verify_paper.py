#!/usr/bin/env python3
"""Independent exact-increment and scientific-value verification for manuscript v24."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

V23 = "a5ef4a157a3e60b91a5087c24ae71ea0c0c01ab21260057298a98426edfed0e2"
AUDIT_V23 = "5f546a314961b87470cb81ae073eec45023d28542741a04be87b91ff271bb143"
A7 = "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423"
SECTION_HEADER = "### 6.20 Fixed-GFP observed-R1 structure increment: development no-go"
ANCHOR_START = "| RK02 structure-increment frozen protocol v2 |"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    repo = args.repo.resolve()
    paper_path = repo / "paper/CodonFlow_preprint_A8.md"
    audit_path = repo / "paper/a8_rk_paper_sync_audit.json"
    update_path = repo / "paper/a8_rk02_structure_paper_update.json"
    production_path = repo / "audits/20261118/RK02/mordstein_structure_increment_dev_v2.json"
    independent_path = repo / "audits/20261118/RK02/mordstein_structure_increment_dev_independent_v2.json"
    final_path = repo / "audits/20261118/RK02/mordstein_structure_increment_dev_finalization_v2.json"
    unit_path = repo / "audits/20261118/RK02/mordstein_structure_increment_unit_tests_v2.json"
    failure_path = repo / "audits/20261118/RK02/mordstein_structure_increment_dev_v1_failed_preflight.json"
    production = json.loads(production_path.read_text())
    independent = json.loads(independent_path.read_text())
    final = json.loads(final_path.read_text())
    unit = json.loads(unit_path.read_text())
    failure = json.loads(failure_path.read_text())
    update = json.loads(update_path.read_text())
    audit = json.loads(audit_path.read_text())
    current = paper_path.read_text()
    snapshot = repo / "paper/snapshots/rk02_structure_v24"
    old = (snapshot / "CodonFlow_preprint_A8_v23.md").read_text()
    checks = []
    def check(name, condition, details=None):
        checks.append({"name": name, "pass": bool(condition), "details": details})
    check("v23_snapshot_hash", sha256(snapshot / "CodonFlow_preprint_A8_v23.md") == V23)
    check("v23_audit_snapshot_hash", sha256(snapshot / "a8_rk_paper_sync_audit_v23.json") == AUDIT_V23)
    check("a7_unchanged", sha256(snapshot / "CodonFlow_preprint_A7.md") == sha256(repo / "paper/CodonFlow_preprint_A7.md") == A7)
    check("single_new_section", current.count(SECTION_HEADER) == 1)
    start = current.index(SECTION_HEADER)
    end = current.index("## 7. Discussion", start)
    section = current[start:end]
    without_section = current[:start] + current[end:]
    check("single_anchor_block", without_section.count(ANCHOR_START) == 1)
    astart = without_section.index(ANCHOR_START)
    aend = without_section.index("A7 is retained as the prior manuscript snapshot.", astart)
    anchors = without_section[astart:aend]
    reconstructed = without_section[:astart] + without_section[aend:]
    check("all_v23_text_preserved_exactly", reconstructed == old)
    check("section_precedes_discussion", start < end)
    check("production_independent_final_chain", production["status"] == "DEV_STRUCTURE_INCREMENT_NO_GO_PENDING_INDEPENDENT" and independent["status"] == "PASS" and final["status"] == "PASS_RK02_MORDSTEIN_STRUCTURE_INCREMENT_DEV")
    check("final_21_checks", final["checks_passed"] == final["checks_total"] == 21)
    check("independent_12_checks", independent["checks_passed"] == independent["checks_total"] == 12)
    check("unit_12_tests", unit["status"] == "PASS" and unit["passed"] == 12 and unit["failed"] == 0)
    check("retained_v1_preflight_no_result", failure["status"] == "FAILED_PREFLIGHT_NO_SCIENTIFIC_RESULT" and failure["n_variants_processed"] == 0 and not failure["structure_features_computed"] and not failure["models_fitted"])
    check("scientific_no_go", final["scientific_result"] == "FIXED_GFP_OBSERVED_R1_STRUCTURE_INCREMENT_NO_GO_DEVELOPMENT_ONLY" and final["structure_increment_pass"] is False and production["structure_increment_pass"] is False)
    check("population_152", production["n_variants"] == independent["n_variants"] == final["n_variants"] == 152 and "same 152 fixed-GFP" in section)
    for model, label in [("depth_only", "depth only"), ("simple", "depth + simple sequence"), ("simple_plus_structure", "depth + simple sequence + observed-R1 structure")]:
        metrics = production["model_metrics"][model]
        row = f"| {label} | {metrics['spearman']:.9f} | {metrics['pearson']:.9f} | {metrics['mse']:.9f} | {metrics['rmse']:.9f} |"
        check("metric_row_" + model, row in section, row)
    for endpoint, label in [("delta_spearman", "delta Spearman"), ("delta_mse", "delta MSE")]:
        effect = production["primary_effects"][endpoint]
        row = f"| {label} | {effect['observed']:.9f} | [{effect['ci95_percentile'][0]:.9f}, {effect['ci95_percentile'][1]:.9f}] | {effect['permutation_p_two_sided']:.9f} | {effect['holm_p']:.3f} |"
        check("effect_row_" + endpoint, row in section, row)
        check("resamples_" + endpoint, effect["bootstrap_resamples"] == effect["permutation_resamples"] == 20000)
    check("development_not_confirmatory", "retrospective, development-only" in section and "not an independent confirmatory test" in section)
    check("cai_reference_caveat", "embedded whitespace" in section and "reference-quality limitation" in section and "61 sense-codon weights" in section)
    check("negative_interpretation_bounded", "does not show that RNA structure is universally uninformative" in section)
    check("no_untouched_ood_generator_sota", all(text in section for text in ["do not use functional untouched data", "impute the central unobserved CDS", "protein/study OOD transfer", "close RK-G1", "authorize generator training", "support a SOTA claim"]))
    for name, path in [("protocol", repo / "configs/a8_rk02_mordstein_structure_increment_protocol_v2.json"), ("production", production_path), ("independent", independent_path), ("finalization", final_path), ("unit", unit_path), ("failure", failure_path)]:
        check("anchor_hash_" + name, sha256(path) in anchors, sha256(path))
    check("update_paper_hash", update["paper_sha256"] == sha256(paper_path))
    check("update_audit_hash", update["audit_sha256"] == sha256(audit_path))
    check("audit_output_hash", audit["output_sha256"] == sha256(paper_path))
    check("audit_base_v23", audit["base_v23_paper_sha256"] == V23 and audit["base_v23_audit_sha256"] == AUDIT_V23)
    check("audit_generated_sections", audit["generated_sections"][-2:] == [SECTION_HEADER[4:], "8.1 RK02 structure-increment evidence anchors"])
    check("audit_last_increment", audit["last_increment"]["paper_sha256"] == sha256(paper_path) and audit["last_increment"]["finalization_sha256"] == sha256(final_path) and audit["last_increment"]["submittable"] is False)
    check("working_manuscript_not_submittable", "non-submittable working manuscript" in current and update["submittable"] is False)
    passed = sum(c["pass"] for c in checks)
    report = {
        "schema": "a8.rk02.structure_paper_verification.v1", "status": "PASS_RK02_STRUCTURE_PAPER_UPDATE" if passed == len(checks) else "FAILED",
        "checks_passed": passed, "checks_total": len(checks), "checks": checks,
        "paper_sha256": sha256(paper_path), "audit_sha256": sha256(audit_path), "update_sha256": sha256(update_path),
        "base_paper_sha256": V23, "base_audit_sha256": AUDIT_V23, "a7_sha256": A7,
        "production_sha256": sha256(production_path), "independent_sha256": sha256(independent_path), "finalization_sha256": sha256(final_path),
        "scientific_result": final["scientific_result"], "submittable": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "paper_sha256": report["paper_sha256"], "audit_sha256": report["audit_sha256"], "output": str(args.output)}))
    if passed != len(checks):
        for c in checks:
            if not c["pass"]:
                print("FAIL", c)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
