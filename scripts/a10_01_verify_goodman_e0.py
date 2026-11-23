"""Independently verify the Goodman2013 E0 raw/clean tables and audit report."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path


PROTOCOL = "a10_01_goodman_e0_independent_verification_v2"
EXPECTED_REPORT_SCHEMA = "a10-01-goodman-e0-audit-report-v2"
EXPECTED_REPORT_PROTOCOL = "a10_01_goodman_e0_protocol_v2"
EXPECTED_RAW_URL = (
    "https://www.science.org/doi/suppl/10.1126/science.1241934/"
    "suppl_file/1241934tables1.csv"
)
EXPECTED_RAW_SHA256 = "a03071027b8c0008d07fb7737de0a7d51765c6cff25bc86e93465a6253c7c33a"
EXPECTED_RAW_DATA_ROWS = 14234
EXPECTED_COLUMN_COUNT = 75
OFFICIAL_LEADER_CONTEXT_GROUPS = 280
EXPECTED_UNIQUE_LEADER_GROUPS = OFFICIAL_LEADER_CONTEXT_GROUPS
EXPECTED_EXAMPLE_CDS_NT_LENGTH = 33
EXPECTED_SCOPE = "procedure_and_qc_only_no_functional_or_model_conclusion"
EXPECTED_TASK = "T1_leader_context_n_terminal_construct_function"
SUPPORTED_CONSTRUCT_SCOPE = "leader-context-limited N-terminal CDS window construct function only"
LEADER_DEFINITION = (
    "Promoter.seq concatenated directly with RBS.seq as an operational construct key; "
    "this is not a native UTR annotation"
)
SPLIT_NOTE = (
    "Group by Gene and block exact duplicates across splits; Gene diversity in this "
    "fragment pool is not protein OOD evidence."
)
BIN_COLUMNS = tuple(f"Bin.{index}" for index in range(1, 13))
BIN_PCT_COLUMNS = tuple(f"Bin.Pct.{index}" for index in range(1, 13))
REQUIRED_COLUMNS = (
    "Name", "CDS.seq", "Count.DNA", "Count.RNA", "Count.A.DNA", "Count.B.DNA",
    "Count.A.RNA", "Count.B.RNA", *BIN_COLUMNS, "Count.Prot", "Promoter", "Gene",
    "Promoter.seq", "RBS.seq", "CDS.type", "RBS.len", "RNA.A", "RNA.B", "RNA",
    *BIN_PCT_COLUMNS, "Trans", "Insuff.Prot", "Insuff.DNA", "Insuff.RNA",
    "Fltr.BelowRange", "Fltr.AboveRange", "Fltr.SetGood", "CAI", "tAI", "CDS.GC", "GC", "dG",
)
NUMERIC_COLUMNS = (
    "Count.DNA", "Count.RNA", "Count.A.DNA", "Count.B.DNA", "Count.A.RNA", "Count.B.RNA",
    *BIN_COLUMNS, "Count.Prot", "RBS.len", "RNA.A", "RNA.B", "RNA", *BIN_PCT_COLUMNS,
    "Trans", "CAI", "tAI", "CDS.GC", "GC", "dG",
)
DISTRIBUTION_COLUMNS = ("CDS.GC", "GC", "CAI", "tAI")
FLAG_COLUMNS = (
    "Insuff.Prot", "Insuff.DNA", "Insuff.RNA",
    "Fltr.BelowRange", "Fltr.AboveRange", "Fltr.SetGood",
)
TRUE_VALUES = {"1", "TRUE", "T", "YES", "Y"}
FALSE_VALUES = {"0", "FALSE", "F", "NO", "N"}
STOP_CODONS = {"TAA", "TAG", "TGA"}
CODON_TABLE = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_number(value):
    if value == value.to_integral_value():
        return int(value)
    return format(value, "f").rstrip("0").rstrip(".")


def json_safe(value):
    if isinstance(value, Decimal):
        return json_number(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def read_csv_table(path, label):
    with Path(path).open("r", encoding="utf-8-sig", errors="strict", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        try:
            columns = next(reader)
        except StopIteration as exc:
            raise ValueError(f"{label} CSV is empty") from exc
        if len(columns) != EXPECTED_COLUMN_COUNT:
            raise ValueError(
                f"{label} CSV must have exactly {EXPECTED_COLUMN_COUNT} columns, found {len(columns)}",
            )
        if any(not column for column in columns) or len(set(columns)) != len(columns):
            raise ValueError(f"{label} CSV has empty or duplicate column names")
        missing = sorted(set(REQUIRED_COLUMNS) - set(columns))
        if missing:
            raise ValueError(f"{label} CSV is missing required columns: {missing}")
        rows = []
        for values in reader:
            if len(values) != len(columns):
                raise ValueError(
                    f"{label} CSV line {reader.line_num} has {len(values)} fields; "
                    f"expected {len(columns)}",
                )
            rows.append(dict(zip(columns, values)))
    return columns, rows


def translate_cds(sequence):
    return "".join(
        CODON_TABLE[sequence[index:index + 3]] for index in range(0, len(sequence), 3)
    )


def quantile(ordered, probability):
    position = Decimal(len(ordered) - 1) * Decimal(str(probability))
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def numeric_summary(tokens):
    values = []
    counts = Counter()
    for token in tokens:
        if not token.strip():
            counts["missing_rows"] += 1
            continue
        try:
            value = Decimal(token)
        except (InvalidOperation, ValueError):
            counts["non_numeric_rows"] += 1
            continue
        try:
            finite = value.is_finite() and math.isfinite(float(value))
        except (OverflowError, ValueError):
            finite = False
        if not finite:
            counts["nonfinite_rows"] += 1
            continue
        values.append(value)
    values.sort()
    result = {
        "rows": len(tokens),
        "missing_rows": counts["missing_rows"],
        "non_numeric_rows": counts["non_numeric_rows"],
        "nonfinite_rows": counts["nonfinite_rows"],
        "finite_rows": len(values),
        "zero_rows": sum(value == 0 for value in values),
        "negative_rows": sum(value < 0 for value in values),
        "positive_rows": sum(value > 0 for value in values),
        "min": None,
        "max": None,
        "mean": None,
        "median": None,
        "quantiles": {key: None for key in ("p01", "p05", "p25", "p75", "p95", "p99")},
    }
    if values:
        result.update({
            "min": values[0],
            "max": values[-1],
            "mean": sum(values, Decimal(0)) / Decimal(len(values)),
            "median": quantile(values, 0.5),
            "quantiles": {
                label: quantile(values, probability)
                for label, probability in (
                    ("p01", 0.01), ("p05", 0.05), ("p25", 0.25),
                    ("p75", 0.75), ("p95", 0.95), ("p99", 0.99),
                )
            },
        })
    return result


def duplicate_summary(keys):
    counts = Counter(keys)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    examples = []
    for key, count in ordered:
        if count <= 1 or len(examples) == 20:
            continue
        displayed = {"Name": key[0], "CDS.seq": key[1]} if isinstance(key, tuple) else key
        examples.append({"key": displayed, "count": count})
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
    ordered = sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))
    return {
        "rows": len(values),
        "unique_groups": len(counts),
        "singleton_groups": sum(count == 1 for count in counts.values()),
        "multi_row_groups": sum(count > 1 for count in counts.values()),
        "rows_in_multi_row_groups": sum(count for count in counts.values() if count > 1),
        "largest_group_size": max(counts.values()),
        "group_size_distribution": {str(size): sizes[size] for size in sorted(sizes)},
        "largest_groups": [{"value": value, "count": count} for value, count in ordered[:10]],
    }


def sequence_summary(rows):
    lengths = Counter()
    issues = Counter()
    invalid_rows = set()
    translations = []
    stop_free = 0
    for index, row in enumerate(rows):
        sequence = row["CDS.seq"]
        lengths[len(sequence)] += 1
        if not sequence:
            issues["empty_cds_rows"] += 1
            invalid_rows.add(index)
        if re.fullmatch(r"[ACGT]+", sequence) is None:
            issues["invalid_alphabet_rows"] += 1
            invalid_rows.add(index)
        if len(sequence) % 3:
            issues["length_not_divisible_by_3_rows"] += 1
            invalid_rows.add(index)
        if not sequence.startswith("ATG"):
            issues["non_atg_start_rows"] += 1
            invalid_rows.add(index)
        if index in invalid_rows:
            translations.append(None)
            continue
        codons = [sequence[pos:pos + 3] for pos in range(0, len(sequence), 3)]
        internal_stop = any(codon in STOP_CODONS for codon in codons[:-1])
        terminal_stop = codons[-1] in STOP_CODONS
        if internal_stop:
            issues["internal_stop_rows"] += 1
            invalid_rows.add(index)
        if terminal_stop:
            issues["terminal_stop_rows"] += 1
            invalid_rows.add(index)
        translations.append(translate_cds(sequence))
        if not internal_stop and not terminal_stop:
            stop_free += 1
    length_values = list(lengths.elements())
    return {
        "rows": len(rows),
        "valid_rows": len(rows) - len(invalid_rows),
        "length_nt_distribution": {str(size): lengths[size] for size in sorted(lengths)},
        "length_nt_summary": {
            "min": min(length_values),
            "max": max(length_values),
            "mean": Decimal(sum(length_values)) / Decimal(len(length_values)),
        },
        "empty_cds_rows": issues["empty_cds_rows"],
        "invalid_alphabet_rows": issues["invalid_alphabet_rows"],
        "length_not_divisible_by_3_rows": issues["length_not_divisible_by_3_rows"],
        "non_atg_start_rows": issues["non_atg_start_rows"],
        "internal_stop_rows": issues["internal_stop_rows"],
        "terminal_stop_rows": issues["terminal_stop_rows"],
        "stop_free_rows": stop_free,
    }, translations


def protein_sort_key(value):
    return (value is not None, value or "")


def translation_summary(rows, translations):
    groups = {}
    for row, protein in zip(rows, translations):
        groups.setdefault(row["Gene"], {}).setdefault(protein, []).append(row["Name"])
    per_gene = [
        {
            "Gene": gene,
            "sample_count": sum(len(names) for names in proteins.values()),
            "unique_translation_count": len(proteins),
            "translations": sorted(proteins, key=protein_sort_key),
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


def summarize_raw(raw_columns, rows):
    if not rows:
        raise ValueError("raw CSV has no data rows")
    names = [row["Name"] for row in rows]
    genes = [row["Gene"] for row in rows]
    cds_values = [row["CDS.seq"] for row in rows]
    name_cds = list(zip(names, cds_values))
    promoters = [row["Promoter.seq"] for row in rows]
    rbs_values = [row["RBS.seq"] for row in rows]
    leaders = [promoter + rbs for promoter, rbs in zip(promoters, rbs_values)]
    sequences, translations = sequence_summary(rows)
    cds_to_genes = {}
    name_to_cds = {}
    for name, gene, cds in zip(names, genes, cds_values):
        cds_to_genes.setdefault(cds, set()).add(gene)
        name_to_cds.setdefault(name, set()).add(cds)
    duplicates = {
        "Name": duplicate_summary(names),
        "exact_CDS": duplicate_summary(cds_values),
        "Name_CDS": duplicate_summary(name_cds),
        "exact_CDS_groups_spanning_multiple_Genes": sum(
            len(group) > 1 for group in cds_to_genes.values()
        ),
        "Names_with_multiple_CDS_sequences": sum(len(group) > 1 for group in name_to_cds.values()),
        "deduplication_applied": False,
    }
    leader_group_count = len(set(leaders))
    construction = {
        "scope": SUPPORTED_CONSTRUCT_SCOPE,
        "official_observed_leader_context_groups": OFFICIAL_LEADER_CONTEXT_GROUPS,
        "observed_leader_context_groups": leader_group_count,
        "official_leader_contexts_vary": True,
        "official_uniform_fixed_leader": False,
        "observed_leader_contexts_vary": leader_group_count > 1,
        "sequence_diversity": {
            "Promoter": diversity_summary([row["Promoter"] for row in rows]),
            "Promoter.seq": diversity_summary(promoters),
            "RBS.seq": diversity_summary(rbs_values),
            "leader": diversity_summary(leaders),
        },
        "leader_definition": LEADER_DEFINITION,
        "CDS.type": {
            "unique_values": len(set(row["CDS.type"] for row in rows)),
            "value_counts": dict(sorted(Counter(row["CDS.type"] for row in rows).items())),
        },
    }
    numeric = {
        column: numeric_summary([row[column] for row in rows]) for column in NUMERIC_COLUMNS
    }
    gene_counts = Counter(genes)
    gene_sizes = sorted(gene_counts.values())
    split_groups = {
        "Gene": group_summary(genes),
        "exact_CDS": group_summary(cds_values),
        "Name_CDS": group_summary([
            json.dumps([name, cds], ensure_ascii=False) for name, cds in name_cds
        ]),
        "translation": group_summary(translations),
        "leader": group_summary(leaders),
    }
    return {
        "raw_csv": {"columns": raw_columns, "column_count": len(raw_columns), "data_rows": len(rows)},
        "sequence_qc": sequences,
        "translation_qc": translation_summary(rows, translations),
        "duplicate_qc": duplicates,
        "construction_qc": construction,
        "filter_qc": {
            "fields": {column: filter_summary([row[column] for row in rows]) for column in FLAG_COLUMNS},
            "filtering_applied": False,
            "rows_removed_from_clean": 0,
            "Fltr.SetGood_used_for_row_selection": False,
        },
        "numeric_qc": numeric,
        "distribution_qc": {column: numeric[column] for column in DISTRIBUTION_COLUMNS},
        "gene_qc": {
            "gene_count": len(gene_counts),
            "sample_counts": dict(sorted(gene_counts.items())),
            "sample_count_summary": {
                "min": gene_sizes[0],
                "max": gene_sizes[-1],
                "mean": Decimal(sum(gene_sizes)) / Decimal(len(gene_sizes)),
                "median": quantile(gene_sizes, 0.5),
                "singleton_genes": sum(size == 1 for size in gene_sizes),
            },
        },
        "split_leakage_qc": {
            "split_performed": False,
            "primary_group": "Gene",
            "additional_duplicate_blocking_groups": ["exact_CDS", "Name_CDS"],
            "groups": split_groups,
            "multi_gene_pool_is_protein_ood": False,
            "protein_ood_supported": False,
            "note": SPLIT_NOTE,
        },
    }


def compare_clean(raw_columns, raw_rows, clean_columns, clean_rows):
    differences = []
    mismatch_cells = 0
    mismatch_rows = 0
    for index in range(max(len(raw_rows), len(clean_rows))):
        if index >= len(raw_rows):
            differences.append({"kind": "unexpected_clean_row", "row": index + 1})
            mismatch_rows += 1
            continue
        if index >= len(clean_rows):
            differences.append({"kind": "missing_clean_row", "row": index + 1})
            mismatch_rows += 1
            continue
        row_mismatch = False
        for column in raw_columns:
            expected = raw_rows[index][column]
            observed = clean_rows[index].get(column)
            if observed != expected:
                mismatch_cells += 1
                row_mismatch = True
                if len(differences) < 100:
                    differences.append({
                        "kind": "field_mismatch", "row": index + 1,
                        "Name": raw_rows[index]["Name"], "field": column,
                        "expected": expected, "observed": observed,
                    })
        mismatch_rows += row_mismatch
    checks = {
        "clean_columns": clean_columns == raw_columns,
        "clean_row_count": len(clean_rows) == len(raw_rows) == EXPECTED_RAW_DATA_ROWS,
        "clean_all_75_fields": not mismatch_cells and not mismatch_rows,
    }
    checks["clean_exact"] = all(checks.values())
    return checks, {
        "mismatch_rows": mismatch_rows,
        "mismatch_cells": mismatch_cells,
        "differences": differences,
    }


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
    return math.isfinite(observed) and math.isclose(observed, target, rel_tol=1e-12, abs_tol=1e-12)


def value_mismatches(observed, expected, path=""):
    if expected is None:
        return [] if observed is None else [path]
    if isinstance(expected, bool):
        return [] if observed is expected else [path]
    if isinstance(expected, int):
        return [] if exact_integer(observed, expected) else [path]
    if isinstance(expected, Decimal):
        return [] if close_number(observed, expected) else [path]
    if isinstance(expected, str):
        return [] if observed == expected else [path]
    if isinstance(expected, dict):
        if not isinstance(observed, dict) or set(observed) != set(expected):
            return [path]
        return [
            mismatch
            for key in expected
            for mismatch in value_mismatches(observed[key], expected[key], f"{path}.{key}")
        ]
    if isinstance(expected, list):
        if not isinstance(observed, list) or len(observed) != len(expected):
            return [path]
        return [
            mismatch
            for index, item in enumerate(expected)
            for mismatch in value_mismatches(observed[index], item, f"{path}[{index}]")
        ]
    return [path]


def walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk_dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_dicts(item)


def nested_values(report, keys):
    return [node[key] for node in walk_dicts(report) for key in keys if key in node]


def check_claim_boundaries(report):
    eligibility = report.get("task_eligibility")
    if not isinstance(eligibility, dict):
        eligibility = {}
    untouched = nested_values(report, ("final_untouched", "is_final_untouched", "untouched"))
    positive = nested_values(report, (
        "scientific_positive", "scientific_positive_claim", "scientific_positive_claimed",
        "scientific_positive_claim_eligible", "positive_scientific_claim", "has_scientific_positive_claim",
    ))
    full_length = nested_values(report, ("full_length_cds_supported", "full_length_cds_eligible"))
    native_utr = nested_values(report, ("native_utr_supported", "native_utr_eligible"))
    protein_ood = nested_values(report, (
        "protein_ood_supported", "protein_ood_eligible", "multi_gene_pool_is_protein_ood",
    ))
    leader_context = nested_values(report, ("leader_context_n_terminal_window_supported",))
    fixed_leader = nested_values(report, (
        "fixed_leader_n_terminal_window_supported",
        "fixed_leader_n_terminal_window_only",
        "fixed_single_leader_claim",
        "single_fixed_leader_claim",
    ))
    no_fixed_leader = nested_values(report, ("no_fixed_single_leader_claim",))
    fixed_leader_denied = bool(fixed_leader) and all(value is False for value in fixed_leader)
    no_fixed_leader_asserted = bool(no_fixed_leader) and all(
        value is True for value in no_fixed_leader
    )
    return {
        "report_scope": report.get("scope") == EXPECTED_SCOPE,
        "report_status_safe": report.get("status") == "candidate_procedure_and_qc_passed",
        "report_e0_only": (
            eligibility.get("task") == EXPECTED_TASK
            and eligibility.get("candidate_research_only") is True
            and eligibility.get("procedure_and_qc_only") is True
            and bool(leader_context)
            and all(value is True for value in leader_context)
        ),
        "no_fixed_single_leader_claim": (
            (no_fixed_leader_asserted or fixed_leader_denied)
            and (not no_fixed_leader or no_fixed_leader_asserted)
            and all(value is False for value in fixed_leader)
        ),
        "not_final_untouched": bool(untouched) and all(value is False for value in untouched),
        "no_scientific_positive": bool(positive) and all(value is False for value in positive),
        "no_full_length_cds_claim": bool(full_length) and all(value is False for value in full_length),
        "no_native_utr_claim": bool(native_utr) and all(value is False for value in native_utr),
        "no_protein_ood_claim": bool(protein_ood) and all(value is False for value in protein_ood),
    }


def compare_report(report, recomputed, raw_sha256, clean_sha256, expected_raw_sha256):
    details = {}
    checks = {}
    for section in (
        "raw_csv", "sequence_qc", "translation_qc", "duplicate_qc", "construction_qc",
        "filter_qc", "numeric_qc", "distribution_qc", "gene_qc", "split_leakage_qc",
    ):
        mismatches = value_mismatches(report.get(section), recomputed[section], section)
        checks[f"report_{section}"] = not mismatches
        details[section] = mismatches[:100]
    clean_info = report.get("clean_csv")
    if not isinstance(clean_info, dict):
        clean_info = {}
    source = report.get("source")
    if not isinstance(source, dict):
        source = {}
    sha256 = report.get("sha256")
    if not isinstance(sha256, dict):
        sha256 = {}
    checks.update({
        "report_identity": (
            report.get("schema") == EXPECTED_REPORT_SCHEMA
            and report.get("protocol") == EXPECTED_REPORT_PROTOCOL
        ),
        "report_source": not value_mismatches(source, {
            "citation_key": "Goodman2013",
            "doi": "10.1126/science.1241934",
            "url": EXPECTED_RAW_URL,
            "license": {
                "status": "unconfirmed",
                "confirmed": False,
                "redistribution_or_derivative_use_requires_review": True,
            },
        }, "source"),
        "report_raw_sha256": sha256.get("raw_csv") == raw_sha256 == expected_raw_sha256,
        "report_clean_sha256": sha256.get("clean_csv") == clean_sha256,
        "report_clean_schema": (
            clean_info.get("columns") == recomputed["raw_csv"]["columns"]
            and exact_integer(clean_info.get("column_count"), EXPECTED_COLUMN_COUNT)
            and exact_integer(clean_info.get("data_rows"), EXPECTED_RAW_DATA_ROWS)
        ),
        "report_clean_policy": (
            clean_info.get("all_original_columns_preserved") is True
            and clean_info.get("all_original_rows_preserved") is True
            and clean_info.get("all_field_values_preserved") is True
            and clean_info.get("filtering_applied") is False
            and clean_info.get("deduplication_applied") is False
            and clean_info.get("serialization")
            == "UTF-8 CSV, original column order and field values, LF line endings"
        ),
        **check_claim_boundaries(report),
    })
    return checks, details


def reject_nonfinite_json(value):
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def verify_goodman_e0(raw_csv, clean_csv, report_json, expected_raw_sha256=None):
    expected_raw_sha256 = expected_raw_sha256 or EXPECTED_RAW_SHA256
    raw_sha256 = file_sha256(raw_csv)
    clean_sha256 = file_sha256(clean_csv)
    raw_columns, raw_rows = read_csv_table(raw_csv, "raw")
    clean_columns, clean_rows = read_csv_table(clean_csv, "clean")
    report = json.loads(
        Path(report_json).read_text(encoding="utf-8"),
        parse_float=Decimal,
        parse_constant=reject_nonfinite_json,
    )
    if not isinstance(report, dict):
        raise ValueError("report JSON must be an object")
    recomputed = summarize_raw(raw_columns, raw_rows)
    clean_checks, clean_details = compare_clean(raw_columns, raw_rows, clean_columns, clean_rows)
    report_checks, report_details = compare_report(
        report, recomputed, raw_sha256, clean_sha256, expected_raw_sha256,
    )
    sequence_issues = (
        "empty_cds_rows", "invalid_alphabet_rows", "length_not_divisible_by_3_rows",
        "non_atg_start_rows", "internal_stop_rows", "terminal_stop_rows",
    )
    checks = {
        "raw_sha256": raw_sha256 == expected_raw_sha256,
        "raw_shape": (
            len(raw_rows) == EXPECTED_RAW_DATA_ROWS and len(raw_columns) == EXPECTED_COLUMN_COUNT
        ),
        "sequence_qc": all(recomputed["sequence_qc"][field] == 0 for field in sequence_issues),
        "gene_translation_consistency": recomputed["translation_qc"]["inconsistent_gene_count"] == 0,
        "leader_group_count": (
            recomputed["construction_qc"]["sequence_diversity"]["leader"]["unique_values"]
            == EXPECTED_UNIQUE_LEADER_GROUPS
        ),
        **clean_checks,
        **report_checks,
    }
    return {
        "protocol": PROTOCOL,
        "passed": all(checks.values()),
        "scope": EXPECTED_SCOPE,
        "supported_construct_scope": SUPPORTED_CONSTRUCT_SCOPE,
        "inputs": {
            "raw_csv": str(raw_csv),
            "raw_url": EXPECTED_RAW_URL,
            "raw_sha256": raw_sha256,
            "expected_raw_sha256": expected_raw_sha256,
            "expected_unique_leader_groups": EXPECTED_UNIQUE_LEADER_GROUPS,
            "clean_csv": str(clean_csv),
            "clean_sha256": clean_sha256,
            "clean_columns": clean_columns,
            "report_json": str(report_json),
        },
        "checks": checks,
        "recomputed": json_safe(recomputed),
        "clean_comparison": clean_details,
        "report_summary_comparison": report_details,
    }


def write_json_exclusive(output, payload):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(json_safe(payload), handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--raw-csv", required=True)
    parser.add_argument("--clean-csv", required=True)
    parser.add_argument("--report", "--report-json", dest="report_json", required=True)
    parser.add_argument("--output", "--out", dest="output", required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    try:
        result = verify_goodman_e0(args.raw_csv, args.clean_csv, args.report_json)
    except Exception as exc:
        result = {
            "protocol": PROTOCOL,
            "passed": False,
            "scope": EXPECTED_SCOPE,
            "inputs": {"raw_csv": args.raw_csv, "clean_csv": args.clean_csv, "report_json": args.report_json},
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    write_json_exclusive(output, result)
    print(json.dumps({"output": str(output), "passed": result["passed"], "checks": result.get("checks", {})}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
