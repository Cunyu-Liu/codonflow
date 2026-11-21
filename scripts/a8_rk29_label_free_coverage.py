#!/usr/bin/env python3
"""A8-RK29 label-free source, sequence, and OOD coverage audit.

This program deliberately parses only Protein_id, Group, predicted iCodon
stability, GEO Name, and reference sequences. It never extracts Decay_rate or
any of the nine abundance measurements. A passing report authorizes the frozen
production protocol to read outcomes in a separate process.
"""
from pathlib import Path
import argparse
import csv
import gzip
import hashlib
import json
import platform
import re
import xml.etree.ElementTree as ET
from collections import Counter

import numpy as np
import RNA

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
CODON_TABLE = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L", "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*", "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L", "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q", "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M", "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K", "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V", "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E", "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def column_letters(cell_reference):
    return re.match(r"[A-Z]+", cell_reference).group(0)


def xlsx_shared_strings(archive):
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in item.iter(f"{{{MAIN_NS}}}t")) for item in root.findall(f"{{{MAIN_NS}}}si")]


def xlsx_cell_value(cell, shared):
    value_type = cell.attrib.get("t")
    if value_type == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{{{MAIN_NS}}}t"))
    value = cell.find(f"{{{MAIN_NS}}}v")
    if value is None:
        return None
    text = value.text
    if value_type == "s":
        return shared[int(text)]
    return text


