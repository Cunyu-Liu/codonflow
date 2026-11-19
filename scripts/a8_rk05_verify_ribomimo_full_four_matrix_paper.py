#!/usr/bin/env python3
"""Independently verify the bounded A8 v15 four-matrix paper delta."""
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


def atomic_json(path: Path, value: dict) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--work-dir", type=Path, default=Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_full_094c_v1/paper_v15/verification"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    audit_path = repo / "paper/a8_rk_paper_sync_audit.json"
    audit = load(audit_path)
    paper_path = Path(audit["output"])
    text = paper_path.read_text(encoding="utf-8")
    snapshot = audit["v14_snapshot"]
    snapshot_paper = Path(snapshot["paper"])
    snapshot_audit = Path(snapshot["audit"])
    original_snapshot_audit = Path(snapshot["original_audit"])

    root = repo / "audits/20261118/RK05"
    summary_path = root / "ribomimo_full_four_matrix_summary_v1.json"
    summary_verification_path = root / "ribomimo_full_four_matrix_summary_verification_v1.json"
    summary = load(summary_path)
    summary_verification = load(summary_verification_path)
    paths = {}
    for slug in ("subtelny14", "mohammad19_1", "mohammad19_2"):
        for kind in ("protocol", "production", "retrain", "independent", "finalization"):
            suffix = {"protocol": "protocol_v1", "production": "v1", "retrain": "retrain_v1", "independent": "independent_v1", "finalization": "finalization_v1"}[kind]
            paths[f"ribomimo_full_{slug}_{kind}"] = root / f"ribomimo_full_{slug}_{suffix}.json"
    paths["ribomimo_full_four_matrix_summary"] = summary_path
    paths["ribomimo_full_four_matrix_summary_verification"] = summary_verification_path

    labels = {"protocol": "frozen protocol", "production": "production", "retrain": "deterministic retrain", "independent": "independent inference", "finalization": "finalization"}
    expected_evidence = []
    for slug in ("subtelny14", "mohammad19_1", "mohammad19_2"):
        for kind in ("protocol", "production", "retrain", "independent", "finalization"):
            key = f"ribomimo_full_{slug}_{kind}"
            expected_evidence.append(f"| RiboMIMO full {slug} {labels[kind]} | `{sha256(paths[key])}` |")
    expected_evidence.append(f"| RiboMIMO full four-matrix summary | `{sha256(summary_path)}` |")
    expected_evidence.append(f"| RiboMIMO full four-matrix summary verification | `{sha256(summary_verification_path)}` |")

    # Reconstruct v14 solely by removing the authorized v15 delta.
    reconstructed = text
    section_title = "**RiboMIMO complete four-matrix official cross-validation.**"
    following_marker = "**iXnos bounded official prefix-read training.**"
    section_start = reconstructed.find(section_title)
    section_end = reconstructed.find(following_marker, section_start)
    section_removal_ok = section_start >= 0 and section_end > section_start
    if section_removal_ok:
        reconstructed = reconstructed[:section_start] + reconstructed[section_end:]
    new_pending = "The three remaining matrices are completed in the four-matrix extension below. Homology/protein/study/functional OOD, publication-metric reproduction, the unified-cost baseline matrix, CodonFlow-RK comparison and SOTA assessment remain pending."
    old_pending = "Full training on Subtelny14, Mohammad19-1 and Mohammad19-2, homology/protein/study/functional OOD, publication-metric reproduction, the unified-cost baseline matrix, CodonFlow-RK comparison and SOTA assessment remain pending."
    pending_replacement_ok = reconstructed.count(new_pending) == 1
    reconstructed = reconstructed.replace(new_pending, old_pending, 1)
    anchor = next(line for line in reconstructed.splitlines() if line.startswith("| RiboMIMO full Mohammad16 finalization |"))
    lines = reconstructed.splitlines(keepends=True)
    anchor_index = next(i for i, line in enumerate(lines) if line.rstrip("\n") == anchor)
    actual_evidence = [line.rstrip("\n") for line in lines[anchor_index + 1:anchor_index + 1 + len(expected_evidence)]]
    evidence_delta_ok = actual_evidence == expected_evidence
    if evidence_delta_ok:
        del lines[anchor_index + 1:anchor_index + 1 + len(expected_evidence)]
    reconstructed = "".join(lines)

    checks = []

    def check(name: str, condition: bool, detail: object) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    check("v15_audit_and_paper_hash", audit["schema_version"] == "a8-rk-paper-sync-v15" and audit["output_sha256"] == sha256(paper_path), {"schema": audit["schema_version"], "paper_sha256": sha256(paper_path)})
    check("v14_snapshot_integrity", sha256(snapshot_paper) == snapshot["paper_sha256"] and sha256(snapshot_audit) == snapshot["audit_sha256"] and sha256(original_snapshot_audit) == snapshot["original_audit_sha256"], snapshot)
    check("v14_snapshot_audit_binding", load(snapshot_audit)["output_sha256"] == sha256(snapshot_paper) and audit["base_v14_audit_sha256"] == sha256(original_snapshot_audit), audit["base_v14_audit_sha256"])
    check("a7_unchanged", sha256(repo / "paper/CodonFlow_preprint_A7.md") == "941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423", True)
    check("section_removal_delta", section_removal_ok and text.count(section_title) == 1, section_start)
    check("pending_sentence_delta", pending_replacement_ok and old_pending not in text, pending_replacement_ok)
    check("evidence_delta", evidence_delta_ok and len(expected_evidence) == 17, len(actual_evidence))
    check("exact_v14_reconstruction", reconstructed == snapshot_paper.read_text(encoding="utf-8"), {"reconstructed_sha256": hashlib.sha256(reconstructed.encode()).hexdigest(), "snapshot_sha256": sha256(snapshot_paper)})

    expected = [
        section_title,
        f"**{summary['total_raw_records']:,} raw records / {summary['total_official_loader_eligible_genes']:,} official-loader-eligible genes**",
        f"**{summary['total_valid_masked_test_codons']:,} valid masked test codons**",
        f"**{summary_verification['checks_passed']}/{summary_verification['checks_total']} checks**",
        "**8 complete training runs, 40 bitwise-identical fold-checkpoint pairs, and 80 independent forward passes**",
        "eligible count remains distinct from RK03 clean QC=8,109",
        "not a unified strong-baseline matrix",
        "non-submittable working manuscript", "No SOTA claim.",
    ]
    for dataset in ("Subtelny14", "Mohammad19-1", "Mohammad19-2", "Mohammad16"):
        row = summary["datasets"][dataset]
        agg = row["aggregate"]
        baseline = row["constant_train_mean_baseline_aggregate"]
        expected.append(f"| {dataset} | {row['raw_records']:,} / {row['eligible_genes']:,} | {agg['r2_mean']:.6f} ± {agg['r2_std']:.6f} | {agg['mse_mean']:.6f} ± {agg['mse_std']:.6f} | {agg['pearson_mean']:.6f} ± {agg['pearson_std']:.6f} | {baseline['r2_mean']:.6f} / {baseline['mse_mean']:.6f} |")
    check("four_matrix_results_rendered", all(value in text for value in expected), {"expected_strings": len(expected)})
    check("summary_verified", summary["status"] == "PASS_COMPLETE_FOUR_MATRIX_OFFICIAL_CV" and summary_verification["status"] == "PASS" and summary_verification["checks_total"] == summary_verification["checks_passed"] and summary_verification["summary_generator_imported"] is False and summary_verification["summary_sha256"] == sha256(summary_path), f"{summary_verification['checks_passed']}/{summary_verification['checks_total']}")
    check("four_matrix_execution_counts", summary["complete_training_runs"] == 8 and summary["checkpoint_pairs_bitwise_identical"] == 40 and summary["independent_forward_passes"] == 80 and summary["official_random_gene_cv_complete_all_four"] is True and len(summary["folds"]) == 40, len(summary["folds"]))
    check("four_matrix_totals", summary["total_raw_records"] == 15669 and summary["total_official_loader_eligible_genes"] == 8124 and summary["rk03_clean_qc_count_not_interchanged"] == 8109, {"raw": summary["total_raw_records"], "eligible": summary["total_official_loader_eligible_genes"]})
    evidence_ok = all(audit["source_paths"].get(name) == str(path) and audit["source_sha256"].get(name) == sha256(path) for name, path in paths.items())
    check("audit_source_hashes", evidence_ok, {name: sha256(path) for name, path in paths.items()})
    check("four_matrix_scope", all(summary[key] is False for key in ("homology_aware_split", "protein_ood", "study_ood", "functional_ood", "publication_metrics_reproduced", "unified_cost_baseline_matrix", "sota_claim")) and "homology/protein/study/functional OOD, publication-metric reproduction, unified-cost baseline ranking, CodonFlow-RK, SOTA and wet-lab validation remain open" in text and audit["scientific_scope"]["submittable"] is False and audit["scientific_scope"]["sota"] is False, summary["scope"])

    passed = sum(row["pass"] for row in checks)
    report = {
        "schema_version": "a8-rk05-four-matrix-paper-verification-v15",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "paper": str(paper_path), "paper_sha256": sha256(paper_path),
        "sync_audit": str(audit_path), "sync_audit_sha256": sha256(audit_path),
        "v14_snapshot": str(snapshot_paper), "v14_snapshot_sha256": sha256(snapshot_paper),
        "checks": checks, "checks_passed": passed, "checks_total": len(checks),
        "paper_update_module_imported": False,
        "scope": "Four-matrix official random-gene CV closed; A8 remains non-submittable because mechanism, model, OOD, unified-cost main matrix, SOTA and wet-lab validation remain open.",
    }
    output = args.output or repo / "paper/a8_rk05_four_matrix_paper_verification.json"
    atomic_json(output, report)
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}", "paper_sha256": report["paper_sha256"], "output": str(output)}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
