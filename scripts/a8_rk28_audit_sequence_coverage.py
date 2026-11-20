#!/usr/bin/env python3
"""RK28 label-free observed-R1 sequence-cluster coverage audit.

Only variant_id and sequence_5prime_300nt are loaded. Outcomes, counts used by
outcomes, depth and model features are never read. No model is fitted here.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def balanced_folds(labels, seed, folds=5):
    ids = np.array(sorted(np.unique(labels).tolist()))
    rng = np.random.default_rng(seed)
    shuffled = ids[rng.permutation(len(ids))].tolist()
    sizes = {int(c): int(np.sum(labels == c)) for c in ids}
    ordered = sorted(shuffled, key=lambda c: -sizes[int(c)])
    loads = np.zeros(folds, dtype=int)
    cluster_loads = np.zeros(folds, dtype=int)
    assignments = {}
    for cluster in ordered:
        candidates = np.flatnonzero(loads == loads.min())
        fold = int(rng.choice(candidates))
        assignments[int(cluster)] = fold
        loads[fold] += sizes[int(cluster)]
        cluster_loads[fold] += 1
    return assignments, loads.tolist(), cluster_loads.tolist()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    parser.add_argument("--output-facts", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    audit = protocol["label_free_coverage_audit"]
    permitted = list(audit["columns_permitted"])
    forbidden = set(audit["columns_forbidden"])
    assert permitted == ["variant_id", "sequence_5prime_300nt"]
    assert not forbidden.intersection(permitted)
    source = Path(protocol["inputs"]["main_csv"]["path"])
    assert sha256(source) == protocol["inputs"]["main_csv"]["sha256"]

    # This is the only source-table read in the coverage program.
    df = pd.read_csv(source, usecols=permitted, dtype=str, keep_default_na=False)
    df["sequence_5prime_300nt"] = df["sequence_5prime_300nt"].str.upper()
    checks = []

    def check(name, passed):
        checks.append({"name": name, "pass": bool(passed)})

    check("152 rows", len(df) == audit["expected_rows"])
    check("unique variant IDs", df["variant_id"].is_unique and not df["variant_id"].eq("").any())
    check("300 nt sequences", df["sequence_5prime_300nt"].str.len().eq(audit["expected_sequence_length"]).all())
    check("ACGT only", df["sequence_5prime_300nt"].str.fullmatch("[ACGT]+").all())
    check("unique observed-R1 sequences", df["sequence_5prime_300nt"].is_unique)
    basic_ok = all(item["pass"] for item in checks)
    n_clusters = 0
    largest_cluster = len(df)
    singleton_clusters = 0
    fold_sizes = [0] * 5
    fold_cluster_counts = [0] * 5
    pairwise_quantiles = {}
    nearest_median = None
    nearest_max = None
    labels = np.zeros(len(df), dtype=int)
    if basic_ok:
        seqs = df["sequence_5prime_300nt"].tolist()
        encoded = np.array([[ord(c) for c in seq] for seq in seqs], dtype=np.uint8)
        identity = (encoded[:, None, :] == encoded[None, :, :]).mean(axis=2)
        np.testing.assert_allclose(np.diag(identity), 1.0)
        off_diag = identity[np.triu_indices(len(df), 1)]
        pairwise_quantiles = {str(q): float(np.quantile(off_diag, q)) for q in [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]}
        linkage_matrix = linkage(squareform(1.0 - identity, checks=False), method="complete")
        labels = fcluster(linkage_matrix, t=1.0 - float(audit["min_identity"]), criterion="distance")
        cluster_ids, sizes = np.unique(labels, return_counts=True)
        n_clusters = int(len(cluster_ids))
        largest_cluster = int(sizes.max())
        singleton_clusters = int(np.sum(sizes == 1))
        if n_clusters > 1:
            nearest = [float(identity[i, labels != labels[i]].max()) for i in range(len(df))]
            nearest_median = float(np.median(nearest))
            nearest_max = float(np.max(nearest))
        assignments, fold_sizes, fold_cluster_counts = balanced_folds(labels, protocol["outer_evaluation"]["primary_seed"])
    else:
        assignments = {}
    check("at least 10 clusters", n_clusters >= 10)
    check("largest cluster <=121", largest_cluster <= math.floor(0.8 * len(df)))
    check("every primary fold >=5 variants", min(fold_sizes) >= 5)
    check("every primary fold >=2 clusters", min(fold_cluster_counts) >= 2)
    feasible = all(item["pass"] for item in checks)
    cluster_sizes = {int(c): int(np.sum(labels == c)) for c in np.unique(labels)} if basic_ok else {}
    facts = pd.DataFrame({
        "variant_id": df["variant_id"],
        "sequence_sha256": [hashlib.sha256(seq.encode()).hexdigest() for seq in df["sequence_5prime_300nt"]],
        "sequence_cluster_id": labels.astype(int),
        "cluster_size": [cluster_sizes.get(int(c), 0) for c in labels],
        "primary_seed_fold": [assignments.get(int(c), -1) for c in labels],
    })
    args.output_facts.parent.mkdir(parents=True, exist_ok=True)
    facts.to_csv(args.output_facts, index=False)
    status = "PASS_LABEL_FREE_COVERAGE_AUDIT_FEASIBLE" if feasible else "PASS_LABEL_FREE_COVERAGE_AUDIT_INFEASIBLE_ZERO_FITS"
    report = {
        "schema": "a8-rk28-label-free-sequence-cluster-coverage-v1",
        "status": status,
        "analysis_type": "retrospective_label_free_coverage_audit_before_RK28_outcome_or_feature_read",
        "protocol": str(args.protocol),
        "protocol_sha256": sha256(args.protocol),
        "coverage_script_sha256": sha256(Path(__file__).resolve()),
        "source_csv": str(source),
        "source_sha256": sha256(source),
        "columns_read": permitted,
        "forbidden_columns_not_read": sorted(forbidden),
        "rows": int(len(df)),
        "sequence_length_nt": audit["expected_sequence_length"],
        "pairwise_identity_quantiles": pairwise_quantiles,
        "selected_min_identity": audit["min_identity"],
        "selected_coverage": {
            "clusters": n_clusters,
            "singleton_clusters": singleton_clusters,
            "singleton_fraction": float(singleton_clusters / n_clusters) if n_clusters else None,
            "largest_cluster": largest_cluster,
            "primary_seed_fold_sizes": fold_sizes,
            "primary_seed_fold_cluster_counts": fold_cluster_counts,
            "cross_cluster_nearest_identity_median": nearest_median,
            "cross_cluster_nearest_identity_max": nearest_max,
        },
        "checks": checks,
        "coverage_feasible": feasible,
        "model_fit_authorized": feasible,
        "scientific_conclusion_if_infeasible": None if feasible else "COVERAGE_INFEASIBLE_ZERO_FITS",
        "facts_csv": str(args.output_facts),
        "facts_sha256": sha256(args.output_facts),
        "outcome_or_model_feature_read": False,
        "expression_or_model_fit_performed": False,
        "functional_untouched_read": False,
        "complete_cds_observed": False,
        "measured_structure": False,
    }
    write_json(args.output_report, report)
    print(json.dumps({"status": status, "coverage_feasible": feasible, "selected_coverage": report["selected_coverage"], "facts_sha256": report["facts_sha256"], "outcome_or_model_feature_read": False}, indent=2))


if __name__ == "__main__":
    main()
