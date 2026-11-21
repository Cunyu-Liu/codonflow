#!/usr/bin/env python3
"""Release-gated, JSON-bound RK29/RK30 working-manuscript integration."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

BLOCK_START = "<!-- A8_RK29_RK30_START -->"
BLOCK_END = "<!-- A8_RK29_RK30_END -->"
ANCHOR_START = "<!-- A8_RK29_RK30_ANCHORS_START -->"
ANCHOR_END = "<!-- A8_RK29_RK30_ANCHORS_END -->"
CONTEXT = {
    "hela_no_intron": "HeLa no intron",
    "hela_with_intron": "HeLa with intron",
    "hek293_no_intron": "HEK293 no intron",
}
MODEL = {"ridge": "Ridge", "histgb": "HistGB"}
ENDPOINT = {"spearman": "ΔSpearman", "mse_improvement": "MSE improvement"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fmt(value, digits=6) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.{digits}g}"


def direction(value: str) -> str:
    if "__to__" in value:
        source, target = value.split("__to__", 1)
        return f"{CONTEXT.get(source, source)} → {CONTEXT.get(target, target)}"
    return CONTEXT.get(value, value)


def table(headers: list[str], rows: list[list[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines += ["| " + " | ".join(str(x) for x in row) + " |" for row in rows]
    return "\n".join(lines)


def replace_marked(text: str, start: str, end: str, block: str, before: str) -> str:
    wrapped = f"{start}\n{block.strip()}\n{end}\n\n"
    if start in text or end in text:
        if text.count(start) != 1 or text.count(end) != 1 or text.index(start) > text.index(end):
            raise ValueError(f"Invalid marked block: {start}")
        return text[: text.index(start)] + wrapped + text[text.index(end) + len(end) :].lstrip("\n")
    if before not in text:
        raise ValueError(f"Insertion anchor absent: {before}")
    return text.replace(before, wrapped + before, 1)


def endpoint_rows(records: list[dict]) -> list[list[object]]:
    return [[
        direction(r["direction"]), MODEL[r["model"]], ENDPOINT[r["endpoint"]], fmt(r["effect"]),
        f"[{fmt(r['ci_low'])}, {fmt(r['ci_high']) }]", fmt(r["holm_p"]),
        f"{round(10 * r['positive_seed_fraction'])}/10", fmt(r["pass"]),
    ] for r in records]


def render_rk29(failure: dict, verification: dict) -> str:
    if failure["status"] != "NOT_DISCRIMINATING_SOURCE_ALIGNMENT_OR_COVERAGE_FAILED":
        raise ValueError("Unexpected RK29 failure status")
    if verification["status"] != "PASS_INDEPENDENT_ALIGNMENT_FAILURE_VERIFICATION":
        raise ValueError("RK29 independent verification did not pass")
    if failure["analysis_rows_generated"] != 0 or failure["model_fit_performed"]:
        raise ValueError("RK29 execution boundary mismatch")
    candidates = failure["candidate_size_distribution"]
    return f"""### 6.40 iCodon source tables did not identify unique sequence–outcome mappings

RK29 asked whether computational MFE features improved out-of-protein prediction of injected-mRNA decay in one-cell zebrafish embryos [diez2022icodon]. The frozen protocol required a unique one-to-one mapping between all {failure['n_s6_measurements']} S6 outcome measurements and {failure['n_unique_fasta_names']} canonical FASTA names before fitting. Row order, nearest matching, arbitrary first matches and outcome-informed assignment were prohibited.

The released GEO table contained {failure['n_geo_rows']} rows, exactly the within-protein FASTA-name × measurement-vector Cartesian product. All {failure['cartesian_pair_checks_passed']} pairs satisfied the frozen join. Candidate counts were {candidates.get('1', 0)} rows with one sequence candidate, {candidates.get('2', 0)} with two and {candidates.get('3', 0)} with three. Thus {failure['n_rows_with_ambiguous_name_candidates']}/{failure['n_s6_measurements']} measurements lacked a unique sequence candidate, and {failure['n_protein_design_groups_with_multiple_assignments']}/{failure['n_protein_design_groups']} protein-by-design groups admitted multiple legal one-to-one assignments. The frozen join admitted approximately 10^{failure['log10_n_valid_global_assignments']:.6f} global sequence–outcome assignments.

