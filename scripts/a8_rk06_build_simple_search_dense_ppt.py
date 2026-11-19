#!/usr/bin/env python3
"""Build and preflight one RK06 slide from frozen, independently verified claims."""
import argparse, hashlib, json, math, re
from pathlib import Path
import xml.etree.ElementTree as ET

NS = "https://www.larkoffice.com/sml/2.0"
ET.register_namespace("", NS)
MARKER = "RK06 · UNIQUE18 REAL DENSE-BUDGET SEARCH"
METHODS = ["uniform", "hill_climbing", "mh_annealing", "areuredi_style"]
SHORT = {"uniform": "Uniform", "hill_climbing": "Hill", "mh_annealing": "MH", "areuredi_style": "AreuRedi"}

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
    for i, line_value in enumerate(str(value).split("\n")):
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
def p_fmt(v):
    v = float(v)
    return "0" if v == 0 else f"{v:.3g}"
def visible_text(elem):
    return "\n".join("".join(p.itertext()) for p in elem.iter() if p.tag.rsplit("}", 1)[-1] == "p")
def all_checks_pass(report):
    checks = report.get("checks")
    return report.get("overall_pass") is True and isinstance(checks, list) and bool(checks) and all(c.get("pass") is True for c in checks)

def build_slide(claims, finalization, paper, commit, ind_count, final_count, paper_count):
    method_summary = {row["method"]: row for row in claims["method_summary"]}
    slide = E("slide")
    style = S(slide, "style"); fill(style, "rgba(248, 250, 252, 1)")
    data = S(slide, "data")
    card(data, 712, 24, 192, 30, "rgba(220, 252, 231, 1)", "rgba(220, 252, 231, 1)")
    text(data, 720, 29, 176, 20, f"IND {ind_count}/{ind_count} · FINAL {final_count}/{final_count}", 10,
         "rgba(21, 128, 61, 1)", True, "center", False, "multiple:1", "caption")
    text(data, 56, 25, 640, 20, MARKER, 10, "rgba(37, 99, 235, 1)", True, "left", False, "multiple:1", "caption")
    text(data, 56, 56, 848, 34, "unique18 真实逐预算搜索证据已闭合", 25, "rgba(15, 23, 42, 1)", True,
         "left", False, "multiple:1", "headline")
    text(data, 56, 94, 848, 40,
         "18 records × 3 seeds × 4 methods × B=1…500 · 108,000 unique synonymous scorer calls\n"
         "Dense AUC = mean HV at B=1…499 · B500 endpoint only · calibration-scaled HV is unclipped", 11,
         "rgba(71, 85, 105, 1)", False, "left", True, "multiple:1.2")

    xs = [56, 344, 632]
    labels = ["FROZEN PRODUCTION", "REAL SCORER BUDGET", "PAIRED INFERENCE"]
    values = ["216 runs", "108,000 calls", "6 primary tests"]
    subs = ["18 records · 3 seeds · 4 methods", "unique synonymous evaluations", "Holm · 20,000 + 20,000 resamples"]
    for x, label, value, sub in zip(xs, labels, values, subs):
        card(data, x, 142, 272, 90, "rgba(239, 246, 255, 1)", "rgba(147, 197, 253, 1)")
        text(data, x+16, 152, 240, 18, label, 10, "rgba(71, 85, 105, 1)", True, "left", True, "multiple:1", "caption")
        text(data, x+16, 174, 240, 31, value, 22, "rgba(30, 64, 175, 1)", True, "left", False, "multiple:1", "headline")
        text(data, x+16, 210, 240, 15, sub, 9, "rgba(100, 116, 139, 1)", False, "left", True, "multiple:1", "caption")

    text(data, 56, 248, 600, 18, "SIX PRIMARY PAIRED TESTS · NON-UNIFORM MINUS UNIFORM · UNIT = RECORD (N=18)", 9,
         "rgba(71, 85, 105, 1)", True, "left", True, "multiple:1", "caption")
    table = S(data, "table", topLeftX=56, topLeftY=272, width=600, height=154)
    cg = S(table, "colgroup")
    for w in [90, 80, 82, 142, 80, 126]: S(cg, "col", width=w)
    headers = ["Search", "Endpoint", "Δ", "95% paired CI", "Holm p", "Proxy gate"]
    tr = S(table, "tr", height=22)
    for h in headers:
        td = S(tr, "td"); fill(td, "rgba(30, 64, 175, 1)")
        c = S(td, "content", fontSize=8, fontFamily="思源黑体", color="rgba(255, 255, 255, 1)", bold="true", lineSpacing="multiple:1", textAlign="center")
        p = S(c, "p"); p.text = h
    supported = 0
    for t in claims["primary_tests"]:
        tr = S(table, "tr", height=22)
        passed = bool(t["supported_advantage"])
        supported += int(passed)
        values = [SHORT[t["method"]], "dense AUC" if t["endpoint"] == "dense_budget_step_auc_v2" else "HV@500",
                  fmt(t["effect"]), f"[{fmt(t['ci95'][0])}, {fmt(t['ci95'][1])}]", p_fmt(t["holm_p"]),
                  "SUPPORTED" if passed else "NOT SUPPORTED"]
        for j, value in enumerate(values):
            td = S(tr, "td")
            color = "rgba(21, 128, 61, 1)" if j == 5 and passed else ("rgba(154, 52, 18, 1)" if j == 5 else "rgba(71, 85, 105, 1)")
            c = S(td, "content", fontSize=8, fontFamily="思源黑体", color=color, bold=str(j == 5).lower(), lineSpacing="multiple:1", textAlign="left" if j == 0 else "center")
            p = S(c, "p"); p.text = str(value)

    card(data, 672, 248, 232, 184, "rgba(239, 246, 255, 1)", "rgba(147, 197, 253, 1)")
    text(data, 688, 259, 200, 18, "SEED-AVERAGED METHOD MEANS", 9, "rgba(71, 85, 105, 1)", True, "left", True, "multiple:1", "caption")
    lines = []
    for m in METHODS:
        r = method_summary[m]
        lines.append(f"{SHORT[m]}  AUC {fmt(r['mean_dense_auc'])}")
        lines.append(f"  HV500 {fmt(r['mean_hv_B500'])}")
    lines += ["Δ = method − uniform", "paired across the same records", "AUC excludes B500 · HV unclipped"]
    text(data, 688, 284, 200, 136, "\n".join(lines), 8, "rgba(71, 85, 105, 1)", False, "left", True, "multiple:1.2")

    card(data, 56, 440, 410, 40, "rgba(239, 246, 255, 1)", "rgba(239, 246, 255, 1)")
    conclusion = (f"结果 · {supported}/6 proxy comparisons supported on unique18 development" if supported else
                  "结果 · 0/6 non-uniform advantages supported；负结果保留")
    text(data, 70, 446, 382, 28, conclusion + "\n真实 B=1…500 曲线完整 · external dense AUC 仍为 null", 10,
         "rgba(30, 64, 175, 1)", False, "left", True, "multiple:1.2")
    card(data, 486, 440, 418, 40, "rgba(255, 247, 237, 1)", "rgba(255, 247, 237, 1)")
    text(data, 500, 446, 390, 28,
         "边界 · Proxy-only · 未访问 expression / untouched · 未训练生成器\n非 SOTA / RK-G1 结论 · manuscript 仍不可提交", 10,
         "rgba(154, 52, 18, 1)", False, "left", True, "multiple:1.2")
    text(data, 56, 496, 700, 18,
         f"Evidence: production 216/216 · independent {ind_count}/{ind_count} · final {final_count}/{final_count} · paper {paper_count}/{paper_count} · GitHub {commit[:10]}",
         8, "rgba(100, 116, 139, 1)", False, "left", True, "multiple:1", "caption")
    text(data, 776, 496, 128, 18, "RK06 · 2026-11-20", 9, "rgba(100, 116, 139, 1)", False, "right", False, "multiple:1", "caption")

    note = S(slide, "note"); nc = S(note, "content")
    paragraphs = [
        "本页只报告 unique18 开发集上的真实 dense-budget 简单搜索证据。冻结设计为 18 records × 3 seeds × 4 methods × B=1…500，共 216 runs 和 108,000 次唯一同义 proxy-scorer 调用。dense AUC 使用 B=1…499 的 HV 算术平均，B500 只作端点；normalized HV 使用冻结 calibration reference/scale，且不截断到 [0,1]。",
        "四方法的 seed-averaged means：" + "；".join(f"{SHORT[m]} dense AUC={method_summary[m]['mean_dense_auc']!r}, HV500={method_summary[m]['mean_hv_B500']!r}" for m in METHODS) + "。",
        "六个 primary paired tests（非 uniform 减 uniform；先对三 seed 取算术平均，再以 record 为配对单位）：" + "；".join(
            f"{t['method']} / {t['endpoint']}: effect={t['effect']!r}, 95% CI=[{t['ci95'][0]!r}, {t['ci95'][1]!r}], Holm p={t['holm_p']!r}" for t in claims["primary_tests"]) + "。",
        f"正式 production 为 216/216 runs；独立复核 {ind_count}/{ind_count} PASS，finalization {final_count}/{final_count} PASS，论文精确增量与事实核验 {paper_count}/{paper_count} PASS。科学代码与论文提交为 {commit}。",
        "外部 LinearDesign/EnsembleDesign 输出是乱序 actual sets，dense budget-step AUC 仍为 null，不能用插值或零填充伪造。当前结果只描述固定 proxy 下的开发集搜索行为，不是表达适应度、湿实验或 SOTA 证据；未访问 untouched/功能标签，未训练生成器，不关闭 RK-G1，也不使 manuscript 可提交。"
    ]
    for paragraph in paragraphs:
        p = S(nc, "p"); p.text = paragraph
    return slide, supported

