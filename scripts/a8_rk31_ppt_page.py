#!/usr/bin/env python3
"""Render one release-gated RK31 slide; never compute or alter scientific results."""
import argparse, hashlib, json
from pathlib import Path
from xml.sax.saxutils import escape

BG="rgba(247,248,250,1)"; WHITE="rgba(255,255,255,1)"; INK="rgba(31,41,55,1)"
MUTED="rgba(100,116,139,1)"; LINE="rgba(226,232,240,1)"; TEAL="rgba(13,148,136,1)"
BLUE="rgba(37,99,235,1)"; GREEN="rgba(5,150,105,1)"; ROSE="rgba(225,29,72,1)"
AMBER="rgba(217,119,6,1)"; PALE_TEAL="rgba(204,251,241,1)"; PALE_BLUE="rgba(219,234,254,1)"
PALE_GREEN="rgba(209,250,229,1)"; PALE_ROSE="rgba(255,228,230,1)"
CONTEXTS={"hela_no_intron":"HeLa no intron","hela_with_intron":"HeLa with intron","hek293_no_intron":"HEK293 no intron"}
ARMS={"null":"Null","shared_simple":"Shared simple","shared_full":"Shared full","context_gated_full":"Context-gated full","no_transport_simple":"No-transport simple","no_transport_full":"No-transport full"}
BASELINES=["shared_simple","shared_full","no_transport_simple","no_transport_full"]
PAGES=["design","protocol","decision","hela_no_intron","hela_with_intron","hek293_no_intron","absolute","reproduction","boundaries"]

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
    band_fill=PALE_GREEN if band.startswith("SUPPORTED") else (PALE_ROSE if "NOT SUPPORTED" in band or "FAIL" in band else PALE_TEAL)
    band_color=GREEN if band.startswith("SUPPORTED") else (ROSE if "NOT SUPPORTED" in band or "FAIL" in band else TEAL)
    data=[txt(48,8,650,14,section.upper(),8.5,accent,True),txt(716,8,196,14,"A8 / RK31 / APPLICABILITY",8.5,MUTED,align="right"),
          txt(48,27,864,35,title,23,INK,True),rect(48,72,58,3,fill=accent,border=None,radius=1),txt(48,82,864,18,subtitle,10.2,MUTED),body,
          rect(48,474,864,30,fill=band_fill,border=None,radius=6),txt(62,478,836,21,band,9.8,band_color,True),
          txt(48,512,780,13,source,8.2,MUTED),txt(850,510,62,15,f"{page_number:03d}",10,INK,True,align="right")]
    note="".join(f"<p>{escape(str(p))}</p>" for p in notes)
    return f'<slide xmlns="https://www.larkoffice.com/sml/2.0"><style><fill><fillColor color="{BG}"/></fill></style><data>{"".join(data)}</data><note><content textType="body" fontSize="12">{note}</content></note></slide>'
def endpoint_rows(endpoints,context):
    rows=[["Baseline","Metric","Observed effect","95% CI","Holm p","Seeds","Decision"]]
    selected=[r for r in endpoints if r["context"]==context]
    assert len(selected)==8
    for r in selected:
        rows.append([ARMS[r["baseline"]],"Spearman" if r["metric"]=="spearman_effect" else "MSE improv.",fmt(r["observed_effect"]),
                     f'[{fmt(r["ci95"][0])}, {fmt(r["ci95"][1])}]',fmt(r["p_holm"],4),f'{r["positive_seeds"]}/10',"PASS" if r["pass"] else "FAIL"])
    return rows

