#!/usr/bin/env python3
"""Build the frozen RK35 protocol JSON with computed SHA256 gates.

Run AFTER the label-free preflight succeeds and BEFORE any production fit.
Refuses to overwrite an existing protocol.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

TEAMS = Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--preflight-report", type=Path, required=True)
    ap.add_argument("--preflight-csv", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    repo = args.repo
    audits32 = repo / "audits/20261121/RK32"
    rk32_result_path = audits32 / "rk32_structure_definition_result_v2.json"
    rk32_result = json.loads(rk32_result_path.read_text())
    rk32_outputs = rk32_result["outputs"]

    def entry(path: Path) -> dict:
        return {"path": str(path), "sha256": sha256(path)}

    inputs = {
        "main_csv": entry(TEAMS / "rk21/kudla_recovery_v1/derived/kudla154_source.csv"),
        "rk27_coverage_report": entry(repo / "audits/20261121/RK27/rk27_sequence_coverage_v1.json"),
        "rk32_preflight_csv": entry(TEAMS / "rk32/structure_definition_v1/preflight_candidate_energies.csv"),
        "rk32_result_v2": entry(rk32_result_path),
        "rk32_oof_predictions": entry(Path(rk32_outputs["oof_predictions.csv"]["path"])),
        "rk32_fold_assignments": entry(Path(rk32_outputs["fold_assignments.csv"]["path"])),
        "rk32_seed_effects": entry(Path(rk32_outputs["seed_effects.csv"]["path"])),
        "rk35_preflight_csv": entry(args.preflight_csv),
        "rk35_preflight_report": entry(args.preflight_report),
    }
    for key, filename in (("rk32_oof_predictions", "oof_predictions.csv"), ("rk32_fold_assignments", "fold_assignments.csv"), ("rk32_seed_effects", "seed_effects.csv")):
        if inputs[key]["sha256"] != rk32_outputs[filename]["sha256"]:
            raise ValueError(f"reuse file hash differs from RK32 result: {key}")
    preflight = json.loads(args.preflight_report.read_text())
    if preflight["status"] != "PASS_LABEL_FREE_PREFLIGHT":
        raise ValueError("preflight not passed")

    gate_reference = {}
    for row in rk32_result["primary_tests"]:
        if "__vienna_local__" in row["test"]:
            gate_reference[row["test"]] = {
                "observed_effect": row["observed_effect"], "ci95": row["ci95"],
                "p_cluster_swap": row["p_cluster_swap"], "pass": row["pass"],
            }

    protocol = {
        "schema": "a8-rk35-coverage-transport-protocol-v1",
        "status": "FROZEN_BEFORE_RK35_EXPRESSION_ASSOCIATION_OR_MODEL_FIT",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scientific_question": "Does the actual RK33 natural window CDS[3:45] (1-based CDS4-45, no start ATG, no upstream UTR) retain the RK32 local-structure increment within the frozen Kudla cohort, and does exact start-aware coverage beat it? Tests coverage-transport vs host/assay as explanations of the RK28/RK33 cross-study negatives, using natural (unmasked) windows.",
        "relationship_to_RK34": "RK34 (parallel session, matched N-mask factorial start_context) owns the clean upstream-vs-start decomposition with a fixed CDS4-38 body. RK35 is complementary: it tests the natural RK33 slice and natural CDS-start window, which RK34's N-masked controls cannot represent. RK35 secondary contrasts (atg_vs_trunc, exact_vs_atg) shift the CDS body and are therefore body-confounded; they are descriptive only and any clean decomposition is deferred to RK34.",
        "analysis_type": "retrospective_outcome_known_followup_not_independent_confirmation",
        "inputs": inputs,
        "cohort": {"n_measurement_rows": 154, "n_exact_cds_groups": 150, "n_sequence_clusters": 37, "utr_length": 144, "cds_length": 720, "target": "group mean log10_expression", "aggregation": "exact cds_sha256 groups, CAI constant within group"},
        "simple_features": ["CAI", "gc_cds", "gc3_cds"],
        "structure_features": {
            "exact_local": ["vienna_exact_local_mfe"],
            "cds_start_local": ["vienna_cds_start_mfe"],
            "trunc_local": ["vienna_trunc_mfe"],
            "trunc_local_d0": ["vienna_trunc_d0_mfe"],
        },
        "window_definitions": {
            "exact_local": "UTR[-4:]+CDS[:38], 42 nt, dangles=2, 37 C; energy from RK32 preflight local_utr_minus4_cds38__dangles2",
            "cds_start_local": "CDS[0:42], 42 nt, includes start ATG, no UTR, dangles=2, 37 C; energy from RK32 preflight local_cds42__dangles2",
            "trunc_local": "CDS[3:45] (1-based CDS4-45), 42 nt, excludes start ATG and UTR, dangles=2, 37 C; energy from RK35 preflight trunc_cds4_45__dangles2",
            "trunc_local_d0": "CDS[3:45], dangles=0, 37 C (RK33 prediction definition); secondary sensitivity only",
        },
        "models": {
            "ridge": "StandardScaler + Ridge(alpha=1.0)",
            "histgb": "HistGradientBoostingRegressor(loss=squared_error, learning_rate=0.05, max_iter=200, max_leaf_nodes=7, min_samples_leaf=10, l2_regularization=1.0, early_stopping=False, random_state=seed+fold)",
        },
        "outer_evaluation": {"seeds": [20261221 + i for i in range(10)], "primary_seed": 20261221, "folds": 5, "fold_scheme": "whole-cluster balanced OOD, identical algorithm to RK32"},
        "fit_accounting": {"new_fits": 300, "reused_fits": 200, "evaluated_fits": 500, "reused_arms": {"simple": "RK32 simple OOF", "exact_local": "RK32 vienna_local OOF"}, "reuse_gates": ["input SHA equality", "regenerated folds equal RK32 fold_assignments for all 10 seeds", "RK32 null equals recomputed train target mean within 1e-12", "consistency gate below"]},
        "primary_contrasts": {
            "trunc_vs_simple": ["simple", "trunc_local"],
            "exact_vs_trunc": ["trunc_local", "exact_local"],
        },
        "gate_contrast": {"exact_vs_simple": ["simple", "exact_local"]},
        "secondary_contrasts": {
            "atg_vs_trunc": ["trunc_local", "cds_start_local"],
            "exact_vs_atg": ["cds_start_local", "exact_local"],
            "trunc_d0_vs_simple": ["simple", "trunc_local_d0"],
        },
        "primary_inference": {
            "resamples": 20000, "bootstrap_seed": 20261321, "permutation_seed": 20261322,
            "bootstrap": "whole-cluster resample, int16 cluster indices, Spearman recomputed on concatenated resampled rows, MSE weighted by cluster multiplicity",
            "permutation": "within-cluster sign swap of the two arm predictions, int8 signs",
            "ci": "percentile 2.5/97.5", "p": "plus-one two-sided (1+#{|null|>=|obs|})/(resamples+1)",
            "multiplicity": "Holm over the 8 primary tests only; gate family Holm(4) internal; secondary family Holm(12) descriptive only, no gate",
            "pass_rule": "effect>0 AND ci_lower>0 AND p_holm<0.05 AND positive_seeds>=8/10",
            "contrast_support": "4/4 endpoints",
        },
        "consistency_gate": {
            "reference": "RK32 result_v2 vienna_local primary tests and seed_effects",
            "tolerance": 1e-12,
            "fields": ["observed_effect", "ci95_lower", "ci95_upper", "p_cluster_swap", "seed_effects_max"],
            "requirement": "all four gate tests bitwise-equal within tolerance AND pass own Holm(4)",
            "on_failure": "CONSISTENCY_GATE_FAILED_NOT_EVALUATED; stop scientific interpretation; engineering audit only",
            "reference_values": gate_reference,
        },
        "decision_tree": {
            "priority": ["gate", "D1", "D2", "D3"],
            "D1": {"condition": "trunc_vs_simple 4/4", "conclusion": "RK33_COVERAGE_RETAINS_INCREMENT_WITHIN_KUDLA_RETROSPECTIVELY", "implication": "the natural RK33 truncated coverage still carries the increment within Kudla; coverage is NOT necessary; RK28/RK33 cross-study negatives cannot be attributed to coverage alone; host/assay/study-level factors become primary candidates; next step: cross-host full-coverage public data transport test; no further Kudla window mining"},
            "D2": {"condition": "trunc_vs_simple fails AND exact_vs_trunc 4/4 AND gate passes", "conclusion": "START_AWARE_COVERAGE_NECESSARY_WITHIN_KUDLA_RETROSPECTIVELY", "implication": "exact start-aware coverage beats the RK33 window and the RK33 window loses the increment within Kudla; start-aware coverage necessary within Kudla (natural-window evidence); clean upstream/start decomposition deferred to RK34; cross-host transport still unproven; host/assay not discriminated"},
            "D3": {"condition": "gate passes AND trunc_vs_simple fails AND exact_vs_trunc fails", "conclusion": "COVERAGE_TRANSPORT_NOT_DISCRIMINATED_RETROSPECTIVELY", "implication": "no claim of coverage necessity or sufficiency; includes small-effect/underpowered cases"},
        },
        "power_note": "37 clusters with 20000 resamples detect large coverage effects of RK32 magnitude; effects below ~0.2 delta-Spearman may fall into D3; no post-hoc power adjustment; primary family reduced to 8 tests (vs an earlier 16-test sketch) to concentrate power on the transport question after RK34 took ownership of the matched-body decomposition",
        "forbidden_claims": ["independent_untouched_confirmation", "causal_host_mechanism", "protein_ood", "external_sota", "generator_training_authorization", "post_hoc_feature_addition", "gate_modification", "resplit", "tolerance_relaxation", "clean_upstream_start_decomposition_from_body_confounded_secondary_contrasts"],
        "functional_untouched_read": False,
        "generator_training_authorized": False,
        "code": {
            "preflight_script": "scripts/a8_rk35_preflight.py",
            "preflight_script_sha256": sha256(repo / "scripts/a8_rk35_preflight.py"),
            "production_script": "scripts/a8_rk35_run_coverage_transport.py",
            "production_script_sha256": sha256(repo / "scripts/a8_rk35_run_coverage_transport.py"),
            "independent_script": "scripts/a8_rk35_verify_coverage_transport.py",
            "independent_script_sha256": sha256(repo / "scripts/a8_rk35_verify_coverage_transport.py"),
            "comparison_script": "scripts/a8_rk35_compare_reproduction.py",
            "comparison_script_sha256": sha256(repo / "scripts/a8_rk35_compare_reproduction.py"),
            "closeout_script": "scripts/a8_rk35_closeout.py",
            "closeout_script_sha256": sha256(repo / "scripts/a8_rk35_closeout.py"),
            "tests": "tests/test_a8_rk35_coverage_transport.py",
            "tests_sha256": sha256(repo / "tests/test_a8_rk35_coverage_transport.py"),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(protocol, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(json.dumps({"protocol": str(args.output), "sha256": sha256(args.output), "status": protocol["status"]}, indent=2))


if __name__ == "__main__":
    main()