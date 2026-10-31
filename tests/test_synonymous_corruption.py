"""The synonymous corruption must stay inside the feasible synonymous support."""
import torch

from codonflow.core.tokenizer import encode_cds, PAD_ID
from codonflow.data.dataset import corrupt_x_t, corrupt_x_t_synonymous
from codonflow.models.synonymous_markov import STANDARD_TABLE_1, CODON_TO_INDEX, encode_cds as _enc

ID_TO_AA = {_enc(c, add_special=False)[0]: STANDARD_TABLE_1[c]
            for c in CODON_TO_INDEX if c in STANDARD_TABLE_1}

CDS = ("ATG" + "GCT" * 20 + "TGG" * 5 + "TAA")


def _protein(ids):
    return "".join(ID_TO_AA[index] for index in ids if index in ID_TO_AA)


def test_synonymous_corruption_preserves_the_protein():
    ids = torch.tensor([encode_cds(CDS, add_special=True)])
    g = torch.Generator().manual_seed(0)
    for _ in range(5):
        x = corrupt_x_t_synonymous(ids, t=torch.tensor([1.0]), generator=g)
        assert _protein(x[0].tolist()) == _protein(ids[0].tolist())
        assert (x != ids).any()


def test_arbitrary_corruption_breaks_the_protein():
    ids = torch.tensor([encode_cds(CDS, add_special=True)])
    g = torch.Generator().manual_seed(0)
    x = corrupt_x_t(ids, t=torch.tensor([1.0]), generator=g)
    assert _protein(x[0].tolist()) != _protein(ids[0].tolist())


def test_synonymous_corruption_keeps_the_terminal_stop():
    ids = torch.tensor([encode_cds(CDS, add_special=True)])
    g = torch.Generator().manual_seed(1)
    x = corrupt_x_t_synonymous(ids, t=torch.tensor([1.0]), generator=g)
    body = [i for i in ids[0].tolist() if i != PAD_ID]
    assert x[0][len(body) - 2].item() == ids[0][len(body) - 2].item()
