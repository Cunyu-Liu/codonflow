#!/usr/bin/env python3
"""Render one release-gated RK32 slide from verified evidence; never alter results."""
import argparse, hashlib, json
from pathlib import Path
from xml.sax.saxutils import escape

BG="rgba(247,248,250,1)"; WHITE="rgba(255,255,255,1)"; INK="rgba(31,41,55,1)"
MUTED="rgba(100,116,139,1)"; LINE="rgba(226,232,240,1)"; TEAL="rgba(13,148,136,1)"
BLUE="rgba(37,99,235,1)"; GREEN="rgba(5,150,105,1)"; ROSE="rgba(225,29,72,1)"
AMBER="rgba(217,119,6,1)"; PALE_TEAL="rgba(204,251,241,1)"; PALE_GREEN="rgba(209,250,229,1)"
PALE_ROSE="rgba(255,228,230,1)"; PALE_AMBER="rgba(254,243,199,1)"
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
PAGES=["design","protocol","decision","ridge","histgb","absolute","reproduction","boundaries"]

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def fmt(v,d=6): return f"{float(v):.{d}g}"
def txt(x,y,w,h,value,size=12,color=INK,bold=False,align="left",wrap=False,text_type="body",valign="middle",line="multiple:1.15"):
    paragraphs=value if isinstance(value,list) else [value]
    body="".join(f"<p>{escape(str(item))}</p>" for item in paragraphs)
    attrs=(f'textType="{text_type}" fontSize="{size}" fontFamily="Inter" color="{color}" textAlign="{align}" '
           f'verticalAlign="{valign}" wrap="{str(wrap).lower()}" lineSpacing="{line}"')
    if bold: attrs+=' bold="true"'
    return f'<shape type="text" topLeftX="{x}" topLeftY="{y}" width="{w}" height="{h}"><content {attrs}>{body}</content></shape>'
def rect(x,y,w,h,fill=WHITE,border=LINE,radius=8):
    b=f'<border color="{border}" width="1"/>' if border else ""
    return f'<shape type="round-rect" topLeftX="{x}" topLeftY="{y}" width="{w}" height="{h}" presetHandlers="{radius}"><fill><fillColor color="{fill}"/></fill>{b}</shape>'
def card(x,y,w,h,label,value,sub,accent=TEAL):
    return rect(x,y,w,h)+txt(x+14,y+9,w-28,15,label.upper(),8.5,MUTED,True)+txt(x+14,y+25,w-28,30,value,21,accent,True)+txt(x+14,y+56,w-28,h-61,sub,8.5,MUTED,wrap=True,valign="top")
def box(x,y,w,h,title,lines,accent=TEAL,fill=WHITE,size=10.2):
    return rect(x,y,w,h,fill=fill)+txt(x+14,y+9,w-28,18,title,10.5,accent,True)+txt(x+14,y+31,w-28,h-39,lines,size,INK,wrap=True,valign="top",line="multiple:1.25")
def table(x,y,widths,row_heights,rows,font=9.2,aligns=None,decision_col=None):
    out=[f'<table topLeftX="{x}" topLeftY="{y}" width="{sum(widths)}" height="{sum(row_heights)}"><colgroup>']
    out += [f'<col width="{w}"/>' for w in widths]; out.append('</colgroup>')
    for r,(height,row) in enumerate(zip(row_heights,rows)):
        out.append(f'<tr height="{height}">')
        for c,value in enumerate(row):
            header=r==0; fill=INK if header else (WHITE if r%2 else "rgba(241,245,249,1)"); color=WHITE if header else INK
            if not header and decision_col==c: color=GREEN if str(value)=="PASS" else ROSE
            align="center" if header else (aligns[c] if aligns else "left")
            bold=' bold="true"' if header or (decision_col==c and not header) else ""
            out.append('<td>'); out.append(f'<fill><fillColor color="{fill}"/></fill>')
            out.append(f'<content textType="body" fontSize="{font}" fontFamily="Inter" color="{color}" textAlign="{align}" verticalAlign="middle" wrap="false" lineSpacing="multiple:1.0"{bold}><p>{escape(str(value))}</p></content></td>')
        out.append('</tr>')
    out.append('</table>'); return "".join(out)