def render(a):
    protocol=json.loads(a.protocol.read_text()); result=json.loads(a.result.read_text()); independent=json.loads(a.independent.read_text())
    closeout=json.loads(a.closeout.read_text()); reproduction=json.loads(a.reproduction.read_text())
    manuscript=json.loads(a.manuscript_report.read_text()); integration=json.loads(a.manuscript_integration.read_text())
    if closeout["status"]!="PASS_RK31_VERIFIED_RESULT_PACKAGING" or closeout["checks_passed"]!=22 or closeout["checks_total"]!=22 or closeout["failed_checks"]: raise RuntimeError("Closeout gate failed")
    if independent["status"]!="PASS_INDEPENDENT_VERIFICATION" or independent["checks_passed"]!=177 or independent["checks_total"]!=177 or independent["failed_checks"] or independent["production_module_imported"]: raise RuntimeError("Independent gate failed")
    if reproduction["status"]!="PASS_RK31_CLEAN_CHECKOUT_REPRODUCTION" or reproduction["checks_passed"]!=77 or reproduction["checks_total"]!=77 or reproduction["failed_checks"]: raise RuntimeError("Reproduction gate failed")
    if len(reproduction["csv_files"])!=5 or not all(x["byte_equal"] for x in reproduction["csv_files"].values()) or reproduction["npz_array_count"]!=54 or reproduction["max_array_abs_delta"]!=0.0: raise RuntimeError("Exact reproduction outputs failed")
    if manuscript["status"]!="PASS_RK31_MANUSCRIPT_REVIEW" or manuscript["checks_passed"]!=18 or manuscript["checks_total"]!=18 or manuscript["failed"]: raise RuntimeError("Manuscript gate failed")
    if integration["status"]!="PASS_RK31_MANUSCRIPT_INTEGRATION" or manuscript["manuscript_sha256"]!=integration["manuscript_sha256"]: raise RuntimeError("Manuscript hash binding failed")
    if sha(a.protocol)!=closeout["protocol_sha256"] or sha(a.result)!=closeout["result_sha256"] or sha(a.independent)!=closeout["independent_sha256"]: raise RuntimeError("Scientific hash binding failed")
    if result["primary_endpoints"]!=closeout["primary_endpoints"] or result["primary_absolute_performance"]!=closeout["primary_absolute_performance"]: raise RuntimeError("Result/closeout tables differ")
    if result["known_context_applicability_pass"] or result["gating_over_shared_full_pass"] or any(result["context_status"].values()): raise RuntimeError("Unexpected positive applicability claim")
    source=f'Source: result {closeout["result_sha256"][:12]} · closeout {sha(a.closeout)[:12]} · independent 177/177 · clean 77/77'
    page=a.page; endpoints=result["primary_endpoints"]
    if page=="design":
        cards="".join([card(48,104,204,78,"Fixed cohort",str(result["n_variants"]),"variants · complete matched input",TEAL),card(268,104,204,78,"Whole clusters",str(result["n_clusters"]),"cluster-disjoint folds",BLUE),card(488,104,204,78,"Known contexts","3","HeLa ± intron · HEK293",TEAL),card(708,104,204,78,"Ridge fits",str(result["ridge_fit_count"]),"10 seeds × 5 folds × 9 fits",BLUE)])
        arms=box(48,202,424,258,"Six frozen prediction arms",["• Shared simple: GC3 + GC + CpG + CAI","• Shared full: simple + three MFE features","• Context-gated full: context interactions","• No-transport simple: fit within each context","• No-transport full: fit within each context","• Null: descriptive reference only"],BLUE,WHITE,10.5)
        lineage=box(488,202,424,258,"Question and evidence lineage",["Can context-gated MFE improve variant-OOD prediction","when the same clusters are absent from every context?","","Input: independently accepted RK30 matched-context CSV","No new reads, clustering or outcome-selected variants","Retrospective outcome-known follow-up","Not independent confirmation or unseen-context transport"],TEAL,WHITE,10.5)
        return base(a.page_number,"01 / Applicability design","One variant-OOD question across three known contexts","Explicit context gating is compared with shared and per-context ridge baselines",cards+arms+lineage,"RETROSPECTIVE KNOWN-CONTEXT VARIANT-OOD · NOT INDEPENDENT CONFIRMATION",source,["RK31 asks whether explicit context-dependent MFE slopes improve variant-OOD prediction.","All sequence clusters are held out simultaneously across the three known contexts.","The six model arms and all inference settings were frozen before the real fit.","This is a retrospective follow-up, not independent confirmation or unseen-context transport."],TEAL)
    if page=="protocol":
        cards="".join([card(48,104,204,78,"Evaluation","10 × 5","seeds × whole-cluster folds",BLUE),card(268,104,204,78,"Uncertainty","10,000","whole-cluster bootstraps",TEAL),card(488,104,204,78,"Null test","10,000","cluster sign-swap permutations",BLUE),card(708,104,204,78,"Primary family","24","3 contexts × 4 baselines × 2 metrics",TEAL)])
        rules=box(48,202,424,120,"Every primary PASS requires all four",["1. Primary-seed observed effect > 0","2. 95% CI lower bound > 0","3. Holm-adjusted p < 0.05 across 24 endpoints","4. At least 8/10 seed effects positive"],ROSE,WHITE,10.5)
        features=box(488,202,424,120,"Feature and fit discipline",["Full adds full-300-nt, minimum-window and mean-window MFE","Gating adds six context × MFE interactions","Fold-local scaling · Ridge alpha = 1.0 · no tuning"],BLUE,WHITE,10.5)
        distinction=box(48,338,864,122,"Observed effect and seed stability are different quantities",["Tables report the frozen primary-seed observed effect and its whole-cluster inference.","The seed column is a stability count, not a substitute for observed effect or family-wide significance.","Broad applicability requires all 24 endpoints; gating-over-shared-full also requires its six dedicated comparisons."],TEAL,PALE_TEAL,11)
        return base(a.page_number,"02 / Frozen protocol","The primary endpoint is observed effect, not the 10-seed mean","One 24-endpoint Holm family · no hyperparameter search · no outcome leakage across contexts",cards+rules+features+distinction,"FROZEN PASS RULE · EFFECT + CI + HOLM P + SEED STABILITY",source,["The observed effect comes from the frozen primary seed.","The ten-seed mean is not substituted for that effect in the primary tables.","Every endpoint must pass four criteria, including family-wide Holm significance.","Broad applicability requires all twenty-four endpoints to pass."],BLUE)
    if page=="decision":
        passed=sum(r["pass"] for r in endpoints); context_pass=sum(result["context_status"].values())
        cards="".join([card(48,104,204,78,"Primary endpoints",f"{passed} / 24","full four-part PASS rule",ROSE),card(268,104,204,78,"Contexts",f"{context_pass} / 3","all eight endpoints required",ROSE),card(488,104,204,78,"Gating over shared full","FALSE","six dedicated endpoints not rescued",ROSE),card(708,104,204,78,"RK-G1","FALSE","no functional or generator gate opened",AMBER)])
        rows=[["Context","Passed endpoints","Context decision"]]
        for c in CONTEXTS:
            rows.append([CONTEXTS[c],f'{sum(r["pass"] for r in endpoints if r["context"]==c)} / 8',"PASS" if result["context_status"][c] else "FAIL"])
        summary=table(48,198,[400,230,234],[28]+[38]*3,rows,10.5,["left","center","center"],2)
        adverse=[r for r in endpoints if r["context"]=="hela_with_intron" and r["baseline"]=="no_transport_full" and r["metric"]=="spearman_effect"][0]
        boxes=box(48,342,424,118,"A significant adverse direction remains a failure",[f'HeLa with intron · gated minus no-transport full',f'Spearman observed effect {fmt(adverse["observed_effect"])}',f'95% CI [{fmt(adverse["ci95"][0])}, {fmt(adverse["ci95"][1])}] · Holm p {fmt(adverse["p_holm"],4)}',"0/10 positive seeds · this does not favor gating"],ROSE,PALE_ROSE,10.4)+box(488,342,424,118,"Local positive directions do not rescue the family",["HeLa no intron and HEK293 contain positive gated-vs-shared-full directions.","Their Holm-adjusted p values remain 1.0 in the 24-endpoint family.","No broad gated-applicability claim is supported."],AMBER,WHITE,10.4)
        return base(a.page_number,"03 / Primary decision","Known-context gated MFE applicability is not supported","All 24 primary endpoints are reported; local directions are not extracted as wins",cards+summary+boxes,"KNOWN_CONTEXT_GATED_MFE_APPLICABILITY_NOT_SUPPORTED",source,["No primary endpoint meets the complete frozen PASS rule.","None of the three contexts reaches its eight-endpoint context gate.","The adverse HeLa-with-intron direction remains a failed comparison, not evidence for gating.","The conclusion is limited to this retrospective known-context variant-OOD design."],ROSE)
    if page in CONTEXTS:
        rows=endpoint_rows(endpoints,page); passed=sum(r["pass"] for r in endpoints if r["context"]==page)
        primary=table(48,104,[176,108,110,190,90,76,114],[28]+[38]*8,rows,9.0,["left","left","right","center","right","center","center"],6)
        note=txt(48,444,864,18,"Positive effect favors context-gated full. MSE improvement is baseline MSE minus gated MSE. All eight rows join the same 24-endpoint Holm family.",9.2,MUTED)
        return base(a.page_number,"04 / Primary endpoints",f'{CONTEXTS[page]} · {passed}/8 endpoints pass',"Frozen primary-seed observed effect · 95% whole-cluster CI · Holm p · 10-seed stability",primary+note,"ALL EIGHT ENDPOINTS SHOWN · NO POST-HOC SELECTION",source,[f'This page reports all eight primary comparisons for {CONTEXTS[page]}.',"Observed effect is the frozen primary-seed quantity used by the PASS rule.","Confidence intervals and permutations resample whole sequence clusters.","The seed column reports stability only and cannot override the other gates."],BLUE)
    if page=="absolute":
        rows=[["Context","Arm","Spearman","MSE"]]
        for r in result["primary_absolute_performance"]: rows.append([CONTEXTS[r["context"]],ARMS[r["arm"]],fmt(r["spearman"]),fmt(r["mse"])])
        absolute=table(48,104,[250,320,147,147],[28]+[18]*18,rows,8.8,["left","left","right","right"])
        return base(a.page_number,"05 / Absolute performance","Absolute scores prevent an increment-only interpretation",f'Frozen primary seed {result["primary_seed"]} · six arms × three contexts · identical held-out variants',absolute,"ABSOLUTE VARIANT-OOD PERFORMANCE · NOT EXTERNAL SOTA OR FUNCTIONAL VALIDATION",source,["All eighteen absolute-performance rows come from the frozen primary seed.","Every arm is evaluated on the same held-out variants within each context.","These scores explain the paired increments but do not replace their inference.","They are not external SOTA, functional-untouched or wet-lab results."],BLUE)
    if page=="reproduction":
        cards="".join([card(48,104,204,76,"Real ridge fits",str(result["ridge_fit_count"]),"production and independent re-fit",BLUE),card(268,104,204,76,"Independent check","177 / 177","no production import",GREEN),card(488,104,204,76,"Clean comparison","77 / 77","separate checkout and artifact root",GREEN),card(708,104,204,76,"Release closeout","22 / 22","423 tests passed · 1 skipped",GREEN)])
        evidence=[["Evidence","SHA256 prefix"]]
        for label,value in [("Protocol",closeout["protocol_sha256"]),("Result",closeout["result_sha256"]),("Independent",closeout["independent_sha256"]),("Closeout",sha(a.closeout)),("Reproduction",sha(a.reproduction)),("Manuscript",integration["manuscript_sha256"])]: evidence.append([label,value[:16]])
        ev=table(48,198,[220,280],[26]+[25]*6,evidence,8.8,["left","left"])
        bounds=box(548,198,364,182,"Exact clean-checkout reproduction",[f'Clean head {reproduction["clean_clone_head"][:12]}',"5 CSV files byte-equal","54 inference arrays · maximum absolute delta 0.0",f'Clean production {reproduction["production_elapsed_seconds_clean"]:.2f} s',f'Clean independent {reproduction["independent_elapsed_seconds_clean"]:.2f} s',"Timings are component costs, not total wall time"],GREEN,WHITE,10.2)
        manuscript_box=box(548,390,364,70,"Report integration",["Manuscript review 18/18 · 24 endpoints + 18 absolute rows",f'GitHub manuscript commit {a.manuscript_commit[:12]}'],TEAL,WHITE,9.6)
        return base(a.page_number,"06 / Reproduction and reports","Exact outputs reproduce; manuscript values are independently audited",f'Clean checkout {reproduction["clean_clone_head"][:12]} · 5 CSV files + 54 arrays · manuscript {integration["manuscript_sha256"][:12]}',cards+ev+bounds+manuscript_box,"REPRODUCED · INDEPENDENTLY VERIFIED · MANUSCRIPT REVIEW 18/18",source,["The clean checkout reruns production and the independent verifier in a separate artifact root.","All five CSV files are byte-equal and all fifty-four inference arrays match exactly.","The manuscript audit checks every table value and distinguishes observed effect from seed means.","Component timings are reported without interpreting them as total workflow wall time."],GREEN)
    if page=="boundaries":
        cards="".join([card(48,104,204,78,"External SOTA","OPEN","complete comparison not closed by RK31",AMBER),card(268,104,204,78,"Dense trajectory","MISSING","dense budget-step AUC remains blocked",AMBER),card(488,104,204,78,"Time-matched","OPEN","seven-method unified cost still required",AMBER),card(708,104,204,78,"Functional untouched","UNREAD","no functional OOD or RK-G1 claim",ROSE)])
        remaining=box(48,202,424,258,"Remaining execution queue · not claimed complete",["• Complete external SOTA and actual-set dense trajectories","• Unified seven-method time-matched evaluation","• Full UTR–CDS remap and multispecies VeloHARMO closure","• Real functional OOD and protein-OOD","• Prospective DBTL / wet-lab validation","• Authorized generator work and RK-G1"],AMBER,WHITE,10.5)
        not_claimed=box(488,202,424,258,"What RK31 does not establish",["• No unseen-context transport or independent confirmation","• No causal RNA-structure mechanism","• No translation-velocity, decay or direct RFU claim","• No external SOTA or functional-untouched result","• No generator training or RK-G1 opening","Failure here does not reject every context-dependent mechanism"],ROSE,WHITE,10.5)
        return base(a.page_number,"07 / Evidence boundary","RK31 closes one applicability test, not the whole research program","Completed: retrospective analysis + independent verification + exact reproduction + manuscript/PPT records",cards+remaining+not_claimed,"REMAINING TASKS STAY OPEN · NO FUNCTIONAL, SOTA OR RK-G1 OVERCLAIM",source,["RK31 closes the specified known-context applicability analysis and its reporting chain.","It does not close the full external SOTA, dense-trajectory or unified time-matched tasks.","Functional untouched data remain unread and RK-G1 remains false.","The remaining queue is recorded explicitly rather than being represented as completed science."],AMBER)
    raise ValueError(page)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ["protocol","result","independent","closeout","reproduction","manuscript-report","manuscript-integration","output"]: p.add_argument("--"+n,type=Path,required=True)
    p.add_argument("--page",choices=PAGES,required=True); p.add_argument("--page-number",type=int,required=True); p.add_argument("--manuscript-commit",required=True)
    a=p.parse_args(); xml=render(a); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(xml+"\n")
    print(json.dumps({"status":"PASS_RK31_SLIDE_XML","page":a.page,"page_number":a.page_number,"bytes":len(xml.encode()),"output":str(a.output)},indent=2))
if __name__=="__main__": main()
