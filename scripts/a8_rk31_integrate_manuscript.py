#!/usr/bin/env python3
"""Render and insert the independently verified RK31 manuscript section."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

START = "<!-- A8_RK31_START -->"
END = "<!-- A8_RK31_END -->"
ANCHOR_START = "<!-- A8_RK31_ANCHORS_START -->"
ANCHOR_END = "<!-- A8_RK31_ANCHORS_END -->"
CONTEXT = {"hela_no_intron": "HeLa no intron", "hela_with_intron": "HeLa with intron",
           "hek293_no_intron": "HEK293 no intron"}
ARM = {"null": "Null", "shared_simple": "Shared simple", "shared_full": "Shared full",
       "context_gated_full": "Context-gated full", "no_transport_simple": "No-transport simple",
       "no_transport_full": "No-transport full"}
METRIC = {"spearman_effect": "ΔSpearman", "mse_improvement": "MSE improvement"}


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fmt(value, digits=9) -> str:
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.{digits}g}"


def table(headers, rows, numeric_columns) -> str:
    aligns = []
    for i in range(len(headers)):
        aligns.append(":---:" if i in numeric_columns else "---")
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(aligns) + "|"]
    lines.extend("| " + " | ".join(str(x) for x in row) + " |" for row in rows)
    return "\n".join(lines)


def replace_marked(text: str, start: str, end: str, body: str, before: str) -> str:
    wrapped = f"{start}\n{body.strip()}\n{end}\n\n"
    if start in text or end in text:
        if text.count(start) != 1 or text.count(end) != 1 or text.index(start) > text.index(end):
            raise ValueError(f"Invalid marked block: {start}")
        return text[:text.index(start)] + wrapped + text[text.index(end) + len(end):].lstrip("\n")
    if before not in text:
        raise ValueError(f"Insertion anchor absent: {before}")
    return text.replace(before, wrapped + before, 1)


def render(protocol, result, independent, closeout, reproduction) -> str:
    if closeout["status"] != "PASS_RK31_VERIFIED_RESULT_PACKAGING" or closeout["checks_passed"] != closeout["checks_total"]:
        raise ValueError("RK31 closeout did not pass")
    if independent["status"] != "PASS_INDEPENDENT_VERIFICATION" or independent["checks_passed"] != 177:
        raise ValueError("RK31 independent verification did not pass")
    if reproduction["status"] != "PASS_RK31_CLEAN_CHECKOUT_REPRODUCTION" or reproduction["checks_passed"] != 77:
        raise ValueError("RK31 clean reproduction did not pass")
    if result["scientific_conclusion"] != closeout["scientific_conclusion"] or len(result["primary_endpoints"]) != 24:
        raise ValueError("RK31 result binding mismatch")
    n_seeds = len(protocol["outer_evaluation"]["sensitivity_seeds"])
    folds = protocol["outer_evaluation"]["folds"]
    boot = protocol["inference"]["cluster_bootstrap"]["resamples"]
    perm = protocol["inference"]["cluster_sign_swap_permutation"]["permutations"]
    primary_rows = []
    for r in result["primary_endpoints"]:
        primary_rows.append([CONTEXT[r["context"]], ARM[r["baseline"]], METRIC[r["metric"]],
                             fmt(r["observed_effect"]), f"[{fmt(r['ci95'][0])}, {fmt(r['ci95'][1])}]",
                             fmt(r["p_holm"]), f"{r['positive_seeds']}/{n_seeds}", fmt(r["pass"])])
    primary_table = table(["Context", "Baseline", "Endpoint", "Observed effect", "95% CI", "Holm *p*", "Positive seeds", "Decision"],
                          primary_rows, {3, 4, 5, 6, 7})
    absolute_rows = [[CONTEXT[r["context"]], ARM[r["arm"]], fmt(r["spearman"]), fmt(r["mse"])]
                     for r in result["primary_absolute_performance"]]
    absolute_table = table(["Context", "Arm", "Spearman", "MSE"], absolute_rows, {2, 3})

    def endpoint(context, baseline, metric):
        return next(r for r in result["primary_endpoints"] if r["context"] == context and
                    r["baseline"] == baseline and r["metric"] == metric)

    hela_s = endpoint("hela_no_intron", "shared_full", "spearman_effect")
    hela_m = endpoint("hela_no_intron", "shared_full", "mse_improvement")
    adverse = endpoint("hela_with_intron", "no_transport_full", "spearman_effect")
    diffs = independent["max_abs_differences"]
    conclusion = result["scientific_conclusion"]
    return f"""### 6.42 Known-context gating did not support broad MFE applicability

