import ast
import csv
import hashlib
import json
import math
import shutil
from collections import Counter
from pathlib import Path

import pytest

from scripts import a10_01_goodman_baselines as baseline
from scripts import a10_01_goodman_freeze_splits as freeze
from scripts import a10_01_verify_goodman_baselines as verifier


ROOT = Path(__file__).resolve().parents[1]
SPLIT_PROTOCOL = ROOT / "configs" / "a10_01_goodman_split_protocol_v1.json"
BASELINE_PROTOCOL = ROOT / "configs" / "a10_01_goodman_baseline_protocol_v1.json"
CLEAN_COLUMNS = [
    "Name",
    "Gene",
    "CDS.seq",
    "Count.Prot",
    "Fltr.SetGood",
    "CAI",
    "GC",
    "dG",
    "tAI",
    "Promoter",
    "RBS.Display",
]
CODONS = [
    first + second + third
    for first in "ACGT"
    for second in "ACGT"
    for third in "ACGT"
]


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def synthetic_rows():
    rows = []
    for gene_index in range(10):
        for replicate in range(4):
            cai = 0.25 + 0.025 * gene_index + 0.01 * replicate
            gc = 0.35 + 0.015 * gene_index - 0.005 * replicate
            dg = -8.0 + 0.2 * gene_index - 0.1 * replicate
            tai = 0.2 + 0.03 * gene_index + 0.02 * replicate
            log_outcome = (
                1.5 + 1.2 * cai - 0.8 * gc - 0.04 * dg + 0.5 * tai + 0.03 * replicate
            )
            rows.append({
                "Name": f"synthetic-name-{gene_index:02d}",
                "Gene": f"synthetic-gene-{gene_index:02d}",
                "CDS.seq": "ATG" + CODONS[(gene_index * 4 + replicate) % 64] + "GCT" * 9,
                "Count.Prot": format(math.expm1(log_outcome), ".17g"),
                "Fltr.SetGood": (
                    "FALSE" if gene_index in (0, 1) and replicate == 3 else "TRUE"
                ),
                "CAI": str(cai),
                "GC": str(gc),
                "dG": str(dg),
                "tAI": str(tai),
                "Promoter": f"synthetic-promoter-{gene_index % 3}",
                "RBS.Display": f"synthetic-rbs-{replicate % 2}",
            })
    return rows


