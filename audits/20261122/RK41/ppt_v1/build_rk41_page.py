#!/usr/bin/env python3
"""Build one RK41 slide from an accepted RK40 layout, preserving its visual system."""
from copy import deepcopy
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
NS = "https://www.larkoffice.com/sml/2.0"
ET.register_namespace("", NS)
Q = lambda x: f"{{{NS}}}{x}"
COMMON_NOTES = [
    "Source: RK41 independent b402c4fd4899 · clean closeout af5ad2580151.",
    "Independent verification: 5,401 checks; clean closeout: 1,114 checks; full project tests: 494 passed, one skipped, five subtests passed.",
    "Coverage: 324 runs, 3,564 raw points, 216 complete new trajectories and 1,604 independently rescored unique sequences.",
    "Internal proxy improvements do not establish external SOTA, functional efficacy, protein OOD, untouched-confirmation success or manuscript-submittable status.",
]
PAGES = {
199: {"ref":193, "texts":[
"01 / FROZEN INTERNAL-BASIN DESIGN","A8 / RK41 / INTERNAL BASIN","Eight internal starts isolate initialization-basin selection",
"Four new arms plus accepted RK40 random B11 baselines · protein-only synonymous starts · no external sequence initialization",
"DEVELOPMENT RECORDS","18","record is the inference unit","SEEDS","3","all-seed direction required","SEARCH ARMS","4 + 2","4 new + 2 accepted · exact B11","PRIMARY FAMILIES","3","two internal + one external",
"01","Pool generation","Eight distinct protein-only synonyms","All eight candidates truly scored",
"02","Start selection","First = index0; Best = max utility","Ties resolve to the lowest index",
"03","Budget control","Cached start + three local points","Exactly 11 unique-scorer outputs",
"04","Frozen inference","Two internal + one external family","Bootstrap + sign-flip + Holm",
"Primary A: raw best−raw first · B: raw best−raw sequential · C: raw best−LinearDesign-11",
"No new arm uses LinearDesign, EnsembleDesign, native synonymous DNA or another external sequence",
"Source: RK41 protocol 9ed2657dfe69 · frozen before smoke and formal outcomes","199",
"Each record and seed generates eight different protein-only synonymous initializations, all evaluated by the real scorer.",
"The first arm selects pool index zero; the best arm selects maximum search utility with lowest-index tie breaking.",
"The selected start is cached and only three new local-search points are added, preserving an exact budget of eleven unique outputs.",
"The three frozen primary families use record-level inference and require both endpoints to pass.",
*COMMON_NOTES]},
200: {"ref":194, "texts":[
"02 / EXECUTION + TRAJECTORY AUDIT","A8 / RK41 / INTERNAL BASIN","324 runs audited across 3,564 raw points",
"Production and detached clean runs · real unique-scorer accounting · independent full-trajectory replay",
"NEW RUNS","216 / 216","18 records x 3 seeds x 4 arms","NEW SCORER CALLS","2,376","eight starts + three local points per run","ANALYSIS RUNS","324","includes 108 accepted RK40 runs","POOL CONSISTENCY","1,296 / 1,296","eight candidates x 216 new runs",
"Audit item","Verified value","Interpretation","Production + clean","216 new runs each","Same decision and 2,376 new scorer calls",
"Pool + trajectory","216 / 216 replayed","1,296 / 1,296 pool checks PASS",
"Objective coverage","1,604 unique sequences","Four objectives independently recomputed; maximum absolute error 0.0",
"Independent audit","5,401 / 5,401 PASS","324 runs and 3,564 raw points; all metrics and inference reproduced",
"Scientific boundary","Internal mechanism only","External actual-set gate is evaluated separately",
"Production and detached clean execution completed every planned run with the same scientific decision",
"Run completion and trajectory identity validate execution—not external performance or functional efficacy",
"Source: production 2e7ef6dd4ad0 · independent b402c4fd4899 · clean af5ad2580151","200",
"The formal design adds 216 runs and 2,376 scorer calls; 108 random-B11 runs are accepted from RK40.",
"The 324 analysis runs contain 3,564 raw points and 216 complete new trajectories.",
"All 1,296 initialization-pool consistency checks pass, and independent replay covers every new trajectory.",
"No external sequence is used to initialize any new arm; no functional or unified time-matched claim is introduced.",
*COMMON_NOTES]},
201: {"ref":195, "extra_endpoint_rows":True, "texts":[
"03 / TWO INTERNAL PRIMARY FAMILIES","A8 / RK41 / INTERNAL BASIN","Basin selection improves both internal search comparisons",
"20,000 paired bootstrap + 20,000 sign-flip · Holm within each family · record-level inference across 18 records",
"BEST−FIRST UTILITY","+0.050030","same eight-member initialization pool","BEST−FIRST HV EFFECT","+0.031529","best single-point normalized HV","SEED DIRECTION","3 / 3 positive","for both best−first endpoints","INTERNAL FAMILY GATES","2 / 2 PASS","all CI, Holm and seed criteria",
"Internal comparison","Effect","95% confidence interval","Holm p","Seed means",
"Best−first · utility","+0.050030","[+0.035533, +0.064341]","9.9995e-5","3 / 3 positive",
"Best−first · single-point HV","+0.031529","[+0.015111, +0.052030]","8.4996e-4","3 / 3 positive",
"Best−random · utility","+0.788952","[+0.621305, +0.952120]","9.9995e-5","3 / 3 positive",
"Best−random · single-point HV","+0.486789","[+0.330474, +0.658647]","9.9995e-5","3 / 3 positive",
"Absolute best raw pool: utility 3.246544 · single-point HV 0.774117 · first-k HV 0.757367",
"INTERNAL_MULTISTART_SUPPORTED · both internal families pass every frozen criterion",
"Identical pool and exact B11 budget isolate initialization-basin selection; these gains do not imply external SOTA",
"Source: RK41 independent b402c4fd4899 · primary families raw basin selection and sequential advantage","201",
"Best raw initialization improves utility by 0.0500296 and single-point HV by 0.0315288 over the first pool member.",
"Against the original sequential raw search, the utility and single-point HV effects are 0.788952 and 0.486789.",
"Both internal families have positive confidence limits, Holm significance and positive effects for all three seeds.",
"The mechanism claim is limited to the frozen proxy-search contract and does not reverse the external actual-set result.",
*COMMON_NOTES]},
202: {"ref":195, "failed":True, "texts":[
"04 / COMMON-INPUT EXTERNAL FAMILY","A8 / RK41 / INTERNAL BASIN","LinearDesign-11 still wins the common-input actual-set gate",
"Best raw pool minus LinearDesign-11 · record-specific first-k actual sets · both endpoints required to pass",
"FIRST-K HV EFFECT","−29.215520","significantly worse in every seed","PAIRWISE NED EFFECT","+0.165764","more within-archive diversity only","HV SEED DIRECTION","0 / 3 positive","all three seed effects negative","EXTERNAL FAMILY GATE","FAIL","HV and NED must both pass",
"Primary endpoint","Effect","95% confidence interval","Holm p","Seed means",
"First-k actual-set HV","−29.215520","[−41.230472, −18.981136]","9.9995e-5","0 / 3 positive",
"First-k pairwise NED","+0.165764","[+0.149476, +0.182711]","9.9995e-5","3 / 3 positive",
"Absolute first-k HV: raw pool best 0.757367 vs LinearDesign-11 29.972887 · NED 0.237053 vs 0.071289",
"COMMON_INPUT_ACTUAL_SET_GATE_FAILED · the HV endpoint remains significantly negative",
"Higher within-archive NED indicates sequence diversity only; it cannot compensate for the frozen HV failure",
"Source: RK41 independent b402c4fd4899 · common-input actual-set versus LinearDesign-11","202",
"Best raw initialization remains significantly worse than LinearDesign-11 on first-k actual-set hypervolume.",
"The HV effect is minus 29.215520 with a fully negative confidence interval and negative effects for all three seeds.",
"Pairwise NED increases by 0.165764, but this denotes greater within-archive sequence diversity and cannot rescue the HV failure.",
"The external family therefore fails and the common-input actual-set task remains unresolved.",
*COMMON_NOTES]},
203: {"ref":197, "texts":[
"05 / ABSOLUTE PERFORMANCE + REPRODUCTION","A8 / RK41 / INTERNAL BASIN","Internal gains reproduce but remain far below LinearDesign-11",
"Common frozen normalization · calibrated arms are scale diagnostics · independent and detached-clean evidence",
"RAW POOL BEST UTILITY","3.246544","best raw sequential = 2.457592","RAW POOL BEST FIRST-K HV","0.757367","LinearDesign-11 = 29.972887","INDEPENDENT VERIFIER","5,401 / 5,401","1,604 sequences · max error 0.0","CLEAN CLOSEOUT","1,114 / 1,114","pointwise and inferential identity",
"Method","Best utility","Best single-point HV","First-k actual-set HV",
"Raw random B11","2.457592","0.287328","0.258270",
"Raw pool first B11","3.196515","0.742588","0.751843",
"Raw pool best B11","3.246544","0.774117","0.757367",
"Calibrated pool best B11","3.310026","0.826891","0.756650",
"LinearDesign-11","11.798970","26.439732","29.972887",
"Independent 5,401/5,401 · clean 1,114/1,114 · full project 494 passed, one skipped, five subtests passed",
"Calibrated arms read development-native calibration and are descriptive; internal gains do not close the actual-set gap",
"Source: independent 5,401 checks · clean 1,114 checks · full project tests 494 passed","203",
"Raw pool-best search improves absolute internal endpoints over raw sequential and pool-first search.",
"LinearDesign-11 remains far ahead on first-k actual-set hypervolume under the frozen post hoc normalization.",
"Independent verification passes 5,401 checks over 1,604 unique sequences with zero maximum objective error.",
"The detached clean closeout passes 1,114 checks; the full project suite records 494 passed tests, one skip and five passed subtests.",
*COMMON_NOTES]},
204: {"ref":198, "texts":[
"06 / SCIENTIFIC BOUNDARY + NEXT TEST","A8 / RK41 / INTERNAL BASIN","Initialization mechanism supported; design task remains open",
"Do not convert internal proxy gains into external-SOTA, functional, OOD or submission claims",
"MECHANISM DECISION","Multistart supported","two internal families pass","COMMON-INPUT TASK","Unresolved","LinearDesign HV gate fails","EXTERNAL SOTA","false","no authorized ranking","FUNCTIONAL / SUBMITTABLE","false / false","functional labels untouched",
"Boundary","Allowed interpretation","Required next evidence",
"Basin selection","Best>start and best>sequential on two internal endpoints","Treat as internal proxy-search mechanism only",
"External actual-set","HV remains negative; NED does not rescue","Stronger common-input search and unified cost comparison",
"Calibration","Calibrated pool-best is descriptive only","No native-search calibration in independent common-input claims",
"External + functional","No SOTA, functional, untouched or OOD claim","Strong baselines and feasibility-gated untouched validation",
"Manuscript","Section 6.52 integrated; preprint non-submittable","Resolve comparative, functional and RK-G1 gates",
"INTERNAL_MULTISTART_SUPPORTED_COMMON_INPUT_TASK_UNRESOLVED",
"Next: stronger common-input search with actual-set and time-matched gates before any SOTA or submission claim",
"Source: RK41 independent and clean closeout · scientific gate false · RK-G1 open","204",
"RK41 supports internal multistart initialization under the frozen proxy-search contract.",
"The common-input external family fails because actual-set hypervolume remains significantly below LinearDesign-11.",
"External SOTA, unified time-matched performance, functional untouched, protein OOD, RK-G1 and submission gates remain open.",
"The next discriminating step is a stronger common-input search algorithm evaluated with actual-set and unified-cost gates.",
*COMMON_NOTES]},
}


