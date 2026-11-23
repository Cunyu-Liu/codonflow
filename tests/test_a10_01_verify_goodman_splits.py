import ast
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from scripts import a10_01_goodman_freeze_splits as freeze
from scripts import a10_01_verify_goodman_splits as verifier


ROOT = Path(__file__).resolve().parents[1]
FROZEN_PROTOCOL = ROOT / "configs" / "a10_01_goodman_split_protocol_v1.json"
HEADER = ["Name", "Gene", "CDS.seq", "Trans", "Count.Prot"]
ASSIGNMENT_COLUMNS = ["Name", "Gene", "CDS.seq", "outer_fold"]
CODONS = [first + second + third for first in "TCAG" for second in "TCAG" for third in "TCAG"]


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def synthetic_rows(outcome_offset=0):
    rows = []
    for gene_index in range(25):
        gene = f"synthetic-gene-{gene_index:02d}"
        cds = "ATG" + CODONS[gene_index] + "GCT" * 9
        for replicate in range(2):
            rows.append({
                "Name": f"synthetic-name-{gene_index:02d}",
                "Gene": gene,
                "CDS.seq": cds,
                "Trans": str(outcome_offset + gene_index * 2 + replicate),
                "Count.Prot": str(1000 + outcome_offset + gene_index * 2 + replicate),
            })
    return rows


