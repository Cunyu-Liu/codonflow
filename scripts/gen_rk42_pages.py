#!/usr/bin/env python3
"""Generate A9-RK42 research-deck pages (205-206) matching the A8-RK design system
(reused verbatim from gen_rk36_pages.py). Values are bound to the frozen RK42
acquisition audit v2 + independent verification, not hand-typed.

Run on server (audit JSON present):
  /home/codonflow-clean-env-v1/bin/python scripts/gen_rk42_pages.py \
      --audit audits/20261122/RK42/independent_data_acquisition_v2.json \
      --indep audits/20261122/RK42/independent_data_acquisition_independent_v2.json \
      --tests audits/20261122/RK42/rk42_full_project_tests_v1.json \
      --outdir audits/20261122/RK42/ppt --start-page 205
"""
import argparse
import json
import os
from pathlib import Path

NS = 'xmlns="https://www.larkoffice.com/sml/2.0"'
BG = "rgba(247, 248, 250, 1)"
TEAL = "rgba(13, 148, 136, 1)"
GREEN = "rgba(5, 150, 105, 1)"
ROSE = "rgba(225, 29, 72, 1)"
AMBER = "rgba(217, 119, 6, 1)"
DARK = "rgba(31, 41, 55, 1)"
SLATE = "rgba(100, 116, 139, 1)"
CARD_BORDER = "rgba(226, 232, 240, 1)"
ROW_ALT = "rgba(241, 245, 249, 1)"
BAND_BG = "rgba(204, 251, 241, 1)"
WHITE = "rgba(255, 255, 255, 1)"
RIGHT_LABEL = "A9 / RK42 / INDEPENDENT DATA ACQUISITION"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, w, h, s, size, color, bold=False, align="left", wrap="false"):
    b = ' bold="true"' if bold else ""
    return (f'<shape width="{w}" height="{h}" topLeftX="{x}" topLeftY="{y}" type="text">'
            f'<content verticalAlign="top" fontSize="{size}" fontFamily="Inter" color="{color}"{b} '
            f'lineSpacing="multiple:1.15" textAlign="{align}" wrap="{wrap}"><p>{esc(s)}</p></content></shape>')


def rect(x, y, w, h, fill, radius=8, border=None):
    bd = f'<border color="{border}" width="1"/>' if border else ""
    return (f'<shape width="{w}" height="{h}" topLeftX="{x}" topLeftY="{y}" presetHandlers="{radius}" type="round-rect">'
            f'<fill><fillColor color="{fill}"/></fill>{bd}'
            f'<content fontSize="16" fontFamily="Inter" color="{DARK}"/></shape>')


def nav(section):
    return text(48, 8, 650, 14, section, 8.5, TEAL, bold=True) + \
        text(716, 8, 196, 14, RIGHT_LABEL, 8.5, SLATE, align="right")


def title(t):
    return text(48, 27, 864, 35, t, 23, DARK, bold=True)


def accent():
    return rect(48, 72, 58, 3, TEAL, radius=1)


def subtitle(t):
    return text(48, 82, 864, 18, t, 10.2, SLATE)


def kpi(x, label, value, caption, color):
    return (rect(x, 104, 204, 76, WHITE, radius=8, border=CARD_BORDER)
            + text(x + 14, 113, 176, 15, label, 8.5, SLATE, bold=True)
            + text(x + 14, 129, 176, 30, value, 21, color, bold=True)
            + text(x + 14, 160, 176, 17, caption, 8.2, SLATE, wrap="true"))


def kpis(cards):
    xs = [48, 268, 488, 708]
    return "".join(kpi(x, *c) for x, c in zip(xs, cards))


def cell(s, size, color, bold, align, fill):
    f = f'<fill><fillColor color="{fill}"/></fill>' if fill else '<fill><fillColor/></fill>'
    b = ' bold="true"' if bold else ""
    return (f'<td>{f}<content fontSize="{size}" fontFamily="Inter" color="{color}"{b} '
            f'lineSpacing="multiple:1" textAlign="{align}" wrap="false"><p>{esc(s)}</p></content></td>')


