import csv
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import a10_01_goodman_e0_audit_v2 as audit


ROOT = Path(__file__).resolve().parents[1]
FROZEN_PROTOCOL = ROOT / "configs" / "a10_01_goodman_e0_protocol_v2.json"
SCRIPT = ROOT / "scripts" / "a10_01_goodman_e0_audit_v2.py"
EXTRA_COLUMNS = [f"Extra.{index:02d}" for index in range(1, 22)]
HEADER = [*audit.REQUIRED_COLUMNS, *EXTRA_COLUMNS]
ALANINE_1 = "ATG" + "GCT" * 10
ALANINE_2 = "ATG" + "GCA" * 10
PHENYLALANINE_1 = "ATG" + "TTT" * 10
PHENYLALANINE_2 = "ATG" + "TTC" * 10


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def make_row(index, gene, cds, name=None):
    row = {column: "" for column in HEADER}
    row.update({
        "Name": name or f"variant-{index}",
        "CDS.seq": cds,
        "Gene": gene,
        "Promoter": "synthetic-promoter",
        "Promoter.seq": "TTGACA",
        "RBS.seq": "AAGGAG",
        "CDS.type": "N-terminal-fragment",
        "RBS.len": "6",
        "Fltr.SetGood": "TRUE",
    })
    for field in audit.NUMERIC_FIELDS:
        row[field] = str(index)
    row["Count.Prot"] = "0" if index == 1 else str(index * 10)
    row["Trans"] = {1: "0.1", 2: "2.5", 3: "10", 4: ""}.get(index, str(index))
    for extra in EXTRA_COLUMNS:
        row[extra] = f"{extra}-value-{index}"
    row["Extra.01"] = f'comma,"quote",{index}'
    return row


def default_rows():
    rows = [
        make_row(1, "gene-A", ALANINE_1),
        make_row(2, "gene-A", ALANINE_2),
        make_row(3, "gene-B", PHENYLALANINE_1),
        make_row(4, "gene-B", PHENYLALANINE_2),
    ]
    rows[0]["Fltr.SetGood"] = "FALSE"
    rows[0]["Fltr.BelowRange"] = "TRUE"
    rows[0]["Insuff.Prot"] = "TRUE"
    rows[0]["Insuff.DNA"] = "TRUE"
    rows[0]["Insuff.RNA"] = "TRUE"
    rows[2]["Promoter.seq"] = "TTGACG"
    return rows


