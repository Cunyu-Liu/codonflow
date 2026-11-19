#!/usr/bin/env python3
"""Independently verify the A8 v12 velocity-proxy manuscript addition."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    parser.add_argument("--output", type=Path, default=Path("/home/codonflow-a8-rk/paper/a8_rk08_velocity_paper_verification.json"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    paper_path = repo / "paper/CodonFlow_preprint_A8.md"
    audit_path = repo / "paper/a8_rk_paper_sync_audit.json"
    text = paper_path.read_text(encoding="utf-8")
    audit = load(audit_path)
    root = repo / "audits/20261118/RK08"
    data = load(root / "velocity_data_v1.json")
    run = load(root / "velocity_run_summary_v1.json")
    retrain = load(root / "velocity_retrain_summary_v1.json")
    independent = load(root / "velocity_verification_v1.json")
    finalization = load(root / "velocity_finalization_v1.json")
    section = text.split("### 6.9 Occupancy-derived velocity proxy", 1)[1].split("### 6.10 Independent functional validation", 1)[0]
    counts = data["counts"]
    records = data["records_by_split_study"]
    mse = next(item for item in run["primary_comparisons"] if item["metric"] == "transcript_balanced_mse")
    pearson = next(item for item in run["primary_comparisons"] if item["metric"] == "mean_transcript_pearson")
    expected_source_keys = {
        "rk08_velocity_data", "rk08_velocity_protocol", "rk08_velocity_production",
        "rk08_velocity_retrain", "rk08_velocity_independent", "rk08_velocity_finalization",
    }
    checks = {
        "schema_v12": audit["schema_version"] == "a8-rk-paper-sync-v12",
        "output_hash": audit["output_sha256"] == sha256(paper_path),
        "a7_unchanged": sha256(repo / "paper/CodonFlow_preprint_A7.md") == "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423",
        "working_manuscript_not_submittable": audit["status"] == "PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE" and audit["scientific_scope"]["submittable"] is False,
        "snapshot_paper_hash": audit["pre_velocity_snapshot"]["paper_sha256"] == sha256(Path(audit["pre_velocity_snapshot"]["paper"])),
        "snapshot_audit_hash": audit["pre_velocity_snapshot"]["audit_sha256"] == sha256(Path(audit["pre_velocity_snapshot"]["audit"])),
        "pre_velocity_hash_chain": audit["base_pre_velocity_paper_sha256"] == audit["pre_velocity_snapshot"]["paper_sha256"] == "36e59a069cf978d21c3231a34d26c729e6637f00c4a326cd5e3c79c0d369cac8",
        "source_key_set": expected_source_keys.issubset(audit["source_paths"]) and expected_source_keys.issubset(audit["source_sha256"]),
        "source_hashes": all(sha256(Path(audit["source_paths"][key])) == audit["source_sha256"][key] for key in expected_source_keys),
        "evidence_anchor_hashes": all(f"| {key} | `{audit['source_sha256'][key]}` |" in text for key in expected_source_keys),
        "independent_pass": independent["status"] == "PASS" and not independent["failures"],
        "finalization_pass": finalization["status"] == "PASS" and finalization["checks_passed"] == finalization["checks_total"],
        "negative_gate_consistent": not run["velocity_mechanism_pass"] and not independent["velocity_mechanism_pass"] and not finalization["velocity_mechanism_pass"],
        "no_rk_g1_or_generator_claim": not run["rk_g1_pass"] and not finalization["rk_g1_pass"] and not finalization["expensive_generation_authorized"],
        "retrain_checkpoint_identical": run["hashes"]["checkpoint_sha256"] == retrain["hashes"]["checkpoint_sha256"],
        "retrain_predictions_identical": run["hashes"]["predictions_sha256"] == retrain["hashes"]["predictions_sha256"],
        "data_counts_rendered": all(f"{value:,}" in section for value in [counts["input_records"], counts["excluded_over_max_codons"], counts["retained_records"], records["train|Mohammad16"], records["dev|Mohammad16"], records["test|Mohammad16"], records["study_ood|Subtelny14"]]),
        "model_selection_rendered": f"{run['training']['parameter_count']:,}-parameter" in section and f"selected epoch {run['selected_epoch']}" in section,
        "primary_mse_rendered": f"{mse['point_delta_model_minus_ridge']:+.6f}" in section and f"{mse['ci95_low']:+.6f}" in section and f"{mse['ci95_high']:+.6f}" in section,
        "primary_pearson_rendered": f"{pearson['point_delta_model_minus_ridge']:+.6f}" in section and f"{pearson['ci95_low']:+.6f}" in section and f"{pearson['ci95_high']:+.6f}" in section,
        "bootstrap_count_rendered": f"{mse['bootstrap_valid']:,} transcript-bootstrap resamples" in section,
        "negative_gate_stated": "`velocity_mechanism_pass=false`" in section and "model was worse than ridge on both criteria" in section,
        "within_study_not_overclaimed": "does not rescue the primary endpoint" in section and "not robust wins" in section,
        "proxy_boundary": "occupancy-derived elongation-speed proxy" in section and "not a physical velocity measurement" in section,
        "ood_boundary": "not homology-cluster OOD" in section and "zero exact CDS overlap" in section,
        "verification_counts_rendered": f"{independent['checks_passed']}/{independent['checks_total']} checks" in section and f"{finalization['checks_passed']}/{finalization['checks_total']} checks" in section,
        "all_partition_rows_rendered": all(label in section for label in ["Mohammad16 dev", "Mohammad16 test", "Mohammad19-1 study-OOD", "Mohammad19-2 study-OOD", "Subtelny14 study/species-OOD (primary)"]),
        "old_pending_sentence_removed": "Velocity OOD and generator readiness remain unevaluated" not in text,
        "next_section_renumbered": text.count("### 6.10 Independent functional validation") == 1,
        "scope_explicit": all(phrase in section for phrase in ["does not close RK-G1", "functional transfer", "cross-head mechanism consistency", "expensive generation remains unauthorized"]),
    }
    failures = [name for name, passed in checks.items() if not passed]
    report = {
        "status": "PASS" if not failures else "FAIL",
        "checks_passed": len(checks) - len(failures),
        "checks_total": len(checks),
        "checks": checks,
        "failures": failures,
        "paper_sha256": sha256(paper_path),
        "audit_sha256": sha256(audit_path),
        "velocity_mechanism_pass": False,
        "submittable": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
