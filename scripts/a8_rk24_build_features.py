#!/usr/bin/env python3
"""Build label-free Boel author-model features from frozen sequences and UH energies."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

import numpy as np


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
CODONS = sorted(c for c, aa in CODON_TABLE.items() if aa != "*")
STOPS = {"TAA", "TAG", "TGA"}
TAG_AA = "LEHHHHHH"
BASE_FIELDS = [
    "length_nt", "gc_fraction", "cai", "full_cds_mfe_per_nt",
    "mfe_5prime_48_kcal_mol", "source_Gz48v",
]


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: str | Path, value: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def translate(codons: list[str]) -> str:
    return "".join(CODON_TABLE[c] for c in codons)


def repetition_rate(protein: str) -> float:
    """Mean 1/d to the next identical amino acid; absent recurrence contributes zero."""
    next_seen: dict[str, int] = {}
    values = [0.0] * len(protein)
    for i in range(len(protein) - 1, -1, -1):
        aa = protein[i]
        if aa in next_seen:
            values[i] = 1.0 / (next_seen[aa] - i)
        next_seen[aa] = i
    return float(np.mean(values))


def core_from_cds(cds: str) -> tuple[str, str, list[str]]:
    seq = "".join(cds.upper().split())
    if not seq or len(seq) % 3 or set(seq) - set("ACGT"):
        raise ValueError("invalid full CDS")
    all_codons = [seq[i:i + 3] for i in range(0, len(seq), 3)]
    if all_codons[-1] not in STOPS:
        raise ValueError("terminal stop required")
    protein_with_tag = translate(all_codons[:-1])
    if "*" in protein_with_tag:
        raise ValueError("internal stop")
    if not protein_with_tag.endswith(TAG_AA):
        raise ValueError("C-terminal LEHHHHHH tag required")
    core_protein = protein_with_tag[:-len(TAG_AA)]
    core_codons = all_codons[:-1-len(TAG_AA)]
    if not core_codons or translate(core_codons) != core_protein:
        raise ValueError("tag removal failed")
    return "".join(core_codons), core_protein, core_codons


def author_static_features(cds: str, gz48v: float) -> dict[str, float | str | int]:
    core_cds, protein, codons = core_from_cds(cds)
    n = len(codons)
    if n < 32:
        raise ValueError(f"at least 32 core codons required, observed {n}")
    counts = Counter(codons)
    frequencies = {f"cf_{c}": counts[c] / n for c in CODONS}
    head = "".join(codons[1:6])
    if len(head) != 15:
        raise ValueError("codons 2-6 must contain 15 nt")
    gc_head = sum(b in "GC" for b in head) / 15.0
    a_h = head.count("A") / 15.0
    g_h = head.count("G") / 15.0
    u3_h = sum(c[2] == "T" for c in codons[1:6]) / 5.0
    indicator = float(gz48v < -39.0 and gc_head > 0.62)
    d_aua = float(any(codons[i] == "ATA" and codons[i + 1] == "ATA" for i in range(n - 1)))
    length_nt = 3 * n
    result: dict[str, float | str | int] = {
        "core_cds_sha256": hashlib.sha256(core_cds.encode()).hexdigest(),
        "core_length_nt": length_nt,
        "core_length_aa": len(protein),
        "core_protein_sha256": hashlib.sha256(protein.encode()).hexdigest(),
        "GC2_6": gc_head,
        "aH": a_h,
        "aH2": a_h ** 2,
        "gH": g_h,
        "gH2": g_h ** 2,
        "u3H": u3_h,
        "I_62": indicator,
        "I_65_descriptive": float(gz48v < -39.0 and gc_head > 0.65),
        "dAUA": d_aua,
        "rAA": repetition_rate(protein),
        "L_knt": length_nt / 1000.0,
        "Linv_knt": 1000.0 / length_nt,
    }
    result.update(frequencies)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split-file", required=True)
    parser.add_argument("--rk23-feature-file", required=True)
    parser.add_argument("--source-id", default="boel_2016_nesg6348")
    parser.add_argument("--output-features", required=True)
    parser.add_argument("--output-report", required=True)
    args = parser.parse_args()

    base = {}
    with gzip.open(args.rk23_feature_file, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["source_row"], row["construct_id"])
            if key in base:
                raise ValueError(f"duplicate base feature identity: {key}")
            base[key] = row

    rows = []
    forbidden = 0
    with open(args.split_file, newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            if raw["source_id"] != args.source_id:
                continue
            split = raw["split_assignment"]
            if split == "functional_untouched":
                forbidden += 1
                raise ValueError("functional_untouched access is forbidden")
            if split not in {"train", "dev", "test"}:
                raise ValueError(f"unexpected split: {split}")
            key = (raw["source_row"], raw["construct_id"])
            if key not in base:
                raise ValueError(f"missing base feature identity: {key}")
            b = base[key]
            cds = "".join(raw["cds"].upper().split())
            if hashlib.sha256(cds.encode()).hexdigest() != b["cds_sha256"]:
                raise ValueError(f"CDS hash mismatch: {key}")
            if raw["operational_protein_cluster"] != b["operational_protein_cluster"]:
                raise ValueError(f"cluster mismatch: {key}")
            source = json.loads(raw["features_json"])
            gz = float(source["Gz48v"])
            if gz != float(b["source_Gz48v"]):
                raise ValueError(f"UH energy mismatch: {key}")
            out = {
                "source_row": raw["source_row"],
                "construct_id": raw["construct_id"],
                "split_assignment": split,
                "operational_protein_cluster": raw["operational_protein_cluster"],
                "cds_sha256": b["cds_sha256"],
            }
            for name in BASE_FIELDS:
                out[name] = b[name]
            out.update(author_static_features(cds, gz))
            rows.append(out)

    rows.sort(key=lambda r: int(r["source_row"]))
    if len(rows) != 6348 or len(base) != 6348:
        raise ValueError(f"expected 6348 rows, observed rows={len(rows)} base={len(base)}")
    identities = {(r["source_row"], r["construct_id"]) for r in rows}
    if len(identities) != len(rows) or identities != set(base):
        raise ValueError("identity mismatch")
    split_counts = Counter(r["split_assignment"] for r in rows)
    if split_counts != Counter({"train": 5079, "dev": 635, "test": 634}):
        raise ValueError(f"split count mismatch: {split_counts}")

    numeric_fields = [f for f in rows[0] if f.startswith("cf_")] + [
        "GC2_6", "aH", "aH2", "gH", "gH2", "u3H", "I_62", "I_65_descriptive",
        "dAUA", "rAA", "L_knt", "Linv_knt",
    ]
    matrix = np.asarray([[float(r[f]) for f in numeric_fields] for r in rows], dtype=float)
    if not np.isfinite(matrix).all():
        raise ValueError("non-finite author features")
    frequency_sums = np.asarray([[float(r[f"cf_{c}"]) for c in CODONS] for r in rows]).sum(axis=1)
    if not np.allclose(frequency_sums, 1.0, rtol=0, atol=1e-12):
        raise ValueError("codon frequencies do not sum to one")
    for r in rows:
        if abs(float(r["aH2"]) - float(r["aH"]) ** 2) > 1e-15 or abs(float(r["gH2"]) - float(r["gH"]) ** 2) > 1e-15:
            raise ValueError("nonlinear head feature mismatch")
        if abs(float(r["L_knt"]) * 1000 - int(r["core_length_nt"])) > 1e-9:
            raise ValueError("length scaling mismatch")
        if abs(float(r["Linv_knt"]) * int(r["core_length_nt"]) - 1000) > 1e-9:
            raise ValueError("inverse length scaling mismatch")

    output = Path(args.output_features)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    tmp = output.with_name(output.name + f".tmp.{os.getpid()}")
    with open(tmp, "wb") as raw_out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_out, mtime=0) as zipped:
            import io
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
    os.replace(tmp, output)

    report = {
        "status": "PASS_LABEL_FREE_AUTHOR_FEATURES",
        "source_id": args.source_id,
        "rows": len(rows),
        "split_counts": dict(sorted(split_counts.items())),
        "clusters": len({r["operational_protein_cluster"] for r in rows}),
        "codon_count": len(CODONS),
        "codons": CODONS,
        "frequency_sum_max_abs_error": float(np.max(np.abs(frequency_sums - 1))),
        "core_length_nt": {"min": min(int(r["core_length_nt"]) for r in rows), "max": max(int(r["core_length_nt"]) for r in rows)},
        "core_length_aa": {"min": min(int(r["core_length_aa"]) for r in rows), "max": max(int(r["core_length_aa"]) for r in rows)},
        "indicator_62_ones": sum(int(r["I_62"]) for r in rows),
        "indicator_65_ones_descriptive_only": sum(int(r["I_65_descriptive"]) for r in rows),
        "dAUA_ones": sum(int(r["dAUA"]) for r in rows),
        "tag_removed": TAG_AA,
        "terminal_stop_excluded": True,
        "regional_slopes_computed_here": False,
        "label_fields_used": [],
        "test_label_values_accessed": False,
        "functional_untouched_accessed": False,
        "input_split_file": str(Path(args.split_file).resolve()),
        "input_split_sha256": sha256_file(args.split_file),
        "input_rk23_feature_file": str(Path(args.rk23_feature_file).resolve()),
        "input_rk23_feature_sha256": sha256_file(args.rk23_feature_file),
        "output_features": str(output.resolve()),
        "output_features_sha256": sha256_file(output),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "definitions": {
            "codon_frequencies": "61 sense-codon counts divided by core codon number; stop and C-terminal LEHHHHHH tag excluded",
            "head": "codons 2-6; aH/gH/GC use all 15 nt, u3H uses each third base",
            "I": "Gz48v < -39 kcal/mol and GC2_6 > 0.62; 0.65 only stored as a descriptive source-discrepancy audit",
            "dAUA": "at least one adjacent in-frame ATA-ATA di-codon",
            "rAA": "mean reciprocal distance to next occurrence of the same amino acid, absent recurrence=0",
            "L": "core CDS nucleotide length excluding stop and tag; L_knt=L/1000 and Linv_knt=1000/L",
            "s7_16_s17_32": "not static; computed downstream from train-only single-codon binary logistic slopes",
        },
    }
    atomic_json(args.output_report, report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
