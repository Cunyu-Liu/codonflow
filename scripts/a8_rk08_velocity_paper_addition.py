#!/usr/bin/env python3
"""Append the independently verified RK08 velocity-proxy result to A8 v11."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_json(path: Path, value: dict) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    parser.add_argument("--work-dir", type=Path, default=Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk08/velocity_proxy_v1/paper_v12"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    paper_path = repo / "paper/CodonFlow_preprint_A8.md"
    audit_path = repo / "paper/a8_rk_paper_sync_audit.json"
    base_audit = load(audit_path)
    base_audit_sha256 = sha256(audit_path)
    pre_velocity_paper_sha256 = sha256(paper_path)
    if base_audit["schema_version"] != "a8-rk-paper-sync-v11" or pre_velocity_paper_sha256 != "36e59a069cf978d21c3231a34d26c729e6637f00c4a326cd5e3c79c0d369cac8":
        raise RuntimeError("The known pre-velocity A8 state (including the RK08 full-function addition) is not current")
    if sha256(repo / "paper/CodonFlow_preprint_A7.md") != "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423":
        raise RuntimeError("A7 template changed")

    root = repo / "audits/20261118/RK08"
    paths = {
        "rk08_velocity_data": root / "velocity_data_v1.json",
        "rk08_velocity_protocol": repo / "configs/a8_rk08_velocity_v1.json",
        "rk08_velocity_production": root / "velocity_run_summary_v1.json",
        "rk08_velocity_retrain": root / "velocity_retrain_summary_v1.json",
        "rk08_velocity_independent": root / "velocity_verification_v1.json",
        "rk08_velocity_finalization": root / "velocity_finalization_v1.json",
    }
    data = load(paths["rk08_velocity_data"])
    run = load(paths["rk08_velocity_production"])
    retrain = load(paths["rk08_velocity_retrain"])
    independent = load(paths["rk08_velocity_independent"])
    finalization = load(paths["rk08_velocity_finalization"])
    if run["status"] != "PASS_PENDING_INDEPENDENT_VERIFICATION":
        raise RuntimeError("Unexpected production status")
    if run["velocity_mechanism_pass"] or independent["velocity_mechanism_pass"] or finalization["velocity_mechanism_pass"]:
        raise RuntimeError("The frozen primary result is negative; refusing a positive-gate manuscript")
    if independent["status"] != "PASS" or independent["failures"]:
        raise RuntimeError("Independent velocity verification is not clean")
    if finalization["status"] != "PASS" or finalization["checks_passed"] != finalization["checks_total"]:
        raise RuntimeError("Velocity finalization is not clean")
    if run["hashes"]["checkpoint_sha256"] != retrain["hashes"]["checkpoint_sha256"] or run["hashes"]["predictions_sha256"] != retrain["hashes"]["predictions_sha256"]:
        raise RuntimeError("Production and retrain hashes differ")

    args.work_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir = args.work_dir / "pre_velocity_snapshot"
    snapshot_dir.mkdir(exist_ok=False)
    snapshot_paper = snapshot_dir / "CodonFlow_preprint_A8_pre_velocity.md"
    shutil.copy2(paper_path, snapshot_paper)
    original_snapshot_audit = snapshot_dir / "a8_rk_paper_sync_audit_v11_original.json"
    shutil.copy2(audit_path, original_snapshot_audit)
    snapshot_audit_data = dict(base_audit)
    snapshot_audit_data["output"] = str(snapshot_paper)
    snapshot_audit_data["output_sha256"] = sha256(snapshot_paper)
    snapshot_audit_data["snapshot_note"] = "Actual pre-velocity manuscript including the pre-existing RK08 full-function addition; original v11 audit is preserved separately."
    snapshot_audit = snapshot_dir / "a8_rk_paper_sync_audit_pre_velocity_snapshot.json"
    atomic_json(snapshot_audit, snapshot_audit_data)

    labels = [
        ("Mohammad16 dev", "dev"),
        ("Mohammad16 test", "test"),
        ("Mohammad19-1 study-OOD", "study_ood:Mohammad19-1"),
        ("Mohammad19-2 study-OOD", "study_ood:Mohammad19-2"),
        ("Subtelny14 study/species-OOD (primary)", "study_ood:Subtelny14"),
    ]
    rows = []
    for label, key in labels:
        metric = run["metrics"][key]
        model = metric["ribokinetic_velocity"]
        ridge = metric["ridge_codon_position_length"]
        rows.append(
            f"| {label} | {model['n_transcripts']:,} | {model['transcript_balanced_mse']:.6f} | {ridge['transcript_balanced_mse']:.6f} | "
            f"{model['mean_transcript_pearson']:.6f} | {ridge['mean_transcript_pearson']:.6f} |"
        )
    mse = next(item for item in run["primary_comparisons"] if item["metric"] == "transcript_balanced_mse")
    pearson = next(item for item in run["primary_comparisons"] if item["metric"] == "mean_transcript_pearson")
    counts = data["counts"]
    records = data["records_by_split_study"]
    addition = f"""### 6.9 Occupancy-derived velocity proxy: in-study fit did not transfer to Subtelny14

