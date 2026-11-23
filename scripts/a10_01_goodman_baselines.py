"""Run leakage-controlled Goodman development baselines on frozen nested splits."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import itertools
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import sklearn
from scipy import __version__ as scipy_version
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge


PROTOCOL = "a10_01_goodman_baseline_protocol_v1"
PROTOCOL_SCHEMA = "a10-01-goodman-baseline-protocol-v1"
DEFAULT_PROTOCOL = Path(__file__).resolve().parents[1] / "configs" / "a10_01_goodman_baseline_protocol_v1.json"
RUN_SCHEMA = "a10-01-goodman-development-baseline-run-v1"
SPLIT_SCHEMA = "a10-01-goodman-frozen-nested-grouped-cv-v1"
SPLIT_PROTOCOL = "a10_01_goodman_split_protocol_v1"
OUTER_FOLDS = 5
INNER_FOLDS = 4
SEQUENCE_NT_LENGTH = 33
SEQUENCE_POSITIONS = SEQUENCE_NT_LENGTH // 3
NUMERIC_FEATURES = ("CAI", "GC", "dG", "tAI")
CATEGORICAL_FEATURES = ("Promoter", "RBS.Display")
MAX_CATEGORIES_PER_FIELD = 16
CODONS = tuple("".join(codon) for codon in itertools.product("ACGT", repeat=3))
CODON_INDEX = {codon: index for index, codon in enumerate(CODONS)}
MAX_FULL_FEATURES = (
    SEQUENCE_POSITIONS * len(CODONS)
    + len(NUMERIC_FEATURES)
    + len(CATEGORICAL_FEATURES) * MAX_CATEGORIES_PER_FIELD
)
RIDGE_ALPHAS = (0.1, 1.0, 10.0, 100.0)
HISTGB_LEARNING_RATES = (0.05, 0.1)
HISTGB_L2_VALUES = (0.0, 1.0)
HISTGB_MAX_ITER = 500
HISTGB_N_ITER_NO_CHANGE = 30
HISTGB_VALIDATION_FRACTION = 0.15
RIDGE_MAX_ITER = 10000
RANDOM_STATE = 20261123
ARMS = (
    "constant",
    "univariate_CAI",
    "univariate_GC",
    "univariate_dG",
    "univariate_tAI",
    "ridge_full",
    "histgb_full",
)
PREDICTION_COLUMNS = (
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
)
REQUIRED_CLEAN_COLUMNS = (
    "Name",
    "Gene",
    "CDS.seq",
    "Count.Prot",
    "Fltr.SetGood",
    *NUMERIC_FEATURES,
    *CATEGORICAL_FEATURES,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--clean-csv", required=True, help="Goodman clean-v3 CSV; never modified")
    parser.add_argument("--split-json", required=True, help="Frozen nested 5 outer x 4 inner split JSON")
    parser.add_argument("--protocol", default=str(DEFAULT_PROTOCOL), help="Frozen baseline protocol JSON")
    parser.add_argument("--output-dir", required=True, help="New directory for predictions and run report")
    return parser.parse_args(argv)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def gene_set_sha256(genes):
    return hashlib.sha256("\n".join(sorted(genes)).encode("utf-8")).hexdigest()


def json_bytes(payload):
    return (json.dumps(
        payload, indent=2, ensure_ascii=False, allow_nan=False,
    ) + "\n").encode("utf-8")


def finite_number(token, label):
    try:
        value = float(token)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric, observed {token!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite, observed {token!r}")
    return value


def input_file(value, label):
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"{label} not found or not a regular file: {path}")
    return path


def load_json(path):
    def reject_constant(value):
        raise ValueError(f"non-finite JSON number is forbidden: {value}")

    with Path(path).open("r", encoding="utf-8", errors="strict") as handle:
        payload = json.load(handle, parse_constant=reject_constant)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def load_protocol(path):
    protocol = load_json(path)
    if protocol.get("schema") != PROTOCOL_SCHEMA or protocol.get("protocol") != PROTOCOL:
        raise ValueError(f"baseline protocol identity mismatch: expected {PROTOCOL}")
    inputs = protocol.get("inputs", {})
    clean = inputs.get("clean_csv", {})
    split = inputs.get("split_json", {})
    if not re.fullmatch(r"[0-9a-f]{64}", clean.get("sha256", "")):
        raise ValueError("protocol clean_csv.sha256 must be a lowercase SHA256")
    if not re.fullmatch(r"[0-9a-f]{64}", split.get("sha256", "")):
        raise ValueError("protocol split_json.sha256 must be a lowercase SHA256")
    if split.get("schema") != SPLIT_SCHEMA or split.get("protocol") != SPLIT_PROTOCOL:
        raise ValueError("protocol frozen split identity mismatch")
    if split.get("outer_folds") != OUTER_FOLDS or split.get("inner_folds") != INNER_FOLDS:
        raise ValueError("protocol must freeze 5 outer and 4 inner folds")
    if inputs.get("untouched_inputs_read") is not False:
        raise ValueError("protocol must forbid untouched inputs")
    outcome = protocol.get("outcome", {})
    if outcome.get("source_column") != "Count.Prot" or outcome.get("transform") != "log1p":
        raise ValueError("primary outcome must be log1p of original Count.Prot")
    if outcome.get("raw_clean_filtering_history_changed") is not False:
        raise ValueError("protocol must preserve raw/clean filtering history")
    features = protocol.get("features", {})
    if any((
        features.get("numeric_columns") != list(NUMERIC_FEATURES),
        features.get("categorical_columns") != list(CATEGORICAL_FEATURES),
        features.get("sequence_nt_length") != SEQUENCE_NT_LENGTH,
        features.get("codon_positions") != SEQUENCE_POSITIONS,
        features.get("codon_vocabulary_size") != len(CODONS),
        features.get("max_categories_per_categorical") != MAX_CATEGORIES_PER_FIELD,
        features.get("max_encoded_features") != MAX_FULL_FEATURES,
        features.get("outer_test_used_for_preprocessing") is not False,
    )):
        raise ValueError("protocol features do not match the controlled production feature arm")
    models = protocol.get("models", {})
    ridge = models.get("ridge", {})
    histgb = models.get("histgb", {})
    if any((
        ridge.get("alpha_grid") != list(RIDGE_ALPHAS),
        ridge.get("solver") != "lsqr",
        ridge.get("tol") != 1e-8,
        ridge.get("max_iter") != RIDGE_MAX_ITER,
        histgb.get("learning_rate_grid") != list(HISTGB_LEARNING_RATES),
        histgb.get("l2_regularization_grid") != list(HISTGB_L2_VALUES),
        histgb.get("max_iter") != HISTGB_MAX_ITER,
        histgb.get("early_stopping") is not True,
        histgb.get("validation_fraction") != HISTGB_VALIDATION_FRACTION,
        histgb.get("n_iter_no_change") != HISTGB_N_ITER_NO_CHANGE,
        histgb.get("random_state") != RANDOM_STATE,
        histgb.get("actual_n_iter_required") is not True,
        histgb.get("reaching_max_iter_is_convergence") is not False,
    )):
        raise ValueError("protocol model grids or stopping settings do not match production")
    study = protocol.get("study", {})
    if any((
        study.get("benchmark_role") != "development_only",
        study.get("final_untouched") is not False,
        study.get("mechanism_claim_eligible") is not False,
        study.get("sota_claim_eligible") is not False,
        study.get("protein_ood_supported") is not False,
    )):
        raise ValueError("protocol claim boundary must remain development-only")
    if protocol.get("outputs", {}).get("overwrite") != "forbidden":
        raise ValueError("protocol outputs must forbid overwriting")
    return protocol


def read_clean(path):
    rows = []
    with Path(path).open("r", encoding="utf-8-sig", errors="strict", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("clean CSV is empty") from exc
        if any(not column for column in header) or len(set(header)) != len(header):
            raise ValueError("clean CSV has empty or duplicate column names")
        missing = [column for column in REQUIRED_CLEAN_COLUMNS if column not in header]
        if missing:
            raise ValueError(f"clean CSV is missing required columns: {missing}")
        for values in reader:
            if len(values) != len(header):
                raise ValueError(
                    f"clean CSV line {reader.line_num} has {len(values)} fields; "
                    f"expected {len(header)}",
                )
            row = dict(zip(header, values))
            row["clean_row_index"] = len(rows)
            if not row["Name"] or not row["Gene"] or not row["CDS.seq"]:
                raise ValueError("Name, Gene and CDS.seq must be non-empty")
            rows.append(row)
    if not rows:
        raise ValueError("clean CSV has no data rows")
    return rows


def validate_split(split, clean_rows):
    if split.get("schema") != SPLIT_SCHEMA or split.get("protocol") != SPLIT_PROTOCOL:
        raise ValueError("frozen split identity mismatch")
    if split.get("untouched_inputs_read") is not False:
        raise ValueError("frozen split must declare that untouched inputs were not read")
    if split.get("outcome_columns_used_for_splitting") is not False:
        raise ValueError("frozen split must be outcome blind")
    grouping = split.get("grouping", {})
    if grouping.get("outer_folds") != OUTER_FOLDS or grouping.get("inner_folds_per_outer") != INNER_FOLDS:
        raise ValueError("frozen split must contain 5 outer folds and 4 inner folds per outer")
    all_genes = {row["Gene"] for row in clean_rows}
    folds = split.get("outer_folds")
    if not isinstance(folds, list) or len(folds) != OUTER_FOLDS:
        raise ValueError("frozen split outer_folds must be a five-element list")
    extracted = []
    outer_test_union = set()
    for outer_index, fold in enumerate(folds):
        if fold.get("outer_fold") != outer_index:
            raise ValueError("outer fold indices must be contiguous and ordered")
        test = set(fold.get("test_genes", []))
        train = set(fold.get("train_genes", []))
        if not test or test & train or test | train != all_genes:
            raise ValueError(f"outer fold {outer_index} is not a complete Gene partition")
        if outer_test_union & test:
            raise ValueError("outer test Gene sets overlap")
        outer_test_union |= test
        inner_mapping = fold.get("train_inner_folds", {})
        if set(inner_mapping) != {str(index) for index in range(INNER_FOLDS)}:
            raise ValueError(f"outer fold {outer_index} must have four inner folds")
        inner = [set(inner_mapping[str(index)]) for index in range(INNER_FOLDS)]
        if any(not genes for genes in inner) or set().union(*inner) != train:
            raise ValueError(f"outer fold {outer_index} inner folds are incomplete")
        if sum(map(len, inner)) != len(train):
            raise ValueError(f"outer fold {outer_index} inner folds overlap")
        extracted.append({"test": test, "train": train, "inner": inner})
    if outer_test_union != all_genes:
        raise ValueError("outer test folds do not cover every clean Gene")
    return extracted


def prepare_records(clean_rows):
    eligible = []
    for row in clean_rows:
        if row["Fltr.SetGood"].strip() != "TRUE":
            continue
        sequence = row["CDS.seq"].upper()
        if len(sequence) != SEQUENCE_NT_LENGTH or set(sequence) - set("ACGT"):
            raise ValueError(
                f"SetGood row {row['clean_row_index']} CDS.seq must be exactly 33 nt of A/C/G/T",
            )
        count_prot = finite_number(row["Count.Prot"], "Count.Prot")
        if count_prot < 0:
            raise ValueError("Count.Prot must be nonnegative for log1p")
        record = {
            "clean_row_index": row["clean_row_index"],
            "Name": row["Name"],
            "Gene": row["Gene"],
            "CDS.seq": sequence,
            "Count.Prot.token": row["Count.Prot"],
            "Count.Prot": count_prot,
            "y": math.log1p(count_prot),
            "Fltr.SetGood": row["Fltr.SetGood"].strip(),
        }
        for feature in NUMERIC_FEATURES:
            record[feature] = finite_number(row[feature], feature)
        for feature in CATEGORICAL_FEATURES:
            record[feature] = row[feature]
        eligible.append(record)
    if not eligible:
        raise ValueError("no rows satisfy Fltr.SetGood == TRUE")
    return eligible


class FullFeatureTransformer:
    def fit(self, records):
        self.means = np.array([
            math.fsum(record[feature] for record in records) / len(records)
            for feature in NUMERIC_FEATURES
        ], dtype=np.float64)
        self.scales = np.array([
            math.sqrt(math.fsum(
                (record[feature] - mean) ** 2 for record in records
            ) / len(records))
            for feature, mean in zip(NUMERIC_FEATURES, self.means)
        ], dtype=np.float64)
        self.scales[self.scales < 1e-12] = 1.0
        self.category_levels = {}
        for feature in CATEGORICAL_FEATURES:
            counts = Counter(record[feature] for record in records)
            ordered = sorted(counts, key=lambda value: (-counts[value], value))
            self.category_levels[feature] = ordered[:MAX_CATEGORIES_PER_FIELD - 1]
        self.n_features = (
            SEQUENCE_POSITIONS * len(CODONS)
            + len(NUMERIC_FEATURES)
            + sum(len(self.category_levels[feature]) + 1 for feature in CATEGORICAL_FEATURES)
        )
        if self.n_features > MAX_FULL_FEATURES:
            raise AssertionError("full feature dimension exceeds its frozen cap")
        return self

    def transform(self, records):
        matrix = np.zeros((len(records), self.n_features), dtype=np.float64)
        numeric_offset = SEQUENCE_POSITIONS * len(CODONS)
        category_offset = numeric_offset + len(NUMERIC_FEATURES)
        category_indices = {}
        for feature in CATEGORICAL_FEATURES:
            levels = self.category_levels[feature]
            category_indices[feature] = (
                {value: index for index, value in enumerate(levels)},
                category_offset,
            )
            category_offset += len(levels) + 1
        for row_index, record in enumerate(records):
            codons = [
                record["CDS.seq"][index:index + 3]
                for index in range(0, SEQUENCE_NT_LENGTH, 3)
            ]
            for position, codon in enumerate(codons):
                matrix[row_index, position * len(CODONS) + CODON_INDEX[codon]] = 1.0
            for feature_index, feature in enumerate(NUMERIC_FEATURES):
                matrix[row_index, numeric_offset + feature_index] = (
                    record[feature] - self.means[feature_index]
                ) / self.scales[feature_index]
            for feature in CATEGORICAL_FEATURES:
                indices, offset = category_indices[feature]
                category_index = indices.get(record[feature], len(indices))
                matrix[row_index, offset + category_index] = 1.0
        return matrix

    def fit_transform(self, records):
        return self.fit(records).transform(records)


def regression_metrics(records, predictions):
    observed = np.array([record["y"] for record in records], dtype=np.float64)
    predicted = np.asarray(predictions, dtype=np.float64)
    if observed.shape != predicted.shape or observed.ndim != 1 or not len(observed):
        raise ValueError("metric inputs must be nonempty one-dimensional arrays of equal length")
    if not np.isfinite(predicted).all():
        raise ValueError("model produced non-finite predictions")
    correlation = (
        spearmanr(observed, predicted).statistic
        if np.ptp(observed) > 0 and np.ptp(predicted) > 0 else np.nan
    )
    spearman = float(correlation) if math.isfinite(float(correlation)) else None
    rmse = math.sqrt(float(np.mean((observed - predicted) ** 2)))
    top_count = (len(records) + 9) // 10
    order = sorted(
        range(len(records)),
        key=lambda index: (-float(predicted[index]), records[index]["clean_row_index"]),
    )
    observed_prot = [record["Count.Prot"] for record in records]
    denominator = math.fsum(observed_prot) / len(observed_prot)
    numerator = math.fsum(observed_prot[index] for index in order[:top_count]) / top_count
    enrichment = numerator / denominator if denominator > 0 else None
    return {
        "spearman": spearman,
        "rmse": rmse,
        "top_decile_enrichment": enrichment,
        "top_decile_count": top_count,
        "top_decile_observed_Count.Prot_mean": numerator,
        "all_observed_Count.Prot_mean": denominator,
    }


def fit_model(records, arm, config):
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    n_iter = None
    max_iter = None
    early_stopping = None
    if arm == "constant":
        mean = math.fsum(record["y"] for record in records) / len(records)
        n_features = 0

        def predict(new_records):
            return np.full(len(new_records), mean, dtype=np.float64)

    elif arm.startswith("univariate_"):
        feature = config["feature"]
        mean = math.fsum(record[feature] for record in records) / len(records)
        scale = math.sqrt(math.fsum(
            (record[feature] - mean) ** 2 for record in records
        ) / len(records))
        if scale < 1e-12:
            scale = 1.0
        design = np.column_stack([
            np.ones(len(records), dtype=np.float64),
            np.array([(record[feature] - mean) / scale for record in records]),
        ])
        coefficients = np.linalg.lstsq(
            design, np.array([record["y"] for record in records]), rcond=None,
        )[0]
        n_features = 1

        def predict(new_records):
            values = np.array([
                (record[feature] - mean) / scale for record in new_records
            ])
            return coefficients[0] + coefficients[1] * values

    else:
        transformer = FullFeatureTransformer()
        matrix = transformer.fit_transform(records)
        outcomes = np.array([record["y"] for record in records], dtype=np.float64)
        n_features = transformer.n_features
        if arm == "ridge_full":
            model = Ridge(
                alpha=config["alpha"],
                fit_intercept=True,
                solver="lsqr",
                tol=1e-8,
                max_iter=RIDGE_MAX_ITER,
            )
            max_iter = RIDGE_MAX_ITER
        elif arm == "histgb_full":
            model = HistGradientBoostingRegressor(
                loss="squared_error",
                learning_rate=config["learning_rate"],
                l2_regularization=config["l2_regularization"],
                max_iter=HISTGB_MAX_ITER,
                early_stopping=True,
                scoring="loss",
                validation_fraction=HISTGB_VALIDATION_FRACTION,
                n_iter_no_change=HISTGB_N_ITER_NO_CHANGE,
                tol=1e-7,
                random_state=RANDOM_STATE,
            )
            max_iter = HISTGB_MAX_ITER
        else:
            raise ValueError(f"unknown arm: {arm}")
        model.fit(matrix, outcomes)
        raw_n_iter = getattr(model, "n_iter_", None)
        if raw_n_iter is not None:
            n_iter = int(np.asarray(raw_n_iter).reshape(-1)[0])
        if arm == "histgb_full":
            early_stopping = {
                "enabled": True,
                "validation_scope": "corresponding_fit_train_rows_only",
                "validation_fraction": HISTGB_VALIDATION_FRACTION,
                "n_iter_no_change": HISTGB_N_ITER_NO_CHANGE,
                "tol": 1e-7,
                "max_iter_reached": n_iter == HISTGB_MAX_ITER,
                "stopped_before_max_iter": n_iter < HISTGB_MAX_ITER,
            }

        def predict(new_records):
            return model.predict(transformer.transform(new_records))

    wall_seconds = time.perf_counter() - wall_start
    cpu_seconds = time.process_time() - cpu_start
    details = {
        "fit_status": "success",
        "fit_train_rows": len(records),
        "n_features": n_features,
        "n_iter": n_iter,
        "max_iter": max_iter,
        "early_stopping": early_stopping,
        "wall_time_seconds": wall_seconds,
        "process_cpu_time_seconds": cpu_seconds,
        "preprocessing_fit_scope": "fit_train_rows_only",
        "outer_test_used_for_fit": False,
        "outer_test_used_for_preprocessing": False,
        "outer_test_used_for_selection": False,
    }
    if arm.startswith("univariate_"):
        details["train_fitted_standardized_coefficient"] = float(coefficients[1])
        details["train_fitted_direction"] = (
            "positive" if coefficients[1] > 0 else "negative" if coefficients[1] < 0 else "zero"
        )
    return predict, details


def candidate_configs(arm):
    if arm == "constant":
        return [{}]
    if arm.startswith("univariate_"):
        return [{"feature": arm.removeprefix("univariate_")}]
    if arm == "ridge_full":
        return [{"alpha": alpha} for alpha in RIDGE_ALPHAS]
    if arm == "histgb_full":
        return [
            {"learning_rate": learning_rate, "l2_regularization": l2_value}
            for learning_rate in HISTGB_LEARNING_RATES
            for l2_value in HISTGB_L2_VALUES
        ]
    raise ValueError(f"unknown arm: {arm}")


def mean_metrics(inner_results):
    rmse = math.fsum(result["metrics"]["rmse"] for result in inner_results) / len(inner_results)
    correlations = [
        result["metrics"]["spearman"] for result in inner_results
        if result["metrics"]["spearman"] is not None
    ]
    return {
        "mean_inner_rmse": rmse,
        "mean_inner_spearman": (
            math.fsum(correlations) / len(correlations) if correlations else None
        ),
    }


def select_candidate(candidates):
    def key(candidate):
        mean_spearman = candidate["mean_inner_spearman"]
        return (
            candidate["mean_inner_rmse"],
            -mean_spearman if mean_spearman is not None else math.inf,
            json.dumps(candidate["config"], sort_keys=True),
        )

    return min(range(len(candidates)), key=lambda index: key(candidates[index]))


def environment_metadata():
    return {
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "numpy_version": np.__version__,
        "scipy_version": scipy_version,
        "sklearn_version": sklearn.__version__,
        "cpu_count": os.cpu_count(),
        "thread_environment": {
            name: os.environ.get(name)
            for name in (
                "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
    }


def git_metadata():
    root = Path(__file__).resolve().parents[1]
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True,
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"], cwd=root, check=True,
            capture_output=True, text=True, timeout=10,
        ).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        head = None
        dirty = None
    return {
        "head_sha": head,
        "worktree_dirty": dirty,
        "baseline_script_sha256": sha256_file(Path(__file__).resolve()),
    }


def prediction_csv_bytes(prediction_rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(PREDICTION_COLUMNS)
    for row in prediction_rows:
        writer.writerow([
            row["clean_row_index"],
            row["Name"],
            row["Gene"],
            row["outer_fold"],
            row["arm"],
            row["fit_id"],
            row["Fltr.SetGood"],
            row["Count.Prot"],
            format(row["observed_log1p_Count.Prot"], ".17g"),
            format(row["prediction_log1p_Count.Prot"], ".17g"),
        ])
    return buffer.getvalue().encode("utf-8")


def write_outputs(output_dir, prediction_payload, report):
    output_dir.mkdir(parents=True, exist_ok=False)
    created = []
    try:
        for name, payload in (
            ("predictions.csv", prediction_payload),
            ("run_report.json", json_bytes(report)),
        ):
            path = output_dir / name
            with path.open("xb") as handle:
                handle.write(payload)
            created.append(path)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        output_dir.rmdir()
        raise


def run_benchmark(clean_csv, split_json, protocol_path=None):
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    protocol_path = Path(protocol_path).expanduser().resolve() if protocol_path else DEFAULT_PROTOCOL
    protocol = load_protocol(protocol_path)
    clean_sha = sha256_file(clean_csv)
    split_sha = sha256_file(split_json)
    if clean_sha != protocol["inputs"]["clean_csv"]["sha256"]:
        raise ValueError("clean CSV SHA256 does not match the baseline protocol")
    if split_sha != protocol["inputs"]["split_json"]["sha256"]:
        raise ValueError("frozen split SHA256 does not match the baseline protocol")
    split = load_json(split_json)
    clean_rows = read_clean(clean_csv)
    if len(clean_rows) != protocol["inputs"]["clean_csv"]["expected_data_rows"]:
        raise ValueError("clean CSV row count does not match the baseline protocol")
    if split.get("input_sha256", {}).get("clean_csv") != clean_sha:
        raise ValueError("clean CSV SHA256 does not match the frozen split")
    if split.get("input", {}).get("data_rows") != len(clean_rows):
        raise ValueError("clean CSV row count does not match the frozen split")
    if split.get("input", {}).get("gene_count") != len({row["Gene"] for row in clean_rows}):
        raise ValueError("clean CSV Gene count does not match the frozen split")
    partitions = validate_split(split, clean_rows)
    eligible = prepare_records(clean_rows)
    if len(eligible) != protocol["inputs"]["clean_csv"]["expected_setgood_rows"]:
        raise ValueError("SetGood row count does not match the baseline protocol")
    by_gene = {}
    for record in eligible:
        by_gene.setdefault(record["Gene"], []).append(record)
    clean_gene_counts = Counter(row["Gene"] for row in clean_rows)
    fit_records = []
    prediction_rows = []
    outer_results = []

    for outer_index, partition in enumerate(partitions):
        test_records = sorted(
            (record for gene in partition["test"] for record in by_gene.get(gene, [])),
            key=lambda record: record["clean_row_index"],
        )
        for arm in ARMS:
            candidates = []
            for candidate_index, config in enumerate(candidate_configs(arm)):
                inner_results = []
                for inner_index, validation_genes in enumerate(partition["inner"]):
                    fit_genes = partition["train"] - validation_genes
                    fit_rows = sorted(
                        (record for gene in fit_genes for record in by_gene.get(gene, [])),
                        key=lambda record: record["clean_row_index"],
                    )
                    validation_rows = sorted(
                        (record for gene in validation_genes for record in by_gene.get(gene, [])),
                        key=lambda record: record["clean_row_index"],
                    )
                    if not fit_rows or not validation_rows:
                        raise ValueError("every inner fit and validation pool must contain SetGood rows")
                    fit_id = (
                        f"outer-{outer_index}__{arm}__inner-{inner_index}"
                        f"__candidate-{candidate_index}"
                    )
                    predict, details = fit_model(fit_rows, arm, config)
                    validation_predictions = predict(validation_rows)
                    metrics = regression_metrics(validation_rows, validation_predictions)
                    fit_record = {
                        "fit_id": fit_id,
                        "selection_role": "inner_candidate",
                        "outer_fold": outer_index,
                        "inner_fold": inner_index,
                        "candidate_index": candidate_index,
                        "arm": arm,
                        "config": config,
                        "fit_train_gene_sha256": gene_set_sha256(fit_genes),
                        "evaluation_gene_sha256": gene_set_sha256(validation_genes),
                        "evaluation_rows": len(validation_rows),
                        "fit_train_gene_count": len(fit_genes),
                        "evaluation_gene_count": len(validation_genes),
                        **details,
                    }
                    fit_records.append(fit_record)
                    inner_results.append({
                        "inner_fold": inner_index,
                        "fit_id": fit_id,
                        "validation_rows": len(validation_rows),
                        "metrics": metrics,
                    })
                candidates.append({
                    "candidate_index": candidate_index,
                    "config": config,
                    "inner_fold_results": inner_results,
                    **mean_metrics(inner_results),
                })
            selected_index = select_candidate(candidates)
            selected_config = candidates[selected_index]["config"]
            final_fit_id = f"outer-{outer_index}__{arm}__outer-final"
            fit_rows = sorted(
                (record for gene in partition["train"] for record in by_gene.get(gene, [])),
                key=lambda record: record["clean_row_index"],
            )
            predict, details = fit_model(fit_rows, arm, selected_config)
            fit_record = {
                "fit_id": final_fit_id,
                "selection_role": "outer_final_refit",
                "outer_fold": outer_index,
                "inner_fold": None,
                "candidate_index": selected_index,
                "arm": arm,
                "config": selected_config,
                "fit_train_gene_sha256": gene_set_sha256(partition["train"]),
                "evaluation_gene_sha256": None,
                "evaluation_rows": 0,
                "fit_train_gene_count": len(partition["train"]),
                "evaluation_gene_count": 0,
                **details,
            }
            fit_records.append(fit_record)
            prediction_start = time.perf_counter()
            predictions = predict(test_records)
            prediction_seconds = time.perf_counter() - prediction_start
            metrics = regression_metrics(test_records, predictions)
            for record, prediction in zip(test_records, predictions):
                prediction_rows.append({
                    "clean_row_index": record["clean_row_index"],
                    "Name": record["Name"],
                    "Gene": record["Gene"],
                    "outer_fold": outer_index,
                    "arm": arm,
                    "fit_id": final_fit_id,
                    "Fltr.SetGood": record["Fltr.SetGood"],
                    "Count.Prot": record["Count.Prot.token"],
                    "observed_log1p_Count.Prot": record["y"],
                    "prediction_log1p_Count.Prot": float(prediction),
                })
            arm_fit_ids = [
                result["fit_id"]
                for candidate in candidates
                for result in candidate["inner_fold_results"]
            ]
            inner_wall = math.fsum(
                record["wall_time_seconds"] for record in fit_records
                if record["fit_id"] in arm_fit_ids
            )
            inner_cpu = math.fsum(
                record["process_cpu_time_seconds"] for record in fit_records
                if record["fit_id"] in arm_fit_ids
            )
            outer_results.append({
                "outer_fold": outer_index,
                "arm": arm,
                "test_rows": len(test_records),
                "test_gene_count": len(partition["test"]),
                "prediction_rows": len(test_records),
                "metrics": metrics,
                "selection": {
                    "strategy": "four_inner_folds_only",
                    "selection_metric": "mean_inner_rmse_log1p_Count.Prot",
                    "tie_breakers": ["higher_mean_inner_spearman", "canonical_config_json"],
                    "outer_test_used": False,
                    "candidates": candidates,
                    "selected_candidate_index": selected_index,
                    "selected_config": selected_config,
                },
                "final_fit_id": final_fit_id,
                "inner_cv_wall_time_seconds": inner_wall,
                "inner_cv_process_cpu_time_seconds": inner_cpu,
                "final_fit_wall_time_seconds": details["wall_time_seconds"],
                "final_fit_process_cpu_time_seconds": details["process_cpu_time_seconds"],
                "total_fit_wall_time_seconds": inner_wall + details["wall_time_seconds"],
                "total_fit_process_cpu_time_seconds": inner_cpu + details["process_cpu_time_seconds"],
                "prediction_wall_time_seconds": prediction_seconds,
            })

    prediction_payload = prediction_csv_bytes(prediction_rows)
    report = {
        "schema": RUN_SCHEMA,
        "protocol": PROTOCOL,
        "status": "completed_development_benchmark",
        "scope": {
            "development_benchmark": True,
            "untouched_evaluation": False,
            "mechanism_evidence": False,
            "sota_claim": False,
            "supported_ood": "Gene-grouped N-terminal fragment construct OOD",
            "protein_ood": False,
            "full_length_cds": False,
            "native_utr": False,
        },
        "data": {
            "clean_csv": str(clean_csv),
            "split_json": str(split_json),
            "protocol_json": str(protocol_path),
            "clean_sha256": clean_sha,
            "split_sha256": split_sha,
            "protocol_sha256": sha256_file(protocol_path),
            "clean_data_rows": len(clean_rows),
            "clean_gene_count": len(clean_gene_counts),
            "eligible_SetGood_rows": len(eligible),
            "excluded_non_SetGood_rows": len(clean_rows) - len(eligible),
            "analysis_filter": {
                "column": "Fltr.SetGood",
                "operator": "==",
                "value": "TRUE",
                "applied_in_memory_for_primary_analysis_only": True,
            },
            "raw_csv_read": False,
            "clean_file_modified": False,
            "raw_or_clean_filtering_applied": False,
            "clean_rows_removed_or_overwritten": 0,
            "untouched_inputs_read": False,
            "outcome": {
                "source_column": "Count.Prot",
                "transform": "log1p",
                "evaluation_scale": "log1p_Count.Prot",
                "top_decile_enrichment_scale": "untransformed_Count.Prot",
                "top_decile_definition": (
                    "Mean observed Count.Prot in the highest-predicted ceil(n/10) rows "
                    "divided by mean observed Count.Prot in all rows; prediction ties "
                    "are ordered by clean_row_index."
                ),
            },
            "outer_folds": OUTER_FOLDS,
            "inner_folds_per_outer": INNER_FOLDS,
        },
        "features": {
            "numeric": list(NUMERIC_FEATURES),
            "categorical": list(CATEGORICAL_FEATURES),
            "sequence": "11 positional codon one-hot blocks over a fixed 64-codon vocabulary",
            "maximum_categories_per_categorical_field": MAX_CATEGORIES_PER_FIELD,
            "maximum_full_feature_count": MAX_FULL_FEATURES,
            "numeric_preprocessing": "train-only mean and population standard deviation; zero variance maps to scale 1",
            "categorical_preprocessing": (
                "train-only frequency selection of at most 15 observed levels plus one "
                "other/unknown level per field"
            ),
            "outer_test_used_for_preprocessing": False,
        },
        "selection_protocol": {
            "candidates": {
                "constant": [{}],
                "univariate": "one train-fitted standardized least-squares coefficient; no hyperparameter selection",
                "ridge_alpha": list(RIDGE_ALPHAS),
                "histgb_learning_rate": list(HISTGB_LEARNING_RATES),
                "histgb_l2_regularization": list(HISTGB_L2_VALUES),
            },
            "histgb_max_iter": HISTGB_MAX_ITER,
            "histgb_n_iter_no_change": HISTGB_N_ITER_NO_CHANGE,
            "histgb_validation_fraction": HISTGB_VALIDATION_FRACTION,
            "random_state": RANDOM_STATE,
            "outer_test_used": False,
        },
        "arms": list(ARMS),
        "environment": environment_metadata(),
        "git": git_metadata(),
        "predictions": {
            "file": "predictions.csv",
            "columns": list(PREDICTION_COLUMNS),
            "rows": len(prediction_rows),
            "sha256": hashlib.sha256(prediction_payload).hexdigest(),
        },
        "fit_records": fit_records,
        "outer_results": outer_results,
        "total_wall_time_seconds": time.perf_counter() - started_wall,
        "total_process_cpu_time_seconds": time.process_time() - started_cpu,
        "limitations": [
            "Development benchmark only; not untouched, mechanism, protein-OOD or SOTA evidence.",
            "Raw and clean artifacts remain unfiltered; only the primary in-memory analysis uses Fltr.SetGood == TRUE.",
            "Metrics are computed on log1p(Count.Prot), except top-decile enrichment on observed Count.Prot.",
            "HistGB n_iter is the observed fitted value; reaching max_iter is not reported as convergence.",
        ],
    }
    return prediction_payload, report


def main(argv=None):
    args = parse_args(argv)
    clean_csv = input_file(args.clean_csv, "clean CSV")
    split_json = input_file(args.split_json, "split JSON")
    protocol_json = input_file(args.protocol, "baseline protocol")
    output_dir = Path(args.output_dir).expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {output_dir}")
    prediction_payload, report = run_benchmark(clean_csv, split_json, protocol_json)
    write_outputs(output_dir, prediction_payload, report)
    print(json.dumps({
        "status": report["status"],
        "output_dir": str(output_dir),
        "prediction_rows": report["predictions"]["rows"],
        "eligible_SetGood_rows": report["data"]["eligible_SetGood_rows"],
        "arms": len(ARMS),
        "outer_folds": OUTER_FOLDS,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
