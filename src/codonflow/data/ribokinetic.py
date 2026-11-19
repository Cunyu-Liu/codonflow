"""RK-08 functional and per-codon velocity datasets.

The loaders are deliberately strict: invalid CDS, duplicate codon positions and
inconsistent metadata raise instead of being silently dropped. Target
normalization and host vocabulary are fitted on train records only.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Collection, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import torch

from ..core.codon import is_valid_cds, is_valid_nucleotide_seq, normalize_to_dna
from ..core.tokenizer import PAD_ID, encode_cds


def file_sha256(path: str, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(block_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _open_text(path: str):
    return gzip.open(path, "rt", newline="") if str(path).endswith(".gz") else open(path, newline="")


def _optional_float(value: object) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    result = float(value)
    return result if math.isfinite(result) else None


@dataclass(frozen=True)
class VariantRecord:
    record_id: str
    cds: str
    split: str
    cluster_id: str = ""
    host: str = "unknown"
    function_target: Optional[float] = None
    initiation_target: Optional[Tuple[float, ...]] = None
    velocity_target: Optional[Tuple[float, ...]] = None
    decay_target: Optional[Tuple[float, ...]] = None
    budget: Optional[float] = None
    utr: Optional[str] = None

    def __post_init__(self) -> None:
        normalized = normalize_to_dna(self.cds)
        object.__setattr__(self, "cds", normalized)
        if not self.record_id:
            raise ValueError("record_id cannot be empty")
        if not self.split:
            raise ValueError("split cannot be empty")
        if not is_valid_cds(normalized):
            raise ValueError(f"invalid CDS for {self.record_id}: frame/stop/alphabet check failed")
        codon_count = len(normalized) // 3
        for name in ("initiation_target", "velocity_target", "decay_target"):
            target = getattr(self, name)
            if target is not None:
                values = tuple(float(x) for x in target)
                if len(values) != codon_count:
                    raise ValueError(f"{name} length != codon count for {self.record_id}")
                if any(math.isinf(x) for x in values):
                    raise ValueError(f"{name} contains infinity for {self.record_id}")
                object.__setattr__(self, name, values)
        if self.function_target is not None and not math.isfinite(self.function_target):
            raise ValueError(f"non-finite function target for {self.record_id}")
        if self.budget is not None and not math.isfinite(self.budget):
            raise ValueError(f"non-finite budget for {self.record_id}")
        if self.utr is not None:
            utr = normalize_to_dna(self.utr)
            if not is_valid_nucleotide_seq(utr):
                raise ValueError(f"invalid UTR alphabet for {self.record_id}")
            object.__setattr__(self, "utr", utr)

    @property
    def codon_count(self) -> int:
        return len(self.cds) // 3


def read_functional_csv(
    path: str,
    cds_column: str = "cds",
    target_column: str = "expression_value",
    split_column: str = "split_assignment",
    id_column: str = "construct_id",
    cluster_column: str = "operational_protein_cluster",
    host_column: str = "host",
    utr_column: Optional[str] = None,
    include_splits: Optional[Collection[str]] = None,
    max_rows_per_split: Optional[int] = None,
) -> List[VariantRecord]:
    """Read one-row-per-CDS functional data without silently dropping rows."""
    records: List[VariantRecord] = []
    split_counts: Dict[str, int] = {}
    with _open_text(path) as handle:
        reader = csv.DictReader(handle)
        required = {cds_column, target_column, split_column, id_column}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing required columns: {sorted(missing)}")
        for line_number, row in enumerate(reader, start=2):
            split = row[split_column].strip()
            if include_splits is not None and split not in include_splits:
                continue
            if max_rows_per_split is not None and split_counts.get(split, 0) >= max_rows_per_split:
                continue
            target = _optional_float(row[target_column])
            if target is None:
                raise ValueError(f"missing/non-finite {target_column} at line {line_number}")
            try:
                record = VariantRecord(
                    record_id=row[id_column].strip(),
                    cds=row[cds_column],
                    split=split,
                    cluster_id=row.get(cluster_column, "").strip(),
                    host=row.get(host_column, "unknown").strip() or "unknown",
                    function_target=target,
                    utr=row.get(utr_column) if utr_column else None,
                )
            except (KeyError, ValueError) as exc:
                raise ValueError(f"invalid functional row at line {line_number}: {exc}") from exc
            records.append(record)
            split_counts[split] = split_counts.get(split, 0) + 1
    if not records:
        raise ValueError("no functional records loaded")
    return records


def read_velocity_long_csv(
    path: str,
    sequence_id_column: str,
    cds_column: str,
    position_column: str,
    target_column: str,
    split_column: str,
    cluster_column: str = "operational_protein_cluster",
    host_column: str = "host",
    position_base: int = 0,
) -> List[VariantRecord]:
    """Read long per-codon Ribo data; unobserved positions retain NaN + mask."""
    if position_base not in (0, 1):
        raise ValueError("position_base must be 0 or 1")
    grouped: Dict[str, dict] = {}
    with _open_text(path) as handle:
        reader = csv.DictReader(handle)
        required = {sequence_id_column, cds_column, position_column, target_column, split_column}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing required columns: {sorted(missing)}")
        for line_number, row in enumerate(reader, start=2):
            record_id = row[sequence_id_column].strip()
            cds = normalize_to_dna(row[cds_column])
            position = int(row[position_column]) - position_base
            target = _optional_float(row[target_column])
            if target is None:
                raise ValueError(f"missing/non-finite target at line {line_number}")
            if not 0 <= position < len(cds) // 3:
                raise ValueError(f"codon position out of range at line {line_number}")
            metadata = grouped.setdefault(
                record_id,
                {
                    "cds": cds,
                    "split": row[split_column].strip(),
                    "cluster_id": row.get(cluster_column, "").strip(),
                    "host": row.get(host_column, "unknown").strip() or "unknown",
                    "targets": {},
                },
            )
            expected = {
                "cds": cds,
                "split": row[split_column].strip(),
                "cluster_id": row.get(cluster_column, "").strip(),
                "host": row.get(host_column, "unknown").strip() or "unknown",
            }
            for key, expected_value in expected.items():
                if metadata[key] != expected_value:
                    raise ValueError(f"inconsistent {key} for {record_id} at line {line_number}")
            if position in metadata["targets"]:
                raise ValueError(f"duplicate codon position for {record_id} at line {line_number}")
            metadata["targets"][position] = target
    records = []
    for record_id, metadata in grouped.items():
        codon_count = len(metadata["cds"]) // 3
        values = tuple(metadata["targets"].get(i, float("nan")) for i in range(codon_count))
        records.append(
            VariantRecord(
                record_id=record_id,
                cds=metadata["cds"],
                split=metadata["split"],
                cluster_id=metadata["cluster_id"],
                host=metadata["host"],
                velocity_target=values,
            )
        )
    if not records:
        raise ValueError("no velocity records loaded")
    return records


def fit_host_vocabulary(records: Sequence[VariantRecord]) -> Dict[str, int]:
    """Fit host IDs on train only; zero is reserved for unseen/unknown hosts."""
    hosts = sorted({r.host for r in records if r.split == "train"})
    if not hosts:
        raise ValueError("no train hosts available")
    return {host: i + 1 for i, host in enumerate(hosts)}


@dataclass(frozen=True)
class TargetNormalizer:
    target: str
    mean: float
    scale: float
    log1p: bool
    train_value_count: int

    @classmethod
    def fit(cls, records: Sequence[VariantRecord], target: str, log1p: bool = False):
        if target not in ("function", "initiation", "velocity", "decay"):
            raise ValueError(f"unknown target {target}")
        values: List[float] = []
        for record in records:
            if record.split != "train":
                continue
            raw = getattr(record, f"{target}_target")
            if raw is None:
                continue
            current = [float(raw)] if target == "function" else list(raw)
            for value in current:
                if not math.isfinite(value):
                    continue
                if log1p:
                    if value < 0:
                        raise ValueError("log1p normalization requires nonnegative targets")
                    value = math.log1p(value)
                values.append(value)
        if not values:
            raise ValueError(f"no finite train values for {target}")
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return cls(target, mean, max(math.sqrt(variance), 1e-8), log1p, len(values))

    def transform_value(self, value: float) -> float:
        if not math.isfinite(value):
            return value
        if self.log1p:
            if value < 0:
                raise ValueError("log1p normalization requires nonnegative targets")
            value = math.log1p(value)
        return (value - self.mean) / self.scale

    def apply(self, records: Sequence[VariantRecord]) -> List[VariantRecord]:
        transformed = []
        for record in records:
            raw = getattr(record, f"{self.target}_target")
            if raw is None:
                transformed.append(record)
            elif self.target == "function":
                transformed.append(replace(record, function_target=self.transform_value(float(raw))))
            else:
                values = tuple(self.transform_value(x) for x in raw)
                transformed.append(replace(record, **{f"{self.target}_target": values}))
        return transformed

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "mean": self.mean,
            "scale": self.scale,
            "log1p": self.log1p,
            "train_value_count": self.train_value_count,
            "fit_split": "train_only",
        }


def collate_ribokinetic(
    records: Sequence[VariantRecord],
    host_vocabulary: Optional[Mapping[str, int]] = None,
) -> Dict[str, torch.Tensor]:
    """Pad codon/target tensors and preserve finite-target masks."""
    if not records:
        raise ValueError("cannot collate an empty batch")
    encoded = [encode_cds(r.cds, add_special=False) for r in records]
    max_len = max(len(x) for x in encoded)
    batch_size = len(records)
    codon_ids = torch.full((batch_size, max_len), PAD_ID, dtype=torch.long)
    pad_mask = torch.ones((batch_size, max_len), dtype=torch.bool)
    for i, ids in enumerate(encoded):
        codon_ids[i, : len(ids)] = torch.tensor(ids, dtype=torch.long)
        pad_mask[i, : len(ids)] = False
    batch: Dict[str, torch.Tensor] = {"codon_ids": codon_ids, "pad_mask": pad_mask}
    vocabulary = host_vocabulary or {}
    batch["host_ids"] = torch.tensor(
        [vocabulary.get(r.host, 0) for r in records], dtype=torch.long
    )
    if all(r.budget is not None for r in records):
        batch["budget"] = torch.tensor([r.budget for r in records], dtype=torch.float32)
    function_mask = torch.tensor([r.function_target is not None for r in records], dtype=torch.bool)
    if function_mask.any():
        batch["function_target"] = torch.tensor(
            [r.function_target if r.function_target is not None else 0.0 for r in records],
            dtype=torch.float32,
        )
        batch["function_mask"] = function_mask
    for name in ("initiation", "velocity", "decay"):
        raw_targets = [getattr(r, f"{name}_target") for r in records]
        if not any(x is not None for x in raw_targets):
            continue
        target = torch.zeros((batch_size, max_len), dtype=torch.float32)
        mask = torch.zeros((batch_size, max_len), dtype=torch.bool)
        for i, (record, values) in enumerate(zip(records, raw_targets)):
            if values is None:
                continue
            length = record.codon_count
            target[i, :length] = torch.nan_to_num(torch.tensor(values, dtype=torch.float32))
            finite = torch.tensor([math.isfinite(x) for x in values], dtype=torch.bool)
            mask[i, :length] = finite
        batch[f"{name}_target"] = target
        batch[f"{name}_mask"] = mask
    if all(r.utr is not None for r in records):
        max_utr = max(len(r.utr) for r in records)
        utr_ids = torch.full((batch_size, max_utr), 4, dtype=torch.long)
        mapping = {"A": 0, "C": 1, "G": 2, "T": 3}
        for i, record in enumerate(records):
            utr_ids[i, : len(record.utr)] = torch.tensor(
                [mapping[x] for x in record.utr], dtype=torch.long
            )
        batch["utr_ids"] = utr_ids
    return batch


def move_batch(batch: Mapping[str, torch.Tensor], device: torch.device) -> Dict[str, torch.Tensor]:
    return {key: value.to(device) for key, value in batch.items()}
