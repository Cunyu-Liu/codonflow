#!/usr/bin/env python3
"""Generate RK34 English section solely from independently accepted evidence."""
from pathlib import Path
import argparse
import hashlib
import json


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def f(value):
    return f"{value:.6f}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    args = parser.parse_args()
    paths = {name: args.base / filename for name, filename in {
        "protocol": "a8_rk34_start_context_protocol_v2.json",
        "result": "rk34_start_context_result_v2.json",
        "independent": "rk34_start_context_independent_v2.json",
        "reproduction": "rk34_clean_reproduction_comparison_v1.json",
        "closeout": "rk34_closeout_v2.json",
    }.items()}
    data = {name: json.loads(path.read_text()) for name, path in paths.items()}
    result, independent = data["result"], data["independent"]
    reproduction, closeout = data["reproduction"], data["closeout"]
    assert independent["status"] == reproduction["status"] == closeout["status"] == "PASS"
    assert result["scientific_conclusion"] == independent["scientific_conclusion"] == "JOINT_EXACT_CONTEXT_WITHOUT_SEPARABLE_CONTRIBUTIONS_RETROSPECTIVELY"
    assert result["n_confirmatory_tests"] == 20 and result["n_confirmatory_pass"] == 12
    primary = [row for row in result["primary_tests"] if row["analysis"] == "primary"]
    sensitivity = [row for row in result["primary_tests"] if row["analysis"] == "sensitivity_d0"]
    assert len(primary) == len(sensitivity) == 20
    families = ["exact_vs_simple", "upstream_given_start", "start_given_upstream", "start_without_upstream", "upstream_without_start"]
    family_results = {(row["analysis"], row["family"]): row for row in result["family_results"]}
    assert family_results[("primary", "exact_vs_simple")]["n_pass"] == 4
    assert all(not family_results[("primary", family)]["all_four_pass"] for family in families[1:])
    hashes = {name: sha(path) for name, path in paths.items()}
    lines = []
    add = lines.append
    add("### 6.45 Exact local context adds robust signal, but matched ablation does not separably identify upstream or start-codon contributions")
    add("")
    add("RK32 localized the Kudla structural increment to a 42-nt window spanning the last four 5′ UTR nucleotides, the start ATG, and CDS positions 4–38, whereas RK33 found no increment for a truncated CDS4–45 window in Mordstein observed R1. RK34 asked whether the exact local context as a whole, the upstream four nucleotides, or the start ATG accounted for the within-Kudla result. This was a retrospective, outcome-known, fixed-GFP analysis rather than an independent confirmation, biological perturbation, or cross-host transport test. The 154 measurement rows, 150 exact-CDS groups, 37 sequence clusters, seed–fold assignments, simple CAI/GC/GC3 features, Ridge and histogram gradient-boosting models, and whole-cluster inference remained fixed.")
    add("")
    add("Four equal-length contexts shared the same CDS4–38 body: exact_real contained the observed upstream four nucleotides and ATG; start_only replaced the upstream nucleotides with N; upstream_only replaced ATG with NNN; and neither masked both elements. Thus every window was 42 nt, and the two factorial contrasts for each element varied only that element in the corresponding background. ViennaRNA at 37 °C with dangling ends enabled (dangles=2) defined the confirmatory analysis; dangles=0 was a prespecified sensitivity analysis that could not rescue a failed primary result. Seven new structure arms required 700 fits, while 200 accepted simple and Vienna-local exact-d2 fits were reused from RK32, yielding 900 evaluated fits.")
    add("")
    add("Five paired families each contained two models × two metrics: exact_real versus simple, upstream given start, start given upstream, start without upstream, and upstream without start. The 20 confirmatory endpoints required a positive observed effect, a positive lower 95% whole-cluster bootstrap confidence limit, Holm-adjusted cluster-swap p < 0.05 across those 20 tests, and at least eight positive seeds. A family required all four endpoints. An upstream contribution required both upstream families, and a start contribution required both start families; these rules prevented a single favorable background or model from being interpreted as an independently identified component.")
    add("")
    add("**The exact local context passed 4/4 endpoints, but none of the four separability families passed all four endpoints (Table 23).** In the confirmatory analysis, upstream-given-start passed 3/4, start-given-upstream 2/4, start-without-upstream 1/4, and upstream-without-start 2/4, giving 12/20 positive endpoints overall. Ridge produced several strong component contrasts, but HistGB and MSE endpoints did not consistently satisfy the joint gate. For example, upstream-given-start HistGB MSE improvement had Holm-adjusted p = 0.138943; start-given-upstream HistGB Spearman and MSE had adjusted p = 0.121594 and 0.138943; and start-without-upstream HistGB effects were near zero with adjusted p = 1.0. The sensitivity analysis retained exactly the same family-level decisions: exact_real versus simple passed 4/4, whereas the four component families did not pass. The supported conclusion is therefore a joint exact-context increment without separately identified upstream or start-codon contributions.")
    add("")
    add("**Table 23**")
    add("")
    add("*Confirmatory Paired Endpoints for the Equal-Length 42-nt Factorial Ablation*")
    add("")
    add("| Comparison | Model | Metric | Effect | 95% CI | Raw *p* | Holm *p* | Positive seeds | Pass |")
    add("|---|---|---|---:|---|---:|---:|---:|---|")
    labels = {"exact_vs_simple": "exact−simple", "upstream_given_start": "upstream | start", "start_given_upstream": "start | upstream", "start_without_upstream": "start | no upstream", "upstream_without_start": "upstream | no start"}
    for row in primary:
        model = {"ridge": "Ridge", "histgb": "HistGB"}[row["model"]]
        metric = "Spearman" if row["metric"] == "spearman_effect" else "MSE improvement"
        add(f'| {labels[row["family"]]} | {model} | {metric} | {f(row["observed_effect"])} | [{f(row["ci95"][0])}, {f(row["ci95"][1])}] | {row["p_cluster_swap"]:.6f} | {row["p_holm"]:.6f} | {row["positive_seeds"]}/10 | {"Yes" if row["pass"] else "No"} |')
    add("")
    add("*Note.* Effects are the first context minus the comparator; MSE improvement is comparator MSE minus context MSE. CI is the 95% whole-cluster bootstrap interval. Raw and Holm-adjusted *p*-values use 20,000 cluster-swap permutations.")
    add("")
    add("Primary-seed absolute performance illustrates why the joint gate matters (Table 24). The exact-d2 arm improved Ridge Spearman from −0.318413 for simple features to 0.666270 and HistGB Spearman from 0.302424 to 0.705171, with corresponding MSE reductions. Artificial N-masked arms showed model-dependent gains and losses, however, and these absolute scores did not override the paired factorial inference. The negative Ridge simple Spearman also warns against treating a high incremental effect as evidence that either the backbone or the resulting predictor is universally strong.")
    add("")
    add("**Table 24**")
    add("")
    add("*Absolute Held-Out Performance for Primary Seed 20261221*")
    add("")
    add("| Model | Arm | Spearman | MSE |")
    add("|---|---|---:|---:|")
    arm_labels = {"null": "null", "simple": "simple", "exact_real_d2": "exact d2", "start_only_d2": "start only d2", "upstream_only_d2": "upstream only d2", "neither_d2": "neither d2", "exact_real_d0": "exact d0", "start_only_d0": "start only d0", "upstream_only_d0": "upstream only d0", "neither_d0": "neither d0"}
    for row in result["primary_absolute_performance"]:
        if row["arm"] == "null":
            model, arm = "Intercept", "null"
        else:
            model, arm = row["arm"].split("_", 1)
            model = {"ridge": "Ridge", "histgb": "HistGB"}[model]
        add(f'| {model} | {arm_labels[arm]} | {f(row["spearman"])} | {f(row["mse"])} |')
    add("")
    add("*Note.* Dangles=0 arms are sensitivity analyses and are shown for completeness rather than as replacements for the confirmatory dangles=2 comparisons.")
    add("")
    add(f'An independently written raw-source implementation reconstructed the windows, energies, clusters, folds, all 900 fits, seed statistics, 40 primary-plus-sensitivity tests, and 82 inference arrays. It passed {independent["checks_passed"]}/{independent["checks_total"]} checks; the maximum absolute prediction difference was {independent["max_deltas"]["prediction"]:.3g}, and all 40 test records and 82 arrays matched within the frozen numerical criteria. The initial independent run retained a single schema failure because the null-baseline arm label became an empty CSV field on readback; only that identifier was canonicalized in verifier v2, with the numerical tolerances and scientific outputs unchanged. A no-hardlinks clean checkout of `4533dd1794fa1dc6fd7519b3b3131463b1ae826e` then repeated production and independent verification. The comparison passed {reproduction["checks_passed"]}/{reproduction["checks_total"]} checks: {reproduction["production_csv_byte_identical"]}/6 production CSV files, {reproduction["production_arrays_exact"]}/82 production arrays, {reproduction["independent_csv_byte_identical"]}/5 independent CSV files, and {reproduction["independent_arrays_exact"]}/82 independent arrays were exactly reproduced. The full project suite reported 455 passed, one skipped, and five passing subtests.')
    add("")
    add("These findings support only a retrospective, fixed-Kudla, sequence-cluster-OOD increment for the exact local context. N-masking is a computational ablation, not a biological perturbation, and the unmatched model behavior leaves interaction, background dependence, nonlinear feature use, and limited cluster-level precision as competing explanations. The experiment does not establish independent upstream or ATG necessity, universal initiation mechanisms, measured-structure validity, host or assay identification, functional or protein OOD, external SOTA, or RK-G1. Independent complete-CDS transport, unified time-matched and seven-method dense comparisons, multispecies VeloHARMO, prospective DBTL, and wet-lab validation remain open. Functional untouched data were not read, and expensive generator training was not authorized.")
    add("")
    add("::: {.evidence-anchor #sec-6-45}")
    add("| Field | Evidence |")
    add("|---|---|")
    add("| Code commits | `4533dd1794fa1dc6fd7519b3b3131463b1ae826e` (accepted science); `cb8c1976d18a2acfe7b92f3039933a0701bc1c13` (clean reproduction and closeout) |")
    add("| Code | `scripts/a8_rk34_run_start_context.py`; `scripts/a8_rk34_verify_start_context_independent.py`; `scripts/a8_rk34_compare_reproduction.py`; `scripts/a8_rk34_closeout.py` |")
    add("| Protocol | `audits/20261121/RK34/a8_rk34_start_context_protocol_v2.json` |")
    add("| Results | `audits/20261121/RK34/rk34_start_context_result_v2.json`; `rk34_start_context_independent_v2.json`; `rk34_clean_reproduction_comparison_v1.json`; `rk34_closeout_v2.json` |")
    add(f'| SHA256 | protocol `{hashes["protocol"]}`; result `{hashes["result"]}`; independent `{hashes["independent"]}`; reproduction `{hashes["reproduction"]}`; closeout `{hashes["closeout"]}` |')
    add("| Analysis | 154 retrospective measurement rows; 150 exact-CDS groups; 37 sequence clusters; 10 seeds × 5 folds; 700 new + 200 reused = 900 evaluated fits; 20 confirmatory + 20 sensitivity tests |")
    add("| Scope | Fixed-Kudla exact local context and artificial matched ablation only; no separable biological mechanism, independent transport, functional/protein OOD, generator, or wet-lab claim |")
    add(":::")
    add("")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines))
    metadata = {"section": "6.45", "tables": [23, 24], "scientific_conclusion": result["scientific_conclusion"], "endpoints_passed": 12, "endpoints_total": 20, "family_results": [family_results[("primary", family)] for family in families], "independent_checks": f'{independent["checks_passed"]}/{independent["checks_total"]}', "reproduction_checks": f'{reproduction["checks_passed"]}/{reproduction["checks_total"]}', "evidence_sha256": hashes, "section_sha256": sha(args.output)}
    args.metadata.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
