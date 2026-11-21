#!/usr/bin/env python3
"""Audit RK31 manuscript/report integration without altering scientific outputs."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

C = {"hela_no_intron":"HeLa no intron","hela_with_intron":"HeLa with intron","hek293_no_intron":"HEK293 no intron"}
A = {"null":"Null","shared_simple":"Shared simple","shared_full":"Shared full","context_gated_full":"Context-gated full","no_transport_simple":"No-transport simple","no_transport_full":"No-transport full"}
M = {"spearman_effect":"ΔSpearman","mse_improvement":"MSE improvement"}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def f(x): return f"{float(x):.9g}"
def ordered_subsequence(original, revised):
    lines=iter(revised.splitlines())
    return all(any(line == candidate for candidate in lines) for line in original.splitlines())

def main():
    p=argparse.ArgumentParser()
    for name in ['original','manuscript','section','academic-final','academic-status','academic-prepare','academic-write','integration','result','output']:
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--manual-reviewed',action='store_true')
    a=p.parse_args(); checks={}
    original=a.original.read_text(); text=a.manuscript.read_text(); section=a.section.read_text()
    integration=json.loads(a.integration.read_text()); result=json.loads(a.result.read_text())
    status=json.loads(a.academic_status.read_text()); prepare=json.loads(a.academic_prepare.read_text()); write=json.loads(a.academic_write.read_text())
    checks['manual_full_section_review']=bool(a.manual_reviewed)
    checks['integration_pass']=integration['status']=='PASS_RK31_MANUSCRIPT_INTEGRATION'
    checks['manuscript_hash_binding']=integration['manuscript_sha256']==sha(a.manuscript) and integration['section_sha256']==sha(a.section)
    checks['original_text_preserved_in_order']=ordered_subsequence(original,text)
    checks['single_rk31_block']=text.count('<!-- A8_RK31_START -->')==1 and text.count('<!-- A8_RK31_END -->')==1 and text.count('### 6.42 ')==1
    checks['rk29_rk30_retained']=text.count('### 6.40 ')==1 and text.count('### 6.41 ')==1
    checks['academic_prepare_write_pass']=prepare['status']=='pass' and write['status']=='pass' and not write['warnings']
    checks['academic_make_status_pass']=status['status']=='PASS' and status['stage']=='deliver'
    stripped='\n'.join(line for line in section.splitlines() if not line.startswith('<!-- A8_RK31_')).strip()+'\n'
    checks['academic_final_exact']=a.academic_final.read_text()==stripped
    endpoint_rows=[line for line in section.splitlines() if line.startswith('| ') and any(line.startswith('| '+c+' |') for c in C.values()) and ('ΔSpearman' in line or 'MSE improvement' in line)]
    checks['primary_24_rows']=len(endpoint_rows)==24
    endpoint_values=True
    for r in result['primary_endpoints']:
        prefix='| '+C[r['context']]+' | '+A[r['baseline']]+' | '+M[r['metric']]+' | '
        rows=[line for line in endpoint_rows if line.startswith(prefix)]
        expected=[f(r['observed_effect']),'['+f(r['ci95'][0])+', '+f(r['ci95'][1])+']',f(r['p_holm']),str(r['positive_seeds'])+'/10','PASS' if r['pass'] else 'FAIL']
        endpoint_values &= len(rows)==1 and all(('| '+value+' |') in rows[0] for value in expected)
    checks['primary_values_and_observed_definition']=bool(endpoint_values) and 'positive primary-seed observed effect' in section
    checks['stale_mean_seed_key_values_absent']=all(x not in section for x in ['0.0608551931','0.0164471707','-0.348546232'])
    absolute_rows=[line for line in section.splitlines() if line.startswith('| ') and any(line.startswith('| '+c+' |') for c in C.values()) and any(('| '+arm+' |') in line for arm in A.values()) and 'ΔSpearman' not in line and 'MSE improvement' not in line]
    checks['absolute_18_rows']=len(absolute_rows)==18
    absolute_values=True
    for r in result['primary_absolute_performance']:
        prefix='| '+C[r['context']]+' | '+A[r['arm']]+' | '
        rows=[line for line in absolute_rows if line.startswith(prefix)]
        absolute_values &= len(rows)==1 and ('| '+f(r['spearman'])+' |') in rows[0] and ('| '+f(r['mse'])+' |') in rows[0]
    checks['absolute_values']=bool(absolute_values)
    checks['scientific_conclusion_and_boundaries']=result['scientific_conclusion'] in section and 'non-submittable working draft' in section and 'unseen-context transport' in section and 'Complete external SOTA' in section and 'RK-G1' in section
    checks['verification_and_reproduction_reported']=all(x in section for x in ['177/177','22/22','77/77','423 tests','five CSV artifacts','54 inference arrays'])
    checks['evidence_anchors_bound']=all(x in text for x in [integration['protocol_sha256'],integration['result_sha256'],integration['independent_sha256'],integration['closeout_sha256'],integration['reproduction_sha256']])
    checks['mordstein_reference_retained']='https://doi.org/10.1016/j.cels.2020.03.001' in text
    failed=[k for k,v in checks.items() if not v]
    report={'status':'PASS_RK31_MANUSCRIPT_REVIEW' if not failed else 'FAIL_RK31_MANUSCRIPT_REVIEW','checks':checks,'checks_passed':sum(checks.values()),'checks_total':len(checks),'failed':failed,'manuscript_sha256':sha(a.manuscript),'section_sha256':sha(a.section),'academic_make_status':status['status'],'academic_deliver_console_note':'Makefile deliver emits a finish_with_status shell error in this isolated copy; make status is retained verbatim and the final Markdown is checked byte-for-byte.','working_draft':True}
    a.output.write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report,indent=2))
    if failed: raise SystemExit(1)
if __name__=='__main__': main()
