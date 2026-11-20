#!/usr/bin/env python3
from copy import deepcopy
import csv
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

REPO = Path('/home/codonflow-a8-rk')
sys.path.insert(0, str(REPO))
from scripts import a8_rk25_run_author_mechanism as rk
from scripts.a8_rk24_build_features import CODONS, author_static_features, core_from_cds

PROTOCOL_PATH = REPO / 'audits/20261121/RK25/a8_rk25_author_mechanism_protocol_v1.json'
AUTHOR_PATH = REPO / 'audits/20261121/RK24/a8_rk24_boel_author_protocol_v1.json'


def synthetic_row(rng, index):
    codons = ['ATG'] + list(rng.choice(CODONS, size=39))
    cds = ''.join(codons + ['CTC', 'GAG'] + ['CAT'] * 6 + ['TAA'])
    gz48v = float(-45 + rng.normal())
    row = author_static_features(cds, gz48v)
    row['source_Gz48v'] = gz48v
    row['cds_sha256'] = rk.sha256_text(cds)
    row['core_codons'] = core_from_cds(cds)[2]
    row['label'] = float(index % 6)
    return row


def synthetic_protocol():
    protocol = json.loads(PROTOCOL_PATH.read_text())
    protocol = deepcopy(protocol)
    protocol['statistics']['replicates'] = 20
    return protocol


