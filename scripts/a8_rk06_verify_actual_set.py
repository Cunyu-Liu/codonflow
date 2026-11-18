#!/usr/bin/env python3
"""Verify a real A8 actual-set rescore against original and A7 raw outputs."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from codonflow.eval.actual_set import summarize_actual_set
from codonflow.eval.anytime import FrozenReference
from codonflow.core.codon import split_codons


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--actual", required=True)
    parser.add_argument("--legacy", required=True)
    parser.add_argument("--original", required=True)
    parser.add_argument("--expected-scorer-commit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    actual = json.loads(Path(args.actual).read_text())
    legacy = json.loads(Path(args.legacy).read_text())
    original = json.loads(Path(args.original).read_text())
    checks = []

    def record(name, passed, observed):
        checks.append({"check": name, "pass": bool(passed), "observed": observed})

    record("protocol_and_identity", actual["protocol"] == "a8_rk06_actual_set_v1" and actual["record_id"] == legacy["record_id"] == original["record_id"] and actual["seed"] == legacy["seed"] == original["seed"], {"protocol": actual["protocol"], "record_id": actual["record_id"], "seed": actual["seed"]})
    record("fixed_clean_scorer", actual["scorer_code_commit"] == args.expected_scorer_commit and actual["scorer_code_dirty"] is False, {"commit": actual["scorer_code_commit"], "dirty": actual["scorer_code_dirty"]})
    record("method_coverage", set(actual["methods"]) == set(legacy["methods"]) == set(original["methods"]), sorted(actual["methods"]))
    record("raw_not_stored_objectives", actual["objectives_recomputed_from_raw_sequences"] is True and actual["stored_objectives_used_for_scoring"] is False, True)

    method_summaries = {}
    for name in sorted(actual["methods"]):
        current = actual["methods"][name]
        old = legacy["methods"][name]
        source = original["methods"][name]
        if current["status"] != "done":
            method_summaries[name] = {"status": current["status"]}
            continue
        sequences = [point["sequence"] for point in current["points"]]
        legacy_sequences = [point["sequence"] for point in old["points"]]
        original_sequences = source["solutions"]
        recomputed = np.asarray([point["objectives"] for point in current["points"]], dtype=float)
        previous = np.asarray([point["objectives"] for point in old["points"]], dtype=float)
        max_difference = float(np.max(np.abs(recomputed - previous))) if recomputed.shape == previous.shape else None
        original_reported = np.asarray(source["obj_vectors"], dtype=float)
        # Legacy A6 stored raw motif counts; RK06/A7 store per-codon motif penalty.
        original_reconciled = recomputed.copy()
        original_reconciled[:, 3] *= np.asarray([len(split_codons(seq)) for seq in sequences], dtype=float)
        max_original_reconciled_difference = float(np.max(np.abs(original_reconciled - original_reported)))
        frozen = FrozenReference.from_dict(current["actual_set"]["reference"])
        repeat = summarize_actual_set(current["points"], frozen)

        method_checks = {
            "counts": current["n_unique"] == old["n_unique"] == source["n_unique"] == len(sequences),
            "sequences_exact": sequences == legacy_sequences == original_sequences,
            "objectives_repeat_a7": max_difference is not None and max_difference <= 1e-9,
            "objectives_reconcile_original_reported": max_original_reconciled_difference <= 1e-9,
            "dense_metrics_null": current["dense_budget_step_auc_v2"] is None and current["actual_set"]["dense_budget_step_auc_v2"] is None and current["actual_set"]["curve"] is None and current["actual_set"]["area"] is None,
            "actual_set_repeat": math.isclose(repeat["hypervolume_normalized"], current["actual_set"]["hypervolume_normalized"], rel_tol=0.0, abs_tol=1e-12) and repeat["n_pareto_points"] == current["actual_set"]["n_pareto_points"],
            "identity_and_finite_hv": current["identity_rate"] == 1.0 and math.isfinite(current["actual_set"]["hypervolume_normalized"]) and current["actual_set"]["hypervolume_normalized"] >= 0.0,
            "legacy_cost_preserved": current["legacy_generation_costs"]["generation_seconds"] == source.get("elapsed_s") and current["legacy_generation_costs"]["wall_clock_seconds"] is None,
        }
        for suffix, passed in method_checks.items():
            record(f"{name}.{suffix}", passed, True if passed else False)
        method_summaries[name] = {
            "status": "PASS" if all(method_checks.values()) else "FAIL",
            "n_actual_outputs": current["actual_set"]["n_actual_outputs"],
            "n_unique_objective_vectors": current["actual_set"]["n_unique_objective_vectors"],
            "n_pareto_points": current["actual_set"]["n_pareto_points"],
            "hypervolume_normalized": current["actual_set"]["hypervolume_normalized"],
            "max_abs_difference_vs_a7_recompute": max_difference,
            "max_abs_difference_vs_original_reported": current["max_abs_reported_objective_difference"],
            "max_abs_difference_vs_original_reconciled": max_original_reconciled_difference,
            "original_motif_scale_reconciled": "legacy raw count = RK06 per-codon penalty * n_codons",
            "dense_budget_step_auc_v2": None,
            "checks": method_checks,
        }

    report = {
        "audit_id": f"rk06_real_actual_set_{actual['record_id'].replace('.', '_')}_s{actual['seed']}_v2",
        "status": "PASS" if all(row["pass"] for row in checks) else "FAIL",
        "scope": "one frozen external record; independent raw-CDS recompute and cross-run consistency; not a method ranking or SOTA result",
        "record_id": actual["record_id"],
        "seed": actual["seed"],
        "actual_sha256": sha256(args.actual),
        "legacy_sha256": sha256(args.legacy),
        "original_sha256": sha256(args.original),
        "scorer_code_commit": actual["scorer_code_commit"],
        "scorer_code_dirty": actual["scorer_code_dirty"],
        "reanalysis_elapsed_s_not_generation_cost": actual["reanalysis_elapsed_s_not_generation_cost"],
        "methods": method_summaries,
        "n_checks": len(checks),
        "n_passed": sum(row["pass"] for row in checks),
        "checks": checks,
        "not_a_method_ranking": True,
        "scientific_gate_passed": False,
        "model_improvement_claim": False,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "n_passed": report["n_passed"], "n_checks": report["n_checks"], "methods": {name: row.get("status") for name, row in method_summaries.items()}}))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
