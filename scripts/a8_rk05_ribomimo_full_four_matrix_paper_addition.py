#!/usr/bin/env python3
"""Advance A8 from v14 to the independently verified four-matrix RiboMIMO result."""
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
    parser.add_argument("--work-dir", type=Path, default=Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_full_094c_v1/paper_v15"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    paper_path = repo / "paper/CodonFlow_preprint_A8.md"
    audit_path = repo / "paper/a8_rk_paper_sync_audit.json"
    base_audit = load(audit_path)
    base_audit_sha256 = sha256(audit_path)
    if base_audit["schema_version"] != "a8-rk-paper-sync-v14" or base_audit["output_sha256"] != sha256(paper_path):
        raise RuntimeError("A8 v14 is not the current verified starting state")
    if sha256(repo / "paper/CodonFlow_preprint_A7.md") != "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423":
        raise RuntimeError("A7 template changed")
    args.work_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir = args.work_dir / "v14_snapshot"
    snapshot_dir.mkdir(exist_ok=False)
    snapshot_paper = snapshot_dir / "CodonFlow_preprint_A8_v14.md"
    shutil.copy2(paper_path, snapshot_paper)
    original_snapshot_audit = snapshot_dir / "a8_rk_paper_sync_audit_v14_original.json"
    shutil.copy2(audit_path, original_snapshot_audit)
    snapshot_audit_data = dict(base_audit)
    snapshot_audit_data["output"] = str(snapshot_paper)
    snapshot_audit = snapshot_dir / "a8_rk_paper_sync_audit_v14_snapshot.json"
    atomic_json(snapshot_audit, snapshot_audit_data)

    root = repo / "audits/20261118/RK05"
    summary_path = root / "ribomimo_full_four_matrix_summary_v1.json"
    summary_verification_path = root / "ribomimo_full_four_matrix_summary_verification_v1.json"
    summary = load(summary_path)
    summary_verification = load(summary_verification_path)
    if summary["status"] != "PASS_COMPLETE_FOUR_MATRIX_OFFICIAL_CV" or summary_verification["status"] != "PASS" or summary_verification["checks_total"] != summary_verification["checks_passed"]:
        raise RuntimeError("Four-matrix summary is not fully verified")

    paths = {}
    for slug in ("subtelny14", "mohammad19_1", "mohammad19_2"):
        for kind in ("protocol", "production", "retrain", "independent", "finalization"):
            filename_kind = {"protocol": "protocol_v1", "production": "v1", "retrain": "retrain_v1", "independent": "independent_v1", "finalization": "finalization_v1"}[kind]
            paths[f"ribomimo_full_{slug}_{kind}"] = root / f"ribomimo_full_{slug}_{filename_kind}.json"
    paths["ribomimo_full_four_matrix_summary"] = summary_path
    paths["ribomimo_full_four_matrix_summary_verification"] = summary_verification_path

    table_rows = []
    for dataset in ("Subtelny14", "Mohammad19-1", "Mohammad19-2", "Mohammad16"):
        row = summary["datasets"][dataset]
        agg = row["aggregate"]
        base = row["constant_train_mean_baseline_aggregate"]
        table_rows.append(
            f"| {dataset} | {row['raw_records']:,} / {row['eligible_genes']:,} | {agg['r2_mean']:.6f} ± {agg['r2_std']:.6f} | {agg['mse_mean']:.6f} ± {agg['mse_std']:.6f} | {agg['pearson_mean']:.6f} ± {agg['pearson_std']:.6f} | {base['r2_mean']:.6f} / {base['mse_mean']:.6f} |"
        )
    addition = f"""**RiboMIMO complete four-matrix official cross-validation.** All four author-processed matrices have now completed the same official **1×10-fold / maximum 100 epochs / early-stop 5** random-gene protocol. The combined input is **{summary['total_raw_records']:,} raw records / {summary['total_official_loader_eligible_genes']:,} official-loader-eligible genes**, with **{summary['total_valid_masked_test_codons']:,} valid masked test codons**. The eligible count remains distinct from RK03 clean QC=8,109.

| Dataset | Raw / eligible genes | R² mean ± SD | MSE mean ± SD | Pearson mean ± SD | Train-mean baseline R² / MSE |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(table_rows)}

Each dataset was trained twice from the frozen protocol: **8 complete training runs, 40 bitwise-identical fold-checkpoint pairs, and 80 independent forward passes**. The independent four-matrix summary passed **{summary_verification['checks_passed']}/{summary_verification['checks_total']} checks**. Train-mean baselines use training-fold density only and are post-hoc references, not a unified strong-baseline matrix. This closes official random-gene CV on the four released matrices only; homology/protein/study/functional OOD, publication-metric reproduction, unified-cost baseline ranking, CodonFlow-RK, SOTA and wet-lab validation remain open."""

    text = paper_path.read_text(encoding="utf-8")
    old_pending = "Full training on Subtelny14, Mohammad19-1 and Mohammad19-2, homology/protein/study/functional OOD, publication-metric reproduction, the unified-cost baseline matrix, CodonFlow-RK comparison and SOTA assessment remain pending."
    new_pending = "The three remaining matrices are completed in the four-matrix extension below. Homology/protein/study/functional OOD, publication-metric reproduction, the unified-cost baseline matrix, CodonFlow-RK comparison and SOTA assessment remain pending."
    if text.count(old_pending) != 1:
        raise RuntimeError("Expected v14 pending sentence is absent or non-unique")
    text = text.replace(old_pending, new_pending, 1)
    if "RiboMIMO complete four-matrix official cross-validation" in text:
        raise RuntimeError("Four-matrix section already exists")
    marker = "**iXnos bounded official prefix-read training.**"
    text = text.replace(marker, addition + "\n\n" + marker, 1)

    anchor = next(line for line in text.splitlines() if line.startswith("| RiboMIMO full Mohammad16 finalization |"))
    labels = {
        "protocol": "frozen protocol", "production": "production", "retrain": "deterministic retrain",
        "independent": "independent inference", "finalization": "finalization",
    }
    evidence = []
    for slug in ("subtelny14", "mohammad19_1", "mohammad19_2"):
        for kind in ("protocol", "production", "retrain", "independent", "finalization"):
            key = f"ribomimo_full_{slug}_{kind}"
            evidence.append(f"| RiboMIMO full {slug} {labels[kind]} | `{sha256(paths[key])}` |")
    evidence.append(f"| RiboMIMO full four-matrix summary | `{sha256(summary_path)}` |")
    evidence.append(f"| RiboMIMO full four-matrix summary verification | `{sha256(summary_verification_path)}` |")
    text = text.replace(anchor, anchor + "\n" + "\n".join(evidence), 1)
    atomic_text(paper_path, text)

    audit = dict(base_audit)
    audit["schema_version"] = "a8-rk-paper-sync-v15"
    audit["base_v14_audit_sha256"] = base_audit_sha256
    audit["v14_snapshot"] = {
        "paper": str(snapshot_paper), "paper_sha256": sha256(snapshot_paper),
        "audit": str(snapshot_audit), "audit_sha256": sha256(snapshot_audit),
        "original_audit": str(original_snapshot_audit), "original_audit_sha256": sha256(original_snapshot_audit),
    }
    audit["output_sha256"] = sha256(paper_path)
    audit["source_paths"] = dict(base_audit["source_paths"]) | {name: str(path) for name, path in paths.items()}
    audit["source_sha256"] = dict(base_audit["source_sha256"]) | {name: sha256(path) for name, path in paths.items()}
    audit["generated_sections"] = list(base_audit["generated_sections"]) + ["6.6 RiboMIMO complete four-matrix official CV", "8.1 four-matrix evidence anchors"]
    audit["pending_preserved"] = ["RiboMIMO homology/protein/study/functional OOD and publication-metric reproduction" if item.startswith("RiboMIMO Subtelny14/Mohammad19-1/Mohammad19-2") else item for item in base_audit["pending_preserved"]]
    audit["scientific_scope"] = dict(base_audit["scientific_scope"])
    audit["scientific_scope"]["ribomimo_full_mohammad16"] = "Complete official Mohammad16 random-gene CV, executed twice with independent inference; incorporated into the four-matrix result"
    audit["scientific_scope"]["ribomimo_official"] = "Bounded diagnostic retained; complete four-matrix official random-gene CV is reported separately; OOD, publication-metric reproduction, unified-cost main matrix and SOTA open"
    audit["scientific_scope"]["ribomimo_full_four_matrix"] = "All four author-processed matrices completed official 1x10-fold/max100/early-stop5 random-gene CV twice with 40 bitwise-identical checkpoint pairs and independent inference; no OOD, publication-metric reproduction, unified-cost ranking or SOTA claim"
    atomic_json(audit_path, audit)
    print(json.dumps({"status": audit["status"], "schema": audit["schema_version"], "paper_sha256": audit["output_sha256"], "audit_sha256": sha256(audit_path), "v14_snapshot": audit["v14_snapshot"]}, indent=2))


if __name__ == "__main__":
    main()