def encode_csv(header, rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([row.get(column, "") for column in header])
    return buffer.getvalue().encode("utf-8")


def write_case(tmp_path, rows=None, header=None, raw_bytes=None, expected_rows=None):
    rows = default_rows() if rows is None else rows
    header = HEADER if header is None else header
    raw = encode_csv(header, rows) if raw_bytes is None else raw_bytes
    raw_path = tmp_path / "synthetic_goodman.csv"
    raw_path.write_bytes(raw)
    protocol = json.loads(FROZEN_PROTOCOL.read_text(encoding="utf-8"))
    protocol["inputs"]["raw_csv"]["sha256"] = sha256(raw)
    protocol["inputs"]["raw_csv"]["expected_data_rows"] = (
        len(rows) if expected_rows is None else expected_rows
    )
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
    clean = tmp_path / "outputs" / "clean.csv"
    report = tmp_path / "outputs" / "report.json"
    args = [
        "--raw-csv", str(raw_path),
        "--protocol", str(protocol_path),
        "--clean-csv", str(clean),
        "--report-json", str(report),
    ]
    return {
        "args": args,
        "raw": raw,
        "raw_path": raw_path,
        "protocol_path": protocol_path,
        "rows": rows,
        "header": header,
        "clean": clean,
        "report": report,
    }


def assert_no_outputs(case):
    assert not case["clean"].exists()
    assert not case["report"].exists()


def test_frozen_protocol_pins_official_asset_and_claim_boundaries():
    protocol = json.loads(FROZEN_PROTOCOL.read_text(encoding="utf-8"))
    raw = protocol["inputs"]["raw_csv"]
    assert protocol["schema"] == "a10-01-goodman-e0-protocol-v2"
    assert protocol["protocol"] == audit.PROTOCOL
    assert raw["url"] == audit.OFFICIAL_URL
    assert raw["sha256"] == "a03071027b8c0008d07fb7737de0a7d51765c6cff25bc86e93465a6253c7c33a"
    assert raw["expected_data_rows"] == 14234
    assert raw["expected_column_count"] == 75
    assert len(protocol["required_columns"]) == 54
    eligibility = protocol["study"]["eligibility"]
    assert eligibility["task"] == "T1_leader_context_n_terminal_construct_function"
    assert eligibility["leader_context_n_terminal_window_supported"] is True
    assert "fixed_leader_n_terminal_window_supported" not in eligibility
    assert eligibility["full_length_cds_supported"] is False
    assert eligibility["native_utr_supported"] is False
    assert eligibility["protein_ood_supported"] is False
    assert eligibility["final_untouched"] is False
    assert protocol["construction"]["official_observed_leader_context_groups"] == 280
    assert protocol["construction"]["leader_contexts_vary"] is True
    assert protocol["construction"]["uniform_fixed_leader"] is False
    assert protocol["construction"]["multi_gene_pool_is_protein_ood"] is False
    assert protocol["cleaning"]["preserve_all_original_columns"] is True
    assert protocol["cleaning"]["preserve_all_rows"] is True
    assert protocol["cleaning"]["delete_rows"] is False
    assert protocol["cleaning"]["apply_fltr_setgood"] is False
    assert protocol["cleaning"]["remove_low_expression_or_failed_variants"] is False
    assert protocol["license"] == {
        "status": "unconfirmed",
        "confirmed": False,
        "redistribution_or_derivative_use_requires_review": True,
    }
    assert protocol["outputs"]["overwrite"] == "forbidden"


def test_valid_synthetic_input_preserves_every_field_row_and_failed_variant(tmp_path):
    case = write_case(tmp_path)

    assert audit.main(case["args"]) == 0

    with case["clean"].open(encoding="utf-8", newline="") as handle:
        clean_rows = list(csv.reader(handle))
    expected_rows = [case["header"]] + [
        [row[column] for column in case["header"]] for row in case["rows"]
    ]
    assert clean_rows == expected_rows
    assert b"\r\n" not in case["clean"].read_bytes()
    report = json.loads(case["report"].read_text(encoding="utf-8"))
    assert report["schema"] == "a10-01-goodman-e0-audit-report-v2"
    assert report["protocol"] == audit.PROTOCOL
    assert report["status"] == "candidate_procedure_and_qc_passed"
    assert report["scope"] == audit.SCOPE
    assert report["sha256"] == {
        "raw_csv": sha256(case["raw"]),
        "protocol": sha256(case["protocol_path"].read_bytes()),
        "clean_csv": sha256(case["clean"].read_bytes()),
    }
    assert report["raw_csv"]["column_count"] == 75
    assert report["raw_csv"]["data_rows"] == 4
    assert report["clean_csv"]["data_rows"] == 4
    assert report["clean_csv"]["all_original_columns_preserved"] is True
    assert report["clean_csv"]["all_original_rows_preserved"] is True
    assert report["clean_csv"]["filtering_applied"] is False
    assert report["clean_csv"]["deduplication_applied"] is False
    assert report["sequence_qc"]["length_nt_distribution"] == {"33": 4}
    assert report["sequence_qc"]["internal_stop_rows"] == 0
    assert report["sequence_qc"]["terminal_stop_rows"] == 0
    assert report["translation_qc"]["consistent_gene_count"] == 2
    assert report["translation_qc"]["inconsistent_gene_count"] == 0
    assert report["filter_qc"]["rows_removed_from_clean"] == 0
    assert report["filter_qc"]["fields"]["Fltr.SetGood"]["true_rows"] == 3
    assert report["filter_qc"]["fields"]["Fltr.SetGood"]["false_rows"] == 1
    assert report["filter_qc"]["fields"]["Fltr.BelowRange"]["true_rows"] == 1
    assert report["numeric_qc"]["Count.Prot"]["zero_rows"] == 1
    assert report["numeric_qc"]["Trans"]["missing_rows"] == 1
    assert report["numeric_qc"]["Trans"]["finite_rows"] == 3
    assert report["numeric_qc"]["Trans"]["min"] == 0.1
    assert report["numeric_qc"]["Trans"]["max"] == 10.0
    assert report["distribution_qc"]["CAI"]["finite_rows"] == 4
    assert report["distribution_qc"]["GC"]["quantiles"]["p95"] is not None
    assert report["gene_qc"]["sample_counts"] == {"gene-A": 2, "gene-B": 2}
    assert report["task_eligibility"]["task"] == "T1_leader_context_n_terminal_construct_function"
    assert report["task_eligibility"]["leader_context_n_terminal_window_supported"] is True
    assert report["task_eligibility"]["fixed_single_leader_claim"] is False
    assert report["task_eligibility"]["native_utr_supported"] is False
    assert report["task_eligibility"]["full_length_cds_supported"] is False
    assert report["construction_qc"]["official_observed_leader_context_groups"] == 280
    assert report["construction_qc"]["observed_leader_context_groups"] == 2
    assert report["construction_qc"]["official_leader_contexts_vary"] is True
    assert report["construction_qc"]["official_uniform_fixed_leader"] is False
    assert report["construction_qc"]["observed_leader_contexts_vary"] is True
    assert report["construction_qc"]["sequence_diversity"]["leader"]["unique_values"] == 2
    assert report["construction_qc"]["CDS.type"]["value_counts"] == {
        "N-terminal-fragment": 4,
    }
    assert report["split_leakage_qc"]["split_performed"] is False
    assert report["split_leakage_qc"]["primary_group"] == "Gene"
    assert report["split_leakage_qc"]["multi_gene_pool_is_protein_ood"] is False
    assert report["split_leakage_qc"]["protein_ood_supported"] is False
    assert report["source"]["license"]["status"] == "unconfirmed"


def test_hash_mismatch_cli_exits_nonzero_without_outputs(tmp_path):
    case = write_case(tmp_path)
    case["raw_path"].write_bytes(case["raw"] + b"hash mismatch")

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), *case["args"]],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode != 0
    assert "raw CSV SHA256 mismatch" in completed.stderr
    assert_no_outputs(case)


