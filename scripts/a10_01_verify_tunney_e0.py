"""Independently verify the candidate Tunney GSE106572 E0 clean table and report."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import re
import sys
import tarfile
from decimal import Decimal, InvalidOperation
from pathlib import Path


PROTOCOL = "a10_01_tunney_e0_independent_verification_v1"
EXPECTED_REPORT_SCHEMA = "a10-01-tunney-e0-audit-report-v1"
EXPECTED_REPORT_PROTOCOL = "a10_01_tunney_e0_protocol_v1"
EXPECTED_RAW_SHA256 = "77e463a2ff17b3049bf1d7cc11325e5fa2510a9dee9680970ba5c7a241054e8d"
EXPECTED_RAW_MEMBER = "GSM2842830_cts_by_codon.size.27.29.txt.gz"
EXPECTED_CLEAN_COLUMNS = ["gene", "codon_index", "count"]
EXPECTED_SCOPE = "procedure_and_qc_only_no_functional_or_model_conclusion"
SAFE_CLAIM_STATUSES = {
    "candidate",
    "candidate_procedure_and_qc_passed",
    "candidate_only",
    "candidate_research",
    "candidate_research_only",
    "candidate_not_untouched_no_positive_claim",
}
UNSAFE_CLAIM_STATUSES = {
    "final_untouched",
    "untouched",
    "scientific_positive",
    "scientifically_positive",
    "positive",
}
RAW_ERROR_COUNTERS = (
    "duplicate_gene_rows",
    "empty_gene_rows",
    "malformed_rows",
    "invalid_count_values",
    "negative_count_values",
    "nonfinite_count_values",
)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_decimal(value, label):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError(f"{label} must be an exact nonnegative number")
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} is not a valid decimal: {value!r}") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"{label} must be finite and nonnegative: {value!r}")
    return number


def decimal_text(value):
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def json_number(value):
    if value == value.to_integral_value():
        return int(value)
    return decimal_text(value)


def json_safe(value):
    if isinstance(value, Decimal):
        return json_number(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def read_raw_counts(raw_tar):
    counts = {}
    with tarfile.open(raw_tar, mode="r:") as archive:
        members = archive.getmembers()
        if len(members) != 1:
            raise ValueError(f"raw tar must contain exactly one member, found {len(members)}")
        member = members[0]
        if member.name != EXPECTED_RAW_MEMBER or not member.isfile():
            raise ValueError(f"unexpected raw tar member: {member.name!r}")
        extracted = archive.extractfile(member)
        if extracted is None:
            raise ValueError(f"cannot read raw tar member: {member.name}")
        with extracted, gzip.GzipFile(fileobj=extracted, mode="rb") as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                for line_number, line in enumerate(text, start=1):
                    fields = line.rstrip("\r\n").split("\t")
                    if len(fields) < 2:
                        raise ValueError(f"raw line {line_number} must contain a gene and codon counts")
                    gene = fields[0]
                    if not gene or gene != gene.strip():
                        raise ValueError(f"raw line {line_number} has an invalid gene")
                    if gene in counts:
                        raise ValueError(f"duplicate raw gene {gene!r} at line {line_number}")
                    tokens = fields[1:]
                    if any(not token or token != token.strip() for token in tokens):
                        raise ValueError(f"raw line {line_number} has an invalid count token")
                    counts[gene] = [
                        parse_decimal(token, f"raw line {line_number} count")
                        for token in tokens
                    ]
    if not counts:
        raise ValueError("raw count table is empty")
    return counts


def read_clean_counts(clean_csv):
    reconstructed = {}
    row_count = 0
    count_sum = Decimal(0)
    with Path(clean_csv).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != EXPECTED_CLEAN_COLUMNS:
            raise ValueError("clean CSV columns must be exactly gene, codon_index, count")
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(row.get(name) is None for name in EXPECTED_CLEAN_COLUMNS):
                raise ValueError(f"clean CSV line {line_number} has missing or extra fields")
            gene = row["gene"]
            if not re.fullmatch(r"\S+", gene or ""):
                raise ValueError(f"clean CSV line {line_number} has an invalid gene")
            index_text = row["codon_index"]
            if not re.fullmatch(r"[1-9][0-9]*", index_text or ""):
                raise ValueError(f"clean CSV line {line_number} has a noncanonical one-based index")
            index = int(index_text)
            count = parse_decimal(row["count"], f"clean CSV line {line_number} count")
            gene_counts = reconstructed.setdefault(gene, {})
            if index in gene_counts:
                raise ValueError(f"duplicate clean gene/index pair: {gene!r}/{index}")
            gene_counts[index] = count
            row_count += 1
            count_sum += count
    return reconstructed, row_count, count_sum


def summarize_counts(counts):
    lengths = [len(values) for values in counts.values()]
    distribution = {}
    for length in lengths:
        distribution[length] = distribution.get(length, 0) + 1
    return {
        "transcript_count": len(counts),
        "codon_count": sum(lengths),
        "count_sum": sum((sum(values, Decimal(0)) for values in counts.values()), Decimal(0)),
        "zero_coverage_transcripts": sum(
            all(value == 0 for value in values) for values in counts.values()
        ),
        "zero_coverage_codons": sum(
            value == 0 for values in counts.values() for value in values
        ),
        "min_length": min(lengths),
        "max_length": max(lengths),
        "mean_length": Decimal(sum(lengths)) / Decimal(len(lengths)),
        "length_distribution": {
            str(length): distribution[length] for length in sorted(distribution)
        },
    }


def compare_clean_counts(raw_counts, clean_counts, clean_rows, clean_sum):
    expected_rows = sum(len(values) for values in raw_counts.values())
    differences = []
    checks = {
        "clean_row_count": clean_rows == expected_rows,
        "clean_gene_set": set(clean_counts) == set(raw_counts),
        "clean_indices": True,
        "clean_counts": True,
        "clean_count_sum": clean_sum == sum(
            (sum(values, Decimal(0)) for values in raw_counts.values()), Decimal(0)
        ),
    }
    for gene in sorted(set(raw_counts) - set(clean_counts)):
        differences.append({"kind": "missing_gene", "gene": gene})
    for gene in sorted(set(clean_counts) - set(raw_counts)):
        differences.append({"kind": "unexpected_gene", "gene": gene})
    for gene in sorted(set(raw_counts) & set(clean_counts)):
        expected = raw_counts[gene]
        observed = clean_counts[gene]
        expected_indices = set(range(1, len(expected) + 1))
        observed_indices = set(observed)
        if observed_indices != expected_indices:
            checks["clean_indices"] = False
            differences.append({
                "kind": "index_mismatch",
                "gene": gene,
                "missing": sorted(expected_indices - observed_indices),
                "unexpected": sorted(observed_indices - expected_indices),
            })
        for index in sorted(expected_indices & observed_indices):
            if observed[index] != expected[index - 1]:
                checks["clean_counts"] = False
                differences.append({
                    "kind": "count_mismatch",
                    "gene": gene,
                    "index": index,
                    "expected": json_number(expected[index - 1]),
                    "observed": json_number(observed[index]),
                })
    checks["clean_exact"] = all(checks.values()) and not differences
    return checks, differences


def exact_integer(value, expected):
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def close_number(value, expected):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return False
    try:
        observed = float(value)
        target = float(expected)
    except (OverflowError, ValueError):
        return False
    return math.isfinite(observed) and math.isclose(
        observed, target, rel_tol=1e-12, abs_tol=1e-12,
    )


def parse_length_distribution(value):
    if not isinstance(value, dict):
        raise ValueError("reported CDS codon-count distribution must be an object")
    parsed = {}
    for raw_length, raw_count in value.items():
        if not re.fullmatch(r"[1-9][0-9]*", str(raw_length)):
            raise ValueError(f"invalid reported codon length: {raw_length!r}")
        if not isinstance(raw_count, int) or isinstance(raw_count, bool) or raw_count < 0:
            raise ValueError("reported length-distribution counts must be nonnegative integers")
        parsed[int(raw_length)] = raw_count
    return parsed


def compare_report_summary(report, raw_counts, recomputed):
    raw_qc = report.get("raw_qc")
    transcript_qc = report.get("transcript_qc")
    clean_info = report.get("clean_csv")
    check_names = (
        "report_transcript_count", "report_codon_count", "report_count_sum",
        "report_zero_coverage", "report_length_distribution", "report_length_summary",
        "report_transcript_qc", "report_raw_qc_clean", "report_clean_schema",
    )
    if not isinstance(raw_qc, dict) or not isinstance(transcript_qc, list) or not isinstance(clean_info, dict):
        return {name: False for name in (*check_names, "report_summary")}, {
            "error": "report raw_qc, transcript_qc and clean_csv must have their frozen types",
        }

    expected_distribution = {
        int(length): count for length, count in recomputed["length_distribution"].items()
    }
    try:
        observed_distribution = parse_length_distribution(
            raw_qc.get("cds_codon_count_distribution"),
        )
    except ValueError:
        observed_distribution = None
    length_summary = raw_qc.get("cds_codon_count_summary")
    if not isinstance(length_summary, dict):
        length_summary = {}

    checks = {
        "report_transcript_count": (
            exact_integer(raw_qc.get("unique_genes"), recomputed["transcript_count"])
            and exact_integer(raw_qc.get("raw_data_rows"), recomputed["transcript_count"])
            and len(transcript_qc) == recomputed["transcript_count"]
        ),
        "report_codon_count": (
            exact_integer(raw_qc.get("clean_rows"), recomputed["codon_count"])
            and exact_integer(clean_info.get("data_rows"), recomputed["codon_count"])
        ),
        "report_length_distribution": observed_distribution == expected_distribution,
        "report_length_summary": (
            exact_integer(length_summary.get("min"), recomputed["min_length"])
            and exact_integer(length_summary.get("max"), recomputed["max_length"])
            and close_number(length_summary.get("mean"), recomputed["mean_length"])
        ),
        "report_raw_qc_clean": all(
            exact_integer(raw_qc.get(name), 0) for name in RAW_ERROR_COUNTERS
        ),
        "report_clean_schema": (
            clean_info.get("columns") == EXPECTED_CLEAN_COLUMNS
            and clean_info.get("codon_index_base") == 1
            and clean_info.get("count_representation")
            == "original input token without rounding or normalization"
        ),
    }

    transcript_mismatches = []
    reported_totals = []
    reported_zero_codons = []
    for position, (gene, values) in enumerate(raw_counts.items()):
        row = transcript_qc[position] if position < len(transcript_qc) else None
        if not isinstance(row, dict):
            transcript_mismatches.append({"gene": gene, "field": "row", "reason": "missing"})
            reported_totals.append(None)
            continue
        total = sum(values, Decimal(0))
        zero_positions = sum(value == 0 for value in values)
        top_count = max(1, (len(values) + 9) // 10)
        expected_shares = {
            "top_10pct_count_share": None,
            "max_count_share": None,
        }
        if total > 0:
            expected_shares = {
                "top_10pct_count_share": sum(
                    sorted(values, reverse=True)[:top_count], Decimal(0),
                ) / total,
                "max_count_share": max(values) / total,
            }
        long_tail = row.get("long_tail")
        if not isinstance(long_tail, dict):
            long_tail = {}
        comparisons = {
            "gene": row.get("gene") == gene,
            "cds_codon_count": exact_integer(row.get("cds_codon_count"), len(values)),
            "total_coverage": close_number(row.get("total_coverage"), total),
            "nonzero_coverage_positions": exact_integer(
                row.get("nonzero_coverage_positions"), len(values) - zero_positions,
            ),
            "zero_coverage_positions": exact_integer(
                row.get("zero_coverage_positions"), zero_positions,
            ),
            "zero_coverage_fraction": close_number(
                row.get("zero_coverage_fraction"), Decimal(zero_positions) / Decimal(len(values)),
            ),
            "top_10pct_positions": exact_integer(
                long_tail.get("top_10pct_positions"), top_count,
            ),
        }
        for field, expected in expected_shares.items():
            comparisons[field] = (
                long_tail.get(field) is None if expected is None
                else close_number(long_tail.get(field), expected)
            )
        for field, matched in comparisons.items():
            if not matched:
                transcript_mismatches.append({"gene": gene, "field": field})
        try:
            reported_total = parse_decimal(
                row.get("total_coverage"), f"report transcript {gene} total_coverage",
            )
        except ValueError:
            reported_total = None
        reported_totals.append(reported_total)
        reported_zero = row.get("zero_coverage_positions")
        reported_zero_codons.append(
            reported_zero if isinstance(reported_zero, int) and not isinstance(reported_zero, bool)
            else None
        )
    checks["report_transcript_qc"] = not transcript_mismatches
    checks["report_count_sum"] = (
        all(value is not None for value in reported_totals)
        and len(reported_totals) == recomputed["transcript_count"]
        and close_number(
            sum(reported_totals, Decimal(0)), recomputed["count_sum"],
        )
    )
    checks["report_zero_coverage"] = (
        all(value is not None for value in reported_totals)
        and all(value is not None for value in reported_zero_codons)
        and len(reported_zero_codons) == recomputed["transcript_count"]
        and sum(value == 0 for value in reported_totals if value is not None)
        == recomputed["zero_coverage_transcripts"]
        and sum(reported_zero_codons) == recomputed["zero_coverage_codons"]
    )
    checks["report_summary"] = all(checks.values())
    details = {
        "transcript_mismatches": transcript_mismatches,
        "reported_count_sum": (
            json_number(sum(reported_totals, Decimal(0)))
            if all(value is not None for value in reported_totals) else None
        ),
        "reported_zero_coverage_transcripts": (
            sum(value == 0 for value in reported_totals if value is not None)
            if all(value is not None for value in reported_totals) else None
        ),
        "reported_zero_coverage_codons": (
            sum(reported_zero_codons)
            if all(value is not None for value in reported_zero_codons) else None
        ),
        "reported_length_distribution": (
            {str(key): observed_distribution[key] for key in sorted(observed_distribution)}
            if observed_distribution is not None else None
        ),
    }
    return checks, details


def walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk_dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_dicts(item)


def check_claim_status(report):
    nodes = list(walk_dicts(report))
    candidate_flags = [
        node[key]
        for node in nodes
        for key in ("candidate", "candidate_research", "candidate_research_only", "is_candidate")
        if key in node
    ]
    untouched_flags = [
        node[key]
        for node in nodes
        for key in ("final_untouched", "is_final_untouched", "untouched")
        if key in node
    ]
    positive_flags = [
        node[key]
        for node in nodes
        for key in (
            "scientific_positive", "scientific_positive_claim",
            "scientific_positive_claimed", "scientific_positive_claim_eligible",
            "positive_scientific_claim", "has_scientific_positive_claim",
        )
        if key in node
    ]
    statuses = [
        report[key]
        for key in ("status", "research_status", "data_role", "dataset_role")
        if isinstance(report.get(key), str)
    ]
    normalized_statuses = [value.strip().lower() for value in statuses]
    candidate = (
        any(value is True for value in candidate_flags)
        or any(value in SAFE_CLAIM_STATUSES for value in normalized_statuses)
    )
    candidate = candidate and all(value is True for value in candidate_flags)
    candidate = candidate and not any(value in UNSAFE_CLAIM_STATUSES for value in normalized_statuses)
    eligibility = report.get("task_eligibility")
    if not isinstance(eligibility, dict):
        eligibility = {}
    return {
        "candidate_status": candidate,
        "not_final_untouched": bool(untouched_flags) and all(value is False for value in untouched_flags),
        "no_scientific_positive": bool(positive_flags) and all(value is False for value in positive_flags),
        "procedure_and_qc_scope": (
            report.get("scope") == EXPECTED_SCOPE
            and eligibility.get("procedure_and_qc_only") is True
            and eligibility.get("functional_prediction_eligible") is False
            and eligibility.get("model_training_or_calibration_eligible") is False
        ),
    }, {
        "statuses": statuses,
        "candidate_flags": candidate_flags,
        "untouched_flags": untouched_flags,
        "scientific_positive_flags": positive_flags,
    }


def report_hash_values(report, kind):
    values = []
    sha256_node = report.get("sha256")
    if isinstance(sha256_node, dict):
        key = "raw_tar" if kind == "raw" else "clean_csv"
        if key in sha256_node:
            values.append(sha256_node[key])
    nested = [report.get(key) for key in ("raw", "source", "inputs", "provenance")]
    nodes = [report, *[node for node in nested if isinstance(node, dict)]]
    keys = (
        ("raw_sha256", "raw_tar_sha256")
        if kind == "raw" else ("clean_sha256", "clean_csv_sha256")
    )
    for node in nodes:
        for key in keys:
            if key in node:
                values.append(node[key])
        if node is not report and kind == "raw" and "sha256" in node:
            values.append(node["sha256"])
    return values


def reject_nonfinite_json(value):
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def verify_tunney_e0(raw_tar, clean_csv, report_json, expected_raw_sha256=None):
    expected_raw_sha256 = expected_raw_sha256 or EXPECTED_RAW_SHA256
    raw_sha256 = file_sha256(raw_tar)
    clean_sha256 = file_sha256(clean_csv)
    raw_counts = read_raw_counts(raw_tar)
    clean_counts, clean_rows, clean_sum = read_clean_counts(clean_csv)
    report = json.loads(
        Path(report_json).read_text(encoding="utf-8"),
        parse_float=Decimal,
        parse_constant=reject_nonfinite_json,
    )
    if not isinstance(report, dict):
        raise ValueError("report JSON must be an object")
    recomputed = summarize_counts(raw_counts)
    clean_checks, differences = compare_clean_counts(
        raw_counts, clean_counts, clean_rows, clean_sum,
    )
    summary_checks, summary_details = compare_report_summary(report, raw_counts, recomputed)
    claim_checks, claim_details = check_claim_status(report)
    reported_raw_hashes = report_hash_values(report, "raw")
    reported_clean_hashes = report_hash_values(report, "clean")
    inputs = report.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}
    checks = {
        "raw_sha256": raw_sha256 == expected_raw_sha256,
        "report_raw_sha256": bool(reported_raw_hashes) and all(
            value == raw_sha256 == expected_raw_sha256 for value in reported_raw_hashes
        ),
        "report_clean_sha256": bool(reported_clean_hashes) and all(
            value == clean_sha256 for value in reported_clean_hashes
        ),
        "report_identity": (
            report.get("schema") == EXPECTED_REPORT_SCHEMA
            and report.get("protocol") == EXPECTED_REPORT_PROTOCOL
        ),
        "report_raw_member": inputs.get("raw_member") == EXPECTED_RAW_MEMBER,
        **clean_checks,
        **summary_checks,
        **claim_checks,
    }
    return {
        "protocol": PROTOCOL,
        "passed": all(checks.values()),
        "scope": "candidate_research_only_not_final_untouched_no_scientific_positive_claim",
        "inputs": {
            "raw_tar": str(raw_tar),
            "raw_sha256": raw_sha256,
            "expected_raw_sha256": expected_raw_sha256,
            "raw_member": EXPECTED_RAW_MEMBER,
            "clean_csv": str(clean_csv),
            "clean_sha256": clean_sha256,
            "clean_columns": EXPECTED_CLEAN_COLUMNS,
            "clean_index_base": 1,
            "report_json": str(report_json),
        },
        "checks": checks,
        "recomputed": json_safe(recomputed),
        "report_summary_comparison": summary_details,
        "claim_status_observed": claim_details,
        "differences": differences,
    }


def write_json_exclusive(output, payload):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(json_safe(payload), handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--raw-tar", required=True)
    parser.add_argument("--clean-csv", required=True)
    parser.add_argument("--report", dest="report_json", required=True)
    parser.add_argument("--output", "--out", dest="output", required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    try:
        result = verify_tunney_e0(args.raw_tar, args.clean_csv, args.report_json)
    except Exception as exc:
        result = {
            "protocol": PROTOCOL,
            "passed": False,
            "scope": "candidate_research_only_not_final_untouched_no_scientific_positive_claim",
            "inputs": {
                "raw_tar": args.raw_tar,
                "clean_csv": args.clean_csv,
                "report_json": args.report_json,
            },
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    write_json_exclusive(output, result)
    print(json.dumps({
        "output": str(output), "passed": result["passed"], "checks": result.get("checks", {}),
    }))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
