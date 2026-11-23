import ast
import csv
import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from scripts import a10_01_verify_tunney_e0 as verifier


RAW_COUNTS = {
    "YAL001C": ("0", "2.5e-1", "3.75", "0"),
    "YAL002W": ("3.5", "0", "0"),
    "YAL003W": ("0", "0"),
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_raw_tar(path, counts=RAW_COUNTS, extra_member=False):
    payload = "".join(
        gene + "\t" + "\t".join(values) + "\n" for gene, values in counts.items()
    ).encode()
    compressed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, mtime=0) as handle:
        handle.write(payload)
    member_bytes = compressed.getvalue()
    with tarfile.open(path, mode="w") as archive:
        member = tarfile.TarInfo(verifier.EXPECTED_RAW_MEMBER)
        member.size = len(member_bytes)
        member.mtime = 0
        member.uid = 0
        member.gid = 0
        member.uname = ""
        member.gname = ""
        archive.addfile(member, io.BytesIO(member_bytes))
        if extra_member:
            extra = tarfile.TarInfo("unexpected.txt")
            extra.size = 1
            archive.addfile(extra, io.BytesIO(b"x"))


def write_clean(path, rows, index_column="codon_index"):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["gene", index_column, "count"])
        writer.writerows(rows)


def clean_rows(counts=RAW_COUNTS):
    return [
        [gene, index, count]
        for gene, values in counts.items()
        for index, count in enumerate(values, start=1)
    ]


def synthetic_transcript_qc():
    return [
        {
            "gene": "YAL001C",
            "cds_codon_count": 4,
            "total_coverage": 4.0,
            "nonzero_coverage_positions": 2,
            "zero_coverage_positions": 2,
            "zero_coverage_fraction": 0.5,
            "long_tail": {
                "top_10pct_positions": 1,
                "top_10pct_count_share": 0.9375,
                "max_count_share": 0.9375,
            },
        },
        {
            "gene": "YAL002W",
            "cds_codon_count": 3,
            "total_coverage": 3.5,
            "nonzero_coverage_positions": 1,
            "zero_coverage_positions": 2,
            "zero_coverage_fraction": 2 / 3,
            "long_tail": {
                "top_10pct_positions": 1,
                "top_10pct_count_share": 1.0,
                "max_count_share": 1.0,
            },
        },
        {
            "gene": "YAL003W",
            "cds_codon_count": 2,
            "total_coverage": 0,
            "nonzero_coverage_positions": 0,
            "zero_coverage_positions": 2,
            "zero_coverage_fraction": 1.0,
            "long_tail": {
                "top_10pct_positions": 1,
                "top_10pct_count_share": None,
                "max_count_share": None,
            },
        },
    ]


def make_case(tmp_path, monkeypatch):
    raw_tar = tmp_path / "GSE106572_RAW.tar"
    clean_csv = tmp_path / "tunney_clean.csv"
    report_json = tmp_path / "tunney_report.json"
    write_raw_tar(raw_tar)
    write_clean(clean_csv, clean_rows())
    raw_sha256 = sha256(raw_tar)
    monkeypatch.setattr(verifier, "EXPECTED_RAW_SHA256", raw_sha256)
    report = {
        "schema": verifier.EXPECTED_REPORT_SCHEMA,
        "protocol": verifier.EXPECTED_REPORT_PROTOCOL,
        "status": "candidate_procedure_and_qc_passed",
        "scope": verifier.EXPECTED_SCOPE,
        "task_eligibility": {
            "task": "T2_translation_occupancy_and_kinetics",
            "candidate_research_only": True,
            "procedure_and_qc_only": True,
            "final_untouched": False,
            "functional_prediction_eligible": False,
            "model_training_or_calibration_eligible": False,
            "scientific_positive_claim_eligible": False,
        },
        "inputs": {"raw_member": verifier.EXPECTED_RAW_MEMBER},
        "sha256": {"raw_tar": raw_sha256, "clean_csv": sha256(clean_csv)},
        "clean_csv": {
            "columns": ["gene", "codon_index", "count"],
            "data_rows": 9,
            "codon_index_base": 1,
            "count_representation": "original input token without rounding or normalization",
        },
        "raw_qc": {
            "raw_data_rows": 3,
            "duplicate_gene_rows": 0,
            "empty_gene_rows": 0,
            "malformed_rows": 0,
            "invalid_count_values": 0,
            "negative_count_values": 0,
            "nonfinite_count_values": 0,
            "clean_rows": 9,
            "unique_genes": 3,
            "cds_codon_count_distribution": {"2": 1, "3": 1, "4": 1},
            "cds_codon_count_summary": {"min": 2, "max": 4, "mean": 3.0},
        },
        "transcript_qc": synthetic_transcript_qc(),
    }
    report_json.write_text(json.dumps(report), encoding="utf-8")
    return {
        "raw_tar": raw_tar,
        "clean_csv": clean_csv,
        "report_json": report_json,
        "report": report,
    }


def verify(case):
    return verifier.verify_tunney_e0(
        case["raw_tar"], case["clean_csv"], case["report_json"],
    )


def save_report(case):
    case["report_json"].write_text(json.dumps(case["report"]), encoding="utf-8")


def arguments(case, output):
    return [
        "--raw-tar", str(case["raw_tar"]),
        "--clean-csv", str(case["clean_csv"]),
        "--report", str(case["report_json"]),
        "--output", str(output),
    ]