def write_clean(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def production_arguments(case):
    return [
        "--clean-csv", str(case["clean"]),
        "--protocol", str(case["protocol"]),
        "--assignment-csv", str(case["assignment"]),
        "--split-json", str(case["split"]),
    ]


def make_case(tmp_path, outcome_offset=0):
    tmp_path.mkdir(parents=True, exist_ok=True)
    rows = synthetic_rows(outcome_offset)
    clean = tmp_path / "synthetic_goodman_clean.csv"
    write_clean(clean, rows)
    protocol = json.loads(FROZEN_PROTOCOL.read_text(encoding="utf-8"))
    clean_protocol = protocol["inputs"]["clean_csv"]
    clean_protocol["sha256"] = sha256_file(clean)
    clean_protocol["expected_data_rows"] = len(rows)
    gene_counts = Counter(row["Gene"] for row in rows)
    clean_protocol["expected_gene_count"] = len(gene_counts)
    clean_protocol["expected_rows_per_gene"] = sorted(set(gene_counts.values()))
    clean_protocol["expected_unique_exact_cds"] = len({row["CDS.seq"] for row in rows})
    protocol_path = tmp_path / "synthetic_split_protocol.json"
    write_json(protocol_path, protocol)
    case = {
        "clean": clean,
        "protocol": protocol_path,
        "assignment": tmp_path / "outputs" / "assignment.csv",
        "split": tmp_path / "outputs" / "frozen_splits.json",
        "rows": rows,
    }
    assert freeze.main(production_arguments(case)) == 0
    return case


def verify(case):
    return verifier.verify_goodman_splits(
        case["clean"], case["protocol"], case["assignment"], case["split"],
    )


def load_report(case):
    return json.loads(case["split"].read_text(encoding="utf-8"))


def save_report(case, report):
    write_json(case["split"], report)


def read_assignment(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def write_assignment(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(ASSIGNMENT_COLUMNS)
        writer.writerows(rows)


def cli_arguments(case, output):
    return [
        "--clean-csv", str(case["clean"]),
        "--protocol", str(case["protocol"]),
        "--assignment-csv", str(case["assignment"]),
        "--split-json", str(case["split"]),
        "--output", str(output),
    ]


def test_official_protocol_and_verifier_independence_are_frozen():
    protocol = json.loads(FROZEN_PROTOCOL.read_text(encoding="utf-8"))
    clean = protocol["inputs"]["clean_csv"]
    assert clean["sha256"] == "ce64f2caa9633fefae840e220d36b6360946d39b9253adc56f3ef297b9ab9c82"
    assert clean["expected_data_rows"] == 14234
    assert clean["expected_gene_count"] == 137
    assert clean["expected_rows_per_gene"] == [102, 104]
    assert clean["expected_unique_exact_cds"] == 4817
    assert protocol["source_qc_reference"]["n_terminal_translation_count"] == 137
    assert protocol["source_qc_reference"]["leader_context_count"] == 280
    assert protocol["split"]["outer_folds"] == 5
    assert protocol["split"]["inner_folds"] == 4
    assert protocol["scope"]["supported_ood"] == "Gene-grouped N-terminal fragment construct OOD"
    assert protocol["scope"]["protein_ood_supported"] is False
    source = Path(verifier.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(
        name == "codonflow" or name.startswith(("codonflow.", "scripts."))
        for name in imported
    )


def test_synthetic_production_to_independent_verification_end_to_end(tmp_path):
    case = make_case(tmp_path)
    result = verify(case)
    report = load_report(case)

    assert result["passed"]
    assert all(result["checks"].values())
    assert report["schema"] == "a10-01-goodman-frozen-nested-grouped-cv-v1"
    assert result["recomputed"]["outer_folds"] == report["outer_folds"]
    assert len(report["outer_folds"]) == 5
    assert all(
        set(outer["train_inner_folds"]) == {"0", "1", "2", "3"}
        for outer in report["outer_folds"]
    )
    assert result["recomputed"]["input"] == {
        "data_rows": 50,
        "gene_count": 25,
        "unique_exact_cds": 25,
        "unique_names": 25,
    }
    assert result["mismatches"] == {"assignment": [], "report": []}
    assignment = read_assignment(case["assignment"])
    assert assignment[0] == ASSIGNMENT_COLUMNS
    assert all(len(row) == 4 for row in assignment)


def test_assignment_extra_inner_fold_column_is_rejected(tmp_path):
    case = make_case(tmp_path)
    rows = read_assignment(case["assignment"])
    rows[0].append("inner_fold")
    for row in rows[1:]:
        row.append("0")
    with case["assignment"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerows(rows)

    with pytest.raises(ValueError, match="header must be exactly"):
        verify(case)


def test_outcome_values_do_not_change_assignment_or_gene_partitions(tmp_path):
    first = make_case(tmp_path / "first", outcome_offset=0)
    second = make_case(tmp_path / "second", outcome_offset=9000)

    assert verify(first)["passed"]
    assert verify(second)["passed"]
    assert first["assignment"].read_bytes() == second["assignment"].read_bytes()
    assert load_report(first)["outer_folds"] == load_report(second)["outer_folds"]
    assert first["clean"].read_bytes() != second["clean"].read_bytes()


@pytest.mark.parametrize("column,value", [
    (0, "TAMPERED_NAME"),
    (1, "synthetic-gene-01"),
    (2, "ATGGCCGCCGCC"),
    (3, "4"),
])
def test_assignment_cell_tampering_is_detected(tmp_path, column, value):
    case = make_case(tmp_path)
    rows = read_assignment(case["assignment"])
    original = rows[1][column]
    rows[1][column] = value if value != original else "0"
    write_assignment(case["assignment"], rows[1:])

    result = verify(case)
    assert not result["passed"]
    assert not result["checks"]["assignment_exact"]
    assert not result["checks"]["deterministic_assignment_bytes"]
    assert not result["checks"]["report_assignment_sha256"]
    assert result["mismatches"]["assignment"]


def test_assignment_row_deletion_violates_quantity_conservation(tmp_path):
    case = make_case(tmp_path)
    rows = read_assignment(case["assignment"])
    write_assignment(case["assignment"], rows[1:-1])

    result = verify(case)
    assert not result["passed"]
    assert not result["checks"]["assignment_row_conservation"]
    assert not result["checks"]["assignment_exact"]


def test_assignment_tampering_with_synchronized_sha_still_fails(tmp_path):
    case = make_case(tmp_path)
    rows = read_assignment(case["assignment"])
    rows[1][3] = "4" if rows[1][3] != "4" else "3"
    write_assignment(case["assignment"], rows[1:])
    report = load_report(case)
    report["assignment_csv"]["sha256"] = sha256_file(case["assignment"])
    save_report(case, report)

    result = verify(case)
    assert result["checks"]["report_assignment_sha256"]
    assert not result["checks"]["assignment_exact"]
    assert not result["checks"]["report_exact"]
    assert not result["passed"]


def test_outer_split_tampering_fails_partition_and_isolation(tmp_path):
    case = make_case(tmp_path)
    report = load_report(case)
    moved_gene = report["outer_folds"][1]["test_genes"][0]
    report["outer_folds"][0]["test_genes"][0] = moved_gene
    save_report(case, report)

    result = verify(case)
    assert not result["checks"]["report_exact"]
    assert not result["checks"]["outer_gene_partition"]
    assert not result["checks"]["outer_gene_isolation"]
    assert not result["passed"]


def test_inner_split_tampering_is_detected(tmp_path):
    case = make_case(tmp_path)
    report = load_report(case)
    inner = report["outer_folds"][0]["train_inner_folds"]
    inner["1"][0] = inner["0"][0]
    save_report(case, report)

    result = verify(case)
    assert not result["checks"]["report_exact"]
    assert not result["checks"]["inner_gene_partition"]
    assert not result["checks"]["inner_gene_isolation"]
    assert not result["passed"]


@pytest.mark.parametrize("path,value,check", [
    (("input", "data_rows"), 51, "report_exact"),
    (("grouping", "maximum_gene_count_difference_within_partition"), 2, "report_exact"),
    (("scope", "protein_ood_supported"), True, "claim_boundaries"),
    (("scope", "multi_gene_pool_is_protein_ood"), True, "claim_boundaries"),
    (("outcome_columns_used_for_splitting",), True, "claim_boundaries"),
    (("untouched_inputs_read",), True, "claim_boundaries"),
    (("source_qc_reference", "leader_context_count"), 1, "source_qc_reference"),
])
def test_report_tampering_is_detected(tmp_path, path, value, check):
    case = make_case(tmp_path)
    report = load_report(case)
    target = report
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    save_report(case, report)

    result = verify(case)
    assert not result["passed"]
    assert not result["checks"]["report_exact"]
    assert not result["checks"][check]
    assert result["mismatches"]["report"]


@pytest.mark.parametrize("path,check", [
    (("input_sha256", "clean_csv"), "report_clean_sha256"),
    (("input_sha256", "protocol"), "report_protocol_sha256"),
    (("assignment_csv", "sha256"), "report_assignment_sha256"),
])
def test_reported_artifact_sha_tampering_is_detected(tmp_path, path, check):
    case = make_case(tmp_path)
    report = load_report(case)
    target = report
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = "0" * 64
    save_report(case, report)

    result = verify(case)
    assert not result["passed"]
    assert not result["checks"][check]
    assert not result["checks"]["report_exact"]


def test_clean_sha_and_shape_tampering_are_detected(tmp_path):
    case = make_case(tmp_path)
    rows = synthetic_rows()
    rows[0]["Gene"] = "synthetic-gene-01"
    write_clean(case["clean"], rows)

    result = verify(case)
    assert not result["passed"]
    assert not result["checks"]["clean_sha256"]
    assert not result["checks"]["clean_gene_row_sizes"]
    assert not result["checks"]["assignment_exact"]


@pytest.mark.parametrize("column,check", [
    ("Name", "clean_name_follows_gene"),
    ("CDS.seq", "clean_exact_cds_follows_gene"),
])
def test_cross_gene_consistency_tampering_is_detected(tmp_path, column, check):
    case = make_case(tmp_path)
    rows = synthetic_rows()
    rows[1][column] = rows[2][column]
    write_clean(case["clean"], rows)

    result = verify(case)
    assert not result["passed"]
    assert not result["checks"][check]


def test_noncanonical_split_serialization_is_detected(tmp_path):
    case = make_case(tmp_path)
    report = load_report(case)
    case["split"].write_text(json.dumps(report, sort_keys=True), encoding="utf-8")

    result = verify(case)
    assert result["checks"]["report_exact"]
    assert not result["checks"]["deterministic_splits_bytes"]
    assert not result["passed"]


def test_main_writes_success_json_and_refuses_overwrite(tmp_path):
    case = make_case(tmp_path)
    output = tmp_path / "nested" / "verification.json"
    assert verifier.main(cli_arguments(case, output)) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["passed"]
    original = output.read_bytes()

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        verifier.main(cli_arguments(case, output))
    assert output.read_bytes() == original


def test_main_writes_failed_json_and_preserves_it_on_overwrite_attempt(tmp_path):
    case = make_case(tmp_path)
    report = load_report(case)
    report["input"]["unique_exact_cds"] += 1
    save_report(case, report)
    output = tmp_path / "failed.json"

    assert verifier.main(cli_arguments(case, output)) == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert not payload["passed"]
    assert not payload["checks"]["report_exact"]
    original = output.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        verifier.main(cli_arguments(case, output))
    assert output.read_bytes() == original
