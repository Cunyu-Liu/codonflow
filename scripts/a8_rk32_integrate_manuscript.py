#!/usr/bin/env python3
"""Render and insert the independently verified RK32 manuscript section."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

START = "<!-- A8_RK32_START -->"
END = "<!-- A8_RK32_END -->"
ANCHOR_START = "<!-- A8_RK32_ANCHORS_START -->"
ANCHOR_END = "<!-- A8_RK32_ANCHORS_END -->"
ARM = {
    "source_local": "Source local", "vienna_local": "Vienna local", "source_full": "Source full",
    "vienna_full_cds": "Vienna full CDS", "vienna_full_mrna": "Vienna full mRNA",
    "mordstein_like": "Mordstein-like",
}
ABS_ARM = {"null": "Null", "ridge_simple": "Ridge simple", "histgb_simple": "HistGB simple", **{
    f"{model}_{arm}": f"{model_name} {arm_name}"
    for model, model_name in [("ridge", "Ridge"), ("histgb", "HistGB")]
    for arm, arm_name in ARM.items()
}}
METRIC = {"spearman_effect": "ΔSpearman", "mse_improvement": "MSE improvement"}
MODEL = {"ridge": "Ridge", "histgb": "HistGB"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fmt(value, digits=9) -> str:
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.{digits}g}"


def table(headers, rows, numeric_columns) -> str:
    aligns = [":---:" if i in numeric_columns else "---" for i in range(len(headers))]
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


def render(protocol, preflight, result, independent, closeout, reproduction) -> str:
    if closeout["status"] != "PASS_RK32_VERIFIED_RESULT_PACKAGING" or closeout["checks_passed"] != closeout["checks_total"]:
        raise ValueError("RK32 closeout did not pass")
    if independent["status"] != "PASS" or len(independent["checks"]) != 23 or not all(x["pass"] for x in independent["checks"]):
        raise ValueError("RK32 independent verification did not pass")
    if reproduction["status"] != "PASS_RK32_CLEAN_CHECKOUT_REPRODUCTION" or reproduction["checks_passed"] != reproduction["checks_total"]:
        raise ValueError("RK32 clean reproduction did not pass")
    if result["scientific_conclusion"] != closeout["scientific_conclusion"] or len(result["primary_tests"]) != 24:
        raise ValueError("RK32 result binding mismatch")
    if preflight["status"] != "PASS_LABEL_FREE_STRUCTURE_PREFLIGHT" or preflight["expression_columns_read"] or preflight["model_fit_performed"]:
        raise ValueError("RK32 preflight boundary mismatch")
    n_seeds = len(protocol["outer_evaluation"]["seeds"])
    folds = protocol["outer_evaluation"]["folds"]
    resamples = protocol["primary_inference"]["resamples"]
    primary_rows = []
    for row in result["primary_tests"]:
        model, arm, metric = row["test"].split("__")
        primary_rows.append([MODEL[model], ARM[arm], METRIC[metric], fmt(row["observed_effect"]),
                             f"[{fmt(row['ci95'][0])}, {fmt(row['ci95'][1])}]", fmt(row["p_holm"]),
                             f"{row['positive_seeds']}/{n_seeds}", fmt(row["pass"])])
    primary_table = table(["Model", "Structure arm", "Endpoint", "Observed effect", "95% CI", "Holm *p*", "Positive seeds", "Decision"],
                          primary_rows, {3, 4, 5, 6, 7})
    absolute_rows = [[ABS_ARM[row["arm"]], fmt(row["spearman"]), fmt(row["mse"])] for row in result["primary_absolute_performance"]]
    absolute_table = table(["Arm", "Spearman", "MSE"], absolute_rows, {1, 2})

    def endpoint(model, arm, metric):
        return next(row for row in result["primary_tests"] if row["test"] == f"{model}__{arm}__{metric}")

    mord_s = endpoint("ridge", "mordstein_like", "spearman_effect")
    mord_m = endpoint("ridge", "mordstein_like", "mse_improvement")
    full_s = endpoint("ridge", "vienna_full_mrna", "spearman_effect")
    local = preflight["candidate_comparisons"]["local_utr_minus4_cds38__dangles2"]
    full = preflight["candidate_comparisons"]["full_mrna__dangles2"]
    arm_decisions = "; ".join(f"{ARM[row['arm']]} {row['n_pass']}/{row['n_tests']}" for row in result["arm_results"])
    diffs = independent["max_deltas"]
    return f"""### 6.43 Structure increments depended on start-aware local coverage

