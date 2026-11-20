#!/usr/bin/env python3
"""Independently verify RK23 manuscript integration and scientific anchors."""
from pathlib import Path
import hashlib
import json

REPO = Path('/home/codonflow-a8-rk')
AUDIT = REPO / 'audits/20261121/RK23/paper'
PAPER = REPO / 'paper/CodonFlow_preprint_A8.md'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    update = json.loads((AUDIT / 'rk23_paper_update_v1.json').read_text())
    source = Path(update['backup']).read_text()
    updated = PAPER.read_text()
    section = (AUDIT / 'rk23_manuscript_section.md').read_text()
    result = json.loads((REPO / 'audits/20261121/RK23/rk23_test_result_v1.json').read_text())
    dev_science = json.loads((REPO / 'audits/20261121/RK23/rk23_dev_independent_verification_v1.json').read_text())
    test_science = json.loads((REPO / 'audits/20261121/RK23/rk23_test_independent_verification_v1.json').read_text())
    prepare = json.loads((AUDIT / 'prepare_check.json').read_text())
    draft = json.loads((AUDIT / 'draft_check.json').read_text())
    status = json.loads((AUDIT / 'status.json').read_text())
    meta = json.loads((AUDIT / 'meta.json').read_text())
    checks = []

    def check(name, condition, detail=None):
        checks.append({'name': name, 'pass': bool(condition), 'detail': detail})

    check('source_hash', hashlib.sha256(source.encode()).hexdigest() == update['before_sha256'] == '5c9f9619a46ed555777f6bc9e986fc873c7ff5674406d93c19d21979155096b6')
    check('updated_hash', sha(PAPER) == update['after_sha256'])
    check('section_hash', sha(AUDIT / 'rk23_manuscript_section.md') == update['section_sha256'] == 'fc02dad4d31ac4f42ad4aca0751c57944cc5af14f1fb1d43bda38c40e05a9125')
    tail = '\n\nA7 is retained as the prior manuscript snapshot.'
    expected = source.replace('## 7. Discussion', section + '\n## 7. Discussion', 1)
    expected = expected.replace(tail, '\n' + update['evidence_block'] + tail, 1)
    check('only_two_authorized_integrations', expected == updated)
    check('section_634_once', updated.count('### 6.34 Boël initiation folding did not improve the frozen protein-OOD comparison') == 1)
    check('section_exact', section in updated and section == update['section_body'])
    check('discussion_preserved', updated.index('### 6.34 ') < updated.index('## 7. Discussion'))
    check('references_preserved', source[source.index('## 9. References'):] == updated[updated.index('## 9. References'):])
    check('non_submittable_preserved', '**non-submittable working manuscript**' in updated)
    check('workflow_prepare', prepare['status'] == 'pass' and prepare['stage'] == 'prepare')
    check('workflow_write', draft['status'] == 'pass' and draft['result']['word_count'] == 689 and not draft['failures'])
    check('workflow_status', status['status'] == 'PASS' and status['lark'] == 'skipped_by_user')
    check('workflow_scope', meta['mode'] == 'draft' and meta['task_scope'] == 'section' and meta['needs_citation'] == 'no' and meta['output_target'] == 'markdown_only')
    check('development_acceptance', dev_science['status'] == 'PASS_INDEPENDENT_VERIFICATION' and dev_science['checks_passed'] == dev_science['checks_total'] == 177)
    check('test_acceptance', test_science['status'] == 'PASS_INDEPENDENT_VERIFICATION' and test_science['checks_passed'] == test_science['checks_total'] == 275)
    check('test_scope_flags', result['rk_g1'] is False and result['generator_training_authorized'] is False and result['functional_untouched_accessed'] is False)
    check('test_reuse_disclosed', result['test_reused_not_globally_untouched'] is True and 'reused protein-OOD evaluation' in updated)
    check('row_and_cluster_counts', all(x in updated for x in ['5,079, 635, and 634 rows', '556 protein clusters', '20,000 operational-protein-cluster bootstrap', '20,000 within-cluster prediction-swap permutations']))
    normalized = updated.replace('−', '-')
    test = result['split_results']['test']
    anchors = []
    for model in ['logistic', 'histgb']:
        metrics = test['metrics']
        comparisons = test['primary_inference']['comparisons']
        anchors += [
            f"{metrics['primary_contrast_base_' + model]['spearman']:.6f}",
            f"{metrics['primary_contrast_augmented_' + model]['spearman']:.6f}",
            f"{metrics['primary_contrast_base_' + model]['mse']:.6f}",
            f"{metrics['primary_contrast_augmented_' + model]['mse']:.6f}",
        ]
        for key in [model + '_delta_spearman', model + '_mse_improvement']:
            item = comparisons[key]
            anchors += [f"{item['effect']:+.6f}", f"{item['ci95'][0]:.6f}", f"{item['ci95'][1]:.6f}"]
    check('primary_numeric_anchors', all(x in normalized for x in anchors), anchors)
    check('primary_gate_statement', 'none of the four primary endpoints passed' in updated and 'all Holm-adjusted *p* values were 1.000' in updated and 'PROTEIN_OOD_INITIATION_STRUCTURE_INCREMENT_NOT_FULLY_SUPPORTED' in updated)
    secondary = test['paired_effects']
    secondary_anchors = []
    for model in ['histgb', 'logistic']:
        item = secondary['secondary_descriptive_contrast_' + model]
        secondary_anchors += [f"{item['delta_spearman']:.6f}", f"{item['mse_improvement']:.6f}"]
    check('secondary_numeric_anchors', all(x in normalized for x in secondary_anchors), secondary_anchors)
    check('secondary_boundary', 'descriptive only' in updated and 'outside the preregistered four-test Holm family' in updated and 'cannot reverse the negative primary result' in updated)
    check('source_data_boundary', all(x in updated for x in ['25 rows, 24 unique construct names, and five protein groups', 'RSP_2139-31C-FO/31C-FO', '`p025`, `p50`, and `p975` fields are model prediction quantiles', 'no fixed-protein expression table', 'did not execute that numerical mechanism test']))
    check('independent_acceptance_text', '177/177 checks' in updated and '275/275 checks' in updated and 'differences were zero for predictions, metrics, bootstrap results, and permutation results' in updated)
    check('verifier_history', 'two pre-resampling interface corrections' in updated and '14/14 synthetic tests' in updated and 'verifier-only correction' in updated and 'terminal stop codon' in updated)
    check('distinct_fixed_gfp_scope', 'does not contradict the distinct fixed-GFP development result in Section 6.33' in updated)
    check('closed_scientific_gates', 'RK-G1 remains false' in updated and 'expensive generator training remains unauthorized' in updated and 'functional untouched data were not accessed' in updated and 'manuscript remains non-submittable' in updated)
    for item in update['evidence']:
        path = Path(item['path'])
        check('evidence_' + item['name'], path.is_file() and sha(path) == item['sha256'] and f"| {item['name']} | `{item['sha256']}` |" in updated)
    check('evidence_row_count', len(update['evidence']) == 12)
    check('update_scope_flags', all(value is False for value in update['scientific_flags'].values()))
    report = {
        'schema': 'a8-rk23-paper-independent-verification-v1',
        'status': 'PASS' if all(x['pass'] for x in checks) else 'FAIL',
        'checks_passed': sum(x['pass'] for x in checks),
        'checks_total': len(checks),
        'checks': checks,
        'before_sha256': update['before_sha256'],
        'after_sha256': update['after_sha256'],
        'section_sha256': update['section_sha256'],
        'scientific_flags': update['scientific_flags'],
    }
    (AUDIT / 'rk23_paper_independent_verification_v1.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': report['status'], 'checks_passed': report['checks_passed'], 'checks_total': report['checks_total'], 'failed': [x for x in checks if not x['pass']]}, indent=2, ensure_ascii=False))
    if report['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
