import ast
import csv
import hashlib
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest

from scripts import a10_01_verify_goodman_e0 as verifier


EXTRA_COLUMNS = tuple(f"Extra.{index:02d}" for index in range(1, 22))
COLUMNS = [*verifier.REQUIRED_COLUMNS, *EXTRA_COLUMNS]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_rows():
    sequences = [
        "ATG" + "GCT" * 10,
        "ATG" + "GCC" * 10,
        "ATG" + "GCT" + "GCC" * 9,
        "ATG" + "TTT" * 11,
    ]
    genes = ["GeneA", "GeneA", "GeneA", "GeneB"]
    trans = ["0.5", "2.0", "4.0", "1.0"]
    protein = ["10", "20", "30", "NA"]
    rows = []
    for index, (sequence, gene) in enumerate(zip(sequences, genes)):
        row = {column: "0" for column in verifier.NUMERIC_COLUMNS}
        row.update({
            "Name": f"SYNTHETIC_{index:02d}",
            "CDS.seq": sequence,
            "Gene": gene,
            "Promoter": "SyntheticPromoter",
            "Promoter.seq": "TTGACATTTT",
            "RBS.seq": "AAGGAG",
            "CDS.type": "synthetic_N_terminal_window",
            "RBS.len": "6",
            "Trans": trans[index],
            "Count.Prot": protein[index],
            **{column: "FALSE" for column in verifier.FLAG_COLUMNS},
            **{column: f"fixture-{index}-{column}" for column in EXTRA_COLUMNS},
        })
        rows.append(row)
    rows[0]["Fltr.SetGood"] = "TRUE"
    rows[1]["Insuff.Prot"] = "TRUE"
    rows[1]["Fltr.BelowRange"] = "TRUE"
    rows[2]["Fltr.AboveRange"] = "TRUE"
    rows[3]["Insuff.DNA"] = "TRUE"
    rows[3]["Insuff.RNA"] = "TRUE"
    return rows


def write_csv(path, rows, columns=COLUMNS):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def json_number(value):
    return int(value) if value == value.to_integral_value() else float(value)


def quantile(values, probability):
    position = Decimal(len(values) - 1) * Decimal(str(probability))
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction


def numeric_summary(rows, column):
    counts = Counter()
    values = []
    for row in rows:
        token = row[column]
        if not token.strip():
            counts["missing_rows"] += 1
            continue
        try:
            value = Decimal(token)
        except InvalidOperation:
            counts["non_numeric_rows"] += 1
            continue
        if not value.is_finite():
            counts["nonfinite_rows"] += 1
            continue
        values.append(value)
    values.sort()
    result = {
        "rows": len(rows),
        "missing_rows": counts["missing_rows"],
        "non_numeric_rows": counts["non_numeric_rows"],
        "nonfinite_rows": counts["nonfinite_rows"],
        "finite_rows": len(values),
        "zero_rows": sum(value == 0 for value in values),
        "negative_rows": sum(value < 0 for value in values),
        "positive_rows": sum(value > 0 for value in values),
        "min": None, "max": None, "mean": None, "median": None,
        "quantiles": {key: None for key in ("p01", "p05", "p25", "p75", "p95", "p99")},
    }
    if values:
        result.update({
            "min": json_number(values[0]),
            "max": json_number(values[-1]),
            "mean": json_number(sum(values, Decimal(0)) / len(values)),
            "median": json_number(quantile(values, 0.5)),
            "quantiles": {
                label: json_number(quantile(values, probability))
                for label, probability in (
                    ("p01", 0.01), ("p05", 0.05), ("p25", 0.25),
                    ("p75", 0.75), ("p95", 0.95), ("p99", 0.99),
                )
            },
        })
    return result


def duplicate_summary(values):
    counts = Counter(values)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    examples = []
    for value, count in ordered:
        if count > 1 and len(examples) < 20:
            key = {"Name": value[0], "CDS.seq": value[1]} if isinstance(value, tuple) else value
            examples.append({"key": key, "count": count})
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


