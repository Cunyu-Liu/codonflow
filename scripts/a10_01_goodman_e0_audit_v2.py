"""Audit frozen Goodman2013 E0 CSV data without filtering or deduplication."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path


PROTOCOL = "a10_01_goodman_e0_protocol_v2"
REPORT_SCHEMA = "a10-01-goodman-e0-audit-report-v2"
SCOPE = "procedure_and_qc_only_no_functional_or_model_conclusion"
OFFICIAL_URL = (
    "https://www.science.org/doi/suppl/10.1126/science.1241934/"
    "suppl_file/1241934tables1.csv"
)
EXPECTED_COLUMN_COUNT = 75
BIN_COLUMNS = [f"Bin.{index}" for index in range(1, 13)]
BIN_PCT_COLUMNS = [f"Bin.Pct.{index}" for index in range(1, 13)]
REQUIRED_COLUMNS = [
    "Name",
    "CDS.seq",
    "Count.DNA",
    "Count.RNA",
    "Count.A.DNA",
    "Count.B.DNA",
    "Count.A.RNA",
    "Count.B.RNA",
    *BIN_COLUMNS,
    "Count.Prot",
    "Promoter",
    "Gene",
    "Promoter.seq",
    "RBS.seq",
    "CDS.type",
    "RBS.len",
    "RNA.A",
    "RNA.B",
    "RNA",
    *BIN_PCT_COLUMNS,
    "Trans",
    "Insuff.Prot",
    "Insuff.DNA",
    "Insuff.RNA",
    "Fltr.BelowRange",
    "Fltr.AboveRange",
    "Fltr.SetGood",
    "CAI",
    "tAI",
    "CDS.GC",
    "GC",
    "dG",
]
FILTER_FIELDS = [
    "Insuff.Prot",
    "Insuff.DNA",
    "Insuff.RNA",
    "Fltr.BelowRange",
    "Fltr.AboveRange",
    "Fltr.SetGood",
]
NUMERIC_FIELDS = [
    "Count.DNA",
    "Count.RNA",
    "Count.A.DNA",
    "Count.B.DNA",
    "Count.A.RNA",
    "Count.B.RNA",
    *BIN_COLUMNS,
    "Count.Prot",
    "RBS.len",
    "RNA.A",
    "RNA.B",
    "RNA",
    *BIN_PCT_COLUMNS,
    "Trans",
    "CAI",
    "tAI",
    "CDS.GC",
    "GC",
    "dG",
]
DISTRIBUTION_FIELDS = ["CDS.GC", "GC", "CAI", "tAI"]
STOP_CODONS = {"TAA", "TAG", "TGA"}
CODON_TABLE = dict(zip(
    (first + second + third for first in "TCAG" for second in "TCAG" for third in "TCAG"),
    "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG",
))
TRUE_VALUES = {"1", "TRUE", "T", "YES", "Y"}
FALSE_VALUES = {"0", "FALSE", "F", "NO", "N"}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--raw-csv", required=True, help="Downloaded 1241934tables1.csv")
    parser.add_argument("--protocol", required=True, help="Frozen Goodman E0 protocol JSON")
    parser.add_argument("--clean-csv", required=True, help="New lossless clean CSV output")
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
    raw_csv = input_file(args.raw_csv, "raw CSV")
    protocol_path = input_file(args.protocol, "protocol")
    clean_csv = Path(args.clean_csv).expanduser().resolve()
    report_json = Path(args.report_json).expanduser().resolve()
    if clean_csv == report_json:
        raise ValueError("clean CSV and report JSON must be different paths")
    for path in (clean_csv, report_json):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
    return raw_csv, protocol_path, clean_csv, report_json


def load_protocol(path):
    with path.open(encoding="utf-8") as handle:
        protocol = json.load(handle)
    if protocol.get("protocol") != PROTOCOL:
        raise ValueError(f"protocol identity mismatch: expected {PROTOCOL}")
    raw = protocol.get("inputs", {}).get("raw_csv", {})
    if raw.get("url") != OFFICIAL_URL:
        raise ValueError("protocol raw CSV URL does not match the frozen official URL")
    if not re.fullmatch(r"[0-9a-f]{64}", raw.get("sha256", "")):
        raise ValueError("protocol inputs.raw_csv.sha256 must be a lowercase SHA256")
    if raw.get("expected_column_count") != EXPECTED_COLUMN_COUNT:
        raise ValueError("protocol must freeze exactly 75 raw CSV columns")
    expected_rows = raw.get("expected_data_rows")
    if isinstance(expected_rows, bool) or not isinstance(expected_rows, int) or expected_rows < 1:
        raise ValueError("protocol expected_data_rows must be a positive integer")
    if protocol.get("required_columns") != REQUIRED_COLUMNS:
        raise ValueError("protocol required_columns do not match the frozen Goodman schema")
    qc = protocol.get("qc", {})
    if qc.get("filter_fields") != FILTER_FIELDS:
        raise ValueError("protocol filter_fields do not match the frozen Goodman schema")
    if qc.get("numeric_fields") != NUMERIC_FIELDS:
        raise ValueError("protocol numeric_fields do not match the frozen Goodman schema")
    if qc.get("distribution_fields") != DISTRIBUTION_FIELDS:
        raise ValueError("protocol distribution_fields do not match the frozen Goodman schema")
    cleaning = protocol.get("cleaning", {})
    if any((
        cleaning.get("preserve_all_original_columns") is not True,
        cleaning.get("preserve_all_rows") is not True,
        cleaning.get("delete_rows") is not False,
        cleaning.get("deduplicate") is not False,
    )):
        raise ValueError("protocol must forbid row deletion and deduplication")
    eligibility = protocol.get("study", {}).get("eligibility", {})
    construction = protocol.get("construction", {})
    if any((
        eligibility.get("task") != "T1_leader_context_n_terminal_construct_function",
        eligibility.get("leader_context_n_terminal_window_supported") is not True,
        "fixed_leader_n_terminal_window_supported" in eligibility,
        construction.get("official_observed_leader_context_groups") != 280,
        construction.get("leader_contexts_vary") is not True,
        construction.get("uniform_fixed_leader") is not False,
    )):
        raise ValueError("protocol must preserve the 280-context leader-limited claim boundary")
    if protocol.get("outputs", {}).get("overwrite") != "forbidden":
        raise ValueError("protocol outputs.overwrite must be forbidden")
    if protocol.get("license", {}).get("status") != "unconfirmed":
        raise ValueError("protocol license status must remain unconfirmed")
    return protocol


def verify_sha256(path, expected):
    observed = sha256_file(path)
    if observed != expected:
        raise ValueError(
            f"raw CSV SHA256 mismatch: expected {expected}, observed {observed}",
        )
    return observed


def read_raw_csv(path, protocol):
    expected_columns = protocol["inputs"]["raw_csv"]["expected_column_count"]
    expected_rows = protocol["inputs"]["raw_csv"]["expected_data_rows"]
    rows = []
    try:
        with path.open("r", encoding="utf-8-sig", errors="strict", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise ValueError("raw CSV is empty") from exc
            if len(header) != expected_columns:
                raise ValueError(
                    f"raw CSV header has {len(header)} columns; expected {expected_columns}",
                )
            empty_columns = [index + 1 for index, name in enumerate(header) if not name]
            if empty_columns:
                raise ValueError(f"raw CSV has empty header fields at positions {empty_columns}")
            duplicates = sorted(name for name, count in Counter(header).items() if count > 1)
            if duplicates:
                raise ValueError(f"raw CSV has duplicate header fields: {duplicates}")
            missing = [name for name in REQUIRED_COLUMNS if name not in header]
            if missing:
                raise ValueError(f"raw CSV missing required columns: {missing}")
            for row in reader:
                if len(row) != expected_columns:
                    raise ValueError(
                        f"raw CSV line {reader.line_num}: expected {expected_columns} fields, "
                        f"observed {len(row)}",
                    )
                rows.append(row)
    except csv.Error as exc:
        raise ValueError(f"raw CSV strict parse error near line {reader.line_num}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"raw CSV is not valid UTF-8: {exc}") from exc
    if len(rows) != expected_rows:
        raise ValueError(
            f"raw CSV data row count mismatch: expected {expected_rows}, observed {len(rows)}",
        )
    return header, rows


def sorted_counts(values):
    return dict(sorted(Counter(values).items()))


def quantile(sorted_values, probability):
    position = (len(sorted_values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def numeric_summary(tokens):
    values = []
    missing = 0
    non_numeric = 0
    nonfinite = 0
    for token in tokens:
        if not token.strip():
            missing += 1
            continue
        try:
            value = float(token)
        except ValueError:
            non_numeric += 1
            continue
        if not math.isfinite(value):
            nonfinite += 1
            continue
        values.append(value)
    values.sort()
    summary = {
        "rows": len(tokens),
        "missing_rows": missing,
        "non_numeric_rows": non_numeric,
        "nonfinite_rows": nonfinite,
        "finite_rows": len(values),
        "zero_rows": sum(value == 0 for value in values),
        "negative_rows": sum(value < 0 for value in values),
        "positive_rows": sum(value > 0 for value in values),
        "min": None,
        "max": None,
        "mean": None,
        "median": None,
        "quantiles": {
            "p01": None,
            "p05": None,
            "p25": None,
            "p75": None,
            "p95": None,
            "p99": None,
        },
    }
    if values:
        summary.update({
            "min": values[0],
            "max": values[-1],
            "mean": math.fsum(value / len(values) for value in values),
            "median": quantile(values, 0.5),
            "quantiles": {
                label: quantile(values, probability)
                for label, probability in (
                    ("p01", 0.01),
                    ("p05", 0.05),
                    ("p25", 0.25),
                    ("p75", 0.75),
                    ("p95", 0.95),
                    ("p99", 0.99),
                )
            },
        })
    return summary


def duplicate_summary(keys):
    counts = Counter(keys)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    examples = []
    for key, count in ordered:
        if count <= 1 or len(examples) == 20:
            continue
        displayed_key = {"Name": key[0], "CDS.seq": key[1]} if isinstance(key, tuple) else key
        examples.append({"key": displayed_key, "count": count})
    return {
        "unique_groups": len(counts),
        "duplicate_rows_beyond_first": sum(count - 1 for count in counts.values()),
        "duplicated_groups": sum(count > 1 for count in counts.values()),
        "largest_group_size": max(counts.values()),
        "examples": examples,
    }


def group_summary(values):
    counts = Counter(values)
    sizes = Counter(counts.values())
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return {
        "rows": len(values),
        "unique_groups": len(counts),
        "singleton_groups": sum(count == 1 for count in counts.values()),
        "multi_row_groups": sum(count > 1 for count in counts.values()),
        "rows_in_multi_row_groups": sum(count for count in counts.values() if count > 1),
        "largest_group_size": max(counts.values()),
        "group_size_distribution": {
            str(size): sizes[size] for size in sorted(sizes)
        },
        "largest_groups": [
            {"value": value, "count": count} for value, count in ordered[:10]
        ],
    }


def translate(cds):
    return "".join(CODON_TABLE[cds[index:index + 3]] for index in range(0, len(cds), 3))


def sequence_qc(rows, column_index):
    lengths = Counter()
    issue_counts = Counter()
    invalid_rows = set()
    issues = []
    translations = []
    stop_free = 0

    def record(row_index, name, kind):
        issue_counts[kind] += 1
        invalid_rows.add(row_index)
        if len(issues) < 20:
            issues.append({"row": row_index + 2, "Name": name, "issue": kind})

    for row_index, row in enumerate(rows):
        name = row[column_index["Name"]]
        cds = row[column_index["CDS.seq"]]
        lengths[len(cds)] += 1
        if not cds:
            record(row_index, name, "empty CDS")
        if re.fullmatch(r"[ACGT]+", cds) is None:
            record(row_index, name, "invalid alphabet")
        if len(cds) % 3:
            record(row_index, name, "length not divisible by 3")
        if not cds.startswith("ATG"):
            record(row_index, name, "non-ATG start")
        if row_index in invalid_rows:
            translations.append(None)
            continue
        codons = [cds[index:index + 3] for index in range(0, len(cds), 3)]
        internal_stop = any(codon in STOP_CODONS for codon in codons[:-1])
        terminal_stop = codons[-1] in STOP_CODONS
        if internal_stop:
            record(row_index, name, "internal stop")
        if terminal_stop:
            record(row_index, name, "terminal stop")
        translations.append(translate(cds))
        if not internal_stop and not terminal_stop:
            stop_free += 1

    if issue_counts:
        detail = "; ".join(
            f"{kind} rows={issue_counts[kind]}" for kind in sorted(issue_counts)
        )
        raise ValueError(
            "CDS sequence QC failed: " + detail + "; examples="
            + json.dumps(issues, ensure_ascii=False),
        )
    length_values = list(lengths.elements())
    return {
        "rows": len(rows),
        "valid_rows": len(rows) - len(invalid_rows),
        "length_nt_distribution": {
            str(length): lengths[length] for length in sorted(lengths)
        },
        "length_nt_summary": {
            "min": min(length_values),
            "max": max(length_values),
            "mean": math.fsum(length_values) / len(length_values),
        },
        "empty_cds_rows": issue_counts["empty CDS"],
        "invalid_alphabet_rows": issue_counts["invalid alphabet"],
        "length_not_divisible_by_3_rows": issue_counts["length not divisible by 3"],
        "non_atg_start_rows": issue_counts["non-ATG start"],
        "internal_stop_rows": issue_counts["internal stop"],
        "terminal_stop_rows": issue_counts["terminal stop"],
        "stop_free_rows": stop_free,
    }, translations


def translation_qc(rows, column_index, translations):
    groups = {}
    for row, protein in zip(rows, translations):
        gene = row[column_index["Gene"]]
        name = row[column_index["Name"]]
        groups.setdefault(gene, {}).setdefault(protein, []).append(name)
    conflicts = [
        {
            "Gene": gene,
            "translations": {
                protein: names[:10] for protein, names in sorted(proteins.items())
            },
        }
        for gene, proteins in sorted(groups.items()) if len(proteins) > 1
    ]
    if conflicts:
        raise ValueError(
            "protein translation inconsistency within Gene groups: "
            + json.dumps(conflicts[:10], ensure_ascii=False),
        )
    per_gene = [
        {
            "Gene": gene,
            "sample_count": sum(len(names) for names in proteins.values()),
            "unique_translation_count": len(proteins),
            "translations": sorted(proteins),
            "consistent": len(proteins) == 1,
        }
        for gene, proteins in sorted(groups.items())
    ]
    return {
        "group": "Gene",
        "gene_count": len(groups),
        "consistent_gene_count": sum(item["consistent"] for item in per_gene),
        "inconsistent_gene_count": sum(not item["consistent"] for item in per_gene),
        "per_gene": per_gene,
    }


def diversity_summary(values):
    counts = Counter(values)
    return {
        "unique_values": len(counts),
        "missing_rows": counts[""],
        "largest_value_count": max(counts.values()),
        "value_counts": dict(sorted(counts.items())),
    }


def filter_summary(values):
    counts = Counter(values)
    true_rows = 0
    false_rows = 0
    other_rows = 0
    for value, count in counts.items():
        normalized = value.strip().upper()
        if normalized in TRUE_VALUES:
            true_rows += count
        elif normalized in FALSE_VALUES:
            false_rows += count
        elif normalized:
            other_rows += count
    return {
        "true_rows": true_rows,
        "false_rows": false_rows,
        "missing_rows": counts[""],
        "other_rows": other_rows,
        "value_counts": dict(sorted(counts.items())),
    }


def serialize_clean(header, rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def write_exclusive(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)


def run_audit(args):
    raw_csv, protocol_path, clean_csv, report_json = validate_args(args)
    protocol = load_protocol(protocol_path)
    raw_sha = verify_sha256(raw_csv, protocol["inputs"]["raw_csv"]["sha256"])
    header, rows = read_raw_csv(raw_csv, protocol)
    column_index = {name: index for index, name in enumerate(header)}

    sequences, translations = sequence_qc(rows, column_index)
    translations_by_gene = translation_qc(rows, column_index, translations)
    names = [row[column_index["Name"]] for row in rows]
    genes = [row[column_index["Gene"]] for row in rows]
    cds_values = [row[column_index["CDS.seq"]] for row in rows]
    name_cds_values = list(zip(names, cds_values))
    promoters = [row[column_index["Promoter.seq"]] for row in rows]
    rbs_values = [row[column_index["RBS.seq"]] for row in rows]
    leaders = [promoter + rbs for promoter, rbs in zip(promoters, rbs_values)]

    cds_to_genes = {}
    name_to_cds = {}
    for name, gene, cds in zip(names, genes, cds_values):
        cds_to_genes.setdefault(cds, set()).add(gene)
        name_to_cds.setdefault(name, set()).add(cds)
    duplicates = {
        "Name": duplicate_summary(names),
        "exact_CDS": duplicate_summary(cds_values),
        "Name_CDS": duplicate_summary(name_cds_values),
        "exact_CDS_groups_spanning_multiple_Genes": sum(
            len(group_genes) > 1 for group_genes in cds_to_genes.values()
        ),
        "Names_with_multiple_CDS_sequences": sum(
            len(group_cds) > 1 for group_cds in name_to_cds.values()
        ),
        "deduplication_applied": False,
    }

    construction = {
        "scope": protocol["construction"]["supported_scope"],
        "official_observed_leader_context_groups": protocol["construction"][
            "official_observed_leader_context_groups"
        ],
        "observed_leader_context_groups": len(set(leaders)),
        "official_leader_contexts_vary": protocol["construction"]["leader_contexts_vary"],
        "official_uniform_fixed_leader": protocol["construction"]["uniform_fixed_leader"],
        "observed_leader_contexts_vary": len(set(leaders)) > 1,
        "sequence_diversity": {
            "Promoter": diversity_summary([
                row[column_index["Promoter"]] for row in rows
            ]),
            "Promoter.seq": diversity_summary(promoters),
            "RBS.seq": diversity_summary(rbs_values),
            "leader": diversity_summary(leaders),
        },
        "leader_definition": protocol["construction"]["leader_sequence_definition"],
        "CDS.type": {
            "unique_values": len(set(row[column_index["CDS.type"]] for row in rows)),
            "value_counts": sorted_counts([
                row[column_index["CDS.type"]] for row in rows
            ]),
        },
    }
    filters = {
        field: filter_summary([row[column_index[field]] for row in rows])
        for field in FILTER_FIELDS
    }
    filter_qc = {
        "fields": filters,
        "filtering_applied": False,
        "rows_removed_from_clean": 0,
        "Fltr.SetGood_used_for_row_selection": False,
    }
    numeric = {
        field: numeric_summary([row[column_index[field]] for row in rows])
        for field in NUMERIC_FIELDS
    }
    gene_counts = Counter(genes)
    gene_sizes = sorted(gene_counts.values())
    gene_qc = {
        "gene_count": len(gene_counts),
        "sample_counts": dict(sorted(gene_counts.items())),
        "sample_count_summary": {
            "min": gene_sizes[0],
            "max": gene_sizes[-1],
            "mean": math.fsum(gene_sizes) / len(gene_sizes),
            "median": quantile(gene_sizes, 0.5),
            "singleton_genes": sum(size == 1 for size in gene_sizes),
        },
    }
    split_groups = {
        "Gene": group_summary(genes),
        "exact_CDS": group_summary(cds_values),
        "Name_CDS": group_summary([
            json.dumps([name, cds], ensure_ascii=False) for name, cds in name_cds_values
        ]),
        "translation": group_summary(translations),
        "leader": group_summary(leaders),
    }
    split_qc = {
        "split_performed": False,
        "primary_group": "Gene",
        "additional_duplicate_blocking_groups": ["exact_CDS", "Name_CDS"],
        "groups": split_groups,
        "multi_gene_pool_is_protein_ood": False,
        "protein_ood_supported": False,
        "note": "Group by Gene and block exact duplicates across splits; Gene diversity in this fragment pool is not protein OOD evidence.",
    }

    clean_payload = serialize_clean(header, rows)
    clean_sha = hashlib.sha256(clean_payload).hexdigest()
    report = {
        "schema": REPORT_SCHEMA,
        "protocol": PROTOCOL,
        "status": "candidate_procedure_and_qc_passed",
        "scope": SCOPE,
        "task_eligibility": {
            **protocol["study"]["eligibility"],
            "fixed_single_leader_claim": False,
        },
        "source": {
            "citation_key": protocol["study"]["citation_key"],
            "doi": protocol["study"]["doi"],
            "url": protocol["inputs"]["raw_csv"]["url"],
            "license": protocol["license"],
        },
        "inputs": {
            "raw_csv": str(raw_csv),
            "protocol": str(protocol_path),
        },
        "sha256": {
            "raw_csv": raw_sha,
            "protocol": sha256_file(protocol_path),
            "clean_csv": clean_sha,
        },
        "raw_csv": {
            "columns": header,
            "column_count": len(header),
            "data_rows": len(rows),
        },
        "clean_csv": {
            "path": str(clean_csv),
            "columns": header,
            "column_count": len(header),
            "data_rows": len(rows),
            "all_original_columns_preserved": True,
            "all_original_rows_preserved": True,
            "all_field_values_preserved": True,
            "filtering_applied": False,
            "deduplication_applied": False,
            "serialization": "UTF-8 CSV, original column order and field values, LF line endings",
        },
        "sequence_qc": sequences,
        "translation_qc": translations_by_gene,
        "duplicate_qc": duplicates,
        "construction_qc": construction,
        "filter_qc": filter_qc,
        "numeric_qc": numeric,
        "distribution_qc": {
            field: numeric[field] for field in DISTRIBUTION_FIELDS
        },
        "gene_qc": gene_qc,
        "split_leakage_qc": split_qc,
        "limitations": protocol["limitations"],
    }
    report_payload = (
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")
    write_exclusive(clean_csv, clean_payload)
    write_exclusive(report_json, report_payload)
    print(json.dumps({
        "status": report["status"],
        "clean_csv": str(clean_csv),
        "report_json": str(report_json),
        "rows": len(rows),
        "columns": len(header),
        "genes": len(gene_counts),
    }))
    return report


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    run_audit(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
