#!/usr/bin/env python3
"""Independently verify the RK21/RK22 manuscript integration and evidence anchors."""
from pathlib import Path
import hashlib,json

REPO=Path('/home/codonflow-a8-rk')
AUDIT=REPO/'audits/20261121/RK22/paper'
PAPER=REPO/'paper/CodonFlow_preprint_A8.md'

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    update=json.loads((AUDIT/'rk22_paper_update_v1.json').read_text())
    source=Path(update['backup']).read_text()
    updated=PAPER.read_text()
    section=(AUDIT/'rk22_manuscript_section.md').read_text()
    body=section.split('\n',1)[1].lstrip()
    summary=json.loads((REPO/'audits/20261121/RK22/rk22_analysis_summary_v1.json').read_text())
    science=json.loads((REPO/'audits/20261121/RK22/rk22_independent_verification_v1.json').read_text())
    recovery=json.loads((REPO/'audits/20261121/RK21/rk21_kudla_independent_verification_v1.json').read_text())
    prepare=json.loads((AUDIT/'prepare_check.json').read_text())
    draft=json.loads((AUDIT/'draft_check.json').read_text())
    status=json.loads((AUDIT/'status.json').read_text())
    checks=[]
    def check(name,condition,detail=None): checks.append({'name':name,'pass':bool(condition),'detail':detail})
    check('source_hash',hashlib.sha256(source.encode()).hexdigest()==update['before_sha256']=='fe92cf4390f9cb79281002f094ca54a6cf79672895d362f4b4d1835c7d18338e')
    check('updated_hash',sha(PAPER)==update['after_sha256'])
    check('section_hash',sha(AUDIT/'rk22_manuscript_section.md')==update['section_sha256']=='43abd8934c992126adbde24735c12d6df2dd3a85e758e41de79eeed626a1ee1a')
    tail='\n\nA7 is retained as the prior manuscript snapshot.'
    expected=source.replace(update['old_data_availability_paragraph'],update['new_data_availability_paragraph'],1)
    expected=expected.replace('## 7. Discussion',body+'\n## 7. Discussion',1)
    expected=expected.replace(tail,'\n'+update['evidence_block']+tail,1)
    check('only_three_authorized_integrations',expected==updated)
    check('old_unavailable_claim_removed','remains unavailable; supporting methods and degenerate oligos' not in updated)
    check('new_data_statement',update['new_data_availability_paragraph'] in updated)
    check('section_632_once',updated.count('### 6.32 Recovery of the row-level fixed-GFP sequence–expression table')==1)
    check('section_633_once',updated.count('### 6.33 Fixed-GFP 5′ MFE adds development signal beyond CAI and GC proxies')==1)
    check('section_exact',body in updated and body==update['section_body'])
    check('discussion_preserved','## 7. Discussion' in updated and updated.index('### 6.33 ') < updated.index('## 7. Discussion'))
    check('references_preserved','## 9. References' in updated and source[source.index('## 9. References'):]==updated[updated.index('## 9. References'):])
    check('non_submittable_preserved','**non-submittable working manuscript**' in updated)
    check('workflow_prepare',prepare['status']=='pass' and prepare['stage']=='prepare')
    check('workflow_write',draft['status']=='pass' and draft['result']['word_count']==698 and not draft['failures'])
    check('workflow_status',status['status']=='PASS' and status['lark']=='skipped_by_user')
    check('draft_mode',json.loads((AUDIT/'meta.json').read_text())['mode']=='draft')
    check('recovery_acceptance',recovery['status']=='PASS_INDEPENDENT_VERIFICATION' and recovery['checks_passed']==recovery['checks_total']==69)
    check('science_acceptance',science['status']=='PASS_INDEPENDENT_VERIFICATION' and science['checks_passed']==science['checks_total']==63)
    check('science_scope',not summary['scientific_flags']['functional_untouched_evaluated'] and not summary['scientific_flags']['rk_g1_pass'] and not summary['scientific_flags']['expensive_generation_authorized'])
    check('recovery_counts',all(x in updated for x in ['154 measurement rows','150 unique sequences','four duplicate pairs','72 measurement rows','71 unique exact CDS','69/69 checks']))
    check('recovery_sequence_facts',all(x in updated for x in ['864 nt long','144-nt 5′ UTR','720-nt CDS','239-aa GFP','43 to 10,606']))
    perf={(x['model'],x['feature_set']):x for x in summary['main']['performance']}
    tests={x['test']:x for x in summary['main']['primary_tests']}
    anchors=[]
    for model in ['ridge','histgb']:
        for features in ['simple','structure']:
            anchors += [f"{perf[(model,features)]['mean_spearman']:.6f}",f"{perf[(model,features)]['mean_mse']:.6f}"]
        anchors += [f"{tests[model+'_spearman_effect']['mean_effect']:+.6f}",f"{tests[model+'_mse_improvement']['mean_effect']:+.6f}"]
        for key in [model+'_spearman_effect',model+'_mse_improvement']:
            anchors += [f"{tests[key]['ci95'][0]:.6f}",f"{tests[key]['ci95'][1]:.6f}"]
    normalized_updated=updated.replace('−','-')
    check('main_numeric_anchors',all(x in normalized_updated for x in anchors),anchors)
    check('main_seed_and_p','10/10 seeds' in updated and 'Holm-adjusted *p* = 0.0078125' in updated)
    tag={x['test']:x for x in summary['tagged']['tests']}
    check('tagged_numeric_anchors',all(x in updated for x in [f"{tag['paired_spearman']['estimate']:.6f}",f"{tag['paired_spearman']['ci95'][0]:.6f}",f"{tag['paired_spearman']['ci95'][1]:.6f}",f"{tag['adjusted_delta_mfe5_coefficient']['estimate']:.6f}",f"{tag['adjusted_delta_mfe5_coefficient']['ci95'][0]:.6f}",f"{tag['adjusted_delta_mfe5_coefficient']['ci95'][1]:.6f}"]))
    check('tagged_p_values','0.0000199998' in updated and '0.0000499975' in updated)
    check('independent_prediction_count','7,500 out-of-fold predictions' in updated and '63/63 checks' in updated)
    check('verifier_history_retained','literal model label `null`' in updated and 'scientific outputs unchanged' in updated)
    check('no_tagged_imputation','no tagged sequence, CAI change, or GC change was imputed' in updated)
    check('no_ood_overclaim','do not show that MFE is the sole causal mediator' in updated and 'establish protein OOD' in updated)
    check('generator_boundary','RK-G1 remains false and expensive generator training remains unauthorized' in updated)
    check('previous_negative_retained','reverse earlier negative results obtained with different proxy endpoints' in updated)
    for item in update['evidence']:
        path=Path(item['path'])
        check('evidence_'+item['name'],path.is_file() and sha(path)==item['sha256'] and f"| {item['name']} | `{item['sha256']}` |" in updated)
    check('evidence_row_count',len(update['evidence'])==10)
    check('update_scope_flags',all(update['scientific_flags'][key] is False for key in ['protein_ood','functional_untouched_evaluated','rk_g1_pass','expensive_generation_authorized','submittable']))
    report={'schema':'a8-rk22-paper-independent-verification-v1','status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','checks_passed':sum(x['pass'] for x in checks),'checks_total':len(checks),'checks':checks,'before_sha256':update['before_sha256'],'after_sha256':update['after_sha256'],'section_sha256':update['section_sha256'],'scientific_flags':update['scientific_flags']}
    (AUDIT/'rk22_paper_independent_verification_v1.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'status':report['status'],'checks_passed':report['checks_passed'],'checks_total':report['checks_total'],'failed':[x for x in checks if not x['pass']]},indent=2,ensure_ascii=False))
    if report['status']!='PASS': raise SystemExit(1)
if __name__=='__main__': main()
