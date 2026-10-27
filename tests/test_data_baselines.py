"""Synthetic regression tests for benchmark identity and leakage audits."""
import json
import random
import sys

import pytest

from scripts.audit_distribution import histogram, overlap_audit
from scripts.audit_homology_split import audit_homology_split
from scripts.build_a6_benchmark import build_unique_benchmark
from scripts.build_a6_benchmark import main as build_benchmark_main
from scripts.build_protein_homology_inputs import build_protein_fasta
from scripts.build_splits import benchmark_components, read_fasta, read_clusters
from scripts.gemorna_arm import (
    load_benchmark_protein,
    main as gemorna_main,
    protein_sha256,
    score_solutions,
)
from scripts.gemorna_ood_score import parse_raw_solutions
from scripts.build_splits import main as build_splits_main


def write_fasta(path, records):
    path.write_text("".join(f">{header}\n{seq}\n" for header, seq in records))
    return str(path)


def fixture_cds_pool():
    from scripts.gemorna_arm import cds_protein
    codons = ["TTT", "TTG", "ATT", "GCT", "GGT"]
    pool = [f"ATG{a}{b}TAA" for a in codons for b in codons]
    assert len({cds_protein(s) for s in pool}) == len(pool)
    return pool


def test_unique_benchmark_replaces_absent_and_duplicate_records_only_from_test(tmp_path, monkeypatch):
    valid = fixture_cds_pool()[:18]
    legacy = [(f"id{i}|sp|short|12nt", s) for i, s in enumerate(valid)]
    replacement = (
        "absent_replacement|sp|short|15nt",
        fixture_cds_pool()[18][:-3] + "GCTTAA",
    )
    test = legacy[1:] + [replacement]
    legacy_path = write_fasta(tmp_path / "legacy.fasta", legacy)
    test_path = write_fasta(tmp_path / "test.fasta", test)
    out, manifest = tmp_path / "frozen.fasta", tmp_path / "manifest.json"
    monkeypatch.setattr(sys, "argv", [
        "build_a6_benchmark.py", "--legacy-fasta", legacy_path, "--test-fasta", test_path,
        "--out-fasta", str(out), "--out-manifest", str(manifest),
    ])
    build_benchmark_main()
    records, audit = build_unique_benchmark(legacy_path, test_path)
    assert records == read_fasta(str(out))
    assert len(records) == len({s for _, s in records}) == 18
    assert all(dict(test).get(h) == s for h, s in records)
    assert records[0] == replacement
    assert audit[0]["reason"] == "legacy record absent from frozen v4 test"
    assert audit[1]["reason"] == "exact legacy record retained in frozen v4 test"
    assert json.loads(manifest.read_text())["protocol"] == "v4_test_unique18_length_stratified_v2"


def test_unique_benchmark_replaces_duplicate_with_deterministic_tiebreak(tmp_path):
    pool = fixture_cds_pool()
    valid = [pool[0], "ATGTTCTTTTAA", *pool[1:17]]
    legacy = [(f"id{i}|sp|short|12nt", s) for i, s in enumerate(valid)]
    candidates = [("z|sp|short|12nt", pool[19]), ("a|sp|short|12nt", pool[18])]
    records, audit = build_unique_benchmark(
        write_fasta(tmp_path / "legacy.fasta", legacy),
        write_fasta(tmp_path / "test.fasta", legacy + candidates),
    )
    assert len(records) == len({s for _, s in records}) == 18
    assert records[1] == candidates[1]
    assert audit[1]["reason"].startswith("duplicate legacy")


def test_unique_benchmark_fails_if_stratum_cannot_be_filled(tmp_path):
    legacy = [(f"id{i}|sp|short|12nt", s) for i, s in enumerate(fixture_cds_pool()[:18])]
    with pytest.raises(ValueError, match="no unused frozen-test candidate"):
        build_unique_benchmark(
            write_fasta(tmp_path / "legacy.fasta", legacy),
            write_fasta(tmp_path / "test.fasta", legacy[:-1]),
        )