RK31 asked whether explicit context-dependent MFE slopes improved variant-level out-of-distribution prediction when the three Mordstein contexts were known but sequence clusters were held out jointly. It reused the independently verified RK30 analysis table containing {result['n_variants']} variants in {result['n_clusters']} clusters and did not download new reads, recluster variants, or select variants by outcome. The analysis was registered as a retrospective outcome-known follow-up, not an independent untouched confirmation or an unseen-context transport experiment.

The simple features were GC3, GC, CpG, and CAI. Full arms added full-fragment MFE and 48-nt-window minimum and mean MFE. Shared-simple and shared-full models pooled contexts with two nonreference context indicators. The context-gated-full arm added six context-by-MFE interactions while retaining shared simple-feature slopes. Separate no-transport-simple and no-transport-full models were fit within each context, and a training-fold context mean supplied a descriptive null reference. Ridge used the RK30 fold-internal scaling and a frozen alpha of 1.0 without hyperparameter search. The frozen evaluation used {n_seeds} seeds, {folds} whole-cluster folds per seed, and {result['ridge_fit_count']} real CPU fits. A cluster held out in one context was excluded from training in every context, and outcomes of held-out variants in other contexts were never predictors.

The candidate was context-gated full. It was compared with shared simple, shared full, no-transport simple, and no-transport full using Spearman effects and MSE improvement in each context. The resulting 24 endpoints formed one Holm family. Inference used {boot:,} whole-cluster bootstraps and {perm:,} cluster sign-swap permutations. An endpoint required a positive primary-seed observed effect, a 95% CI lower bound above zero, Holm *p* < 0.05, and at least 8/10 positive seeds. Broad known-context applicability required all 24 endpoints to pass; the six gated-versus-shared-full endpoints were also examined separately as the direct gating subset.

**Table 17**

*Known-Context Gated-MFE Primary Endpoints*

{primary_table}

*Note.* ΔSpearman = candidate − baseline; MSE improvement = baseline − candidate. Observed effects and resampling inference use frozen primary seed {result['primary_seed']}; positive-seed counts summarize all {n_seeds} seeds. CI denotes the 95% whole-cluster bootstrap confidence interval. The family-wise Holm adjustment spans all 24 endpoints. The literal null arm is a valid model label, not missing data.

No primary endpoint passed, and the context-level decision was false for HeLa no intron, HeLa with intron, and HEK293 no intron. The direct gating subset also failed. A descriptive positive point pattern did not override this decision: in HeLa no intron, gated full versus shared full had a primary-seed Spearman effect of {fmt(hela_s['observed_effect'])}, a 95% CI of [{fmt(hela_s['ci95'][0])}, {fmt(hela_s['ci95'][1])}], {hela_s['positive_seeds']}/10 positive seeds, and Holm *p* = {fmt(hela_s['p_holm'])}. The corresponding MSE improvement was {fmt(hela_m['observed_effect'])}, with a 95% CI of [{fmt(hela_m['ci95'][0])}, {fmt(hela_m['ci95'][1])}], {hela_m['positive_seeds']}/10 positive seeds, and Holm *p* = {fmt(hela_m['p_holm'])}. Both endpoints failed the frozen joint rule.

An adverse comparison was also retained rather than removed. In HeLa with intron, gated full versus no-transport full had a primary-seed Spearman effect of {fmt(adverse['observed_effect'])}, a 95% CI of [{fmt(adverse['ci95'][0])}, {fmt(adverse['ci95'][1])}], Holm *p* = {fmt(adverse['p_holm'])}, and {adverse['positive_seeds']}/10 positive seeds. This result does not identify a causal mechanism, but it directly contradicts interpreting the gated model as a uniformly beneficial applicability strategy.

**Table 18**

*Absolute Known-Context Variant-OOD Performance at the Primary Seed*

{absolute_table}

*Note.* Values use frozen primary seed {result['primary_seed']}. Null is the training-fold context mean. These are retrospective fixed-Flow-seq outcomes, not direct RFU, translation velocity, mRNA decay, functional validation, or an external SOTA comparison.

