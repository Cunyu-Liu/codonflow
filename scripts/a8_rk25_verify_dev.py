#!/usr/bin/env python3
"""Independent RK25 dev refit and metric verification; no production fitting imports."""
from pathlib import Path
import argparse
import hashlib
import json
import pickle

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, log_softmax
from scipy.stats import pearsonr, spearmanr

CODON_TABLE = {
    'TTT':'F','TTC':'F','TTA':'L','TTG':'L','TCT':'S','TCC':'S','TCA':'S','TCG':'S',
    'TAT':'Y','TAC':'Y','TAA':'*','TAG':'*','TGT':'C','TGC':'C','TGA':'*','TGG':'W',
    'CTT':'L','CTC':'L','CTA':'L','CTG':'L','CCT':'P','CCC':'P','CCA':'P','CCG':'P',
    'CAT':'H','CAC':'H','CAA':'Q','CAG':'Q','CGT':'R','CGC':'R','CGA':'R','CGG':'R',
    'ATT':'I','ATC':'I','ATA':'I','ATG':'M','ACT':'T','ACC':'T','ACA':'T','ACG':'T',
    'AAT':'N','AAC':'N','AAA':'K','AAG':'K','AGT':'S','AGC':'S','AGA':'R','AGG':'R',
    'GTT':'V','GTC':'V','GTA':'V','GTG':'V','GCT':'A','GCC':'A','GCA':'A','GCG':'A',
    'GAT':'D','GAC':'D','GAA':'E','GAG':'E','GGT':'G','GGC':'G','GGA':'G','GGG':'G',
}
CODONS = sorted(c for c, aa in CODON_TABLE.items() if aa != '*')
MODELS = ['ribokinetic_all', 'boel_author', 'ridge_all', 'histgb_all']


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def text_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def load_frames(protocol):
    static = pd.read_csv(protocol['data']['author_feature_file'])
    static['source_row'] = static['source_row'].astype(str)
    columns = ['source_row','construct_id','source_id','ood_assignment','operational_protein_cluster',
               'expression_value','cds','features_json']
    source = pd.read_csv(protocol['data']['functional_csv'], usecols=columns)
    source = source[source['source_id'] == protocol['data']['source_id']].copy()
    source['source_row'] = source['source_row'].astype(str)
    if set(source['ood_assignment']) & {'functional_untouched', 'untouched'}:
        raise ValueError('forbidden untouched partition')
    counts = source['ood_assignment'].value_counts().to_dict()
    if counts != protocol['data']['expected_rows']:
        raise ValueError(f'assignment counts mismatch: {counts}')
    frames = {}
    for split in ['train', 'dev']:
        part = source[source['ood_assignment'] == split].copy()
        part['_source_row_int'] = part['source_row'].astype(int)
        part = part.sort_values('_source_row_int')
        merged = part.merge(static, on=['source_row','construct_id'], how='left', validate='one_to_one',
                            suffixes=('','_static'), indicator=True)
        if not (merged['_merge'] == 'both').all():
            raise ValueError(f'missing static features: {split}')
        core_codons = []
        for row in merged.itertuples():
            cds = ''.join(row.cds.upper().split())
            if text_hash(cds) != row.cds_sha256:
                raise ValueError('CDS hash mismatch')
            if row.operational_protein_cluster != row.operational_protein_cluster_static:
                raise ValueError('cluster mismatch')
            energy = float(json.loads(row.features_json)['Gz48v'])
            if energy != float(row.source_Gz48v):
                raise ValueError('UH mismatch')
            codons = [cds[i:i+3] for i in range(0, len(cds), 3)]
            if codons[-1] not in {'TAA','TAG','TGA'} or len(codons) < 41:
                raise ValueError('invalid CDS')
            core = codons[:-9]
            core_cds = ''.join(core)
            protein = ''.join(CODON_TABLE[c] for c in core)
            if text_hash(core_cds) != row.core_cds_sha256 or text_hash(protein) != row.core_protein_sha256:
                raise ValueError('core identity mismatch')
            if len(core_cds) != int(row.core_length_nt) or len(protein) != int(row.core_length_aa):
                raise ValueError('core length mismatch')
            core_codons.append(core)
        merged['core_codons'] = core_codons
        if len(merged) != protocol['data']['expected_rows'][split]:
            raise ValueError('row count mismatch')
        frames[split] = merged.reset_index(drop=True)
    return frames


