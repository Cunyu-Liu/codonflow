"""Independently verify frozen Goodman nested Gene-grouped CV artifacts.

The implementation mirrors the frozen public protocol without importing the
production partitioner. Only Name/Gene/CDS.seq are projected from the clean CSV.
"""
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
VERIFICATION_PROTOCOL = "a10_01_goodman_nested_grouped_cv_independent_verification_v2"
REQUIRED_COLUMNS = ["Name", "Gene", "CDS.seq"]
ASSIGNMENT_COLUMNS = [*REQUIRED_COLUMNS, "outer_fold"]
OUTER_FOLDS = 5
INNER_FOLDS = 4
SUPPORTED_OOD = "Gene-grouped N-terminal fragment construct OOD"


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(payload):
    return (json.dumps(
        payload, indent=2, ensure_ascii=False, allow_nan=False,
    ) + "\n").encode("utf-8")


def write_json_exclusive(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(canonical_json_bytes(payload))


def reject_nonfinite_json(value):
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def load_json(path, label):
    with Path(path).open("r", encoding="utf-8", errors="strict") as handle:
        payload = json.load(handle, parse_constant=reject_nonfinite_json)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} JSON must be an object")
    return payload


def positive_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"protocol {label} must be a positive integer")


def load_protocol(path):
    protocol = load_json(path, "protocol")
    if protocol.get("schema") != PROTOCOL_SCHEMA or protocol.get("protocol") != PROTOCOL:
        raise ValueError(f"protocol identity mismatch: expected {PROTOCOL}")
    clean = protocol.get("inputs", {}).get("clean_csv", {})
    if not re.fullmatch(r"[0-9a-f]{64}", clean.get("sha256", "")):
        raise ValueError("protocol inputs.clean_csv.sha256 must be a lowercase SHA256")
    for key in ("expected_data_rows", "expected_gene_count", "expected_unique_exact_cds"):
        positive_integer(clean.get(key), key)
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
        scope.get("supported_ood") != SUPPORTED_OOD,
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


