#!/usr/bin/env python3
"""Build exactly one RK40 slide XML per invocation; never batch-write pages."""
from html import escape
from pathlib import Path
import argparse

BG = "rgba(248, 250, 252, 1)"
INK = "rgba(24, 37, 51, 1)"
MUTED = "rgba(105, 119, 135, 1)"
TEAL = "rgba(24, 158, 132, 1)"
PINK = "rgba(206, 65, 102, 1)"
AMBER = "rgba(176, 116, 24, 1)"
BORDER = "rgba(226, 232, 240, 1)"
ALT = "rgba(246, 248, 251, 1)"
GREEN = "rgba(220, 247, 238, 1)"
YELLOW = "rgba(255, 244, 211, 1)"
REDBAND = "rgba(255, 235, 239, 1)"
FONT = "Inter"
NOTE_COMMON = [
    "Source: RK40 independent ae5b90d0ac3c · clean closeout 7ddf1dab2bfaa92e.",
    "Independent verification: 5,031 checks; clean closeout: 948 checks; full project tests: 484 passed.",
    "Trajectories: 1,188 / 1,188 prefix checks PASS. Inference: >20,000 paired evaluations plus 1,188 prefix checks.",
    "Native calibration and external initialization are search diagnostics; independent common-input/SOTA remains unresolved.",
]


def txt(x, y, w, h, value, size=9, color=INK, bold=False, align="left", wrap=False):
    paragraphs = value if isinstance(value, (list, tuple)) else [value]
    ps = "".join(f"<p>{escape(str(p))}</p>" for p in paragraphs)
    wrap_attr = ' wrap="false"' if not wrap else ""
    return (f'<shape type="text" topLeftX="{x}" topLeftY="{y}" width="{w}" height="{h}">'
            f'<content fontSize="{size}" fontFamily="{FONT}" color="{color}" bold="{str(bold).lower()}" '
            f'lineSpacing="multiple:1.05" textAlign="{align}"{wrap_attr}>{ps}</content></shape>')


def rect(x, y, w, h, fill, radius=10, border=None):
    border_xml = f'<border color="{border}" width="1"/>' if border else ""
    return (f'<shape type="round-rect" topLeftX="{x}" topLeftY="{y}" width="{w}" height="{h}" presetHandlers="{radius}">'
            f'<fill><fillColor color="{fill}"/></fill>{border_xml}'
            '<content fontSize="16" fontFamily="思源黑体" color="rgba(31, 35, 41, 1)"/></shape>')


def header(section, title, subtitle):
    return [txt(48, 7, 480, 15, section, 8, TEAL, True),
            txt(650, 7, 262, 15, "A8 / RK40 / NORMALIZATION + BUDGET", 7, MUTED, False, "right"),
            txt(48, 27, 864, 40, title, 26, INK, True), rect(48, 72, 58, 4, TEAL, 1),
            txt(48, 80, 864, 18, subtitle, 9, MUTED)]


def kpis(cards):
    out = []
    for x, (label, value, caption, color) in zip([48, 268, 488, 708], cards):
        out += [rect(x, 104, 204, 76, "rgba(255, 255, 255, 1)", 10, BORDER),
                txt(x + 10, 110, 184, 14, label, 8, MUTED, True),
                txt(x + 10, 126, 184, 28, value, 20, color, True),
                txt(x + 10, 157, 184, 15, caption, 7, MUTED)]
    return out


def table(y, widths, rows, row_heights, font_size=9):
    assert len(widths) == len(rows[0]) and len(rows) == len(row_heights)
    out = [f'<table width="864" height="{sum(row_heights)}" topLeftX="48" topLeftY="{y}">', "<colgroup>"]
    out += [f'<col span="1" width="{w}"/>' for w in widths] + ["</colgroup>"]
    for ridx, (row, rh) in enumerate(zip(rows, row_heights)):
        out.append(f'<tr height="{rh}">')
        for cell in row:
            fill = INK if ridx == 0 else (ALT if ridx % 2 == 0 else None)
            fill_xml = f'<fillColor color="{fill}"/>' if fill else "<fillColor/>"
            color = "rgba(255, 255, 255, 1)" if ridx == 0 else INK
            out.append('<td><fill>' + fill_xml + '</fill>'
                       f'<content paddingTop="2" paddingBottom="2" paddingLeft="7" paddingRight="7" fontSize="{font_size}" '
                       f'fontFamily="{FONT}" color="{color}" bold="{str(ridx == 0).lower()}" lineSpacing="multiple:1" '
                       f'textAlign="left"><p>{escape(str(cell))}</p></content></td>')
        out.append("</tr>")
    return out + ["</table>"]