def feature_names(author_protocol):
    comparison = author_protocol['comparison']
    names = list(comparison['author_noncodon_features'])
    names += [f'cf_{codon}' for codon in CODONS if codon != 'ATG']
    names += list(comparison['author_regional_features'])
    if len(names) != 72 or len(set(names)) != 72:
        raise ValueError('feature contract')
    return names


def matrix(frame, names, slopes):
    columns = []
    for name in names:
        if name in {'s7_16','s17_32'}:
            start, end = (6,16) if name == 's7_16' else (16,32)
            values = [np.mean([slopes[c] for c in codons[start:end]]) for codons in frame['core_codons']]
            columns.append(np.asarray(values, float))
        else:
            columns.append(frame[name].to_numpy(float))
    result = np.column_stack(columns)
    if not np.isfinite(result).all():
        raise ValueError('non-finite feature matrix')
    return result


def binary_fit(x, y, l2, max_iter, tolerance):
    x = np.asarray(x, float).reshape(-1, 1)
    y = np.asarray(y, float)
    mean, scale = x.mean(axis=0), x.std(axis=0)
    z = (x - mean) / scale
    n = len(y)
    def objective(theta):
        w, b = theta[:1], theta[1]
        logits = z[:,0] * w[0] + b
        loss = np.mean(np.logaddexp(0, logits) - y * logits) + 0.5 * l2 * w @ w
        residual = expit(logits) - y
        gradient = np.array([np.sum(z[:,0] * residual) / n + l2 * w[0], np.sum(residual) / n])
        return float(loss), gradient
    result = minimize(objective, np.zeros(2), jac=True, method='L-BFGS-B',
                      options={'maxiter':int(max_iter),'ftol':1e-13,'gtol':1e-9,'maxls':50})
    _, gradient = objective(result.x)
    if not result.success or np.max(np.abs(gradient)) > tolerance:
        raise RuntimeError('binary convergence')
    return {
        'mean':mean, 'scale':scale, 'weight':result.x[:1], 'bias':float(result.x[1]),
        'success':bool(result.success), 'gradient':float(np.max(np.abs(gradient))),
        'iterations':int(result.nit),
    }


def multinomial_fit(x, y, classes, l2, max_iter):
    mean, scale = x.mean(axis=0), x.std(axis=0)
    if np.any(scale <= 1e-12):
        raise ValueError('zero variance')
    z = (x - mean) / scale
    class_index = {int(label):i for i,label in enumerate(classes)}
    targets = np.array([class_index[int(label)] for label in y])
    one_hot = np.eye(len(classes))[targets]
    n, d = z.shape
    k = len(classes)
    def objective(theta):
        weights = theta[:k*d].reshape(k,d)
        bias = theta[k*d:]
        logits = z @ weights.T + bias
        log_probability = log_softmax(logits, axis=1)
        probability = np.exp(log_probability)
        loss = -np.mean(log_probability[np.arange(n), targets]) + 0.5 * l2 * np.sum(weights**2)
        residual = (probability - one_hot) / n
        grad_w = residual.T @ z + l2 * weights
        grad_b = residual.sum(axis=0)
        return float(loss), np.concatenate([grad_w.ravel(), grad_b])
    result = minimize(objective, np.zeros(k*d+k), jac=True, method='L-BFGS-B',
                      options={'maxiter':int(max_iter),'ftol':1e-12,'gtol':1e-7,'maxls':50})
    _, gradient = objective(result.x)
    if not result.success or np.max(np.abs(gradient)) > 1e-4:
        raise RuntimeError('multinomial convergence')
    return {
        'mean':mean, 'scale':scale, 'weights':result.x[:k*d].reshape(k,d), 'bias':result.x[k*d:],
        'classes':np.asarray(classes, float), 'success':bool(result.success),
        'gradient':float(np.max(np.abs(gradient))), 'iterations':int(result.nit),
        'objective':float(result.fun),
    }


def expected_score(model, x):
    z = (x - model['mean']) / model['scale']
    logits = z @ model['weights'].T + model['bias']
    return np.exp(log_softmax(logits, axis=1)) @ model['classes']


