import math

import numpy as np

from codonflow.eval.metrics import (
    cai,
    cai_weights_from_rscu,
    compute_rscu,
    levenshtein,
    ned,
    pairwise_ned,
    unique_fraction,
    codon_entropy_per_aa_position,
    hypervolume,
)
from codonflow.core.motifs import count_motifs, motif_penalty_score


RSCU_EQUAL = {c: 1.0 for c in
              [a + b + d for a in "ACGT" for b in "ACGT" for d in "ACGT"]
              if c not in ("TAA", "TAG", "TGA")}


def test_rscu_basic():
    rscu = compute_rscu(["ATGGCTTAA", "ATGGCCTAA"])
    assert rscu["ATG"] == 1.0
    assert abs(rscu["GCT"] - 2.0) < 1e-9
    assert abs(rscu["GCC"] - 2.0) < 1e-9
    assert rscu["GCA"] == 0.0


def test_cai_equal_weights_one():
    w = cai_weights_from_rscu(RSCU_EQUAL)
    assert abs(cai("ATGGCTTAA", w) - 1.0) < 1e-9


def test_cai_prefers_frequent():
    rscu = dict(RSCU_EQUAL)
    rscu["GCT"] = 2.0
    rscu["GCC"] = 0.5
    w = cai_weights_from_rscu(rscu)
    assert cai("ATGGCTTAA", w) > cai("ATGGCCTAA", w)


def test_levenshtein():
    assert levenshtein("ATG", "ATG") == 0
    assert levenshtein("ATG", "ACG") == 1
    assert levenshtein("", "AAA") == 3


def test_ned():
    assert abs(ned("ATG", "ACG") - 1 / 3) < 1e-9
    assert ned("AAAA", "AAAA") == 0.0


def test_pairwise_ned_positive():
    seqs = ["ATGAAATTTTAA", "ATGAAGTTTTAA", "ATGAAATTCTAA"]
    assert pairwise_ned(seqs) > 0
    assert unique_fraction(seqs) == 1.0


def test_unique_fraction_distinct_counts():
    assert unique_fraction(["ATG", "ATG"]) == 0.5
    assert unique_fraction(["ATG", "ACC"]) == 1.0


def test_codon_entropy():
    hom = ["ATGGCTTAA"] * 10
    div = ["ATGGCTTAA", "ATGGCCTAA", "ATGGCCTAA", "ATGGCTTAA"]
    assert codon_entropy_per_aa_position(div) > codon_entropy_per_aa_position(hom)


def test_hypervolume_2d():
    ref = [0.0, 0.0]
    pts = [[1.0, 1.0]]
    hv = hypervolume(pts, ref)
    assert abs(hv - 1.0) < 0.05


def test_hypervolume_empty():
    assert hypervolume([], [0, 0, 0, 0]) == 0.0


def test_motifs():
    s = "ATG" * 30 + "AATAAA" + "TAA"
    counts = count_motifs(s)
    assert counts.get("polyA_AATAAA", 0) >= 1
    assert motif_penalty_score(s) > 0


def test_homopolymer():
    s = "ATG" + "A" * 8 + "TAA"
    counts = count_motifs(s)
    assert counts.get("homopolymer_A", 0) >= 1
