#!/usr/bin/env python3
"""Verify the RK25 scientific closeout and registry against frozen evidence."""
from pathlib import Path
import hashlib
import json

ROOT = Path('/home/codonflow-a8-rk')
AUDIT = ROOT/'audits/20261121/RK25'
RESULT = json.loads((AUDIT/'rk25_ood_result_v1.json').read_text())
DEV = json.loads((AUDIT/'rk25_dev_independent_verification_v1.json').read_text())
OOD = json.loads((AUDIT/'rk25_ood_independent_verification_v1.json').read_text())
PROTOCOL = AUDIT/'a8_rk25_author_mechanism_protocol_v1.json'
CLOSEOUT_PATH = AUDIT/'A8_RK25_AUTHOR_MECHANISM_CLOSEOUT.md'
REGISTRY_PATH = ROOT/'experiments/REGISTRY.md'
CLOSEOUT = CLOSEOUT_PATH.read_text()
CLOSEOUT_NORMALIZED = CLOSEOUT.replace('−', '-')
REGISTRY = REGISTRY_PATH.read_text()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


checks = []
def check(name, condition):
    checks.append({'name':name,'pass':bool(condition)})


check('dev PASS',DEV['status']=='PASS' and DEV['checks_passed']==DEV['checks_total']==337)
check('OOD PASS',OOD['status']=='PASS' and OOD['checks_passed']==OOD['checks_total']==678)
check('OOD production binding',OOD['production_result_sha256']==sha(AUDIT/'rk25_ood_result_v1.json'))
check('protocol hash',sha(PROTOCOL)=='26df69797a64e97db53ccb8b53255ca17d69af85f7c1ab3e76338cd500496909')
check('result hash',sha(AUDIT/'rk25_ood_result_v1.json')=='72d0f42b30685984a6592dcb2fba208765e3663562b819d1982099226c6fdf42')
check('independent report hash',sha(AUDIT/'rk25_ood_independent_verification_v1.json')=='2fac738cc3373140de9628b069048f0e71cccd39eec95352559d0dfb9a83ab69')
check('mechanism gate false',RESULT['mechanism_vs_author_pass'] is False and OOD['mechanism_vs_author_pass'] is False)
check('author reference gate true',RESULT['author_reference_pass'] is True and OOD['author_reference_pass'] is True)
check('strong chain false',RESULT['strong_comparator_chain_pass'] is False and OOD['strong_comparator_chain_pass'] is False)
check('RK-G1 false',RESULT['rk_g1'] is False and OOD['rk_g1'] is False)
check('test descriptive',RESULT['test_descriptive_only'] is True and OOD['test_descriptive_only'] is True)
check('sequence OOD research partition',RESULT['sequence_ood_already_observed'] is True and OOD['sequence_ood_already_observed'] is True)
check('functional untouched false',RESULT['functional_untouched_evaluated'] is False and OOD['functional_untouched_evaluated'] is False)
check('no new training',RESULT['new_neural_or_generator_training'] is False)
check('dev replay',RESULT['dev_replay_within_1e_12'] is True and RESULT['dev_replay_max_abs_difference']<=1e-12)
check('six confirmatory',len(RESULT['confirmatory_comparisons'])==6)
check('all sequence OOD',all(row['partition']=='sequence_ood' for row in RESULT['confirmatory_comparisons']))
check('endpoint pattern',[row['endpoint_pass'] for row in RESULT['confirmatory_comparisons']]==[False,False,True,True,True,True])
check('empirical p zeros',all(row['sign_pvalue']==0 and row['holm_pvalue']==0 for row in RESULT['confirmatory_comparisons']))
for row in RESULT['confirmatory_comparisons']:
    label=f"{row['left']} {row['right']} {row['metric']}"
    check(f'CI direction {label}',row['ci95_low']<=row['point_delta_mean_per_seed']<=row['ci95_high'])
    for key in ['point_delta_mean_per_seed','ci95_low','ci95_high']:
        value=row[key]
        anchors={f'{value:+.8f}',f'{value:.8f}'}
        check(f'closeout numeric {label} {key}',any(anchor in CLOSEOUT_NORMALIZED for anchor in anchors))
