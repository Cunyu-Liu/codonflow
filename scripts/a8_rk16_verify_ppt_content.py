#!/usr/bin/env python3
"""Bind the RK16 slide's claims to the final pushed scientific artifacts."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("RK16_PPT_WORK_DIR", Path(__file__).resolve().parent)).resolve()
SRC = ROOT / "source_snapshot"
OUT = ROOT / "rk16_ppt_content_verification_v1.json"
EXPECTED_HASHES = {
    "rk16_dense_prefix_audit_v1.json": "3cd364114a6e1a247ccdb4896310115a1527519089f87776c4f3b10007d64500",
    "rk16_primary_comparisons_v1.csv": "6baceb837aa8ba34c0d2bf1d4b4b7877323eb1d3e0089f6aa6c846d0e651ac0b",
    "rk16_independent_verification_v1.json": "d07f796bfbf76dd0898ba249f7344cc5d1cfc33e90762e207fad938b3be2e4b6",
    "rk16_finalization_v1.json": "2cf31798c4532b3ee8cd253dde3908032195187971c3a9bd7d599a8cfc4abb27",
    "rk16_manuscript_verification_v1.json": "d9ec84beca4bfd9d5ecd62a33f8b2262433be73833ca3cc59504e1bbe49327c1",
}
EXPECTED_MEANS = {
    "lineardesign_lambda11": (22.794606316429064, 29.972887490261744),
    "ensembledesign_11run": (14.896234418783472, 16.693982080997003),
    "codongpt": (5.205444025614179, 7.989211310427903),
    "uniform_synonymous": (0.7029515245686863, 0.9666178877667078),
}
EXPECTED_ENSEMBLE_EFFECTS = (7.8983718976455926, 13.278905409264743)

checks: list[dict[str, object]] = []


def record(name: str, passed: bool, evidence: object = None) -> None:
    checks.append({"check": name, "pass": bool(passed), "evidence": evidence})


def load_json(name: str) -> dict:
    return json.loads((SRC / name).read_text(encoding="utf-8"))


actual_hashes = {
    name: hashlib.sha256((SRC / name).read_bytes()).hexdigest()
    for name in EXPECTED_HASHES
}
for name, expected in EXPECTED_HASHES.items():
    record(f"source_hash:{name}", actual_hashes[name] == expected, actual_hashes[name])

audit = load_json("rk16_dense_prefix_audit_v1.json")
independent = load_json("rk16_independent_verification_v1.json")
post_independent = load_json("rk16_postpush_independent_verification_v1.json")
finalization = load_json("rk16_finalization_v1.json")
post_finalization = load_json("rk16_postpush_finalization_v1.json")
manuscript_verification = load_json("rk16_manuscript_verification_v1.json")
manuscript = (SRC / "rk16_manuscript_section_v1.md").read_text(encoding="utf-8")
closeout = (SRC / "A8_RK16_DENSE_PREFIX_CLOSEOUT.md").read_text(encoding="utf-8")

record("audit_pass", audit["status"] == "PASS", audit["status"])
record(
    "primary_panel_counts",
    (audit["record_count"], audit["primary_method_count"], audit["primary_real_generation_call_count"]) == (18, 4, 792),
    [audit["record_count"], audit["primary_method_count"], audit["primary_real_generation_call_count"]],
)
record("dense_prefix_gate", audit["dense_prefix_superiority_pass"] is True)
record("three_comparator_gates", all(audit["per_comparator_two_metric_pass"].values()), audit["per_comparator_two_metric_pass"])
for method, expected in EXPECTED_MEANS.items():
    summary = audit["method_summary"][method]
    actual = (summary["mean_dense_budget_step_auc_v2"], summary["mean_endpoint_hypervolume_normalized_b11"])
    record(f"method_means:{method}", actual == expected, actual)

with (SRC / "rk16_primary_comparisons_v1.csv").open(newline="", encoding="utf-8") as handle:
    comparisons = list(csv.DictReader(handle))
record("six_primary_comparisons", len(comparisons) == 6, len(comparisons))
record("all_comparisons_pass", all(row["pass"] == "True" for row in comparisons))
record("all_cis_above_zero", all(float(row["ci95_low"]) > 0 for row in comparisons))
record(
    "common_holm_p",
    all(float(row["holm_p"]) == 0.000599970001499925 for row in comparisons),
    sorted({row["holm_p"] for row in comparisons}),
)
ensemble = [row for row in comparisons if row["comparison"].endswith("ensembledesign_11run")]
ensemble_effects = tuple(float(row["mean_effect"]) for row in ensemble)
record("ensemble_effects", ensemble_effects == EXPECTED_ENSEMBLE_EFFECTS, ensemble_effects)

for name, report, expected in (
    ("independent", independent, 88),
    ("postpush_independent", post_independent, 88),
    ("finalization", finalization, 53),
    ("postpush_finalization", post_finalization, 53),
    ("manuscript", manuscript_verification, 59),
):
    record(
        f"acceptance:{name}",
        report["checks_passed"] == report["checks_total"] == expected and all(c["pass"] for c in report["checks"]),
        f"{report['checks_passed']}/{report['checks_total']}",
    )
record("postpush_independent_byte_identical", (SRC / "rk16_independent_verification_v1.json").read_bytes() == (SRC / "rk16_postpush_independent_verification_v1.json").read_bytes())
record("postpush_finalization_byte_identical", (SRC / "rk16_finalization_v1.json").read_bytes() == (SRC / "rk16_postpush_finalization_v1.json").read_bytes())

negative_tokens = (
    "time_matched_comparison=false",
    "scientific_gate_passed=false",
    "codonflow_rk_evaluated=false",
    "functional_ood_evaluated=false",
    "functional_untouched_evaluated=false",
    "rk_g1_pass=false",
    "expensive_generation_authorized=false",
    "external_sota_authorized=false",
    "sota_claimed=false",
)
record("closeout_negative_boundaries", all(token in closeout for token in negative_tokens), list(negative_tokens))
record("audit_negative_boundaries", all(audit[key] is False for key in (
    "time_matched_comparison", "scientific_gate_passed", "codonflow_rk_evaluated",
    "functional_ood_evaluated", "rk_g1_pass", "expensive_generation_authorized",
    "external_sota_authorized", "sota_claimed",
)))
manuscript_tokens = (
    "22.794606", "29.972887", "14.896234", "16.693982", "5.205444", "7.989211",
    "0.702952", "0.966618", "+7.898372", "+13.278905", "88/88", "53/53",
    "Unified time-matched evaluation", "CodonFlow-RK generation", "functional OOD and untouched evaluation",
    "external SOTA remain open", "manuscript remains non-submittable",
)
record("manuscript_slide_binding", all(token in manuscript for token in manuscript_tokens), list(manuscript_tokens))

passed = sum(bool(c["pass"]) for c in checks)
report = {
    "schema": "a8-rk16-ppt-content-verification-v1",
    "status": "PASS" if passed == len(checks) else "FAIL",
    "source_commit": "4115d281abe4a798b05525dff43f751460ee03a3",
    "source_snapshot": "remote /home/codonflow-a8-rk final pushed files",
    "source_hashes": actual_hashes,
    "checks_passed": passed,
    "checks_total": len(checks),
    "checks": checks,
    "slide_values": {
        "records": 18,
        "primary_calls": 792,
        "methods": list(EXPECTED_MEANS),
        "primary_tests_passed": 6,
        "primary_tests_total": 6,
        "bootstrap_resamples": 20000,
        "independent": "88/88",
        "finalization": "53/53",
        "manuscript": "59/59",
        "means": EXPECTED_MEANS,
        "ensemble_effects": EXPECTED_ENSEMBLE_EFFECTS,
    },
}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "output": str(OUT)}, ensure_ascii=False))
raise SystemExit(0 if report["status"] == "PASS" else 1)