def test_protein_homology_inputs_include_external_benchmark_once(tmp_path):
    corpus = write_fasta(tmp_path / "corpus.fasta", [
        ("a", "ATGAAATTTTGA"), ("duplicate", "ATGAAGTTCTGA"), ("c", "ATGGCTTAA"),
    ])
    benchmark = write_fasta(tmp_path / "benchmark.fasta", [
        ("external", "ATGCAATAA"), ("same_protein", "ATGAAGTTCTGA"),
    ])
    manifest = build_protein_fasta(
        [corpus], [benchmark], tmp_path / "proteins.fasta", tmp_path / "manifest.json",
    )
    assert manifest["n_unique_proteins"] == 3
    assert manifest["n_benchmark_seed_proteins"] == 1
    assert [row["id"] for row in manifest["records"]] == ["a", "c", "benchmark__external"]
    assert len(manifest["protein_fasta_sha256"]) == 64


def test_external_benchmark_identifier_excludes_its_homology_component():
    seqs = {"a": "ATGAAATTTTGA", "homolog": "ATGGCTTAA"}
    clusters = {"benchmark__external": ["homolog"], "a": ["a"]}
    excluded, report = benchmark_components(
        clusters, seqs, [("external", "ATGCAATAA")],
    )
    assert excluded == {"homolog"}
    assert report["n_identifier_matched"] == 1
    assert report["n_exact_protein_matched"] == 0


def test_homology_audit_checks_external_components_and_conservation(tmp_path):
    original = write_fasta(tmp_path / "original.fasta", [
        ("a", "ATGAAATTTTGA"), ("b", "ATGGCTTAA"), ("c", "ATGTTTTAA"),
    ])
    benchmark = write_fasta(tmp_path / "benchmark.fasta", [("external", "ATGCAATAA")])
    clusters = tmp_path / "clusters.tsv"
    clusters.write_text("a\ta\nbenchmark__external\tb\nc\tc\n")
    excluded = write_fasta(tmp_path / "excluded.fasta", [("b", "ATGGCTTAA")])
    split_dir = tmp_path / "splits"
    split_dir.mkdir()
    write_fasta(split_dir / "train.fasta", [("a", "ATGAAATTTTGA")])
    write_fasta(split_dir / "val.fasta", [("c", "ATGTTTTAA")])
    write_fasta(split_dir / "test.fasta", [])
    (split_dir / "split_audit.json").write_text(json.dumps({
        "n_input_seqs": 3, "n_retained_input_records": 2,
        "n_removed_as_protein_duplicates": 0,
        "benchmark_exclusion": {"n_excluded_cds": 1},
    }))
    report = audit_homology_split(split_dir, str(clusters), [benchmark], original, excluded)
    assert report["n_retained"] == 2
    assert report["n_benchmark_cluster_representatives"] == 1
    assert all(report["checks"].values())
    write_fasta(tmp_path / "excluded.fasta", [])
    write_fasta(split_dir / "train.fasta", [("b", "ATGGCTTAA")])
    with pytest.raises(ValueError, match="benchmark protein clusters"):
        audit_homology_split(split_dir, str(clusters), [benchmark], original, excluded)


def test_benchmark_fasta_is_authoritative(tmp_path):
    fasta = write_fasta(tmp_path / "bench.fasta", [
        ("egfp_P42212_syn", "ATGGCTTAA"),
        ("nluc_JQ437370.1", "ATGAAATTTTGA"),
    ])
    header, protein = load_benchmark_protein(fasta, "nluc")
    assert header == "nluc_JQ437370.1"
    assert protein == "MKF"
    assert protein_sha256(protein) == protein_sha256("MKF")
    with pytest.raises(ValueError, match="exactly one"):
        load_benchmark_protein(fasta, "missing")


def test_single_record_benchmark_supports_transcript_header(tmp_path):
    fasta = write_fasta(tmp_path / "mouse.fasta", [("ENSMUST00000202556.4", "ATGAAATTTTGA")])
    assert load_benchmark_protein(fasta, "mouse") == ("ENSMUST00000202556.4", "MKF")


def test_invalid_benchmark_frame_fails_fast(tmp_path):
    fasta = write_fasta(tmp_path / "bad.fasta", [("nluc", "ATGAA")])
    with pytest.raises(ValueError, match="valid CDS"):
        load_benchmark_protein(fasta, "nluc")


