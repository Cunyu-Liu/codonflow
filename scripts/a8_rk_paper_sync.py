#!/usr/bin/env python3
"""Generate the A8-RK working manuscript from verified evidence only.

The A7 manuscript is read-only. Every new numeric claim below is rendered from
frozen JSON artifacts; incomplete RNARL, mechanism, model, OOD, and wet-lab
results remain explicitly pending.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def replace_section(text: str, heading: str, next_heading: str, body: str) -> str:
    start = text.index(heading)
    end = text.index(next_heading, start + len(heading))
    return text[:start] + body.rstrip() + "\n\n" + text[end:]


def append_to_section(text: str, next_heading: str, addition: str) -> str:
    end = text.index(next_heading)
    return text[:end].rstrip() + "\n\n" + addition.strip() + "\n\n" + text[end:]


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    parser.add_argument("--template", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--rk07-dir", type=Path, default=Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk07/final"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    template = args.template or repo / "paper/CodonFlow_preprint_A7.md"
    output = args.output or repo / "paper/CodonFlow_preprint_A8.md"
    audit_path = args.audit or repo / "paper/a8_rk_paper_sync_audit.json"
    require(template.resolve() != output.resolve(), "A7 template must not be overwritten")

    paths = {
        "rk02": repo / "audits/20261118/RK02/audit_summary.json",
        "rk04": repo / "audits/20261118/RK04/split_summary.json",
        "rk04_verify": repo / "audits/20261118/RK04/independent_split_verification.json",
        "ribomimo": repo / "audits/20261118/RK03/ribomimo_qc_summary.json",
        "ribomimo_verify": repo / "audits/20261118/RK03/ribomimo_independent_verification.json",
        "ct_final": repo / "audits/20261118/RK03/codontransformer_finalization.json",
        "id3": repo / "audits/20261118/RK05/id3_official_quick_test.json",
        "id3_verify": repo / "audits/20261118/RK05/id3_official_quick_test_independent.json",
        "id3_final": repo / "audits/20261118/RK05/id3_official_quick_test_finalization.json",
        "ld_smoke": repo / "audits/20261118/RK05/lineardesign_official_smoke_v2.json",
        "ld_verify": repo / "audits/20261118/RK05/lineardesign_independent_verification_v2.json",
        "ld_final": repo / "audits/20261118/RK05/lineardesign_finalization.json",
        "ld_v1_failure": repo / "audits/20261118/RK05/lineardesign_official_smoke_v1_failure.json",
        "ed_example": repo / "audits/20261118/RK05/ensembledesign_official_example_smoke_v2.json",
        "ed_c01": repo / "audits/20261118/RK05/ensembledesign_c01_smoke_v1.json",
        "ed_example_verify": repo / "audits/20261118/RK05/ensembledesign_official_example_independent_v2.json",
        "ed_c01_verify": repo / "audits/20261118/RK05/ensembledesign_c01_independent_v1.json",
        "ed_final": repo / "audits/20261118/RK05/ensembledesign_finalization.json",
        "cdgb_audit": repo / "audits/20261118/RK05/cdgb_source_audit.json",
        "cdgb_verify": repo / "audits/20261118/RK05/cdgb_source_independent_verification.json",
        "cdgb_final": repo / "audits/20261118/RK05/cdgb_source_finalization.json",
        "rnarl_smoke": repo / "audits/20261118/RK05/rnarl_official_contract_smoke_v2.json",
        "rnarl_verify": repo / "audits/20261118/RK05/rnarl_official_independent_verification.json",
        "rnarl_qc": repo / "audits/20261118/RK03/rnarl_qc.json",
        "rnarl_qc_verify": repo / "audits/20261118/RK03/rnarl_independent_verification_v2.json",
        "rnarl_final": repo / "audits/20261118/RK03/rnarl_finalization_recovery_v4.json",
        "velo_qc": repo / "audits/20261118/RK03/veloharmo_ecoli_qc.json",
        "velo_verify": repo / "audits/20261118/RK03/veloharmo_ecoli_independent_verification.json",
        "velo_loader": repo / "audits/20261118/RK03/veloharmo_official_loader_smoke.json",
        "velo_final": repo / "audits/20261118/RK03/veloharmo_finalization.json",
        "rk07": args.rk07_dir / "final_results.json",
        "rk07_verify": repo / "audits/20261118/RK07/final_independent_verification.json",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    require(not missing, f"missing frozen evidence: {missing}")
    data = {name: load(path) for name, path in paths.items()}
    source_hashes = {name: sha256(path) for name, path in paths.items()}

    rk02 = data["rk02"]
    rk04 = data["rk04"]
    rk04v = data["rk04_verify"]
    ribo = data["ribomimo"]
    ribov = data["ribomimo_verify"]
    ct = data["ct_final"]
    id3 = data["id3"]
    id3v = data["id3_verify"]
    id3f = data["id3_final"]
    ld = data["ld_smoke"]
    ldv = data["ld_verify"]
    ldf = data["ld_final"]
    ld_fail = data["ld_v1_failure"]
    ed = data["ed_example"]
    edc = data["ed_c01"]
    edv = data["ed_example_verify"]
    edcv = data["ed_c01_verify"]
    edf = data["ed_final"]
    cdgb = data["cdgb_audit"]
    cdgbv = data["cdgb_verify"]
    cdgbf = data["cdgb_final"]
    rnarl = data["rnarl_smoke"]
    rnalrv = data["rnarl_verify"]
    rnarlq = data["rnarl_qc"]
    rnarlqv = data["rnarl_qc_verify"]
    rnalrf = data["rnarl_final"]
    veloq = data["velo_qc"]
    velov = data["velo_verify"]
    velol = data["velo_loader"]
    velof = data["velo_final"]
    rk07 = data["rk07"]
    rk07v = data["rk07_verify"]

    require(rk02["functional_long_rows"] == 25420, "unexpected RK02 row count")
    require(rk04["status"] == "PASS_WITH_SCIENTIFIC_BOUNDARIES", "RK04 not finalized")
    require(rk04v["status"] == "PASS" and all(c["status"] == "PASS" for c in rk04v["checks"]), "RK04 verification failed")
    require(rk04["leakage"]["all_pairwise_overlaps_zero"], "RK04 leakage guard failed")
    require(not rk04["functional_untouched_evaluated"], "untouched MAGE was evaluated")
    require(ribov["status"] == "PASS" and all(c["pass"] for c in ribov["checks"]), "RiboMIMO verification failed")
    require(ct["status"] == "PASS" and ct["result"]["verification_status"] == "PASS", "CodonTransformer not finalized")
    require(ct["result"]["bounded_natural_sequence_distribution_ready"], "CodonTransformer scope changed")
    require(not ct["result"]["functional_training_authorized"], "CodonTransformer functional scope exceeded")
    require(rk07v["status"] == "PASS" and all(c["pass"] for c in rk07v["checks"]), "RK07 verification failed")
    require(rk07["dev_baseline_exact_match"] and not rk07["forbidden_split_used"], "RK07 freeze guard failed")
    require(id3["status"] == "PASS_OFFICIAL_QUICK_TEST_SMOKE", "ID3 execution not complete")
    require(id3v["status"] == "BOUNDED_OFFICIAL_EXECUTION_COMPLETE_WITH_CPC_STE_TRAJECTORY_DEFECT", "ID3 independent status changed")
    require(id3v["science_flags"]["all_final_sequence_scores_independently_verified"], "ID3 final scores not verified")
    require(not id3v["science_flags"]["all_payload_metrics_independently_verified"], "ID3 CPC defect boundary changed")
    require(id3f["status"] == "BOUNDED_OFFICIAL_QUICK_TEST_COMPLETE_WITH_CPC_STE_TRAJECTORY_DEFECT" and id3f["science_flags"]["ppt_record_ready"], "ID3 finalization not ready")
    require(id3f["checks_passed"] == id3f["checks_total"] == 11, "ID3 finalization checks failed")
    require(not id3f["science_flags"]["main_baseline_comparison"] and not id3f["science_flags"]["sota_claim"], "ID3 scope exceeded")
    require(ld["status"] == "BOUNDED_OFFICIAL_EXECUTION_COMPLETE" and ld["run_count"] == len(ld["runs"]) == 3, "LinearDesign bounded execution incomplete")
    require(ldv["status"] == "PASS" and ldv["passed_checks"] == ldv["check_count"] == 10 and ldv["max_numeric_delta"] == 0.0, "LinearDesign independent verification failed")
    require(ldf["status"] == "BOUNDED_LINEARDESIGN_OFFICIAL_SMOKE_VERIFIED" and ldf["passed_checks"] == ldf["check_count"] == 8, "LinearDesign finalization failed")
    require(ld_fail["status"] == "FAIL_INDEPENDENT_SCORER_CONVENTION_MISMATCH" and not ld_fail["production_report_written"], "LinearDesign v1 failure was not preserved")
    require(not ldf["science_flags"]["main_baseline_comparison"] and not ldf["science_flags"]["sota_claim"], "LinearDesign scope exceeded")
    require(ed["status"] == edc["status"] == "BOUNDED_OFFICIAL_EXECUTION_COMPLETE", "EnsembleDesign bounded execution incomplete")
    require(ed["run_count"] == 6 and ed["input_record_count"] == 3 and edc["run_count"] == 2 and edc["input_record_count"] == 1, "EnsembleDesign bounded run contract changed")
    require(ed["official_example"]["pass"] and ed["unique_output_sequences"] == 4 and edc["unique_output_sequences"] == 2, "EnsembleDesign output identity contract changed")
    require(edv["status"] == edcv["status"] == "PASS" and edv["passed_checks"] == edv["check_count"] == 13 and edcv["passed_checks"] == edcv["check_count"] == 13, "EnsembleDesign independent verification failed")
    require(edv["max_numeric_delta"] == edcv["max_numeric_delta"] == 0.0 and not edv["independent_production_import"] and not edcv["independent_production_import"], "EnsembleDesign independent recomputation contract changed")
    require(edf["status"] == "PASS" and edf["passed_checks"] == edf["check_count"] == 11 and edf["task_completion_authorized"], "EnsembleDesign finalization failed")
    require(not edf["main_baseline_matrix_closed"] and not edf["functional_ood_closed"] and not edf["sota_claim"] and not ed["matched_lineardesign_comparison"] and not edc["matched_lineardesign_comparison"], "EnsembleDesign scientific scope exceeded")
    require(cdgb["status"] == "SOURCE_IDENTITY_UNRESOLVED_OFFICIAL_EXECUTION_NOT_AUTHORIZED" and cdgb["query_count_succeeded"] == cdgb["query_count_expected"] == 9, "CDGB source audit incomplete")
    require(cdgb["candidate_doi_identity"]["conflict"] and not cdgb["candidate_doi_identity"]["resolved"], "CDGB candidate DOI conflict missing")
    require(cdgbv["status"] == "PASS" and cdgbv["checks_passed"] == cdgbv["checks_total"] == 8 and not cdgbv["independent_production_import"], "CDGB independent verification failed")
    require(cdgbf["status"] == "SOURCE_IDENTITY_UNRESOLVED_OFFICIAL_EXECUTION_NOT_AUTHORIZED" and cdgbf["checks_passed"] == cdgbf["checks_total"] == 6 and cdgbf["science_flags"]["paper_sync_ready"], "CDGB finalization failed")
    require(cdgbf["science_flags"]["official_sequence_output_count"] == 0 and cdgbf["science_flags"]["performance_result_count"] == 0 and not cdgbf["science_flags"]["official_execution_complete"], "CDGB execution scope exceeded")
    require(not cdgbf["science_flags"]["method_invalid_claim"] and not cdgbf["science_flags"]["implementation_nonexistence_claim"], "CDGB negative wording exceeded evidence")
    require(rnalrv["status"] == "PASS_NEGATIVE_REPRODUCIBILITY_AUDIT" and all(rnalrv["checks"].values()), "RNARL negative audit not verified")
    require(not rnarl["official_full_training_executed"] and not rnarl["paper_metrics_reproduced"], "RNARL availability scope exceeded")
    require(rnarlqv["status"] == "PASS" and rnarlqv["passed_checks"] == rnarlqv["check_count"] == 8 and rnarlqv["max_numeric_delta"] == 0.0, "RNARL full independent QC failed")
    require(not rnarlqv["independent_production_import"], "RNARL verifier imported production code")
    require(rnalrf["status"] == "PASS_BOUNDED_LINEARDESIGN_PAIR_TABLE_QC_ONLY" and rnalrf["passed_checks"] == rnalrf["check_count"] == 10, "RNARL finalization failed")
    require(rnarlq["total_rows"] == rnalrf["raw_rows"] == 260754 and rnarlq["clean_rows"] == rnalrf["clean_rows"] == 256578 and rnarlq["clean_pairs"] == rnalrf["clean_pairs"] == 128289, "RNARL full counts changed")
    require(rnalrf["raw_cross_split_overlap_keys"]["exact_cds"] == 22 and rnalrf["raw_cross_split_exact_cds_rows"] == 44, "RNARL raw leakage record changed")
    require(rnalrf["clean_cross_split_exact_cds_keys"] == 0 and rnalrf["clean_cross_split_protein_sequence_keys"] == 0, "RNARL clean leakage guard failed")
    require(not rnalrf["science_flags"]["natural_cds_source_validated"] and not rnalrf["science_flags"]["functional_training_authorized"] and not rnalrf["science_flags"]["official_model_reproduced"], "RNARL data scope exceeded")
    require(velov["status"] == "PASS" and velov["passed_checks"] == velov["check_count"] == 7 and velov["max_numeric_delta"] == 0.0, "VeloHARMO independent QC failed")
    require(not velov["independent_production_import"], "VeloHARMO verifier imported production code")
    require(velof["status"] == "ECOLI_QC_VERIFIED_FIVE_SPECIES_NOT_AVAILABLE" and velof["passed_checks"] == velof["check_count"] == 8, "VeloHARMO finalization failed")
    require(veloq["raw_records"] == veloq["clean_records"] == 1170 and veloq["excluded_records"] == 0 and veloq["duplicate_gene_ids"] == 0 and veloq["modal_feature_numeric_dim"] == 6, "VeloHARMO E. coli counts changed")
    require(velol["pass"] and velol["x_all_finite"] and velol["density_all_finite"] and not velol["training_performed"] and not velol["publication_metrics_reproduced"], "VeloHARMO loader scope changed")
    require(not velof["science_flags"]["five_species_data_closed"] and not velof["science_flags"]["official_cross_validation_reproduced"] and not velof["science_flags"]["sota_claim"], "VeloHARMO scientific scope exceeded")

    split_counts = {k: rk04["counts"][k]["rows"] for k in ("train", "dev", "test", "functional_untouched")}
    test = rk07["split_metrics"]["test"]
    points = {name: test["models"][name]["point"] for name in test["models"]}
    gc_delta = test["paired_comparisons"]["gc_fraction"]
    min_holm = min(v["spearman_p_holm"] for v in test["paired_comparisons"].values())
    quick = id3["source_preset_contract"]["quick_test"]
    id3_summary = next(c["detail"] for c in id3["checks"] if c["name"] == "summary_12_total")
    id3_pass_count = sum(bool(c["pass"]) for c in id3v["checks"])
    id3_check_count = len(id3v["checks"])
    ld_rows = "\n".join(f"| {r['lambda']:.1f} | {r['official_mfe_kcal_mol']:.2f} | {r['official_cai']:.3f} | {r['elapsed_s']:.3f} |" for r in ld["runs"])
    ed_rows = "\n".join(f"| {r['record_id']} | {r['protein_length_aa']} | {r['best_run_id']} | {r['best_official_efe_kcal_mol']:.2f} |" for r in ed["records"])
    ed_c01_record = edc["records"][0]

    section_31 = f"""### 3.1 External data and verified availability

