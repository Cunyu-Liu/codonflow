#!/usr/bin/env python3
"""Build exactly one RK39 slide XML per invocation; never batch-write pages."""
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


def txt(x, y, w, h, value, size=9, color=INK, bold=False, align="left", wrap=False):
    paragraphs = value if isinstance(value, (list, tuple)) else [value]
    ps = "".join(f"<p>{escape(str(p))}</p>" for p in paragraphs)
    wrap_attr = ' wrap="false"' if not wrap else ""
    return (
        f'<shape type="text" topLeftX="{x}" topLeftY="{y}" width="{w}" height="{h}">'
        f'<content fontSize="{size}" fontFamily="{FONT}" color="{color}" bold="{str(bold).lower()}" '
        f'lineSpacing="multiple:1.05" textAlign="{align}"{wrap_attr}>{ps}</content></shape>'
    )


def rect(x, y, w, h, fill, radius=10, border=None):
    border_xml = f'<border color="{border}" width="1"/>' if border else ""
    return (
        f'<shape type="round-rect" topLeftX="{x}" topLeftY="{y}" width="{w}" height="{h}" presetHandlers="{radius}">'
        f'<fill><fillColor color="{fill}"/></fill>{border_xml}'
        f'<content fontSize="16" fontFamily="思源黑体" color="rgba(31, 35, 41, 1)"/></shape>'
    )


def header(section, title, subtitle):
    return [
        txt(48, 7, 480, 15, section, 8, TEAL, True),
        txt(650, 7, 262, 15, "A8 / RK39 / COMMON INPUT + ACTUAL SET", 7, MUTED, False, "right"),
        txt(48, 27, 864, 40, title, 26, INK, True),
        rect(48, 72, 58, 4, TEAL, 1),
        txt(48, 80, 864, 18, subtitle, 9, MUTED),
    ]


def kpis(cards):
    out = []
    xs = [48, 268, 488, 708]
    for x, (label, value, caption, color) in zip(xs, cards):
        out += [
            rect(x, 104, 204, 76, "rgba(255, 255, 255, 1)", 10, BORDER),
            txt(x + 10, 110, 184, 14, label, 8, MUTED, True),
            txt(x + 10, 126, 184, 28, value, 20, color, True),
            txt(x + 10, 157, 184, 15, caption, 7, MUTED),
        ]
    return out


def table(y, widths, rows, row_heights, font_size=9):
    assert len(widths) == len(rows[0])
    assert len(rows) == len(row_heights)
    total_h = sum(row_heights)
    out = [f'<table width="864" height="{total_h}" topLeftX="48" topLeftY="{y}">', "<colgroup>"]
    out += [f'<col span="1" width="{w}"/>' for w in widths]
    out.append("</colgroup>")
    for ridx, (row, rh) in enumerate(zip(rows, row_heights)):
        out.append(f'<tr height="{rh}">')
        for cell in row:
            fill = INK if ridx == 0 else (ALT if ridx % 2 == 0 else None)
            fill_xml = f'<fillColor color="{fill}"/>' if fill else "<fillColor/>"
            color = "rgba(255, 255, 255, 1)" if ridx == 0 else INK
            out.append(
                '<td><fill>' + fill_xml + '</fill>'
                f'<content paddingTop="2" paddingBottom="2" paddingLeft="7" paddingRight="7" '
                f'fontSize="{font_size}" fontFamily="{FONT}" color="{color}" bold="{str(ridx == 0).lower()}" '
                f'lineSpacing="multiple:1" textAlign="left"><p>{escape(str(cell))}</p></content></td>'
            )
        out.append("</tr>")
    out.append("</table>")
    return out


def band(y, text, fill, color):
    return [rect(48, y, 864, 30, fill, 8), txt(60, y + 3, 840, 24, text, 9, color, True, wrap=True)]


def footer(page, source):
    return [
        txt(48, 510, 810, 14, source, 7, MUTED),
        txt(886, 507, 28, 17, str(page), 9, INK, True, "right"),
    ]


def slide(page, section, title, subtitle, body, source, notes):
    parts = header(section, title, subtitle) + body + footer(page, source)
    note_xml = "".join(f"<p>{escape(n)}</p>" for n in notes)
    return (
        '<slide xmlns="https://www.larkoffice.com/sml/2.0">\n'
        f'<style><fill><fillColor color="{BG}"/></fill></style>\n'
        '<data>\n' + "\n".join(parts) + '\n</data>\n'
        f'<note><content>{note_xml}</content></note>\n</slide>\n'
    )