def main():
    ap = argparse.ArgumentParser()
    for name in ["claims", "finalization", "independent", "paper-verification", "baseline-xml", "baseline-response", "output", "report"]:
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--git-commit", required=True)
    a = ap.parse_args()
    claims, final, independent, paper = load(a.claims), load(a.finalization), load(a.independent), load(a.paper_verification)
    if not all_checks_pass(final) or not all_checks_pass(independent) or not all_checks_pass(paper):
        raise SystemExit("Refusing PPT: finalization/independent/paper verification has a failed or missing check")
    if not claims.get("finalization_overall_pass") or claims.get("finalization_sha256") != sha(a.finalization):
        raise SystemExit("Refusing PPT: claims do not bind the passing finalization")
    if not all(f.get("pass") is True for f in paper.get("candidate_facts", [])):
        raise SystemExit("Refusing PPT: paper candidate facts are not all passing")
    if not re.fullmatch(r"[0-9a-f]{40}", a.git_commit): raise SystemExit("Invalid Git commit")
    base_response = load(a.baseline_response)
    if not base_response.get("ok"): raise SystemExit("Baseline response is not ok")
    parser = ET.XMLParser()
    root = ET.parse(a.baseline_xml, parser=parser).getroot()
    if root.tag.rsplit("}", 1)[-1] != "presentation": raise SystemExit("Baseline is not a presentation")
    pages = [e for e in list(root) if e.tag.rsplit("}", 1)[-1] == "slide"]
    existing = visible_text(root)
    if MARKER in existing: raise SystemExit("Refusing duplicate RK06 page")
    ind_total = independent["check_counts"]["total"]
    final_total = final["check_counts"]["total"]
    paper_total = len(paper["checks"]) + len(paper.get("candidate_facts", []))
    slide, supported = build_slide(claims, final, paper, a.git_commit, ind_total, final_total, paper_total)
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
    check("single_slide_without_presentation_wrapper", parsed.tag == f"{{{NS}}}slide")
    check("no_preassigned_ids", all("id" not in e.attrib for e in parsed.iter()))
    check("no_external_images_or_embeds", all(e.tag.rsplit("}", 1)[-1] not in {"img", "embed", "undefined"} for e in parsed.iter()))
    check("single_marker", visible_text(parsed).count(MARKER) == 1)
    bounds = []
    for e in data:
        kind = e.tag.rsplit("}", 1)[-1]
        if kind not in {"shape", "table", "line", "img", "icon"}: continue
        if kind == "line": continue
        x, y, w, h = (float(e.attrib[k]) for k in ["topLeftX", "topLeftY", "width", "height"])
        inside = x >= 0 and y >= 0 and x + w <= 960 and y + h <= 540
        bounds.append({"kind": kind, "x": x, "y": y, "w": w, "h": h, "inside": inside})
    check("all_elements_inside_canvas", all(b["inside"] for b in bounds), bounds)
    boxes = []
    for e in data:
        if e.tag.rsplit("}", 1)[-1] == "shape" and e.attrib.get("type") == "text":
            boxes.append((e, *(float(e.attrib[k]) for k in ["topLeftX", "topLeftY", "width", "height"])))
    overlaps = []
    for i, (_, x1, y1, w1, h1) in enumerate(boxes):
        for _, x2, y2, w2, h2 in boxes[i+1:]:
            ix, iy = max(0, min(x1+w1, x2+w2)-max(x1, x2)), max(0, min(y1+h1, y2+h2)-max(y1, y2))
            if ix * iy > 0.01: overlaps.append([x1, y1, w1, h1, x2, y2, w2, h2])
    check("no_text_text_overlap", not overlaps, overlaps)
    check("six_primary_rows", len([e for e in data.iter() if e.tag.rsplit("}", 1)[-1] == "tr"]) == 7)
    for row in claims["method_summary"]:
        check(f"visible_{row['method']}_mean_dense_auc", fmt(row["mean_dense_auc"]) in texts)
        check(f"visible_{row['method']}_mean_hv_B500", fmt(row["mean_hv_B500"]) in texts)
    for t in claims["primary_tests"]:
        expected_support = float(t["effect"]) > 0 and float(t["ci95"][0]) > 0 and float(t["holm_p"]) < 0.05
        check(f"frozen_gate_{t['method']}_{t['endpoint']}", bool(t["supported_advantage"]) == expected_support)
        for label, value in [("effect", fmt(t["effect"])), ("ci_low", fmt(t["ci95"][0])), ("ci_high", fmt(t["ci95"][1])), ("holm_p", p_fmt(t["holm_p"]))]:
            check(f"visible_{t['method']}_{t['endpoint']}_{label}", value in texts, value)
    check("negative_or_positive_gate_count_exact", str(supported) + "/6" in texts)
    check("dense_scope_visible", all(s in texts for s in ["B=1…499", "B500 endpoint only", "unclipped", "external dense AUC 仍为 null"]))
    check("boundaries_visible", all(s in texts for s in ["Proxy-only", "未训练生成器", "manuscript 仍不可提交"]))
    check("git_commit_visible", a.git_commit[:10] in texts)
    check("speaker_notes_present", any(e.tag.rsplit("}", 1)[-1] == "note" for e in parsed))
    report = {"status": "PASS", "candidate_sha256": sha(out), "baseline_xml_sha256": sha(a.baseline_xml),
              "baseline_slide_count": len(pages), "baseline_revision_id": base_response.get("data", {}).get("revision_id"),
              "baseline_last_slide_id": pages[-1].attrib.get("id"), "git_commit": a.git_commit,
              "supported_proxy_comparisons": supported, "claims_sha256": sha(a.claims),
              "finalization_sha256": sha(a.finalization), "independent_sha256": sha(a.independent),
              "paper_verification_sha256": sha(a.paper_verification),
              "checks": checks}
    Path(a.report).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "candidate_sha256": report["candidate_sha256"], "checks": len(checks),
                      "baseline_slides": len(pages), "baseline_revision": report["baseline_revision_id"],
                      "supported_proxy_comparisons": supported}, indent=2))

if __name__ == "__main__": main()