The A8-RK audit separates verified data artifacts from model evidence. RiboMIMO contributes **{ribo['total_records']:,} raw records** and **{ribo['total_clean_records']:,} clean records** across four author-processed codon-level A-site-count datasets; the independent verifier passed **{len(ribov['checks'])}/{len(ribov['checks'])} checks**. These files do not contain UTRs or raw reads, so they do not authorize an independent P-site remapping analysis. The clean rule requires aligned lengths, canonical CDS translation, finite nonnegative counts, strict coverage, and exact translated-reference protein matching.

CodonTransformer training-table QC read **{ct['result']['rows']:,} raw rows** and retained **{ct['result']['clean_rows']:,} clean rows**; organism counts changed from **{ct['result']['raw_organisms']} raw** to **{ct['result']['clean_organisms']} clean**. Finalization passed with **{ct['result']['verification_checks']} independent checks**. The raw-table SHA256 is `{ct['result']['raw_sha256']}`. This artifact supports only a bounded natural DNA–protein sequence-distribution corpus; it does not provide host-matched functional labels, a trained model, functional OOD evidence, or a baseline ranking.

The functional long table contains **{rk02['functional_long_rows']:,} rows** and has SHA256 `{rk02['clean_artifacts']['functional_long']['sha256']}`. It comprises the verified Boël cross-protein records and MAGE construct-assay rows. The row-level Kudla 154-variant sequence–expression table remains unavailable; supporting methods and degenerate oligos are not substitutes for that table.

