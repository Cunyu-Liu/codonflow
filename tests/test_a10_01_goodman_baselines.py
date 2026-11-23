import csv
import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np
import pytest

from scripts import a10_01_goodman_baselines as baseline
from scripts import a10_01_goodman_e0_audit_v2 as audit
from scripts import a10_01_goodman_freeze_splits as freeze


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "configs" / "a10_01_goodman_baseline_protocol_v1.json"
SAFE_CODONS = ["GCT", "GCC", "GCA", "GCG", "GGT", "GGC", "GGA", "GGG"]


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def encode_csv(rows):
    columns = [column for column in rows[0] if not column.startswith("_")]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row[column] for column in columns})
    return buffer.getvalue().encode("utf-8")


def synthetic_row(index, gene=None, raw=None, flag="TRUE"):
    raw = float(1 + index * index) if raw is None else float(raw)
    return {
        "Name": f"synthetic-name-{index:03d}",
        "Gene": gene or f"synthetic-gene-{index // 4:02d}",
        "CDS.seq": "ATG" + "".join(
            SAFE_CODONS[(index >> (2 * position)) & 3] for position in range(10)
        ),
        "Count.Prot": str(raw),
        "Fltr.SetGood": flag,
        "CAI": str(0.25 + 0.005 * index),
        "GC": str(0.4 + 0.002 * (index % 17)),
        "dG": str(-2.0 - 0.03 * index),
        "tAI": str(0.3 + 0.003 * (index % 23)),
        "Promoter": f"promoter-{index % 3}",
        "RBS.Display": f"rbs-{index % 2}",
        "_clean_row_index": index,
    }


def prepared(row):
    count = float(row["Count.Prot"])
    return {
        "clean_row_index": row["_clean_row_index"],
        "Name": row["Name"], "Gene": row["Gene"], "CDS.seq": row["CDS.seq"],
        "Count.Prot.token": row["Count.Prot"], "Count.Prot": count,
        "y": math.log1p(count), "Fltr.SetGood": row["Fltr.SetGood"],
        **{feature: float(row[feature]) for feature in baseline.NUMERIC_FEATURES},
        **{feature: row[feature] for feature in baseline.CATEGORICAL_FEATURES},
    }


def synthetic_case(tmp_path):
    rows = []
    index = 0
    for gene_index in range(15):
        for _ in range(4):
            rows.append(synthetic_row(index, gene=f"synthetic-gene-{gene_index:02d}"))
            index += 1
    for gene_index in range(5):
        excluded = synthetic_row(
            index, gene=f"synthetic-gene-{gene_index:02d}", raw=-999, flag="FALSE",
        )
        excluded["CAI"] = "not-a-number"
        rows.append(excluded)
        index += 1
    clean_bytes = encode_csv(rows)
    clean = tmp_path / "synthetic_goodman_clean.csv"
    clean.write_bytes(clean_bytes)
    records = [(row["Name"], row["Gene"], row["CDS.seq"]) for row in rows]
    _, outer_reports = freeze.build_partition(records)
    split = {
        "schema": baseline.SPLIT_SCHEMA,
        "protocol": baseline.SPLIT_PROTOCOL,
        "untouched_inputs_read": False,
        "outcome_columns_used_for_splitting": False,
        "input_sha256": {"clean_csv": sha256(clean_bytes)},
        "input": {"data_rows": len(rows), "gene_count": 15},
        "grouping": {"outer_folds": 5, "inner_folds_per_outer": 4},
        "outer_folds": outer_reports,
    }
    split_path = tmp_path / "synthetic_frozen_split.json"
    split_path.write_bytes(baseline.json_bytes(split))
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    protocol["inputs"]["clean_csv"].update({
        "sha256": sha256(clean_bytes), "expected_data_rows": len(rows),
        "expected_setgood_rows": sum(row["Fltr.SetGood"] == "TRUE" for row in rows),
    })
    protocol["inputs"]["split_json"]["sha256"] = sha256(split_path.read_bytes())
    protocol["models"]["ridge"]["alpha_grid"] = list(baseline.RIDGE_ALPHAS)
    protocol["models"]["histgb"].update({
        "learning_rate_grid": list(baseline.HISTGB_LEARNING_RATES),
        "l2_regularization_grid": list(baseline.HISTGB_L2_VALUES),
        "max_iter": baseline.HISTGB_MAX_ITER,
        "n_iter_no_change": baseline.HISTGB_N_ITER_NO_CHANGE,
        "validation_fraction": baseline.HISTGB_VALIDATION_FRACTION,
    })
    protocol_path = tmp_path / "synthetic_baseline_protocol.json"
    protocol_path.write_bytes(baseline.json_bytes(protocol))
    return {
        "rows": rows, "clean": clean, "clean_bytes": clean_bytes,
        "split": split, "split_path": split_path, "protocol": protocol,
        "protocol_path": protocol_path, "output": tmp_path / "new_benchmark_outputs",
        "args": [
            "--clean-csv", str(clean), "--split-json", str(split_path),
            "--protocol", str(protocol_path), "--output-dir", str(tmp_path / "new_benchmark_outputs"),
        ],
    }


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_frozen_protocol_preserves_outcome_scope_and_controlled_budget():
    protocol = baseline.load_protocol(PROTOCOL_PATH)
    assert protocol["outcome"]["source_column"] == "Count.Prot"
    assert protocol["outcome"]["transform"] == "log1p"
    assert protocol["outcome"]["raw_clean_filtering_history_changed"] is False
    assert protocol["inputs"]["clean_csv"]["filter_applied_by_cleaning"] is False
    assert protocol["inputs"]["clean_csv"]["filter_applied_by_baseline_after_read"] is True
    assert protocol["inputs"]["split_json"]["outer_folds"] == 5
    assert protocol["inputs"]["split_json"]["inner_folds"] == 4
    assert protocol["features"]["categorical_columns"] == ["Promoter", "RBS.Display"]
    assert protocol["features"]["max_encoded_features"] == 740
    assert protocol["models"]["histgb"]["early_stopping"] is True
    assert protocol["models"]["histgb"]["reaching_max_iter_is_convergence"] is False
    assert protocol["study"]["benchmark_role"] == "development_only"
    assert protocol["study"]["final_untouched"] is False
    assert protocol["study"]["mechanism_claim_eligible"] is False
    assert protocol["study"]["sota_claim_eligible"] is False
    assert protocol["inputs"]["untouched_inputs_read"] is False


