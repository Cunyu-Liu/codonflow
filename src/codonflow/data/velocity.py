"""Compact per-codon velocity-proxy records for the RK08 mechanism study.

The on-disk JSONL representation stores one record per transcript and uses null
for unobserved/masked codon targets. It avoids repeating the CDS on every long-
format row. Targets are occupancy-derived proxies, not physical velocity assays.
"""
from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
from typing import Collection, List, Optional

from .ribokinetic import VariantRecord


def dataset_of(record: VariantRecord) -> str:
    """Return the fixed RiboMIMO study prefix from a record identifier."""
    if ":" not in record.record_id:
        raise ValueError(f"record_id lacks study prefix: {record.record_id}")
    return record.record_id.split(":", 1)[0]


def read_velocity_jsonl(
    path: str,
    include_splits: Optional[Collection[str]] = None,
    include_datasets: Optional[Collection[str]] = None,
    max_records_per_split: Optional[int] = None,
) -> List[VariantRecord]:
    """Read compact velocity records without silently dropping invalid rows."""
    records: List[VariantRecord] = []
    split_counts = {}
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            row = json.loads(line)
            split = str(row["split"])
            dataset = str(row["dataset"])
            if include_splits is not None and split not in include_splits:
                continue
            if include_datasets is not None and dataset not in include_datasets:
                continue
            if max_records_per_split is not None and split_counts.get(split, 0) >= max_records_per_split:
                continue
            if row["record_id"] != f"{dataset}:{row['source_record_id']}":
                raise ValueError(f"record/study/source identifier mismatch at line {line_number}")
            raw_targets = row["velocity_target"]
            if len(raw_targets) != len(row["cds"]) // 3:
                raise ValueError(f"target/codon length mismatch at line {line_number}")
            targets = tuple(float("nan") if value is None else float(value) for value in raw_targets)
            if any(math.isinf(value) for value in targets):
                raise ValueError(f"infinite target at line {line_number}")
            record = VariantRecord(
                record_id=row["record_id"],
                cds=row["cds"],
                split=split,
                cluster_id=row["cluster_id"],
                host=row["host"],
                velocity_target=targets,
            )
            if dataset_of(record) != dataset:
                raise ValueError(f"dataset prefix mismatch at line {line_number}")
            records.append(record)
            split_counts[split] = split_counts.get(split, 0) + 1
    if not records:
        raise ValueError("no velocity records loaded")
    return records
