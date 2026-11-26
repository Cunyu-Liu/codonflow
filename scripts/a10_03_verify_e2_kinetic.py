#!/usr/bin/env python3
"""Independently verify A10-03/E2 v3/v4 artifacts without production imports.

The verifier rebuilds RK37 QC/density/mask and transcript-grouped nested folds
from the raw header/codon/count matrix, rejecting exact CDS/ID conflicts. It
recomputes fixed-rung top2 selection, rejected-at-rung status, rung-last-state
resume history and selected-only plateau stopping without a final epoch cap.
It also audits parameter matching, CUDA and cost records. Selected inner states are used to rebuild every score,
rate, independent SciPy steady state and outer ensemble prediction. Ensemble
means are density ensembles, never a claim of a common steady state.

TB-MSE, per-transcript Pearson/Spearman, paired bootstrap/sign-flip inference,
two-comparator Holm correction and seed-first pooled inference are recomputed.
Default mode pins the Mohammad16 input and all frozen scientific numerics.
Synthetic tests must explicitly pass ``allow_synthetic=True`` or
``--allow-synthetic``. Verification JSON is always created exclusively.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares, root
from scipy.special import expit


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_PATH = ROOT / "scripts" / "a10_03_e2_kinetic.py"
MEAN_FIELD_OPERATOR_PATH = ROOT / "src" / "codonflow" / "models" / "kinetic_mean_field.py"
PARALLEL_IMPLEMENTATION_PATH = ROOT / "scripts" / "a10_03_e2_kinetic_parallel.py"
PARALLEL_SCHEMA = "a10-03-e2-kinetic-parallel-v1"
PROTOCOL = "a10_03_e2_kinetic_protocol_v3"
PROTOCOL_SCHEMA = "a10-03-e2-kinetic-protocol-v3"
SUMMARY_SCHEMA = "a10-03-e2-kinetic-summary-v4"
SPLIT_SCHEMA = "a10-03-e2-kinetic-splits-v3"
SELECTION_SCHEMA = "a10-03-e2-kinetic-selection-v4"
CURVE_SCHEMA = "a10-03-e2-kinetic-curve-v4"
PROVENANCE_SCHEMA = "a10-03-e2-kinetic-startup-provenance-v3"
STATE_SCHEMA = "a10-03-e2-kinetic-selected-inner-states-v3"
VERIFICATION_SCHEMA = "a10-03-e2-kinetic-independent-verification-v4"
REAL_RAW_SHA256 = "d093a3b0c53aa90d0626cc277a65a558c538ecbeb4d1cda091f02aad134588bc"
REAL_ELIGIBLE = 1073
ARMS = ("independent", "position", "kinetic")
COMPARATORS = ("independent", "position")
REAL_MODEL_SEEDS = [1234, 2345, 3456]
REAL_SPLIT_SEED = 9100301
INFERENCE_SEED = 9100302
REAL_RESAMPLES = 20000
REBUILD_ATOL = 2e-8
MEMBER_RESIDUAL_TOLERANCE = 1e-10
ROOT_TOLERANCE = 1e-12
ROOT_MAXFEV = 1000
REAL_QC = {
    "input_records": 1761,
    "rejected_too_short": 0,
    "rejected_missing_start_atg": 171,
    "rejected_missing_terminal_stop": 0,
    "rejected_internal_stop": 0,
    "rejected_coverage": 517,
    "rejected_no_unmasked_positive_position": 0,
    "eligible_transcripts": REAL_ELIGIBLE,
    "sha256": REAL_RAW_SHA256,
    "minimum_eligible_length": 16,
    "maximum_eligible_length": 1521,
}
REAL_FROZEN_VALUES = {
    ("inputs", "expected_eligible_transcripts"): REAL_ELIGIBLE,
    ("preprocessing", "masked_first_positions"): 5,
    ("preprocessing", "masked_last_positions"): 4,
    ("preprocessing", "minimum_length"): 10,
    ("split", "outer_folds"): 3,
    ("split", "inner_folds"): 3,
    ("split", "seed"): REAL_SPLIT_SEED,
    ("model", "trainable_parameters_per_model"): {"independent": 65, "position": 1, "kinetic": 65},
    ("model", "selected_inner_ensemble_members"): 3,
    ("model", "trainable_parameters_per_selected_ensemble"): {"independent": 195, "position": 3, "kinetic": 195},
    ("model", "rate_floor"): 0.0001,
    ("model", "rate_ceiling"): 1000.0,
    ("training", "model_seeds"): REAL_MODEL_SEEDS,
    ("training", "minimum_model_seeds"): 3,
    ("training", "batch_transcripts"): 32,
    ("training", "successive_halving", "rung_epochs"): 50,
    ("training", "successive_halving", "retained_candidates_per_arm"): 2,
    ("training", "gradient_clip_norm"): 1.0,
    ("training", "early_stopping", "min_absolute_improvement"): 0.000001,
    ("training", "early_stopping", "patience_epochs"): 25,
    ("hyperparameters", "learning_rate", "minimum"): 0.0001,
    ("hyperparameters", "learning_rate", "maximum"): 0.01,
    ("hyperparameters", "learning_rate", "count"): 3,
    ("hyperparameters", "weight_decays"): [0.0, 0.0001],
}
CODON_ALPHABET = "TCAG"
CODONS = tuple(a + b + c for a in CODON_ALPHABET for b in CODON_ALPHABET for c in CODON_ALPHABET)
CODON_TO_INDEX = {codon: index for index, codon in enumerate(CODONS)}
STOP_CODONS = frozenset({"TAA", "TAG", "TGA"})
OUTPUT_FILES = (
    "provenance.json", "splits.json", "curves.jsonl", "selection.json",
    "selected_inner_states.npz", "predictions.npz", "per_transcript_metrics.csv", "summary.json",
)
ARTIFACT_FILES = OUTPUT_FILES[:-1]
CSV_FIELDS = [
    "seed", "arm", "outer_fold", "transcript_index", "transcript_id", "length",
    "n_positions", "mse", "pearson", "spearman",
    "solver_max_abs_normalized_residual",
]
PREDICTION_ARRAYS = (
    "seeds", "arms", "transcript_indices", "transcript_ids", "lengths", "codons",
    "target", "mask", "outer_fold", "prediction", "flux",
    "ensemble_mean_residual_diagnostic", "solver_max_abs_normalized_residual",
    "ensemble_mean_is_common_steady_state", "kinetic_conservation_level",
)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(payload):
    return (json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


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
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def is_number(value, positive=False, nonnegative=False):
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(value) and (not positive or value > 0)
        and (not nonnegative or value >= 0)
    )


def is_integer(value, minimum=None):
    return isinstance(value, int) and not isinstance(value, bool) and (minimum is None or value >= minimum)


def learning_rate_grid(config):
    if config.get("spacing") != "log10_uniform":
        raise ValueError("learning rates must be log10-uniform")
    minimum, maximum = config.get("minimum"), config.get("maximum")
    count = config.get("count")
    if not is_number(minimum, positive=True) or not is_number(maximum, positive=True) or minimum > maximum:
        raise ValueError("invalid learning-rate bounds")
    if not is_integer(count, 1):
        raise ValueError("learning-rate count must be positive")
    return np.logspace(math.log10(minimum), math.log10(maximum), count).tolist()


def load_protocol(path, allow_synthetic=False):
    protocol = load_json(path)
    if protocol.get("schema") != PROTOCOL_SCHEMA or protocol.get("protocol") != PROTOCOL:
        raise ValueError("E2 protocol identity mismatch")
    scope = protocol.get("scope", {})
    for key in ("development_only",):
        if scope.get(key) is not True:
            raise ValueError(f"scope.{key} must be true")
    for key in (
        "untouched", "final_research_ood", "absolute_elongation_rates",
        "exact_stochastic_simulation", "sota_claim", "positive_kinetic_claim_presupposed",
    ):
        if scope.get(key) is not False:
            raise ValueError(f"scope.{key} must be false")
    inputs = protocol.get("inputs", {})
    if any((
        inputs.get("raw_path_supplied_by_cli") is not True,
        inputs.get("untouched_inputs_read") is not False,
        inputs.get("format") != "strict three-line records: header, codon line, count line",
        inputs.get("identity_conflicts") != "duplicate transcript ID or duplicate exact normalized CDS is a fatal input conflict",
        re.fullmatch(r"[0-9a-f]{64}", inputs.get("sha256", "")) is None,
    )):
        raise ValueError("raw input contract mismatch")
    expected = inputs.get("expected_eligible_transcripts")
    if not is_integer(expected, 9):
        raise ValueError("3 by 3 nested CV requires at least nine eligible transcripts")
    preprocessing = protocol.get("preprocessing", {})
    if any((
        preprocessing.get("convention") != "RK37",
        preprocessing.get("positive_rule") != "count > 0.5",
        preprocessing.get("coverage_rule") != "mean(count > 0.5) > 0.6 over all codon positions",
        preprocessing.get("density_rule") != "count / mean(count[count > 0.5]) using all positions in that transcript",
        preprocessing.get("loss_evaluation_mask") != "(count > 0.5) and zero-based position >= 5 and position < L - 4",
        preprocessing.get("masked_first_positions") != 5,
        preprocessing.get("masked_last_positions") != 4,
        preprocessing.get("minimum_length") != 10,
        preprocessing.get("identity_rule") != "transcript ID and exact normalized CDS must each be unique",
        preprocessing.get("start_codon_rule") != "first codon must be ATG",
        preprocessing.get("terminal_stop_rule") != "last codon must be TAA, TAG or TGA",
        preprocessing.get("internal_stop_rule") != "no TAA, TAG or TGA before the terminal codon",
        preprocessing.get("qc_rejection_precedence") != "length, ATG, terminal stop, internal stop, coverage, unmasked positive position",
        preprocessing.get("low_count_targets_masked") is not True,
    )):
        raise ValueError("preprocessing must match frozen RK37 rules")
    split = protocol.get("split", {})
    if any((
        split.get("unit") != "transcript", split.get("outer_folds") != 3,
        split.get("inner_folds") != 3,
        split.get("algorithm") != "numpy_default_rng_permutation_then_sorted_np_array_split",
        split.get("shared_across_arms_and_model_seeds") is not True,
        split.get("outer_test_targets_used_for_fitting_early_stopping_or_selection") is not False,
        split.get("final_predictor") != "equal-weight density ensemble of the three selected inner-fold models",
        not is_integer(split.get("seed")),
    )):
        raise ValueError("exact-CDS/ID isolated nested split contract mismatch")
    model = protocol.get("model", {})
    if any((
        model.get("arms") != list(ARMS),
        model.get("shared_score_field") != "independent/kinetic: codon_embedding_64_by_1[codon_i] + relative_position_weight * i / (L - 1)",
        model.get("position_score_field") != "relative_position_weight * i / (L - 1), without codon parameters or bias",
        model.get("trainable_parameters_per_model") != {"independent": 65, "position": 1, "kinetic": 65},
        model.get("extra_modules") is not False,
        model.get("independent_density") != "sigmoid(score)",
        model.get("position_density") != "sigmoid(relative_position_weight * i / (L - 1))",
        model.get("kinetic_rate") != "clamp(rate_floor + softplus(score), max=rate_ceiling)",
        model.get("boundary_mapping") != "alpha=rate[0]; k=rate[0:L-1]; beta=rate[L-1]",
        model.get("selected_inner_ensemble_members") != 3,
        model.get("trainable_parameters_per_selected_ensemble") != {"independent": 195, "position": 3, "kinetic": 195},
        not is_number(model.get("rate_floor"), positive=True),
        not is_number(model.get("rate_ceiling"), positive=True),
        model["rate_floor"] >= model["rate_ceiling"],
    )):
        raise ValueError("independent/kinetic/position parameter contract mismatch")
    training = protocol.get("training", {})
    seeds = training.get("model_seeds")
    if (
        not isinstance(seeds, list) or len(seeds) < 3 or len(set(seeds)) != len(seeds)
        or not all(is_integer(seed, 1) for seed in seeds)
        or training.get("minimum_model_seeds") != 3
        or training.get("record_every_epoch_train_and_validation_curve") is not True
        or training.get("record_rung_and_resume_history") is not True
        or training.get("optimizer") != "AdamW"
        or training.get("dtype") != "float64"
        or training.get("gradient_clip_error_if_nonfinite") is not True
        or training.get("finite_parameters_required_after_optimizer_step") is not True
        or not is_integer(training.get("batch_transcripts"), 1)
        or not is_number(training.get("gradient_clip_norm"), positive=True)
        or training.get("final_epoch_limit") is not None
        or training.get("resume_from_rung_last_state") is not True
        or training.get("resume_optimizer_and_rng_state") is not True
        or training.get("selected_candidates_stop_only_on_validation_plateau") is not True
        or training.get("rung_rejection_is_not_convergence") is not True
    ):
        raise ValueError("at least three seeds, complete curves and no continuation epoch cap are required")
    halving = training.get("successive_halving", {})
    if any((
        not is_integer(halving.get("rung_epochs"), 1),
        halving.get("rung_is_fixed_and_never_early_stopped") is not True,
        halving.get("retained_candidates_per_arm") != 2,
        halving.get("ranking_metric") != "inner_oof_validation_tb_mse_at_rung_last_epoch",
        halving.get("ranking_scope") != "within each seed, outer fold and arm across the unchanged hyperparameter grid",
        halving.get("tie_break") != "protocol grid order",
        halving.get("rejected_stop_reason") != "rejected_at_rung_not_converged",
    )):
        raise ValueError("successive-halving rung/top2/continuation contract mismatch")
    stopping = training.get("early_stopping", {})
    if any((
        stopping.get("monitor") != "inner validation transcript-balanced MSE",
        stopping.get("mode") != "min",
        not is_number(stopping.get("min_absolute_improvement"), nonnegative=True),
        not is_integer(stopping.get("patience_epochs"), 1),
        stopping.get("restore_best_validation_state") is not True,
    )):
        raise ValueError("inner validation plateau stopping contract mismatch")
    hyper = protocol.get("hyperparameters", {})
    learning_rate_grid(hyper.get("learning_rate", {}))
    decays = hyper.get("weight_decays")
    if not isinstance(decays, list) or not decays or not all(is_number(value, nonnegative=True) for value in decays):
        raise ValueError("weight-decay grid must be finite and nonnegative")
    if any((
        hyper.get("rung_selection_metric") != "inner out-of-fold transcript-balanced MSE at each fold's rung last state",
        hyper.get("selection_metric") != "inner out-of-fold transcript-balanced MSE at each fold's restored best-validation state after resume",
    )):
        raise ValueError("rung and resumed hyperparameter selection must use inner OOF TB-MSE only")
    runtime = protocol.get("runtime", {})
    if any((
        runtime.get("device") != "cuda", runtime.get("cpu_fallback") is not False,
        runtime.get("cuda_forward_backward_probe_required") is not True,
    )):
        raise ValueError("real CUDA without CPU fallback is required")
    evaluation = protocol.get("evaluation", {})
    if any((
        evaluation.get("split") != "outer test only",
        evaluation.get("primary_metric") != "transcript_balanced_mse",
        evaluation.get("secondary_metrics") != ["mean_per_transcript_pearson", "mean_per_transcript_spearman"],
        evaluation.get("kinetic_effect") != "primary: independent TB-MSE minus kinetic TB-MSE; positive favors kinetic",
        evaluation.get("position_control_effect") != "position TB-MSE minus kinetic TB-MSE; positive favors kinetic over the simple position control",
        evaluation.get("ensemble_mean_is_common_steady_state") is not False,
        evaluation.get("development_comparison_only") is not True,
    )):
        raise ValueError("evaluation contract mismatch")
    outputs = protocol.get("outputs", {})
    if any((
        outputs.get("overwrite") != "forbidden",
        outputs.get("v3_requires_new_directory_not_v1_or_v2_output") is not True,
        outputs.get("files") != list(OUTPUT_FILES),
        outputs.get("ensemble_mean_residual_diagnostic") != "arithmetic diagnostic only; not a common steady-state residual",
    )):
        raise ValueError("v3 outputs must be exclusive, separate from v1/v2 and explicit about ensemble diagnostics")
    if not allow_synthetic:
        if any((
            inputs.get("sha256") != REAL_RAW_SHA256,
            expected != REAL_ELIGIBLE,
            inputs.get("expected_basename") != "Mohammad16.txt",
        )):
            raise ValueError(f"real verification requires pinned Mohammad16 SHA and {REAL_ELIGIBLE} eligible transcripts")
        mismatches = []
        for path_parts, expected_value in REAL_FROZEN_VALUES.items():
            observed = protocol
            for part in path_parts:
                observed = observed.get(part) if isinstance(observed, dict) else None
            mismatches.extend(value_mismatches(observed, expected_value, ".".join(path_parts)))
        if mismatches:
            raise ValueError(f"real verification violates frozen scientific numerics: {mismatches}")
    return protocol


def parse_codon_line(line, record_number):
    tokens = line.replace(",", " ").split()
    if len(tokens) == 1 and len(tokens[0]) % 3 == 0:
        sequence = tokens[0]
        tokens = [sequence[index:index + 3] for index in range(0, len(sequence), 3)]
    if not tokens or any(len(token) != 3 for token in tokens):
        raise ValueError(f"record {record_number}: invalid codon row")
    indices = []
    for token in tokens:
        codon = token.upper().replace("U", "T")
        if codon not in CODON_TO_INDEX:
            raise ValueError(f"record {record_number}: invalid codon {token!r}")
        indices.append(CODON_TO_INDEX[codon])
    return np.asarray(indices, dtype=np.int64)


def parse_raw(path):
    """Independently parse raw triplets and apply RK37 eligibility and normalization."""
    with Path(path).open("r", encoding="utf-8-sig", errors="strict") as handle:
        lines = [line.strip() for line in handle if line.strip()]
    if not lines or len(lines) % 3:
        raise ValueError("raw matrix must contain nonempty header/codon/count triplets")
    records = []
    seen = {}
    seen_cds = {}
    qc = {
        "input_records": len(lines) // 3,
        "rejected_too_short": 0,
        "rejected_missing_start_atg": 0,
        "rejected_missing_terminal_stop": 0,
        "rejected_internal_stop": 0,
        "rejected_coverage": 0,
        "rejected_no_unmasked_positive_position": 0,
    }
    for number, offset in enumerate(range(0, len(lines), 3), 1):
        header, codon_line, count_line = lines[offset:offset + 3]
        if not header.startswith(">") or not header[1:].strip():
            raise ValueError(f"record {number}: invalid header")
        transcript_id = header[1:].strip().split()[0]
        if transcript_id in seen:
            raise ValueError(f"record {number}: transcript ID conflict {transcript_id!r} with record {seen[transcript_id]}")
        codons = parse_codon_line(codon_line, number)
        exact_cds = tuple(codons.tolist())
        if exact_cds in seen_cds:
            previous_number, previous_id = seen_cds[exact_cds]
            raise ValueError(f"record {number}: exact CDS conflict with record {previous_number} ({previous_id!r})")
        seen[transcript_id] = number
        seen_cds[exact_cds] = (number, transcript_id)
        try:
            counts = np.asarray([float(value) for value in count_line.replace(",", " ").split()], dtype=np.float64)
        except ValueError as exc:
            raise ValueError(f"record {number}: invalid count row") from exc
        if counts.ndim != 1 or len(counts) != len(codons) or not np.all(np.isfinite(counts)) or np.any(counts < 0):
            raise ValueError(f"record {number}: counts must be finite, nonnegative and length-matched")
        length = len(codons)
        if length < 10:
            qc["rejected_too_short"] += 1
            continue
        codon_strings = [CODONS[index] for index in codons]
        if codon_strings[0] != "ATG":
            qc["rejected_missing_start_atg"] += 1
            continue
        if codon_strings[-1] not in STOP_CODONS:
            qc["rejected_missing_terminal_stop"] += 1
            continue
        if any(codon in STOP_CODONS for codon in codon_strings[:-1]):
            qc["rejected_internal_stop"] += 1
            continue
        positive = counts > 0.5
        coverage = float(np.mean(positive))
        if coverage <= 0.6:
            qc["rejected_coverage"] += 1
            continue
        positions = np.arange(length)
        mask = positive & (positions >= 5) & (positions < length - 4)
        if not np.any(mask):
            qc["rejected_no_unmasked_positive_position"] += 1
            continue
        positive_mean = float(np.mean(counts[positive]))
        records.append({
            "index": len(records), "transcript_id": transcript_id, "codons": codons,
            "counts": counts, "density": counts / positive_mean, "mask": mask,
            "coverage": coverage, "positive_mean": positive_mean, "length": length,
        })
    qc.update({
        "eligible_transcripts": len(records),
        "sha256": sha256_file(path),
        "minimum_eligible_length": min((record["length"] for record in records), default=None),
        "maximum_eligible_length": max((record["length"] for record in records), default=None),
    })
    return records, qc


def assert_exact_cds_id_isolation(splits, records):
    def identities(indices):
        selected = [records[int(index)] for index in indices]
        return (
            {record["codons"].tobytes() for record in selected},
            {record["transcript_id"] for record in selected},
        )

    for outer in splits:
        test_cds, test_ids = identities(outer["test"])
        development_cds = set()
        development_ids = set()
        for inner in outer["inner"]:
            train_cds, train_ids = identities(inner["train"])
            validation_cds, validation_ids = identities(inner["validation"])
            if train_cds & validation_cds or train_ids & validation_ids:
                raise RuntimeError("exact CDS/ID leakage between inner train and validation")
            if (train_cds | validation_cds) & test_cds or (train_ids | validation_ids) & test_ids:
                raise RuntimeError("exact CDS/ID leakage into outer test")
            development_cds |= validation_cds
            development_ids |= validation_ids
        all_cds, all_ids = identities([record["index"] for record in records])
        if development_cds != all_cds - test_cds or development_ids != all_ids - test_ids:
            raise RuntimeError("inner validation folds do not partition outer development exactly once")


def make_nested_splits(records, seed):
    indices = np.asarray([record["index"] for record in records], dtype=np.int64)
    if len(indices) < 9 or len(set(indices.tolist())) != len(indices):
        raise ValueError("nested CV requires at least nine unique transcript indices")
    permutation = np.random.default_rng(seed).permutation(indices)
    outer_tests = [np.sort(fold).astype(np.int64) for fold in np.array_split(permutation, 3)]
    splits = []
    for outer_fold, test in enumerate(outer_tests):
        development = np.sort(np.setdiff1d(indices, test, assume_unique=True))
        inner_permutation = np.random.default_rng([seed, outer_fold, 917]).permutation(development)
        validations = [np.sort(fold).astype(np.int64) for fold in np.array_split(inner_permutation, 3)]
        inner = []
        for inner_fold, validation in enumerate(validations):
            train = np.sort(np.setdiff1d(development, validation, assume_unique=True))
            if np.intersect1d(train, validation).size or np.intersect1d(train, test).size or np.intersect1d(validation, test).size:
                raise RuntimeError("nested transcript split leakage")
            inner.append({"inner_fold": inner_fold, "train": train, "validation": validation})
        splits.append({"outer_fold": outer_fold, "test": test, "inner": inner})
    if not np.array_equal(np.sort(np.concatenate([item["test"] for item in splits])), indices):
        raise RuntimeError("outer folds do not partition transcripts")
    assert_exact_cds_id_isolation(splits, records)
    return splits


def split_payload(splits, records):
    return {
        "schema": SPLIT_SCHEMA,
        "protocol": PROTOCOL,
        "unit": "transcript",
        "outer_folds": [
            {
                "outer_fold": outer["outer_fold"],
                "test_indices": outer["test"].tolist(),
                "test_transcript_ids": [records[int(index)]["transcript_id"] for index in outer["test"]],
                "inner_folds": [
                    {
                        "inner_fold": inner["inner_fold"],
                        "train_indices": inner["train"].tolist(),
                        "validation_indices": inner["validation"].tolist(),
                        "train_transcript_ids": [records[int(index)]["transcript_id"] for index in inner["train"]],
                        "validation_transcript_ids": [records[int(index)]["transcript_id"] for index in inner["validation"]],
                    }
                    for inner in outer["inner"]
                ],
            }
            for outer in splits
        ],
    }


def value_mismatches(observed, expected, path=""):
    if expected is None:
        return [] if observed is None else [path]
    if isinstance(expected, bool):
        return [] if observed is expected else [path]
    if isinstance(expected, int):
        return [] if is_integer(observed) and observed == expected else [path]
    if isinstance(expected, float):
        if not is_number(observed):
            return [path]
        return [] if math.isclose(observed, expected, rel_tol=1e-9, abs_tol=1e-11) else [path]
    if isinstance(expected, str):
        return [] if observed == expected else [path]
    if isinstance(expected, list):
        if not isinstance(observed, list) or len(observed) != len(expected):
            return [path]
        return [
            mismatch for index, (left, right) in enumerate(zip(observed, expected))
            for mismatch in value_mismatches(left, right, f"{path}[{index}]")
        ]
    if isinstance(expected, dict):
        if not isinstance(observed, dict) or set(observed) != set(expected):
            return [path]
        return [
            mismatch for key, value in expected.items()
            for mismatch in value_mismatches(observed[key], value, f"{path}.{key}")
        ]
    return [path]


def curve_grid(protocol):
    rates = learning_rate_grid(protocol["hyperparameters"]["learning_rate"])
    decays = protocol["hyperparameters"]["weight_decays"]
    return [(lr, wd) for lr in rates for wd in decays]


def validate_curve(record, key, grid, protocol):
    seed, outer, inner, arm, grid_index = key
    required = {
        "schema", "seed", "outer_fold", "inner_fold", "arm", "grid_index",
        "learning_rate", "weight_decay", "rung_selected", "rung", "resume",
        "stop_reason", "validation_plateau_converged", "rung_rejection_is_not_convergence",
        "selected_candidates_have_no_final_epoch_cap", "epochs",
    }
    if set(record) != required or record["schema"] != CURVE_SCHEMA:
        raise ValueError("curve schema or fields mismatch")
    if (record["seed"], record["outer_fold"], record["inner_fold"], record["arm"], record["grid_index"]) != key:
        raise ValueError("curve key mismatch")
    lr, wd = grid[grid_index]
    if record["learning_rate"] != lr or record["weight_decay"] != wd:
        raise ValueError("curve hyperparameters differ from frozen grid")
    if any((
        not isinstance(record["rung_selected"], bool),
        record["rung_rejection_is_not_convergence"] is not True,
        record["selected_candidates_have_no_final_epoch_cap"] is not True,
    )):
        raise ValueError("rung rejection/no-final-cap boundaries missing")
    epochs = record["epochs"]
    rung_epochs = protocol["training"]["successive_halving"]["rung_epochs"]
    if not isinstance(epochs, list) or len(epochs) < rung_epochs:
        raise ValueError("every candidate must have the complete frozen rung history")
    previous_elapsed = 0.0
    validation = []
    for index, epoch in enumerate(epochs, 1):
        if set(epoch) != {"epoch", "train_tb_mse", "validation_tb_mse", "elapsed_seconds"}:
            raise ValueError("curve epoch fields mismatch")
        if epoch["epoch"] != index or not is_number(epoch["train_tb_mse"], nonnegative=True):
            raise ValueError("rung/resume epochs must be contiguous with finite train loss")
        if not is_number(epoch["validation_tb_mse"], nonnegative=True):
            raise ValueError("curve validation loss must be finite")
        if not is_number(epoch["elapsed_seconds"], nonnegative=True) or epoch["elapsed_seconds"] < previous_elapsed:
            raise ValueError("curve elapsed time must be finite and nondecreasing across resume")
        previous_elapsed = epoch["elapsed_seconds"]
        validation.append(float(epoch["validation_tb_mse"]))
    rung = record["rung"]
    if not isinstance(rung, dict) or set(rung) != {
        "epochs", "last_epoch", "last_validation_tb_mse", "last_state_sha256", "last_optimizer_state_sha256",
    }:
        raise ValueError("rung metadata fields mismatch")
    if any((
        rung["epochs"] != rung_epochs, rung["last_epoch"] != rung_epochs,
        not is_number(rung["last_validation_tb_mse"], nonnegative=True),
        not math.isclose(rung["last_validation_tb_mse"], validation[rung_epochs - 1], rel_tol=1e-9, abs_tol=1e-11),
        re.fullmatch(r"[0-9a-f]{64}", rung["last_state_sha256"]) is None,
        re.fullmatch(r"[0-9a-f]{64}", rung["last_optimizer_state_sha256"]) is None,
    )):
        raise ValueError("rung last epoch/loss/state metadata mismatch")
    stopping = protocol["training"]["early_stopping"]
    best_loss = math.inf
    best_epoch = None
    for epoch, value in enumerate(validation, 1):
        if value < best_loss - stopping["min_absolute_improvement"]:
            best_loss = value
            best_epoch = epoch
    if best_epoch is None:
        raise ValueError("curve has no best validation state")
    rung_last_validation = validation[rung_epochs - 1]
    rung_last_elapsed = epochs[rung_epochs - 1]["elapsed_seconds"]
    if not record["rung_selected"]:
        if any((
            len(epochs) != rung_epochs, record["resume"] is not None,
            record["stop_reason"] != "rejected_at_rung_not_converged",
            record["validation_plateau_converged"] is not False,
        )):
            raise ValueError("rejected rung candidates cannot be converged or resumed")
    else:
        resume = record["resume"]
        if not isinstance(resume, dict) or set(resume) != {
            "source", "source_epoch", "start_epoch", "rung_last_state_sha256",
            "restored_model_state_sha256", "rung_last_optimizer_state_sha256",
            "optimizer_state_restored", "rng_state_restored",
        }:
            raise ValueError("selected candidate resume metadata fields mismatch")
        if any((
            len(epochs) <= rung_epochs,
            resume["source"] != "rung_last_state", resume["source_epoch"] != rung_epochs,
            resume["start_epoch"] != rung_epochs + 1,
            resume["rung_last_state_sha256"] != rung["last_state_sha256"],
            resume["restored_model_state_sha256"] != rung["last_state_sha256"],
            resume["rung_last_optimizer_state_sha256"] != rung["last_optimizer_state_sha256"],
            resume["optimizer_state_restored"] is not True, resume["rng_state_restored"] is not True,
            record["stop_reason"] != "validation_plateau", record["validation_plateau_converged"] is not True,
        )):
            raise ValueError("selected candidates must restore rung-last model/optimizer/RNG and reach plateau")
        expected_stop_epoch = max(rung_epochs + 1, best_epoch + stopping["patience_epochs"])
        if len(epochs) != expected_stop_epoch:
            raise ValueError("selected validation plateau does not satisfy frozen patience")
    return {
        "promoted": record["rung_selected"], "best_epoch": best_epoch, "best_validation_tb_mse": best_loss,
        "rung_last_validation_tb_mse": rung_last_validation,
        "epochs_ran": len(epochs), "continuation_epochs_ran": len(epochs) - rung_epochs,
        "rung_last_elapsed_seconds": rung_last_elapsed,
        "last_elapsed_seconds": previous_elapsed,
    }


def grid_order_minimum(scores):
    return min(scores, key=lambda grid_index: (scores[grid_index], grid_index))


def audit_training(output_dir, protocol, splits):
    seeds = protocol["training"]["model_seeds"]
    grid = curve_grid(protocol)
    expected_curve_keys = {
        (seed, outer, inner, arm, grid_index)
        for seed in seeds for outer in range(3) for inner in range(3)
        for arm in ARMS for grid_index in range(len(grid))
    }
    curves = {}
    with (output_dir / "curves.jsonl").open("r", encoding="utf-8", errors="strict") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                record = json.loads(line, parse_constant=reject_nonfinite_json)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid curves.jsonl line {line_number}") from exc
            if not isinstance(record, dict):
                raise ValueError("curve row must be an object")
            key = tuple(record.get(name) for name in ("seed", "outer_fold", "inner_fold", "arm", "grid_index"))
            if key not in expected_curve_keys or key in curves:
                raise ValueError(f"duplicate or unexpected curve key {key}")
            curves[key] = {"audit": validate_curve(record, key, grid, protocol), "raw": record}
    if set(curves) != expected_curve_keys:
        raise ValueError("not all seed/arm/grid/inner curves were recorded")
    selection = load_json(output_dir / "selection.json")
    if selection.get("schema") != SELECTION_SCHEMA or selection.get("protocol") != PROTOCOL or set(selection) != {"schema", "protocol", "records"}:
        raise ValueError("selection.json identity mismatch")
    records = selection["records"]
    expected_selection_keys = {(seed, outer, arm) for seed in seeds for outer in range(3) for arm in ARMS}
    seen = set()
    all_fits = []
    fit_wall = 0.0
    rung_wall = 0.0
    continuation_wall = 0.0
    legacy_cumulative_cost_fits = 0
    epochs_ran = 0
    peak_memory = 0
    for record in records:
        required = {
            "seed", "outer_fold", "arm", "selected_grid_index", "rung_selected_grid_indices",
            "rung_selection_metric", "selection_metric", "outer_test_used_for_selection", "candidates",
        }
        if set(record) != required:
            raise ValueError("selection record fields mismatch")
        key = (record["seed"], record["outer_fold"], record["arm"])
        if key not in expected_selection_keys or key in seen:
            raise ValueError("duplicate or unexpected selection record")
        seen.add(key)
        seed, outer, arm = key
        if any((
            record["rung_selection_metric"] != "rung_inner_oof_tb_mse",
            record["selection_metric"] != "inner_oof_tb_mse_after_rung_resume",
            record["outer_test_used_for_selection"] is not False,
        )):
            raise ValueError("outer test participated in selection or final selection ignored rung resume")
        candidates = record["candidates"]
        if not isinstance(candidates, list) or len(candidates) != len(grid):
            raise ValueError("selection does not contain the complete LR/wd grid")
        rung_scores = []
        final_scores = {}
        for grid_index, (candidate, (lr, wd)) in enumerate(zip(candidates, grid)):
            if set(candidate) != {
                "grid_index", "learning_rate", "weight_decay", "folds", "rung_selected",
                "rung_inner_oof_tb_mse", "rung_inner_oof_transcripts",
                "inner_oof_tb_mse", "inner_oof_transcripts",
            }:
                raise ValueError("candidate fields mismatch")
            if candidate["grid_index"] != grid_index or candidate["learning_rate"] != lr or candidate["weight_decay"] != wd:
                raise ValueError("candidate grid order or values changed")
            folds = candidate["folds"]
            if not isinstance(folds, list) or len(folds) != 3:
                raise ValueError("candidate must contain all three inner folds")
            if not isinstance(candidate["rung_selected"], bool):
                raise ValueError("candidate promoted status must be boolean")
            weighted_rung_loss = 0.0
            weighted_final_loss = 0.0
            validation_count = 0
            for inner in range(3):
                fold = folds[inner]
                if set(fold) != {
                    "inner_fold", "rung_last_validation_tb_mse", "resumed_from_rung_last_state",
                    "best_epoch", "best_validation_tb_mse", "stop_reason",
                    "validation_plateau_converged", "cost",
                } or fold["inner_fold"] != inner:
                    raise ValueError("inner selection fold fields mismatch")
                curve = curves[(seed, outer, inner, arm, grid_index)]
                audit = curve["audit"]
                if fold["resumed_from_rung_last_state"] is not candidate["rung_selected"] or audit["promoted"] is not candidate["rung_selected"]:
                    raise ValueError("curve, fold and candidate disagree on promoted status")
                for field in (
                    "rung_last_validation_tb_mse", "best_epoch", "best_validation_tb_mse",
                    "stop_reason", "validation_plateau_converged",
                ):
                    expected = audit[field] if field in audit else curve["raw"][field]
                    if value_mismatches(fold[field], expected, field):
                        raise ValueError(f"selection and curve disagree on {field}")
                split = splits[outer]["inner"][inner]
                cost = fold["cost"]
                cost_fields = {
                    "wall_clock_seconds", "epochs_ran", "train_transcripts",
                    "validation_transcripts", "cuda_peak_memory_bytes",
                }
                split_cost_fields = {"rung_wall_clock_seconds", "continuation_wall_clock_seconds"}
                if set(cost) not in (cost_fields, cost_fields | split_cost_fields):
                    raise ValueError("fit cost fields mismatch")
                if any((
                    cost["epochs_ran"] != audit["epochs_ran"],
                    cost["train_transcripts"] != len(split["train"]),
                    cost["validation_transcripts"] != len(split["validation"]),
                    not is_number(cost["wall_clock_seconds"], nonnegative=True),
                    cost["wall_clock_seconds"] + 1e-12 < audit["last_elapsed_seconds"],
                    not is_integer(cost["cuda_peak_memory_bytes"], 0),
                )):
                    raise ValueError("fit cost differs from curve, split or CUDA ledger")
                if set(cost) == cost_fields:
                    legacy_cumulative_cost_fits += 1
                    if candidate["rung_selected"]:
                        fit_rung_wall = audit["rung_last_elapsed_seconds"]
                        fit_continuation_wall = cost["wall_clock_seconds"] - fit_rung_wall
                    else:
                        fit_rung_wall = cost["wall_clock_seconds"]
                        fit_continuation_wall = 0.0
                else:
                    fit_rung_wall = cost["rung_wall_clock_seconds"]
                    fit_continuation_wall = cost["continuation_wall_clock_seconds"]
                    continuation_elapsed = audit["last_elapsed_seconds"] - audit["rung_last_elapsed_seconds"]
                    if any((
                        not is_number(fit_rung_wall, nonnegative=True),
                        not is_number(fit_continuation_wall, nonnegative=True),
                        fit_rung_wall + 1e-12 < audit["rung_last_elapsed_seconds"],
                        fit_continuation_wall + 1e-12 < continuation_elapsed,
                        not math.isclose(
                            cost["wall_clock_seconds"], fit_rung_wall + fit_continuation_wall,
                            rel_tol=1e-9, abs_tol=1e-11,
                        ),
                    )):
                        raise ValueError("split rung/continuation cost is inconsistent with curves or total wall")
                weighted_rung_loss += fold["rung_last_validation_tb_mse"] * len(split["validation"])
                if candidate["rung_selected"]:
                    weighted_final_loss += fold["best_validation_tb_mse"] * len(split["validation"])
                validation_count += len(split["validation"])
                fit_wall += cost["wall_clock_seconds"]
                rung_wall += fit_rung_wall
                continuation_wall += fit_continuation_wall
                epochs_ran += cost["epochs_ran"]
                peak_memory = max(peak_memory, cost["cuda_peak_memory_bytes"])
                all_fits.append(fold)
            expected_rung_score = weighted_rung_loss / validation_count
            if not is_number(candidate["rung_inner_oof_tb_mse"], nonnegative=True) or not math.isclose(
                candidate["rung_inner_oof_tb_mse"], expected_rung_score, rel_tol=1e-9, abs_tol=1e-11,
            ) or candidate["rung_inner_oof_transcripts"] != validation_count:
                raise ValueError("rung OOF score differs from rung-last validation curves")
            rung_scores.append(expected_rung_score)
            if candidate["rung_selected"]:
                expected_final_score = weighted_final_loss / validation_count
                if not is_number(candidate["inner_oof_tb_mse"], nonnegative=True) or not math.isclose(
                    candidate["inner_oof_tb_mse"], expected_final_score, rel_tol=1e-9, abs_tol=1e-11,
                ):
                    raise ValueError("final OOF score differs from promoted plateau curves")
                if candidate["inner_oof_transcripts"] != validation_count:
                    raise ValueError("promoted candidate OOF transcript count mismatch")
                final_scores[grid_index] = expected_final_score
            elif candidate["inner_oof_tb_mse"] is not None:
                raise ValueError("eliminated candidate must not have a final converged OOF score")
            elif candidate["inner_oof_transcripts"] != 0:
                raise ValueError("eliminated candidate must have zero final OOF transcripts")
        expected_promoted = np.argsort(np.asarray(rung_scores), kind="mergesort")[:2].tolist()
        if record["rung_selected_grid_indices"] != expected_promoted or set(final_scores) != set(expected_promoted):
            raise ValueError("top2 promotion is not the rung-OOF minimum with grid-order ties")
        if record["selected_grid_index"] not in expected_promoted or record["selected_grid_index"] != grid_order_minimum(
            final_scores,
        ):
            raise ValueError("selected LR/wd are not the promoted post-continuation inner-OOF minimum")
    if seen != expected_selection_keys:
        raise ValueError("missing selection records")
    return {
        "fit_count": len(all_fits),
        "fit_wall_clock_seconds": fit_wall,
        "rung_wall_clock_seconds": rung_wall,
        "continuation_wall_clock_seconds": continuation_wall,
        "legacy_cumulative_cost_fits": legacy_cumulative_cost_fits,
        "epochs_ran": epochs_ran,
        "cuda_peak_memory_bytes": peak_memory,
        "convergence": {
            "fits": len(all_fits),
            "rung_fits": len(all_fits),
            "resumed_fits": sum(fold["resumed_from_rung_last_state"] for fold in all_fits),
            "validation_plateau": sum(fold["stop_reason"] == "validation_plateau" for fold in all_fits),
            "rejected_at_rung_not_converged": sum(
                fold["stop_reason"] == "rejected_at_rung_not_converged" for fold in all_fits
            ),
            "rung_rejection_is_not_convergence": True,
            "selected_candidates_have_no_final_epoch_cap": True,
            "complete_curves_file": "curves.jsonl",
        },
    }


def load_selected_states(path, protocol, startup_sha256):
    selection = load_json(path.parent / "selection.json")
    selections = {
        (record["seed"], record["outer_fold"], record["arm"]): record
        for record in selection["records"]
    }
    seeds = protocol["training"]["model_seeds"]
    with np.load(path, allow_pickle=False) as archive:
        archive_keys = set(archive.files)
        if "metadata" not in archive_keys:
            raise ValueError("selected inner state archive has no metadata")
        metadata = json.loads(archive["metadata"].item(), parse_constant=reject_nonfinite_json)
        if not isinstance(metadata, dict) or set(metadata) != {
            "schema", "protocol", "dtype", "model_config", "startup_sha256", "records",
        }:
            raise ValueError("selected inner state metadata fields mismatch")
        if metadata["schema"] != STATE_SCHEMA or metadata["protocol"] != PROTOCOL or metadata["dtype"] != "float64":
            raise ValueError("selected inner state archive identity mismatch")
        if value_mismatches(metadata["model_config"], protocol["model"], "state.model_config"):
            raise ValueError("selected inner state model configuration mismatch")
        if value_mismatches(metadata["startup_sha256"], startup_sha256, "state.startup_sha256"):
            raise ValueError("selected states do not match startup source hashes")
        records = metadata["records"]
        if not isinstance(records, list):
            raise ValueError("selected inner state records must be a list")
        expected_keys = {(seed, outer, arm) for seed in seeds for outer in range(3) for arm in ARMS}
        seen = set()
        selected_states = {}
        referenced_arrays = {"metadata"}
        for record in records:
            required = {
                "seed", "seed_index", "outer_fold", "arm", "arm_index", "selected_grid_index",
                "learning_rate", "weight_decay", "members",
            }
            if not isinstance(record, dict) or set(record) != required:
                raise ValueError("selected inner state record fields mismatch")
            key = (record["seed"], record["outer_fold"], record["arm"])
            if key not in expected_keys or key in seen:
                raise ValueError("duplicate or unexpected selected inner state record")
            seen.add(key)
            seed, outer, arm = key
            selection_record = selections[key]
            selected_index = selection_record["selected_grid_index"]
            lr, wd = curve_grid(protocol)[selected_index]
            expected_record = {
                "seed_index": seeds.index(seed), "arm_index": ARMS.index(arm),
                "selected_grid_index": selected_index, "learning_rate": lr, "weight_decay": wd,
            }
            for field, expected in expected_record.items():
                if value_mismatches(record[field], expected, field):
                    raise ValueError(f"selected state and selection disagree on {field}")
            members = record["members"]
            if not isinstance(members, list) or len(members) != 3:
                raise ValueError("each selection must save three inner members")
            selected_states[key] = []
            for inner, member in enumerate(members):
                if not isinstance(member, dict) or set(member) != {
                    "inner_fold", "fit_seed", "best_epoch", "best_validation_tb_mse", "state_keys",
                } or member["inner_fold"] != inner:
                    raise ValueError("selected inner member fields or order mismatch")
                expected_fit_seed = int(np.random.SeedSequence([seed, outer, inner]).generate_state(1)[0])
                fold = selection_record["candidates"][selected_index]["folds"][inner]
                if member["fit_seed"] != expected_fit_seed:
                    raise ValueError("selected member fit seed differs from frozen seed derivation")
                for field in ("best_epoch", "best_validation_tb_mse"):
                    if value_mismatches(member[field], fold[field], field):
                        raise ValueError(f"selected member and curve selection disagree on {field}")
                expected_names = {"relative_position.weight"}
                if arm != "position":
                    expected_names.add("codon.weight")
                state_keys = member["state_keys"]
                if not isinstance(state_keys, dict) or set(state_keys) != expected_names:
                    raise ValueError("selected member state keys mismatch")
                state = {}
                for name in sorted(expected_names):
                    expected_key = f"state/{seeds.index(seed)}/{outer}/{ARMS.index(arm)}/{inner}/{name}"
                    if state_keys[name] != expected_key or expected_key not in archive_keys:
                        raise ValueError("selected member state array path mismatch")
                    value = np.asarray(archive[expected_key])
                    expected_shape = (64, 1) if name == "codon.weight" else (1, 1)
                    if value.shape != expected_shape or value.dtype != np.float64 or not np.all(np.isfinite(value)):
                        raise ValueError("selected member state array is invalid")
                    state[name] = value.copy()
                    referenced_arrays.add(expected_key)
                selected_states[key].append(state)
        if seen != expected_keys or archive_keys != referenced_arrays:
            raise ValueError("selected state archive is incomplete or contains unreferenced arrays")
        return selected_states


def steady_state_residual(state, alpha, internal_rates, beta):
    rho = state[:-1]
    flux = state[-1]
    return np.concatenate((
        [alpha * (1.0 - rho[0]) - flux],
        internal_rates * rho[:-1] * (1.0 - rho[1:]) - flux,
        [beta * rho[-1] - flux],
    ))


def steady_state_jacobian(state, alpha, internal_rates, beta):
    rho = state[:-1]
    length = len(rho)
    jacobian = np.zeros((length + 1, length + 1), dtype=np.float64)
    jacobian[0, 0] = -alpha
    if length > 1:
        rows = np.arange(1, length)
        jacobian[rows, rows - 1] = internal_rates * (1.0 - rho[1:])
        jacobian[rows, rows] = -internal_rates * rho[:-1]
    jacobian[-1, -2] = beta
    jacobian[:, -1] = -1.0
    return jacobian


def scaled_steady_state_residual(state, alpha, internal_rates, beta, flux_scale):
    rho = state[:-1]
    scaled_flux = state[-1]
    return np.concatenate((
        [1.0 - rho[0] - scaled_flux * flux_scale / alpha],
        rho[:-1] * (1.0 - rho[1:]) - scaled_flux * flux_scale / internal_rates,
        [rho[-1] - scaled_flux * flux_scale / beta],
    ))


def scaled_steady_state_jacobian(state, alpha, internal_rates, beta, flux_scale):
    rho = state[:-1]
    length = len(rho)
    jacobian = np.zeros((length + 1, length + 1), dtype=np.float64)
    jacobian[0, 0] = -1.0
    if length > 1:
        rows = np.arange(1, length)
        jacobian[rows, rows - 1] = 1.0 - rho[1:]
        jacobian[rows, rows] = -rho[:-1]
    jacobian[-1, -2] = 1.0
    rates = np.concatenate(([alpha], internal_rates, [beta]))
    jacobian[:, -1] = -flux_scale / rates
    return jacobian


def checked_physical_state(solved, state, alpha, internal_rates, beta):
    if not solved.success or state.shape != (len(internal_rates) + 2,) or not np.all(np.isfinite(state)):
        raise RuntimeError(f"independent SciPy steady-state solve failed: {solved.message}")
    rho = np.asarray(state[:-1], dtype=np.float64)
    flux = float(state[-1])
    if np.any(rho < -1e-10) or np.any(rho > 1.0 + 1e-10) or not math.isfinite(flux) or flux <= 0:
        raise RuntimeError("independent SciPy steady state is outside the physical domain")
    rho = np.clip(rho, 0.0, 1.0)
    state = np.concatenate((rho, [flux]))
    residual = steady_state_residual(state, alpha, internal_rates, beta) / flux
    if not np.all(np.isfinite(residual)) or np.max(np.abs(residual)) > MEMBER_RESIDUAL_TOLERANCE:
        raise RuntimeError("independent SciPy member violates flux conservation tolerance")
    return {"rho": rho, "flux": flux, "residual": residual}


def independent_steady_state(alpha, internal_rates, beta):
    internal_rates = np.asarray(internal_rates, dtype=np.float64)
    length = len(internal_rates) + 1
    rates = np.concatenate(([alpha], internal_rates, [beta]))
    if internal_rates.ndim != 1 or not np.all(np.isfinite(rates)) or np.any(rates <= 0):
        raise ValueError("steady-state rates must be finite, positive and correctly shaped")
    initial_flux = alpha * beta / (alpha + beta) if length == 1 else float(np.min(rates)) / 4.0
    initial_rho = np.asarray([alpha / (alpha + beta)]) if length == 1 else np.linspace(
        1.0 - initial_flux / alpha, initial_flux / beta, length,
    )
    initial = np.concatenate((initial_rho, [initial_flux]))
    solved = root(
        steady_state_residual, initial, args=(alpha, internal_rates, beta),
        jac=steady_state_jacobian, method="hybr",
        options={"xtol": ROOT_TOLERANCE, "maxfev": ROOT_MAXFEV},
    )
    try:
        return checked_physical_state(solved, np.asarray(solved.x, dtype=np.float64), alpha, internal_rates, beta)
    except RuntimeError as original_error:
        flux_scale = float(np.min(rates))
        scaled_initial = initial.copy()
        scaled_initial[-1] /= flux_scale
        scaled = root(
            scaled_steady_state_residual, scaled_initial, args=(alpha, internal_rates, beta, flux_scale),
            jac=scaled_steady_state_jacobian, method="hybr",
            options={"xtol": ROOT_TOLERANCE, "maxfev": ROOT_MAXFEV},
        )
        scaled_state = np.asarray(scaled.x, dtype=np.float64)
        if scaled_state.shape == initial.shape:
            scaled_state[-1] *= flux_scale
        try:
            return checked_physical_state(scaled, scaled_state, alpha, internal_rates, beta)
        except RuntimeError as scaled_error:
            bounded = least_squares(
                steady_state_residual, np.maximum(initial, 0.0), args=(alpha, internal_rates, beta),
                jac=steady_state_jacobian, bounds=(0.0, np.inf),
                xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=ROOT_MAXFEV,
            )
            try:
                return checked_physical_state(
                    bounded, np.asarray(bounded.x, dtype=np.float64), alpha, internal_rates, beta,
                )
            except RuntimeError:
                bounded_initial = np.maximum(scaled_initial, 0.0)
                bounded = least_squares(
                    scaled_steady_state_residual, bounded_initial,
                    args=(alpha, internal_rates, beta, flux_scale),
                    jac=scaled_steady_state_jacobian, bounds=(0.0, np.inf),
                    xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=ROOT_MAXFEV,
                )
                bounded_state = np.asarray(bounded.x, dtype=np.float64)
                if bounded_state.shape == initial.shape:
                    bounded_state[-1] *= flux_scale
                try:
                    return checked_physical_state(bounded, bounded_state, alpha, internal_rates, beta)
                except RuntimeError as bounded_error:
                    raise bounded_error from scaled_error


def rebuild_selected_member(record, state, arm, model_config):
    length = record["length"]
    relative_position = np.arange(length, dtype=np.float64) / max(length - 1, 1)
    weight = float(np.asarray(state["relative_position.weight"]).reshape(()))
    if arm == "position":
        score = weight * relative_position
    else:
        embedding = np.asarray(state["codon.weight"], dtype=np.float64).reshape(64)
        score = embedding[record["codons"]] + weight * relative_position
    if not np.all(np.isfinite(score)):
        raise ValueError("selected state produced a nonfinite score")
    if arm in ("independent", "position"):
        return {"rho": expit(score), "flux": None, "residual": None}
    rates = float(model_config["rate_floor"]) + np.logaddexp(0.0, score)
    rates = np.minimum(rates, float(model_config["rate_ceiling"]))
    if not np.all(np.isfinite(rates)) or np.any(rates <= 0):
        raise ValueError("selected state produced invalid kinetic rates")
    return independent_steady_state(rates[0], rates[:-1], rates[-1])


def load_predictions(path):
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != set(PREDICTION_ARRAYS):
            raise ValueError("prediction array keys mismatch")
        return {name: np.asarray(archive[name]).copy() for name in PREDICTION_ARRAYS}


def average_ranks(values):
    values = np.asarray(values, dtype=np.float64)
    order = np.argsort(values, kind="mergesort")
    ordered = values[order]
    ranks = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        stop = start + 1
        while stop < len(values) and ordered[stop] == ordered[start]:
            stop += 1
        ranks[order[start:stop]] = (start + stop - 1) / 2.0 + 1.0
        start = stop
    return ranks


def correlation(x, y):
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if len(x) < 2 or np.ptp(x) == 0.0 or np.ptp(y) == 0.0:
        return None
    x = x - np.mean(x)
    y = y - np.mean(y)
    denominator = math.sqrt(float(np.sum(x ** 2) * np.sum(y ** 2)))
    if denominator == 0.0:
        return None
    value = float(np.sum(x * y) / denominator)
    return value if math.isfinite(value) else None


def evaluate_predictions(arrays, records, protocol, splits, selected_states):
    seeds = protocol["training"]["model_seeds"]
    n_seeds, n_arms, n_records = len(seeds), len(ARMS), len(records)
    max_length = max(record["length"] for record in records)
    shapes = {
        "seeds": (n_seeds,), "arms": (n_arms,), "transcript_indices": (n_records,),
        "transcript_ids": (n_records,), "lengths": (n_records,), "codons": (n_records, max_length),
        "target": (n_records, max_length), "mask": (n_records, max_length),
        "outer_fold": (n_records,), "prediction": (n_seeds, n_arms, n_records, max_length),
        "flux": (n_seeds, n_arms, n_records),
        "ensemble_mean_residual_diagnostic": (n_seeds, n_arms, n_records, max_length + 1),
        "solver_max_abs_normalized_residual": (n_seeds, n_arms, n_records),
    }
    for name, shape in shapes.items():
        if arrays[name].shape != shape:
            raise ValueError(f"prediction array {name} shape {arrays[name].shape} != {shape}")
    if not np.array_equal(arrays["seeds"], np.asarray(seeds)) or not np.array_equal(arrays["arms"], np.asarray(ARMS)):
        raise ValueError("prediction seed/arm order mismatch")
    if not np.array_equal(arrays["transcript_indices"], np.arange(n_records)):
        raise ValueError("prediction transcript indices mismatch")
    if not np.array_equal(arrays["transcript_ids"], np.asarray([record["transcript_id"] for record in records])):
        raise ValueError("prediction transcript IDs differ from raw")
    if not np.array_equal(arrays["lengths"], np.asarray([record["length"] for record in records])):
        raise ValueError("prediction lengths differ from raw")
    outer_assignment = np.empty(n_records, dtype=np.int64)
    for outer in splits:
        outer_assignment[outer["test"]] = outer["outer_fold"]
    if not np.array_equal(arrays["outer_fold"], outer_assignment):
        raise ValueError("prediction outer folds differ from raw-derived split")
    if arrays["ensemble_mean_is_common_steady_state"].shape != () or arrays["ensemble_mean_is_common_steady_state"].item() is not False:
        raise ValueError("ensemble mean must not be labeled a common steady state")
    if arrays["kinetic_conservation_level"].shape != () or arrays["kinetic_conservation_level"].item() != "selected_inner_member_separately":
        raise ValueError("kinetic conservation must be evaluated per selected inner member")
    rows = []
    member_residual_maxima = []
    member_fluxes = []
    for record in records:
        index, length = record["index"], record["length"]
        if not np.array_equal(arrays["codons"][index, :length], record["codons"]):
            raise ValueError("prediction codons differ from raw")
        if np.any(arrays["codons"][index, length:] != -1):
            raise ValueError("padded codons must be -1")
        if not np.allclose(arrays["target"][index, :length], record["density"], rtol=0, atol=0):
            raise ValueError("prediction target differs from independently normalized raw density")
        if not np.all(np.isnan(arrays["target"][index, length:])):
            raise ValueError("padded target must be NaN")
        if not np.array_equal(arrays["mask"][index], np.pad(record["mask"], (0, max_length - length))):
            raise ValueError("prediction mask differs from raw QC mask")
        for seed_index, seed in enumerate(seeds):
            for arm_index, arm in enumerate(ARMS):
                prediction = arrays["prediction"][seed_index, arm_index, index]
                if not np.all(np.isfinite(prediction[:length])) or np.any(prediction[:length] < 0) or np.any(prediction[:length] > 1):
                    raise ValueError("outer-test density must be finite and in [0,1]")
                if not np.all(np.isnan(prediction[length:])):
                    raise ValueError("padded density must be NaN")
                states = selected_states.get((seed, int(outer_assignment[index]), arm))
                if states is None:
                    raise ValueError("selected inner states missing for outer prediction")
                members = [rebuild_selected_member(record, state, arm, protocol["model"]) for state in states]
                expected_prediction = np.mean([member["rho"] for member in members], axis=0)
                if not np.allclose(prediction[:length], expected_prediction, rtol=REBUILD_ATOL, atol=REBUILD_ATOL):
                    raise ValueError("outer ensemble density differs from selected inner states")
                flux = arrays["flux"][seed_index, arm_index, index]
                residual = arrays["ensemble_mean_residual_diagnostic"][seed_index, arm_index, index]
                solver_residual = arrays["solver_max_abs_normalized_residual"][seed_index, arm_index, index]
                if arm != "kinetic":
                    if not np.isnan(flux) or not np.all(np.isnan(residual)) or not np.isnan(solver_residual):
                        raise ValueError("non-kinetic arm must not invent kinetic diagnostics")
                    residual_value = None
                else:
                    expected_flux = float(np.mean([member["flux"] for member in members]))
                    expected_residual = np.mean([member["residual"] for member in members], axis=0)
                    expected_solver_max = float(max(np.max(np.abs(member["residual"])) for member in members))
                    if not np.isfinite(flux) or flux <= 0 or not np.isfinite(solver_residual) or solver_residual < 0:
                        raise ValueError("kinetic flux/residual scalar must be finite and physical")
                    if not np.all(np.isfinite(residual[:length + 1])) or not np.all(np.isnan(residual[length + 1:])):
                        raise ValueError("kinetic normalized residual real/padded values invalid")
                    if not math.isclose(float(flux), expected_flux, rel_tol=REBUILD_ATOL, abs_tol=REBUILD_ATOL):
                        raise ValueError("outer ensemble flux differs from selected members")
                    if not np.allclose(residual[:length + 1], expected_residual, rtol=REBUILD_ATOL, atol=REBUILD_ATOL):
                        raise ValueError("mean residual diagnostic differs from selected members")
                    if not math.isclose(float(solver_residual), expected_solver_max, rel_tol=REBUILD_ATOL, abs_tol=REBUILD_ATOL):
                        raise ValueError("solver maximum differs from per-member conservation")
                    residual_value = float(solver_residual)
                    for member in members:
                        member_residual_maxima.append(float(np.max(np.abs(member["residual"]))))
                        member_fluxes.append(float(member["flux"]))
                mask = record["mask"]
                target = record["density"][mask]
                predicted = prediction[:length][mask]
                rows.append({
                    "seed": seed, "arm": arm, "outer_fold": int(outer_assignment[index]),
                    "transcript_index": index, "transcript_id": record["transcript_id"],
                    "length": length, "n_positions": int(mask.sum()),
                    "mse": float(np.mean((target - predicted) ** 2)),
                    "pearson": correlation(target, predicted),
                    "spearman": correlation(average_ranks(target), average_ranks(predicted)),
                    "solver_max_abs_normalized_residual": residual_value,
                })
    seed_order = {seed: index for index, seed in enumerate(seeds)}
    arm_order = {arm: index for index, arm in enumerate(ARMS)}
    rows.sort(key=lambda row: (seed_order[row["seed"]], arm_order[row["arm"]], row["transcript_index"]))
    return {
        "rows": rows,
        "member_conservation": {
            "maximum_member_abs_normalized_residual": float(max(member_residual_maxima)),
            "minimum_member_flux": float(min(member_fluxes)),
            "maximum_member_flux": float(max(member_fluxes)),
            "kinetic_members_checked": len(member_fluxes),
            "ensemble_mean_is_common_steady_state": False,
            "ensemble_interpretation": "equal-weight density/flux predictions; conservation is certified per member",
        },
    }


def mean_or_none(values):
    defined = [value for value in values if value is not None]
    return float(np.mean(defined)) if defined else None


def summarize_metric_rows(rows, seeds):
    summary = {}
    for seed in seeds:
        summary[str(seed)] = {}
        for arm in ARMS:
            selected = [row for row in rows if row["seed"] == seed and row["arm"] == arm]
            residuals = [row["solver_max_abs_normalized_residual"] for row in selected]
            summary[str(seed)][arm] = {
                "n_transcripts": len(selected),
                "n_positions": sum(row["n_positions"] for row in selected),
                "tb_mse": float(np.mean([row["mse"] for row in selected])),
                "mean_per_transcript_pearson": mean_or_none([row["pearson"] for row in selected]),
                "mean_per_transcript_spearman": mean_or_none([row["spearman"] for row in selected]),
                "defined_pearson": sum(row["pearson"] is not None for row in selected),
                "defined_spearman": sum(row["spearman"] is not None for row in selected),
                "maximum_solver_abs_normalized_residual": max(residuals) if residuals[0] is not None else None,
            }
        for comparator in COMPARATORS:
            summary[str(seed)][f"{comparator}_minus_kinetic_tb_mse"] = (
                summary[str(seed)][comparator]["tb_mse"] - summary[str(seed)]["kinetic"]["tb_mse"]
            )
    return summary


def paired_inference(effects, n_bootstrap=REAL_RESAMPLES, n_signflip=REAL_RESAMPLES, seed=INFERENCE_SEED, batch_size=512):
    effects = np.asarray(effects, dtype=np.float64)
    if effects.ndim != 1 or not len(effects) or not np.all(np.isfinite(effects)):
        raise ValueError("paired effects must be finite and nonempty")
    if not is_integer(n_bootstrap, 1) or not is_integer(n_signflip, 1) or not is_integer(batch_size, 1):
        raise ValueError("inference resampling counts must be positive")
    rng = np.random.default_rng(seed)
    bootstrap = np.empty(n_bootstrap, dtype=np.float64)
    for start in range(0, n_bootstrap, batch_size):
        stop = min(start + batch_size, n_bootstrap)
        indices = rng.integers(0, len(effects), size=(stop - start, len(effects)))
        bootstrap[start:stop] = np.mean(effects[indices], axis=1)
    observed = float(np.mean(effects))
    exceedances = 0
    for start in range(0, n_signflip, batch_size):
        stop = min(start + batch_size, n_signflip)
        signs = rng.integers(0, 2, size=(stop - start, len(effects)), dtype=np.int8) * 2 - 1
        null = np.mean(signs * effects, axis=1)
        exceedances += int(np.count_nonzero(np.abs(null) >= abs(observed)))
    return {
        "effect": observed,
        "bootstrap_95ci": [float(np.quantile(bootstrap, 0.025)), float(np.quantile(bootstrap, 0.975))],
        "signflip_p_two_sided": float((exceedances + 1) / (n_signflip + 1)),
        "n_bootstrap": n_bootstrap, "n_signflip": n_signflip, "n_transcripts": len(effects),
    }


def holm_adjust(p_values):
    p_values = np.asarray(p_values, dtype=np.float64)
    order = np.argsort(p_values, kind="mergesort")
    adjusted = np.empty(len(p_values), dtype=np.float64)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p_values) - rank) * p_values[index])
        adjusted[index] = min(1.0, running)
    return adjusted


def recompute_inference(rows, seeds, n_resamples=20000, batch_size=512, seed=INFERENCE_SEED):
    transcripts = sorted({row["transcript_index"] for row in rows})
    lookup = {}
    for row in rows:
        key = (row["seed"], row["transcript_index"], row["arm"])
        if key in lookup or row["seed"] not in seeds or row["arm"] not in ARMS:
            raise ValueError("duplicate or unexpected transcript metric row")
        lookup[key] = row["mse"]
    expected_keys = {
        (model_seed, transcript, arm)
        for model_seed in seeds for transcript in transcripts for arm in ARMS
    }
    if set(lookup) != expected_keys:
        raise ValueError("all three arms must be paired for every seed and transcript")

    def effects_for(model_seed, comparator):
        return [
            lookup[(model_seed, transcript, comparator)] - lookup[(model_seed, transcript, "kinetic")]
            for transcript in transcripts
        ]

    per_seed = {}
    for model_seed in seeds:
        comparisons = {}
        for comparator in COMPARATORS:
            comparisons[comparator] = paired_inference(
                effects_for(model_seed, comparator), n_resamples, n_resamples,
                [seed, model_seed], batch_size,
            )
        adjusted = holm_adjust([comparisons[name]["signflip_p_two_sided"] for name in COMPARATORS])
        for comparator, value in zip(COMPARATORS, adjusted):
            comparisons[comparator]["holm_p"] = float(value)
        per_seed[str(model_seed)] = {"comparisons": comparisons}

    pooled_comparisons = {}
    for comparator in COMPARATORS:
        pooled_effects = [
            float(np.mean([lookup[(model_seed, transcript, comparator)] - lookup[(model_seed, transcript, "kinetic")] for model_seed in seeds]))
            for transcript in transcripts
        ]
        pooled_comparisons[comparator] = paired_inference(
            pooled_effects, n_resamples, n_resamples, [seed, 0x7FFFFFFF], batch_size,
        )
    adjusted = holm_adjust([pooled_comparisons[name]["signflip_p_two_sided"] for name in COMPARATORS])
    for comparator, value in zip(COMPARATORS, adjusted):
        pooled_comparisons[comparator]["holm_p"] = float(value)

    across_seeds = {}
    h2_by_comparator = {}
    for comparator in COMPARATORS:
        effects = [float(np.mean(effects_for(model_seed, comparator))) for model_seed in seeds]
        all_positive = all(value > 0 for value in effects)
        across_seeds[comparator] = {
            "effects": effects,
            "all_seed_effects_positive": all_positive,
            "same_nonzero_sign": all_positive or all(value < 0 for value in effects),
        }
        h2_by_comparator[comparator] = bool(
            all_positive
            and pooled_comparisons[comparator]["bootstrap_95ci"][0] > 0
            and pooled_comparisons[comparator]["holm_p"] < 0.05
            and all(
                per_seed[str(model_seed)]["comparisons"][comparator]["bootstrap_95ci"][0] > 0
                and per_seed[str(model_seed)]["comparisons"][comparator]["holm_p"] < 0.05
                for model_seed in seeds
            )
        )
    return {
        "effect_definition": "comparator TB-MSE minus kinetic TB-MSE; positive favors kinetic",
        "comparators": list(COMPARATORS),
        "cluster": "transcript",
        "n_model_seeds": len(seeds),
        "seed_aggregation": "mean within transcript before pooled cluster bootstrap and sign-flip",
        "holm_family": "two comparators within each seed and separately for seed-first pooled inference",
        "per_seed": per_seed,
        "pooled_seed_first": {"comparisons": pooled_comparisons},
        "across_seeds": across_seeds,
        "h2_by_comparator": h2_by_comparator,
        "h2_development_positive": all(h2_by_comparator.values()),
        "scope": "development_only_not_final_research_ood_or_sota",
    }


def compare_csv(path, expected_rows):
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != CSV_FIELDS:
            return ["CSV header"]
        rows = list(reader)
    if len(rows) != len(expected_rows):
        return ["CSV row count"]
    mismatches = []
    for index, (observed, expected) in enumerate(zip(rows, expected_rows)):
        for field in CSV_FIELDS:
            if field in ("arm", "transcript_id"):
                valid = observed[field] == expected[field]
            elif field in ("seed", "outer_fold", "transcript_index", "length", "n_positions"):
                try:
                    valid = int(observed[field]) == expected[field]
                except ValueError:
                    valid = False
            elif expected[field] is None:
                valid = observed[field] == ""
            else:
                try:
                    value = float(observed[field])
                    valid = math.isfinite(value) and math.isclose(value, expected[field], rel_tol=1e-9, abs_tol=1e-11)
                except ValueError:
                    valid = False
            if not valid:
                mismatches.append(f"row[{index}].{field}")
    return mismatches


def valid_environment(environment):
    cuda = environment.get("cuda") if isinstance(environment, dict) else None
    return (
        isinstance(cuda, dict)
        and isinstance(cuda.get("requested_device"), str) and cuda["requested_device"].startswith("cuda")
        and cuda.get("available") is True
        and isinstance(cuda.get("torch_cuda_version"), str) and bool(cuda["torch_cuda_version"])
        and isinstance(cuda.get("name"), str) and bool(cuda["name"])
        and isinstance(cuda.get("capability"), list) and len(cuda["capability"]) == 2
        and all(is_integer(value, 0) for value in cuda["capability"])
    )


def valid_cost(cost, training):
    required = {
        "started_utc", "finished_utc", "wall_clock_seconds", "candidate_fits",
        "epochs_ran", "candidate_fit_wall_clock_seconds", "cuda_peak_memory_bytes",
    }
    split_fields = {"rung_wall_clock_seconds", "continuation_wall_clock_seconds"}
    allowed = required | split_fields | {"parallel"}
    if not isinstance(cost, dict) or not required <= set(cost) or not set(cost) <= allowed:
        return False, ["cost.keys"]
    if set(cost) & split_fields and not split_fields <= set(cost):
        return False, ["cost.keys"]
    mismatches = []
    try:
        started = datetime.fromisoformat(cost["started_utc"])
        finished = datetime.fromisoformat(cost["finished_utc"])
        if finished < started:
            mismatches.append("cost.finished_utc")
    except (TypeError, ValueError):
        mismatches.append("cost.timestamps")
    expected = {
        "candidate_fits": training["fit_count"], "epochs_ran": training["epochs_ran"],
        "candidate_fit_wall_clock_seconds": training["fit_wall_clock_seconds"],
        "cuda_peak_memory_bytes": training["cuda_peak_memory_bytes"],
    }
    if set(cost) & split_fields:
        expected.update({
            "rung_wall_clock_seconds": training["rung_wall_clock_seconds"],
            "continuation_wall_clock_seconds": training["continuation_wall_clock_seconds"],
        })
    for key, value in expected.items():
        mismatches.extend(value_mismatches(cost.get(key), value, f"cost.{key}"))
    if not is_number(cost.get("wall_clock_seconds"), nonnegative=True):
        mismatches.append("cost.wall_clock_seconds")
    parallel = cost.get("parallel")
    if parallel is None:
        if is_number(cost.get("wall_clock_seconds"), nonnegative=True) and cost["wall_clock_seconds"] + 1e-9 < training["fit_wall_clock_seconds"]:
            mismatches.append("cost.wall_clock_seconds")
    else:
        parallel_fields = {
            "max_workers", "start_method", "shard_execution_wall_clock_seconds",
            "shard_wall_clock_seconds_sum", "cache_hits", "cache_misses",
        }
        if not isinstance(parallel, dict) or set(parallel) != parallel_fields:
            mismatches.append("cost.parallel.keys")
        else:
            if not is_integer(parallel["max_workers"], 1) or parallel["start_method"] != "spawn":
                mismatches.append("cost.parallel.execution")
            for key in ("shard_execution_wall_clock_seconds", "shard_wall_clock_seconds_sum"):
                if not is_number(parallel[key], nonnegative=True):
                    mismatches.append(f"cost.parallel.{key}")
            for key in ("cache_hits", "cache_misses"):
                if not is_integer(parallel[key], 0):
                    mismatches.append(f"cost.parallel.{key}")
            if is_integer(parallel["cache_hits"], 0) and is_integer(parallel["cache_misses"], 0) and parallel["cache_hits"] + parallel["cache_misses"] != 27:
                mismatches.append("cost.parallel.shard_count")
            if is_number(parallel["shard_execution_wall_clock_seconds"], nonnegative=True) and parallel["shard_execution_wall_clock_seconds"] > cost["wall_clock_seconds"] + 1e-9:
                mismatches.append("cost.parallel.wall_clock_seconds")
    return not mismatches, mismatches


def audit_parallel(path, protocol, training, summary):
    payload = load_json(path)
    mismatches = []
    required = {
        "schema", "protocol", "max_workers", "start_method", "schedule", "scheduled_specs",
        "canonical_merge", "parallel_implementation_sha256", "shards", "cache_hits", "cache_misses",
        "shard_execution_wall_clock_seconds", "shard_wall_clock_seconds_sum",
        "candidate_fit_wall_clock_seconds_serial_sum", "wall_is_not_serial_sum", "scientific_gate_claimed",
    }
    if set(payload) != required or payload["schema"] != PARALLEL_SCHEMA or payload["protocol"] != PROTOCOL:
        return ["parallel.identity_or_keys"]
    expected_specs = [
        {"seed": seed, "seed_index": seed_index, "outer_fold": outer, "arm": arm}
        for seed_index, seed in enumerate(protocol["training"]["model_seeds"])
        for outer in range(3) for arm in ARMS
    ]
    scheduled = sorted(expected_specs, key=lambda spec: (spec["arm"] != "kinetic", spec["seed_index"], spec["outer_fold"]))
    if payload["scheduled_specs"] != scheduled or payload["schedule"] != "kinetic_first":
        mismatches.append("parallel.schedule")
    if payload["canonical_merge"] != "seed_index,outer_fold,protocol_arm_order":
        mismatches.append("parallel.canonical_merge")
    if payload["parallel_implementation_sha256"] != sha256_file(PARALLEL_IMPLEMENTATION_PATH):
        mismatches.append("parallel.implementation_sha256")
    shards = payload["shards"]
    if not isinstance(shards, list) or len(shards) != 27:
        mismatches.append("parallel.shards.count")
    else:
        if [entry.get("spec") for entry in shards] != expected_specs:
            mismatches.append("parallel.shards.canonical_order")
        for entry in shards:
            if set(entry) != {"spec", "cache_hit", "path", "sha256", "shard_cost"}:
                mismatches.append("parallel.shards.keys")
                break
            if not isinstance(entry["cache_hit"], bool) or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None:
                mismatches.append("parallel.shards.integrity")
                break
            cost = entry["shard_cost"]
            if not isinstance(cost, dict) or set(cost) != {"wall_clock_seconds"} or not is_number(cost["wall_clock_seconds"], nonnegative=True):
                mismatches.append("parallel.shards.cost")
                break
    if payload["cache_hits"] + payload["cache_misses"] != 27:
        mismatches.append("parallel.cache_accounting")
    for key in ("shard_execution_wall_clock_seconds", "shard_wall_clock_seconds_sum", "candidate_fit_wall_clock_seconds_serial_sum"):
        if not is_number(payload[key], nonnegative=True):
            mismatches.append(f"parallel.{key}")
    if not math.isclose(payload["candidate_fit_wall_clock_seconds_serial_sum"], training["fit_wall_clock_seconds"], rel_tol=1e-12, abs_tol=1e-12):
        mismatches.append("parallel.serial_cost_sum")
    shard_sum = sum(entry["shard_cost"]["wall_clock_seconds"] for entry in shards if isinstance(entry.get("shard_cost"), dict))
    if not math.isclose(payload["shard_wall_clock_seconds_sum"], shard_sum, rel_tol=1e-9, abs_tol=1e-9):
        mismatches.append("parallel.shard_cost_sum")
    if payload["wall_is_not_serial_sum"] is not True or payload["scientific_gate_claimed"] is not False:
        mismatches.append("parallel.claim_boundary")
    summary_parallel = summary.get("cost", {}).get("parallel")
    expected_summary = {key: payload[key] for key in (
        "max_workers", "start_method", "shard_execution_wall_clock_seconds",
        "shard_wall_clock_seconds_sum", "cache_hits", "cache_misses",
    )}
    mismatches.extend(value_mismatches(summary_parallel, expected_summary, "summary.cost.parallel"))
    return mismatches


def audit_provenance(path, startup_sha256):
    provenance = load_json(path)
    mismatches = []
    for key, expected in (
        ("schema", PROVENANCE_SCHEMA), ("protocol", PROTOCOL),
        ("stage", "startup_before_device_probe_raw_parse_or_training"), ("sha256", startup_sha256),
    ):
        mismatches.extend(value_mismatches(provenance.get(key), expected, f"provenance.{key}"))
    if set(provenance) != {"schema", "protocol", "recorded_utc", "stage", "sha256"}:
        mismatches.append("provenance.keys")
    try:
        datetime.fromisoformat(provenance["recorded_utc"])
    except (KeyError, TypeError, ValueError):
        mismatches.append("provenance.recorded_utc")
    return mismatches


def verify_e2_kinetic(protocol_path, raw_path, output_dir, allow_synthetic=False, n_resamples=20000):
    protocol_path = Path(protocol_path).expanduser().resolve()
    raw_path = Path(raw_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    protocol = load_protocol(protocol_path, allow_synthetic=allow_synthetic)
    if not allow_synthetic and n_resamples != REAL_RESAMPLES:
        raise ValueError(f"real verification requires exactly {REAL_RESAMPLES} resamples")
    raw_sha = sha256_file(raw_path)
    records, qc = parse_raw(raw_path)
    splits = make_nested_splits(records, protocol["split"]["seed"])
    seeds = protocol["training"]["model_seeds"]
    summary = load_json(output_dir / "summary.json")
    parallel_path = output_dir / "parallel.json"
    has_parallel = parallel_path.exists() or "parallel" in summary.get("cost", {})
    startup_sha256 = {
        "protocol": sha256_file(protocol_path),
        "implementation": sha256_file(IMPLEMENTATION_PATH),
        "mean_field_operator": sha256_file(MEAN_FIELD_OPERATOR_PATH),
    }
    checks = {}
    details = {}
    observed_files = {str(path.relative_to(output_dir)) for path in output_dir.rglob("*") if path.is_file()}
    expected_output_files = set(OUTPUT_FILES) | ({"parallel.json"} if has_parallel else set())
    checks["output_files_exact"] = observed_files == expected_output_files
    provenance_mismatches = audit_provenance(output_dir / "provenance.json", startup_sha256)
    checks["startup_source_provenance_recomputed"] = not provenance_mismatches
    details["provenance"] = provenance_mismatches
    checks["raw_sha256"] = raw_sha == protocol["inputs"]["sha256"] and (allow_synthetic or raw_sha == REAL_RAW_SHA256)
    checks["raw_basename"] = raw_path.name == protocol["inputs"]["expected_basename"]
    checks["exact_cds_id_isolation_and_qc"] = (
        len({record["transcript_id"] for record in records}) == len(records)
        and len({record["codons"].tobytes() for record in records}) == len(records)
        and all(record["codons"][0] == CODON_TO_INDEX["ATG"] for record in records)
        and all(CODONS[record["codons"][-1]] in STOP_CODONS for record in records)
        and all(not any(CODONS[codon] in STOP_CODONS for codon in record["codons"][:-1]) for record in records)
    )
    checks["eligible_transcript_count"] = len(records) == protocol["inputs"]["expected_eligible_transcripts"]
    real_qc_mismatches = [] if allow_synthetic else value_mismatches(qc, REAL_QC, "qc")
    checks["real_strict_qc_recomputed_from_raw"] = not real_qc_mismatches
    details["real_qc"] = real_qc_mismatches
    if not allow_synthetic:
        checks["eligible_transcript_count"] = checks["eligible_transcript_count"] and len(records) == REAL_ELIGIBLE
    mismatches = value_mismatches(load_json(output_dir / "splits.json"), split_payload(splits, records), "splits")
    checks["raw_rebuilt_transcript_nested_splits"] = not mismatches
    details["splits"] = mismatches[:100]
    try:
        training = audit_training(output_dir, protocol, splits)
        checks["complete_inner_curves_plateau_and_inner_only_selection"] = True
        details["training"] = []
    except Exception as exc:
        training = None
        checks["complete_inner_curves_plateau_and_inner_only_selection"] = False
        details["training"] = [f"{type(exc).__name__}: {exc}"]
    try:
        selected_states = load_selected_states(output_dir / "selected_inner_states.npz", protocol, startup_sha256)
        arrays = load_predictions(output_dir / "predictions.npz")
        evaluation = evaluate_predictions(arrays, records, protocol, splits, selected_states)
        checks["selected_states_outer_ensembles_and_member_conservation"] = True
        details["predictions"] = []
    except Exception as exc:
        evaluation = None
        checks["selected_states_outer_ensembles_and_member_conservation"] = False
        details["predictions"] = [f"{type(exc).__name__}: {exc}"]
    if evaluation is not None:
        mismatches = compare_csv(output_dir / "per_transcript_metrics.csv", evaluation["rows"])
        checks["per_transcript_metrics_csv_recomputed"] = not mismatches
        details["csv"] = mismatches[:100]
        expected_metrics = summarize_metric_rows(evaluation["rows"], seeds)
        mismatches = value_mismatches(summary.get("metrics"), expected_metrics, "summary.metrics")
        checks["summary_tb_mse_pearson_spearman_recomputed"] = not mismatches
        details["metrics"] = mismatches[:100]
        inference = recompute_inference(
            evaluation["rows"], seeds, n_resamples=n_resamples, batch_size=min(512, n_resamples),
        )
    else:
        checks["per_transcript_metrics_csv_recomputed"] = False
        checks["summary_tb_mse_pearson_spearman_recomputed"] = False
        expected_metrics = None
        inference = None
    expected_data = {
        "path": str(raw_path), "sha256": raw_sha, "qc": qc,
        "normalization": protocol["preprocessing"], "untouched_read": False,
    }
    for key, expected in (
        ("schema", SUMMARY_SCHEMA), ("protocol", PROTOCOL),
        ("status", "development_experiment_completed"), ("scope", protocol["scope"]),
        ("data", expected_data), ("limitations", protocol["limitations"]),
    ):
        mismatches = value_mismatches(summary.get(key), expected, f"summary.{key}")
        checks[f"summary_{key}"] = not mismatches
        details[f"summary_{key}"] = mismatches[:100]
    parameter_matching = {
        "per_inner_model": {"independent": 65, "position": 1, "kinetic": 65},
        "selected_inner_members_per_arm": 3,
        "per_selected_ensemble": {"independent": 195, "position": 3, "kinetic": 195},
    }
    mismatches = value_mismatches(summary.get("parameter_matching"), parameter_matching, "summary.parameter_matching")
    checks["parameter_count_matching"] = not mismatches
    details["parameter_matching"] = mismatches
    expected_artifacts = {
        "comparisons": {
            "primary": "independent_minus_kinetic_tb_mse",
            "simple_position_control": "position_minus_kinetic_tb_mse",
        },
        "ensemble": {
            "density_prediction": "equal-weight mean of selected inner member densities",
            "kinetic_conservation": "evaluated separately for every selected inner member",
            "mean_is_common_steady_state": False,
            "mean_residual_array_is_diagnostic_only": True,
        },
        "selected_inner_states": {
            "path": "selected_inner_states.npz",
            "selections": len(seeds) * 3 * len(ARMS),
            "members": len(seeds) * 3 * len(ARMS) * 3,
            "reconstruction": "load_selected_inner_member or predict_from_saved_state",
        },
    }
    for key, expected in expected_artifacts.items():
        mismatches = value_mismatches(summary.get(key), expected, f"summary.{key}")
        checks[f"summary_{key}"] = not mismatches
        details[key] = mismatches
    if training is not None:
        mismatches = value_mismatches(summary.get("convergence"), training["convergence"], "summary.convergence")
        checks["summary_convergence"] = not mismatches
        details["convergence"] = mismatches
        valid, mismatches = valid_cost(summary.get("cost"), training)
        checks["complete_cost_ledger"] = valid
        details["cost"] = mismatches
    else:
        checks["summary_convergence"] = False
        checks["complete_cost_ledger"] = False
    checks["real_cuda_no_fallback_recorded"] = valid_environment(summary.get("environment"))
    if has_parallel and training is not None:
        try:
            parallel_mismatches = audit_parallel(parallel_path, protocol, training, summary)
        except Exception as exc:
            parallel_mismatches = [f"{type(exc).__name__}: {exc}"]
        checks["parallel_shard_execution_ledger"] = not parallel_mismatches
        details["parallel"] = parallel_mismatches
    else:
        checks["parallel_shard_execution_ledger"] = not has_parallel
        details["parallel"] = [] if not has_parallel else ["parallel ledger requires complete training"]
    artifact_names = list(ARTIFACT_FILES) + (["parallel.json"] if has_parallel else [])
    artifact_hashes = {name: sha256_file(output_dir / name) for name in artifact_names}
    observed_sha = summary.get("sha256", {})
    expected_sha = {**startup_sha256, "raw_input": raw_sha, "artifacts": artifact_hashes}
    if has_parallel:
        expected_sha["parallel_implementation"] = sha256_file(PARALLEL_IMPLEMENTATION_PATH)
    mismatches = []
    for key, value in expected_sha.items():
        mismatches.extend(value_mismatches(observed_sha.get(key), value, f"summary.sha256.{key}"))
    checks["summary_artifact_sha256"] = not mismatches
    details["sha256"] = mismatches
    return {
        "schema": VERIFICATION_SCHEMA, "protocol": PROTOCOL,
        "passed": bool(all(checks.values())), "scope": protocol["scope"],
        "output_dir": str(output_dir), "raw_sha256": raw_sha,
        "protocol_sha256": sha256_file(protocol_path),
        "summary_sha256": sha256_file(output_dir / "summary.json"),
        "verification_script_sha256": sha256_file(__file__),
        "checks": checks, "mismatches": details,
        "recomputed": {
            "qc": qc, "metrics": expected_metrics,
            "member_conservation": evaluation["member_conservation"] if evaluation else None,
            "training": {key: value for key, value in training.items() if not key.startswith("_")} if training else None,
            "inference": inference,
        },
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--raw", required=True)
    parser.add_argument("--output-dir", required=True, help="Existing production output directory")
    parser.add_argument("--output", required=True, help="New exclusive independent verification JSON")
    parser.add_argument("--allow-synthetic", action="store_true", help="Explicitly permit non-Mohammad synthetic raw")
    parser.add_argument("--resamples", type=int, default=20000, help="Paired bootstrap and sign-flip resamples per seed")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    try:
        result = verify_e2_kinetic(
            args.protocol, args.raw, args.output_dir,
            allow_synthetic=args.allow_synthetic, n_resamples=args.resamples,
        )
    except Exception as exc:
        result = {
            "schema": VERIFICATION_SCHEMA, "protocol": PROTOCOL, "passed": False,
            "output_dir": args.output_dir,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    write_json_exclusive(output, result)
    print(json.dumps({"output": str(output), "passed": result["passed"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
