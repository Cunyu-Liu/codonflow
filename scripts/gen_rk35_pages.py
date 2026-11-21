#!/usr/bin/env python3
"""Generate RK35 research-deck pages matching the established A8-RK design system
(Inter, light-gray canvas, teal accent, nav bar + judgment title + KPI cards +
dark-header table + conclusion bands + source line + page number).
Values are copied verbatim from the frozen RK35 result JSON (6 decimals)."""
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
RIGHT_LABEL = "A8 / RK35 / COVERAGE TRANSPORT"


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


# ---------------- Page 159 · TRANSPORT QUESTION ----------------
p1_body = kpis([
    ("STRUCTURE ARMS", "6", "3 new + 2 reused + null", TEAL),
    ("PRIMARY TESTS", "8", "C1 + C2 · Holm(8)", TEAL),
    ("EVALUATED FITS", "500", "300 new + 200 reused", TEAL),
    ("GATE Δ vs RK32", "0", "exact_vs_simple reproduced", GREEN),
]) + table(48, 202, 864,
    ["Arm", "Window (42 nt · 37°C)", "Role"],
    [
        ["simple", "sequence-only baseline", "reused · RK32 simple"],
        ["exact_local", "UTR[-4:] + CDS[:38] · dangles 2", "reused · RK32 vienna_local"],
        ["cds_start_local", "CDS[0:42] · dangles 2", "new · ATG start coverage"],
        ["trunc_local", "CDS[3:45] · dangles 2", "new · natural RK33 window"],
        ["trunc_local_d0", "CDS[3:45] · dangles 0", "new · dangles sensitivity"],
    ],
    [200, 380, 284], ["left", "left", "left"], header_h=26, row_h=30) \
    + band(400, "Primary: C1 trunc_vs_simple + C2 exact_vs_trunc (8 tests). Gate: exact_vs_simple must reproduce RK32 within 1e-12.") \
    + band(440, "Decision tree gate > D1 > D2 > D3. C3/C4 are body-shift confounded → descriptive; clean decomposition deferred to RK34.")
p1 = page("01 / TRANSPORT QUESTION",
    "Does the natural RK33 window still carry the Kudla increment?",
    "RK35 · coverage-transport discriminative test · natural unmasked windows",
    p1_body,
    "Source: protocol a26ec02a1f5a · preflight 0847653d4060 · preregistration A8_RK35_PREREGISTRATION.md",
    165,
    ["RK35 asks whether the real, unmasked RK33 window CDS[3:45] still carries the RK32 local-structure increment inside Kudla.",
     "Six structure arms share one 154-sequence panel; three arms are new and two are reused from RK32 to keep the comparison fair.",
     "The gate forces exact_vs_simple to reproduce RK32 before any new contrast is interpreted."])

# ---------------- Page 160 · FROZEN EXECUTION ----------------
p2_body = kpis([
    ("NEW REAL FITS", "300", "3 arms × 10 seeds × 5 folds × 2", TEAL),
    ("REUSED FITS", "200", "simple + exact_local · RK32", TEAL),
    ("BOOTSTRAP / PERM", "20k", "percentile CI · plus-one p", TEAL),
    ("GATE MAX Δ", "0", "within 1e-12 of RK32", GREEN),
]) + table(48, 202, 864,
    ["Model", "Metric", "Δ effect", "95% CI", "Holm p", "Pass"],
    [
        ["Ridge", "Spearman", "+0.984683", "[0.528853, 1.129653]", "0.000200", "Yes"],
        ["Ridge", "MSE improve", "+0.156926", "[0.071305, 0.214567]", "0.000800", "Yes"],
        ["HistGB", "Spearman", "+0.402747", "[0.220999, 0.523021]", "0.000300", "Yes"],
        ["HistGB", "MSE improve", "+0.104263", "[0.055664, 0.130178]", "0.000600", "Yes"],
    ],
    [110, 150, 130, 230, 120, 124], ["left", "left", "right", "right", "right", "right"], header_h=26, row_h=34) \
    + band(392, "Inference: seeds 20261221–20261230, primary 20261221 · 5 folds · bootstrap 20000 (seed 20261321) · permutation 20000 (seed 20261322).") \
    + band(432, "PASS = effect>0 and CI lower>0 and Holm<0.05 and >=8/10 seeds; contrast support requires 4/4. Production wall 166.54 s.")
