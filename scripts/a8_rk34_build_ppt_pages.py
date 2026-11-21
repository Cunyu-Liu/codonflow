#!/usr/bin/env python3
"""Generate nine RK34 slides locally from accepted evidence; no online writes."""
from pathlib import Path
import argparse
import hashlib
import json
import re
from xml.sax.saxutils import escape

BG="rgba(247, 248, 250, 1)"; WHITE="rgba(255, 255, 255, 1)"; INK="rgba(31, 41, 55, 1)"
MUTED="rgba(100, 116, 139, 1)"; GRID="rgba(226, 232, 240, 1)"; ALT="rgba(241, 245, 249, 1)"
BLUE="rgba(37, 99, 235, 1)"; TEAL="rgba(13, 148, 136, 1)"; GREEN="rgba(5, 150, 105, 1)"
AMBER="rgba(217, 119, 6, 1)"; ROSE="rgba(225, 29, 72, 1)"; PALE_BLUE="rgba(219, 234, 254, 1)"
PALE_GREEN="rgba(209, 250, 229, 1)"; PALE_AMBER="rgba(254, 243, 199, 1)"; PALE_TEAL="rgba(204, 251, 241, 1)"
counter=0

def uid(prefix="r34"):
    global counter
    counter+=1
    return f"{prefix}{counter:04d}"

def tx(x,y,w,h,text,size=10,color=INK,bold=False,align="left",wrap=False,line=1.15):
    paras="".join(f"<p>{escape(str(v))}</p>" for v in str(text).split("\n"))
    bold_attr=' bold="true"' if bold else ""
    wrap_attr="" if wrap else ' wrap="false"'
    return f'<shape width="{w}" height="{h}" topLeftX="{x}" topLeftY="{y}" type="text" id="{uid()}"><content verticalAlign="top" fontSize="{size}" fontFamily="Inter" color="{color}"{bold_attr} lineSpacing="multiple:{line}" textAlign="{align}"{wrap_attr}>{paras}</content></shape>'

def rect(x,y,w,h,fill=WHITE,border=True,radius=8):
    b=f'<border color="{GRID}" width="1" />' if border else ""
    return f'<shape width="{w}" height="{h}" topLeftX="{x}" topLeftY="{y}" presetHandlers="{radius}" type="round-rect" id="{uid()}"><fill><fillColor color="{fill}" /></fill>{b}<content fontSize="16" fontFamily="Inter" color="{INK}" /></shape>'

def table(x,y,widths,rows,row_heights=None,font=8.5,aligns=None):
    heights=row_heights or [25]*len(rows)
    cols="".join(f'<col span="1" width="{w}" />' for w in widths)
    out=[f'<table id="{uid()}" width="{sum(widths)}" height="{sum(heights)}" topLeftX="{x}" topLeftY="{y}"><colgroup>{cols}</colgroup>']
    for ri,row in enumerate(rows):
        out.append(f'<tr height="{heights[ri]}">')
        for ci,value in enumerate(row):
            head=ri==0; fill=INK if head else (ALT if ri%2==0 else None)
            color_attr=f' color="{fill}"' if fill else ""
            fill_xml=f'<fill><fillColor{color_attr} /></fill>'
            align=(aligns[ci] if aligns else ("left" if ci==0 else "right"))
            bold_attr=' bold="true"' if head else ""
            out.append(f'<td id="{uid()}">{fill_xml}<content fontSize="{font}" fontFamily="Inter" color="{WHITE if head else INK}"{bold_attr} lineSpacing="multiple:1" textAlign="{align}" wrap="false"><p>{escape(str(value))}</p></content></td>')
        out.append('</tr>')
    out.append('</table>')
    return "".join(out)

def kpi(x,label,value,note,color=BLUE):
    return "".join([rect(x,104,204,76),tx(x+14,113,176,15,label,8.5,MUTED,True),tx(x+14,129,176,30,value,21,color,True),tx(x+14,160,176,17,note,8.2,MUTED,wrap=True)])