The analysis therefore stopped with `{failure['status']}`: {failure['analysis_rows_generated']} analysis rows and 0 model fits were produced. No effect, confidence interval, permutation *p* value, runtime ranking or SOTA claim exists for RK29. This is a source-identifiability result, not a negative RNA-structure mechanism result. An independent implementation recomputed the Cartesian pairs and assignment ambiguity without importing production modules and returned `{verification['status']}`. A future analysis requires an authoritative per-variant sequence key and a new protocol; the current join must not be silently repaired.
"""


def render_rk30(closeout: dict, counting: dict, model: dict, protocol: dict) -> str:
    if closeout["status"] != "PASS_RK30_VERIFIED_RESULT_PACKAGING" or not all(closeout["release_gates"].values()):
        raise ValueError("RK30 release gates did not pass")
    if len(closeout["primary_endpoints"]) != 16 or len(closeout["secondary_endpoints"]) != 12:
        raise ValueError("RK30 endpoint count mismatch")
    if closeout["cost"]["fit_count"] != protocol["models"]["expected_total_fits"]:
        raise ValueError("RK30 fit count mismatch")
    n_seeds = len(protocol["outer_evaluation"]["sensitivity_seeds"])
    n_runs = counting.get("n_runs", sum(c["expected_runs"] for c in protocol["contexts"].values()))
    n_experiments = counting.get("n_experiments", sum(len(c["replicates"]) for c in protocol["contexts"].values()))
    folds = protocol["outer_evaluation"]["folds"]
    boot = protocol["primary_transport"]["cluster_bootstrap"]["resamples"]
    perm = protocol["primary_transport"]["cluster_swap_permutation"]["permutations"]
    primary_seed = closeout["absolute_performance_seed"]
    outcomes = closeout["coverage"]["condition_score_summary"]
    outcome_table = table(["Condition", "N", "Mean", "SD", "Min", "Max"], [[
        direction(c), v["n"], fmt(v["mean"]), fmt(v["sd"]), fmt(v["min"]), fmt(v["max"]),
    ] for c, v in outcomes.items()])
    direction_table = table(["Transport direction", "Passed endpoints", "Direction decision"], [[
        direction(r["direction"]), f"{r['passed_endpoints']}/{r['total_endpoints']}", fmt(r["all_four_endpoints_pass"]),
    ] for r in closeout["primary_direction_summary"]])
    primary_table = table(["Direction", "Model", "Endpoint", "Effect", "95% cluster-bootstrap CI", "Holm *p*", "Positive seeds", "Decision"], endpoint_rows(closeout["primary_endpoints"]))
    absolute_table = table(["Direction", "Model", "Metric", "Null", "Simple", "Structure", "Mean-seed effect"], [[
        direction(r["direction"]), MODEL[r["model"]], "Spearman" if r["endpoint"] == "spearman" else "MSE",
        fmt(r["null_mean"]), fmt(r["simple_mean"]), fmt(r["structure_mean"]), fmt(r["effect"]),
    ] for r in closeout["primary_absolute_performance"]])
    secondary_table = table(["Condition", "Model", "Endpoint", "Effect", "95% cluster-bootstrap CI", "Holm *p*", "Positive seeds", "Decision"], endpoint_rows(closeout["secondary_endpoints"]))
    directions = closeout["primary_direction_summary"]
    host_pass = all(r["all_four_endpoints_pass"] for r in directions[:2])
    intron_pass = all(r["all_four_endpoints_pass"] for r in directions[2:])
    conclusion = closeout["scientific_conclusion"]
    interpretation = (
        "All four ordered directions passed, supporting context-transportable predicted-MFE increments only within this matched retrospective design."
        if closeout["primary_family_supported"] else
        "The four-direction family did not pass, so a broad context-transportable predicted-MFE increment is not supported. This does not establish that RNA structure is universally irrelevant."
    )
    cost = closeout["cost"]
    return f"""### 6.41 Matched host and 5′UTR-intron transport in the Mordstein GFP library