def base(page_number,section,title,subtitle,body,band,source,notes,accent=TEAL):
    band_fill=PALE_GREEN if band.startswith("REPRODUCED") else (PALE_ROSE if "NOT SUPPORTED" in band else PALE_TEAL)
    band_color=GREEN if band.startswith("REPRODUCED") else (ROSE if "NOT SUPPORTED" in band else TEAL)
    data=[txt(48,8,650,14,section.upper(),8.5,accent,True),txt(716,8,196,14,"A8 / RK32 / STRUCTURE",8.5,MUTED,align="right"),
          txt(48,27,864,35,title,23,INK,True),rect(48,72,58,3,fill=accent,border=None,radius=1),txt(48,82,864,18,subtitle,10.2,MUTED),body,
          rect(48,474,864,30,fill=band_fill,border=None,radius=6),txt(62,478,836,21,band,9.8,band_color,True),
          txt(48,512,780,13,source,8.2,MUTED),txt(850,510,62,15,str(page_number),10,INK,True,align="right")]
    note="".join(f"<p>{escape(str(p))}</p>" for p in notes)
    return f'<slide xmlns="https://www.larkoffice.com/sml/2.0"><style><fill><fillColor color="{BG}"/></fill></style><data>{"".join(data)}</data><note><content textType="body" fontSize="12">{note}</content></note></slide>'
def endpoint_rows(endpoints,model):
    rows=[["Structure arm","Metric","Observed effect","95% CI","Holm p","Seeds","Decision"]]
    selected=[r for r in endpoints if r["test"].startswith(model+"__")]
    assert len(selected)==12
    for r in selected:
        _,arm,metric=r["test"].split("__")
        rows.append([ARMS[arm],"Spearman gain" if metric=="spearman_effect" else "MSE improv.",fmt(r["observed_effect"]),
                     f'[{fmt(r["ci95"][0])}, {fmt(r["ci95"][1])}]',fmt(r["p_holm"],4),f'{r["positive_seeds"]}/10',"PASS" if r["pass"] else "FAIL"])
    return rows

