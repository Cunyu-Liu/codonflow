#!/usr/bin/env python3
"""Build and independently audit the RK33 scientific/reproduction closeout."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--audit-dir", type=Path, required=True)
    p.add_argument("--clean-repo", type=Path, required=True)
    p.add_argument("--clean-commit", required=True)
    p.add_argument("--closeout", type=Path, required=True)
    p.add_argument("--verification", type=Path, required=True)
    args = p.parse_args()
    a = args.audit_dir
    paths = {
        "protocol": a / "a8_rk33_local_coverage_protocol_v1.json",
        "preflight": a / "rk33_label_free_preflight_v1.json",
        "synthetic_v1": a / "rk33_production_synthetic_v1.json",
        "synthetic_v2": a / "rk33_production_synthetic_v2.json",
        "result": a / "rk33_local_coverage_result_v1.json",
        "independent": a / "rk33_local_coverage_independent_v1.json",
        "reproduction": a / "rk33_clean_reproduction_v1.json",
        "project_tests": a / "rk33_project_tests_v1.log",
        "failed_console": a / "rk33_production_console_v1.log",
        "production_console": a / "rk33_production_console_v2.log",
        "clean_console": a / "rk33_clean_production_console_v1.log",
        "clean_independent_console": a / "rk33_clean_independent_console_v1.log",
    }
    for label, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"{label}: {path}")
    d = {k: json.loads(v.read_text()) for k, v in paths.items() if v.suffix == ".json"}
    result, ind, repro = d["result"], d["independent"], d["reproduction"]
    test_text = paths["project_tests"].read_text()
    match = re.search(r"=+\s*(\d+) passed, (\d+) skipped(?:, \d+ warnings)? in ([0-9.]+)s\s*=+", test_text)
    if not match:
        raise ValueError("Project-test summary not found")
    project_tests = {"passed": int(match.group(1)), "skipped": int(match.group(2)), "seconds": float(match.group(3))}
    clean_head = subprocess.check_output(["git", "-C", str(args.clean_repo), "rev-parse", "HEAD"], text=True).strip()
    clean_tracked_diff = subprocess.run(["git", "-C", str(args.clean_repo), "diff", "--quiet"]).returncode
    checks = []

    def check(name, ok, details):
        checks.append({"name": name, "pass": bool(ok), "details": details})

    check("preflight_21_of_21", d["preflight"]["status"] == "PASS_RK33_LABEL_FREE_PREFLIGHT" and d["preflight"]["checks_passed"] == d["preflight"]["checks_total"] == 21, {"status": d["preflight"]["status"], "checks": d["preflight"]["checks_total"]})
    for version in ["synthetic_v1", "synthetic_v2"]:
        check(f"{version}_18_of_18", d[version]["status"] == "PASS" and d[version]["checks_passed"] == d[version]["checks_total"] == 18, {"status": d[version]["status"], "checks": d[version]["checks_total"]})
    check("production_conclusion", result["scientific_conclusion"] == "LOCAL42_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED", result["scientific_conclusion"])
    check("fit_accounting", (result["new_model_fits"], result["reused_rk28_model_fits"], result["evaluated_model_fits"]) == (200, 200, 400), {k: result[k] for k in ["new_model_fits", "reused_rk28_model_fits", "evaluated_model_fits"]})
    check("twelve_frozen_endpoints", len(result["primary_tests"]) == 12 and len(ind["independent_tests"]) == 12, {"production": len(result["primary_tests"]), "independent": len(ind["independent_tests"])})
    check("zero_of_twelve", not result["all_12_pass"] and not any(t["pass"] for t in result["primary_tests"]), {"passed": sum(t["pass"] for t in result["primary_tests"]), "total": len(result["primary_tests"])})
    check("all_ci_cross_zero", all(t["ci95"][0] < 0 < t["ci95"][1] for t in result["primary_tests"]), {t["test"]: t["ci95"] for t in result["primary_tests"]})
    check("all_holm_one", all(t["p_holm"] == 1.0 for t in result["primary_tests"]), {t["test"]: t["p_holm"] for t in result["primary_tests"]})
    check("all_families_fail", not any(result["family_pass"].values()), result["family_pass"])
    check("independent_76_of_76", ind["status"] == "PASS" and ind["checks_passed"] == ind["checks_total"] == 76, {"status": ind["status"], "checks": ind["checks_total"]})
    check("independent_conclusion_match", ind["independent_conclusion"] == result["scientific_conclusion"] and ind["family_pass"] == result["family_pass"], {"independent": ind["independent_conclusion"], "production": result["scientific_conclusion"], "family_pass": ind["family_pass"]})
    production_gates = [(t["test"], t["pass"]) for t in result["primary_tests"]]
    independent_gates = [(t["test"], t["pass"]) for t in ind["independent_tests"]]
    check("independent_endpoint_gates_match", independent_gates == production_gates, {"production": production_gates, "independent": independent_gates})
    check("independent_numeric_tolerances", ind["max_abs_deltas"]["primary_tests"] <= 1e-12 and ind["max_abs_deltas"]["inference_arrays"] <= 1e-12, ind["max_abs_deltas"])
    check("reproduction_pass", repro["status"] == "PASS" and repro["checks_passed"] == repro["checks_total"], {"status": repro["status"], "checks": f'{repro["checks_passed"]}/{repro["checks_total"]}'})
    check("csv_byte_identical", repro["csv_byte_equal"] == repro["csv_total"] and repro["csv_total"] > 0, {"equal": repro["csv_byte_equal"], "total": repro["csv_total"]})
    check("arrays_exact", repro["arrays_exact_equal"] == repro["arrays_total"] and repro["arrays_total"] > 0, {"equal": repro["arrays_exact_equal"], "total": repro["arrays_total"]})
    check("clean_commit", clean_head == args.clean_commit, {"expected": args.clean_commit, "observed": clean_head})
    check("clean_tracked_tree_unchanged", clean_tracked_diff == 0, {"git_diff_quiet_returncode": clean_tracked_diff})
    check("project_tests", project_tests["passed"] == 429 and project_tests["skipped"] == 1, project_tests)
    required_false = ["functional_untouched_read", "independent_untouched_confirmation", "protein_ood", "rk_g1_complete", "exact_kudla_start_aware_transport", "host_or_assay_effect_identified", "dangles_effect_identified", "measured_structure", "velocity_or_decay_measured"]
    check("scientific_boundaries", all(result["scientific_flags"].get(k) is False for k in required_false) and result["scientific_flags"]["retrospective_outcome_known"] is True, {k: result["scientific_flags"].get(k) for k in required_false + ["retrospective_outcome_known"]})
    check("retained_failure_and_success_logs", paths["failed_console"].stat().st_size > 0 and paths["production_console"].stat().st_size > 0, {"failed_log_bytes": paths["failed_console"].stat().st_size, "success_log_bytes": paths["production_console"].stat().st_size})
    hashes = {label: digest(path) for label, path in paths.items()}
    report = {
        "schema": "a8-rk33-local-coverage-closeout-verification-v2",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "checks": checks,
        "checks_passed": sum(c["pass"] for c in checks),
        "checks_total": len(checks),
        "failed_checks": [c["name"] for c in checks if not c["pass"]],
        "scientific_conclusion": result["scientific_conclusion"],
        "analysis_type": result["analysis_type"],
        "new_model_fits": result["new_model_fits"],
        "reused_rk28_model_fits": result["reused_rk28_model_fits"],
        "evaluated_model_fits": result["evaluated_model_fits"],
        "endpoints_passed": sum(t["pass"] for t in result["primary_tests"]),
        "endpoints_total": len(result["primary_tests"]),
        "independent_checks": f'{ind["checks_passed"]}/{ind["checks_total"]}',
        "reproduction_checks": f'{repro["checks_passed"]}/{repro["checks_total"]}',
        "csv_byte_equal": f'{repro["csv_byte_equal"]}/{repro["csv_total"]}',
        "arrays_exact_equal": f'{repro["arrays_exact_equal"]}/{repro["arrays_total"]}',
        "clean_commit": clean_head,
        "production_seconds": result["elapsed_seconds"],
        "independent_seconds": ind["elapsed_seconds"],
        "clean_production_seconds": repro["clean_production_elapsed_seconds"],
        "clean_independent_seconds": repro["clean_independent_elapsed_seconds"],
        "project_tests": project_tests,
        "artifact_sha256": hashes,
        "scientific_flags": result["scientific_flags"],
    }
    args.verification.parent.mkdir(parents=True, exist_ok=True)
    args.verification.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if report["status"] != "PASS":
        print(json.dumps({"status": report["status"], "failed": report["failed_checks"]}, indent=2))
        raise SystemExit(1)
    lines = [
        "# A8 / RK33 — Local observed-R1 coverage closeout",
        "",
        "**Status: SCIENTIFIC AND REPRODUCTION CLOSEOUT PASS.** The result remains retrospective and is not independent confirmation.",
        "",
        "## Frozen question and execution",
        "",
        "Under the same 152 Mordstein HEK293 observed-R1 variants, 74 whole-sequence clusters, ten seeds, five folds, simple sequence backbone, Ridge/HistGB models, and inference protocol, RK33 tested whether a 42-nt CDS4–45 local MFE improves over no structure, a single full-300 MFE, and the RK28 full-300/window48 three-feature arm.",
        "",
        "The protocol was frozen before outcomes were fitted. The label-free preflight passed 21/21 checks; both synthetic suites passed 18/18. The first production attempt stopped before fitting because target CSV round-trip comparison used zero-tolerance equality. Only that identity check was changed to a 1e-12 absolute tolerance; the scientific design did not change, and the failure log is retained.",
        "",
        "| Item | Verified value |",
        "|---|---:|",
        f'| New model fits | {result["new_model_fits"]} |',
        f'| Reused accepted RK28 fits | {result["reused_rk28_model_fits"]} |',
        f'| Total evaluated fits | {result["evaluated_model_fits"]} |',
        f'| Primary endpoints | {len(result["primary_tests"])} |',
        f'| Production / independent time | {result["elapsed_seconds"]:.6f} / {ind["elapsed_seconds"]:.6f} s |',
        "",
        "## Scientific decision",
        "",
        "**LOCAL42_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED — 0/12 endpoints passed.** All 12 whole-cluster 95% confidence intervals cross zero and all unified Holm-adjusted p-values are 1.0. The smallest unadjusted permutation p-value is 0.16799160041997901, so the failure is not merely an edge created by multiplicity correction. Positive seed counts in some local42–full3 comparisons do not override failed observed-effect, interval, or multiplicity gates.",
        "",
        "## Independent verification and clean reproduction",
        "",
        f'The independent raw-source/model/statistics implementation passed {ind["checks_passed"]}/{ind["checks_total"]} checks and reproduced the same three-family gate. A separate no-hardlinks checkout of `{clean_head}` repeated production and independent verification. The comparison passed {repro["checks_passed"]}/{repro["checks_total"]} checks; {repro["csv_byte_equal"]}/{repro["csv_total"]} CSV files were byte-identical and {repro["arrays_exact_equal"]}/{repro["arrays_total"]} NPZ arrays were exactly equal.',
        "",
        "| Component | Original | Clean checkout |",
        "|---|---:|---:|",
        f'| Production | {result["elapsed_seconds"]:.6f} s | {repro["clean_production_elapsed_seconds"]:.6f} s |',
        f'| Independent verification | {ind["elapsed_seconds"]:.6f} s | {repro["clean_independent_elapsed_seconds"]:.6f} s |',
        "",
        f'Full project tests: **{project_tests["passed"]} passed, {project_tests["skipped"]} skipped** ({project_tests["seconds"]:.2f} s).',
        "",
        "## Evidence hashes",
        "",
        "| Evidence | SHA256 |",
        "|---|---|",
    ]
    for label in ["protocol", "preflight", "result", "independent", "reproduction", "project_tests", "failed_console", "production_console"]:
        lines.append(f'| {label} | `{hashes[label]}` |')
    lines += [
        f'| closeout verification | `{digest(args.verification)}` |',
        "",
        "## Non-claims and remaining tasks",
        "",
        "This experiment does not reconstruct the exact start-aware Kudla window: the observed FASTA begins at CDS position 4 and lacks the start ATG, four upstream nucleotides, complete UTR–CDS context, and measured structure. It does not identify host, assay, measured-versus-predicted structure, or dangling-end effects. It provides no external-SOTA, unified time-matched, complete seven-method dense-trajectory, multispecies VeloHARMO, functional/protein-OOD, prospective DBTL, or RK-G1 result. Functional untouched data were not read; expensive generator training was not authorized; no wet-lab work was performed.",
        "",
        "The full manuscript remains a non-submittable working draft until those gates are complete.",
        "",
    ]
    args.closeout.parent.mkdir(parents=True, exist_ok=True)
    args.closeout.write_text("\n".join(lines))
    print(json.dumps({"status": report["status"], "checks": f'{report["checks_passed"]}/{report["checks_total"]}', "csv": report["csv_byte_equal"], "arrays": report["arrays_exact_equal"], "closeout": str(args.closeout), "verification": str(args.verification)}, indent=2))


if __name__ == "__main__":
    main()