The RNARL official 21-file pair table contains **{rnalrf['raw_rows']:,} raw rows**, **{rnalrf['clean_rows']:,} clean rows**, and **{rnalrf['clean_pairs']:,} clean pairs**. Raw cross-split exact-CDS overlap comprised **{rnalrf['raw_cross_split_overlap_keys']['exact_cds']} keys / {rnalrf['raw_cross_split_exact_cds_rows']} rows**; production QC excluded the whole protein pairs, and independent clean-table rescanning found zero exact-CDS and zero protein-sequence cross-split keys. The corrected independent verifier passed **{rnarlqv['passed_checks']}/{rnarlqv['check_count']} checks** with maximum numeric delta **{rnarlqv['max_numeric_delta']:.1f}**, and recovery finalization passed **{rnalrf['passed_checks']}/{rnalrf['check_count']} checks**. The initial order-based verifier failure and recovery failure remain preserved. This is only a publisher-provided LinearDesign-like pair table: it does not establish natural-CDS provenance, lambda strata, UTR/raw-read remapping, functional training, functional OOD, official-model reproduction, or a baseline ranking.

VeloHARMO was audited at fixed commit `{velof['commit']}`. Its processed E. coli matrix has **{veloq['raw_records']:,} raw = {veloq['clean_records']:,} clean records**, **{veloq['duplicate_gene_ids']} duplicate gene IDs**, and **{veloq['modal_feature_numeric_dim']} numeric features**. Independent verification passed **{velov['passed_checks']}/{velov['check_count']} checks** with maximum numeric delta **{velov['max_numeric_delta']:.1f}**, and finalization passed **{velof['passed_checks']}/{velof['check_count']} checks**. The official `VeloGRU/VeloGRU_data.py::load_data` returned finite tensors `x={velol['x_shape']}`, `density={velol['density_shape']}`, and `length={velol['length_shape']}`. Only the processed E. coli matrix plus E. coli/yeast weights were materialized; **five-species processed matrices are not available** because Pseudomonas, Drosophila, human, and yeast matrices are missing. No five-species dataset closure, raw-read remapping, training, cross-validation, publication-metric, functional-OOD, or SOTA claim is authorized."""

    split_addition = f"""**RK04 frozen operational split.** MMseqs2 clustering used identity **{rk04['protocol']['identity']:.2f}**, bidirectional coverage **{rk04['protocol']['bidirectional_coverage']:.2f}**, and seed **{rk04['protocol']['seed']}**. The Boël rows were assigned to train/dev/test = **{split_counts['train']:,}/{split_counts['dev']:,}/{split_counts['test']:,}**, while **{split_counts['functional_untouched']:,} MAGE rows** remained untouched. Independent verification passed **{len(rk04v['checks'])}/{len(rk04v['checks'])} checks**, including zero overlap for exact CDS, exact protein/derived infA, source protein ID, operational cluster, construct-signature group, and nonblank mutation signature. These are operational MMseqs2 clusters, not curated protein families. The split is leakage-controlled but is not itself training-ready evidence: MAGE was not evaluated, and no generator or SOTA claim is authorized."""

    model_labels = [
        ("cai", "CAI"),
        ("gc_fraction", "GC fraction (direction selected on train)"),
        ("full_cds_mfe_kcal_mol", "Full-CDS MFE"),
        ("full_cds_mfe_per_nt", "Full-CDS MFE per nt"),
        ("mfe_5prime_48_kcal_mol", "5′ 48-nt MFE"),
        ("combined_logistic", "Combined logistic"),
    ]
    rows = "\n".join(f"| {label} | {points[key]['spearman']:.4f} |" for key, label in model_labels)
    section_62 = f"""### 6.2 Proxy validity: bounded cross-protein diagnostic

