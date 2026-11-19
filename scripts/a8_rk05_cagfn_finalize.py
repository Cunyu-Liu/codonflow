#!/usr/bin/env python3
"""Finalize only the bounded CAGFN official-source smoke evidence."""
import argparse, hashlib, json
from pathlib import Path

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',required=True);ap.add_argument('--source-dir',required=True)
    ap.add_argument('--run-report',required=True);ap.add_argument('--independent-report',required=True);ap.add_argument('--report',required=True)
    a=ap.parse_args();repo=Path(a.repo).resolve();src=Path(a.source_dir).resolve()
    runp=Path(a.run_report).resolve();indp=Path(a.independent_report).resolve();run=json.loads(runp.read_text());ind=json.loads(indp.read_text())
    proto=repo/'configs/a8_rk05_cagfn_official_smoke_protocol_v4.json';protocol=json.loads(proto.read_text())
    checks=[]
    def check(name,cond,detail):checks.append({'name':name,'pass':bool(cond),'detail':detail})
    check('official_source_commit',protocol['source']['commit']=='952ccf9682988ef88cf1251877e918b85fbee9e9',protocol['source'])
    for name,meta in run['source_files'].items():
        p=src/name;check('source_hash_'+name,p.exists() and sha(p)==meta['sha256'],meta['sha256'])
    weights=[str(p.relative_to(src)) for p in src.rglob('*') if p.is_file() and p.suffix.lower() in {'.pth','.pt','.ckpt'}]
    check('no_public_pretrained_weights',len(weights)==0,weights)
    utils=(src/'utils.py').read_text();check('silent_zero_mfe_hazard_disclosed','except Exception as e:' in utils and 'energy = 0' in utils,'Upstream compute_mfe_energy catches exceptions and substitutes zero')
    check('silent_zero_cai_hazard_disclosed','score = 0' in utils,'Upstream compute_cai catches exceptions and substitutes zero')
    check('official_mfe_engine_not_vienna','from MFE_calculator import RNAFolder' in utils and 'import RNA\n' not in utils,'CAGFN bundled RNAFolder')
    check('no_zero_values_in_independent_output',ind['summary']['n_sequences']==20 and all(r['mfe_recomputed']!=0 and r['cai_recomputed']!=0 for r in ind['rows']),True)
    check('run_process_complete',run['status']=='COMPLETED_PROCESS' and run['returncode']==0,run['status'])
    check('independent_all_pass',ind['status']=='PASS' and ind['checks_passed']==ind['checks_total'],f"{ind['checks_passed']}/{ind['checks_total']}")
    check('twenty_unique_valid_sequences',ind['summary']['n_sequences']==20 and ind['summary']['n_unique_sequences']==20 and all(r['protein_identity'] and r['only_terminal_stop'] for r in ind['rows']),ind['summary'])
    check('checkpoint_two_iterations',ind['checkpoint'] is not None and len(ind['checkpoint']['loss'])==2 and len(ind['checkpoint']['reward'])==2,ind['checkpoint'])
    failures=[]
    for v in [1,2,3]:
        p=repo/f'audits/20261118/RK05/cagfn_official_smoke_v{v}.json';x=json.loads(p.read_text());failures.append({'version':v,'path':str(p.relative_to(repo)),'sha256':sha(p),'status':x['status'],'returncode':x['returncode']})
    check('three_failed_attempts_retained',all(x['status']=='FAILED_PROCESS' and x['returncode']!=0 for x in failures),failures)
    check('no_sota_or_full_reproduction_claim',not ind['claim_boundaries']['sota_claim'] and not ind['claim_boundaries']['full_cagfn_reproduction'],ind['claim_boundaries'])
    passed=sum(c['pass'] for c in checks);status='PASS_RK05_CAGFN_OFFICIAL_BOUNDED_SMOKE' if passed==len(checks) else 'FAIL'
    artifacts={str(p.relative_to(repo)):sha(p) for p in [runp,indp,proto,repo/'scripts/a8_rk05_cagfn_run_smoke.py',repo/'scripts/a8_rk05_cagfn_verify_smoke.py']}
    for v in range(1,5):
        p=repo/f'configs/a8_rk05_cagfn_official_smoke_protocol_v{v}.json';artifacts[str(p.relative_to(repo))]=sha(p)
    report={'schema':'a8.rk05.cagfn_official_smoke_finalization.v1','task_id':'RK05.CAGFN_OFFICIAL_BOUNDED_SMOKE',
            'status':status,'checks_passed':passed,'checks_total':len(checks),'checks':checks,'artifacts':artifacts,
            'failure_history':failures,'scientific_result':ind['summary'],'cost':ind['cost'],'checkpoint':ind['checkpoint'],
            'publication_boundary':{'paper':'Curriculum-Augmented GFlowNets for mRNA Design: Enhancing Sequence Generation',
                'arxiv':'https://arxiv.org/abs/2510.03811','openreview':'https://openreview.net/forum?id=lt7QTLnCaF','openreview_status':'rejected',
                'repository':'https://github.com/ayalaajil/GFN_for_mRNA_design','source_commit':protocol['source']['commit'],'pretrained_weights_available':False},
            'completion':{'bounded_official_smoke_closed':status.startswith('PASS'),'actual_training_completed':True,'actual_generation_completed':True,
                'actual_checkpoint_saved':True,'independent_raw_output_verification_completed':True,'full_cagfn_reproduction':False,
                'converged_model_claim':False,'main_model_baseline_matrix_closed':False,'time_matched_comparison':False,
                'functional_ood_closed':False,'sota_claim':False,'paper_update_authorized':status.startswith('PASS'),
                'ppt_update_authorized':status.startswith('PASS')}}
    out=Path(a.report);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':status,'checks_passed':passed,'checks_total':len(checks),'completion':report['completion'],'report':str(out)},indent=2))
    return 0 if status.startswith('PASS') else 1
if __name__=='__main__':raise SystemExit(main())