def page187():
    cards = [
        ("DEVELOPMENT PROTEINS", "18", "fixed before outcome access", TEAL),
        ("SEEDS PER ARM", "3", "record is the inference unit", TEAL),
        ("SEARCH ARMS", "3", "primary plus two diagnostics", TEAL),
        ("SCORER CALLS", "1,782", "162 runs x 11 points", TEAL),
    ]
    flow = [
        ("01", "Protein only", ["Translate native CDS once", "Discard native synonymous choices"]),
        ("02", "Common initialization", ["First-codon template + RNG", "Native CDS never enters search"]),
        ("03", "Fixed stop + evaluation", ["TAA for every method", "No native normalization in search"]),
        ("04", "Matched actual sets", ["First k real unique outputs", "No best-k or zero filling"]),
    ]
    body = kpis(cards)
    for x, (num, title, lines) in zip([48, 268, 488, 708], flow):
        body += [
            rect(x, 204, 204, 200, "rgba(255, 255, 255, 1)", 10, BORDER),
            txt(x + 12, 216, 60, 30, num, 20, TEAL, True),
            txt(x + 12, 254, 180, 38, title, 12, INK, True, wrap=True),
            txt(x + 12, 304, 180, 70, lines, 9, MUTED, False, wrap=True),
        ]
    for x in [252, 472, 692]:
        body.append(f'<line startX="{x}" startY="304" endX="{x + 16}" endY="304"><border color="{TEAL}" width="2"/><endArrow type="arrow"/></line>')
    body += band(438, "Primary arm: hill-climbing vs LinearDesign-11 · co-primary normalized HV and pairwise NED", GREEN, TEAL)
    body += band(474, "20,000 paired bootstrap + 20,000 sign-flip · Holm over two endpoints · all seeds must be positive", YELLOW, AMBER)
    return slide(187, "01 / FROZEN FAIR-COMPARISON PROTOCOL", "The fair comparison was frozen before outcomes were seen",
                 "Protein-only synonymous initialization · fixed TAA · matched unique-DNA cardinality", body,
                 "Source: RK39 protocol 6e72fc94bd39 · preregistered primary and sensitivity analyses",
                 ["Native CDS is used only to obtain the protein and is excluded from search initialization and normalization.",
                  "Every method is evaluated with fixed terminal TAA and identical post-search calibration.",
                  "Each simple-search archive uses its first k real unique outputs, where k matches LinearDesign-11.",
                  "The primary comparison and both co-primary endpoints were frozen before result inspection."])


def page188():
    cards = [
        ("COMPLETED RUNS", "162 / 162", "18 records x 3 seeds x 3 arms", TEAL),
        ("UNIQUE-SCORER CALLS", "1,782", "11 real points per run", TEAL),
        ("WORKERS", "4", "single-thread execution", TEAL),
        ("WALL TIME", "342.52 s", "1,311.998 s summed scoring", TEAL),
    ]
    rows = [
        ["Audit item", "Verified value", "Interpretation"],
        ["Frozen design", "18 records x 3 seeds x 3 arms", "11 scored points per run; no inferred external dense curve"],
        ["Run completion", "162 runs / 1,782 calls", "All planned production runs completed"],
        ["Matched cardinality", "131 total · mean 7.278 · range 4-11", "Real LinearDesign-11 unique-DNA count per record"],
        ["Input audit", "Protein-only initialization · fixed TAA", "Native CDS and native-derived normalization excluded from search"],
        ["Selection audit", "First k outputs only", "No best-k, zero filling or post-hoc subset selection"],
    ]
    body = kpis(cards) + table(204, [190, 280, 394], rows, [28, 38, 38, 38, 38, 38])
    body += band(438, "Production and clean runs both completed 162 runs / 1,782 calls with the same scientific decision", GREEN, TEAL)
    body += band(474, "Execution coverage establishes what was run; it does not establish scientific success", YELLOW, AMBER)
    return slide(188, "02 / EXECUTION AND COVERAGE", "All 162 runs completed; coverage is not a model win",
                 "Four single-thread workers · real scorer outputs · no zero filling or post-hoc archive selection", body,
                 "Source: production b9882da07404 · clean 0f24145a78fa · independent 824b07b985ef",
                 ["The frozen design contains 162 runs and 1,782 unique-scorer calls.",
                  "LinearDesign-11 contributes 131 matched unique DNA outputs across the 18 records.",
                  "Production and clean execution reproduce the same run counts and scientific decision.",
                  "Execution coverage is reported separately from model performance."])


