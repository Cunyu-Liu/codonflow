#!/usr/bin/env python3
"""Bind RK26 closeout, registry, source hashes, and independent evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

REPO = Path('/home/codonflow-a8-rk')
ROOT = REPO/'audits/20261121/RK26'


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--science-commit', required=True)
    args = parser.parse_args()
    protocol_path = ROOT/'a8_rk26_mage_pair_feasibility_protocol_v1.json'
    result_path = ROOT/'rk26_pair_feasibility_result_v1.json'
    independent_path = ROOT/'rk26_pair_feasibility_independent_v1.json'
    closeout_path = ROOT/'A8_RK26_MAGE_PAIR_FEASIBILITY_CLOSEOUT.md'
    protocol = json.loads(protocol_path.read_text())
    result = json.loads(result_path.read_text())
    independent = json.loads(independent_path.read_text())
    closeout = closeout_path.read_text()
    registry = (REPO/'experiments/REGISTRY.md').read_text()
    checks = []
    def check(name, passed, detail=None):
        checks.append({'name':name,'pass':bool(passed),'detail':detail})

    check('independent_42_of_42', independent['status']=='PASS' and independent['checks_passed']==42 and independent['checks_total']==42)
    check('independent_all_checks_true', all(row['pass'] for row in independent['checks']))
    check('production_hash_bound', independent['production_report_sha256']==sha256(result_path))
    check('protocol_hash_bound', result['protocol_sha256']==independent['protocol_sha256']==sha256(protocol_path))
    check('row_count', result['rows']==independent['independent_pair_contexts'][0]['rows']+independent['independent_pair_contexts'][1]['rows']==8192)
    check('single_count', result['synonymous_single_variants']==independent['independent_single_synonymous']==6)
    check('double_count', result['synonymous_double_variants']==independent['independent_double_synonymous']==4)
    check('pair_1_2_counts', result['pair_contexts'][0]['single_synonymous']==4 and result['pair_contexts'][0]['double_synonymous']==3 and result['pair_contexts'][0]['coverage_rule_pass']==1)
    check('pair_2_3_counts', result['pair_contexts'][1]['single_synonymous']==2 and result['pair_contexts'][1]['double_synonymous']==1 and result['pair_contexts'][1]['coverage_rule_pass']==0)
    check('candidate_closed_not_feasible', result['confirmatory_single_to_double_ood_feasible'] is False)
    check('bounded_outcome', result['scientific_outcome']=='FIXED_PROTEIN_SINGLE_TO_DOUBLE_SYNONYMOUS_OOD_NOT_SUPPORTED_BY_SAMPLE_COVERAGE')
    check('retrospective_role', result['analysis_role']=='retrospective_data_adequacy_audit_not_a_preregistered_mechanism_experiment')
    check('no_model_or_endpoint', result['model_fits']==result['functional_endpoint_evaluations']==result['confidence_intervals_or_p_values']==0)
    check('no_test_or_untouched_access', result['original_mage_33_construct_mechanism_test_accessed'] is False and result['rk04_functional_untouched_split_accessed'] is False)
    check('rk_g1_and_generator_closed', result['rk_g1_pass'] is False and result['generator_training_authorized'] is False)
    for name in ['pair_facts_csv_gz','pair_counts_csv']:
        artifact = result['artifacts'][name]
        check(f'{name}_hash', sha256(artifact['path'])==artifact['sha256'])
        check(f'{name}_bytes', Path(artifact['path']).stat().st_size==artifact['bytes'])
    check('fact_rows_8192', result['artifacts']['pair_facts_csv_gz']['rows']==8192)
    check('counts_rows_2', result['artifacts']['pair_counts_csv']['rows']==2)

    required_paths = {
        'protocol':protocol_path, 'result':result_path, 'independent':independent_path,
        'production_script':REPO/'scripts/a8_rk26_audit_mage_pair_feasibility.py',
        'independent_script':REPO/'scripts/a8_rk26_verify_mage_pair_feasibility.py',
        'tests':REPO/'tests/test_a8_rk26_mage_pair_feasibility.py',
        'test_console':ROOT/'rk26_test_console_v1.log',
        'facts':Path(result['artifacts']['pair_facts_csv_gz']['path']),
        'counts':Path(result['artifacts']['pair_counts_csv']['path']),
    }
    for name,path in required_paths.items():
        check(f'closeout_binds_{name}_sha256', sha256(path) in closeout)
    for phrase in [
        '6 synonymous single-codon variants', '4 synonymous double-codon variants',
        'only **1 synonymous double-codon variant**', '10/10 PASS', '42/42 PASS',
        '8,192/8,192 rows', 'not a preregistered mechanism experiment',
        'Model fits: **0**', 'Functional endpoint evaluations: **0**',
        'RK-G1 remains **false**', 'generator training remains **unauthorized**',
        'af338407392db625a3deaa76aab923ff1298fe3d'
    ]:
        check('closeout_phrase_'+str(len(checks)), phrase in closeout, phrase)
    test_console = (ROOT/'rk26_test_console_v1.log').read_text()
    check('test_console_10_ok', 'Ran 10 tests' in test_console and 'OK' in test_console)

    lines = [line for line in registry.splitlines() if line.startswith('| RK26 |')]
    check('one_rk26_registry_row', len(lines)==1, len(lines))
    if len(lines)==1:
        cells = [cell.strip() for cell in lines[0].strip().strip('|').split('|')]
        check('registry_11_columns', len(cells)==11, len(cells))
        check('registry_status_completed', cells[8]=='completed', cells[8])
        check('registry_science_commit', cells[9]==args.science_commit, cells[9])
        check('registry_counts', 'single-syn6' in cells[4] and 'double-syn4' in cells[4], cells[4])
        check('registry_independent_42', 'independent42/42' in cells[7], cells[7])
        check('registry_no_test_or_generator', 'test/untouched untouched' in cells[10] and 'no generator' in cells[10], cells[10])
        check('registry_run_log_exists', Path(cells[6]).exists(), cells[6])
        check('registry_data_exists', Path(cells[5]).exists(), cells[5])
    exists = subprocess.run(['git','cat-file','-e',args.science_commit+'^{commit}'],cwd=REPO).returncode==0
    ancestor = subprocess.run(['git','merge-base','--is-ancestor',args.science_commit,'HEAD'],cwd=REPO).returncode==0
    check('science_commit_exists',exists,args.science_commit)
    check('science_commit_ancestor_of_head',ancestor)

    report = {
        'schema':'a8-rk26-closeout-verification-v1',
        'status':'PASS' if all(row['pass'] for row in checks) else 'FAIL',
        'checks_passed':sum(row['pass'] for row in checks),
        'checks_total':len(checks),
        'checks':checks,
        'science_commit':args.science_commit,
        'protocol_sha256':sha256(protocol_path),
        'production_result_sha256':sha256(result_path),
        'independent_report_sha256':sha256(independent_path),
        'closeout_sha256':sha256(closeout_path),
        'rk_g1_pass':False,
        'generator_training_authorized':False,
    }
    output = ROOT/'rk26_closeout_verification_v1.json'
    output.write_text(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False)+'\n')
    print(json.dumps({'status':report['status'],'checks':f"{report['checks_passed']}/{report['checks_total']}",'output':str(output),'sha256':sha256(output)},indent=2))
    if report['status']!='PASS':
        raise SystemExit(1)


if __name__=='__main__':
    main()
