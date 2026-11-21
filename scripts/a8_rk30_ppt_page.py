#!/usr/bin/env python3
"""Render one release-gated RK30 slide; never compute or alter scientific results."""
import argparse
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

BG = "rgba(247,248,250,1)"
WHITE = "rgba(255,255,255,1)"
INK = "rgba(31,41,55,1)"
MUTED = "rgba(100,116,139,1)"
LINE = "rgba(226,232,240,1)"
TEAL = "rgba(13,148,136,1)"
BLUE = "rgba(37,99,235,1)"
GREEN = "rgba(5,150,105,1)"
ROSE = "rgba(225,29,72,1)"
AMBER = "rgba(217,119,6,1)"
PALE_TEAL = "rgba(204,251,241,1)"
PALE_BLUE = "rgba(219,234,254,1)"
PALE_GREEN = "rgba(209,250,229,1)"
PALE_ROSE = "rgba(255,228,230,1)"

DIRECTIONS = {
    "hela_no_intron__to__hek293_no_intron": "HeLa no-intron → HEK293",
    "hek293_no_intron__to__hela_no_intron": "HEK293 → HeLa no-intron",
    "hela_no_intron__to__hela_with_intron": "HeLa no-intron → with-intron",
    "hela_with_intron__to__hela_no_intron": "HeLa with-intron → no-intron",
    "hela_no_intron": "HeLa no-intron",
    "hela_with_intron": "HeLa with-intron",
    "hek293_no_intron": "HEK293 no-intron",
}
PAGES = ["design", "cohort", "directions", "ridge_primary", "histgb_primary",
         "ridge_absolute", "histgb_absolute", "secondary", "reproduction"]


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fmt(value, digits=6):
    if value is None:
        return "not recorded"
    return f"{float(value):.{digits}g}"


def txt(x, y, w, h, value, size=12, color=INK, bold=False, align="left",
        wrap=False, text_type="body", valign="middle", line="multiple:1.15"):
    paragraphs = value if isinstance(value, list) else [value]
    body = "".join(f"<p>{escape(str(item))}</p>" for item in paragraphs)
    attrs = (f'textType="{text_type}" fontSize="{size}" fontFamily="Inter" color="{color}" '
             f'textAlign="{align}" verticalAlign="{valign}" wrap="{str(wrap).lower()}" '
             f'lineSpacing="{line}"')
    if bold:
        attrs += ' bold="true"'
    return (f'<shape type="text" topLeftX="{x}" topLeftY="{y}" width="{w}" height="{h}">'
            f'<content {attrs}>{body}</content></shape>')


def rect(x, y, w, h, fill=WHITE, border=LINE, radius=8):
    border_xml = f'<border color="{border}" width="1"/>' if border else ""
    return (f'<shape type="round-rect" topLeftX="{x}" topLeftY="{y}" width="{w}" height="{h}" '
            f'presetHandlers="{radius}"><fill><fillColor color="{fill}"/></fill>{border_xml}</shape>')


def card(x, y, w, h, label, value, sub, accent=TEAL):
    return (rect(x, y, w, h) +
            txt(x + 14, y + 9, w - 28, 15, label.upper(), 8.5, MUTED, True) +
            txt(x + 14, y + 25, w - 28, 30, value, 21, accent, True) +
            txt(x + 14, y + 56, w - 28, h - 61, sub, 8.5, MUTED, wrap=True, valign="top"))


def box(x, y, w, h, title, lines, accent=TEAL, fill=WHITE, size=10.2):
    return (rect(x, y, w, h, fill=fill) +
            txt(x + 14, y + 9, w - 28, 18, title, 10.5, accent, True) +
            txt(x + 14, y + 31, w - 28, h - 39, lines, size, INK, wrap=True,
                valign="top", line="multiple:1.25"))