def test_production_75_column_header_uses_rbs_display_for_categorical_feature(tmp_path):
    header = [
        *audit.REQUIRED_COLUMNS,
        "RBS.Display",
        *[f"Extra.{index:02d}" for index in range(1, 21)],
    ]
    assert len(audit.REQUIRED_COLUMNS) == 54
    assert len(header) == len(set(header)) == 75
    assert "RBS" not in header
    assert "RBS.Display" in header
    assert "RBS.seq" in header
    assert set(baseline.REQUIRED_CLEAN_COLUMNS) <= set(header)
    source = synthetic_row(0)
    row = {column: "" for column in header}
    row.update({column: value for column, value in source.items() if not column.startswith("_")})
    row["RBS.seq"] = "AAGGAG"
    clean = tmp_path / "synthetic_75_column_header.csv"
    with clean.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerow(row)

    clean_rows = baseline.read_clean(clean)
    eligible = baseline.prepare_records(clean_rows)
    transformer = baseline.FullFeatureTransformer().fit(eligible)

    assert eligible[0]["RBS.Display"] == "rbs-0"
    assert "RBS" not in eligible[0]
    assert transformer.category_levels["RBS.Display"] == ["rbs-0"]
    assert "RBS.seq" not in transformer.category_levels


def test_full_preprocessing_uses_only_corresponding_train_statistics():
    train = [prepared(synthetic_row(index)) for index in range(4)]
    for row, value in zip(train, [1.0, 2.0, 3.0, 4.0]):
        row["CAI"] = value
    test = [prepared(synthetic_row(100)), prepared(synthetic_row(101))]
    test[0]["CAI"] = 100.0
    test[0]["Promoter"] = "never-observed-in-train"

    transformer = baseline.FullFeatureTransformer()
    train_matrix = transformer.fit_transform(train)
    test_matrix = transformer.transform(test)

    assert transformer.means[0] == pytest.approx(2.5)
    assert transformer.scales[0] == pytest.approx(np.std([1.0, 2.0, 3.0, 4.0]))
    numeric_offset = baseline.SEQUENCE_POSITIONS * len(baseline.CODONS)
    assert test_matrix[0, numeric_offset] == pytest.approx((100.0 - 2.5) / transformer.scales[0])
    assert test_matrix[0, numeric_offset] != pytest.approx((100.0 - 50.5) / transformer.scales[0])
    assert train_matrix.shape[1] == test_matrix.shape[1] == transformer.n_features
    assert transformer.n_features <= baseline.MAX_FULL_FEATURES
    assert "never-observed-in-train" not in transformer.category_levels["Promoter"]