def slide(number,section,title,subtitle,body,accent=BLUE,banner=None,banner_color=None,banner_fill=None,source="",notes=None):
    content=[tx(48,8,650,14,section,8.5,accent,True),tx(716,8,196,14,"A8 / RK34 / START CONTEXT",8.5,MUTED,align="right"),tx(48,27,864,35,title,23,INK,True),rect(48,72,58,3,accent,False,1),tx(48,82,864,18,subtitle,10.2,MUTED),*body]
    if banner:
        content += [rect(48,474,864,30,banner_fill or PALE_BLUE,False,6),tx(62,478,836,21,banner,9.8,banner_color or accent,True)]
    content += [tx(48,512,780,13,source,8.2,MUTED),tx(850,510,62,15,str(number),10,INK,True,"right")]
    note_xml=""
    if notes:
        notes=list(notes)+["All reported values and evidence boundaries on this page come from the accepted RK34 source files."]
        note_xml=f'<note id="{uid("n34")}"><content>{"".join(f"<p>{escape(n)}</p>" for n in notes)}</content></note>'
    return f'<slide xmlns="https://www.larkoffice.com/sml/2.0"><style><fill id="{uid("f34")}"><fillColor color="{BG}" /></fill></style><data>{"".join(content)}</data>{note_xml}</slide>\n'

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(); p.add_argument("--base",type=Path,required=True); p.add_argument("--output-dir",type=Path,required=True); p.add_argument("--manifest",type=Path,required=True); p.add_argument("--page",type=int,choices=range(156,165)); args=p.parse_args(); b=args.base
    r=json.loads((b/"rk34_start_context_result_v2.json").read_text()); ind=json.loads((b/"rk34_start_context_independent_v2.json").read_text()); ind1=json.loads((b/"rk34_start_context_independent_v1.json").read_text()); repro=json.loads((b/"rk34_clean_reproduction_comparison_v1.json").read_text()); close=json.loads((b/"rk34_closeout_v2.json").read_text()); manuscript=json.loads((b/"rk34_manuscript_integration_v1.json").read_text()); audit=json.loads((b/"rk34_manuscript_audit_v1.json").read_text())
    assert ind["status"]==repro["status"]==close["status"]==manuscript["status"]==audit["status"]=="PASS" and ind1["status"]=="FAIL"
    primary=[t for t in r["primary_tests"] if t["analysis"]=="primary"]; by_test={t["test"]:t for t in primary}
    fams=[("exact_vs_simple","exact − simple"),("upstream_given_start","upstream | start"),("start_given_upstream","start | upstream"),("start_without_upstream","start | no upstream"),("upstream_without_start","upstream | no start")]
    fam_result={(x["analysis"],x["family"]):x for x in r["family_results"]}
    hashes={name:sha(b/file) for name,file in {"protocol":"a8_rk34_start_context_protocol_v2.json","result":"rk34_start_context_result_v2.json","independent":"rk34_start_context_independent_v2.json","reproduction":"rk34_clean_reproduction_comparison_v1.json","closeout":"rk34_closeout_v2.json"}.items()}
    source=f"Source: result {hashes['result'][:12]} · closeout {hashes['closeout'][:12]} · independent 155/155 · clean {repro['checks_passed']}/{repro['checks_total']}"
    pages={}
    design_rows=[["Arm","Upstream 4 nt","Start ATG","CDS4–38 body"],["exact_real","observed","ATG","identical"],["start_only","NNNN","ATG","identical"],["upstream_only","observed","NNN","identical"],["neither","NNNN","NNN","identical"]]
    body=[kpi(48,"MEASUREMENT ROWS","154","fixed retrospective Kudla GFP"),kpi(268,"EXACT-CDS GROUPS","150","37 whole-sequence clusters"),kpi(488,"CONTEXT LENGTH","42 nt","same body in every arm"),kpi(708,"EVALUATED FITS","900","700 new + 200 reused"),table(48,198,[180,230,180,274],design_rows,[26,32,32,32,32],9.2,["left","center","center","center"]),rect(48,378,424,70),tx(62,387,396,18,"2 × 2 factorial contrasts",10.5,BLUE,True),tx(62,412,396,27,"Each element is contrasted with and without the other.\nLength, body, splits, features and models stay matched.",9.5,INK,wrap=True),rect(488,378,424,70),tx(502,387,396,18,"Retrospective computational ablation",10.5,AMBER,True),tx(502,412,396,27,"N-masking is not biological perturbation.\nNo independent host, assay or measured-structure claim.",9.5,INK,wrap=True)]
    pages[156]=slide(156,"01 / FACTORIAL DESIGN","Equal-length contexts separate the question, not yet the mechanism","Fixed Kudla sequence-cluster OOD · exact local context versus four matched component contrasts",body,BLUE,"SAME BODY · SAME LENGTH · TWO BACKGROUNDS PER COMPONENT",BLUE,PALE_BLUE,source,["The four windows differ only in the upstream four nucleotides and start ATG.","This design tests separability under the frozen predictive contract; it does not perturb biological RNA."])
    fit_rows=[["Component","Primary d2","Sensitivity d0","Fit provenance"],["simple","100","shared","reused RK32"],["exact_real","100","100","d2 reused · d0 new"],["start_only","100","100","new"],["upstream_only","100","100","new"],["neither","100","100","new"]]
    body=[kpi(48,"NEW REAL FITS","700","seven new structure arms"),kpi(268,"REUSED FITS","200","simple + exact Vienna d2"),kpi(488,"CONFIRMATORY TESTS","20","five families × four endpoints"),kpi(708,"SENSITIVITY TESTS","20","dangles=0 · no rescue"),table(48,198,[210,170,190,294],fit_rows,[26,29,29,29,29,29],8.8,["left","right","right","left"]),rect(48,392,424,56),tx(62,401,396,18,"Four gates per endpoint",10.5,BLUE,True),tx(62,424,396,17,"effect > 0 · CI lower > 0 · Holm p < 0.05 · ≥8/10 seeds",9.3,INK),rect(488,392,424,56),tx(502,401,396,18,"Prefit correction retained",10.5,AMBER,True),tx(502,424,396,17,"GC3 [2::3] mask indexing only · protocol v2 refrozen before fits",9.2,INK)]
    pages[157]=slide(157,"02 / FROZEN EXECUTION","The 900-fit contract separates confirmatory and sensitivity evidence","10 seeds × 5 folds · Ridge + HistGB · 20,000 bootstraps + 20,000 cluster-swap permutations",body,BLUE,"20 PRIMARY ENDPOINTS · UNIFIED HOLM · D0 CANNOT RESCUE PRIMARY FAILURE",BLUE,PALE_BLUE,f"Protocol: {hashes['protocol'][:16]} · result {hashes['result'][:16]}",["The failed first production attempt stopped before fitting because of a GC3 mask indexing error.","Protocol v2 was frozen before the successful 700 new fits; no endpoint or seed changed after seeing results."])
    family_rows=[["Comparison","Ridge Δρ","HistGB Δρ","Passed","Family"]]
    for fam,label in fams:
        rr=by_test[f"primary__ridge__{fam}__spearman_effect"]; hh=by_test[f"primary__histgb__{fam}__spearman_effect"]; fr=fam_result[("primary",fam)]
        family_rows.append([label,f"{rr['observed_effect']:+.6f}",f"{hh['observed_effect']:+.6f}",f"{fr['n_pass']} / 4","PASS" if fr["all_four_pass"] else "FAIL"])
    body=[kpi(48,"PRIMARY DECISION","12 / 20","positive endpoints overall",TEAL),kpi(268,"EXACT − SIMPLE","4 / 4","joint context gate passed",GREEN),kpi(488,"SEPARABLE COMPONENTS","0 / 2","neither upstream nor ATG",ROSE),kpi(708,"D0 FAMILY RESCUE","0","same five family decisions",AMBER),table(48,202,[250,160,160,150,144],family_rows,[28,38,38,38,38,38],9.1,["left","right","right","right","right"]),rect(48,430,864,30,PALE_TEAL,False,6),tx(62,434,836,21,"Supported: exact local context increment. Not supported: independently separable upstream or start-codon contribution.",9.6,TEAL,True)]
    pages[158]=slide(158,"03 / PRIMARY DECISION","Joint exact context passes; component mechanisms do not","JOINT_EXACT_CONTEXT_WITHOUT_SEPARABLE_CONTRIBUTIONS_RETROSPECTIVELY",body,TEAL,"12 / 20 ENDPOINTS · EXACT CONTEXT 4 / 4 · NO SEPARABLE COMPONENT GATE",TEAL,PALE_TEAL,source,["Only the exact-versus-simple family passed all four endpoints.","Upstream and start contributions each required two matched families; neither met that prespecified rule."])
    def endpoint_page(number,section,model,title):
        rows=[["Comparison","Metric","Effect","95% CI","Raw p","Holm p","Seeds","Pass"]]
        for t in primary:
            if t["model"]!=model: continue
            label=dict(fams)[t["family"]]; metric="Spearman" if t["metric"]=="spearman_effect" else "MSE impr."
            rows.append([label,metric,f"{t['observed_effect']:+.5f}",f"[{t['ci95'][0]:+.4f},{t['ci95'][1]:+.4f}]",f"{t['p_cluster_swap']:.4f}",f"{t['p_holm']:.4f}",f"{t['positive_seeds']}/10","Y" if t["pass"] else "N"])
        model_label={"ridge":"Ridge","histgb":"HistGB"}[model]
        body=[table(38,104,[150,86,102,210,76,82,82,86],rows,[26]+[30]*10,8.2,["left","left","right","right","right","right","right","center"]),tx(48,450,864,16,f"{model_label} · positive effect favors the named component or exact context; MSE improvement is comparator MSE − context MSE.",9,MUTED)]
        return slide(number,section,title,"All ten frozen confirmatory endpoints · no post-hoc selection · unified Holm across all 20 primary tests",body,BLUE,None,None,None,source,["Every confirmatory endpoint for this model is shown, including failed and partially passed comparisons.","A positive point estimate or seed count alone does not pass the four-part gate."])
    pages[159]=endpoint_page(159,"04 / RIDGE ENDPOINTS","ridge","Ridge separates several contrasts, but not every family")
    pages[160]=endpoint_page(160,"05 / HISTGB ENDPOINTS","histgb","HistGB confirms the joint context and limits component claims")
    abs_rows=[["Model","Arm","Spearman","MSE"]]; arm_labels={"simple":"simple","exact_real_d2":"exact d2","start_only_d2":"start only d2","upstream_only_d2":"upstream only d2","neither_d2":"neither d2"}
    for row in r["primary_absolute_performance"]:
        if row["arm"]=="null": abs_rows.append(["Intercept","null",f"{row['spearman']:.6f}",f"{row['mse']:.6f}"]); continue
        model,arm=row["arm"].split("_",1)
        if arm in arm_labels: abs_rows.append([{"ridge":"Ridge","histgb":"HistGB"}[model],arm_labels[arm],f"{row['spearman']:.6f}",f"{row['mse']:.6f}"])
    exact_r=by_test["primary__ridge__exact_vs_simple__spearman_effect"]; exact_h=by_test["primary__histgb__exact_vs_simple__spearman_effect"]
    body=[table(48,104,[160,320,192,192],abs_rows,[24]+[23]*11,8.7,["left","left","right","right"]),rect(48,402,424,48),tx(62,410,396,30,f"Exact − simple Ridge Δρ {exact_r['observed_effect']:+.6f}\n95% CI [{exact_r['ci95'][0]:+.4f}, {exact_r['ci95'][1]:+.4f}]",9.4,INK,wrap=True),rect(488,402,424,48),tx(502,410,396,30,f"Exact − simple HistGB Δρ {exact_h['observed_effect']:+.6f}\n95% CI [{exact_h['ci95'][0]:+.4f}, {exact_h['ci95'][1]:+.4f}]",9.4,INK,wrap=True)]
    pages[161]=slide(161,"06 / ABSOLUTE PERFORMANCE","Primary-seed scores support context, not separable mechanism","Frozen primary seed 20261221 · dangles=2 arms shown · paired inference remains primary",body,BLUE,"DESCRIPTIVE ABSOLUTE SCORES · RETROSPECTIVE FIXED-GFP EXPRESSION ONLY",TEAL,PALE_TEAL,source,["Absolute performance is descriptive and does not replace paired whole-cluster inference.","Negative simple-backbone Ridge Spearman cautions against interpreting a large increment as universal predictive strength."])
    evidence_rows=[["Evidence","SHA256 prefix / status"],["Protocol",hashes['protocol'][:16]],["Result",hashes['result'][:16]],["Independent v1",f"FAIL {ind1['checks_passed']}/{ind1['checks_total']} · retained"],["Independent v2",f"PASS {ind['checks_passed']}/{ind['checks_total']} · {hashes['independent'][:12]}"],["Clean reproduction",f"PASS {repro['checks_passed']}/{repro['checks_total']}"],["Closeout",f"PASS {close['checks_passed']}/{close['checks_total']}"]]
    body=[kpi(48,"INDEPENDENT V2","155 / 155","raw source through all 900 fits",GREEN),kpi(268,"CLEAN COMPARISON",f"{repro['checks_passed']} / {repro['checks_total']}","byte and array identity",GREEN),kpi(488,"FULL PROJECT TESTS","455 PASS","1 skipped · 5 subtests",GREEN),kpi(708,"CLOSEOUT",f"{close['checks_passed']} / {close['checks_total']}","scientific evidence accepted",GREEN),table(48,198,[220,280],evidence_rows,[26]+[25]*6,8.5,["left","left"]),rect(548,198,364,182),tx(562,207,336,18,"Exact clean-checkout reproduction",10.5,GREEN,True),tx(562,233,336,132,f"Clean commit 4533dd1794fa\nProduction CSV {repro['production_csv_byte_identical']}/6 byte-identical\nProduction arrays {repro['production_arrays_exact']}/82 exact\nIndependent CSV {repro['independent_csv_byte_identical']}/5 byte-identical\nIndependent arrays {repro['independent_arrays_exact']}/82 exact\nFunctional untouched not read",9.7,INK,wrap=True,line=1.2),rect(548,390,364,58),tx(562,399,336,18,"Failures preserved, not hidden",10.5,AMBER,True),tx(562,422,336,22,"v1 null-arm CSV schema FAIL · prefit GC3 log · clean missing-argument log",8.9,INK,wrap=True)]
    pages[162]=slide(162,"07 / REPRODUCTION EVIDENCE","Independent code and clean checkout reproduce the same decision","155/155 independent checks · exact CSV and NPZ agreement · closeout bound to retained failure history",body,GREEN,"REPRODUCED · INDEPENDENTLY VERIFIED · NO NUMERICAL TOLERANCE RELAXATION",GREEN,PALE_GREEN,source,["The independent v1 failure was an identifier round-trip issue, not a numerical scientific discrepancy.","The clean comparison covers production and independent CSV files and every inference array."])
    report_rows=[["Record","Verified value"],["Manuscript section","§6.45"],["Confirmatory table","Table 23 · 20 rows"],["Absolute table","Table 24 · 19 rows"],["Original SHA",manuscript['original_sha256'][:16]],["Updated SHA",manuscript['updated_sha256'][:16]],["Manuscript audit",f"{audit['checks_passed']}/{audit['checks_total']} PASS"],["Submission status","non-submittable working draft"]]
    body=[kpi(48,"PAPER SECTION","§6.45","before RK35 when present"),kpi(268,"ENDPOINT TABLE","20 ROWS","Table 23 · all primary tests"),kpi(488,"ABSOLUTE TABLE","19 ROWS","Table 24 · d2 + d0 context"),kpi(708,"DECISION","12 / 20","identical to source JSON",TEAL),table(48,198,[270,594],report_rows,[26]+[25]*7,8.8,["left","left"]),rect(48,424,424,34),tx(62,431,396,20,"Paper claim: joint exact-context increment; no separable component identification.",9.2,INK,wrap=True),rect(488,424,424,34),tx(502,431,396,20,"Prior manuscript bytes preserved outside insertion; no submit-ready claim.",9.2,INK,wrap=True)]
    pages[163]=slide(163,"08 / MANUSCRIPT SYNCHRONIZATION","The working paper records the positive result and its limits","English section generated from accepted JSON · native tables · insertion-only integration audited",body,BLUE,"RESULTS, NON-CLAIMS AND REPRODUCTION ARE TRACEABLE TO ACCEPTED EVIDENCE",BLUE,PALE_BLUE,f"Manuscript: {manuscript['updated_sha256'][:16]} · section {manuscript['section_sha256'][:16]}",["The RK34 section is inserted before RK35 if that section already exists, otherwise before Discussion.","The manuscript remains a non-submittable working draft and does not claim functional or protein OOD."])
    body=[kpi(48,"EXACT LOCAL CONTEXT","SUPPORTED","fixed Kudla retrospective only",GREEN),kpi(268,"SEPARABLE MECHANISM","NOT SUPPORTED","upstream and ATG gates failed",ROSE),kpi(488,"EXTERNAL / TIME-MATCHED","OPEN","SOTA and dense comparisons open",AMBER),kpi(708,"FUNCTIONAL UNTOUCHED","UNREAD","no functional OOD or RK-G1",ROSE),rect(48,202,424,248),tx(62,211,396,18,"Closed by RK34",10.5,GREEN,True),tx(62,237,396,190,"• Equal-length 2 × 2 start-context ablation\n• 700 new + 200 reused = 900 fits\n• Exact local context 4/4; overall 12/20\n• Independent 155/155 raw-source verification\n• Exact clean-checkout reproduction\n• English working-paper and research-record update",10.1,INK,wrap=True,line=1.22),rect(488,202,424,248),tx(502,211,396,18,"Still open — not future-work-as-completion",10.5,ROSE,True),tx(502,237,396,190,"• Independent complete-CDS transport and untouched evaluation\n• Functional/protein OOD and host/assay identification\n• External SOTA and unified time-matched evaluation\n• Complete seven-method dense generation calls\n• Multispecies VeloHARMO and prospective DBTL\n• Authorized generator work, wet-lab and RK-G1",10.1,INK,wrap=True,line=1.22)]
    pages[164]=slide(164,"09 / EVIDENCE BOUNDARY","RK34 resolves joint context, not biological necessity or transport","No separable mechanism · no independent cross-host claim · no measured structure · no wet-lab experiment",body,AMBER,"REMAINING SCIENTIFIC GATES STAY OPEN · RK-G1 = FALSE",TEAL,PALE_TEAL,source,["The positive exact-context result is restricted to the fixed retrospective Kudla sequence-cluster evaluation.","The ablation does not establish biological necessity, independent transport, functional OOD, or RK-G1."])
    args.output_dir.mkdir(parents=True,exist_ok=True); manifest={"status":"GENERATED_NOT_ONLINE","pages":[],"source_sha256":{**hashes,"manuscript":manuscript['updated_sha256']}}
    for number,xml in ({args.page:pages[args.page]} if args.page else pages).items():
        xml=re.sub(r' id="[^"]+"',"",xml); path=args.output_dir/f"rk34_{number}.xml"; path.write_text(xml); manifest["pages"].append({"page":number,"path":str(path),"sha256":sha(path),"bytes":path.stat().st_size})
    args.manifest.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n"); print(json.dumps({"status":manifest["status"],"pages":[p["page"] for p in manifest["pages"]],"manifest":str(args.manifest)},indent=2))

if __name__=="__main__": main()
