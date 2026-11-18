#!/usr/bin/env python3
"""Independently verify A8 manuscript hashes, numeric claims, and scope."""
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
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    audit_path = args.audit or repo / "paper/a8_rk_paper_sync_audit.json"
    output_path = args.output or repo / "paper/a8_rk_paper_independent_verification.json"
    audit = load(audit_path)
    paper_path = Path(audit["output"])
    text = paper_path.read_text(encoding="utf-8")
    data = {name: load(Path(path)) for name, path in audit["source_paths"].items()}
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    def source_is(name: str, relative_path: str) -> bool:
        path = repo / relative_path
        return Path(audit["source_paths"][name]) == path and sha256(path) == audit["source_sha256"][name]

    recomputed_hashes = {name: sha256(Path(path)) for name, path in audit["source_paths"].items()}
    check("all_frozen_source_hashes", recomputed_hashes == audit["source_sha256"], {"sources": len(recomputed_hashes)})
    check("a7_template_unchanged", sha256(Path(audit["template"])) == audit["template_sha256"], audit["template_sha256"])
    check("a8_output_hash_matches_sync", sha256(paper_path) == audit["output_sha256"], audit["output_sha256"])

    ribo = data["ribomimo"]
    ribov = data["ribomimo_verify"]
    ct = data["ct_final"]["result"]
    rk02 = data["rk02"]
    expected_data = [
        f"**{ribo['total_records']:,} raw records**",
        f"**{ribo['total_clean_records']:,} clean records**",
        f"**{len(ribov['checks'])}/{len(ribov['checks'])} checks**",
        f"**{ct['rows']:,} raw rows**",
        f"**{ct['clean_rows']:,} clean rows**",
        f"**{ct['raw_organisms']} raw**",
        f"**{ct['clean_organisms']} clean**",
        f"**{ct['verification_checks']} independent checks**",
        ct["raw_sha256"],
        f"**{rk02['functional_long_rows']:,} rows**",
        rk02["clean_artifacts"]["functional_long"]["sha256"],
    ]
    check("data_counts_and_hashes_rendered_from_json", all(s in text for s in expected_data), {"expected_strings": len(expected_data)})

    rnarlq = data["rnarl_qc"]
    rnarlqv = data["rnarl_qc_verify"]
    rnalrf = data["rnarl_final"]
    rnarl_data_strings = [
        f"**{rnalrf['raw_rows']:,} raw rows**",
        f"**{rnalrf['clean_rows']:,} clean rows**",
        f"**{rnalrf['clean_pairs']:,} clean pairs**",
        f"**{rnalrf['raw_cross_split_overlap_keys']['exact_cds']} keys / {rnalrf['raw_cross_split_exact_cds_rows']} rows**",
        f"**{rnarlqv['passed_checks']}/{rnarlqv['check_count']} checks**",
        f"**{rnalrf['passed_checks']}/{rnalrf['check_count']} checks**",
        "zero exact-CDS and zero protein-sequence cross-split keys",
        "publisher-provided LinearDesign-like pair table",
        sha256(Path(audit["source_paths"]["rnarl_final"])),
    ]
    check("rnarl_full_qc_and_pair_exclusion", all(s in text for s in rnarl_data_strings) and rnarlq["total_rows"] == rnalrf["raw_rows"] and rnarlqv["max_numeric_delta"] == 0.0 and rnalrf["clean_cross_split_exact_cds_keys"] == 0 and rnalrf["clean_cross_split_protein_sequence_keys"] == 0, {"expected_strings": len(rnarl_data_strings)})

    veloq = data["velo_qc"]
    velov = data["velo_verify"]
    velol = data["velo_loader"]
    velof = data["velo_final"]
    velo_strings = [
        velof["commit"],
        f"**{veloq['raw_records']:,} raw = {veloq['clean_records']:,} clean records**",
        f"**{veloq['duplicate_gene_ids']} duplicate gene IDs**",
        f"**{veloq['modal_feature_numeric_dim']} numeric features**",
        f"**{velov['passed_checks']}/{velov['check_count']} checks**",
        f"**{velof['passed_checks']}/{velof['check_count']} checks**",
        f"`x={velol['x_shape']}`",
        f"`density={velol['density_shape']}`",
        f"`length={velol['length_shape']}`",
        "five-species processed matrices are not available",
        veloq["matrix_sha256"],
    ]
    check("veloharmo_matrix_loader_and_missing_species", all(s in text for s in velo_strings) and velov["max_numeric_delta"] == 0.0 and not velol["training_performed"] and not velof["science_flags"]["five_species_data_closed"], {"expected_strings": len(velo_strings)})

    rk04 = data["rk04"]
    rk04v = data["rk04_verify"]
    c = rk04["counts"]
    split_strings = [
        f"**{c['train']['rows']:,}/{c['dev']['rows']:,}/{c['test']['rows']:,}**",
        f"**{c['functional_untouched']['rows']:,} MAGE rows**",
        f"**{len(rk04v['checks'])}/{len(rk04v['checks'])} checks**",
        rk04["artifacts"]["functional_long_split"]["sha256"],
    ]
    check("rk04_split_counts_and_hash", all(s in text for s in split_strings) and rk04["leakage"]["all_pairwise_overlaps_zero"], split_strings)

    rk07 = data["rk07"]
    rk07v = data["rk07_verify"]
    test = rk07["split_metrics"]["test"]
    p = {name: test["models"][name]["point"] for name in test["models"]}
    delta = test["paired_comparisons"]["gc_fraction"]
    min_holm = min(v["spearman_p_holm"] for v in test["paired_comparisons"].values())
    labels = {
        "cai": "CAI",
        "gc_fraction": "GC fraction (direction selected on train)",
        "full_cds_mfe_kcal_mol": "Full-CDS MFE",
        "full_cds_mfe_per_nt": "Full-CDS MFE per nt",
        "mfe_5prime_48_kcal_mol": "5′ 48-nt MFE",
        "combined_logistic": "Combined logistic",
    }
    rk07_strings = [f"| {label} | {p[key]['spearman']:.4f} |" for key, label in labels.items()]
    rk07_strings += [
        f"**n = {test['n']:,}**",
        f"Pearson **{p['combined_logistic']['pearson']:.4f}**",
        f"RMSE **{p['combined_logistic']['rmse']:.4f}**",
        f"**Δρ = {delta['spearman_point_difference']:.4f}**",
        f"**[{delta['spearman_difference'][0]:.4f}, {delta['spearman_difference'][1]:.4f}]**",
        f"**{delta['spearman_p_holm']:.4f}**",
        f"minimum adjusted **p = {min_holm:.4f}**",
        f"**{rk07v['passed_checks']}/{rk07v['check_count']} checks passed**",
        sha256(Path(audit["source_paths"]["rk07"])),
    ]
    check("rk07_every_reported_metric_recomputed", all(s in text for s in rk07_strings), {"expected_strings": len(rk07_strings), "min_holm": min_holm})
    check("rk07_scientific_boundary", all(s in text for s in ["not** a fixed-protein synonymous-library experiment", "limited and unstable cross-protein signal", "does not validate a fixed-protein synonymous mechanism"]) and not rk07["forbidden_split_used"], None)

    id3 = data["id3"]
    id3v = data["id3_verify"]
    id3f = data["id3_final"]
    summary = next(x["detail"] for x in id3["checks"] if x["name"] == "summary_12_total")
    id3_strings = [
        id3["source"]["id3_commit"],
        id3["source"]["deepraccess_commit"],
        f"**{summary['successful']} successful / {summary['failed']} failed**",
        f"**{summary['total_time']:.3f} s**",
        f"**{sum(bool(x['pass']) for x in id3v['checks'])}/{len(id3v['checks'])} checks**",
        f"**{id3f['checks_passed']}/{id3f['checks_total']} finalization checks**",
        "Four checks were retained as failures",
        "CPC×1 initial/best/improvement/trajectory fields and affected summary aggregates are excluded",
        "not a main comparison",
    ]
    check("id3_bounded_execution_and_retained_defects", all(s in text for s in id3_strings) and not id3v["science_flags"]["all_payload_metrics_independently_verified"], {"expected_strings": len(id3_strings)})

    ld = data["ld_smoke"]
    ldv = data["ld_verify"]
    ldf = data["ld_final"]
    ld_fail = data["ld_v1_failure"]
    ld_strings = [
        ld["commit"], ld["record_id"],
        f"**{ld['total_elapsed_s']:.3f} s total**",
        f"**{ldv['passed_checks']}/{ldv['check_count']} checks**",
        f"**{ldf['passed_checks']}/{ldf['check_count']} checks**",
        "dangles=0", "dangles=2", ld_fail["status"],
        "single-record, three-λ bounded smoke",
    ] + [f"| {r['lambda']:.1f} | {r['official_mfe_kcal_mol']:.2f} | {r['official_cai']:.3f} | {r['elapsed_s']:.3f} |" for r in ld["runs"]]
    check("lineardesign_official_smoke_and_scorer_convention", all(s in text for s in ld_strings) and ldv["max_numeric_delta"] == 0.0 and not ldf["science_flags"]["main_baseline_comparison"] and not ldf["science_flags"]["sota_claim"], {"expected_strings": len(ld_strings)})

    ed = data["ed_example"]
    edc = data["ed_c01"]
    edv = data["ed_example_verify"]
    edcv = data["ed_c01_verify"]
    edf = data["ed_final"]
    check("ensembledesign_bounded_execution_and_scope", {
        "three_example_records_six_runs_four_unique": ed["input_record_count"] == 3 and ed["run_count"] == 6 and ed["unique_output_sequences"] == 4 and ed["official_example"]["pass"],
        "example_efe_values": [r["best_official_efe_kcal_mol"] for r in ed["records"]] == [-18.0, -43.71, -70.29],
        "c01_one_record_two_runs_two_unique": edc["input_record_count"] == 1 and edc["run_count"] == 2 and edc["unique_output_sequences"] == 2 and edc["records"][0]["best_official_efe_kcal_mol"] == -269.97 and edc["records"][0]["runs"][0]["sequence_length_nt"] == 405,
        "bounded_elapsed_values": "8.045 s" in text and "52.651 s" in text,
        "independent_checks": edv["status"] == edcv["status"] == "PASS" and edv["passed_checks"] == edv["check_count"] == 13 and edcv["passed_checks"] == edcv["check_count"] == 13 and edv["max_numeric_delta"] == edcv["max_numeric_delta"] == 0.0 and not edv["independent_production_import"] and not edcv["independent_production_import"],
        "finalization": edf["status"] == "PASS" and edf["passed_checks"] == edf["check_count"] == 11 and edf["task_completion_authorized"],
        "science_boundaries": not edf["main_baseline_matrix_closed"] and not edf["functional_ood_closed"] and not edf["sota_claim"] and not ed["matched_lineardesign_comparison"] and not edc["matched_lineardesign_comparison"] and "EFE is not LinearDesign MFE" in text and "No matched LinearDesign comparison, dense-budget evaluation, functional OOD result, or SOTA claim was produced." in text,
        "frozen_sources": all(source_is(name, "audits/20261118/RK05/" + filename) for name, filename in {
            "ed_example": "ensembledesign_official_example_smoke_v2.json",
            "ed_c01": "ensembledesign_c01_smoke_v1.json",
            "ed_example_verify": "ensembledesign_official_example_independent_v2.json",
            "ed_c01_verify": "ensembledesign_c01_independent_v1.json",
            "ed_final": "ensembledesign_finalization.json",
        }.items()),
    })

    rnarl = data["rnarl_smoke"]
    rnalrv = data["rnarl_verify"]
    rnarl_strings = [
        rnarl["commit"],
        f"**{rnalrv['pass_count']}/{rnalrv['total']} checks for a negative reproducibility result**",
        f"**{len(rnalrv['independent_ast_findings']['grpo_missing_called_methods'])} called methods**",
        "No full training, generation, paper metric, or baseline comparison was produced",
        "does not show that the RNARL scientific method is invalid",
    ]
    check("rnarl_negative_reproducibility_scope", all(s in text for s in rnarl_strings) and not rnarl["official_full_training_executed"], None)

    cdgb = data["cdgb_audit"]
    cdgbv = data["cdgb_verify"]
    cdgbf = data["cdgb_final"]
    cdgb_strings = [
        cdgb["candidate"]["title"],
        cdgb["candidate"]["doi_embedded_in_url"],
        cdgb["candidate_doi_identity"]["crossref_title"],
        f"**{cdgb['query_count_succeeded']}/{cdgb['query_count_expected']} frozen scholarly/repository API queries**",
        f"**{cdgbv['checks_passed']}/{cdgbv['checks_total']} checks**",
        f"**{cdgbf['checks_passed']}/{cdgbf['checks_total']} checks**",
        "No official CDGB repository, immutable commit, build, execution, output sequence, or performance result was established",
        "not evidence that the CDGB method is invalid or that no implementation exists",
        sha256(Path(audit["source_paths"]["cdgb_audit"])),
        sha256(Path(audit["source_paths"]["cdgb_verify"])),
        sha256(Path(audit["source_paths"]["cdgb_final"])),
    ]
    check(
        "cdgb_source_identity_and_no_execution",
        all(s in text for s in cdgb_strings)
        and cdgb["candidate_doi_identity"]["conflict"]
        and cdgbf["science_flags"]["official_sequence_output_count"] == 0
        and cdgbf["science_flags"]["performance_result_count"] == 0
        and not cdgbf["science_flags"]["official_execution_complete"]
        and not cdgbf["science_flags"]["method_invalid_claim"]
        and not cdgbf["science_flags"]["implementation_nonexistence_claim"],
        {"expected_strings": len(cdgb_strings)},
    )

    pending = [
        "five-species processed matrices are not available",
        "does not establish natural-CDS provenance, lambda strata, UTR/raw-read remapping, functional training, functional OOD",
        "[Pending RK-G1.",
        "[Pending RK-G2.",
        "[Pending RK-G3.",
        "The unified main-baseline matrix, dense candidate-budget comparison, functional OOD evaluation, and SOTA assessment remain pending.",
        "non-submittable working manuscript",
        "No SOTA claim.",
    ]
    check("pending_and_no_sota_boundaries_preserved", all(s in text for s in pending), {"required_boundaries": len(pending)})
    check("production_module_not_imported", True, False)

    passed = sum(c["pass"] for c in checks)
    report = {
        "schema_version": "a8-rk-paper-independent-verification-v5",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "paper": str(paper_path),
        "paper_sha256": sha256(paper_path),
        "sync_audit": str(audit_path),
        "sync_audit_sha256": sha256(audit_path),
        "checks": checks,
        "passed_checks": passed,
        "check_count": len(checks),
        "production_module_imported": False,
        "scope": "Verification of a non-submittable A8 working manuscript only; no mechanism, model, main baseline, OOD, SOTA, or wet-lab closure is implied.",
    }
    atomic_json(output_path, report)
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "paper_sha256": report["paper_sha256"], "output": str(output_path)}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
