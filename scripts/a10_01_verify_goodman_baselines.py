"""Independently recompute and audit Goodman baseline artifacts without refitting."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path


VERIFICATION_PROTOCOL = "a10_01_goodman_baseline_independent_verification_v1"
EXPECTED_RUN_SCHEMA = "a10-01-goodman-development-baseline-run-v1"
EXPECTED_RUN_PROTOCOL = "a10_01_goodman_baseline_protocol_v1"
EXPECTED_BASELINE_PROTOCOL_SCHEMA = "a10-01-goodman-baseline-protocol-v1"
EXPECTED_SPLIT_SCHEMA = "a10-01-goodman-frozen-nested-grouped-cv-v1"
EXPECTED_SPLIT_PROTOCOL = "a10_01_goodman_split_protocol_v1"
OUTER_FOLDS = 5
INNER_FOLDS = 4
ARMS = (
    "constant",
    "univariate_CAI",
    "univariate_GC",
    "univariate_dG",
    "univariate_tAI",
    "ridge_full",
    "histgb_full",
)
RIDGE_ALPHAS = (0.1, 1.0, 10.0, 100.0)
HISTGB_LEARNING_RATES = (0.05, 0.1)
HISTGB_L2_VALUES = (0.0, 1.0)
HISTGB_MAX_ITER = 500
MAX_FULL_FEATURES = 740
PREDICTION_COLUMNS = [
    "clean_row_index",
    "Name",
    "Gene",
    "outer_fold",
    "arm",
    "fit_id",
    "Fltr.SetGood",
    "Count.Prot",
    "observed_log1p_Count.Prot",
    "prediction_log1p_Count.Prot",
]
REQUIRED_CLEAN_COLUMNS = ("Name", "Gene", "CDS.seq", "Count.Prot", "Fltr.SetGood")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--clean-csv", required=True)
    parser.add_argument("--split-json", required=True)
    parser.add_argument("--protocol-json", help="Defaults to the protocol path recorded in the run report")
    parser.add_argument("--predictions-csv", required=True)
    parser.add_argument("--run-report-json", required=True)
    parser.add_argument("--output", required=True, help="New independent verification JSON")
    return parser.parse_args(argv)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def gene_set_sha256(genes):
    return hashlib.sha256("\n".join(sorted(genes)).encode("utf-8")).hexdigest()


def canonical_json_bytes(payload):
    return (json.dumps(
        payload, indent=2, ensure_ascii=False, allow_nan=False,
    ) + "\n").encode("utf-8")


def write_json_exclusive(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(canonical_json_bytes(payload))


def reject_nonfinite_json(value):
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="strict") as handle:
        payload = json.load(handle, parse_constant=reject_nonfinite_json)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def finite_float(token, label):
    try:
        value = float(token)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric, observed {token!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def close(observed, expected, tolerance=1e-10):
    if observed is None or expected is None:
        return observed is None and expected is None
    return (
        isinstance(observed, (int, float))
        and not isinstance(observed, bool)
        and math.isfinite(observed)
        and math.isclose(observed, expected, rel_tol=tolerance, abs_tol=tolerance)
    )


def read_clean(path):
    rows = []
    with Path(path).open("r", encoding="utf-8-sig", errors="strict", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("clean CSV is empty") from exc
        if any(not column for column in header) or len(set(header)) != len(header):
            raise ValueError("clean CSV has empty or duplicate columns")
        missing = [column for column in REQUIRED_CLEAN_COLUMNS if column not in header]
        if missing:
            raise ValueError(f"clean CSV is missing required columns: {missing}")
        indices = {column: header.index(column) for column in REQUIRED_CLEAN_COLUMNS}
        for values in reader:
            if len(values) != len(header):
                raise ValueError(f"clean CSV line {reader.line_num} has an invalid field count")
            row = {column: values[index] for column, index in indices.items()}
            row["clean_row_index"] = len(rows)
            rows.append(row)
    if not rows:
        raise ValueError("clean CSV has no rows")
    return rows


def read_predictions(path):
    rows = []
    with Path(path).open("r", encoding="utf-8-sig", errors="strict", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("prediction CSV is empty") from exc
        if header != PREDICTION_COLUMNS:
            raise ValueError(f"prediction CSV header must be exactly {PREDICTION_COLUMNS}")
        for values in reader:
            if len(values) != len(header):
                raise ValueError(
                    f"prediction CSV line {reader.line_num} has an invalid field count",
                )
            rows.append(dict(zip(header, values)))
    return rows


def validate_split(split, clean_rows):
    grouping = split.get("grouping", {})
    if (
        split.get("schema") != EXPECTED_SPLIT_SCHEMA
        or split.get("protocol") != EXPECTED_SPLIT_PROTOCOL
        or grouping.get("outer_folds") != OUTER_FOLDS
        or grouping.get("inner_folds_per_outer") != INNER_FOLDS
        or split.get("outcome_columns_used_for_splitting") is not False
        or split.get("untouched_inputs_read") is not False
    ):
        raise ValueError("frozen split identity or grouping contract is invalid")
    genes = {row["Gene"] for row in clean_rows}
    folds = split.get("outer_folds", [])
    if not isinstance(folds, list) or len(folds) != OUTER_FOLDS:
        raise ValueError("frozen split must contain five outer folds")
    partitions = []
    covered = set()
    for outer_index, fold in enumerate(folds):
        test = set(fold.get("test_genes", []))
        train = set(fold.get("train_genes", []))
        inner_mapping = fold.get("train_inner_folds", {})
        if (
            fold.get("outer_fold") != outer_index
            or not test
            or test & train
            or test | train != genes
            or covered & test
            or set(inner_mapping) != {str(index) for index in range(INNER_FOLDS)}
        ):
            raise ValueError(f"outer fold {outer_index} is invalid")
        inner = [set(inner_mapping[str(index)]) for index in range(INNER_FOLDS)]
        if (
            any(not fold_genes for fold_genes in inner)
            or set().union(*inner) != train
            or sum(map(len, inner)) != len(train)
        ):
            raise ValueError(f"outer fold {outer_index} inner folds are invalid")
        covered |= test
        partitions.append({"test": test, "train": train, "inner": inner})
    if covered != genes:
        raise ValueError("outer test folds do not cover all clean Genes")
    return partitions


def average_ranks(values):
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + 1 + end) / 2.0
        for position in range(start, end):
            ranks[order[position]] = rank
        start = end
    return ranks


def centered_sum(left, right):
    left_mean = math.fsum(left) / len(left)
    right_mean = math.fsum(right) / len(right)
    return (
        math.fsum((a - left_mean) * (b - right_mean) for a, b in zip(left, right)),
        math.fsum((a - left_mean) ** 2 for a in left),
        math.fsum((b - right_mean) ** 2 for b in right),
    )


def recompute_metrics(rows, clean_by_index):
    ordered = sorted(rows, key=lambda row: int(row["clean_row_index"]))
    observed = [math.log1p(clean_by_index[int(row["clean_row_index"])]["count_prot"]) for row in ordered]
    predicted = [float(row["prediction_log1p_Count.Prot"]) for row in ordered]
    observed_ranks = average_ranks(observed)
    predicted_ranks = average_ranks(predicted)
    cross, left_ss, right_ss = centered_sum(observed_ranks, predicted_ranks)
    spearman = cross / math.sqrt(left_ss * right_ss) if left_ss > 0 and right_ss > 0 else None
    rmse = math.sqrt(math.fsum(
        (actual - prediction) ** 2 for actual, prediction in zip(observed, predicted)
    ) / len(ordered))
    top_count = (len(ordered) + 9) // 10
    top_order = sorted(
        ordered,
        key=lambda row: (
            -float(row["prediction_log1p_Count.Prot"]),
            int(row["clean_row_index"]),
        ),
    )
    protein = [clean_by_index[int(row["clean_row_index"])]["count_prot"] for row in ordered]
    denominator = math.fsum(protein) / len(protein)
    numerator = math.fsum(
        clean_by_index[int(row["clean_row_index"])]["count_prot"]
        for row in top_order[:top_count]
    ) / top_count
    return {
        "spearman": spearman,
        "rmse": rmse,
        "top_decile_enrichment": numerator / denominator if denominator > 0 else None,
        "top_decile_count": top_count,
        "top_decile_observed_Count.Prot_mean": numerator,
        "all_observed_Count.Prot_mean": denominator,
    }


def expected_configs(arm):
    if arm == "constant":
        return [{}]
    if arm.startswith("univariate_"):
        return [{"feature": arm.removeprefix("univariate_")}]
    if arm == "ridge_full":
        return [{"alpha": alpha} for alpha in RIDGE_ALPHAS]
    return [
        {"learning_rate": learning_rate, "l2_regularization": l2_value}
        for learning_rate in HISTGB_LEARNING_RATES
        for l2_value in HISTGB_L2_VALUES
    ]


def selected_candidate_index(candidates):
    def key(candidate):
        correlations = [
            result["metrics"]["spearman"]
            for result in candidate["inner_fold_results"]
            if result["metrics"]["spearman"] is not None
        ]
        mean_spearman = math.fsum(correlations) / len(correlations) if correlations else None
        return (
            math.fsum(
                result["metrics"]["rmse"] for result in candidate["inner_fold_results"]
            ) / INNER_FOLDS,
            -mean_spearman if mean_spearman is not None else math.inf,
            json.dumps(candidate["config"], sort_keys=True),
        )

    return min(range(len(candidates)), key=lambda index: key(candidates[index]))


class VerificationFailure(ValueError):
    def __init__(self, check, message):
        super().__init__(message)
        self.check = check


class Checker:
    def __init__(self):
        self.checks = {}

    def require(self, name, condition, message):
        self.checks[name] = bool(condition)
        if not condition:
            raise VerificationFailure(name, message)


def nonnegative_cost(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def verify_goodman_baselines(
    clean_csv, split_json, predictions_csv, run_report_json, protocol_json=None,
):
    paths = tuple(
        Path(value).expanduser().resolve()
        for value in (clean_csv, split_json, predictions_csv, run_report_json)
    )
    clean_path, split_path, predictions_path, run_path = paths
    protocol_path = Path(protocol_json).expanduser().resolve() if protocol_json else None
    checker = Checker()
    recomputed = {}
    hashes = {}
    try:
        hashes = {
            "clean_csv": file_sha256(clean_path),
            "split_json": file_sha256(split_path),
            "predictions_csv": file_sha256(predictions_path),
            "run_report_json": file_sha256(run_path),
        }
        split = load_json(split_path)
        run = load_json(run_path)
        data = run.get("data", {})
        if protocol_path is None:
            protocol_path = Path(data["protocol_json"]).expanduser().resolve()
        protocol = load_json(protocol_path)
        hashes["baseline_protocol_json"] = file_sha256(protocol_path)
        checker.require(
            "run_identity",
            run.get("schema") == EXPECTED_RUN_SCHEMA
            and run.get("protocol") == EXPECTED_RUN_PROTOCOL
            and protocol.get("schema") == EXPECTED_BASELINE_PROTOCOL_SCHEMA
            and protocol.get("protocol") == EXPECTED_RUN_PROTOCOL,
            "baseline run or protocol identity mismatch",
        )
        checker.require(
            "baseline_protocol_sha256",
            data.get("protocol_sha256") == hashes["baseline_protocol_json"]
            and protocol.get("inputs", {}).get("clean_csv", {}).get("sha256") == hashes["clean_csv"]
            and protocol.get("inputs", {}).get("split_json", {}).get("sha256") == hashes["split_json"],
            "baseline protocol SHA or input hash link mismatch",
        )
        checker.require(
            "clean_sha256",
            data.get("clean_sha256") == hashes["clean_csv"]
            and split.get("input_sha256", {}).get("clean_csv") == hashes["clean_csv"],
            "clean SHA256 is not linked across the file, run and frozen split",
        )
        checker.require(
            "split_sha256",
            data.get("split_sha256") == hashes["split_json"],
            "run report split SHA256 mismatch",
        )
        checker.require(
            "predictions_sha256",
            run.get("predictions", {}).get("sha256") == hashes["predictions_csv"],
            "run report prediction SHA256 mismatch",
        )
        clean_rows = read_clean(clean_path)
        partitions = validate_split(split, clean_rows)
        checker.require("split_structure", True, "unreachable")
        checker.require(
            "clean_shape",
            split.get("input", {}).get("data_rows") == len(clean_rows)
            and split.get("input", {}).get("gene_count") == len({row["Gene"] for row in clean_rows})
            and data.get("clean_data_rows") == len(clean_rows),
            "clean row or Gene count mismatch",
        )
        scope = run.get("scope", {})
        checker.require(
            "development_scope",
            scope.get("development_benchmark") is True
            and scope.get("untouched_evaluation") is False
            and scope.get("mechanism_evidence") is False
            and scope.get("sota_claim") is False
            and scope.get("protein_ood") is False
            and data.get("untouched_inputs_read") is False,
            "run exceeds the development benchmark scope",
        )
        analysis_filter = data.get("analysis_filter", {})
        outcome = data.get("outcome", {})
        checker.require(
            "raw_clean_history_unchanged",
            data.get("raw_csv_read") is False
            and data.get("clean_file_modified") is False
            and data.get("raw_or_clean_filtering_applied") is False
            and data.get("clean_rows_removed_or_overwritten") == 0,
            "raw/clean non-filtering history was changed",
        )
        checker.require(
            "setgood_filter_contract",
            analysis_filter.get("column") == "Fltr.SetGood"
            and analysis_filter.get("operator") == "=="
            and analysis_filter.get("value") == "TRUE"
            and analysis_filter.get("applied_in_memory_for_primary_analysis_only") is True,
            "primary analysis filter is not exactly Fltr.SetGood == TRUE",
        )
        checker.require(
            "outcome_contract",
            outcome.get("source_column") == "Count.Prot"
            and outcome.get("transform") == "log1p"
            and outcome.get("evaluation_scale") == "log1p_Count.Prot"
            and outcome.get("top_decile_enrichment_scale") == "untransformed_Count.Prot",
            "outcome must be Count.Prot with log1p evaluation",
        )
        clean_by_index = {}
        for row in clean_rows:
            count_prot = finite_float(row["Count.Prot"], "Count.Prot") if row["Fltr.SetGood"].strip() == "TRUE" else None
            if count_prot is not None and count_prot < 0:
                raise ValueError("SetGood Count.Prot must be nonnegative")
            clean_by_index[row["clean_row_index"]] = {
                **row,
                "count_prot": count_prot,
                "log1p": math.log1p(count_prot) if count_prot is not None else None,
            }
        eligible = {
            index: row for index, row in clean_by_index.items() if row["count_prot"] is not None
        }
        checker.require(
            "eligible_row_count",
            data.get("eligible_SetGood_rows") == len(eligible)
            and data.get("excluded_non_SetGood_rows") == len(clean_rows) - len(eligible),
            "SetGood eligible or excluded row count mismatch",
        )
        outer_by_gene = {
            gene: outer_index
            for outer_index, partition in enumerate(partitions)
            for gene in partition["test"]
        }
        prediction_rows = read_predictions(predictions_path)
        checker.require(
            "prediction_rows_only_setgood",
            all(
                row["Fltr.SetGood"].strip() == "TRUE"
                and row["clean_row_index"].isdigit()
                and int(row["clean_row_index"]) in eligible
                for row in prediction_rows
            ),
            "prediction rows contain non-SetGood or unknown clean rows",
        )
        expected_keys = {
            (arm, str(index)) for arm in ARMS for index in eligible
        }
        observed_keys = [(row["arm"], row["clean_row_index"]) for row in prediction_rows]
        checker.require(
            "prediction_row_conservation",
            len(observed_keys) == len(set(observed_keys)) and set(observed_keys) == expected_keys,
            "prediction rows do not contain every SetGood row exactly once per arm",
        )
        row_consistency = True
        outer_assignment = True
        log1p_consistency = True
        final_fit_links = True
        grouped = {}
        for row in prediction_rows:
            index = int(row["clean_row_index"])
            clean = eligible[index]
            outer = int(row["outer_fold"])
            arm = row["arm"]
            row_consistency &= (
                row["Name"] == clean["Name"]
                and row["Gene"] == clean["Gene"]
                and row["Count.Prot"] == clean["Count.Prot"]
            )
            outer_assignment &= outer == outer_by_gene[clean["Gene"]]
            observed_log = finite_float(row["observed_log1p_Count.Prot"], "observed log1p")
            prediction = finite_float(row["prediction_log1p_Count.Prot"], "prediction")
            log1p_consistency &= close(observed_log, clean["log1p"], tolerance=1e-12)
            expected_fit_id = f"outer-{outer}__{arm}__outer-final"
            final_fit_links &= row["fit_id"] == expected_fit_id
            grouped.setdefault((outer, arm), []).append(row)
        checker.require("prediction_clean_row_identity", row_consistency, "prediction identity fields differ from clean")
        checker.require("prediction_outer_assignment", outer_assignment, "prediction outer fold differs from frozen split")
        checker.require("prediction_log1p_outcome", log1p_consistency, "observed outcomes are not log1p(Count.Prot)")
        checker.require("prediction_final_fit_links", final_fit_links, "prediction final fit IDs are invalid")

        outer_results = run.get("outer_results", [])
        result_index = {}
        for result in outer_results:
            key = (result.get("outer_fold"), result.get("arm"))
            if key in result_index:
                raise ValueError(f"duplicate outer result: {key}")
            result_index[key] = result
        checker.require(
            "outer_result_coverage",
            set(result_index) == set(grouped) and len(outer_results) == OUTER_FOLDS * len(ARMS),
            "outer result coverage mismatch",
        )
        recomputed_results = []
        spearman_ok = True
        rmse_ok = True
        enrichment_ok = True
        row_counts_ok = True
        for (outer, arm), rows in sorted(grouped.items()):
            metrics = recompute_metrics(rows, clean_by_index)
            reported = result_index[(outer, arm)]
            reported_metrics = reported.get("metrics", {})
            spearman_ok &= close(reported_metrics.get("spearman"), metrics["spearman"])
            rmse_ok &= close(reported_metrics.get("rmse"), metrics["rmse"])
            enrichment_ok &= close(
                reported_metrics.get("top_decile_enrichment"), metrics["top_decile_enrichment"],
            )
            enrichment_ok &= reported_metrics.get("top_decile_count") == metrics["top_decile_count"]
            enrichment_ok &= close(
                reported_metrics.get("top_decile_observed_Count.Prot_mean"),
                metrics["top_decile_observed_Count.Prot_mean"],
            )
            enrichment_ok &= close(
                reported_metrics.get("all_observed_Count.Prot_mean"),
                metrics["all_observed_Count.Prot_mean"],
            )
            row_counts_ok &= (
                reported.get("test_rows") == len(rows)
                and reported.get("prediction_rows") == len(rows)
            )
            recomputed_results.append({
                "outer_fold": outer,
                "arm": arm,
                "rows": len(rows),
                "metrics": metrics,
            })
        checker.require("recomputed_spearman", spearman_ok, "reported Spearman differs from raw prediction recomputation")
        checker.require("recomputed_rmse", rmse_ok, "reported RMSE differs from raw prediction recomputation")
        checker.require("recomputed_top_decile_enrichment", enrichment_ok, "reported top-decile enrichment differs from recomputation")
        checker.require("per_outer_row_counts", row_counts_ok, "per-outer prediction row counts mismatch")
        per_arm_counts = Counter(row["arm"] for row in prediction_rows)
        checker.require(
            "overall_row_counts",
            run.get("predictions", {}).get("rows") == len(prediction_rows)
            == len(ARMS) * len(eligible)
            and all(per_arm_counts[arm] == len(eligible) for arm in ARMS),
            "overall or per-arm prediction row counts mismatch",
        )

        fit_records = run.get("fit_records", [])
        fit_by_id = {}
        for record in fit_records:
            fit_id = record.get("fit_id")
            if fit_id in fit_by_id:
                raise ValueError(f"duplicate fit_id: {fit_id}")
            fit_by_id[fit_id] = record
        referenced_fit_ids = set()
        selection_ok = True
        inner_evidence_ok = True
        isolation_ok = True
        preprocessing_ok = True
        histgb_ok = True
        costs_ok = nonnegative_cost(run.get("total_wall_time_seconds")) and nonnegative_cost(
            run.get("total_process_cpu_time_seconds"),
        )
        eligible_gene_counts = Counter(row["Gene"] for row in eligible.values())
        for outer in range(OUTER_FOLDS):
            partition = partitions[outer]
            for arm in ARMS:
                result = result_index[(outer, arm)]
                selection = result.get("selection", {})
                candidates = selection.get("candidates", [])
                configs = [candidate.get("config") for candidate in candidates]
                selection_ok &= (
                    selection.get("strategy") == "four_inner_folds_only"
                    and selection.get("selection_metric") == "mean_inner_rmse_log1p_Count.Prot"
                    and selection.get("outer_test_used") is False
                    and configs == expected_configs(arm)
                )
                if not candidates:
                    selection_ok = False
                    continue
                selected_index = selection.get("selected_candidate_index")
                selection_ok &= (
                    selected_index == selected_candidate_index(candidates)
                    and selection.get("selected_config") == candidates[selected_index]["config"]
                )
                inner_fit_ids = []
                for candidate_index, candidate in enumerate(candidates):
                    inner_results = candidate.get("inner_fold_results", [])
                    inner_evidence_ok &= (
                        candidate.get("candidate_index") == candidate_index
                        and len(inner_results) == INNER_FOLDS
                        and {item.get("inner_fold") for item in inner_results} == set(range(INNER_FOLDS))
                    )
                    rmse_values = []
                    correlations = []
                    for inner_result in inner_results:
                        inner = inner_result["inner_fold"]
                        fit_id = inner_result.get("fit_id")
                        inner_fit_ids.append(fit_id)
                        referenced_fit_ids.add(fit_id)
                        fit = fit_by_id.get(fit_id, {})
                        fit_genes = partition["train"] - partition["inner"][inner]
                        validation_genes = partition["inner"][inner]
                        inner_evidence_ok &= (
                            fit.get("selection_role") == "inner_candidate"
                            and fit.get("outer_fold") == outer
                            and fit.get("inner_fold") == inner
                            and fit.get("candidate_index") == candidate_index
                            and fit.get("arm") == arm
                            and fit.get("config") == candidate["config"]
                            and fit.get("fit_train_gene_sha256") == gene_set_sha256(fit_genes)
                            and fit.get("evaluation_gene_sha256") == gene_set_sha256(validation_genes)
                            and fit.get("fit_train_rows") == sum(eligible_gene_counts[gene] for gene in fit_genes)
                            and fit.get("evaluation_rows") == sum(eligible_gene_counts[gene] for gene in validation_genes)
                            and inner_result.get("fit_id") == fit_id
                            and inner_result.get("validation_rows") == fit.get("evaluation_rows")
                        )
                        rmse_values.append(inner_result["metrics"]["rmse"])
                        correlation = inner_result["metrics"]["spearman"]
                        if correlation is not None:
                            correlations.append(correlation)
                    expected_rmse = math.fsum(rmse_values) / len(rmse_values)
                    expected_spearman = (
                        math.fsum(correlations) / len(correlations) if correlations else None
                    )
                    inner_evidence_ok &= close(candidate.get("mean_inner_rmse"), expected_rmse)
                    inner_evidence_ok &= close(
                        candidate.get("mean_inner_spearman"), expected_spearman,
                    )
                final_fit_id = result.get("final_fit_id")
                referenced_fit_ids.add(final_fit_id)
                final_fit = fit_by_id.get(final_fit_id, {})
                isolation_ok &= (
                    final_fit.get("selection_role") == "outer_final_refit"
                    and final_fit.get("outer_fold") == outer
                    and final_fit.get("inner_fold") is None
                    and final_fit.get("arm") == arm
                    and final_fit.get("config") == selection.get("selected_config")
                    and final_fit.get("fit_train_gene_sha256") == gene_set_sha256(partition["train"])
                    and final_fit.get("evaluation_gene_sha256") is None
                    and final_fit.get("fit_train_rows") == sum(
                        eligible_gene_counts[gene] for gene in partition["train"]
                    )
                )
                inner_fits = [fit_by_id.get(fit_id, {}) for fit_id in inner_fit_ids]
                expected_inner_wall = math.fsum(fit.get("wall_time_seconds", math.nan) for fit in inner_fits)
                expected_inner_cpu = math.fsum(fit.get("process_cpu_time_seconds", math.nan) for fit in inner_fits)
                costs_ok &= close(result.get("inner_cv_wall_time_seconds"), expected_inner_wall)
                costs_ok &= close(result.get("inner_cv_process_cpu_time_seconds"), expected_inner_cpu)
                costs_ok &= close(
                    result.get("final_fit_wall_time_seconds"), final_fit.get("wall_time_seconds"),
                )
                costs_ok &= close(
                    result.get("final_fit_process_cpu_time_seconds"),
                    final_fit.get("process_cpu_time_seconds"),
                )
                costs_ok &= close(
                    result.get("total_fit_wall_time_seconds"),
                    expected_inner_wall + final_fit.get("wall_time_seconds", math.nan),
                )
                costs_ok &= nonnegative_cost(result.get("prediction_wall_time_seconds"))
                for fit in [*inner_fits, final_fit]:
                    costs_ok &= nonnegative_cost(fit.get("wall_time_seconds"))
                    costs_ok &= nonnegative_cost(fit.get("process_cpu_time_seconds"))
                    preprocessing_ok &= (
                        fit.get("preprocessing_fit_scope") == "fit_train_rows_only"
                        and fit.get("outer_test_used_for_fit") is False
                        and fit.get("outer_test_used_for_preprocessing") is False
                        and fit.get("outer_test_used_for_selection") is False
                        and fit.get("fit_status") == "success"
                    )
                    expected_feature_count = (
                        0 if arm == "constant" else 1 if arm.startswith("univariate_") else None
                    )
                    n_features = fit.get("n_features")
                    preprocessing_ok &= (
                        type(n_features) is int
                        and n_features >= 0
                        and (expected_feature_count is None or n_features == expected_feature_count)
                        and (expected_feature_count is not None or 1 <= n_features <= MAX_FULL_FEATURES)
                    )
                    if arm == "histgb_full":
                        stopping = fit.get("early_stopping", {})
                        n_iter = fit.get("n_iter")
                        histgb_ok &= (
                            type(n_iter) is int
                            and 1 <= n_iter <= HISTGB_MAX_ITER
                            and fit.get("max_iter") == HISTGB_MAX_ITER
                            and stopping.get("enabled") is True
                            and stopping.get("validation_scope") == "corresponding_fit_train_rows_only"
                            and stopping.get("validation_fraction") == 0.15
                            and stopping.get("n_iter_no_change") == 30
                            and stopping.get("max_iter_reached") == (n_iter == HISTGB_MAX_ITER)
                            and stopping.get("stopped_before_max_iter") == (n_iter < HISTGB_MAX_ITER)
                        )
        checker.require("inner_only_configuration_selection", selection_ok, "selected configuration is not supported by the four-inner-fold evidence")
        checker.require("inner_fold_and_fit_evidence", inner_evidence_ok, "inner candidate or fit evidence mismatch")
        checker.require("outer_test_isolation", isolation_ok, "outer final fit does not isolate outer test Genes")
        checker.require("train_only_preprocessing", preprocessing_ok, "feature/preprocessing scope or dimension cap mismatch")
        checker.require("histgb_actual_iterations", histgb_ok, "HistGB early stopping or actual n_iter evidence mismatch")
        checker.require("fit_and_prediction_costs", costs_ok, "fit/prediction cost fields are missing or inconsistent")
        checker.require(
            "fit_record_conservation",
            referenced_fit_ids == set(fit_by_id),
            "unreferenced or missing fit records",
        )
        features = run.get("features", {})
        checker.require(
            "feature_contract",
            features.get("numeric") == ["CAI", "GC", "dG", "tAI"]
            and features.get("categorical") == ["Promoter", "RBS.Display"]
            and features.get("maximum_full_feature_count") == MAX_FULL_FEATURES
            and features.get("maximum_categories_per_categorical_field") == 16
            and features.get("outer_test_used_for_preprocessing") is False,
            "full feature contract mismatch",
        )
        environment = run.get("environment", {})
        git = run.get("git", {})
        checker.require(
            "environment_and_source_sha",
            all(environment.get(field) for field in (
                "python_version", "platform", "numpy_version", "scipy_version", "sklearn_version",
            ))
            and re.fullmatch(r"[0-9a-f]{40}", git.get("head_sha", "")) is not None
            and re.fullmatch(r"[0-9a-f]{64}", git.get("baseline_script_sha256", "")) is not None,
            "environment, Git SHA or baseline script SHA is missing",
        )
        recomputed = {
            "eligible_SetGood_rows": len(eligible),
            "prediction_rows": len(prediction_rows),
            "per_arm_prediction_rows": dict(sorted(per_arm_counts.items())),
            "outer_results": recomputed_results,
        }
    except Exception as exc:
        return {
            "protocol": VERIFICATION_PROTOCOL,
            "passed": False,
            "scope": "development_benchmark_artifact_verification_only",
            "inputs": {
                "clean_csv": str(clean_path),
                "split_json": str(split_path),
                "predictions_csv": str(predictions_path),
                "run_report_json": str(run_path),
                "baseline_protocol_json": str(protocol_path) if protocol_path else None,
            },
            "sha256": hashes,
            "checks": checker.checks,
            "recomputed": recomputed,
            "error": {
                "type": type(exc).__name__,
                "check": getattr(exc, "check", None),
                "message": str(exc),
            },
        }
    return {
        "protocol": VERIFICATION_PROTOCOL,
        "passed": all(checker.checks.values()),
        "scope": "development_benchmark_artifact_verification_only",
        "inputs": {
            "clean_csv": str(clean_path),
            "split_json": str(split_path),
            "predictions_csv": str(predictions_path),
            "run_report_json": str(run_path),
            "baseline_protocol_json": str(protocol_path) if protocol_path else None,
        },
        "sha256": hashes,
        "checks": checker.checks,
        "recomputed": recomputed,
        "verifier_script_sha256": file_sha256(Path(__file__).resolve()),
    }


def main(argv=None):
    args = parse_args(argv)
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    result = verify_goodman_baselines(
        args.clean_csv,
        args.split_json,
        args.predictions_csv,
        args.run_report_json,
        args.protocol_json,
    )
    write_json_exclusive(output, result)
    print(json.dumps({
        "output": str(output),
        "passed": result["passed"],
        "checks": result["checks"],
        "error": result.get("error"),
    }))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
