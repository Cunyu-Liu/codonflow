import json
from pathlib import Path

import numpy as np
import pytest

from scripts.a8_rk05_lineardesign_official_smoke import parse_stdout, translate
from scripts.a8_rk12_lineardesign_unique18 import atomic_json
from scripts.a8_rk12_score_actual_set_matrix import holm_adjust, paired_effect
from scripts.a8_rk12_verify_actual_set_matrix import cai, cai_weights, motif_penalty, normalized_hv
from scripts.a8_rk12_verify_lineardesign_unique18 import translate as independent_translate

REPO = Path(__file__).resolve().parents[2]
PROTOCOL = REPO / "configs/a8_rk12_lineardesign_unique18_protocol_v1.json"


def test_frozen_unique18_grid_has_198_ordered_runs():
    protocol = json.loads(PROTOCOL.read_text())
    assert len(protocol["record_order"]) == len(set(protocol["record_order"])) == 18
    assert protocol["lambda_grid"] == [i / 10 for i in range(11)]
    assert protocol["expected_run_count"] == 18 * 11 == 198
    assert protocol["execution"]["workers"] == 1
    assert protocol["execution"]["order"] == "record_order_then_ascending_lambda"


def test_lambda_grid_is_not_mislabeled_as_dense_budget_auc():
    protocol = json.loads(PROTOCOL.read_text())
    assert protocol["dense_budget_step_auc_v2"] is None
    assert "not successive real-scorer budgets" in protocol["dense_auc_unavailable_reason"]
    assert protocol["untouched24_used"] is False
    assert protocol["functional_untouched_used"] is False
    assert protocol["sota_claim"] is False


def test_generation_and_independent_scoring_costs_are_separate():
    protocol = json.loads(PROTOCOL.read_text())
    assert "single worker" in protocol["cost"]["generation_wall_clock"]
    assert "never added" in protocol["cost"]["independent_scoring_wall_clock"]
    assert protocol["cost"]["forward_calls"] is None


def test_official_stdout_parser_preserves_sequence_structure_and_metrics():
    sequence = "AUGGCUGAA"
    structure = "........."
    stdout = (
        f"mRNA sequence: {sequence}\n"
        f"mRNA structure: {structure}\n"
        "mRNA folding free energy: -12.3 kcal/mol; mRNA CAI: 0.456\n"
    )
    parsed = parse_stdout(stdout)
    assert parsed == {
        "sequence_rna": sequence,
        "structure": structure,
        "official_mfe_kcal_mol": -12.3,
        "official_cai": 0.456,
    }


def test_independent_codon_translation_matches_existing_helper_for_all_codons():
    codons = [a + b + c for a in "TCAG" for b in "TCAG" for c in "TCAG"]
    for codon in codons:
        assert independent_translate(codon) == translate(codon)


def test_atomic_json_round_trip_and_no_partial_file(tmp_path):
    output = tmp_path / "report.json"
    payload = {"status": "PASS", "values": [1, 2, 3]}
    atomic_json(output, payload)
    assert json.loads(output.read_text()) == payload
    assert not (tmp_path / "report.json.tmp").exists()
    with pytest.raises(TypeError):
        atomic_json(tmp_path / "bad.json", {"bad": object()})
    assert not (tmp_path / "bad.json").exists()


def test_paired_effect_is_record_aligned_and_deterministic():
    new = list(range(1, 19))
    comparator = [0] * 18
    first = paired_effect(new, comparator, resamples=1000, seed=7)
    second = paired_effect(new, comparator, resamples=1000, seed=7)
    assert first == second
    assert first["mean_effect"] == 9.5
    assert first["ci95"][0] > 0
    assert first["bootstrap_p_two_sided"] < 0.01
    assert first["per_record_effects"] == new


def test_holm_adjustment_is_monotone_and_matches_hand_example():
    raw = {"a": 0.01, "b": 0.02, "c": 0.04, "d": 0.20}
    adjusted = holm_adjust(raw)
    assert adjusted == {"a": 0.04, "b": 0.06, "c": 0.08, "d": 0.20}


def test_independent_cai_and_motif_hand_checks():
    codons = [a + b + c for a in "TCAG" for b in "TCAG" for c in "TCAG"]
    weights = cai_weights({codon: 1.0 for codon in codons})
    assert cai("ATGGCTTAA", weights) == 1.0
    assert motif_penalty("AATAAA") == 1.0
    assert motif_penalty("AAAAAA") == 1.0
    assert motif_penalty("TAATACGACTCACTATA") == 1.0
    assert motif_penalty("ATGGCT") == 0.0


def test_independent_two_dimensional_hypervolume_hand_check():
    objectives = np.asarray([[1.0, 2.0], [2.0, 1.0]])
    reference = np.zeros(2)
    scale = np.ones(2)
    assert normalized_hv(objectives, reference, scale) == pytest.approx(3.0)
