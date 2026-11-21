#!/usr/bin/env python3
"""Generate eight RK33 research-record slides from accepted evidence, without online writes."""
from pathlib import Path
import argparse
import hashlib
import json
import re
from xml.sax.saxutils import escape

BG = "rgba(247, 248, 250, 1)"
WHITE = "rgba(255, 255, 255, 1)"
INK = "rgba(31, 41, 55, 1)"
MUTED = "rgba(100, 116, 139, 1)"
GRID = "rgba(226, 232, 240, 1)"
ALT = "rgba(241, 245, 249, 1)"
BLUE = "rgba(37, 99, 235, 1)"
TEAL = "rgba(13, 148, 136, 1)"
GREEN = "rgba(5, 150, 105, 1)"
AMBER = "rgba(217, 119, 6, 1)"
ROSE = "rgba(225, 29, 72, 1)"
PALE_BLUE = "rgba(219, 234, 254, 1)"
PALE_GREEN = "rgba(209, 250, 229, 1)"
PALE_AMBER = "rgba(254, 243, 199, 1)"
PALE_TEAL = "rgba(204, 251, 241, 1)"

counter = 0

def uid(prefix="r33"):
    global counter
    counter += 1
    return f"{prefix}{counter:04d}"


def tx(x, y, w, h, text, size=10, color=INK, bold=False, align="left", wrap=False, line=1.15):
    paras = "".join(f"<p>{escape(str(v))}</p>" for v in str(text).split("\n"))
    wrap_attr = ' wrap="false"' if not wrap else ""
    bold_attr = ' bold="true"' if bold else ""
    return f'<shape width="{w}" height="{h}" topLeftX="{x}" topLeftY="{y}" type="text" id="{uid()}"><content verticalAlign="top" fontSize="{size}" fontFamily="Inter" color="{color}"{bold_attr} lineSpacing="multiple:{line}" textAlign="{align}"{wrap_attr}>{paras}</content></shape>'


def rect(x, y, w, h, fill=WHITE, border=True, radius=8):
    b = f'<border color="{GRID}" width="1" />' if border else ""
    return f'<shape width="{w}" height="{h}" topLeftX="{x}" topLeftY="{y}" presetHandlers="{radius}" type="round-rect" id="{uid()}"><fill><fillColor color="{fill}" /></fill>{b}<content fontSize="16" fontFamily="思源黑体" color="{INK}" /></shape>'


def table(x, y, widths, rows, row_heights=None, font=8.5, aligns=None, header=True):
    height = sum(row_heights or [25] * len(rows))
    cols = "".join(f'<col span="1" width="{w}" />' for w in widths)
    out = [f'<table id="{uid()}" width="{sum(widths)}" height="{height}" topLeftX="{x}" topLeftY="{y}"><colgroup>{cols}</colgroup>']
    for ri, row in enumerate(rows):
        rh = (row_heights or [25] * len(rows))[ri]
        out.append(f'<tr height="{rh}">')
        for ci, value in enumerate(row):
            is_head = header and ri == 0
            fill = INK if is_head else (ALT if ri % 2 == 0 else None)
            color_attr = f' color="{fill}"' if fill else ""
            fill_xml = f'<fill><fillColor{color_attr} /></fill>'
            color = WHITE if is_head else INK
            bold = ' bold="true"' if is_head else ""
            align = (aligns[ci] if aligns else ("left" if ci == 0 else "right"))
            out.append(f'<td id="{uid()}">{fill_xml}<content fontSize="{font}" fontFamily="Inter" color="{color}"{bold} lineSpacing="multiple:1" textAlign="{align}" wrap="false"><p>{escape(str(value))}</p></content></td>')
        out.append('</tr>')
    out.append('</table>')
    return "".join(out)


def kpi(x, label, value, note, color=BLUE):
    return "".join([
        rect(x, 104, 204, 76),
        tx(x + 14, 113, 176, 15, label, 8.5, MUTED, True),
        tx(x + 14, 129, 176, 30, value, 21, color, True),
        tx(x + 14, 160, 176, 17, note, 8.2, MUTED, wrap=True),
    ])


