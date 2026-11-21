#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import a8_rk30_download_hela_r1 as download
import a8_rk30_fixed_reference_counts as counter
import a8_rk02_mordstein_reference_recovery as recovery

PROTOCOL_PATH = Path(os.environ["RK30_PROTOCOL"])


def protocol():
    return json.loads(PROTOCOL_PATH.read_text())


def synthetic_counts(p):
    variant_ids = pd.read_csv(p["inputs"]["reference_csv"]["path"], usecols=["variant_id"])["variant_id"].tolist()
    rows = []
    for variant_index, variant_id in enumerate(variant_ids):
        for context, definition in p["contexts"].items():
            for replicate in definition["replicates"]:
                for bin_number in range(1, 9):
                    rows.append({"variant_id": variant_id, "context": context,
                                 "replicate": replicate, "run": f"{replicate}_{bin_number}",
                                 "bin": bin_number, "count": 125 + variant_index + bin_number})
    return pd.DataFrame(rows)


def test_flow_score_and_input_validation():
    assert counter.flow_score([1, 0, 0, 0, 0, 0, 0, 0]) == 1.0
    assert counter.flow_score([0, 0, 0, 0, 0, 0, 0, 2]) == 8.0
    assert counter.flow_score([100] * 8) == 4.5
    with pytest.raises(ValueError):
        counter.flow_score([0] * 8)
    with pytest.raises(ValueError):
        counter.flow_score([1] * 7)


def test_unique_nearest_assignment_boundaries():
    refs = ["A" * 300, "C" * 300]
    assigner = recovery.SeedAssigner(refs, 8)
    assert assigner.assign("A" * 300) == 0
    assert assigner.assign("A" * 292 + "C" * 8) == 0
    assert assigner.assign("A" * 291 + "C" * 9) is None
    assert assigner.assign("C" * 300) == 1
    assert assigner.assign("A" * 299) is None


def test_metadata_exactly_64_r1_runs_without_reading_fastq():
    runs = counter.parse_runs(protocol(), require_files=False)
    assert len(runs) == 64
    assert {(r["context"], r["replicate"], r["bin"]) for r in runs} == {
        (context, rep, b) for context, definition in protocol()["contexts"].items()
        for rep in definition["replicates"] for b in range(1, 9)}
    assert all(r["r2"] is None for r in runs)


def test_download_selects_56_hela_r1_only_and_exact_bytes(tmp_path):
    p = protocol()
    jobs = download.jobs_from_metadata(Path(p["inputs"]["metadata_tsv"]["path"]), tmp_path, [])
    assert len(jobs) == 56
    assert sum(j["expected_bytes"] for j in jobs) == p["download"]["expected_new_r1_bytes"]
    assert {j["mate"] for j in jobs} == {1}
    assert all(j["token"].endswith("_1") for j in jobs)
    assert all("HeLa" in j["experiment_title"] for j in jobs)
    assert all(j["path"].with_suffix(j["path"].suffix + ".part").exists() for j in jobs)


def test_common_cohort_requires_every_replicate():
    p = protocol()
    counts = synthetic_counts(p)
    failed_variant = counts["variant_id"].iloc[0]
    mask = ((counts["variant_id"] == failed_variant) &
            (counts["context"] == "hela_no_intron") &
            (counts["replicate"] == "CM5a"))
    counts.loc[mask, "count"] = 0
    outcomes, diagnostics = counter.outcome_table(counts, p)
    assert len(outcomes) == 151
    assert failed_variant not in set(outcomes["variant_id"])
    assert diagnostics["coverage_feasible"]
    assert diagnostics["context_pass_counts"]["hela_no_intron"] == 151
    assert diagnostics["context_pass_counts"]["hela_with_intron"] == 152


def test_context_score_is_unweighted_replicate_mean():
    p = protocol()
    counts = synthetic_counts(p)
    outcomes, diagnostics = counter.outcome_table(counts, p)
    rep = diagnostics["replicate_scores"]
    selected_variant = counts["variant_id"].drop_duplicates().iloc[1]
    expected = (rep[(rep["variant_id"] == selected_variant) & (rep["context"] == "hela_no_intron")]
                ["replicate_score"].mean())
    actual = outcomes.loc[outcomes["variant_id"] == selected_variant, "target__hela_no_intron"].iloc[0]
    assert abs(expected - actual) < 1e-12


def test_coverage_failure_is_prefixed_and_deterministic():
    p = protocol()
    counts = synthetic_counts(p)
    failed_variants = counts["variant_id"].drop_duplicates().iloc[:60]
    counts.loc[counts["variant_id"].isin(failed_variants), "count"] = 0
    outcomes, diagnostics = counter.outcome_table(counts, p)
    assert len(outcomes) == 92
    assert not diagnostics["coverage_feasible"]


def test_frozen_model_arithmetic_and_transport_pairs():
    p = protocol()
    pairs = p["primary_transport"]["ordered_pairs"]
    assert len(pairs) == 4
    assert len({(x["source"], x["target"]) for x in pairs}) == 4
    assert 4 * 10 * 5 * 4 == p["models"]["expected_transport_fits"] == 800
    assert 3 * 10 * 5 * 6 == p["models"]["expected_within_context_fits"] == 900
    assert p["models"]["expected_total_fits"] == 1700


def test_no_posthoc_threshold_or_untouched_authorization():
    p = protocol()
    assert p["outcome_and_qc"]["minimum_assigned_reads_per_variant_per_replicate"] == 1000
    assert p["outcome_and_qc"]["minimum_common_variants"] == 100
    assert p["outcome_and_qc"]["minimum_common_clusters"] == 50
    assert not p["scientific_boundaries"]["functional_untouched_read"]
    assert not p["scientific_boundaries"]["generator_training_authorized"]


def test_reference_and_cluster_facts_are_label_free_and_aligned():
    p = protocol()
    ref = pd.read_csv(p["inputs"]["reference_csv"]["path"], usecols=["variant_id", "sequence_5prime_300nt"])
    facts = pd.read_csv(p["inputs"]["cluster_facts_csv"]["path"])
    assert len(ref) == 152 and ref["variant_id"].is_unique
    assert ref["sequence_5prime_300nt"].str.len().eq(300).all()
    assert len(facts) == 152 and facts["sequence_cluster_id"].nunique() == 74
    assert set(ref["variant_id"]) == set(facts["variant_id"])