def write_clean(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CLEAN_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def verify(case):
    return verifier.verify_goodman_baselines(
        case["clean"], case["split"], case["predictions"], case["run"],
    )


def verifier_arguments(case, output):
    return [
        "--clean-csv", str(case["clean"]),
        "--split-json", str(case["split"]),
        "--protocol-json", str(case["baseline_protocol"]),
        "--predictions-csv", str(case["predictions"]),
        "--run-report-json", str(case["run"]),
        "--output", str(output),
    ]


@pytest.fixture(scope="module")
def synthetic_case(tmp_path_factory):
    root = tmp_path_factory.mktemp("goodman_synthetic_baselines")
    rows = synthetic_rows()
    clean = root / "synthetic_goodman_clean.csv"
    write_clean(clean, rows)
    protocol = load_json(SPLIT_PROTOCOL)
    clean_contract = protocol["inputs"]["clean_csv"]
    clean_contract["sha256"] = sha256_file(clean)
    clean_contract["expected_data_rows"] = len(rows)
    gene_counts = Counter(row["Gene"] for row in rows)
    clean_contract["expected_gene_count"] = len(gene_counts)
    clean_contract["expected_rows_per_gene"] = sorted(set(gene_counts.values()))
    clean_contract["expected_unique_exact_cds"] = len({row["CDS.seq"] for row in rows})
    protocol_path = root / "synthetic_split_protocol.json"
    write_json(protocol_path, protocol)
    assignment = root / "frozen" / "assignment.csv"
    split = root / "frozen" / "split.json"
    assert freeze.main([
        "--clean-csv", str(clean),
        "--protocol", str(protocol_path),
        "--assignment-csv", str(assignment),
        "--split-json", str(split),
    ]) == 0
    baseline_protocol = load_json(BASELINE_PROTOCOL)
    baseline_protocol["inputs"]["clean_csv"].update({
        "sha256": sha256_file(clean),
        "expected_data_rows": len(rows),
        "expected_setgood_rows": sum(row["Fltr.SetGood"] == "TRUE" for row in rows),
    })
    baseline_protocol["inputs"]["split_json"]["sha256"] = sha256_file(split)
    baseline_protocol_path = root / "synthetic_baseline_protocol.json"
    write_json(baseline_protocol_path, baseline_protocol)
    output_dir = root / "baseline_outputs"
    assert baseline.main([
        "--clean-csv", str(clean),
        "--split-json", str(split),
        "--protocol", str(baseline_protocol_path),
        "--output-dir", str(output_dir),
    ]) == 0
    case = {
        "root": root,
        "clean": clean,
        "split": split,
        "baseline_protocol": baseline_protocol_path,
        "output_dir": output_dir,
        "predictions": output_dir / "predictions.csv",
        "run": output_dir / "run_report.json",
        "verification": root / "verification.json",
        "rows": rows,
    }
    assert verifier.main(verifier_arguments(case, case["verification"])) == 0
    case["result"] = load_json(case["verification"])
    return case


def copy_case(synthetic_case, tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    paths = {"baseline_protocol": synthetic_case["baseline_protocol"]}
    for key in ("clean", "split", "predictions", "run"):
        destination = tmp_path / synthetic_case[key].name
        shutil.copyfile(synthetic_case[key], destination)
        paths[key] = destination
    return paths


def read_predictions(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_predictions(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=baseline.PREDICTION_COLUMNS, lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def synchronize_prediction_sha(case):
    run = load_json(case["run"])
    run["predictions"]["sha256"] = sha256_file(case["predictions"])
    write_json(case["run"], run)


def test_verifier_does_not_import_training_or_project_code():
    tree = ast.parse(Path(verifier.__file__).read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(
        name == "scripts" or name.startswith(("scripts.", "codonflow", "sklearn", "scipy", "numpy"))
        for name in imported
    )


def test_synthetic_end_to_end_passes_and_recomputes_every_arm_and_outer(synthetic_case):
    result = synthetic_case["result"]
    run = load_json(synthetic_case["run"])
    eligible = sum(row["Fltr.SetGood"] == "TRUE" for row in synthetic_case["rows"])

    assert result["passed"], result.get("error")
    assert all(result["checks"].values())
    assert eligible == 38
    assert result["recomputed"]["eligible_SetGood_rows"] == eligible
    assert result["recomputed"]["prediction_rows"] == len(baseline.ARMS) * eligible
    assert len(result["recomputed"]["outer_results"]) == 5 * len(baseline.ARMS)
    assert set(result["recomputed"]["per_arm_prediction_rows"]) == set(baseline.ARMS)
    assert set(result["recomputed"]["per_arm_prediction_rows"].values()) == {eligible}
    assert run["data"]["outcome"]["source_column"] == "Count.Prot"
    assert run["data"]["outcome"]["transform"] == "log1p"
    assert run["data"]["analysis_filter"] == {
        "column": "Fltr.SetGood",
        "operator": "==",
        "value": "TRUE",
        "applied_in_memory_for_primary_analysis_only": True,
    }
    assert run["data"]["raw_or_clean_filtering_applied"] is False
    assert run["data"]["clean_file_modified"] is False
    assert run["scope"]["development_benchmark"] is True
    assert run["scope"]["untouched_evaluation"] is False
    assert run["scope"]["mechanism_evidence"] is False
    assert run["scope"]["sota_claim"] is False
    assert len(run["outer_results"]) == 35
    assert all(result["metrics"]["spearman"] is None for result in run["outer_results"] if result["arm"] == "constant")
    assert all(
        0 <= fit["n_features"] <= baseline.MAX_FULL_FEATURES
        for fit in run["fit_records"]
    )
    hist_fits = [fit for fit in run["fit_records"] if fit["arm"] == "histgb_full"]
    assert hist_fits
    assert all(type(fit["n_iter"]) is int and 1 <= fit["n_iter"] <= 500 for fit in hist_fits)
    assert all(fit["max_iter"] == 500 for fit in hist_fits)
    assert all(fit["early_stopping"]["enabled"] is True for fit in hist_fits)
    ridge_results = [result for result in run["outer_results"] if result["arm"] == "ridge_full"]
    assert all(result["selection"]["selected_config"]["alpha"] in baseline.RIDGE_ALPHAS for result in ridge_results)
    assert all(len(result["selection"]["candidates"]) == 4 for result in ridge_results)
    assert all(
        len(candidate["inner_fold_results"]) == 4
        for result in ridge_results
        for candidate in result["selection"]["candidates"]
    )
    assert all(
        fit["wall_time_seconds"] >= 0 and fit["process_cpu_time_seconds"] >= 0
        for fit in run["fit_records"]
    )


def test_baseline_and_verifier_refuse_to_overwrite_outputs(synthetic_case, tmp_path):
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        baseline.main([
            "--clean-csv", str(synthetic_case["clean"]),
            "--split-json", str(synthetic_case["split"]),
            "--protocol", str(synthetic_case["baseline_protocol"]),
            "--output-dir", str(synthetic_case["output_dir"]),
        ])
    original_run = synthetic_case["run"].read_bytes()
    original_verification = synthetic_case["verification"].read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        verifier.main(verifier_arguments(synthetic_case, synthetic_case["verification"]))
    assert synthetic_case["run"].read_bytes() == original_run
    assert synthetic_case["verification"].read_bytes() == original_verification
    assert not (tmp_path / "unexpected").exists()


def test_prediction_tampering_is_recomputed_even_with_synchronized_sha(synthetic_case, tmp_path):
    case = copy_case(synthetic_case, tmp_path)
    rows = read_predictions(case["predictions"])
    rows[0]["prediction_log1p_Count.Prot"] = str(
        float(rows[0]["prediction_log1p_Count.Prot"]) + 1.0,
    )
    write_predictions(case["predictions"], rows)
    synchronize_prediction_sha(case)

    result = verify(case)

    assert not result["passed"]
    assert result["error"]["check"].startswith("recomputed_")
    assert not result["checks"][result["error"]["check"]]


@pytest.mark.parametrize("metric", ["spearman", "rmse", "top_decile_enrichment"])
def test_reported_metric_tampering_is_detected(synthetic_case, tmp_path, metric):
    case = copy_case(synthetic_case, tmp_path)
    run = load_json(case["run"])
    target = next(
        result for result in run["outer_results"]
        if result["metrics"][metric] is not None
    )
    target["metrics"][metric] += 0.25
    write_json(case["run"], run)

    result = verify(case)

    expected_check = {
        "spearman": "recomputed_spearman",
        "rmse": "recomputed_rmse",
        "top_decile_enrichment": "recomputed_top_decile_enrichment",
    }[metric]
    assert not result["passed"]
    assert result["error"]["check"] == expected_check
    assert not result["checks"][expected_check]


def test_prediction_row_deletion_and_setgood_tampering_are_detected(synthetic_case, tmp_path):
    deleted = copy_case(synthetic_case, tmp_path / "deleted")
    rows = read_predictions(deleted["predictions"])
    write_predictions(deleted["predictions"], rows[:-1])
    synchronize_prediction_sha(deleted)
    deleted_result = verify(deleted)
    assert not deleted_result["passed"]
    assert deleted_result["error"]["check"] == "prediction_row_conservation"

    flagged = copy_case(synthetic_case, tmp_path / "flagged")
    rows = read_predictions(flagged["predictions"])
    rows[0]["Fltr.SetGood"] = "FALSE"
    write_predictions(flagged["predictions"], rows)
    synchronize_prediction_sha(flagged)
    flagged_result = verify(flagged)
    assert not flagged_result["passed"]
    assert flagged_result["error"]["check"] == "prediction_rows_only_setgood"


def test_clean_and_split_sha_tampering_are_detected(synthetic_case, tmp_path):
    clean_case = copy_case(synthetic_case, tmp_path / "clean")
    with clean_case["clean"].open("ab") as handle:
        handle.write(b"\n")
    clean_result = verify(clean_case)
    assert not clean_result["passed"]
    assert clean_result["error"]["check"] in {"baseline_protocol_sha256", "clean_sha256"}

    split_case = copy_case(synthetic_case, tmp_path / "split")
    split = load_json(split_case["split"])
    split["input_sha256"]["clean_csv"] = "0" * 64
    write_json(split_case["split"], split)
    split_result = verify(split_case)
    assert not split_result["passed"]
    assert split_result["error"]["check"] in {
        "baseline_protocol_sha256", "clean_sha256", "split_sha256",
    }


def test_non_inner_selected_configuration_is_rejected(synthetic_case, tmp_path):
    case = copy_case(synthetic_case, tmp_path)
    run = load_json(case["run"])
    result = next(result for result in run["outer_results"] if result["arm"] == "ridge_full")
    selection = result["selection"]
    original = selection["selected_candidate_index"]
    replacement = (original + 1) % len(selection["candidates"])
    selection["selected_candidate_index"] = replacement
    selection["selected_config"] = selection["candidates"][replacement]["config"]
    write_json(case["run"], run)

    verified = verify(case)

    assert not verified["passed"]
    assert verified["error"]["check"] == "inner_only_configuration_selection"


def test_outer_fit_gene_hash_tampering_is_rejected(synthetic_case, tmp_path):
    case = copy_case(synthetic_case, tmp_path)
    run = load_json(case["run"])
    fit = next(fit for fit in run["fit_records"] if fit["selection_role"] == "outer_final_refit")
    fit["fit_train_gene_sha256"] = "0" * 64
    write_json(case["run"], run)

    result = verify(case)

    assert not result["passed"]
    assert result["error"]["check"] == "outer_test_isolation"


def test_histgb_iteration_and_cost_tampering_are_rejected(synthetic_case, tmp_path):
    iteration_case = copy_case(synthetic_case, tmp_path / "iteration")
    run = load_json(iteration_case["run"])
    fit = next(fit for fit in run["fit_records"] if fit["arm"] == "histgb_full")
    fit["n_iter"] = None
    write_json(iteration_case["run"], run)
    iteration_result = verify(iteration_case)
    assert not iteration_result["passed"]
    assert iteration_result["error"]["check"] == "histgb_actual_iterations"

    cost_case = copy_case(synthetic_case, tmp_path / "cost")
    run = load_json(cost_case["run"])
    run["fit_records"][0]["wall_time_seconds"] = -1.0
    write_json(cost_case["run"], run)
    cost_result = verify(cost_case)
    assert not cost_result["passed"]
    assert cost_result["error"]["check"] == "fit_and_prediction_costs"


def test_legacy_rbs_feature_contract_tampering_is_rejected(synthetic_case, tmp_path):
    case = copy_case(synthetic_case, tmp_path)
    run = load_json(case["run"])
    run["features"]["categorical"] = ["Promoter", "RBS"]
    write_json(case["run"], run)

    result = verify(case)

    assert not result["passed"]
    assert result["error"]["check"] == "feature_contract"
    assert not result["checks"]["feature_contract"]


def test_failed_cli_writes_new_failure_json_without_overwrite(synthetic_case, tmp_path):
    case = copy_case(synthetic_case, tmp_path)
    run = load_json(case["run"])
    run["data"]["outcome"]["transform"] = "log"
    write_json(case["run"], run)
    output = tmp_path / "failed_verification.json"

    assert verifier.main(verifier_arguments(case, output)) == 1
    result = load_json(output)
    assert not result["passed"]
    assert result["error"]["check"] == "outcome_contract"
    original = output.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        verifier.main(verifier_arguments(case, output))
    assert output.read_bytes() == original