def table(x, y, widths, row_heights, rows, font=9.2, aligns=None, decision_col=None):
    total_w, total_h = sum(widths), sum(row_heights)
    out = [f'<table topLeftX="{x}" topLeftY="{y}" width="{total_w}" height="{total_h}"><colgroup>']
    out += [f'<col width="{w}"/>' for w in widths]
    out.append('</colgroup>')
    for r, (height, row) in enumerate(zip(row_heights, rows)):
        out.append(f'<tr height="{height}">')
        for c, value in enumerate(row):
            header = r == 0
            fill = INK if header else (WHITE if r % 2 else "rgba(241,245,249,1)")
            color = WHITE if header else INK
            if not header and decision_col == c:
                color = GREEN if str(value) == "PASS" else ROSE
            align = "center" if header else (aligns[c] if aligns else "left")
            out.append('<td>')
            out.append(f'<fill><fillColor color="{fill}"/></fill>')
            bold = ' bold="true"' if header or (decision_col == c and not header) else ""
            out.append(f'<content textType="body" fontSize="{font}" fontFamily="Inter" color="{color}" '
                       f'textAlign="{align}" verticalAlign="middle" wrap="false" lineSpacing="multiple:1.0"'
                       f'{bold}>'
                       f'<p>{escape(str(value))}</p></content></td>')
        out.append('</tr>')
    out.append('</table>')
    return "".join(out)


def base(page_number, section, title, subtitle, body, band, source, notes, accent=TEAL):
    band_fill = PALE_GREEN if band.startswith("SUPPORTED") else (PALE_ROSE if "NOT" in band or "FAIL" in band else PALE_TEAL)
    band_color = GREEN if band.startswith("SUPPORTED") else (ROSE if "NOT" in band or "FAIL" in band else TEAL)
    data = [txt(48, 8, 650, 14, section.upper(), 8.5, accent, True),
            txt(716, 8, 196, 14, "A8 / RK30 / MORDSTEIN", 8.5, MUTED, align="right"),
            txt(48, 27, 864, 35, title, 23, INK, True),
            rect(48, 72, 58, 3, fill=accent, border=None, radius=1),
            txt(48, 82, 864, 18, subtitle, 10.2, MUTED),
            body,
            rect(48, 474, 864, 30, fill=band_fill, border=None, radius=6),
            txt(62, 478, 836, 21, band, 9.8, band_color, True),
            txt(48, 512, 780, 13, source, 8.2, MUTED),
            txt(850, 510, 62, 15, f"{page_number:03d}", 10, INK, True, align="right")]
    note = "".join(f"<p>{escape(str(p))}</p>" for p in notes)
    return ('<presentation xmlns="https://www.larkoffice.com/sml/2.0" width="960" height="540"><slide>'
            f'<style><fill><fillColor color="{BG}"/></fill></style><data>{"".join(data)}</data>'
            f'<note><content textType="body" fontSize="12">{note}</content></note></slide></presentation>')


def endpoint_rows(rows, model=None, secondary=False):
    selected = [r for r in rows if (model is None or r["model"] == model)]
    if secondary:
        out = [["Context", "Model", "Metric", "Effect", "95% CI", "Holm p", "Seeds", "Decision"]]
        for r in selected:
            out.append([DIRECTIONS[r["direction"]], r["model"].upper(),
                        "Spearman" if r["endpoint"] == "spearman" else "MSE improv.", fmt(r["effect"]),
                        f'[{fmt(r["ci_low"])}, {fmt(r["ci_high"])}]', fmt(r["holm_p"], 4),
                        f'{round(10 * r["positive_seed_fraction"])}/10', "PASS" if r["pass"] else "FAIL"])
        return out
    out = [["Direction", "Metric", "Effect", "95% CI", "Holm p", "Seeds", "Decision"]]
    for r in selected:
        out.append([DIRECTIONS[r["direction"]],
                    "Spearman" if r["endpoint"] == "spearman" else "MSE improv.", fmt(r["effect"]),
                    f'[{fmt(r["ci_low"])}, {fmt(r["ci_high"])}]', fmt(r["holm_p"], 4),
                    f'{round(10 * r["positive_seed_fraction"])}/10', "PASS" if r["pass"] else "FAIL"])
    return out


def absolute_rows(rows, model):
    out = [["Direction", "Metric", "Null", "Simple", "Structure", "Mean effect"]]
    for r in [r for r in rows if r["model"] == model]:
        out.append([DIRECTIONS[r["direction"]],
                    "Spearman" if r["endpoint"] == "spearman" else "MSE improv.",
                    fmt(r["null_mean"]), fmt(r["simple_mean"]), fmt(r["structure_mean"]), fmt(r["effect"])])
    return out