def page189():
    cards = [
        ("HV EFFECT", "-29.714618", "hill-climbing minus LinearDesign-11", PINK),
        ("NED EFFECT", "-0.066598", "paired within-record diversity effect", PINK),
        ("POSITIVE RECORDS", "0 / 18", "for each co-primary endpoint", PINK),
        ("SEED DIRECTION", "3 / 3 negative", "for both co-primary endpoints", PINK),
    ]
    rows = [
        ["Co-primary endpoint", "Paired effect", "95% confidence interval", "Holm p", "Direction"],
        ["Normalized HV", "-29.714618", "[-41.925699, -19.552535]", "9.9995e-5", "0 / 18 positive"],
        ["Pairwise NED", "-0.066598", "[-0.082247, -0.051135]", "9.9995e-5", "0 / 18 positive"],
    ]
    body = kpis(cards) + table(204, [170, 150, 280, 120, 144], rows, [28, 62, 62])
    body += [txt(80, 374, 800, 40, "Record is the statistical unit: three seeds are averaged within each record before paired inference across 18 records", 10, MUTED, False, "center", True)]
    body += band(438, "COMMON_INPUT_ACTUAL_SET_TASK_UNRESOLVED · primary gate: false", REDBAND, PINK)
    body += band(474, "Both intervals exclude zero in the negative direction: a significant loss, not an inconclusive result", YELLOW, AMBER)
    return slide(189, "03 / CONFIRMATORY PRIMARY RESULT", "LinearDesign-11 wins both primary endpoints on every record",
                 "20,000 paired bootstrap · 20,000 sign-flip · Holm across two endpoints · three-seed consistency required", body,
                 "Source: production tests b9882da07404 · independent recomputation 824b07b985ef",
                 ["Hill-climbing loses normalized hypervolume by 29.714618 and pairwise NED by 0.066598.",
                  "Both effects are negative on all 18 records and for every seed-averaged direction.",
                  "Holm-adjusted sign-flip p is 9.9995e-5 for both co-primary endpoints.",
                  "The common-input actual-set task remains unresolved; the primary gate fails."])


def page190():
    cards = [
        ("LINEARDESIGN-11 HV", "29.972887", "mean normalized hypervolume", TEAL),
        ("LINEARDESIGN-11 NED", "0.071289", "mean pairwise diversity", TEAL),
        ("UNIFORM HV", "0.720246", "still far below the comparator", PINK),
        ("UNIFORM NED", "0.240866", "diversity only; not functional quality", TEAL),
    ]
    rows = [
        ["Method", "Normalized HV", "Pairwise NED", "Effect HV", "Effect NED"],
        ["LinearDesign-11", "29.972887", "0.071289", "reference", "reference"],
        ["Hill-climbing", "0.258270", "0.004692", "-29.714618", "-0.066598"],
        ["MH-annealing", "0.259383", "0.004857", "-29.713504", "-0.066432"],
        ["Uniform synonymous", "0.720246", "0.240866", "-29.252642", "+0.169577"],
    ]
    body = kpis(cards) + table(204, [220, 160, 160, 160, 164], rows, [28, 42, 42, 42, 42])
    body += band(438, "Uniform improves NED on 18 / 18 records but loses HV on 18 / 18: a proxy tradeoff, not a rescue", YELLOW, AMBER)
    body += band(474, "MH-annealing is negative on both endpoints; sensitivity arms are diagnostic and cannot overturn the primary gate", REDBAND, PINK)
    return slide(190, "04 / ABSOLUTE PERFORMANCE + SENSITIVITY", "Uniform raises diversity but still loses hypervolume",
                 "Absolute actual-set metrics · effects are simple-search minus LinearDesign-11 · sensitivity is not confirmatory rescue", body,
                 "Source: production b9882da07404 · absolute values averaged over seeds within records, then across records",
                 ["LinearDesign-11 has mean normalized HV 29.972887 and mean pairwise NED 0.071289.",
                  "Hill-climbing and MH-annealing are both far below LinearDesign-11 on HV and NED.",
                  "Uniform improves NED on all records but loses HV on all records.",
                  "The uniform result is a proxy quality-diversity tradeoff and cannot rescue the failed primary gate."])


