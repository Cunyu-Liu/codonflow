#!/usr/bin/env python3
"""Generate RK36 research-deck pages (170-173) matching the A8-RK design system.
Values copied verbatim from the frozen RK36 feasibility result + verification."""
from pathlib import Path

OUT = Path(__file__).parent
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
RIGHT_LABEL = "A8 / RK36 / FEASIBILITY & PIVOT"
PROJECT_PASSED = "455"  # set from final project test summary before write


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


# ---------------- Page 170 · FEASIBILITY QUESTION ----------------
p1_body = kpis([
    ("DATASETS AUDITED", "4", "Kudla · Boel · Mordstein · MAGE", TEAL),
    ("ELIGIBILITY REQS", "7", "R1–R7 frozen label-free", TEAL),
    ("QUALIFYING", "0", "none reconstruct exact window", ROSE),
    ("DECISION", "3 → 2", "record feasibility → pivot", AMBER),
]) + table(48, 202, 864,
    ["Req", "Requirement", "Meaning for strict independent transport"],
    [
        ["R1", "Independent study / host", "Not the Kudla training cohort"],
        ["R2", "Full CDS per variant", "Complete coding sequence available"],
        ["R3", "Native variant-specific 5'UTR", ">=4 nt upstream of ATG; same construct geometry"],
        ["R4", "Fixed-protein synonymous library", "Not a cross-protein non-synonymous pool"],
        ["R5", "Protein identity + family map", "Protein / study OOD isolation feasible"],
        ["R6", "Fresh continuous outcome", "Adequate dynamic range; not coarse ordinal"],
        ["R7", "Isolation + provenance", "Cluster isolation; license / accession / raw SHA"],
    ],
    [60, 300, 504], ["left", "left", "left"], header_h=26, row_h=24, size=9.1) \
    + band(400, "Mandate: RK34 ends same-cohort window ablation; RK35 shows coverage is not necessary within Kudla → §4 branch 1 seeks independent data.") \
    + band(440, "Label-free audit frozen before any outcome association; reads schema / coverage / identity only, no outcome-effect correlation.")
p1 = page("01 / FEASIBILITY QUESTION",
    "Can any independent dataset reconstruct the exact start window?",
    "RK36 · label-free independent-transport feasibility audit · §4 branch 1 first step",
    p1_body,
    "Source: protocol 891023c8746b · preregistration A8_RK36_PREREGISTRATION.md · long table 25420 rows / 31 cols",
    170,
    ["The handover makes RK34 the terminal same-cohort ablation and requires independent validation or a pivot afterwards.",
     "RK36 freezes seven eligibility requirements and audits four available datasets label-free, before any outcome association.",
     "A dataset qualifies only if all seven pass; the exact window is UTR[-4:]+CDS[:38] with the same construct geometry as Kudla."])

# ---------------- Page 171 · ELIGIBILITY MATRIX ----------------
p2_body = table(48, 108, 864,
    ["Dataset", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "Qualifies"],
    [
        ["Kudla 2009 GFP (E. coli)", "Fail", "Pass", "Pass", "Pass", "Pass", "Pass", "Pass", "No"],
        ["Boel 2016 (E. coli BL21)", "Pass", "Pass", "Fail", "Fail", "Fail", "Fail", "Fail", "No"],
        ["Mordstein 2020 (HEK293)", "Pass", "Fail", "Fail", "Pass", "Pass", "Pass", "Pass", "No"],
        ["Kelsic 2016 MAGE infA", "Pass", "Fail", "Fail", "Pass", "Pass", "Pass", "Fail", "No"],
    ],
    [232, 76, 76, 76, 76, 76, 76, 76, 100],
    ["left", "center", "center", "center", "center", "center", "center", "center", "center"],
    header_h=28, row_h=36, size=9.6) \
    + band(296, "Kudla: R1 fail — the RK27/32/34/35 training cohort, not independent.", size=9.2) \
    + band(338, "Boel: R3–R7 fail — cross-protein non-synonymous, ordinal 0–5, fixed pET/T7 leader (no native UTR), family map absent.", size=9.2) \
    + band(380, "Mordstein: R2–R3 fail — observed-R1 starts at CDS pos 4; no start ATG / upstream 4 nt (RK28/RK33 0/12).", size=9.2) \
    + band(422, "MAGE infA: R2/R3/R7 fail — no full construct in supplement; functional untouched frozen (19072 rows).", size=9.2)
p2 = page("02 / ELIGIBILITY MATRIX",
    "No dataset passes all seven requirements (0 / 4)",
    "Table 27 · frozen R1–R7 · the unified functional long table has no 5'UTR column",
    p2_body,
    "Source: result 9b02373b460a · independent 8b1c2bfbec7e (24/24) · boel/mordstein/mage raw sources",
    171,
    ["The eligibility matrix shows zero of four datasets qualifies for a strict independent transport experiment.",
     "Kudla has the full native UTR but is the training cohort; Boel is independent but non-synonymous, ordinal and UTR-less.",
     "Mordstein is cross-host and synonymous yet truncated at CDS position 4; MAGE has no full construct and is frozen untouched."])