def test_generation_records_hash_unique_and_identity_counts(tmp_path, monkeypatch):
    fasta = write_fasta(tmp_path / "bench.fasta", [("nluc_test", "ATGAAATTTTGA")])
    proteins = []
    outputs = iter([
        ("ATGAAATTT", 0.1),  # synonymous, no stop
        ("ATGAAATTT", 0.2),  # duplicate
        ("ATGGCTTAA", 0.3),  # wrong protein
    ])

    def fake_generate(protein):
        proteins.append(protein)
        return next(outputs)

    monkeypatch.setattr("scripts.gemorna_arm.run_generate", fake_generate)
    out = tmp_path / "gemorna.json"
    monkeypatch.setattr(sys, "argv", [
        "gemorna_arm.py", "--gene", "nluc", "--benchmark-fasta", fasta,
        "--n", "3", "--out", str(out),
    ])
    gemorna_main()
    result = json.loads(out.read_text())
    assert proteins == ["MKF"] * 3
    assert result["expected_protein_sha256"] == protein_sha256("MKF")
    assert result["n_unique"] == 1
    assert result["n_invalid_identity"] == 1
    assert result["solutions"][0]["seq"] == "ATGAAATTT"


def test_identity_checked_before_metrics_and_ood_deduplicated():
    solutions = [
        {"seq": "ATGAAATTT", "naturalness": 0.1},
        {"seq": "ATGAAGTTC", "naturalness": 0.2},
        {"seq": "ATGGCTTAA", "naturalness": 0.3},
        {"seq": "ATGAAAT", "naturalness": 0.4},
    ]
    mfe_inputs = []

    def fake_mfe(seqs):
        mfe_inputs.extend(seqs)
        return [-float(len(s)) for s in seqs]

    summary, scored = score_solutions(
        solutions, "MKF", mfe_fn=fake_mfe, deduplicate=True
    )
    assert summary["n_identity_pass"] == 2
    assert summary["n_unique"] == 2
    assert summary["n_invalid_identity"] == 2
    assert mfe_inputs == ["ATGAAATTTTAA", "ATGAAGTTCTAA"]
    assert [s["seq"] for s in scored] == mfe_inputs
    assert parse_raw_solutions("ATGAAATTT 0.2\n") == [{"seq": "ATGAAATTT", "naturalness": 0.2}]


def test_internal_stop_is_rejected_not_treated_as_terminal():
    summary, scored = score_solutions([{"seq": "ATGTAA", "naturalness": None}], "MKF")
    assert summary["n_invalid_identity"] == 1
    assert scored == []


def test_benchmark_connected_component_and_unmatched_reported():
    bench = "ATGAAATTTTGA"
    synonymous = "ATGAAGTTCTGA"
    other = "ATGGCTTAA"
    seqs = {"a": bench, "b": synonymous, "c": other, "d": other}
    clusters = {"a": ["b"], "b": ["c"], "d": ["d"]}
    excluded, report = benchmark_components(
        clusters, seqs, [("nluc", bench), ("unmatched", "ATGTGTTA")]
    )
    assert excluded == {"a", "b", "c"}
    assert report["n_exact_sequence_matched"] == 1
    assert report["n_exact_sequence_unmatched"] == 1
    assert report["n_connected_components"] == 1
    assert report["n_excluded_cds"] == 3


def test_synonymous_and_identifier_matches_seed_connected_exclusion():
    synonymous = "ATGAAGTTCTGA"
    seqs = {"source": synonymous, "homolog": "ATGGCTTAA", "other": "ATGTGTTA"}
    clusters = {"source": ["homolog"], "other": ["other"]}
    excluded, report = benchmark_components(
        clusters, seqs, [("source extra annotation", "ATGAAATTTTGA")]
    )
    assert excluded == {"source", "homolog"}
    assert report["n_exact_protein_matched"] == 1
    assert report["n_identifier_matched"] == 1
    assert report["n_unmatched"] == 0
    assert report["n_excluded_cds"] == 2