def independent_fit(train, author_protocol):
    y = train['expression_value'].to_numpy(float)
    extreme = (y == 0) | (y == 5)
    binary_y = (y[extreme] == 5).astype(float)
    cfg = author_protocol['models']['single_codon_binary']
    slopes = {}
    diagnostics = []
    for codon in CODONS:
        x = train[f'cf_{codon}'].to_numpy(float)[extreme]
        fitted = binary_fit(x, binary_y, cfg['l2'], cfg['max_iter'], cfg['gradient_max_abs_tolerance'])
        slopes[codon] = float(fitted['weight'][0] / fitted['scale'][0])
        diagnostics.append(fitted)
    names = feature_names(author_protocol)
    train_matrix = matrix(train, names, slopes)
    cfg = author_protocol['models']['author_multiclass']
    multi = multinomial_fit(train_matrix, y, author_protocol['label_classes'], cfg['l2'], cfg['max_iter'])
    return {'slopes':slopes, 'names':names, 'multi':multi, 'single_diagnostics':diagnostics}


def base_frame(frames):
    output = []
    for split in ['train','dev']:
        frame = frames[split]
        output.append(pd.DataFrame({
            'source_row':frame['source_row'].astype(str), 'construct_id':frame['construct_id'],
            'ood_assignment':split, 'operational_protein_cluster':frame['operational_protein_cluster'],
            'expression_value':frame['expression_value'].to_numpy(float),
        }))
    return pd.concat(output, ignore_index=True)


def align_frozen(protocol, base):
    output = {seed:{'ribokinetic_all':None} for seed in protocol['seeds']}
    for seed in protocol['seeds']:
        record = protocol['frozen_ribokinetic_all_predictions'][str(seed)]
        raw = pd.read_csv(record['path']).rename(columns={
            'record_id':'construct_id','split':'ood_assignment','cluster_id':'cluster','target':'prediction_target',
        })
        raw = raw[raw['ood_assignment'].isin(['train','dev'])]
        aligned = base.merge(raw[['construct_id','ood_assignment','cluster','prediction_target','prediction']],
                             on=['construct_id','ood_assignment'], how='left', validate='one_to_one')
        if aligned['cluster'].isna().any() or not np.array_equal(aligned['cluster'], aligned['operational_protein_cluster']):
            raise ValueError('neural cluster alignment')
        if not np.array_equal(aligned['prediction_target'].to_numpy(float), aligned['expression_value'].to_numpy(float)):
            raise ValueError('neural target alignment')
        output[seed]['ribokinetic_all'] = aligned['prediction'].to_numpy(float)
    raw = pd.read_csv(protocol['data']['baseline_predictions'])
    raw = raw[raw['ood_assignment'].isin(['train','dev'])]
    raw['source_row'] = raw['source_row'].astype(str)
    aligned = base.merge(raw[['source_row','construct_id','ood_assignment','expression','pred_ridge_all','pred_histgb_all']],
                         on=['source_row','construct_id','ood_assignment'], how='left', validate='one_to_one')
    if not np.allclose(aligned['expression_value'], aligned['expression']):
        raise ValueError('baseline target alignment')
    for seed in protocol['seeds']:
        output[seed]['ridge_all'] = aligned['pred_ridge_all'].to_numpy(float)
        output[seed]['histgb_all'] = aligned['pred_histgb_all'].to_numpy(float)
    return output


