from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import a8_rk03_mage_pure_external_nested_cv as model


def test_pure_feature_schema_and_values() -> None:
    features = model.pure_features(-1.25, -2.0)
    assert list(features) == ["RCS", "delta_rcs_vs_wt", "abs_delta_rcs_vs_wt"]
    assert features == {"RCS": -1.25, "delta_rcs_vs_wt": 0.75, "abs_delta_rcs_vs_wt": 0.75}
    assert not ({"position", "GC", "MFE", "wt_codon", "mutant_codon", "amino_acid"} & set(features))


def test_raw_schema_never_selects_labels_or_sequences() -> None:
    header = ["construct_id", "expression_value", "expression_stdev", "cds", "protein_sequence", "record_class", "expression_type", "codon_position", "wt_codon", "mutant_codon", "amino_acid", "features_json"]
    indices = model.raw_column_indices(header)
    assert set(indices) == set(model.RAW_COLUMNS)
    assert not ({"expression_value", "expression_stdev", "cds", "protein_sequence"} & set(indices))


def test_raw_schema_rejects_missing_required_feature() -> None:
    with pytest.raises(AssertionError):
        model.raw_column_indices(["construct_id"])


def test_attach_features_skips_unselected_test_construct_and_labels(tmp_path: Path) -> None:
    path = tmp_path / "raw.csv"
    header = model.RAW_COLUMNS + ["expression_value", "expression_stdev", "cds", "protein_sequence"]
    rows = [
        {"construct_id": "wt1", "record_class": "wild_type_control", "expression_type": "relative_fitness_rich", "codon_position": "10", "wt_codon": "AAA", "mutant_codon": "AAA", "amino_acid": "K", "features_json": json.dumps({"RCS": -2.0}), "expression_value": "not-a-number", "expression_stdev": "not-a-number", "cds": "NOT_READ", "protein_sequence": "NOT_READ"},
        {"construct_id": "dev1", "record_class": "single_codon_variant", "expression_type": "relative_fitness_rich", "codon_position": "10", "wt_codon": "AAA", "mutant_codon": "AAG", "amino_acid": "K", "features_json": json.dumps({"RCS": -1.0}), "expression_value": "not-a-number", "expression_stdev": "not-a-number", "cds": "NOT_READ", "protein_sequence": "NOT_READ"},
        {"construct_id": "test1", "record_class": "single_codon_variant", "expression_type": "relative_fitness_rich", "codon_position": "10", "wt_codon": "AAA", "mutant_codon": "AAC", "amino_acid": "N", "features_json": json.dumps({"RCS": 99}), "expression_value": "not-a-number", "expression_stdev": "not-a-number", "cds": "NOT_READ", "protein_sequence": "NOT_READ"},
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    records = [{"construct_id": "dev1", "position": "10"}]
    model.attach_external_features({"source": {"raw_feature_csv": str(path), "raw_feature_csv_sha256": digest}}, records)
    assert records[0]["pure_features"] == {"RCS": -1.0, "delta_rcs_vs_wt": 1.0, "abs_delta_rcs_vs_wt": 1.0}
    assert len(records) == 1 and records[0]["construct_id"] != "test1"


def test_fit_predict_is_deterministic_and_finite() -> None:
    matrix = np.asarray([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [2.0, 4.0, 4.0], [3.0, 9.0, 9.0], [4.0, 16.0, 16.0]])
    y = np.asarray([0.0, 1.0, 1.5, 2.0, 2.5])
    train = np.asarray([0, 1, 2, 3])
    evaluation = np.asarray([4])
    first = model.fit_predict(matrix, y, train, evaluation, 1.0)
    second = model.fit_predict(matrix, y, train, evaluation, 1.0)
    np.testing.assert_array_equal(first, second)
    assert first.shape == (1,) and np.isfinite(first).all()


def test_nested_pure_returns_one_prediction_per_id_and_125_fits() -> None:
    records = []
    for i in range(20):
        rcs = float(i) / 10.0
        records.append({"construct_id": f"c{i}", "position": str(i), "y": float(i % 5), "folds": {"7": i % 5}, "pure_features": model.pure_features(rcs, -1.0)})
    matrix = model.feature_matrix(records)
    y = np.asarray([row["y"] for row in records])
    cfg = {"nested_cv": {"outer_folds": 5, "inner_folds": 4, "alpha_grid": [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]}}
    result = model.nested_pure(records, matrix, y, "7", cfg)
    assert len(result["predictions"]) == 20
    assert set(result["predictions"]) == {row["construct_id"] for row in records}
    assert np.isfinite(list(result["predictions"].values())).all()
    assert result["fit_count"] == 125
    assert len(result["selections"]) == 5


def test_favorable_direction_is_not_reversed() -> None:
    assert model.favorable({"delta_spearman": 0.01, "delta_rmse": -0.01})
    assert not model.favorable({"delta_spearman": -0.01, "delta_rmse": -0.01})
    assert not model.favorable({"delta_spearman": 0.01, "delta_rmse": 0.01})


def test_support_requires_ci_holm_and_sensitivity() -> None:
    comparison = {"delta_spearman_ci95": [0.01, 0.02], "delta_rmse_ci95": [-0.02, -0.01], "holm_p_spearman": 0.01, "holm_p_rmse": 0.01, "sensitivity_signs_ok": True}
    assert model.supported(comparison)
    for key, value in [("sensitivity_signs_ok", False), ("holm_p_spearman", 0.05), ("delta_spearman_ci95", [0.0, 0.02]), ("delta_rmse_ci95", [-0.02, 0.0])]:
        changed = dict(comparison)
        changed[key] = value
        assert not model.supported(changed)


def test_frozen_protocol_keeps_no_go_and_three_comparisons() -> None:
    root = Path(__file__).resolve().parents[2]
    cfg = json.loads((root / "configs/a8_rk03_mage_pure_external_nested_cv_protocol_v1.json").read_text())
    assert cfg["frozen_before_pure_external_model_fitting"] is True
    assert cfg["development_data"]["test_construct_feature_rows_selected"] is False
    assert cfg["development_data"]["raw_expression_value_or_stdev_fields_accessed"] is False
    assert cfg["pure_external_arm"]["categorical_features"] == []
    assert cfg["pure_external_arm"]["position_or_position_interactions_included"] is False
    assert len(cfg["primary_comparisons"]) == 3
    assert cfg["gate_and_interpretation"]["test_authorized"] is False
    assert cfg["gate_and_interpretation"]["rk_g1_pass"] is False
    assert cfg["gate_and_interpretation"]["generator_training_authorized"] is False


def test_old_arm_names_are_not_renamed() -> None:
    assert model.OLD_ARMS == ["intrinsic", "rcs_only", "full_mechanism"]
    assert model.PURE == "pure_external_rcs"
    assert model.PURE not in model.OLD_ARMS