def render(args):
    protocol = json.loads(args.protocol.read_text())
    closeout = json.loads(args.closeout.read_text())
    ppt = json.loads(args.ppt_payload.read_text())
    manuscript = json.loads(args.manuscript_report.read_text())
    reproduction = json.loads(args.reproduction_manifest.read_text())
    comparison = json.loads(args.comparison_report.read_text())
    closeout_sha = sha256(args.closeout)
    if closeout["status"] != "PASS_RK30_VERIFIED_RESULT_PACKAGING" or not all(closeout["release_gates"].values()):
        raise RuntimeError("Closeout/release gates do not pass")
    if ppt["closeout_sha256"] != closeout_sha or ppt["primary_endpoints"] != closeout["primary_endpoints"]:
        raise RuntimeError("PPT payload is not bound to this closeout")
    if manuscript["status"] != "PASS_RK29_RK30_MANUSCRIPT_INTEGRATION" or manuscript["closeout_sha256"] != closeout_sha:
        raise RuntimeError("Manuscript is not bound to this closeout")
    if sha256(args.protocol) != closeout["protocol_sha256"]:
        raise RuntimeError("Protocol hash mismatch")
    if reproduction["status"] != "PASS_RK30_CLEAN_CHECKOUT_REPRODUCTION" or not reproduction["production_rerun"] or reproduction["git_dirty"]:
        raise RuntimeError("Clean full reproduction has not passed")
    if not reproduction.get("production_reproduction_equivalence_pass") or comparison["status"] != "PASS_RK30_PRODUCTION_REPRODUCTION_EQUIVALENCE":
        raise RuntimeError("Production/reproduction equivalence has not passed")

    coverage, cost = closeout["coverage"], closeout["cost"]
    variants, clusters = coverage["variants"], coverage["clusters"]
    source = f'Source: closeout {closeout_sha[:12]} · protocol {closeout["protocol_sha256"][:12]} · independently verified'
    conclusion = closeout["scientific_conclusion"]
    supported = conclusion == "MATCHED_CONTEXT_MFE_TRANSPORT_SUPPORTED_RETROSPECTIVELY"
    page = args.page

    if page == "design":
        contexts = protocol["contexts"]
        cards = "".join([
            card(48, 104, 204, 78, "Raw design", "64 R1 runs", "8 experiments · Bin1–8", TEAL),
            card(268, 104, 204, 78, "New data", "56 HeLa files", "40 no-intron + 16 with-intron", BLUE),
            card(488, 104, 204, 78, "Fixed space", "152 / 74", "variants / sequence clusters", TEAL),
            card(708, 104, 204, 78, "Counting", "max 8 nt", "unique nearest 300-nt reference", BLUE)])
        conditions = [
            (48, "HeLa · no intron", f'{len(contexts["hela_no_intron"]["replicates"])} replicates · 40 runs'),
            (348, "HeLa · with intron", f'{len(contexts["hela_with_intron"]["replicates"])} replicates · 16 runs'),
            (648, "HEK293 · no intron", f'{len(contexts["hek293_no_intron"]["replicates"])} replicate · 8 runs')]
        condition_xml = "".join(card(x, 202, 264, 76, "Matched context", title, sub, TEAL if i < 2 else BLUE)
                                for i, (x, title, sub) in enumerate(conditions))
        strips = (rect(48, 294, 864, 30, fill=PALE_BLUE, border=None) +
                  txt(62, 299, 836, 20, "HOST TRANSPORT  ·  HeLa no-intron ↔ HEK293 no-intron", 10, BLUE, True) +
                  rect(48, 332, 864, 30, fill=PALE_TEAL, border=None) +
                  txt(62, 337, 836, 20, "INTRON TRANSPORT  ·  HeLa no-intron ↔ HeLa with-intron", 10, TEAL, True))
        boxes = (box(48, 378, 424, 82, "Fair comparison",
                     ["• Simple: GC3 + GC + CpG + CAI", "• Structure adds three predicted-MFE features",
                      "• Same folds, seeds and hyperparameters; depth excluded"], BLUE) +
                 box(488, 378, 424, 82, "Whole-cluster transport",
                     ["• Source test-cluster outcomes excluded from training", "• Target clusters held out intact; no target tuning",
                      "• 16 primary endpoints share one Holm family"], TEAL))
        body = cards + condition_xml + strips + boxes
        return base(args.page_number, "01 / Matched design", "Matched GFP contexts isolate host and intron transport",
                    "Same study, vector, variants, observed 300-nt fragment and MFE definition", body,
                    "MATCHED CONTEXTS · HOST AND INTRON TESTED SEPARATELY", source,
                    ["RK30 keeps the GFP library and observed-R1 representation fixed.",
                     "The 56 new HeLa files complement the eight existing HEK293 files.",
                     "Transport is evaluated by whole sequence cluster, not random variant splits.",
                     "Sequencing depth is quality control only and never enters a biological predictor."], TEAL)

    if page == "cohort":
        raw_pass = closeout["release_gates"]["raw_independent_pass"]
        cards = "".join([
            card(48, 104, 204, 76, "Common cohort", str(variants), "variants passing all 8 experiments", TEAL),
            card(268, 104, 204, 76, "Whole clusters", str(clusters), "fixed before new HeLa outcomes", BLUE),
            card(488, 104, 204, 76, "Conditions", "3", "equal-weight replicate scores", TEAL),
            card(708, 104, 204, 76, "Raw audit", "PASS" if raw_pass else "FAIL", "hashes + checkpoints + brute-force reads", GREEN if raw_pass else ROSE)])
        rows = [["Condition", "N", "Mean", "SD", "Minimum", "Maximum"]]
        for name in coverage["conditions"]:
            s = coverage["condition_score_summary"][name]
            rows.append([DIRECTIONS[name], s["n"], fmt(s["mean"], 5), fmt(s["sd"], 5), fmt(s["min"], 5), fmt(s["max"], 5)])
        outcomes = table(48, 198, [244, 80, 120, 120, 150, 150], [26] + [28] * 3, rows, 10,
                         ["left", "center", "right", "right", "right", "right"])
        boxes = (box(48, 326, 424, 134, "Confounding separated by design",
                     ["• Same variants and fragment across host and intron conditions",
                      "• No outcome-informed reference re-picking or re-clustering",
                      "• Complete eight-bin support required in every replicate",
                      "• Target outcomes never enter source training or scaling"], TEAL) +
                 box(488, 326, 424, 134, "What remains indistinguishable",
                     ["• Host contrast still includes other cell-line differences",
                      "• Intron contrast is specific to this 5′UTR construction",
                      "• Predicted MFE is not measured RNA structure",
                      "• Flow-seq bins are not direct velocity or decay"], ROSE))
        return base(args.page_number, "02 / Cohort and QC", "Cohort coverage and outcome shifts are fixed before modeling",
                    "Complete-case variants only · bin-weighted scores · no post-hoc threshold search", body=cards + outcomes + boxes,
                    band="RAW INDEPENDENT PASS · COHORT AND LEAKAGE BOUNDARIES REPORTED", source=source,
                    notes=[f"The common cohort contains {variants} variants in {clusters} fixed clusters.",
                           "Every variant passes complete bin and read-support rules in all eight experiments.",
                           "Outcome summaries are descriptive and are shown before model effects.",
                           "The matched design removes selected sequence confounds but not every host-specific mechanism."], accent=TEAL)

    if page == "directions":
        rows = [["Transport direction", "Endpoints passed", "Mechanism", "Direction decision"]]
        for r in closeout["primary_direction_summary"]:
            mechanism = "Host" if "hek293" in r["direction"] else "5′UTR intron"
            rows.append([DIRECTIONS[r["direction"]], f'{r["passed_endpoints"]} / {r["total_endpoints"]}', mechanism,
                         "PASS" if r["all_four_endpoints_pass"] else "FAIL"])
        directions = table(48, 104, [350, 150, 150, 214], [28] + [46] * 4, rows, 10.5,
                           ["left", "center", "center", "center"], 3)
        host = closeout["primary_direction_summary"][0]["all_four_endpoints_pass"] and closeout["primary_direction_summary"][1]["all_four_endpoints_pass"]
        intron = closeout["primary_direction_summary"][2]["all_four_endpoints_pass"] and closeout["primary_direction_summary"][3]["all_four_endpoints_pass"]
        boxes = (box(48, 336, 424, 124, "Host transport · bidirectional gate",
                     [f'HeLa → HEK293: {closeout["primary_direction_summary"][0]["passed_endpoints"]}/4 endpoints',
                      f'HEK293 → HeLa: {closeout["primary_direction_summary"][1]["passed_endpoints"]}/4 endpoints',
                      "PASS" if host else "NOT SUPPORTED across both directions"], BLUE,
                     PALE_BLUE if host else PALE_ROSE, 11) +
                 box(488, 336, 424, 124, "Intron transport · bidirectional gate",
                     [f'No-intron → with-intron: {closeout["primary_direction_summary"][2]["passed_endpoints"]}/4 endpoints',
                      f'With-intron → no-intron: {closeout["primary_direction_summary"][3]["passed_endpoints"]}/4 endpoints',
                      "PASS" if intron else "NOT SUPPORTED across both directions"], TEAL,
                     PALE_TEAL if intron else PALE_ROSE, 11))
        band = "SUPPORTED RETROSPECTIVELY · ALL FOUR DIRECTIONS PASS" if supported else "BROAD CONTEXT TRANSPORT NOT SUPPORTED · DIRECTIONS REPORTED SEPARATELY"
        return base(args.page_number, "03 / Primary decision",
                    "All four transport directions pass" if supported else "Broad MFE transport is not supported in all four directions",
                    "Each direction requires four endpoints: effect > 0, CI lower bound > 0, Holm p < 0.05 and at least 8/10 positive seeds",
                    directions + boxes, band, source,
                    ["The primary family contains four ordered transport directions and sixteen endpoints.",
                           "A direction passes only when both models and both metrics satisfy every frozen rule.",
                           "Host and intron transport are reported separately rather than pooled.",
                           "Failure rejects this broad transport claim; it does not prove a universal negative structure mechanism."], BLUE)

    if page in ["ridge_primary", "histgb_primary"]:
        model = "ridge" if page.startswith("ridge") else "histgb"
        rows = endpoint_rows(closeout["primary_endpoints"], model=model)
        primary = table(48, 104, [224, 108, 92, 184, 82, 70, 104], [28] + [38] * 8, rows, 9.2,
                        ["left", "left", "right", "center", "right", "center", "center"], 6)
        note = txt(48, 444, 864, 18,
                   "Effect: structure minus simple Spearman; or simple minus structure MSE. Positive favors structure. One Holm family spans both models.",
                   9.2, MUTED)
        passed = sum(r["pass"] for r in closeout["primary_endpoints"] if r["model"] == model)
        return base(args.page_number, "04 / Primary endpoints", f'{model.upper()} · {passed}/8 transport endpoints pass',
                    "10 seeds × 5 whole-cluster folds · 10,000 cluster bootstraps · 10,000 sign-swap permutations",
                    primary + note, f'{model.upper()} PRIMARY ENDPOINTS · EFFECT + CI + HOLM P + SEED STABILITY', source,
                    [f"This page reports all eight {model} primary endpoints without selection.",
                     "Effects are paired structure increments over the simple biological covariates.",
                     "Confidence intervals and permutations resample whole sequence clusters.",
                     "The displayed seed column counts positive effects across the ten frozen splits."], BLUE)

    if page in ["ridge_absolute", "histgb_absolute"]:
        model = "ridge" if page.startswith("ridge") else "histgb"
        rows = absolute_rows(closeout["primary_absolute_performance"], model)
        absolute = table(48, 104, [224, 108, 110, 110, 110, 202], [28] + [34] * 8, rows, 9.2,
                         ["left", "left", "right", "right", "right", "right"])
        strips = (rect(48, 416, 864, 18, fill=PALE_BLUE, border=None, radius=4) +
                  txt(58, 417, 844, 15, "FAIR ARMS · simple = GC3 + GC + CpG + CAI · structure adds three MFE features · depth excluded", 8.8, BLUE, True) +
                  txt(48, 440, 864, 18,
                      f'Absolute values use frozen primary seed {closeout["absolute_performance_seed"]}; mean effect averages all 10 seeds. No target tuning.',
                      9.2, MUTED))
        return base(args.page_number, "05 / Absolute performance", f'{model.upper()} · absolute scores prevent increment-only misreading',
                    "Null, simple and structure evaluated on the same target-context held-out clusters", absolute + strips,
                    "ABSOLUTE PERFORMANCE + PAIRED INCREMENT · NO SOTA OR VELOCITY CLAIM", source,
                    ["Null, simple and structure scores come from the frozen primary seed.",
                     "The mean effect is separately averaged over all ten seeds.",
                     "All arms use identical held-out variants, folds and target outcomes.",
                     "These fixed-context ridge and HistGB results are not an external SOTA comparison."], BLUE)

    if page == "secondary":
        rows = endpoint_rows(closeout["secondary_endpoints"], secondary=True)
        secondary = table(48, 104, [184, 70, 102, 82, 174, 76, 66, 110], [26] + [27] * 12, rows, 8.6,
                          ["left", "left", "left", "right", "center", "right", "center", "center"], 7)
        passed = sum(r["pass"] for r in closeout["secondary_endpoints"])
        return base(args.page_number, "06 / Secondary analysis", f'Within-context signals · {passed}/12 endpoints pass',
                    "Three conditions × two models × two metrics · separate 12-endpoint Holm family", secondary,
                    "SECONDARY ONLY · WITHIN-CONTEXT RESULTS CANNOT RESCUE PRIMARY TRANSPORT FAILURE", source,
                    ["Within-context fits use the same fixed variants and whole-cluster folds.",
                     "Twelve secondary endpoints have their own Holm family.",
                     "MFE-only arms are descriptive references and are not part of the primary increment decision.",
                     "A within-context association cannot rescue a failed ordered transport direction."], TEAL)

    if page == "reproduction":
        verify_seconds = cost.get("independent_verification_cost_seconds")
        cards = "".join([
            card(48, 104, 204, 76, "Real CPU fits", f'{cost["fit_count"]:,}', "800 transport + 900 within-context", BLUE),
            card(268, 104, 204, 76, "Production cost", f'{cost["production_cost_seconds"]:.1f} s', f'{cost["cpu_threads"]} thread · frozen models', TEAL),
            card(488, 104, 204, 76, "Independent check", f'{verify_seconds:.1f} s' if verify_seconds is not None else "PASS", "raw counts + all model outputs", GREEN),
            card(708, 104, 204, 76, "Clean rerun", "PASS", "separate artifact root · exact outputs", GREEN)])
        artifact = closeout["artifact_sha256"]
        evidence = [["Evidence", "SHA256 prefix"]]
        for label, key, value in [
            ("Protocol", None, closeout["protocol_sha256"]),
            ("Counting", "RK30_COUNTING.json", None),
            ("Model summary", "RK30_MODEL_SUMMARY.json", None),
            ("Raw verification", "RK30_RAW_VERIFICATION.json", None),
            ("Model verification", "RK30_MODEL_INDEPENDENT.json", None),
            ("Closeout", None, closeout_sha),
            ("Rerun comparison", None, sha256(args.comparison_report)),
            ("Manuscript", None, manuscript["manuscript_sha256"]),
        ]:
            evidence.append([label, (value or artifact[key])[:16]])
        evidence_xml = table(48, 198, [220, 280], [26] + [25] * 8, evidence, 8.8, ["left", "left"])
        boundaries = box(548, 198, 364, 226, "Evidence boundary",
                         ["• Same GFP observed-R1 library only", "• Predicted MFE, not measured structure",
                          "• No protein OOD or functional-untouched read", "• No velocity, decay or direct RFU claim",
                          "• No generator training or external SOTA claim", "• RK-G1 remains open"], ROSE, WHITE, 10.2)
        return base(args.page_number, "07 / Reproduction and limits", "Reproduction closes the evidence chain; limits remain",
                    f'Clean checkout {reproduction["git_head"][:12]} · {comparison["n_csv_files"]} CSV files + {comparison["n_npz_arrays"]} inference arrays exactly reproduced',
                    cards + evidence_xml + boundaries,
                    "REPRODUCED AND INDEPENDENTLY VERIFIED · NO CLAIM BEYOND THE MATCHED GFP DESIGN", source,
                    ["The clean checkout reruns counting, all model fits and both independent verifiers.",
                     "Production and reproduction CSV files and inference arrays are compared exactly.",
                     "Timings and output inventory paths are excluded from scientific-summary comparison.",
                     "All remaining biological and external-validity boundaries are stated explicitly."], GREEN)
    raise ValueError(page)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["protocol", "closeout", "ppt-payload", "manuscript-report", "reproduction-manifest", "comparison-report", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--page", choices=PAGES, required=True)
    parser.add_argument("--page-number", type=int, required=True)
    args = parser.parse_args()
    xml = render(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(xml + "\n")
    print(json.dumps({"status": "PASS_RK30_SLIDE_XML", "page": args.page,
                      "page_number": args.page_number, "bytes": len(xml.encode()),
                      "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