The resulting conclusion was `{conclusion}`. This rejects the frozen broad known-context applicability claim; it does not establish that every possible context-dependent mechanism is ineffective. Production required {result['elapsed_seconds']:.6f} s and independent recomputation required {independent['elapsed_seconds']:.6f} s. The independent implementation did not import production or RK28 helpers and passed {independent['checks_passed']}/{independent['checks_total']} checks. Maximum absolute differences were {fmt(diffs['prediction'], 6)} for predictions, {fmt(diffs['metric'], 6)} for metrics, {fmt(diffs['effect'], 6)} for seed effects, {fmt(diffs['inference'], 6)} for inference arrays, and {fmt(diffs['primary_ci'], 6)} for primary confidence intervals. Release closeout passed {closeout['checks_passed']}/{closeout['checks_total']} checks, and project testing passed 423 tests with one skipped test.

A separate clean checkout at {reproduction['clean_clone_head']} repeated the complete analysis and independent verification. The clean comparison passed {reproduction['checks_passed']}/{reproduction['checks_total']} checks: all five CSV artifacts were byte-identical and all {reproduction['npz_array_count']} inference arrays matched exactly. Clean production and independent verification required {reproduction['production_elapsed_seconds_clean']:.6f} and {reproduction['independent_elapsed_seconds_clean']:.6f} s, respectively. The retained history includes an initial provenance-gate stop before any fit and an initial independent-report failure caused by literal `null` being parsed as missing; the corrected provenance check and literal-null parsing did not alter the scientific definitions or production artifacts.

RK31 does not read functional-untouched data, authorize generator training, perform wet-lab or prospective design–build–test work, establish protein OOD, close complete external SOTA, or complete RK-G1. The manuscript remains a non-submittable working draft. Complete external SOTA, unified time-matched comparison, dense budget-step trajectories, functional OOD, and the RK-G1 generation decision remain open rather than being reclassified as completed by this retrospective result.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ["protocol", "result", "independent", "closeout", "reproduction", "manuscript", "section-output", "output", "report"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    result = json.loads(args.result.read_text())
    independent = json.loads(args.independent.read_text())
    closeout = json.loads(args.closeout.read_text())
    reproduction = json.loads(args.reproduction.read_text())
    if closeout["protocol_sha256"] != sha256(args.protocol) or closeout["result_sha256"] != sha256(args.result):
        raise ValueError("Protocol/result hash binding failed")
    if closeout["independent_sha256"] != sha256(args.independent):
        raise ValueError("Independent hash binding failed")
    section = START + "\n" + render(protocol, result, independent, closeout, reproduction) + "\n" + END
    args.section_output.write_text(section + "\n")
    original = args.manuscript.read_text()
    text = replace_marked(original, START, END, section[len(START):-len(END)], "## 7. Discussion")
    anchors = table(["Evidence", "SHA256"], [
        ["RK31 frozen protocol", sha256(args.protocol)],
        ["RK31 verified production result", sha256(args.result)],
        ["RK31 independent verification", sha256(args.independent)],
        ["RK31 release closeout", sha256(args.closeout)],
        ["RK31 clean-checkout reproduction comparison", sha256(args.reproduction)],
    ], {1})
    text = replace_marked(text, ANCHOR_START, ANCHOR_END, anchors, "A7 is retained as the prior manuscript snapshot.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + ".tmp-rk31")
    temporary.write_text(text)
    os.replace(temporary, args.output)
    report = {
        "status": "PASS_RK31_MANUSCRIPT_INTEGRATION",
        "protocol_sha256": sha256(args.protocol), "result_sha256": sha256(args.result),
        "independent_sha256": sha256(args.independent), "closeout_sha256": sha256(args.closeout),
        "reproduction_sha256": sha256(args.reproduction),
        "section_sha256": sha256(args.section_output), "manuscript_sha256": sha256(args.output),
        "input_manuscript_sha256": sha256(args.manuscript),
        "input_lines": len(original.splitlines()), "output_lines": len(text.splitlines()),
        "primary_endpoints": len(result["primary_endpoints"]),
        "absolute_rows": len(result["primary_absolute_performance"]),
        "scientific_conclusion": result["scientific_conclusion"],
        "working_draft": True,
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
