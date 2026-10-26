#!/usr/bin/env python3
"""Summarize paired normalized-S3 comparisons with completeness checks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def paired_deltas(group: dict, model_tags: list[str]) -> list[float]:
    if len(model_tags) != 2 or len(group["models"]) != 2:
        raise ValueError("paired comparison requires exactly two complete model rows")
    base, treatment = group["models"]
    a, b = base["codonflow/hv"], treatment["codonflow/hv"]
    return [100.0 * (b - a) / a if a > 0 else (float("inf") if b > 0 else 0.0)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    if report.get("protocol") != "joint_pooled_reference_v2":
        raise ValueError("report must use complete joint pooled references")
    if report.get("exclusions"):
        raise ValueError("incomplete comparison is diagnostic-only; no verdict permitted")
    deltas = []
    rows = []
    for arm, group in report["arms"].items():
        delta = paired_deltas(group, report["model_tags"])[0]
        deltas.append(delta)
        rows.append({"arm": arm, "delta_pct": delta})
    if not deltas:
        raise ValueError("no complete paired arms")
    # The geometric ratio is computed on normalized HV values, including zero
    # pairs explicitly rather than silently selecting a convenient subset.
    ratios = []
    for arm, group in report["arms"].items():
        base, treatment = group["models"]
        a, b = base["codonflow/hv"], treatment["codonflow/hv"]
        if a <= 0:
            raise ValueError(f"{arm}: zero baseline requires separate non-ratio analysis")
        ratios.append(b / a)
    summary = {
        "protocol": report["protocol"], "model_tags": report["model_tags"],
        "n_arms": len(rows), "rows": rows,
        "geomean_ratio": float(np.exp(np.mean(np.log(ratios)))),
        "median_delta_pct": float(np.median(deltas)),
        "n_positive": sum(d > 0 for d in deltas),
        "n_negative": sum(d < 0 for d in deltas),
        "scope": "legacy exploratory protocol until new data/model protocol is frozen",
    }
    args.out.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