def test_build_splits_preserves_unaffected_cluster_assignment(tmp_path, monkeypatch):
    seqs = {"a": "ATGAAATTTTGA", "b": "ATGAAGTTCTGA", "c": "ATGGCTTAA"}
    cleaned = write_fasta(tmp_path / "cleaned.fasta", list(seqs.items()))
    clusters = tmp_path / "clusters.tsv"
    clusters.write_text("a\ta\na\tb\nc\tc\n")
    bench = write_fasta(tmp_path / "bench.fasta", [("nluc", seqs["a"])])

    def build(out_dir, benchmark=None):
        argv = [
            "build_splits.py", "--cleaned", cleaned, "--cluster-tsv", str(clusters),
            "--out-dir", str(out_dir), "--train-frac", "0.5",
        ]
        if benchmark:
            argv += ["--benchmark-fasta", benchmark]
        monkeypatch.setattr(sys, "argv", argv)
        from scripts.build_splits import main
        main()

    def expected_assignments():
        names = sorted(read_clusters(str(clusters)))
        random.Random(0).shuffle(names)
        n_train = int(len(names) * 0.5)
        n_val = max(1, int(len(names) * 0.1))
        return {
            "train": names[:n_train],
            "val": names[n_train:n_train + n_val],
            "test": names[n_train + n_val:],
        }

    expected = expected_assignments()
    with_bench = tmp_path / "with"
    build(with_bench, bench)
    unaffected_before = {
        split: seqs["c"] if "c" in expected[split] else None
        for split in ("train", "val", "test")
    }
    unaffected_after = {
        split: dict(read_fasta(str(with_bench / f"{split}.fasta"))).get("c")
        for split in ("train", "val", "test")
    }
    assert unaffected_after == unaffected_before
    assert sum(v is not None for v in unaffected_after.values()) == 1
    for split in ("train", "val", "test"):
        retained = dict(read_fasta(str(with_bench / f"{split}.fasta")))
        assert "a" not in retained and "b" not in retained
    report = json.loads((with_bench / "split_audit.json").read_text())
    assert report["benchmark_exclusion"]["n_excluded_cds"] == 2


def test_group_by_protein_removes_exact_protein_duplicates(tmp_path, monkeypatch):
    cleaned = tmp_path / "cleaned.fasta"
    cleaned.write_text(">a\nATGAAATTTTGA\n>b\nATGAAGTTCTGA\n>c\nATGGCTTAA\n")
    clusters = tmp_path / "clusters.tsv"
    clusters.write_text("a\ta\na\tb\na\tc\n")
    bench = tmp_path / "bench.fasta"
    bench.write_text(">external\nATGACATAA\n")
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", [
        "build_splits.py", "--cleaned", str(cleaned), "--cluster-tsv", str(clusters),
        "--benchmark-fasta", str(bench), "--out-dir", str(out), "--group-by-protein",
    ])
    build_splits_main()
    retained = sum((out / f"{split}.fasta").read_text().count(">") for split in ("train", "val", "test"))
    assert retained == 2
    report = json.loads((out / "split_audit.json").read_text())
    assert report["group_by_protein"] is True


def test_multiple_benchmarks_and_excluded_fasta_are_audited(tmp_path, monkeypatch):
    seqs = {"a": "ATGAAATTTTGA", "b": "ATGGCTTAA", "c": "ATGCAATAA"}
    cleaned = write_fasta(tmp_path / "cleaned.fasta", list(seqs.items()))
    clusters = tmp_path / "clusters.tsv"
    clusters.write_text("a\ta\nb\tb\nc\tc\n")
    first = write_fasta(tmp_path / "first.fasta", [("a", seqs["a"])])
    second = write_fasta(tmp_path / "second.fasta", [("b", seqs["b"])])
    excluded = tmp_path / "excluded.fasta"
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", [
        "build_splits.py", "--cleaned", cleaned, "--cluster-tsv", str(clusters),
        "--benchmark-fasta", first, second, "--out-dir", str(out),
        "--excluded-out-fasta", str(excluded), "--train-frac", "0.5",
    ])
    build_splits_main()
    retained = "".join((out / f"{split}.fasta").read_text() for split in ("train", "val", "test"))
    assert ">c\n" in retained and ">a\n" not in retained and ">b\n" not in retained
    assert set(dict(read_fasta(str(excluded)))) == {"a", "b"}
    report = json.loads((out / "split_audit.json").read_text())
    assert len(report["input_sha256"]["benchmark_fasta"]) == 2
    assert len(report["excluded_out_sha256"]) == 64


