#!/usr/bin/env python3
"""Independent RK25 test/sequence-OOD verification and hierarchical-bootstrap replay."""
from pathlib import Path
import argparse
import json
import pickle
import sys

import numpy as np
import pandas as pd
from scipy.stats import rankdata

REPO = Path('/home/codonflow-a8-rk')
sys.path.insert(0, str(REPO))
from scripts.a8_rk25_verify_dev import (
    CODON_TABLE, MODELS, atomic_json, expected_score, matrix, metrics, sha256, text_hash,
)

PARTITIONS = ['train', 'dev', 'test', 'sequence_ood']
ENDPOINTS = ['spearman', 'cluster_balanced_mse']


def load_all_frames(protocol):
    static = pd.read_csv(protocol['data']['author_feature_file'], low_memory=False)
    static['source_row'] = static['source_row'].astype(str)
    columns = ['source_row','construct_id','source_id','ood_assignment','operational_protein_cluster',
               'expression_value','cds','features_json']
    source = pd.read_csv(protocol['data']['functional_csv'], usecols=columns, low_memory=False)
    source = source[source['source_id'] == protocol['data']['source_id']].copy()
    source['source_row'] = source['source_row'].astype(str)
    if set(source['ood_assignment']) & {'functional_untouched','untouched'}:
        raise ValueError('forbidden untouched partition')
    if source['ood_assignment'].value_counts().to_dict() != protocol['data']['expected_rows']:
        raise ValueError('assignment counts')
    frames = {}
    for split in PARTITIONS:
        part = source[source['ood_assignment'] == split].copy()
        part['_source_row_int'] = part['source_row'].astype(int)
        part = part.sort_values('_source_row_int')
        merged = part.merge(static, on=['source_row','construct_id'], how='left', validate='one_to_one',
                            suffixes=('','_static'), indicator=True)
        if not (merged['_merge'] == 'both').all():
            raise ValueError(f'missing features {split}')
        core_codons = []
        for row in merged.itertuples():
            cds = ''.join(row.cds.upper().split())
            if text_hash(cds) != row.cds_sha256:
                raise ValueError('CDS hash')
            if row.operational_protein_cluster != row.operational_protein_cluster_static:
                raise ValueError('cluster mismatch')
            if float(json.loads(row.features_json)['Gz48v']) != float(row.source_Gz48v):
                raise ValueError('UH mismatch')
            codons = [cds[i:i+3] for i in range(0,len(cds),3)]
            core = codons[:-9]
            protein = ''.join(CODON_TABLE[c] for c in core)
            if text_hash(''.join(core)) != row.core_cds_sha256 or text_hash(protein) != row.core_protein_sha256:
                raise ValueError('core hash')
            core_codons.append(core)
        merged['core_codons'] = core_codons
        if len(merged) != protocol['data']['expected_rows'][split]:
            raise ValueError('partition rows')
        frames[split] = merged.reset_index(drop=True)
    return frames


def make_base(frames):
    rows = []
    for split in PARTITIONS:
        frame = frames[split]
        rows.append(pd.DataFrame({
            'source_row':frame['source_row'].astype(str), 'construct_id':frame['construct_id'],
            'ood_assignment':split, 'operational_protein_cluster':frame['operational_protein_cluster'],
            'expression_value':frame['expression_value'].to_numpy(float),
        }))
    return pd.concat(rows, ignore_index=True)


def align_all(protocol, base):
    output = {seed:{} for seed in protocol['seeds']}
    for seed in protocol['seeds']:
        record = protocol['frozen_ribokinetic_all_predictions'][str(seed)]
        raw = pd.read_csv(record['path']).rename(columns={
            'record_id':'construct_id','split':'ood_assignment','cluster_id':'cluster','target':'prediction_target',
        })
        aligned = base.merge(raw[['construct_id','ood_assignment','cluster','prediction_target','prediction']],
                             on=['construct_id','ood_assignment'], how='left', validate='one_to_one')
        if aligned['cluster'].isna().any() or not np.array_equal(aligned['cluster'],aligned['operational_protein_cluster']):
            raise ValueError('neural cluster')
        if not np.array_equal(aligned['prediction_target'].to_numpy(float),aligned['expression_value'].to_numpy(float)):
            raise ValueError('neural target')
        output[seed]['ribokinetic_all'] = aligned['prediction'].to_numpy(float)
    raw = pd.read_csv(protocol['data']['baseline_predictions'])
    raw['source_row'] = raw['source_row'].astype(str)
    aligned = base.merge(raw[['source_row','construct_id','ood_assignment','expression','pred_ridge_all','pred_histgb_all']],
                         on=['source_row','construct_id','ood_assignment'], how='left', validate='one_to_one')
    if not np.allclose(aligned['expression_value'],aligned['expression']):
        raise ValueError('baseline target')
    for seed in protocol['seeds']:
        output[seed]['ridge_all'] = aligned['pred_ridge_all'].to_numpy(float)
        output[seed]['histgb_all'] = aligned['pred_histgb_all'].to_numpy(float)
    return output