RK30 held the Mordstein GFP reference set, observed {protocol['inputs']['reference_csv']['expected_sequence_length']}-nt R1 coverage, sequence clusters, predicted-structure definitions and models constant across HeLa without intron, HeLa with intron and HEK293 without intron [mordstein2020codon]. The fixed counting pipeline used {n_runs} R1 runs in {n_experiments} experiments. Reads were assigned to a unique nearest reference within {protocol['fixed_reference_counting']['maximum_error_nt']} nt; every variant required all eight bins and at least {protocol['outcome_and_qc']['minimum_assigned_reads_per_variant_per_replicate']:,} assigned reads in every experiment. The common complete cohort contained {closeout['coverage']['variants']} variants in {closeout['coverage']['clusters']} frozen clusters. Raw independent verification passed, including source hashes, checkpoints, brute-force read assignment and outcome recomputation.

**Table 12**

*Common-cohort Flow-seq outcome distributions*

{outcome_table}

*Note.* Scores are bin-weighted Flow-seq outcomes, not direct RFU, translation velocity or mRNA decay.

The simple arms contained observed-R1 GC3, GC, CpG and CAI; structure arms added full-fragment MFE and 48-nt-window minimum/mean MFE. Depth was retained for QC but excluded from transported predictors. Ridge and HistGB used frozen hyperparameters, {n_seeds} fold-assignment seeds and {folds} whole-cluster folds. Four ordered transport directions were evaluated with {boot:,} cluster bootstraps and {perm:,} cluster sign-swap permutations; all 16 primary endpoints formed one Holm family. A pass required a positive mean-seed effect, a 95% CI lower bound above zero, Holm *p* < 0.05 and at least 8/10 positive seeds.

**Table 13**

*Primary ordered transport decisions*

{direction_table}

**Table 14**

*Primary predicted-MFE increment endpoints*

{primary_table}

*Note.* ΔSpearman = structure − simple; MSE improvement = simple − structure. Effects are means over {n_seeds} seeds. CI and permutation inference use the frozen primary seed ({protocol['outer_evaluation']['primary_seed']}).

**Table 15**

*Absolute null/simple/structure performance at the frozen primary seed ({primary_seed})*

{absolute_table}

The three within-context analyses were secondary, with a separate 12-endpoint Holm family, and could not rescue a failed primary transport family.

**Table 16**

*Secondary within-context predicted-MFE increments*

{secondary_table}

The resulting conclusion was `{conclusion}`. {interpretation} Bidirectional host transport decision: {fmt(host_pass)}; bidirectional intron transport decision: {fmt(intron_pass)}. The matched design removes the study, vector-library, variant-reference, observed-fragment and predicted-feature-definition differences that jointly confounded RK27 versus RK28. It does not resolve measured-versus-predicted structure, full-CDS coverage, protein OOD, every cell-line-specific mechanism or a causal splicing mechanism.

