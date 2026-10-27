"""Exact finite-state Doob tests and lightweight synonymous adapter tests."""
import math

import numpy as np
import pytest
import torch
from scipy.special import logsumexp

from codonflow.core.codon import (
    CODON_TO_INDEX,
    STANDARD_TABLE_1,
    SYNONYMOUS_CODONS,
    is_synonymous,
    is_valid_cds,
    split_codons,
)
from codonflow.models.synonymous_markov import (
    FiniteStepSynonymousMarkovEditor,
    SynonymousJumpProposal,
    SynonymousTransition,
    exact_doob_transitions,
)


class DeterministicCodonModel(torch.nn.Module):
    """Small logits-only stand-in; no checkpoint or stochastic layers."""

    def forward(self, ids):
        batch, length = ids.shape
        rows = torch.arange(length, dtype=torch.float32).unsqueeze(0)
        blank = 0.17 * rows.expand(batch, -1)
        tokens = torch.full((batch, length, 67), -2.0)
        for codon_id in range(64):
            tokens[:, :, codon_id] = 0.013 * codon_id
        return blank, tokens


class IndependentReward:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def __call__(self, sequences):
        self.calls.append(tuple(sequences))
        return [self.values.get(s, 0.0) for s in sequences]


def protein_synonyms(codon):
    return SYNONYMOUS_CODONS[STANDARD_TABLE_1[codon]]


def test_exact_backward_recursion_and_terminal_doob_distribution():
    # Two states, four steps, full support.  All calculations are exhaustive.
    states = ("TTTTAA", "TTCTAA")
    assert is_synonymous(*states)
    assert all(is_valid_cds(s) for s in states)
    q = np.array([[0.7, 0.3], [0.2, 0.8]], dtype=np.float64)
    terminal_g = np.array([2.0, 5.0])
    terminal_step = 4
    h = np.zeros((terminal_step + 1, 2))
    h[terminal_step] = terminal_g
    for step in range(terminal_step - 1, -1, -1):
        h[step] = q @ h[step + 1]
        assert np.allclose(h[step], q @ h[step + 1], rtol=1e-14, atol=1e-14)

    base = np.eye(2)
    tilted = np.eye(2)
    for step in range(terminal_step):
        base = base @ q
        guided_q = np.empty_like(q)
        for source in range(2):
            log_guided = exact_doob_transitions(
                np.log(q[source]).tolist(),
                np.log(h[step + 1]).tolist(),
                math.log(h[step, source]),
            )
            guided_q[source] = np.exp(log_guided)
        assert np.allclose(guided_q.sum(axis=1), 1.0, atol=1e-14)
        tilted = tilted @ guided_q

    for source in range(2):
        expected = base[source] * terminal_g / h[0, source]
        assert np.allclose(tilted[source], expected, rtol=1e-12, atol=1e-12)
        assert math.isclose(tilted[source].sum(), 1.0, abs_tol=1e-12)


def test_exact_doob_helper_rejects_nonharmonic_value():
    with pytest.raises(ValueError, match="harmonic"):
        exact_doob_transitions([math.log(0.5), math.log(0.5)], [0.0, 0.0], 1.0)


def test_model_adapter_full_joint_normalization_and_synonymy():
    source = "TTTGCTTAA"  # F has two alternatives; A has four; stop is fixed.
    proposal = SynonymousJumpProposal(DeterministicCodonModel())
    transitions = proposal.enumerate_transitions(split_codons(source), time=0.25)
    expected_count = 1 + sum(len(protein_synonyms(c)) - 1 for c in split_codons(source)[:-1])
    assert len(transitions) == expected_count
    assert math.isclose(logsumexp([t.log_probability for t in transitions]), 0.0, abs_tol=1e-12)
    assert sum(t.is_stay for t in transitions) == 1
    assert len({t.codons for t in transitions}) == len(transitions)
    for transition in transitions:
        sequence = transition.sequence
        assert is_valid_cds(sequence)
        assert is_synonymous(sequence, source)
        assert sequence[-3:] == "TAA"
        differences = [i for i, (a, b) in enumerate(zip(split_codons(source), transition.codons)) if a != b]
        assert len(differences) == (0 if transition.is_stay else 1)
        if not transition.is_stay:
            assert transition.codons[transition.position] in protein_synonyms(source[3 * transition.position : 3 * transition.position + 3])