def metrics(y, prediction, clusters):
    frame = pd.DataFrame({'cluster':clusters,'error':(prediction-y)**2})
    cluster_mse = frame.groupby('cluster')['error'].mean()
    variance = np.sum((y-y.mean())**2)
    return {
        'n_rows':int(len(y)), 'n_clusters':int(frame['cluster'].nunique()),
        'row_mse':float(np.mean((prediction-y)**2)),
        'row_r2':float(1-np.sum((prediction-y)**2)/variance),
        'row_spearman':float(spearmanr(y,prediction).statistic),
        'row_pearson':float(pearsonr(y,prediction).statistic),
        'cluster_balanced_mse':float(cluster_mse.mean()),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--result', type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    result = json.loads(args.result.read_text())
    author_protocol = json.loads(Path(protocol['data']['author_definition_protocol']).read_text())
    checks = []
    def check(name, condition):
        checks.append({'name':name,'pass':bool(condition)})
    protocol_hash = sha256(args.protocol)
    result_hash = sha256(args.result)
    check('protocol binding', result['protocol_sha256'] == protocol_hash)
    check('implementation binding', result['implementation_sha256'] == sha256(Path('/home/codonflow-a8-rk/scripts/a8_rk25_run_author_mechanism.py')))
    check('dev only status', result['status'] == 'DEV_ONLY_NO_TEST_OR_SEQUENCE_OOD_READOUT')
    check('dev splits', result['splits'] == ['train','dev'])
    check('no test metrics', 'test' not in result['metrics'])
    check('no sequence-OOD metrics', 'sequence_ood' not in result['metrics'])
    check('no confirmatory comparisons', result['confirmatory_comparisons'] == [])
    check('no bootstrap', result['bootstrap']['path'] is None)
    check('untouched false', result['functional_untouched_evaluated'] is False)
    check('RK-G1 remains false', result['rk_g1'] is False)
    for key, expected in result['input_sha256'].items():
        if key.startswith('ribokinetic_all_seed'):
            seed = key.replace('ribokinetic_all_seed','')
            path = protocol['frozen_ribokinetic_all_predictions'][seed]['path']
        else:
            path = protocol['data'][key]
        check(f'input hash {key}', sha256(path) == expected)
    model_path = Path(result['model_artifact'])
    model_hash = sha256(model_path)
    check('model artifact hash', model_hash == result['model_artifact_sha256'])
    prediction_path = Path(result['predictions'])
    check('prediction hash', sha256(prediction_path) == result['predictions_sha256'])
    with open(model_path,'rb') as handle:
        artifact = pickle.load(handle)
    check('artifact protocol hash', artifact['protocol_sha256'] == protocol_hash)
    check('artifact feature hash', artifact['author_feature_file_sha256'] == protocol['data']['author_feature_file_sha256'])
    production = pd.read_csv(prediction_path)
    production['source_row'] = production['source_row'].astype(str)
    check('prediction rows', len(production) == 4 * (4019+503))
    check('prediction partitions', set(production['ood_assignment']) == {'train','dev'})
    check('prediction seeds', set(production['seed']) == set(protocol['seeds']))
    frames = load_frames(protocol)
    base = base_frame(frames)
    fitted = independent_fit(frames['train'], author_protocol)
    check('feature names', fitted['names'] == artifact['model']['author_feature_names'])
    stored_slopes = np.array([artifact['model']['single_slopes'][c] for c in CODONS])
    independent_slopes = np.array([fitted['slopes'][c] for c in CODONS])
    slope_difference = float(np.max(np.abs(stored_slopes-independent_slopes)))
    check('single-codon slope reproduction', slope_difference < 1e-7)
    stored_multi = artifact['model']['author_multiclass']
    multi = fitted['multi']
    weight_difference = float(np.max(np.abs(np.asarray(stored_multi['weights'])-multi['weights'])))
    bias_difference = float(np.max(np.abs(np.asarray(stored_multi['bias'])-multi['bias'])))
    mean_difference = float(np.max(np.abs(np.asarray(stored_multi['train_mean'])-multi['mean'])))
    scale_difference = float(np.max(np.abs(np.asarray(stored_multi['train_scale'])-multi['scale'])))
    check('multiclass weight reproduction', weight_difference < 1e-6)
    check('multiclass bias reproduction', bias_difference < 1e-7)
    check('feature mean reproduction', mean_difference < 1e-10)
    check('feature scale reproduction', scale_difference < 1e-10)
    check('single-codon convergence', all(item['success'] for item in fitted['single_diagnostics']))
    check('multinomial convergence', multi['success'])
    full = pd.concat([frames['train'],frames['dev']], ignore_index=True)
    author_prediction = expected_score(multi, matrix(full, fitted['names'], fitted['slopes']))
    frozen = align_frozen(protocol, base)
    for seed in protocol['seeds']:
        frozen[seed]['boel_author'] = author_prediction
    max_prediction_difference = 0.0
    for seed in protocol['seeds']:
        observed = production[production['seed'] == seed].reset_index(drop=True)
        check(f'identity order seed {seed}', observed['construct_id'].tolist() == base['construct_id'].tolist()
              and observed['ood_assignment'].tolist() == base['ood_assignment'].tolist())
        for model in MODELS:
            difference = float(np.max(np.abs(observed[model].to_numpy(float)-frozen[seed][model])))
            max_prediction_difference = max(max_prediction_difference,difference)
            check(f'prediction {model} seed {seed}', difference < 1e-9)
    max_metric_difference = 0.0
    independent_metrics = {}
    for split in ['train','dev']:
        independent_metrics[split] = {'per_seed':{},'mean_across_seeds':{}}
        indices = base['ood_assignment'].to_numpy() == split
        y = base.loc[indices,'expression_value'].to_numpy(float)
        clusters = base.loc[indices,'operational_protein_cluster'].to_numpy(str)
        for seed in protocol['seeds']:
            independent_metrics[split]['per_seed'][str(seed)] = {}
            for model in MODELS:
                observed = metrics(y, frozen[seed][model][indices], clusters)
                independent_metrics[split]['per_seed'][str(seed)][model] = observed
                expected = result['metrics'][split]['per_seed'][str(seed)][model]
                for key, value in observed.items():
                    difference = abs(float(value)-float(expected[key]))
                    max_metric_difference = max(max_metric_difference,difference)
                    check(f'metric {split} {seed} {model} {key}', difference < 1e-9)
        for model in MODELS:
            independent_metrics[split]['mean_across_seeds'][model] = {}
            for key in ['row_mse','row_r2','row_spearman','row_pearson','cluster_balanced_mse']:
                value = float(np.mean([independent_metrics[split]['per_seed'][str(seed)][model][key] for seed in protocol['seeds']]))
                independent_metrics[split]['mean_across_seeds'][model][key] = value
                expected = result['metrics'][split]['mean_across_seeds'][model][key]
                difference = abs(value-float(expected))
                max_metric_difference = max(max_metric_difference,difference)
                check(f'mean metric {split} {model} {key}', difference < 1e-9)
    max_comparison_difference = 0.0
    independent_points = []
    for split in ['train','dev']:
        means = independent_metrics[split]['mean_across_seeds']
        for comparison in protocol['comparisons']:
            left,right = comparison['left'],comparison['right']
            for endpoint,column in [('spearman','row_spearman'),('cluster_balanced_mse','cluster_balanced_mse')]:
                delta = float(means[left][column]-means[right][column])
                independent_points.append({'partition':split,'left':left,'right':right,'metric':endpoint,
                                           'point_delta_mean_per_seed':delta})
    expected_points = {(r['partition'],r['left'],r['right'],r['metric']):r for r in result['point_comparisons']}
    for row in independent_points:
        key = (row['partition'],row['left'],row['right'],row['metric'])
        difference = abs(row['point_delta_mean_per_seed']-expected_points[key]['point_delta_mean_per_seed'])
        max_comparison_difference = max(max_comparison_difference,difference)
        check(f'point comparison {key}', difference < 1e-9)
    failed = [item['name'] for item in checks if not item['pass']]
    independent_path = model_path.parent / 'rk25_dev_independent_refit.npz'
    np.savez_compressed(independent_path, author_prediction=author_prediction,
                        single_slopes=independent_slopes, codons=np.asarray(CODONS),
                        multiclass_weights=multi['weights'], multiclass_bias=multi['bias'],
                        train_mean=multi['mean'], train_scale=multi['scale'])
    report = {
        'schema':'a8-rk25-dev-independent-verification-v1',
        'status':'PASS' if not failed else 'FAIL',
        'protocol_sha256':protocol_hash,
        'production_result_sha256':result_hash,
        'production_implementation_sha256':result['implementation_sha256'],
        'independent_implementation_sha256':sha256(Path(__file__).resolve()),
        'model_artifact_sha256':model_hash,
        'predictions_sha256':result['predictions_sha256'],
        'independent_arrays':str(independent_path),
        'independent_arrays_sha256':sha256(independent_path),
        'checks_total':len(checks),'checks_passed':len(checks)-len(failed),'failed_checks':failed,
        'checks':checks,
        'max_abs_single_slope_difference':slope_difference,
        'max_abs_multiclass_weight_difference':weight_difference,
        'max_abs_multiclass_bias_difference':bias_difference,
        'max_abs_feature_mean_difference':mean_difference,
        'max_abs_feature_scale_difference':scale_difference,
        'max_abs_prediction_difference':max_prediction_difference,
        'max_abs_metric_difference':max_metric_difference,
        'max_abs_point_comparison_difference':max_comparison_difference,
        'train_dev_rows':[4019,503],
        'test_or_sequence_ood_metrics_accessed':False,
        'functional_untouched_evaluated':False,
        'rk_g1':False,
    }
    output = args.result.parent / 'rk25_dev_independent_verification_v1.json'
    atomic_json(output, report)
    print(json.dumps({'status':report['status'],'checks':f"{report['checks_passed']}/{report['checks_total']}",
                      'report':str(output),'max_prediction_difference':max_prediction_difference,
                      'max_metric_difference':max_metric_difference},indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