def table(x, y, w, headers, rows, colw, aligns, header_h=26, row_h=24, size=9.1):
    cols = "".join(f'<col span="1" width="{cw}"/>' for cw in colw)
    hrow = f'<tr height="{header_h}">' + "".join(
        cell(h, size, WHITE, True, a, DARK) for h, a in zip(headers, aligns)) + "</tr>"
    body = ""
    for i, r in enumerate(rows):
        fill = ROW_ALT if i % 2 else None
        body += f'<tr height="{row_h}">' + "".join(
            cell(v, size, DARK, False, a, fill) for v, a in zip(r, aligns)) + "</tr>"
    h = header_h + row_h * len(rows)
    return f'<table width="{w}" height="{h}" topLeftX="{x}" topLeftY="{y}"><colgroup>{cols}</colgroup>{hrow}{body}</table>'


def band(y, t, size=9.6):
    return rect(48, y, 864, 30, BAND_BG, radius=6) + text(62, y + 4, 836, 21, t, size, TEAL, bold=True)


def source(t):
    return text(48, 512, 780, 13, t, 8.2, SLATE)


def pagenum(n):
    return text(850, 510, 62, 15, str(n), 10, DARK, bold=True, align="right")


def note(sentences):
    ps = "".join(f"<p>{esc(s)}</p>" for s in sentences)
    return f"<note><content>{ps}</content></note>"


def page(section, t, sub, body, src, num, notes):
    inner = nav(section) + title(t) + accent() + subtitle(sub) + body + source(src) + pagenum(num)
    return f'<slide {NS}><style><fill><fillColor color="{BG}"/></fill></style><data>{inner}</data>{note(notes)}</slide>\n'