def filter_summary(rows, column):
    counts = Counter(row[column] for row in rows)
    true_rows = sum(count for value, count in counts.items() if value.strip().upper() in verifier.TRUE_VALUES)
    false_rows = sum(count for value, count in counts.items() if value.strip().upper() in verifier.FALSE_VALUES)
    other_rows = sum(
        count for value, count in counts.items()
        if value.strip() and value.strip().upper() not in verifier.TRUE_VALUES | verifier.FALSE_VALUES
    )
    return {
        "true_rows": true_rows,
        "false_rows": false_rows,
        "missing_rows": counts[""],
        "other_rows": other_rows,
        "value_counts": dict(sorted(counts.items())),
    }


def diversity(value_counts):
    return {
        "unique_values": len(value_counts),
        "missing_rows": value_counts.get("", 0),
        "largest_value_count": max(value_counts.values()),
        "value_counts": dict(sorted(value_counts.items())),
    }


def duplicate_qc(rows):
    names = [row["Name"] for row in rows]
    cds_values = [row["CDS.seq"] for row in rows]
    cds_to_genes = {}
    name_to_cds = {}
    for row in rows:
        cds_to_genes.setdefault(row["CDS.seq"], set()).add(row["Gene"])
        name_to_cds.setdefault(row["Name"], set()).add(row["CDS.seq"])
    return {
        "Name": duplicate_summary(names),
        "exact_CDS": duplicate_summary(cds_values),
        "Name_CDS": duplicate_summary(list(zip(names, cds_values))),
        "exact_CDS_groups_spanning_multiple_Genes": sum(len(values) > 1 for values in cds_to_genes.values()),
        "Names_with_multiple_CDS_sequences": sum(len(values) > 1 for values in name_to_cds.values()),
        "deduplication_applied": False,
    }


def split_qc(rows):
    names = [row["Name"] for row in rows]
    genes = [row["Gene"] for row in rows]
    cds_values = [row["CDS.seq"] for row in rows]
    translations = [
        "M" + "A" * 10 if gene == "GeneA" else "M" + "F" * 11 for gene in genes
    ]
    leader = "TTGACATTTTAAGGAG"
    return {
        "split_performed": False,
        "primary_group": "Gene",
        "additional_duplicate_blocking_groups": ["exact_CDS", "Name_CDS"],
        "groups": {
            "Gene": group_summary(genes),
            "exact_CDS": group_summary(cds_values),
            "Name_CDS": group_summary([
                json.dumps([name, cds], ensure_ascii=False) for name, cds in zip(names, cds_values)
            ]),
            "translation": group_summary(translations),
            "leader": group_summary([leader] * len(rows)),
        },
        "multi_gene_pool_is_protein_ood": False,
        "protein_ood_supported": False,
        "note": verifier.SPLIT_NOTE,
    }