RK07 evaluated whether simple sequence-derived scores carry signal across different proteins in Boël et al. It is **not** a fixed-protein synonymous-library experiment. The combined model used train-only preprocessing and convex logistic fitting with the frozen feature set `{', '.join(rk07['combined_model']['feature_names'])}`; development results were frozen before test evaluation, and `functional_untouched` was not used.

On the frozen test set (**n = {test['n']:,}**), Spearman correlations were:

| Predictor | Test Spearman |
|---|---:|
{rows}

The combined model had Pearson **{points['combined_logistic']['pearson']:.4f}** and RMSE **{points['combined_logistic']['rmse']:.4f}**. Its point estimate exceeded the strongest single-proxy Spearman (directional GC) by **Δρ = {gc_delta['spearman_point_difference']:.4f}**, but the paired 95% bootstrap interval was **[{gc_delta['spearman_difference'][0]:.4f}, {gc_delta['spearman_difference'][1]:.4f}]** and the Holm-adjusted p-value was **{gc_delta['spearman_p_holm']:.4f}**. No paired Spearman comparison survived Holm correction on test (minimum adjusted **p = {min_holm:.4f}**). CAI alone was effectively uncorrelated (**ρ = {points['cai']['spearman']:.4f}**).

The independent verifier recomputed all **{rk07v['checks'][2]['details']['rows']:,}** CAI/GC/MFE rows, model predictions, **{rk07v['checks'][6]['details']['bootstrap_replicates_per_split']:,} bootstrap replicates per split**, stratified metrics, and Holm correction; **{rk07v['passed_checks']}/{rk07v['check_count']} checks passed**. The supported conclusion is therefore **limited and unstable cross-protein signal**, not a decisive failure of within-protein proxies. This diagnostic does not validate a fixed-protein synonymous mechanism, functional OOD gain, generator, or external-baseline ranking."""

    missing_methods = len(rnalrv["independent_ast_findings"]["grpo_missing_called_methods"])
    section_65 = f"""### 6.5 Baseline execution and reproducibility status

