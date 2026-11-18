#!/usr/bin/env python3
import csv
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scripts.a8_rk07_proxy_features import (
    SENSE_CODONS, atomic_feature_csv, canonical_cds, compute_row,
    gc_and_cai, read_sequence_rows, translate,
)
from scripts.a8_rk07_proxy_evaluate import (
    attach_labels,
    fit_multinomial_logistic, holm_adjust, logistic_expected_score,
    prediction_metrics, tercile_index, tercile_thresholds,
)


class RK07ProxyTests(unittest.TestCase):
    def test_canonical_cds_and_translation(self):
        cds, coding = canonical_cds("atg gct taa\n")
        self.assertEqual(cds, "ATGGCTTAA")
        self.assertEqual(coding, "ATGGCT")
        self.assertEqual(translate(coding), "MA")
        with self.assertRaises(ValueError):
            canonical_cds("ATGTAATAA")
        with self.assertRaises(ValueError):
            canonical_cds("ATGGCTTTA")

    def test_gc_and_cai(self):
        gc, cai = gc_and_cai("ATGGCTGCT", {"ATG": 1.0, "GCT": 0.5})
        self.assertAlmostEqual(gc, 5 / 9)
        self.assertAlmostEqual(cai, 0.5 ** (2 / 3))

    def test_real_vienna_smoke_row(self):
        weights = {codon: 1.0 for codon in SENSE_CODONS}
        row = {
            "source_id": "synthetic", "source_row": "1", "protein_id": "p",
            "construct_id": "c", "operational_protein_cluster": "cl",
            "split_assignment": "train", "cds": "ATGGCTGCTTAA",
            "protein_sequence": "MAA", "features_json": "{}",
        }
        result = compute_row(row, weights, 18.0, 8)
        self.assertEqual(result["length_nt"], 9)
        self.assertTrue(np.isfinite(result["full_cds_mfe_kcal_mol"]))
        self.assertTrue(np.isfinite(result["mfe_5prime_48_kcal_mol"]))
        self.assertAlmostEqual(result["cai"], 1.0)

    def test_logistic_fit_and_expected_score(self):
        rng = np.random.default_rng(7)
        x = rng.normal(size=(240, 2))
        y = np.where(x[:, 0] + 0.5 * x[:, 1] > 0.7, 2, np.where(x[:, 0] < -0.7, 0, 1))
        model = fit_multinomial_logistic(x, y, np.array([0, 1, 2]), 0.001, 1000)
        prediction = logistic_expected_score(model, x)
        self.assertTrue(model["optimizer"]["success"])
        self.assertLess(model["optimizer"]["gradient_max_abs"], 1e-4)
        self.assertTrue(np.all((prediction >= 0) & (prediction <= 2)))
        self.assertGreater(np.mean(np.rint(prediction) == y), 0.9)
        self.assertAlmostEqual(float(x.mean(axis=0)[0]), float(model["train_mean"][0]))

    def test_top_k_tie_break_and_holm(self):
        y = np.array([0, 5, 0, 0], dtype=float)
        prediction = np.array([1, 1, 0, 0], dtype=float)
        source_rows = np.array([2, 1, 3, 4])
        metrics = prediction_metrics(y, prediction, source_rows, 0.5, 5)
        self.assertEqual(metrics["top10_n"], 2)
        self.assertEqual(metrics["top10_e5_rate"], 0.5)
        self.assertEqual(metrics["top10_e5_enrichment"], 2.0)
        adjusted = holm_adjust({"a": 0.01, "b": 0.04, "c": 0.03})
        self.assertAlmostEqual(adjusted["a"], 0.03)
        self.assertAlmostEqual(adjusted["b"], 0.06)
        self.assertAlmostEqual(adjusted["c"], 0.06)

    def test_train_only_terciles(self):
        rows = [{"length_nt": i, "gc_fraction": i / 100} for i in range(1, 10)]
        thresholds = tercile_thresholds(rows, ["length_nt", "gc_fraction"])
        self.assertEqual(tercile_index(3, thresholds["length_nt"]), 0)
        self.assertEqual(tercile_index(4, thresholds["length_nt"]), 1)
        self.assertEqual(tercile_index(9, thresholds["length_nt"]), 2)
        # An extreme evaluation value never enters threshold estimation.
        self.assertEqual(thresholds, tercile_thresholds(rows, ["length_nt", "gc_fraction"]))

    def _protocol(self, path):
        return {
            "source_id": "boel", "split_file": str(path),
            "allowed_splits": ["train", "dev", "test"],
            "forbidden_split": "functional_untouched",
            "expected_rows": {"train": 1, "dev": 0, "test": 0, "total": 1},
        }

    def _write_split(self, path, split="train"):
        fields = [
            "source_id", "source_row", "protein_id", "construct_id",
            "operational_protein_cluster", "split_assignment", "cds",
            "protein_sequence", "features_json", "expression_value",
        ]
        row = {
            "source_id": "boel", "source_row": "2", "protein_id": "p",
            "construct_id": "c", "operational_protein_cluster": "cl",
            "split_assignment": split, "cds": "ATGGCTTAA", "protein_sequence": "MA",
            "features_json": "{}", "expression_value": "5",
        }
        with open(path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerow(row)

    def test_feature_reader_drops_expression_label(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "split.csv"
            self._write_split(path)
            rows = read_sequence_rows(self._protocol(path), None)
            self.assertEqual(len(rows), 1)
            self.assertNotIn("expression_value", rows[0])

    def test_functional_untouched_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "split.csv"
            self._write_split(path, "functional_untouched")
            with self.assertRaises(ValueError):
                read_sequence_rows(self._protocol(path), None)

    def test_smoke_label_join_skips_unsampled_rows_but_full_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "split.csv"
            self._write_split(path)
            with open(path, newline="") as handle:
                rows = list(csv.DictReader(handle)); fields = list(rows[0])
            extra = dict(rows[0]); extra["source_row"] = "3"; extra["construct_id"] = "other"
            with open(path, "a", newline="") as handle:
                csv.DictWriter(handle, fieldnames=fields).writerow(extra)
            feature = {
                "source_row": "2", "construct_id": "c", "operational_protein_cluster": "cl",
                "split_assignment": "train", "cds_sha256": hashlib.sha256(b"ATGGCTTAA").hexdigest(),
            }
            protocol = self._protocol(path); protocol["label_field"] = "expression_value"; protocol["label_classes"] = [0, 1, 2, 3, 4, 5]
            attach_labels({"train": [dict(feature)]}, protocol, enforce_expected=False)
            with self.assertRaises(ValueError):
                attach_labels({"train": [dict(feature)]}, protocol, enforce_expected=True)

    def test_deterministic_feature_gzip(self):
        weights = {codon: 1.0 for codon in SENSE_CODONS}
        row = {
            "source_id": "synthetic", "source_row": "1", "protein_id": "p",
            "construct_id": "c", "operational_protein_cluster": "cl",
            "split_assignment": "train", "cds": "ATGGCTTAA", "protein_sequence": "MA",
            "features_json": "{}",
        }
        features = [compute_row(row, weights, 18.0, 6)]
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "a.csv.gz"; second = Path(directory) / "b.csv.gz"
            atomic_feature_csv(first, features); atomic_feature_csv(second, features)
            self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(), hashlib.sha256(second.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
