#!/usr/bin/env python3
"""Independent hand-value audit of the A8 RK-06 dense/actual-set evaluator."""
import argparse
import json
from pathlib import Path

import numpy as np

from codonflow.eval.actual_set import summarize_actual_set
from codonflow.eval.anytime import FrozenReference, anytime_curve, dense_budget_step_auc_v2


def check(name, passed, expected, observed):
    return {"check": name, "pass": bool(passed), "expected": expected, "observed": observed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    ref1 = FrozenReference(reference=np.array([0.0]), scale=np.array([1.0]))
    ref2 = FrozenReference(reference=np.array([0.0, 0.0]), scale=np.array([1.0, 1.0]))
    records = [
        {"budget": 3, "objectives": [2.0]},
        {"budget": 1, "objectives": [1.0]},
        {"budget": 2, "objectives": [3.0]},
    ]
    dense = dense_budget_step_auc_v2(records, ref1, max_budget=3)
    constant = dense_budget_step_auc_v2(
        [{"budget": b, "objectives": [2.0]} for b in range(1, 501)],
        ref1,
        max_budget=500,
    )
    missing_rejected = False
    missing_message = ""
    try:
        dense_budget_step_auc_v2([
            {"budget": 1, "objectives": [1.0]},
            {"budget": 3, "objectives": [2.0]},
        ], ref1, max_budget=3)
    except ValueError as exc:
        missing_rejected = "missing real-scorer budgets" in str(exc)
        missing_message = str(exc)

    actual = summarize_actual_set([
        {"output_id": "a", "objectives": [1.0, 0.0]},
        {"output_id": "b", "objectives": [0.0, 1.0]},
        {"output_id": "c", "objectives": [2.0, 2.0]},
    ], ref2)
    legacy = anytime_curve(records, ref1, budgets=(1, 2, 3))

    checks = [
        check("dense_real_budget_curve", [row["budget"] for row in dense["curve"]] == [1, 2, 3], [1, 2, 3], [row["budget"] for row in dense["curve"]]),
        check("hand_hv_values", [row["hv"] for row in dense["curve"]] == [1.0, 3.0, 3.0], [1.0, 3.0, 3.0], [row["hv"] for row in dense["curve"]]),
        check("hand_auc_formula", dense["area"] == 4.0 and dense["auc"] == 2.0 and dense["denominator"] == 2, {"area": 4.0, "auc": 2.0, "denominator": 2}, {"area": dense["area"], "auc": dense["auc"], "denominator": dense["denominator"]}),
        check("b500_denominator_499", constant["denominator"] == 499 and constant["area"] == 998.0 and constant["auc"] == 2.0, {"denominator": 499, "area": 998.0, "auc": 2.0}, {"denominator": constant["denominator"], "area": constant["area"], "auc": constant["auc"]}),
        check("endpoint_excluded_from_auc", dense["curve"][-1]["used_in_auc"] is False and dense["endpoint_hv"] == 3.0, {"used_in_auc": False, "endpoint_hv": 3.0}, {"used_in_auc": dense["curve"][-1]["used_in_auc"], "endpoint_hv": dense["endpoint_hv"]}),
        check("missing_budget_rejected_not_zero_filled", missing_rejected and dense["missing_budgets_zero_filled"] is False, True, {"rejected": missing_rejected, "message": missing_message}),
        check("no_synthetic_origin", dense["synthetic_origin_added"] is False and dense["curve"][0]["budget"] == 1, True, {"synthetic_origin_added": dense["synthetic_origin_added"], "first_budget": dense["curve"][0]["budget"]}),
        check("actual_set_hand_hv", actual["hypervolume_normalized"] == 4.0 and actual["n_pareto_points"] == 1 and actual["pareto"][0]["record_ids"] == ["c"], {"hv": 4.0, "pareto_ids": ["c"]}, {"hv": actual["hypervolume_normalized"], "pareto_ids": actual["pareto"][0]["record_ids"]}),
        check("actual_set_dense_metrics_null", actual["dense_budget_step_auc_v2"] is None and actual["curve"] is None and actual["area"] is None, True, {"dense_budget_step_auc_v2": actual["dense_budget_step_auc_v2"], "curve": actual["curve"], "area": actual["area"]}),
        check("legacy_sparse_behavior_preserved_not_reused", legacy["curve"][0]["budget"] == 1 and legacy["curve"][0]["hv"] == 1.0 and legacy["area"] == 5.5, {"first_budget": 1, "first_hv": 1.0, "area_with_implicit_origin_trapezoids": 5.5}, {"first_budget": legacy["curve"][0]["budget"], "first_hv": legacy["curve"][0]["hv"], "area_with_implicit_origin_trapezoids": legacy["area"]}),
    ]
    report = {
        "audit_id": "rk06_dense_actual_synthetic_v1",
        "status": "PASS" if all(row["pass"] for row in checks) else "FAIL",
        "scope": "synthetic evaluator verification only; no model or baseline performance evaluated",
        "formula": "sum(HV_b for b=1..Bmax-1)/(Bmax-1)",
        "checks": checks,
        "n_checks": len(checks),
        "n_passed": sum(row["pass"] for row in checks),
        "model_results_evaluated": False,
        "untouched_functional_data_used": False,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "n_passed": report["n_passed"], "n_checks": report["n_checks"], "output": str(output)}))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
