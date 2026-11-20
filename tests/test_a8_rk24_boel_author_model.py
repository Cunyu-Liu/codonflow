import json
from pathlib import Path

import numpy as np
import pytest
from scipy.special import expit
from scipy.stats import rankdata

from scripts import a8_rk24_build_features as build
from scripts import a8_rk24_run_boel_author_model as rk24


ROOT = Path(__file__).resolve().parents[1]


def protocol():
    return json.loads((ROOT / "audits/20261121/RK24/a8_rk24_boel_author_protocol_v1.json").read_text())


def synthetic_cds(codons=None):
    codons = list(codons or (["ATG"] + ["GCT"] * 31))
    tag = ["CTC", "GAG"] + ["CAC"] * 6
    return "".join(codons + tag + ["TGA"])


def test_repetition_rate_matches_published_lrprl_example():
    assert build.repetition_rate("LRPRL") == pytest.approx(0.15)


def test_core_removes_exact_tag_and_stop():
    cds = synthetic_cds()
    core, protein, codons = build.core_from_cds(cds)
    assert len(codons) == 32 and len(core) == 96 and len(protein) == 32
    assert core == "".join(codons)
    assert not protein.endswith(build.TAG_AA)


def test_tag_is_required():
    codons = ["ATG"] + ["GCT"] * 39
    with pytest.raises(ValueError, match="tag required"):
        build.core_from_cds("".join(codons + ["TGA"]))


def test_author_static_head_length_and_codon_contract():
    codons = ["ATG", "AAA", "AAC", "AAG", "ATA", "ATC"] + ["GCT"] * 26
    f = build.author_static_features(synthetic_cds(codons), -40.0)
    head = "".join(codons[1:6])
    assert f["aH"] == pytest.approx(head.count("A") / 15)
    assert f["gH"] == pytest.approx(head.count("G") / 15)
    assert f["u3H"] == pytest.approx(sum(c[2] == "T" for c in codons[1:6]) / 5)
    assert f["I_62"] == float(-40 < -39 and f["GC2_6"] > 0.62)
    assert f["core_length_nt"] == 96 and f["L_knt"] == pytest.approx(0.096)
    assert f["Linv_knt"] == pytest.approx(1000 / 96)
    assert sum(f[f"cf_{c}"] for c in build.CODONS) == pytest.approx(1)


def test_daua_is_in_frame_adjacent():
    codons = ["ATG"] + ["GCT"] * 31
    codons[10:12] = ["ATA", "ATA"]
    assert build.author_static_features(synthetic_cds(codons), -10)["dAUA"] == 1
    codons[10:12] = ["ATA", "GCT"]
    codons[12] = "ATA"
    # Two AUA codons separated by another codon are not an AUA-AUA di-codon.
    assert build.author_static_features(synthetic_cds(codons), -10)["dAUA"] == 0


def test_author_feature_count_and_atg_omission():
    names = rk24.author_feature_names(protocol())
    assert len(names) == 72 and len(set(names)) == 72
    assert "cf_ATG" not in names and "s7_16" in names and "s17_32" in names


def test_regional_slopes_use_codons_7_16_and_17_32():
    codons = ["ATG"] + ["GCT"] * 31
    rows = [{"core_codons": codons}]
    slopes = {c: float(i + 1) for i, c in enumerate(build.CODONS)}
    x = rk24.feature_matrix(rows, ["s7_16", "s17_32"], slopes)
    expected = slopes["GCT"]
    np.testing.assert_allclose(x, [[expected, expected]])
    other = ["ATG"] + ["GCT"] * 31
    other[6] = "AAA"
    rows[0]["core_codons"] = other
    changed = rk24.feature_matrix(rows, ["s7_16", "s17_32"], slopes)
    assert changed[0, 0] != x[0, 0] and changed[0, 1] == x[0, 1]


def test_binary_logistic_recovers_direction_and_prediction():
    rng = np.random.default_rng(24)
    x = rng.normal(size=400)
    y = (rng.random(400) < expit(0.3 + 1.2 * x)).astype(float)
    model = rk24.fit_binary_logistic(x, y, 0.0, 5000, 1e-6)
    raw_slope = model["weights"][0] / model["train_scale"][0]
    assert raw_slope > 0.5
    p = rk24.binary_predict(model, x)
    z = (x - model["train_mean"][0]) / model["train_scale"][0]
    np.testing.assert_allclose(p, expit(z * model["weights"][0] + model["bias"]))


def test_auc_handles_ties_and_logloss_direction():
    y = np.asarray([0, 0, 1, 1], dtype=float)
    p = np.asarray([0.2, 0.4, 0.4, 0.8])
    ranks = rankdata(p)
    expected = (ranks[y == 1].sum() - 2 * 3 / 2) / 4
    assert rk24.fast_auc(y, p) == pytest.approx(expected)
    good = np.asarray([0.1, 0.2, 0.8, 0.9])
    assert rk24.fast_logloss(y, good) < rk24.fast_logloss(y, 1 - good)


def test_resampling_shapes_and_endpoint_signs(tmp_path):
    rng = np.random.default_rng(24)
    clusters = np.repeat(np.arange(8), 8)
    y = np.tile(np.arange(8) % 6, 8).astype(float)
    base_b = np.clip(1 - y / 5 + rng.normal(scale=0.05, size=len(y)), 1e-4, 1 - 1e-4)
    author_b = np.clip(y / 5 * 0.98 + 0.01, 1e-4, 1 - 1e-4)
    base_m = 5 - y + rng.normal(scale=0.1, size=len(y))
    author_m = y.copy()
    predictions = {"base_binary_p_e5": base_b, "author_binary_p_e5": author_b,
                   "base_multiclass_expected": base_m, "author_multiclass_expected": author_m}
    cfg = protocol()
    cfg["bootstrap"]["replicates"] = 40
    cfg["permutation"]["replicates"] = 40
    out = rk24.resample_primary(y, predictions, clusters, cfg, 0, tmp_path / "arrays.npz")
    arrays = np.load(tmp_path / "arrays.npz")
    assert arrays["bootstrap_effects"].shape == (40, 4)
    assert arrays["permutation_effects"].shape == (40, 4)
    assert all(out["comparisons"][name]["effect"] > 0 for name in rk24.ENDPOINTS)


def test_protocol_has_four_endpoints_and_train_only_supervision():
    cfg = protocol()
    assert cfg["primary_endpoints"] == rk24.ENDPOINTS
    assert cfg["label_field"] == "expression_value"
    assert cfg["comparison"]["published_coefficients_used_for_prediction"] is False
    assert cfg["comparison"]["all_supervised_reconstruction_train_only"] is True
    assert cfg["models"]["author_binary"]["l2"] == 0
    assert cfg["models"]["author_multiclass"]["l2"] == 0.01


def test_input_hashes_and_closed_gates():
    cfg = protocol()
    for path_key, digest_key in rk24.INPUT_HASH_KEYS.items():
        assert path_key in cfg and digest_key in cfg
    assert cfg["forbidden_split"] == "functional_untouched"
    assert cfg["gate"]["generator_training_authorized"] is False
    assert cfg["gate"]["rk_g1_remains_false_even_if_pass"] is True
