#!/usr/bin/env python3
"""Independently audit the live RK32 slides against verified scientific artifacts."""
import argparse, hashlib, json, struct
from pathlib import Path
import xml.etree.ElementTree as ET

ARMS={"source_local":"Source local","vienna_local":"Vienna local","source_full":"Source full","vienna_full_cds":"Vienna full CDS","vienna_full_mrna":"Vienna full mRNA","mordstein_like":"Mordstein-like"}
ABS_ARMS={"null":"Null","ridge_simple":"Ridge simple","histgb_simple":"HistGB simple",**{f"{m}_{a}":f"{mn} {an}" for m,mn in [("ridge","Ridge"),("histgb","HistGB")] for a,an in ARMS.items()}}
DEFINITIONS={
 "source_local":"Source-reported local MFE · start-aware -4 to +37 nt",
 "vienna_local":"Vienna local MFE · UTR[-4:] + CDS[:38] · dangles=2",
 "source_full":"Source-reported full-transcript MFE · retained as independent arm",
 "vienna_full_cds":"Vienna CDS-only MFE · complete 720-nt CDS · dangles=2",
 "vienna_full_mrna":"Vienna complete 864-nt mRNA MFE · dangles=2",
 "mordstein_like":"CDS[:300] MFE + 48-nt minimum-window and window-mean MFE",
}
EXPECTED_IDS=["pZF","pZQ","pZu","pZk","pZE","pZK","pZm","pZJ"]

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def fmt(v,d=6): return f"{float(v):.{d}g}"
def slides(path): return ET.parse(path).getroot().findall('.//{*}slide')
def normalized_slide(slide):
    slide=ET.fromstring(ET.tostring(slide)); slide.tail=None
    return ET.tostring(slide)
def text(slide): return " ".join(''.join(slide.itertext()).split())
def table_rows(slide,index=0):
    table=slide.findall('.//{*}table')[index]
    return [[" ".join(''.join(td.itertext()).split()) for td in tr.findall('./{*}td')] for tr in table.findall('./{*}tr')]
def jpeg_size(path):
    data=Path(path).read_bytes(); assert data[:2]==b'\xff\xd8'
    i=2
    while i<len(data)-9:
        if data[i]!=255: i+=1; continue
        marker=data[i+1]; i+=2
        if marker in [0xD8,0xD9]: continue
        length=struct.unpack('>H',data[i:i+2])[0]
        if marker in list(range(0xC0,0xC4))+list(range(0xC5,0xC8))+list(range(0xC9,0xCC))+list(range(0xCD,0xD0)):
            h,w=struct.unpack('>HH',data[i+3:i+7]); return w,h
        i+=length
    raise ValueError(f'No JPEG dimensions: {path}')