def test_stay_probability_logsumexp_not_logit_sum():
    source = "TTTTAA"

    class StayModel(DeterministicCodonModel):
        def forward(self, ids):
            batch, length = ids.shape
            blank = torch.zeros((batch, length))
            tokens = torch.full((batch, length, 67), -10.0)
            # Position 1: strong change; position 2: strong stay.
            blank[0, 1] = 0.0
            blank[0, 2] = 0.0
            tokens[0, 1, CODON_TO_INDEX["TTT"]] = 0.0
            tokens[0, 2, CODON_TO_INDEX["TTC"]] = 0.0  # TTT stays TTT; TTC is the only alternative.
            return blank, tokens

    transitions, log_probabilities = SynonymousJumpProposal(StayModel())._transition_tensors(split_codons(source))
    stay_index = next(i for i, transition in enumerate(transitions) if transition.is_stay)
    assert math.isclose(sum(math.exp(float(p)) for p in log_probabilities), 1.0, abs_tol=1e-10)
    assert math.isclose(float(log_probabilities[stay_index]), 0.0, abs_tol=1e-3)


def test_model_adapter_rejects_invalid_sources():
    proposal = SynonymousJumpProposal(DeterministicCodonModel())
    for invalid in ("ATG", "ATGTAGTAA", "ATGN", "ATGTA", ""):
        with pytest.raises(ValueError):
            proposal.enumerate_transitions(split_codons(invalid) if invalid else [])


def test_sample_transition_fixed_rng_reproducibility():
    source = split_codons("TTTGCTTAA")
    proposal = SynonymousJumpProposal(DeterministicCodonModel())
    first = proposal.sample_transition(source, 0, np.random.default_rng(19))
    second = proposal.sample_transition(source, 0, np.random.default_rng(19))
    assert first == second


def test_log_h_uses_independent_terminal_rollout_rewards():
    source = split_codons("TTTTAA")
    values = {"TTTTAA": math.log(2.0), "TTCTAA": math.log(8.0)}
    reward = IndependentReward(values)
    calls = {"base": 0}

    class TwoTerminalProposal(SynonymousJumpProposal):
        def enumerate_transitions(self, codons, time=0):
            other = ("TTC", "TAA")
            # Uniform base terminal law gives h=(2+8)/2=5, unlike immediate G=2.
            return [
                SynonymousTransition(source, math.log(0.5), None),
                SynonymousTransition(other, math.log(0.5), 0),
            ]

    proposal = TwoTerminalProposal(DeterministicCodonModel())

    def counted_sample(codons, time=0, rng=None):
        # Balanced deterministic draws make the Monte-Carlo identity exact.
        calls["base"] += 1
        codons = source if calls["base"] % 2 else ("TTC", "TAA")
        return SynonymousTransition(codons, math.log(0.5), None)

    proposal.sample_transition = counted_sample
    editor = FiniteStepSynonymousMarkovEditor(
        proposal, reward, terminal_step=1, rollout_count=8, rng=np.random.default_rng(3)
    )
    assert math.isclose(editor.estimate_log_h(source, 0), math.log(5.0), abs_tol=1e-12)
    assert calls["base"] == 8
    assert editor.unique_terminal_reward_calls == 2


def test_rollout_guidance_is_not_immediate_atc_and_counts_budget():
    source = "TTTGCTTAA"
    # This is an independent known terminal potential, not an ATC utility.
    values = {
        "TTTGCTTAA": math.log(2.0),
        "TTTGCCTAA": math.log(7.0),
        "TTTGCATAA": math.log(3.0),
        "TTTGCGTAA": math.log(4.0),
        "TTCGCTTAA": math.log(5.0),
    }
    default_values = {sequence: 0.0 for sequence in (
        "TTTGCTTAA", "TTTGCCTAA", "TTTGCATAA", "TTTGCGTAA", "TTCGCTTAA"
    )}
    default_values.update(values)
    reward = IndependentReward(default_values)
    editor = FiniteStepSynonymousMarkovEditor(
        SynonymousJumpProposal(DeterministicCodonModel()),
        reward,
        terminal_step=2,
        rollout_count=3,
        candidate_count=3,
        rng=np.random.default_rng(11),
    )
    guided, current_log_h, candidate_log_h = editor.guided_transitions(split_codons(source), 0)
    assert editor.mode == "rollout"
    assert len(guided) == 3
    assert math.isclose(logsumexp([t.log_probability for t in guided]), 0.0, abs_tol=1e-12)
    assert len(candidate_log_h) == len(guided)
    assert math.isfinite(current_log_h)
    assert editor.unique_terminal_reward_calls > 0
    assert editor.proposal.forward_calls > 0
    assert reward.calls  # Actual terminal reward calls, not immediate ATC substitution.


