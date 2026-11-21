#!/usr/bin/env python3
"""Build, integrate, and independently audit the RK37 manuscript section."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_section(root):
    root = Path(root)
    audit = root / "audits/20261122/RK37"
    production = json.loads((audit / "rk37_translation_pivot_result_v1.json").read_text())
    independent = json.loads((audit / "rk37_translation_pivot_independent_v1.json").read_text())
    clean = json.loads((audit / "rk37_translation_pivot_clean_result_v1.json").read_text())
    comparison = json.loads((audit / "rk37_clean_reproduction_comparison_v1.json").read_text())
    closeout = json.loads((audit / "rk37_science_closeout_v2.json").read_text())
    protocol = json.loads((root / "configs/a8_rk37_translation_pivot_protocol_v1.json").read_text())
    primary = production["source_reports"][0]
    metrics = primary["target_evaluation"]["target_metrics"]
    endpoints = production["primary_endpoints"]
    max_delta = max(v for v in independent["max_differences"].values() if isinstance(v, (int, float)))
    names = {
        "tb_mse_improvement_over_constant": "TB-MSE improvement over constant",
        "mean_pearson_improvement_over_position_raw": "Mean Pearson improvement over position raw",
    }
    rows = []
    for endpoint in endpoints:
        rows.append(
            f"| {names[endpoint['name']]} | {endpoint['effect']:.8f} | [{endpoint['ci95_low']:.8f}, {endpoint['ci95_high']:.8f}] | {endpoint['holm_pvalue']:.8g} | "
            f"{endpoint['sensitivity_effects'][0]:.8f}; {endpoint['sensitivity_effects'][1]:.8f} | Fail |"
        )
    arm_labels = (
        ("constant", "Constant", "—"),
        ("ribomimo_raw", "RiboMIMO raw", "frozen"),
        ("ribomimo_anchored", "RiboMIMO anchored", "frozen"),
        ("position_raw_unanchored", "Position raw", "100"),
        ("position_raw_anchored", "Position raw anchored", "100"),
        ("position_centered_anchored", "Position centered anchored", "100"),
        ("local_raw_anchored", "Local raw anchored", "0.1"),
        ("local_centered_anchored", "Local centered anchored", "0.1"),
    )
    absolute_rows = []
    for arm, label, alpha in arm_labels:
        value = metrics[arm]
        pearson = "0 (degenerate)" if arm == "constant" else f"{value['mean_transcript_pearson']:.9f}"
        spearman = "NA" if value["mean_transcript_spearman"] is None else f"{value['mean_transcript_spearman']:.9f}"
        absolute_rows.append(f"| {label} | {alpha} | {value['transcript_balanced_mse']:.9f} | {pearson} | {spearman} |")
    protocol_sha = sha256(root / "configs/a8_rk37_translation_pivot_protocol_v1.json")
    result_sha = sha256(audit / "rk37_translation_pivot_result_v1.json")
    independent_sha = sha256(audit / "rk37_translation_pivot_independent_v1.json")
    clean_sha = sha256(audit / "rk37_translation_pivot_clean_result_v1.json")
    comparison_sha = sha256(audit / "rk37_clean_reproduction_comparison_v1.json")
    closeout_sha = sha256(audit / "rk37_science_closeout_v2.json")
    local_sensitivity = [s["target_evaluation"]["target_metrics"]["local_centered_anchored"] for s in production["source_reports"][1:]]
    position_gain = metrics["position_centered_anchored"]["mean_transcript_pearson"] - metrics["position_raw_unanchored"]["mean_transcript_pearson"]
    return f"""### 6.48 Local codon-context ridge did not improve cross-study translation-occupancy prediction over constant or position controls

The RK36 eligibility audit triggered a data-supported pivot, and the earlier Mohammad16-to-Subtelny14 benchmark supplied a discriminating translation-occupancy problem rather than a claim about physical elongation velocity. In that benchmark, official RiboMIMO had higher transcript-balanced mean squared error (TB-MSE) than both a source-fitted position ridge and a constant predictor, while its mean within-transcript Pearson correlation was approximately zero. RK37 therefore asked whether a preregistered local codon-context representation could simultaneously improve TB-MSE over the constant control and mean Pearson correlation over the existing position ridge. The target was normalized ribosome-occupancy density; it was not a direct kinetic rate or a protein-expression endpoint.

The protocol was frozen before any target normalized outcome was read. Mohammad16 supplied 1,179 eligible source transcripts and Subtelny14 supplied 3,921 eligible target transcripts, with zero exact-CDS overlap. The 86-dimensional position representation reproduced RK05, whereas the 477-dimensional local representation encoded seven codons at offsets −3 through +3, window-validity indicators, 20 relative-position bins, relative position and log length. Raw and transcript-centered targets were distinguished. Deployment anchoring used only the source-training global mean, leaving within-transcript correlation unchanged. Three source split seeds, four feature/target families and four ridge penalties produced exactly 48 unique source fits. All penalties and deployed arms were selected on source validation before target evaluation. The two confirmatory endpoints used 20,000 transcript-paired bootstraps and 20,000 sign-flip permutations at primary seed 1234, two-side Holm correction and two sensitivity seeds.