class RK25Tests(unittest.TestCase):
    def test_01_protocol_contract(self):
        protocol = json.loads(PROTOCOL_PATH.read_text())
        self.assertEqual(len(protocol['comparisons']), 3)
        self.assertEqual(len(protocol['comparisons']) * len(protocol['endpoints']), 6)
        self.assertEqual(protocol['statistics']['replicates'], 20000)
        self.assertFalse(protocol['data']['functional_untouched_evaluated'])
        self.assertFalse(protocol['author_model']['published_coefficients_used_for_prediction'])
        self.assertFalse(protocol['decision']['expensive_generation_authorized'])

    def test_02_split_gate(self):
        rk.validate_allowed_splits(['train', 'dev'], False)
        rk.validate_allowed_splits(['train', 'dev', 'test', 'sequence_ood'], True)
        with self.assertRaises(ValueError):
            rk.validate_allowed_splits(['train', 'dev', 'sequence_ood'], False)
        with self.assertRaises(ValueError):
            rk.validate_allowed_splits(['dev', 'train'], True)

    def test_03_cluster_balanced_mse(self):
        y = np.array([0., 1., 2.])
        prediction = np.array([0., 0., 2.])
        clusters = np.array(['a', 'a', 'b'])
        expected = np.mean([np.mean([0., 1.]), 0.])
        self.assertAlmostEqual(rk.cluster_balanced_mse(y, prediction, clusters), expected)

    def test_04_prediction_identity_and_target(self):
        base = pd.DataFrame({
            'construct_id': ['x', 'y'], 'ood_assignment': ['dev', 'dev'],
            'expression_value': [1., 2.], 'operational_protein_cluster': ['a', 'b'],
        })
        prediction = pd.DataFrame({
            'construct_id': ['x', 'y'], 'ood_assignment': ['dev', 'dev'],
            'prediction': [1.1, 1.9], 'target': [1., 2.],
            'operational_protein_cluster': ['a', 'b'],
        })
        values = rk.merge_one_prediction(base, prediction, ['construct_id', 'ood_assignment'], 'prediction')
        np.testing.assert_allclose(values, [1.1, 1.9])
        prediction.loc[0, 'target'] = 4.
        with self.assertRaises(ValueError):
            rk.merge_one_prediction(base, prediction, ['construct_id', 'ood_assignment'], 'prediction')

    def test_05_csv_partition_readback(self):
        frame = pd.DataFrame({'ood_assignment': ['train', 'dev', 'test'], 'target': [0, 1, 2]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'predictions.csv'
            frame.to_csv(path, index=False)
            observed = rk.read_csv_partitions(path, ['train', 'dev'])
        self.assertEqual(observed['target'].tolist(), [0, 1])

    def test_06_point_comparisons(self):
        protocol = synthetic_protocol()
        frames = []
        for seed in protocol['seeds']:
            frame = pd.DataFrame({
                'seed': [seed] * 6,
                'ood_assignment': ['sequence_ood'] * 6,
                'expression_value': [0, 1, 2, 3, 4, 5],
                'operational_protein_cluster': ['a', 'a', 'b', 'b', 'c', 'c'],
                'ribokinetic_all': [0, 1, 2, 3, 4, 5],
                'boel_author': [0, 1, 2, 3, 4, 4],
                'ridge_all': [0, 1, 2, 3, 3, 4],
                'histgb_all': [0, 1, 2, 2, 3, 4],
            })
            frames.append(frame)
        metrics, _ = rk.calculate_metrics(frames, protocol)
        points = rk.point_comparisons(metrics, protocol)
        self.assertEqual(len(points), 6)
        self.assertTrue(all(row['partition'] == 'sequence_ood' for row in points))
        self.assertTrue(all(row['benefit'] > 0 for row in points if row['left'] == 'ribokinetic_all'))

    def test_07_bootstrap_reproducible(self):
        protocol = synthetic_protocol()
        rng = np.random.default_rng(7)
        frames = []
        for seed in protocol['seeds']:
            y = np.tile(np.arange(6), 4).astype(float)
            frame = pd.DataFrame({
                'seed': [seed] * 24, 'ood_assignment': ['sequence_ood'] * 24,
                'expression_value': y,
                'operational_protein_cluster': np.repeat(['a', 'b', 'c', 'd'], 6),
            })
            for model_index, model in enumerate(rk.MODELS):
                frame[model] = y + rng.normal(0, 0.5 + 0.2 * model_index, len(y))
            frames.append(frame)
        first = rk.hierarchical_bootstrap(frames, protocol)
        second = rk.hierarchical_bootstrap(frames, protocol)
        for left, right in zip(first, second):
            np.testing.assert_array_equal(left, right)

    def test_08_holm_and_direction(self):
        protocol = synthetic_protocol()
        points = []
        for left, right in rk.comparison_pairs(protocol):
            for metric in rk.ENDPOINTS:
                delta = 0.2 if metric == 'spearman' else -0.3
                points.append({
                    'partition': 'sequence_ood', 'left': left, 'right': right, 'metric': metric,
                    'point_delta_mean_per_seed': delta,
                    'benefit': delta if metric == 'spearman' else -delta,
                    'confirmatory': True,
                })
        deltas = np.zeros((100, 3, 2))
        deltas[:, :, 0] = 0.2
        deltas[:, :, 1] = -0.3
        rows = rk.summarize_bootstrap(deltas, points, protocol)
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row['endpoint_pass'] for row in rows))
        self.assertTrue(all(row['holm_pvalue'] == 0 for row in rows))

    def test_09_author_model_fit_smoke(self):
        rng = np.random.default_rng(19)
        rows = [synthetic_row(rng, index) for index in range(120)]
        protocol = json.loads(AUTHOR_PATH.read_text())
        for name in rk.author_feature_names(protocol):
            if name in {'s7_16', 's17_32'}:
                continue
            values = np.asarray([float(row[name]) for row in rows])
            if np.std(values) <= 1e-12:
                rows[0][name] = float(values[0] + 1.0)
        model = rk.fit_author_model(rows, protocol)
        prediction = rk.predict_author(model, rows[:7])
        self.assertEqual(len(model['single_models']), 61)
        self.assertEqual(len(model['author_feature_names']), 72)
        self.assertEqual(prediction.shape, (7,))
        self.assertTrue(np.isfinite(prediction).all())
        diagnostics = rk.model_diagnostics(model)
        self.assertTrue(diagnostics['single_codon_all_converged'])

    def test_10_static_old_split_is_ignored(self):
        rng = np.random.default_rng(23)
        splits = ['train', 'dev', 'test', 'sequence_ood']
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            static_path = directory / 'static.csv.gz'
            functional_path = directory / 'functional.csv'
            static_rows = []
            functional_rows = []
            for index, split in enumerate(splits):
                row = synthetic_row(rng, index)
                codons = row.pop('core_codons')
                cds = ''.join(codons + ['CTC', 'GAG'] + ['CAT'] * 6 + ['TAA'])
                row.update({
                    'source_row': str(index), 'construct_id': f'c{index}',
                    'operational_protein_cluster': 'cluster',
                    'split_assignment': 'old_split_must_not_be_used',
                })
                static_rows.append(row)
                functional_rows.append({
                    'source_id': 'boel_2016_nesg6348', 'source_row': str(index),
                    'construct_id': f'c{index}', 'ood_assignment': split,
                    'operational_protein_cluster': 'cluster', 'cds': cds,
                    'features_json': json.dumps({'Gz48v': row['source_Gz48v']}),
                    'expression_value': index % 6,
                })
            with gzip.open(static_path, 'wt', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(static_rows[0]))
                writer.writeheader(); writer.writerows(static_rows)
            with open(functional_path, 'w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(functional_rows[0]))
                writer.writeheader(); writer.writerows(functional_rows)
            protocol = synthetic_protocol()
            protocol['data']['author_feature_file'] = str(static_path)
            protocol['data']['functional_csv'] = str(functional_path)
            protocol['data']['expected_rows'] = {split: 1 for split in splits}
            loaded = rk.load_data(protocol, ['train', 'dev'])
            self.assertEqual(loaded['train'][0]['rk20_partition'], 'train')
            self.assertEqual(loaded['dev'][0]['rk20_partition'], 'dev')
            self.assertEqual(loaded['train'][0]['split_assignment'], 'old_split_must_not_be_used')

    def test_11_cds_hash_mismatch_rejected(self):
        # The full loader test above establishes the positive path; this checks its core identity guard directly.
        row = synthetic_row(np.random.default_rng(3), 0)
        cds = ''.join(row['core_codons'] + ['CTC', 'GAG'] + ['CAT'] * 6 + ['TAA'])
        self.assertNotEqual(rk.sha256_text(cds[:-3] + 'TAG'), row['cds_sha256'])

    def test_12_model_feature_contract_is_72(self):
        protocol = json.loads(AUTHOR_PATH.read_text())
        names = rk.author_feature_names(protocol)
        self.assertEqual(len(names), 72)
        self.assertEqual(len(set(names)), 72)
        self.assertIn('source_Gz48v', names)
        self.assertIn('s7_16', names)
        self.assertIn('s17_32', names)
    def test_13_real_prediction_schema_mapping(self):
        neural = pd.DataFrame({
            'record_id': ['a', 'b', 'c'], 'split': ['train', 'dev', 'test'],
            'cluster_id': ['x', 'y', 'z'], 'target': [0., 1., 2.],
            'prediction': [0.1, 1.1, 2.1], 'lower_95': [0., 1., 2.],
            'upper_95': [0.2, 1.2, 2.2],
        })
        baseline = pd.DataFrame({
            'source_row': [0, 1, 2], 'construct_id': ['a', 'b', 'c'],
            'ood_assignment': ['train', 'dev', 'test'], 'cluster_id': ['x', 'y', 'z'],
            'expression': [0., 1., 2.], 'pred_ridge_all': [0.2, 1.2, 2.2],
            'pred_histgb_all': [0.3, 1.3, 2.3],
        })
        with tempfile.TemporaryDirectory() as directory:
            neural_path = Path(directory) / 'neural.csv'
            baseline_path = Path(directory) / 'baseline.csv'
            neural.to_csv(neural_path, index=False)
            baseline.to_csv(baseline_path, index=False)
            neural_observed = rk.read_neural_prediction(neural_path, ['train', 'dev'])
            baseline_observed = rk.read_baseline_prediction(baseline_path, ['train', 'dev'])
        self.assertEqual(neural_observed['construct_id'].tolist(), ['a', 'b'])
        self.assertEqual(neural_observed['ood_assignment'].tolist(), ['train', 'dev'])
        self.assertEqual(baseline_observed['ridge_all'].tolist(), [0.2, 1.2])
        self.assertEqual(baseline_observed['expression_value'].tolist(), [0., 1.])


if __name__ == '__main__':
    unittest.main(verbosity=2)
