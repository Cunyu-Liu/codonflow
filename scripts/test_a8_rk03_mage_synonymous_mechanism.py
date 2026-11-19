import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import a8_rk03_mage_synonymous_mechanism as mage


def test_feature_set_alignment():
    assert mage.numeric_for("intrinsic") == mage.INTRINSIC_NUM
    assert mage.numeric_for("local_mfe") == mage.INTRINSIC_NUM + mage.MFE_NUM
    assert mage.numeric_for("rcs_only") == mage.INTRINSIC_NUM + mage.RCS_NUM
    assert mage.numeric_for("full_mechanism") == mage.INTRINSIC_NUM + mage.MFE_NUM + mage.RCS_NUM
    assert not (set(mage.MFE_NUM) & set(mage.RCS_NUM))


def test_construct_feature_deltas():
    row = {
        "wt_codon": "CTG", "mutant_codon": "TTA", "codon_position": "10", "amino_acid": "L",
        "features_json": json.dumps({"RCS": "2.5", "mfe_ddG_43nt_sliding": "-8"}),
    }
    wt = {"features_json": json.dumps({"RCS": "1.5", "mfe_ddG_43nt_sliding": "-5"})}
    f = mage.construct_features(row, wt)
    assert f["delta_rcs_vs_wt"] == 1.0
    assert f["delta_mfe_vs_wt"] == -3.0
    assert f["abs_delta_mfe_vs_wt"] == 3.0
    assert f["delta_gc_fraction"] == pytest.approx(1 / 3 - 1.0)
    assert f["nt_changes"] == 2.0


def test_holm_two_is_monotone():
    adjusted = mage.holm_two([0.01, 0.04])
    assert adjusted == pytest.approx([0.02, 0.04])
    assert mage.holm_two([0.2, 0.01]) == pytest.approx([0.2, 0.02])


def test_effect_direction_and_bootstrap():
    y = np.asarray([0.1, 0.4, 0.2, 0.8, 0.5, 0.9])
    reference = np.asarray([0.8, 0.1, 0.7, 0.2, 0.9, 0.3])
    candidate = y + 0.01
    result = mage.paired_analysis(y, candidate, reference, 17, 19, 100, True)
    assert result["delta_spearman"] > 0.99
    assert result["delta_rmse"] < 0
    assert result["delta_spearman_ci95"][0] > 0
    assert result["delta_rmse_ci95"][1] < 0


def test_unseen_category_is_safe():
    base = {c: "x" for c in mage.CATS}
    base.update({n: 0.0 for n in mage.INTRINSIC_NUM})
    base["expression_value"] = "0.1"
    train = [dict(base), dict(base)]
    train[1]["mutant_codon"] = "y"
    test = [dict(base)]
    test[0]["mutant_codon"] = "never_seen"
    model = mage.make_pipeline("intrinsic", 1.0)
    X, y = mage.xy(train, "intrinsic")
    model.fit(X, y)
    Xt, _ = mage.xy(test, "intrinsic")
    assert np.isfinite(model.predict(Xt)).all()