def fast_spearman(y, prediction):
    if np.std(y) <= 0 or np.std(prediction) <= 0:
        return np.nan
    return float(np.corrcoef(rankdata(y),rankdata(prediction))[0,1])


def independent_bootstrap(y, clusters, predictions, protocol):
    seeds = protocol['seeds']
    pairs = [(item['left'],item['right']) for item in protocol['comparisons']]
    cluster_frame = pd.DataFrame({'cluster':clusters,'row':np.arange(len(y))})
    groups = [group['row'].to_numpy() for _,group in cluster_frame.groupby('cluster',sort=True)]
    cluster_mse = {
        (seed,model):np.array([np.mean((predictions[seed][model][group]-y[group])**2) for group in groups])
        for seed in seeds for model in MODELS
    }
    replicates = int(protocol['statistics']['replicates'])
    rng = np.random.default_rng(int(protocol['statistics']['seed']))
    raw = np.zeros((replicates,len(pairs),len(ENDPOINTS)))
    cluster_draws = np.zeros((replicates,len(groups)),dtype=np.int32)
    seed_draws = np.zeros((replicates,len(seeds)),dtype=np.int64)
    for replicate in range(replicates):
        selected_clusters = rng.integers(0,len(groups),len(groups))
        selected_seed_indices = rng.integers(0,len(seeds),len(seeds))
        selected_seeds = [seeds[int(index)] for index in selected_seed_indices]
        selected_rows = np.concatenate([groups[index] for index in selected_clusters])
        cluster_draws[replicate] = selected_clusters
        seed_draws[replicate] = selected_seeds
        per_seed = {(left,right,endpoint):[] for left,right in pairs for endpoint in ENDPOINTS}
        for seed in selected_seeds:
            values = {}
            for model in MODELS:
                values[(model,'spearman')] = fast_spearman(y[selected_rows],predictions[seed][model][selected_rows])
                values[(model,'cluster_balanced_mse')] = float(np.mean(cluster_mse[(seed,model)][selected_clusters]))
            for left,right in pairs:
                for endpoint in ENDPOINTS:
                    per_seed[(left,right,endpoint)].append(values[(left,endpoint)]-values[(right,endpoint)])
        for pair_index,(left,right) in enumerate(pairs):
            for endpoint_index,endpoint in enumerate(ENDPOINTS):
                raw[replicate,pair_index,endpoint_index] = np.mean(per_seed[(left,right,endpoint)])
    return raw,cluster_draws,seed_draws


def holm_adjust(values):
    values = np.asarray(values,float)
    order = np.argsort(values)
    adjusted = np.empty(len(values),float)
    running = 0.0
    for rank,index in enumerate(order):
        running = max(running,(len(values)-rank)*values[index])
        adjusted[index] = min(1.0,running)
    return adjusted


