#!/usr/bin/env python3
"""Verify the RK22 slide against frozen science and optional online readback."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import xml.etree.ElementTree as ET


def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1048576),b""): h.update(b)
    return h.hexdigest()


def local(tag): return tag.rsplit("}",1)[-1]


def signature(element):
    attrs=[]
    for key,value in element.attrib.items():
        name=local(key)
        if name=="id" or (local(element.tag)=="col" and name=="span" and value=="1"): continue
        attrs.append((name,value))
    text=(element.text or "").strip()
    return (local(element.tag),tuple(sorted(attrs)),text,tuple(signature(c) for c in element))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--candidate",required=True)
    ap.add_argument("--summary",required=True)
    ap.add_argument("--independent",required=True)
    ap.add_argument("--source")
    ap.add_argument("--source-response")
    ap.add_argument("--online")
    ap.add_argument("--online-response")
    ap.add_argument("--add-response")
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    checks=[]
    def check(name,condition,detail=None):
        checks.append({"name":name,"pass":bool(condition),"detail":detail})
    candidate_path=Path(args.candidate)
    candidate=ET.parse(candidate_path).getroot()
    summary=json.loads(Path(args.summary).read_text())
    independent=json.loads(Path(args.independent).read_text())
    check("candidate_root",local(candidate.tag)=="slide")
    check("science_independent_pass",independent["status"]=="PASS_INDEPENDENT_VERIFICATION" and independent["checks_passed"]==independent["checks_total"]==63)
    check("main_science_pass",summary["main"]["development_structure_increment_pass"] is True)
    check("tagged_science_pass",summary["tagged"]["paired_structure_expression_pass"] is True)
    check("science_scope",summary["scientific_flags"]["functional_untouched_evaluated"] is False and summary["scientific_flags"]["rk_g1_pass"] is False and summary["scientific_flags"]["expensive_generation_authorized"] is False)
    text=" ".join(" ".join(candidate.itertext()).split())
    perf={(x["model"],x["feature_set"]):x for x in summary["main"]["performance"]}
    tests={x["test"]:x for x in summary["main"]["primary_tests"]}
    tag={x["test"]:x for x in summary["tagged"]["tests"]}
    required={
        "title":"5′ MFE adds fixed-GFP signal beyond simple proxies",
        "design":"150 exact-CDS groups · 10 seeds × 5-fold OOF · 71 paired tagged CDS",
        "hist_gain":f"{tests['histgb_spearman_effect']['mean_effect']:+.3f}",
        "hist_gain_ci":f"95% CI [{tests['histgb_spearman_effect']['ci95'][0]:.3f}, {tests['histgb_spearman_effect']['ci95'][1]:.3f}]",
        "hist_mse_gain":f"{tests['histgb_mse_improvement']['mean_effect']:+.3f}",
        "tag_rho":f"{tag['paired_spearman']['estimate']:.3f}",
        "tag_ci":f"95% CI [{tag['paired_spearman']['ci95'][0]:.3f}, {tag['paired_spearman']['ci95'][1]:.3f}]",
        "verification":f"{independent['checks_passed']} / {independent['checks_total']}",
        "main_holm":"Holm p = 0.0078125",
        "tag_adjusted":f"Adjusted coefficient = {tag['adjusted_delta_mfe5_coefficient']['estimate']:.4f}",
        "tag_adjusted_ci":f"95% CI [{tag['adjusted_delta_mfe5_coefficient']['ci95'][0]:.4f}, {tag['adjusted_delta_mfe5_coefficient']['ci95'][1]:.4f}]",
        "tag_holm":"Holm p = 0.000050",
        "page":"114 · RK22",
        "boundary":"Development pass, not protein OOD",
        "generator_boundary":"generator training unauthorized",
        "source_commits":"protocol 48eea1e2 · verified evidence b506bf4d",
    }
    for model in ["ridge","histgb"]:
        prefix=model.capitalize() if model=="histgb" else "Ridge"
        required[model+"_simple_rho"]=f"{perf[(model,'simple')]['mean_spearman']:.3f}"
        required[model+"_structure_rho"]=f"{perf[(model,'structure')]['mean_spearman']:.3f}"
        required[model+"_gain"]=f"{tests[model+'_spearman_effect']['mean_effect']:+.3f} [{tests[model+'_spearman_effect']['ci95'][0]:.3f}, {tests[model+'_spearman_effect']['ci95'][1]:.3f}]"
        required[model+"_mse"]=f"{perf[(model,'simple')]['mean_mse']:.4f} → {perf[(model,'structure')]['mean_mse']:.4f}"
    for name,anchor in required.items(): check("anchor_"+name,anchor in text,anchor)
    check("four_main_endpoints",len(tests)==4 and all(x["pass"] and x["positive_seeds"]==10 and abs(x["p_holm"]-0.0078125)<1e-15 for x in tests.values()))
    check("two_tag_endpoints",len(tag)==2 and all(x["pass"] for x in tag.values()))
    check("pass_banner","4/4 main + 2/2 paired endpoints PASS" in text)
    check("no_untagged_imputation","no tagged CAI/GC deltas imputed" in text)
    check("no_sovereignty_overclaim",all(x not in text for x in ["SOTA achieved","protein OOD PASS","generator training authorized","RK-G1 = true"]))
    check("no_candidate_ids",all("id" not in {local(k) for k in e.attrib} for e in candidate.iter()))
    check("single_table",sum(local(e.tag)=="table" for e in candidate.iter())==1)
    table=next(e for e in candidate.iter() if local(e.tag)=="table")
    rows=[e for e in table if local(e.tag)=="tr"]
    check("table_three_rows",len(rows)==3)
    check("table_five_columns",all(sum(local(c.tag)=="td" for c in row)==5 for row in rows))
    notes=[e for e in candidate.iter() if local(e.tag)=="note"]
    check("one_note",len(notes)==1)
    note_paras=[e for e in notes[0].iter() if local(e.tag)=="p"]
    check("five_note_paragraphs",len(note_paras)==5)
    note_text=" ".join(" ".join(notes[0].itertext()).split())
    check("note_full_commits","48eea1e2bd194b80e9c169e9420a3185e65fcb85" in note_text and "b506bf4deca5eb229bf683ceb7ebb12ef1141833" in note_text)
    geometry_ok=True
    for e in candidate.iter():
        if local(e.tag) in {"shape","table","img","embed"}:
            try:
                x=float(e.get("topLeftX")); y=float(e.get("topLeftY")); w=float(e.get("width")); h=float(e.get("height"))
                geometry_ok &= x>=0 and y>=0 and w>0 and h>0 and x+w<=960 and y+h<=540
            except (TypeError,ValueError): geometry_ok=False
    check("all_elements_in_canvas",geometry_ok)
    font_sizes=[float(e.get("fontSize")) for e in candidate.iter() if local(e.tag)=="content" and e.get("fontSize")]
    check("font_size_minimum",bool(font_sizes) and min(font_sizes)>=9)
    check("inter_font",all(e.get("fontFamily")=="Inter" for e in candidate.iter() if local(e.tag)=="content" and e.get("fontSize")))
    check("no_external_media",all(not (local(e.tag)=="img" and (e.get("src") or "").startswith("http")) for e in candidate.iter()))

    if args.online:
        source=ET.parse(args.source).getroot()
        online=ET.parse(args.online).getroot()
        source_response=json.loads(Path(args.source_response).read_text())
        online_response=json.loads(Path(args.online_response).read_text())
        add_response=json.loads(Path(args.add_response).read_text())
        ns_source=source.tag.split("}")[0]+"}" if "}" in source.tag else ""
        ns_online=online.tag.split("}")[0]+"}" if "}" in online.tag else ""
        source_slides=source.findall(ns_source+"slide")
        online_slides=online.findall(ns_online+"slide")
        check("source_read_ok",source_response["ok"] is True)
        check("online_read_ok",online_response["ok"] is True)
        check("add_ok",add_response.get("ok") is True and bool(add_response.get("data",{}).get("slide_id")))
        check("source_113",len(source_slides)==113)
        check("online_114",len(online_slides)==114)
        check("revision_increment",online_response["data"]["revision_id"]==source_response["data"]["revision_id"]+1)
        check("new_slide_id",online_slides[-1].get("id")==add_response["data"]["slide_id"])
        check("old_slide_ids_order",[x.get("id") for x in online_slides[:113]]==[x.get("id") for x in source_slides])
        check("old_semantics_preserved",all(signature(a)==signature(b) for a,b in zip(source_slides,online_slides[:113])))
        check("candidate_online_semantics",signature(candidate)==signature(online_slides[-1]))
        check("canvas_preserved",online.get("width")=="960" and online.get("height")=="540")
        old_text=" ".join(" ".join(source.itertext()).split())
        check("single_new_title",required["title"] not in old_text)
    report={
        "schema":"a8-rk22-ppt-verification-v1",
        "status":"PASS" if all(x["pass"] for x in checks) else "FAIL",
        "mode":"online" if args.online else "candidate",
        "checks_passed":sum(x["pass"] for x in checks),"checks_total":len(checks),"checks":checks,
        "candidate_sha256":sha(candidate_path),"science_summary_sha256":sha(args.summary),"independent_sha256":sha(args.independent),
    }
    if args.online:
        report.update({"source_sha256":sha(args.source),"online_sha256":sha(args.online),"slide_id":add_response["data"]["slide_id"],"revision_id":online_response["data"]["revision_id"]})
    Path(args.output).write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"status":report["status"],"checks_passed":report["checks_passed"],"checks_total":report["checks_total"],"failed":[x for x in checks if not x["pass"]]},indent=2,ensure_ascii=False))
    if report["status"]!="PASS": raise SystemExit(1)

if __name__=="__main__": main()