RK32 asked whether the incremental predictive value of mRNA structure depended on structure provenance, coordinate system, or coverage within one fixed Kudla exact-CDS cohort. A label-free preflight read sequences and source-reported structure fields but no expression outcomes and fit no predictive model. The 864-nt source transcript comprised a 144-nt 5′UTR and a 720-nt CDS. Among prespecified local candidates, UTR[-4:] + CDS[:38] with ViennaRNA dangles=2 at 37 °C had the lowest RMSE against the source local field (Pearson *r* = {fmt(local['pearson'])}; RMSE = {fmt(local['rmse'])} kcal/mol). The complete 864-nt transcript with dangles=2 was closest to the source full field (Pearson *r* = {fmt(full['pearson'])}; RMSE = {fmt(full['rmse'])} kcal/mol). These comparisons established provenance rather than outcome-selected arms; source and Vienna values were retained separately because they were not numerically identical.

The frozen analysis reused {result['n_exact_cds_groups']} exact-CDS groups from {result['n_measurement_rows']} measurement rows and the RK27 {result['n_sequence_clusters']} whole-sequence clusters without reclustering or outcome-dependent filtering. CAI, GC, and GC3 formed the common simple backbone. Six structure arms added source local MFE, Vienna local MFE, source full MFE, Vienna full-CDS MFE, Vienna full-mRNA MFE, or the Mordstein-like combination of CDS[:300] MFE and 48-nt-window minimum and mean MFE. Ridge and HistGB were evaluated over {n_seeds} seeds and {folds} whole-cluster folds per seed, yielding {result['total_model_fits']} real CPU fits: 10 × 5 × 2 × (1 shared simple + 6 structure arms).

For each structure arm and model, ΔSpearman was structure minus simple and MSE improvement was simple minus structure. The resulting 24 endpoints formed one Holm family. Inference used {resamples:,} whole-cluster bootstraps and {resamples:,} cluster sign-swap permutations at frozen primary seed {result['primary_seed']}. Each endpoint required a positive observed effect, a 95% CI lower bound above zero, Holm *p* < 0.05, and at least 8/10 positive seeds. An arm passed only when all four endpoints passed. The analysis was retrospective and outcome-known, not an independent untouched confirmation.

**Table 19**

*Structure-Definition Increment Endpoints Under Whole-Cluster OOD*

{primary_table}

*Note.* ΔSpearman = structure − simple; MSE improvement = simple − structure. Observed effects and resampling inference use frozen primary seed {result['primary_seed']}; positive-seed counts summarize all {n_seeds} seeds. CI denotes the 95% whole-cluster bootstrap confidence interval. The Holm adjustment spans all 24 endpoints.

Both local arms passed all four endpoints, whereas all three full-coverage arms failed all four. The Mordstein-like arm passed only Ridge ΔSpearman: effect = {fmt(mord_s['observed_effect'])}, 95% CI [{fmt(mord_s['ci95'][0])}, {fmt(mord_s['ci95'][1])}], Holm *p* = {fmt(mord_s['p_holm'])}. Its Ridge MSE improvement had a CI above zero ({fmt(mord_m['observed_effect'])}; 95% CI [{fmt(mord_m['ci95'][0])}, {fmt(mord_m['ci95'][1])}]) but failed multiplicity control (Holm *p* = {fmt(mord_m['p_holm'])}). Ridge full-mRNA ΔSpearman likewise did not pass (effect = {fmt(full_s['observed_effect'])}; 95% CI [{fmt(full_s['ci95'][0])}, {fmt(full_s['ci95'][1])}]; Holm *p* = {fmt(full_s['p_holm'])}). The arm-level accounting was {arm_decisions}.

**Table 20**

*Absolute Structure-Definition Performance at the Primary Seed*

{absolute_table}

*Note.* Values use frozen primary seed {result['primary_seed']}. Null is the training-fold mean. These are retrospective fixed-GFP expression outcomes under sequence-cluster OOD, not functional or protein OOD, direct structural measurements, or an external SOTA comparison.

The resulting conclusion was `{result['scientific_conclusion']}`. Within this cohort, the evidence supports an increment for the two start-aware local definitions, not a universal structure effect or a claim that longer coverage is inherently uninformative. The exact −4…37 window cannot be reconstructed from the current Mordstein observed-R1 FASTA, which starts at CDS position 4 and lacks the start codon and four upstream nucleotides; RK32 therefore does not close cross-study local-structure transport.

