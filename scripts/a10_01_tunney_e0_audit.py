"""Audit frozen Tunney GSE106572 E0 inputs and write a non-overwriting codon long table."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
import sys
import tarfile
from collections import Counter
from pathlib import Path, PurePosixPath


PROTOCOL = "a10_01_tunney_e0_protocol_v1"
REPORT_SCHEMA = "a10-01-tunney-e0-audit-report-v1"
MEMBER_NAME = "GSM2842830_cts_by_codon.size.27.29.txt.gz"
CLEAN_COLUMNS = ["gene", "codon_index", "count"]
OFFSET_PATTERN = re.compile(
    r"(?<![0-9])\(?\s*(27|28|29)\s*,\s*([012])\s*\)?\s*(?:->|=>|→|:|=)\s*([0-9]+)",
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--raw-tar", required=True, help="Downloaded GSE106572_RAW.tar")
    parser.add_argument("--soft-gz", required=True, help="Downloaded GSE106572_family.soft.gz")
    parser.add_argument("--protocol", required=True, help="Frozen E0 protocol JSON")
    parser.add_argument("--clean-csv", required=True, help="New clean codon-long CSV output")
    parser.add_argument("--report-json", required=True, help="New QC report JSON output")
    return parser.parse_args(argv)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_file(value, label):
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"{label} not found or not a regular file: {path}")
    return path


def validate_args(args):
    raw_tar = input_file(args.raw_tar, "raw tar")
    soft_gz = input_file(args.soft_gz, "SOFT gzip")
    protocol_path = input_file(args.protocol, "protocol")
    clean_csv = Path(args.clean_csv).expanduser().resolve()
    report_json = Path(args.report_json).expanduser().resolve()
    if clean_csv == report_json:
        raise ValueError("clean CSV and report JSON must be different paths")
    for path in (clean_csv, report_json):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
    return raw_tar, soft_gz, protocol_path, clean_csv, report_json


def load_protocol(path):
    with path.open(encoding="utf-8") as handle:
        protocol = json.load(handle)
    if protocol.get("protocol") != PROTOCOL:
        raise ValueError(f"protocol identity mismatch: expected {PROTOCOL}")
    inputs = protocol.get("inputs", {})
    for key in ("raw_tar", "soft_gz"):
        if not re.fullmatch(r"[0-9a-f]{64}", inputs.get(key, {}).get("sha256", "")):
            raise ValueError(f"protocol inputs.{key}.sha256 must be a lowercase SHA256")
    members = inputs.get("raw_tar", {}).get("required_members")
    if members != [MEMBER_NAME]:
        raise ValueError(f"protocol must freeze exactly one raw member: {MEMBER_NAME}")
    offsets = protocol.get("soft_qualification", {}).get("a_site_offsets")
    if not isinstance(offsets, list) or not offsets:
        raise ValueError("protocol must freeze A-site offsets")
    return protocol


def verify_sha256(path, expected, label):
    observed = sha256_file(path)
    if observed != expected:
        raise ValueError(
            f"{label} SHA256 mismatch: expected {expected}, observed {observed}",
        )
    return observed


def parse_soft(path, protocol):
    samples = []
    series_fields = {}
    duplicate_metadata = []
    current = None
    with gzip.open(path, "rt", encoding="utf-8", errors="strict", newline="") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\r\n")
            if line.startswith("^SAMPLE"):
                _, separator, sample_id = line.partition("=")
                if not separator or not sample_id.strip():
                    raise ValueError(f"SOFT line {line_number}: malformed SAMPLE declaration")
                current = {"sample_id": sample_id.strip(), "fields": {}}
                samples.append(current)
                continue
            if line.startswith("!Series_"):
                key_value = line[1:].split("=", 1)
                if len(key_value) != 2:
                    raise ValueError(f"SOFT line {line_number}: malformed series metadata")
                key = key_value[0].strip()
                value = key_value[1].strip()
                if not key or not value:
                    raise ValueError(f"SOFT line {line_number}: empty series metadata field")
                series_fields.setdefault(key, []).append(value)
                continue
            if current is None or not line.startswith("!Sample_"):
                continue
            key_value = line[1:].split("=", 1)
            if len(key_value) != 2:
                raise ValueError(f"SOFT line {line_number}: malformed sample metadata")
            key = key_value[0].strip()
            value = key_value[1].strip()
            if not key or not value:
                raise ValueError(f"SOFT line {line_number}: empty sample metadata field")
            values = current["fields"].setdefault(key, [])
            if value in values:
                duplicate_metadata.append({
                    "sample_id": current["sample_id"], "field": key, "value": value,
                })
            values.append(value)

    qualification = protocol["soft_qualification"]
    expected_sample_id = protocol["study"]["sample_accession"]
    sample_id_counts = Counter(sample["sample_id"] for sample in samples)
    duplicate_sample_ids = sorted(
        sample_id for sample_id, count in sample_id_counts.items() if count > 1
    )
    if duplicate_sample_ids:
        raise ValueError(f"duplicate SOFT sample declarations: {duplicate_sample_ids}")
    if len(samples) != qualification["expected_sample_count"]:
        raise ValueError(
            f"SOFT sample count mismatch: expected {qualification['expected_sample_count']}, "
            f"observed {len(samples)}",
        )
    if not samples or samples[0]["sample_id"] != expected_sample_id:
        observed = samples[0]["sample_id"] if samples else None
        raise ValueError(f"SOFT sample mismatch: expected {expected_sample_id}, observed {observed}")

    fields = samples[0]["fields"]

    def values(*keys):
        result = []
        for key in keys:
            for field, field_values in fields.items():
                numbered_supplementary = (
                    key == "Sample_supplementary_file"
                    and re.fullmatch(r"Sample_supplementary_file_[0-9]+", field)
                )
                if field == key or numbered_supplementary:
                    result.extend(field_values)
        return result

    missing_fields = [
        key for key in qualification["required_sample_fields"] if not values(key)
    ]

    organisms = values("Sample_organism_ch1")
    characteristics = values(
        "Sample_characteristics_ch1", "Sample_source_name_ch1", "Sample_description",
    )
    processing = values("Sample_data_processing")
    supplementary_files = values("Sample_supplementary_file")
    series_overall_design = series_fields.get("Series_overall_design", [])
    processing_text = "\n".join(processing)
    lane_evidence_text = "\n".join([*series_overall_design, *processing]).casefold()

    if protocol["study"]["organism"] not in organisms:
        missing_fields.append(f"organism:{protocol['study']['organism']}")
    if not any(re.search(r"\bBY474\b", value) for value in characteristics):
        missing_fields.append(f"strain:{protocol['study']['strain']}")
    lane_merge_verified = all((
        "ribo" in lane_evidence_text,
        re.search(
            r"\bone\s+(?:[a-z0-9]+(?:-[a-z0-9]+)*\s+){0,5}experiment\b",
            lane_evidence_text,
        ) is not None,
        re.search(r"\btwo\s+lanes\b", lane_evidence_text) is not None,
        re.search(r"\b(?:replicates|lanes)\s+were\s+merged\b", lane_evidence_text) is not None,
    ))
    if not lane_merge_verified:
        missing_fields.append("one Ribo experiment with two merged lanes")

    rsem_version = qualification["expected_rsem_version"]
    rsem_verified = re.search(
        rf"\bRSEM\s+(?:v\.?\s*)?{re.escape(rsem_version)}\b",
        processing_text,
        flags=re.IGNORECASE,
    ) is not None
    if not rsem_verified:
        missing_fields.append(f"RSEM:{rsem_version}")
    multimapping_weighted = (
        re.search(r"multi[-\s]?mapping", processing_text, flags=re.IGNORECASE) is not None
        and re.search(r"weight", processing_text, flags=re.IGNORECASE) is not None
    )
    if not multimapping_weighted:
        missing_fields.append("RSEM multi-mapping weights")
    if protocol["study"]["genome_build"] not in processing_text:
        missing_fields.append(f"genome_build:{protocol['study']['genome_build']}")
    if not any(Path(value).name == MEMBER_NAME for value in supplementary_files):
        missing_fields.append(f"supplementary_file:{MEMBER_NAME}")

    observed_offset_map = {}
    offset_conflicts = []
    for value in processing:
        if "offset" not in value.casefold() and "a-site" not in value.casefold():
            continue
        for match in OFFSET_PATTERN.finditer(value):
            key = (int(match.group(1)), int(match.group(2)))
            offset = int(match.group(3))
            if key in observed_offset_map and observed_offset_map[key] != offset:
                offset_conflicts.append({
                    "read_length": key[0], "frame": key[1],
                    "offsets": [observed_offset_map[key], offset],
                })
            observed_offset_map[key] = offset
    expected_offsets = [
        (item["read_length"], item["frame"], item["offset"])
        for item in qualification["a_site_offsets"]
    ]
    for read_length, frame, offset in expected_offsets:
        observed = observed_offset_map.get((read_length, frame))
        if observed is None:
            missing_fields.append(f"A-site offset:({read_length},{frame})->{offset}")
        elif observed != offset:
            offset_conflicts.append({
                "read_length": read_length, "frame": frame,
                "expected": offset, "observed": observed,
            })
    if offset_conflicts:
        raise ValueError(f"conflicting SOFT A-site offsets: {offset_conflicts}")
    if missing_fields:
        raise ValueError(
            "SOFT metadata qualification failed; missing fields: "
            + ", ".join(missing_fields),
        )

    observed_offsets = [
        {"read_length": read_length, "frame": frame, "offset": observed_offset_map[(read_length, frame)]}
        for read_length, frame in sorted(observed_offset_map)
    ]
    return {
        "sample_count": len(samples),
        "sample_ids": [sample["sample_id"] for sample in samples],
        "organisms": organisms,
        "characteristics": characteristics,
        "series_overall_design": series_overall_design,
        "data_processing": processing,
        "supplementary_files": supplementary_files,
        "ribo_experiment_count": qualification["expected_ribo_experiment_count"],
        "lane_count": qualification["expected_lane_count"],
        "lanes_merged_before_analysis": lane_merge_verified,
        "rsem_version": rsem_version,
        "multimapping_weighted": multimapping_weighted,
        "genome_build": protocol["study"]["genome_build"],
        "a_site_offsets": observed_offsets,
        "a_site_offsets_match_protocol": all(
            observed_offset_map.get((read_length, frame)) == offset
            for read_length, frame, offset in expected_offsets
        ),
        "missing_fields": missing_fields,
    }, {
        "duplicate_sample_ids": duplicate_sample_ids,
        "identical_field_rows": len(duplicate_metadata),
        "identical_field_examples": duplicate_metadata[:20],
        "deduplication_applied": False,
    }


def validate_member_path(member):
    name = member.name
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or "\x00" in name:
        raise ValueError(f"unsafe raw tar member path: {name!r}")


def transcript_qc(gene, values):
    codon_count = len(values)
    zero_positions = sum(value == 0 for value in values)
    total = math.fsum(values)
    if not math.isfinite(total):
        raise ValueError(f"transcript {gene!r}: non-finite total coverage")
    maximum = max(values)
    top_count = max(1, math.ceil(codon_count * 0.10))
    if total > 0:
        top_share = math.fsum(sorted(values, reverse=True)[:top_count]) / total
        max_share = maximum / total
    else:
        top_share = None
        max_share = None
    return {
        "gene": gene,
        "cds_codon_count": codon_count,
        "total_coverage": total,
        "nonzero_coverage_positions": codon_count - zero_positions,
        "zero_coverage_positions": zero_positions,
        "zero_coverage_fraction": zero_positions / codon_count,
        "long_tail": {
            "top_10pct_positions": top_count,
            "top_10pct_count_share": top_share,
            "max_count_share": max_share,
        },
    }


def parse_raw_member(raw_tar, protocol):
    records = []
    transcripts = []
    codon_count_distribution = Counter()
    seen_genes = set()
    member_digest = hashlib.sha256()
    counters = {
        "raw_data_rows": 0,
        "duplicate_gene_rows": 0,
        "empty_gene_rows": 0,
        "malformed_rows": 0,
        "invalid_count_values": 0,
        "negative_count_values": 0,
        "nonfinite_count_values": 0,
    }
    with tarfile.open(raw_tar, mode="r:*") as archive:
        members = archive.getmembers()
        for member in members:
            validate_member_path(member)
        if len(members) != 1:
            raise ValueError(f"raw tar must contain exactly one member; observed {len(members)}")
        member = members[0]
        if not member.isfile():
            raise ValueError(f"raw tar member is not a regular file: {member.name}")
        if member.name != MEMBER_NAME:
            raise ValueError(f"unexpected raw tar member: {member.name!r}; expected {MEMBER_NAME!r}")
        extracted = archive.extractfile(member)
        if extracted is None:
            raise ValueError(f"unable to read raw tar member: {member.name}")
        with extracted, gzip.GzipFile(fileobj=extracted, mode="rb") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                member_digest.update(raw_line)
                counters["raw_data_rows"] += 1
                try:
                    line = raw_line.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ValueError(f"raw member line {line_number}: invalid UTF-8") from exc
                fields = line.rstrip("\r\n").split("\t")
                gene = fields[0]
                if not gene.strip():
                    counters["empty_gene_rows"] += 1
                    raise ValueError(f"raw member line {line_number}: empty gene")
                if gene != gene.strip() or len(fields) < 2 or (len(fields) == 2 and not fields[1]):
                    counters["malformed_rows"] += 1
                    raise ValueError(
                        f"raw member line {line_number}: malformed gene + counts row",
                    )
                if gene in seen_genes:
                    counters["duplicate_gene_rows"] += 1
                    raise ValueError(f"raw member line {line_number}: duplicate gene {gene!r}")
                seen_genes.add(gene)
                tokens = fields[1:]
                values = []
                for codon_index, token in enumerate(tokens, start=1):
                    if not token or token != token.strip():
                        counters["invalid_count_values"] += 1
                        raise ValueError(
                            f"raw member line {line_number}, codon {codon_index}: invalid count {token!r}",
                        )
                    try:
                        value = float(token)
                    except ValueError as exc:
                        counters["invalid_count_values"] += 1
                        raise ValueError(
                            f"raw member line {line_number}, codon {codon_index}: invalid count {token!r}",
                        ) from exc
                    if not math.isfinite(value):
                        counters["nonfinite_count_values"] += 1
                        raise ValueError(
                            f"raw member line {line_number}, codon {codon_index}: non-finite count {token!r}",
                        )
                    if value < 0:
                        counters["negative_count_values"] += 1
                        raise ValueError(
                            f"raw member line {line_number}, codon {codon_index}: negative count {token!r}",
                        )
                    values.append(value)
                    records.append((gene, codon_index, token))
                codon_count_distribution[len(values)] += 1
                transcripts.append(transcript_qc(gene, values))
    if not records:
        raise ValueError("raw member contains no gene + count rows")
    distribution = {
        str(count): codon_count_distribution[count] for count in sorted(codon_count_distribution)
    }
    codon_counts = [
        transcript["cds_codon_count"] for transcript in transcripts
    ]
    counters.update({
        "clean_rows": len(records),
        "unique_genes": len(seen_genes),
        "cds_codon_count_distribution": distribution,
        "cds_codon_count_summary": {
            "min": min(codon_counts),
            "max": max(codon_counts),
            "mean": math.fsum(codon_counts) / len(codon_counts),
        },
    })
    return records, transcripts, counters, member_digest.hexdigest()


def write_clean(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(CLEAN_COLUMNS)
        writer.writerows(records)
    return sha256_file(path)


def run_audit(args):
    raw_tar, soft_gz, protocol_path, clean_csv, report_json = validate_args(args)
    protocol = load_protocol(protocol_path)
    raw_sha = verify_sha256(
        raw_tar, protocol["inputs"]["raw_tar"]["sha256"], "raw tar",
    )
    soft_sha = verify_sha256(
        soft_gz, protocol["inputs"]["soft_gz"]["sha256"], "SOFT gzip",
    )
    soft_metadata, duplicate_metadata = parse_soft(soft_gz, protocol)
    records, transcripts, raw_qc, member_sha = parse_raw_member(raw_tar, protocol)
    clean_sha = write_clean(clean_csv, records)
    report = {
        "schema": REPORT_SCHEMA,
        "protocol": PROTOCOL,
        "status": "candidate_procedure_and_qc_passed",
        "scope": "procedure_and_qc_only_no_functional_or_model_conclusion",
        "task_eligibility": protocol["study"]["eligibility"],
        "inputs": {
            "raw_tar": str(raw_tar),
            "soft_gz": str(soft_gz),
            "protocol": str(protocol_path),
            "raw_member": MEMBER_NAME,
        },
        "sha256": {
            "raw_tar": raw_sha,
            "soft_gz": soft_sha,
            "protocol": sha256_file(protocol_path),
            "raw_member_uncompressed": member_sha,
            "clean_csv": clean_sha,
        },
        "clean_csv": {
            "path": str(clean_csv),
            "columns": CLEAN_COLUMNS,
            "data_rows": len(records),
            "codon_index_base": 1,
            "count_representation": "original input token without rounding or normalization",
        },
        "raw_qc": raw_qc,
        "transcript_qc": transcripts,
        "soft_metadata": soft_metadata,
        "duplicate_metadata": duplicate_metadata,
        "limitations": protocol["limitations"],
    }
    report_json.parent.mkdir(parents=True, exist_ok=True)
    with report_json.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    print(json.dumps({
        "status": report["status"],
        "clean_csv": str(clean_csv),
        "report_json": str(report_json),
        "clean_rows": len(records),
        "unique_genes": raw_qc["unique_genes"],
    }))
    return report


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    run_audit(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
