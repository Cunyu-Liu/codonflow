#!/usr/bin/env python3
"""Post-hoc support/depth robustness for the finalized observed-end associations."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

from scripts.a8_rk02_mordstein_proxy_diagnostics import association, correlation, sha256, write_json


def bootstrap_only(x: np.ndarray, y: np.ndarray, seed: int, B: int) -> dict:
    observed = correlation("spearman", x, y)
    rng = np.random.default_rng(seed)
    values = np.empty(B)
    for index in range(B):
        take = rng.integers(0, len(x), size=len(x))
        values[index] = correlation("spearman", x[take], y[take])
    if not np.isfinite(values).all():
        raise RuntimeError("non-finite support bootstrap")
    return {"observed": observed, "ci95_percentile": [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))], "seed": seed, "bootstrap_resamples": B}


def partial_rank(x: np.ndarray, y: np.ndarray, depth: np.ndarray) -> float:
    xr, yr, dr = rankdata(x), rankdata(y), rankdata(depth)
    design = np.column_stack([np.ones(len(dr)), dr])
    x_residual = xr - design @ np.linalg.lstsq(design, xr, rcond=None)[0]
    y_residual = yr - design @ np.linalg.lstsq(design, yr, rcond=None)[0]
    return float(np.corrcoef(x_residual, y_residual)[0, 1])


def partial_bootstrap(x: np.ndarray, y: np.ndarray, depth: np.ndarray, seed: int, B: int) -> dict:
    observed = partial_rank(x, y, depth)
    rng = np.random.default_rng(seed)
    values = np.empty(B)
    for index in range(B):
        take = rng.integers(0, len(x), size=len(x))
        values[index] = partial_rank(x[take], y[take], depth[take])
    if not np.isfinite(values).all():
        raise RuntimeError("non-finite partial bootstrap")
    return {"observed": observed, "ci95_percentile": [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))], "seed": seed, "bootstrap_resamples": B}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    repo = args.repo.resolve()
    protocol_path = args.protocol.resolve()
    protocol = json.loads(protocol_path.read_text())
    primary_path = repo / protocol["primary_production"]
    primary = json.loads(primary_path.read_text())
    independent_path = repo / protocol["primary_independent"]
    finalization_path = repo / protocol["primary_finalization"]
    independent = json.loads(independent_path.read_text())
    finalization = json.loads(finalization_path.read_text())
    if independent["status"] != "PASS" or finalization["status"] != "PASS":
        raise RuntimeError("primary analysis is not finalized")
    if finalization["production_sha256"] != sha256(primary_path) or finalization["independent_sha256"] != sha256(independent_path):
        raise RuntimeError("primary hash binding failed")
    rows = primary["variant_metrics"]
    y_all = np.asarray([r["flowseq_score_r1_only"] for r in rows])
    depth_all = np.asarray([r["total_assigned_reads"] for r in rows], dtype=float)
    B = int(protocol["bootstrap_resamples"])
    stride = int(protocol["seed_stride"])
    base = int(protocol["seed"])
    support = []
    for threshold_index, threshold in enumerate(protocol["support_thresholds"]):
        keep = depth_all >= threshold
        n = int(keep.sum())
        if n < 20:
            raise RuntimeError(f"support stratum too small: {threshold} n={n}")
        y = y_all[keep]
        item = {"threshold": int(threshold), "n": n, "features": {}}
        for feature_index, feature in enumerate(protocol["features"]):
            x = np.asarray([r[feature] for r in rows])[keep]
            seed = base + threshold_index * stride + feature_index * 10000
            item["features"][feature] = bootstrap_only(x, y, seed, B)
        support.append(item)
    log_depth = np.log10(depth_all)
    depth = {}
    depth_items = [("flowseq_score_r1_only", y_all), *[(feature, np.asarray([r[feature] for r in rows])) for feature in protocol["features"]]]
    for index, (name, values) in enumerate(depth_items):
        seed = base + 7 * stride + index * 10000
        depth[name] = association(log_depth, values, "spearman", seed, B)
    partial = {}
    for feature_index, feature in enumerate(protocol["features"]):
        x = np.asarray([r[feature] for r in rows])
        partial[feature] = partial_bootstrap(x, y_all, depth_all, base + 10 * stride + feature_index * 10000, B)
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"], text=True).strip()
    payload = {
        "schema": "a8.rk02.mordstein_proxy_robustness.v1",
        "status": "PASS_PENDING_INDEPENDENT_VERIFICATION",
        "analysis_status": protocol["analysis_status"],
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sha256(protocol_path),
        "primary_production_sha256": sha256(primary_path),
        "primary_independent_sha256": sha256(independent_path),
        "primary_finalization_sha256": sha256(finalization_path),
        "code_commit": commit,
        "tracked_tree_clean_at_launch": not bool(dirty),
        "support_sensitivity": support,
        "depth_associations": depth,
        "partial_spearman_controlling_depth": partial,
        "positive_ci_all_thresholds": {
            feature: all(item["features"][feature]["ci95_percentile"][0] > 0 for item in support)
            for feature in protocol["features"]
        },
        "boundaries": protocol["boundaries"],
        "wall_elapsed_s": time.perf_counter() - started,
    }
    output = repo / protocol["output"]["production"]
    write_json(output, payload)
    print(json.dumps({"status": payload["status"], "positive_ci_all_thresholds": payload["positive_ci_all_thresholds"], "wall_s": payload["wall_elapsed_s"]}))


if __name__ == "__main__":
    main()
