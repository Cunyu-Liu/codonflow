"""RK33 unit tests; synthetic data only, no research outcomes."""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import a8_rk02_mordstein_structure_increment as rk02  # noqa: E402
import a8_rk33_run_local_coverage as production  # noqa: E402


def synthetic_frame():
    rng = np.random.default_rng(3301)
    frame = pd.DataFrame({"seed": 20261222, "target": rng.normal(size=152), "sequence_cluster_id": np.arange(152) % 74 + 1})
    for arm in production.ARMS:
        frame[arm] = frame["target"] + rng.normal(scale=0.5, size=len(frame))
    return frame


def test_local42_exact_slice_and_vienna():
    sequence = "ATG" + "".join(np.random.default_rng(33).choice(list("ACGT"), size=297))
    md = rk02.RNA.md(); md.dangles = 0; md.temperature = 37.0
    expected = float(rk02.RNA.fold_compound(sequence[:42].replace("T", "U"), md).mfe()[1])
    assert production.local42_mfe(sequence) == expected


def test_holm_and_frozen_test_order():
    assert np.allclose(production.holm([0.01, 0.02, 0.03]), [0.03, 0.04, 0.04])
    assert len(production.TEST_ORDER) == len(set(production.TEST_ORDER)) == 12


def test_effect_signs_and_absolute_rows():
    frame = synthetic_frame()
    metrics, effects = production.effect_names_for_seed(frame, 20261222)
    assert len(metrics) == 8 and list(effects) == production.TEST_ORDER
    expected_spearman = production.spearman(frame["target"], frame["ridge_local42"]) - production.spearman(frame["target"], frame["ridge_simple"])
    expected_mse = np.mean((frame["target"] - frame["ridge_simple"]) ** 2 - (frame["target"] - frame["ridge_local42"]) ** 2)
    assert np.isclose(effects["local42_vs_simple__ridge_spearman_effect"], expected_spearman)
    assert np.isclose(effects["local42_vs_simple__ridge_mse_improvement"], expected_mse)


def test_cluster_inference_shapes_and_bounds():
    tests, arrays = production.primary_inference(synthetic_frame(), 32, 20261323, 20261324)
    assert len(tests) == 12
    assert arrays["bootstrap_cluster_indices"].shape == (32, 74)
    assert arrays["permutation_cluster_signs"].shape == (32, 74)
    assert set(np.unique(arrays["permutation_cluster_signs"])) <= {-1, 1}
    assert all(0 < row["p_cluster_swap"] <= 1 and 0 < row["p_holm"] <= 1 for row in tests)


def test_family_conclusion_not_collapsed_to_single_metric():
    assert production.conclusion_for({name: True for name in production.FAMILIES}) == "LOCAL42_INCREMENT_AND_FULL_STRUCTURE_SUPERIORITY_SUPPORTED_RETROSPECTIVELY"
    assert production.conclusion_for({"local42_vs_simple": True, "local42_vs_full1": False, "local42_vs_full3": True}) == "LOCAL42_INCREMENT_SUPPORTED_BUT_FULL_STRUCTURE_SUPERIORITY_NOT_ESTABLISHED"
    assert production.conclusion_for({"local42_vs_simple": False, "local42_vs_full1": True, "local42_vs_full3": True}) == "LOCAL42_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED"


def test_protocol_preserves_start_aware_boundary():
    protocol = json.loads((Path(__file__).resolve().parents[1] / "audits/20261121/RK33/a8_rk33_local_coverage_protocol_v1.json").read_text())
    assert protocol["coverage"]["local_coordinates"] == "CDS_4_45"
    assert protocol["models"]["new_model_fits"] == 200
    assert protocol["primary_inference"]["total_tests"] == 12
    assert not protocol["scientific_boundaries"]["exact_kudla_start_aware_transport"]
    assert not protocol["scientific_boundaries"]["functional_untouched_read"]
    assert not protocol["scientific_boundaries"]["rk_g1_complete"]