def test_required_schema_failure_is_fatal(tmp_path):
    header = list(HEADER)
    header[header.index("CDS.seq")] = "CDS.typo"
    case = write_case(tmp_path, header=header)

    with pytest.raises(ValueError, match=r"missing required columns: \['CDS.seq'\]"):
        audit.main(case["args"])
    assert_no_outputs(case)


def test_wrong_data_row_width_is_fatal(tmp_path):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(HEADER)
    writer.writerow(["too-few"] * 74)
    case = write_case(tmp_path, raw_bytes=buffer.getvalue().encode(), expected_rows=1)

    with pytest.raises(ValueError, match="expected 75 fields, observed 74"):
        audit.main(case["args"])
    assert_no_outputs(case)


@pytest.mark.parametrize(
    "cds,message",
    [
        ("ATG" + "TAA" + "GCT" * 9, "internal stop"),
        ("ATG" + "GCT" * 9 + "TAA", "terminal stop"),
        ("ATG" + "GCT" * 9 + "GCN", "invalid alphabet"),
        ("GTG" + "GCT" * 10, "non-ATG start"),
        ("ATGGCTG", "length not divisible by 3"),
    ],
)
def test_critical_cds_sequence_failures_are_fatal(tmp_path, cds, message):
    case = write_case(tmp_path, rows=[make_row(1, "gene-A", cds)])

    with pytest.raises(ValueError, match=message):
        audit.main(case["args"])
    assert_no_outputs(case)


def test_internal_stop_cli_exits_nonzero(tmp_path):
    internal_stop = "ATG" + "TAA" + "GCT" * 9
    case = write_case(tmp_path, rows=[make_row(1, "gene-A", internal_stop)])

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), *case["args"]],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode != 0
    assert "internal stop" in completed.stderr
    assert_no_outputs(case)


def test_duplicates_are_reported_and_never_removed(tmp_path):
    rows = [
        make_row(1, "gene-A", ALANINE_1, name="shared-name"),
        make_row(2, "gene-A", ALANINE_1, name="shared-name"),
        make_row(3, "gene-B", ALANINE_1, name="other-name"),
    ]
    case = write_case(tmp_path, rows=rows)

    assert audit.main(case["args"]) == 0
    report = json.loads(case["report"].read_text(encoding="utf-8"))
    duplicates = report["duplicate_qc"]
    assert duplicates["Name"]["duplicate_rows_beyond_first"] == 1
    assert duplicates["Name"]["duplicated_groups"] == 1
    assert duplicates["exact_CDS"]["duplicate_rows_beyond_first"] == 2
    assert duplicates["exact_CDS"]["duplicated_groups"] == 1
    assert duplicates["Name_CDS"]["duplicate_rows_beyond_first"] == 1
    assert duplicates["Name_CDS"]["duplicated_groups"] == 1
    assert duplicates["exact_CDS_groups_spanning_multiple_Genes"] == 1
    assert duplicates["Names_with_multiple_CDS_sequences"] == 0
    assert duplicates["deduplication_applied"] is False
    assert report["clean_csv"]["data_rows"] == 3
    with case["clean"].open(encoding="utf-8", newline="") as handle:
        assert len(list(csv.reader(handle))) == 4
    exact_group = report["split_leakage_qc"]["groups"]["exact_CDS"]
    assert exact_group["unique_groups"] == 1
    assert exact_group["largest_group_size"] == 3


def test_translation_inconsistency_within_gene_is_fatal(tmp_path):
    rows = [
        make_row(1, "gene-A", ALANINE_1),
        make_row(2, "gene-A", PHENYLALANINE_1),
    ]
    case = write_case(tmp_path, rows=rows)

    with pytest.raises(ValueError, match="translation inconsistency.*gene-A"):
        audit.main(case["args"])
    assert_no_outputs(case)


@pytest.mark.parametrize("existing_output", ["clean", "report"])
def test_existing_outputs_are_never_overwritten(tmp_path, existing_output):
    case = write_case(tmp_path)
    existing = case[existing_output]
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"keep-original")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        audit.main(case["args"])

    assert existing.read_bytes() == b"keep-original"
    other = case["report"] if existing_output == "clean" else case["clean"]
    assert not other.exists()
