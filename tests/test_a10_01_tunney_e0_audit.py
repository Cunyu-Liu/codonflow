import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from scripts import a10_01_tunney_e0_audit as audit


ROOT = Path(__file__).resolve().parents[1]
FROZEN_PROTOCOL = ROOT / "configs" / "a10_01_tunney_e0_protocol_v1.json"
SCRIPT = ROOT / "scripts" / "a10_01_tunney_e0_audit.py"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def member_bytes(rows):
    return "".join(
        gene + "\t" + "\t".join(counts) + "\n" for gene, counts in rows
    ).encode()


def synthetic_tar(payload, member_name=audit.MEMBER_NAME, extra_member=False):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        members = [(member_name, payload)]
        if extra_member:
            members.append(("unexpected.txt", b"not allowed\n"))
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def synthetic_soft(repeat_processing=False, omit_a_site=False):
    processing = [
        "One Ribo experiment was sequenced as two lanes and the two lanes were merged before analysis.",
        "RSEM 1.3.0 assigned multi-mapping weights to reads; weighted counts were retained.",
        "Reads were aligned to sacCer3.",
    ]
    if not omit_a_site:
        processing.append(
            "A-site offsets: (27,0)->15, (27,1)->14, (28,0)->15, "
            "(29,0)->15, (29,2)->16."
        )
    if repeat_processing:
        processing.append(processing[0])
    lines = [
        "^DATABASE = Geo",
        "^SAMPLE = GSM2842830",
        "!Sample_title = synthetic Ribo audit fixture",
        "!Sample_organism_ch1 = Saccharomyces cerevisiae",
        "!Sample_characteristics_ch1 = strain: BY474",
        *(f"!Sample_data_processing = {value}" for value in processing),
        f"!Sample_supplementary_file = {audit.MEMBER_NAME}",
    ]
    return gzip.compress(("\n".join(lines) + "\n").encode())


def real_soft_fragment():
    supplementary_url = (
        "ftp://ftp.ncbi.nlm.nih.gov/geo/samples/GSM2842nnn/GSM2842830/suppl/"
        + audit.MEMBER_NAME
    )
    lines = [
        "^DATABASE = Geo",
        "!Series_overall_design = Two lanes of sequencing from one ribosome profiling experiment",
        "^SAMPLE = GSM2842830",
        "!Sample_organism_ch1 = Saccharomyces cerevisiae",
        "!Sample_characteristics_ch1 = strain: BY474",
        (
            "!Sample_data_processing = Replicates were merged before counting. "
            "RSEM v. 1.3.0 assigned multi-mapping weights using sacCer3."
        ),
        (
            "!Sample_data_processing = A-site offsets: (27,0)->15, (27,1)->14, "
            "(28,0)->15, (29,0)->15, (29,2)->16."
        ),
        f"!Sample_supplementary_file_1 = {supplementary_url}",
    ]
    return gzip.compress(("\n".join(lines) + "\n").encode()), supplementary_url


def write_case(
    tmp_path,
    rows=None,
    raw_bytes=None,
    soft_bytes=None,
):
    if rows is None:
        rows = [("YAL001C", ["1", "2.5e-1", "0"]), ("YAL002W", ["0", "0"])]
    payload = member_bytes(rows)
    raw = synthetic_tar(gzip.compress(payload)) if raw_bytes is None else raw_bytes
    soft = synthetic_soft() if soft_bytes is None else soft_bytes
    raw_path = tmp_path / "GSE106572_RAW.tar"
    soft_path = tmp_path / "GSE106572_family.soft.gz"
    raw_path.write_bytes(raw)
    soft_path.write_bytes(soft)
    protocol = json.loads(FROZEN_PROTOCOL.read_text())
    protocol["inputs"]["raw_tar"]["sha256"] = sha256(raw)
    protocol["inputs"]["soft_gz"]["sha256"] = sha256(soft)
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol))
    clean = tmp_path / "outputs" / "clean.csv"
    report = tmp_path / "outputs" / "report.json"
    args = [
        "--raw-tar", str(raw_path),
        "--soft-gz", str(soft_path),
        "--protocol", str(protocol_path),
        "--clean-csv", str(clean),
        "--report-json", str(report),
    ]
    return {
        "args": args,
        "raw": raw,
        "soft": soft,
        "payload": payload,
        "clean": clean,
        "report": report,
        "raw_path": raw_path,
        "soft_path": soft_path,
    }


def assert_no_outputs(case):
    assert not case["clean"].exists()
    assert not case["report"].exists()


