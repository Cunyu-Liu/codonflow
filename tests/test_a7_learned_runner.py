import numpy as np

from codonflow.core.codon import gc_fraction
from codonflow.models.synonymous_markov import SynonymousTransition
from scripts.a7_run_learned import learned_search


class TinyProposal:
    def __init__(self):
        self.forward_calls = 0

    def validate_source(self, codons):
        return tuple(codons)

    def enumerate_transitions(self, codons, step=0, count_forward=True):
        if count_forward:
            self.forward_calls += 1
        current = list(codons)
        alternatives = [current]
        for codon in ["GCA", "GCC", "GCG", "GCT"]:
            edited = current.copy()
            edited[1] = codon
            if edited != current:
                alternatives.append(edited)
        log_probability = float(np.log(1 / len(alternatives)))
        return [SynonymousTransition(tuple(state), log_probability, None if state == current else 1)
                for state in alternatives]

    def sample_transition_batch(self, states, step, rng):
        self.forward_calls += 1
        return [rng.choice(self.enumerate_transitions(state, count_forward=False)) for state in states]


def test_learned_base_uses_unique_terminal_budget_and_paired_start():
    proposal = TinyProposal()
    initial = "ATGGCTTAA"
    result = learned_search(initial, proposal, lambda sequence: [gc_fraction(sequence)],
                            [1], ([0], [1]), seed=3, max_unique_scorer=4)
    assert result["status"] == "done"
    assert len(result["points"]) == 4
    assert len(set(point["sequence"] for point in result["points"])) == 4
    assert result["points"][0]["sequence"] == initial
    assert [point["budget"] for point in result["points"]] == [1, 2, 3, 4]
    assert result["costs"]["forward_calls"] == proposal.forward_calls
    assert result["costs"]["rollout_batch_forwards"] == 0