def yn(status):
    return "Y" if status == "PASS" else "N"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", required=True)
    ap.add_argument("--indep", required=True)
    ap.add_argument("--tests", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--start-page", type=int, default=205)
    args = ap.parse_args()
    aud = json.load(open(args.audit))
    indep = json.load(open(args.indep))
    tests = json.load(open(args.tests))
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    n = args.start_page
    src_by_id = {s["id"]: s for s in aud["sources"]}
    order = ["Cambray2018", "Kosuri2013", "Goodman2013", "Mutalik2013", "Rhodius2012",
             "Salis2011", "EspahBorujeni2014_2017", "deBoer2020", "Lind2020"]
    short = {"EspahBorujeni2014_2017": "EspahBorujeni14/17"}
    tally = aud["fail_tally_non_qualifying"]
    cam = src_by_id["Cambray2018"]["raw_rederive"]
    nrow = cam["n_complete_rows"]
    npep = cam["n_distinct_translated_peptides"]
    prot = cam["numeric_phenotype_ranges"]["clean.lin.prot.mean"]
    indep_str = "%d/%d" % (indep["n_pass"], indep["n_checks"])
    tests_str = "%d passed/%d skipped/%d failed" % (tests["passed"], tests["skipped"], tests["failed"])

    # ---- Page 205: 0/9 qualify matrix ----
    rows = []
    for cid in order:
        s = src_by_id[cid]
        rows.append([short.get(cid, cid), yn(s["R"]["R2"]["status"]), yn(s["R"]["R3"]["status"]),
                     yn(s["R"]["R4"]["status"]), yn(s["R"]["R5"]["status"]), yn(s["R"]["R7"]["status"]), "NO"])
    p205_body = kpis([
        ("CANDIDATES", str(aud["n_candidates"]), "public construct-level sources", TEAL),
        ("ELIGIBILITY", "R1-R7", "frozen, reused from RK36", TEAL),
        ("QUALIFYING", str(aud["n_qualifying"]), "none passes all seven", ROSE),
        ("BRANCH", "B3", "wet-lab DBTL - user approval", AMBER),
    ]) + table(48, 202, 864,
        ["Candidate", "R2 fullCDS", "R3 nativeUTR", "R4 synonym", "R5 family", "R7 rawSHA", "Qualify"],
        rows, [230, 92, 92, 92, 92, 92, 182],
        ["left", "center", "center", "center", "center", "center", "center"],
        header_h=26, row_h=22, size=9.0) \
        + band(438, "R1 (independent study/host) and R6 (continuous outcome) PASS for all 9. Gap = R2/R3/R4/R5: no fixed-protein synonymous library with native variant-specific UTR + full CDS + family map.", size=9.0) \
        + band(476, "Branch B3: no qualifying public data -> prospective DBTL/wet-lab requires user budget + timeline approval; phase C positive core is data-blocked.", size=9.2)
    p205 = page("01 / ACQUISITION VERDICT",
        "0 of 9 public candidates qualify under frozen R1-R7",
        "RK42 - label-free independent-data acquisition audit - Y=PASS, N=FAIL (R1/R6 all PASS, omitted)",
        p205_body,
        "Source: audit v2 5b73e43fbc18 - protocol aa6071c3b13b - independent %s - commit ab58f523" % indep_str,
        n,
        ["RK42 audits nine public construct-level datasets against the seven frozen eligibility requirements, label-free, before any outcome association.",
         "None passes all seven: regulatory-grammar libraries fix the CDS, N-terminal fusions fix the leader and vary amino acids, and the one synonymous set is too small.",
         "The branch decision is B3: build prospective independent data via DBTL/wet-lab, which requires user budget and timeline approval."])

    # ---- Page 206: raw evidence + decision ----
    p206_body = kpis([
        ("DESIGNED SEGMENT", "96 bp", "all %s raw rows - not full CDS" % format(nrow, ","), ROSE),
        ("DISTINCT PEPTIDES", format(npep, ","), "amino acids vary - not synonymous", ROSE),
        ("PROTEIN P_NI", "%g-%g" % (prot["min"], prot["max"]), "continuous + growth + mRNA t1/2", GREEN),
        ("UPSTREAM [-30;3]", "CONSTANT", "fixed synthetic leader - not native", ROSE),
    ]) + table(48, 202, 864,
        ["Missing dimension (non-qualifying sources)", "Count / 9", "Consequence"],
        [
            ["R3 native variant-specific 5'UTR", str(tally["R3"]), "fixed synthetic leader or synthetic regulatory parts"],
            ["R5 protein identity + family map", str(tally["R5"]), "single reporter; no protein OOD"],
            ["R4 fixed-protein synonymous library", str(tally["R4"]), "regulatory variation or amino-acid variation"],
            ["R7 documentable raw construct SHA", str(tally["R7"]), "Cloudflare-blocked or not downloaded"],
            ["R2 full CDS per variant", str(tally["R2"]), "N-terminal segment / fixed reporter / promoter"],
        ], [430, 110, 324], ["left", "center", "left"], header_h=26, row_h=24, size=9.0) \
        + band(372, "Cambray raw re-derived independently: 19,760 real CSV rows, gs.sequence=96bp, 12,394 peptides, P_NI 1-100; Note 1 '[-30;3] segment is constant'. Kosuri: 114 promoters x 111 RBS drive fixed sfGFP.", size=8.8) \
        + band(410, "DBTL design (B3): >=2 fixed proteins + family map; synonymous CDS library; native complete UTR-CDS; independent E. coli host; continuous fluorescence + growth fitness; protocol frozen before outcomes.", size=8.8) \
        + band(448, "USER DECISION: (A) strict R1-R7 -> wet-lab DBTL (budget + >1 month); or (B) authorize R3-relaxation for the functional benchmark only (Goodman-style); strict R3 kept for transport claims.", size=8.6)
    p206 = page("02 / RAW EVIDENCE & DECISION",
        "Raw-verified evidence and the independent-data decision",
        "RK42 - independent verify %s - full project tests %s - phase C training not started (RK-G1 authorized, data-blocked)" % (indep_str, tests_str),
        p206_body,
        "Source: Cambray nbt.4238 Supp Note1/Tables + partial Data15 - Kosuri pnas.1301301110 methods - audit v2 5b73e43fbc18",
        n + 1,
        ["The Cambray verdict is re-derived from real raw data, not memory: every designed sequence is 96 base pairs, the encoded peptides vary, and the upstream leader is constant.",
         "The dominant missing dimensions are native variant-specific UTR, protein family map, and a fixed-protein synonymous library.",
         "Phase C cannot start without qualifying independent data; the user must choose strict wet-lab DBTL or authorize a functional-benchmark R3 relaxation."])

    (out / ("page-%d.xml" % n)).write_text(p205)
    (out / ("page-%d.xml" % (n + 1))).write_text(p206)
    print("wrote", out / ("page-%d.xml" % n), "and", out / ("page-%d.xml" % (n + 1)))
    print("indep", indep_str, "tests", tests_str, "n_qualifying", aud["n_qualifying"])


if __name__ == "__main__":
    main()