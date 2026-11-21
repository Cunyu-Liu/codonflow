#!/usr/bin/env python3
"""Independent RK29 alignment-failure verification; no production imports."""
from pathlib import Path
import argparse
import collections
import gzip
import hashlib
import json
import math
import re
import subprocess
import time
import zipfile
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_DOC = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
REL_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def column_number(reference):
    letters = re.match(r"[A-Z]+", reference).group(0)
    value = 0
    for character in letters:
        value = value * 26 + ord(character) - 64
    return value - 1


def parse_xlsx_rows(path):
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            for node in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall(MAIN + "si"):
                shared.append("".join(node.itertext()))
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet = workbook.find(MAIN + "sheets").find(MAIN + "sheet")
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(x.attrib["Target"] for x in relations.findall(REL_PKG + "Relationship") if x.attrib["Id"] == sheet.attrib[REL_DOC + "id"])
        sheet_path = target.lstrip("/") if target.startswith("/xl/") else "xl/" + target.lstrip("/")
        root = ET.fromstring(archive.read(sheet_path))
        table = []
        for row in root.iter(MAIN + "row"):
            values = {}
            for cell in row.findall(MAIN + "c"):
                kind = cell.attrib.get("t")
                if kind == "inlineStr":
                    inline = cell.find(MAIN + "is")
                    value = "".join(inline.itertext()) if inline is not None else ""
                else:
                    node = cell.find(MAIN + "v")
                    value = "" if node is None or node.text is None else node.text
                    if kind == "s" and value != "":
                        value = shared[int(value)]
                values[column_number(cell.attrib["r"])] = value
            width = max(values) + 1 if values else 0
            table.append([values.get(i, "") for i in range(width)])
    header = [str(x) for x in table[0]]
    rows = []
    for raw in table[1:]:
        padded = list(raw) + [""] * (len(header) - len(raw))
        record = dict(zip(header, padded))
        for key, value in list(record.items()):
            if key not in {"Protein_id", "Group"} and value != "":
                record[key] = float(value)
        rows.append(record)
    return header, rows


def parse_fasta(path):
    records = {}
    name = None
    chunks = []
    with gzip.open(path, "rt") as handle:
        for raw in handle:
            line = raw.strip()
            if line.startswith(">"):
                if name is not None:
                    records[name] = "".join(chunks)
                name, chunks = line[1:].split()[0], []
            elif line:
                chunks.append(line)
    if name is not None:
        records[name] = "".join(chunks)
    return records


