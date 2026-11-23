#!/usr/bin/env python3
"""Run the frozen A10-03/E2 development flux-conservation comparison."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
import torch
from scipy import stats
from torch import nn
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from codonflow.models import kinetic_mean_field


PROTOCOL = "a10_03_e2_kinetic_protocol_v2"
SUMMARY_SCHEMA = "a10-03-e2-kinetic-summary-v2"
SPLIT_SCHEMA = "a10-03-e2-kinetic-splits-v2"
SELECTION_SCHEMA = "a10-03-e2-kinetic-selection-v2"
PROVENANCE_SCHEMA = "a10-03-e2-kinetic-startup-provenance-v2"
STATE_SCHEMA = "a10-03-e2-kinetic-selected-inner-states-v2"
ARMS = ("independent", "position", "kinetic")
CODON_ALPHABET = "TCAG"
CODONS = tuple(
    first + second + third
    for first in CODON_ALPHABET
    for second in CODON_ALPHABET
    for third in CODON_ALPHABET
)
CODON_TO_INDEX = {codon: index for index, codon in enumerate(CODONS)}
STOP_CODONS = frozenset({"TAA", "TAG", "TGA"})
METRIC_FIELDS = [
    "seed",
    "arm",
    "outer_fold",
    "transcript_index",
    "transcript_id",
    "length",
    "n_positions",
    "mse",
    "pearson",
    "spearman",
    "solver_max_abs_normalized_residual",
]


@dataclass(frozen=True)
class Transcript:
    index: int
    transcript_id: str
    codons: np.ndarray
    counts: np.ndarray
    density: np.ndarray
    mask: np.ndarray
    coverage: float
    positive_mean: float

    @property
    def length(self):
        return int(len(self.codons))


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_exclusive(path, payload):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def learning_rate_grid(config):
    if config.get("spacing") != "log10_uniform":
        raise ValueError("learning rates must use a log10-uniform grid")
    minimum = float(config["minimum"])
    maximum = float(config["maximum"])
    count = _positive_int(config["count"], "learning rate count")
    if not math.isfinite(minimum) or not math.isfinite(maximum) or not 0 < minimum <= maximum:
        raise ValueError("learning rate bounds must be finite, positive and ordered")
    return np.logspace(math.log10(minimum), math.log10(maximum), count).tolist()


def load_protocol(path):
    with Path(path).open(encoding="utf-8") as handle:
        protocol = json.load(handle)
    if protocol.get("protocol") != PROTOCOL or protocol.get("schema") != "a10-03-e2-kinetic-protocol-v2":
        raise ValueError(f"protocol identity mismatch: expected {PROTOCOL}")
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
    if inputs.get("raw_path_supplied_by_cli") is not True or inputs.get("untouched_inputs_read") is not False:
        raise ValueError("raw input must be CLI-supplied development data only")
    if re.fullmatch(r"[0-9a-f]{64}", inputs.get("sha256", "")) is None:
        raise ValueError("raw input SHA256 must be lowercase hexadecimal")
    expected = _positive_int(inputs.get("expected_eligible_transcripts"), "eligible transcript count")
    if expected < 9:
        raise ValueError("3 by 3 nested transcript CV requires at least nine eligible transcripts")
    preprocessing = protocol.get("preprocessing", {})
    if preprocessing.get("convention") != "RK37" or preprocessing.get("positive_rule") != "count > 0.5":
        raise ValueError("protocol must freeze the RK37 count > 0.5 convention")
    if preprocessing.get("masked_first_positions") != 5 or preprocessing.get("masked_last_positions") != 4:
        raise ValueError("protocol must mask the first five and last four positions")
    if any((
        preprocessing.get("identity_rule") != "transcript ID and exact normalized CDS must each be unique",
        preprocessing.get("start_codon_rule") != "first codon must be ATG",
        preprocessing.get("terminal_stop_rule") != "last codon must be TAA, TAG or TGA",
        preprocessing.get("internal_stop_rule") != "no TAA, TAG or TGA before the terminal codon",
    )):
        raise ValueError("protocol must freeze CDS identity and ATG/stop QC")
    split = protocol.get("split", {})
    if split.get("unit") != "transcript" or split.get("outer_folds") != 3 or split.get("inner_folds") != 3:
        raise ValueError("protocol must freeze transcript-grouped 3 by 3 nested CV")
    if split.get("shared_across_arms_and_model_seeds") is not True:
        raise ValueError("splits must be shared across arms and model seeds")
    if split.get("outer_test_targets_used_for_fitting_early_stopping_or_selection") is not False:
        raise ValueError("outer test targets must not affect fitting, early stopping or selection")
    model = protocol.get("model", {})
    expected_parameters = {"independent": 65, "position": 1, "kinetic": 65}
    if model.get("arms") != list(ARMS) or model.get("trainable_parameters_per_model") != expected_parameters:
        raise ValueError("protocol must freeze independent/kinetic matching and the one-parameter position control")
    if model.get("trainable_parameters_per_selected_ensemble") != {arm: 3 * count for arm, count in expected_parameters.items()}:
        raise ValueError("protocol ensemble parameter counts do not match the three selected members")
    if model.get("extra_modules") is not False or model.get("selected_inner_ensemble_members") != 3:
        raise ValueError("no extra modules or unmatched ensemble capacity is allowed")
    if not 0 < float(model.get("rate_floor")) < float(model.get("rate_ceiling")):
        raise ValueError("rate floor and ceiling must be positive and ordered")
    training = protocol.get("training", {})
    seeds = training.get("model_seeds")
    if not isinstance(seeds, list) or len(seeds) < 3 or len(set(seeds)) != len(seeds):
        raise ValueError("at least three unique model seeds are required")
    for seed in seeds:
        _positive_int(seed, "model seed")
    maximum_epochs = _positive_int(training.get("maximum_epochs"), "maximum epochs")
    stopping = training.get("early_stopping", {})
    patience = _positive_int(stopping.get("patience_epochs"), "early stopping patience")
    if maximum_epochs <= patience or stopping.get("restore_best_validation_state") is not True:
        raise ValueError("epoch limit must exceed patience and best validation state must be restored")
    if training.get("maximum_epoch_is_not_convergence") is not True:
        raise ValueError("the epoch ceiling must not count as convergence")
    if training.get("record_every_epoch_train_and_validation_curve") is not True:
        raise ValueError("every train and validation epoch must be recorded")
    if training.get("gradient_clip_error_if_nonfinite") is not True or training.get("finite_parameters_required_after_optimizer_step") is not True:
        raise ValueError("nonfinite gradients and parameters must fail closed")
    learning_rate_grid(protocol.get("hyperparameters", {}).get("learning_rate", {}))
    weight_decays = protocol.get("hyperparameters", {}).get("weight_decays")
    if not isinstance(weight_decays, list) or not weight_decays:
        raise ValueError("weight decay grid must be nonempty")
    if any(not math.isfinite(float(value)) or float(value) < 0 for value in weight_decays):
        raise ValueError("weight decays must be finite and nonnegative")
    runtime = protocol.get("runtime", {})
    if runtime.get("device") != "cuda" or runtime.get("cpu_fallback") is not False:
        raise ValueError("production training requires explicit CUDA without CPU fallback")
    outputs = protocol.get("outputs", {})
    if outputs.get("overwrite") != "forbidden" or outputs.get("v2_requires_new_directory_not_v1_remote_output") is not True:
        raise ValueError("v2 outputs must be exclusive and separate from v1")
    if protocol.get("evaluation", {}).get("ensemble_mean_is_common_steady_state") is not False:
        raise ValueError("ensemble means must not be labeled a common steady state")
    return protocol


def _parse_codon_line(line, record_number):
    tokens = line.replace(",", " ").split()
    if len(tokens) == 1 and len(tokens[0]) % 3 == 0:
        sequence = tokens[0]
        tokens = [sequence[index:index + 3] for index in range(0, len(sequence), 3)]
    if not tokens or any(len(token) != 3 for token in tokens):
        raise ValueError(f"record {record_number}: codon line does not contain complete codons")
    indices = []
    for token in tokens:
        codon = token.upper().replace("U", "T")
        if codon not in CODON_TO_INDEX:
            raise ValueError(f"record {record_number}: invalid codon {token!r}")
        indices.append(CODON_TO_INDEX[codon])
    return np.asarray(indices, dtype=np.int64)


def parse_raw_matrix(path, expected_sha256=None):
    """Parse unique CDS records and apply frozen identity, ATG/stop and RK37 QC."""
    path = Path(path).expanduser().resolve()
    observed_sha = sha256_file(path)
    if expected_sha256 is not None and observed_sha != expected_sha256:
        raise ValueError(f"raw input SHA256 mismatch: expected {expected_sha256}, observed {observed_sha}")
    with path.open(encoding="utf-8-sig", newline=None) as handle:
        lines = [line.strip() for line in handle if line.strip()]
    if not lines or len(lines) % 3:
        raise ValueError("raw matrix must contain nonempty header/codon/count triplets")
    records = []
    seen_ids = {}
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
    for record_number, offset in enumerate(range(0, len(lines), 3), start=1):
        header, codon_line, count_line = lines[offset:offset + 3]
        if not header.startswith(">") or not header[1:].strip():
            raise ValueError(f"record {record_number}: header must start with '>' and contain an ID")
        transcript_id = header[1:].strip().split()[0]
        if transcript_id in seen_ids:
            previous = seen_ids[transcript_id]
            raise ValueError(
                f"record {record_number}: transcript ID conflict {transcript_id!r} with record {previous}",
            )
        codons = _parse_codon_line(codon_line, record_number)
        exact_cds = tuple(codons.tolist())
        if exact_cds in seen_cds:
            previous_number, previous_id = seen_cds[exact_cds]
            raise ValueError(
                f"record {record_number}: exact CDS conflict with record {previous_number} ({previous_id!r})",
            )
        seen_ids[transcript_id] = record_number
        seen_cds[exact_cds] = (record_number, transcript_id)
        try:
            counts = np.asarray([float(value) for value in count_line.replace(",", " ").split()], dtype=np.float64)
        except ValueError as error:
            raise ValueError(f"record {record_number}: count line contains a nonnumeric value") from error
        if counts.ndim != 1 or len(counts) != len(codons):
            raise ValueError(f"record {record_number}: codon and count lengths differ")
        if not np.all(np.isfinite(counts)) or np.any(counts < 0):
            raise ValueError(f"record {record_number}: counts must be finite and nonnegative")
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
        density = counts / positive_mean
        records.append(Transcript(
            index=len(records),
            transcript_id=transcript_id,
            codons=codons,
            counts=counts,
            density=density,
            mask=mask,
            coverage=coverage,
            positive_mean=positive_mean,
        ))
    qc.update({
        "eligible_transcripts": len(records),
        "sha256": observed_sha,
        "minimum_eligible_length": min((record.length for record in records), default=None),
        "maximum_eligible_length": max((record.length for record in records), default=None),
    })
    return records, qc


def _folds(indices, n_folds):
    return [np.sort(fold).astype(np.int64) for fold in np.array_split(np.asarray(indices), n_folds)]


def make_nested_splits(records, seed, outer_folds=3, inner_folds=3):
    if outer_folds != 3 or inner_folds != 3:
        raise ValueError("the frozen experiment requires three outer and three inner folds")
    indices = np.asarray([record.index for record in records], dtype=np.int64)
    if len(indices) < 9 or len(set(indices.tolist())) != len(indices):
        raise ValueError("nested CV requires at least nine unique transcript indices")
    permutation = np.random.default_rng(seed).permutation(indices)
    splits = []
    for outer_fold, test in enumerate(_folds(permutation, outer_folds)):
        development = np.sort(np.setdiff1d(indices, test, assume_unique=True))
        inner_permutation = np.random.default_rng([seed, outer_fold, 917]).permutation(development)
        inner = []
        for inner_fold, validation in enumerate(_folds(inner_permutation, inner_folds)):
            train = np.sort(np.setdiff1d(development, validation, assume_unique=True))
            if np.intersect1d(train, validation).size or np.intersect1d(train, test).size or np.intersect1d(validation, test).size:
                raise RuntimeError("nested transcript split leakage detected")
            inner.append({"inner_fold": inner_fold, "train": train, "validation": validation})
        splits.append({"outer_fold": outer_fold, "test": np.sort(test), "inner": inner})
    if not np.array_equal(np.sort(np.concatenate([item["test"] for item in splits])), indices):
        raise RuntimeError("outer folds do not partition all transcripts exactly once")
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
                "test_transcript_ids": [records[int(index)].transcript_id for index in outer["test"]],
                "inner_folds": [
                    {
                        "inner_fold": inner["inner_fold"],
                        "train_indices": inner["train"].tolist(),
                        "validation_indices": inner["validation"].tolist(),
                        "train_transcript_ids": [records[int(index)].transcript_id for index in inner["train"]],
                        "validation_transcript_ids": [records[int(index)].transcript_id for index in inner["validation"]],
                    }
                    for inner in outer["inner"]
                ],
            }
            for outer in splits
        ],
    }


class PositionField(nn.Module):
    def __init__(self):
        super().__init__()
        self.relative_position = nn.Linear(1, 1, bias=False)

    def forward(self, codons, lengths):
        max_length = codons.shape[1]
        denominator = torch.clamp(lengths.to(torch.float64) - 1, min=1).reshape(-1, 1)
        positions = torch.arange(max_length, device=codons.device, dtype=torch.float64).reshape(1, -1)
        relative = positions / denominator
        return self.relative_position(relative.unsqueeze(-1)).squeeze(-1)


class ScoreField(PositionField):
    def __init__(self):
        super().__init__()
        self.codon = nn.Embedding(64, 1)

    def forward(self, codons, lengths):
        return self.codon(codons).squeeze(-1) + super().forward(codons, lengths)


def resolve_cuda_device(name):
    device = torch.device(name)
    if device.type != "cuda":
        raise ValueError("production training requires an explicit CUDA device; refusing CPU fallback")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA was explicitly requested but is unavailable; refusing CPU fallback")
    index = torch.cuda.current_device() if device.index is None else device.index
    if index < 0 or index >= torch.cuda.device_count():
        raise ValueError(f"requested CUDA device index {index} is unavailable")
    device = torch.device("cuda", index)
    probe = torch.tensor([1.0, 2.0], dtype=torch.float64, device=device, requires_grad=True)
    probe.square().sum().backward()
    if probe.grad is None or probe.grad.device.type != "cuda":
        raise RuntimeError("CUDA forward/backward probe failed; refusing CPU fallback")
    torch.cuda.synchronize(device)
    return device


def _require_batch_solver():
    solver = getattr(kinetic_mean_field, "solve_kinetic_mean_field_batch", None)
    if not callable(solver):
        raise RuntimeError(
            "kinetic_mean_field.solve_kinetic_mean_field_batch(alpha,k,beta,lengths) is required; "
            "no CPU or single-sample production fallback is provided",
        )
    return solver


def _pack(records, device):
    lengths = torch.tensor([record.length for record in records], dtype=torch.int64, device=device)
    max_length = max(record.length for record in records)
    codons = torch.zeros((len(records), max_length), dtype=torch.int64, device=device)
    target = torch.zeros((len(records), max_length), dtype=torch.float64, device=device)
    mask = torch.zeros((len(records), max_length), dtype=torch.bool, device=device)
    for row, record in enumerate(records):
        length = record.length
        codons[row, :length] = torch.as_tensor(record.codons, dtype=torch.int64, device=device)
        target[row, :length] = torch.as_tensor(record.density, dtype=torch.float64, device=device)
        mask[row, :length] = torch.as_tensor(record.mask, dtype=torch.bool, device=device)
    return {"codons": codons, "target": target, "mask": mask, "lengths": lengths}


def forward_arm(model, arm, packed, model_config):
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    score = model(packed["codons"], packed["lengths"])
    if arm in {"independent", "position"}:
        return {"rho": torch.sigmoid(score), "flux": None, "residual": None, "rates": None}
    rates = float(model_config["rate_floor"]) + F.softplus(score)
    rates = torch.clamp(rates, max=float(model_config["rate_ceiling"]))
    lengths = packed["lengths"]
    rows = torch.arange(len(lengths), device=rates.device)
    real = torch.arange(rates.shape[1], device=rates.device).reshape(1, -1) < lengths.reshape(-1, 1)
    if not bool(torch.isfinite(rates[real]).all()) or not bool((rates[real] > 0).all()):
        raise RuntimeError("kinetic arm produced a nonfinite or nonpositive real rate")
    alpha = rates[:, 0]
    k = rates[:, :-1]
    beta = rates[rows, lengths - 1]
    solver = _require_batch_solver()
    rho, flux, residual = solver(alpha=alpha, k=k, beta=beta, lengths=lengths)
    expected_shapes = (rates.shape, (len(lengths),), (len(lengths), rates.shape[1] + 1))
    if rho.shape != expected_shapes[0] or flux.shape != expected_shapes[1] or residual.shape != expected_shapes[2]:
        raise RuntimeError("mean-field batch solver returned invalid padded shapes")
    if any(value.device != rates.device for value in (rho, flux, residual)):
        raise RuntimeError("mean-field batch solver changed the explicitly requested device")
    real_residual = torch.arange(residual.shape[1], device=rates.device).reshape(1, -1) <= lengths.reshape(-1, 1)
    if not bool(torch.isfinite(rho[real]).all()) or not bool(torch.isfinite(flux).all()) or not bool(torch.isfinite(residual[real_residual]).all()):
        raise RuntimeError("mean-field batch solver returned nonfinite real values")
    if bool((rho[real] < -1e-8).any()) or bool((rho[real] > 1 + 1e-8).any()) or bool((flux <= 0).any()):
        raise RuntimeError("mean-field batch solver returned values outside the physical domain")
    return {"rho": rho, "flux": flux, "residual": residual, "rates": rates}


def _transcript_losses(output, packed):
    squared = (output["rho"] - packed["target"]).square()
    mask = packed["mask"]
    counts = mask.sum(dim=1)
    if bool((counts == 0).any()):
        raise RuntimeError("every transcript must have at least one unmasked positive target")
    return (squared * mask).sum(dim=1) / counts


def _batches(records, batch_size, order=None):
    order = np.arange(len(records)) if order is None else np.asarray(order)
    for start in range(0, len(order), batch_size):
        yield [records[int(index)] for index in order[start:start + batch_size]]


def loss_on_records(model, arm, records, protocol, device, per_transcript=False):
    model.eval()
    losses = []
    indices = []
    with torch.no_grad():
        for batch in _batches(records, protocol["training"]["batch_transcripts"]):
            packed = _pack(batch, device)
            values = _transcript_losses(forward_arm(model, arm, packed, protocol["model"]), packed)
            losses.extend(float(value) for value in values.detach().cpu())
            indices.extend(record.index for record in batch)
    if per_transcript:
        return dict(zip(indices, losses))
    return float(np.mean(losses))


def predict_on_records(model, arm, records, protocol, device):
    model.eval()
    result = {}
    with torch.no_grad():
        for batch in _batches(records, protocol["training"]["batch_transcripts"]):
            packed = _pack(batch, device)
            output = forward_arm(model, arm, packed, protocol["model"])
            for row, record in enumerate(batch):
                length = record.length
                result[record.index] = {
                    "rho": output["rho"][row, :length].detach().cpu().numpy(),
                    "flux": None if output["flux"] is None else float(output["flux"][row].detach().cpu()),
                    "residual": None if output["residual"] is None else output["residual"][row, :length + 1].detach().cpu().numpy(),
                    "max_abs_residual": None if output["residual"] is None else float(output["residual"][row, :length + 1].abs().max().detach().cpu()),
                }
    return result


def _new_model(device, seed, arm="independent"):
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    model = PositionField() if arm == "position" else ScoreField()
    return model.to(device=device, dtype=torch.float64)


def _require_finite_parameters(model, context):
    for name, parameter in model.named_parameters():
        if not bool(torch.isfinite(parameter).all()):
            raise RuntimeError(f"nonfinite model parameter {name!r} {context}")


def _synchronize(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def save_selected_inner_states(path, selected_states, model_config, startup_sha256):
    arrays = {}
    metadata_records = []
    for selection in selected_states:
        metadata = {key: value for key, value in selection.items() if key != "members"}
        metadata["members"] = []
        for member in selection["members"]:
            member_metadata = {key: value for key, value in member.items() if key != "state"}
            state_keys = {}
            for name, value in member["state"].items():
                key = (
                    f"state/{selection['seed_index']}/{selection['outer_fold']}/"
                    f"{selection['arm_index']}/{member['inner_fold']}/{name}"
                )
                arrays[key] = value.detach().cpu().numpy()
                state_keys[name] = key
            member_metadata["state_keys"] = state_keys
            metadata["members"].append(member_metadata)
        metadata_records.append(metadata)
    payload = {
        "schema": STATE_SCHEMA,
        "protocol": PROTOCOL,
        "dtype": "float64",
        "model_config": model_config,
        "startup_sha256": startup_sha256,
        "records": metadata_records,
    }
    arrays["metadata"] = np.asarray(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    with Path(path).open("xb") as handle:
        np.savez_compressed(handle, **arrays)


def load_selected_inner_member(path, seed, outer_fold, arm, inner_fold, protocol, device):
    with np.load(Path(path), allow_pickle=False) as archive:
        metadata = json.loads(archive["metadata"].item())
        if metadata.get("schema") != STATE_SCHEMA or metadata.get("protocol") != PROTOCOL:
            raise ValueError("selected inner state archive identity mismatch")
        if metadata.get("model_config") != protocol["model"] or metadata.get("dtype") != "float64":
            raise ValueError("selected inner state archive configuration mismatch")
        matches = [
            record for record in metadata["records"]
            if (record["seed"], record["outer_fold"], record["arm"]) == (seed, outer_fold, arm)
        ]
        if len(matches) != 1:
            raise ValueError("selected inner state archive must contain exactly one matching selection")
        selection = matches[0]
        members = [member for member in selection["members"] if member["inner_fold"] == inner_fold]
        if len(members) != 1:
            raise ValueError("selected inner state archive must contain exactly one matching member")
        member = members[0]
        state = {
            name: torch.from_numpy(archive[key].copy()).to(device=device, dtype=torch.float64)
            for name, key in member["state_keys"].items()
        }
    model = _new_model(device, member["fit_seed"], arm)
    model.load_state_dict(state, strict=True)
    _require_finite_parameters(model, "after loading selected inner state")
    return model, {"selection": selection, "member": member}


def predict_from_saved_state(path, seed, outer_fold, arm, inner_fold, records, protocol, device):
    model, _ = load_selected_inner_member(
        path, seed, outer_fold, arm, inner_fold, protocol, device,
    )
    return predict_on_records(model, arm, records, protocol, device)


def fit_candidate(arm, train_records, validation_records, learning_rate, weight_decay, seed, protocol, device):
    """Fit one inner candidate without accepting or inspecting any outer-test records."""
    started = time.perf_counter()
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    model = _new_model(device, seed, arm)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    training = protocol["training"]
    stopping = training["early_stopping"]
    maximum_epochs = training["maximum_epochs"]
    patience = stopping["patience_epochs"]
    min_improvement = float(stopping["min_absolute_improvement"])
    rng = np.random.default_rng(seed)
    best_loss = math.inf
    best_epoch = None
    best_state = None
    stale_epochs = 0
    curves = []
    stop_reason = "maximum_epochs_reached"
    for epoch in range(1, maximum_epochs + 1):
        model.train()
        for batch in _batches(train_records, training["batch_transcripts"], rng.permutation(len(train_records))):
            packed = _pack(batch, device)
            optimizer.zero_grad(set_to_none=True)
            loss = _transcript_losses(forward_arm(model, arm, packed, protocol["model"]), packed).mean()
            if not bool(torch.isfinite(loss)):
                raise RuntimeError("nonfinite training loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                model.parameters(), training["gradient_clip_norm"], error_if_nonfinite=True,
            )
            optimizer.step()
            _require_finite_parameters(model, "after optimizer step")
        train_loss = loss_on_records(model, arm, train_records, protocol, device)
        validation_loss = loss_on_records(model, arm, validation_records, protocol, device)
        _synchronize(device)
        curves.append({
            "epoch": epoch,
            "train_tb_mse": train_loss,
            "validation_tb_mse": validation_loss,
            "elapsed_seconds": time.perf_counter() - started,
        })
        if validation_loss < best_loss - min_improvement:
            best_loss = validation_loss
            best_epoch = epoch
            best_state = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= patience:
                stop_reason = "validation_plateau"
                break
    if best_state is None:
        raise RuntimeError("training did not produce a finite validation state")
    model.load_state_dict({name: value.to(device) for name, value in best_state.items()})
    _require_finite_parameters(model, "after restoring best validation state")
    validation_mse = loss_on_records(model, arm, validation_records, protocol, device, per_transcript=True)
    _synchronize(device)
    cost = {
        "wall_clock_seconds": time.perf_counter() - started,
        "epochs_ran": len(curves),
        "train_transcripts": len(train_records),
        "validation_transcripts": len(validation_records),
        "cuda_peak_memory_bytes": torch.cuda.max_memory_allocated(device) if device.type == "cuda" else None,
    }
    return {
        "best_state": best_state,
        "best_epoch": best_epoch,
        "best_validation_tb_mse": best_loss,
        "validation_transcript_mse": validation_mse,
        "curves": curves,
        "stop_reason": stop_reason,
        "validation_plateau_converged": stop_reason == "validation_plateau",
        "maximum_epoch_is_not_convergence": True,
        "cost": cost,
    }


def _correlations(target, prediction):
    if len(target) < 2 or np.ptp(target) == 0 or np.ptp(prediction) == 0:
        return None, None
    pearson = float(stats.pearsonr(target, prediction)[0])
    spearman = float(stats.spearmanr(target, prediction)[0])
    if not math.isfinite(pearson) or not math.isfinite(spearman):
        return None, None
    return pearson, spearman


def _mean_or_none(values):
    defined = [value for value in values if value is not None]
    return float(np.mean(defined)) if defined else None


def prediction_metrics(records, predictions, solver_residuals, seeds):
    rows = []
    for seed_index, seed in enumerate(seeds):
        for arm_index, arm in enumerate(ARMS):
            for record in records:
                mask = record.mask
                target = record.density[mask]
                prediction = predictions[seed_index, arm_index, record.index, :record.length][mask]
                if not np.all(np.isfinite(prediction)):
                    raise RuntimeError("missing or nonfinite outer-test prediction")
                pearson, spearman = _correlations(target, prediction)
                residual = solver_residuals[seed_index, arm_index, record.index]
                rows.append({
                    "seed": seed,
                    "arm": arm,
                    "outer_fold": None,
                    "transcript_index": record.index,
                    "transcript_id": record.transcript_id,
                    "length": record.length,
                    "n_positions": int(mask.sum()),
                    "mse": float(np.mean((target - prediction) ** 2)),
                    "pearson": pearson,
                    "spearman": spearman,
                    "solver_max_abs_normalized_residual": float(residual) if np.isfinite(residual) else None,
                })
    return rows


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
                "mean_per_transcript_pearson": _mean_or_none([row["pearson"] for row in selected]),
                "mean_per_transcript_spearman": _mean_or_none([row["spearman"] for row in selected]),
                "defined_pearson": sum(row["pearson"] is not None for row in selected),
                "defined_spearman": sum(row["spearman"] is not None for row in selected),
                "maximum_solver_abs_normalized_residual": max(residuals) if residuals[0] is not None else None,
            }
        independent = summary[str(seed)]["independent"]["tb_mse"]
        position = summary[str(seed)]["position"]["tb_mse"]
        kinetic = summary[str(seed)]["kinetic"]["tb_mse"]
        summary[str(seed)]["independent_minus_kinetic_tb_mse"] = independent - kinetic
        summary[str(seed)]["position_minus_kinetic_tb_mse"] = position - kinetic
    return summary


def _environment(device):
    cuda = {
        "requested_device": str(device),
        "available": torch.cuda.is_available(),
        "torch_cuda_version": torch.version.cuda,
    }
    if device.type == "cuda":
        cuda.update({
            "name": torch.cuda.get_device_name(device),
            "capability": list(torch.cuda.get_device_capability(device)),
        })
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "torch": torch.__version__,
        "cuda": cuda,
    }


def run_experiment(protocol_path, raw_path, output_dir, device="cuda:0"):
    started = time.perf_counter()
    started_utc = datetime.now(timezone.utc).isoformat()
    protocol_path = Path(protocol_path).expanduser().resolve()
    raw_path = Path(raw_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {output_dir}")
    protocol = load_protocol(protocol_path)
    if protocol["inputs"].get("expected_basename") and raw_path.name != protocol["inputs"]["expected_basename"]:
        raise ValueError(f"raw input basename must be {protocol['inputs']['expected_basename']!r}")
    startup_sha256 = {
        "protocol": sha256_file(protocol_path),
        "implementation": sha256_file(Path(__file__).resolve()),
        "mean_field_operator": sha256_file(kinetic_mean_field.__file__),
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(output_dir / "provenance.json", {
        "schema": PROVENANCE_SCHEMA,
        "protocol": PROTOCOL,
        "recorded_utc": started_utc,
        "stage": "startup_before_device_probe_raw_parse_or_training",
        "sha256": startup_sha256,
    })
    device = resolve_cuda_device(device)
    _require_batch_solver()
    records, qc = parse_raw_matrix(raw_path, protocol["inputs"]["sha256"])
    expected = protocol["inputs"]["expected_eligible_transcripts"]
    if len(records) != expected:
        raise ValueError(f"eligible transcript count mismatch: expected {expected}, observed {len(records)}")
    splits = make_nested_splits(records, protocol["split"]["seed"])
    write_json_exclusive(output_dir / "splits.json", split_payload(splits, records))

    seeds = protocol["training"]["model_seeds"]
    rates = learning_rate_grid(protocol["hyperparameters"]["learning_rate"])
    weight_decays = protocol["hyperparameters"]["weight_decays"]
    max_length = max(record.length for record in records)
    predictions = np.full((len(seeds), len(ARMS), len(records), max_length), np.nan, dtype=np.float64)
    fluxes = np.full((len(seeds), len(ARMS), len(records)), np.nan, dtype=np.float64)
    residuals = np.full((len(seeds), len(ARMS), len(records), max_length + 1), np.nan, dtype=np.float64)
    solver_residuals = np.full((len(seeds), len(ARMS), len(records)), np.nan, dtype=np.float64)
    target = np.full((len(records), max_length), np.nan, dtype=np.float64)
    mask = np.zeros((len(records), max_length), dtype=np.bool_)
    codons = np.full((len(records), max_length), -1, dtype=np.int64)
    outer_assignment = np.full(len(records), -1, dtype=np.int64)
    for record in records:
        target[record.index, :record.length] = record.density
        mask[record.index, :record.length] = record.mask
        codons[record.index, :record.length] = record.codons
    for outer in splits:
        outer_assignment[outer["test"]] = outer["outer_fold"]

    selection_records = []
    selected_state_records = []
    fit_costs = []
    with (output_dir / "curves.jsonl").open("x", encoding="utf-8", newline="\n") as curve_handle:
        for seed_index, seed in enumerate(seeds):
            for outer in splits:
                outer_test = [records[int(index)] for index in outer["test"]]
                for arm_index, arm in enumerate(ARMS):
                    candidates = []
                    for grid_index, (learning_rate, weight_decay) in enumerate((lr, wd) for lr in rates for wd in weight_decays):
                        candidate = {
                            "grid_index": grid_index,
                            "learning_rate": learning_rate,
                            "weight_decay": weight_decay,
                            "folds": [],
                        }
                        states = []
                        oof_mse = {}
                        for inner in outer["inner"]:
                            train_records = [records[int(index)] for index in inner["train"]]
                            validation_records = [records[int(index)] for index in inner["validation"]]
                            fit_seed = int(np.random.SeedSequence([seed, outer["outer_fold"], inner["inner_fold"]]).generate_state(1)[0])
                            fitted = fit_candidate(
                                arm, train_records, validation_records, learning_rate, weight_decay,
                                fit_seed, protocol, device,
                            )
                            states.append({
                                "inner_fold": inner["inner_fold"],
                                "fit_seed": fit_seed,
                                "best_epoch": fitted["best_epoch"],
                                "best_validation_tb_mse": fitted["best_validation_tb_mse"],
                                "state": fitted["best_state"],
                            })
                            oof_mse.update(fitted["validation_transcript_mse"])
                            candidate["folds"].append({
                                "inner_fold": inner["inner_fold"],
                                "best_epoch": fitted["best_epoch"],
                                "best_validation_tb_mse": fitted["best_validation_tb_mse"],
                                "stop_reason": fitted["stop_reason"],
                                "validation_plateau_converged": fitted["validation_plateau_converged"],
                                "cost": fitted["cost"],
                            })
                            fit_costs.append(fitted["cost"])
                            curve_record = {
                                "schema": "a10-03-e2-kinetic-curve-v2",
                                "seed": seed,
                                "outer_fold": outer["outer_fold"],
                                "inner_fold": inner["inner_fold"],
                                "arm": arm,
                                "grid_index": grid_index,
                                "learning_rate": learning_rate,
                                "weight_decay": weight_decay,
                                "stop_reason": fitted["stop_reason"],
                                "validation_plateau_converged": fitted["validation_plateau_converged"],
                                "maximum_epoch_is_not_convergence": True,
                                "epochs": fitted["curves"],
                            }
                            curve_handle.write(json.dumps(curve_record, allow_nan=False) + "\n")
                        expected_oof = set(int(index) for outer_inner in outer["inner"] for index in outer_inner["validation"])
                        if set(oof_mse) != expected_oof or set(oof_mse) & set(outer["test"].tolist()):
                            raise RuntimeError("inner out-of-fold predictions are incomplete or touch outer test")
                        candidate["inner_oof_tb_mse"] = float(np.mean(list(oof_mse.values())))
                        candidate["inner_oof_transcripts"] = len(oof_mse)
                        candidates.append({"report": candidate, "states": states})
                    selected_index = min(range(len(candidates)), key=lambda index: candidates[index]["report"]["inner_oof_tb_mse"])
                    selected = candidates[selected_index]
                    selection_records.append({
                        "seed": seed,
                        "outer_fold": outer["outer_fold"],
                        "arm": arm,
                        "selected_grid_index": selected_index,
                        "selection_metric": "inner_oof_tb_mse",
                        "outer_test_used_for_selection": False,
                        "candidates": [candidate["report"] for candidate in candidates],
                    })
                    selected_state_records.append({
                        "seed": seed,
                        "seed_index": seed_index,
                        "outer_fold": outer["outer_fold"],
                        "arm": arm,
                        "arm_index": arm_index,
                        "selected_grid_index": selected_index,
                        "learning_rate": selected["report"]["learning_rate"],
                        "weight_decay": selected["report"]["weight_decay"],
                        "members": selected["states"],
                    })
                    member_predictions = []
                    for state in selected["states"]:
                        model = _new_model(device, state["fit_seed"], arm)
                        model.load_state_dict({
                            name: value.to(device) for name, value in state["state"].items()
                        })
                        _require_finite_parameters(model, "after restoring selected inner state")
                        member_predictions.append(predict_on_records(model, arm, outer_test, protocol, device))
                    for record in outer_test:
                        index = record.index
                        members = [prediction[index] for prediction in member_predictions]
                        predictions[seed_index, arm_index, index, :record.length] = np.mean([item["rho"] for item in members], axis=0)
                        if arm == "kinetic":
                            fluxes[seed_index, arm_index, index] = float(np.mean([item["flux"] for item in members]))
                            residuals[seed_index, arm_index, index, :record.length + 1] = np.mean([item["residual"] for item in members], axis=0)
                            solver_residuals[seed_index, arm_index, index] = max(item["max_abs_residual"] for item in members)

    state_path = output_dir / "selected_inner_states.npz"
    save_selected_inner_states(state_path, selected_state_records, protocol["model"], startup_sha256)

    rows = prediction_metrics(records, predictions, solver_residuals, seeds)
    for row in rows:
        row["outer_fold"] = int(outer_assignment[row["transcript_index"]])
    with (output_dir / "per_transcript_metrics.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=METRIC_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    write_json_exclusive(output_dir / "selection.json", {
        "schema": SELECTION_SCHEMA,
        "protocol": PROTOCOL,
        "records": selection_records,
    })
    with (output_dir / "predictions.npz").open("xb") as handle:
        np.savez_compressed(
            handle,
            seeds=np.asarray(seeds, dtype=np.int64),
            arms=np.asarray(ARMS),
            transcript_indices=np.arange(len(records), dtype=np.int64),
            transcript_ids=np.asarray([record.transcript_id for record in records]),
            lengths=np.asarray([record.length for record in records], dtype=np.int64),
            codons=codons,
            target=target,
            mask=mask,
            outer_fold=outer_assignment,
            prediction=predictions,
            flux=fluxes,
            ensemble_mean_residual_diagnostic=residuals,
            solver_max_abs_normalized_residual=solver_residuals,
            ensemble_mean_is_common_steady_state=np.asarray(False),
            kinetic_conservation_level=np.asarray("selected_inner_member_separately"),
        )
    metrics = summarize_metric_rows(rows, seeds)
    all_fits = [fold for record in selection_records for candidate in record["candidates"] for fold in candidate["folds"]]
    artifact_hashes = {
        name: sha256_file(output_dir / name)
        for name in (
            "provenance.json", "splits.json", "curves.jsonl", "selection.json",
            "selected_inner_states.npz", "predictions.npz", "per_transcript_metrics.csv",
        )
    }
    summary = {
        "schema": SUMMARY_SCHEMA,
        "protocol": PROTOCOL,
        "status": "development_experiment_completed",
        "scope": protocol["scope"],
        "data": {
            "path": str(raw_path),
            "sha256": protocol["inputs"]["sha256"],
            "qc": qc,
            "normalization": protocol["preprocessing"],
            "untouched_read": False,
        },
        "parameter_matching": {
            "per_inner_model": {
                arm: sum(parameter.numel() for parameter in _new_model(torch.device("cpu"), 1, arm).parameters())
                for arm in ARMS
            },
            "selected_inner_members_per_arm": 3,
            "per_selected_ensemble": {
                arm: 3 * sum(parameter.numel() for parameter in _new_model(torch.device("cpu"), 1, arm).parameters())
                for arm in ARMS
            },
        },
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
            "selections": len(selected_state_records),
            "members": sum(len(record["members"]) for record in selected_state_records),
            "reconstruction": "load_selected_inner_member or predict_from_saved_state",
        },
        "metrics": metrics,
        "convergence": {
            "fits": len(all_fits),
            "validation_plateau": sum(fold["stop_reason"] == "validation_plateau" for fold in all_fits),
            "maximum_epochs_reached_not_converged": sum(fold["stop_reason"] == "maximum_epochs_reached" for fold in all_fits),
            "maximum_epoch_is_not_convergence": True,
            "complete_curves_file": "curves.jsonl",
        },
        "cost": {
            "started_utc": started_utc,
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "wall_clock_seconds": time.perf_counter() - started,
            "candidate_fits": len(fit_costs),
            "epochs_ran": sum(cost["epochs_ran"] for cost in fit_costs),
            "candidate_fit_wall_clock_seconds": sum(cost["wall_clock_seconds"] for cost in fit_costs),
            "cuda_peak_memory_bytes": max((cost["cuda_peak_memory_bytes"] or 0 for cost in fit_costs), default=0) if device.type == "cuda" else None,
        },
        "environment": _environment(device),
        "sha256": {
            **startup_sha256,
            "raw_input": protocol["inputs"]["sha256"],
            "artifacts": artifact_hashes,
        },
        "limitations": protocol["limitations"],
    }
    write_json_exclusive(output_dir / "summary.json", summary)
    print(json.dumps({"status": summary["status"], "output_dir": str(output_dir), "seeds": seeds}))
    return summary


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--protocol", required=True, help="Frozen A10-03/E2 protocol JSON")
    parser.add_argument("--raw", required=True, help="Development Mohammad16 raw matrix; never an untouched input")
    parser.add_argument("--output-dir", required=True, help="New exclusive output directory")
    parser.add_argument("--device", default="cuda:0", help="Explicit CUDA device; CPU is rejected")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    run_experiment(args.protocol, args.raw, args.output_dir, args.device)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
