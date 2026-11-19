#!/usr/bin/env python3
"""Verify the exact v22-to-v23 CAGFN manuscript increment without importing updater code."""
import argparse, hashlib, json
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',required=True);ap.add_argument('--update-report',required=True);ap.add_argument('--report',required=True);a=ap.parse_args();repo=Path(a.repo).resolve()
    paper=repo/'paper/CodonFlow_preprint_A8.md';auditp=repo/'paper/a8_rk_paper_sync_audit.json';snap=repo/'paper/snapshots/rk05_cagfn_v23';parent=snap/'CodonFlow_preprint_A8_v22.md';parentaudit=snap/'a8_rk_paper_sync_audit_v22.json';a7=snap/'CodonFlow_preprint_A7.md'
    root=repo/'audits/20261118/RK05';indp=root/'cagfn_official_smoke_independent_v4.json';finp=root/'cagfn_official_smoke_finalization_v1.json';runp=root/'cagfn_official_smoke_v4.json';protop=repo/'configs/a8_rk05_cagfn_official_smoke_protocol_v4.json'
    ind=json.loads(indp.read_text());fin=json.loads(finp.read_text());run=json.loads(runp.read_text());proto=json.loads(protop.read_text());text=paper.read_text();old=parent.read_text();audit=json.loads(auditp.read_text());oldaudit=json.loads(parentaudit.read_text());checks=[]
    def check(name,cond,detail):checks.append({'name':name,'pass':bool(cond),'detail':detail})
    check('parent_v22_hash',sha(parent)=='dd87b75d5b3d73e2db5500921a12d0195ad5b0c299b06ea487f341f6cd40b419',sha(parent))
    check('parent_audit_hash',sha(parentaudit)=='b39f57a006b3aeaa9e46bb781dafad76d5901c9c849dcb4f96dafecd4d2a8f92',sha(parentaudit))
    check('a7_unchanged',sha(a7)==sha(repo/'paper/CodonFlow_preprint_A7.md')=='941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423',sha(a7))
    check('independent_33_pass',ind['status']=='PASS' and ind['checks_passed']==ind['checks_total']==33,f"{ind['checks_passed']}/{ind['checks_total']}")
    check('finalization_22_pass',fin['status']=='PASS_RK05_CAGFN_OFFICIAL_BOUNDED_SMOKE' and fin['checks_passed']==fin['checks_total']==22,f"{fin['checks_passed']}/{fin['checks_total']}")
    start=text.index('### 6.19 CAGFN official-source bounded train-generate-audit chain');end=text.index('## 7. Discussion',start);section=text[start:end]
    check('single_619_section',text.count('### 6.19 ')==1,True)
    stripped=text[:start]+text[end:]
    anchor_lines=[line for line in stripped.splitlines() if line.startswith('| RK05 CAGFN ')]
    check('seven_evidence_anchors',len(anchor_lines)==7,anchor_lines)
    stripped='\n'.join(line for line in stripped.splitlines() if not line.startswith('| RK05 CAGFN ')) + ('\n' if stripped.endswith('\n') else '')
    # The insertion leaves exactly one blank line where the seven rows were removed.
    stripped=stripped.replace('| RK-13 finalization | `cc2f9aa87b7ed511a087313a12e222259b9e3e34713c36835f67ed9c56479a5b` |\n\n\nA7 is retained','| RK-13 finalization | `cc2f9aa87b7ed511a087313a12e222259b9e3e34713c36835f67ed9c56479a5b` |\n\nA7 is retained')
    check('all_prior_manuscript_text_exact',stripped==old,{'current_sha':sha(paper),'parent_sha':sha(parent)})
    required=[proto['source']['commit'],proto['observed_dependency_recovery']['selected_torchgfn_commit'],'TorchGFN 2.1.0','two iterations','20 samples','33-codon','MLP override','20 / 20','99 nt','33/33','22/22','bounded dependency-recovery smoke','not a converged model','not time-matched costs','no functional, OOD, wet-lab or SOTA claim']
    for phrase in required:check('section_phrase_'+phrase,phrase in section,phrase)
    s=ind['summary'];c=ind['cost']
    numeric={'wall':f"{c['total_wall_clock_seconds']:.6f} s",'training':f"{c['training_seconds']:.2f} s",'inference':f"{c['inference_seconds']:.2f} s",'gc':f"{s['mean_gc_percent']:.6f}",'mfe':f"{s['mean_official_rnafolder_mfe_kcal_mol']:.6f}",'cai':f"{s['mean_cai']:.6f}",'ned':f"{s['mean_pairwise_normalized_edit_distance']:.6f}"}
    for k,v in numeric.items():check('numeric_'+k,v in section,v)
    check('source_status_rejected','OpenReview page is marked rejected' in section,True)
    check('mfe_not_vienna',"bundled `RNAFolder`, not the ViennaRNA-based scorer" in section,True)
    check('cai_reference_boundary',"hard-coded human reference set, not each target's natural mRNA" in section,True)
    check('not_in_seven_method_matrix','not entered into the seven-method matrix' in section,True)
    check('no_pretrained_weights','public tree contained no pretrained weights' in section,True)
    check('three_failures_preserved','Three earlier bounded attempts were retained unchanged' in section,True)
    check('non_submittable_retained','non-submittable working manuscript' in text,True)
    check('laajil_reference_preserved',text.count('Laajil, A., et al.')==1 and text.count('https://arxiv.org/abs/2510.03811')==1,True)
    expected_paths=[protop,root/'cagfn_official_smoke_v1.json',root/'cagfn_official_smoke_v2.json',root/'cagfn_official_smoke_v3.json',runp,indp,finp]
    for p,line in zip(expected_paths,anchor_lines):check('anchor_hash_'+p.name,f'`{sha(p)}`' in line,sha(p))
    allowed_changed={'base_v22_paper_sha256','base_v22_audit_sha256','generated_sections','schema_version','pre_rk05_cagfn_snapshot','source_paths','scientific_scope','output_sha256','rk05_cagfn_v23'}
    for k in oldaudit:
        if k not in allowed_changed:check('audit_preserved_'+k,audit.get(k)==oldaudit[k],k)
    check('audit_old_sections_prefix',audit['generated_sections'][:len(oldaudit['generated_sections'])]==oldaudit['generated_sections'],len(oldaudit['generated_sections']))
    check('audit_two_new_sections',audit['generated_sections'][-2:]==['6.19 CAGFN official-source bounded train-generate-audit chain','8.1 RK05 CAGFN evidence anchors'],audit['generated_sections'][-2:])
    check('audit_schema_v18',audit['schema_version']=='a8-rk-paper-sync-v18',audit['schema_version'])
    check('audit_parent_hashes',audit['base_v22_paper_sha256']==sha(parent) and audit['base_v22_audit_sha256']==sha(parentaudit),True)
    check('audit_output_hash',audit['output_sha256']==sha(paper),sha(paper))
    check('audit_source_paths_old_preserved',all(audit['source_paths'][k]==v for k,v in oldaudit['source_paths'].items()),True)
    check('audit_scope_old_preserved',all(audit['scientific_scope'][k]==v for k,v in oldaudit['scientific_scope'].items()),True)
    check('audit_no_sota_submission',audit['scientific_scope']['sota'] is False and audit['scientific_scope']['submittable'] is False,True)
    check('audit_snapshot_hashes',audit['pre_rk05_cagfn_snapshot']['paper_sha256']==sha(parent) and audit['pre_rk05_cagfn_snapshot']['audit_sha256']==sha(parentaudit) and audit['pre_rk05_cagfn_snapshot']['a7_sha256']==sha(a7),True)
    update=json.loads(Path(a.update_report).read_text());check('update_report_hashes',update['paper_sha256']==sha(paper) and update['audit_sha256']==sha(auditp),True)
    passed=sum(c['pass'] for c in checks);status='PASS' if passed==len(checks) else 'FAIL'
    report={'schema':'a8.rk05.cagfn_paper_verification.v1','status':status,'checks_passed':passed,'checks_total':len(checks),'checks':checks,'paper_sha256':sha(paper),'audit_sha256':sha(auditp),'parent_paper_sha256':sha(parent),'parent_audit_sha256':sha(parentaudit),'a7_sha256':sha(a7)}
    Path(a.report).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':status,'checks_passed':passed,'checks_total':len(checks),'paper_sha256':sha(paper),'audit_sha256':sha(auditp)},indent=2));return 0 if status=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