def test_sampling_reproducibility_trace_and_incumbent_opt_in():
    source = "TTTGCTTAA"
    possible = [
        "TTTGCTTAA", "TTCGCTTAA", "TTTGCCTAA", "TTTGCATAA", "TTTGCGTAA",
        "TTCGCCTAA", "TTCGCATAA", "TTCGCGTAA",
    ]
    rewards = {s: float(i) for i, s in enumerate(possible)}

    def run(incumbent=False, proposal=None):
        reward = IndependentReward(rewards)
        editor = FiniteStepSynonymousMarkovEditor(
            proposal or SynonymousJumpProposal(DeterministicCodonModel()),
            reward,
            terminal_step=2,
            rollout_count=2,
            candidate_count=2,
            rng=np.random.default_rng(23),
        )
        terminal, trace = editor.sample(source, return_incumbent=incumbent)
        return terminal, trace, editor

    first, trace, editor = run()
    per_path_forwards = editor.proposal.forward_calls
    second, second_trace, second_editor = run(proposal=editor.proposal)
    assert editor.proposal.forward_calls == 2 * per_path_forwards
    assert second_editor.proposal.forward_calls == 2 * per_path_forwards
    assert first == second
    assert trace == second_trace
    assert first == trace[-1]["sequence"]  # Default is the trajectory terminal.
    assert is_valid_cds(first) and is_synonymous(first, source)
    assert len(trace) == 2
    assert trace[-1]["mode"] == "rollout"
    assert trace[-1]["unique_terminal_reward_calls"] > 0
    assert trace[-1]["forward_calls"] > 0
    assert editor.terminal_reward_evaluations >= editor.unique_terminal_reward_calls
    assert trace[-1]["chosen_base_log_probability"] == pytest.approx(-0.47174700857447993)

    incumbent, _, incumbent_editor = run(incumbent=True)
    assert incumbent == incumbent_editor.best_terminal
    assert rewards[incumbent] == incumbent_editor.best_terminal_reward


def test_rollout_zero_is_explicit_immediate_ablation():
    source = split_codons("TTTTAA")
    reward = IndependentReward({"TTTTAA": math.log(2.0), "TTCTAA": math.log(8.0)})
    proposal = SynonymousJumpProposal(DeterministicCodonModel())
    editor = FiniteStepSynonymousMarkovEditor(
        proposal, reward, terminal_step=2, rollout_count=0, rng=np.random.default_rng(0)
    )
    before = proposal.forward_calls
    assert editor.mode == "immediate"
    assert editor.estimate_log_h(source, 0) == math.log(2.0)
    assert proposal.forward_calls == before


def test_sampled_path_log_probability_is_normalized_and_differentiable():
    source = "TTTGCTTAA"
    model = DeterministicCodonModel()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    blank_bias = torch.nn.Parameter(torch.zeros(12))
    token_bias = torch.nn.Parameter(torch.zeros(67))

    def forward(ids):
        batch, length = ids.shape
        blank = blank_bias[:length].unsqueeze(0).expand(batch, -1)
        tokens = token_bias.unsqueeze(0).unsqueeze(0).expand(batch, length, -1)
        return blank, tokens

    model.forward = forward
    proposal = SynonymousJumpProposal(model)
    initial = "TTCGCTTAA"
    terminal = "TTTGCTTAA"
    lp = proposal.sampled_path_log_probability(initial, [initial, terminal])
    assert torch.isfinite(lp)
    lp.backward()
    assert blank_bias.grad is not None and token_bias.grad is not None
    assert torch.isfinite(blank_bias.grad).all()
    assert torch.isfinite(token_bias.grad).all()
    with pytest.raises(ValueError, match="non-local"):
        proposal.sampled_path_log_probability(initial, [initial, "TTTGCTTAA", "TTCGCCTAA"])


def test_terminal_step_and_infeasible_reward_behavior():
    source = "TTTTAA"
    reward = IndependentReward({source: -math.inf, "TTCTAA": -math.inf})
    editor = FiniteStepSynonymousMarkovEditor(
        SynonymousJumpProposal(DeterministicCodonModel()),
        reward,
        terminal_step=0,
        rng=np.random.default_rng(0),
    )
    terminal, trace = editor.sample(source)
    assert terminal == source and trace == []
    with pytest.raises(ValueError, match="No feasible"):
        editor.sample(source, return_incumbent=True)
