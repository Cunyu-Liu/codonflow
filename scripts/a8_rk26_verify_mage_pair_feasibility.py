#!/usr/bin/env python3
"""Independent raw-source verification for RK26; imports no production code."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

RAW_FIELDS = ["codon1", "aa1", "pos1", "codon2", "aa2", "pos2", "is_wt"]
CLEAN_FIELDS = ["source_row", "construct_id", "mutation_signature", "record_class", "codon_position", "wt_codon", "mutant_codon", "amino_acid"]
EXPECTED_FACT_FIELDS = ["source_row", "pair_id", "codon1", "aa1", "codon2", "aa2", "wt_codon1", "wt_aa1", "wt_codon2", "wt_aa2", "mutation_signature", "mutation_order", "is_synonymous", "record_class"]
EXPECTED_COUNT_FIELDS = ["pair_id", "wt_codon1", "wt_codon2", "rows", "wild_type", "single_total", "double_total", "single_synonymous", "double_synonymous", "unique_observed_codon_pairs", "coverage_rule_pass"]
GENETIC_CODE = {
    "TTT":"F","TTC":"F","TTA":"L","TTG":"L","CTT":"L","CTC":"L","CTA":"L","CTG":"L",
    "ATT":"I","ATC":"I","ATA":"I","ATG":"M","GTT":"V","GTC":"V","GTA":"V","GTG":"V",
    "TCT":"S","TCC":"S","TCA":"S","TCG":"S","CCT":"P","CCC":"P","CCA":"P","CCG":"P",
    "ACT":"T","ACC":"T","ACA":"T","ACG":"T","GCT":"A","GCC":"A","GCA":"A","GCG":"A",
    "TAT":"Y","TAC":"Y","TAA":"*","TAG":"*","CAT":"H","CAC":"H","CAA":"Q","CAG":"Q",
    "AAT":"N","AAC":"N","AAA":"K","AAG":"K","GAT":"D","GAC":"D","GAA":"E","GAG":"E",
    "TGT":"C","TGC":"C","TGA":"*","TGG":"W","CGT":"R","CGC":"R","CGA":"R","CGG":"R",
    "AGT":"S","AGC":"S","AGA":"R","AGG":"R","GGT":"G","GGC":"G","GGA":"G","GGG":"G",
}
ORDER_TO_CLASS = {0: "wild_type_control", 1: "single_codon_variant_in_pair_assay", 2: "codon_pair_variant"}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def load_projected_csv(path, allowed):
    rows = []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        reader.fieldnames = [name.strip() for name in reader.fieldnames]
        for raw in reader:
            projected = {key: raw[key].strip() for key in allowed}
            for key in ["pos1", "pos2", "is_wt", "source_row"]:
                if key in projected and projected[key] != "":
                    projected[key] = int(projected[key])
            rows.append(projected)
    return rows


def independent_facts(raw_rows):
    wild_types = {}
    for row in raw_rows:
        if row["is_wt"] == 1:
            key = f"{row['pos1']}-{row['pos2']}"
            assert key not in wild_types
            wild_types[key] = row
    facts = []
    for offset, row in enumerate(raw_rows):
        key = f"{row['pos1']}-{row['pos2']}"
        wt = wild_types[key]
        codons = (row["codon1"], row["codon2"])
        labels = (row["aa1"], row["aa2"])
        wt_codons = (wt["codon1"], wt["codon2"])
        wt_labels = (wt["aa1"], wt["aa2"])
        for codon, aa in zip(codons + wt_codons, labels + wt_labels):
            assert GENETIC_CODE[codon] == aa
        edits = []
        if codons[0] != wt_codons[0]:
            edits.append(f"{row['pos1']}:{wt_codons[0]}>{codons[0]}")
        if codons[1] != wt_codons[1]:
            edits.append(f"{row['pos2']}:{wt_codons[1]}>{codons[1]}")
        order = len(edits)
        assert (order == 0) == (row["is_wt"] == 1)
        synonymous = int(all(GENETIC_CODE[c] == GENETIC_CODE[w] for c, w in zip(codons, wt_codons)))
        facts.append({
            "source_row": offset + 2, "pair_id": key,
            "codon1": codons[0], "aa1": labels[0], "codon2": codons[1], "aa2": labels[1],
            "wt_codon1": wt_codons[0], "wt_aa1": wt_labels[0], "wt_codon2": wt_codons[1], "wt_aa2": wt_labels[1],
            "mutation_signature": ";".join(edits), "mutation_order": order,
            "is_synonymous": synonymous, "record_class": ORDER_TO_CLASS[order],
        })
    return facts


def independent_counts(facts, protocol):
    minimum = protocol["confirmatory_design_requirements"]
    counts = []
    for pair in protocol["expected_pair_contexts"]:
        rows = [fact for fact in facts if fact["pair_id"] == pair]
        singles = sum(fact["mutation_order"] == 1 and fact["is_synonymous"] for fact in rows)
        doubles = sum(fact["mutation_order"] == 2 and fact["is_synonymous"] for fact in rows)
        counts.append({
            "pair_id": pair, "wt_codon1": rows[0]["wt_codon1"], "wt_codon2": rows[0]["wt_codon2"],
            "rows": len(rows), "wild_type": sum(fact["mutation_order"] == 0 for fact in rows),
            "single_total": sum(fact["mutation_order"] == 1 for fact in rows),
            "double_total": sum(fact["mutation_order"] == 2 for fact in rows),
            "single_synonymous": singles, "double_synonymous": doubles,
            "unique_observed_codon_pairs": len({(fact["codon1"], fact["codon2"]) for fact in rows}),
            "coverage_rule_pass": int(singles >= minimum["minimum_synonymous_single_variants_per_pair"] and doubles >= minimum["minimum_synonymous_double_variants_per_pair"]),
        })
    return counts


def read_gzip_dicts(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def normalized(value):
    if isinstance(value, bool):
        return int(value)
    return value


def verify(protocol_path: Path):
    protocol = json.loads(protocol_path.read_text())
    result_path = Path(protocol["outputs"]["small_report_root"]) / "rk26_pair_feasibility_result_v1.json"
    result = json.loads(result_path.read_text())
    checks = []
    def check(name, passed, detail=None):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    check("protocol_hash", sha256(protocol_path) == result["protocol_sha256"])
    check("raw_hash", sha256(protocol["source"]["raw_csv"]) == protocol["source"]["raw_sha256"])
    check("clean_hash", sha256(protocol["source"]["clean_csv"]) == protocol["source"]["clean_sha256"])
    raw = load_projected_csv(protocol["source"]["raw_csv"], RAW_FIELDS)
    clean = load_projected_csv(protocol["source"]["clean_csv"], CLEAN_FIELDS)
    facts = independent_facts(raw)
    counts = independent_counts(facts, protocol)
    check("raw_rows_8192", len(raw) == 8192, len(raw))
    check("clean_rows_8192", len(clean) == 8192, len(clean))
    check("fact_rows_8192", len(facts) == 8192, len(facts))
    check("result_rows_8192", result["rows"] == 8192, result["rows"])
    check("two_pair_contexts", sorted({fact["pair_id"] for fact in facts}) == ["1-2", "2-3"])

    produced_facts = read_gzip_dicts(result["artifacts"]["pair_facts_csv_gz"]["path"])
    check("fact_schema_sequence_only", list(produced_facts[0]) == EXPECTED_FACT_FIELDS, list(produced_facts[0]))
    forbidden = set(protocol["prohibited_analysis_columns"])
    check("fact_schema_has_no_forbidden_columns", not forbidden.intersection(produced_facts[0]))
    check("produced_fact_row_count", len(produced_facts) == len(facts))
    mismatches = []
    for expected, observed in zip(facts, produced_facts):
        for key in EXPECTED_FACT_FIELDS:
            if str(normalized(expected[key])) != str(observed[key]):
                mismatches.append((expected["source_row"], key, expected[key], observed[key]))
    check("all_8192_fact_rows_exact", not mismatches, mismatches[:3])

    clean_mismatches = []
    for source, fact in zip(sorted(clean, key=lambda row: row["source_row"]), facts):
        expected = {
            "source_row": fact["source_row"], "codon_position": fact["pair_id"].replace("-", ";"),
            "wt_codon": f"{fact['wt_codon1']};{fact['wt_codon2']}",
            "mutant_codon": f"{fact['codon1']};{fact['codon2']}",
            "amino_acid": f"{fact['aa1']};{fact['aa2']}",
            "mutation_signature": fact["mutation_signature"], "record_class": fact["record_class"],
        }
        for key, value in expected.items():
            if str(source[key]) != str(value):
                clean_mismatches.append((fact["source_row"], key, source[key], value))
    check("all_8192_clean_rows_reconciled", not clean_mismatches, clean_mismatches[:3])

    produced_counts_path = Path(result["artifacts"]["pair_counts_csv"]["path"])
    with produced_counts_path.open(newline="", encoding="utf-8") as handle:
        produced_counts = list(csv.DictReader(handle))
    check("count_schema", list(produced_counts[0]) == EXPECTED_COUNT_FIELDS)
    count_mismatches = []
    for expected, observed in zip(counts, produced_counts):
        for key in EXPECTED_COUNT_FIELDS:
            if str(normalized(expected[key])) != str(observed[key]):
                count_mismatches.append((expected["pair_id"], key, expected[key], observed[key]))
    check("context_counts_exact", not count_mismatches, count_mismatches[:3])
    check("result_context_counts_exact", all(str(counts[i][key]) == str(result["pair_contexts"][i][key]) for i in range(2) for key in EXPECTED_COUNT_FIELDS))

    for artifact_name in ["pair_facts_csv_gz", "pair_counts_csv"]:
        artifact = result["artifacts"][artifact_name]
        path = Path(artifact["path"])
        check(f"{artifact_name}_sha256", sha256(path) == artifact["sha256"])
        check(f"{artifact_name}_bytes", path.stat().st_size == artifact["bytes"])

    classes = Counter(fact["record_class"] for fact in facts)
    check("class_counts", dict(classes) == {"codon_pair_variant": 7938, "single_codon_variant_in_pair_assay": 252, "wild_type_control": 2}, dict(classes))
    single_syn = sum(fact["mutation_order"] == 1 and fact["is_synonymous"] for fact in facts)
    double_syn = sum(fact["mutation_order"] == 2 and fact["is_synonymous"] for fact in facts)
    check("six_synonymous_singles", single_syn == 6 and result["synonymous_single_variants"] == 6, single_syn)
    check("four_synonymous_doubles", double_syn == 4 and result["synonymous_double_variants"] == 4, double_syn)
    expected_by_pair = {"1-2": (4, 3, 1), "2-3": (2, 1, 0)}
    for row in counts:
        expected = expected_by_pair[row["pair_id"]]
        observed = (row["single_synonymous"], row["double_synonymous"], row["coverage_rule_pass"])
        check(f"pair_{row['pair_id']}_synonymous_coverage", observed == expected, observed)
        check(f"pair_{row['pair_id']}_complete_64_by_64_grid", row["rows"] == 4096 and row["unique_observed_codon_pairs"] == 4096)
        check(f"pair_{row['pair_id']}_mutation_order_totals", row["wild_type"] == 1 and row["single_total"] == 126 and row["double_total"] == 3969)
    check("candidate_not_feasible", result["confirmatory_single_to_double_ood_feasible"] is False)
    check("scientific_outcome_bounded", result["scientific_outcome"] == "FIXED_PROTEIN_SINGLE_TO_DOUBLE_SYNONYMOUS_OOD_NOT_SUPPORTED_BY_SAMPLE_COVERAGE")
    for field in ["model_fits", "functional_endpoint_evaluations", "confidence_intervals_or_p_values"]:
        check(f"zero_{field}", result[field] == 0, result[field])
    for field in ["original_mage_33_construct_mechanism_test_accessed", "rk04_functional_untouched_split_accessed", "protein_ood_claim", "velocity_decay_or_spatial_coupling_claim", "rk_g1_pass", "generator_training_authorized"]:
        check(f"boundary_{field}", result[field] is False, result[field])
    check("retrospective_not_preregistered", result["analysis_role"] == "retrospective_data_adequacy_audit_not_a_preregistered_mechanism_experiment")
    check("not_power_analysis", result["not_a_power_analysis"] is True)

    report = {
        "schema": "a8-rk26-mage-pair-feasibility-independent-v1",
        "status": "PASS" if all(row["pass"] for row in checks) else "FAIL",
        "checks_passed": sum(row["pass"] for row in checks),
        "checks_total": len(checks),
        "checks": checks,
        "protocol_sha256": sha256(protocol_path),
        "production_report_sha256": sha256(result_path),
        "independent_single_synonymous": single_syn,
        "independent_double_synonymous": double_syn,
        "independent_pair_contexts": counts,
        "candidate_confirmatory_design_feasible": False,
        "model_fits": 0,
        "functional_endpoint_evaluations": 0,
        "original_mage_33_construct_mechanism_test_accessed": False,
        "rk04_functional_untouched_split_accessed": False,
        "rk_g1_pass": False,
        "generator_training_authorized": False,
    }
    output = Path(protocol["outputs"]["small_report_root"]) / "rk26_pair_feasibility_independent_v1.json"
    dump(output, report)
    print(json.dumps({"status": report["status"], "checks": f"{report['checks_passed']}/{report['checks_total']}", "output": str(output), "sha256": sha256(output)}, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.protocol)
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