def synthetic_report(rows, raw_sha, clean_sha):
    same_four = {"Synthetic": 4}
    return {
        "schema": verifier.EXPECTED_REPORT_SCHEMA,
        "protocol": verifier.EXPECTED_REPORT_PROTOCOL,
        "status": "candidate_procedure_and_qc_passed",
        "scope": verifier.EXPECTED_SCOPE,
        "task_eligibility": {
            "task": "T1_leader_context_n_terminal_construct_function",
            "candidate_research_only": True,
            "procedure_and_qc_only": True,
            "final_untouched": False,
            "leader_context_n_terminal_window_supported": True,
            "fixed_single_leader_claim": False,
            "full_length_cds_supported": False,
            "native_utr_supported": False,
            "protein_ood_supported": False,
            "scientific_positive_claim_eligible": False,
        },
        "source": {
            "citation_key": "Goodman2013",
            "doi": "10.1126/science.1241934",
            "url": verifier.EXPECTED_RAW_URL,
            "license": {
                "status": "unconfirmed",
                "confirmed": False,
                "redistribution_or_derivative_use_requires_review": True,
            },
        },
        "sha256": {"raw_csv": raw_sha, "clean_csv": clean_sha},
        "raw_csv": {"columns": COLUMNS, "column_count": 75, "data_rows": len(rows)},
        "clean_csv": {
            "columns": COLUMNS,
            "column_count": 75,
            "data_rows": len(rows),
            "all_original_columns_preserved": True,
            "all_original_rows_preserved": True,
            "all_field_values_preserved": True,
            "filtering_applied": False,
            "deduplication_applied": False,
            "serialization": "UTF-8 CSV, original column order and field values, LF line endings",
        },
        "sequence_qc": {
            "rows": 4,
            "valid_rows": 4,
            "length_nt_distribution": {"33": 3, "36": 1},
            "length_nt_summary": {"min": 33, "max": 36, "mean": 33.75},
            "empty_cds_rows": 0,
            "invalid_alphabet_rows": 0,
            "length_not_divisible_by_3_rows": 0,
            "non_atg_start_rows": 0,
            "internal_stop_rows": 0,
            "terminal_stop_rows": 0,
            "stop_free_rows": 4,
        },
        "translation_qc": {
            "group": "Gene",
            "gene_count": 2,
            "consistent_gene_count": 2,
            "inconsistent_gene_count": 0,
            "per_gene": [
                {"Gene": "GeneA", "sample_count": 3, "unique_translation_count": 1,
                 "translations": ["M" + "A" * 10], "consistent": True},
                {"Gene": "GeneB", "sample_count": 1, "unique_translation_count": 1,
                 "translations": ["M" + "F" * 11], "consistent": True},
            ],
        },
        "duplicate_qc": duplicate_qc(rows),
        "construction_qc": {
            "scope": verifier.SUPPORTED_CONSTRUCT_SCOPE,
            "official_observed_leader_context_groups": 280,
            "observed_leader_context_groups": 1,
            "official_leader_contexts_vary": True,
            "official_uniform_fixed_leader": False,
            "observed_leader_contexts_vary": False,
            "sequence_diversity": {
                "Promoter": diversity({"SyntheticPromoter": 4}),
                "Promoter.seq": diversity({"TTGACATTTT": 4}),
                "RBS.seq": diversity({"AAGGAG": 4}),
                "leader": diversity({"TTGACATTTTAAGGAG": 4}),
            },
            "leader_definition": verifier.LEADER_DEFINITION,
            "CDS.type": {
                "unique_values": 1,
                "value_counts": {"synthetic_N_terminal_window": 4},
            },
        },
        "filter_qc": {
            "fields": {column: filter_summary(rows, column) for column in verifier.FLAG_COLUMNS},
            "filtering_applied": False,
            "rows_removed_from_clean": 0,
            "Fltr.SetGood_used_for_row_selection": False,
        },
        "numeric_qc": {column: numeric_summary(rows, column) for column in verifier.NUMERIC_COLUMNS},
        "distribution_qc": {
            column: numeric_summary(rows, column) for column in verifier.DISTRIBUTION_COLUMNS
        },
        "gene_qc": {
            "gene_count": 2,
            "sample_counts": {"GeneA": 3, "GeneB": 1},
            "sample_count_summary": {"min": 1, "max": 3, "mean": 2, "median": 2, "singleton_genes": 1},
        },
        "split_leakage_qc": split_qc(rows),
    }


def make_case(tmp_path, monkeypatch):
    raw_csv = tmp_path / "synthetic_goodman_raw.csv"
    clean_csv = tmp_path / "synthetic_goodman_clean.csv"
    report_json = tmp_path / "synthetic_goodman_report.json"
    rows = synthetic_rows()
    write_csv(raw_csv, rows)
    write_csv(clean_csv, rows)
    raw_sha = sha256(raw_csv)
    monkeypatch.setattr(verifier, "EXPECTED_RAW_SHA256", raw_sha)
    monkeypatch.setattr(verifier, "EXPECTED_RAW_DATA_ROWS", len(rows))
    monkeypatch.setattr(verifier, "EXPECTED_UNIQUE_LEADER_GROUPS", 1)
    report = synthetic_report(rows, raw_sha, sha256(clean_csv))
    report_json.write_text(json.dumps(report), encoding="utf-8")
    return {"raw_csv": raw_csv, "clean_csv": clean_csv, "report_json": report_json, "report": report}


