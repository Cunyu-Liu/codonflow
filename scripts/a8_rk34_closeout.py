#!/usr/bin/env python3
"""Evidence-bounded RK34 closeout after independent and clean reproduction."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path("/home/codonflow-a8-rk")
AUDIT = ROOT / "audits/20261121/RK34"
TEAMS = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk34/start_context_v1")
FAMILIES = ["exact_vs_simple", "upstream_given_start", "start_given_upstream", "start_without_upstream", "upstream_without_start"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reproduction-report", type=Path, required=True)
    parser.add_argument("--project-tests-log", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    if args.output_json.exists() or args.output_md.exists():
        raise FileExistsError("closeout outputs must be new")
    paths = {
        "protocol": AUDIT / "a8_rk34_start_context_protocol_v2.json",
        "freeze": AUDIT / "rk34_freeze_verification_v2.json",
        "preflight": AUDIT / "rk34_start_context_preflight_v1.json",
        "production": AUDIT / "rk34_start_context_result_v2.json",
        "independent": AUDIT / "rk34_start_context_independent_v2.json",
        "independent_failed_v1": AUDIT / "rk34_start_context_independent_v1.json",
        "reproduction": args.reproduction_report,
        "production_log": AUDIT / "rk34_production_v2.log",
        "independent_log": AUDIT / "rk34_independent_v2.log",
        "independent_failed_v1_log": AUDIT / "rk34_independent_v1.log",
        "failure_log": AUDIT / "rk34_production_v1.log",
        "tests_v1": AUDIT / "rk34_synthetic_tests_v1.log",
        "tests_v2": AUDIT / "rk34_synthetic_tests_v2.log",
        "tests_independent": AUDIT / "rk34_synthetic_tests_with_independent_v2.log",
        "project_tests": args.project_tests_log,
    }
    data = {key: json.loads(path.read_text()) for key, path in paths.items() if key in {"protocol", "freeze", "preflight", "production", "independent", "reproduction"}}
    protocol, production, independent, reproduction = (data[key] for key in ("protocol", "production", "independent", "reproduction"))
    checks = []

    def check(name, ok, details=None):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    check("freeze_30", data["freeze"]["status"] == "PASS" and data["freeze"]["checks_passed"] == data["freeze"]["checks_total"] == 30)
    check("preflight_12", data["preflight"]["status"] == "PASS_LABEL_FREE_START_CONTEXT_PREFLIGHT" and data["preflight"]["checks_passed"] == data["preflight"]["checks_total"] == 12)
    check("protocol_binding", production["protocol_sha256"] == independent["protocol_sha256"] == sha(paths["protocol"]))
    check("independent_binds_production", independent["production_summary_sha256"] == sha(paths["production"]))
    check("scientific_conclusion", production["scientific_conclusion"] == independent["scientific_conclusion"] == reproduction["scientific_conclusion"] == "JOINT_EXACT_CONTEXT_WITHOUT_SEPARABLE_CONTRIBUTIONS_RETROSPECTIVELY")
    primary = {row["family"]: row for row in production["family_results"] if row["analysis"] == "primary"}
    sensitivity = {row["family"]: row for row in production["family_results"] if row["analysis"] == "sensitivity_d0"}
    check("exact_family_pass", primary["exact_vs_simple"]["all_four_pass"] and primary["exact_vs_simple"]["n_pass"] == 4)
    check("separable_families_fail", all(not primary[family]["all_four_pass"] for family in FAMILIES[1:]), {family: primary[family]["n_pass"] for family in FAMILIES[1:]})
    check("sensitivity_does_not_rescue", sensitivity["exact_vs_simple"]["all_four_pass"] and all(not sensitivity[family]["all_four_pass"] for family in FAMILIES[1:]), {family: sensitivity[family]["n_pass"] for family in FAMILIES})
    check("confirmatory_12_of_20", production["n_confirmatory_tests"] == 20 and production["n_confirmatory_pass"] == 12 and len(production["primary_tests"]) == 40)
    check("fit_accounting", production["new_model_fits"] == 700 and production["reused_rk32_model_fits"] == 200 and production["evaluated_model_fits"] == 900 and independent["independent_model_fits"] == 900)
    check("independent_pass", independent["status"] == "PASS" and independent["checks_passed"] == independent["checks_total"])
    endpoint_checks = [row for row in independent["checks"] if row["name"].startswith("endpoint_")]
    inference_array_check = [row for row in independent["checks"] if row["name"] == "inference_array_identity"]
    deltas = independent["max_deltas"]
    check("independent_numeric_precision", deltas["prediction"] < 1e-10 and deltas["seed_metric"] < 1e-12 and deltas["seed_effect"] < 1e-12 and deltas["ci"] < 1e-10 and len(endpoint_checks) == 40 and all(row["pass"] for row in endpoint_checks) and len(inference_array_check) == 1 and inference_array_check[0]["pass"] and reproduction["independent_arrays_exact"] == 82)
    check("energy_roundtrip", production["max_recomputed_energy_abs_delta"] < 1e-12, production["max_recomputed_energy_abs_delta"])
    check("reproduction_pass", reproduction["status"] == "PASS" and reproduction["checks_passed"] == reproduction["checks_total"] and reproduction["production_csv_byte_identical"] == 6 and reproduction["production_arrays_exact"] == 82 and reproduction["independent_csv_byte_identical"] == 5 and reproduction["independent_arrays_exact"] == 82)
    for key, record in production["outputs"].items():
        path = Path(record["path"])
        check(f"production_output_{key}", path.is_file() and path.stat().st_size == record["bytes"] and sha(path) == record["sha256"])
    for key, record in independent["outputs"].items():
        path = Path(record["path"])
        check(f"independent_output_{key}", path.is_file() and path.stat().st_size == record["bytes"] and sha(path) == record["sha256"])
    for key, count in (("tests_v1", 8), ("tests_v2", 9), ("tests_independent", 11)):
        text = paths[key].read_text()
        check(key, f"{count} passed" in text and "failed" not in text)
    project_text = paths["project_tests"].read_text()
    match = re.search(r"(\d+) passed(?:, (\d+) skipped)?", project_text)
    check("project_tests", match is not None and "failed" not in project_text and "ERROR" not in project_text, match.group(0) if match else None)
    failure_text = paths["failure_log"].read_text()
    check("prefit_failure_retained", "ValueError" in failure_text and "broadcast" in failure_text and not (AUDIT / "rk34_start_context_result_v1.json").exists())
    failed_independent = json.loads(paths["independent_failed_v1"].read_text())
    failed_names = [row["name"] for row in failed_independent["checks"] if not row["pass"]]
    check("independent_v1_failure_retained", failed_independent["status"] == "FAIL" and failed_names == ["seed_metric_identity"] and independent["verification_revision"] == "v2_canonicalize_null_baseline_arm_after_csv_roundtrip" and independent["seed_metric_numeric_tolerance"] == 1e-9)
    check("untouched_not_read", not production["scientific_flags"]["functional_untouched_read"] and not independent["functional_untouched_read"])
    flags = production["scientific_flags"]
    boundaries = protocol["scientific_boundaries"]
    check("claims_boundary", not flags["protein_ood"] and not flags["RK_G1_complete"] and not flags["host_or_assay_identified"] and not flags["full_external_sota"] and not boundaries["generator_training_authorized"] and not boundaries["functional_untouched_read"] and not independent["functional_untouched_read"])

    test_rows = [row for row in production["primary_tests"] if row["analysis"] == "primary"]
    lines = [
        "# RK34 | Equal-length start-context 2×2 ablation closeout", "",
        f"- **Status**: {'PASS' if all(row['pass'] for row in checks) else 'FAIL'}; production 900 evaluated fits = 700 new + 200 accepted RK32; independent 900 fits.", "",
        f"- **Conclusion**: `{production['scientific_conclusion']}`. The exact 42-nt window improves over matched simple features in all four confirmatory tests; neither upstream-only nor start-only separability claim passes both required families.", "",
        "## Family gates", "", "| Analysis | Family | Passed / 4 | Family gate |", "|---|---|---:|---|",
    ]
    for analysis, rows in (("primary d2", primary), ("sensitivity d0", sensitivity)):
        for family in FAMILIES:
            lines.append(f"| {analysis} | {family} | {rows[family]['n_pass']} | {'PASS' if rows[family]['all_four_pass'] else 'FAIL'} |")
    lines += ["", "## Confirmatory endpoints (d2)", "", "| Family | Model | Metric | Effect | 95% CI | Holm p | Positive seeds | Gate |", "|---|---|---|---:|---|---:|---:|---|"]
    for row in test_rows:
        lines.append(f"| {row['family']} | {row['model']} | {row['metric']} | {row['observed_effect']:.6g} | [{row['ci95'][0]:.6g}, {row['ci95'][1]:.6g}] | {row['p_holm']:.6g} | {row['positive_seeds']}/10 | {'PASS' if row['pass'] else 'FAIL'} |")
    lines += ["", "## Verification and boundaries", "",
              f"- Independent: {independent['checks_passed']}/{independent['checks_total']} PASS; maximum prediction delta {deltas['prediction']:.3g}; 40/40 test records and 82/82 inference arrays exactly equal.",
              f"- Clean reproduction: {reproduction['checks_passed']}/{reproduction['checks_total']} PASS; 6/6 production CSV, 82/82 production arrays, 5/5 independent CSV and 82/82 independent arrays exact.",
              f"- Component wall time: production {production['component_wall_seconds']:.3f} s; independent {independent['elapsed_seconds']:.3f} s.",
              "- Retrospective fixed-Kudla, 37 sequence clusters, 150 exact-CDS groups, 154 measurement rows. Artificial N-masking is a computational ablation, not a biological perturbation.",
              "- No claim of universal upstream/start mechanism, independent untouched transport, host/assay identification, functional/protein OOD, external SOTA, prospective DBTL, wet lab, or RK-G1.",
              "- External complete SOTA, unified time-matched, seven-method common dense matrix, multi-species VeloHARMO, real functional/protein OOD, untouched and prospective validation remain open.", ""]
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text("\n".join(lines))
    payload = {
        "schema": "a8-rk34-closeout-v1", "status": "PASS" if all(row["pass"] for row in checks) else "FAIL",
        "scientific_conclusion": production["scientific_conclusion"], "primary_family_results": [primary[family] for family in FAMILIES],
        "confirmatory_tests": len(test_rows), "confirmatory_pass": sum(row["pass"] for row in test_rows),
        "inputs": {key: {"path": str(path), "sha256": sha(path)} for key, path in paths.items()},
        "closeout_markdown_sha256": sha(args.output_md), "checks": checks,
        "checks_passed": sum(row["pass"] for row in checks), "checks_total": len(checks),
    }
    args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in payload.items() if key not in {"checks", "inputs"}}, indent=2))
    if payload["status"] != "PASS":
        print(json.dumps([row for row in checks if not row["pass"]], indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
