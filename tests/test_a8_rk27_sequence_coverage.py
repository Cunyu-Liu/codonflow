from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "a8_rk27_audit_sequence_coverage.py"
SPEC = importlib.util.spec_from_file_location("rk27_coverage", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_protocol_is_frozen_and_retrospective() -> None:
    protocol = json.loads((ROOT / "audits/20261121/RK27/a8_rk27_kudla_sequence_cluster_ood_protocol_v1.json").read_text())
    assert protocol["status"] == "FROZEN_BEFORE_ANY_RK27_MODEL_FIT_OR_NEW_EXPRESSION_ASSOCIATION"
    assert protocol["scientific_boundaries"]["labels_previously_used_in_RK22_development"] is True
    assert protocol["scientific_boundaries"]["functional_untouched_read"] is False
    assert protocol["scientific_boundaries"]["generator_training_authorized"] is False
    assert protocol["primary_inference"]["cluster_bootstrap"]["resamples"] == 20000
    assert protocol["primary_inference"]["cluster_swap_permutation"]["permutations"] == 20000


def test_label_free_columns_are_disjoint_from_forbidden() -> None:
    protocol = json.loads((ROOT / "audits/20261121/RK27/a8_rk27_kudla_sequence_cluster_ood_protocol_v1.json").read_text())
    audit = protocol["label_free_coverage_audit"]
    assert set(audit["columns_permitted"]) == {"source_row", "cds", "protein_aa"}
    assert not set(audit["columns_permitted"]).intersection(audit["columns_forbidden"])


def test_balanced_fold_sizes_is_deterministic() -> None:
    labels = np.repeat(np.arange(1, 8), [12, 10, 8, 6, 4, 2, 1])
    first = MODULE.balanced_fold_sizes(labels, 20261221)
    second = MODULE.balanced_fold_sizes(labels, 20261221)
    assert first == second
    assert sum(first) == len(labels)
    assert len(first) == 5


def test_balanced_fold_sizes_handles_equal_clusters() -> None:
    labels = np.repeat(np.arange(1, 11), 3)
    loads = MODULE.balanced_fold_sizes(labels, 7)
    assert loads == [6, 6, 6, 6, 6]
