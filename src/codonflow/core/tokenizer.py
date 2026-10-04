"""Codon-level tokenizer: 64 codons + BOS + EOS + PAD = 67 tokens (spec R3-1).

Round-trip encode/decode must be lossless for any valid CDS; illegal
nucleotide strings must raise (Task 1.1.4).
"""
from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from .codon import (
    CODONS,
    CODON_TO_INDEX,
    is_valid_nucleotide_seq,
    normalize_to_dna,
)

VOCAB_SIZE = 67
PAD_TOKEN = "<PAD>"
BOS_TOKEN = "<BOS>"
EOS_TOKEN = "<EOS>"

PAD_ID = 64
BOS_ID = 65
EOS_ID = 66

SPECIAL_TOKENS = (PAD_TOKEN, BOS_TOKEN, EOS_TOKEN)

ID_TO_TOKEN: Tuple[str, ...] = tuple(CODONS) + (PAD_TOKEN, BOS_TOKEN, EOS_TOKEN)
TOKEN_TO_ID = {t: i for i, t in enumerate(ID_TO_TOKEN)}


def encode_cds(seq: str, add_special: bool = True) -> List[int]:
    """Tokenize a CDS into codon ids; raises on illegal characters or frame."""
    s = normalize_to_dna(seq)
    if not is_valid_nucleotide_seq(s):
        raise ValueError(f"Illegal nucleotide sequence: {seq!r}")
    if len(s) % 3 != 0:
        raise ValueError(f"Sequence length {len(s)} not a multiple of 3")
    ids = [CODON_TO_INDEX[s[i : i + 3]] for i in range(0, len(s), 3)]
    if add_special:
        return [BOS_ID] + ids + [EOS_ID]
    return ids


def decode_cds(ids: Sequence[int], strip_special: bool = True) -> str:
    """De-tokenize codon ids back to a DNA CDS string."""
    if strip_special:
        ids = [i for i in ids if i < 64]
    parts: List[str] = []
    for i in ids:
        if not 0 <= i < VOCAB_SIZE:
            raise ValueError(f"Token id {i} out of range")
        if i >= 64:
            if not strip_special:
                parts.append(ID_TO_TOKEN[i])
            continue
        parts.append(CODONS[i])
    if not strip_special and parts and (parts[0] == BOS_TOKEN or parts[-1] == EOS_TOKEN):
        pass
    return "".join(parts)


def encode_batch(seqs: Iterable[str], max_len: int = 2002) -> List[List[int]]:
    return [encode_cds(s)[:max_len] for s in seqs]


def is_legal_codon_token_stream(ids: Sequence[int]) -> bool:
    return all(0 <= i < VOCAB_SIZE for i in ids)