def independent_summary(raw, points, protocol):
    expected = {(r['left'],r['right'],r['metric']):r for r in points if r['partition']=='sequence_ood'}
    rows = []
    for pair_index,comparison in enumerate(protocol['comparisons']):
        left,right = comparison['left'],comparison['right']
        for endpoint_index,endpoint in enumerate(ENDPOINTS):
            point = expected[(left,right,endpoint)]
            samples = raw[:,pair_index,endpoint_index]
            valid = samples[np.isfinite(samples)]
            benefit = valid if endpoint == 'spearman' else -valid
            pvalue = float(min(1.0,2.0*min(np.mean(benefit<=0),np.mean(benefit>=0))))
            row = dict(point)
            row.update({
                'ci95_low':float(np.quantile(valid,0.025)), 'ci95_high':float(np.quantile(valid,0.975)),
                'sign_pvalue':pvalue, 'bootstrap_valid':int(len(valid)),
                'bootstrap_requested':int(protocol['statistics']['replicates']),
            })
            row['point_direction_pass'] = bool(row['benefit']>0)
            row['ci_direction_pass'] = bool((endpoint=='spearman' and row['ci95_low']>0)
                                            or (endpoint=='cluster_balanced_mse' and row['ci95_high']<0))
            rows.append(row)
    adjusted = holm_adjust([row['sign_pvalue'] for row in rows])
    for row,pvalue in zip(rows,adjusted):
        row['holm_pvalue'] = float(pvalue)
        row['direction_pass'] = bool(row['point_direction_pass'] and row['ci_direction_pass'])
        row['endpoint_pass'] = bool(row['direction_pass'] and row['holm_pvalue']<0.05)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--dev-result',type=Path,required=True)
    parser.add_argument('--dev-independent-report',type=Path,required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    result = json.loads(args.result.read_text())
    dev_report = json.loads(args.dev_independent_report.read_text())
    checks = []
    def check(name,condition):
        checks.append({'name':name,'pass':bool(condition)})
    protocol_hash = sha256(args.protocol)
    result_hash = sha256(args.result)
    check('protocol binding',result['protocol_sha256']==protocol_hash)
    check('implementation binding',result['implementation_sha256']==sha256(REPO/'scripts/a8_rk25_run_author_mechanism.py'))
    check('OOD phase',result['phase']=='ood')
    check('all partitions',result['splits']==PARTITIONS)
    check('dev report PASS',dev_report['status']=='PASS')
    check('dev report protocol',dev_report['protocol_sha256']==protocol_hash)
    check('dev report production hash',dev_report['production_result_sha256']==sha256(args.dev_result))
    check('dev report model hash',dev_report['model_artifact_sha256']==result['model_artifact_sha256'])
    check('OOD binds dev report',result['dev_independent_report_sha256']==sha256(args.dev_independent_report))
    check('dev replay tolerance',result['dev_replay_within_1e_12'] is True
          and result['dev_replay_max_abs_difference']<=1e-12)
    check('test descriptive',result['test_descriptive_only'] is True)
    check('sequence-OOD observed scope',result['sequence_ood_already_observed'] is True)
    check('six confirmatory tests',len(result['confirmatory_comparisons'])==6)
    check('confirmatory partition',all(row['partition']=='sequence_ood' for row in result['confirmatory_comparisons']))
    check('functional untouched false',result['functional_untouched_evaluated'] is False)
    check('RK-G1 false',result['rk_g1'] is False)
    check('no new neural training',result['new_neural_or_generator_training'] is False)
    for key,expected in result['input_sha256'].items():
        if key.startswith('ribokinetic_all_seed'):
            seed = key.replace('ribokinetic_all_seed','')
            path = protocol['frozen_ribokinetic_all_predictions'][seed]['path']
        else:
            path = protocol['data'][key]
        check(f'input hash {key}',sha256(path)==expected)
    model_path = Path(result['model_artifact'])
    check('model hash',sha256(model_path)==result['model_artifact_sha256'])
    prediction_path = Path(result['predictions'])
    check('prediction hash',sha256(prediction_path)==result['predictions_sha256'])
    bootstrap_path = Path(result['bootstrap']['path'])
    check('bootstrap hash',sha256(bootstrap_path)==result['bootstrap']['sha256'])
    with open(model_path,'rb') as handle:
        artifact = pickle.load(handle)
    check('artifact protocol',artifact['protocol_sha256']==protocol_hash)
    frames = load_all_frames(protocol)
    base = make_base(frames)
    full = pd.concat([frames[split] for split in PARTITIONS],ignore_index=True)
    model = artifact['model']
    author_prediction = expected_score({
        'mean':np.asarray(model['author_multiclass']['train_mean']),
        'scale':np.asarray(model['author_multiclass']['train_scale']),
        'weights':np.asarray(model['author_multiclass']['weights']),
        'bias':np.asarray(model['author_multiclass']['bias']),
        'classes':np.asarray(model['author_multiclass']['classes'],float),
    },matrix(full,model['author_feature_names'],model['single_slopes']))
    dev_arrays = np.load(dev_report['independent_arrays'])
    dev_refit_difference = float(np.max(np.abs(author_prediction[:4019+503]-dev_arrays['author_prediction'])))
    check('frozen model matches independent dev refit',dev_refit_difference<2e-9)
    frozen = align_all(protocol,base)
    for seed in protocol['seeds']:
        frozen[seed]['boel_author'] = author_prediction
    production = pd.read_csv(prediction_path)
    production['source_row'] = production['source_row'].astype(str)
    check('prediction rows',len(production)==4*6348)
    check('prediction partitions',set(production['ood_assignment'])==set(PARTITIONS))
    max_prediction_difference = 0.0
    for seed in protocol['seeds']:
        observed = production[production['seed']==seed].reset_index(drop=True)
        check(f'identity seed {seed}',observed['construct_id'].tolist()==base['construct_id'].tolist()
              and observed['ood_assignment'].tolist()==base['ood_assignment'].tolist())
        for model_name in MODELS:
            difference = float(np.max(np.abs(observed[model_name].to_numpy(float)-frozen[seed][model_name])))
            max_prediction_difference = max(max_prediction_difference,difference)
            check(f'prediction {seed} {model_name}',difference<2e-9)
    max_metric_difference = 0.0
    independent_metrics = {}
    for split in PARTITIONS:
        independent_metrics[split] = {'per_seed':{},'mean_across_seeds':{}}
        indices = base['ood_assignment'].to_numpy()==split
        y = base.loc[indices,'expression_value'].to_numpy(float)
        clusters = base.loc[indices,'operational_protein_cluster'].to_numpy(str)
        for seed in protocol['seeds']:
            independent_metrics[split]['per_seed'][str(seed)] = {}
            for model_name in MODELS:
                observed = metrics(y,frozen[seed][model_name][indices],clusters)
                independent_metrics[split]['per_seed'][str(seed)][model_name] = observed
                expected = result['metrics'][split]['per_seed'][str(seed)][model_name]
                for key,value in observed.items():
                    difference = abs(float(value)-float(expected[key]))
                    max_metric_difference = max(max_metric_difference,difference)
                    check(f'metric {split} {seed} {model_name} {key}',difference<2e-9)
        for model_name in MODELS:
            independent_metrics[split]['mean_across_seeds'][model_name] = {}
            for key in ['row_mse','row_r2','row_spearman','row_pearson','cluster_balanced_mse']:
                value = float(np.mean([independent_metrics[split]['per_seed'][str(seed)][model_name][key]
                                       for seed in protocol['seeds']]))
                independent_metrics[split]['mean_across_seeds'][model_name][key] = value
                expected = result['metrics'][split]['mean_across_seeds'][model_name][key]
                difference = abs(value-float(expected))
                max_metric_difference = max(max_metric_difference,difference)
                check(f'mean metric {split} {model_name} {key}',difference<2e-9)
    independent_points = []
    for split in PARTITIONS:
        means = independent_metrics[split]['mean_across_seeds']
        for comparison in protocol['comparisons']:
            left,right = comparison['left'],comparison['right']
            for endpoint,column in [('spearman','row_spearman'),('cluster_balanced_mse','cluster_balanced_mse')]:
                delta = float(means[left][column]-means[right][column])
                independent_points.append({'partition':split,'left':left,'right':right,'metric':endpoint,
                                           'point_delta_mean_per_seed':delta,
                                           'benefit':delta if endpoint=='spearman' else -delta,
                                           'confirmatory':split=='sequence_ood'})
    expected_points = {(r['partition'],r['left'],r['right'],r['metric']):r for r in result['point_comparisons']}
    max_point_difference = 0.0
    for row in independent_points:
        key = (row['partition'],row['left'],row['right'],row['metric'])
        difference = abs(row['point_delta_mean_per_seed']-expected_points[key]['point_delta_mean_per_seed'])
        max_point_difference = max(max_point_difference,difference)
        check(f'point {key}',difference<2e-9)
    ood_indices = base['ood_assignment'].to_numpy()=='sequence_ood'
    y = base.loc[ood_indices,'expression_value'].to_numpy(float)
    clusters = base.loc[ood_indices,'operational_protein_cluster'].to_numpy(str)
    predictions = {seed:{model_name:frozen[seed][model_name][ood_indices] for model_name in MODELS}
                   for seed in protocol['seeds']}
    raw,cluster_draws,seed_draws = independent_bootstrap(y,clusters,predictions,protocol)
    produced_npz = np.load(bootstrap_path)
    max_bootstrap_difference = float(np.max(np.abs(raw-produced_npz['raw_delta'])))
    check('raw bootstrap reproduction',max_bootstrap_difference<2e-9)
    check('cluster draws exact',np.array_equal(cluster_draws,produced_npz['cluster_draws']))
    check('seed draws exact',np.array_equal(seed_draws,produced_npz['seed_draws']))
    independent_comparisons = independent_summary(raw,independent_points,protocol)
    max_inference_difference = 0.0
    for independent,produced in zip(independent_comparisons,result['confirmatory_comparisons']):
        check('comparison identity', (independent['left'],independent['right'],independent['metric'])
              ==(produced['left'],produced['right'],produced['metric']))
        for key in ['point_delta_mean_per_seed','ci95_low','ci95_high','sign_pvalue','holm_pvalue']:
            difference = abs(float(independent[key])-float(produced[key]))
            max_inference_difference = max(max_inference_difference,difference)
            check(f'inference {independent["left"]} {independent["right"]} {independent["metric"]} {key}',difference<2e-9)
        for key in ['point_direction_pass','ci_direction_pass','direction_pass','endpoint_pass']:
            check(f'flag {independent["left"]} {independent["right"]} {independent["metric"]} {key}',
                  independent[key]==produced[key])
    gates = {
        'mechanism_vs_author_pass':all(row['endpoint_pass'] for row in independent_comparisons[:2]),
        'author_reference_pass':all(row['endpoint_pass'] for row in independent_comparisons[2:]),
        'strong_comparator_chain_pass':all(row['endpoint_pass'] for row in independent_comparisons),
    }
    for key,value in gates.items():
        check(f'gate {key}',value==result[key])
    failed = [item['name'] for item in checks if not item['pass']]
    independent_path = bootstrap_path.parent/'rk25_ood_independent_bootstrap.npz'
    np.savez_compressed(independent_path,raw_delta=raw,cluster_draws=cluster_draws,seed_draws=seed_draws)
    report = {
        'schema':'a8-rk25-ood-independent-verification-v1',
        'status':'PASS' if not failed else 'FAIL',
        'protocol_sha256':protocol_hash,'production_result_sha256':result_hash,
        'production_implementation_sha256':result['implementation_sha256'],
        'independent_implementation_sha256':sha256(Path(__file__).resolve()),
        'dev_result_sha256':sha256(args.dev_result),
        'dev_independent_report_sha256':sha256(args.dev_independent_report),
        'model_artifact_sha256':result['model_artifact_sha256'],
        'predictions_sha256':result['predictions_sha256'],
        'production_bootstrap_sha256':result['bootstrap']['sha256'],
        'independent_bootstrap':str(independent_path),
        'independent_bootstrap_sha256':sha256(independent_path),
        'checks_total':len(checks),'checks_passed':len(checks)-len(failed),'failed_checks':failed,
        'checks':checks,
        'max_abs_dev_refit_prediction_difference':dev_refit_difference,
        'max_abs_prediction_difference':max_prediction_difference,
        'max_abs_metric_difference':max_metric_difference,
        'max_abs_point_comparison_difference':max_point_difference,
        'max_abs_bootstrap_difference':max_bootstrap_difference,
        'max_abs_inference_difference':max_inference_difference,
        **gates,
        'confirmatory_comparisons':independent_comparisons,
        'functional_untouched_evaluated':False,
        'sequence_ood_already_observed':True,
        'test_descriptive_only':True,
        'rk_g1':False,
    }
    output = args.result.parent/'rk25_ood_independent_verification_v1.json'
    atomic_json(output,report)
    print(json.dumps({'status':report['status'],'checks':f"{report['checks_passed']}/{report['checks_total']}",
                      **gates,'max_bootstrap_difference':max_bootstrap_difference,
                      'max_inference_difference':max_inference_difference,'report':str(output)},indent=2))
    if failed:
        raise SystemExit(1)


if __name__=='__main__':
    main()
