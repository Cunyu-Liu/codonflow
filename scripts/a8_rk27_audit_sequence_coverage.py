#!/usr/bin/env python3
"""RK27 label-free Kudla sequence-cluster coverage audit.

This script is intentionally unable to read expression, MFE, CAI or model outputs.
It freezes only sequence-derived clusters and coverage facts before model fitting.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def balanced_fold_sizes(labels: np.ndarray, seed: int, folds: int = 5) -> list[int]:
    ids = np.array(sorted(np.unique(labels).tolist()))
    rng = np.random.default_rng(seed)
    shuffled = ids[rng.permutation(len(ids))].tolist()
    sizes = {int(c): int(np.sum(labels == c)) for c in ids}
    ordered = sorted(shuffled, key=lambda c: -sizes[int(c)])
    loads = np.zeros(folds, dtype=int)
    for cluster in ordered:
        candidates = np.flatnonzero(loads == loads.min())
        fold = int(rng.choice(candidates))
        loads[fold] += sizes[int(cluster)]
    return loads.tolist()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    parser.add_argument("--output-facts", type=Path, required=True)
    args = parser.parse_args()

    protocol = json.loads(args.protocol.read_text())
    audit = protocol["label_free_coverage_audit"]
    permitted = list(audit["columns_permitted"])
    forbidden = set(audit["columns_forbidden"])
    assert not forbidden.intersection(permitted)
    source = Path(protocol["inputs"]["main_csv"]["path"])
    assert sha256(source) == protocol["inputs"]["main_csv"]["sha256"]

    # Only these three columns are loaded; all outcome and mechanism columns stay unread.
    raw = pd.read_csv(source, usecols=permitted)
    raw["cds"] = raw["cds"].astype(str).str.upper()
    raw["protein_aa"] = raw["protein_aa"].astype(str)
    df = raw.drop_duplicates("cds").sort_values("source_row").reset_index(drop=True)
    assert len(df) == audit["expected_unique_cds"]
    assert df["protein_aa"].nunique() == audit["expected_protein_groups"]
    assert df["cds"].str.len().nunique() == 1
    length = int(df["cds"].str.len().iloc[0])
    assert length == 720
    assert df["cds"].str.fullmatch("[ACGT]+").all()

    seqs = df["cds"].tolist()
    encoded = np.array([[ord(c) for c in seq] for seq in seqs], dtype=np.uint8)
    identity = (encoded[:, None, :] == encoded[None, :, :]).mean(axis=2)
    np.testing.assert_allclose(np.diag(identity), 1.0)
    assert identity.max() < 1.0 + 1e-12
    off_diag = identity[np.triu_indices(len(df), 1)]
    assert off_diag.max() < 1.0
    linkage_matrix = linkage(squareform(1.0 - identity, checks=False), method="complete")

    coverage_rows = []
    selected = None
    selected_labels = None
    for min_identity in audit["candidate_min_identities"]:
        labels = fcluster(linkage_matrix, t=1.0 - float(min_identity), criterion="distance")
        cluster_ids, sizes = np.unique(labels, return_counts=True)
        singleton_fraction = float(np.mean(sizes == 1))
        if len(cluster_ids) == 1:
            nearest_median = None
            nearest_max = None
            primary_fold_sizes = [len(df), 0, 0, 0, 0]
        else:
            nearest = [float(identity[i, labels != labels[i]].max()) for i in range(len(df))]
            nearest_median = float(np.median(nearest))
            nearest_max = float(np.max(nearest))
            primary_fold_sizes = balanced_fold_sizes(labels, protocol["outer_evaluation"]["primary_seed"])
        row = {
            "min_identity": float(min_identity),
            "clusters": int(len(cluster_ids)),
            "singleton_clusters": int(np.sum(sizes == 1)),
            "singleton_fraction": singleton_fraction,
            "largest_cluster": int(sizes.max()),
            "median_cluster_size": float(np.median(sizes)),
            "primary_seed_fold_sizes": primary_fold_sizes,
            "cross_cluster_nearest_identity_median": nearest_median,
            "cross_cluster_nearest_identity_max": nearest_max,
        }
        row["coverage_eligible"] = bool(
            row["clusters"] >= 30
            and row["largest_cluster"] <= 75
            and row["singleton_fraction"] <= 0.50
        )
        coverage_rows.append(row)
        if selected is None and row["coverage_eligible"]:
            selected = float(min_identity)
            selected_labels = labels.copy()

    assert selected == audit["selected_min_identity_from_label_free_audit"]
    selected_row = next(row for row in coverage_rows if row["min_identity"] == selected)
    assert selected_row["clusters"] == audit["expected_clusters"]
    assert selected_row["largest_cluster"] == audit["expected_largest_cluster"]
    assert selected_row["singleton_clusters"] == audit["expected_singleton_clusters"]

    cluster_sizes = {int(c): int(np.sum(selected_labels == c)) for c in np.unique(selected_labels)}
    facts = pd.DataFrame({
        "first_source_row": df["source_row"].astype(int),
        "cds_sha256": [hashlib.sha256(seq.encode()).hexdigest() for seq in seqs],
        "sequence_cluster_id": selected_labels.astype(int),
    })
    facts["cluster_size"] = facts["sequence_cluster_id"].map(cluster_sizes).astype(int)
    assert len(facts) == 150
    assert facts["cds_sha256"].is_unique
    assert facts.groupby("sequence_cluster_id").size().max() == 61
    args.output_facts.parent.mkdir(parents=True, exist_ok=True)
    facts.to_csv(args.output_facts, index=False)

    report = {
        "schema": "a8-rk27-label-free-sequence-cluster-coverage-v1",
        "status": "PASS_LABEL_FREE_COVERAGE_AUDIT",
        "analysis_type": "retrospective_label_free_coverage_audit_before_RK27_model_fit",
        "protocol": str(args.protocol),
        "protocol_sha256": sha256(args.protocol),
        "coverage_script_sha256": sha256(Path(__file__).resolve()),
        "source_csv": str(source),
        "source_sha256": sha256(source),
        "columns_read": permitted,
        "forbidden_columns_not_read": sorted(forbidden),
        "measurement_rows": int(len(raw)),
        "unique_cds": int(len(df)),
        "cds_length_nt": length,
        "exact_protein_groups": int(df["protein_aa"].nunique()),
        "pairwise_identity_quantiles": {
            str(q): float(np.quantile(off_diag, q))
            for q in [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]
        },
        "coverage_rows": coverage_rows,
        "selected_min_identity": selected,
        "selected_coverage": selected_row,
        "facts_csv": str(args.output_facts),
        "facts_sha256": sha256(args.output_facts),
        "expression_or_model_fit_performed": False,
        "functional_untouched_read": False,
    }
    write_json(args.output_report, report)
    print(json.dumps({
        "status": report["status"],
        "unique_cds": report["unique_cds"],
        "selected_min_identity": selected,
        "selected_coverage": selected_row,
        "facts_sha256": report["facts_sha256"],
        "expression_or_model_fit_performed": False,
    }, indent=2))


if __name__ == "__main__":
    main()
