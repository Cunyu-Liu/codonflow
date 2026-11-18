#!/usr/bin/env python3
"""Independent RK-02 verifier: no imports from the producer implementation."""
import argparse
import csv
import hashlib
import json
import math
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def csv_rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return reader.fieldnames, rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.audit_dir / "download_manifest.json").read_text())
    summary = json.loads((args.audit_dir / "audit_summary.json").read_text())
    checks = []
    raw_counts = {}
    clean_counts = {}

    def check(name, condition, detail):
        checks.append({"check": name, "status": "PASS" if condition else "FAIL", "detail": detail})

    for record in manifest["records"]:
        if record.get("status") == "failed":
            continue
        path = args.data_root / record["relative_path"]
        actual = sha256(path)
        check("raw_sha256:" + record["file_id"], actual == record["sha256"], actual)
        if record["file_id"] == "protein_dataset_xlsx":
            with zipfile.ZipFile(path) as archive:
                root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
                count = len(list(root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"))) - 1
            raw_counts[record["file_id"]] = count
        elif record["file_id"].startswith("data_s"):
            with path.open(encoding="utf-8-sig", newline="") as handle:
                count = sum(1 for _ in csv.DictReader(handle))
            raw_counts[record["file_id"]] = count

    clean_by_file = {}
    for key, artifact in summary["clean_artifacts"].items():
        path = args.data_root / artifact["path"]
        actual = sha256(path)
        check("clean_sha256:" + key, actual == artifact["sha256"], actual)
        fields, rows = csv_rows(path)
        clean_by_file[key] = rows
        clean_counts[key] = len(rows)
        check("clean_row_count:" + key, len(rows) == artifact["rows"], len(rows))
        required = {"source_id", "construct_id", "expression_type", "expression_value", "split_assignment"}
        check("clean_schema:" + key, required.issubset(fields), sorted(required))

    boel = clean_by_file["boel_2016_nesg6348"]
    stops = {"TAA", "TAG", "TGA"}
    boel_valid = all(
        len(row["cds"]) % 3 == 0
        and row["cds"].startswith("ATG")
        and row["cds"][-3:] in stops
        and all(row["cds"][i:i + 3] not in stops for i in range(0, len(row["cds"]) - 3, 3))
        and row["expression_value"] in {"0", "1", "2", "3", "4", "5"}
        for row in boel
    )
    check("boel_independent_translation_and_labels", boel_valid, len(boel))
    check("boel_raw_clean_rows", raw_counts["protein_dataset_xlsx"] == len(boel),
          {"raw": raw_counts["protein_dataset_xlsx"], "clean": len(boel)})
    expression = dict(sorted(Counter(row["expression_value"] for row in boel).items()))
    check("boel_expression_distribution", expression == summary["actual_download_and_clean_counts"]["boel_2016_nesg6348"]["expression_distribution"], expression)

    for file_id, multiplier in (("data_s1_single_codon_csv", 2), ("data_s2_codon_pair_csv", 1), ("data_s3_utr_csv", 1)):
        check("mage_raw_clean_multiplicity:" + file_id,
              clean_counts[file_id] == raw_counts[file_id] * multiplier,
              {"raw": raw_counts[file_id], "clean": clean_counts[file_id], "assay_multiplier": multiplier})
    single_signatures = {row["mutation_signature"] for row in clean_by_file["data_s1_single_codon_csv"] if row["mutation_signature"]}
    pair_signatures = {row["mutation_signature"] for row in clean_by_file["data_s2_codon_pair_csv"] if row["mutation_signature"]}
    check("mage_single_unique_variants", len(single_signatures) == 4599, len(single_signatures))
    check("mage_pair_unique_signatures", len(pair_signatures) == 8127, len(pair_signatures))
    check("mage_pair_nonwt_measurement_rows",
          sum(bool(row["mutation_signature"]) for row in clean_by_file["data_s2_codon_pair_csv"]) == 8190, 8190)
    combined = sum(clean_counts[key] for key in ("boel_2016_nesg6348", "data_s1_single_codon_csv", "data_s2_codon_pair_csv", "data_s3_utr_csv"))
    check("functional_long_independent_sum", clean_counts["functional_long"] == combined,
          {"sum": combined, "long": clean_counts["functional_long"]})
    all_rows = [row for rows in clean_by_file.values() for row in rows]
    check("no_random_or_preassigned_split", all(row["split_assignment"].startswith("UNASSIGNED") for row in all_rows), len(all_rows))
    check("no_kudla_synthetic_rows", not any(row["source_id"] == "kudla_2009_gfp" for row in clean_by_file["functional_long"]), 0)
    kudla = summary["actual_download_and_clean_counts"]["kudla_2009_gfp"]
    check("kudla_zero_actual_sequence_label_rows", kudla["actual_sequence_label_rows"] == 0 and kudla["clean_rows"] == 0,
          {"paper_reported": kudla["paper_reported_construct_count"], "actual": kudla["actual_sequence_label_rows"]})
    check("kudla_supporting_files_verified", len(kudla["raw_supporting_files"]) == 2 and all(
        item["status"] != "failed" and len(item["sha256"]) == 64 for item in kudla["raw_supporting_files"]),
          kudla["raw_supporting_files"])
    _, product_failures = csv_rows(args.audit_dir / "data_product_failures.csv")
    check("kudla_data_product_failure_recorded", len(product_failures) == 1 and product_failures[0]["source_id"] == "kudla_2009_gfp", len(product_failures))
    numeric = all(math.isfinite(float(row["expression_value"])) for row in all_rows)
    check("all_expression_values_finite", numeric, len(all_rows))
    report = {
        "schema_version": "a8-rk-independent-verification-v1",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "producer_module_imported": False,
        "raw_counts": raw_counts,
        "clean_counts": clean_counts,
        "checks": checks,
        "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
    }
    output = args.audit_dir / "independent_verification.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": len(checks), "raw_counts": raw_counts, "clean_counts": clean_counts}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
