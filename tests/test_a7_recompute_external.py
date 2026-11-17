import hashlib
import json

import pytest

from codonflow.core.codon import STANDARD_TABLE_1
from codonflow.models.guided_sampler import synonymous_x0
from scripts.a7_recompute_external import recompute_external
from tests.test_a7_g2_raw_verification import valid_result
import numpy as np


def external_inputs(tmp_path):
    _, source, calibration_dir = valid_result(tmp_path)
    calibration = json.loads((calibration_dir / "g1.json").read_text())
    variant = synonymous_x0(source, np.random.default_rng(7))
    payload = {
        "status": "done", "benchmark_sha256": "b" * 64,
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "methods": {
            "gemorna": {"status": "done", "solutions": [source, variant], "n_unique": 2,
                        "obj_vectors": [[999, 999, 999, 999]] * 2,
                        "elapsed_s": 12.0, "forward_calls": None,
                        "terminal_reward_evaluations": 2, "unique_terminal_reward_calls": 2},
            "codongpt": {"status": "architectural_exclusion", "reason": "context limit"},
        },
    }
    rscu = {codon: 1.0 for codon in STANDARD_TABLE_1}
    return payload, source, calibration, rscu, variant


def test_external_recompute_uses_a7_objectives_without_padding(tmp_path):
    payload, source, calibration, rscu, variant = external_inputs(tmp_path)
    result = recompute_external(payload, source, calibration, rscu)
    method = result["gemorna"]
    assert method["n_unique"] == 2
    assert method["covered_frozen_budgets"] == []
    assert method["missing_frozen_budgets"] == [50, 100, 500]
    assert method["points"][0]["objectives"] != [999, 999, 999, 999]
    assert method["legacy_generation_costs"]["time_semantics"] == "legacy_generation_time_not_end_to_end"
    assert result["codongpt"]["status"] == "architectural_exclusion"
    assert np.isfinite(method["actual_budget_auc"])


def test_external_recompute_rejects_duplicates_and_non_synonymous(tmp_path):
    payload, source, calibration, rscu, variant = external_inputs(tmp_path)
    payload["methods"]["gemorna"]["solutions"][1] = payload["methods"]["gemorna"]["solutions"][0]
    with pytest.raises(ValueError, match="count mismatch"):
        recompute_external(payload, source, calibration, rscu)
    payload, source, calibration, rscu, variant = external_inputs(tmp_path)
    payload["methods"]["gemorna"]["solutions"][1] = "ATG" + "AAA" * 20 + "TAA"
    with pytest.raises(ValueError, match="identity failure"):
        recompute_external(payload, source, calibration, rscu)