def read_xlsx_selected(path, selected_columns):
    """Return only requested columns; all non-requested data cells are skipped."""
    import zipfile
    with zipfile.ZipFile(path) as archive:
        shared = xlsx_shared_strings(archive)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.findall(f".//{{{MAIN_NS}}}sheet")
        assert len(sheets) == 1
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        xml_rows = root.findall(f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row")
        header_cells = {}
        for cell in xml_rows[0].findall(f"{{{MAIN_NS}}}c"):
            header_cells[column_letters(cell.attrib["r"])] = xlsx_cell_value(cell, shared)
        selected_letters = {letter for letter, name in header_cells.items() if name in selected_columns}
        assert {header_cells[x] for x in selected_letters} == set(selected_columns)
        records = []
        for row in xml_rows[1:]:
            record = {}
            for cell in row.findall(f"{{{MAIN_NS}}}c"):
                letter = column_letters(cell.attrib["r"])
                if letter not in selected_letters:
                    continue
                record[header_cells[letter]] = xlsx_cell_value(cell, shared)
            records.append(record)
        return sheets[0].attrib["name"], header_cells, records


def read_geo_metadata_only(path):
    """Parse only the first three quoted CSV fields; abundance fields are not parsed."""
    records = []
    with gzip.open(path, "rt", newline="") as handle:
        header = next(csv.reader([handle.readline()]))
        assert header[:3] == ["Name", "Protein_id", "Group"]
        for line in handle:
            fields = line.rstrip("\n\r").split(",", 3)
            assert len(fields) == 4
            metadata = [value[1:-1].replace('""', '"') if len(value) >= 2 and value[0] == '"' and value[-1] == '"' else value for value in fields[:3]]
            records.append({"Name": metadata[0], "Protein_id": metadata[1], "Group": metadata[2]})
    return header, records


def read_fasta_gz(path):
    records = {}
    name = None
    chunks = []
    with gzip.open(path, "rt") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith(">"):
                if name is not None:
                    assert name not in records
                    records[name] = "".join(chunks).upper()
                name, chunks = line[1:].split()[0], []
            elif line:
                assert name is not None
                chunks.append(line)
    if name is not None:
        assert name not in records
        records[name] = "".join(chunks).upper()
    return records


def canonical_metadata(name):
    """Recover Protein_id and design Group from the reference-FASTA grammar."""
    parts = name.split("-")
    assert len(parts) == 4
    cohort, protein, _run, suffix = parts
    if suffix.startswith("rIDT_"):
        group = "IDT"
    elif suffix == "rGenewiz_1":
        group = "Genewiz"
    elif suffix in {"r1", "r2", "r3", "r4", "r5"}:
        group = "iCodon_" + suffix[1:]
    else:
        raise ValueError(f"unrecognized reference name: {name}")
    return f"{cohort}_{protein}", group


def translate(sequence):
    assert len(sequence) % 3 == 0
    return "".join(CODON_TABLE[sequence[i:i + 3]] for i in range(0, len(sequence), 3))


def find(parent, index):
    while parent[index] != index:
        parent[index] = parent[parent[index]]
        index = parent[index]
    return index


def union(parent, left, right):
    left, right = find(parent, left), find(parent, right)
    if left != right:
        parent[max(left, right)] = min(left, right)


def make_cluster_folds(cluster_labels, seed, n_folds=5):
    labels = np.asarray(cluster_labels, dtype=int)
    ids = np.array(sorted(np.unique(labels).tolist()), dtype=int)
    rng = np.random.default_rng(seed)
    shuffled = ids[rng.permutation(len(ids))].tolist()
    sizes = {int(c): int(np.sum(labels == c)) for c in ids}
    ordered = sorted(shuffled, key=lambda c: -sizes[int(c)])
    loads = np.zeros(n_folds, dtype=int)
    assignment = {}
    for cluster in ordered:
        candidates = np.flatnonzero(loads == loads.min())
        fold = int(rng.choice(candidates))
        assignment[int(cluster)] = fold
        loads[fold] += sizes[int(cluster)]
    folds = np.array([assignment[int(c)] for c in labels], dtype=int)
    return folds, loads.tolist()


def mfe(sequence):
    model = RNA.md(temperature=28.0)
    compound = RNA.fold_compound(sequence.replace("T", "U"), model)
    _, value = compound.mfe()
    return float(value)


def structure_features(variable, full, constant5):
    return {
        "mfe_variable_297nt_28C": mfe(variable),
        "mfe_full_339nt_28C": mfe(full),
        "mfe_variable_5prime48nt_28C": mfe(variable[:48]),
        "mfe_constant5prime33nt_plus_variable48nt_28C": mfe(constant5 + variable[:48]),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    assert protocol["schema"] == "a8-rk29-icodon-decay-cluster-ood-protocol-v1"
    assert protocol["frozen_before_outcome_access"] is True
    input_hashes = {}
    for key, spec in protocol["inputs"].items():
        input_hashes[key] = {"path": spec["path"], "sha256": sha256(spec["path"]), "bytes": Path(spec["path"]).stat().st_size}
        assert input_hashes[key]["sha256"] == spec["sha256"]

    allowed = protocol["label_free_coverage"]["authorized_columns"]["outcome_xlsx"]
    sheet, outcome_header, outcome = read_xlsx_selected(protocol["inputs"]["outcome_xlsx"]["path"], allowed)
    assert sheet == protocol["inputs"]["outcome_xlsx"]["sheet_name"]
    geo_header, geo = read_geo_metadata_only(protocol["inputs"]["geo_perfect_csv_gz"]["path"])
    fasta = read_fasta_gz(protocol["inputs"]["reference_fasta_gz"]["path"])
    assert len(outcome) == protocol["inputs"]["outcome_xlsx"]["expected_rows"]
    assert len(geo) == protocol["inputs"]["geo_perfect_csv_gz"]["expected_rows"]
    geo_names = sorted({r["Name"] for r in geo})
    assert len(geo_names) == protocol["inputs"]["geo_perfect_csv_gz"]["expected_unique_names"]
    assert len(fasta) == protocol["inputs"]["reference_fasta_gz"]["expected_records"]

    constant5 = protocol["sequence_definition"]["constant_5prime"]
    constant3 = protocol["sequence_definition"]["constant_3prime"]
    variable_length = protocol["sequence_definition"]["variable_length_nt"]
    full_length = protocol["sequence_definition"]["full_length_nt"]
    outcome_pair_multiset = Counter((r["Protein_id"], r["Group"]) for r in outcome)
    geo_pair_multiset = Counter(canonical_metadata(name) for name in geo_names)
    assert outcome_pair_multiset == geo_pair_multiset, "label-free canonical Protein_id-by-Group multisets differ"
    baseline_values = np.array([float(r["Predicted_mRNA_stability"]) for r in outcome], dtype=float)
    assert np.isfinite(baseline_values).all()
    rows = []
    for name in geo_names:
        protein_id, design_group = canonical_metadata(name)
        assert name in fasta
        full = fasta[name]
        assert len(full) == full_length and set(full) <= set("ACGT")
        assert full.startswith(constant5) and full.endswith(constant3)
        variable = full[len(constant5):len(constant5) + variable_length]
        assert len(variable) == variable_length and "*" not in translate(variable)
        rows.append({
            "Name": name, "Protein_id": protein_id, "Group": design_group,
            "variable": variable, "translation": translate(variable),
            "full_sha256": hashlib.sha256(full.encode()).hexdigest(),
        })
    assert len({r["Name"] for r in rows}) == len(rows)
    assert len({r["full_sha256"] for r in rows}) == len(rows), "unexpected exact full-CDS duplicates before outcome review"
    protein_translations = {}
    for row in rows:
        protein_translations.setdefault(row["Protein_id"], set()).add(row["translation"])
    assert all(len(x) == 1 for x in protein_translations.values())
    source_variant_count = len(rows)
    source_protein_counts = Counter(r["Protein_id"] for r in rows)
    minimum_per_protein = protocol["label_free_coverage"]["power_gate"]["min_variants_per_protein"]
    selected_proteins = {p for p, count in source_protein_counts.items() if count >= minimum_per_protein}
    excluded_proteins = {p: count for p, count in sorted(source_protein_counts.items()) if p not in selected_proteins}
    rows = [r for r in rows if r["Protein_id"] in selected_proteins]
    assert len(rows) == protocol["label_free_coverage"]["expected_selected_variants"]
    assert len(selected_proteins) == protocol["label_free_coverage"]["expected_selected_proteins"]

    parent = list(range(len(rows)))
    by_protein = {}
    by_sequence = {}
    for index, row in enumerate(rows):
        by_protein.setdefault(row["Protein_id"], []).append(index)
        by_sequence.setdefault(row["variable"], []).append(index)
    for indices in list(by_protein.values()) + list(by_sequence.values()):
        for index in indices[1:]:
            union(parent, indices[0], index)

    encoded = np.array([list(r["variable"].encode()) for r in rows], dtype=np.uint8)
    protein_array = np.array([r["Protein_id"] for r in rows])
    cross_protein_pairs = 0
    max_cross_protein_identity = 0.0
    cross_protein_examples = []
    for i in range(len(rows) - 1):
        identities = np.mean(encoded[i + 1:] == encoded[i], axis=1)
        different_protein = protein_array[i + 1:] != protein_array[i]
        if different_protein.any():
            max_cross_protein_identity = max(max_cross_protein_identity, float(identities[different_protein].max()))
        for offset in np.flatnonzero((identities >= 0.90) & different_protein):
            j = i + 1 + int(offset)
            identity = float(identities[offset])
            cross_protein_pairs += 1
            if len(cross_protein_examples) < 20:
                cross_protein_examples.append([rows[i]["Name"], rows[j]["Name"], identity])
            union(parent, i, j)
    roots = [find(parent, i) for i in range(len(rows))]
    root_names = {}
    for index, root in enumerate(roots):
        root_names.setdefault(root, []).append(rows[index]["Protein_id"])
    ordered_roots = sorted(root_names, key=lambda root: (min(root_names[root]), root))
    root_to_group = {root: i + 1 for i, root in enumerate(ordered_roots)}
    groups = np.array([root_to_group[root] for root in roots], dtype=int)
    folds, fold_sizes = make_cluster_folds(groups, protocol["outer_evaluation"]["primary_seed"], protocol["outer_evaluation"]["n_folds"])
    for fold in range(protocol["outer_evaluation"]["n_folds"]):
        assert set(groups[folds == fold]).isdisjoint(set(groups[folds != fold]))

    protein_counts = {p: len(v) for p, v in by_protein.items()}
    design_counts = {g: sum(r["Group"] == g for r in rows) for g in sorted({r["Group"] for r in rows})}
    gate = protocol["label_free_coverage"]["power_gate"]
    gate_checks = {
        "variants": len(rows) >= gate["min_variants"],
        "evaluation_groups": len(set(groups)) >= gate["min_evaluation_groups"],
        "proteins": len(protein_counts) >= gate["min_proteins"],
        "median_variants_per_protein": float(np.median(list(protein_counts.values()))) >= gate["min_median_variants_per_protein"],
        "min_variants_per_protein": min(protein_counts.values()) >= gate["min_variants_per_protein"],
        "required_design_groups": all(design_counts.get(g, 0) > 0 for g in gate["required_design_groups"]),
    }
    assert all(gate_checks.values()), gate_checks

    coverage_cfg = protocol["label_free_coverage"]
    manifest_path = Path(coverage_cfg["manifest_path"])
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", newline="") as handle:
        fields = ["Name", "Protein_id", "Group", "full_cds_sha256", "translation_sha256", "evaluation_group_id", "primary_seed_fold", "gc", "gc3"]
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for index, row in enumerate(rows):
            variable = row["variable"]
            codons = [variable[i:i + 3] for i in range(0, len(variable), 3)]
            writer.writerow({
                "Name": row["Name"], "Protein_id": row["Protein_id"], "Group": row["Group"],
                "full_cds_sha256": row["full_sha256"], "translation_sha256": hashlib.sha256(row["translation"].encode()).hexdigest(),
                "evaluation_group_id": int(groups[index]), "primary_seed_fold": int(folds[index]),
                "gc": format((variable.count("G") + variable.count("C")) / len(variable), ".17g"),
                "gc3": format(sum(c[2] in "GC" for c in codons) / len(codons), ".17g"),
            })
    structure_path = manifest_path.with_name("label_free_structure_features.tsv")
    with structure_path.open("w", newline="") as handle:
        structure_fields = list(protocol["features"]["structure_addition"])
        writer = csv.DictWriter(handle, fieldnames=["Name"] + structure_fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            full = fasta[row["Name"]]
            values = structure_features(row["variable"], full, constant5)
            assert np.isfinite(list(values.values())).all()
            writer.writerow({"Name": row["Name"], **{k: format(v, ".17g") for k, v in values.items()}})

    report = {
        "schema": "a8-rk29-label-free-coverage-v1",
        "status": "PASS_LABEL_FREE_COVERAGE_AUDIT_FEASIBLE",
        "protocol": str(args.protocol), "protocol_sha256": sha256(args.protocol),
        "coverage_feasible": True, "model_fit_authorized": True,
        "outcome_values_accessed": False, "abundance_values_accessed": False,
        "expression_or_model_fit_performed": False, "forbidden_columns_accessed": [],
        "parsed_outcome_sheet_columns": allowed,
        "outcome_sheet_all_headers": list(outcome_header.values()),
        "geo_all_headers": geo_header,
        "geo_parsed_columns": ["Name", "Protein_id", "Group"],
        "inputs": input_hashes,
        "selected_coverage": {
            "n_variants": len(rows), "n_source_variants": source_variant_count,
            "n_excluded_variants": source_variant_count - len(rows), "excluded_low_coverage_proteins": excluded_proteins,
            "n_geo_source_rows": len(geo), "n_geo_unique_names": len(geo_names),
            "geo_auxiliary_metadata_used": False, "canonical_name_metadata_match": True,
            "n_reference_records": len(fasta), "n_proteins": len(protein_counts),
            "n_evaluation_groups": len(set(groups)), "design_group_counts": design_counts,
            "protein_variant_count_min": min(protein_counts.values()),
            "protein_variant_count_median": float(np.median(list(protein_counts.values()))),
            "protein_variant_count_max": max(protein_counts.values()),
            "variable_length_nt": variable_length, "full_length_nt": full_length,
            "synonymy_pass": True, "constant_context_pass": True,
            "protein_group_multiset_match": True, "baseline_finite_count": int(np.isfinite(baseline_values).sum()),
            "exact_full_cds_duplicate_count": 0,
            "cross_protein_identity_threshold": 0.90,
            "cross_protein_pairs_at_or_above_threshold": cross_protein_pairs,
            "max_cross_protein_identity_observed": max_cross_protein_identity,
            "cross_protein_pair_examples": cross_protein_examples,
            "primary_seed_fold_sizes": fold_sizes,
            "power_gate_checks": gate_checks,
        },
        "facts_tsv": str(manifest_path), "facts_sha256": sha256(manifest_path),
        "structure_features_tsv": str(structure_path), "structure_features_sha256": sha256(structure_path),
        "structure_coverage": {"engine": "ViennaRNA", "version": RNA.__version__, "temperature_C": 28.0, "n_rows": len(rows), "all_finite": True},
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "ViennaRNA": RNA.__version__},
        "next_step": "Commit this protocol, audit code, and report before running the separate outcome-authorized production process.",
    }
    write_json(coverage_cfg["report_path"], report)
    print(json.dumps({"status": report["status"], "selected_coverage": report["selected_coverage"], "report": coverage_cfg["report_path"], "facts_sha256": report["facts_sha256"], "structure_features_sha256": report["structure_features_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