def verify(case):
    return verifier.verify_goodman_e0(case["raw_csv"], case["clean_csv"], case["report_json"])


def save_report(case):
    case["report_json"].write_text(json.dumps(case["report"]), encoding="utf-8")


def arguments(case, output):
    return [
        "--raw-csv", str(case["raw_csv"]), "--clean-csv", str(case["clean_csv"]),
        "--report", str(case["report_json"]), "--output", str(output),
    ]


def test_official_identity_and_claim_scope_are_frozen():
    assert verifier.EXPECTED_RAW_SHA256 == "a03071027b8c0008d07fb7737de0a7d51765c6cff25bc86e93465a6253c7c33a"
    assert verifier.EXPECTED_RAW_URL.endswith("1241934tables1.csv")
    assert verifier.EXPECTED_RAW_DATA_ROWS == 14234
    assert verifier.EXPECTED_COLUMN_COUNT == 75
    assert len(COLUMNS) == 75
    assert verifier.OFFICIAL_LEADER_CONTEXT_GROUPS == 280
    assert verifier.EXPECTED_UNIQUE_LEADER_GROUPS == 280
    assert verifier.EXPECTED_REPORT_SCHEMA == "a10-01-goodman-e0-audit-report-v2"
    assert verifier.EXPECTED_REPORT_PROTOCOL == "a10_01_goodman_e0_protocol_v2"
    assert verifier.EXPECTED_EXAMPLE_CDS_NT_LENGTH == 33
    assert verifier.EXPECTED_SCOPE == "procedure_and_qc_only_no_functional_or_model_conclusion"


