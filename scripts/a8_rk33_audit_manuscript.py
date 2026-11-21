#!/usr/bin/env python3
"""Audit every RK33 manuscript number and the insertion-only integration contract."""
from pathlib import Path
import argparse
import hashlib
import json


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    b = args.base
    original_path = b / "CodonFlow_preprint_A8.pre_rk33.md"
    updated_path = b / "CodonFlow_preprint_A8.md"
    section_path = b / "academic_workflow/paper-write-en/.workflow/paper_final.md"
    integration_path = b / "rk33_manuscript_integration_v1.json"
    workflow_status_path = b / "rk33_academic_workflow_status_v1.json"
    result = json.loads((b / "rk33_local_coverage_result_v1.json").read_text())
    independent = json.loads((b / "rk33_local_coverage_independent_v1.json").read_text())
    reproduction = json.loads((b / "rk33_clean_reproduction_v1.json").read_text())
    closeout = json.loads((b / "rk33_closeout_verification_v2.json").read_text())
    integration = json.loads(integration_path.read_text())
    workflow_status = json.loads(workflow_status_path.read_text())
    original, updated, section = original_path.read_text(), updated_path.read_text(), section_path.read_text()
    checks = []

    def check(name, ok, details):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    check("integration_pass", integration["status"] == "PASS" and integration["non_insertion_content_preserved_exactly"], integration)
    check("workflow_pass", workflow_status["status"] == "PASS" and workflow_status["stage"] == "deliver", workflow_status)
    check("updated_hash", sha(updated_path) == integration["updated_sha256"], {"expected": integration["updated_sha256"], "observed": sha(updated_path)})
    check("original_hash", sha(original_path) == integration["original_sha256"] == "e65608c5b46f012a9eb632bc0997062e65b33aa1a46ffd16376d1a21a555581c", integration["original_sha256"])
    check("section_hash", sha(section_path) == integration["section_sha256"], {"expected": integration["section_sha256"], "observed": sha(section_path)})
    stripped = section.strip() + "\n\n"
    recovered = updated.replace(stripped, "", 1)
    check("insertion_only_recovery", recovered == original and updated.count(stripped) == 1, {"recovered_original": recovered == original, "insertions": updated.count(stripped)})
    check("section_location", updated.count("### 6.44 ") == 1 and updated.index("### 6.44 ") < updated.index("## 7. Discussion"), {"section_count": updated.count("### 6.44 ")})
    labels = {"local42_vs_simple": "local42−simple", "local42_vs_full1": "local42−full1", "local42_vs_full3": "local42−full3"}
    for t in result["primary_tests"]:
        family, rest = t["test"].split("__")
        model, metric = rest.split("_", 1)
        metric_label = "Spearman" if metric.startswith("spearman") else "MSE improvement"
        row = f'| {labels[family]} | {model.capitalize()} | {metric_label} | {t["observed_effect"]:.6f} | [{t["ci95"][0]:.6f}, {t["ci95"][1]:.6f}] | {t["p_cluster_swap"]:.6f} | {t["p_holm"]:.6f} | {t["positive_seeds"]}/10 | No |'
        check(f'endpoint_row_{t["test"]}', section.count(row) == 1, row)
    arm_labels = {"simple": "simple", "local42": "simple + local42 MFE", "full1": "simple + full-300 MFE", "full3": "simple + full-300/window48 MFEs"}
    for row in result["primary_absolute_performance"]:
        model, arm = row["arm"].split("_", 1)
        text = f'| {model.capitalize()} | {arm_labels[arm]} | {row["spearman"]:.6f} | {row["mse"]:.6f} |'
        check(f'absolute_row_{row["arm"]}', section.count(text) == 1, text)
    for name, text in {
        "scientific_conclusion": "0/12 endpoints passed and all three family gates were false",
        "independent_checks": f'{independent["checks_passed"]}/{independent["checks_total"]} checks',
        "reproduction_checks": f'{reproduction["checks_passed"]}/{reproduction["checks_total"]} checks',
        "csv_reproduction": f'{reproduction["csv_byte_equal"]}/{reproduction["csv_total"]} CSV files were byte-identical',
        "array_reproduction": f'{reproduction["arrays_exact_equal"]}/{reproduction["arrays_total"]} NPZ arrays were exactly equal',
        "clean_commit": closeout["clean_commit"],
        "project_tests": "429 passed and one skipped test",
        "fit_accounting": "200 new fits; 200 accepted simple/full3 fits were reused, for 400 evaluated fits",
        "not_independent": "not an independent confirmation or a test of RNA velocity",
        "no_functional_untouched": "Functional untouched data were not read",
        "no_wet_lab": "no wet-lab experiment was performed",
        "rk_g1_open": "RK-G1 remain open",
        "closeout_hash": closeout["artifact_sha256"]["result"],
    }.items():
        check(name, text in section, text)
    report = {
        "schema": "a8-rk33-manuscript-audit-v1",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "checks": checks,
        "checks_passed": sum(c["pass"] for c in checks),
        "checks_total": len(checks),
        "failed_checks": [c["name"] for c in checks if not c["pass"]],
        "manuscript_sha256": sha(updated_path),
        "section_sha256": sha(section_path),
        "original_sha256": sha(original_path),
        "integration_sha256": sha(integration_path),
        "workflow_status_sha256": sha(workflow_status_path),
        "manuscript_status": "non_submittable_working_draft",
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f'{report["checks_passed"]}/{report["checks_total"]}', "failed": report["failed_checks"], "manuscript_sha256": report["manuscript_sha256"]}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
