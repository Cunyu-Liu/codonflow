#!/usr/bin/env python3
"""Independent raw-output verification for the bounded official CAGFN smoke."""
import argparse, hashlib, importlib.util, json, math, re, sys
from pathlib import Path
import numpy as np
import torch
from Bio.Seq import Seq
from CAI import CAI
from Levenshtein import distance

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod;spec.loader.exec_module(mod);return mod

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--run-report',required=True);ap.add_argument('--protocol',required=True)
    ap.add_argument('--source-dir',required=True);ap.add_argument('--report',required=True)
    ap.add_argument('--parent-reports',nargs='+',required=True)
    a=ap.parse_args(); run_path=Path(a.run_report).resolve();protocol_path=Path(a.protocol).resolve()
    run=json.loads(run_path.read_text());protocol=json.loads(protocol_path.read_text());src=Path(a.source_dir).resolve()
    artifact=Path(protocol['bounded_run']['working_directory']).resolve();checks=[]
    def check(name,cond,detail):
        checks.append({'name':name,'pass':bool(cond),'detail':detail})
    check('run_process_completed',run['status']=='COMPLETED_PROCESS' and run['returncode']==0,{'status':run['status'],'returncode':run['returncode']})
    check('protocol_hash_matches',run['protocol_sha256']==sha(protocol_path),run['protocol_sha256'])
    check('official_unconditional_entrypoint',protocol['source']['entrypoint']=='main.py',protocol['source']['entrypoint'])
    check('source_commit_frozen',protocol['source']['commit']=='952ccf9682988ef88cf1251877e918b85fbee9e9',protocol['source']['commit'])
    check('no_source_modification_allowed',protocol['source']['source_modification_allowed'] is False,False)
    check('bounded_two_iterations',protocol['bounded_run']['training_iterations']==2,2)
    check('bounded_twenty_samples',protocol['bounded_run']['generated_samples']==20,20)
    check('architecture_override_disclosed',protocol['bounded_run']['architecture']=='MLP','CLI --arch MLP; bounded smoke, not exact full-paper reproduction')
    for p in a.parent_reports:
        q=Path(p);x=json.loads(q.read_text());check('parent_failure_retained_'+q.stem,x['status']=='FAILED_PROCESS' and x['returncode']!=0,{'path':str(q),'status':x['status'],'returncode':x['returncode'],'sha256':sha(q)})
    seq_files=sorted(artifact.rglob('generated_sequences_*.txt'))
    check('exactly_one_raw_sequence_file',len(seq_files)==1,[str(x) for x in seq_files])
    if len(seq_files)!=1: raise SystemExit('No unique sequence file')
    seq_path=seq_files[0];raw=seq_path.read_text();rows=[]
    pat=re.compile(r'^Sequence (\d+): ([ACGU]+), Reward: (-?\d+\.\d+), GC Content: (-?\d+\.\d+), MFE: (-?\d+\.\d+), CAI: (-?\d+\.\d+)$')
    for line in raw.splitlines():
        m=pat.fullmatch(line.strip())
        if not m: check('unparsed_raw_line',False,line);continue
        rows.append({'index':int(m.group(1)),'sequence':m.group(2),'reward_printed':float(m.group(3)),
                     'gc_percent_printed':float(m.group(4)),'mfe_printed':float(m.group(5)),'cai_printed':float(m.group(6))})
    check('twenty_rows_parsed',len(rows)==20,len(rows))
    check('row_indices_unique_ordered',[r['index'] for r in rows]==list(range(1,21)),[r['index'] for r in rows])
    check('twenty_unique_sequences',len({r['sequence'] for r in rows})==20,len({r['sequence'] for r in rows}))
    import yaml
    cfg=yaml.safe_load((src/'config.yaml').read_text());target=cfg['protein_seq'];natural=cfg['natural_mRNA_seq']
    check('natural_reference_translation',str(Seq(natural.replace('U','T')).translate(table=1))==target,target)
    mfe_mod=load_module('cagfn_independent_mfe',src/'MFE_calculator.py')
    cai_mod=load_module('cagfn_independent_cai',src/'CAI_calculator.py')
    max_gc_err=max_mfe_err=max_cai_err=0.0;zero_mfe=zero_cai=0
    for r in rows:
        rna=r['sequence'];dna=rna.replace('U','T');protein=str(Seq(dna).translate(table=1))
        r['nt_length']=len(rna);r['protein_identity']=protein==target
        r['start_codon_valid']=rna.startswith('AUG');r['terminal_stop_count']=sum(rna[i:i+3] in {'UAA','UAG','UGA'} for i in range(0,len(rna),3))
        r['only_terminal_stop']=rna[-3:] in {'UAA','UAG','UGA'} and '*' not in protein[:-1]
        r['gc_percent_recomputed']=100.0*sum(c in 'GC' for c in rna)/len(rna)
        sol=mfe_mod.RNAFolder(energies=None,loop_min=4).solve(rna);r['mfe_recomputed']=float(sol.energy())
        r['cai_recomputed']=float(CAI(dna,reference=cai_mod.def_refs))
        r['gc_rounding_abs_error']=abs(r['gc_percent_recomputed']-r['gc_percent_printed'])
        r['mfe_rounding_abs_error']=abs(r['mfe_recomputed']-r['mfe_printed'])
        r['cai_rounding_abs_error']=abs(r['cai_recomputed']-r['cai_printed'])
        max_gc_err=max(max_gc_err,r['gc_rounding_abs_error']);max_mfe_err=max(max_mfe_err,r['mfe_rounding_abs_error']);max_cai_err=max(max_cai_err,r['cai_rounding_abs_error'])
        zero_mfe+=int(r['mfe_recomputed']==0.0);zero_cai+=int(r['cai_recomputed']==0.0)
    check('all_lengths_99_nt',all(r['nt_length']==99 for r in rows),sorted({r['nt_length'] for r in rows}))
    check('all_protein_identity',all(r['protein_identity'] for r in rows),sum(r['protein_identity'] for r in rows))
    check('all_start_augs',all(r['start_codon_valid'] for r in rows),sum(r['start_codon_valid'] for r in rows))
    check('exactly_one_terminal_stop_each',all(r['terminal_stop_count']==1 and r['only_terminal_stop'] for r in rows),[r['terminal_stop_count'] for r in rows])
    check('gc_values_match_rounded_output',max_gc_err<=0.005000001,max_gc_err)
    check('mfe_values_match_rounded_output',max_mfe_err<=0.005000001,max_mfe_err)
    check('cai_values_match_rounded_output',max_cai_err<=0.005000001,max_cai_err)
    check('no_silent_zero_mfe',zero_mfe==0,zero_mfe);check('no_silent_zero_cai',zero_cai==0,zero_cai)
    check('all_metrics_finite',all(math.isfinite(r[k]) for r in rows for k in ['mfe_recomputed','cai_recomputed','gc_percent_recomputed']),True)
    ckpts=sorted(artifact.rglob('trained_gflownet_*.pth'));check('exactly_one_checkpoint',len(ckpts)==1,[str(x) for x in ckpts])
    if len(ckpts)==1:
        ck=torch.load(ckpts[0],map_location='cpu',weights_only=True)
        hist=ck.get('training_history',{});loss=hist.get('loss',[]);reward=hist.get('reward',[])
        check('checkpoint_has_model_state',isinstance(ck.get('model_state'),dict) and len(ck['model_state'])>0,len(ck.get('model_state',{})))
        check('two_finite_training_losses',len(loss)==2 and all(math.isfinite(float(x)) for x in loss),[float(x) for x in loss])
        check('two_finite_training_rewards',len(reward)==2 and all(math.isfinite(float(x)) for x in reward),[float(x) for x in reward])
        checkpoint_summary={'bytes':ckpts[0].stat().st_size,'sha256':sha(ckpts[0]),'loss':[float(x) for x in loss],'reward':[float(x) for x in reward]}
    else: checkpoint_summary=None
    listed={x['path']:x for x in run['output_files']}
    for p in [seq_path]+ckpts:
        rel=str(p.relative_to(artifact));check('raw_hash_matches_run_'+p.name,rel in listed and listed[rel]['sha256']==sha(p),{'path':rel,'sha256':sha(p)})
    log=(artifact/'console.log').read_text()
    mt=re.search(r'Training completed in ([0-9.]+) seconds',log);mi=re.search(r'Inference \(sampling\) completed in ([0-9.]+) seconds',log)
    training_seconds=float(mt.group(1)) if mt else None;inference_seconds=float(mi.group(1)) if mi else None
    check('training_and_inference_times_present',training_seconds is not None and inference_seconds is not None,{'training':training_seconds,'inference':inference_seconds})
    neds=[distance(rows[i]['sequence'],rows[j]['sequence'])/99.0 for i in range(20) for j in range(i+1,20)]
    summary={'n_sequences':len(rows),'n_unique_sequences':len({r['sequence'] for r in rows}),
             'mean_gc_percent':float(np.mean([r['gc_percent_recomputed'] for r in rows])),
             'mean_official_rnafolder_mfe_kcal_mol':float(np.mean([r['mfe_recomputed'] for r in rows])),
             'mean_cai':float(np.mean([r['cai_recomputed'] for r in rows])),
             'mean_pairwise_normalized_edit_distance':float(np.mean(neds)),
             'min_pairwise_normalized_edit_distance':float(np.min(neds)),'max_pairwise_normalized_edit_distance':float(np.max(neds)),
             'max_rounding_errors':{'gc_percent':max_gc_err,'mfe':max_mfe_err,'cai':max_cai_err}}
    passed=sum(c['pass'] for c in checks);status='PASS' if passed==len(checks) else 'FAIL'
    report={'schema':'a8.rk05.cagfn_official_smoke_independent.v1','task_id':protocol['task_id'],
            'status':status,'checks_passed':passed,'checks_total':len(checks),'checks':checks,
            'run_report_sha256':sha(run_path),'protocol_sha256':sha(protocol_path),'raw_sequence_file':{'path':str(seq_path),'sha256':sha(seq_path)},
            'source':protocol['source'],'dependency_recovery':protocol['observed_dependency_recovery'],
            'summary':summary,'checkpoint':checkpoint_summary,
            'cost':{'total_wall_clock_seconds':run['wall_clock_seconds'],'training_seconds':training_seconds,'inference_seconds':inference_seconds,
                    'hardware':'CPU','threads':1,'includes':'Whole process includes imports, W&B offline logging, plotting and serialization; training and inference are separately reported.',
                    'time_matched_comparison':False},
            'rows':rows,'claim_boundaries':{'bounded_smoke_only':True,'official_unconditional_entrypoint_process_completed':True,
                'source_modified':False,'full_cagfn_reproduction':False,'converged_model_claim':False,'sota_claim':False,
                'functional_or_ood_claim':False,'main_model_baseline_matrix_closed':False,'time_matched_comparison':False,
                'mfe_engine':'CAGFN bundled RNAFolder, not ViennaRNA','zero_policy':'Direct external CAI and RNAFolder calls; no silent exception-to-zero fallback.'}}
    out=Path(a.report);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':status,'checks_passed':passed,'checks_total':len(checks),'summary':summary,'cost':report['cost'],'report':str(out)},indent=2))
    return 0 if status=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
