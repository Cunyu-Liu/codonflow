#!/usr/bin/env python3
"""Build the immutable RK-G0 evidence/cost protocol from frozen source reports."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SOURCES = {
    "rk12_final": "audits/20261118/RK12/rk12_finalization_v1.json",
    "rk13_final": "audits/20261118/RK13/rk13_finalization_v1.json",
    "rk12_independent": "audits/20261118/RK12/actual_set_matrix_independent_v2.json",
    "rk06_final": "audits/20261120/RK06/simple_search_dense_finalization_v1.json",
    "rk06_independent": "audits/20261120/RK06/simple_search_dense_independent_v2.json",
    "cagfn_final": "audits/20261118/RK05/cagfn_official_smoke_finalization_v1.json",
    "id3_final": "audits/20261118/RK05/id3_official_quick_test_finalization.json",
    "ct_smoke": "audits/20261118/RK05/codontransformer_official_smoke_v1.json",
    "ct_final": "audits/20261118/RK05/codontransformer_finalization_v1.json",
    "velo_smoke": "audits/20261118/RK05/veloharmo_official_smoke_v1.json",
    "ixnos_final": "audits/20261118/RK05/ixnos_finalization_v1.json",
    "ixnos_independent": "audits/20261118/RK05/ixnos_independent_verification_v1.json",
    "rose_production": "audits/20261118/RK05/rose_official_single_checkpoint_v1.json",
    "ribo_independent": "audits/20261119/RK05/ribomimo_study_ood_independent_retrain_v1.json",
    "ribo_final": "audits/20261119/RK05/ribomimo_study_ood_finalization_v1.json",
    "rnarl_final": "audits/20261118/RK03/rnarl_finalization_recovery_v4.json",
    "cdgb_final": "audits/20261118/RK05/cdgb_source_finalization.json",
    "boel_split": "audits/20261118/RK04/sequence_ood_finalization.json",
    "mage_closure": "audits/20261120/RK03/mage_oof_comparator_closure_v2.json",
    "mordstein_recovery": "audits/20261118/RK02/mordstein_recovery_full_finalization_v1.json",
    "source_feasibility": "audits/20261120/RK03/source_feasibility_finalization_v1.json",
    "full_function": "audits/20261118/RK08/full_function_finalization_v1.json",
}


def ptr(pointer: str) -> dict:
    return {"pointer": pointer}


def const(value) -> dict:
    return {"constant": value}


def null(reason: str) -> dict:
    return {"null_reason": reason}


def sump(*pointers: str) -> dict:
    return {"sum_pointers": list(pointers)}


def row(row_id: str, method: str, task: str, scope: str, source: str | None,
        accepted_status: str | None, comparison_class: str, metrics: dict,
        status_constant: str | None = None) -> dict:
    return {
        "row_id": row_id,
        "method": method,
        "task": task,
        "scope": scope,
        "source": source,
        "status_pointer": "/status" if source else None,
        "accepted_status": accepted_status,
        "status_constant": status_constant,
        "comparison_class": comparison_class,
        "metrics": metrics,
    }


NOT_MEASURED = null("No valid measured cost for this scope; null is explicit and is not zero.")
PRETRAINED = null("Released pretrained weights were used; upstream training was not rerun.")
SHARED_SCORING = null("Shared actual-set rescoring is not attributable to this individual generator.")
INHERITED = null("Inherited actual sets were scored, but generation wall-clock was not measured in RK12/RK13.")

ROWS = [
    row("lineardesign_unique18", "LinearDesign", "accessibility/CDS multi-objective",
        "unique18; 18 records x 11 lambdas; actual sets; not dense", "rk12_final",
        "PASS_COMPLETE_RK12_UNIQUE18_LINEARDESIGN_AND_ACTUAL_SET_MATRIX", "external_actual_set", {
            "wall_clock_s": ptr("/lineardesign_generation_seconds"),
            "training_s": const(0.0),
            "generation_or_inference_s": ptr("/lineardesign_generation_seconds"),
            "scoring_s": SHARED_SCORING,
            "actual_outputs": ptr("/method_summary/lineardesign_lambda11/total_actual_outputs"),
            "legal_rate": ptr("/method_summary/lineardesign_lambda11/min_identity_rate"),
        }),
    row("ensembledesign_unique18", "EnsembleDesign", "accessibility/CDS multi-objective",
        "unique18; 18 records x 11 runs; actual sets; not dense", "rk13_final",
        "PASS_RK13_ENSEMBLEDESIGN_SEVEN_METHOD_MATRIX", "external_actual_set", {
            "wall_clock_s": ptr("/ensemble_generation_seconds"),
            "training_s": const(0.0),
            "generation_or_inference_s": ptr("/ensemble_generation_seconds"),
            "scoring_s": SHARED_SCORING,
            "actual_outputs": ptr("/method_summary/ensembledesign_11run/total_actual_outputs"),
            "legal_rate": ptr("/method_summary/ensembledesign_11run/min_identity_rate"),
        }),
]

for method, key in [
    ("codonGPT", "codongpt"),
    ("GEMORNA", "gemorna"),
    ("CAI greedy", "cai_greedy"),
    ("uniform synonymous actual-set", "uniform_synonymous"),
    ("LinearDesignScan", "lineardesign_scan"),
]:
    ROWS.append(row(
        f"inherited_{key}", method, "accessibility/CDS multi-objective",
        "RK12/RK13 frozen actual sets; inherited generation; no dense trajectory",
        "rk13_final", "PASS_RK13_ENSEMBLEDESIGN_SEVEN_METHOD_MATRIX", "external_actual_set", {
            "wall_clock_s": INHERITED,
            "training_s": NOT_MEASURED,
            "generation_or_inference_s": INHERITED,
            "scoring_s": SHARED_SCORING,
            "actual_outputs": ptr(f"/method_summary/{key}/total_actual_outputs"),
            "legal_rate": ptr(f"/method_summary/{key}/min_identity_rate"),
        }))

ROWS.extend([
    row("cagfn_official_smoke", "CAGFN", "learned synonymous generation smoke",
        "official bounded toy training and inference smoke; no main comparison", "cagfn_final",
        "PASS_RK05_CAGFN_OFFICIAL_BOUNDED_SMOKE", "official_smoke", {
            "wall_clock_s": ptr("/cost/total_wall_clock_seconds"),
            "training_s": ptr("/cost/training_seconds"),
            "generation_or_inference_s": ptr("/cost/inference_seconds"),
            "scoring_s": NOT_MEASURED,
        }),
    row("id3_official_quick_test", "ID3", "accessibility optimization",
        "one protein; 12 runs; 2 iterations; one seed; CPC trajectory defect retained", "id3_final",
        "BOUNDED_OFFICIAL_QUICK_TEST_COMPLETE_WITH_CPC_STE_TRAJECTORY_DEFECT", "official_smoke", {
            "wall_clock_s": ptr("/execution/official_total_wall_time_s"),
            "training_s": const(0.0),
            "generation_or_inference_s": ptr("/execution/official_total_wall_time_s"),
            "scoring_s": NOT_MEASURED,
            "runs": ptr("/execution/successful"),
        }),
    row("codontransformer_official_smoke", "CodonTransformer", "organism-conditioned generation",
        "official example plus C01; four GPU inferences; two unique CDS", "ct_smoke",
        "BOUNDED_OFFICIAL_EXECUTION_COMPLETE", "official_smoke", {
            "wall_clock_s": sump("/model_load_seconds", "/total_inference_seconds"),
            "training_s": PRETRAINED,
            "generation_or_inference_s": ptr("/total_inference_seconds"),
            "scoring_s": NOT_MEASURED,
            "runs": sump("/default_run_count", "/constrained_run_count"),
            "actual_outputs": ptr("/unique_sequence_count"),
        }),
    row("veloharmo_official_smoke", "VeloHARMO", "harmonization",
        "E. coli released test plus bounded GA; no five-species matrix", "velo_smoke",
        "BOUNDED_OFFICIAL_ALGORITHM_EXECUTION_COMPLETE", "official_smoke", {
            "wall_clock_s": sump("/official_velogru_test/wall_seconds", "/bounded_ga/wall_seconds"),
            "training_s": PRETRAINED,
            "generation_or_inference_s": ptr("/bounded_ga/wall_seconds"),
            "scoring_s": NOT_MEASURED,
        }),
    row("ixnos_real_prefix", "iXnos", "Ribo-seq/P-site feasibility and model smoke",
        "1,000,000-read real prefix; two epochs; not full SRR1049521 protocol", "ixnos_independent",
        "PASS", "official_smoke", {
            "wall_clock_s": ptr("/independent_process_seconds"),
            "training_s": ptr("/independent_training_seconds_including_compile"),
            "generation_or_inference_s": NOT_MEASURED,
            "scoring_s": NOT_MEASURED,
        }),
    row("rose_released_checkpoint", "ROSE", "ribosome stalling classification",
        "released-test single-checkpoint inference; Battle15 and Pop14", "rose_production",
        "PASS_COMPLETE_RELEASED_TEST_SINGLE_CHECKPOINT_INFERENCE", "official_smoke", {
            "wall_clock_s": ptr("/execution/total_seconds"),
            "training_s": PRETRAINED,
            "generation_or_inference_s": sump(
                "/studies/Battle15/timing_seconds/single_full_forward",
                "/studies/Pop14/timing_seconds/single_full_forward"),
            "scoring_s": NOT_MEASURED,
        }),
    row("ribomimo_study_ood", "RiboMIMO", "study-OOD ribosome occupancy",
        "Mohammad16 to Subtelny14; three-seed independent retraining/evaluation", "ribo_independent",
        "PASS_STUDY_OOD_PENDING_INDEPENDENT", "study_ood_cost", {
            "wall_clock_s": ptr("/execution/wall_seconds_all_seeds"),
            "training_s": sump("/runs/0/training_seconds", "/runs/1/training_seconds", "/runs/2/training_seconds"),
            "generation_or_inference_s": sump(
                "/runs/0/target_evaluation_seconds", "/runs/1/target_evaluation_seconds",
                "/runs/2/target_evaluation_seconds"),
            "scoring_s": sump(
                "/runs/0/ridge_selection_seconds", "/runs/1/ridge_selection_seconds",
                "/runs/2/ridge_selection_seconds"),
            "runs": const(3),
        }),
])

for index, (method, label) in enumerate([
    ("uniform", "uniform simple search"),
    ("hill_climbing", "hill-climbing"),
    ("mh_annealing", "MH-annealing"),
    ("areuredi_style", "AReUReDi-style"),
]):
    base = f"/claims/method_summary/{index}"
    ROWS.append(row(
        f"rk06_dense_{method}", label, "CDS proxy multi-objective simple search",
        "unique18 development; 18 records x 3 seeds; B=1..500; 54 runs; 27,000 unique scorer calls",
        "rk06_final", "FINALIZED_DEVELOPMENT_DENSE_EVIDENCE", "dense_proxy_search", {
            "wall_clock_s": ptr(base + "/sum_wall_clock_seconds"),
            "training_s": const(0.0),
            "generation_or_inference_s": ptr(base + "/sum_generation_cache_proposal_seconds"),
            "scoring_s": ptr(base + "/sum_scoring_seconds"),
            "unique_scorer_calls": ptr(base + "/sum_unique_scorer_calls"),
            "runs": ptr(base + "/n_runs"),
        }))

ROWS.extend([
    row("rnarl_availability", "RNARL", "learned synonymous generation",
        "publisher pair-table QC only; official model not reproduced", "rnarl_final",
        "PASS_BOUNDED_LINEARDESIGN_PAIR_TABLE_QC_ONLY", "availability_only", {
            "wall_clock_s": null("No valid official RNARL training/generation run; data QC time is not model cost."),
            "training_s": NOT_MEASURED,
            "generation_or_inference_s": NOT_MEASURED,
            "scoring_s": NOT_MEASURED,
            "qc_pairs": ptr("/clean_pairs"),
        }),
    row("cdgb_source_audit", "CDGB", "codon deoptimization",
        "source identity unresolved; official execution not authorized", "cdgb_final",
        "SOURCE_IDENTITY_UNRESOLVED_OFFICIAL_EXECUTION_NOT_AUTHORIZED", "availability_only", {
            "wall_clock_s": NOT_MEASURED,
            "training_s": NOT_MEASURED,
            "generation_or_inference_s": NOT_MEASURED,
            "scoring_s": NOT_MEASURED,
        }),
    row("coformer_not_run", "COformer", "codon optimization",
        "not run in the frozen A8-RK evidence; no availability audit claimed", None, None,
        "not_run", {
            "wall_clock_s": NOT_MEASURED,
            "training_s": NOT_MEASURED,
            "generation_or_inference_s": NOT_MEASURED,
            "scoring_s": NOT_MEASURED,
        }, status_constant="NOT_RUN"),
    row("charming_not_run", "CHARMING", "codon optimization",
        "not run in the frozen A8-RK evidence; no availability audit claimed", None, None,
        "not_run", {
            "wall_clock_s": NOT_MEASURED,
            "training_s": NOT_MEASURED,
            "generation_or_inference_s": NOT_MEASURED,
            "scoring_s": NOT_MEASURED,
        }, status_constant="NOT_RUN"),
])


def check(check_id: str, source: str, pointer: str, expected, category: str = "G0") -> dict:
    return {"check_id": check_id, "category": category, "source": source,
            "pointer": pointer, "operator": "eq", "expected": expected}


GATE_CHECKS = [
    check("boel_split_reliable", "boel_split", "/status", "PASS"),
    check("mage_oof_technical_pass", "mage_closure", "/overall_pass", True),
    check("mordstein_full_recovery_pass", "mordstein_recovery", "/status", "PASS"),
    check("rnarl_full_pair_table_qc", "rnarl_final", "/status", "PASS_BOUNDED_LINEARDESIGN_PAIR_TABLE_QC_ONLY"),
    check("rnarl_21_files", "rnarl_final", "/raw_files", 21),
    check("lineardesign_reproduced", "rk12_final", "/status", "PASS_COMPLETE_RK12_UNIQUE18_LINEARDESIGN_AND_ACTUAL_SET_MATRIX"),
    check("ensembledesign_reproduced", "rk13_final", "/status", "PASS_RK13_ENSEMBLEDESIGN_SEVEN_METHOD_MATRIX"),
    check("codontransformer_reproduced", "ct_final", "/status", "CLOSED_BOUNDED_OFFICIAL_SMOKE"),
    check("cagfn_reproduced", "cagfn_final", "/status", "PASS_RK05_CAGFN_OFFICIAL_BOUNDED_SMOKE"),
    check("dense_evaluator_finalized", "rk06_final", "/status", "FINALIZED_DEVELOPMENT_DENSE_EVIDENCE"),
    check("dense_independent_pass", "rk06_independent", "/status", "INDEPENDENT_PASS"),
    check("actual_set_independent_pass", "rk12_independent", "/status", "PASS"),
    check("raw_read_psite_feasibility_bounded", "ixnos_final", "/status", "CLOSED_BOUNDED_OFFICIAL_SMOKE"),
    check("utr_source_feasibility_metadata", "source_feasibility", "/status", "FINALIZED_SOURCE_FEASIBILITY_METADATA_ONLY"),
    check("ribomimo_study_ood_closed", "ribo_final", "/status", "PASS_RK05_RIBOMIMO_STUDY_OOD"),
    check("full_function_technical_pass", "full_function", "/status", "PASS", "BOUNDARY"),
    check("rk_g1_remains_false", "full_function", "/rk_g1_pass", False, "BOUNDARY"),
    check("mage_mechanism_gate_remains_false", "mage_closure", "/scientific_gate_pass", False, "BOUNDARY"),
    check("rk06_scientific_gate_remains_false", "rk06_final", "/claims/scientific_gate_passed", False, "BOUNDARY"),
    check("rk06_rk_g1_remains_open", "rk06_final", "/claims/rk_g1_closed", False, "BOUNDARY"),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build(root: Path) -> dict:
    sources = {}
    for alias, relative in SOURCES.items():
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        sources[alias] = {"path": relative, "sha256": sha256(path)}
    return {
        "schema_version": "a8-g0-closeout-protocol-v2",
        "protocol_id": "CF-A8-RK06-G0-CLOSEOUT-V2",
        "evidence_baseline_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "sources": sources,
        "cost_policy": {
            "unit": "seconds unless the metric name states calls/runs/rate",
            "null_policy": "null means unavailable or not attributable, never zero",
            "aggregation": "do not sum or rank across mixed hardware, tasks, actual-set, dense and smoke scopes",
            "time_matched": False,
            "external_dense_complete": False,
            "complete_sota": False,
        },
        "cost_rows": ROWS,
        "gate_checks": GATE_CHECKS,
        "g0_pass_status": "PASS_BOUNDED_DATA_BASELINE_EVALUATION_READY",
        "rk03_remaining_status": "FEASIBILITY_CLOSED_NOT_FULL_REMAP",
        "boundaries": {
            "rk_g1_passed": False,
            "generator_training_authorized": False,
            "time_matched_complete": False,
            "external_dense_complete": False,
            "complete_sota": False,
            "full_utr_cds_remap_complete": False,
            "five_species_veloharmo_complete": False,
            "rnarl_official_model_reproduced": False,
            "functional_untouched_evaluated": False,
            "wet_lab_validation_complete": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.root / "configs/a8_g0_closeout_protocol_v2.json"
    protocol = build(args.root.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(protocol, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output), "sha256": sha256(output),
                      "sources": len(protocol["sources"]), "cost_rows": len(ROWS),
                      "gate_checks": len(GATE_CHECKS)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