**ID3 bounded official execution.** The fixed ID3 commit `{id3['source']['id3_commit']}` and DeepRaccess commit `{id3['source']['deepraccess_commit']}` were materialized, and the official `cpu_v4` quick-test preset was executed. The actual protocol was **{len(quick['proteins'])} protein × {len(quick['constraints'])} constraints × {len(quick['variants'])} variants = {id3_summary['total_experiments']} runs**, **{quick['iterations']} iterations**, **{quick['seeds']} seed**, and `enable_cai={str(quick['enable_cai']).lower()}`. The official summary recorded **{id3_summary['successful']} successful / {id3_summary['failed']} failed** runs in **{id3_summary['total_time']:.3f} s**. Independent verification finished at **{id3_pass_count}/{id3_check_count} checks**, and finalization passed **{id3f['checks_passed']}/{id3f['checks_total']} finalization checks** with final-sequence evidence ready for recording.

This is a smoke result, not the separate full-12×12 protocol and not a main comparison. Four checks were retained as failures: `CodonProfileConstraint.forward()` omits `beta` when calling `CodonPsiFunction.forward()`, and the `beta == 1.0` runner branch records a soft-path accessibility value as a discrete score. Consequently, CPC×1 initial/best/improvement/trajectory fields and affected summary aggregates are excluded. Only the bounded final sequences and final scores are retained.