Independent recomputation from the raw Kudla table rebuilt the cohort, Vienna and Mordstein-like features, {result['total_model_fits']} model fits, and all inference. It passed 23/23 checks. Maximum absolute differences were {fmt(diffs['features'], 6)} for features, {fmt(diffs['predictions'], 6)} for predictions, {fmt(diffs['metrics'], 6)} for metrics, {fmt(diffs['effects'], 6)} for seed effects, {fmt(diffs['inference'], 6)} for inference arrays, and {fmt(diffs['summary'], 6)} for summary values. Production and independent recomputation required {result['component_wall_seconds']:.6f} and {independent['component_wall_seconds']:.6f} s, respectively. Release closeout passed {closeout['checks_passed']}/{closeout['checks_total']} checks, and project testing passed {closeout['pytest_passed']} tests with {closeout['pytest_skipped']} skipped.

A separate clean checkout at {reproduction['clean_clone_head']} repeated production and independent verification. The comparison passed {reproduction['checks_passed']}/{reproduction['checks_total']} checks: all {reproduction['csv_count']} CSV artifacts were byte-identical and all {reproduction['npz_array_count']} inference arrays matched exactly. Clean production and independent verification required {reproduction['production_elapsed_seconds_clean']:.6f} and {reproduction['independent_elapsed_seconds_clean']:.6f} s. The retained history includes a pre-fit v1 stop caused by using exact-CDS identifiers as CDS hashes and an independent-report correction for literal `null` parsing; neither engineering correction changed the scientific arms, folds, models, outcomes, inference, or acceptance gates.

RK32 does not read functional-untouched data, authorize generator training, perform wet-lab or prospective design–build–test work, establish protein OOD, close complete external SOTA or unified time-matched comparison, complete a seven-method dense generation-call matrix, or complete RK-G1. The manuscript remains a non-submittable working draft, and these open tasks are not reclassified as completed by this retrospective structure-definition result.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ["protocol", "preflight", "result", "independent", "closeout", "reproduction", "manuscript", "section-output", "output", "report"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    preflight = json.loads(args.preflight.read_text())
    result = json.loads(args.result.read_text())
    independent = json.loads(args.independent.read_text())
    closeout = json.loads(args.closeout.read_text())
    reproduction = json.loads(args.reproduction.read_text())
    if closeout["protocol_sha256"] != sha256(args.protocol) or closeout["result_sha256"] != sha256(args.result):
        raise ValueError("Protocol/result hash binding failed")
    if closeout["independent_sha256"] != sha256(args.independent) or closeout["reproduction_sha256"] != sha256(args.reproduction):
        raise ValueError("Verification hash binding failed")
    section = START + "\n" + render(protocol, preflight, result, independent, closeout, reproduction) + "\n" + END
    args.section_output.write_text(section + "\n")
    original = args.manuscript.read_text()
    text = replace_marked(original, START, END, section[len(START):-len(END)], "## 7. Discussion")
    anchors = table(["Evidence", "SHA256"], [
        ["RK32 label-free structure preflight", sha256(args.preflight)],
        ["RK32 frozen protocol v2", sha256(args.protocol)],
        ["RK32 verified production result", sha256(args.result)],
        ["RK32 independent verification", sha256(args.independent)],
        ["RK32 release closeout", sha256(args.closeout)],
        ["RK32 clean-checkout reproduction comparison", sha256(args.reproduction)],
    ], {1})
    text = replace_marked(text, ANCHOR_START, ANCHOR_END, anchors, "A7 is retained as the prior manuscript snapshot.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + ".tmp-rk32")
    temporary.write_text(text)
    os.replace(temporary, args.output)
    report = {
        "status": "PASS_RK32_MANUSCRIPT_INTEGRATION",
        "protocol_sha256": sha256(args.protocol), "preflight_sha256": sha256(args.preflight),
        "result_sha256": sha256(args.result), "independent_sha256": sha256(args.independent),
        "closeout_sha256": sha256(args.closeout), "reproduction_sha256": sha256(args.reproduction),
        "section_sha256": sha256(args.section_output), "manuscript_sha256": sha256(args.output),
        "input_manuscript_sha256": sha256(args.manuscript), "input_lines": len(original.splitlines()),
        "output_lines": len(text.splitlines()), "primary_endpoints": len(result["primary_tests"]),
        "absolute_rows": len(result["primary_absolute_performance"]),
        "scientific_conclusion": result["scientific_conclusion"], "working_draft": True,
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
