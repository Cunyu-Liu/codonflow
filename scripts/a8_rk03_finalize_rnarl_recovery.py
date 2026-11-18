#!/usr/bin/env python3
"""Finalize an already completed RNARL QC run after corrected independent verification.

This recovery finalizer never overwrites production QC or historical FAIL reports.
It rechecks source bytes, manifests, counts, clean-set leakage and scientific scope.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EXPECTED = {
    "processed_file_count": 21,
    "total_rows": 260754,
    "clean_rows": 256578,
    "clean_pairs": 128289,
}


def digest(path: Path, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/home/codonflow-a8-rk"))
    parser.add_argument("--data-root", type=Path, default=Path("/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit = args.repo / "audits/20261118/RK03"
    config_path = args.repo / "configs/a8_rk03_sources.json"
    raw_dir = args.data_root / "raw/rnarl_v1"
    qc_dir = args.data_root / "clean/rnarl_v2"
    qc_path = audit / "rnarl_qc.json"
    verification_path = audit / "rnarl_independent_verification_v2.json"
    historical_v1_path = audit / "rnarl_independent_verification.json"
    historical_v3_path = audit / "rnarl_finalization_recovery_v3.json"
    qc = load(qc_path)
    verification = load(verification_path)
    historical_v1 = load(historical_v1_path)
    historical_v3 = load(historical_v3_path)
    config = load(config_path)
    source = next(s for s in config["sources"] if s["source_id"] == "rnarl_v1")
    checks = []

    def add(name: str, condition: bool, detail=None) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    raw_errors = []
    for spec in source["files"]:
        path = raw_dir / spec["filename"]
        if not path.is_file():
            raw_errors.append({"filename": spec["filename"], "error": "missing"})
            continue
        if path.stat().st_size != int(spec["expected_bytes"]):
            raw_errors.append({"filename": spec["filename"], "error": "bytes"})
        if digest(path, "md5") != spec["expected_md5"].lower():
            raw_errors.append({"filename": spec["filename"], "error": "md5"})
    add("raw_21_files_exact_bytes_md5", not raw_errors and len(source["files"]) == 21, raw_errors)

    manifest_results = {}
    for name in ("rnarl_download_manifest.json", "rnarl_reverify_download_manifest.json"):
        manifest = load(audit / name)
        records = [r for r in manifest["records"] if r["source_id"] == "rnarl_v1"]
        verified_statuses = {"downloaded_verified", "reused_verified"}
        manifest_results[name] = manifest["status"] == "complete" and not manifest["failures"] and len(records) == 21 and all(r["status"] in verified_statuses for r in records)
    add("download_and_reverify_manifests_complete", all(manifest_results.values()), manifest_results)

    add("production_counts", all(qc.get(k) == v for k, v in EXPECTED.items()) and qc["expected_file_count"] == 21, {k: qc.get(k) for k in EXPECTED})
    add("corrected_independent_verifier", verification["status"] == "PASS" and verification["passed_checks"] == verification["check_count"] == 8 and verification["max_numeric_delta"] == 0.0 and verification["independent_production_import"] is False, {"status": verification["status"], "checks": f"{verification['passed_checks']}/{verification['check_count']}", "max_numeric_delta": verification["max_numeric_delta"], "comparison_contract": verification["comparison_contract"]})
    recomputed = verification["recomputed"]
    recompute_ok = recomputed["rows"] == qc["total_rows"] and recomputed["clean_rows"] == qc["clean_rows"] and recomputed["clean_pairs"] == qc["clean_pairs"] and recomputed["overlap_keys"] == {"protein_id": 0, "protein_sequence": 0, "exact_cds": 22}
    add("independent_counts_and_raw_overlap", recompute_ok and qc["split_overlaps"]["exact_cds"]["overlapping_keys"] == 22 and qc["overlap_row_counts"]["cross_split_exact_cds"] == 44, recomputed)

    manifest = load(qc_dir / "artifact_manifest.json")
    artifact_errors = []
    for name, record in manifest["outputs"].items():
        path = qc_dir / name
        if not path.is_file() or path.stat().st_size != int(record["bytes"]) or digest(path) != record["sha256"]:
            artifact_errors.append(name)
    add("artifact_manifest_hashes", not artifact_errors, artifact_errors)

    clean_rows = 0
    pair_counts = defaultdict(int)
    pair_cds = defaultdict(set)
    cds_splits = defaultdict(set)
    protein_splits = defaultdict(set)
    scope_violations = 0
    with gzip.open(qc_dir / "rnarl_clean.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            clean_rows += 1
            pair_id = row["pair_id"]
            pair_counts[pair_id] += 1
            pair_cds[pair_id].add(row["cds_sha256"])
            cds_splits[row["cds_sha256"]].add(row["split"])
            protein_splits[row["protein_sha256"]].add(row["split"])
            required = row["clean_eligible"] and row["base_qc_pass"] and row["pair_pass"] and row["pair_structure_pass"] and row["pair_distinct_cds"] and row["pair_same_protein_sequence"]
            forbidden = row["pair_cross_split_overlap"] or row["cross_split_exact_cds"] or row["cross_split_protein_id"] or row["cross_split_protein_sequence"] or row["natural_cds_source_validated"] or row["lambda_identity_inferred_from_order_or_mfe"] or row["pair_lambda_01_recoverable"] or row["reported_lambda"] is not None
            scope_violations += int(not required or forbidden)
    clean_cds_overlap = sum(len(splits) > 1 for splits in cds_splits.values())
    clean_protein_overlap = sum(len(splits) > 1 for splits in protein_splits.values())
    malformed_pairs = sum(pair_counts[p] != 2 or len(pair_cds[p]) != 2 for p in pair_counts)
    clean_ok = clean_rows == EXPECTED["clean_rows"] and len(pair_counts) == EXPECTED["clean_pairs"] and malformed_pairs == 0 and clean_cds_overlap == 0 and clean_protein_overlap == 0 and scope_violations == 0
    add("clean_pairs_and_leakage_exclusion", clean_ok, {"clean_rows": clean_rows, "clean_pairs": len(pair_counts), "malformed_pairs": malformed_pairs, "clean_exact_cds_cross_split_keys": clean_cds_overlap, "clean_protein_sequence_cross_split_keys": clean_protein_overlap, "scope_violations": scope_violations})

    scope_ok = qc["clean_pair_level_leakage_exclusion_applied"] and not qc["long_format_two_distinct_cds_pattern_observed"] and not qc["lambda_label_recoverable"] and not qc["lambda_stratified_analysis_ready"] and not qc["natural_cds_source_validated"] and not qc["natural_distribution_eligible"] and not qc["functional_training_authorized"] and not qc["functional_ood_claim_authorized"]
    add("bounded_scientific_scope", scope_ok, {"pair_table_only": True, "natural_distribution_eligible": qc["natural_distribution_eligible"], "lambda_stratified_analysis_ready": qc["lambda_stratified_analysis_ready"], "functional_training_authorized": qc["functional_training_authorized"], "functional_ood_claim_authorized": qc["functional_ood_claim_authorized"]})
    history_ok = historical_v1["status"] == "FAIL" and historical_v1["passed_checks"] == 6 and historical_v1["check_count"] == 8 and historical_v3["status"] == "FAIL"
    add("historical_failures_preserved", history_ok, {"independent_v1": "FAIL 6/8", "recovery_v3": "FAIL", "interpretation": "Historical comparison-contract failure retained; corrected record_id-join verifier is separate v2 evidence."})
    add("home_code_teams_data_layout", str(args.repo).startswith("/home/") and str(args.data_root).startswith("/teams/HoulabData_1788502323/liucunyu/"))

    passed = sum(c["pass"] for c in checks)
    status = "PASS_BOUNDED_LINEARDESIGN_PAIR_TABLE_QC_ONLY" if passed == len(checks) else "FAIL"
    evidence_paths = [config_path, qc_path, verification_path, historical_v1_path, historical_v3_path, audit / "rnarl_official_file_sizes_final.json", audit / "rnarl_download_manifest.json", audit / "rnarl_reverify_download_manifest.json", qc_dir / "qc_summary.json", qc_dir / "artifact_manifest.json"]
    result = {
        "schema_version": "a8-rk03-rnarl-recovery-finalization-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "checks": checks,
        "passed_checks": passed,
        "check_count": len(checks),
        "raw_files": 21,
        "raw_rows": qc["total_rows"],
        "clean_rows": qc["clean_rows"],
        "clean_pairs": qc["clean_pairs"],
        "raw_cross_split_overlap_keys": recomputed["overlap_keys"],
        "raw_cross_split_exact_cds_rows": qc["overlap_row_counts"]["cross_split_exact_cds"],
        "clean_cross_split_exact_cds_keys": clean_cds_overlap,
        "clean_cross_split_protein_sequence_keys": clean_protein_overlap,
        "independent_verification": {"report": verification_path.name, "status": verification["status"], "checks": f"{verification['passed_checks']}/{verification['check_count']}", "max_numeric_delta": verification["max_numeric_delta"], "comparison_contract": verification["comparison_contract"]},
        "historical_failures_preserved": [historical_v1_path.name, historical_v3_path.name],
        "science_flags": {
            "ppt_record_ready": passed == len(checks),
            "bounded_lineardesign_pair_table_ready": passed == len(checks),
            "long_format_two_distinct_cds_pattern_observed": False,
            "lambda_label_recoverable": False,
            "lambda_stratified_analysis_ready": False,
            "natural_cds_source_validated": False,
            "natural_distribution_eligible": False,
            "raw_read_or_psite_remapping_complete": False,
            "functional_training_authorized": False,
            "functional_ood_claim_authorized": False,
            "official_model_reproduced": False,
            "main_baseline_comparison": False,
            "sota_claim": False,
        },
        "scope": "Publisher-provided LinearDesign-like pair table QC only. Raw exact-CDS cross-split overlaps were excluded as whole protein pairs. No natural-CDS distribution, lambda stratification, functional training/OOD, official model reproduction or SOTA authorization.",
        "artifacts": {str(p.relative_to(args.repo)) if p.is_relative_to(args.repo) else str(p): digest(p) for p in evidence_paths},
    }
    if args.output.exists():
        raise RuntimeError(f"refusing to overwrite {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    part = args.output.with_name(args.output.name + f".part-{os.getpid()}")
    part.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(part, args.output)
    print(json.dumps({"status": status, "checks": f"{passed}/{len(checks)}", "raw_rows": result["raw_rows"], "clean_rows": result["clean_rows"], "clean_pairs": result["clean_pairs"], "science_flags": result["science_flags"]}, indent=2))
    if status == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
