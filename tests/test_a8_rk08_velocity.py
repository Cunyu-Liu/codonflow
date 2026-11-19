#!/usr/bin/env python3
import gzip
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from codonflow.data.ribokinetic import VariantRecord
from codonflow.data.velocity import read_velocity_jsonl


ROOT = Path(__file__).resolve().parents[1]
PREPARE = ROOT / "scripts" / "a8_rk08_prepare_velocity.py"
TRAIN = ROOT / "scripts" / "a8_rk08_train_velocity.py"
spec = importlib.util.spec_from_file_location("velocity_train", TRAIN)
velocity_train = importlib.util.module_from_spec(spec)
spec.loader.exec_module(velocity_train)


def raw_record(record_id, dataset, index, cds, density):
    return {
        "record_id": f"{dataset}:{record_id}",
        "dataset": dataset,
        "organism": "test-host",
        "source_accession": "GSE_TEST",
        "source_commit": "094c693d4df45f4b29f5a3209b31c452a39092a5",
        "source_record_index": index,
        "source_key": record_id,
        "cds_dna": cds,
        "n_codons": len(cds) // 3,
        "density_normalized": density,
        "reference_protein_sha256": "a" * 64,
        "clean_eligible": True,
    }


class VelocityPreparationTest(unittest.TestCase):
    def test_prepare_masks_termini_and_reads_compact_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "clean.jsonl.gz"
            cds = "ATGGCTGCTGCTTAA"
            rows = [
                raw_record("000000", "Mohammad16", 0, cds, [1.0, 2.0, 3.0, 4.0, 5.0]),
                raw_record("000001", "Subtelny14", 1, "ATGGCTGCTGTTTAA", [2.0, 3.0, 4.0, 5.0, 6.0]),
            ]
            with gzip.open(source, "wt", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")
            audit = root / "audit.json"
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT / "src")
            completed = subprocess.run(
                [sys.executable, str(PREPARE), "--input-jsonl", str(source), "--output-dir", str(root / "out"), "--audit-json", str(audit)],
                check=False,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            records = read_velocity_jsonl(str(root / "out" / "velocity_records.jsonl.gz"))
            self.assertEqual(len(records), 2)
            self.assertIn(records[0].split, {"train", "dev", "test"})
            self.assertEqual(records[1].split, "study_ood")
            for record in records:
                self.assertEqual(record.codon_count, 5)
                self.assertTrue(math.isnan(record.velocity_target[0]))
                self.assertTrue(math.isnan(record.velocity_target[-1]))
            self.assertAlmostEqual(records[0].velocity_target[1], -math.log1p(2.0))
            self.assertAlmostEqual(records[0].velocity_target[3], -math.log1p(4.0))
            metadata = json.loads(audit.read_text())
            self.assertFalse(metadata["functional_ood_accessed"])
            self.assertFalse(metadata["homology_ood_claimed"])
            self.assertEqual(metadata["counts"]["retained_records"], 2)


class VelocityModelEvaluationTest(unittest.TestCase):
    def make_record(self, index, values):
        targets = [float("nan"), *values, float("nan")]
        return VariantRecord(
            record_id=f"Mohammad16:{index:06d}",
            cds="ATG" + "GCT" * len(values) + "TAA",
            split="train",
            cluster_id=f"cluster-{index}",
            host="test-host",
            velocity_target=tuple(targets),
        )

    def test_feature_matrix_and_metrics_use_only_observed_elongation_positions(self):
        records = [self.make_record(0, [0.0, 1.0, 2.0]), self.make_record(1, [1.0, 2.0, 3.0])]
        matrix, targets = velocity_train.feature_matrix(records, 20)
        self.assertEqual(matrix.shape, (6, 86))
        np.testing.assert_allclose(targets, [0.0, 1.0, 2.0, 1.0, 2.0, 3.0])
        ridge = velocity_train.fit_ridge(records, 20, 1.0)
        predictions = velocity_train.predict_ridge(ridge, records, 20)
        self.assertTrue(np.isnan(predictions[records[0].record_id][0]))
        result = velocity_train.metrics(records, predictions)
        self.assertEqual(result["n_observed_positions"], 6)
        self.assertEqual(result["n_transcripts"], 2)

    def test_paired_bootstrap_rewards_consistent_improvement(self):
        records = [self.make_record(i, [0.1 * i, 1.0 + 0.1 * i, 2.0 + 0.1 * i, 3.0 + 0.1 * i]) for i in range(12)]
        model = {record.record_id: np.asarray(record.velocity_target) for record in records}
        ridge = {record.record_id: -np.asarray(record.velocity_target) for record in records}
        rows, passed = velocity_train.paired_bootstrap(records, model, ridge, 100, 7)
        self.assertTrue(passed)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["holm_pvalue"] < 0.05 for row in rows))


if __name__ == "__main__":
    unittest.main()
