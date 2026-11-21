from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SPEC = importlib.util.spec_from_file_location("rk39", ROOT / "scripts/a8_rk39_common_input_actual_set.py")
RK39 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RK39)

from codonflow.eval.anytime import FrozenReference


def protocol():
    return json.loads((ROOT / "configs/a8_rk39_common_input_actual_set_protocol_v1.json").read_text())


def test_protocol_counts_and_no_native_search():
    p = protocol()
    assert p["expected_run_count"] == 18 * 3 * 3 == 162
    assert p["expected_unique_scorer_calls"] == 162 * 11 == 1782
    assert p["input_semantics"]["native_cds_used_in_search"] is False
    assert p["input_semantics"]["search_normalization"] is None
    assert p["input_semantics"]["terminal_stop"] == "TAA"
    assert p["primary_method"] == "hill_climbing"
    assert p["primary_endpoints"] == ["hypervolume_normalized", "pairwise_ned"]
    assert p["functional_untouched_used"] is False
    assert p["sota_claim"] is False


def test_protein_only_template_and_initial_discard_native_synonyms_and_stop():
    a = "ATGGCTGCTTGA"
    b = "ATGGCCGCATAG"
    assert RK39.protein_from_cds(a) == RK39.protein_from_cds(b) == "MAA*"
    template_a = RK39.protein_only_template(a)
    template_b = RK39.protein_only_template(b)
    assert template_a == template_b
    assert template_a.endswith("TAA")
    assert RK39.protein_only_initial(a, 7) == RK39.protein_only_initial(b, 7)
    assert RK39.protein_from_cds(RK39.protein_only_initial(a, 7)) == "MAA*"


def test_actual_set_metrics_are_order_invariant_and_unpadded():
    frozen = FrozenReference(reference=np.full(4, -1.0), scale=np.ones(4))
    points = [
        {"output_id": "a", "sequence": "ATGGCTTAA", "objectives": [0.2, 0.3, 0.4, 0.5]},
        {"output_id": "b", "sequence": "ATGGCCTAA", "objectives": [0.5, 0.4, 0.3, 0.2]},
        {"output_id": "c", "sequence": "ATGGCATAA", "objectives": [0.3, 0.5, 0.2, 0.4]},
    ]
    a = RK39.evaluate_actual_set(points, frozen)
    b = RK39.evaluate_actual_set(list(reversed(points)), frozen)
    assert a["hypervolume_normalized"] == b["hypervolume_normalized"]
    assert a["pairwise_ned"] == b["pairwise_ned"]
    assert a["n_actual_outputs"] == 3
    assert a["dense_budget_step_auc_v2"] is None


def test_holm_and_primary_gate_direction():
    adjusted = RK39.holm_adjust([0.01, 0.04, 0.03])
    assert np.allclose(adjusted, [0.03, 0.06, 0.06])
    p = copy.deepcopy(protocol())
    p["statistics"]["paired_bootstrap_resamples"] = 200
    p["statistics"]["paired_sign_flip_permutations"] = 200
    records = [f"r{i:02d}" for i in range(18)]
    external = {r: {"hypervolume_normalized": 0.1, "pairwise_ned": 0.05, "k": 5} for r in records}
    descriptors = []
    for i, record in enumerate(records):
        for seed in [0, 1, 2]:
            for method in p["methods"]:
                good = method == "hill_climbing"
                descriptors.append({
                    "record_id": record, "seed": seed, "method": method,
                    "matched_linear_design_k": 5,
                    "hypervolume_normalized": (0.2 if good else 0.09) + i * 1e-5 + seed * 1e-6,
                    "pairwise_ned": (0.08 if good else 0.04) + i * 1e-5 + seed * 1e-6,
                })
    result = RK39.inference(descriptors, external, p)
    assert result["primary_gate_passed"] is True
    primary = [row for row in result["tests"] if row["confirmatory"]]
    assert len(primary) == 2
    assert all(row["effect"] > 0 and row["ci95"][0] > 0 and row["holm_p"] < 0.05 for row in primary)
    assert all(row["all_seed_effects_positive"] for row in primary)
    assert all(row["supported_advantage"] is None for row in result["tests"] if not row["confirmatory"])


def test_failed_primary_cannot_be_rescued_by_sensitivity():
    p = copy.deepcopy(protocol())
    p["statistics"]["paired_bootstrap_resamples"] = 100
    p["statistics"]["paired_sign_flip_permutations"] = 100
    records = [f"r{i:02d}" for i in range(18)]
    external = {r: {"hypervolume_normalized": 0.1, "pairwise_ned": 0.05, "k": 5} for r in records}
    descriptors = []
    for record in records:
        for seed in [0, 1, 2]:
            for method in p["methods"]:
                descriptors.append({
                    "record_id": record, "seed": seed, "method": method,
                    "matched_linear_design_k": 5,
                    "hypervolume_normalized": 0.2 if method == "mh_annealing" else 0.09,
                    "pairwise_ned": 0.08 if method == "mh_annealing" else 0.04,
                })
    result = RK39.inference(descriptors, external, p)
    assert result["primary_gate_passed"] is False
    assert any(row["method"] == "mh_annealing" and row["effect"] > 0 for row in result["tests"])