def test_constant_uses_train_mean_and_univariate_direction_is_train_fitted():
    records = [prepared(synthetic_row(index, raw=value)) for index, value in enumerate([1, 3, 7, 15])]
    predict, details = baseline.fit_model(records, "constant", {})
    expected = math.fsum(record["y"] for record in records) / len(records)
    assert details["wall_time_seconds"] >= 0
    assert details["process_cpu_time_seconds"] >= 0
    assert predict(records) == pytest.approx(np.full(len(records), expected))

    increasing = [prepared(synthetic_row(index)) for index in range(6)]
    for index, record in enumerate(increasing):
        record["y"] = 2.0 + index
    _, positive = baseline.fit_model(increasing, "univariate_CAI", {"feature": "CAI"})
    assert positive["train_fitted_direction"] == "positive"
    assert positive["train_fitted_standardized_coefficient"] > 0
    for index, record in enumerate(increasing):
        record["y"] = 10.0 - index
    _, negative = baseline.fit_model(increasing, "univariate_CAI", {"feature": "CAI"})
    assert negative["train_fitted_direction"] == "negative"
    assert negative["train_fitted_standardized_coefficient"] < 0


def test_inner_selection_uses_mean_rmse_then_spearman_and_deterministic_config():
    candidates = [
        {"config": {"alpha": 1.0}, "mean_inner_rmse": 0.2, "mean_inner_spearman": 0.8},
        {"config": {"alpha": 10.0}, "mean_inner_rmse": 0.1, "mean_inner_spearman": 0.1},
        {"config": {"alpha": 100.0}, "mean_inner_rmse": 0.2, "mean_inner_spearman": 0.9},
    ]
    assert baseline.select_candidate(candidates) == 1
    candidates[1]["mean_inner_rmse"] = 0.2
    assert baseline.select_candidate(candidates) == 2
    candidates[2]["mean_inner_spearman"] = 0.8
    assert baseline.select_candidate(candidates) == 0


def test_outer_metrics_cover_spearman_rmse_and_raw_count_top_decile_enrichment():
    records = [prepared(synthetic_row(index, raw=index + 1)) for index in range(20)]
    observed = np.asarray([record["y"] for record in records])
    perfect = baseline.regression_metrics(records, observed)
    reversed_metrics = baseline.regression_metrics(records, observed[::-1])
    constant = baseline.regression_metrics(records, np.full(len(records), np.mean(observed)))

    assert perfect["spearman"] == pytest.approx(1.0)
    assert perfect["rmse"] == pytest.approx(0.0)
    assert perfect["top_decile_count"] == 2
    assert perfect["top_decile_enrichment"] == pytest.approx(19.5 / 10.5)
    assert reversed_metrics["spearman"] == pytest.approx(-1.0)
    assert reversed_metrics["top_decile_enrichment"] == pytest.approx(1.5 / 10.5)
    assert constant["spearman"] is None
    assert constant["rmse"] == pytest.approx(np.std(observed))