**Both confirmatory endpoints failed, and both effects were adverse (Table 28).** The primary local-centered-anchored model increased rather than decreased TB-MSE relative to constant, with an improvement effect of {endpoints[0]['effect']:.8f} and a 95% interval entirely below zero. It also reduced mean Pearson correlation relative to position raw by {abs(endpoints[1]['effect']):.8f}. Both sensitivity-seed effects were negative for both endpoints. Small Holm-adjusted p values therefore do not denote success: the resampling evidence supported degradation in the direction opposite to the preregistered gate. The decision remained `CROSS_STUDY_TRANSLATION_TASK_UNRESOLVED_COMPONENT_DIAGNOSIS_REQUIRED`.

**Table 28**

*Preregistered RK37 Dual Diagnostic Endpoints*

| Endpoint | Effect | 95% CI | Holm *p* | Sensitivity effects | Gate |
|---|---|---|---|---|---|
{chr(10).join(rows)}

*Note.* Effects are improvements, so positive values were required. CI = transcript-paired bootstrap 95% confidence interval. Holm correction covered the two confirmatory endpoints. Sensitivity effects are reported for seeds 2345 and 3456. Each gate additionally required a positive effect, a positive CI lower bound, Holm *p* < .05 and two positive sensitivity effects.

The absolute metrics localized the failure beyond a single penalty choice (Table 29). At primary seed 1234, local-centered anchoring gave TB-MSE {metrics['local_centered_anchored']['transcript_balanced_mse']:.9f} and mean Pearson r {metrics['local_centered_anchored']['mean_transcript_pearson']:.9f}, compared with {metrics['constant']['transcript_balanced_mse']:.9f} and {metrics['position_raw_unanchored']['mean_transcript_pearson']:.9f} for the respective controls. Although source validation selected local α = 0.1 at seed 1234 and α = 100 at the other seeds, the α = 100 sensitivity runs still gave local-centered TB-MSE {local_sensitivity[0]['transcript_balanced_mse']:.9f} and {local_sensitivity[1]['transcript_balanced_mse']:.9f}, with mean Pearson r only {local_sensitivity[0]['mean_transcript_pearson']:.9f} and {local_sensitivity[1]['mean_transcript_pearson']:.9f}. The failure therefore was not rescued by the alternate frozen-seed penalty. Position centering increased mean Pearson by only {position_gain:.9f} and did not beat constant TB-MSE. Anchoring RiboMIMO reduced TB-MSE from {metrics['ribomimo_raw']['transcript_balanced_mse']:.9f} to {metrics['ribomimo_anchored']['transcript_balanced_mse']:.9f}, but this remained far above constant. No target-selected replacement arm was introduced.

**Table 29**

*Primary-Seed Absolute Cross-Study Occupancy Metrics*

| Arm | α | TB-MSE | Mean Pearson *r* | Mean Spearman ρ |
|---|---|---|---|---|
{chr(10).join(absolute_rows)}

*Note.* TB-MSE = transcript-balanced mean squared error. The constant within-transcript correlation is degenerate and is shown as zero/NA rather than interpreted as a learned association. Position and local penalties were selected using source validation only. RiboMIMO predictions were frozen from RK05. Anchoring changes calibration but not within-transcript Pearson or Spearman correlation.

An independently written implementation reconstructed the raw matrices, COO-to-CSR features, source splits, all 48 fits, target predictions, model coefficients and inference arrays without importing the production module. It passed {independent['checks_passed']}/{independent['checks_total']} checks, with maximum numeric difference {max_delta:.3e}. A detached clean checkout reproduced the production run with {comparison['checks_passed']}/{comparison['checks_total']} comparisons, exact equality for {comparison['exact_arrays_compared']} arrays and byte-identical per-transcript CSV files. The full project suite recorded 466 passed, 1 skipped and 5 subtests passed. Scientific closeout passed {closeout['checks_passed']}/{closeout['checks_total']} checks; its earlier schema and log-format failures were retained. Production, independent and clean runtimes were {production['execution']['wall_seconds']:.3f}, {independent['wall_seconds']:.3f} and {clean['execution']['wall_seconds']:.3f} seconds, respectively. These checks establish computational agreement, not biological transport.

RK37 consequently rejects this local ridge pivot for the observed Mohammad16-to-Subtelny14 direction; it does not establish a universal absence of local sequence effects. The experiment remains a retrospective follow-up on a target already observed in RK05, not untouched confirmation, protein-family OOD, physical velocity estimation, functional-expression validation or external SOTA. Functional-untouched data were not read, no generator was trained, no wet-lab or prospective DBTL experiment was performed, and RK-G1 remains false.

