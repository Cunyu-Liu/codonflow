#!/usr/bin/env python3
import hashlib
import json
import sys
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    root = Path(sys.argv[1]).resolve()
    evidence = root / "ppt"
    old_path = root / "CodonFlow_preprint_A8_v11.md"
    new_path = root / "CodonFlow_preprint_A8_v12.md"
    summary_path = evidence / "sequence_ood_model_summary.json"
    independent_path = evidence / "sequence_ood_model_independent_verification.json"
    final_path = evidence / "sequence_ood_model_finalization.json"
    output_path = root / "rk04_model_paper_verification.json"
    old = old_path.read_text()
    new = new_path.read_text()
    summary = json.loads(summary_path.read_text())
    independent = json.loads(independent_path.read_text())
    final = json.loads(final_path.read_text())
    checks = []

    def check(name, condition, detail):
        checks.append({"name": name, "status": "PASS" if condition else "FAIL", "detail": detail})

    check("v11_preserved", sha(old_path) == "0158f579cb1634b1a36c666c4cf7c930dcabe276abc00e3c00f5546ef1005a05", sha(old_path))
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    protected = [line for line in old_lines if not line.startswith("> **Status:") and line != "[Pending RK-G3. Report untouched proteins/studies, length/GC/homology strata, available hosts and complete costs.]"]
    cursor = 0
    for line in new_lines:
        if cursor < len(protected) and line == protected[cursor]:
            cursor += 1
    check("all_other_v11_lines_preserved_in_order", cursor == len(protected), {"protected": len(protected), "matched": cursor})
    check("working_manuscript_status", "working manuscript — not for submission" in new and "No SOTA claim." in new, "non-submittable")
    check("independent_and_final", independent["status"] == "PASS" and independent["checks_passed"] == 40 and final["status"] == "PASS" and final["checks_passed"] == 18, "40/40 + 18/18")
    primary = summary["primary_family"]
    check("primary_selection", primary == "ridge_all" and summary["selected"][primary]["params"]["alpha"] == 100.0 and f"{summary['selected'][primary]['dev_metrics']['cluster_balanced_mse']:.6f}" in new, primary)
    check("split_counts", all(token in new for token in ["4,019/503/490 rows", "3,561/447/436 clusters", "1,336 rows / 1,110 clusters", "19,072 MAGE functional-untouched rows"]), "retained/test/OOD/untouched")
    for family in ["constant", "ridge_gc", "ridge_basic", "ridge_all", "histgb_all"]:
        values = [summary["test_metrics"][family]["row_r2"], summary["test_metrics"][family]["cluster_balanced_mse"], summary["sequence_ood_metrics"][family]["row_r2"], summary["sequence_ood_metrics"][family]["cluster_balanced_mse"]]
        if family != "constant":
            values += [summary["test_metrics"][family]["row_spearman"], summary["sequence_ood_metrics"][family]["row_spearman"]]
        check(f"metrics_{family}", all(f"{value:.6f}" in new for value in values), "six-decimal evidence match")
    comparison = summary["primary_comparison"]
    for partition in ["test", "sequence_ood"]:
        observed = comparison["observed"][partition]
        boot = comparison["bootstrap"][partition]["statistics"]
        expected = []
        for metric in ["row_spearman_delta", "cluster_balanced_mse_delta"]:
            expected += [f"{observed[metric]:+.6f}" if metric == "row_spearman_delta" else f"{observed[metric]:.6f}"]
            expected += [f"{x:.6f}" for x in boot[metric]["ci95"]]
        check(f"bootstrap_{partition}", all(value in new for value in expected), expected)
    check("histgb_not_post_hoc_primary", "not used to replace the dev-frozen primary post hoc" in new and summary["test_metrics"]["histgb_all"]["row_spearman"] > summary["test_metrics"][primary]["row_spearman"], "secondary family retained")
    check("verification_recorded", all(token in new for token in ["40/40 checks", "18/18 checks", "12/12", "maximum prediction delta **0.0**"]), "independent/final/tests")
    check("scientific_boundaries", all(token in new for token in ["low absolute R²", "do not establish fixed-protein synonymous mechanisms", "CodonFlow-RK generator readiness", "functional-untouched performance", "or SOTA"]), "limited proxy only")
    check("failure_history_retained", all(token in new for token in ["initial schema failure", "incomplete multithreaded run", "constant-prediction floating-point correlation artifact"]), "failures not hidden")
    expected_hashes = [sha(summary_path), sha(independent_path), sha(final_path), summary["artifacts"]["predictions"]["sha256"], summary["artifacts"]["metrics"]["sha256"]]
    check("evidence_hashes_in_manuscript", all(value in new for value in expected_hashes), expected_hashes)
    check("functional_untouched_still_pending", "19,072 MAGE functional-untouched rows** remain unevaluated" in new and independent["functional_untouched_evaluated"] is False, "untouched not evaluated")
    failed = [c for c in checks if c["status"] == "FAIL"]
    report = {
        "protocol_id": "a8_rk04_model_paper_verification_v1",
        "status": "PASS" if not failed else "FAIL",
        "manuscript": str(new_path), "manuscript_sha256": sha(new_path),
        "prior_manuscript": str(old_path), "prior_manuscript_sha256": sha(old_path),
        "checks": checks,
        "summary": {"checks": f"{len(checks)-len(failed)}/{len(checks)}", "failed": [c["name"] for c in failed]},
        "evidence": {
            "model_summary_sha256": sha(summary_path),
            "independent_verification_sha256": sha(independent_path),
            "finalization_sha256": sha(final_path),
        },
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({**report["summary"], "status": report["status"], "manuscript_sha256": report["manuscript_sha256"]}, ensure_ascii=False))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
