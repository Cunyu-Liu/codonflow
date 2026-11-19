#!/usr/bin/env python3
"""Independent recompute of post-hoc support/depth robustness; no production import."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

from scripts.a8_rk02_verify_mordstein_proxy import corr, recompute_association, sha256


def support_recompute(x: np.ndarray, y: np.ndarray, seed: int, B: int) -> dict:
    observed = corr(x, y, "spearman")
    rng = np.random.default_rng(seed)
    values = np.empty(B)
    for index in range(B):
        take = rng.integers(0, len(x), size=len(x))
        values[index] = corr(x[take], y[take], "spearman")
    return {"observed": observed, "ci95_percentile": [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))], "seed": seed, "bootstrap_resamples": B}


def partial_rank(x: np.ndarray, y: np.ndarray, depth: np.ndarray) -> float:
    xr, yr, dr = rankdata(x), rankdata(y), rankdata(depth)
    design = np.column_stack([np.ones(len(dr)), dr])
    xr = xr - design @ np.linalg.lstsq(design, xr, rcond=None)[0]
    yr = yr - design @ np.linalg.lstsq(design, yr, rcond=None)[0]
    return float(np.corrcoef(xr, yr)[0, 1])


def partial_recompute(x: np.ndarray, y: np.ndarray, depth: np.ndarray, seed: int, B: int) -> dict:
    observed = partial_rank(x, y, depth)
    rng = np.random.default_rng(seed)
    values = np.empty(B)
    for index in range(B):
        take = rng.integers(0, len(x), size=len(x))
        values[index] = partial_rank(x[take], y[take], depth[take])
    return {"observed": observed, "ci95_percentile": [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))], "seed": seed, "bootstrap_resamples": B}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    protocol = json.loads(args.protocol.read_text())
    production = json.loads(args.production.read_text())
    primary = json.loads((repo / protocol["primary_production"]).read_text())
    primary_independent_path = repo / protocol["primary_independent"]
    primary_finalization_path = repo / protocol["primary_finalization"]
    primary_independent = json.loads(primary_independent_path.read_text())
    primary_finalization = json.loads(primary_finalization_path.read_text())
    checks = {}
    checks["primary_pass_and_hashes"] = (
        primary_independent["status"] == primary_finalization["status"] == "PASS"
        and production["primary_production_sha256"] == sha256(repo / protocol["primary_production"])
        and production["primary_independent_sha256"] == sha256(primary_independent_path)
        and production["primary_finalization_sha256"] == sha256(primary_finalization_path)
    )
    checks["protocol_hash_and_posthoc_status"] = production["protocol_sha256"] == sha256(args.protocol) and production["analysis_status"] == "POST_HOC_EXPLORATORY_NOT_PRIMARY_NOT_A_NEW_GATE"
    rows = primary["variant_metrics"]
    y_all = np.asarray([r["flowseq_score_r1_only"] for r in rows])
    depth_all = np.asarray([r["total_assigned_reads"] for r in rows], dtype=float)
    B = int(protocol["bootstrap_resamples"])
    stride = int(protocol["seed_stride"])
    base = int(protocol["seed"])
    max_delta = 0.0
    support_ok = True
    for threshold_index, (threshold, saved_item) in enumerate(zip(protocol["support_thresholds"], production["support_sensitivity"])):
        keep = depth_all >= threshold
        support_ok &= saved_item["threshold"] == threshold and saved_item["n"] == int(keep.sum())
        for feature_index, feature in enumerate(protocol["features"]):
            x = np.asarray([r[feature] for r in rows])[keep]
            seed = base + threshold_index * stride + feature_index * 10000
            result = support_recompute(x, y_all[keep], seed, B)
            saved = saved_item["features"][feature]
            support_ok &= saved["seed"] == seed and saved["bootstrap_resamples"] == B
            max_delta = max(max_delta, abs(result["observed"] - saved["observed"]), *(abs(a - b) for a, b in zip(result["ci95_percentile"], saved["ci95_percentile"])))
    checks["seven_support_strata_recompute"] = bool(support_ok and max_delta <= 1e-12)
    support_delta = max_delta
    log_depth = np.log10(depth_all)
    depth_items = [("flowseq_score_r1_only", y_all), *[(feature, np.asarray([r[feature] for r in rows])) for feature in protocol["features"]]]
    depth_ok = True
    for index, (name, values) in enumerate(depth_items):
        seed = base + 7 * stride + index * 10000
        result = recompute_association(log_depth, values, "spearman", seed, B)
        saved = production["depth_associations"][name]
        depth_ok &= saved["seed"] == seed and saved["bootstrap_resamples"] == saved["permutation_resamples"] == B
        max_delta = max(max_delta, abs(result["observed"] - saved["observed"]), abs(result["permutation_p_two_sided"] - saved["permutation_p_two_sided"]), *(abs(a - b) for a, b in zip(result["ci95_percentile"], saved["ci95_percentile"])))
    checks["three_depth_associations_recompute"] = bool(depth_ok and max_delta <= 1e-12)
    partial_ok = True
    for feature_index, feature in enumerate(protocol["features"]):
        x = np.asarray([r[feature] for r in rows])
        seed = base + 10 * stride + feature_index * 10000
        result = partial_recompute(x, y_all, depth_all, seed, B)
        saved = production["partial_spearman_controlling_depth"][feature]
        partial_ok &= saved["seed"] == seed and saved["bootstrap_resamples"] == B
        max_delta = max(max_delta, abs(result["observed"] - saved["observed"]), *(abs(a - b) for a, b in zip(result["ci95_percentile"], saved["ci95_percentile"])))
    checks["two_partial_spearman_recompute"] = bool(partial_ok and max_delta <= 1e-12)
    flags = {feature: all(item["features"][feature]["ci95_percentile"][0] > 0 for item in production["support_sensitivity"]) for feature in protocol["features"]}
    checks["positive_threshold_flags_recompute"] = flags == production["positive_ci_all_thresholds"]
    boundaries = production["boundaries"]
    checks["scope_not_upgraded"] = boundaries == protocol["boundaries"] and boundaries["protein_ood_evaluation"] is False and boundaries["causal_inference"] is False and boundaries["generator_training_authorized"] is False and boundaries["sota_claim"] is False
    checks["finite_resampling_and_population"] = np.isfinite(max_delta) and len(rows) == 152 and len(production["support_sensitivity"]) == 7
    failed = [name for name, passed in checks.items() if not passed]
    payload = {
        "schema": "a8.rk02.mordstein_proxy_robustness_independent.v1",
        "status": "PASS" if not failed else "FAIL",
        "checks_total": len(checks), "checks_passed": len(checks) - len(failed), "checks": checks, "failed_checks": failed,
        "production_sha256": sha256(args.production), "protocol_sha256": sha256(args.protocol),
        "max_abs_delta": max_delta, "support_only_max_abs_delta_before_depth": support_delta,
        "scientific_gate": "POST_HOC_ROBUSTNESS_ONLY_NOT_CAUSAL_NOT_OOD_NOT_SOTA",
    }
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.output)
    print(json.dumps({"status": payload["status"], "checks": f"{payload['checks_passed']}/{payload['checks_total']}", "max_delta": max_delta, "failed": failed}))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