def page191():
    cards = [
        ("INDEPENDENT VERIFIER", "1216 / 1216", "raw points, objectives, metrics and inference", TEAL),
        ("CLEAN CLOSEOUT", "830 / 830", "pointwise production-clean agreement", TEAL),
        ("MAX OBJECTIVE ERROR", "0.0", "1,594 independently rescored sequences", TEAL),
        ("FULL PROJECT TESTS", "477 passed", "1 skipped · 5 subtests passed", TEAL),
    ]
    rows = [
        ["Stage", "Result", "Verified evidence"],
        ["Production", "162 runs / 1,782 calls", "Raw run JSON archived on /teams; summary committed"],
        ["Independent verifier", "1216 / 1216 PASS", "1,594 unique sequences · four objectives · maximum absolute error 0.0"],
        ["Detached clean reproduction", "830 / 830 PASS", "Initial states, budgets, objectives, actual-set metrics, inference and decision agree"],
        ["Full project tests", "477 passed", "1 skipped · 5 subtests passed"],
        ["Manuscript §6.50 + Tables 32-33", "638 words · PASS", "prepare + write + deliver · idempotent integration · two native tables"],
    ]
    body = kpis(cards) + table(204, [220, 190, 454], rows, [28, 38, 38, 38, 38, 38])
    body += band(438, "Science commit b3f89b94 · clean + manuscript commit 9bbac1a6 · remote origin verified", GREEN, TEAL)
    body += band(474, "Clean comparison excludes wall time and file hashes; large raw runs remain outside Git on /teams", YELLOW, AMBER)
    return slide(191, "05 / INDEPENDENT REPRODUCTION + PAPER", "Independent and clean checks reproduce the negative result",
                 "Raw-sequence recomputation · detached clean run · full tests · manuscript §6.50 and Tables 32-33 synchronized", body,
                 "Source: independent 824b07b985ef · clean closeout a5695d6fff · manuscript 611a0ceec7ad",
                 ["The independent verifier passes 1,216 checks and independently rescores 1,594 unique sequences.",
                  "The detached clean closeout passes 830 checks and reproduces the same negative scientific decision.",
                  "The full project suite records 477 passed tests, one skip and five passed subtests.",
                  "Manuscript section 6.50 and Tables 32-33 are synchronized with the verified reports."])


def page192():
    cards = [
        ("EXTERNAL SOTA", "false", "one comparator; no unified dense ranking", PINK),
        ("TIME-MATCHED", "false", "cost scopes are not unified", PINK),
        ("FUNCTIONAL UNTOUCHED", "false", "outcomes were not read or evaluated", PINK),
        ("RK-G1 / SUBMITTABLE", "false / false", "scientific gates remain open", PINK),
    ]
    rows = [
        ["Open gate", "What is still missing", "Allowed next evidence"],
        ["Common dense + time-matched", "No shared dense curves or unified cost accounting", "Preregistered matched-budget study"],
        ["Functional + protein OOD", "No functional labels read or evaluated", "Feasibility audit before outcome access"],
        ["Generator evidence", "A7/G2 failed; costly training is not authorized", "No automatic retraining or SOTA claim"],
        ["Prospective validation", "No wet-lab or prospective DBTL result", "Strong algorithmic + wild-type controls"],
        ["Manuscript readiness", "Core functional and comparative claims remain unsupported", "Keep non-submittable working-draft status"],
    ]
    body = kpis(cards) + table(204, [220, 380, 264], rows, [28, 38, 38, 38, 38, 38])
    body += band(438, "RK39 closes one fair comparison; the common-input actual-set task remains unresolved", REDBAND, PINK)
    body += band(474, "Next evidence must discriminate a scientific claim; engineering volume and repeated negative results are not enough", YELLOW, AMBER)
    return slide(192, "06 / SCIENTIFIC BOUNDARY", "The comparison is closed; the scientific question is not",
                 "Common-input fairness is necessary but insufficient · external, functional, prospective and submission gates remain open", body,
                 "Source: RK39 clean closeout a5695d6fff · scientific gate false · manuscript remains non-submittable",
                 ["RK39 closes the specified common-input actual-set comparison with a negative result.",
                  "External SOTA, unified time matching and functional untouched confirmation remain false.",
                  "Protein OOD, prospective DBTL, wet-lab validation and generator evidence remain unresolved.",
                  "The next step must supply discriminating scientific evidence rather than inflate claims."])


BUILDERS = {187: page187, 188: page188, 189: page189, 190: page190, 191: page191, 192: page192}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("page", type=int, choices=sorted(BUILDERS))
    args = parser.parse_args()
    output = Path(f"rk39_{args.page}.xml")
    output.write_text(BUILDERS[args.page](), encoding="utf-8")
    print(output.resolve())