def band(y, text, fill, color):
    return [rect(48, y, 864, 30, fill, 8), txt(60, y + 3, 840, 24, text, 9, color, True, wrap=True)]


def footer(page, source):
    return [txt(48, 510, 810, 14, source, 7, MUTED), txt(886, 507, 28, 17, str(page), 9, INK, True, "right")]


def slide(page, section, title, subtitle, body, source, notes):
    parts = header(section, title, subtitle) + body + footer(page, source)
    note_xml = "".join(f"<p>{escape(n)}</p>" for n in list(notes) + NOTE_COMMON)
    return ('<slide xmlns="https://www.larkoffice.com/sml/2.0">\n'
            f'<style><fill><fillColor color="{BG}"/></fill></style>\n<data>\n' + "\n".join(parts)
            + f'\n</data>\n<note><content>{note_xml}</content></note>\n</slide>\n')


def page193():
    cards = [("DEVELOPMENT RECORDS", "18", "record is the inference unit", TEAL),
             ("SEEDS", "3", "all-seed direction required", TEAL),
             ("SEARCH ARMS", "5 + 1", "5 new + 1 accepted · raw11", TEAL),
             ("PRIMARY FAMILIES", "2", "two endpoints per family", TEAL)]
    flow = [("01", "Normalization", ["Raw vs native-source calibrated", "Search-time scale diagnostic only"]),
            ("02", "Budget", ["11 vs 101 real unique outputs", "Identical short-prefix trajectory"]),
            ("03", "Initialization", ["Random vs first LinearDesign output", "External seed is diagnostic only"]),
            ("04", "Frozen inference", ["Best utility + single-point HV", "Bootstrap + sign-flip + Holm"])]
    body = kpis(cards)
    for x, (num, title, lines) in zip([48, 268, 488, 708], flow):
        body += [rect(x, 204, 204, 200, "rgba(255, 255, 255, 1)", 10, BORDER),
                 txt(x + 12, 216, 60, 30, num, 20, TEAL, True),
                 txt(x + 12, 254, 180, 38, title, 12, INK, True, wrap=True),
                 txt(x + 12, 304, 180, 70, lines, 9, MUTED, False, wrap=True)]
    body += band(438, "Primary family A: calibrated_random_b11 − raw_random_b11 · family B: raw_random_b101 − raw_random_b11", GREEN, TEAL)
    body += band(474, "Calibrated and external-seeded arms are mechanism diagnostics—not common-input or independent-SOTA evidence", YELLOW, AMBER)
    return slide(193, "01 / FROZEN MECHANISM DESIGN", "Frozen controls separate scale, budget and initialization",
                 "Five new arms plus the accepted RK39 raw11 baseline · fixed protein and TAA · development-only mechanism test", body,
                 "Source: RK40 protocol 367be7986a78 · preregistration frozen before formal outcomes",
                 ["The accepted raw_random_b11 arm is reused from independently verified RK39.",
                  "Two primary families each require positive CI lower bounds, Holm significance, and positive effects for all three seeds.",
                  "Long-budget interactions and external initialization are diagnostic, not confirmatory rescue.",
                  "Native calibration and external initialization are prohibited from independent common-input claims."])


def page194():
    cards = [("NEW RUNS", "270 / 270", "18 records x 3 seeds x 5 arms", TEAL),
             ("NEW SCORER CALLS", "12,690", "real unique outputs only", TEAL),
             ("ANALYSIS RUNS", "324", "includes 54 accepted RK39 runs", TEAL),
             ("RAW POINTS", "13,284", "594 accepted + 12,690 new", TEAL)]
    rows = [["Audit item", "Verified value", "Interpretation"],
            ["Production + clean", "270 new runs each", "Same decision and 12,690 new scorer calls"],
            ["Short / long identity", "1188 / 1188 PASS", "101-point prefix exactly matches corresponding 11-point run"],
            ["Objective coverage", "11,275 unique sequences", "Independent verifier recomputes CAI, negative MFE, GC and motif terms"],
            ["External curves", "Not inferred", "Actual LinearDesign points only; no dense external fabrication"],
            ["Scientific boundary", "Mechanism gate only", "No unified time-matched or functional conclusion"]]
    body = kpis(cards) + table(204, [190, 280, 394], rows, [28, 38, 38, 38, 38, 38])
    body += band(438, "Production and detached clean execution completed all planned runs with identical scientific decision", GREEN, TEAL)
    body += band(474, "Run completion and trajectory identity validate execution—not external performance or functional efficacy", YELLOW, AMBER)
    return slide(194, "02 / EXECUTION + TRAJECTORY AUDIT", "270 runs completed with exact long/short prefix identity",
                 "Production and clean runs · real unique-scorer accounting · no external dense-curve inference", body,
                 "Source: production fedfa3209723 · clean 36542aa4e2c0 · trajectory audit 1188/1188",
                 ["The formal design adds 270 runs and 12,690 scorer calls; 54 raw11 runs are accepted from RK39.",
                  "The 324 analysis runs contain 13,284 raw points.",
                  "Every long-run short prefix matches the corresponding short run for all 1,188 point checks.",
                  "No external dense curve, functional label, or time-matched claim is introduced."])


