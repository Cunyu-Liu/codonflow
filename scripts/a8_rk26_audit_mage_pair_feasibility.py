#!/usr/bin/env python3
"""RK26 sequence-only MAGE pair-assay data-adequacy audit.

No outcome, RCS, MFE, model fitting, functional split, or test metric is used.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import time
from collections import Counter
from pathlib import Path

import pandas as pd

REQUIRED_RAW = ["codon1", "aa1", "pos1", "codon2", "aa2", "pos2", "is_wt"]
REQUIRED_CLEAN = ["source_row", "construct_id", "mutation_signature", "record_class", "codon_position", "wt_codon", "mutant_codon", "amino_acid"]
FACT_COLUMNS = [
    "source_row", "pair_id", "codon1", "aa1", "codon2", "aa2", "wt_codon1", "wt_aa1",
    "wt_codon2", "wt_aa2", "mutation_signature", "mutation_order", "is_synonymous", "record_class",
]
COUNT_COLUMNS = [
    "pair_id", "wt_codon1", "wt_codon2", "rows", "wild_type", "single_total", "double_total",
    "single_synonymous", "double_synonymous", "unique_observed_codon_pairs", "coverage_rule_pass",
]
CLASS_BY_ORDER = {0: "wild_type_control", 1: "single_codon_variant_in_pair_assay", 2: "codon_pair_variant"}
STANDARD_TABLE_1 = {
    "TTT":"F","TTC":"F","TTA":"L","TTG":"L","CTT":"L","CTC":"L","CTA":"L","CTG":"L",
    "ATT":"I","ATC":"I","ATA":"I","ATG":"M","GTT":"V","GTC":"V","GTA":"V","GTG":"V",
    "TCT":"S","TCC":"S","TCA":"S","TCG":"S","CCT":"P","CCC":"P","CCA":"P","CCG":"P",
    "ACT":"T","ACC":"T","ACA":"T","ACG":"T","GCT":"A","GCC":"A","GCA":"A","GCG":"A",
    "TAT":"Y","TAC":"Y","TAA":"*","TAG":"*","CAT":"H","CAC":"H","CAA":"Q","CAG":"Q",
    "AAT":"N","AAC":"N","AAA":"K","AAG":"K","GAT":"D","GAC":"D","GAA":"E","GAG":"E",
    "TGT":"C","TGC":"C","TGA":"*","TGG":"W","CGT":"R","CGC":"R","CGA":"R","CGG":"R",
    "AGT":"S","AGC":"S","AGA":"R","AGG":"R","GGT":"G","GGC":"G","GGA":"G","GGG":"G",
}


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def dump(path: str | Path, value: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def pair_id(row: dict) -> str:
    return f"{int(row['pos1'])}-{int(row['pos2'])}"


def mutation_signature(row: dict, wt1: str, wt2: str) -> str:
    edits = []
    if row["codon1"] != wt1:
        edits.append(f"{int(row['pos1'])}:{wt1}>{row['codon1']}")
    if row["codon2"] != wt2:
        edits.append(f"{int(row['pos2'])}:{wt2}>{row['codon2']}")
    return ";".join(edits)


def load_raw_sequence_columns(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, usecols=lambda name: name.strip() in REQUIRED_RAW, keep_default_na=False)
    frame.columns = [name.strip() for name in frame.columns]
    assert list(frame.columns) == REQUIRED_RAW, list(frame.columns)
    for column in ["codon1", "codon2", "aa1", "aa2"]:
        frame[column] = frame[column].astype(str).str.strip()
    for column in ["pos1", "pos2", "is_wt"]:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(int)
    return frame


def build_sequence_facts(raw: pd.DataFrame) -> list[dict]:
    assert set(raw.columns) == set(REQUIRED_RAW)
    wt_rows: dict[str, dict] = {}
    for _, row in raw.loc[raw["is_wt"].eq(1)].iterrows():
        key = pair_id(row)
        assert key not in wt_rows, f"duplicate WT for {key}"
        wt_rows[key] = row.to_dict()
    facts = []
    for index, row_series in raw.iterrows():
        row = row_series.to_dict()
        key = pair_id(row)
        assert key in wt_rows, f"missing WT for {key}"
        wt = wt_rows[key]
        codons = [row["codon1"], row["codon2"]]
        observed_aa = [row["aa1"], row["aa2"]]
        wt_codons = [wt["codon1"], wt["codon2"]]
        wt_aa = [wt["aa1"], wt["aa2"]]
        for codon, label in zip(codons + wt_codons, observed_aa + wt_aa):
            assert codon in STANDARD_TABLE_1, codon
            assert STANDARD_TABLE_1[codon] == label, (codon, label, STANDARD_TABLE_1[codon])
        order = int(codons[0] != wt_codons[0]) + int(codons[1] != wt_codons[1])
        assert (order == 0) == bool(row["is_wt"])
        synonymous = all(STANDARD_TABLE_1[c] == STANDARD_TABLE_1[w] for c, w in zip(codons, wt_codons))
        facts.append({
            "source_row": index + 2,
            "pair_id": key,
            "codon1": codons[0], "aa1": observed_aa[0], "codon2": codons[1], "aa2": observed_aa[1],
            "wt_codon1": wt_codons[0], "wt_aa1": wt_aa[0], "wt_codon2": wt_codons[1], "wt_aa2": wt_aa[1],
            "mutation_signature": mutation_signature(row, wt_codons[0], wt_codons[1]),
            "mutation_order": order,
            "is_synonymous": int(synonymous),
            "record_class": CLASS_BY_ORDER[order],
        })
    return facts


def summarize_contexts(facts: list[dict], protocol: dict) -> list[dict]:
    requirements = protocol["confirmatory_design_requirements"]
    output = []
    for key in protocol["expected_pair_contexts"]:
        rows = [row for row in facts if row["pair_id"] == key]
        assert len(rows) == protocol["expected_rows_per_pair"]
        single_syn = sum(row["mutation_order"] == 1 and row["is_synonymous"] == 1 for row in rows)
        double_syn = sum(row["mutation_order"] == 2 and row["is_synonymous"] == 1 for row in rows)
        coverage = single_syn >= requirements["minimum_synonymous_single_variants_per_pair"] and double_syn >= requirements["minimum_synonymous_double_variants_per_pair"]
        output.append({
            "pair_id": key,
            "wt_codon1": rows[0]["wt_codon1"], "wt_codon2": rows[0]["wt_codon2"],
            "rows": len(rows),
            "wild_type": sum(row["mutation_order"] == 0 for row in rows),
            "single_total": sum(row["mutation_order"] == 1 for row in rows),
            "double_total": sum(row["mutation_order"] == 2 for row in rows),
            "single_synonymous": single_syn,
            "double_synonymous": double_syn,
            "unique_observed_codon_pairs": len({(row["codon1"], row["codon2"]) for row in rows}),
            "coverage_rule_pass": int(coverage),
        })
    return output


def verify_clean_alignment(clean: pd.DataFrame, facts: list[dict]) -> None:
    assert len(clean) == len(facts)
    clean = clean.sort_values("source_row").reset_index(drop=True)
    ordered = sorted(facts, key=lambda row: row["source_row"])
    for source, fact in zip(clean.to_dict("records"), ordered):
        assert int(source["source_row"]) == fact["source_row"]
        expected = {
            "codon_position": fact["pair_id"].replace("-", ";"),
            "wt_codon": f"{fact['wt_codon1']};{fact['wt_codon2']}",
            "mutant_codon": f"{fact['codon1']};{fact['codon2']}",
            "amino_acid": f"{fact['aa1']};{fact['aa2']}",
            "mutation_signature": fact["mutation_signature"],
            "record_class": fact["record_class"],
        }
        for column, value in expected.items():
            assert str(source[column]) == str(value), (fact["source_row"], column, source[column], value)


def write_outputs(facts: list[dict], counts: list[dict], protocol: dict) -> dict:
    root = Path(protocol["outputs"]["large_artifact_root"])
    root.mkdir(parents=True, exist_ok=True)
    facts_path = root / protocol["outputs"]["pair_facts_csv_gz"]
    with facts_path.open("wb") as raw_handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as gz:
            with io.TextIOWrapper(gz, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(text, fieldnames=FACT_COLUMNS, lineterminator="\n")
                writer.writeheader()
                writer.writerows(facts)
    counts_path = root / protocol["outputs"]["pair_counts_csv"]
    with counts_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COUNT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(counts)
    return {
        "pair_facts_csv_gz": {"path": str(facts_path), "bytes": facts_path.stat().st_size, "sha256": sha256(facts_path), "rows": len(facts)},
        "pair_counts_csv": {"path": str(counts_path), "bytes": counts_path.stat().st_size, "sha256": sha256(counts_path), "rows": len(counts)},
    }


def run(protocol_path: Path) -> dict:
    started = time.perf_counter()
    protocol = json.loads(protocol_path.read_text())
    assert sha256(protocol["source"]["raw_csv"]) == protocol["source"]["raw_sha256"]
    assert sha256(protocol["source"]["clean_csv"]) == protocol["source"]["clean_sha256"]
    raw = load_raw_sequence_columns(protocol["source"]["raw_csv"])
    clean = pd.read_csv(protocol["source"]["clean_csv"], usecols=REQUIRED_CLEAN, keep_default_na=False)
    facts = build_sequence_facts(raw)
    verify_clean_alignment(clean, facts)
    counts = summarize_contexts(facts, protocol)
    artifacts = write_outputs(facts, counts, protocol)
    class_counts = Counter(row["record_class"] for row in facts)
    single_syn = sum(row["mutation_order"] == 1 and row["is_synonymous"] == 1 for row in facts)
    double_syn = sum(row["mutation_order"] == 2 and row["is_synonymous"] == 1 for row in facts)
    feasible = all(row["coverage_rule_pass"] == 1 for row in counts) and len(counts) >= protocol["confirmatory_design_requirements"]["minimum_pair_contexts"]
    result = {
        "schema": "a8-rk26-mage-pair-feasibility-result-v1",
        "protocol_sha256": sha256(protocol_path),
        "analysis_role": protocol["analysis_role"],
        "source": protocol["source"],
        "rows": len(facts),
        "pair_contexts": counts,
        "record_class_counts": dict(sorted(class_counts.items())),
        "synonymous_single_variants": single_syn,
        "synonymous_double_variants": double_syn,
        "confirmatory_single_to_double_ood_feasible": feasible,
        "scientific_outcome": "COVERAGE_FEASIBILITY_ONLY__SEPARATE_PREREGISTERED_MECHANISM_PROTOCOL_REQUIRED" if feasible else "FIXED_PROTEIN_SINGLE_TO_DOUBLE_SYNONYMOUS_OOD_NOT_SUPPORTED_BY_SAMPLE_COVERAGE",
        "decision_explanation": "Both pair contexts meet the frozen coverage rule." if feasible else "At least one pair context fails the frozen per-pair synonymous-single/double coverage rule; no confirmatory model comparison or endpoint evaluation is supported.",
        "not_a_power_analysis": True,
        "descriptive_analysis_remains_possible_but_not_confirmatory": True,
        "model_fits": 0,
        "functional_endpoint_evaluations": 0,
        "confidence_intervals_or_p_values": 0,
        "original_mage_33_construct_mechanism_test_accessed": False,
        "rk04_functional_untouched_split_accessed": False,
        "protein_ood_claim": False,
        "velocity_decay_or_spatial_coupling_claim": False,
        "rk_g1_pass": False,
        "generator_training_authorized": False,
        "artifacts": artifacts,
        "wall_seconds": time.perf_counter() - started,
    }
    output = Path(protocol["outputs"]["small_report_root"]) / "rk26_pair_feasibility_result_v1.json"
    dump(output, result)
    result["report_path"] = str(output)
    result["report_sha256"] = sha256(output)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.protocol)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
