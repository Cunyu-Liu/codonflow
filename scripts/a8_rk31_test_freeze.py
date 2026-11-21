#!/usr/bin/env python3
"""Label-free synthetic gates and preexperiment freeze for RK31."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import a8_rk28_run_sequence_cluster_ood as rk28
import a8_rk31_run_known_context_applicability as rk31


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def synthetic_frame(n: int = 90) -> pd.DataFrame:
    rng = np.random.default_rng(731)
    frame = pd.DataFrame({"variant_id": [f"v{i:03d}" for i in range(n)],
                          "sequence_cluster_id": np.arange(n) % 30})
    for name in ["gc3_observed_5prime", "gc_observed_5prime", "cpg_per_100nt_observed_5prime",
                 "cai_human_def_refs_observed_r1", "mfe_observed_r1_full_kcal_mol",
                 "mfe_observed_r1_window48_min_kcal_mol", "mfe_observed_r1_window48_mean_kcal_mol"]:
        frame[name] = rng.normal(size=n)
    slopes = {"hela_no_intron": 0.0, "hela_with_intron": 1.4, "hek293_no_intron": -1.1}
    for context, slope in slopes.items():
        frame[f"target__{context}"] = (0.7 * frame["gc3_observed_5prime"] +
                                       slope * frame["mfe_observed_r1_full_kcal_mol"] +
                                       rng.normal(scale=0.08, size=n))
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--base-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    checks = []

    def record(name: str, condition: bool, evidence=None) -> None:
        checks.append({"check": name, "pass": bool(condition), "evidence": evidence})
        if not condition:
            raise AssertionError(name)

    record("protocol_schema", protocol.get("schema") == "a8-rk31-known-context-applicability-protocol-v1")
    record("retrospective_boundary", protocol.get("evidence_status") == "retrospective_outcome_known_followup_not_independent_confirmation")
    record("primary_contract", protocol["primary_comparisons"]["expected_endpoints"] == 24 and
           len(protocol["primary_comparisons"]["baselines"]) == 4)
    record("fit_contract", protocol["outer_evaluation"]["expected_ridge_fits"] == 450 and
           protocol["outer_evaluation"]["fits_per_seed"] == 45)
    for key, item in protocol["inputs"].items():
        record(f"input_hash_{key}", sha256(Path(item["path"])) == item["sha256"])
    record("artifact_root_absent", not Path(protocol["execution"]["artifact_root"]).exists(),
           protocol["execution"]["artifact_root"])

    frame = synthetic_frame()
    contexts = protocol["contexts"]
    nonreference = [c for c in contexts if c != protocol["reference_context"]]
    long = rk31.make_long(frame, contexts, nonreference)
    interacted = rk31.add_interactions(long, protocol)
    record("long_shape", len(long) == 3 * len(frame) and long["target"].notna().all())
    record("indicator_reference_zero", all(long.loc[long["context"] == protocol["reference_context"],
                                                    f"context__{c}"].eq(0).all() for c in nonreference))
    expected = long["context__hela_with_intron"].to_numpy(float) * long["mfe_observed_r1_full_kcal_mol"].to_numpy(float)
    record("interaction_exact", np.array_equal(interacted["context__hela_with_intron__x__mfe_observed_r1_full_kcal_mol"].to_numpy(float), expected))
    expected_widths = {"shared_simple": 6, "shared_full": 9, "context_gated_full": 15,
                       "no_transport_simple": 4, "no_transport_full": 7}
    record("feature_widths", {arm: len(rk31.feature_names(protocol, arm)) for arm in expected_widths} == expected_widths,
           {arm: len(rk31.feature_names(protocol, arm)) for arm in expected_widths})

    leakage_free = True
    fold_sizes = []
    for seed in protocol["outer_evaluation"]["sensitivity_seeds"]:
        folds, loads = rk28.make_cluster_folds(frame["sequence_cluster_id"].to_numpy(int), seed)
        fold_sizes.append(loads)
        for fold in range(5):
            leakage_free &= not bool(set(frame.loc[folds != fold, "sequence_cluster_id"]) &
                                     set(frame.loc[folds == fold, "sequence_cluster_id"]))
    record("whole_cluster_folds", leakage_free and len(fold_sizes) == 10, fold_sizes)

    train = frame.loc[frame["sequence_cluster_id"] % 5 != 0].copy()
    test = frame.loc[frame["sequence_cluster_id"] % 5 == 0].copy()
    train_long = rk31.add_interactions(rk31.make_long(train, contexts, nonreference), protocol)
    test_long = rk31.add_interactions(rk31.make_long(test, contexts, nonreference), protocol)
    predictions = {}
    for arm in ["shared_simple", "shared_full", "context_gated_full"]:
        predictions[arm] = rk28.fit_predict("ridge", rk31.feature_names(protocol, arm), train_long, test_long, 731)
        record(f"synthetic_fit_{arm}", np.isfinite(predictions[arm]).all())
    target = test_long["target"].to_numpy(float)
    mse = {arm: float(np.mean((target - pred) ** 2)) for arm, pred in predictions.items()}
    record("known_context_mechanism_discriminating", mse["context_gated_full"] < mse["shared_full"] and
           mse["context_gated_full"] < mse["shared_simple"], mse)

    primary = test_long.loc[test_long["context"] == "hela_with_intron",
                            ["variant_id", "sequence_cluster_id", "target"]].copy().reset_index(drop=True)
    primary["context_gated_full"] = primary["target"] + 0.01
    primary["shared_full"] = np.random.default_rng(732).normal(size=len(primary))
    cluster_ids = primary["sequence_cluster_id"].to_numpy(int)
    unique = np.array(sorted(np.unique(cluster_ids)))
    cluster_index = np.searchsorted(unique, cluster_ids)
    cluster_rows = [np.flatnonzero(cluster_index == i) for i in range(len(unique))]
    boot = np.random.default_rng(733).integers(0, len(unique), size=(100, len(unique)), dtype=np.int16)
    signs = np.random.default_rng(734).choice(np.array([-1, 1], dtype=np.int8), size=(100, len(unique)))
    result, bootstrap, permutation = rk31.contrast_inference(primary, "shared_full", "mse_improvement",
                                                             cluster_rows, cluster_index, boot, signs)
    record("inference_finite", np.isfinite(bootstrap).all() and np.isfinite(permutation).all() and
           result["observed_effect"] > 0 and 0 < result["p_cluster_swap"] <= 1, result)
    record("holm_24", len(rk31.holm_adjust(np.linspace(0.001, 0.1, 24))) == 24)
    record("no_functional_untouched", protocol["scientific_boundaries"]["functional_untouched_read"] is False)
    record("generator_not_authorized", protocol["scientific_boundaries"]["generator_training_authorized"] is False)

    report = {
        "schema": "a8-rk31-preexperiment-freeze-v1",
        "status": "PASS_RK31_PREEXPERIMENT_FREEZE",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "base_commit": args.base_commit,
        "protocol": str(args.protocol.resolve()),
        "protocol_sha256": sha256(args.protocol),
        "production_script_sha256": sha256(Path(rk31.__file__).resolve()),
        "test_script_sha256": sha256(Path(__file__).resolve()),
        "checks_passed": sum(c["pass"] for c in checks), "checks_total": len(checks), "checks": checks,
        "synthetic_only": True,
        "real_rk31_model_fit_executed": False,
        "real_rk31_metric_readout_executed": False,
        "functional_untouched_read": False,
        "generator_training_authorized": False,
        "git_tracked_dirty_before_freeze": subprocess.run(["git", "diff", "--quiet"], cwd=Path(__file__).resolve().parents[1]).returncode != 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}",
                      "synthetic_mse": mse, "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