def test_frozen_protocol_pins_official_assets_and_claim_boundaries():
    protocol = json.loads(FROZEN_PROTOCOL.read_text())
    assert protocol["protocol"] == audit.PROTOCOL
    assert protocol["inputs"]["raw_tar"] == {
        "url": "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE106nnn/GSE106572/suppl/GSE106572_RAW.tar",
        "sha256": "77e463a2ff17b3049bf1d7cc11325e5fa2510a9dee9680970ba5c7a241054e8d",
        "required_members": [audit.MEMBER_NAME],
        "member_format": protocol["inputs"]["raw_tar"]["member_format"],
    }
    assert protocol["inputs"]["soft_gz"] == {
        "url": "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE106nnn/GSE106572/soft/GSE106572_family.soft.gz",
        "sha256": "bece19f4017a51558a0475ba2b1f775556d038df573194f5a6351a949b0393d1",
    }
    offsets = protocol["soft_qualification"]["a_site_offsets"]
    assert [
        (item["read_length"], item["frame"], item["offset"]) for item in offsets
    ] == [(27, 0, 15), (27, 1, 14), (28, 0, 15), (29, 0, 15), (29, 2, 16)]
    eligibility = protocol["study"]["eligibility"]
    assert eligibility["task"] == "T2_translation_occupancy_and_kinetics"
    assert eligibility["candidate_research_only"] is True
    assert eligibility["procedure_and_qc_only"] is True
    assert eligibility["final_untouched"] is False
    assert eligibility["scientific_positive_claim_eligible"] is False
    assert protocol["count_rules"]["allow_noninteger_multimapping_weights"] is True
    assert protocol["count_rules"]["round_counts"] is False
    assert protocol["outputs"]["overwrite"] == "forbidden"


def test_valid_synthetic_inputs_preserve_counts_and_write_complete_qc(tmp_path):
    case = write_case(tmp_path)

    assert audit.main(case["args"]) == 0

    assert case["clean"].read_text() == (
        "gene,codon_index,count\n"
        "YAL001C,1,1\n"
        "YAL001C,2,2.5e-1\n"
        "YAL001C,3,0\n"
        "YAL002W,1,0\n"
        "YAL002W,2,0\n"
    )
    report = json.loads(case["report"].read_text())
    assert report["protocol"] == audit.PROTOCOL
    assert report["status"] == "candidate_procedure_and_qc_passed"
    assert report["scope"] == "procedure_and_qc_only_no_functional_or_model_conclusion"
    assert report["task_eligibility"]["candidate_research_only"] is True
    assert report["task_eligibility"]["final_untouched"] is False
    assert report["task_eligibility"]["scientific_positive_claim_eligible"] is False
    assert report["sha256"] == {
        "raw_tar": sha256(case["raw"]),
        "soft_gz": sha256(case["soft"]),
        "protocol": sha256((tmp_path / "protocol.json").read_bytes()),
        "raw_member_uncompressed": sha256(case["payload"]),
        "clean_csv": sha256(case["clean"].read_bytes()),
    }
    assert report["raw_qc"] == {
        "raw_data_rows": 2,
        "duplicate_gene_rows": 0,
        "empty_gene_rows": 0,
        "malformed_rows": 0,
        "invalid_count_values": 0,
        "negative_count_values": 0,
        "nonfinite_count_values": 0,
        "clean_rows": 5,
        "unique_genes": 2,
        "cds_codon_count_distribution": {"2": 1, "3": 1},
        "cds_codon_count_summary": {"min": 2, "max": 3, "mean": 2.5},
    }
    first, second = report["transcript_qc"]
    assert first["total_coverage"] == 1.25
    assert first["zero_coverage_positions"] == 1
    assert first["zero_coverage_fraction"] == pytest.approx(1 / 3)
    assert first["long_tail"] == {
        "top_10pct_positions": 1,
        "top_10pct_count_share": 0.8,
        "max_count_share": 0.8,
    }
    assert second["total_coverage"] == 0
    assert second["zero_coverage_positions"] == 2
    assert second["long_tail"]["top_10pct_count_share"] is None
    assert second["long_tail"]["max_count_share"] is None
    metadata = report["soft_metadata"]
    assert metadata["sample_ids"] == ["GSM2842830"]
    assert metadata["ribo_experiment_count"] == 1
    assert metadata["lane_count"] == 2
    assert metadata["lanes_merged_before_analysis"] is True
    assert metadata["rsem_version"] == "1.3.0"
    assert metadata["multimapping_weighted"] is True
    assert metadata["genome_build"] == "sacCer3"
    assert metadata["a_site_offsets_match_protocol"] is True
    assert metadata["missing_fields"] == []
    assert report["duplicate_metadata"]["identical_field_rows"] == 0
    assert report["limitations"]


