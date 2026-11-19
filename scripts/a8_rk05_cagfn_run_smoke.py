#!/usr/bin/env python3
"""Run an unmodified, bounded CAGFN training/generation smoke with raw evidence."""
import argparse, hashlib, json, os, platform, subprocess, sys, time
from pathlib import Path

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def dump(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--protocol',required=True)
    ap.add_argument('--python',required=True)
    ap.add_argument('--report',required=True)
    a=ap.parse_args()
    python_path=str(Path(a.python).absolute())
    protocol_path=Path(a.protocol).resolve(); protocol=json.loads(protocol_path.read_text())
    src=Path(protocol['source']['source_directory']).resolve()
    artifact=Path(protocol['bounded_run']['working_directory']).resolve(); artifact.mkdir(parents=True,exist_ok=True)
    progress=Path(protocol['bounded_run']['in_progress_file']); done=Path(protocol['bounded_run']['completion_file'])
    if done.exists(): raise SystemExit(f'Refusing duplicate completed run: {done}')
    if progress.exists(): raise SystemExit(f'Refusing duplicate in-progress run: {progress}')
    if (artifact/'console.log').exists(): raise SystemExit('Refusing to overwrite console.log')
    source_files={}
    for rel in ['main.py','main_conditional.py','env.py','utils.py','reward.py','preprocessor.py','Architecture.py','MFE_calculator.py','CAI_calculator.py','config.yaml']:
        source_files[rel]={'sha256':sha(src/rel),'bytes':(src/rel).stat().st_size}
    entrypoint=protocol['source'].get('entrypoint','main.py')
    cmd=[python_path,str(src/entrypoint),'--config_path',str(src/'config.yaml'),
         '--arch','MLP','--n_iterations','2','--n_samples','20','--batch_size','16',
         '--hidden_dim','256','--n_hidden','4','--embedding_dim','32','--seed','42',
         '--run_name','bounded_smoke']
    env=os.environ.copy();env.update({'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1',
        'OPENBLAS_NUM_THREADS':'1','WANDB_MODE':'offline','WANDB_SILENT':'true','MPLBACKEND':'Agg','PYTHONHASHSEED':'42'})
    start=time.time(); start_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(start))
    base={'schema':'a8.rk05.cagfn_official_smoke_run.v1','task_id':protocol['task_id'],
          'protocol_sha256':sha(protocol_path),'source':protocol['source'],'source_files':source_files,
          'dependency_recovery':protocol['observed_dependency_recovery'],'command':cmd,'cwd':str(artifact),
          'environment_overrides':{k:env[k] for k in ['CUDA_VISIBLE_DEVICES','OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','WANDB_MODE','WANDB_SILENT','MPLBACKEND','PYTHONHASHSEED']},
          'start_time_utc':start_utc,'python':sys.version,'platform':platform.platform(),
          'status':'IN_PROGRESS','claim_boundaries':protocol['claim_boundaries']}
    dump(progress,base)
    with (artifact/'console.log').open('wb') as log:
        proc=subprocess.Popen(cmd,cwd=artifact,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        assert proc.stdout is not None
        for chunk in iter(lambda:proc.stdout.read(8192),b''):
            log.write(chunk);log.flush()
        rc=proc.wait()
    end=time.time()
    freeze=subprocess.run([python_path,'-m','pip','freeze'],capture_output=True,text=True,check=False)
    (artifact/'environment_freeze.txt').write_text(freeze.stdout+freeze.stderr)
    files=[]
    for p in sorted(artifact.rglob('*')):
        if p.is_file() and p.name not in ['console.log','environment_freeze.txt']:
            files.append({'path':str(p.relative_to(artifact)),'bytes':p.stat().st_size,'sha256':sha(p)})
    report=dict(base);report.update({'status':'COMPLETED_PROCESS' if rc==0 else 'FAILED_PROCESS',
        'returncode':rc,'end_time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(end)),
        'wall_clock_seconds':end-start,'console_log':{'path':str(artifact/'console.log'),'sha256':sha(artifact/'console.log')},
        'environment_freeze':{'path':str(artifact/'environment_freeze.txt'),'sha256':sha(artifact/'environment_freeze.txt')},
        'output_files':files,'scientific_verification_status':'NOT_YET_RUN'})
    dump(a.report,report);dump(done,{'status':report['status'],'report':str(Path(a.report).resolve()),'returncode':rc,'wall_clock_seconds':end-start})
    progress.unlink()
    print(json.dumps({'status':report['status'],'returncode':rc,'wall_clock_seconds':end-start,'output_files':len(files),'report':str(a.report)},indent=2))
    return 0 if rc==0 else 1
if __name__=='__main__': raise SystemExit(main())
