#!/usr/bin/env python3
"""Contract tests for the independent RK-12 frozen-scorer reimplementation."""
import pytest

from codonflow.core.motifs import motif_penalty_score
from scripts.a8_rk12_verify_actual_set_matrix import motif_penalty


@pytest.mark.parametrize(
    "sequence",
    [
        "AAAAAA",
        "CAGG",
        "AAAAAACAGG",
        "TAATACGACTCACTATA",
        "ATTTAGGTGACACTAT",
        "AATAAATAAA",
        "ATGAAACCCGGGTTTTTTTAA",
    ],
)
def test_independent_motif_matches_frozen_production_default(sequence):
    assert motif_penalty(sequence) == pytest.approx(motif_penalty_score(sequence), abs=1e-12)


def test_homopolymer_uses_summed_run_length_not_run_count():
    assert motif_penalty("AAAAAA") == pytest.approx(6.0)
    assert motif_penalty("AAAAAACCCCCC") == pytest.approx(12.0)


def test_overlapping_catalogue_occurrences_are_counted():
    assert motif_penalty("AATAAATAAA") == pytest.approx(2.0)