p2 = page("02 / FROZEN EXECUTION",
    "Frozen 500-fit contract; the gate reproduces RK32 exactly",
    "FROZEN_BEFORE_RK35_EXPRESSION_ASSOCIATION_OR_MODEL_FIT",
    p2_body,
    "Source: result c811bb6e3481 · protocol a26ec02a1f5a · independent d037542df5ee",
    166,
    ["The protocol was frozen before any RK35 expression association or model fit; no endpoint or seed changed after seeing results.",
     "Three hundred new real fits plus two hundred reused RK32 fits give five hundred evaluated fits with no double counting.",
     "All four gate endpoints pass and the maximum gate delta against RK32 is zero, so the new contrasts are interpretable."])

# ---------------- Page 161 · PRIMARY DECISION ----------------
p3_body = kpis([
    ("PRIMARY DECISION", "D1", "coverage retains increment", TEAL),
    ("C1 trunc − simple", "4 / 4", "both models · both metrics", GREEN),
    ("C2 exact − trunc", "2 / 4", "Ridge only · HistGB n.s.", AMBER),
    ("GATE exact − simple", "4 / 4", "reproduces RK32 · Δ=0", GREEN),
]) + table(48, 202, 864,
    ["Comparison", "Model", "Metric", "Δ effect", "95% CI", "Holm p", "Seeds", "Pass"],
    [
        ["trunc − simple", "Ridge", "Spearman", "+0.735912", "[0.269426, 0.883119]", "0.011099", "10/10", "Yes"],
        ["trunc − simple", "Ridge", "MSE improve", "+0.112439", "[0.037299, 0.157190]", "0.043398", "10/10", "Yes"],
        ["exact − trunc", "Ridge", "Spearman", "+0.248771", "[0.096534, 0.433405]", "0.011099", "10/10", "Yes"],
        ["exact − trunc", "Ridge", "MSE improve", "+0.044487", "[0.020955, 0.073430]", "0.043398", "10/10", "Yes"],
        ["trunc − simple", "HistGB", "Spearman", "+0.365595", "[0.215323, 0.493275]", "0.001750", "10/10", "Yes"],
        ["trunc − simple", "HistGB", "MSE improve", "+0.101934", "[0.048890, 0.135677]", "0.000800", "10/10", "Yes"],
        ["exact − trunc", "HistGB", "Spearman", "+0.037152", "[-0.058908, 0.101375]", "0.356982", "—", "No"],
        ["exact − trunc", "HistGB", "MSE improve", "+0.002329", "[-0.020657, 0.017988]", "0.770161", "—", "No"],
    ],
    [160, 78, 120, 96, 168, 84, 70, 88],
    ["left", "left", "left", "right", "right", "right", "right", "right"], header_h=26, row_h=24, size=8.8) \
    + band(430, "Supported: natural RK33 window CDS[3:45] carries the Kudla increment without ATG/UTR; coverage loss cannot solely explain RK28/RK33 negatives.") \
    + band(474, "C1 4 / 4 · C2 2 / 4 · HOST / ASSAY / STUDY-LEVEL FACTORS NOW PRIMARY CANDIDATES")
p3 = page("03 / PRIMARY DECISION",
    "Natural window retains the increment; coverage is not necessary",
    "D1 · RK33_COVERAGE_RETAINS_INCREMENT_WITHIN_KUDLA_RETROSPECTIVELY",
    p3_body,
    "Source: result c811bb6e3481 · independent 39/39 · closeout 99308d7fad54",
    167,
    ["C1 trunc_vs_simple passes all four endpoints: the natural RK33 window keeps a positive increment for both models and both metrics.",
     "C2 exact_vs_trunc passes only for Ridge; HistGB is not significant, so exact coverage adds little beyond the natural window here.",
     "Decision D1: coverage is not necessary within Kudla retrospectively; host, assay and study-level factors become the primary candidates."])

