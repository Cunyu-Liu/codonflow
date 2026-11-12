import json

import pytest

from codonflow.core.codon import feasible_edit, gc_fraction
from codonflow.models.simple_search import SimpleSearch, augmented_tchebycheff

SOURCE = "TTTGCTTAA"


def objective(sequence):
    return [gc_fraction(sequence), -abs(gc_fraction(sequence) - 0.55), -sequence.count("TTT")]


@pytest.mark.parametrize("method", SimpleSearch.METHODS)
def test_search_is_reproducible_legal_and_budgeted(method):
    budget = 4 if method == "uniform" else 8
    first = SimpleSearch(SOURCE, objective, [1, 1, 0.1], seed=7).run(method, max_unique_scorer=budget)
    second = SimpleSearch(SOURCE, objective, [1, 1, 0.1], seed=7).run(method, max_unique_scorer=budget)
    assert first.status == "done"
    assert len(first.points) == budget
    assert [point["budget"] for point in first.points] == list(range(1, budget + 1))
    assert [point["sequence"] for point in first.points] == [point["sequence"] for point in second.points]
    assert [point["objectives"] for point in first.points] == [point["objectives"] for point in second.points]
    assert len({point["sequence"] for point in first.points}) == budget
    assert all(feasible_edit(point["sequence"], SOURCE) for point in first.points)
    payload = first.to_dict()
    assert payload["costs"]["unique_terminal_reward_calls"] == budget
    assert payload["costs"]["forward_calls"] == 0
    json.dumps(payload)


def test_uniform_uses_the_same_single_codon_operator():
    result = SimpleSearch(SOURCE, objective, [1, 1, 0.1], seed=7).run("uniform", max_unique_scorer=4)
    for point in result.points[1:]:
        differences = [i for i, (a, b) in enumerate(zip(result.source, point["sequence"])) if a != b]
        assert 1 <= len(differences) <= 3
        assert differences[0] // 3 == differences[-1] // 3


def test_calibration_retains_frozen_global_synonymous_sampling():
    result = SimpleSearch(SOURCE, objective, [1, 1, 0.1], seed=7,
                          uniform_operator="global_synonymous").run("uniform", max_unique_scorer=4)
    assert result.points[1]["sequence"] != SOURCE
    assert result.points[1]["sequence"][3:6] != SOURCE[3:6]


def test_tchebycheff_ignores_zero_weight_axes_in_minimum():
    balanced = augmented_tchebycheff([0.2, 0.5], [1, 0])
    changed = augmented_tchebycheff([0.2, 0.9], [1, 0])
    assert balanced == changed


def test_search_rejects_invalid_source():
    with pytest.raises(ValueError, match="valid CDS"):
        SimpleSearch("ATG", objective, [1, 1, 1])


def test_utility_uses_frozen_calibration_normalization():
    search = SimpleSearch(SOURCE, objective, [1, 1], normalization=([0, 0], [1, 100]))
    raw = search._utility("hill_climbing", [1, 100])
    assert raw == 2.0
    normalized = search._utility("hill_climbing", [0.5, 50])
    assert normalized == 1.0