def render(a):
    protocol=json.loads(a.protocol.read_text()); preflight=json.loads(a.preflight.read_text()); result=json.loads(a.result.read_text())
    independent=json.loads(a.independent.read_text()); closeout=json.loads(a.closeout.read_text()); reproduction=json.loads(a.reproduction.read_text())
    manuscript=json.loads(a.manuscript_report.read_text()); integration=json.loads(a.manuscript_integration.read_text())
    if closeout["status"]!="PASS_RK32_VERIFIED_RESULT_PACKAGING" or closeout["checks_passed"]!=closeout["checks_total"] or closeout["failed_checks"]: raise RuntimeError("Closeout gate failed")
    if independent["status"]!="PASS" or len(independent["checks"])!=23 or not all(x["pass"] for x in independent["checks"]): raise RuntimeError("Independent gate failed")
    if reproduction["status"]!="PASS_RK32_CLEAN_CHECKOUT_REPRODUCTION" or reproduction["checks_passed"]!=reproduction["checks_total"]: raise RuntimeError("Reproduction gate failed")
    if reproduction["csv_count"]!=6 or reproduction["csv_byte_equal_count"]!=6 or reproduction["npz_array_count"]!=50 or reproduction["npz_exact_equal_count"]!=50: raise RuntimeError("Exact reproduction outputs failed")
    if manuscript["status"]!="PASS_RK32_MANUSCRIPT_REVIEW" or manuscript["checks_passed"]!=18 or manuscript["failed_checks"]: raise RuntimeError("Manuscript gate failed")
    if integration["status"]!="PASS_RK32_MANUSCRIPT_INTEGRATION" or manuscript["manuscript_sha256"]!=integration["manuscript_sha256"]: raise RuntimeError("Manuscript hash binding failed")
    if sha(a.protocol)!=closeout["protocol_sha256"] or sha(a.result)!=closeout["result_sha256"] or sha(a.independent)!=closeout["independent_sha256"] or sha(a.reproduction)!=closeout["reproduction_sha256"]: raise RuntimeError("Scientific hash binding failed")
    if result["primary_tests"]!=closeout["primary_tests"] or result["primary_absolute_performance"]!=closeout["primary_absolute_performance"]: raise RuntimeError("Result/closeout tables differ")
    if preflight["status"]!="PASS_LABEL_FREE_STRUCTURE_PREFLIGHT" or preflight["expression_columns_read"] or preflight["model_fit_performed"]: raise RuntimeError("Preflight boundary failed")
    if result["scientific_conclusion"]!="STRUCTURE_INCREMENT_DEFINITION_DEPENDENT_RETROSPECTIVELY" or len(result["primary_tests"])!=24 or result["total_model_fits"]!=700: raise RuntimeError("Scientific result mismatch")
    source=f'Source: result {closeout["result_sha256"][:12]} · closeout {sha(a.closeout)[:12]} · independent 23/23 · clean 106/106'
    page=a.page; endpoints=result["primary_tests"]
    if page=="design":
        local=preflight["candidate_comparisons"]["local_utr_minus4_cds38__dangles2"]; full=preflight["candidate_comparisons"]["full_mrna__dangles2"]
        cards="".join([card(48,104,204,78,"Exact-CDS groups",str(result["n_exact_cds_groups"]),f'{result["n_measurement_rows"]} measurement rows',TEAL),card(268,104,204,78,"Whole clusters",str(result["n_sequence_clusters"]),"reused RK27 cluster assignments",BLUE),card(488,104,204,78,"Source transcript","864 nt","144-nt 5′UTR + 720-nt CDS",TEAL),card(708,104,204,78,"Real CPU fits",str(result["total_model_fits"]),"10 seeds × 5 folds × 2 × 7",BLUE)])
        arms=box(48,202,424,258,"Six frozen structure arms",[f'• {ARMS[k]}' for k in ARMS],BLUE,WHITE,10.5)
        lineage=box(488,202,424,258,"Label-free preflight and question",["Which structure provenance and coverage add signal","beyond the same CAI + GC + GC3 backbone?","",f'Local closest: r {fmt(local["pearson"],6)} · RMSE {fmt(local["rmse"],5)}',f'Full closest: r {fmt(full["pearson"],6)} · RMSE {fmt(full["rmse"],5)}',"No expression outcomes read during preflight","Source and Vienna retained as separate arms"],TEAL,WHITE,10.3)
        return base(a.page_number,"01 / Structure-definition design","One fixed cohort asks which structure definition adds signal","Label-free provenance audit followed by frozen retrospective whole-cluster OOD",cards+arms+lineage,"RETROSPECTIVE FIXED-GFP SEQUENCE-OOD · NOT INDEPENDENT CONFIRMATION",source,["RK32 compares six structure definitions within one fixed Kudla exact-CDS cohort.","The preflight uses sequence and source structure fields without reading expression outcomes.","All model arms share the same simple sequence backbone and whole-cluster folds.","This is a retrospective analysis, not independent confirmation."],TEAL)
    if page=="protocol":
        cards="".join([card(48,104,204,78,"Evaluation","10 × 5","seeds × whole-cluster folds",BLUE),card(268,104,204,78,"Resampling","20,000","bootstraps and sign-swap permutations",TEAL),card(488,104,204,78,"Primary family","24","6 arms × 2 models × 2 metrics",BLUE),card(708,104,204,78,"Arm gate","4 / 4","all endpoints required for an arm",TEAL)])
        rows=[["Structure arm","Frozen definition","Required evidence"]]
        for arm in ARMS: rows.append([ARMS[arm],DEFINITIONS[arm],"Ridge + HistGB · 2 metrics"])
        definitions=table(48,198,[184,480,200],[26]+[29]*6,rows,8.8,["left","left","left"])
        rule=box(48,406,864,54,"Every endpoint must pass all four",["Observed effect > 0 · 95% CI lower bound > 0 · Holm p < 0.05 across 24 endpoints · at least 8/10 positive seeds"],ROSE,PALE_ROSE,9.8)
        return base(a.page_number,"02 / Frozen protocol","One 24-endpoint family tests structure beyond the same backbone","Frozen primary seed 20261221 · no reclustering · no hyperparameter search · no outcome-selected arms",cards+definitions+rule,"FROZEN PASS RULE · EFFECT + CI + HOLM P + SEED STABILITY",source,["Each structure arm is compared with the same CAI, GC and GC3 backbone.","The twenty-four endpoints form one Holm multiplicity family.","An arm passes only when all four of its endpoints pass every gate.","Observed effects and seed-stability counts are reported separately."],BLUE)
    if page=="decision":
        passed=sum(r["pass"] for r in endpoints); local_pass=sum(x["all_four_pass"] for x in result["arm_results"] if x["arm"] in ["source_local","vienna_local"]); full_pass=sum(x["all_four_pass"] for x in result["arm_results"] if "full" in x["arm"]); mord=next(x for x in result["arm_results"] if x["arm"]=="mordstein_like")
        cards="".join([card(48,104,204,78,"Primary endpoints",f"{passed} / 24","nine passes across all six arms",TEAL),card(268,104,204,78,"Local arms",f"{local_pass} / 2","source and Vienna · all four endpoints",GREEN),card(488,104,204,78,"Full-coverage arms",f"{full_pass} / 3","zero of twelve endpoints pass",ROSE),card(708,104,204,78,"Mordstein-like",f'{mord["n_pass"]} / 4',"only Ridge Spearman gain passes",AMBER)])
        rows=[["Structure arm","Passed endpoints","Arm decision"]]
        for row in result["arm_results"]: rows.append([ARMS[row["arm"]],f'{row["n_pass"]} / 4',"PASS" if row["all_four_pass"] else "FAIL"])
        summary=table(48,198,[400,230,234],[26]+[22]*6,rows,9.5,["left","center","center"],2)
        def endpoint(model,arm,metric): return next(r for r in endpoints if r["test"]==f"{model}__{arm}__{metric}")
        mm=endpoint("ridge","mordstein_like","mse_improvement"); fs=endpoint("ridge","vienna_full_mrna","spearman_effect")
        boxes=box(48,370,424,90,"A positive CI does not override Holm failure",[f'Mordstein-like · Ridge MSE improvement {fmt(mm["observed_effect"])}',f'95% CI [{fmt(mm["ci95"][0])}, {fmt(mm["ci95"][1])}]',f'Holm p {fmt(mm["p_holm"],4)} · endpoint FAIL'],AMBER,PALE_AMBER,10.0)+box(488,370,424,90,"Full-mRNA evidence remains inconclusive",[f'Ridge Spearman gain {fmt(fs["observed_effect"])}',f'95% CI [{fmt(fs["ci95"][0])}, {fmt(fs["ci95"][1])}]',f'Holm p {fmt(fs["p_holm"],4)} · endpoint FAIL'],ROSE,PALE_ROSE,10.0)
        return base(a.page_number,"03 / Primary decision","Structure increments depend on the local coverage definition","Both local arms pass; all three full-coverage arms fail; Mordstein-like passes only one endpoint",cards+summary+boxes,"STRUCTURE_INCREMENT_DEFINITION_DEPENDENT_RETROSPECTIVELY",source,["Both start-aware local structure arms pass all four endpoints.","None of the three full-coverage arms passes an endpoint under the frozen rule.","The Mordstein-like arm passes only Ridge Spearman gain and fails its other three endpoints.","The result supports definition dependence, not a universal structure mechanism."],TEAL)
    if page in ["ridge","histgb"]:
        model_name="Ridge" if page=="ridge" else "HistGB"; rows=endpoint_rows(endpoints,page); passed=sum(r["pass"] for r in endpoints if r["test"].startswith(page+"__"))
        primary=table(48,104,[154,98,104,206,90,72,140],[28]+[27]*12,rows,8.2,["left","left","right","center","right","center","center"],6)
        note=txt(48,460,864,12,"Spearman gain = structure − simple; MSE improvement = simple − structure. All 12 rows join the same 24-endpoint Holm family.",8.6,MUTED)
        return base(a.page_number,"04 / Primary endpoints",f'{model_name} · {passed}/12 endpoints pass',"Frozen primary-seed observed effect · 95% whole-cluster CI · Holm p · 10-seed stability",primary+note,"ALL TWELVE ENDPOINTS SHOWN · NO POST-HOC SELECTION",source,[f'This page reports all twelve primary structure comparisons for {model_name}.',"Observed effects come from the frozen primary seed.","Confidence intervals and permutations resample whole sequence clusters.","The seed column reports stability and cannot override the other acceptance gates."],BLUE)
    if page=="absolute":
        rows=[["Arm","Spearman","MSE"]]
        for r in result["primary_absolute_performance"]: rows.append([ABS_ARMS[r["arm"]],fmt(r["spearman"]),fmt(r["mse"])])
        absolute=table(48,104,[440,212,212],[26]+[21]*15,rows,8.5,["left","right","right"])
        note=txt(48,450,864,14,"Primary-seed absolute scores explain the increments; they are not external SOTA, functional OOD or direct structural measurements.",8.8,MUTED)
        return base(a.page_number,"05 / Absolute performance","Local definitions improve absolute held-out expression prediction",f'Frozen primary seed {result["primary_seed"]} · null + shared simple + six structure arms × two models',absolute+note,"ABSOLUTE SEQUENCE-OOD PERFORMANCE · RETROSPECTIVE FIXED-GFP EXPRESSION ONLY",source,["All fifteen absolute-performance rows come from the frozen primary seed.","Local structure arms outperform their shared simple backbones in this cohort.","The scores help interpret increments but do not replace their confidence intervals or multiplicity control.","They are retrospective expression outcomes, not functional or protein OOD."],BLUE)
    if page=="reproduction":
        cards="".join([card(48,104,204,76,"Real CPU fits",str(result["total_model_fits"]),"per run; independent repeats all",BLUE),card(268,104,204,76,"Independent check","23 / 23","raw data through all inference",GREEN),card(488,104,204,76,"Clean comparison","106 / 106","6 CSV files + 50 arrays exact",GREEN),card(708,104,204,76,"Release closeout",f'{closeout["checks_passed"]} / {closeout["checks_total"]}',f'{closeout["pytest_passed"]} tests passed · {closeout["pytest_skipped"]} skipped',GREEN)])
        evidence=[["Evidence","SHA256 prefix"]]
        for label,value in [("Protocol",closeout["protocol_sha256"]),("Result",closeout["result_sha256"]),("Independent",closeout["independent_sha256"]),("Closeout",sha(a.closeout)),("Reproduction",sha(a.reproduction)),("Manuscript",integration["manuscript_sha256"])]: evidence.append([label,value[:16]])
        ev=table(48,198,[220,280],[26]+[25]*6,evidence,8.8,["left","left"])
        bounds=box(548,198,364,182,"Exact clean-checkout reproduction",[f'Clean head {reproduction["clean_clone_head"][:12]}',"6 CSV files byte-equal","50 inference arrays exactly equal",f'Clean production {reproduction["production_elapsed_seconds_clean"]:.2f} s',f'Clean independent {reproduction["independent_elapsed_seconds_clean"]:.2f} s',"Timings are component costs, not total wall time"],GREEN,WHITE,10.2)
        manuscript_box=box(548,390,364,70,"Report integration",["Manuscript review 18/18 · 24 endpoints + 15 absolute rows",f'GitHub manuscript commit {a.manuscript_commit[:12]}'],TEAL,WHITE,9.6)
        return base(a.page_number,"06 / Reproduction and reports","Exact artifacts reproduce; manuscript values are independently audited",f'Clean checkout {reproduction["clean_clone_head"][:12]} · 6 CSV files + 50 arrays · manuscript {integration["manuscript_sha256"][:12]}',cards+ev+bounds+manuscript_box,"REPRODUCED · INDEPENDENTLY VERIFIED · MANUSCRIPT REVIEW 18/18",source,["A separate clean checkout repeats production and independent verification.","All six CSV files are byte-identical and all fifty inference arrays match exactly.","The manuscript audit checks every table row and preserves all prior manuscript content.","Component timings are not interpreted as total workflow wall time."],GREEN)
    if page=="boundaries":
        cards="".join([card(48,104,204,78,"External SOTA","OPEN","complete comparison not closed by RK32",AMBER),card(268,104,204,78,"Seven-method dense","OPEN","four-method prefixes only",AMBER),card(488,104,204,78,"Time-matched","OPEN","controlled cost comparison open",AMBER),card(708,104,204,78,"Functional untouched","UNREAD","no functional OOD or RK-G1 claim",ROSE)])
        remaining=box(48,202,424,258,"Remaining execution queue · not claimed complete",["• Complete external SOTA and unified time-matched evaluation","• Complete seven-method dense generation-call trajectories","• Full UTR–CDS remap and multispecies VeloHARMO closure","• Real functional OOD and protein-OOD","• Prospective DBTL / wet-lab validation","• Authorized generator work and RK-G1"],AMBER,WHITE,10.3)
        not_claimed=box(488,202,424,258,"What RK32 does not establish",["• No universal structure effect or independent confirmation","• No direct transport of the exact local window to RK28","  Mordstein observed-R1 starts at CDS position 4","  start ATG and four upstream nucleotides are absent","• No protein OOD, generator training or wet-lab result","Local support does not reject every longer-context mechanism"],ROSE,WHITE,10.3)
        return base(a.page_number,"07 / Evidence boundary","RK32 resolves one definition question, not the whole research program","Completed: retrospective analysis + independent verification + exact reproduction + manuscript/PPT records",cards+remaining+not_claimed,"REMAINING TASKS STAY OPEN · LOCAL TRANSPORT AND RK-G1 NOT CLOSED",source,["RK32 closes the specified structure-definition analysis and its reporting chain.","The exact start-aware local window cannot be reconstructed from the current Mordstein observed-R1 fragment.","External SOTA, unified time-matched comparison and complete seven-method dense trajectories remain open.","Functional untouched data remain unread and RK-G1 remains false."],AMBER)
    raise ValueError(page)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ["protocol","preflight","result","independent","closeout","reproduction","manuscript-report","manuscript-integration","output"]: p.add_argument("--"+n,type=Path,required=True)
    p.add_argument("--page",choices=PAGES,required=True); p.add_argument("--page-number",type=int,required=True); p.add_argument("--manuscript-commit",required=True)
    a=p.parse_args(); xml=render(a); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(xml+"\n")
    print(json.dumps({"status":"PASS_RK32_SLIDE_XML","page":a.page,"page_number":a.page_number,"bytes":len(xml.encode()),"output":str(a.output)},indent=2))
if __name__=="__main__": main()
