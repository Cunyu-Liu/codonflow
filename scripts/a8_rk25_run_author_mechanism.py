#!/usr/bin/env python3
"""RK25 train-only Boel author comparator on the frozen RK20 partition."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

REPO = Path('/home/codonflow-a8-rk')
sys.path.insert(0, str(REPO))
from scripts.a8_rk07_proxy_evaluate import fit_multinomial_logistic, logistic_expected_score
from scripts.a8_rk20_compare_functional_multiseed import (
    fast_spearman, holm_adjust, point_metrics,
)
from scripts.a8_rk24_build_features import CODONS, core_from_cds
from scripts.a8_rk24_run_boel_author_model import (
    author_feature_names, feature_matrix, fit_binary_logistic,
)

MODELS = ['ribokinetic_all', 'boel_author', 'ridge_all', 'histgb_all']
METRIC_NAMES = ['row_mse', 'row_r2', 'row_spearman', 'row_pearson', 'cluster_balanced_mse']
ENDPOINTS = {'spearman': 'row_spearman', 'cluster_balanced_mse': 'cluster_balanced_mse'}
INPUT_HASH_KEYS = [
    'functional_csv', 'baseline_predictions', 'author_feature_file', 'author_feature_preflight',
    'author_definition_protocol', 'author_run_implementation', 'rk07_implementation',
    'rk23_implementation', 'feature_builder', 'rk20_execution', 'rk20_comparison_summary',
    'rk20_comparison_implementation',
]


def cluster_mse_table(y, prediction, clusters):
    frame = pd.DataFrame({
        'cluster': np.asarray(clusters, str),
        'squared_error': (np.asarray(prediction, float) - np.asarray(y, float)) ** 2,
    })
    grouped = frame.groupby('cluster', sort=True)['squared_error'].mean()
    return pd.DataFrame({'cluster': grouped.index.to_numpy(str), 'mse': grouped.to_numpy(float)})


def cluster_balanced_mse(y, prediction, clusters):
    return float(cluster_mse_table(y, prediction, clusters)['mse'].mean())


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
    os.replace(temporary, path)


def validate_allowed_splits(splits, allow_ood):
    expected = ['train', 'dev', 'test', 'sequence_ood'] if allow_ood else ['train', 'dev']
    if list(splits) != expected:
        raise ValueError(f'invalid split request for allow_ood={allow_ood}: {splits}')
    if not allow_ood and {'test', 'sequence_ood'} & set(splits):
        raise ValueError('test/OOD requested before frozen confirmation')


def verify_input_hashes(protocol):
    data = protocol['data']
    checks = {}
    for key in INPUT_HASH_KEYS:
        actual = sha256_file(data[key])
        expected = data[key + '_sha256']
        if actual != expected:
            raise ValueError(f'{key} hash mismatch: {actual} != {expected}')
        checks[key] = actual
    for seed, record in protocol['frozen_ribokinetic_all_predictions'].items():
        actual = sha256_file(record['path'])
        if actual != record['sha256']:
            raise ValueError(f'RiboKinetic prediction hash mismatch for seed {seed}')
        checks[f'ribokinetic_all_seed{seed}'] = actual
    return checks


def load_static_features(protocol):
    rows = {}
    import gzip
    with gzip.open(protocol['data']['author_feature_file'], 'rt', encoding='utf-8', newline='') as handle:
        for raw in csv.DictReader(handle):
            key = (str(raw['source_row']), raw['construct_id'])
            if key in rows:
                raise ValueError(f'duplicate static identity: {key}')
            rows[key] = dict(raw)
    return rows


def load_data(protocol, splits):
    validate_allowed_splits(splits, 'sequence_ood' in splits)
    static = load_static_features(protocol)
    output = {split: [] for split in splits}
    found = set()
    assignment_counts = {split: 0 for split in protocol['data']['partitions']}
    with open(protocol['data']['functional_csv'], newline='', encoding='utf-8') as handle:
        for raw in csv.DictReader(handle):
            if raw['source_id'] != protocol['data']['source_id']:
                continue
            split = raw['ood_assignment']
            if split in protocol['data']['forbidden_partitions']:
                raise ValueError('forbidden functional-untouched row encountered')
            if split not in assignment_counts:
                raise ValueError(f'unexpected partition: {split}')
            assignment_counts[split] += 1
            if split not in splits:
                continue
            key = (str(raw['source_row']), raw['construct_id'])
            if key in found or key not in static:
                raise ValueError(f'unknown or duplicate feature identity: {key}')
            row = static[key]
            cds = ''.join(raw['cds'].upper().split())
            if sha256_text(cds) != row['cds_sha256']:
                raise ValueError(f'CDS hash mismatch: {key}')
            if row['operational_protein_cluster'] != raw['operational_protein_cluster']:
                raise ValueError(f'cluster mismatch: {key}')
            source = json.loads(raw['features_json'])
            if float(source['Gz48v']) != float(row['source_Gz48v']):
                raise ValueError(f'UH mismatch: {key}')
            core_cds, core_protein, core_codons = core_from_cds(cds)
            if sha256_text(core_cds) != row['core_cds_sha256']:
                raise ValueError(f'core CDS hash mismatch: {key}')
            if sha256_text(core_protein) != row['core_protein_sha256']:
                raise ValueError(f'core protein hash mismatch: {key}')
            if len(core_cds) != int(row['core_length_nt']) or len(core_protein) != int(row['core_length_aa']):
                raise ValueError(f'core length mismatch: {key}')
            label = float(raw[protocol['data']['label_field']])
            if label not in protocol['data']['label_classes']:
                raise ValueError(f'unexpected label: {label}')
            row['label'] = label
            row['core_codons'] = core_codons
            row['rk20_partition'] = split
            output[split].append(row)
            found.add(key)
    if assignment_counts != protocol['data']['expected_rows']:
        raise ValueError(f'full assignment counts differ from protocol: {assignment_counts}')
    for split, rows in output.items():
        rows.sort(key=lambda item: int(item['source_row']))
        if len(rows) != int(protocol['data']['expected_rows'][split]):
            raise ValueError(f'{split} row count mismatch')
    return output


def fit_author_model(train_rows, author_protocol):
    labels = np.asarray([row['label'] for row in train_rows], dtype=float)
    extreme = (labels == 0) | (labels == 5)
    binary_labels = (labels[extreme] == 5).astype(float)
    cfg = author_protocol['models']['single_codon_binary']
    single_models = {}
    single_slopes = {}
    for codon in CODONS:
        values = np.asarray([float(row[f'cf_{codon}']) for row in train_rows], dtype=float)[extreme]
        model = fit_binary_logistic(
            values, binary_labels, float(cfg['l2']), int(cfg['max_iter']),
            float(cfg['gradient_max_abs_tolerance']),
        )
        raw_slope = float(model['weights'][0] / model['train_scale'][0])
        raw_intercept = float(model['bias'] - model['weights'][0] * model['train_mean'][0] / model['train_scale'][0])
        single_models[codon] = {
            'raw_slope': raw_slope, 'raw_intercept': raw_intercept, 'standardized_model': model,
        }
        single_slopes[codon] = raw_slope
    names = author_feature_names(author_protocol)
    matrix = feature_matrix(train_rows, names, single_slopes)
    cfg = author_protocol['models']['author_multiclass']
    model = fit_multinomial_logistic(
        matrix, labels, np.asarray(author_protocol['label_classes'], dtype=int),
        float(cfg['l2']), int(cfg['max_iter']),
    )
    model['feature_names'] = names
    return {
        'single_models': single_models,
        'single_slopes': single_slopes,
        'author_multiclass': model,
        'author_feature_names': names,
    }


def predict_author(model, rows):
    matrix = feature_matrix(rows, model['author_feature_names'], model['single_slopes'])
    return logistic_expected_score(model['author_multiclass'], matrix)


def base_frame(rows_by_split):
    records = []
    for split, rows in rows_by_split.items():
        for row in rows:
            records.append({
                'source_row': str(row['source_row']),
                'construct_id': row['construct_id'],
                'ood_assignment': split,
                'operational_protein_cluster': row['operational_protein_cluster'],
                'expression_value': float(row['label']),
            })
    return pd.DataFrame(records)


def read_csv_partitions(path, splits, split_column='ood_assignment'):
    assignments = pd.read_csv(path, usecols=[split_column])[split_column]
    keep = assignments.isin(splits).to_numpy()
    frame = pd.read_csv(path, skiprows=lambda index: index != 0 and not keep[index - 1])
    if len(frame) != int(np.sum(keep)):
        raise ValueError(f'partition filtering mismatch: {path}')
    return frame


def read_neural_prediction(path, splits):
    frame = read_csv_partitions(path, splits, split_column='split').rename(columns={
        'record_id': 'construct_id', 'split': 'ood_assignment',
        'cluster_id': 'operational_protein_cluster',
    })
    required = {'construct_id', 'ood_assignment', 'operational_protein_cluster', 'target', 'prediction'}
    if not required.issubset(frame.columns):
        raise ValueError(f'neural prediction schema mismatch: {path}')
    if not np.isfinite(frame[['prediction', 'lower_95', 'upper_95']].to_numpy(float)).all():
        raise ValueError(f'non-finite neural prediction or interval: {path}')
    return frame


def read_baseline_prediction(path, splits):
    frame = read_csv_partitions(path, splits).rename(columns={
        'cluster_id': 'operational_protein_cluster', 'expression': 'expression_value',
        'pred_ridge_all': 'ridge_all', 'pred_histgb_all': 'histgb_all',
    })
    required = {'source_row', 'construct_id', 'ood_assignment', 'expression_value', 'ridge_all', 'histgb_all'}
    if not required.issubset(frame.columns):
        raise ValueError(f'baseline prediction schema mismatch: {path}')
    return frame


def merge_one_prediction(base, prediction, key_columns, prediction_name):
    merged = base.merge(
        prediction, on=key_columns, how='left', validate='one_to_one', indicator=True,
        suffixes=('', '_prediction'),
    )
    if not (merged['_merge'] == 'both').all():
        raise ValueError(f'missing prediction identity: {prediction_name}')
    if 'target' in merged and not np.array_equal(
        merged['expression_value'].to_numpy(float), merged['target'].to_numpy(float),
    ):
        raise ValueError(f'target mismatch: {prediction_name}')
    if 'expression_value_prediction' in merged and not np.array_equal(
        merged['expression_value'].to_numpy(float), merged['expression_value_prediction'].to_numpy(float),
    ):
        raise ValueError(f'expression mismatch: {prediction_name}')
    if 'operational_protein_cluster_prediction' in merged and not np.array_equal(
        merged['operational_protein_cluster'].to_numpy(str),
        merged['operational_protein_cluster_prediction'].to_numpy(str),
    ):
        raise ValueError(f'cluster mismatch: {prediction_name}')
    values = merged[prediction_name].to_numpy(float)
    if not np.isfinite(values).all():
        raise ValueError(f'non-finite prediction: {prediction_name}')
    return values


def build_prediction_frames(protocol, rows_by_split, model):
    base = base_frame(rows_by_split)
    splits = list(rows_by_split)
    seed_frames = []
    for seed in protocol['seeds']:
        record = protocol['frozen_ribokinetic_all_predictions'][str(seed)]
        prediction = read_neural_prediction(record['path'], splits)
        values = merge_one_prediction(base, prediction, ['construct_id', 'ood_assignment'], 'prediction')
        frame = base.copy()
        frame['seed'] = int(seed)
        frame['ribokinetic_all'] = values
        seed_frames.append(frame)
    baseline = read_baseline_prediction(protocol['data']['baseline_predictions'], splits)
    baseline['source_row'] = baseline['source_row'].astype(str)
    keys = ['source_row', 'construct_id', 'ood_assignment']
    ridge = merge_one_prediction(base, baseline, keys, 'ridge_all')
    histgb = merge_one_prediction(base, baseline, keys, 'histgb_all')
    author = np.concatenate([predict_author(model, rows_by_split[split]) for split in splits])
    if len(author) != len(base):
        raise ValueError('author prediction length mismatch')
    for frame in seed_frames:
        frame['boel_author'] = author
        frame['ridge_all'] = ridge
        frame['histgb_all'] = histgb
    return seed_frames


def calculate_metrics(frames, protocol):
    all_metrics = {}
    metric_rows = []
    for split in protocol['data']['partitions']:
        if split not in set(frames[0]['ood_assignment']):
            continue
        partition_metrics = {}
        for frame in frames:
            subset = frame[frame['ood_assignment'] == split]
            y = subset['expression_value'].to_numpy(float)
            clusters = subset['operational_protein_cluster'].to_numpy(str)
            seed = int(frame['seed'].iloc[0])
            partition_metrics[str(seed)] = {}
            for model in MODELS:
                values = point_metrics(y, subset[model].to_numpy(float), clusters)
                partition_metrics[str(seed)][model] = values
                metric_rows.append({'partition': split, 'seed': seed, 'model': model, **values})
        mean_metrics = {}
        for model in MODELS:
            mean_metrics[model] = {
                key: float(np.mean([partition_metrics[str(seed)][model][key] for seed in protocol['seeds']]))
                for key in METRIC_NAMES
            }
            for key in ('row_spearman', 'cluster_balanced_mse'):
                mean_metrics[model]['seed_sd_' + key] = float(np.std([
                    partition_metrics[str(seed)][model][key] for seed in protocol['seeds']
                ], ddof=1))
        all_metrics[split] = {'per_seed': partition_metrics, 'mean_across_seeds': mean_metrics}
    return all_metrics, metric_rows


def comparison_pairs(protocol):
    return [(item['left'], item['right']) for item in protocol['comparisons']]


def point_comparisons(all_metrics, protocol):
    rows = []
    for split, split_metrics in all_metrics.items():
        means = split_metrics['mean_across_seeds']
        for left, right in comparison_pairs(protocol):
            for endpoint, metric_name in ENDPOINTS.items():
                delta = float(means[left][metric_name] - means[right][metric_name])
                rows.append({
                    'partition': split, 'left': left, 'right': right, 'metric': endpoint,
                    'point_delta_mean_per_seed': delta,
                    'benefit': delta if endpoint == 'spearman' else -delta,
                    'confirmatory': split == protocol['data']['primary_partition'],
                })
    return rows


def hierarchical_bootstrap(frames, protocol):
    split = protocol['data']['primary_partition']
    subset = frames[0][frames[0]['ood_assignment'] == split]
    y = subset['expression_value'].to_numpy(float)
    clusters = subset['operational_protein_cluster'].to_numpy(str)
    seeds = protocol['seeds']
    pairs = comparison_pairs(protocol)
    endpoints = list(ENDPOINTS)
    predictions = {}
    cluster_tables = {}
    for frame in frames:
        seed = int(frame['seed'].iloc[0])
        part = frame[frame['ood_assignment'] == split]
        predictions[seed] = {model: part[model].to_numpy(float) for model in MODELS}
        cluster_tables[seed] = {
            model: cluster_mse_table(y, predictions[seed][model], clusters) for model in MODELS
        }
    groups = sorted(set(clusters))
    indices = [np.flatnonzero(clusters == group) for group in groups]
    replicates = int(protocol['statistics']['replicates'])
    rng = np.random.default_rng(int(protocol['statistics']['seed']))
    deltas = np.zeros((replicates, len(pairs), len(endpoints)), dtype=float)
    cluster_draws = np.zeros((replicates, len(groups)), dtype=np.int32)
    seed_draws = np.zeros((replicates, len(seeds)), dtype=np.int64)
    for replicate in range(replicates):
        chosen_groups = rng.integers(0, len(groups), len(groups))
        chosen_seed_indices = rng.integers(0, len(seeds), len(seeds))
        chosen_seeds = [seeds[int(index)] for index in chosen_seed_indices]
        cluster_draws[replicate] = chosen_groups
        seed_draws[replicate] = chosen_seeds
        sampled_indices = [indices[index] for index in chosen_groups]
        boot_indices = np.concatenate(sampled_indices)
        boot_y = y[boot_indices]
        for left_index, (left, right) in enumerate(pairs):
            spearman_delta = []
            mse_delta = []
            for seed in chosen_seeds:
                spearman_delta.append(
                    fast_spearman(boot_y, predictions[seed][left][boot_indices])
                    - fast_spearman(boot_y, predictions[seed][right][boot_indices])
                )
                mse_delta.append(
                    float(np.mean(cluster_tables[seed][left]['mse'].to_numpy(float)[chosen_groups])
                          - np.mean(cluster_tables[seed][right]['mse'].to_numpy(float)[chosen_groups]))
                )
            deltas[replicate, left_index, 0] = np.mean(spearman_delta)
            deltas[replicate, left_index, 1] = np.mean(mse_delta)
    return deltas, cluster_draws, seed_draws


def summarize_bootstrap(deltas, point_rows, protocol):
    rows = [dict(row) for row in point_rows if row['partition'] == protocol['data']['primary_partition']]
    pairs = comparison_pairs(protocol)
    endpoints = list(ENDPOINTS)
    lookup = {(row['left'], row['right'], row['metric']): row for row in rows}
    ordered = []
    for pair_index, (left, right) in enumerate(pairs):
        for endpoint_index, endpoint in enumerate(endpoints):
            row = lookup[(left, right, endpoint)]
            samples = deltas[:, pair_index, endpoint_index]
            valid = samples[np.isfinite(samples)]
            benefit = valid if endpoint == 'spearman' else -valid
            pvalue = float(min(1.0, 2.0 * min(np.mean(benefit <= 0), np.mean(benefit >= 0))))
            row['ci95_low'] = float(np.quantile(valid, 0.025))
            row['ci95_high'] = float(np.quantile(valid, 0.975))
            row['sign_pvalue'] = pvalue
            row['bootstrap_valid'] = int(len(valid))
            row['bootstrap_requested'] = int(protocol['statistics']['replicates'])
            row['point_direction_pass'] = bool(row['benefit'] > 0)
            row['ci_direction_pass'] = bool(
                (endpoint == 'spearman' and row['ci95_low'] > 0)
                or (endpoint == 'cluster_balanced_mse' and row['ci95_high'] < 0)
            )
            ordered.append(row)
    adjusted = holm_adjust([row['sign_pvalue'] for row in ordered])
    for row, adjusted_p in zip(ordered, adjusted):
        row['holm_pvalue'] = float(adjusted_p)
        row['direction_pass'] = bool(row['point_direction_pass'] and row['ci_direction_pass'])
        row['endpoint_pass'] = bool(row['direction_pass'] and row['holm_pvalue'] < 0.05)
    return ordered


def model_diagnostics(model):
    single = [record['standardized_model']['optimizer'] for record in model['single_models'].values()]
    slopes = [record['raw_slope'] for record in model['single_models'].values()]
    multiclass = model['author_multiclass'].get('optimizer', {})
    return {
        'single_codon_models': len(single),
        'single_codon_all_converged': all(bool(item['success']) for item in single),
        'single_codon_max_gradient_abs': max(float(item['gradient_max_abs']) for item in single),
        'single_codon_max_iterations': max(int(item['iterations']) for item in single),
        'max_abs_raw_slope': max(abs(value) for value in slopes),
        'author_multiclass_optimizer': multiclass,
        'author_feature_count': len(model['author_feature_names']),
    }


def require_dev_independent(protocol, args, model_path, dev_result_path):
    if not args.frozen_ood_confirmation:
        return None
    for path in (model_path, dev_result_path, args.dev_independent_report):
        if path is None:
            raise ValueError('OOD confirmation requires model, dev result, and independent report')
    dev_result = json.loads(Path(dev_result_path).read_text())
    independent = json.loads(Path(args.dev_independent_report).read_text())
    if independent.get('status') != 'PASS':
        raise ValueError('dev independent verification has not passed')
    if independent.get('protocol_sha256') != sha256_file(args.protocol):
        raise ValueError('independent report protocol mismatch')
    if independent.get('production_result_sha256') != sha256_file(dev_result_path):
        raise ValueError('independent report does not bind the frozen dev result')
    if independent.get('model_artifact_sha256') != sha256_file(model_path):
        raise ValueError('independent report does not bind the frozen model')
    if dev_result.get('model_artifact_sha256') != sha256_file(model_path):
        raise ValueError('dev result model mismatch')
    return {'dev_result': dev_result, 'independent_report': independent}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--splits', nargs='+', required=True)
    parser.add_argument('--frozen-ood-confirmation', action='store_true')
    parser.add_argument('--model-artifact', type=Path)
    parser.add_argument('--dev-result', type=Path)
    parser.add_argument('--dev-independent-report', type=Path)
    args = parser.parse_args()
    started = time.time()
    protocol = json.loads(args.protocol.read_text())
    validate_allowed_splits(args.splits, args.frozen_ood_confirmation)
    input_hashes = verify_input_hashes(protocol)
    output_root = Path(protocol['output_root'])
    phase = 'ood' if args.frozen_ood_confirmation else 'dev'
    phase_root = output_root / phase
    phase_root.mkdir(parents=True, exist_ok=True)
    model_path = args.model_artifact or output_root / 'dev/rk25_author_model.pkl'
    dev_result_path = args.dev_result or Path(REPO / protocol['audit_root'] / 'rk25_dev_result_v1.json')
    gate = require_dev_independent(protocol, args, model_path, dev_result_path)
    rows_by_split = load_data(protocol, args.splits)
    author_protocol = json.loads(Path(protocol['data']['author_definition_protocol']).read_text())
    if args.frozen_ood_confirmation:
        with open(model_path, 'rb') as handle:
            artifact = pickle.load(handle)
        model = artifact['model']
    else:
        model = fit_author_model(rows_by_split['train'], author_protocol)
        artifact = {
            'schema': 'a8-rk25-author-model-artifact-v1',
            'protocol_sha256': sha256_file(args.protocol),
            'author_definition_protocol_sha256': input_hashes['author_definition_protocol'],
            'author_feature_file_sha256': input_hashes['author_feature_file'],
            'model': model,
        }
        with open(model_path, 'wb') as handle:
            pickle.dump(artifact, handle, protocol=pickle.HIGHEST_PROTOCOL)
    frames = build_prediction_frames(protocol, rows_by_split, model)
    prediction_path = phase_root / f'rk25_{phase}_predictions.csv.gz'
    pd.concat(frames, ignore_index=True).to_csv(prediction_path, index=False, compression='gzip')
    if args.frozen_ood_confirmation:
        previous = pd.read_csv(output_root / 'dev/rk25_dev_predictions.csv.gz')
        previous['source_row'] = previous['source_row'].astype(str)
        current = pd.concat(frames, ignore_index=True)
        current_dev = current[current['ood_assignment'].isin(['train', 'dev'])].reset_index(drop=True)
        if not current_dev.equals(previous):
            difference = 0.0
            for column in MODELS:
                difference = max(difference, float(np.max(np.abs(
                    current_dev[column].to_numpy(float) - previous[column].to_numpy(float)
                ))))
            raise ValueError(f'dev replay changed; maximum prediction difference={difference}')
    metrics, metric_rows = calculate_metrics(frames, protocol)
    points = point_comparisons(metrics, protocol)
    comparisons = []
    bootstrap_path = None
    gates = {
        'mechanism_vs_author_pass': False,
        'author_reference_pass': False,
        'strong_comparator_chain_pass': False,
    }
    if args.frozen_ood_confirmation:
        deltas, cluster_draws, seed_draws = hierarchical_bootstrap(frames, protocol)
        bootstrap_path = phase_root / 'rk25_sequence_ood_bootstrap.npz'
        np.savez_compressed(
            bootstrap_path, raw_delta=deltas, cluster_draws=cluster_draws, seed_draws=seed_draws,
            comparisons=np.asarray([f'{left}|{right}' for left, right in comparison_pairs(protocol)]),
            endpoints=np.asarray(list(ENDPOINTS)),
        )
        comparisons = summarize_bootstrap(deltas, points, protocol)
        gates['mechanism_vs_author_pass'] = all(row['endpoint_pass'] for row in comparisons[:2])
        gates['author_reference_pass'] = all(row['endpoint_pass'] for row in comparisons[2:])
        gates['strong_comparator_chain_pass'] = all(row['endpoint_pass'] for row in comparisons)
    diagnostics = model_diagnostics(model)
    if not diagnostics['single_codon_all_converged']:
        raise ValueError('single-codon convergence failure')
    result = {
        'schema': 'a8-rk25-author-mechanism-result-v1',
        'protocol_sha256': sha256_file(args.protocol),
        'implementation_sha256': sha256_file(Path(__file__).resolve()),
        'phase': phase,
        'status': 'FROZEN_SEQUENCE_OOD_EVALUATED_PENDING_INDEPENDENT_VERIFICATION' if args.frozen_ood_confirmation else 'DEV_ONLY_NO_TEST_OR_SEQUENCE_OOD_READOUT',
        'splits': args.splits,
        'rows': {split: len(rows) for split, rows in rows_by_split.items()},
        'input_sha256': input_hashes,
        'model_artifact': str(model_path),
        'model_artifact_sha256': sha256_file(model_path),
        'predictions': str(prediction_path),
        'predictions_sha256': sha256_file(prediction_path),
        'dev_replay_exact': args.frozen_ood_confirmation,
        'model_diagnostics': diagnostics,
        'metrics': metrics,
        'metric_rows': metric_rows,
        'point_comparisons': points,
        'confirmatory_comparisons': comparisons,
        'bootstrap': {
            'path': str(bootstrap_path) if bootstrap_path else None,
            'sha256': sha256_file(bootstrap_path) if bootstrap_path else None,
            'replicates': protocol['statistics']['replicates'] if args.frozen_ood_confirmation else 0,
            'seed': protocol['statistics']['seed'] if args.frozen_ood_confirmation else None,
        },
        **gates,
        'rk_g1': False,
        'functional_untouched_evaluated': False,
        'new_neural_or_generator_training': False,
        'sequence_ood_already_observed': True,
        'test_descriptive_only': True,
        'dev_independent_report_sha256': sha256_file(args.dev_independent_report) if args.dev_independent_report else None,
        'elapsed_seconds': time.time() - started,
        'limitations': protocol['prohibited_claims'],
    }
    name = 'rk25_ood_result_v1.json' if args.frozen_ood_confirmation else 'rk25_dev_result_v1.json'
    result_path = REPO / protocol['audit_root'] / name
    atomic_json(result_path, result)
    metric_path = REPO / protocol['audit_root'] / f'rk25_{phase}_metrics_v1.csv'
    pd.DataFrame(metric_rows).to_csv(metric_path, index=False)
    comparison_path = REPO / protocol['audit_root'] / f'rk25_{phase}_comparisons_v1.csv'
    pd.DataFrame(comparisons if comparisons else points).to_csv(comparison_path, index=False)
    print(json.dumps({
        'status': result['status'], 'result': str(result_path),
        'model_artifact_sha256': result['model_artifact_sha256'],
        'predictions_sha256': result['predictions_sha256'],
        **gates,
    }, indent=2))


if __name__ == '__main__':
    main()
