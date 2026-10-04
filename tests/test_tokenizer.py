import pytest

from codonflow.core.tokenizer import (
    BOS_ID,
    EOS_ID,
    PAD_ID,
    VOCAB_SIZE,
    decode_cds,
    encode_cds,
    ID_TO_TOKEN,
)


def test_vocab_size_67():
    assert VOCAB_SIZE == 67
    assert ID_TO_TOKEN[64] == "<PAD>"
    assert ID_TO_TOKEN[65] == "<BOS>"
    assert ID_TO_TOKEN[66] == "<EOS>"


def test_roundtrip():
    seq = "ATGGCTTAA"
    ids = encode_cds(seq)
    assert ids[0] == BOS_ID and ids[-1] == EOS_ID
    assert decode_cds(ids) == seq


def test_roundtrip_long():
    seq = "ATG" * 100 + "TAA"
    assert decode_cds(encode_cds(seq)) == seq


def test_rna_t():
    assert decode_cds(encode_cds("AUGGCUUAA")) == "ATGGCTTAA"


def test_illegal_chars_raise():
    with pytest.raises(ValueError):
        encode_cds("ATGN")
    with pytest.raises(ValueError):
        encode_cds("ATGAA")


def test_all_64_codons_roundtrip():
    triplets = []
    for a in "ACGT":
        for b in "ACGT":
            for c in "ACGT":
                triplets.append(a + b + c)
    seq = "".join(triplets[:21]) + "TAA"
    assert decode_cds(encode_cds(seq)) == seq