Production completed {cost['fit_count']} CPU fits ({cost['transport_fit_count']} transport + {cost['within_context_fit_count']} within-context) in {cost['production_cost_seconds']:.6f} s; independent model verification required {fmt(cost['independent_verification_cost_seconds'])} s. Both independent gates passed before manuscript integration. No functional-untouched evaluation, generator training, prospective design–build–test, external SOTA or clinical-expression claim follows. RK-G1 remains open and the manuscript remains a non-submittable working draft.
"""


def add_references(text: str) -> str:
    diez = "Diez, M., Medina-Muñoz, S. G., Castellano, L. A., et al. iCodon customizes gene expression based on the codon composition. *Scientific Reports* (2022). https://doi.org/10.1038/s41598-022-15526-7"
    mordstein = "Mordstein, C., Savisaar, R., Young, R. S., et al. Codon Usage and Splicing Jointly Influence mRNA Localization. *Cell Systems* (2020). https://doi.org/10.1016/j.cels.2020.03.001"
    if "10.1038/s41598-022-15526-7" not in text:
        text = text.replace("\n\nFallahpour,", "\n\n" + diez + "\n\nFallahpour,", 1)
    if "10.1016/j.cels.2020.03.001" not in text:
        if "\n\nPatel," in text:
            text = text.replace("\n\nPatel,", "\n\n" + mordstein + "\n\nPatel,", 1)
        elif "\n\nRajbanshi," in text:
            text = text.replace("\n\nRajbanshi,", "\n\n" + mordstein + "\n\nRajbanshi,", 1)
        else:
            raise ValueError("Mordstein reference insertion anchor absent")
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--manuscript", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    root = args.artifact_root.resolve()
    repo = Path(__file__).resolve().parents[1]
    closeout_path = root / "RK30_CLOSEOUT.json"
    closeout = json.loads(closeout_path.read_text())
    if closeout.get("status") != "PASS_RK30_VERIFIED_RESULT_PACKAGING" or not all(closeout.get("release_gates", {}).values()):
        raise ValueError("RK30 release gates did not pass")
    counting = json.loads((root / "RK30_COUNTING.json").read_text())
    model = json.loads((root / "RK30_MODEL_SUMMARY.json").read_text())
    protocol_path = args.protocol.resolve()
    protocol = json.loads(protocol_path.read_text())
    if closeout["protocol_sha256"] != sha256(protocol_path):
        raise ValueError("Protocol binding failed")
    ppt = json.loads((root / "RK30_RESULTS_FOR_PPT.json").read_text())
    closeout_sha = sha256(closeout_path)
    if ppt["closeout_sha256"] != closeout_sha:
        raise ValueError("PPT payload is not bound to the current closeout")
    rk29_dir = repo / "audits/20261121/RK29"
    rk29_failure_path = rk29_dir / "RK29_ALIGNMENT_FAILURE.json"
    rk29_verification_path = rk29_dir / "RK29_ALIGNMENT_VERIFICATION.json"
    rk29_failure = json.loads(rk29_failure_path.read_text())
    rk29_verification = json.loads(rk29_verification_path.read_text())
    block = BLOCK_START + "\n" + render_rk29(rk29_failure, rk29_verification) + "\n" + render_rk30(closeout, counting, model, protocol) + "\n" + BLOCK_END
    text = args.manuscript.read_text()
    text = replace_marked(text, BLOCK_START, BLOCK_END, block[len(BLOCK_START) : -len(BLOCK_END)], "## 7. Discussion")
    artifacts = closeout["artifact_sha256"]
    anchors = table(["Evidence", "SHA256"], [
        ["RK29 alignment failure", sha256(rk29_failure_path)],
        ["RK29 independent alignment verification", sha256(rk29_verification_path)],
        ["RK30 frozen matched-context protocol", closeout["protocol_sha256"]],
        ["RK30 fixed-reference counting", artifacts["RK30_COUNTING.json"]],
        ["RK30 model summary", artifacts["RK30_MODEL_SUMMARY.json"]],
        ["RK30 raw independent verification", artifacts["RK30_RAW_VERIFICATION.json"]],
        ["RK30 independent model verification", artifacts["RK30_MODEL_INDEPENDENT.json"]],
        ["RK30 verified closeout", closeout_sha],
    ])
    text = replace_marked(text, ANCHOR_START, ANCHOR_END, anchors, "A7 is retained as the prior manuscript snapshot.")
    text = add_references(text)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + ".tmp-rk30")
    temporary.write_text(text)
    os.replace(temporary, args.output)
    report_path = args.report or root / "RK30_MANUSCRIPT_INTEGRATION.json"
    report = {
        "status": "PASS_RK29_RK30_MANUSCRIPT_INTEGRATION",
        "closeout_sha256": closeout_sha,
        "manuscript": str(args.output), "manuscript_sha256": sha256(args.output),
        "primary_endpoints": len(closeout["primary_endpoints"]),
        "secondary_endpoints": len(closeout["secondary_endpoints"]),
        "scientific_conclusion": closeout["scientific_conclusion"],
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
