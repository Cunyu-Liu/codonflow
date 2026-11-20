#!/usr/bin/env python3
"""Synthetic checks for RK28 production helpers; reads no study outcomes."""
from pathlib import Path
import importlib.util
import json
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

REPO = Path("/home/codonflow-a8-rk")
SCRIPT = REPO / "scripts/a8_rk28_run_sequence_cluster_ood.py"
OUTPUT = REPO / "audits/20261121/RK28/rk28_production_synthetic_v1.json"


def main():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("rk28_production", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checks = []

    def check(name, condition):
        checks.append({"name": name, "pass": bool(condition)})
        if not condition:
            raise AssertionError(name)

    x = np.array([1.0, 1.0, 2.0, 2.0, 3.0])
    y = np.array([1.0, 2.0, 2.0, 3.0, 3.0])
    check("Spearman ties match SciPy", abs(module.spearman(x, y) - spearmanr(x, y).statistic) < 1e-14)
    check("Holm monotone adjusted p", np.allclose(module.holm_adjust([0.01, 0.02, 0.03, 0.04]), [0.04, 0.06, 0.06, 0.06]))
    simple = np.array([1.0, 2.0, 3.0, 4.0])
    structure = np.array([4.0, 3.0, 2.0, 1.0])
    a, b = module.swap_arms(simple, structure, np.array([True, False, True, False]))
    check("cluster arm swap", np.array_equal(a, [4.0, 2.0, 2.0, 4.0]) and np.array_equal(b, [1.0, 3.0, 3.0, 1.0]))
    labels = np.repeat(np.arange(1, 13), [1, 2, 3, 1, 2, 3, 1, 2, 3, 1, 2, 3])
    folds, loads = module.make_cluster_folds(labels, 20261222)
    check("fold sizes sum", sum(loads) == len(labels))
    check("whole-cluster folds", all(np.unique(folds[labels == label]).size == 1 for label in np.unique(labels)))
    check("five nonempty folds", len(np.unique(folds)) == 5 and min(loads) > 0)
    for fold in range(5):
        check(f"fold {fold} cluster disjoint", set(labels[folds == fold]).isdisjoint(set(labels[folds != fold])))

    rng = np.random.default_rng(7)
    train = pd.DataFrame({"x1": rng.normal(size=60), "x2": rng.normal(size=60)})
    train["target"] = 2.0 + 3.0 * train["x1"] - 0.5 * train["x2"]
    test = pd.DataFrame({"x1": rng.normal(size=12), "x2": rng.normal(size=12)})
    test["target"] = 2.0 + 3.0 * test["x1"] - 0.5 * test["x2"]
    prediction = module.fit_predict("ridge", ["x1", "x2"], train, test, 1)
    check("ridge finite", np.isfinite(prediction).all())
    check("ridge learns synthetic relation", np.max(np.abs(prediction - test["target"].to_numpy())) < 0.25)
    check("ridge L2 shrinkage remains highly ranked", module.spearman(prediction, test["target"].to_numpy()) > 0.999)

    n_clusters, per_cluster = 10, 4
    n = n_clusters * per_cluster
    rng = np.random.default_rng(20261222)
    target = rng.normal(size=n)
    synthetic = pd.DataFrame({
        "target": target,
        "ridge_simple": target + rng.normal(scale=0.8, size=n),
        "ridge_structure": target.copy(),
        "histgb_simple": target + rng.normal(scale=0.8, size=n),
        "histgb_structure": target.copy(),
    })
    cluster_ids = np.repeat(np.arange(n_clusters), per_cluster)
    results, arrays = module.primary_inference(synthetic, cluster_ids, 20261323, 20261324, 128)
    check("four synthetic primary tests", len(results) == 4)
    check("all synthetic effects positive", all(row["observed_effect"] > 0 for row in results))
    check("synthetic arrays finite", all(np.isfinite(value).all() for key, value in arrays.items() if key.startswith("bootstrap__") or key.startswith("permutation__")))
    check("synthetic bootstrap shape", arrays["bootstrap_cluster_indices"].shape == (128, n_clusters))
    check("synthetic permutation shape", arrays["permutation_cluster_signs"].shape == (128, n_clusters))
    check("synthetic Holm present", all(0 <= row["p_holm"] <= 1 for row in results))
    payload = {"schema": "a8-rk28-production-synthetic-v1", "status": "PASS", "checks": checks, "passed": len(checks), "failed": 0, "study_outcomes_read": False, "model_fit_on_study_data": False}
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "PASS", "checks": len(checks), "study_outcomes_read": False}, indent=2))


if __name__ == "__main__":
    main()
