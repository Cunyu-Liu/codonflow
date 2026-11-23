"""Freeze deterministic, outcome-blind nested Gene-grouped Goodman CV splits."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path


PROTOCOL = "a10_01_goodman_split_protocol_v1"
PROTOCOL_SCHEMA = "a10-01-goodman-split-protocol-v1"
REPORT_SCHEMA = "a10-01-goodman-frozen-nested-grouped-cv-v1"
REQUIRED_COLUMNS = ["Name", "Gene", "CDS.seq"]
ASSIGNMENT_COLUMNS = [*REQUIRED_COLUMNS, "outer_fold"]
OUTER_FOLDS = 5
INNER_FOLDS = 4


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--clean-csv", required=True, help="Goodman clean-v3 CSV")
    parser.add_argument("--protocol", required=True, help="Frozen split protocol JSON")
    parser.add_argument("--assignment-csv", required=True, help="New outer-fold assignment CSV")
    parser.add_argument("--split-json", required=True, help="New frozen nested split JSON")
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
    clean_csv = input_file(args.clean_csv, "clean CSV")
    protocol_path = input_file(args.protocol, "protocol")
    assignment_csv = Path(args.assignment_csv).expanduser().resolve()
    split_json = Path(args.split_json).expanduser().resolve()
    if assignment_csv == split_json:
        raise ValueError("assignment CSV and split JSON must be different paths")
    for path in (assignment_csv, split_json):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
    return clean_csv, protocol_path, assignment_csv, split_json


def positive_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"protocol {label} must be a positive integer")
    return value


def load_protocol(path):
    with path.open(encoding="utf-8") as handle:
        protocol = json.load(handle)
    if protocol.get("schema") != PROTOCOL_SCHEMA or protocol.get("protocol") != PROTOCOL:
        raise ValueError(f"protocol identity mismatch: expected {PROTOCOL}")
    clean = protocol.get("inputs", {}).get("clean_csv", {})
    if not re.fullmatch(r"[0-9a-f]{64}", clean.get("sha256", "")):
        raise ValueError("protocol inputs.clean_csv.sha256 must be a lowercase SHA256")
    positive_integer(clean.get("expected_data_rows"), "expected_data_rows")
    positive_integer(clean.get("expected_gene_count"), "expected_gene_count")
    positive_integer(clean.get("expected_unique_exact_cds"), "expected_unique_exact_cds")
    rows_per_gene = clean.get("expected_rows_per_gene")
    if not isinstance(rows_per_gene, list) or not rows_per_gene:
        raise ValueError("protocol expected_rows_per_gene must be a nonempty integer list")
    for value in rows_per_gene:
        positive_integer(value, "expected_rows_per_gene entries")
    if rows_per_gene != sorted(set(rows_per_gene)):
        raise ValueError("protocol expected_rows_per_gene must be sorted and unique")
    if clean.get("required_columns") != REQUIRED_COLUMNS:
        raise ValueError("protocol clean CSV required columns must be Name, Gene and CDS.seq")
    if protocol.get("inputs", {}).get("untouched_inputs_read") is not False:
        raise ValueError("protocol must forbid reading untouched inputs")
    split = protocol.get("split", {})
    if any((
        split.get("primary_group") != "Gene",
        split.get("consistency_groups") != ["exact_CDS", "Name"],
        split.get("outer_folds") != OUTER_FOLDS,
        split.get("inner_folds") != INNER_FOLDS,
        split.get("balance_metric") != "Gene_count",
        split.get("maximum_gene_count_difference_within_partition") != 1,
        split.get("deterministic") is not True,
        split.get("hash_algorithm") != "SHA256",
        split.get("hash_namespace") != PROTOCOL,
        split.get("selection_columns") != REQUIRED_COLUMNS,
        split.get("outcome_columns_used_for_splitting") is not False,
    )):
        raise ValueError("protocol split settings do not match the frozen nested grouped CV")
    scope = protocol.get("scope", {})
    if any((
        scope.get("supported_ood") != "Gene-grouped N-terminal fragment construct OOD",
        scope.get("leader_context_n_terminal_window_supported") is not True,
        scope.get("protein_ood_supported") is not False,
        scope.get("multi_gene_pool_is_protein_ood") is not False,
        scope.get("full_length_cds_supported") is not False,
        scope.get("native_utr_supported") is not False,
    )):
        raise ValueError("protocol must preserve the N-terminal construct OOD claim boundary")
    outputs = protocol.get("outputs", {})
    if any((
        outputs.get("assignment_csv_columns") != ASSIGNMENT_COLUMNS,
        outputs.get("overwrite") != "forbidden",
        outputs.get("creation_mode") != "exclusive",
    )):
        raise ValueError("protocol outputs must use exclusive non-overwriting creation")
    return protocol


def verify_sha256(path, expected):
    observed = sha256_file(path)
    if observed != expected:
        raise ValueError(
            f"clean CSV SHA256 mismatch: expected {expected}, observed {observed}",
        )
    return observed


def consistency_conflicts(records, value_index, label):
    owners = {}
    conflicts = {}
    for record in records:
        value = record[value_index]
        gene = record[1]
        previous = owners.setdefault(value, gene)
        if previous != gene:
            conflicts.setdefault(value, {previous}).add(gene)
    if conflicts:
        examples = [
            {"value": value, "Genes": sorted(conflicts[value])}
            for value in sorted(conflicts)[:10]
        ]
        raise ValueError(
            f"{label} spans multiple Gene groups: "
            + json.dumps(examples, ensure_ascii=False),
        )


def read_clean_csv(path, protocol):
    clean = protocol["inputs"]["clean_csv"]
    records = []
    try:
        with path.open("r", encoding="utf-8-sig", errors="strict", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise ValueError("clean CSV is empty") from exc
            duplicates = sorted(name for name, count in Counter(header).items() if count > 1)
            if duplicates:
                raise ValueError(f"clean CSV has duplicate header fields: {duplicates}")
            missing = [name for name in REQUIRED_COLUMNS if name not in header]
            if missing:
                raise ValueError(f"clean CSV missing required columns: {missing}")
            indices = {name: header.index(name) for name in REQUIRED_COLUMNS}
            for row in reader:
                if len(row) != len(header):
                    raise ValueError(
                        f"clean CSV line {reader.line_num}: expected {len(header)} fields, "
                        f"observed {len(row)}",
                    )
                record = tuple(row[indices[name]] for name in REQUIRED_COLUMNS)
                for column, value in zip(REQUIRED_COLUMNS, record):
                    if not value:
                        raise ValueError(
                            f"clean CSV line {reader.line_num}: empty required field {column}",
                        )
                records.append(record)
    except csv.Error as exc:
        raise ValueError(f"clean CSV strict parse error near line {reader.line_num}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"clean CSV is not valid UTF-8: {exc}") from exc
    if len(records) != clean["expected_data_rows"]:
        raise ValueError(
            f"clean CSV data row count mismatch: expected {clean['expected_data_rows']}, "
            f"observed {len(records)}",
        )
    gene_counts = Counter(record[1] for record in records)
    if len(gene_counts) != clean["expected_gene_count"]:
        raise ValueError(
            f"clean CSV Gene count mismatch: expected {clean['expected_gene_count']}, "
            f"observed {len(gene_counts)}",
        )
    invalid_gene_counts = {
        gene: count for gene, count in sorted(gene_counts.items())
        if count not in clean["expected_rows_per_gene"]
    }
    if invalid_gene_counts:
        raise ValueError(f"clean CSV rows per Gene mismatch: {invalid_gene_counts}")
    consistency_conflicts(records, 2, "exact CDS")
    consistency_conflicts(records, 0, "Name")
    unique_exact_cds = len({record[2] for record in records})
    if unique_exact_cds != clean["expected_unique_exact_cds"]:
        raise ValueError(
            f"clean CSV unique exact CDS mismatch: expected "
            f"{clean['expected_unique_exact_cds']}, observed {unique_exact_cds}",
        )
    return records, gene_counts


def balanced_gene_folds(genes, fold_count, namespace):
    genes = sorted(genes)
    if len(genes) < fold_count:
        raise ValueError(
            f"partition {namespace} needs at least {fold_count} Genes; observed {len(genes)}",
        )
    folds = [[] for _ in range(fold_count)]
    for gene in genes:
        minimum = min(len(fold) for fold in folds)
        candidates = [index for index, fold in enumerate(folds) if len(fold) == minimum]
        selected = min(
            candidates,
            key=lambda index: (
                hashlib.sha256(
                    f"{PROTOCOL}\0{namespace}\0{gene}\0{index}".encode("utf-8"),
                ).digest(),
                index,
            ),
        )
        folds[selected].append(gene)
    return [sorted(fold) for fold in folds]


def assert_balanced(folds, label):
    sizes = [len(fold) for fold in folds]
    if not sizes or min(sizes) < 1 or max(sizes) - min(sizes) > 1:
        raise ValueError(f"{label} is not nonempty and Gene-count balanced: {sizes}")


def validate_partition(records, outer, inner_by_outer):
    genes = {record[1] for record in records}
    flat_outer = [gene for fold in outer for gene in fold]
    if len(flat_outer) != len(genes) or set(flat_outer) != genes:
        raise ValueError("outer folds do not assign every Gene exactly once")
    assert_balanced(outer, "outer partition")
    gene_outer = {gene: index for index, fold in enumerate(outer) for gene in fold}
    for value_index, label in ((0, "Name"), (2, "exact CDS")):
        values = {}
        for record in records:
            value = record[value_index]
            fold = gene_outer[record[1]]
            if values.setdefault(value, fold) != fold:
                raise ValueError(f"{label} crosses outer folds")
    for outer_index, (test, inner) in enumerate(zip(outer, inner_by_outer)):
        train = genes - set(test)
        flat_inner = [gene for fold in inner for gene in fold]
        if set(test) & train or set(test) & set(flat_inner):
            raise ValueError(f"outer fold {outer_index} test Genes overlap training Genes")
        if len(flat_inner) != len(train) or set(flat_inner) != train:
            raise ValueError(f"outer fold {outer_index} inner folds are incomplete or overlap")
        assert_balanced(inner, f"outer fold {outer_index} inner partition")


def build_partition(records):
    genes = {record[1] for record in records}
    outer = balanced_gene_folds(genes, OUTER_FOLDS, "outer")
    inner_by_outer = []
    outer_reports = []
    gene_counts = Counter(record[1] for record in records)
    for outer_index, test in enumerate(outer):
        train = sorted(genes - set(test))
        inner = balanced_gene_folds(
            train, INNER_FOLDS, f"outer-{outer_index}-inner",
        )
        inner_by_outer.append(inner)
        outer_reports.append({
            "outer_fold": outer_index,
            "test_genes": test,
            "train_genes": train,
            "test_gene_count": len(test),
            "train_gene_count": len(train),
            "test_row_count": sum(gene_counts[gene] for gene in test),
            "train_row_count": sum(gene_counts[gene] for gene in train),
            "train_inner_folds": {
                str(index): fold for index, fold in enumerate(inner)
            },
            "inner_fold_gene_counts": {
                str(index): len(fold) for index, fold in enumerate(inner)
            },
            "inner_fold_row_counts": {
                str(index): sum(gene_counts[gene] for gene in fold)
                for index, fold in enumerate(inner)
            },
        })
    validate_partition(records, outer, inner_by_outer)
    return outer, outer_reports


def serialize_assignment(records, outer):
    gene_outer = {gene: index for index, fold in enumerate(outer) for gene in fold}
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(ASSIGNMENT_COLUMNS)
    for name, gene, cds in records:
        writer.writerow([name, gene, cds, gene_outer[gene]])
    return buffer.getvalue().encode("utf-8")


def write_exclusive(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)


def freeze_splits(args):
    clean_csv, protocol_path, assignment_csv, split_json = validate_args(args)
    protocol = load_protocol(protocol_path)
    clean_sha = verify_sha256(clean_csv, protocol["inputs"]["clean_csv"]["sha256"])
    records, gene_counts = read_clean_csv(clean_csv, protocol)
    outer, outer_reports = build_partition(records)
    assignment_payload = serialize_assignment(records, outer)
    report = {
        "schema": REPORT_SCHEMA,
        "protocol": PROTOCOL,
        "status": "frozen_nested_grouped_cv_partition",
        "input_sha256": {
            "clean_csv": clean_sha,
            "protocol": sha256_file(protocol_path),
        },
        "input": {
            "data_rows": len(records),
            "gene_count": len(gene_counts),
            "unique_exact_cds": len({record[2] for record in records}),
            "unique_names": len({record[0] for record in records}),
        },
        "selection_columns": REQUIRED_COLUMNS,
        "outcome_columns_used_for_splitting": False,
        "untouched_inputs_read": False,
        "scope": protocol["scope"],
        "source_qc_reference": protocol["source_qc_reference"],
        "grouping": {
            "primary_group": "Gene",
            "consistency_groups": ["exact_CDS", "Name"],
            "cross_gene_exact_cds_groups": 0,
            "cross_gene_name_groups": 0,
            "outer_folds": OUTER_FOLDS,
            "inner_folds_per_outer": INNER_FOLDS,
            "balance_metric": "Gene_count",
            "maximum_gene_count_difference_within_partition": 1,
            "algorithm": protocol["split"]["algorithm"],
        },
        "leakage_qc": {
            "every_gene_assigned_to_exactly_one_outer_fold": True,
            "outer_test_train_gene_overlap_count": 0,
            "outer_test_inner_gene_overlap_count": 0,
            "within_outer_inner_gene_overlap_count": 0,
            "exact_cds_cross_outer_group_count": 0,
            "name_cross_outer_group_count": 0,
        },
        "outer_folds": outer_reports,
        "assignment_csv": {
            "columns": ASSIGNMENT_COLUMNS,
            "data_rows": len(records),
            "sha256": hashlib.sha256(assignment_payload).hexdigest(),
        },
        "limitations": protocol["limitations"],
    }
    split_payload = (
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")
    write_exclusive(assignment_csv, assignment_payload)
    try:
        write_exclusive(split_json, split_payload)
    except Exception:
        assignment_csv.unlink()
        raise
    print(json.dumps({
        "status": report["status"],
        "assignment_csv": str(assignment_csv),
        "split_json": str(split_json),
        "rows": len(records),
        "genes": len(gene_counts),
        "outer_folds": OUTER_FOLDS,
        "inner_folds_per_outer": INNER_FOLDS,
    }))
    return report


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    freeze_splits(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
