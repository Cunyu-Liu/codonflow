"""CodonFlow core: genetic code tables and hard constraints.

Implements the standard codon table (NCBI translation table 1), synonymous
codon groups, and the feasibility predicate used by the gated terminal
distribution (spec R2/R3-2): reading frame + protein identity + unique stop.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict, Iterable, List, Tuple

RNA_ALPHABET = "ACGU"
DNA_ALPHABET = "ACGT"

STANDARD_TABLE_1 = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}

STOP_CODONS = ("TAA", "TAG", "TGA")
START_CODON = "ATG"

CODONS = tuple(sorted(STANDARD_TABLE_1.keys()))
CODON_TO_INDEX = {c: i for i, c in enumerate(CODONS)}

SYNONYMOUS_CODONS: Dict[str, Tuple[str, ...]] = {}
for _codon, _aa in STANDARD_TABLE_1.items():
    if _aa != "*":
        SYNONYMOUS_CODONS.setdefault(_aa, []).append(_codon)
SYNONYMOUS_CODONS = {aa: tuple(sorted(cs)) for aa, cs in SYNONYMOUS_CODONS.items()}

AMINO_ACIDS = tuple(sorted(SYNONYMOUS_CODONS.keys()))

AA_TO_CODONS_INDEX: Dict[str, Tuple[int, ...]] = {
    aa: tuple(CODON_TO_INDEX[c] for c in cs)
    for aa, cs in SYNONYMOUS_CODONS.items()
}
STOP_INDICES = tuple(CODON_TO_INDEX[c] for c in STOP_CODONS)
START_INDEX = CODON_TO_INDEX[START_CODON]
AA_OF_INDEX = tuple(STANDARD_TABLE_1[c] for c in CODONS)


def normalize_to_dna(seq: str) -> str:
    return seq.upper().replace("U", "T")


def normalize_to_rna(seq: str) -> str:
    return normalize_to_dna(seq).replace("T", "U")


def is_valid_nucleotide_seq(seq: str) -> bool:
    s = seq.upper()
    return len(s) > 0 and all(ch in "ACGTU" for ch in s)


def split_codons(seq: str) -> List[str]:
    s = normalize_to_dna(seq)
    if len(s) % 3 != 0:
        raise ValueError(f"Sequence length {len(s)} is not a multiple of 3")
    return [s[i : i + 3] for i in range(0, len(s), 3)]


@lru_cache(maxsize=65536)
def _translate_cached(seq_dna: str) -> str:
    return "".join(
        STANDARD_TABLE_1.get(seq_dna[i : i + 3], "X")
        for i in range(0, len(seq_dna) - len(seq_dna) % 3, 3)
    )


def translate(seq: str) -> str:
    """Translate a DNA/RNA CDS with the standard table; unknown codons -> X."""
    return _translate_cached(normalize_to_dna(seq))


def translate_to_dna_aa(aa_seq: str) -> str:
    return "".join(SYNONYMOUS_CODONS[aa][0] for aa in aa_seq)


def is_synonymous(y: str, x: str) -> bool:
    """Protein identity check: translate(y) == translate(x) (spec Task 1.3)."""
    return translate(y) == translate(x)


def has_unique_terminal_stop(seq: str) -> bool:
    """Terminal codon is a stop AND no internal stop codons."""
    s = normalize_to_dna(seq)
    if len(s) < 3 or len(s) % 3 != 0:
        return False
    if s[-3:] not in STOP_CODONS:
        return False
    return "*" not in translate(s[:-3])


def reading_frame_ok(seq: str) -> bool:
    return len(seq) % 3 == 0


def is_valid_cds(seq: str) -> bool:
    """Full CDS legality: valid alphabet, frame, unique terminal stop."""
    s = normalize_to_dna(seq)
    return (
        is_valid_nucleotide_seq(s)
        and reading_frame_ok(s)
        and has_unique_terminal_stop(s)
    )


def protein_of_cds(seq: str) -> str:
    """Amino-acid chain without the terminal stop."""
    return translate(normalize_to_dna(seq)[:-3])


def synthesize_cds_from_protein(protein: str) -> str:
    """Build a valid CDS (best-codon synthesis + terminal stop) for tests."""
    return translate_to_dna_aa(protein) + "TAA"


def gc_fraction(seq: str) -> float:
    s = seq.upper()
    if not s:
        return 0.0
    gc = sum(1 for ch in s if ch in "GC")
    return gc / len(s)


def feasible_edit(y: str, x: str) -> bool:
    """Hard feasibility predicate F for the gated terminal distribution.

    F = {translate(y) == translate(x)} AND {len(y) % 3 == 0} AND {unique
    terminal stop} (spec Task 2.2.1). GC and motif are NOT part of F.
    """
    return (
        is_synonymous(y, x)
        and reading_frame_ok(y)
        and has_unique_terminal_stop(y)
    )


def synonymous_codons_for(aa: str) -> Tuple[str, ...]:
    return SYNONYMOUS_CODONS[aa]


def codon_options_at(position: int, source_codons: Iterable[str]) -> List[str]:
    """Allowed replacement codons at a position (same amino acid, spec R3-1
    synonymous-replacement edit operator)."""
    src = list(source_codons)
    if position < 0 or position >= len(src):
        raise IndexError("position out of range")
    aa = STANDARD_TABLE_1[src[position]]
    return [c for c in SYNONYMOUS_CODONS[aa]]
