#!/usr/bin/env python3
"""Independently verify the RK26 section and insertion-only manuscript update."""
from pathlib import Path
import argparse
import hashlib
import json

ORIGINAL_SHA256 = '46db82d54dcc2e87c4f8bf3a71017b8dd9fe921eb18c337b8e81f96784902578'
HEADING = '### 6.37 Fixed-protein single-to-double synonymous OOD was not supported by MAGE pair coverage'
SCIENCE_COMMIT = '6c142514701188efc7cdf79dd99eaf637685434c'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for name in ['original','manuscript','section','paper-final','result','independent','closeout','meta','prepare','draft','status','deliver-log','update-initial-log','update-report','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    original = args.original.read_text()
    manuscript = args.manuscript.read_text()
    section = args.section.read_text()
    paper_final = args.paper_final.read_text()
    result = json.loads(args.result.read_text())
    independent = json.loads(args.independent.read_text())
    closeout = json.loads(args.closeout.read_text())
    meta = json.loads(args.meta.read_text())
    prepare = json.loads(args.prepare.read_text())
    draft = json.loads(args.draft.read_text())
    status = json.loads(args.status.read_text())
    update_report = json.loads(args.update_report.read_text())
    deliver_log = args.deliver_log.read_text()
    update_initial_log = args.update_initial_log.read_text()
    checks = []
    def check(name,condition):
        checks.append({'name':name,'pass':bool(condition)})
    check('original frozen hash',sha(args.original)==ORIGINAL_SHA256)
    check('section occurs once',manuscript.count(section.strip())==1)
    check('section heading once',manuscript.count(HEADING)==1)
    without_section = manuscript.replace('\n'+section.strip()+'\n\n## 7. Discussion','\n## 7. Discussion',1)
    ledger_rows = [line for line in without_section.splitlines() if line.startswith('| RK26 ')]
    recovered = '\n'.join(line for line in without_section.splitlines() if not line.startswith('| RK26 '))+'\n'
    check('nine RK26 evidence rows',len(ledger_rows)==9)
    check('all prior manuscript text unchanged',recovered==original)
    check('paper final byte text equals section',paper_final==section)
    check('paper final hash binds section',sha(args.paper_final)==sha(args.section))
    check('draft mode',meta['mode']=='draft')
    check('Markdown-only target',meta['output_target']=='markdown_only')
    check('no citation task',meta['needs_citation']=='no')
    check('prepare pass',prepare['status']=='pass')
    check('draft pass',draft['status']=='pass')
    check('draft section hash',draft['result']['input_sha256']==sha(args.section))
    check('draft 595 words',draft['result']['word_count']==595)
    check('three-state PASS',status['status']=='PASS')
    check('draft delivery reason',status.get('reason','').startswith('写作检查通过'))
    check('delivery shell failure retained','finish_with_status: command not found' in deliver_log)
    check('initial insertion failure retained','assert recovered == original' in update_initial_log and 'AssertionError' in update_initial_log)
    check('update report pass',update_report['status']=='PASS' and update_report['insertion_only'] is True)
    check('update report manuscript hash',update_report['manuscript_sha256']==sha(args.manuscript))
    check('update report reconstruction',update_report['old_manuscript_reconstruction_exact'] is True)
    check('independent feasibility 42/42',independent['status']=='PASS' and independent['checks_total']==independent['checks_passed']==42 and all(c['pass'] for c in independent['checks']))
    check('closeout 54/54',closeout['status']=='PASS' and closeout['checks_total']==closeout['checks_passed']==54 and all(c['pass'] for c in closeout['checks']))
    check('production result bound',independent['production_report_sha256']==sha(args.result)==closeout['production_result_sha256'])
    check('independent report bound',closeout['independent_report_sha256']==sha(args.independent))
    check('science commit bound',closeout['science_commit']==SCIENCE_COMMIT)
    check('science outcome exact',result['scientific_outcome']=='FIXED_PROTEIN_SINGLE_TO_DOUBLE_SYNONYMOUS_OOD_NOT_SUPPORTED_BY_SAMPLE_COVERAGE')
    check('science no fit or endpoint',result['model_fits']==0 and result['functional_endpoint_evaluations']==0 and result['confidence_intervals_or_p_values']==0)
    check('science splits unread',result['original_mage_33_construct_mechanism_test_accessed'] is False and result['rk04_functional_untouched_split_accessed'] is False)
    check('science no authorization',result['rk_g1_pass'] is False and result['generator_training_authorized'] is False)
    check('retrospective role',result['analysis_role']=='retrospective_data_adequacy_audit_not_a_preregistered_mechanism_experiment')
    check('table caption once',section.count('**Table 9**')==1)
    for pair in result['pair_contexts']:
        label = pair['pair_id'].replace('-', '–')
        expected = f"| {label} | {pair['wt_codon1']};{pair['wt_codon2']} | {pair['rows']:,} | {pair['single_total']} | {pair['double_total']:,} | {pair['single_synonymous']} | {pair['double_synonymous']} | {'PASS' if pair['coverage_rule_pass']==1 else 'FAIL'} |"
        check('manuscript pair row '+pair['pair_id'],expected in section)
    total = f"| Total | — | {result['rows']:,} | {result['record_class_counts']['single_codon_variant_in_pair_assay']} | {result['record_class_counts']['codon_pair_variant']:,} | {result['synonymous_single_variants']} | {result['synonymous_double_variants']} | NOT FEASIBLE |"
    check('manuscript total row',total in section)
    required = [
        'retrospective data-adequacy audit rather than a preregistered mechanism experiment',
        'Neither the original 33-construct MAGE mechanism-test set nor the RK04 functional-untouched split was accessed.',
        'This was a design-feasibility rule, not a power analysis.',
        'Only 6 synonymous single-codon variants and 4 synonymous double-codon variants remained',
        'No model was fitted, no functional endpoint was evaluated, and no confidence interval or *p* value was produced.',
        'this audit is not a negative result about the performance of positional or structural interaction models',
        'Synthetic tests passed 10/10',
        'Independent acceptance passed 42/42 checks',
        'closeout and registry binding passed 54/54 checks',
        'RK-G1 remains false and expensive generator training remains unauthorized',
        'the manuscript remains a non-submittable working draft',
        'do not support the proposed confirmatory cross-context model comparison',
    ]
    for text in required:
        check('required statement: '+text,text in section)
    check('no mechanism success claim','MECHANISM PASS' not in section and 'mechanism increment was supported' not in section)
    evidence = {
        'RK26 frozen pair-feasibility protocol':result['protocol_sha256'],
        'RK26 raw MAGE pair source':result['source']['raw_sha256'],
        'RK26 clean MAGE pair source':result['source']['clean_sha256'],
        'RK26 sequence-only pair facts':result['artifacts']['pair_facts_csv_gz']['sha256'],
        'RK26 pair-feasibility result':sha(args.result),
        'RK26 independent pair-feasibility verification':sha(args.independent),
        'RK26 scientific closeout':closeout['closeout_sha256'],
        'RK26 closeout verification':sha(args.closeout),
        'RK26 manuscript section':sha(args.section),
    }
    for name,digest in evidence.items():
        check('evidence row '+name,f'| {name} | `{digest}` |' in ledger_rows)
    failed = [item['name'] for item in checks if not item['pass']]
    report = {
        'schema':'a8-rk26-manuscript-verification-v1','status':'PASS' if not failed else 'FAIL',
        'original_sha256':sha(args.original),'manuscript_sha256':sha(args.manuscript),
        'section_sha256':sha(args.section),'paper_final_sha256':sha(args.paper_final),
        'result_sha256':sha(args.result),'independent_sha256':sha(args.independent),
        'closeout_sha256':sha(args.closeout),'prepare_sha256':sha(args.prepare),
        'draft_sha256':sha(args.draft),'status_sha256':sha(args.status),
        'update_report_sha256':sha(args.update_report),'workflow_status':status['status'],
        'mode':'draft','output_target':'markdown_only','delivery_shell_failure_retained':True,
        'initial_insertion_failure_retained':True,'checks_total':len(checks),
        'checks_passed':len(checks)-len(failed),'failed_checks':failed,'checks':checks,
        'old_manuscript_preserved_exactly':recovered==original,
        'model_fits':0,'functional_endpoint_evaluations':0,'functional_untouched_evaluated':False,
        'rk_g1':False,'generator_training_authorized':False,
    }
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({key:report[key] for key in ['status','checks_total','checks_passed','failed_checks','manuscript_sha256']},indent=2))
    if failed:
        raise SystemExit(1)


if __name__=='__main__':
    main()
