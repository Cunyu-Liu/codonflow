#!/usr/bin/env python3
"""Append the independently verified Mohammad16 full-CV result to A8 v10."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    paper_path = repo / "paper/CodonFlow_preprint_A8.md"
    audit_path = repo / "paper/a8_rk_paper_sync_audit.json"
    base_audit = load(audit_path)
    base_audit_sha256 = sha256(audit_path)
    if base_audit["schema_version"] != "a8-rk-paper-sync-v10":
        raise RuntimeError("Run the preserved v10 paper sync before this v11 addition")
    if sha256(paper_path) != base_audit["output_sha256"]:
        raise RuntimeError("Current A8 paper does not match the v10 audit")
    if sha256(repo / "paper/CodonFlow_preprint_A7.md") != "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423":
        raise RuntimeError("A7 template changed")

    root = repo / "audits/20261118/RK05"
    paths = {
        "ribomimo_full_preflight": root / "ribomimo_full_loader_preflight_v1.json",
        "ribomimo_full_protocol": root / "ribomimo_full_mohammad16_protocol_v2.json",
        "ribomimo_full_failure_v1": root / "ribomimo_full_mohammad16_v1_failed.json",
        "ribomimo_full_production": root / "ribomimo_full_mohammad16_v2.json",
        "ribomimo_full_retrain": root / "ribomimo_full_mohammad16_retrain_v1.json",
        "ribomimo_full_independent": root / "ribomimo_full_mohammad16_independent_v1.json",
        "ribomimo_full_finalization": root / "ribomimo_full_mohammad16_finalization_v1.json",
    }
    data = {name: load(path) for name, path in paths.items()}
    preflight = data["ribomimo_full_preflight"]
    protocol = data["ribomimo_full_protocol"]
    failure = data["ribomimo_full_failure_v1"]
    production = data["ribomimo_full_production"]
    retrain = data["ribomimo_full_retrain"]
    independent = data["ribomimo_full_independent"]
    finalization = data["ribomimo_full_finalization"]
    if preflight["status"] != "PASS" or production["status"] != retrain["status"] or not production["status"].startswith("PASS_COMPLETE_OFFICIAL_1X10FOLD_MAX100"):
        raise RuntimeError("Full RiboMIMO production evidence is incomplete")
    if independent["status"] != "PASS" or independent["checks_total"] != independent["checks_passed"]:
        raise RuntimeError("Independent full inference verification is incomplete")
    if finalization["status"] != "PASS_COMPLETE_WITH_INDEPENDENT_RETRAIN_AND_INFERENCE" or finalization["checks_total"] != finalization["checks_passed"] or not finalization["all_checkpoints_bitwise_equal"]:
        raise RuntimeError("Full finalization is incomplete")
    if failure["status"] != "FAIL_OFFICIAL_TRAINING":
        raise RuntimeError("Retained v1 failure identity changed")

    aggregate = production["official_result"]["aggregate"]
    baseline = independent["constant_train_mean_baseline_aggregate"]
    eligible_total = sum(row["eligible_official_coverage_gt_0.6"] for row in preflight["datasets"].values())
    fold_rows = "\n".join(
        f"| {row['fold'] + 1} | {row['best_epoch']} | {row['test_at_best_validation']['r2']:.6f} | {row['test_at_best_validation']['mse']:.6f} | {row['test_at_best_validation']['pearson']:.6f} |"
        for row in production["official_result"]["folds"]
    )
    addition = f"""**RiboMIMO full Mohammad16 official cross-validation.** The four author-processed matrices first passed the official-loader preflight with **{eligible_total:,} eligible records**; this loader count is distinct from the RK03 clean-QC total of 8,109 and the two QC conventions are not interchanged. For Mohammad16, the complete matrix contained **{production['matrix']['raw_records']:,} raw / {production['matrix']['official_loader_eligible_records']:,} eligible genes**. The fixed official commit `{production['source']['commit']}` executed **one repeat × ten folds, maximum 100 epochs, early stopping 5, batch size 16, seed 1234, and nucleotide+amino-acid features** on an NVIDIA GeForce RTX 5090. Seven runtime-only compatibility replacements preserve ragged arrays, numeric padding dtype and the modern PyTorch CPU-length requirement; model, optimizer, split and training logic are unchanged. The failed first run caused by CUDA `pack_padded_sequence` lengths is retained as `{failure['status']}`.

| Fold | Best-validation epoch | Test R² | Test MSE | Test Pearson |
| --- | ---: | ---: | ---: | ---: |
{fold_rows}

