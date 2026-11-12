import json

import pytest

from codonflow.core.codon import STANDARD_TABLE_1
from scripts.a7_build_calibration import main as calibration_main
from scripts.a7_build_confirmation import build_confirmation


def write_fasta(path, records):
    path.write_text("".join(f">{header}\n{sequence}\n" for header, sequence in records))


def synthetic_records():
    records = []
    by_aa = {}
    for codon, aa in STANDARD_TABLE_1.items():
        if aa != "*":
            by_aa.setdefault(aa, codon)
    amino_codons = [by_aa[aa] for aa in sorted(by_aa)]
    for index in range(36):
        body = [100, 250, 450][index % 3]
        first = amino_codons[index % len(amino_codons)]
        second = amino_codons[index // len(amino_codons)]
        sequence = "ATG" + first + second + "GCT" * (body - 3) + "TAA"
        records.append((f"g{index}", sequence))
    return records


def test_confirmation_excludes_old_records_and_freezes_strata(tmp_path):
    records = synthetic_records()
    test = tmp_path / "test.fasta"
    exclusion = tmp_path / "old.fasta"
    clusters = tmp_path / "clusters.tsv"
    write_fasta(test, records)
    write_fasta(exclusion, records[:4])
    clusters.write_text("".join(f"{header}\t{header}\n" for header, _ in records))
    selected, audit = build_confirmation(str(test), [str(exclusion)], str(clusters), n=24)
    assert len(selected) == 24
    assert not {row["header"] for row in selected} & {f"g{i}" for i in range(4)}
    assert {row["length_bin"] for row in selected} == {"short", "mid", "long"}
    assert audit["n_excluded_cluster_representatives"] == 4


def test_confirmation_fails_when_stratum_is_insufficient(tmp_path):
    records = synthetic_records()[:6]
    test = tmp_path / "test.fasta"
    clusters = tmp_path / "clusters.tsv"
    write_fasta(test, records)
    clusters.write_text("".join(f"{header}\t{header}\n" for header, _ in records))
    with pytest.raises(ValueError):
        build_confirmation(str(test), [], str(clusters), n=24)


def test_calibration_uses_only_supplied_calibration_points(tmp_path):
    source = tmp_path / "calibration.json"
    out = tmp_path / "reference.json"
    source.write_text(json.dumps({"objectives": [[0, 0], [1, 1], [2, 2], [3, 3]]}))
    import sys
    old = sys.argv
    try:
        sys.argv = ["a7_build_calibration.py", "--objectives-json", str(source), "--out", str(out)]
        calibration_main()
    finally:
        sys.argv = old
    result = json.loads(out.read_text())
    assert result["source_role"] == "independent_calibration_not_test"
    assert result["n_calibration_points"] == 4
    assert result["scale"] == pytest.approx([2.85, 2.85])