**LinearDesign bounded official execution.** The clean codeload archive at commit `{ld['commit']}` was built from source, and the official README example matched its documented sequence. On frozen 135-aa protein `{ld['record_id']}`, the official binary produced three unique synonymous outputs for λ = 0/0.5/1 in **{ld['total_elapsed_s']:.3f} s total**:

| λ | Official MFE (kcal/mol) | Official CAI | Wall time (s) |
|---:|---:|---:|---:|
{ld_rows}

Independent raw-output verification passed **{ldv['passed_checks']}/{ldv['check_count']} checks** with maximum numeric delta **{ldv['max_numeric_delta']:.1f}**, and finalization passed **{ldf['passed_checks']}/{ldf['check_count']} checks**. Official MFE matched ViennaRNA at 37°C with `dangles=0` (maximum rounding delta {ldf['checks'][4]['detail']['max_mfe_delta']:.6f}); default `dangles=2` values were also retained. The earlier default-dangles v1 failure is preserved as `{ld_fail['status']}` rather than erased. This remains a single-record, three-λ bounded smoke, not the full seven-λ actual-set matrix, dense-budget comparison, functional OOD evaluation, or SOTA result.

**EnsembleDesign bounded official execution.** The fixed official commit `{ed['commit']}` was built without source modification. The README example completed **{ed['input_record_count']} records × {ed['parameters']['num_runs']} runs = {ed['run_count']} runs** with **{ed['unique_output_sequences']} unique CDSs** in **{ed['total_elapsed_s']:.3f} s**; the official sequences and reported EFE values matched:

| Record | Protein length (aa) | Best run | Official EFE (kcal/mol) |
|---|---:|---:|---:|
{ed_rows}

