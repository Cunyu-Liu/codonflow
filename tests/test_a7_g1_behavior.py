from scripts.a7_g1_behavior import behavior_metrics, passes_g1


def test_behavior_metrics_accepts_diverse_legal_outputs():
    source = "ATGGCTTAA"
    sequences = [source] + ["ATGGCCTAA"] * 99
    row = behavior_metrics(source, sequences, ["ATGGCTTAA"])
    assert row["identity_legal"] == 1.0
    assert row["non_source_rate"] == 0.99
    assert row["n_unique"] == 2
    assert row["max_single_frequency"] == 0.99
    assert row["uniform_exact_overlap"] == 1
    assert not passes_g1(row)


def test_behavior_metrics_rejects_source_collapse():
    source = "ATGGCTTAA"
    row = behavior_metrics(source, [source] * 100, [source] * 100)
    assert row["non_source_rate"] == 0
    assert row["n_unique"] == 1
    assert row["max_single_frequency"] == 1
    assert row["uniform_exact_overlap"] == 1
    assert not passes_g1(row)


def test_non_source_rate_is_measured_from_paired_random_initialization():
    source = "ATGGCTTAA"
    initial = "ATGGCGTAA"
    row = behavior_metrics(source, [initial] * 100, [initial] * 100, [initial] * 100)
    assert row["identity_legal"] == 1.0
    assert row["non_source_rate"] == 0.0
    assert not passes_g1(row)