def test_group_by_protein_accepts_only_represented_unlisted_duplicates(tmp_path, monkeypatch):
    cleaned = write_fasta(tmp_path / "cleaned.fasta", [
        ("representative", "ATGAAATTTTGA"),
        ("unlisted_synonym", "ATGAAGTTCTGA"),
        ("other", "ATGGCTTAA"),
    ])
    clusters = tmp_path / "clusters.tsv"
    clusters.write_text("representative\trepresentative\nother\tother\n")
    benchmark = write_fasta(tmp_path / "benchmark.fasta", [("external", "ATGCAATAA")])
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", [
        "build_splits.py", "--cleaned", cleaned, "--cluster-tsv", str(clusters),
        "--benchmark-fasta", benchmark, "--out-dir", str(out), "--group-by-protein",
    ])
    build_splits_main()
    report = json.loads((out / "split_audit.json").read_text())
    assert report["n_unlisted_exact_protein_duplicate_ids"] == 1
    assert report["n_retained_input_records"] == 2


def test_group_by_protein_rejects_unrepresented_protein(tmp_path, monkeypatch):
    cleaned = write_fasta(tmp_path / "cleaned.fasta", [("missing", "ATGCAATAA")])
    clusters = tmp_path / "clusters.tsv"
    clusters.write_text("other\tother\n")
    benchmark = write_fasta(tmp_path / "benchmark.fasta", [("external", "ATGAAATTTTGA")])
    monkeypatch.setattr(sys, "argv", [
        "build_splits.py", "--cleaned", cleaned, "--cluster-tsv", str(clusters),
        "--benchmark-fasta", benchmark, "--out-dir", str(tmp_path / "out"),
        "--group-by-protein",
    ])
    with pytest.raises(ValueError, match="proteins absent"):
        build_splits_main()


def test_build_splits_requires_explicit_benchmark_path(monkeypatch):
    monkeypatch.setattr(sys, "argv", [
        "build_splits.py", "--cleaned", "x.fasta", "--cluster-tsv", "x.tsv", "--out-dir", "out",
    ])
    with pytest.raises(SystemExit) as exc:
        build_splits_main()
    assert exc.value.code == 2


def test_exact_cds_and_protein_overlap_with_duplicates(tmp_path):
    fastas = {
        "train": write_fasta(tmp_path / "train.fasta", [
            ("a", "ATGAAATTTTGA"), ("a_duplicate", "ATGAAATTTTGA"),
            ("synonymous", "ATGAAGTTCTGA"),
        ]),
        "val": write_fasta(tmp_path / "val.fasta", [("v", "ATGAAATTTTGA")]),
        "test": write_fasta(tmp_path / "test.fasta", [("t", "ATGGCTTAA")]),
        "benchmark": write_fasta(tmp_path / "bench.fasta", [
            ("nluc", "ATGAAATTTTGA"), ("egfp", "ATGGCTTAA"),
        ]),
    }
    result = overlap_audit(
        {k: fastas[k] for k in ("train", "val", "test")}, fastas["benchmark"]
    )
    assert result["splits"]["train"]["n_duplicate_cds_inputs"] == 1
    assert result["splits"]["train"]["n_duplicate_protein_inputs"] == 2
    assert result["splits"]["train"]["length_nt"]["mean"] == 12
    assert result["splits"]["train"]["gc"]["q50"] == 2 / 12
    assert sum(result["splits"]["train"]["histograms"]["length_nt"]["counts"]) == 3
    assert sum(result["splits"]["train"]["histograms"]["gc"]["counts"]) == 3
    assert result["splits"]["train"]["length_nt"]["q05"] == 12
    assert result["overlaps"]["train__val"]["n_shared_cds"] == 1
    assert result["overlaps"]["train__val"]["n_train_inputs_with_shared_cds"] == 2
    assert result["overlaps"]["train__test"]["n_shared_protein"] == 0
    assert result["overlaps"]["train__benchmark"]["n_shared_cds"] == 1
    assert result["overlaps"]["test__benchmark"]["n_shared_protein"] == 1
    assert result == overlap_audit(
        {k: fastas[k] for k in ("train", "val", "test")}, fastas["benchmark"]
    )
    assert "not family-disjoint proof" in result["scope"]
    with pytest.raises(ValueError, match="outside"):
        histogram([6001], [0, 300, 6000])
