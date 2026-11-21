#!/usr/bin/env python3
"""Generate seven evidence-bound RK37 slides and a candidate manifest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

BG = "rgba(247, 248, 250, 1)"
INK = "rgba(31, 41, 55, 1)"
MUTED = "rgba(100, 116, 139, 1)"
TEAL = "rgba(13, 148, 136, 1)"
RED = "rgba(225, 29, 72, 1)"
GREEN = "rgba(5, 150, 105, 1)"
AMBER = "rgba(217, 119, 6, 1)"
WHITE = "rgba(255, 255, 255, 1)"
BORDER = "rgba(226, 232, 240, 1)"
ALT = "rgba(241, 245, 249, 1)"
PALE_TEAL = "rgba(204, 251, 241, 1)"
PALE_RED = "rgba(255, 228, 230, 1)"
PALE_AMBER = "rgba(254, 243, 199, 1)"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text(x, y, w, h, value, size=10, color=INK, bold=False, align="left", wrap=False):
    bold_attr = 'bold="true" ' if bold else ""
    return (
        f'<shape width="{w}" height="{h}" topLeftX="{x}" topLeftY="{y}" type="text">'
        f'<content verticalAlign="top" fontSize="{size}" fontFamily="Inter" color="{color}" '
        f'{bold_attr}lineSpacing="multiple:1.15" textAlign="{align}" wrap="{str(wrap).lower()}">'
        f'<p>{escape(str(value))}</p></content></shape>'
    )


def rect(x, y, w, h, fill=WHITE, radius=8, border=True):
    border_xml = f'<border color="{BORDER}" width="1"/>' if border else ""
    return (
        f'<shape width="{w}" height="{h}" topLeftX="{x}" topLeftY="{y}" presetHandlers="{radius}" type="round-rect">'
        f'<fill><fillColor color="{fill}"/></fill>{border_xml}'
        f'<content fontSize="16" fontFamily="Inter" color="{INK}"/></shape>'
    )


def card(x, label, value, detail, color=TEAL):
    return "".join((
        rect(x, 104, 204, 76),
        text(x + 14, 113, 176, 15, label, 8.5, MUTED, True),
        text(x + 14, 129, 176, 30, value, 21, color, True),
        text(x + 14, 160, 176, 17, detail, 8.2, MUTED),
    ))


def band(y, value, fill=PALE_TEAL, color=TEAL, size=9.4):
    return "".join((
        rect(48, y, 864, 30, fill, 6, False),
        text(62, y + 4, 836, 21, value, size, color, True),
    ))


def table(x, y, widths, rows, row_heights=None, font_size=9.1, aligns=None):
    total_w = sum(widths)
    total_h = sum(row_heights) if row_heights else 26 + 30 * (len(rows) - 1)
    row_heights = row_heights or [26] + [30] * (len(rows) - 1)
    aligns = aligns or ["left"] * len(widths)
    out = [f'<table width="{total_w}" height="{total_h}" topLeftX="{x}" topLeftY="{y}"><colgroup>']
    out.extend(f'<col span="1" width="{w}"/>' for w in widths)
    out.append('</colgroup>')
    for r, (values, height) in enumerate(zip(rows, row_heights)):
        out.append(f'<tr height="{height}">')
        for c, value in enumerate(values):
            fill = INK if r == 0 else (ALT if r % 2 == 0 else WHITE)
            color = WHITE if r == 0 else INK
            bold = r == 0
            bold_attr = 'bold="true" ' if bold else ""
            out.append(
                f'<td><fill><fillColor color="{fill}"/></fill>'
                f'<content fontSize="{font_size}" fontFamily="Inter" color="{color}" {bold_attr}'
                f'lineSpacing="multiple:1" textAlign="{aligns[c]}" wrap="false"><p>{escape(str(value))}</p></content></td>'
            )
        out.append('</tr>')
    out.append('</table>')
    return "".join(out)


def slide(page, kicker, title_value, subtitle, body, source, notes):
    header = "".join((
        text(48, 8, 650, 14, kicker, 8.5, TEAL, True),
        text(716, 8, 196, 14, "A8 / RK37 / TRANSLATION PIVOT", 8.5, MUTED, False, "right"),
        text(48, 27, 864, 35, title_value, 23, INK, True),
        rect(48, 72, 58, 3, TEAL, 1, False),
        text(48, 82, 864, 18, subtitle, 10.2, MUTED),
    ))
    footer = "".join((
        text(48, 512, 780, 13, source, 8.2, MUTED),
        text(850, 510, 62, 15, str(page), 10, INK, True, "right"),
    ))
    note_xml = "".join(f"<p>{escape(n)}</p>" for n in notes)
    return (
        '<slide xmlns="https://www.larkoffice.com/sml/2.0"><style><fill>'
        f'<fillColor color="{BG}"/></fill></style><data>{header}{body}{footer}</data>'
        f'<note><content>{note_xml}</content></note></slide>\n'
    )


def main():
    base = Path(__file__).resolve().parent
    ev = base / "evidence"
    out = base / "candidates"
    out.mkdir(exist_ok=True)
    p = json.loads((ev / "rk37_translation_pivot_result_v1.json").read_text())
    ind = json.loads((ev / "rk37_translation_pivot_independent_v1.json").read_text())
    clean = json.loads((ev / "rk37_translation_pivot_clean_result_v1.json").read_text())
    comp = json.loads((ev / "rk37_clean_reproduction_comparison_v1.json").read_text())
    close = json.loads((ev / "rk37_science_closeout_v2.json").read_text())
    ma = json.loads((ev / "rk37_manuscript_audit_v1.json").read_text())
    mi = json.loads((ev / "rk37_manuscript_integration_v1.json").read_text())
    protocol = json.loads((ev / "a8_rk37_translation_pivot_protocol_v1.json").read_text())
    primary = p["source_reports"][0]
    m = primary["target_evaluation"]["target_metrics"]
    endpoints = p["primary_endpoints"]
    source_sha = sha(ev / "rk37_translation_pivot_result_v1.json")
    protocol_sha = sha(ev / "a8_rk37_translation_pivot_protocol_v1.json")
    max_delta = max(v for v in ind["max_differences"].values() if isinstance(v, (int, float)))
    pos_gain = m["position_centered_anchored"]["mean_transcript_pearson"] - m["position_raw_unanchored"]["mean_transcript_pearson"]
    slides = []

    body = "".join((
        card(48, "SOURCE ELIGIBLE", f"{p['source_identity']['eligible_records']:,}", "Mohammad16 · source fitting only"),
        card(268, "TARGET ELIGIBLE", f"{p['target_identity']['eligible_records']:,}", "Subtelny14 · retrospective follow-up"),
        card(488, "EXACT CDS OVERLAP", str(p["target_identity"]["exact_cds_overlap"]), "no exact sequence overlap", GREEN),
        card(708, "CONFIRMATORY GATES", "2", "MSE and Pearson must both pass", AMBER),
        table(48, 202, [180, 330, 354], [
            ["Design choice", "Frozen implementation", "Reason"],
            ["Candidate", "477-d local codon context", "Seven codons at offsets -3 through +3 + position controls"],
            ["Existing control", "86-d position ridge", "Reproduces RK05; primary correlation comparator"],
            ["Error control", "Source-anchored constant", "Primary TB-MSE comparator"],
            ["Target", "Normalized ribosome occupancy", "Not physical elongation velocity or protein expression"],
            ["Deployment", "Raw / centered + source-only anchor", "No target outcome used for centering or calibration"],
        ], [26, 30, 30, 30, 30, 30]),
        band(400, "RK05 supplies the hurdle: RiboMIMO lost to source-fitted ridge and constant; beating RiboMIMO alone is insufficient."),
        band(440, "Success requires positive effects, positive CI lower bounds, Holm p<.05 and same-direction sensitivity seeds on BOTH endpoints.", PALE_AMBER, AMBER, 9.1),
    ))
    slides.append((174, "01 / PIVOT QUESTION", "Can local codon context improve cross-study occupancy prediction?", "Mohammad16 → Subtelny14 · normalized ribosome-occupancy proxy · retrospective follow-up to RK05", body, f"Source: result {source_sha[:12]} · protocol {protocol_sha[:12]} · source/target matrices SHA-bound", [
        "RK37 tests whether local codon context can repair the cross-study failure observed for RiboMIMO.",
        "The task uses normalized ribosome occupancy, not a direct physical translation-speed measurement.",
        "Both the constant error gate and the position-ridge correlation gate must pass before any improvement claim.",
    ]))

    body = "".join((
        card(48, "SOURCE SEEDS", str(p["fit_accounting"]["seeds"]), "1234 primary · 2345 / 3456 sensitivity"),
        card(268, "FEATURE FAMILIES", str(p["fit_accounting"]["families_per_seed"]), "position / local × raw / centered"),
        card(488, "ALPHA GRID", str(p["fit_accounting"]["alphas_per_family"]), "0.1 · 1 · 10 · 100"),
        card(708, "UNIQUE RIDGE FITS", f"{p['fit_accounting']['actual_unique_fits']} / {p['fit_accounting']['planned_unique_fits']}", "planned = actual · no refits", GREEN),
        table(48, 202, [180, 684], [
            ["Component", "Frozen execution rule"],
            ["Position features", "86 dimensions · one-hot codon at relative masked position + length / position terms"],
            ["Local features", "477 dimensions · 7 codons + validity indicators + 20 relative-position bins"],
            ["Centering", "Within source-train transcript only; deployment adds source-training global mean"],
            ["Selection", "Source validation only · all models and deployed arms fixed before target outcome access"],
            ["Primary inference", "20,000 transcript-paired bootstraps + 20,000 sign-flip permutations"],
            ["Multiplicity", "Two endpoints · unified two-sided Holm correction · two sensitivity seeds"],
        ], [26, 32, 32, 32, 32, 32, 32]),
        band(424, f"Freeze commit {p['frozen_git_commit'][:8]} · protocol SHA {protocol_sha[:12]} · target outcomes accessed after all source fits: {str(p['target_outcomes_accessed_after_all_source_fits']).lower()}"),
        band(464, "Primary candidate fixed in advance: local_centered_anchored. No post-target replacement candidate is promoted.", PALE_AMBER, AMBER),
    ))
    slides.append((175, "02 / FROZEN EXECUTION", "All selection is source-only; exactly 48 fits are preregistered", "3 seeds × 4 families × 4 alphas · source fitting and selection precede target outcomes", body, f"Source: protocol {protocol_sha[:12]} · freeze {p['frozen_git_commit'][:8]} · 20,000 bootstrap + 20,000 permutation", [
        "The protocol freezes three seeds, four feature-target families and four ridge penalties, giving 48 unique fits.",
        "Transcript centering and deployment anchoring use source data only, and target outcomes are accessed after source fitting and selection.",
        "The confirmatory analysis uses transcript-level resampling and Holm correction across two endpoints.",
    ]))

    sens_mse = endpoints[0]["sensitivity_effects"]
    sens_r = endpoints[1]["sensitivity_effects"]
    body = "".join((
        card(48, "TB-MSE IMPROVEMENT", f"{endpoints[0]['effect']:.8f}", "constant − local · negative = worse", RED),
        card(268, "PEARSON IMPROVEMENT", f"{endpoints[1]['effect']:.8f}", "local − position raw · negative = worse", RED),
        card(488, "HOLM p · BOTH", f"{endpoints[0]['holm_pvalue']:.5g}", "sign-flip permutation · adverse direction", AMBER),
        card(708, "GATES PASSED", "0 / 2", "both CIs entirely below zero", RED),
        table(48, 202, [210, 100, 230, 90, 117, 117], [
            ["Endpoint", "Effect", "95% CI", "Holm p", "Seed 2345", "Seed 3456"],
            ["Constant − local TB-MSE", f"{endpoints[0]['effect']:.8f}", f"[{endpoints[0]['ci95_low']:.8f}, {endpoints[0]['ci95_high']:.8f}]", f"{endpoints[0]['holm_pvalue']:.5g}", f"{sens_mse[0]:.8f}", f"{sens_mse[1]:.8f}"],
            ["Local − position mean r", f"{endpoints[1]['effect']:.8f}", f"[{endpoints[1]['ci95_low']:.8f}, {endpoints[1]['ci95_high']:.8f}]", f"{endpoints[1]['holm_pvalue']:.5g}", f"{sens_r[0]:.8f}", f"{sens_r[1]:.8f}"],
        ], [30, 44, 44], 8.8),
        band(336, "Small p values do NOT mean success: both intervals exclude zero in the adverse direction; all four sensitivity effects are negative.", PALE_RED, RED, 9.3),
        band(376, "DECISION · CROSS_STUDY_TRANSLATION_TASK_UNRESOLVED_COMPONENT_DIAGNOSIS_REQUIRED", PALE_RED, RED, 9.2),
        band(420, "Primary local centered: TB-MSE " + f"{m['local_centered_anchored']['transcript_balanced_mse']:.9f}" + " · mean Pearson r " + f"{m['local_centered_anchored']['mean_transcript_pearson']:.9f}" + " · no confirmatory gate passes.", PALE_AMBER, AMBER),
        band(460, "Interpretation is bounded to this observed Mohammad16 → Subtelny14 direction; it is not a universal mechanism-null result."),
    ))
    slides.append((176, "03 / PRIMARY DECISION", "Both preregistered endpoints move in the wrong direction", "20,000 transcript-paired bootstraps + 20,000 sign-flip permutations · unified Holm · 3 seeds", body, f"Source: result {source_sha[:12]} · primary seed {p['primary_seed']} · 0/2 gates · task unresolved", [
        "The local candidate increases transcript-balanced error relative to constant and lowers correlation relative to the position ridge.",
        "Both confidence intervals are entirely negative and both sensitivity-seed effects are negative for each endpoint.",
        "The small Holm-adjusted p values support reproducible degradation, not a successful model improvement.",
    ]))

    arm_rows = [
        ("constant", "Constant", "—"),
        ("ribomimo_raw", "RiboMIMO raw", "frozen"),
        ("ribomimo_anchored", "RiboMIMO anchored", "frozen"),
        ("position_raw_unanchored", "Position raw", "100"),
        ("position_raw_anchored", "Position raw anchored", "100"),
        ("position_centered_anchored", "Position centered anchored", "100"),
        ("local_raw_anchored", "Local raw anchored", "0.1"),
        ("local_centered_anchored", "Local centered anchored", "0.1"),
    ]
    rows = [["Arm", "alpha", "TB-MSE", "Mean Pearson r", "Mean Spearman rho"]]
    for arm, label, alpha in arm_rows:
        v = m[arm]
        pearson = "0 (degenerate)" if arm == "constant" else f"{v['mean_transcript_pearson']:.9f}"
        spearman = "NA" if v["mean_transcript_spearman"] is None else f"{v['mean_transcript_spearman']:.9f}"
        rows.append([label, alpha, f"{v['transcript_balanced_mse']:.9f}", pearson, spearman])
    body = "".join((
        card(48, "CONSTANT TB-MSE", f"{m['constant']['transcript_balanced_mse']:.9f}", "lowest primary-seed error", GREEN),
        card(268, "POSITION RAW", f"{m['position_raw_unanchored']['transcript_balanced_mse']:.9f}", f"mean r {m['position_raw_unanchored']['mean_transcript_pearson']:.9f}", TEAL),
        card(488, "LOCAL CENTERED", f"{m['local_centered_anchored']['transcript_balanced_mse']:.9f}", f"mean r {m['local_centered_anchored']['mean_transcript_pearson']:.9f}", RED),
        card(708, "RIBOMIMO RAW", f"{m['ribomimo_raw']['transcript_balanced_mse']:.9f}", f"mean r {m['ribomimo_raw']['mean_transcript_pearson']:.9f}", RED),
        table(48, 202, [280, 80, 180, 170, 154], rows, [24] + [28] * 8, 9.0),
        band(464, "All learned arms exceed constant TB-MSE at the primary seed; position retains the highest mean Pearson among learned arms.", PALE_RED, RED),
    ))
    slides.append((177, "04 / ABSOLUTE PERFORMANCE", "No learned arm beats constant on primary-seed TB-MSE", "Primary seed 1234 · Table 29 values · transcript-balanced MSE · within-transcript correlations", body, f"Source: result {source_sha[:12]} · manuscript Table 29 · 8 primary-seed arms", [
        "The constant predictor has the lowest transcript-balanced error among the displayed primary-seed arms.",
        "The position ridge has the highest mean within-transcript Pearson correlation among learned arms, while local context is near zero.",
        "Constant correlation is degenerate and is shown as zero or not applicable rather than interpreted as learned signal.",
    ]))

    local_sens = [s["target_evaluation"]["target_metrics"]["local_centered_anchored"] for s in p["source_reports"][1:]]
    body = "".join((
        card(48, "POSITION CENTERING", f"+{pos_gain:.9f} r", "small descriptive correlation gain", TEAL),
        card(268, "LOCAL alpha=100", f"{local_sens[1]['transcript_balanced_mse']:.9f}", "best sensitivity TB-MSE · still > constant", RED),
        card(488, "RIBO ANCHORED", f"{m['ribomimo_anchored']['transcript_balanced_mse']:.9f}", "error falls slightly · remains > constant", AMBER),
        card(708, "TARGET-SELECTED ARMS", "0", "no post-hoc winner promoted", GREEN),
        rect(48, 202, 864, 78), text(62, 211, 220, 16, "01 · POSITION CENTERING", 9, TEAL, True),
        text(62, 232, 836, 34, f"Mean r {m['position_raw_unanchored']['mean_transcript_pearson']:.9f} → {m['position_centered_anchored']['mean_transcript_pearson']:.9f} (+{pos_gain:.9f}); centered TB-MSE {m['position_centered_anchored']['transcript_balanced_mse']:.9f} remains above constant {m['constant']['transcript_balanced_mse']:.9f}.", 9.4, INK, False, "left", True),
        rect(48, 290, 864, 78), text(62, 299, 220, 16, "02 · LOCAL PENALTY SENSITIVITY", 9, RED, True),
        text(62, 320, 836, 34, f"alpha=100 sensitivity runs: TB-MSE {local_sens[0]['transcript_balanced_mse']:.9f} / {local_sens[1]['transcript_balanced_mse']:.9f}; mean r {local_sens[0]['mean_transcript_pearson']:.9f} / {local_sens[1]['mean_transcript_pearson']:.9f}. Failure persists across the frozen seed-specific penalties.", 9.4, INK, False, "left", True),
        rect(48, 378, 864, 78), text(62, 387, 220, 16, "03 · RIBOMIMO ANCHORING", 9, AMBER, True),
        text(62, 408, 836, 34, f"TB-MSE {m['ribomimo_raw']['transcript_balanced_mse']:.9f} → {m['ribomimo_anchored']['transcript_balanced_mse']:.9f}; mean r remains {m['ribomimo_anchored']['mean_transcript_pearson']:.9f}. Calibration alone does not rescue error or ranking.", 9.4, INK, False, "left", True),
        band(466, "Component diagnosis is complete for the frozen arms; none is relabeled as a new result after inspecting the target.", PALE_AMBER, AMBER),
    ))
    slides.append((178, "05 / COMPONENT DIAGNOSIS", "Simple calibration or alpha explanations do not rescue the pivot", "Frozen auxiliary arms · sensitivity seeds · no target-selected replacement model", body, f"Source: result {source_sha[:12]} · 3 seeds · primary and auxiliary arms", [
        "Position centering yields only a very small correlation increase and does not beat constant error.",
        "The alternative frozen local penalty still produces high error and near-zero correlation in both sensitivity seeds.",
        "Anchoring RiboMIMO changes calibration but does not make its error competitive or alter within-transcript correlation.",
    ]))

    body = "".join((
        card(48, "INDEPENDENT", f"{ind['checks_passed']} / {ind['checks_total']}", f"max numeric diff {max_delta:.3e}", GREEN),
        card(268, "CLEAN REPRODUCTION", f"{comp['checks_passed']} / {comp['checks_total']}", f"{comp['exact_arrays_compared']} arrays exact · 3 CSV byte-equal", GREEN),
        card(488, "SCIENCE CLOSEOUT", f"{close['checks_passed']} / {close['checks_total']}", "post-push rerun remains 90/90", GREEN),
        card(708, "PROJECT TESTS", "466 passed", "1 skipped · 5 subtests · 0 failed", GREEN),
        table(48, 202, [180, 150, 534], [
            ["Stage", "Result", "Evidence"],
            ["Frozen production", "48 / 48 fits", f"{p['frozen_git_commit'][:8]} · result SHA {source_sha[:12]} · 155.861 s"],
            ["Independent verifier", "771 / 771", "raw + features + 48 fits + coefficients + inference independently rebuilt"],
            ["Detached clean checkout", "877 / 877", f"111 NPZ arrays exact · 3 CSV byte-identical · {clean['execution']['wall_seconds']:.3f} s"],
            ["Scientific closeout", "90 / 90", "v1 88/90 FAIL retained; schema/log-reader fixes only · v2 90/90"],
            ["Manuscript", "16 / 16", f"§6.48 + Tables 28–29 · exact baseline rollback · SHA {ma['manuscript_sha256'][:12]}"],
            ["English workflow", "PASS", "947 words · markdown_only · prepare + write + deliver + status"],
        ], [26, 30, 30, 30, 30, 30, 30], 9.0),
        band(424, f"Manuscript integration: {mi['before_lines']} → {mi['after_lines']} lines · section SHA {mi['section_sha256'][:12]} · manuscript commit f2108c0d."),
        band(464, "Failure history is preserved: two initial test-fixture failures and three closeout reader failures did not alter scientific code or results.", PALE_AMBER, AMBER, 9.1),
    ))
    slides.append((179, "06 / REPRODUCTION & PAPER", "Independent and clean runs reproduce the negative decision", "771 independent checks · 877 clean comparisons · 90 closeout checks · manuscript §6.48 synchronized", body, f"Source: independent {sha(ev / 'rk37_translation_pivot_independent_v1.json')[:12]} · clean comparison {sha(ev / 'rk37_clean_reproduction_comparison_v1.json')[:12]} · closeout {sha(ev / 'rk37_science_closeout_v2.json')[:12]}", [
        "An independently written implementation reconstructs the raw data, features, model fits and inference without importing production code.",
        "A detached clean checkout reproduces every compared array and per-transcript CSV, while scientific closeout passes 90 checks.",
        "The English manuscript section and both tables are generated from accepted evidence and audited by exact rollback to the prior manuscript.",
    ]))

    body = "".join((
        card(48, "SCIENTIFIC TASK", "unresolved", "local ridge pivot rejected on this direction", RED),
        card(268, "RK-G1", str(p["scientific_scope"]["rk_g1_complete"]).lower(), "no generative training authorized", RED),
        card(488, "FUNCTIONAL UNTOUCHED", "not read", "retrospective RK05 follow-up only", AMBER),
        card(708, "WET LAB / DBTL", "not run", "no prospective functional validation", AMBER),
        table(48, 202, [180, 330, 354], [
            ["Scope", "Supported", "Not supported"],
            ["Effect", "Local ridge underperforms on observed direction", "Universal absence of local sequence effects"],
            ["Measurement", "Normalized ribosome-occupancy proxy", "Physical elongation velocity or protein expression"],
            ["Generalization", "Mohammad16 → Subtelny14 study shift", "Protein / homology OOD or untouched confirmation"],
            ["Diagnosis", "Frozen alpha, centering and anchoring checks", "SOTA, generator gain or functional rescue"],
        ], [26, 38, 38, 38, 38], 9.0),
        band(400, "NEXT DISCRIMINATIVE REQUIREMENT · a genuinely untouched translation-dynamics or functional dataset must pass provenance and split gates before new confirmatory claims.", PALE_AMBER, AMBER, 8.9),
        band(440, "RK37 is computationally closed, but the scientific task remains unresolved; RK-G1=false and no wet-lab or generator claim is made.", PALE_RED, RED, 9.2),
    ))
    slides.append((180, "07 / EVIDENCE BOUNDARY", "RK37 rejects this pivot, not all local sequence effects", "Negative retrospective cross-study diagnostic · no untouched, protein-OOD, physical-speed, SOTA or generator claim", body, f"Source: closeout {sha(ev / 'rk37_science_closeout_v2.json')[:12]} · manuscript {ma['manuscript_sha256'][:12]} · RK-G1=false", [
        "RK37 rejects the frozen local ridge pivot for the observed cross-study direction, not every possible local sequence mechanism.",
        "The result is retrospective and does not establish protein-family generalization, physical translation speed, functional expression or external SOTA.",
        "The scientific task remains unresolved, functional untouched data were not read, and no generator or wet-lab experiment is authorized by this result.",
    ]))

    manifest = {
        "status": "PASS_RK37_PPT_CANDIDATES",
        "presentation": "WB1KsYGualerMUddEzMcCw1En0g",
        "baseline_pages": 173,
        "baseline_revision": 145,
        "expected_final_pages": 180,
        "evidence_sha256": {f.name: sha(f) for f in sorted(ev.glob("*.json"))},
        "pages": [],
    }
    for page, kicker, title_value, subtitle, body, source, notes in slides:
        xml = slide(page, kicker, title_value, subtitle, body, source, notes)
        root = ET.fromstring(xml)
        ns = {"s": root.tag.split("}")[0].strip("{")}
        assert root.find("s:data", ns) is not None
        assert len(root.findall("s:note/s:content/s:p", ns)) == 3
        assert "<p>" in xml and "None" not in xml
        path = out / f"rk37_{page}.xml"
        path.write_text(xml)
        manifest["pages"].append({"page": page, "slide_file": path.name, "title": title_value, "kicker": kicker, "sha256": sha(path), "required_tokens": [str(page), "A8 / RK37 / TRANSLATION PIVOT", title_value], "notes": len(notes)})
    (base / "rk37_ppt_candidate_manifest_v1.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": manifest["status"], "pages": len(slides), "final_pages": 180, "files": [entry["page"] for entry in manifest["pages"]]}, indent=2))


if __name__ == "__main__":
    main()