Across the ten best-validation checkpoint test folds, R² was **{aggregate['r2_mean']:.6f} ± {aggregate['r2_std']:.6f}**, MSE was **{aggregate['mse_mean']:.6f} ± {aggregate['mse_std']:.6f}**, and Pearson was **{aggregate['pearson_mean']:.6f} ± {aggregate['pearson_std']:.6f}** (mean ± population SD). An independent post-hoc constant predictor using only each training fold's mean density gave R² **{baseline['r2_mean']:.6f} ± {baseline['r2_std']:.6f}** and MSE **{baseline['mse_mean']:.6f} ± {baseline['mse_std']:.6f}**; this is a train-only reference, not an official output or a unified baseline matrix. Every eligible gene occurred in exactly one test fold. A second complete deterministic 10-fold training run produced bitwise-identical checkpoint tensors for all ten folds and identical six-decimal metrics. Independent two-pass checkpoint inference passed **{independent['checks_passed']}/{independent['checks_total']} checks**, finalization passed **{finalization['checks_passed']}/{finalization['checks_total']} checks**, and unit tests passed **10/10**. This closes only the official random-gene CV protocol on Mohammad16. Full training on Subtelny14, Mohammad19-1 and Mohammad19-2, homology/protein/study/functional OOD, publication-metric reproduction, the unified-cost baseline matrix, CodonFlow-RK comparison and SOTA assessment remain pending."""

    text = paper_path.read_text(encoding="utf-8")
    if "RiboMIMO full Mohammad16 official cross-validation" in text:
        raise RuntimeError("Full Mohammad16 section already exists; refusing duplicate insertion")
    marker = "**iXnos bounded official prefix-read training.**"
    text = text.replace(marker, addition + "\n\n" + marker, 1)

    evidence_lines = [
        ("RiboMIMO full four-matrix loader preflight", "ribomimo_full_preflight"),
        ("RiboMIMO full Mohammad16 frozen protocol v2", "ribomimo_full_protocol"),
        ("RiboMIMO full Mohammad16 retained v1 failure", "ribomimo_full_failure_v1"),
        ("RiboMIMO full Mohammad16 production", "ribomimo_full_production"),
        ("RiboMIMO full Mohammad16 deterministic retrain", "ribomimo_full_retrain"),
        ("RiboMIMO full Mohammad16 independent inference", "ribomimo_full_independent"),
        ("RiboMIMO full Mohammad16 finalization", "ribomimo_full_finalization"),
    ]
    anchor = next(line for line in text.splitlines() if line.startswith("| RiboMIMO bounded finalization |"))
    extra = "\n".join(f"| {label} | `{sha256(paths[key])}` |" for label, key in evidence_lines)
    text = text.replace(anchor, anchor + "\n" + extra, 1)
    atomic_write(paper_path, text)

    audit = dict(base_audit)
    audit["schema_version"] = "a8-rk-paper-sync-v11"
    audit["base_v10_audit_sha256"] = base_audit_sha256
    audit["output_sha256"] = sha256(paper_path)
    audit["source_paths"] = dict(base_audit["source_paths"]) | {name: str(path) for name, path in paths.items()}
    audit["source_sha256"] = dict(base_audit["source_sha256"]) | {name: sha256(path) for name, path in paths.items()}
    audit["generated_sections"] = list(base_audit["generated_sections"]) + ["6.5 RiboMIMO full Mohammad16", "8.1 full Mohammad16 evidence anchors"]
    audit["pending_preserved"] = ["RiboMIMO Subtelny14/Mohammad19-1/Mohammad19-2 full protocols and homology/protein/study/functional OOD" if item.startswith("RiboMIMO full 10-fold") else item for item in base_audit["pending_preserved"]]
    audit["scientific_scope"] = dict(base_audit["scientific_scope"])
    audit["scientific_scope"]["ribomimo_full_mohammad16"] = "Complete official 1x10-fold/max100/early-stop5 random-gene CV on all 1,179 eligible Mohammad16 genes, executed twice with bitwise-identical checkpoints and independently recomputed predictions; other three datasets, OOD, publication-metric reproduction, main matrix and SOTA open"
    audit["scientific_scope"]["ribomimo_official"] = "Bounded 20-gene two-fold two-epoch official training retained as a diagnostic; full Mohammad16 is reported separately; other datasets, OOD, main matrix and SOTA open"
    atomic_write(audit_path, json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": audit["status"], "schema": audit["schema_version"], "paper_sha256": audit["output_sha256"], "audit_sha256": sha256(audit_path), "aggregate": aggregate}, indent=2))


if __name__ == "__main__":
    main()