To test the velocity channel with direct supervision rather than function-only pooling, we used the frozen RiboMIMO author-processed normalized ribosome-density matrices. The target was `-log1p(normalized density)`, an **occupancy-derived elongation-speed proxy**, not a physical velocity measurement. The first codon and stop codon were masked. Of {counts['input_records']:,} clean records, {counts['excluded_over_max_codons']:,} exceeded the frozen 1,002-codon limit, leaving {counts['retained_records']:,}. Mohammad16 was split by deterministic record-ID hash into {records['train|Mohammad16']:,}/{records['dev|Mohammad16']:,}/{records['test|Mohammad16']:,} train/dev/test transcripts. Subtelny14 contributed {records['study_ood|Subtelny14']:,} transcripts and had zero exact CDS overlap with any Mohammad16 split; this is exact-CDS-disjoint study/species OOD, not homology-cluster OOD.

The {run['training']['parameter_count']:,}-parameter RiboKinetic model and the codon/relative-position/length ridge used identical observed positions. Checkpoint selection used only Mohammad16 development transcript-balanced MSE and selected epoch {run['selected_epoch']}. Test and all study-OOD partitions were excluded from fitting and selection.

| Partition | Transcripts | RiboKinetic TB-MSE | Ridge TB-MSE | RiboKinetic mean within-transcript r | Ridge mean within-transcript r |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

On the preregistered Subtelny14 primary endpoint, the model was worse than ridge on both criteria. The model-minus-ridge TB-MSE difference was **{mse['point_delta_model_minus_ridge']:+.6f}** (95% CI [{mse['ci95_low']:+.6f}, {mse['ci95_high']:+.6f}]), and the mean within-transcript Pearson difference was **{pearson['point_delta_model_minus_ridge']:+.6f}** (95% CI [{pearson['ci95_low']:+.6f}, {pearson['ci95_high']:+.6f}]). Both empirical Holm-adjusted p-values were 0 across {mse['bootstrap_valid']:,} transcript-bootstrap resamples. Therefore `velocity_mechanism_pass=false`.

The within-study Mohammad16 test improvement is descriptive and does not rescue the primary endpoint: model/ridge TB-MSE was {run['metrics']['test']['ribokinetic_velocity']['transcript_balanced_mse']:.6f}/{run['metrics']['test']['ridge_codon_position_length']['transcript_balanced_mse']:.6f}, and mean within-transcript Pearson was {run['metrics']['test']['ribokinetic_velocity']['mean_transcript_pearson']:.6f}/{run['metrics']['test']['ridge_codon_position_length']['mean_transcript_pearson']:.6f}. On Mohammad19-1/2, the model had higher mean within-transcript Pearson but worse TB-MSE than ridge, so these overlapping-CDS study transfers are not robust wins. The primary negative result is retained without post-hoc model tuning.