The same bounded protocol then executed `{edc['benchmark']['record_id']}` ({ed_c01_record['protein_length_aa']} aa) for **{edc['run_count']} runs**, producing **{edc['unique_output_sequences']} unique CDSs** in **{edc['total_elapsed_s']:.3f} s**. Best run {ed_c01_record['best_run_id']} had official EFE **{ed_c01_record['best_official_efe_kcal_mol']:.2f} kcal/mol** and CDS length **{ed_c01_record['runs'][0]['sequence_length_nt']} nt**; no extra terminal stop was appended. Independent raw-output and scorer verification passed **{edv['passed_checks']}/{edv['check_count']}** example checks and **{edcv['passed_checks']}/{edcv['check_count']}** C01 checks, both with maximum numeric delta **0.0**; finalization passed **{edf['passed_checks']}/{edf['check_count']} checks**. The initial stop-contract wrapper failure remains preserved. EFE is not LinearDesign MFE, so these values do not authorize a direct cross-method ranking. No matched LinearDesign comparison, dense-budget evaluation, functional OOD result, or SOTA claim was produced.

**RNARL fixed-source availability audit.** At public commit `{rnarl['commit']}`, exact entry-point smoke and independent AST checks passed **{rnalrv['pass_count']}/{rnalrv['total']} checks for a negative reproducibility result**. Actor and reward constructors do not match their public entry calls, the actor lacks the called evaluation method, and GRPO lacks **{missing_methods} called methods** plus its main globals. No full training, generation, paper metric, or baseline comparison was produced. This finding concerns the current public snapshot's direct executability; it does not show that the RNARL scientific method is invalid.

**CDGB source-identity audit.** The candidate title `{cdgb['candidate']['title']}` was assessed through **{cdgb['query_count_succeeded']}/{cdgb['query_count_expected']} frozen scholarly/repository API queries** across Crossref, OpenAlex, Europe PMC, and GitHub; no exact scholarly title match was found. The DOI embedded in the candidate URL, `{cdgb['candidate']['doi_embedded_in_url']}`, instead resolves to `{cdgb['candidate_doi_identity']['crossref_title']}` in Briefings in Bioinformatics volume {cdgb['candidate_doi_identity']['crossref_volume']} issue {cdgb['candidate_doi_identity']['crossref_issue']}. The exact GitHub CDGB+codon and CDGB+protein-representation repository queries each returned zero records; the broader codon-deoptimization query returned {cdgb['query_summaries']['github_codon_deoptimization']['total_count_reported_by_github']} unrelated candidates and does not establish official ownership. Independent verification passed **{cdgbv['checks_passed']}/{cdgbv['checks_total']} checks**, and finalization passed **{cdgbf['checks_passed']}/{cdgbf['checks_total']} checks**. No official CDGB repository, immutable commit, build, execution, output sequence, or performance result was established. This bounded source audit is not evidence that the CDGB method is invalid or that no implementation exists.

The unified main-baseline matrix, dense candidate-budget comparison, functional OOD evaluation, and SOTA assessment remain pending."""

    evidence_rows = [
        ("RK02 functional long table", rk02["clean_artifacts"]["functional_long"]["sha256"]),
        ("RK04 split assignment table", rk04["artifacts"]["functional_long_split"]["sha256"]),
        ("RK07 frozen result", source_hashes["rk07"]),
        ("RiboMIMO independent verifier", source_hashes["ribomimo_verify"]),
        ("CodonTransformer raw table", ct["result"]["raw_sha256"]),
        ("ID3 independent verifier v2", source_hashes["id3_verify"]),
        ("LinearDesign independent verifier v2", source_hashes["ld_verify"]),
        ("LinearDesign finalization", source_hashes["ld_final"]),
        ("LinearDesign v1 retained failure", source_hashes["ld_v1_failure"]),
        ("EnsembleDesign example production", source_hashes["ed_example"]),
        ("EnsembleDesign C01 production", source_hashes["ed_c01"]),
        ("EnsembleDesign example independent verifier", source_hashes["ed_example_verify"]),
        ("EnsembleDesign C01 independent verifier", source_hashes["ed_c01_verify"]),
        ("EnsembleDesign finalization", source_hashes["ed_final"]),
        ("CDGB source audit", source_hashes["cdgb_audit"]),
        ("CDGB independent verifier", source_hashes["cdgb_verify"]),
        ("CDGB finalization", source_hashes["cdgb_final"]),
        ("RNARL negative audit", source_hashes["rnarl_verify"]),
        ("RNARL full QC finalization", source_hashes["rnarl_final"]),
        ("RNARL corrected independent verifier", source_hashes["rnarl_qc_verify"]),
        ("VeloHARMO E. coli matrix", veloq["matrix_sha256"]),
        ("VeloHARMO finalization", source_hashes["velo_final"]),
        ("VeloHARMO independent verifier", source_hashes["velo_verify"]),
    ]
    evidence_table = "\n".join(f"| {name} | `{digest}` |" for name, digest in evidence_rows)
    reproducibility_addition = f"""### 8.1 A8-RK evidence anchors