def page195():
    cards = [("UTILITY EFFECT", "+0.040193", "calibrated11 − raw11", TEAL),
             ("SINGLE-POINT HV EFFECT", "+0.018154", "paired within-record effect", TEAL),
             ("SEED DIRECTION", "3 / 3 positive", "for both primary endpoints", TEAL),
             ("FAMILY GATE", "PASS", "both CI lower bounds > 0", TEAL)]
    rows = [["Primary endpoint", "Effect", "95% confidence interval", "Holm p", "Seed means"],
            ["Best normalized weighted utility", "+0.040193", "[+0.025678, +0.055808]", "1.9999e-4", "3 / 3 positive"],
            ["Best single-point normalized HV", "+0.018154", "[+0.009908, +0.028232]", "1.9999e-4", "3 / 3 positive"]]
    body = kpis(cards) + table(204, [230, 130, 260, 110, 134], rows, [28, 62, 62])
    body += [txt(80, 374, 800, 40, "Absolute raw11 → calibrated11: utility 2.457592 → 2.497785 · single-point HV 0.287328 → 0.305482", 10, MUTED, False, "center", True)]
    body += band(438, "SEARCH_SCALE_MISMATCH_SUPPORTED_AT_SHORT_BUDGET · normalization family passes", GREEN, TEAL)
    body += band(474, "The effect is real but small: native-source calibration is diagnostic and cannot establish common-input SOTA", YELLOW, AMBER)
    return slide(195, "03 / PRIMARY FAMILY A — NORMALIZATION", "Calibrated search improves both short-budget endpoints",
                 "20,000 paired bootstrap + 20,000 sign-flip · Holm across two endpoints · all three seeds positive", body,
                 "Source: production fedfa3209723 · primary family normalization_at_short_budget",
                 ["Calibrated random search improves best utility by 0.0401927 at budget 11.",
                  "Best single-point normalized HV improves by 0.0181540.",
                  "Both Holm-adjusted sign-flip p values are 0.00019999 and every seed mean is positive.",
                  "The normalization family passes, but the absolute gain is small and not an external-SOTA result."])


def page196():
    cards = [("UTILITY EFFECT", "+1.739176", "raw101 − raw11", TEAL),
             ("SINGLE-POINT HV EFFECT", "+1.322804", "paired within-record effect", TEAL),
             ("SEED DIRECTION", "3 / 3 positive", "for both primary endpoints", TEAL),
             ("FAMILY GATE", "PASS", "both CI lower bounds > 0", TEAL)]
    rows = [["Primary endpoint", "Effect", "95% confidence interval", "Holm p", "Seed means"],
            ["Best normalized weighted utility", "+1.739176", "[+1.530088, +1.964111]", "9.9995e-5", "3 / 3 positive"],
            ["Best single-point normalized HV", "+1.322804", "[+0.992600, +1.666782]", "9.9995e-5", "3 / 3 positive"]]
    body = kpis(cards) + table(204, [230, 130, 260, 110, 134], rows, [28, 62, 62])
    body += [txt(80, 374, 800, 40, "Absolute raw11 → raw101: utility 2.457592 → 4.196768 · single-point HV 0.287328 → 1.610131", 10, MUTED, False, "center", True)]
    body += band(438, "SHORT_BUDGET_LIMIT_SUPPORTED_WITHIN_RAW_SEARCH · raw-budget family passes", GREEN, TEAL)
    body += band(474, "Diagnostic calibrated101 reaches 4.770496 / 2.892627; long-budget interactions do not enter the primary gate", YELLOW, AMBER)
    return slide(196, "04 / PRIMARY FAMILY B — BUDGET", "Raw budget 101 improves both primary endpoints",
                 "Identical initialization and raw weights · short prefix exact · inference across 18 development records", body,
                 "Source: production fedfa3209723 · primary family budget_within_raw_search",
                 ["Raw budget 101 improves best utility by 1.739176 over budget 11.",
                  "Best single-point normalized HV improves by 1.322804.",
                  "Both Holm-adjusted sign-flip p values are 0.000099995 and every seed mean is positive.",
                  "Calibrated long-budget results are diagnostic and cannot repair a failed external comparison."])


