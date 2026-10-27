#!/usr/bin/env python3
"""Recompute S3 HV from complete objective pools without changing solutions.

Paired model comparisons share one reference point per gene and seed. Partial
method pools are reported as exclusions, never silently promoted to verdicts.
The previous S3R2 file is retained; this writes a separate v2 artifact.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from codonflow.eval.metrics import hypervolume  # noqa: E402

DEFAULT_DATA = Path("/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs")
REQUIRED_METHODS = (
    "codonflow", "lineardesign_scan", "codongpt", "gemorna",
    "cai_greedy", "uniform_synonymous",
)
ALIASES = {"uniform_synonymous": ("uniform_synonymous", "uniform_edit_flow")}


def load_rows(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    for rows in data.values():
        if isinstance(rows, list):
            return rows
    raise ValueError(f"{path}: no experiment rows")


def objective_pool(row: dict) -> dict[str, np.ndarray]:
    pool = {}
    for method in REQUIRED_METHODS:
        names = ALIASES.get(method, (method,))
        for name in names:
            key = f"S3_quad/{name}/obj_vectors"
            if key in row:
                pool[method] = np.asarray(row[key], dtype=float)
                break
    return pool


def joint_range_reference(points, allow_degenerate: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Shared min - 5% range reference; optionally handle constant pilot axes."""
    values = np.asarray(points, dtype=float)
    if values.ndim != 2 or not len(values) or not np.isfinite(values).all():
        raise ValueError("joint reference requires a nonempty finite objective matrix")
    scale = np.ptp(values, axis=0)
    if np.any(scale <= 0) and not allow_degenerate:
        raise ValueError("degenerate objective range prevents pooled normalization")
    safe_scale = np.where(scale > 0, scale, 1.0)
    reference = values.min(axis=0) - 0.05 * safe_scale
    reference = np.where(scale > 0, reference, values.min(axis=0) - 1e-6)
    return reference, safe_scale


def pooled_reference(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    pools = [objective_pool(row) for row in rows]
    missing = sorted({
        method for pool in pools for method in REQUIRED_METHODS
        if method not in pool or pool[method].ndim != 2 or pool[method].shape[1] != 4 or not len(pool[method])
    })
    if missing:
        raise ValueError(f"incomplete or malformed S3 method pool: {', '.join(missing)}")
    all_points = np.vstack([points for pool in pools for points in pool.values()])
    if not np.isfinite(all_points).all():
        raise ValueError("objective pool contains NaN or infinity")
    reference, _ = joint_range_reference(all_points)
    scale = np.quantile(all_points, 0.95, axis=0) - all_points.min(axis=0)
    return reference, scale


def normalized_hypervolumes(row: dict, reference: np.ndarray, scale: np.ndarray) -> dict:
    pool = objective_pool(row)
    result = {}
    for method, points in pool.items():
        normalized = (points - reference) / scale
        hv = float(hypervolume(normalized.tolist(), np.zeros(4)))
        result[f"{method}/hv"] = hv
    result["n_solutions"] = {method: len(points) for method, points in pool.items()}
    return result


def recompute_group(rows: list[dict]) -> dict:
    reference, scale = pooled_reference(rows)
    return {
        "reference": reference.tolist(), "scale": scale.tolist(),
        "n_models": len(rows),
        "models": [normalized_hypervolumes(row, reference, scale) for row in rows],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model-tags", nargs="+", required=True,
                        help="e.g. E5_v3_56m E5_v3_355m; paired by gene and seed")
    parser.add_argument("--allow-diagnostic", action="store_true",
                        help="write exclusions but do not fail on incomplete pairs/pools")
    args = parser.parse_args()
    files = {tag: {p.stem: p for p in args.eval_dir.glob(f"{tag}_*_s[0-9].json")}
             for tag in args.model_tags}
    arms = sorted({
        path.stem[len(tag):]
        for tag, paths in files.items() for path in paths.values()
    })
    output, exclusions = {}, []
    for arm in arms:
        paths = [args.eval_dir / f"{tag}{arm}.json" for tag in args.model_tags]
        missing = [path.name for path in paths if not path.exists()]
        if missing:
            exclusions.append({"arm": arm, "reason": f"missing {', '.join(missing)}"})
            continue
        try:
            rows = []
            for path in paths:
                arm_rows = load_rows(path)
                if len(arm_rows) != 1:
                    raise ValueError("expected exactly one gene-seed row")
                rows.append(arm_rows[0])
            output[arm] = recompute_group(rows)
        except ValueError as error:
            exclusions.append({"arm": arm, "reason": str(error)})
    report = {"protocol": "joint_pooled_reference_v2", "model_tags": args.model_tags,
              "arms": output, "exclusions": exclusions}
    if exclusions and not args.allow_diagnostic:
        print(json.dumps(report, indent=2))
        raise SystemExit("incomplete comparison; no verdict written")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps({"complete_arms": len(output), "exclusions": exclusions,
                      "out": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
