#!/usr/bin/env python3
"""Verify the RK25 manuscript section and insertion-only manuscript update."""
from pathlib import Path
import argparse
import hashlib
import json


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalized(text):
    return text.replace('−','-').replace('–','-')


def scientific(value):
    mantissa, exponent = f'{value:.3e}'.split('e')
    exponent = int(exponent)
    superscript = str(exponent).translate(str.maketrans('-0123456789','⁻⁰¹²³⁴⁵⁶⁷⁸⁹'))
    return f'{mantissa} × 10{superscript}'


def main():
    parser = argparse.ArgumentParser()
    for name in ['original','manuscript','section','paper-final','result','independent','prepare','draft','status','deliver-log','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    original = args.original.read_text()
    manuscript = args.manuscript.read_text()
    section = args.section.read_text()
    paper_final = args.paper_final.read_text()
    result = json.loads(args.result.read_text())
    independent = json.loads(args.independent.read_text())
    prepare = json.loads(args.prepare.read_text())
    draft = json.loads(args.draft.read_text())
    status = json.loads(args.status.read_text())
    deliver_log = args.deliver_log.read_text()
    checks = []
    def check(name,condition):
        checks.append({'name':name,'pass':bool(condition)})
    check('original frozen hash',sha(args.original)=='12949c09f3b4707c87bfdd4486d1ad761762a81264d1b9da6a5df9fbef4d6643')
    check('section occurs once',manuscript.count(section.strip())==1)
    check('section heading once',manuscript.count('### 6.36 The complete author model outperformed all-channel on sequence-OOD')==1)
    without_section = manuscript.replace('\n'+section.strip()+'\n\n## 7. Discussion','\n## 7. Discussion',1)
    ledger_rows = [line for line in without_section.splitlines() if line.startswith('| RK25 ')]
    recovered = '\n'.join(line for line in without_section.splitlines() if not line.startswith('| RK25 '))+'\n'
    check('eight RK25 evidence rows',len(ledger_rows)==8)
    check('all prior manuscript text unchanged',recovered==original)
    check('paper final byte text equals section',paper_final==section)
    check('paper final hash binds section',sha(args.paper_final)==sha(args.section))
    check('prepare pass',prepare['status']=='pass')
    check('draft pass',draft['status']=='pass')
    check('draft section hash',draft['result']['input_sha256']==sha(args.section))
    check('draft 684 words',draft['result']['word_count']==684)
    check('three-state PASS',status['status']=='PASS')
    check('draft mode remains explicit',status.get('reason','').startswith('写作检查通过'))
    check('delivery shell failure retained','finish_with_status: command not found' in deliver_log)
    check('independent OOD 678/678',independent['status']=='PASS' and independent['checks_total']==independent['checks_passed']==678)
    check('production result bound',independent['production_result_sha256']==sha(args.result))
    check('science gates false true false',result['mechanism_vs_author_pass'] is False and result['author_reference_pass'] is True and result['strong_comparator_chain_pass'] is False)
    norm = normalized(section)
    for row in result['confirmatory_comparisons']:
        label = f"{row['left']} {row['right']} {row['metric']}"
        check(f'manuscript point {label}',f"{row['point_delta_mean_per_seed']:+.6f}" in norm)
        check(f'manuscript CI low {label}',f"{row['ci95_low']:.6f}" in norm)
        check(f'manuscript CI high {label}',f"{row['ci95_high']:.6f}" in norm)
    for partition in ['sequence_ood','test']:
        for model in ['ribokinetic_all','boel_author','ridge_all','histgb_all']:
            values = result['metrics'][partition]['mean_across_seeds'][model]
            check(f'{partition} Spearman {model}',f"{values['row_spearman']:.6f}" in norm)
            check(f'{partition} MSE {model}',f"{values['cluster_balanced_mse']:.6f}" in norm)
    for key in ['max_abs_dev_refit_prediction_difference','max_abs_prediction_difference','max_abs_metric_difference','max_abs_bootstrap_difference','max_abs_inference_difference']:
        check(f'independent magnitude {key}',scientific(independent[key]) in section)
    required = [
        'Development acceptance passed 337/337 checks.',
        'passing 678/678 checks.',
        'Scientific closeout and registry binding passed 89/89 checks.',
        'the mechanism component passed 0/2 endpoints',
        'the author-reference component passed 4/4',
        'the strong comparator chain failed',
        'RK-G1 remains false and expensive generator training remains unauthorized',
        'Functional untouched data were not read',
        'the manuscript remains a non-submittable working draft',
        'do not imply a literally zero probability',
        'rather than a majority vote across the six endpoints',
    ]
    for text in required:
        check('required statement: '+text,text in section)
    check('no majority success claim','4/6 PASS' not in section and '4 / 6 PASS' not in section)
    evidence = {
        'RK25 frozen author-mechanism protocol':independent['protocol_sha256'],
        'RK25 frozen sequence-OOD result':independent['production_result_sha256'],
        'RK25 sequence-OOD predictions':independent['predictions_sha256'],
        'RK25 sequence-OOD production bootstrap':independent['production_bootstrap_sha256'],
        'RK25 independent OOD verification':sha(args.independent),
        'RK25 independent OOD bootstrap':independent['independent_bootstrap_sha256'],
        'RK25 scientific closeout':'1d09a3f3896ce71cc95c0dfa12b95367a3ef060b34c478a05406595365bf140e',
        'RK25 manuscript section':sha(args.section),
    }
    for name,digest in evidence.items():
        check('evidence row '+name,f'| {name} | `{digest}` |' in ledger_rows)
    failed = [item['name'] for item in checks if not item['pass']]
    report = {
        'schema':'a8-rk25-manuscript-verification-v1','status':'PASS' if not failed else 'FAIL',
        'original_sha256':sha(args.original),'manuscript_sha256':sha(args.manuscript),
        'section_sha256':sha(args.section),'paper_final_sha256':sha(args.paper_final),
        'result_sha256':sha(args.result),'independent_sha256':sha(args.independent),
        'prepare_sha256':sha(args.prepare),'draft_sha256':sha(args.draft),'status_sha256':sha(args.status),
        'workflow_status':status['status'],'mode':'draft','output_target':'markdown_only',
        'delivery_shell_failure_retained':True,'checks_total':len(checks),
        'checks_passed':len(checks)-len(failed),'failed_checks':failed,'checks':checks,
        'old_manuscript_preserved_exactly':not failed or recovered==original,
        'functional_untouched_evaluated':False,'rk_g1':False,
    }
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({key:report[key] for key in ['status','checks_total','checks_passed','failed_checks','manuscript_sha256']},indent=2))
    if failed:
        raise SystemExit(1)


if __name__=='__main__':
    main()
