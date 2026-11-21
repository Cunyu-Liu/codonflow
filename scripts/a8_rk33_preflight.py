#!/usr/bin/env python3
"""RK33 label-free sequence/fold preflight; never computes MFE or reads outcomes."""
from pathlib import Path
import argparse
import hashlib
import json

import pandas as pd


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    checks = []
    def check(name, condition, details):
        checks.append({"name": name, "pass": bool(condition), "details": details})

    for name, spec in protocol["inputs"].items():
        path = Path(spec["path"])
        check(f"input_hash_{name}", path.is_file() and sha256(path) == spec["sha256"], {"path": str(path), "sha256": spec["sha256"]})
    source = pd.read_csv(protocol["inputs"]["main_csv"]["path"], usecols=["variant_id", "sequence_5prime_300nt"], keep_default_na=False)
    sequences = source["sequence_5prime_300nt"].str.upper()
    check("variant_rows_and_ids", len(source) == 152 and source["variant_id"].is_unique, {"rows": len(source), "unique_ids": source["variant_id"].nunique()})
    check("unique_300nt_acgt", sequences.nunique() == 152 and sequences.str.len().eq(300).all() and sequences.apply(lambda x: set(x) <= set("ACGT")).all(), {"unique_sequences": sequences.nunique(), "lengths": sorted(sequences.str.len().unique().tolist())})
    local = sequences.str.slice(0, 42)
    check("local42_coordinates_valid", local.str.len().eq(42).all() and local.apply(lambda x: set(x) <= set("ACGT")).all(), {"local_coordinate": "CDS4-45", "unique_local42": local.nunique(), "note": "No folding or other model feature is computed."})
    headers = [line for line in Path(protocol["inputs"]["references_r1_fasta"]["path"]).read_text().splitlines() if line.startswith(">")]
    check("fasta_observed_coordinate_provenance", len(headers) == 152 and all("observed=CDS_4_303" in line for line in headers), {"headers": len(headers), "observed": "CDS_4_303", "start_atg_and_upstream4_observed": False})

    assignments = pd.read_csv(protocol["inputs"]["rk28_fold_assignments"]["path"])
    check("rk28_assignment_shape", len(assignments) == 1520 and list(assignments.columns) == ["seed", "variant_id", "sequence_cluster_id", "fold"], {"rows": len(assignments), "columns": list(assignments.columns)})
    check("rk28_assignment_coverage", set(assignments["variant_id"]) == set(source["variant_id"]) and assignments.groupby("seed").size().eq(152).all() and not assignments.duplicated(["seed", "variant_id"]).any(), {"seeds": assignments["seed"].nunique(), "variants_per_seed": sorted(assignments.groupby("seed").size().unique().tolist())})
    check("rk28_cluster_coverage", assignments["sequence_cluster_id"].nunique() == 74 and assignments.groupby("variant_id")["sequence_cluster_id"].nunique().eq(1).all(), {"clusters": assignments["sequence_cluster_id"].nunique()})
    check("rk28_fold_domain", set(assignments["fold"]) == {0, 1, 2, 3, 4}, {"folds": sorted(assignments["fold"].unique().tolist())})
    primary = assignments[assignments["seed"] == protocol["outer_evaluation"]["primary_seed"]]
    fold_sizes = primary.groupby("fold").size().reindex(range(5)).tolist()
    fold_clusters = primary.groupby("fold")["sequence_cluster_id"].nunique().reindex(range(5)).tolist()
    check("primary_fold_coverage", fold_sizes == [30, 31, 31, 30, 30] and min(fold_clusters) >= 2, {"fold_sizes": fold_sizes, "fold_clusters": fold_clusters})
    leakage_rows = 0
    for seed, group in assignments.groupby("seed"):
        for fold in range(5):
            test_clusters = set(group.loc[group["fold"] == fold, "sequence_cluster_id"])
            train_clusters = set(group.loc[group["fold"] != fold, "sequence_cluster_id"])
            leakage_rows += int(not test_clusters.isdisjoint(train_clusters))
    check("all_50_cluster_partitions_disjoint", leakage_rows == 0, {"leaking_seed_folds": leakage_rows})
    check("frozen_fit_accounting", protocol["models"]["new_model_fits"] == 200 and protocol["models"]["reused_rk28_model_fits"] == 200 and protocol["models"]["evaluated_model_fits"] == 400, {"new": 200, "reused": 200, "evaluated": 400})
    check("twelve_endpoint_family", protocol["primary_inference"]["total_tests"] == 12 and len(protocol["primary_inference"]["families"]) == 3, {"tests": 12, "multiplicity": protocol["primary_inference"]["multiplicity"]})
    check("no_untouched_or_window_search", protocol["coverage"]["functional_untouched_read"] is False and protocol["coverage"]["local_length_nt"] == 42, {"functional_untouched_read": False, "local_length": 42, "alternative_lengths": 0})

    report = {
        "schema": "a8-rk33-label-free-preflight-v1",
        "status": "PASS_RK33_LABEL_FREE_PREFLIGHT" if all(row["pass"] for row in checks) else "FAIL_RK33_LABEL_FREE_PREFLIGHT",
        "protocol_sha256": sha256(args.protocol),
        "checks": checks,
        "checks_passed": sum(row["pass"] for row in checks),
        "checks_total": len(checks),
        "coverage_feasible": all(row["pass"] for row in checks),
        "model_fit_authorized": all(row["pass"] for row in checks),
        "expression_or_model_fit_performed": False,
        "local_mfe_computed": False,
        "outcome_columns_read": [],
        "source_columns_read": ["variant_id", "sequence_5prime_300nt"],
        "functional_untouched_read": False,
        "selected_coverage": {"variants": 152, "clusters": 74, "unique_local42": int(local.nunique()), "primary_seed_fold_sizes": fold_sizes, "primary_seed_fold_clusters": fold_clusters},
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f'{report["checks_passed"]}/{report["checks_total"]}', "selected_coverage": report["selected_coverage"], "report": str(args.report)}, indent=2))
    if report["status"] != "PASS_RK33_LABEL_FREE_PREFLIGHT":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