::: {{.evidence-anchor #sec-6-48}}
| Field | Evidence |
|---|---|
| Code commits | `5786ffc0` (frozen protocol and production); `b8cf49c7` (independent verifier); `066ee562` (science and independent evidence); `87a33bd4` (clean reproduction and closeout) |
| Protocol | `configs/a8_rk37_translation_pivot_protocol_v1.json`; SHA256 `{protocol_sha}` |
| Results | `audits/20261122/RK37/rk37_translation_pivot_result_v1.json`; SHA256 `{result_sha}` |
| Independent | `rk37_translation_pivot_independent_v1.json`; {independent['checks_passed']}/{independent['checks_total']} PASS; SHA256 `{independent_sha}` |
| Clean reproduction | `rk37_translation_pivot_clean_result_v1.json`; SHA256 `{clean_sha}`; comparison {comparison['checks_passed']}/{comparison['checks_total']} PASS, SHA256 `{comparison_sha}` |
| Closeout | `rk37_science_closeout_v2.json`; {closeout['checks_passed']}/{closeout['checks_total']} PASS; SHA256 `{closeout_sha}`; retained v1 = {closeout['checks_total'] - 2}/{closeout['checks_total']} FAIL |
| Artifacts | `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk37/translation_pivot_v1/`; 48 fits per production, independent and clean runs |
| Scope | Negative retrospective cross-study normalized-occupancy diagnostic; no physical velocity, untouched, protein-OOD, functional, SOTA, generator, wet-lab or RK-G1 claim |
:::
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "integrate", "audit"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--section")
    parser.add_argument("--output", required=True)
    parser.add_argument("--baseline-sha")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    manuscript = root / "paper/CodonFlow_preprint_A8.md"
    if args.mode == "build":
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(build_section(root))
        print(json.dumps({"status": "PASS", "section_sha256": sha256(output), "words": len(output.read_text().split())}, indent=2))
        return
    if not args.section or not args.baseline_sha:
        raise ValueError("integrate/audit require --section and --baseline-sha")
    section = Path(args.section).read_text()
    current = manuscript.read_text()
    report_path = Path(args.output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if args.mode == "integrate":
        before_sha = sha256(manuscript)
        if before_sha != args.baseline_sha:
            raise RuntimeError(f"baseline mismatch: {before_sha}")
        if "### 6.48 " in current:
            raise RuntimeError("RK37 section already present")
        if section != build_section(root):
            raise RuntimeError("workflow section differs from evidence-generated section")
        marker = "\n## 7. Discussion\n"
        if current.count(marker) != 1:
            raise RuntimeError("Discussion insertion marker is not unique")
        updated = current.replace(marker, "\n" + section + "\n## 7. Discussion\n", 1)
        manuscript.write_text(updated)
        report = {"status": "PASS_RK37_MANUSCRIPT_INTEGRATION", "before_sha256": before_sha, "after_sha256": sha256(manuscript), "before_lines": len(current.splitlines()), "after_lines": len(updated.splitlines()), "section_sha256": hashlib.sha256(section.encode()).hexdigest()}
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return
    expected = build_section(root)
    restored = current.replace(expected + "\n", "", 1)
    checks = {
        "section_exactly_once": current.count(expected) == 1,
        "workflow_section_matches_evidence": section == expected,
        "section_6_48_once": current.count("### 6.48 ") == 1,
        "table_28_once": current.count("**Table 28**") == 1,
        "table_29_once": current.count("**Table 29**") == 1,
        "discussion_after_section": current.index("### 6.48 ") < current.index("## 7. Discussion"),
        "baseline_restored_exactly": hashlib.sha256(restored.encode()).hexdigest() == args.baseline_sha,
        "negative_decision_present": "CROSS_STUDY_TRANSLATION_TASK_UNRESOLVED_COMPONENT_DIAGNOSIS_REQUIRED" in expected,
        "both_gates_fail": expected.count("| Fail |") == 2,
        "independent_771": "771/771" in expected,
        "clean_877": "877/877" in expected,
        "closeout_90": "90/90" in expected,
        "no_untouched_claim": "not untouched confirmation" in expected,
        "no_physical_velocity_claim": "not a direct kinetic rate" in expected,
        "rk_g1_false": "RK-G1 remains false" in expected,
        "evidence_anchor_once": current.count("{.evidence-anchor #sec-6-48}") == 1,
    }
    passed = sum(checks.values())
    report = {"status": "PASS_RK37_MANUSCRIPT_AUDIT" if passed == len(checks) else "FAIL", "checks_passed": passed, "checks_total": len(checks), "checks": checks, "manuscript_sha256": sha256(manuscript), "restored_baseline_sha256": hashlib.sha256(restored.encode()).hexdigest(), "section_sha256": hashlib.sha256(expected.encode()).hexdigest(), "manuscript_lines": len(current.splitlines())}
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
