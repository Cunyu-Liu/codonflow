#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper", required=True)
    parser.add_argument("--tasks", required=True)
    parser.add_argument("--comparison", required=True)
    parser.add_argument("--update-report", required=True)
    parser.add_argument("--audit-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    paper = Path(args.paper).read_text()
    tasks = Path(args.tasks).read_text()
    summary = json.loads(Path(args.comparison).read_text())
    update = json.loads(Path(args.update_report).read_text())
    audit = Path(args.audit_dir)
    checks = {}

    def check(name, value):
        checks[name] = bool(value)

    check("paper_hash_matches_update", sha256(args.paper) == update["paper_after_sha256"])
    check("tasks_hash_matches_update", sha256(args.tasks) == update["tasks_after_sha256"])
    check("one_new_results_section", paper.count("### 6.8 Same-backbone mechanism-channel ablation on Boël sequence-OOD") == 1)
    check("functional_validation_renumbered", paper.count("### 6.9 Independent functional validation") == 1)
    check("old_section_number_removed", "### 6.8 Independent functional validation" not in paper)
    check("manuscript_still_non_submittable", "non-submittable working manuscript" in paper)
    metrics = summary["metrics"]["sequence_ood"]
    for model, label in [
        ("ribokinetic_all", "RiboKinetic all channels"),
        ("ribokinetic_none", "RiboKinetic no channels"),
        ("ridge_all", "Full-proxy ridge"),
        ("ridge_gc", "GC-only ridge"),
        ("histgb_all", "Full-proxy HistGB"),
    ]:
        row = metrics[model]
        check(f"{model}_cb_mse", f"{row['cluster_balanced_mse']:.6f}" in paper)
        check(f"{model}_spearman", f"{row['row_spearman']:.6f}" in paper)
        check(f"{model}_r2", f"{row['row_r2']:.6f}" in paper)
        check(f"{model}_label", label in paper)
    for left, right in [("ribokinetic_all", "ribokinetic_none"), ("ribokinetic_all", "ridge_all"), ("ribokinetic_all", "ridge_gc")]:
        rows = [r for r in summary["comparisons"] if r["partition"] == "sequence_ood" and r["left"] == left and r["right"] == right]
        check(f"comparison_rows_{right}", len(rows) == 2)
        for row in rows:
            for key in ["point_delta", "ci95_low", "ci95_high"]:
                check(f"{right}_{row['metric']}_{key}", f"{row[key]:.6f}" in paper)
    check("gate_false_in_paper", summary["rk_g1_pass"] is False and "preregistered RK-G1 criterion was not met" in paper)
    check("no_sota_claim", "preclude an SOTA or broad superiority claim" in paper)
    check("cross_protein_boundary", "cross-protein, nonsynonymous constructs" in paper)
    check("velocity_boundary", "Velocity OOD and generator readiness remain unevaluated" in paper)
    check("function_only_supervision", "function-only supervision" in paper)
    check("mechanism_heads_not_validated", "not validated mechanism-specific estimates" in paper)
    check("bootstrap_count", f"{summary['bootstrap']['replicates']:,}" in paper)
    check("parameter_count", "4,997 parameters" in paper)
    check("all_cost", f"{summary['costs']['ribokinetic_all']['elapsed_seconds']:.4f} seconds" in paper)
    check("none_cost", f"{summary['costs']['ribokinetic_none']['elapsed_seconds']:.4f} seconds" in paper)
    check("independent_count", "224 of 224 checks" in paper)
    check("finalization_count", "48 of 48 checks" in paper)
    check("clean_environment_open", "Clean-environment reproduction remains outstanding" in paper)
    check("task_gate_false", "**RK-G1 状态：未通过**" in tasks)
    check("task_independent_count", "224/224 PASS" in tasks)
    check("prepare_pass", json.loads((audit / "prepare_check.json").read_text())["status"] == "pass")
    check("draft_pass", json.loads((audit / "draft_check.json").read_text())["status"] == "pass")
    for name, digest in update["evidence_anchors"].items():
        check(f"evidence_anchor_{name}", digest in paper)
    failures = [name for name, value in checks.items() if not value]
    report = {
        "status": "PASS" if not failures else "FAIL",
        "checks_passed": len(checks) - len(failures),
        "checks_total": len(checks),
        "failures": failures,
        "paper_sha256": sha256(args.paper),
        "tasks_sha256": sha256(args.tasks),
        "rk_g1_pass": summary["rk_g1_pass"],
        "manuscript_status": "non-submittable working manuscript",
        "checks": checks,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
