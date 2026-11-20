#!/usr/bin/env python3
"""Build and preflight one evidence-bound RK08 constant-field result slide."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "https://www.larkoffice.com/sml/2.0"
ET.register_namespace("", NS)
MARKER = "RK08 · CONSTANT FIELD"
PAGE = 109
EVIDENCE_COMMITS = ("3dec5eca", "9223f481")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def element(parent, tag, **attrs):
    return ET.SubElement(parent, f"{{{NS}}}{tag}", {k: str(v) for k, v in attrs.items()})


def fill(parent, color):
    node = element(parent, "fill")
    element(node, "fillColor", color=color)


def text(parent, x, y, w, h, value, size=10, color="rgba(71, 85, 105, 1)",
         bold=False, align="left", wrap=True, line="multiple:1.15", text_type=None):
    shape = element(parent, "shape", type="text", topLeftX=x, topLeftY=y, width=w, height=h)
    attrs = dict(fontSize=size, fontFamily="Aptos", color=color,
                 bold=str(bool(bold)).lower(), lineSpacing=line,
                 textAlign=align, wrap=str(bool(wrap)).lower())
    if text_type:
        attrs["textType"] = text_type
    content = element(shape, "content", **attrs)
    for line_value in str(value).split("\n"):
        p = element(content, "p")
        p.text = line_value
    return shape


def card(parent, x, y, w, h, color="rgba(255, 255, 255, 1)", border="rgba(226, 232, 240, 1)"):
    shape = element(parent, "shape", type="round-rect", topLeftX=x, topLeftY=y,
                    width=w, height=h, presetHandlers=10)
    fill(shape, color)
    element(shape, "border", color=border, width=1)
    element(shape, "content", fontSize=16, fontFamily="思源黑体", color="rgba(31, 35, 41, 1)")


def visible_text(root):
    return "\n".join("".join(p.itertext()) for p in root.iter()
                     if p.tag.rsplit("}", 1)[-1] == "p")


def signed(value, digits=5):
    value = float(value)
    if value == 0:
        return "0"
    return f"{value:+.{digits}f}".replace("-", "−")


def plain(value, digits=6):
    return f"{float(value):.{digits}f}".replace("-", "−")


def p_display(value):
    return "<0.001" if float(value) == 0 else f"{float(value):.5f}"


def display_comparison(row):
    mse = row["transcript_balanced_mse"]
    cor = row["mean_transcript_pearson"]
    return {
        "mse": f"{signed(row['delta_transcript_balanced_mse'])} [{signed(mse['ci95'][0])}, {signed(mse['ci95'][1])}]",
        "mse_p": p_display(mse["holm_pvalue"]),
        "cor": f"{signed(row['delta_mean_transcript_pearson'])} [{signed(cor['ci95'][0])}, {signed(cor['ci95'][1])}]",
        "cor_p": p_display(cor["holm_pvalue"]),
    }


def build_slide(production, independent, finalization, postpush, recheck):
    metrics = production["metrics"][production["primary_partition"]]
    comparisons = production["primary_comparisons"]
    slide = ET.Element(f"{{{NS}}}slide")
    style = element(slide, "style")
    fill(style, "rgba(248, 250, 252, 1)")
    data = element(slide, "data")

    text(data, 48, 20, 690, 16, "A8-RK · VELOCITY MECHANISM CONTROL · 20 NOV 2026",
         10, "rgba(100, 116, 139, 1)", wrap=False, line="multiple:1", text_type="caption")
    text(data, 770, 20, 142, 16, MARKER, 10, "rgba(15, 118, 110, 1)", True,
         "right", False, "multiple:1", "caption")
    text(data, 48, 43, 864, 38, "Constant field wins the primary study-OOD control",
         28, "rgba(15, 23, 42, 1)", True, wrap=False, line="multiple:1", text_type="title")
    accent = element(data, "shape", type="rect", topLeftX=48, topLeftY=87, width=56, height=4, presetHandlers=2)
    fill(accent, "rgba(15, 118, 110, 1)")
    element(accent, "content", fontSize=16, fontFamily="思源黑体", color="rgba(31, 35, 41, 1)")
    text(data, 116, 82, 796, 18,
         "3,630 Subtelny14 transcripts · 20 train-fitted relative-position bins · 2,000 bootstraps × 3 seeds · 6 Holm-adjusted tests",
         11, wrap=False, line="multiple:1")

    cards = [
        (48, "CONSTANT FIELD · TB-MSE", plain(metrics["constant"]["transcript_balanced_mse"]), "LOWER IS BETTER"),
        (270, "CONSTANT FIELD · MEAN R", signed(metrics["constant"]["mean_transcript_pearson"], 6), "ABSOLUTE TRANSFER REMAINS LOW"),
        (492, "INDEPENDENT · FROZEN", f"{independent['passed_count']} / {independent['check_count']}", "PASS · MAX DELTA 6.25E-17"),
        (714, "FRESH RECHECK · UNIT", f"{recheck['passed_count']} / {recheck['check_count']}", "PASS · 10/10 TESTS"),
    ]
    for x, label, value, sub in cards:
        card(data, x, 110, 198, 66)
        text(data, x + 16, 119, 166, 12, label, 8.5, "rgba(100, 116, 139, 1)",
             wrap=False, line="multiple:1", text_type="caption")
        text(data, x + 16, 134, 166, 27, value, 22, "rgba(15, 23, 42, 1)", True,
             wrap=False, line="multiple:1", text_type="headline")
        text(data, x + 16, 162, 166, 10, sub, 8, "rgba(15, 118, 110, 1)", True,
             wrap=False, line="multiple:1", text_type="caption")

    text(data, 48, 194, 620, 20, "Primary paired comparisons · positive MSE and negative r favor the constant field",
         14, "rgba(15, 23, 42, 1)", True, wrap=False, line="multiple:1", text_type="headline")
    text(data, 700, 196, 212, 16, "Rounded display · full precision in note", 9,
         "rgba(100, 116, 139, 1)", align="right", wrap=False, line="multiple:1", text_type="caption")
    table = element(data, "table", topLeftX=48, topLeftY=222, width=864, height=136)
    colgroup = element(table, "colgroup")
    for width in [150, 280, 70, 280, 84]:
        element(colgroup, "col", width=width)
    headers = ["Comparison", "Delta TB-MSE [95% CI]", "Holm p", "Delta mean-r [95% CI]", "Holm p"]
    row = element(table, "tr", height=28)
    for header in headers:
        td = element(row, "td")
        fill(td, "rgba(15, 118, 110, 1)")
        content = element(td, "content", fontSize=10, fontFamily="思源黑体",
                          color="rgba(255, 255, 255, 1)", bold="true", textAlign="center")
        p = element(content, "p")
        p.text = header
    labels = [
        ("model_minus_constant", "model − constant"),
        ("ridge_minus_constant", "ridge − constant"),
        ("model_minus_ridge", "model − ridge"),
    ]
    for key, label in labels:
        values = display_comparison(comparisons[key])
        row = element(table, "tr", height=36)
        for j, value in enumerate([label, values["mse"], values["mse_p"], values["cor"], values["cor_p"]]):
            td = element(row, "td")
            if j > 0:
                fill(td, "rgba(255, 247, 237, 1)")
            content = element(td, "content", fontSize=10, fontFamily="Aptos",
                              color="rgba(154, 52, 18, 1)" if j > 0 else "rgba(30, 41, 59, 1)",
                              bold="true" if j in (0, 2, 4) else "false",
                              textAlign="left" if j == 0 else "center")
            p = element(content, "p")
            p.text = value

    card(data, 48, 370, 420, 70, "rgba(255, 247, 237, 1)", "rgba(253, 186, 116, 1)")
    text(data, 64, 380, 388, 18, "Primary constant-field control fails", 13,
         "rgba(154, 52, 18, 1)", True, wrap=False, line="multiple:1", text_type="headline")
    text(data, 64, 400, 388, 34,
         "Both learned models are worse on both primary endpoints\nAll three preregistered support flags remain false; sensitivity seeds agree.",
         10.5, "rgba(30, 41, 59, 1)", line="multiple:1.1")
    card(data, 492, 370, 420, 70, "rgba(255, 247, 237, 1)", "rgba(253, 186, 116, 1)")
    text(data, 508, 380, 388, 18, "This is not evidence of strong absolute transfer", 13,
         "rgba(154, 52, 18, 1)", True, wrap=False, line="multiple:1", text_type="headline")
    text(data, 508, 400, 388, 34,
         "Constant mean r = 0.124649 on an occupancy-derived speed proxy\nNo causal, functional, protein-OOD, external-SOTA, or readiness claim.",
         10.5, "rgba(30, 41, 59, 1)", line="multiple:1.1")

    card(data, 48, 455, 864, 36, "rgba(255, 247, 237, 1)", "rgba(253, 186, 116, 1)")
    text(data, 64, 461, 832, 24,
         "Velocity mechanism = false · RK-G1 = false · functional untouched not evaluated · generator training unauthorized",
         11, "rgba(154, 52, 18, 1)", True, wrap=False, line="multiple:1")
    text(data, 48, 505, 720, 13,
         "Source: manuscript v33 §3.6 · production / independent / finalization · evidence 3dec5eca / 9223f481",
         9, "rgba(100, 116, 139, 1)", wrap=False, line="multiple:1", text_type="caption")
    text(data, 800, 505, 112, 13, f"A8-RK · {PAGE}", 9, "rgba(100, 116, 139, 1)",
         align="right", wrap=False, line="multiple:1", text_type="caption")

    note = element(slide, "note")
    content = element(note, "content")
    paragraphs = [
        f"The primary partition was {production['primary_partition']} with {metrics['constant']['n_transcripts']} transcripts and {metrics['constant']['n_observed_positions']} observed positions; the sequence-independent field used 20 relative-position bins fitted only on Mohammad16 training data, and the analysis performed no model training, checkpoint selection, forward pass, or scorer call.",
        "Primary metrics were " + "; ".join(
            f"{name} TB-MSE={metrics[name]['transcript_balanced_mse']!r}, mean transcript Pearson={metrics[name]['mean_transcript_pearson']!r}, position MSE={metrics[name]['position_mse']!r}"
            for name in ("model", "ridge", "constant")
        ) + ".",
    ]
    comparison_sentences = []
    for key, label in labels:
        row = comparisons[key]
        mse = row["transcript_balanced_mse"]
        cor = row["mean_transcript_pearson"]
        comparison_sentences.append(
            f"{label}: Delta TB-MSE={row['delta_transcript_balanced_mse']!r} with 95% CI={mse['ci95']!r} and Holm p={mse['holm_pvalue']!r}, "
            f"Delta mean-r={row['delta_mean_transcript_pearson']!r} with 95% CI={cor['ci95']!r} and Holm p={cor['holm_pvalue']!r}, "
            f"bootstrap={row['bootstrap_replicates']} at primary seed {row['bootstrap_seed']}, and sensitivity results {row['sensitivity_bootstrap_mean_deltas']!r}"
        )
    paragraphs.append("Paired comparisons were " + "; ".join(comparison_sentences) + ".")
    paragraphs.append(
        f"Independent verification passed {independent['passed_count']}/{independent['check_count']} with maximum numeric delta {independent['max_numeric_delta']!r}, finalization passed {finalization['passed_count']}/{finalization['check_count']}, postpush verification passed {postpush['passed_count']}/{postpush['check_count']}, the fresh recheck passed {recheck['passed_count']}/{recheck['check_count']} with maximum numeric delta {recheck['max_numeric_delta']!r}, and the targeted unit suite passed 10/10; evidence commits were 3dec5eca and 9223f481."
    )
    paragraphs.append(
        "All preregistered support flags were false, and this sequence-independent position-field diagnostic on occupancy-derived speed proxies does not establish causal mechanism, functional improvement, protein-OOD transport, external SOTA, or generation readiness; RK-G1 remains false, functional untouched data were not evaluated, and generator training remains unauthorized."
    )
    for paragraph in paragraphs:
        p = element(content, "p")
        p.text = paragraph
    return slide


def semantic_signature(element_):
    tail = element_.tail if element_.tail and element_.tail.strip() else None
    return (element_.tag, tuple(sorted(element_.attrib.items())), element_.text, tail,
            tuple(semantic_signature(child) for child in element_))


def main():
    ap = argparse.ArgumentParser()
    for name in ["production", "independent", "finalization", "postpush", "recheck",
                 "unit-log", "baseline-xml", "baseline-response", "output", "report"]:
        ap.add_argument("--" + name, required=True)
    args = ap.parse_args()
    paths = {name: Path(getattr(args, name.replace("-", "_"))) for name in
             ["production", "independent", "finalization", "postpush", "recheck", "unit_log", "baseline_xml", "baseline_response"]}
    production = load(paths["production"])
    independent = load(paths["independent"])
    finalization = load(paths["finalization"])
    postpush = load(paths["postpush"])
    recheck = load(paths["recheck"])
    baseline_response = load(paths["baseline_response"])
    baseline = ET.parse(paths["baseline_xml"]).getroot()
    baseline_slides = [e for e in list(baseline) if e.tag.rsplit("}", 1)[-1] == "slide"]

    if production.get("status") != "PASS_CONSTANT_VELOCITY_FIELD_PRODUCTION":
        raise SystemExit("Refusing PPT: production is not passed")
    if independent.get("status") != "PASS_CONSTANT_VELOCITY_INDEPENDENT" or independent.get("failed_count") != 0:
        raise SystemExit("Refusing PPT: independent verification is not passed")
    if recheck.get("status") != "PASS_CONSTANT_VELOCITY_INDEPENDENT" or recheck.get("failed_count") != 0:
        raise SystemExit("Refusing PPT: fresh independent recheck is not passed")
    if production["protocol_sha256"] != independent["protocol_sha256"] or production["protocol_sha256"] != recheck["protocol_sha256"]:
        raise SystemExit("Refusing PPT: protocol hashes differ")
    if independent["production_sha256"] != sha(paths["production"]) or recheck["production_sha256"] != sha(paths["production"]):
        raise SystemExit("Refusing PPT: independent reports do not bind production")
    if finalization.get("status") != "PASS_CONSTANT_VELOCITY_FIELD_CLOSEOUT" or finalization.get("failed_count") != 0:
        raise SystemExit("Refusing PPT: finalization failed")
    if postpush.get("status") != "PASS_CONSTANT_VELOCITY_INDEPENDENT" or postpush.get("failed_count") != 0:
        raise SystemExit("Refusing PPT: postpush verification failed")
    if "10 passed" not in paths["unit_log"].read_text(encoding="utf-8"):
        raise SystemExit("Refusing PPT: targeted unit-test log is not passing")
    gates = production["gates"]
    if any(gates[key] for key in ["velocity_mechanism_pass", "rk_g1_pass", "functional_untouched_evaluated", "generator_training_authorized", "external_sota_claim_authorized"]):
        raise SystemExit("Refusing PPT: negative scientific boundary changed")
    if any(production["support"].values()):
        raise SystemExit("Refusing PPT: support flags are expected to remain false")
    if not baseline_response.get("ok") or len(baseline_slides) != 108:
        raise SystemExit("Refusing PPT: expected a readable 108-page baseline")
    if baseline_slides[-1].get("id") != "pZS" or MARKER in visible_text(baseline):
        raise SystemExit("Refusing PPT: baseline anchor changed or duplicate marker exists")

    slide = build_slide(production, independent, finalization, postpush, recheck)
    ET.indent(slide, space="  ")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(ET.tostring(slide, encoding="utf-8", xml_declaration=False) + b"\n")
    parsed = ET.parse(output).getroot()
    data = parsed.find(f"{{{NS}}}data")
    visible = visible_text(data)
    checks = []

    def check(name, condition, detail=None):
        checks.append({"name": name, "pass": bool(condition), "detail": detail})
        if not condition:
            raise SystemExit(f"PPT preflight failed: {name}: {detail}")

    check("single_slide", parsed.tag == f"{{{NS}}}slide")
    check("no_preassigned_ids", all("id" not in e.attrib for e in parsed.iter()))
    check("no_external_or_unknown_media", all(e.tag.rsplit("}", 1)[-1] not in {"img", "embed", "undefined"} for e in parsed.iter()))
    check("no_emoji", not re.search(r"[\U0001F300-\U0001FAFF]", visible_text(parsed)))
    check("single_marker", visible.count(MARKER) == 1)
    for i, e in enumerate(data.findall(".//*[@topLeftX]")):
        x, y, w, h = (float(e.get(k)) for k in ["topLeftX", "topLeftY", "width", "height"])
        check(f"canvas_bounds_{i}", 0 <= x and 0 <= y and x + w <= 960 and y + h <= 540, [x, y, w, h])
    boxes = [(float(e.get("topLeftX")), float(e.get("topLeftY")), float(e.get("width")), float(e.get("height")))
             for e in data if e.tag == f"{{{NS}}}shape" and e.get("type") == "text"]
    overlaps = []
    for i, (x1, y1, w1, h1) in enumerate(boxes):
        for x2, y2, w2, h2 in boxes[i + 1:]:
            ix = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
            iy = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
            if ix * iy > 0.01:
                overlaps.append([x1, y1, w1, h1, x2, y2, w2, h2])
    check("no_text_text_overlap", not overlaps, overlaps)
    check("native_table", len(data.findall(f".//{{{NS}}}tr")) == 4)
    for key in ["model_minus_constant", "ridge_minus_constant", "model_minus_ridge"]:
        values = display_comparison(production["primary_comparisons"][key])
        for label, value in values.items():
            check(f"visible_{key}_{label}", value in visible, value)
    for phrase in ["Velocity mechanism = false", "RK-G1 = false", "functional untouched not evaluated",
                   "generator training unauthorized", "3,630 Subtelny14 transcripts", "A8-RK · 109"]:
        check(f"boundary_{phrase}", phrase in visible)
    report = {
        "schema": "a8-rk08-constant-field-ppt-candidate-v1",
        "status": "PASS_CONSTANT_FIELD_PPT_CANDIDATE",
        "overall_pass": True,
        "check_counts": {"passed": len(checks), "total": len(checks)},
        "candidate_sha256": sha(output),
        "baseline_xml_sha256": sha(paths["baseline_xml"]),
        "baseline_slide_count": len(baseline_slides),
        "baseline_revision_id": baseline_response.get("data", {}).get("revision_id"),
        "baseline_last_slide_id": baseline_slides[-1].get("id"),
        "production_sha256": sha(paths["production"]),
        "independent_sha256": sha(paths["independent"]),
        "finalization_sha256": sha(paths["finalization"]),
        "postpush_sha256": sha(paths["postpush"]),
        "recheck_sha256": sha(paths["recheck"]),
        "velocity_mechanism_pass": False,
        "rk_g1_pass": False,
        "functional_untouched_evaluated": False,
        "generator_training_authorized": False,
        "checks": checks,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks),
                      "candidate_sha256": report["candidate_sha256"],
                      "baseline_slides": len(baseline_slides),
                      "baseline_revision": report["baseline_revision_id"]}, indent=2))


if __name__ == "__main__":
    main()
