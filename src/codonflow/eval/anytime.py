"""Frozen reference domains and anytime multi-objective evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np

from .metrics import hypervolume


def _matrix(points: Iterable[Iterable[float]]) -> np.ndarray:
    values = np.asarray(list(points), dtype=float)
    if values.ndim != 2 or values.shape[0] == 0 or values.shape[1] == 0:
        raise ValueError("objective matrix must be nonempty and two-dimensional")
    if not np.isfinite(values).all():
        raise ValueError("objective matrix contains NaN or infinity")
    return values


@dataclass(frozen=True)
class FrozenReference:
    reference: np.ndarray
    scale: np.ndarray

    @classmethod
    def from_calibration(
        cls,
        points: Iterable[Iterable[float]],
        margin: float = 0.05,
        upper_quantile: float = 0.95,
    ) -> "FrozenReference":
        values = _matrix(points)
        if margin < 0 or not 0 < upper_quantile <= 1:
            raise ValueError("invalid reference calibration parameters")
        lower = values.min(axis=0)
        upper = values.max(axis=0)
        scale = np.quantile(values, upper_quantile, axis=0) - lower
        degenerate = np.flatnonzero(scale <= 0).tolist()
        if degenerate:
            raise ValueError(f"degenerate calibration axes: {degenerate}")
        reference = lower - margin * (upper - lower)
        return cls(reference=reference, scale=scale)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Sequence[float]]) -> "FrozenReference":
        reference = np.asarray(payload["reference"], dtype=float)
        scale = np.asarray(payload["scale"], dtype=float)
        if (reference.ndim != 1 or scale.shape != reference.shape
                or not np.isfinite(reference).all() or not np.isfinite(scale).all()
                or np.any(scale <= 0)):
            raise ValueError("invalid frozen reference")
        return cls(reference=reference, scale=scale)

    def normalize(self, points: Iterable[Iterable[float]]) -> np.ndarray:
        values = _matrix(points)
        if values.shape[1] != len(self.reference):
            raise ValueError("objective dimension does not match frozen reference")
        return (values - self.reference) / self.scale

    def to_dict(self) -> dict:
        return {"reference": self.reference.tolist(), "scale": self.scale.tolist()}


def _hypervolume_normalized(points: np.ndarray) -> float:
    if not len(points):
        return 0.0
    dimensions = points.shape[1]
    if dimensions == 1:
        return float(max(0.0, points[:, 0].max()))
    if dimensions == 2:
        clipped = points[np.all(points >= 0, axis=1)]
        if not len(clipped):
            return 0.0
        clipped = np.unique(clipped, axis=0)
        xs = np.sort(np.unique(clipped[:, 0]))[::-1]
        area = 0.0
        for index, x_value in enumerate(xs):
            left = xs[index + 1] if index + 1 < len(xs) else 0.0
            height = clipped[clipped[:, 0] >= x_value, 1].max()
            area += (x_value - left) * max(0.0, height)
        return float(area)
    return float(hypervolume(points.tolist(), np.zeros(dimensions)))


def anytime_curve(
    records: Iterable[Mapping],
    frozen: FrozenReference,
    budgets: Sequence[int] = (50, 100, 500),
) -> dict:
    ordered_budgets = [int(value) for value in budgets]
    if (not ordered_budgets or ordered_budgets[0] <= 0
            or ordered_budgets != sorted(set(ordered_budgets))):
        raise ValueError("budgets must be unique, positive and increasing")
    points = []
    seen_budgets = set()
    for record in records:
        budget = int(record["budget"])
        if budget <= 0 or budget in seen_budgets:
            raise ValueError("each scored sequence must have one unique positive budget")
        seen_budgets.add(budget)
        objectives = np.asarray(record["objectives"], dtype=float)
        if objectives.ndim != 1 or not np.isfinite(objectives).all():
            raise ValueError("invalid objective vector")
        points.append((budget, objectives))
    points.sort(key=lambda row: row[0])
    curve = []
    for budget in ordered_budgets:
        selected = [objectives for spent, objectives in points if spent <= budget]
        if selected:
            normalized = frozen.normalize(selected)
            value = _hypervolume_normalized(normalized)
        else:
            value = 0.0
        curve.append({"budget": budget, "hv": float(value), "n_scored": len(selected)})
    area = 0.0
    previous_budget, previous_hv = 0, 0.0
    for row in curve:
        area += (row["budget"] - previous_budget) * (previous_hv + row["hv"]) / 2
        previous_budget, previous_hv = row["budget"], row["hv"]
    return {
        "curve": curve,
        "area": float(area),
        "auc": float(area / ordered_budgets[-1]),
        "reference": frozen.to_dict(),
    }


def dense_budget_step_auc_v2(
    records: Iterable[Mapping],
    frozen: FrozenReference,
    max_budget: int = 500,
) -> dict:
    """Dense anytime AUC over real scorer budgets 1..``max_budget - 1``.

    Unlike :func:`anytime_curve`, this metric never inserts a synthetic origin,
    uses no trapezoid integration and does not impute missing budgets.  A dense
    trajectory must contain exactly one finite objective vector at every integer
    budget from 1 through ``max_budget``; otherwise the trajectory is invalid.
    The B=max_budget point is returned for endpoint comparisons but is excluded
    from the AUC sum, matching sum(HV_b for b=1..Bmax-1)/(Bmax-1).
    """
    if isinstance(max_budget, bool) or not isinstance(max_budget, int) or max_budget < 2:
        raise ValueError("max_budget must be an integer >= 2")

    points = []
    seen_budgets = set()
    for record in records:
        raw_budget = record["budget"]
        if isinstance(raw_budget, bool) or not isinstance(raw_budget, int):
            raise ValueError("dense budgets must be integer real-scorer positions")
        budget = raw_budget
        if budget <= 0 or budget > max_budget:
            raise ValueError("dense budgets must lie in 1..max_budget")
        if budget in seen_budgets:
            raise ValueError(f"duplicate dense scorer budget: {budget}")
        seen_budgets.add(budget)
        objectives = np.asarray(record["objectives"], dtype=float)
        if objectives.ndim != 1 or not np.isfinite(objectives).all():
            raise ValueError("invalid objective vector")
        points.append((budget, objectives))

    missing = sorted(set(range(1, max_budget + 1)) - seen_budgets)
    if missing:
        preview = missing[:20]
        suffix = "..." if len(missing) > 20 else ""
        raise ValueError(
            f"dense trajectory has {len(missing)} missing real-scorer budgets: "
            f"{preview}{suffix}; missing budgets are not zero-filled"
        )

    points_by_budget = dict(points)
    selected = []
    curve = []
    for budget in range(1, max_budget + 1):
        selected.append(points_by_budget[budget])
        normalized = frozen.normalize(selected)
        curve.append({
            "budget": budget,
            "hv": float(_hypervolume_normalized(normalized)),
            "n_scored": len(selected),
            "used_in_auc": budget < max_budget,
        })

    area = float(sum(row["hv"] for row in curve if row["used_in_auc"]))
    denominator = max_budget - 1
    return {
        "metric": "dense_budget_step_auc_v2",
        "curve": curve,
        "area": area,
        "auc": float(area / denominator),
        "denominator": denominator,
        "auc_budget_start": 1,
        "auc_budget_end": max_budget - 1,
        "endpoint_budget": max_budget,
        "endpoint_hv": curve[-1]["hv"],
        "synthetic_origin_added": False,
        "missing_budgets_zero_filled": False,
        "reference": frozen.to_dict(),
    }