Two complete training runs produced bitwise-identical checkpoints and prediction files. Independent raw-source verification passed **{independent['checks_passed']}/{independent['checks_total']} checks**, and finalization passed **{finalization['checks_passed']}/{finalization['checks_total']} checks**. This closes reproducibility of a negative velocity-proxy experiment only. It does not close RK-G1, functional transfer, cross-head mechanism consistency, physical velocity validation, homology OOD, generator readiness, SOTA or wet-lab validation; expensive generation remains unauthorized.
"""
    text = paper_path.read_text(encoding="utf-8")
    old = "Velocity OOD and generator readiness remain unevaluated, and expensive generation training remains unauthorized."
    new = "An independent occupancy-derived velocity-proxy analysis is reported in Section 6.9; it did not pass its preregistered Subtelny14 transfer gate. Neither experiment authorizes expensive generation training."
    if text.count(old) != 1:
        raise RuntimeError("Expected RK08 velocity-pending sentence is absent or non-unique")
    text = text.replace(old, new, 1)
    marker = "### 6.9 Independent functional validation"
    if text.count(marker) != 1 or "### 6.9 Occupancy-derived velocity proxy" in text:
        raise RuntimeError("Unexpected section state")
    text = text.replace(marker, addition + "\n### 6.10 Independent functional validation", 1)
    anchor = next(line for line in text.splitlines() if line.startswith("| RK08 no-channel checkpoint |"))
    evidence = [f"| {key} | `{sha256(path)}` |" for key, path in paths.items()]
    text = text.replace(anchor, anchor + "\n" + "\n".join(evidence), 1)
    atomic_text(paper_path, text)

    audit = dict(base_audit)
    audit["schema_version"] = "a8-rk-paper-sync-v12"
    audit["base_v11_audit_sha256"] = base_audit_sha256
    audit["base_v11_declared_output_sha256"] = base_audit["output_sha256"]
    audit["base_pre_velocity_paper_sha256"] = pre_velocity_paper_sha256
    audit["pre_velocity_snapshot"] = {
        "paper": str(snapshot_paper), "paper_sha256": sha256(snapshot_paper),
        "audit": str(snapshot_audit), "audit_sha256": sha256(snapshot_audit),
        "original_audit": str(original_snapshot_audit), "original_audit_sha256": sha256(original_snapshot_audit),
    }
    audit["output_sha256"] = sha256(paper_path)
    audit["source_paths"] = dict(base_audit["source_paths"]) | {name: str(path) for name, path in paths.items()}
    audit["source_sha256"] = dict(base_audit["source_sha256"]) | {name: sha256(path) for name, path in paths.items()}
    audit["generated_sections"] = list(base_audit["generated_sections"]) + ["6.9 RK08 occupancy-derived velocity proxy OOD", "8.1 RK08 velocity evidence anchors"]
    audit["pending_preserved"] = list(base_audit["pending_preserved"]) + ["physical velocity assays, functional velocity transfer and homology-cluster velocity OOD"]
    audit["scientific_scope"] = dict(base_audit["scientific_scope"])
    audit["scientific_scope"]["rk08_velocity"] = "Reproducible negative occupancy-derived velocity-proxy experiment: within-study gains did not transfer to the preregistered Subtelny14 primary endpoint; ridge was superior on both primary criteria; no RK-G1, functional transfer, physical velocity, homology OOD or generator claim"
    atomic_json(audit_path, audit)
    print(json.dumps({"status": audit["status"], "schema": audit["schema_version"], "paper_sha256": audit["output_sha256"], "audit_sha256": sha256(audit_path), "velocity_mechanism_pass": False}, indent=2))


if __name__ == "__main__":
    main()
