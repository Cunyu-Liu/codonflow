"""Unit tests for the codon core (round-trip, constraints, translation)."""
import pytest

from codonflow.core.codon import (
    CODONS,
    STOP_CODONS,
    SYNONYMOUS_CODONS,
    feasible_edit,
    gc_fraction,
    has_unique_terminal_stop,
    is_synonymous,
    is_valid_cds,
    protein_of_cds,
    split_codons,
    synthesize_cds_from_protein,
    translate,
)


def test_codon_table_size():
    assert len(CODONS) == 64
    assert len(SYNONYMOUS_CODONS) == 20


def test_translate_known():
    assert translate("ATGGCTTAA") == "MA*"
    assert translate("ATGAAATTTTGA") == "MKF*"
    assert translate("AUGGCCUAA") == "MA*"


def test_synonymous():
    assert is_synonymous("ATGGCTTAA", "ATGGCCTAA")
    assert not is_synonymous("ATGGCTTAA", "ATGGATTAA")


def test_terminal_stop():
    assert has_unique_terminal_stop("ATGTAA")
    assert not has_unique_terminal_stop("ATGTAGTAA")
    assert not has_unique_terminal_stop("ATGGCA")


def test_valid_cds():
    assert is_valid_cds(synthesize_cds_from_protein("MKF"))
    assert not is_valid_cds("ATGN")
    assert not is_valid_cds("ATGG")


def test_frame_split():
    with pytest.raises(ValueError):
        split_codons("ATGG")


def test_feasible_edit():
    x = synthesize_cds_from_protein("MKF")
    y = "ATGAAGTTCTGA"
    assert feasible_edit(y, x)
    assert not feasible_edit("ATGAAATTATGA", x)


def test_gc():
    assert abs(gc_fraction("GCAT") - 0.5) < 1e-9


def test_protein_roundtrip():
    p = "MKWVHIS"
    cds = synthesize_cds_from_protein(p)
    assert protein_of_cds(cds) == p


def test_all_synonymous_same_length():
    for aa, group in SYNONYMOUS_CODONS.items():
        for c in group:
            assert len(c) == 3
            assert translate(c) == aa