# ---------------- Page 162 · ABSOLUTE & SECONDARY ----------------
p4_body = table(48, 108, 864,
    ["Model", "Arm", "Spearman ρ", "MSE"],
    [
        ["Ridge", "simple", "-0.318413", "0.257149"],
        ["Ridge", "exact local d2", "+0.666270", "0.100223"],
        ["Ridge", "CDS-start d2", "+0.307810", "0.156892"],
        ["Ridge", "trunc CDS4-45 d2", "+0.417499", "0.144710"],
        ["Ridge", "trunc CDS4-45 d0", "+0.314038", "0.163578"],
        ["HistGB", "simple", "+0.302424", "0.198658"],
        ["HistGB", "exact local d2", "+0.705171", "0.094394"],
        ["HistGB", "CDS-start d2", "+0.602022", "0.117825"],
        ["HistGB", "trunc CDS4-45 d2", "+0.668019", "0.096724"],
        ["HistGB", "trunc CDS4-45 d0", "+0.538153", "0.133087"],
    ],
    [130, 350, 192, 192], ["left", "left", "right", "right"], header_h=26, row_h=24, size=9.1) \
    + band(392, "Secondary (descriptive · body-shift confounded): atg_vs_trunc is negative for both models (Ridge Δρ −0.109689, HistGB −0.065997).") \
    + band(432, "exact_vs_atg Ridge positive (Δρ +0.358460); trunc_d0_vs_simple mixed. Clean upstream/start decomposition deferred to RK34.")
p4 = page("04 / ABSOLUTE & SECONDARY",
    "Exact context leads; truncation keeps most of the gain",
    "Primary-seed absolute performance (Table 26) · secondary contrasts descriptive",
    p4_body,
    "Source: result c811bb6e3481 · primary seed 20261221 · null intercept ρ −0.367234 / MSE 0.194471",
    168,
    ["On the primary seed, exact local context is strongest (Ridge ρ 0.666, HistGB ρ 0.705); the natural truncated window keeps most of that gain.",
     "The CDS-start and dangles-0 arms sit between simple and exact, consistent with a coverage gradient rather than a single necessary element.",
     "Secondary contrasts are descriptive only because the body shifts; the clean upstream-versus-start decomposition is left to RK34."])

# ---------------- Page 163 · EVIDENCE & BOUNDARY ----------------
p5_body = kpis([
    ("INDEPENDENT", "39 / 39", "max pred Δ 1.33e-15", GREEN),
    ("CLEAN COMPARE", "12 / 12", "6 CSV byte-identical · 50 NPZ", GREEN),
    ("CLOSEOUT", "21 / 21", "freeze 291ccdbc · clean 9c26dcab", GREEN),
    ("PROJECT TESTS", "453", "passed · 1 skipped · 0 failed", TEAL),
]) + table(48, 202, 864,
    ["Stage", "Result", "Evidence"],
    [
        ["Label-free preflight", "24 / 24", "rk35_preflight_v1.json"],
        ["Synthetic unit tests", "15 / 15", "test_a8_rk35_coverage_transport.py"],
        ["Independent verifier v2", "39 / 39", "wall 185.09 s · gate Δ 0"],
        ["Clean reproduction", "12 / 12", "worktree 9c26dcab · compare v2"],
        ["Closeout", "21 / 21", "rk35_closeout_v1.json"],
    ],
    [240, 140, 484], ["left", "left", "left"], header_h=26, row_h=30) \
    + band(400, "Manuscript §6.46 + Tables 25/26 written and audited (integration 10/10, review 43/43); registry, tasks and handoff recorded.") \
    + band(440, "Boundary: same-cohort Kudla-retrospective diagnostic, not independent confirmation. RK34 ends window ablation; independent-validation / pivot decision pending user. RK-G1=false.")
p5 = page("05 / EVIDENCE & BOUNDARY",
    "Independent code and a clean checkout reproduce every value",
    "Verification chain closed · manuscript §6.46 synchronized · scope bounded",
    p5_body,
    "Source: closeout 99308d7fad54 · compare f8faf2b69392 · independent d037542df5ee · manuscript a76d0a97f240",
    169,
    ["An independent verifier and a clean checkout at the science commit reproduce every CSV byte-for-byte and every NPZ array exactly.",
     "The full project suite passes 453 tests with one skip and zero failures; the manuscript section was audited against the frozen result.",
     "This is a same-cohort retrospective diagnostic, not independent confirmation; the prompt makes RK34 the end of window ablation, so the independent-validation versus pivot decision is left to the user."])

for fn, content in [("rk35_p165.xml", p1), ("rk35_p166.xml", p2), ("rk35_p167.xml", p3),
                    ("rk35_p168.xml", p4), ("rk35_p169.xml", p5)]:
    (OUT / fn).write_text(content)
    print(fn, len(content))