def page197():
    cards = [("EXTERNAL-SEED UTILITY EFFECT", "+8.587983", "raw external11 − raw random11", TEAL),
             ("EXTERNAL-SEED HV EFFECT", "+15.787477", "diagnostic; not independent design", TEAL),
             ("INDEPENDENT VERIFIER", "5031 / 5031", "11,275 sequences · max error 0.0", TEAL),
             ("CLEAN CLOSEOUT", "948 / 948", "pointwise and inferential identity", TEAL)]
    rows = [["Stage / arm", "Utility", "Single-point HV", "Evidence status"],
            ["Raw random11", "2.457592", "0.287328", "accepted baseline"],
            ["Calibrated random101", "4.770496", "2.892627", "diagnostic long arm"],
            ["Raw external11", "11.045575", "16.074805", "external-initialized diagnostic"],
            ["Calibrated external11", "11.049869", "16.135076", "external-initialized diagnostic"],
            ["Independent + clean", "5031 PASS", "948 PASS", "raw objectives, metrics, inference and decision"]]
    body = kpis(cards) + table(204, [230, 150, 180, 304], rows, [28, 38, 38, 38, 38, 38])
    body += band(438, "Initialization diagnostics are descriptively much larger than short-budget normalization effects", GREEN, TEAL)
    body += band(474, "External seeds are LinearDesign outputs: they diagnose search basins, not an independent CodonFlow design", YELLOW, AMBER)
    return slide(197, "05 / INITIALIZATION DIAGNOSTIC + REPRODUCTION", "External initialization exposes a large search-basin effect",
                 "Diagnostic contrasts are non-confirmatory · independent raw rescoring and detached clean comparison verify the result", body,
                 "Source: independent 5031 checks · clean closeout 948 checks · full project tests 484 passed",
                 ["Raw external initialization has a diagnostic utility effect of 8.587983 and HV effect of 15.787477 over random initialization.",
                  "The calibrated external contrast is similarly large and remains non-confirmatory.",
                  "Independent verification passes 5,031 checks over 11,275 unique sequences with zero maximum objective error.",
                  "The detached clean closeout passes 948 checks; the full project suite records 484 passed tests."])


def page198():
    cards = [("MECHANISM DECISION", "Both contribute", "normalization + short budget", TEAL),
             ("COMMON-INPUT TASK", "Unresolved", "RK39 defeat is not reversed", PINK),
             ("EXTERNAL SOTA", "false", "no authorized ranking", PINK),
             ("FUNCTIONAL / SUBMITTABLE", "false / false", "functional labels untouched", PINK)]
    rows = [["Boundary", "Allowed interpretation", "Required next evidence"],
            ["Normalization", "Small positive internal short-budget effect", "Common-input algorithm without native-search calibration"],
            ["Budget", "More real evaluations improve internal best-single metrics", "Actual-set and unified cost-matched comparison"],
            ["Initialization", "External seeds expose a search-basin limitation", "Preregistered internal multi-start or basin-aware search"],
            ["External + functional", "No SOTA, functional, untouched or OOD claim", "Strong baselines and feasibility-gated untouched validation"],
            ["Manuscript", "Working preprint remains non-submittable", "Resolve core comparative and functional gates"]]
    body = kpis(cards) + table(204, [190, 360, 314], rows, [28, 38, 38, 38, 38, 38])
    body += band(438, "NORMALIZATION_AND_SHORT_BUDGET_BOTH_CONTRIBUTE · mechanism resolved, design task still open", GREEN, TEAL)
    body += band(474, "Next: basin-aware internal initialization followed by common-input actual-set and time-matched evaluation", YELLOW, AMBER)
    return slide(198, "06 / SCIENTIFIC BOUNDARY + NEXT TEST", "Mechanism resolved; common-input design remains open",
                 "Do not convert internal proxy gains into independent-SOTA, functional, OOD or submission claims", body,
                 "Source: RK40 independent and clean closeout · scientific gate false · RK-G1 open",
                 ["RK40 supports contributions from search normalization and short budget under frozen internal proxy endpoints.",
                  "External-seeded arms identify a basin problem but are not independent CodonFlow designs.",
                  "RK39 common-input actual-set failure, external SOTA, functional untouched, protein OOD, RK-G1 and submission gates remain open.",
                  "The next discriminating step is internal basin-aware initialization followed by common-input actual-set and unified-cost evaluation."])


BUILDERS = {193: page193, 194: page194, 195: page195, 196: page196, 197: page197, 198: page198}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("page", type=int, choices=sorted(BUILDERS))
    args = parser.parse_args()
    output = Path(f"rk40_{args.page}.xml")
    output.write_text(BUILDERS[args.page](), encoding="utf-8")
    print(output.resolve())