def metadata(name):
    cohort, protein, _run, suffix = name.split("-")
    if suffix.startswith("rIDT_"):
        group = "IDT"
    elif suffix == "rGenewiz_1":
        group = "Genewiz"
    else:
        assert suffix in {"r1", "r2", "r3", "r4", "r5"}
        group = "iCodon_" + suffix[-1]
    return cohort + "_" + protein, group


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--failure-report", type=Path, required=True)
    parser.add_argument("--audit-script", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--production-log", type=Path, required=True)
    parser.add_argument("--production-root", type=Path, required=True)
    args = parser.parse_args()
    start = time.perf_counter()
    protocol = json.loads(args.protocol.read_text())
    report = json.loads(args.failure_report.read_text())
    assert report["status"] == "NOT_DISCRIMINATING_SOURCE_ALIGNMENT_OR_COVERAGE_FAILED"
    assert report["protocol_sha256"] == digest(args.protocol)
    assert report["audit_script_sha256"] == digest(args.audit_script)
    for key, spec in protocol["inputs"].items():
        assert digest(spec["path"]) == spec["sha256"] == report["inputs"][key]["sha256"]
    header, records = parse_xlsx_rows(protocol["inputs"]["outcome_xlsx"]["path"])
    assert len(records) == 955 and len(set(header)) == len(header)
    geo = pd.read_csv(protocol["inputs"]["geo_perfect_csv_gz"]["path"])
    fasta = parse_fasta(protocol["inputs"]["reference_fasta_gz"]["path"])
    names = sorted(set(geo["Name"].astype(str)))
    assert len(names) == 955
    name_metadata = {name: metadata(name) for name in names}
    time_map = protocol["outcome_access"]["geo_to_outcome_timepoint_map"]
    outcome_by_protein = collections.defaultdict(list)
    for row in records:
        outcome_by_protein[row["Protein_id"]].append(row)
    names_by_protein = collections.defaultdict(list)
    for name in names:
        names_by_protein[name_metadata[name][0]].append(name)

    candidate_sizes = []
    pair_checks = 0
    for protein, outcome_rows in sorted(outcome_by_protein.items()):
        protein_names = sorted(names_by_protein[protein])
        n = len(outcome_rows)
        assert len(protein_names) == n
        protein_geo = geo[geo["Name"].isin(protein_names)]
        assert len(protein_geo) == n * n
        for row in outcome_rows:
            row_candidates = []
            for name in protein_names:
                rows = protein_geo[protein_geo["Name"] == name]
                match = (rows["Protein_id"].to_numpy(str) == row["Protein_id"]) & (rows["Group"].to_numpy(str) == row["Group"])
                for geo_key, outcome_key in time_map.items():
                    match &= np.isclose(rows[geo_key].to_numpy(float), float(row[outcome_key]), rtol=0.0, atol=1e-12)
                assert int(match.sum()) == 1
                pair_checks += 1
                row_candidates.append(name)
            assert len(row_candidates) == n
            # Candidate count under the frozen canonical protein/design join.
            design_count = sum(name_metadata[name][1] == row["Group"] for name in row_candidates)
            candidate_sizes.append(design_count)

    factorials = []
    for (protein, group), frame in pd.DataFrame(records).groupby(["Protein_id", "Group"], sort=True):
        k = len(frame)
        fasta_count = sum(name_metadata[name] == (protein, group) for name in names)
        assert fasta_count == k
        factorials.append(math.factorial(k))
    assignments = math.prod(factorials)
    distribution = {str(key): value for key, value in sorted(collections.Counter(candidate_sizes).items())}
    assert distribution == report["candidate_size_distribution"]
    assert pair_checks == report["cartesian_pair_checks_passed"] == 10227
    assert str(assignments) == report["n_valid_global_sequence_outcome_assignments"]
    assert math.isclose(math.log10(assignments), report["log10_n_valid_global_assignments"], rel_tol=0, abs_tol=1e-12)
    assert len(factorials) == report["n_protein_design_groups"]
    assert sum(x > 1 for x in factorials) == report["n_protein_design_groups_with_multiple_assignments"]
    assert sum(size > 1 for size in candidate_sizes) == report["n_rows_with_ambiguous_name_candidates"]
    assert assignments > 1

    example = report["representative_ambiguity"]
    seqs = [fasta[name] for name in example["names"]]
    assert seqs[0] != seqs[1]
    assert sum(a != b for a, b in zip(*seqs)) == example["full_sequence_hamming_distance"]
    assert [hashlib.sha256(seq.encode()).hexdigest() for seq in seqs] == example["full_sequence_sha256"]
    production_text = args.production_log.read_text()
    assert "ambiguous or missing measurement join" in production_text
    forbidden_outputs = ["analysis_variants_950.csv", "oof_predictions.csv", "fold_assignments.csv", "seed_metrics.csv", "seed_effects.csv", "primary_inference_arrays.npz"]
    assert all(not (args.production_root / name).exists() for name in forbidden_outputs)
    result_path = args.failure_report.parent / "RK29_RESULT.json"
    assert not result_path.exists()
    subprocess.run(["git", "merge-base", "--is-ancestor", report["protocol_freeze_commit"], "HEAD"], cwd=str(args.protocol.parent.parent), check=True)

    verification = {
        "schema": "a8-rk29-independent-alignment-verification-v1",
        "status": "PASS_INDEPENDENT_ALIGNMENT_FAILURE_VERIFICATION",
        "confirmed_conclusion": report["status"],
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "failure_report": str(args.failure_report), "failure_report_sha256": digest(args.failure_report),
        "protocol_sha256": digest(args.protocol), "protocol_freeze_commit": report["protocol_freeze_commit"],
        "verifier_script_sha256": digest(Path(__file__).resolve()),
        "raw_input_hashes_reverified": True, "cartesian_pair_checks_recomputed": pair_checks,
        "candidate_size_distribution_recomputed": distribution,
        "n_valid_global_sequence_outcome_assignments_recomputed": str(assignments),
        "n_ambiguous_rows_recomputed": sum(size > 1 for size in candidate_sizes),
        "n_ambiguous_protein_design_groups_recomputed": sum(x > 1 for x in factorials),
        "representative_sequence_difference_recomputed": True,
        "production_failure_log_sha256": digest(args.production_log),
        "production_failure_log_contains_ambiguous_join_stop": True,
        "model_output_files_absent": forbidden_outputs,
        "rk29_result_json_absent": True, "model_fit_or_scientific_result_found": False,
        "row_order_or_arbitrary_assignment_used": False,
        "imports_production_or_coverage_modules": False,
        "elapsed_seconds": float(time.perf_counter() - start),
    }
    args.output.write_text(json.dumps(verification, indent=2) + "\n")
    print(json.dumps(verification, indent=2))


if __name__ == "__main__":
    main()
