"""Independently verify the RK16 manuscript section against accepted scientific artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    repo = args.repo_root.resolve()
    audit_dir = repo / "audits/20261120/RK16"
    manuscript_path = repo / "paper/CodonFlow_preprint_A8.md"
    section_path = audit_dir / "rk16_manuscript_section_v1.md"
    integration_path = audit_dir / "rk16_manuscript_integration_v1.json"
    audit = json.loads((audit_dir / "rk16_dense_prefix_audit_v1.json").read_text())
    finalization = json.loads((audit_dir / "rk16_finalization_v1.json").read_text())
    independent = json.loads((audit_dir / "rk16_postpush_independent_verification_v1.json").read_text())
    integration = json.loads(integration_path.read_text())
    prepare = json.loads((audit_dir / "rk16_manuscript_prepare_check.json").read_text())
    draft = json.loads((audit_dir / "rk16_manuscript_draft_check.json").read_text())
    writing_status = json.loads((audit_dir / "rk16_manuscript_status.json").read_text())
    manuscript = manuscript_path.read_text()
    section_source = section_path.read_text().rstrip() + "\n"
    start = manuscript.index("### 6.31 ")
    end = manuscript.index("\n## 7. Discussion", start)
    section = manuscript[start:end].rstrip() + "\n"
    checks = []

    def check(name: str, condition: bool, evidence=None) -> None:
        checks.append({"check": name, "pass": bool(condition), "evidence": evidence})

    check("single_section_6_31", manuscript.count("### 6.31 ") == 1)
    check("section_exactly_matches_accepted_source", section == section_source)
    check("section_source_hash", sha256(section_path) == integration["section_sha256"] == draft["result"]["input_sha256"])
    check("integration_before_hash", integration["before_sha256"] == "26377af298518e6f3e04d7569be78aa57ce3ce298471cc1fafcf150e8462929d")
    check("integration_after_hash", integration["after_sha256"] == sha256(manuscript_path))
    check("non_target_text_preserved", integration["non_target_text_preserved"] is True)
    check("prepare_pass", prepare["status"] == "pass")
    check("draft_pass", draft["status"] == "pass" and not draft["failures"])
    check("writing_status_pass", writing_status["status"] == "PASS" and writing_status["stage"] == "deliver")
    check("draft_mode_retained", draft["result"]["mode"] == "draft" and integration["manuscript_mode"] == "draft")
    check("non_submittable_header", "not for submission" in manuscript and "No SOTA claim" in manuscript)
    check("non_submittable_close", "non-submittable working manuscript" in manuscript and "manuscript remains non-submittable" in section)
    check("independent_88_88", independent["checks_passed"] == independent["checks_total"] == 88 and "88/88" in section)
    check("finalization_53_53", finalization["checks_passed"] == finalization["checks_total"] == 53 and "53/53" in section)
    check("dense_gate_true", audit["dense_prefix_superiority_pass"] is True)
    check("record_and_call_counts", audit["record_count"] == 18 and audit["primary_real_generation_call_count"] == 792 and "792 primary generation-call positions" in section)
    check("six_tests_pass", len(audit["primary_comparisons"]) == 6 and all(item["pass"] for item in audit["primary_comparisons"].values()))
    check("six_cis_positive", all(item["ci95"][0] > 0.0 for item in audit["primary_comparisons"].values()))
    check("six_holm_values_rendered", all(f"{item['holm_p']:.8f}" in section for item in audit["primary_comparisons"].values()))

    labels = {
        "lineardesign_lambda11": "LinearDesign-11",
        "ensembledesign_11run": "EnsembleDesign-11",
        "codongpt": "codonGPT",
        "uniform_synonymous": "Uniform synonymous",
    }
    for method, label in labels.items():
        summary = audit["method_summary"][method]
        check(f"mean_binding_{method}", label in section and f"{summary['mean_dense_budget_step_auc_v2']:.6f}" in section and f"{summary['mean_endpoint_hypervolume_normalized_b11']:.6f}" in section)

    for key, item in audit["primary_comparisons"].items():
        expected = f"{item['mean_effect']:+.6f}"
        check(f"effect_binding_{key}", expected in section, expected)
        low = f"{item['ci95'][0]:+.6f}"
        high = f"{item['ci95'][1]:+.6f}"
        check(f"ci_binding_{key}", low in section and high in section, [low, high])

    secondary = audit["secondary_b100_descriptive_summary"]
    check("secondary_b100_auc_binding", f"{secondary['codongpt']['mean_dense_budget_step_auc_v2_b1_b99']:.6f}" in section and f"{secondary['uniform_synonymous']['mean_dense_budget_step_auc_v2_b1_b99']:.6f}" in section)
    check("secondary_b100_hv_binding", f"{secondary['codongpt']['mean_endpoint_hypervolume_normalized_b100']:.6f}" in section and f"{secondary['uniform_synonymous']['mean_endpoint_hypervolume_normalized_b100']:.6f}" in section)
    check("secondary_excluded_from_holm", "not included in the primary Holm family" in section)
    check("excluded_methods_disclosed", all(name in section for name in ("GEMORNA", "legacy LinearDesign scan", "CAI-greedy")))
    check("time_matched_open", not finalization["time_matched_comparison"] and "Unified time-matched evaluation" in section)
    check("codonflow_not_evaluated", not finalization["codonflow_rk_evaluated"] and "CodonFlow-RK generation" in section)
    check("functional_untouched_not_evaluated", not finalization["functional_untouched_evaluated"] and "untouched evaluation" in section)
    check("rk_g1_false", not finalization["rk_g1_pass"] and "RK-G1 remains false" in section)
    check("generator_unauthorized", not finalization["expensive_generation_authorized"] and "generator training remains unauthorized" in section)
    check("sota_not_claimed", not finalization["sota_claimed"] and "external SOTA remain open" in section)

    expected_anchors = {
        "RK16 dense-prefix frozen protocol": finalization["protocol_sha256"],
        "RK16 full dense-prefix matrix": finalization["matrix_sha256"],
        "RK16 dense-prefix audit": finalization["audit_sha256"],
        "RK16 primary comparison CSV": finalization["csv_sha256"],
        "RK16 independent verification": finalization["independent_sha256"],
        "RK16 finalization": sha256(audit_dir / "rk16_finalization_v1.json"),
        "RK16 full CPU-suite console log": finalization["full_regression_sha256"],
        "RK16 engineering failures": finalization["engineering_failures_sha256"],
        "RK16 closeout": finalization["closeout_sha256"],
        "RK16 manuscript source section": sha256(section_path),
        "RK16 manuscript prepare check": sha256(audit_dir / "rk16_manuscript_prepare_check.json"),
        "RK16 manuscript draft check": sha256(audit_dir / "rk16_manuscript_draft_check.json"),
        "RK16 manuscript writing status": sha256(audit_dir / "rk16_manuscript_status.json"),
    }
    check("evidence_anchor_count", len(expected_anchors) == integration["evidence_anchor_rows"] == 13)
    for name, digest in expected_anchors.items():
        check(f"anchor_{name}", f"| {name} | `{digest}` |" in manuscript)

    passed = sum(item["pass"] for item in checks)
    report = {
        "schema": "a8-rk16-manuscript-verification-v1",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "manuscript_sha256": sha256(manuscript_path),
        "section_sha256": sha256(section_path),
        "checks_passed": passed,
        "checks_total": len(checks),
        "checks": checks,
        "manuscript_mode": "draft",
        "manuscript_submittable": False,
        "dense_prefix_superiority_pass": audit["dense_prefix_superiority_pass"],
        "time_matched_comparison": False,
        "scientific_gate_passed": False,
        "rk_g1_pass": False,
        "expensive_generation_authorized": False,
        "external_sota_authorized": False,
        "sota_claimed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"RK16 manuscript verification: {passed}/{len(checks)}")
    if passed != len(checks):
        for item in checks:
            if not item["pass"]:
                print(json.dumps(item))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
