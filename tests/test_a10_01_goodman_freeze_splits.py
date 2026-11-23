import csv
import hashlib
import io
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from scripts import a10_01_goodman_freeze_splits as freeze


ROOT = Path(__file__).resolve().parents[1]
FROZEN_PROTOCOL = ROOT / "configs" / "a10_01_goodman_split_protocol_v1.json"
SCRIPT = ROOT / "scripts" / "a10_01_goodman_freeze_splits.py"
HEADER = ["Name", "Gene", "CDS.seq", "Trans", "Count.Prot"]
CODONS = [first + second + third for first in "TCAG" for second in "TCAG" for third in "TCAG"]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def default_rows():
    rows = []
    for gene_index in range(25):
        cds = "ATG" + CODONS[gene_index] + "GCT" * 9
        for replicate in range(2):
            rows.append({
                "Name": f"synthetic-name-{gene_index:02d}",
                "Gene": f"synthetic-gene-{gene_index:02d}",
                "CDS.seq": cds,
                "Trans": str(gene_index * 2 + replicate),
                "Count.Prot": str(1000 + gene_index * 2 + replicate),
            })
    return rows


def encode_csv(rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(HEADER)
    for row in rows:
        writer.writerow([row[column] for column in HEADER])
    return buffer.getvalue().encode("utf-8")


def write_case(tmp_path, rows=None, outcome_shift=0):
    tmp_path.mkdir(parents=True, exist_ok=True)
    rows = default_rows() if rows is None else rows
    if outcome_shift:
        rows = [dict(row) for row in rows]
        for row in rows:
            row["Trans"] = str(int(row["Trans"]) + outcome_shift)
            row["Count.Prot"] = str(int(row["Count.Prot"]) + outcome_shift)
    raw = encode_csv(rows)
    clean = tmp_path / "synthetic_goodman_clean.csv"
    clean.write_bytes(raw)
    protocol = json.loads(FROZEN_PROTOCOL.read_text(encoding="utf-8"))
    clean_protocol = protocol["inputs"]["clean_csv"]
    clean_protocol["sha256"] = sha256(raw)
    clean_protocol["expected_data_rows"] = len(rows)
    gene_counts = Counter(row["Gene"] for row in rows)
    clean_protocol["expected_gene_count"] = len(gene_counts)
    clean_protocol["expected_rows_per_gene"] = sorted(set(gene_counts.values()))
    clean_protocol["expected_unique_exact_cds"] = len({row["CDS.seq"] for row in rows})
    protocol_path = tmp_path / "synthetic_split_protocol.json"
    protocol_path.write_text(
        json.dumps(protocol, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    return {
        "clean": clean,
        "protocol": protocol_path,
        "assignment": tmp_path / "outputs" / "assignment.csv",
        "report": tmp_path / "outputs" / "frozen_splits.json",
        "rows": rows,
        "raw": raw,
    }


def arguments(case, assignment=None, report=None):
    return [
        "--clean-csv", str(case["clean"]),
        "--protocol", str(case["protocol"]),
        "--assignment-csv", str(assignment or case["assignment"]),
        "--split-json", str(report or case["report"]),
    ]


def read_assignment(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def assert_no_outputs(case):
    assert not case["assignment"].exists()
    assert not case["report"].exists()


def test_frozen_protocol_pins_clean_v3_and_claim_boundaries():
    protocol = json.loads(FROZEN_PROTOCOL.read_text(encoding="utf-8"))
    clean = protocol["inputs"]["clean_csv"]
    assert protocol["schema"] == "a10-01-goodman-split-protocol-v1"
    assert protocol["protocol"] == freeze.PROTOCOL
    assert clean["sha256"] == "ce64f2caa9633fefae840e220d36b6360946d39b9253adc56f3ef297b9ab9c82"
    assert clean["expected_data_rows"] == 14234
    assert clean["expected_gene_count"] == 137
    assert clean["expected_rows_per_gene"] == [102, 104]
    assert clean["expected_unique_exact_cds"] == 4817
    assert clean["required_columns"] == ["Name", "Gene", "CDS.seq"]
    assert protocol["source_qc_reference"]["n_terminal_translation_count"] == 137
    assert protocol["source_qc_reference"]["leader_context_count"] == 280
    assert protocol["inputs"]["untouched_inputs_read"] is False
    split = protocol["split"]
    assert split["outer_folds"] == 5
    assert split["inner_folds"] == 4
    assert split["primary_group"] == "Gene"
    assert split["selection_columns"] == ["Name", "Gene", "CDS.seq"]
    assert split["outcome_columns_used_for_splitting"] is False
    assert "Trans" in split["forbidden_outcome_columns"]
    assert "Count.Prot" in split["forbidden_outcome_columns"]
    scope = protocol["scope"]
    assert scope["supported_ood"] == "Gene-grouped N-terminal fragment construct OOD"
    assert scope["protein_ood_supported"] is False
    assert scope["multi_gene_pool_is_protein_ood"] is False
    assert protocol["outputs"]["overwrite"] == "forbidden"


def test_outputs_are_deterministic_and_assign_every_input_row_once(tmp_path):
    case = write_case(tmp_path)
    assert freeze.main(arguments(case)) == 0
    first_assignment = case["assignment"].read_bytes()
    first_report = case["report"].read_bytes()
    second_assignment = tmp_path / "repeat" / "assignment.csv"
    second_report = tmp_path / "repeat" / "frozen_splits.json"

    assert freeze.main(arguments(case, second_assignment, second_report)) == 0

    assert second_assignment.read_bytes() == first_assignment
    assert second_report.read_bytes() == first_report
    assignment = read_assignment(case["assignment"])
    assert list(assignment[0]) == ["Name", "Gene", "CDS.seq", "outer_fold"]
    assert len(assignment) == len(case["rows"])
    assert [row["Name"] for row in assignment] == [row["Name"] for row in case["rows"]]
    assert [row["Gene"] for row in assignment] == [row["Gene"] for row in case["rows"]]
    assert [row["CDS.seq"] for row in assignment] == [row["CDS.seq"] for row in case["rows"]]
    assert Counter(row["Gene"] for row in assignment) == Counter(
        row["Gene"] for row in case["rows"]
    )
    report = json.loads(first_report)
    assert report["input_sha256"] == {
        "clean_csv": sha256(case["raw"]),
        "protocol": sha256(case["protocol"].read_bytes()),
    }
    assert report["input"] == {
        "data_rows": 50,
        "gene_count": 25,
        "unique_exact_cds": 25,
        "unique_names": 25,
    }
    assert report["assignment_csv"]["data_rows"] == 50
    assert report["assignment_csv"]["sha256"] == sha256(first_assignment)
    assert report["outcome_columns_used_for_splitting"] is False
    assert report["untouched_inputs_read"] is False
    assert report["scope"]["protein_ood_supported"] is False


def test_outer_and_inner_partitions_are_balanced_complete_and_leak_free(tmp_path):
    case = write_case(tmp_path)
    freeze.main(arguments(case))
    report = json.loads(case["report"].read_text(encoding="utf-8"))
    genes = {row["Gene"] for row in case["rows"]}
    gene_rows = Counter(row["Gene"] for row in case["rows"])
    all_test_genes = []

    assert len(report["outer_folds"]) == 5
    for outer in report["outer_folds"]:
        test = set(outer["test_genes"])
        train = set(outer["train_genes"])
        assert outer["outer_fold"] in range(5)
        assert test.isdisjoint(train)
        assert test | train == genes
        assert outer["test_gene_count"] == len(test)
        assert outer["train_gene_count"] == len(train)
        assert outer["test_row_count"] == sum(gene_rows[gene] for gene in test)
        assert outer["train_row_count"] == sum(gene_rows[gene] for gene in train)
        all_test_genes.extend(outer["test_genes"])
        inner = [set(outer["train_inner_folds"][str(index)]) for index in range(4)]
        assert set().union(*inner) == train
        assert test.isdisjoint(set().union(*inner))
        assert sum(map(len, inner)) == len(train)
        for left in range(4):
            for right in range(left + 1, 4):
                assert inner[left].isdisjoint(inner[right])
        inner_sizes = [len(fold) for fold in inner]
        assert max(inner_sizes) - min(inner_sizes) <= 1
        assert outer["inner_fold_gene_counts"] == {
            str(index): len(inner[index]) for index in range(4)
        }
        assert outer["inner_fold_row_counts"] == {
            str(index): sum(gene_rows[gene] for gene in inner[index])
            for index in range(4)
        }

    outer_sizes = [len(outer["test_genes"]) for outer in report["outer_folds"]]
    assert max(outer_sizes) - min(outer_sizes) <= 1
    assert len(all_test_genes) == len(genes)
    assert set(all_test_genes) == genes
    assert report["leakage_qc"] == {
        "every_gene_assigned_to_exactly_one_outer_fold": True,
        "outer_test_train_gene_overlap_count": 0,
        "outer_test_inner_gene_overlap_count": 0,
        "within_outer_inner_gene_overlap_count": 0,
        "exact_cds_cross_outer_group_count": 0,
        "name_cross_outer_group_count": 0,
    }


def test_exact_cds_and_name_follow_gene_in_outer_and_inner_partitions(tmp_path):
    case = write_case(tmp_path)
    freeze.main(arguments(case))
    assignment = read_assignment(case["assignment"])
    report = json.loads(case["report"].read_text(encoding="utf-8"))

    for column in ("CDS.seq", "Name"):
        by_outer = {}
        for row in assignment:
            by_outer.setdefault(row[column], set()).add(row["outer_fold"])
        assert all(len(folds) == 1 for folds in by_outer.values())
        for outer in report["outer_folds"]:
            gene_inner = {
                gene: str(inner)
                for inner in range(4)
                for gene in outer["train_inner_folds"][str(inner)]
            }
            by_inner = {}
            for row in assignment:
                if row["Gene"] in gene_inner:
                    by_inner.setdefault(row[column], set()).add(gene_inner[row["Gene"]])
            assert all(len(folds) == 1 for folds in by_inner.values())
    assert report["grouping"]["cross_gene_exact_cds_groups"] == 0
    assert report["grouping"]["cross_gene_name_groups"] == 0


@pytest.mark.parametrize(
    "column,message",
    [("CDS.seq", "exact CDS spans multiple Gene groups"),
     ("Name", "Name spans multiple Gene groups")],
)
def test_cross_gene_exact_cds_or_name_is_fatal(tmp_path, column, message):
    rows = default_rows()
    rows[2][column] = rows[0][column]
    case = write_case(tmp_path, rows=rows)

    with pytest.raises(ValueError, match=message):
        freeze.main(arguments(case))
    assert_no_outputs(case)


def test_outcome_values_cannot_change_gene_partition(tmp_path):
    first = write_case(tmp_path / "first")
    second = write_case(tmp_path / "second", outcome_shift=10000)
    freeze.main(arguments(first))
    freeze.main(arguments(second))

    assert first["assignment"].read_bytes() == second["assignment"].read_bytes()
    first_report = json.loads(first["report"].read_text(encoding="utf-8"))
    second_report = json.loads(second["report"].read_text(encoding="utf-8"))
    assert first_report["outer_folds"] == second_report["outer_folds"]
    assert first_report["input_sha256"]["clean_csv"] != second_report["input_sha256"]["clean_csv"]


def test_clean_input_hash_mismatch_cli_exits_nonzero_without_outputs(tmp_path):
    case = write_case(tmp_path)
    case["clean"].write_bytes(case["raw"] + b"hash mismatch")

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), *arguments(case)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode != 0
    assert "clean CSV SHA256 mismatch" in completed.stderr
    assert_no_outputs(case)


@pytest.mark.parametrize("existing_output", ["assignment", "report"])
def test_existing_outputs_are_never_overwritten(tmp_path, existing_output):
    case = write_case(tmp_path)
    existing = case[existing_output]
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"keep-original")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freeze.main(arguments(case))

    assert existing.read_bytes() == b"keep-original"
    other = case["report"] if existing_output == "assignment" else case["assignment"]
    assert not other.exists()