The working-manuscript values above were rendered from the following frozen artifacts. Large CSV, prediction, and weight files remain outside Git under the project artifact root; their report-level hashes are recorded here.

| Evidence | SHA256 |
|---|---|
{evidence_table}

A7 is retained as the prior manuscript snapshot. This A8 file remains a **non-submittable working manuscript** until the mechanism, main model, actual-set baselines, OOD, clean-environment reproduction, and prospective validation gates are complete."""

    text = template.read_text(encoding="utf-8")
    old_status = next(line for line in text.splitlines() if line.startswith("**Status:") or line.startswith("> **Status:"))
    new_status = "> **Status: A8-RK working manuscript — not for submission.** Verified data, operational split, bounded cross-protein diagnostic, and bounded baseline-execution audits are recorded; core mechanism, model, main baseline matrix, OOD, generator, and wet-lab closure remain incomplete. No SOTA claim."
    text = text.replace(old_status, new_status, 1)
    text = replace_section(text, "### 3.1 Natural, mechanistic and functional data", "### 3.2 Leakage-controlled generalization tasks", section_31)
    text = append_to_section(text, "### 3.3 Task-specific comparisons", split_addition)
    text = replace_section(text, "### 6.2 Proxy validity on real synonymous variants", "### 6.3 Incremental evidence for spatial coupling", section_62)
    text = replace_section(text, "### 6.5 Task-specific strongest-baseline comparisons", "### 6.6 Mechanistic ablations and failure boundaries", section_65)
    text = append_to_section(text, "## 9. References", reproducibility_addition)

    require("### 6.2 Proxy validity: bounded cross-protein diagnostic\n\nRK07 evaluated" in text, "RK07 section insertion failed")
    require("RNARL official 21-file pair table contains" in text, "RNARL full QC result missing")
    require("five-species processed matrices are not available" in text, "VeloHARMO missing-species boundary missing")
    require("LinearDesign bounded official execution" in text, "LinearDesign bounded result missing")
    require("EnsembleDesign bounded official execution" in text and "EFE is not LinearDesign MFE" in text and "No matched LinearDesign comparison" in text, "EnsembleDesign bounded result or scope missing")
    require("CDGB source-identity audit" in text and "not evidence that the CDGB method is invalid or that no implementation exists" in text, "CDGB bounded source result missing")
    require("The unified main-baseline matrix" in text, "baseline pending boundary missing")
    require("No SOTA claim." in text, "working-manuscript boundary missing")
    atomic_write(output, text)

    audit = {
        "schema_version": "a8-rk-paper-sync-v5",
        "status": "PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE",
        "template": str(template),
        "template_sha256": sha256(template),
        "output": str(output),
        "output_sha256": sha256(output),
        "source_paths": {name: str(path) for name, path in paths.items()},
        "source_sha256": source_hashes,
        "generated_sections": ["3.1", "3.2 RK04 addition", "6.2", "6.5", "8.1"],
        "pending_preserved": ["RNARL natural-CDS provenance and UTR/raw-read remapping", "VeloHARMO five-species matrices and official cross-validation", "Q2 empirical MFE", "Q3 mechanistic increments", "Q4–Q6 model and proxy failure", "dense candidate-budget comparison", "main baseline matrix", "OOD", "wet-lab validation"],
        "scientific_scope": {
            "rk07": "bounded cross-protein diagnostic only",
            "id3": "official bounded quick-test only; CPC STE defects retained",
            "lineardesign": "official single-record three-lambda bounded smoke only; both dangling-end conventions retained",
            "ensembledesign": "official README example and single-C01 bounded smoke only; EFE is not MFE; no matched comparison or ranking",
            "cdgb": "bounded source-identity audit only; unresolved candidate identity; no official repository, execution, sequence, or performance result",
            "rnarl_code": "negative public-snapshot reproducibility only",
            "rnarl_data": "bounded publisher-provided LinearDesign-like pair table only",
            "veloharmo": "processed E. coli matrix and official loader only; five-species data and model evidence open",
            "sota": False,
            "submittable": False,
        },
    }
    atomic_write(audit_path, json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": audit["status"], "output": str(output), "output_sha256": audit["output_sha256"], "audit": str(audit_path)}, indent=2))


if __name__ == "__main__":
    main()
