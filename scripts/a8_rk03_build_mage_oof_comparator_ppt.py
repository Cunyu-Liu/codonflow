#!/usr/bin/env python3
"""Build one evidence-bound slide for the MAGE OOF comparator-closure audit."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

NS = "https://www.larkoffice.com/sml/2.0"
ET.register_namespace("", NS)
MARKER = "RK03 · MAGE OOF COMPARATOR CLOSURE"


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p): return json.loads(Path(p).read_text())
def E(tag, **attrs): return ET.Element(f"{{{NS}}}{tag}", {k: str(v) for k, v in attrs.items()})
def S(parent, tag, **attrs): return ET.SubElement(parent, f"{{{NS}}}{tag}", {k: str(v) for k, v in attrs.items()})
def fill(parent, color):
    f = S(parent, "fill"); S(f, "fillColor", color=color)
def text(slide, x, y, w, h, value, size=10, color="rgba(71, 85, 105, 1)", bold=False,
         align="left", wrap=True, line="multiple:1.15", text_type=None):
    sh = S(slide, "shape", type="text", topLeftX=x, topLeftY=y, width=w, height=h)
    kw = dict(fontSize=size, fontFamily="思源黑体", color=color, bold=str(bool(bold)).lower(),
              lineSpacing=line, textAlign=align, wrap=str(bool(wrap)).lower())
    if text_type: kw["textType"] = text_type
    c = S(sh, "content", **kw)
    for line_value in str(value).split("\n"):
        p = S(c, "p"); p.text = line_value
    return sh
def card(slide, x, y, w, h, color, border):
    sh = S(slide, "shape", type="round-rect", topLeftX=x, topLeftY=y, width=w, height=h, presetHandlers=12)
    fill(sh, color); S(sh, "border", color=border, width=1)
    S(sh, "content", fontSize=16, fontFamily="思源黑体", color="rgba(31, 35, 41, 1)")
def fmt(v):
    v = float(v)
    if v == 0: return "0"
    return f"{v:.4g}"
def pfmt(v):
    v = float(v)
    return "0" if v == 0 else f"{v:.3g}"
def visible_text(elem):
    return "\n".join("".join(p.itertext()) for p in elem.iter() if p.tag.rsplit("}", 1)[-1] == "p")
def ci(row, name):
    return f"[{fmt(row[name+'_ci95'][0])}, {fmt(row[name+'_ci95'][1])}]"
def sign(v): return "+" if float(v) > 0 else ("−" if float(v) < 0 else "0")


def build(prod, ind, commit):
    comparisons = prod["exploratory_comparisons"]
    full_rcs = comparisons["full_mechanism_minus_rcs_only"]
    rcs_intr = comparisons["rcs_only_minus_intrinsic"]
    full_mean = comparisons["full_mechanism_minus_outer_train_mean"]
    models = prod["primary_models"]
    slide = E("slide")
    style = S(slide, "style"); fill(style, "rgba(248, 250, 252, 1)")
    data = S(slide, "data")
    count = ind["check_counts"]
    card(data, 712, 24, 192, 30, "rgba(220, 252, 231, 1)", "rgba(220, 252, 231, 1)")
    text(data, 720, 29, 176, 20, f"IND {count['passed']}/{count['total']} · 9/9 TESTS", 10,
         "rgba(21, 128, 61, 1)", True, "center", False, "multiple:1", "caption")
    text(data, 56, 25, 640, 20, MARKER, 10, "rgba(37, 99, 235, 1)", True, "left", False, "multiple:1", "caption")
    text(data, 56, 56, 848, 34, "MAGE 对照补全：优于均值，不等于机制增量", 25, "rgba(15, 23, 42, 1)", True,
         "left", False, "multiple:1", "headline")
    text(data, 56, 94, 848, 38,
         "131 development OOF · 原 33 test constructs 排除 · post-hoc exploratory · 0 new model fits\n"
         "20,000 bootstrap + 20,000 paired permutations · Holm across 5 tests · three outer-CV seeds", 11,
         "rgba(71, 85, 105, 1)", False, "left", True, "multiple:1.2")

    cards = [
        (56, "FULL MECHANISM RMSE", fmt(models["full_mechanism"]["rmse"]), "OOF · primary seed"),
        (344, "OUTER-TRAIN MEAN RMSE", fmt(models["outer_train_mean"]["rmse"]), "fold-specific train means only"),
        (632, "FULL − MEAN · ΔRMSE", fmt(full_mean["delta_rmse"]), f"95% CI {ci(full_mean, 'delta_rmse')} · Holm p={pfmt(full_mean['holm_p_rmse'])}"),
    ]
    for x, label, value, sub in cards:
        card(data, x, 140, 272, 88, "rgba(239, 246, 255, 1)", "rgba(147, 197, 253, 1)")
        text(data, x+16, 150, 240, 18, label, 10, "rgba(71, 85, 105, 1)", True, "left", True, "multiple:1", "caption")
        text(data, x+16, 172, 240, 31, value, 22, "rgba(30, 64, 175, 1)", True, "left", False, "multiple:1", "headline")
        text(data, x+16, 207, 240, 15, sub, 8, "rgba(100, 116, 139, 1)", False, "left", True, "multiple:1", "caption")

    text(data, 56, 240, 848, 18, "THREE EXPLORATORY PAIRED CONTRASTS · POSITIVE Δρ FAVORS CANDIDATE · NEGATIVE ΔRMSE FAVORS CANDIDATE", 9,
         "rgba(71, 85, 105, 1)", True, "left", True, "multiple:1", "caption")
    table = S(data, "table", topLeftX=56, topLeftY=264, width=820, height=122)
    cg = S(table, "colgroup")
    for w in [200, 230, 80, 230, 80]: S(cg, "col", width=w)
    headers = ["Contrast", "ΔSpearman [95% CI]", "Holm p", "ΔRMSE [95% CI]", "Holm p"]
    tr = S(table, "tr", height=24)
    for h in headers:
        td = S(tr, "td"); fill(td, "rgba(30, 64, 175, 1)")
        c = S(td, "content", fontSize=8, fontFamily="思源黑体", color="rgba(255, 255, 255, 1)", bold="true", lineSpacing="multiple:1", textAlign="center")
        p = S(c, "p"); p.text = h
    rows = [
        ("Full − RCS arm", full_rcs, False),
        ("RCS arm − intrinsic", rcs_intr, False),
        ("Full − outer-train mean", full_mean, True),
    ]
    for label, row, mean_only in rows:
        tr = S(table, "tr", height=30)
        rho = "descriptive only" if mean_only else f"{fmt(row['delta_spearman'])} {ci(row, 'delta_spearman')}"
        prho = "—" if mean_only else pfmt(row["holm_p_spearman"])
        values = [label, rho, prho, f"{fmt(row['delta_rmse'])} {ci(row, 'delta_rmse')}", pfmt(row["holm_p_rmse"])]
        for j, value in enumerate(values):
            td = S(tr, "td")
            color = "rgba(71, 85, 105, 1)"
            c = S(td, "content", fontSize=8, fontFamily="思源黑体", color=color, bold=str(j == 0).lower(), lineSpacing="multiple:1", textAlign="left" if j == 0 else "center")
            p = S(c, "p"); p.text = str(value)

    sens = prod["sensitivity"]
    seeds = ["40261119", "40261120", "40261121"]
    def series(cid, metric): return " / ".join(sign(sens[s]["comparisons"][cid][metric]) for s in seeds)
    card(data, 56, 402, 410, 74, "rgba(239, 246, 255, 1)", "rgba(239, 246, 255, 1)")
    text(data, 70, 409, 382, 58,
         f"SEED SIGNS · primary / sensitivity 1 / sensitivity 2\nFull−mean ΔRMSE: {series('full_mechanism_minus_outer_train_mean', 'delta_rmse')} · 3/3 favorable\n"
         f"Full−RCS Δρ: {series('full_mechanism_minus_rcs_only', 'delta_spearman')} · ΔRMSE: {series('full_mechanism_minus_rcs_only', 'delta_rmse')}\n"
         f"RCS−intrinsic Δρ: {series('rcs_only_minus_intrinsic', 'delta_spearman')} · ΔRMSE: {series('rcs_only_minus_intrinsic', 'delta_rmse')}", 8,
         "rgba(30, 64, 175, 1)", False, "left", True, "multiple:1.15")
    card(data, 486, 402, 418, 74, "rgba(255, 247, 237, 1)", "rgba(255, 247, 237, 1)")
    text(data, 500, 409, 390, 58,
         "结论 · 均值对照方向一致；4/4 机制增量检验 Holm p=1，CI 跨 0\n"
         "DEV_NO_GO_TEST_UNTOUCHED 不变 · no test / transport / generator\n"
         "rcs_only 含 intrinsic；纯外部模型与常数速度臂仍未闭合", 9,
         "rgba(154, 52, 18, 1)", False, "left", True, "multiple:1.2")
    text(data, 56, 496, 700, 18,
         f"Evidence: 131 OOF · independent {count['passed']}/{count['total']} · tests 9/9 · 120,000 resamples · GitHub {commit[:10]}",
         8, "rgba(100, 116, 139, 1)", False, "left", True, "multiple:1", "caption")
    text(data, 776, 496, 128, 18, "RK03 · 2026-11-20", 9, "rgba(100, 116, 139, 1)", False, "right", False, "multiple:1", "caption")

    note = S(slide, "note"); nc = S(note, "content")
    paragraphs = [
        "本页只使用既有 MAGE nested-CV 的 131 个 development OOF 预测，原 33 个 test constructs 未读取。没有重新拟合模型，也没有新序列、标签或湿实验。该分析是 post-hoc exploratory comparator closure，不是独立确认。",
        f"full mechanism 的 RMSE={models['full_mechanism']['rmse']!r}，outer-training-mean 的 RMSE={models['outer_train_mean']['rmse']!r}。full−mean ΔRMSE={full_mean['delta_rmse']!r}，95% CI={full_mean['delta_rmse_ci95']!r}，raw permutation p={full_mean['permutation_p_rmse']!r}，五检验 Holm p={full_mean['holm_p_rmse']!r}。三个 seed 的 ΔRMSE 分别为 " + ", ".join(repr(sens[s]['comparisons']['full_mechanism_minus_outer_train_mean']['delta_rmse']) for s in seeds) + "。",
        f"full−rcs_only：ΔSpearman={full_rcs['delta_spearman']!r}，95% CI={full_rcs['delta_spearman_ci95']!r}，Holm p={full_rcs['holm_p_spearman']!r}；ΔRMSE={full_rcs['delta_rmse']!r}，95% CI={full_rcs['delta_rmse_ci95']!r}，Holm p={full_rcs['holm_p_rmse']!r}。",
        f"rcs_only−intrinsic：ΔSpearman={rcs_intr['delta_spearman']!r}，95% CI={rcs_intr['delta_spearman_ci95']!r}，Holm p={rcs_intr['holm_p_spearman']!r}；ΔRMSE={rcs_intr['delta_rmse']!r}，95% CI={rcs_intr['delta_rmse_ci95']!r}，Holm p={rcs_intr['holm_p_rmse']!r}。",
        "outer-training mean 在每个 outer fold 内只用训练折标签均值，但不同 fold 的均值可变，因此其 OOF Spearman 只作描述，不作配对 Spearman 推断。rcs_only 是冻结臂名，实际包含 intrinsic+RCS，不是纯外部预训练模型。独立复核 24/24、单元测试 9/9 通过。DEV_NO_GO_TEST_UNTOUCHED 不变；未授权 test、transport、生成器训练或 SOTA 结论。科学代码提交为 " + commit + "。",
    ]
    for paragraph in paragraphs:
        p = S(nc, "p"); p.text = paragraph
    return slide


def main():
    ap = argparse.ArgumentParser()
    for name in ["production", "independent", "unit-log", "baseline-xml", "baseline-response", "output", "report"]:
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--git-commit", required=True)
    a = ap.parse_args()
    prod, ind = load(a.production), load(a.independent)
    if prod.get("overall_pass") is not True or ind.get("overall_pass") is not True:
        raise SystemExit("Refusing PPT: production/independent technical pass missing")
    if ind.get("production_report_sha256") != sha(a.production):
        raise SystemExit("Refusing PPT: independent report does not bind production")
    if prod.get("scientific_gate") != "UNCHANGED_DEV_NO_GO_TEST_UNTOUCHED" or prod.get("test_authorized") is not False:
        raise SystemExit("Refusing PPT: scientific boundary changed")
    unit = Path(a.unit_log).read_text()
    if "Ran 9 tests" not in unit or "OK" not in unit:
        raise SystemExit("Refusing PPT: nine-test success log missing")
    if not re.fullmatch(r"[0-9a-f]{40}", a.git_commit): raise SystemExit("Invalid Git commit")
    base_response = load(a.baseline_response)
    if not base_response.get("ok"): raise SystemExit("Baseline response is not ok")
    root = ET.parse(a.baseline_xml).getroot()
    if MARKER in visible_text(root): raise SystemExit("Refusing duplicate MAGE comparator page")
    pages = [e for e in list(root) if e.tag.rsplit("}", 1)[-1] == "slide"]
    slide = build(prod, ind, a.git_commit)
    ET.indent(slide, space="  ")
    out = Path(a.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(ET.tostring(slide, encoding="utf-8", xml_declaration=False) + b"\n")
    parsed = ET.parse(out).getroot()
    data = next(e for e in parsed if e.tag.rsplit("}", 1)[-1] == "data")
    texts = visible_text(data)
    checks = []
    def check(name, passed, detail=None):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        if not passed: raise SystemExit(f"PPT preflight failed: {name}: {detail}")
    check("single_slide", parsed.tag == f"{{{NS}}}slide")
    check("no_preassigned_ids", all("id" not in e.attrib for e in parsed.iter()))
    check("no_external_images_or_embeds", all(e.tag.rsplit("}", 1)[-1] not in {"img", "embed", "undefined"} for e in parsed.iter()))
    check("single_marker", visible_text(parsed).count(MARKER) == 1)
    bounds = []
    for e in data:
        if e.tag.rsplit("}", 1)[-1] not in {"shape", "table", "line", "img", "icon"}: continue
        if e.tag.rsplit("}", 1)[-1] == "line": continue
        x, y, w, h = (float(e.attrib[k]) for k in ["topLeftX", "topLeftY", "width", "height"])
        inside = x >= 0 and y >= 0 and x+w <= 960 and y+h <= 540
        bounds.append({"x": x, "y": y, "w": w, "h": h, "inside": inside})
    check("all_elements_inside_canvas", all(b["inside"] for b in bounds), bounds)
    boxes = []
    for e in data:
        if e.tag.rsplit("}", 1)[-1] == "shape" and e.attrib.get("type") == "text":
            boxes.append((e, *(float(e.attrib[k]) for k in ["topLeftX", "topLeftY", "width", "height"])))
    overlaps = []
    for i, (_, x1, y1, w1, h1) in enumerate(boxes):
        for _, x2, y2, w2, h2 in boxes[i+1:]:
            ix, iy = max(0, min(x1+w1, x2+w2)-max(x1, x2)), max(0, min(y1+h1, y2+h2)-max(y1, y2))
            if ix*iy > 0.01: overlaps.append([x1, y1, w1, h1, x2, y2, w2, h2])
    check("no_text_text_overlap", not overlaps, overlaps)
    check("three_comparison_rows", len([e for e in data.iter() if e.tag.rsplit("}", 1)[-1] == "tr"]) == 4)
    for cid in ["full_mechanism_minus_rcs_only", "rcs_only_minus_intrinsic", "full_mechanism_minus_outer_train_mean"]:
        row = prod["exploratory_comparisons"][cid]
        for value in [fmt(row["delta_rmse"]), ci(row, "delta_rmse"), pfmt(row["holm_p_rmse"])]:
            check(f"visible_{cid}_{value}", value in texts, value)
    check("mean_spearman_not_inferential", "descriptive only" in texts)
    check("scientific_boundaries_visible", all(s in texts for s in ["DEV_NO_GO_TEST_UNTOUCHED", "no test / transport / generator", "纯外部模型与常数速度臂仍未闭合", "rcs_only 含 intrinsic"]))
    check("git_commit_visible", a.git_commit[:10] in texts)
    check("speaker_notes_present", any(e.tag.rsplit("}", 1)[-1] == "note" for e in parsed))
    report = {"status": "PASS", "candidate_sha256": sha(out), "baseline_xml_sha256": sha(a.baseline_xml),
              "baseline_slide_count": len(pages), "baseline_revision_id": base_response.get("data", {}).get("revision_id"),
              "baseline_last_slide_id": pages[-1].attrib.get("id"), "git_commit": a.git_commit,
              "production_sha256": sha(a.production), "independent_sha256": sha(a.independent), "checks": checks}
    Path(a.report).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "PASS", "candidate_sha256": report["candidate_sha256"], "checks": len(checks),
                      "baseline_slides": len(pages), "baseline_revision": report["baseline_revision_id"]}, indent=2))


if __name__ == "__main__": main()
