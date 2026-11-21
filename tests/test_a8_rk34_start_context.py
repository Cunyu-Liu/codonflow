"""RK34 synthetic tests; no research outcome data."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import RNA

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import a8_rk34_run_start_context as production  # noqa: E402


def synthetic_frame(seed=20261221):
    rng = np.random.default_rng(3401)
    n = 150
    frame = pd.DataFrame({
        "seed": seed, "target": rng.normal(size=n),
        "sequence_cluster_id": np.arange(n) % 37 + 1,
        "null": rng.normal(size=n),
    })
    for model in production.MODELS:
        for arm in ["simple"] + production.ARMS:
            frame[f"{model}_{arm}"] = frame["target"] + rng.normal(scale=0.5, size=n)
    return frame


def test_matched_factorial_sequences():
    utr = "ACGU" * 36
    cds = "ATG" + "C" * 35 + "G" * (720 - 38)
    contexts = production.context_sequences(utr, cds)
    assert set(contexts) == set(production.CONTEXTS)
    assert all(len(sequence) == 42 for sequence in contexts.values())
    assert contexts["exact_real"] == "ACGU" + "ATG" + "C" * 35
    assert contexts["start_only"] == "NNNN" + "ATG" + "C" * 35
    assert contexts["upstream_only"] == "ACGU" + "NNN" + "C" * 35
    assert contexts["neither"] == "NNNN" + "NNN" + "C" * 35
    assert contexts["exact_real"][4:] == contexts["start_only"][4:]
    assert contexts["exact_real"][7:] == contexts["upstream_only"][7:]


def test_gc3_uses_third_codon_positions_only():
    gc, gc3 = production.cds_gc_features("ATGCCCGGG")
    assert np.isclose(gc, 7 / 9) and np.isclose(gc3, 1.0)
    gc, gc3 = production.cds_gc_features("AAATTTAAA")
    assert np.isclose(gc, 0.0) and np.isclose(gc3, 0.0)


def test_vienna_exact_and_n_masked_energies():
    utr = "ACGU" * 36
    cds = "ATG" + "".join(np.random.default_rng(34).choice(list("ACGT"), size=717))
    contexts = production.context_sequences(utr, cds)
    for dangles in (0, 2):
        md = RNA.md(); md.dangles = dangles; md.temperature = 37.0
        expected = float(RNA.fold_compound(contexts["exact_real"].replace("T", "U"), md).mfe()[1])
        assert production.mfe(contexts["exact_real"], dangles) == expected
        for context in production.CONTEXTS:
            assert np.isfinite(production.mfe(contexts[context], dangles))


def test_frozen_test_order_and_fit_accounting():
    assert len(production.ARMS) == 8
    assert len([arm for arm in production.ARMS if arm != "exact_real_d2"]) == 7
    assert 10 * 5 * 2 * 7 == 700
    assert 700 + 200 == 900
    assert len(production.TEST_ORDER) == len(set(production.TEST_ORDER)) == 40
    assert sum(name.startswith("primary__") for name in production.TEST_ORDER) == 20
    assert sum(name.startswith("sensitivity_d0__") for name in production.TEST_ORDER) == 20


def test_effect_signs_and_absolute_rows():
    frame = synthetic_frame()
    metrics, effects = production.effect_names_for_seed(frame, 20261221)
    assert len(metrics) == 19 and list(effects) == production.TEST_ORDER
    y = frame["target"].to_numpy(float)
    exact = frame["ridge_exact_real_d2"].to_numpy(float)
    simple = frame["ridge_simple"].to_numpy(float)
    assert np.isclose(effects["primary__ridge__exact_vs_simple__spearman_effect"], production.spearman(y, exact) - production.spearman(y, simple))
    assert np.isclose(effects["primary__ridge__exact_vs_simple__mse_improvement"], np.mean((y - simple) ** 2 - (y - exact) ** 2))
    start = frame["histgb_start_only_d2"].to_numpy(float)
    neither = frame["histgb_neither_d2"].to_numpy(float)
    assert np.isclose(effects["primary__histgb__start_without_upstream__spearman_effect"], production.spearman(y, start) - production.spearman(y, neither))


def test_cluster_inference_shapes_bounds_and_separate_holm():
    tests, arrays = production.run_inference(synthetic_frame(), 32, 20261321, 20261322)
    assert len(tests) == 40
    assert arrays["bootstrap_cluster_indices"].shape == (32, 37)
    assert arrays["permutation_cluster_signs"].shape == (32, 37)
    assert set(np.unique(arrays["permutation_cluster_signs"])) <= {-1, 1}
    assert sum(row["confirmatory"] for row in tests) == 20
    assert all(0 < row["p_cluster_swap"] <= 1 and 0 < row["p_holm"] <= 1 for row in tests)
    for analysis in ("primary", "sensitivity_d0"):
        assert sum(row["analysis"] == analysis for row in tests) == 20


def test_conclusion_requires_both_factorial_families():
    base = {name: False for name in production.FAMILIES}
    assert production.conclusion_for(base) == "NO_EXACT_CONTEXT_INCREMENT_SUPPORTED_RETROSPECTIVELY"
    base["exact_vs_simple"] = True
    assert production.conclusion_for(base) == "JOINT_EXACT_CONTEXT_WITHOUT_SEPARABLE_CONTRIBUTIONS_RETROSPECTIVELY"
    base["upstream_given_start"] = True
    assert production.conclusion_for(base) == "JOINT_EXACT_CONTEXT_WITHOUT_SEPARABLE_CONTRIBUTIONS_RETROSPECTIVELY"
    base["upstream_without_start"] = True
    assert production.conclusion_for(base) == "UPSTREAM_BUT_NOT_START_CONTRIBUTION_SUPPORTED_RETROSPECTIVELY"
    base["start_given_upstream"] = base["start_without_upstream"] = True
    assert production.conclusion_for(base) == "START_AND_UPSTREAM_CONTRIBUTIONS_SUPPORTED_RETROSPECTIVELY"


def test_cluster_fold_isolation_is_deterministic():
    labels = np.arange(150) % 37 + 1
    first, loads = production.make_cluster_folds(labels, 20261221)
    second, second_loads = production.make_cluster_folds(labels, 20261221)
    assert np.array_equal(first, second) and loads == second_loads and len(loads) == 5
    for fold in range(5):
        assert set(labels[first == fold]).isdisjoint(set(labels[first != fold]))


def test_preregistration_retains_scientific_boundaries():
    text = (Path(__file__).resolve().parents[1] / "audits/20261121/RK34/A8_RK34_START_CONTEXT_PREREGISTRATION.md").read_text()
    assert "700 new + 200 accepted reused = 900" in text
    assert "20 confirmatory tests" in text
    assert "cannot upgrade a failed confirmatory result" in text
    assert "Functional untouched data are not read" in text
    assert "RK-G1" in text