def main(page):
    cfg = PAGES[page]
    tree = ET.parse(ROOT / f"reference_{cfg['ref']}.xml")
    root = tree.getroot()
    table = root.find(f".//{Q('table')}")
    if cfg.get("extra_endpoint_rows"):
        rows = table.findall(Q("tr"))
        table.append(deepcopy(rows[1]))
        table.append(deepcopy(rows[2]))
        for row in table.findall(Q("tr"))[1:]:
            row.set("height", "38")
        table.set("height", "180")
        for shape in root.findall(f".//{Q('shape')}"):
            text = "".join(shape.itertext())
            if text.startswith("Absolute raw11"):
                shape.set("topLeftY", "394")
                shape.set("height", "30")
    paragraphs = root.findall(f".//{Q('p')}")
    assert len(paragraphs) == len(cfg["texts"]), (page, len(paragraphs), len(cfg["texts"]))
    for p, text in zip(paragraphs, cfg["texts"]):
        for child in list(p):
            p.remove(child)
        p.text = text
    for elem in root.iter():
        elem.attrib.pop("id", None)
    if cfg.get("failed"):
        for color in root.findall(f".//{Q('fillColor')}"):
            if color.get("color") == "rgba(220, 247, 238, 1)":
                color.set("color", "rgba(253, 236, 241, 1)")
        parents = {child: parent for parent in root.iter() for child in parent}
        for idx in (5, 11, 14, 32):
            content = parents[paragraphs[idx]]
            content.set("color", "rgba(206, 65, 102, 1)")
    out = ROOT / f"rk41_{page}.xml"
    tree.write(out, encoding="utf-8", xml_declaration=False)
    print(out)


if __name__ == "__main__":
    main(int(sys.argv[1]))