def test_synthetic_exact_reconstruction_and_independent_summary_pass(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    result = verify(case)

    assert result["passed"]
    assert all(result["checks"].values())
    assert result["recomputed"]["raw_csv"]["data_rows"] == 4
    assert result["recomputed"]["duplicate_qc"]["Name"]["unique_groups"] == 4
    assert result["recomputed"]["duplicate_qc"]["exact_CDS"]["unique_groups"] == 4
    assert result["recomputed"]["sequence_qc"]["length_nt_distribution"] == {"33": 3, "36": 1}
    construction = result["recomputed"]["construction_qc"]
    assert construction["official_observed_leader_context_groups"] == 280
    assert construction["observed_leader_context_groups"] == 1
    assert construction["official_leader_contexts_vary"] is True
    assert construction["official_uniform_fixed_leader"] is False
    assert construction["observed_leader_contexts_vary"] is False
    assert result["recomputed"]["gene_qc"]["sample_counts"] == {"GeneA": 3, "GeneB": 1}
    assert result["recomputed"]["translation_qc"]["per_gene"][1]["translations"] == ["M" + "F" * 11]
    assert {
        column: result["recomputed"]["filter_qc"]["fields"][column]["true_rows"]
        for column in verifier.FLAG_COLUMNS
    } == {
        "Insuff.Prot": 1, "Insuff.DNA": 1, "Insuff.RNA": 1,
        "Fltr.BelowRange": 1, "Fltr.AboveRange": 1, "Fltr.SetGood": 1,
    }
    trans = result["recomputed"]["numeric_qc"]["Trans"]
    assert trans["finite_rows"] == 4
    assert trans["min"] == "0.5"
    assert trans["max"] == 4
    assert trans["mean"] == "1.875"
    assert trans["median"] == "1.5"
    assert trans["quantiles"]["p95"] == "3.7"
    protein = result["recomputed"]["numeric_qc"]["Count.Prot"]
    assert protein["finite_rows"] == 3
    assert protein["non_numeric_rows"] == 1
    assert protein["mean"] == 20
    assert result["clean_comparison"]["mismatch_cells"] == 0


@pytest.mark.parametrize("field", ["Name", "CDS.seq", "Trans", "Extra.21"])
def test_clean_any_of_all_75_fields_tampering_is_detected(tmp_path, monkeypatch, field):
    case = make_case(tmp_path, monkeypatch)
    rows = synthetic_rows()
    rows[1][field] = "TAMPERED"
    write_csv(case["clean_csv"], rows)
    result = verify(case)

    assert not result["passed"]
    assert not result["checks"]["clean_all_75_fields"]
    assert not result["checks"]["clean_exact"]
    assert not result["checks"]["report_clean_sha256"]
    assert any(item.get("field") == field for item in result["clean_comparison"]["differences"])


def test_clean_row_deletion_and_reordering_are_detected(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    rows = synthetic_rows()
    write_csv(case["clean_csv"], rows[:2])
    result = verify(case)
    assert not result["checks"]["clean_row_count"]
    assert not result["checks"]["clean_exact"]

    write_csv(case["clean_csv"], [rows[1], rows[0], *rows[2:]])
    result = verify(case)
    assert result["checks"]["clean_row_count"]
    assert not result["checks"]["clean_all_75_fields"]


def test_raw_sha_and_reported_raw_sha_are_both_enforced(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    case["report"]["sha256"]["raw_csv"] = "0" * 64
    save_report(case)
    result = verify(case)
    assert result["checks"]["raw_sha256"]
    assert not result["checks"]["report_raw_sha256"]

    case["report"]["sha256"]["raw_csv"] = sha256(case["raw_csv"])
    save_report(case)
    rows = synthetic_rows()
    rows[0]["Trans"] = "99"
    write_csv(case["raw_csv"], rows)
    result = verify(case)
    assert not result["checks"]["raw_sha256"]
    assert not result["checks"]["clean_exact"]
    assert not result["checks"]["report_numeric_qc"]


def test_reported_clean_sha_is_enforced(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    case["report"]["sha256"]["clean_csv"] = "0" * 64
    save_report(case)
    result = verify(case)
    assert not result["passed"]
    assert not result["checks"]["report_clean_sha256"]
    assert result["checks"]["clean_exact"]


@pytest.mark.parametrize("section,path,value,check", [
    ("raw_csv", ("data_rows",), 5, "report_raw_csv"),
    ("duplicate_qc", ("Name", "unique_groups"), 3, "report_duplicate_qc"),
    ("duplicate_qc", ("exact_CDS", "unique_groups"), 3, "report_duplicate_qc"),
    ("sequence_qc", ("valid_rows",), 3, "report_sequence_qc"),
    ("sequence_qc", ("terminal_stop_rows",), 1, "report_sequence_qc"),
    ("translation_qc", ("inconsistent_gene_count",), 1, "report_translation_qc"),
    ("construction_qc", ("official_observed_leader_context_groups",), 279, "report_construction_qc"),
    ("construction_qc", ("observed_leader_context_groups",), 2, "report_construction_qc"),
    ("construction_qc", ("official_leader_contexts_vary",), False, "report_construction_qc"),
    ("construction_qc", ("official_uniform_fixed_leader",), True, "report_construction_qc"),
    ("construction_qc", ("observed_leader_contexts_vary",), True, "report_construction_qc"),
    ("construction_qc", ("sequence_diversity", "leader", "unique_values"), 2, "report_construction_qc"),
    ("construction_qc", ("sequence_diversity", "RBS.seq", "largest_value_count"), 3, "report_construction_qc"),
    ("construction_qc", ("CDS.type", "unique_values"), 2, "report_construction_qc"),
])
def test_report_raw_qc_tampering_is_detected(tmp_path, monkeypatch, section, path, value, check):
    case = make_case(tmp_path, monkeypatch)
    target = case["report"][section]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    save_report(case)
    result = verify(case)
    assert not result["passed"]
    assert not result["checks"][check]
    assert result["checks"]["clean_exact"]


def test_gene_sample_count_and_translation_tampering_are_detected(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    case["report"]["gene_qc"]["sample_counts"]["GeneA"] = 2
    case["report"]["translation_qc"]["per_gene"][1]["translations"] = ["M" + "Y" * 11]
    save_report(case)
    result = verify(case)
    assert not result["passed"]
    assert not result["checks"]["report_gene_qc"]
    assert not result["checks"]["report_translation_qc"]


def test_filter_count_and_filter_missingness_tampering_are_detected(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    case["report"]["filter_qc"]["fields"]["Insuff.Prot"]["true_rows"] = 0
    case["report"]["filter_qc"]["fields"]["Fltr.SetGood"]["false_rows"] = 2
    save_report(case)
    result = verify(case)
    assert not result["passed"]
    assert not result["checks"]["report_filter_qc"]


@pytest.mark.parametrize("column,key,value", [
    ("Trans", "mean", 2.0),
    ("Trans", "median", 2.0),
    ("Count.Prot", "mean", 21),
    ("Count.Prot", "non_numeric_rows", 0),
    ("dG", "min", -999),
])
def test_numeric_summary_tampering_is_detected(tmp_path, monkeypatch, column, key, value):
    case = make_case(tmp_path, monkeypatch)
    case["report"]["numeric_qc"][column][key] = value
    save_report(case)
    result = verify(case)
    assert not result["passed"]
    assert not result["checks"]["report_numeric_qc"]
    assert result["report_summary_comparison"]["numeric_qc"]


@pytest.mark.parametrize("field,value,check", [
    ("final_untouched", True, "not_final_untouched"),
    ("scientific_positive_claim_eligible", True, "no_scientific_positive"),
    ("full_length_cds_supported", True, "no_full_length_cds_claim"),
    ("native_utr_supported", True, "no_native_utr_claim"),
    ("protein_ood_supported", True, "no_protein_ood_claim"),
    ("leader_context_n_terminal_window_supported", False, "report_e0_only"),
    ("no_fixed_single_leader_claim", False, "no_fixed_single_leader_claim"),
    ("fixed_single_leader_claim", True, "no_fixed_single_leader_claim"),
    ("fixed_leader_n_terminal_window_supported", True, "no_fixed_single_leader_claim"),
    ("procedure_and_qc_only", False, "report_e0_only"),
])
def test_claim_boundary_forgery_is_detected(tmp_path, monkeypatch, field, value, check):
    case = make_case(tmp_path, monkeypatch)
    case["report"]["task_eligibility"][field] = value
    save_report(case)
    result = verify(case)
    assert not result["passed"]
    assert not result["checks"][check]


def test_nested_untouched_claim_and_construct_scope_forgery_fail(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    case["report"]["nested_evidence"] = {
        "final_untouched": True,
        "fixed_leader_n_terminal_window_supported": True,
    }
    case["report"]["construction_qc"]["scope"] = "full-length native-UTR protein OOD"
    case["report"]["construction_qc"]["leader_definition"] = "one uniform fixed leader"
    save_report(case)
    result = verify(case)
    assert not result["passed"]
    assert not result["checks"]["not_final_untouched"]
    assert not result["checks"]["no_fixed_single_leader_claim"]
    assert not result["checks"]["report_construction_qc"]


def test_optional_explicit_non_single_leader_boundary_passes(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    case["report"]["task_eligibility"]["no_fixed_single_leader_claim"] = True
    save_report(case)
    result = verify(case)
    assert result["passed"]
    assert result["checks"]["no_fixed_single_leader_claim"]


def test_unique_leader_group_count_is_independently_enforced(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    monkeypatch.setattr(verifier, "EXPECTED_UNIQUE_LEADER_GROUPS", 2)
    result = verify(case)
    assert not result["passed"]
    assert not result["checks"]["leader_group_count"]
    assert result["checks"]["report_construction_qc"]


def test_legacy_v1_report_identity_is_rejected(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    case["report"]["schema"] = "a10-01-goodman-e0-audit-report-v1"
    case["report"]["protocol"] = "a10_01_goodman_e0_protocol_v1"
    save_report(case)
    result = verify(case)
    assert not result["passed"]
    assert not result["checks"]["report_identity"]


@pytest.mark.parametrize("kind,sequence", [
    ("length", ("ATG" + "GCT" * 10)[:-1]),
    ("start", "GTG" + "GCT" * 10),
    ("alphabet", "ATG" + "GCT" * 9 + "GCN"),
    ("terminal_stop", "ATG" + "GCT" * 9 + "TAA"),
])
def test_raw_sequence_qc_failures_are_recomputed(tmp_path, monkeypatch, kind, sequence):
    case = make_case(tmp_path, monkeypatch)
    rows = synthetic_rows()
    rows[0]["CDS.seq"] = sequence
    write_csv(case["raw_csv"], rows)
    result = verify(case)
    assert not result["passed"]
    assert not result["checks"]["sequence_qc"]
    counter = {
        "length": "length_not_divisible_by_3_rows",
        "start": "non_atg_start_rows",
        "alphabet": "invalid_alphabet_rows",
        "terminal_stop": "terminal_stop_rows",
    }[kind]
    assert result["recomputed"]["sequence_qc"][counter] == 1


def test_duplicate_name_and_cds_are_recomputed_without_silent_deduplication(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    rows = synthetic_rows()
    rows[1]["Name"] = rows[0]["Name"]
    rows[1]["CDS.seq"] = rows[0]["CDS.seq"]
    write_csv(case["raw_csv"], rows)
    write_csv(case["clean_csv"], rows)
    raw_sha = sha256(case["raw_csv"])
    monkeypatch.setattr(verifier, "EXPECTED_RAW_SHA256", raw_sha)
    case["report"] = synthetic_report(rows, raw_sha, sha256(case["clean_csv"]))
    save_report(case)

    result = verify(case)
    assert result["passed"]
    assert result["recomputed"]["duplicate_qc"]["Name"]["unique_groups"] == 3
    assert result["recomputed"]["duplicate_qc"]["Name"]["duplicate_rows_beyond_first"] == 1
    assert result["recomputed"]["duplicate_qc"]["exact_CDS"]["unique_groups"] == 3
    assert result["recomputed"]["duplicate_qc"]["exact_CDS"]["duplicate_rows_beyond_first"] == 1


def test_within_gene_nonsynonymous_variants_fail(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    rows = synthetic_rows()
    rows[2]["Gene"] = "GeneB"
    write_csv(case["raw_csv"], rows)
    result = verify(case)
    assert not result["passed"]
    assert not result["checks"]["gene_translation_consistency"]
    assert result["recomputed"]["translation_qc"]["inconsistent_gene_count"] == 1


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
    case["report"]["numeric_qc"]["Trans"]["mean"] = 999
    save_report(case)
    output = tmp_path / "failed-verification.json"
    assert verifier.main(arguments(case, output)) == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert not payload["passed"]
    assert not payload["checks"]["report_numeric_qc"]
    original = output.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        verifier.main(arguments(case, output))
    assert output.read_bytes() == original


def test_main_reports_malformed_raw_as_nonzero_json(tmp_path, monkeypatch):
    case = make_case(tmp_path, monkeypatch)
    malformed_columns = COLUMNS[:-1]
    malformed_rows = [{column: row[column] for column in malformed_columns} for row in synthetic_rows()]
    write_csv(case["raw_csv"], malformed_rows, columns=malformed_columns)
    output = tmp_path / "malformed.json"
    assert verifier.main(arguments(case, output)) == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert not payload["passed"]
    assert payload["error"]["type"] == "ValueError"
    assert "exactly 75 columns" in payload["error"]["message"]


def test_verifier_has_no_production_imports():
    tree = ast.parse(Path(verifier.__file__).read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(name == "codonflow" or name.startswith(("codonflow.", "scripts.")) for name in imported)
