"""Actual-output-set evaluation without fabricated optimization trajectories."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

import numpy as np

from .anytime import FrozenReference, _hypervolume_normalized, _matrix


def summarize_actual_set(
    records: Iterable[Mapping],
    frozen: FrozenReference,
) -> dict:
    """Evaluate only the outputs that really exist.

    External DP/beam/one-shot methods often provide a finite actual set rather
    than one observation at every scorer budget.  This function reports the
    actual-set Pareto front and hypervolume and explicitly leaves dense AUC and
    the anytime curve null.  It never pads requests, synthesizes budgets or
    turns duplicate objective vectors into extra Pareto points.
    """
    rows = list(records)
    if not rows:
        raise ValueError("actual output set must be nonempty")
    record_ids = []
    for index, record in enumerate(rows):
        record_id = str(record.get("output_id", f"row_{index}"))
        record_ids.append(record_id)
    if len(set(record_ids)) != len(record_ids):
        raise ValueError("actual output IDs must be unique")

    values = _matrix(record["objectives"] for record in rows)
    normalized = frozen.normalize(values)
    groups = defaultdict(list)
    representatives = {}
    for index, vector in enumerate(normalized):
        key = tuple(float(value) for value in vector)
        groups[key].append(record_ids[index])
        representatives.setdefault(key, index)

    unique_indices = list(representatives.values())
    unique_values = normalized[unique_indices]
    pareto_indices = []
    for candidate in range(len(unique_indices)):
        point = unique_values[candidate]
        dominated = False
        for other in range(len(unique_indices)):
            if other == candidate:
                continue
            competitor = unique_values[other]
            if np.all(competitor >= point) and np.any(competitor > point):
                dominated = True
                break
        if not dominated:
            pareto_indices.append(candidate)

    pareto = []
    for unique_index in pareto_indices:
        source_index = unique_indices[unique_index]
        key = tuple(float(value) for value in normalized[source_index])
        pareto.append({
            "record_ids": groups[key],
            "objectives": values[source_index].tolist(),
            "normalized_objectives": normalized[source_index].tolist(),
        })

    return {
        "evaluation_mode": "actual_set_only",
        "n_actual_outputs": len(rows),
        "n_unique_objective_vectors": len(unique_indices),
        "n_pareto_points": len(pareto),
        "pareto": pareto,
        "hypervolume_normalized": float(_hypervolume_normalized(normalized)),
        "curve": None,
        "area": None,
        "dense_budget_step_auc_v2": None,
        "dense_auc_unavailable_reason": "no_real_dense_budget_trajectory",
        "synthetic_origin_added": False,
        "missing_budgets_zero_filled": False,
        "reference": frozen.to_dict(),
    }
