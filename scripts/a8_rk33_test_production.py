#!/usr/bin/env python3
"""Synthetic/unit gates for RK33 production utilities; no research outcomes used."""
from pathlib import Path
import argparse
import json
import math

import numpy as np
import pandas as pd

import a8_rk02_mordstein_structure_increment as rk02
import a8_rk33_run_local_coverage as production


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    checks = []
    def check(name, condition, details=None):
        checks.append({"name": name, "pass": bool(condition), "details": details})

    sequence = "ATG" + "".join(np.random.default_rng(33).choice(list("ACGT"), size=297))
    observed = production.local42_mfe(sequence)
    md = rk02.RNA.md(); md.dangles = 0; md.temperature = 37.0
    expected = float(rk02.RNA.fold_compound(sequence[:42].replace("T", "U"), md).mfe()[1])
    check("local42_exact_slice_and_vienna", observed == expected, {"observed": observed, "expected": expected, "length": 42})
    check("local42_finite", math.isfinite(observed) and abs(observed) < 100000, observed)

    adjusted = production.holm([0.01, 0.02, 0.03])
    check("holm_monotonic_running_max", np.allclose(adjusted, [0.03, 0.04, 0.04]), adjusted.tolist())
    check("test_order_12_unique", len(production.TEST_ORDER) == 12 and len(set(production.TEST_ORDER)) == 12, production.TEST_ORDER)

    rng = np.random.default_rng(3301)
    n = 152
    frame = pd.DataFrame({"seed": 20261222, "target": rng.normal(size=n), "sequence_cluster_id": np.arange(n) % 74 + 1})
    for arm in production.ARMS:
        frame[arm] = frame["target"] + rng.normal(scale=0.5, size=n)
    metrics, effects = production.effect_names_for_seed(frame, 20261222)
    check("eight_absolute_arms", len(metrics) == 8 and {row["arm"] for row in metrics} == set(production.ARMS), len(metrics))
    check("twelve_seed_effects", list(effects) == production.TEST_ORDER and np.isfinite(list(effects.values())).all(), len(effects))
    check("spearman_sign_convention", np.isclose(effects["local42_vs_simple__ridge_spearman_effect"], production.spearman(frame["target"], frame["ridge_local42"]) - production.spearman(frame["target"], frame["ridge_simple"])), effects["local42_vs_simple__ridge_spearman_effect"])
    expected_mse = np.mean((frame["target"] - frame["ridge_simple"]) ** 2 - (frame["target"] - frame["ridge_local42"]) ** 2)
    check("mse_sign_convention", np.isclose(effects["local42_vs_simple__ridge_mse_improvement"], expected_mse), expected_mse)

    tests, arrays = production.primary_inference(frame, 64, 20261323, 20261324)
    check("inference_12_rows", len(tests) == 12 and [row["test"] for row in tests] == production.TEST_ORDER, len(tests))
    check("inference_finite", all(np.isfinite([row["observed_effect"], *row["ci95"], row["p_cluster_swap"], row["p_holm"]]).all() for row in tests), True)
    check("bootstrap_array_shapes", arrays["bootstrap_cluster_indices"].shape == (64, 74) and all(arrays[f"bootstrap__{name}"].shape == (64,) for name in production.TEST_ORDER), arrays["bootstrap_cluster_indices"].shape)
    check("permutation_array_shapes", arrays["permutation_cluster_signs"].shape == (64, 74) and set(np.unique(arrays["permutation_cluster_signs"])) <= {-1, 1}, arrays["permutation_cluster_signs"].shape)
    check("p_value_bounds", all(0 < row["p_cluster_swap"] <= 1 and 0 < row["p_holm"] <= 1 for row in tests), True)

    check("conclusion_all12", production.conclusion_for({name: True for name in production.FAMILIES}) == "LOCAL42_INCREMENT_AND_FULL_STRUCTURE_SUPERIORITY_SUPPORTED_RETROSPECTIVELY", True)
    check("conclusion_simple_only", production.conclusion_for({"local42_vs_simple": True, "local42_vs_full1": False, "local42_vs_full3": True}) == "LOCAL42_INCREMENT_SUPPORTED_BUT_FULL_STRUCTURE_SUPERIORITY_NOT_ESTABLISHED", True)
    check("conclusion_simple_fail", production.conclusion_for({"local42_vs_simple": False, "local42_vs_full1": True, "local42_vs_full3": True}) == "LOCAL42_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED", True)
    source = Path(production.__file__).read_text()
    check("new_fit_arms_frozen", '"local42": simple + protocol["models"]["feature_sets"]["local42_addition"]' in source and '"full1": simple + protocol["models"]["feature_sets"]["full1_addition"]' in source and '"full3": simple +' not in source, True)
    check("no_functional_untouched_access", "untouched" not in source.lower().replace("functional_untouched_read", ""), True)

    report = {"schema": "a8-rk33-production-synthetic-v1", "status": "PASS" if all(row["pass"] for row in checks) else "FAIL", "checks": checks, "checks_passed": sum(row["pass"] for row in checks), "checks_total": len(checks), "research_outcome_used": False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": f'{report["checks_passed"]}/{report["checks_total"]}', "report": str(args.report)}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
