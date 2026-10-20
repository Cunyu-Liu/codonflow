#!/usr/bin/env python
import json, math, glob, os
V2_DIR = "/teams/HoulabData_1788502323/liucunyu/codonflow/figures_src/data"
V3_DIR = "/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs"
SECTIONS = {"S1": "S1_cai", "S2": "S2_cai_mfe", "S3": "S3_quad"}

def load(dirpath, prefix):
    out = {}
    for f in glob.glob(os.path.join(dirpath, prefix + "*.json")):
        base = os.path.basename(f).replace(prefix, "")
        data = json.load(open(f))
        gene = list(data.keys())[0]
        meta = gene.split("|")
        rec = data[gene][0]
        out[base] = {"meta": meta, "hv": {k: rec.get(sec + "/codonflow/hv") for k, sec in SECTIONS.items()}}
    return out

v2 = load(V2_DIR, "HELD18_")
v3 = load(V3_DIR, "HELD18_V356m_")
common = sorted(set(v2) & set(v3))
print("genes common: %d" % len(common))
rows = []
for g in common:
    m = v2[g]["meta"]
    rows.append((g, m[1], m[2], m[3], v2[g]["hv"], v3[g]["hv"]))

def geo(vals):
    vals = [v for v in vals if v is not None and v > 0]
    if not vals:
        return None
    return math.exp(sum(math.log(v) for v in vals) / len(vals))

for sec in ["S1", "S2", "S3"]:
    ratios = [r[5][sec] / r[4][sec] for r in rows if r[4][sec] and r[5][sec]]
    g_all = geo(ratios)
    print("")
    print("## %s (codonflow HV): geomean ratio v3/v2conv = %.3f (n=%d)" % (sec, g_all, len(ratios)))
    print("| gene | species | bin | len | v2conv | v3 | ratio |")
    print("|---|---|---|---|---|---|---|")
    for g, sp, bin_, ln, h2, h3 in rows:
        if h2[sec] and h3[sec]:
            print("| %s | %s | %s | %s | %.2f | %.2f | %.3f |" % (g, sp, bin_, ln, h2[sec], h3[sec], h3[sec]/h2[sec]))
    for b in ["short", "mid", "long"]:
        br = [r[5][sec] / r[4][sec] for r in rows if r[2] == b and r[4][sec] and r[5][sec]]
        if br:
            print("%s bin geomean ratio: %.3f (n=%d)" % (b, geo(br), len(br)))
