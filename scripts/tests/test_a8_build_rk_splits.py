#!/usr/bin/env python3
import csv
import tempfile
import unittest
from pathlib import Path

from scripts.a8_rk_functional_data import LONG_FIELDS, translate_dna
from scripts.a8_build_rk_splits import (
    SPLITS,
    UNTOUCHED,
    allocate_clusters,
    build_split_rows,
    construct_signature_group,
    derive_infa_reference,
    overlap_audit,
    protein_inputs,
    read_clusters,
)


def blank_row(source="boel_2016_nesg6348", protein_id="p1", dataset="protein_dataset_xlsx"):
    row = {field: "" for field in LONG_FIELDS}
    row.update({
        "source_id": source,
        "dataset_id": dataset,
        "protein_id": protein_id,
        "construct_id": f"{source}:{protein_id}",
        "expression_type": "ordinal_total_protein_expression_score_0_5" if source.startswith("boel") else "relative_fitness_rich",
        "expression_value": "3",
        "split_assignment": "UNASSIGNED",
    })
    return row


def infa_wt_rows():
    rows = []
    codons = ["ATG"] + ["AAA"] * 72
    codons[-1] = "TGA"
    for position, codon in enumerate(codons, start=1):
        row = blank_row("kelsic_2016_mage_seq", "infA", "data_s1_single_codon_csv")
        row.update({
            "record_class": "wild_type_control",
            "codon_position": str(position),
            "mutant_codon": codon,
            "construct_id": f"infA:single:{position}:WT",
        })
        rows.append(row)
    return rows


class SplitTests(unittest.TestCase):
    def test_infa_reference_reconstruction(self):
        rows = infa_wt_rows()
        cds, protein = derive_infa_reference(rows)
        self.assertEqual(len(cds), 219)
        self.assertEqual(len(protein), 72)
        self.assertEqual(translate_dna(cds), protein + "*")
        self.assertNotIn("*", protein)

    def test_infa_reference_rejects_gap(self):
        rows = infa_wt_rows()
        del rows[10]
        with self.assertRaisesRegex(Exception, "incomplete"):
            derive_infa_reference(rows)

    def test_protein_inputs_include_derived_infa(self):
        boel = blank_row(protein_id="b1")
        boel["protein_sequence"] = "MKK"
        proteins, _, infa = protein_inputs([boel, *infa_wt_rows()])
        self.assertEqual(proteins["boel__b1"], "MKK")
        self.assertEqual(proteins["mage__infA"], infa)
        self.assertEqual(len(infa), 72)

    def test_allocation_is_deterministic_balanced_and_label_blind(self):
        reps = {f"r{i}": [f"p{i}"] for i in range(20)}
        reps["held"] = ["mage__infA"]
        counts = {f"p{i}": 1 for i in range(20)}
        counts["mage__infA"] = 100
        first = allocate_clusters(reps, counts, {"held"}, seed=17)
        second = allocate_clusters(reps, counts, {"held"}, seed=17)
        self.assertEqual(first, second)
        self.assertEqual(first["held"], UNTOUCHED)
        totals = {split: sum(counts[members[0]] for rep, members in reps.items() if first[rep] == split) for split in SPLITS}
        self.assertEqual(totals, {"train": 16, "dev": 2, "test": 2})
        changed_labels = dict(counts)
        self.assertEqual(allocate_clusters(reps, changed_labels, {"held"}, seed=17), first)

    def test_construct_signature_grouping(self):
        first = blank_row("kelsic_2016_mage_seq", "infA", "data_s1_single_codon_csv")
        first.update({"mutation_signature": "2:AAA>AAG", "construct_id": "single"})
        second = dict(first, dataset_id="data_s2_codon_pair_csv", construct_id="pair")
        self.assertEqual(construct_signature_group(first), construct_signature_group(second))
        wt1 = blank_row("kelsic_2016_mage_seq", "infA")
        wt1["construct_id"] = "wt-position-1"
        wt2 = dict(wt1, construct_id="wt-position-2")
        self.assertNotEqual(construct_signature_group(wt1), construct_signature_group(wt2))

    def test_split_rows_and_overlap_audit(self):
        rows = []
        reps = {}
        counts = {}
        for i in range(20):
            row = blank_row(protein_id=f"p{i}")
            row["protein_sequence"] = f"M{i}"
            row["cds"] = f"CDS{i}"
            rows.append(row)
            reps[f"boel__p{i}"] = [f"boel__p{i}"]
            counts[f"boel__p{i}"] = 1
        mage = infa_wt_rows()[0]
        mage["mutation_signature"] = "1:ATG>AAA"
        mage["construct_id"] = "mage-mutant"
        rows.append(mage)
        reps["mage__infA"] = ["mage__infA"]
        counts["mage__infA"] = 1
        member_to_rep = {members[0]: rep for rep, members in reps.items()}
        assignments = allocate_clusters(reps, counts, {"mage__infA"}, seed=5)
        split_rows = build_split_rows(rows, member_to_rep, assignments)
        audit = overlap_audit(split_rows)
        self.assertTrue(audit["all_pairwise_overlaps_zero"])
        self.assertEqual(split_rows[-1]["split_assignment"], UNTOUCHED)

    def test_overlap_audit_detects_construct_leakage(self):
        rows = []
        for i, split in enumerate(("train", "test")):
            row = blank_row(protein_id=f"p{i}")
            row.update({
                "split_assignment": split,
                "operational_protein_cluster": f"r{i}",
                "construct_signature_group": "shared-construct",
                "cds": f"CDS{i}",
                "protein_sequence": f"M{i}",
            })
            rows.append(row)
        audit = overlap_audit(rows)
        self.assertFalse(audit["all_pairwise_overlaps_zero"])
        self.assertEqual(audit["pairwise_overlaps"]["construct_signature_group"]["test__train"], 1)

    def test_cluster_tsv_requires_exact_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clusters.tsv"
            path.write_text("p1\tp1\np1\tp2\n")
            member, groups = read_clusters(path, {"p1", "p2"})
            self.assertEqual(member, {"p1": "p1", "p2": "p1"})
            self.assertEqual(groups, {"p1": ["p1", "p2"]})
            with self.assertRaisesRegex(Exception, "coverage mismatch"):
                read_clusters(path, {"p1", "p2", "p3"})


if __name__ == "__main__":
    unittest.main()