def read_clean_projection(path):
    rows = []
    with Path(path).open("r", encoding="utf-8-sig", errors="strict", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("clean CSV is empty") from exc
        if any(not column for column in header) or len(set(header)) != len(header):
            raise ValueError("clean CSV has empty or duplicate column names")
        missing = [column for column in REQUIRED_COLUMNS if column not in header]
        if missing:
            raise ValueError(f"clean CSV is missing split columns: {missing}")
        indices = tuple(header.index(column) for column in REQUIRED_COLUMNS)
        for values in reader:
            if len(values) != len(header):
                raise ValueError(
                    f"clean CSV line {reader.line_num} has {len(values)} fields; "
                    f"expected {len(header)}",
                )
            record = tuple(values[index] for index in indices)
            if any(not value for value in record):
                raise ValueError("Name, Gene and CDS.seq must be non-empty")
            rows.append(record)
    if not rows:
        raise ValueError("clean CSV has no data rows")
    return rows


def read_assignment(path):
    rows = []
    with Path(path).open("r", encoding="utf-8-sig", errors="strict", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("assignment CSV is empty") from exc
        if header != ASSIGNMENT_COLUMNS:
            raise ValueError(
                f"assignment CSV header must be exactly {ASSIGNMENT_COLUMNS}",
            )
        for values in reader:
            if len(values) != len(ASSIGNMENT_COLUMNS):
                raise ValueError(
                    f"assignment CSV line {reader.line_num} has {len(values)} fields; "
                    f"expected {len(ASSIGNMENT_COLUMNS)}",
                )
            rows.append(tuple(values))
    return rows


def clean_summary(rows):
    gene_counts = Counter(row[1] for row in rows)
    return {
        "data_rows": len(rows),
        "gene_count": len(gene_counts),
        "unique_exact_cds": len({row[2] for row in rows}),
        "unique_names": len({row[0] for row in rows}),
    }, gene_counts


def mapping_is_functional(rows, value_index):
    mapping = {}
    for row in rows:
        mapping.setdefault(row[value_index], set()).add(row[1])
    return all(len(genes) == 1 for genes in mapping.values()), mapping


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


def expected_partition(gene_counts):
    genes = set(gene_counts)
    outer = balanced_gene_folds(genes, OUTER_FOLDS, "outer")
    outer_reports = []
    for outer_index, test in enumerate(outer):
        train = sorted(genes - set(test))
        inner = balanced_gene_folds(
            train, INNER_FOLDS, f"outer-{outer_index}-inner",
        )
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
    return outer, outer_reports


def expected_assignment(rows, outer):
    gene_outer = {gene: index for index, fold in enumerate(outer) for gene in fold}
    return [
        (name, gene, cds, str(gene_outer[gene]))
        for name, gene, cds in rows
    ]


def assignment_bytes(rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(ASSIGNMENT_COLUMNS)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def expected_report(protocol, summary, outer_reports, clean_sha, protocol_sha, assignment_sha):
    return {
        "schema": REPORT_SCHEMA,
        "protocol": PROTOCOL,
        "status": "frozen_nested_grouped_cv_partition",
        "input_sha256": {
            "clean_csv": clean_sha,
            "protocol": protocol_sha,
        },
        "input": summary,
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
            "data_rows": summary["data_rows"],
            "sha256": assignment_sha,
        },
        "limitations": protocol["limitations"],
    }


def value_mismatches(observed, expected, path=""):
    if expected is None:
        return [] if observed is None else [path]
    if isinstance(expected, bool):
        return [] if observed is expected else [path]
    if isinstance(expected, int):
        return [] if type(observed) is int and observed == expected else [path]
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


def string_set(values):
    return (
        isinstance(values, list)
        and all(isinstance(value, str) and value for value in values)
        and len(values) == len(set(values))
    )


def extract_gene_sets(report, all_genes):
    try:
        folds = report["outer_folds"]
        if len(folds) != OUTER_FOLDS:
            return None
        extracted = []
        for outer_fold, fold in enumerate(folds):
            test = fold["test_genes"]
            train = fold["train_genes"]
            inner_folds = fold["train_inner_folds"]
            if (
                type(fold["outer_fold"]) is not int
                or fold["outer_fold"] != outer_fold
                or not string_set(test)
                or not string_set(train)
                or not isinstance(inner_folds, dict)
                or set(inner_folds) != {str(index) for index in range(INNER_FOLDS)}
            ):
                return None
            inners = []
            for index in range(INNER_FOLDS):
                inner = inner_folds[str(index)]
                if not string_set(inner):
                    return None
                inners.append(set(inner))
            extracted.append((set(test), set(train), inners))
    except (KeyError, TypeError):
        return None
    universe = set(all_genes)
    if any(
        not genes <= universe
        for test, train, inners in extracted
        for genes in (test, train, *inners)
    ):
        return None
    return extracted


def values_for_genes(mapping, genes):
    return set().union(*(mapping[gene] for gene in genes)) if genes else set()


def split_invariant_checks(report, all_genes, name_genes, cds_genes):
    genes_by_name = {}
    genes_by_cds = {}
    for name, genes in name_genes.items():
        for gene in genes:
            genes_by_name.setdefault(gene, set()).add(name)
    for cds, genes in cds_genes.items():
        for gene in genes:
            genes_by_cds.setdefault(gene, set()).add(cds)
    extracted = extract_gene_sets(report, all_genes)
    checks = {
        "outer_gene_partition": False,
        "outer_gene_isolation": False,
        "inner_gene_partition": False,
        "inner_gene_isolation": False,
        "outer_name_isolation": False,
        "outer_exact_cds_isolation": False,
        "inner_name_isolation": False,
        "inner_exact_cds_isolation": False,
        "outer_gene_balance": False,
        "inner_gene_balance": False,
    }
    if extracted is None:
        return checks
    universe = set(all_genes)
    checks["outer_gene_partition"] = (
        all(test | train == universe for test, train, _ in extracted)
        and set().union(*(test for test, _, _ in extracted)) == universe
        and sum(len(test) for test, _, _ in extracted) == len(universe)
    )
    checks["outer_gene_isolation"] = all(
        test.isdisjoint(train) for test, train, _ in extracted
    ) and all(
        extracted[left][0].isdisjoint(extracted[right][0])
        for left in range(OUTER_FOLDS)
        for right in range(left + 1, OUTER_FOLDS)
    )
    checks["inner_gene_partition"] = all(
        set().union(*inners) == train
        and sum(len(inner) for inner in inners) == len(train)
        for _, train, inners in extracted
    )
    checks["inner_gene_isolation"] = all(
        test.isdisjoint(set().union(*inners))
        and all(
            inners[left].isdisjoint(inners[right])
            for left in range(INNER_FOLDS)
            for right in range(left + 1, INNER_FOLDS)
        )
        for test, _, inners in extracted
    )
    for label, mapping in (("name", genes_by_name), ("exact_cds", genes_by_cds)):
        checks[f"outer_{label}_isolation"] = all(
            values_for_genes(mapping, test).isdisjoint(values_for_genes(mapping, train))
            for test, train, _ in extracted
        )
        checks[f"inner_{label}_isolation"] = all(
            values_for_genes(mapping, inner).isdisjoint(
                values_for_genes(mapping, train - inner)
            )
            for _, train, inners in extracted
            for inner in inners
        )
    outer_sizes = [len(test) for test, _, _ in extracted]
    checks["outer_gene_balance"] = (
        min(outer_sizes) >= 1 and max(outer_sizes) - min(outer_sizes) <= 1
    )
    checks["inner_gene_balance"] = all(
        min(len(inner) for inner in inners) >= 1
        and max(len(inner) for inner in inners) - min(len(inner) for inner in inners) <= 1
        for _, _, inners in extracted
    )
    return checks


def assignment_mismatches(observed, expected):
    mismatches = []
    for index in range(max(len(observed), len(expected))):
        if index >= len(observed):
            mismatches.append({"row": index + 2, "kind": "missing"})
        elif index >= len(expected):
            mismatches.append({"row": index + 2, "kind": "unexpected"})
        elif observed[index] != expected[index]:
            mismatches.append({
                "row": index + 2,
                "kind": "value",
                "expected": list(expected[index]),
                "observed": list(observed[index]),
            })
        if len(mismatches) == 100:
            break
    return mismatches


def verify_goodman_splits(clean_csv, protocol_path, assignment_csv, split_json):
    paths = tuple(
        Path(value).expanduser().resolve()
        for value in (clean_csv, protocol_path, assignment_csv, split_json)
    )
    clean_path, protocol_path, assignment_path, split_path = paths
    protocol = load_protocol(protocol_path)
    clean_contract = protocol["inputs"]["clean_csv"]
    rows = read_clean_projection(clean_path)
    summary, gene_counts = clean_summary(rows)
    name_functional, name_genes = mapping_is_functional(rows, 0)
    cds_functional, cds_genes = mapping_is_functional(rows, 2)
    outer, outer_reports = expected_partition(gene_counts)
    recomputed_assignment = expected_assignment(rows, outer)
    recomputed_assignment_bytes = assignment_bytes(recomputed_assignment)
    assignment_sha = hashlib.sha256(recomputed_assignment_bytes).hexdigest()

    observed_assignment = read_assignment(assignment_path)
    observed_report = load_json(split_path, "split report")
    hashes = {
        "clean_csv": file_sha256(clean_path),
        "protocol": file_sha256(protocol_path),
        "assignment_csv": file_sha256(assignment_path),
        "split_json": file_sha256(split_path),
    }
    recomputed_report = expected_report(
        protocol,
        summary,
        outer_reports,
        hashes["clean_csv"],
        hashes["protocol"],
        assignment_sha,
    )
    recomputed_split_bytes = canonical_json_bytes(recomputed_report)
    report_input_hashes = observed_report.get("input_sha256", {})
    if not isinstance(report_input_hashes, dict):
        report_input_hashes = {}
    report_assignment = observed_report.get("assignment_csv", {})
    if not isinstance(report_assignment, dict):
        report_assignment = {}
    assignment_projection_ok = len(observed_assignment) == len(rows) and all(
        observed[:3] == clean for observed, clean in zip(observed_assignment, rows)
    )
    checks = {
        "clean_sha256": hashes["clean_csv"] == clean_contract["sha256"],
        "clean_row_count": summary["data_rows"] == clean_contract["expected_data_rows"],
        "clean_gene_count": summary["gene_count"] == clean_contract["expected_gene_count"],
        "clean_gene_row_sizes": set(gene_counts.values()) <= set(
            clean_contract["expected_rows_per_gene"]
        ),
        "clean_unique_exact_cds": (
            summary["unique_exact_cds"] == clean_contract["expected_unique_exact_cds"]
        ),
        "clean_name_follows_gene": name_functional,
        "clean_exact_cds_follows_gene": cds_functional,
        "assignment_row_conservation": assignment_projection_ok,
        "assignment_exact": observed_assignment == recomputed_assignment,
        "report_exact": not value_mismatches(observed_report, recomputed_report, "report"),
        "report_clean_sha256": report_input_hashes.get("clean_csv") == hashes["clean_csv"],
        "report_protocol_sha256": report_input_hashes.get("protocol") == hashes["protocol"],
        "report_assignment_sha256": (
            report_assignment.get("sha256") == hashes["assignment_csv"]
        ),
        "deterministic_assignment_bytes": assignment_path.read_bytes() == recomputed_assignment_bytes,
        "deterministic_splits_bytes": split_path.read_bytes() == recomputed_split_bytes,
        "source_qc_reference": (
            observed_report.get("source_qc_reference") == protocol["source_qc_reference"]
        ),
        "claim_boundaries": (
            observed_report.get("scope") == protocol["scope"]
            and observed_report.get("outcome_columns_used_for_splitting") is False
            and observed_report.get("untouched_inputs_read") is False
        ),
        **split_invariant_checks(observed_report, set(gene_counts), name_genes, cds_genes),
    }
    return {
        "protocol": VERIFICATION_PROTOCOL,
        "passed": all(checks.values()),
        "scope": SUPPORTED_OOD,
        "inputs": {
            "clean_csv": str(clean_path),
            "protocol": str(protocol_path),
            "assignment_csv": str(assignment_path),
            "split_json": str(split_path),
        },
        "sha256": {
            **hashes,
            "expected_assignment_csv": assignment_sha,
            "expected_split_json": hashlib.sha256(recomputed_split_bytes).hexdigest(),
        },
        "recomputed": {
            "input": summary,
            "outer_folds": outer_reports,
            "source_qc_reference": protocol["source_qc_reference"],
        },
        "checks": checks,
        "mismatches": {
            "assignment": assignment_mismatches(observed_assignment, recomputed_assignment),
            "report": value_mismatches(observed_report, recomputed_report, "report")[:100],
        },
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--clean-csv", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--assignment-csv", required=True)
    parser.add_argument("--split-json", required=True)
    parser.add_argument("--output", required=True, help="New independent verification JSON")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    try:
        result = verify_goodman_splits(
            args.clean_csv, args.protocol, args.assignment_csv, args.split_json,
        )
    except Exception as exc:
        result = {
            "protocol": VERIFICATION_PROTOCOL,
            "passed": False,
            "scope": SUPPORTED_OOD,
            "inputs": {
                "clean_csv": args.clean_csv,
                "protocol": args.protocol,
                "assignment_csv": args.assignment_csv,
                "split_json": args.split_json,
            },
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    write_json_exclusive(output, result)
    print(json.dumps({
        "output": str(output),
        "passed": result["passed"],
        "checks": result.get("checks", {}),
    }))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
