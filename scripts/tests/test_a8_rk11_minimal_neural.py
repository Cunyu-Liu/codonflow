from __future__ import annotations

import math

import torch

from codonflow.core.codon import AA_OF_INDEX, CODON_TO_INDEX
from codonflow.models.minimal_neural import (
    FIXED_TERMINAL_STOP,
    MinimalCodonFlowRK,
    MinimalNeuralConfig,
    enumerate_legal_single_edit,
    exact_conditional_kernel,
    multifidelity_loss,
)


def source() -> torch.Tensor:
    return torch.tensor([
        CODON_TO_INDEX["ATG"], CODON_TO_INDEX["CTT"],
        CODON_TO_INDEX["GCT"], FIXED_TERMINAL_STOP,
    ])


def model() -> MinimalCodonFlowRK:
    torch.manual_seed(7)
    return MinimalCodonFlowRK(MinimalNeuralConfig())


def kernel(m=None, remaining=1.0, beta=0.75, beta_cost=0.1, preferences=None):
    m = m or model()
    preferences = torch.zeros(4) if preferences is None else preferences
    return exact_conditional_kernel(
        m, source(), 1, 0.5, torch.tensor([0, 1, 2, 3, 4]),
        preferences, remaining, beta=beta, beta_cost=beta_cost,
    )


def test_single_edit_states_are_unique_synonymous_and_stop_safe():
    x = source()
    candidates = enumerate_legal_single_edit(x)
    assert candidates.shape == (9, 4)
    assert torch.equal(candidates[0], x)
    assert len({tuple(row) for row in candidates.tolist()}) == len(candidates)
    for row in candidates:
        assert row[-1] == FIXED_TERMINAL_STOP
        assert all(AA_OF_INDEX[int(value)] != "*" for value in row[:-1])
        assert [AA_OF_INDEX[v] for v in row[:-1]] == [AA_OF_INDEX[int(v)] for v in x[:-1]]
        assert sum(a != b for a, b in zip(row, x.tolist())) <= 1


def test_terminal_stop_and_internal_stop_guards():
    bad = source().clone(); bad[-1] = CODON_TO_INDEX["TAA"]
    try:
        enumerate_legal_single_edit(bad)
        assert False, "wrong terminal stop accepted"
    except ValueError:
        pass
    bad = source().clone(); bad[1] = CODON_TO_INDEX["TAG"]
    try:
        enumerate_legal_single_edit(bad)
        assert False, "internal stop accepted"
    except ValueError:
        pass


def test_three_nucleotide_expansion_and_utr_pair_shapes():
    result = kernel()
    assert result["nucleotide_hidden"].shape == (9, 4, 3, 16)
    assert result["utr_pair"].shape == (9, 4, 5)
    assert torch.isfinite(result["nucleotide_hidden"]).all()


def test_zero_temperature_is_uniform_over_feasible_states():
    result = kernel(beta=0.0, beta_cost=0.0)
    expected = -math.log(9)
    assert torch.allclose(result["log_probabilities"], torch.full((9,), expected), atol=1e-6)
    assert math.isclose(result["log_probabilities"].exp().sum().item(), 1.0, abs_tol=1e-6)


def test_budget_is_a_hard_mask_not_a_soft_penalty():
    result = kernel(remaining=0.42)
    assert bool(result["allowed"][0])
    assert (~result["allowed"]).any()
    assert torch.isinf(result["log_probabilities"][~result["allowed"]]).all()
    assert (result["log_probabilities"][~result["allowed"]] < 0).all()
    assert (result["cost"][result["allowed"]] <= 0.42 + 1e-7).all()


def test_kernel_matches_independent_logit_reconstruction():
    result = kernel(preferences=torch.tensor([0.7, -0.25, 0.45, -0.15]))
    logits = -math.log(9) - 0.75 * (result["delta_phi"] * torch.tensor([0.7, -0.25, 0.45, -0.15])).sum(1) - 0.1 * result["delta_cost"]
    manual = torch.log_softmax(logits, dim=0)
    assert torch.allclose(manual, result["log_probabilities"], atol=1e-6)
    assert torch.count_nonzero(result["delta_phi"][0]) == 0
    assert result["delta_cost"][0] == 0


def test_multifidelity_masks_weights_and_heteroscedastic_function():
    m = model().double()
    x = source().repeat(3, 1)
    out = m(x, torch.tensor([0, 1, 2]), torch.tensor([0.2, 0.5, 0.8], dtype=torch.float64), torch.tensor([0, 1, 2, 3, 4]).repeat(3, 1))
    targets = torch.randn(3, 4, dtype=torch.float64)
    mask = torch.ones(3, 4, dtype=torch.bool); mask[0, 0] = False
    total, terms = multifidelity_loss(out, targets, mask, torch.tensor([0, 1, 2]), m.fidelity_weights)
    assert torch.isfinite(total) and total > 0
    assert terms["masked_values"] == 11
    zero, _ = multifidelity_loss(out, out["potentials"].detach(), mask, torch.tensor([0, 1, 2]), m.fidelity_weights)
    assert torch.isfinite(zero)


def test_kernel_is_differentiable_through_potential_heads():
    m = model()
    result = kernel(m=m, preferences=torch.tensor([0.7, -0.25, 0.45, -0.15]))
    loss = -result["log_probabilities"][0]
    loss.backward()
    gradients = [p.grad for p in m.parameters() if p.grad is not None]
    assert gradients
    assert all(torch.isfinite(g).all() for g in gradients)
    assert any(torch.count_nonzero(g) for g in gradients)


def test_length_five_contract_without_length_generalization_claim():
    m = model()
    x = torch.tensor([CODON_TO_INDEX[c] for c in ["ATG", "CTT", "GCT", "TTT"]] + [FIXED_TERMINAL_STOP])
    candidates = enumerate_legal_single_edit(x)
    out = m(candidates, torch.zeros(len(candidates), dtype=torch.long), torch.full((len(candidates),), 0.5), torch.tensor([0, 1, 2, 3, 4]).repeat(len(candidates), 1))
    assert out["potentials"].shape == (len(candidates), 4)
    assert torch.isfinite(out["potentials"]).all()


def test_invalid_vocabulary_and_fidelity_ids_fail_closed():
    m = model()
    bad = source().repeat(1, 1); bad[0, 0] = 64
    try:
        m.expand_nucleotides(bad)
        assert False, "invalid token accepted"
    except ValueError:
        pass
    out = m(source().repeat(2, 1), torch.zeros(2, dtype=torch.long), torch.zeros(2), torch.tensor([0, 1, 2, 3, 4]).repeat(2, 1))
    try:
        multifidelity_loss(out, torch.zeros(2, 4), torch.ones(2, 4), torch.tensor([0, 9]), m.fidelity_weights)
        assert False, "invalid fidelity accepted"
    except ValueError:
        pass