for model in ['ribokinetic_all','boel_author','ridge_all','histgb_all']:
    metrics=RESULT['metrics']['sequence_ood']['mean_across_seeds'][model]
    check(f'Spearman anchor {model}',f"{metrics['row_spearman']:.8f}" in CLOSEOUT)
    check(f'MSE anchor {model}',f"{metrics['cluster_balanced_mse']:.8f}" in CLOSEOUT)
for phrase in [
    'AUTHOR_REFERENCE_SUPERIORITY_SUPPORTED', 'ALL_CHANNEL_MECHANISM_INCREMENT_NOT_SUPPORTED',
    'STRONG_COMPARATOR_CHAIN_FAILED', '337/337', '678/678', '20,000 hierarchical bootstrap',
    'not a majority vote', 'Test was descriptive only', 'Functional untouched data were not accessed',
    'RK-G1 = false', 'expensive generator training remains unauthorized',
    'does not establish fixed-protein synonymous causality', 'not functional-untouched confirmation',
    '44014ad0fc923fba65d52fcda953117d9c822051',
    '62b2c05135a3ea3e05c646fbee8764693e7b1464878e009126ae94443b7508e4',
    '5c289704bc23a7e85351a5f52f54089f086f38434f3a824807af4b09d457d157',
    '10018793d3a24711554ce4ab1b98c76e14271c7fc1c9d2ea75ab4bf4ac41939f',
    'a86068da089f05fab00a13621e66493b2853e21197d3a491061ddce24c22c3c4',
]:
    check(f'closeout anchor {phrase[:50]}',phrase in CLOSEOUT)
rows=[line for line in REGISTRY.splitlines() if line.startswith('| CF-A8-RK25 |')]
check('one RK25 registry row',len(rows)==1)
if rows:
    row=rows[0]
    check('RK25 row 11 columns',row.count('|')==12)
    for phrase in ['44014ad0fc923fba65d52fcda953117d9c822051','678/678','337/337',
                   'mechanism 0/2 FAIL','4/4 PASS','strong chain FAIL','RK-G1=false',
                   'test descriptive only','no functional untouched access']:
        check(f'registry anchor {phrase}',phrase in row)
for line in REGISTRY.splitlines():
    if line.startswith('| CF-A8-RK24') or line.startswith('| CF-A8-RK25'):
        check(f'registry schema {line.split("|")[1].strip()}',line.count('|')==12)
check('model hash binding',RESULT['model_artifact_sha256']==OOD['model_artifact_sha256'])
check('prediction hash binding',RESULT['predictions_sha256']==OOD['predictions_sha256'])
check('bootstrap hash binding',RESULT['bootstrap']['sha256']==OOD['production_bootstrap_sha256'])
check('independent bootstrap exists',Path(OOD['independent_bootstrap']).is_file())
check('independent bootstrap hash',sha(OOD['independent_bootstrap'])==OOD['independent_bootstrap_sha256'])
failed=[item['name'] for item in checks if not item['pass']]
report={
    'schema':'a8-rk25-closeout-verification-v1','status':'PASS' if not failed else 'FAIL',
    'result_sha256':sha(AUDIT/'rk25_ood_result_v1.json'),
    'ood_independent_report_sha256':sha(AUDIT/'rk25_ood_independent_verification_v1.json'),
    'closeout_sha256':sha(CLOSEOUT_PATH),'registry_sha256':sha(REGISTRY_PATH),
    'implementation_sha256':sha(Path(__file__).resolve()),
    'checks_total':len(checks),'checks_passed':len(checks)-len(failed),'failed_checks':failed,'checks':checks,
    'mechanism_vs_author_pass':False,'author_reference_pass':True,'strong_comparator_chain_pass':False,
    'rk_g1':False,'functional_untouched_evaluated':False,
}
out=AUDIT/'rk25_closeout_verification_v1.json'
out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({k:report[k] for k in ['status','checks_total','checks_passed','failed_checks','closeout_sha256','registry_sha256']},indent=2))
if failed:
    raise SystemExit(1)