# ---------------- Page 172 · PIVOT DECISION ----------------
p3_body = kpis([
    ("BRANCH 3", "record", "feasibility + missing dims", TEAL),
    ("BRANCH 2", "pivot", "stop start-aware MFE core", AMBER),
    ("NEXT TASK", "RK37", "functional prediction bench", TEAL),
    ("RK-G1", "false", "no generative training", ROSE),
]) + table(48, 202, 864,
    ["Aspect", "Pivot plan"],
    [
        ["Direction", "Functional sequence modeling / translation dynamics (not start-aware MFE core)"],
        ["Next task", "RK37 · preregistered translation-speed / functional prediction benchmark"],
        ["Data", "Bounded clean data (e.g., RiboMIMO); protein / study OOD evaluation"],
        ["Baselines", "Constant + Ridge controls · CAI/GC · full-proxy MFE · general sequence models"],
        ["SOTA gate", "Paired 95% CI lower>0 · multiplicity pass · 100% legality · full cost"],
    ],
    [150, 714], ["left", "left"], header_h=26, row_h=28, size=9.1) \
    + band(384, "Trigger evidence: RK23 Boel protein-OOD 0/4 (Holm p=1) + RK25 mechanism 0/2 already constitute cross-protein / cross-host transport failure.", size=9.0) \
    + band(422, "Data to seek: construct-level synonymous data with native full UTR–CDS + continuous fresh outcome in an independent host; Cambray 2018 fixed-UTR needs raw verification first.", size=8.8) \
    + band(460, "Six missing dimensions recorded (synonymous library · native UTR · full cross-host CDS · continuous outcome · family map · provenance); no mismatched dataset substituted.", size=8.8)
p3 = page("03 / PIVOT DECISION",
    "Record missing dimensions; pivot to functional sequence modeling",
    "§4 branch 3 → branch 2 · start-aware MFE is not a portable core innovation on available data",
    p3_body,
    "Source: result 9b02373b460a · pivot_plan · RK23 protein-OOD 0/4 · RK25 mechanism 0/2",
    172,
    ["With no qualifying independent data, branch 3 records the missing dimensions rather than substituting a mismatched dataset.",
     "This formally triggers the branch-2 pivot: stop treating start-aware MFE as the core innovation and move to functional sequence modeling.",
     "RK37 is a preregistered functional prediction benchmark with strong controls and a strict SOTA gate; generative training stays unauthorized."])

# ---------------- Page 173 · EVIDENCE & BOUNDARY ----------------
p4_body = kpis([
    ("INDEPENDENT", "24 / 24", "raw sources re-derived", GREEN),
    ("MANUSCRIPT", "32 / 32", "§6.47 review · 12/12 integ.", GREEN),
    ("FREEZE", "7942d6a9", "protocol + audit scripts", TEAL),
    ("PROJECT TESTS", PROJECT_PASSED, "passed · 1 skipped · 0 failed", TEAL),
]) + table(48, 202, 864,
    ["Stage", "Result", "Evidence"],
    [
        ["Protocol freeze", "FROZEN", "891023c8746b · label-free R1–R7 · commit 7942d6a9"],
        ["Feasibility audit", "0 / 4 qualify", "rk36_feasibility_result_v1.json · 9b02373b460a"],
        ["Independent verify", "24 / 24", "rk36_feasibility_independent_v1.json · 8b1c2bfbec7e"],
        ["Manuscript §6.47", "12/12 + 32/32", "Table 27 · commit cb528983 · 1984 lines"],
        ["Project tests", PROJECT_PASSED + " / 1 / 0", "run_tests_json.py tests/ · rk36_final_project_tests"],
    ],
    [210, 150, 504], ["left", "left", "left"], header_h=26, row_h=30, size=9.1) \
    + band(400, "Manuscript §6.47 + Table 27 written and audited; registry, tasks and handoff recorded; science eca9171d · manuscript cb528983.") \
    + band(440, "Boundary: feasibility / eligibility only — no transport effect, SOTA or mechanism claim; functional untouched not read; RK-G1=false.", size=9.0)
p4 = page("04 / EVIDENCE & BOUNDARY",
    "Independent verification confirms the feasibility verdict",
    "Verification chain closed · manuscript §6.47 synchronized · scope bounded",
    p4_body,
    "Source: independent 8b1c2bfbec7e · result 9b02373b460a · protocol 891023c8746b · manuscript 8011248f9686",
    173,
    ["An independent verifier re-read the raw sources and re-derived every discriminating fact and qualifying verdict, passing 24 of 24 checks.",
     "The manuscript section 6.47 and Table 27 were audited against the frozen result; integration passed 12/12 and review 32/32.",
     "This is a feasibility audit only: it makes no transport, SOTA or mechanism claim, reads no functional-untouched outcome, and authorizes no generative training."])

for fn, content in [("rk36_p170.xml", p1), ("rk36_p171.xml", p2), ("rk36_p172.xml", p3), ("rk36_p173.xml", p4)]:
    (OUT / fn).write_text(content)
    print(fn, len(content))