def test_synthetic_exact_reconstruction_and_summary_pass(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    result = verify(case)

    assert result["passed"]
    assert all(result["checks"].values())
    assert result["recomputed"] == {
        "transcript_count": 3,
        "codon_count": 9,
        "count_sum": "7.5",
        "zero_coverage_transcripts": 1,
        "zero_coverage_codons": 6,
        "min_length": 2,
        "max_length": 4,
        "mean_length": 3,
        "length_distribution": {"2": 1, "3": 1, "4": 1},
    }
    assert result["report_summary_comparison"]["reported_count_sum"] == "7.5"
    assert result["inputs"]["clean_index_base"] == 1
    assert result["differences"] == []


def test_legacy_index_column_is_rejected(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    write_clean(case["clean_csv"], clean_rows(), index_column="index")

    with pytest.raises(ValueError, match="exactly gene, codon_index, count"):
        verify(case)


@pytest.mark.parametrize("kind", ["gene", "index", "count"])
def test_clean_gene_index_count_tampering_is_detected(tmp_path, monkeypatch, kind):
    case = make_case(tmp_path, monkeypatch)
    rows = clean_rows()
    if kind == "gene":
        rows[0][0] = "NOT_IN_RAW"
    elif kind == "index":
        for row in rows[:4]:
            row[1] += 1
    else:
        rows[1][2] = "9.25"
    write_clean(case["clean_csv"], rows)

    result = verify(case)
    assert not result["passed"]
    assert not result["checks"]["clean_exact"]
    expected_check = {
        "gene": "clean_gene_set", "index": "clean_indices", "count": "clean_counts",
    }[kind]
    assert not result["checks"][expected_check]
    assert result["differences"]


@pytest.mark.parametrize(
    "kind,check",
    [
        ("transcript_count", "report_transcript_count"),
        ("count_sum", "report_count_sum"),
        ("zero_coverage_transcripts", "report_zero_coverage"),
        ("zero_coverage_codons", "report_zero_coverage"),
        ("length_distribution", "report_length_distribution"),
        ("length_mean", "report_length_summary"),
    ],
)
def test_report_summary_tampering_is_detected(tmp_path, monkeypatch, kind, check):
    case = make_case(tmp_path, monkeypatch)
    report = case["report"]
    if kind == "transcript_count":
        report["raw_qc"]["unique_genes"] = 4
    elif kind == "count_sum":
        report["transcript_qc"][0]["total_coverage"] = 8.5
    elif kind == "zero_coverage_transcripts":
        report["transcript_qc"][2]["total_coverage"] = 1
    elif kind == "zero_coverage_codons":
        report["transcript_qc"][0]["zero_coverage_positions"] = 1
    elif kind == "length_distribution":
        report["raw_qc"]["cds_codon_count_distribution"] = {"2": 2, "3": 1}
    else:
        report["raw_qc"]["cds_codon_count_summary"]["mean"] = 2.5
    save_report(case)

    result = verify(case)
    assert not result["passed"]
    assert not result["checks"][check]
    assert not result["checks"]["report_summary"]
    assert result["checks"]["clean_exact"]


@pytest.mark.parametrize(
    "field,value,check",
    [
        ("final_untouched", True, "not_final_untouched"),
        ("scientific_positive_claim_eligible", True, "no_scientific_positive"),
        ("candidate_research_only", False, "candidate_status"),
    ],
)
def test_claim_status_forgery_is_detected(tmp_path, monkeypatch, field, value, check):
    case = make_case(tmp_path, monkeypatch)
    case["report"]["task_eligibility"][field] = value
    save_report(case)

    result = verify(case)
    assert not result["passed"]
    assert not result["checks"][check]


def test_raw_sha_and_reported_raw_sha_are_both_enforced(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    case["report"]["sha256"]["raw_tar"] = "0" * 64
    save_report(case)
    result = verify(case)
    assert result["checks"]["raw_sha256"]
    assert not result["checks"]["report_raw_sha256"]
    assert not result["passed"]

    changed = dict(RAW_COUNTS)
    changed["YAL001C"] = ("0", "2.5e-1", "3.5", "0")
    write_raw_tar(case["raw_tar"], changed)
    result = verify(case)
    assert not result["checks"]["raw_sha256"]
    assert not result["checks"]["clean_exact"]
    assert not result["passed"]


def test_missing_summary_and_contradictory_nested_claim_fail(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    del case["report"]["transcript_qc"][0]["total_coverage"]
    case["report"]["nested_evidence"] = {"final_untouched": True}
    save_report(case)

    result = verify(case)
    assert not result["checks"]["report_count_sum"]
    assert not result["checks"]["report_summary"]
    assert not result["checks"]["not_final_untouched"]
    assert not result["passed"]


def test_main_writes_new_success_json_and_refuses_overwrite(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    output = tmp_path / "nested" / "verification.json"

    assert verifier.main(arguments(case, output)) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["passed"]
    assert payload["protocol"] == verifier.PROTOCOL
    original = output.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        verifier.main(arguments(case, output))
    assert output.read_bytes() == original


def test_main_returns_nonzero_and_preserves_failed_output(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    case["report"]["transcript_qc"][0]["total_coverage"] = 999
    save_report(case)
    output = tmp_path / "failed-verification.json"

    assert verifier.main(arguments(case, output)) == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert not payload["passed"]
    assert not payload["checks"]["report_count_sum"]
    original = output.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        verifier.main(arguments(case, output))
    assert output.read_bytes() == original


def test_main_reports_malformed_raw_tar_as_nonzero_json(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    write_raw_tar(case["raw_tar"], extra_member=True)
    output = tmp_path / "malformed.json"

    assert verifier.main(arguments(case, output)) == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert not payload["passed"]
    assert payload["error"]["type"] == "ValueError"
    assert "exactly one member" in payload["error"]["message"]


def test_verifier_has_no_production_imports():
    tree = ast.parse(Path(verifier.__file__).read_text(encoding="utf-8"))
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
