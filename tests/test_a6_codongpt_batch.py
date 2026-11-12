from types import SimpleNamespace

import torch

from codonflow.core.codon import CODONS, protein_of_cds
from scripts.run_a6_baselines import codongpt_batch_sample, generate_method


class Tokenizer:
    def __init__(self):
        self.tokens = ["[BOS]", *CODONS]
        self.ids = {token: index for index, token in enumerate(self.tokens)}

    def convert_tokens_to_ids(self, tokens):
        return [self.ids[token] for token in tokens]

    def convert_ids_to_tokens(self, ids):
        if isinstance(ids, int):
            ids = [ids]
        return [self.tokens[index] for index in ids]


class Model:
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
        self.calls = []

    def __call__(self, input_ids):
        self.calls.append(tuple(input_ids.shape))
        logits = torch.zeros((*input_ids.shape, len(self.tokenizer.tokens)))
        return SimpleNamespace(logits=logits)


def test_codongpt_batch_preserves_protein_and_batches_forward_calls():
    tokenizer = Tokenizer()
    model = Model(tokenizer)
    solutions = codongpt_batch_sample(model, tokenizer, "MA", 4, 0, torch.device("cpu"))
    assert len(solutions) == 4
    assert all(protein_of_cds(sequence) == "MA" for sequence in solutions)
    assert len(model.calls) == 3
    assert model.calls[0] == (4, 1)
    assert model.calls[-1] == (4, 3)


def test_codongpt_cost_distinguishes_batched_and_token_equivalent_forwards():
    tokenizer = Tokenizer()
    model = Model(tokenizer)
    weights = {codon: 1.0 for codon in CODONS}
    _solutions, costs = generate_method("codongpt", "ATGGCTTAA", weights, 4, 0,
                                        torch.device("cpu"), (model, tokenizer))
    assert costs["forward_calls"] == 3
    assert costs["autoregressive_token_forward_evaluations"] == 12
    assert len(model.calls) == 3
