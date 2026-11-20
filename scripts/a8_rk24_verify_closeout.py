#!/usr/bin/env python3
"""Evidence-bind the RK24 scientific closeout without importing production code."""
import argparse
import hashlib
import json
from pathlib import Path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--closeout', required=True)
    p.add_argument('--result', required=True)
    p.add_argument('--independent', required=True)
    p.add_argument('--comparator', required=True)
    p.add_argument('--dev-comparator', required=True)
    p.add_argument('--protocol', required=True)
    p.add_argument('--test-commit', required=True)
    p.add_argument('--dev-commit', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    text = Path(a.closeout).read_text()
    result = json.loads(Path(a.result).read_text())
    ind = json.loads(Path(a.independent).read_text())
    comp = json.loads(Path(a.comparator).read_text())
    dev_comp = json.loads(Path(a.dev_comparator).read_text())
    checks = []

    def add(name, ok):
        checks.append({'name': name, 'pass': bool(ok)})

    add('independent_status', ind['status'] == 'PASS_INDEPENDENT_VERIFICATION')
    add('independent_153', ind['checks_total'] == ind['checks_passed'] == 153 and not ind['checks_failed'])
    add('independent_gate', ind['scientific_gate']['all_four_pass'] and all(ind['scientific_gate']['endpoints'].values()))
    add('test_commit', a.test_commit == 'b4c04d2935015386603a5dff8b1f8c9247295b5a' and a.test_commit in text)
    add('dev_commit', a.dev_commit == 'cb0aa0957c1f62afbd37cf1cdc5aaf3d94c24ebd' and a.dev_commit in text)
    for key, path in [('result', a.result), ('independent', a.independent), ('comparator', a.comparator), ('protocol', a.protocol)]:
        digest = sha256(path)
        add('sha256_' + key, digest in text)
    add('result_hash_binding', result['protocol_sha256'] == ind['protocol_sha256'] == sha256(a.protocol))
    add('independent_result_hash_binding', ind['result_sha256'] == sha256(a.result))
    add('comparator_result_hash_binding', comp['rk24_result_sha256'] == sha256(a.result))
    add('untouched_unread', result['functional_untouched_accessed'] is False and comp['functional_untouched_accessed'] is False)
    add('generator_closed', result['generator_training_authorized'] is False and result['rk_g1'] is False)
    add('no_published_coefficients', result['published_coefficients_used_for_prediction'] is False)
    add('train_only', result['train_fit_only'] is True)

    test = result['split_results']['test']
    binary = test['metrics']['binary']
    multi = test['metrics']['multiclass']
    add('test_n', test['n'] == multi['author']['n'] == 634 and binary['n'] == 398)
    add('test_clusters', test['primary_inference']['binary_clusters'] == 364 and test['primary_inference']['multiclass_clusters'] == 556)
    add('test_replicates', test['primary_inference']['bootstrap_replicates'] == test['primary_inference']['permutation_replicates'] == 20000)
    add('test_gate', test['primary_inference']['all_four_pass'] and test['primary_inference']['passed_endpoints'] == 4)
    for split in ('dev', 'test'):
        inference = result['split_results'][split]['primary_inference']
        add(split + '_four_pass', inference['all_four_pass'] and inference['passed_endpoints'] == 4)
        for name, comparison in inference['comparisons'].items():
            add(split + '_' + name + '_pass', comparison['passes_all'] and comparison['effect'] > 0 and comparison['ci95'][0] > 0 and comparison['p_holm'] < 0.05)
            add(split + '_' + name + '_holm_text', str(comparison['p_holm']) in text if split == 'test' else True)

    anchors = [
        f"{binary['base']['auc']:.8f}", f"{binary['author']['auc']:.8f}",
        f"{binary['base']['logloss']:.8f}", f"{binary['author']['logloss']:.8f}",
        f"{multi['base']['spearman']:.8f}", f"{multi['author']['spearman']:.8f}",
        f"{multi['base']['mse']:.8f}", f"{multi['author']['mse']:.8f}",
    ]
    for i, anchor in enumerate(anchors):
        add('metric_anchor_' + str(i), anchor in text)
    for name, comparison in test['primary_inference']['comparisons'].items():
        expected = f"+{comparison['effect']:.8f}"
        ci = f"[{comparison['ci95'][0]:.8f}, {comparison['ci95'][1]:.8f}]"
        add(name + '_effect_text', expected in text)
        add(name + '_ci_text', ci in text)

    for split, report in [('test', comp), ('dev', dev_comp)]:
        hm = report['metrics']['rk23_histgb_plus_uh']
        am = report['metrics']['rk24_author_multiclass']
        de = report['descriptive_effects']
        add(split + '_histgb_spearman', f"{hm['spearman']:.8f}" in text and f"{am['spearman']:.8f}" in text and f"+{de['author_minus_histgb_spearman']:.8f}" in text)
        add(split + '_histgb_mse', f"{hm['mse']:.8f}" in text and f"{am['mse']:.8f}" in text and f"+{de['histgb_minus_author_mse']:.8f}" in text)
        add(split + '_descriptive_only', report['primary_gate_changed'] is False and report['primary_protocol_changed'] is False)
    add('histgb_status', comp['status'] == 'PASS_DESCRIPTIVE_HISTGB_COMPARATOR')

    for key in ('max_static_feature_difference', 'max_prediction_difference', 'max_metric_difference', 'max_bootstrap_difference', 'max_permutation_difference'):
        add(key, str(ind[key]) in text)
    for phrase in (
        'Development independent acceptance: **97/97**',
        'test independent acceptance: **153/153**',
        '**4/4 PASS**',
        'not** evidence that CodonFlow-RK beats it',
        'cross-protein, non-synonymous ordinal-expression prediction',
        '`RK-G1 = false`; expensive generator training remains unauthorized.',
        'Functional untouched data were not accessed; no GPU was used.',
        'does not add a confirmatory p-value family',
    ):
        add('boundary_' + phrase[:36], phrase in text)

    failed = [c['name'] for c in checks if not c['pass']]
    report = {
        'status': 'PASS' if not failed else 'FAIL',
        'checks_total': len(checks), 'checks_passed': len(checks) - len(failed),
        'checks_failed': failed, 'checks': checks,
        'test_commit': a.test_commit, 'dev_commit': a.dev_commit,
        'closeout_sha256': sha256(a.closeout),
    }
    Path(a.output).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'checks'}, indent=2))
    raise SystemExit(0 if not failed else 1)


if __name__ == '__main__':
    main()