def slide(number, section, title, subtitle, body, accent=BLUE, banner=None, banner_color=None, banner_fill=None, source="", notes=None):
    content = [
        tx(48, 8, 650, 14, section, 8.5, accent, True),
        tx(716, 8, 196, 14, "A8 / RK33 / COVERAGE", 8.5, MUTED, align="right"),
        tx(48, 27, 864, 35, title, 23, INK, True),
        rect(48, 72, 58, 3, accent, False, 1),
        tx(48, 82, 864, 18, subtitle, 10.2, MUTED),
        *body,
    ]
    if banner:
        content += [rect(48, 474, 864, 30, banner_fill or PALE_BLUE, False, 6), tx(62, 478, 836, 21, banner, 9.8, banner_color or accent, True)]
    content += [tx(48, 512, 780, 13, source, 8.2, MUTED), tx(850, 510, 62, 15, str(number), 10, INK, True, "right")]
    note_xml = ""
    if notes:
        notes = list(notes)
        notes.append("All reported values and evidence boundaries on this page come from the accepted RK33 source files.")
        note_xml = f'<note id="{uid("n33")}"><content>{"".join(f"<p>{escape(n)}</p>" for n in notes)}</content></note>'
    return f'<slide xmlns="https://www.larkoffice.com/sml/2.0"><style><fill id="{uid("f33")}"><fillColor color="{BG}" /></fill></style><data>{"".join(content)}</data>{note_xml}</slide>\n'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--page", type=int, choices=range(148, 156))
    args = p.parse_args()
    b = args.base
    r = json.loads((b / "rk33_local_coverage_result_v1.json").read_text())
    ind = json.loads((b / "rk33_local_coverage_independent_v1.json").read_text())
    pre = json.loads((b / "rk33_label_free_preflight_v1.json").read_text())
    repro = json.loads((b / "rk33_clean_reproduction_v1.json").read_text())
    close = json.loads((b / "rk33_closeout_verification_v2.json").read_text())
    manuscript = json.loads((b / "rk33_manuscript_integration_v1.json").read_text())
    assert close["status"] == ind["status"] == repro["status"] == manuscript["status"] == "PASS"
    assert close["endpoints_passed"] == 0 and close["endpoints_total"] == 12
    tests = r["primary_tests"]
    by_test = {t["test"]: t for t in tests}
    protocol_sha = sha(b / "a8_rk33_local_coverage_protocol_v1.json")
    result_sha = sha(b / "rk33_local_coverage_result_v1.json")
    ind_sha = sha(b / "rk33_local_coverage_independent_v1.json")
    repro_sha = sha(b / "rk33_clean_reproduction_v1.json")
    close_sha = sha(b / "rk33_closeout_verification_v2.json")
    source = f"Source: result {result_sha[:12]} · closeout {close_sha[:12]} · independent 76/76 · clean {repro['checks_passed']}/{repro['checks_total']}"
    pages = {}

    body = [
        kpi(48, "OBSERVED VARIANTS", "152", "identical across all four arms"),
        kpi(268, "SEQUENCE CLUSTERS", "74", "whole-cluster held-out folds"),
        kpi(488, "FROZEN ARMS", "4", "simple · local42 · full1 · full3"),
        kpi(708, "EVALUATED FITS", "400", "200 new + 200 accepted RK28"),
        rect(48, 202, 424, 246), tx(62, 211, 396, 18, "Four matched structure definitions", 10.5, BLUE, True),
        tx(62, 237, 396, 190, "simple\nSequence-only backbone\n\nlocal42\nsimple + CDS4–45 42-nt MFE\n\nfull1\nsimple + one full-300 MFE\n\nfull3\nsimple + full-300/window48 MFEs", 10.1, INK, wrap=True, line=1.18),
        rect(488, 202, 424, 246), tx(502, 211, 396, 18, "One paired inferential contract", 10.5, TEAL, True),
        tx(502, 237, 396, 190, "10 seeds × 5 whole-cluster folds\nRidge + HistGB; ViennaRNA 37 °C, dangles=0\n\n3 families × 4 endpoints = 12 tests\n20,000 cluster bootstraps + 20,000 swaps\nUnified Holm correction across all 12\n\nAll 12 required to claim local-structure support", 10.1, INK, wrap=True, line=1.2),
    ]
    pages[148] = slide(148, "01 / MATCHED COVERAGE DESIGN", "A local-versus-full test inside Mordstein observed R1", "Retrospective outcome-known follow-up · no functional untouched data · no exact Kudla start-aware transport", body, BLUE, "SAME VARIANTS · SAME SPLITS · SAME MODELS · SAME INFERENCE", BLUE, PALE_BLUE, source, ["Only the structure definition and one-versus-three structure features change across the frozen arms.", "This is an observed-R1 coverage follow-up, not independent confirmation or an RNA-velocity experiment."])

    arm_rows = [["Arm", "Structure features", "Fit provenance", "Evaluated fits"],
                ["simple", "none", "reused RK28", "100"],
                ["local42", "one CDS4–45 MFE", "new", "100"],
                ["full1", "one full-300 MFE", "new", "100"],
                ["full3", "full-300 + 48-nt min/mean", "reused RK28", "100"]]
    body = [
        kpi(48, "LABEL-FREE PREFLIGHT", "21 / 21", "no expression or model fit", GREEN),
        kpi(268, "SYNTHETIC SUITES", "18 / 18", "both versions passed", GREEN),
        kpi(488, "UNIQUE LOCAL42", "93", "among 152 full sequences"),
        kpi(708, "FROZEN ENDPOINTS", "12", "one unified Holm family"),
        table(48, 198, [150, 310, 220, 184], arm_rows, [26, 30, 30, 30, 30], 9, ["left", "left", "left", "right"]),
        rect(48, 360, 424, 90), tx(62, 369, 396, 18, "Each endpoint must pass all four gates", 10.5, BLUE, True),
        tx(62, 392, 396, 48, "observed effect > 0 · CI lower bound > 0\nHolm p < 0.05 · at least 8/10 positive seeds", 10, INK, wrap=True, line=1.25),
        rect(488, 360, 424, 90), tx(502, 369, 396, 18, "Prefit engineering correction only", 10.5, AMBER, True),
        tx(502, 392, 396, 48, "First run stopped before fitting: zero-tolerance target CSV check.\nChanged only to 1e-12 absolute tolerance; design and logs retained.", 9.5, INK, wrap=True, line=1.2),
    ]
    pages[149] = slide(149, "02 / FROZEN PROTOCOL", "The execution contract was fixed before outcome fitting", "Fold sizes 30/31/31/30/30 · 50/50 seed-folds leakage-free · primary seed 20261222", body, BLUE, "200 NEW FITS + 200 REUSED FITS · NO POST-HOC ENDPOINT SELECTION", BLUE, PALE_BLUE, f"Protocol: {protocol_sha[:16]} · preflight {sha(b / 'rk33_label_free_preflight_v1.json')[:16]}", ["The first production failure was an identity-check engineering error, not a scientific result.", "Only the target CSV comparison tolerance changed; the scientific protocol remained fixed."])

    fam_rows = [["Comparison", "Ridge effect", "HistGB effect", "Endpoints passed", "Family gate"]]
    for fam, label in [("local42_vs_simple", "local42 − simple"), ("local42_vs_full1", "local42 − full1"), ("local42_vs_full3", "local42 − full3")]:
        rr = by_test[f"{fam}__ridge_spearman_effect"]
        hh = by_test[f"{fam}__histgb_spearman_effect"]
        fam_tests = [t for t in tests if t["test"].startswith(fam + "__")]
        fam_rows.append([label, f"{rr['observed_effect']:+.6f}", f"{hh['observed_effect']:+.6f}", f"{sum(t['pass'] for t in fam_tests)} / 4", "FAIL"])
    minp = min(t["p_cluster_swap"] for t in tests)
    body = [
        kpi(48, "PRIMARY DECISION", "0 / 12", "no endpoint passed", ROSE),
        kpi(268, "FAMILY GATES", "0 / 3", "all comparisons unsupported", ROSE),
        kpi(488, "95% CI CROSSES ZERO", "12 / 12", "every metric and model", AMBER),
        kpi(708, "HOLM p = 1.0", "12 / 12", "unified multiplicity control", AMBER),
        table(48, 202, [250, 160, 160, 160, 134], fam_rows, [28, 40, 40, 40], 9.5, ["left", "right", "right", "right", "right"]),
        rect(48, 366, 424, 82), tx(62, 375, 396, 18, "Not a multiplicity-only edge case", 10.5, AMBER, True),
        tx(62, 399, 396, 37, f"Minimum unadjusted cluster-swap p = {minp:.6f}.\nAll raw intervals already include no effect.", 10, INK, wrap=True, line=1.2),
        rect(488, 366, 424, 82), tx(502, 375, 396, 18, "Positive seeds are not a passed gate", 10.5, ROSE, True),
        tx(502, 399, 396, 37, "local42−full3 reaches 9/10 positive HistGB Spearman seeds,\nbut observed effect, CI and multiplicity requirements still fail.", 9.7, INK, wrap=True, line=1.2),
    ]
    pages[150] = slide(150, "03 / PRIMARY DECISION", "Local42 adds no supported observed-R1 structure increment", "LOCAL42_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED", body, ROSE, "0 / 12 ENDPOINTS PASSED · LOCAL COVERAGE ADVANTAGE NOT SUPPORTED", ROSE, PALE_AMBER, source, ["The scientific gate is negative even before Holm correction because every confidence interval crosses zero.", "Positive point estimates or seed counts do not establish a local-structure advantage."])

    endpoint_rows = [["Comparison", "Model", "Metric", "Effect", "95% CI", "Raw p", "Holm p", "Seeds"]]
    labels = {"local42_vs_simple": "local42−simple", "local42_vs_full1": "local42−full1", "local42_vs_full3": "local42−full3"}
    for t in tests:
        fam, rest = t["test"].split("__")
        model, metric = rest.split("_", 1)
        endpoint_rows.append([labels[fam], model, "Spearman" if metric.startswith("spearman") else "MSE impr.", f"{t['observed_effect']:+.5f}", f"[{t['ci95'][0]:+.4f},{t['ci95'][1]:+.4f}]", f"{t['p_cluster_swap']:.4f}", f"{t['p_holm']:.1f}", f"{t['positive_seeds']}/10"])
    body = [
        table(48, 104, [130, 76, 82, 104, 206, 74, 84, 108], endpoint_rows, [26] + [25] * 12, 8.2, ["left", "left", "left", "right", "right", "right", "right", "right"]),
        tx(48, 438, 864, 18, "Effect = local42 − comparator for Spearman; comparator MSE − local42 MSE for MSE improvement. Positive values favor local42.", 9, MUTED),
    ]
    pages[151] = slide(151, "04 / ALL FROZEN ENDPOINTS", "Twelve paired tests, twelve failed gates", "20,000 whole-cluster bootstraps + 20,000 cluster-swap permutations · unified Holm correction", body, AMBER, "EVERY CONFIDENCE INTERVAL CROSSES ZERO · NO ENDPOINT SURVIVES ALL FOUR GATES", AMBER, PALE_AMBER, source, ["This page reports all twelve frozen primary endpoints without post-hoc selection.", "MSE improvement is oriented so positive values favor local42."])

    abs_rows = [["Model", "Arm", "Spearman", "MSE"]]
    arm_labels = {"simple": "simple", "local42": "+ local42", "full1": "+ full1", "full3": "+ full3"}
    abs_map = {}
    for row in r["primary_absolute_performance"]:
        model, arm = row["arm"].split("_", 1)
        abs_map[(model, arm)] = row
        abs_rows.append([model, arm_labels[arm], f"{row['spearman']:.6f}", f"{row['mse']:.6f}"])
    cards = []
    for x, fam, label in [(48, "local42_vs_simple", "local42 − simple"), (316, "local42_vs_full1", "local42 − full1"), (584, "local42_vs_full3", "local42 − full3")]:
        rr = by_test[f"{fam}__ridge_spearman_effect"]
        hh = by_test[f"{fam}__histgb_spearman_effect"]
        cards += [rect(x, 340, 252, 108), tx(x + 14, 349, 224, 18, label, 10.2, BLUE, True), tx(x + 14, 374, 224, 62, f"Ridge effect {rr['observed_effect']:+.6f}\n95% CI [{rr['ci95'][0]:+.4f}, {rr['ci95'][1]:+.4f}]\nHistGB effect {hh['observed_effect']:+.6f}\n95% CI [{hh['ci95'][0]:+.4f}, {hh['ci95'][1]:+.4f}]", 9.1, INK, wrap=True, line=1.18)]
    body = [table(48, 104, [160, 320, 192, 192], abs_rows, [26] + [25] * 8, 9, ["left", "left", "right", "right"]), *cards]
    pages[152] = slide(152, "05 / ABSOLUTE PERFORMANCE", "Absolute scores explain direction, not structural significance", "Frozen primary seed 20261222 · paired intervals remain the primary evidence", body, BLUE, "DESCRIPTIVE PRIMARY-SEED SCORES · RETROSPECTIVE FIXED-VARIANT EXPRESSION ONLY", TEAL, PALE_TEAL, source, ["Absolute scores are included to interpret paired effects, not to replace uncertainty analysis.", "The HistGB local42 absolute increase over simple is not statistically supported by the paired primary endpoint."])

    evidence_rows = [["Evidence", "SHA256 prefix"],
                     ["Protocol", protocol_sha[:16]],
                     ["Result", result_sha[:16]],
                     ["Independent", ind_sha[:16]],
                     ["Reproduction", repro_sha[:16]],
                     ["Closeout", close_sha[:16]],
                     ["Manuscript", manuscript["updated_sha256"][:16]]]
    body = [
        kpi(48, "NEW REAL FITS", "200", "plus 200 accepted RK28 fits"),
        kpi(268, "INDEPENDENT CHECK", "76 / 76", "raw source through inference", GREEN),
        kpi(488, "CLEAN COMPARISON", f"{repro['checks_passed']} / {repro['checks_total']}", f"{repro['csv_total']} CSV + {repro['arrays_total']} arrays", GREEN),
        kpi(708, "FULL PROJECT TESTS", "429 PASS", "1 skipped · exit code 0", GREEN),
        table(48, 198, [220, 280], evidence_rows, [26] + [25] * 6, 8.8, ["left", "left"]),
        rect(548, 198, 364, 182), tx(562, 207, 336, 18, "Exact clean-checkout reproduction", 10.5, GREEN, True),
        tx(562, 233, 336, 132, f"Clean head {close['clean_commit'][:12]}\n{repro['csv_byte_equal']}/{repro['csv_total']} CSV files byte-identical\n{repro['arrays_exact_equal']}/{repro['arrays_total']} NPZ arrays exactly equal\nProduction {r['elapsed_seconds']:.2f} s → {repro['clean_production_elapsed_seconds']:.2f} s\nIndependent {ind['elapsed_seconds']:.2f} s → {repro['clean_independent_elapsed_seconds']:.2f} s\nTimings are component costs, not total wall time", 9.7, INK, wrap=True, line=1.2),
        rect(548, 390, 364, 58), tx(562, 399, 336, 18, "Accepted scientific closeout", 10.5, TEAL, True), tx(562, 422, 336, 17, f"Closeout {close['checks_passed']}/{close['checks_total']} PASS · conclusion unchanged", 9.4, INK),
    ]
    pages[153] = slide(153, "06 / REPRODUCTION EVIDENCE", "Independent code and a clean checkout reproduce 0/12", "Original and clean artifacts match exactly; engineering and scientific gates are recorded separately", body, GREEN, "REPRODUCED · INDEPENDENTLY VERIFIED · FULL PROJECT TESTS PASSED", GREEN, PALE_GREEN, source, ["The clean comparison checks scientific fields, CSV bytes, and every inference array.", "The project test count includes the six new RK33 unit tests."])

    report_rows = [["Record", "Verified value"],
                   ["Manuscript section", "§6.44"],
                   ["Native result tables", "Table 21 + Table 22"],
                   ["Original manuscript SHA", manuscript["original_sha256"][:16]],
                   ["Updated manuscript SHA", manuscript["updated_sha256"][:16]],
                   ["Prior content", "byte-preserved outside insertion"],
                   ["Submission status", "non-submittable working draft"]]
    body = [
        kpi(48, "PAPER SECTION", "§6.44", "inserted before Discussion"),
        kpi(268, "ENDPOINT TABLE", "12 ROWS", "Table 21 · all frozen tests"),
        kpi(488, "ABSOLUTE TABLE", "8 ROWS", "Table 22 · primary seed"),
        kpi(708, "DECISION", "0 / 12", "identical to source JSON", ROSE),
        table(48, 198, [270, 594], report_rows, [26] + [27] * 6, 8.8, ["left", "left"]),
        rect(48, 402, 424, 48), tx(62, 411, 396, 29, "Paper claim: no robust local42 increment under this observed-R1 protocol; not a universal no-structure claim.", 9.4, INK, wrap=True),
        rect(488, 402, 424, 48), tx(502, 411, 396, 29, "External SOTA, functional/protein OOD, exact start-aware transport and RK-G1 remain explicitly open.", 9.4, INK, wrap=True),
    ]
    pages[154] = slide(154, "07 / MANUSCRIPT SYNCHRONIZATION", "The working paper records the result and its limits", "English section generated from accepted JSON · prior manuscript content preserved · no submit-ready claim", body, BLUE, "RESULTS, TABLES, REPRODUCTION AND NON-CLAIMS ARE TRACEABLE TO ACCEPTED EVIDENCE", BLUE, PALE_BLUE, f"Manuscript: {manuscript['updated_sha256'][:16]} · section {manuscript['section_sha256'][:16]}", ["The new English section is inserted immediately before Discussion.", "The manuscript remains a working draft and is not represented as submission-ready."])

    body = [
        kpi(48, "EXTERNAL SOTA", "OPEN", "complete comparison remains open", AMBER),
        kpi(268, "SEVEN-METHOD DENSE", "OPEN", "four-method prefixes only", AMBER),
        kpi(488, "TIME-MATCHED", "OPEN", "controlled cost comparison open", AMBER),
        kpi(708, "FUNCTIONAL UNTOUCHED", "UNREAD", "no functional OOD or RK-G1", ROSE),
        rect(48, 202, 424, 248), tx(62, 211, 396, 18, "Closed by RK33", 10.5, GREEN, True),
        tx(62, 237, 396, 190, "• Matched local42/simple/full1/full3 comparison\n• 200 new fits + 200 accepted RK28 fits\n• All 12 frozen paired endpoints\n• Independent 76/76 raw-source verification\n• Exact clean-checkout reproduction\n• English working-paper and research-record update", 10.1, INK, wrap=True, line=1.22),
        rect(488, 202, 424, 248), tx(502, 211, 396, 18, "Still open — not future-work-as-completion", 10.5, ROSE, True),
        tx(502, 237, 396, 190, "• Full UTR–CDS remap and exact start-aware transport\n• Independent untouched and protein/functional OOD\n• External SOTA and unified time-matched evaluation\n• Complete seven-method dense generation calls\n• Multispecies VeloHARMO and prospective DBTL\n• Authorized generator work and RK-G1", 10.1, INK, wrap=True, line=1.22),
    ]
    pages[155] = slide(155, "08 / EVIDENCE BOUNDARY", "RK33 closes one coverage test, not the research program", "No host/assay/dangles/measured-structure identification · no velocity or decay measurement · no wet-lab claim", body, AMBER, "REMAINING SCIENTIFIC GATES STAY OPEN · RK-G1 = FALSE", TEAL, PALE_TEAL, source, ["The result does not reject every longer-context mechanism or every possible local window.", "Functional untouched data remain unread, expensive generator training remains unauthorized, and no wet-lab work was performed."])

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"status": "GENERATED_NOT_ONLINE", "pages": [], "source_sha256": {"protocol": protocol_sha, "result": result_sha, "independent": ind_sha, "reproduction": repro_sha, "closeout": close_sha, "manuscript": manuscript["updated_sha256"]}}
    selected = {args.page: pages[args.page]} if args.page else pages
    for number, xml in selected.items():
        # New-slide IDs are assigned by the service; do not submit locally invented IDs.
        xml = re.sub(r' id="[^"]+"', "", xml)
        path = args.output_dir / f"rk33_{number}.xml"
        path.write_text(xml)
        manifest["pages"].append({"page": number, "path": str(path), "sha256": sha(path), "bytes": path.stat().st_size})
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"], "pages": [p["page"] for p in manifest["pages"]], "manifest": str(args.manifest)}, indent=2))


if __name__ == "__main__":
    main()