def test_outer_test_outcomes_cannot_change_inner_selection_or_final_predictions(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(baseline, "ARMS", ("ridge_full",))
    monkeypatch.setattr(baseline, "RIDGE_ALPHAS", (0.1, 10.0))
    case = synthetic_case(tmp_path)
    original_validate = baseline.validate_split
    test_genes = original_validate(case["split"], case["rows"])[0]["test"]
    monkeypatch.setattr(
        baseline, "validate_split",
        lambda split, clean_rows: original_validate(split, clean_rows)[:1],
    )
    first_payload, first = baseline.run_benchmark(
        case["clean"], case["split_path"], case["protocol_path"],
    )

    for row in case["rows"]:
        if row["Gene"] in test_genes and row["Fltr.SetGood"] == "TRUE":
            row["Count.Prot"] = str(float(row["Count.Prot"]) + 10000)
    case["clean"].write_bytes(encode_csv(case["rows"]))
    case["split"]["input_sha256"]["clean_csv"] = sha256(case["clean"].read_bytes())
    case["split_path"].write_bytes(baseline.json_bytes(case["split"]))
    case["protocol"]["inputs"]["clean_csv"]["sha256"] = sha256(case["clean"].read_bytes())
    case["protocol"]["inputs"]["split_json"]["sha256"] = sha256(case["split_path"].read_bytes())
    case["protocol_path"].write_bytes(baseline.json_bytes(case["protocol"]))
    second_payload, second = baseline.run_benchmark(
        case["clean"], case["split_path"], case["protocol_path"],
    )

    assert first["outer_results"][0]["selection"] == second["outer_results"][0]["selection"]
    first_predictions = list(csv.DictReader(io.StringIO(first_payload.decode("utf-8"))))
    second_predictions = list(csv.DictReader(io.StringIO(second_payload.decode("utf-8"))))
    assert {row["Gene"] for row in first_predictions} == test_genes
    assert [row["prediction_log1p_Count.Prot"] for row in first_predictions] == [
        row["prediction_log1p_Count.Prot"] for row in second_predictions
    ]
    assert [row["observed_log1p_Count.Prot"] for row in first_predictions] != [
        row["observed_log1p_Count.Prot"] for row in second_predictions
    ]


def test_complete_synthetic_5x4_run_outputs_schema_iterations_sha_and_no_overwrite(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(baseline, "RIDGE_ALPHAS", (0.1, 10.0))
    monkeypatch.setattr(baseline, "HISTGB_LEARNING_RATES", (0.05,))
    monkeypatch.setattr(baseline, "HISTGB_L2_VALUES", (0.0,))
    monkeypatch.setattr(baseline, "HISTGB_MAX_ITER", 20)
    monkeypatch.setattr(baseline, "HISTGB_N_ITER_NO_CHANGE", 3)
    monkeypatch.setattr(baseline, "HISTGB_VALIDATION_FRACTION", 0.25)
    case = synthetic_case(tmp_path)
    original_clean = case["clean"].read_bytes()

    assert baseline.main(case["args"]) == 0

    output = case["output"]
    assert {path.name for path in output.iterdir()} == {"predictions.csv", "run_report.json"}
    assert case["clean"].read_bytes() == original_clean
    predictions = read_csv(output / "predictions.csv")
    report = json.loads((output / "run_report.json").read_text(encoding="utf-8"))
    good_rows = [row for row in case["rows"] if row["Fltr.SetGood"] == "TRUE"]
    excluded_names = {row["Name"] for row in case["rows"] if row["Fltr.SetGood"] == "FALSE"}
    assert list(predictions[0]) == list(baseline.PREDICTION_COLUMNS)
    assert len(predictions) == len(good_rows) * len(baseline.ARMS) == 420
    assert {row["arm"] for row in predictions} == set(baseline.ARMS)
    assert {row["outer_fold"] for row in predictions} == {"0", "1", "2", "3", "4"}
    assert not {row["Name"] for row in predictions} & excluded_names
    assert all(row["Fltr.SetGood"] == "TRUE" for row in predictions)
    for row in predictions[:20]:
        assert float(row["observed_log1p_Count.Prot"]) == pytest.approx(math.log1p(float(row["Count.Prot"])))
    assert len(report["outer_results"]) == 35
    assert len(report["fit_records"]) == 5 * (4 * 8 + 7)
    assert all(record["wall_time_seconds"] >= 0 for record in report["fit_records"])
    assert all(record["process_cpu_time_seconds"] >= 0 for record in report["fit_records"])
    assert all(record["outer_test_used_for_fit"] is False for record in report["fit_records"])
    assert all(record["outer_test_used_for_preprocessing"] is False for record in report["fit_records"])
    assert all(record["outer_test_used_for_selection"] is False for record in report["fit_records"])
    for outer in report["outer_results"]:
        assert outer["selection"]["outer_test_used"] is False
        assert len(outer["selection"]["candidates"]) >= 1
        for candidate in outer["selection"]["candidates"]:
            assert len(candidate["inner_fold_results"]) == 4
        assert outer["metrics"]["rmse"] >= 0
        assert outer["metrics"]["top_decile_enrichment"] >= 0
    hist_fits = [record for record in report["fit_records"] if record["arm"] == "histgb_full"]
    assert len(hist_fits) == 5 * (4 + 1)
    assert all(0 < record["n_iter"] <= 20 for record in hist_fits)
    assert all(record["max_iter"] == 20 for record in hist_fits)
    assert all(record["early_stopping"]["enabled"] is True for record in hist_fits)
    assert all(
        record["early_stopping"]["validation_scope"] == "corresponding_fit_train_rows_only"
        for record in hist_fits
    )
    assert report["status"] == "completed_development_benchmark"
    assert report["scope"] == {
        "development_benchmark": True, "untouched_evaluation": False,
        "mechanism_evidence": False, "sota_claim": False,
        "supported_ood": "Gene-grouped N-terminal fragment construct OOD",
        "protein_ood": False, "full_length_cds": False, "native_utr": False,
    }
    assert report["data"]["clean_data_rows"] == 65
    assert report["data"]["eligible_SetGood_rows"] == 60
    assert report["data"]["excluded_non_SetGood_rows"] == 5
    assert report["data"]["clean_sha256"] == sha256(original_clean)
    assert report["data"]["split_sha256"] == sha256(case["split_path"].read_bytes())
    assert report["data"]["protocol_sha256"] == sha256(case["protocol_path"].read_bytes())
    assert report["data"]["untouched_inputs_read"] is False
    assert report["data"]["raw_or_clean_filtering_applied"] is False
    assert report["git"]["head_sha"]
    assert report["git"]["baseline_script_sha256"] == sha256(
        (ROOT / "scripts" / "a10_01_goodman_baselines.py").read_bytes(),
    )
    assert report["environment"]["sklearn_version"]
    assert report["predictions"]["sha256"] == sha256((output / "predictions.csv").read_bytes())
    assert report["total_wall_time_seconds"] >= 0
    assert report["total_process_cpu_time_seconds"] >= 0

    report_bytes = (output / "run_report.json").read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        baseline.main(case["args"])
    assert (output / "run_report.json").read_bytes() == report_bytes