def test_real_soft_fragment_with_series_design_and_numbered_supplementary_file(tmp_path):
    soft_bytes, supplementary_url = real_soft_fragment()
    case = write_case(tmp_path, soft_bytes=soft_bytes)

    assert audit.main(case["args"]) == 0
    metadata = json.loads(case["report"].read_text())["soft_metadata"]
    assert metadata["series_overall_design"] == [
        "Two lanes of sequencing from one ribosome profiling experiment"
    ]
    assert metadata["supplementary_files"] == [supplementary_url]
    assert metadata["lanes_merged_before_analysis"] is True
    assert metadata["ribo_experiment_count"] == 1
    assert metadata["lane_count"] == 2
    assert metadata["rsem_version"] == "1.3.0"
    assert metadata["multimapping_weighted"] is True
    assert metadata["a_site_offsets_match_protocol"] is True
    assert metadata["missing_fields"] == []


def test_duplicate_soft_metadata_is_reported_without_silent_deduplication(tmp_path):
    case = write_case(tmp_path, soft_bytes=synthetic_soft(repeat_processing=True))

    assert audit.main(case["args"]) == 0
    report = json.loads(case["report"].read_text())
    duplicates = report["duplicate_metadata"]
    assert duplicates["identical_field_rows"] == 1
    assert duplicates["deduplication_applied"] is False
    assert duplicates["identical_field_examples"][0]["field"] == "Sample_data_processing"
    processing = report["soft_metadata"]["data_processing"]
    assert len(processing) == 5


def test_duplicate_gene_fails_without_outputs(tmp_path):
    rows = [("YAL001C", ["1"]), ("YAL001C", ["2"])]
    case = write_case(tmp_path, rows=rows)

    with pytest.raises(ValueError, match="duplicate gene 'YAL001C'"):
        audit.main(case["args"])
    assert_no_outputs(case)


@pytest.mark.parametrize(
    "token, message",
    [
        ("not-a-number", "invalid count"),
        ("-0.25", "negative count"),
        ("NaN", "non-finite count"),
        ("inf", "non-finite count"),
    ],
)
def test_invalid_negative_and_nonfinite_counts_fail(tmp_path, token, message):
    case = write_case(tmp_path, rows=[("YAL001C", ["1", token])])

    with pytest.raises(ValueError, match=message):
        audit.main(case["args"])
    assert_no_outputs(case)


@pytest.mark.parametrize(
    "rows, message",
    [
        ([("", ["1"])], "empty gene"),
        ([("YAL001C", [])], r"malformed gene \+ counts row"),
    ],
)
def test_empty_gene_and_missing_counts_fail(tmp_path, rows, message):
    case = write_case(tmp_path, rows=rows)

    with pytest.raises(ValueError, match=message):
        audit.main(case["args"])
    assert_no_outputs(case)


def test_path_traversal_member_is_rejected_before_name_validation(tmp_path):
    raw = synthetic_tar(gzip.compress(b"YAL001C\t1\n"), member_name="../escape.txt.gz")
    case = write_case(tmp_path, raw_bytes=raw)

    with pytest.raises(ValueError, match="unsafe raw tar member path"):
        audit.main(case["args"])
    assert_no_outputs(case)


def test_extra_tar_member_is_rejected(tmp_path):
    raw = synthetic_tar(gzip.compress(b"YAL001C\t1\n"), extra_member=True)
    case = write_case(tmp_path, raw_bytes=raw)

    with pytest.raises(ValueError, match="exactly one member"):
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


@pytest.mark.parametrize("input_key, label", [("raw_path", "raw tar"), ("soft_path", "SOFT gzip")])
def test_input_hash_mismatch_fails(tmp_path, input_key, label):
    case = write_case(tmp_path)
    case[input_key].write_bytes(case[input_key].read_bytes() + b"hash mismatch")

    with pytest.raises(ValueError, match=rf"{label} SHA256 mismatch"):
        audit.main(case["args"])
    assert_no_outputs(case)


def test_hash_mismatch_cli_exits_nonzero(tmp_path):
    case = write_case(tmp_path)
    case["raw_path"].write_bytes(case["raw"] + b"changed")

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), *case["args"]],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode != 0
    assert "raw tar SHA256 mismatch" in completed.stderr
    assert_no_outputs(case)


def test_missing_required_a_site_metadata_fails(tmp_path):
    case = write_case(tmp_path, soft_bytes=synthetic_soft(omit_a_site=True))

    with pytest.raises(ValueError, match="missing fields:.*A-site offset"):
        audit.main(case["args"])
    assert_no_outputs(case)