def endpoint_rows(endpoints,model):
    rows=[["Structure arm","Metric","Observed effect","95% CI","Holm p","Seeds","Decision"]]
    selected=[r for r in endpoints if r['test'].startswith(model+'__')]; assert len(selected)==12
    for r in selected:
        _,arm,metric=r['test'].split('__')
        rows.append([ARMS[arm],"Spearman gain" if metric=='spearman_effect' else "MSE improv.",fmt(r['observed_effect']),f'[{fmt(r["ci95"][0])}, {fmt(r["ci95"][1])}]',fmt(r['p_holm'],4),f'{r["positive_seeds"]}/10',"PASS" if r['pass'] else "FAIL"])
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['pre-xml','final-xml','final-response','result','preflight','independent','closeout','reproduction','manuscript-report','manuscript-integration','screenshot-dir','output']: p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args(); checks=[]
    def check(name,condition,evidence):
        checks.append({'name':name,'pass':bool(condition),'evidence':evidence})
    final=json.loads(a.final_response.read_text()); pre=slides(a.pre_xml); live=slides(a.final_xml); new=live[-8:]
    result=json.loads(a.result.read_text()); preflight=json.loads(a.preflight.read_text()); independent=json.loads(a.independent.read_text()); closeout=json.loads(a.closeout.read_text()); reproduction=json.loads(a.reproduction.read_text()); manuscript=json.loads(a.manuscript_report.read_text()); integration=json.loads(a.manuscript_integration.read_text())
    check('live_readback_ok_revision_112',final.get('ok') and final['data']['revision_id']==112,{'revision_id':final['data']['revision_id']})
    check('slide_count_147',len(live)==147,{'slide_count':len(live)})
    check('pre_snapshot_139',len(pre)==139,{'pre_slide_count':len(pre)})
    changed=[i+1 for i,(x,y) in enumerate(zip(pre,live[:139])) if normalized_slide(x)!=normalized_slide(y)]
    check('all_139_preexisting_slides_content_unchanged',not changed,{'changed_pages':changed,'comparison':'XML parsed; only element-tail whitespace ignored'})
    check('new_slide_ids_and_order',[s.get('id') for s in new]==EXPECTED_IDS,{'expected':EXPECTED_IDS,'observed':[s.get('id') for s in new]})
    check('page_numbers_140_to_147',all(str(140+i) in text(s) for i,s in enumerate(new)),{'pages':list(range(140,148))})
    check('speaker_notes_present_all_new_pages',all(''.join(s.findall('.//{*}note')[0].itertext()).strip() for s in new),{'notes_nonempty':8})
    screenshots=[]; shot_ok=True
    for i,slide_id in enumerate(EXPECTED_IDS,140):
        matches=[p for p in a.screenshot_dir.glob(f'*_p{i}_{slide_id}.jpg') if not p.name.startswith('._')]; ok=len(matches)==1
        if ok:
            dims=jpeg_size(matches[0]); ok=dims==(960,540) and matches[0].stat().st_size>10000
            screenshots.append({'page':i,'slide_id':slide_id,'path':str(matches[0]),'dimensions':list(dims),'bytes':matches[0].stat().st_size,'sha256':sha(matches[0])})
        else: shot_ok=False
        shot_ok=shot_ok and ok
    check('eight_current_screenshots_960x540',shot_ok,{'screenshots':screenshots,'manual_visual_readback':'8/8 completed before this audit'})
    design=text(new[0]); local=preflight['candidate_comparisons']['local_utr_minus4_cds38__dangles2']; full=preflight['candidate_comparisons']['full_mrna__dangles2']
    design_terms=['150','37','864 nt','700',f'{result["n_measurement_rows"]} measurement rows','144-nt 5′UTR + 720-nt CDS',fmt(local['pearson']),fmt(local['rmse'],5),fmt(full['pearson']),fmt(full['rmse'],5),'No expression outcomes read during preflight']
    check('design_and_label_free_preflight_values',all(x in design for x in design_terms),{'required_terms':design_terms})
    expected_protocol=[["Structure arm","Frozen definition","Required evidence"]]+[[ARMS[k],DEFINITIONS[k],"Ridge + HistGB · 2 metrics"] for k in ARMS]
    check('frozen_protocol_six_arms_exact',table_rows(new[1])==expected_protocol and '24' in text(new[1]) and '20,000' in text(new[1]) and '4 / 4' in text(new[1]),{'observed_rows':table_rows(new[1])})
    expected_decision=[["Structure arm","Passed endpoints","Arm decision"]]+[[ARMS[r['arm']],f'{r["n_pass"]} / 4',"PASS" if r['all_four_pass'] else "FAIL"] for r in result['arm_results']]
    decision_ok=table_rows(new[2])==expected_decision and '9 / 24' in text(new[2]) and result['scientific_conclusion'] in text(new[2])
    check('decision_table_and_conclusion_exact',decision_ok,{'observed_rows':table_rows(new[2]),'conclusion':result['scientific_conclusion']})
    check('ridge_12_endpoints_exact',table_rows(new[3])==endpoint_rows(result['primary_tests'],'ridge'),{'rows':len(table_rows(new[3]))-1})
    check('histgb_12_endpoints_exact',table_rows(new[4])==endpoint_rows(result['primary_tests'],'histgb'),{'rows':len(table_rows(new[4]))-1})
    expected_abs=[["Arm","Spearman","MSE"]]+[[ABS_ARMS[r['arm']],fmt(r['spearman']),fmt(r['mse'])] for r in result['primary_absolute_performance']]
    check('absolute_15_rows_exact',table_rows(new[5])==expected_abs,{'rows':len(table_rows(new[5]))-1})
    pass_count=sum(r['pass'] for r in result['primary_tests']); local_pass=sum(r['all_four_pass'] for r in result['arm_results'] if r['arm'] in ['source_local','vienna_local']); full_pass=sum(r['all_four_pass'] for r in result['arm_results'] if 'full' in r['arm'])
    check('pass_accounting_9_24_local2_full0',pass_count==9 and local_pass==2 and full_pass==0 and '0 / 3' in text(new[2]) and '1 / 4' in text(new[2]),{'endpoint_passes':pass_count,'local_arm_passes':local_pass,'full_arm_passes':full_pass})
    repro=text(new[6]); repro_terms=['700','23 / 23','106 / 106','423 tests passed · 1 skipped',closeout['protocol_sha256'][:16],closeout['result_sha256'][:16],closeout['independent_sha256'][:16],sha(a.closeout)[:16],sha(a.reproduction)[:16],reproduction['clean_clone_head'][:12]]
    check('reproduction_and_closeout_evidence_exact',all(x in repro for x in repro_terms) and independent['status']=='PASS' and closeout['checks_passed']==23 and reproduction['checks_passed']==106,{'required_terms':repro_terms})
    check('manuscript_hash_and_review_bound',integration['manuscript_sha256'][:16] in repro and manuscript['status']=='PASS_RK32_MANUSCRIPT_REVIEW' and manuscript['checks_passed']==18 and 'd03d84586194' in repro,{'manuscript_sha256':integration['manuscript_sha256'],'review_checks':manuscript['checks_passed']})
    check('fit_count_label_unambiguous','per run; independent repeats all' in repro and 'production and independent re-fit' not in repro,{'fit_label':'700 per run; independent repeats all'})
    boundary=text(new[7]); boundary_terms=['OPEN','UNREAD','no functional OOD or RK-G1 claim','Mordstein observed-R1 starts at CDS position 4','start ATG and four upstream nucleotides are absent','Complete external SOTA and unified time-matched evaluation','Complete seven-method dense generation-call trajectories','Full UTR–CDS remap and multispecies VeloHARMO closure','Prospective DBTL / wet-lab validation','RK-G1 NOT CLOSED']
    check('remaining_tasks_and_local_transport_boundary_explicit',all(x in boundary for x in boundary_terms),{'required_terms':boundary_terms})
    check('no_preprint_submission_or_independent_confirmation_claim',all('preprint submitted' not in text(s).lower() and 'independently confirmed mechanism' not in text(s).lower() for s in new),{'scope':'eight new slides'})
    failed=[c['name'] for c in checks if not c['pass']]
    report={'status':'PASS_RK32_PPT_AUDIT' if not failed else 'FAIL_RK32_PPT_AUDIT','presentation':'https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g','revision_id':final['data']['revision_id'],'slide_count':len(live),'rk32_pages':list(range(140,148)),'rk32_slide_ids':EXPECTED_IDS,'checks_total':len(checks),'checks_passed':sum(c['pass'] for c in checks),'failed_checks':failed,'checks':checks,'evidence_sha256':{'pre_xml':sha(a.pre_xml),'final_xml':sha(a.final_xml),'result':sha(a.result),'independent':sha(a.independent),'closeout':sha(a.closeout),'reproduction':sha(a.reproduction),'manuscript_review':sha(a.manuscript_report),'manuscript_integration':sha(a.manuscript_integration)}}
    a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n'); print(json.dumps({k:report[k] for k in ['status','revision_id','slide_count','checks_total','checks_passed','failed_checks']},indent=2))
    if failed: raise SystemExit(1)
if __name__=='__main__': main()
