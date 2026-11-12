import json

import pytest

from codonflow.eval.metrics import cai_weights_from_rscu, compute_rscu
from scripts.a7_data_audit import audit_records, validate_cleaning_manifest


def test_data_audit_reports_quality_distribution_and_metadata():
    records = [
        ("g1", "ATGTTTGCTTAA"),
        ("g2", "ATGGAAGCTTAA"),
        ("bad", "ATGNNNTAA"),
    ]
    weights = cai_weights_from_rscu(compute_rscu([sequence for _, sequence in records[:2]]))
    result = audit_records(records, cai_weights=weights, min_length=1,
                           species_map={"g1": "human", "g2": "mouse"},
                           cluster_map={"g1": "c1", "g2": "c2"})
    assert result["n"] == 3
    assert result["n_unique_proteins"] == 2
    assert result["invalid_reason_counts"]["alphabet"] == 1
    assert result["metadata"]["species_counts"]["human"] == 1
    assert result["metadata"]["n_species_mapped"] == 2
    assert result["metadata"]["n_clusters"] == 2
    assert result["cai"]["mean"] > 0
    assert len(result["rscu"]) == 61


def test_data_audit_separates_operator_legality_from_atg_quality():
    result = audit_records([("partial", "GTGTTTGCTTAA")], min_length=1)
    assert result["n_operator_legal"] == 1
    assert result["n_valid_cds"] == 0
    assert result["n_atg_start"] == 0
    assert result["n_unique_proteins"] == 1
    assert result["invalid_reason_counts"] == {"start": 1}


def test_cleaning_manifest_requires_conservation():
    validate_cleaning_manifest({"n_input": 10, "n_retained": 7,
                                "removed": {"length": 2, "stop": 1}, "fasta_n": 7})
    with pytest.raises(ValueError, match="conserve"):
        validate_cleaning_manifest({"n_input": 10, "n_retained": 8,
                                    "removed": {"length": 1}})
