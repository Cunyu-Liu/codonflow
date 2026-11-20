#!/usr/bin/env python3
"""Independently verify RK24 manuscript integration and scientific anchors."""
from pathlib import Path
import hashlib
import json

REPO = Path('/home/codonflow-a8-rk')
AUDIT = REPO / 'audits/20261121/RK24/paper'
PAPER = REPO / 'paper/CodonFlow_preprint_A8.md'
EXPECTED_BEFORE = '168042d268da301057d9214393c25c05904c6a64d60bbb88ff265fc2cf8755b6'
EXPECTED_SECTION = 'f23926a336ecc1502e622e228a3cbf7b04577cb757c63e5695afb69a1505a2bd'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    update = json.loads((AUDIT / 'rk24_paper_update_v1.json').read_text())
    source = Path(update['backup']).read_text()
    updated = PAPER.read_text()
    section = (AUDIT / 'rk24_manuscript_section.md').read_text()
    result = json.loads((REPO / 'audits/20261121/RK24/rk24_test_result_v1.json').read_text())
    dev_science = json.loads((REPO / 'audits/20261121/RK24/rk24_dev_independent_verification_v1.json').read_text())
    test_science = json.loads((REPO / 'audits/20261121/RK24/rk24_test_independent_verification_v1.json').read_text())
    histgb = json.loads((REPO / 'audits/20261121/RK24/rk24_test_histgb_comparator_v1.json').read_text())
    prepare = json.loads((AUDIT / 'prepare_check.json').read_text())
    draft = json.loads((AUDIT / 'draft_check.json').read_text())
    status = json.loads((AUDIT / 'status.json').read_text())
    meta = json.loads((AUDIT / 'meta.json').read_text())
    checks = []

    def check(name, condition, detail=None):
        checks.append({'name': name, 'pass': bool(condition), 'detail': detail})

    check('source_hash', hashlib.sha256(source.encode()).hexdigest() == update['before_sha256'] == EXPECTED_BEFORE)
    check('updated_hash', sha(PAPER) == update['after_sha256'])
    check('section_hash', sha(AUDIT / 'rk24_manuscript_section.md') == update['section_sha256'] == EXPECTED_SECTION)
    tail = '\n\nA7 is retained as the prior manuscript snapshot.'
    expected = source.replace('## 7. Discussion', section + '\n## 7. Discussion', 1)
    expected = expected.replace(tail, '\n' + update['evidence_block'] + tail, 1)
    check('only_two_authorized_integrations', expected == updated)
    check('section_635_once', updated.count('### 6.35 The train-only Boël author model established a stronger protein-OOD baseline') == 1)
    check('section_exact', section in updated and section == update['section_body'])
    check('discussion_preserved', updated.index('### 6.35 ') < updated.index('## 7. Discussion'))
    check('references_preserved', source[source.index('## 9. References'):] == updated[updated.index('## 9. References'):])
    check('rk23_section_preserved', source[source.index('### 6.34 '):source.index('## 7. Discussion')] == updated[updated.index('### 6.34 '):updated.index('### 6.35 ')])
    check('non_submittable_preserved', '**non-submittable working manuscript**' in updated)
    check('workflow_prepare', prepare['status'] == 'pass' and prepare['stage'] == 'prepare')
    check('workflow_write', draft['status'] == 'pass' and draft['result']['word_count'] == 699 and not draft['failures'])
    check('workflow_draft_identity', draft['result']['input_sha256'] == EXPECTED_SECTION)
    check('workflow_status', status['status'] == 'PASS' and status['lark'] == 'skipped_by_user')
    check('workflow_scope', meta['mode'] == 'draft' and meta['task_scope'] == 'section' and meta['needs_citation'] == 'no' and meta['output_target'] == 'markdown_only')
    check('final_matches_section', (AUDIT / 'paper_final.md').read_text() == section)
    check('development_acceptance', dev_science['status'] == 'PASS_INDEPENDENT_VERIFICATION' and dev_science['checks_passed'] == dev_science['checks_total'] == 97)
    check('test_acceptance', test_science['status'] == 'PASS_INDEPENDENT_VERIFICATION' and test_science['checks_passed'] == test_science['checks_total'] == 153)
    check('test_scope_flags', result['rk_g1'] is False and result['generator_training_authorized'] is False and result['functional_untouched_accessed'] is False)
    check('test_reuse_disclosed', result['test_reused_not_globally_untouched'] is True and 'protein-OOD test split was reused and is not globally untouched' in updated)
    check('published_coefficients_excluded', result['published_coefficients_used_for_prediction'] is False and 'published coefficients were not used for prediction' in updated)
    check('row_and_cluster_counts', all(x in updated for x in ['5,079, 635, and 634 rows', '398 rows from 364 protein clusters', '206 E0 and 192 E5', '634 rows from 556 clusters']))
    check('inference_contract', all(x in updated for x in ['20,000 protein-cluster bootstrap replicates', '20,000 within-cluster prediction-swap permutations', 'Holm correction across the four tests', 'Holm-adjusted *p* < 0.05']))
    check('model_contract', all(x in updated for x in ['61 single-codon slopes', 'unregularized binary logistic models', 'L2 = 0.01', 'terminal stop codon', 'C-terminal LEHHHHHH tag', 'amino acids 7–16 and 17–32']))
    check('convergence_statement', 'All 61 single-codon fits and all four final models converged' in updated)
    test = result['split_results']['test']
    metrics = test['metrics']
    comparisons = test['primary_inference']['comparisons']
    anchors = [
        f"{metrics['binary']['base']['auc']:.6f}", f"{metrics['binary']['author']['auc']:.6f}",
        f"{metrics['binary']['base']['logloss']:.6f}", f"{metrics['binary']['author']['logloss']:.6f}",
        f"{metrics['multiclass']['base']['spearman']:.6f}", f"{metrics['multiclass']['author']['spearman']:.6f}",
        f"{metrics['multiclass']['base']['mse']:.6f}", f"{metrics['multiclass']['author']['mse']:.6f}",
    ]
    for key in ['binary_delta_auc', 'binary_logloss_improvement', 'multiclass_delta_spearman', 'multiclass_mse_improvement']:
        item = comparisons[key]
        anchors += [f"{item['effect']:+.6f}", f"{item['ci95'][0]:.6f}", f"{item['ci95'][1]:.6f}", f"{item['p_holm']:.6f}"]
    check('primary_numeric_anchors', all(x in updated for x in anchors), anchors)
    check('primary_gate_statement', '4/4 endpoints passed' in updated and 'Every confidence interval excluded zero' in updated and test['primary_inference']['all_four_pass'] is True)
    check('table_7_once', updated.count('**Table 7**') == 1 and '*Frozen Protein-OOD Effects of the Train-Only Boël Author Model*' in updated)
    check('table_direction_note', 'effect is base-plus-UH loss minus author-model loss' in updated and 'positive effects indicate improvement' in updated)
    hist = histgb['metrics']
    effects = histgb['descriptive_effects']
    hist_anchors = [
        f"{hist['rk23_histgb_plus_uh']['spearman']:.6f}", f"{hist['rk23_histgb_plus_uh']['mse']:.6f}",
        f"{hist['rk24_author_multiclass']['spearman']:.6f}", f"{hist['rk24_author_multiclass']['mse']:.6f}",
        f"{effects['author_minus_histgb_spearman']:+.6f}", f"{effects['histgb_minus_author_mse']:+.6f}",
    ]
    check('histgb_numeric_anchors', all(x in updated for x in hist_anchors), hist_anchors)
    check('histgb_boundary', 'descriptive HistGB comparator' in updated and 'no additional confirmatory *p* value' in updated and 'did not alter the four-endpoint gate' in updated and histgb['primary_gate_changed'] is False)
    check('logistic_crosscheck', histgb['base_logistic_crosscheck_max_abs_difference'] == 0 and 'identical to the frozen RK23 logistic predictions' in updated)
    check('independent_acceptance_text', '97/97 checks' in updated and '153/153 checks' in updated and 'without importing the RK07, RK23, or RK24 production modules' in updated)
    difference_anchors = ['7.216 × 10⁻¹⁶', '2.474 × 10⁻⁹', '5.402 × 10⁻¹¹', '3.042 × 10⁻¹⁰', '2.148 × 10⁻¹⁰']
    check('independent_difference_anchors', all(x in updated for x in difference_anchors), difference_anchors)
    check('independent_difference_values', test_science['max_static_feature_difference'] < 1e-15 and test_science['max_prediction_difference'] < 3e-9 and test_science['max_metric_difference'] < 1e-10 and test_science['max_bootstrap_difference'] < 4e-10 and test_science['max_permutation_difference'] < 3e-10)
    check('verifier_history', '12/12 synthetic tests' in updated and 'label-field mapping and verifier interfaces' in updated and 'none changed the frozen scientific definitions or accepted outputs' in updated)
    check('limited_scope_claim', 'train-only author-structure model outperformed the frozen base-plus-UH comparator' in updated and 'cross-protein, nonsynonymous ordinal-expression benchmark' in updated)
    check('no_codonflow_superiority', 'not evidence that CodonFlow-RK has outperformed the author model' in updated)
    check('closed_scientific_gates', all(x in updated for x in ['RK-G1 remains false', 'expensive generator training remains unauthorized', 'functional untouched data were not accessed', 'manuscript remains non-submittable']))
    check('mechanism_boundary', all(x in updated for x in ['does not establish fixed-protein synonymous causality', 'translation velocity', 'mRNA decay', 'complete spatial-coupling mechanism', 'external SOTA']))
    for item in update['evidence']:
        path = Path(item['path'])
        check('evidence_' + item['name'], path.is_file() and sha(path) == item['sha256'] and f"| {item['name']} | `{item['sha256']}` |" in updated)
    check('evidence_row_count', len(update['evidence']) == 16)
    expected_flags = {
        'author_structure_superiority_supported_limited_scope': True,
        'codonflow_rk_superiority_supported': False,
        'fixed_protein_synonymous_mechanism_supported': False,
        'functional_untouched_evaluated': False,
        'rk_g1_pass': False,
        'expensive_generation_authorized': False,
        'submittable': False,
    }
    check('update_scope_flags', update['scientific_flags'] == expected_flags)
    report = {
        'schema': 'a8-rk24-paper-independent-verification-v1',
        'status': 'PASS' if all(x['pass'] for x in checks) else 'FAIL',
        'checks_passed': sum(x['pass'] for x in checks),
        'checks_total': len(checks),
        'checks': checks,
        'before_sha256': update['before_sha256'],
        'after_sha256': update['after_sha256'],
        'section_sha256': update['section_sha256'],
        'scientific_flags': update['scientific_flags'],
    }
    (AUDIT / 'rk24_paper_independent_verification_v1.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': report['status'], 'checks_passed': report['checks_passed'], 'checks_total': report['checks_total'], 'failed': [x for x in checks if not x['pass']]}, indent=2, ensure_ascii=False))
    if report['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
