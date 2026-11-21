#!/usr/bin/env python3
"""Generate the isolated RK33 English section directly from accepted evidence JSON."""
from pathlib import Path
import argparse
import hashlib
import json


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def f(x):
    return f"{x:.6f}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--metadata", type=Path, required=True)
    args = p.parse_args()
    b = args.base
    paths = {
        "protocol": b / "a8_rk33_local_coverage_protocol_v1.json",
        "preflight": b / "rk33_label_free_preflight_v1.json",
        "result": b / "rk33_local_coverage_result_v1.json",
        "independent": b / "rk33_local_coverage_independent_v1.json",
        "reproduction": b / "rk33_clean_reproduction_v1.json",
        "closeout": b / "rk33_closeout_verification_v2.json",
    }
    d = {name: json.loads(path.read_text()) for name, path in paths.items()}
    r, ind, repro, close = d["result"], d["independent"], d["reproduction"], d["closeout"]
    assert r["scientific_conclusion"] == ind["independent_conclusion"] == "LOCAL42_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED"
    assert ind["status"] == repro["status"] == close["status"] == "PASS"
    assert not r["all_12_pass"] and not any(t["pass"] for t in r["primary_tests"])
    assert close["endpoints_passed"] == 0 and close["endpoints_total"] == 12
    tests = r["primary_tests"]
    minimum_raw_p = min(t["p_cluster_swap"] for t in tests)
    hashes = {name: sha(path) for name, path in paths.items()}
    section = []
    add = section.append
    add("### 6.44 A 42-nt local MFE does not add robust observed-R1 structure signal under matched sequence-cluster holdout")
    add("")
    add("RK32 established that local start-aware definitions can carry expression signal in the fixed Kudla GFP library, but it could not transport that result to Mordstein because the observed R1 fragment begins at CDS position 4. RK33 therefore asked a narrower, directly executable question: within the same observed-R1 representation, does a 42-nt CDS4–45 minimum free energy (MFE) add robust signal beyond the existing sequence and full-fragment definitions? This was a retrospective, outcome-known coverage follow-up, not an independent confirmation or a test of RNA velocity. The same 152 HEK293 variants, 74 whole-sequence clusters, 1,520 seed–fold assignments, simple sequence features, Ridge and histogram gradient-boosting models, and statistical inference were held fixed.")
    add("")
    add("Four arms were frozen before model fitting: simple sequence only; simple plus one local42 MFE; simple plus one full-300 MFE (full1); and the previously accepted RK28 full-300 plus 48-nt minimum/mean MFE three-feature arm (full3). ViennaRNA was evaluated at 37 °C with dangling ends disabled. Only local42 and full1 required new fitting, giving 10 seeds × 5 folds × 2 models × 2 arms = 200 new fits; 200 accepted simple/full3 fits were reused, for 400 evaluated fits. Three paired comparison families—local42 versus simple, full1, and full3—each contained Ridge Spearman, Ridge MSE improvement, HistGB Spearman, and HistGB MSE improvement endpoints. Each endpoint required a positive observed effect, a whole-cluster bootstrap lower confidence limit above zero, a unified Holm-adjusted cluster-swap permutation p-value below 0.05, and at least eight positive seeds. All 12 endpoints were required for structural support.")
    add("")
    add("The label-free preflight passed 21/21 checks, including 152 unique 300-nt sequences, 93 unique local42 subsequences, fold sizes of 30/31/31/30/30 variants, and zero whole-cluster leakage across all 50 seed–fold assignments. Both synthetic production suites passed 18/18 checks. The first production attempt stopped before any new model fit because a zero-tolerance CSV target comparison was sensitive to floating-point text round trips. The correction changed only this identity comparison to a 1e-12 absolute tolerance; feature definitions, folds, models, endpoints, and seeds were unchanged, and the failed console log was retained.")
    add("")
    add("**The prespecified decision was not supported: 0/12 endpoints passed and all three family gates were false (Table 21).** Every 95% confidence interval crossed zero, and every unified Holm-adjusted p-value was 1.0. The minimum unadjusted cluster-swap p-value was " + f"{minimum_raw_p:.6f}" + ", so the negative decision was not produced solely by multiplicity correction. For local42 versus simple, Ridge effects were negative, whereas HistGB point estimates were positive but highly uncertain. For local42 versus full1, Ridge again favored neither local coverage nor the full fragment, and HistGB intervals included both directions. Local42 versus full3 produced several positive point estimates and as many as 9/10 positive seeds for HistGB Spearman, but its confidence interval still crossed zero and its adjusted p-value remained 1.0. Seed direction alone therefore cannot be interpreted as a structural advantage.")
    add("")
    add("Table 21. Frozen paired primary endpoints for the 42-nt local MFE. Effects are local42 minus comparator; MSE improvement is comparator MSE minus local42 MSE. CI denotes the 95% whole-cluster bootstrap interval, and Holm p is adjusted across all 12 tests.")
    add("")
    add("| Comparison | Model | Metric | Observed effect | 95% CI | Raw p | Holm p | Positive seeds | Pass |")
    add("|---|---|---|---:|---|---:|---:|---:|---|")
    labels = {"local42_vs_simple": "local42−simple", "local42_vs_full1": "local42−full1", "local42_vs_full3": "local42−full3"}
    for t in tests:
        family, rest = t["test"].split("__")
        model, metric = rest.split("_", 1)
        metric_label = "Spearman" if metric.startswith("spearman") else "MSE improvement"
        add(f'| {labels[family]} | {model.capitalize()} | {metric_label} | {f(t["observed_effect"])} | [{f(t["ci95"][0])}, {f(t["ci95"][1])}] | {t["p_cluster_swap"]:.6f} | {t["p_holm"]:.6f} | {t["positive_seeds"]}/10 | No |')
    add("")
    add("Primary-seed absolute performance provides context for these paired increments (Table 22). Ridge simple achieved Spearman 0.349548 and MSE 2.057832; local42 did not improve either value. HistGB local42 gave a modest absolute increase over simple (Spearman 0.262811 versus 0.238982), but the paired whole-cluster interval was compatible with no gain. Full3 did not outperform the simpler backbones in absolute primary-seed scores. These descriptive values explain the direction of individual fits but do not replace the paired uncertainty analysis or establish a practically useful expression predictor.")
    add("")
    add("Table 22. Absolute held-out observed-R1 performance for the frozen primary seed 20261222.")
    add("")
    add("| Model | Arm | Spearman | MSE |")
    add("|---|---|---:|---:|")
    arm_labels = {"simple": "simple", "local42": "simple + local42 MFE", "full1": "simple + full-300 MFE", "full3": "simple + full-300/window48 MFEs"}
    for row in r["primary_absolute_performance"]:
        model, arm = row["arm"].split("_", 1)
        add(f'| {model.capitalize()} | {arm_labels[arm]} | {f(row["spearman"])} | {f(row["mse"])} |')
    add("")
    add(f'An independently written implementation rebuilt the cluster definitions, folds, target, local/full MFE features, model predictions, seed effects, and all inference from the source tables. It passed {ind["checks_passed"]}/{ind["checks_total"]} checks and returned the identical three-family decision and all 12 endpoint gates. A separate no-hardlinks clean checkout of `{close["clean_commit"]}` then repeated production and independent verification. The reproduction comparison passed {repro["checks_passed"]}/{repro["checks_total"]} checks: {repro["csv_byte_equal"]}/{repro["csv_total"]} CSV files were byte-identical and {repro["arrays_exact_equal"]}/{repro["arrays_total"]} NPZ arrays were exactly equal. Original/clean production took {r["elapsed_seconds"]:.6f}/{repro["clean_production_elapsed_seconds"]:.6f} s; original/clean independent verification took {ind["elapsed_seconds"]:.6f}/{repro["clean_independent_elapsed_seconds"]:.6f} s. The complete project suite reported 429 passed and one skipped test.')
    add("")
    add("The evidence boundary is narrower than a universal claim that local structure is uninformative. The observed fragment lacks the start ATG, four upstream nucleotides, complete UTR–CDS context, and measured structure; consequently, RK33 cannot identify start-aware folding, host, assay, measured-versus-predicted structure, or dangling-end effects. It also does not measure RNA decay, nuclear export, translation velocity, functional rescue, or protein OOD. A full UTR–CDS remap and an independent untouched evaluation remain necessary before transporting the RK32 local mechanism across datasets. External SOTA, unified time-matched and seven-method dense-trajectory comparisons, multispecies VeloHARMO, prospective DBTL, and RK-G1 remain open. Functional untouched data were not read, expensive generator training was not authorized, and no wet-lab experiment was performed.")
    add("")
    add("::: {.evidence-anchor #sec-6-44}")
    add("| Field | Evidence |")
    add("|---|---|")
    add(f'| Code commits | `20e1ac389313fc21c36e82a5745be3d89bf0dffa` (accepted science); `{close["clean_commit"]}` (clean reproduction) |')
    add("| Code | `scripts/a8_rk33_run_local_coverage.py`; `scripts/a8_rk33_verify_local_coverage.py`; `scripts/a8_rk33_compare_reproduction.py`; `scripts/a8_rk33_closeout.py` |")
    add("| Protocol | `audits/20261121/RK33/a8_rk33_local_coverage_protocol_v1.json` |")
    add("| Results | `audits/20261121/RK33/rk33_local_coverage_result_v1.json`; `rk33_local_coverage_independent_v1.json`; `rk33_closeout_verification_v2.json` |")
    add(f'| SHA256 | protocol `{hashes["protocol"]}`; result `{hashes["result"]}`; independent `{hashes["independent"]}`; reproduction `{hashes["reproduction"]}`; closeout `{hashes["closeout"]}` |')
    add("| Analysis | 152 retrospective outcome-known observed-R1 variants; 74 whole-sequence clusters; 10 seeds × 5 folds; 200 new fits + 200 reused fits; 20,000 cluster bootstraps and 20,000 cluster-swap permutations |")
    add("| Scope | Local/full coverage and one-/three-feature comparisons only; no exact Kudla start-aware transport, independent untouched, functional/protein OOD, RNA velocity, decay, generator, or wet-lab claim |")
    add(":::")
    add("")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(section))
    metadata = {
        "section": "6.44",
        "tables": [21, 22],
        "scientific_conclusion": r["scientific_conclusion"],
        "endpoints_passed": 0,
        "endpoints_total": 12,
        "minimum_raw_permutation_p": minimum_raw_p,
        "new_model_fits": r["new_model_fits"],
        "reused_model_fits": r["reused_rk28_model_fits"],
        "evaluated_model_fits": r["evaluated_model_fits"],
        "independent_checks": f'{ind["checks_passed"]}/{ind["checks_total"]}',
        "reproduction_checks": f'{repro["checks_passed"]}/{repro["checks_total"]}',
        "csv_byte_equal": f'{repro["csv_byte_equal"]}/{repro["csv_total"]}',
        "arrays_exact_equal": f'{repro["arrays_exact_equal"]}/{repro["arrays_total"]}',
        "clean_commit": close["clean_commit"],
        "evidence_sha256": hashes,
        "section_sha256": sha(args.output),
    }
    args.metadata.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
