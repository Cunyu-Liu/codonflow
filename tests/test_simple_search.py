import json

import pytest

from codonflow.core.codon import feasible_edit, gc_fraction
from codonflow.models.simple_search import SimpleSearch, augmented_tchebycheff

SOURCE = "TTTGCTTAA"


def objective(sequence):
    return [gc_fraction(sequence), -abs(gc_fraction(sequence) - 0.55), -sequence.count("TTT")]


@pytest.mark.parametrize("method", SimpleSearch.METHODS)
def test_search_is_reproducible_legal_and_budgeted(method):
    first = SimpleSearch(SOURCE, objective, [1, 1, 0.1], seed=7).run(method, max_unique_scorer=8)
    second = SimpleSearch(SOURCE, objective, [1, 1, 0.1], seed=7).run(method, max_unique_scorer=8)
    assert first.status == "done"
    assert len(first.points) == 8
    assert [point["budget"] for point in first.points] == list(range(1, 9))
    assert [point["sequence"] for point in first.points] == [point["sequence"] for point in second.points]
    assert [point["objectives"] for point in first.points] == [point["objectives"] for point in second.points]
    assert len({point["sequence"] for point in first.points}) == 8
    assert all(feasible_edit(point["sequence"], SOURCE) for point in first.points)
    payload = first.to_dict()
    assert payload["costs"]["unique_terminal_reward_calls"] == 8
    assert payload["costs"]["forward_calls"] == 0
    json.dumps(payload)


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
