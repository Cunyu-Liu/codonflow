#!/usr/bin/env python3
"""Generate three offline RK-13 slide candidates from finalized evidence only."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

NS = "https://www.larkoffice.com/sml/2.0"
FONT = "思源黑体"
INK = "rgba(15, 23, 42, 1)"
BODY = "rgba(71, 85, 105, 1)"
MUTED = "rgba(100, 116, 139, 1)"
BLUE = "rgba(30, 64, 175, 1)"
GREEN = "rgba(21, 128, 61, 1)"
ORANGE = "rgba(154, 52, 18, 1)"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(x, y, w, h, lines, size=10, color=BODY, bold=False, align="left", wrap=True, spacing=1.2, text_type="body"):
    if isinstance(lines, str):
        lines = [lines]
    paragraphs = "".join(f"<p>{escape(str(line))}</p>" for line in lines)
    return (f'<shape type="text" topLeftX="{x}" topLeftY="{y}" width="{w}" height="{h}">'
            f'<content textType="{text_type}" fontSize="{size}" fontFamily="{FONT}" color="{color}" bold="{str(bold).lower()}" textAlign="{align}" wrap="{str(wrap).lower()}" lineSpacing="multiple:{spacing}">'
            f'{paragraphs}</content></shape>')


def card(x, y, w, h, fill="rgba(255, 255, 255, 1)", border="rgba(226, 232, 240, 1)"):
    return (f'<shape type="round-rect" topLeftX="{x}" topLeftY="{y}" width="{w}" height="{h}" presetHandlers="12">'
            f'<fill><fillColor color="{fill}"/></fill><border color="{border}" width="1"/></shape>')


def badge(label, value):
    return "".join([card(736, 24, 168, 30, "rgba(220, 252, 231, 1)", "rgba(220, 252, 231, 1)"),
                    text(744, 29, 152, 20, value, 10, GREEN, True, "center", False, 1.0, "caption"),
                    text(56, 25, 660, 20, label, 10, "rgba(37, 99, 235, 1)", True, "left", False, 1.0, "caption")])


def kpi(x, label, value, note, green=False):
    fill = "rgba(240, 253, 244, 1)" if green else "rgba(239, 246, 255, 1)"
    border = "rgba(134, 239, 172, 1)" if green else "rgba(147, 197, 253, 1)"
    color = GREEN if green else BLUE
    return "".join([card(x, 142, 272, 90, fill, border),
                    text(x + 16, 152, 240, 18, label, 10, BODY, True, "left", True, 1.0, "caption"),
                    text(x + 16, 174, 240, 31, value, 22, color, True, "left", False, 1.0, "headline"),
                    text(x + 16, 210, 240, 15, note, 9, MUTED, False, "left", True, 1.0, "caption")])


def table(x, y, widths, rows, row_heights=None, font_size=9):
    if row_heights is None:
        row_heights = [26] + [28] * (len(rows) - 1)
    assert len(rows) == len(row_heights)
    out = [f'<table topLeftX="{x}" topLeftY="{y}" width="{sum(widths)}" height="{sum(row_heights)}"><colgroup>']
    out.extend(f'<col width="{w}"/>' for w in widths)
    out.append('</colgroup>')
    for r, (row, height) in enumerate(zip(rows, row_heights)):
        out.append(f'<tr height="{height}">')
        for c, value in enumerate(row):
            header = r == 0
            fill = "rgba(30, 64, 175, 1)" if header else ("rgba(239, 246, 255, 1)" if r == len(rows) - 1 and str(row[0]).startswith("Verification") else None)
            color = "rgba(255, 255, 255, 1)" if header else (BLUE if fill else BODY)
            align = "left" if c == 0 else "center"
            out.append('<td>')
            if fill:
                out.append(f'<fill><fillColor color="{fill}"/></fill>')
            out.append(f'<content textType="body" fontSize="{font_size}" fontFamily="{FONT}" color="{color}" bold="{str(header or bool(fill)).lower()}" textAlign="{align}" lineSpacing="multiple:1.0"><p>{escape(str(value))}</p></content></td>')
        out.append('</tr>')
    out.append('</table>')
    return "".join(out)


def bottom_cards(conclusion, boundary):
    return "".join([card(56, 436, 410, 44, "rgba(239, 246, 255, 1)", "rgba(239, 246, 255, 1)"),
                    text(70, 443, 382, 31, conclusion, 10, BLUE, False, "left", True, 1.2),
                    card(486, 436, 418, 44, "rgba(255, 247, 237, 1)", "rgba(255, 247, 237, 1)"),
                    text(500, 443, 390, 31, boundary, 10, ORANGE, False, "left", True, 1.2)])


def slide(content, notes):
    note_xml = "".join(f"<p>{escape(note)}</p>" for note in notes)
    return (f'<slide xmlns="{NS}"><style><fill><fillColor color="rgba(248, 250, 252, 1)"/></fill></style>'
            f'<data>{content}</data><note><content textType="body">{note_xml}</content></note></slide>\n')


def footer(evidence):
    return "".join([text(56, 496, 700, 18, evidence, 9, MUTED, False, "left", True, 1.0, "caption"),
                    text(776, 496, 128, 18, "RK13 · 2026-11-19", 9, MUTED, False, "right", False, 1.0, "caption")])


def fmt_signed(value):
    return f"{value:+.6f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalization", type=Path, required=True)
    parser.add_argument("--ensemble", type=Path, required=True)
    parser.add_argument("--ensemble-independent", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--matrix-independent", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate-report", type=Path, required=True)
    args = parser.parse_args()
    if args.candidate_report.exists():
        raise FileExistsError(args.candidate_report)
    final = json.loads(args.finalization.read_text())
    ensemble = json.loads(args.ensemble.read_text())
    ensemble_ind = json.loads(args.ensemble_independent.read_text())
    matrix = json.loads(args.matrix.read_text())
    matrix_ind = json.loads(args.matrix_independent.read_text())
    if not final["status"].startswith("PASS_") or final["checks_passed"] != final["checks_total"]:
        raise ValueError("RK-13 finalization has not passed")
    for key, path in (("ensemble_sha256", args.ensemble), ("ensemble_independent_sha256", args.ensemble_independent), ("matrix_sha256", args.matrix), ("matrix_independent_sha256", args.matrix_independent)):
        if final[key] != sha256(path):
            raise ValueError(f"evidence hash mismatch: {key}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    record_pairs = sum(r["unique_output_sequences"] for r in ensemble["records"])
    seconds = ensemble["total_generation_elapsed_s"]
    max_efe = ensemble_ind["max_efe_abs_delta_from_rounded_official"]
    short_commit = matrix["scorer_code_commit"][:8]
    verification_badge = f"{matrix_ind['checks_passed']}/{matrix_ind['checks_total']} · INDEPENDENT"

    content96 = "".join([
        badge("RK13 · OFFICIAL ENSEMBLEDESIGN UNIQUE18", "RAW FILES · VERIFIED"),
        text(56, 51, 848, 39, "198 次官方生成完成 18 × 11 runs", 25, INK, True, "left", False, 1.0, "headline"),
        text(56, 94, 848, 40, ["fixed cd9324f9 · four internal threads · raw stdout/stderr retained", "beam 100 · lr 0.03 · epsilon 0.5 · three iterations"], 11, BODY),
        kpi(56, "GENERATOR RUNS", str(ensemble["run_count"]), "18 proteins × 11 independent runs"),
        kpi(344, "UNIQUE RECORD–SEQUENCE PAIRS", str(record_pairs), "within-record deduplication"),
        kpi(632, "GENERATION WALL CLOCK", f"{seconds:.3f} s", f"{seconds / 60:.1f} min · scoring excluded", True),
        text(56, 253, 544, 18, "RAW-OUTPUT RECOMPUTE + ACCEPTANCE", 9, BODY, True, "left", True, 1.0, "caption"),
        table(56, 280, [178, 174, 192], [
            ["Check", "Scale", "Observed"],
            ["Official runs", "18 × 11", f"{ensemble['run_count']}/198 complete"],
            ["Protein identity", "all official outputs", "198/198"],
            ["Independent EFE", "ViennaRNA raw CDS", f"max |Δ| {max_efe:.6g}"],
            ["Source + payload", "fixed official commit", "unmodified · verified"],
            ["Verification", "science finalization", f"{final['checks_passed']}/{final['checks_total']} PASS"],
        ], [24, 24, 24, 24, 24, 22], 9),
        card(632, 252, 272, 170),
        text(648, 263, 240, 18, "MEASURED CONTRACT", 9, BODY, True, "left", True, 1.0, "caption"),
        text(648, 290, 240, 110, ["official CPU implementation", "TAA appended only for evaluation", "11 runs are not scorer budgets", "dense budget-step AUC = null", "EFE is not LinearDesign MFE"], 9, BLUE),
        bottom_cards(["结论 · 官方生成与原始文件核验已闭合", f"{record_pairs} 个唯一记录–序列对 · identity = 1.000"], ["边界 · 不是主模型或 SOTA 证据", "dense AUC、功能、OOD 与等时间比较未闭合"]),
        footer(f"Evidence: raw independent PASS + finalization {final['checks_passed']}/{final['checks_total']} · GitHub {short_commit}"),
    ])
    notes96 = [
        f"这一页记录固定来源 EnsembleDesign 在 unique18 上的正式生成，共 {ensemble['run_count']} 个 generator runs。",
        f"记录内去重后形成 {record_pairs} 个唯一记录–序列对，官方端到端生成 wall-clock 合计 {seconds:.3f} 秒。",
        f"独立核验从原始 CDS 重算 EFE，最大差为 {max_efe:.6g} kcal/mol，所有输出保持蛋白身份。",
        "十一次独立运行不是连续 scorer budget，因此不构造 dense budget-step AUC，也不作功能或 SOTA 结论。",
    ]

    display = {"lineardesign_lambda11": "LinearDesign-11", "ensembledesign_11run": "EnsembleDesign-11", "gemorna": "GEMORNA", "codongpt": "codonGPT", "cai_greedy": "CAI-greedy", "uniform_synonymous": "Uniform", "lineardesign_scan": "LD-scan (secondary)"}
    method_order = list(display)
    summary = matrix["method_summary"]
    method_rows = [["Method", "Outputs", "Mean HV", "Mean NED"]]
    for name in method_order:
        item = summary[name]
        method_rows.append([display[name], item["total_actual_outputs"], f"{item['mean_hypervolume_normalized']:.6f}", f"{item['mean_ned']:.6f}"])
    hv_items = [item for item in matrix["primary_comparisons"].values() if item["metric"] == "hypervolume_normalized"]
    ned_items = [item for item in matrix["primary_comparisons"].values() if item["metric"] == "ned"]
    def comparison_rows(items):
        rows = [["Comparator", "Metric", "Effect", "95% CI", "Holm p"]]
        for item in items:
            rows.append([display[item["comparator"]], "HV" if item["metric"] == "hypervolume_normalized" else "NED", fmt_signed(item["mean_effect"]), f"[{fmt_signed(item['ci95'][0])}, {fmt_signed(item['ci95'][1])}]", f"{item['holm_p_twelve_primary']:.4g}"])
        return rows
    significant_hv = [item for item in hv_items if item["ci_excludes_zero"] and item["holm_p_twelve_primary"] < 0.05]
    significant_ned = [item for item in ned_items if item["ci_excludes_zero"] and item["holm_p_twelve_primary"] < 0.05]
    highest = matrix["descriptive_highest_mean_hv_method"]
    direct = matrix["primary_comparisons"]["lineardesign_lambda11_minus_ensembledesign_11run:hypervolume_normalized"]
    content97 = "".join([
        badge("RK13 · SEVEN-METHOD SHARED-SCORER MATRIX", verification_badge),
        text(56, 51, 848, 39, "七方法实际集合：HV 配对效应与区间", 25, INK, True, "left", False, 1.0, "headline"),
        text(56, 94, 848, 40, ["18 development records · raw CDS rescore · six legacy fields preserved exactly", "20,000 paired bootstraps · percentile 95% CI · Holm across 12 tests"], 11, BODY),
        text(56, 142, 400, 18, "ACTUAL-SET SUMMARY · DESCRIPTIVE", 9, BODY, True, "left", True, 1.0, "caption"),
        table(56, 168, [166, 70, 90, 82], method_rows, [26] + [28] * 7, 9),
        text(488, 142, 416, 18, "LINEARDESIGN − COMPARATOR · HV", 9, BODY, True, "left", True, 1.0, "caption"),
        table(488, 168, [80, 50, 72, 152, 62], comparison_rows(hv_items), [26] + [34] * 6, 8),
        text(56, 402, 848, 22, f"直接对比 EnsembleDesign：ΔHV {fmt_signed(direct['mean_effect'])} · 95% CI [{fmt_signed(direct['ci95'][0])}, {fmt_signed(direct['ci95'][1])}] · Holm p={direct['holm_p_twelve_primary']:.4g} · 描述性最高 mean HV：{display[highest]}", 9, BLUE, True),
        bottom_cards(["结论 · 六项 HV 主比较已冻结并独立重算", f"{len(significant_hv)}/6 项 CI 排除零且 Holm p<0.05"], ["边界 · 描述性最高不等于 SOTA", "没有 CodonFlow-RK 主模型、dense AUC 或功能 OOD"]),
        footer(f"Evidence: {verification_badge} + finalization {final['checks_passed']}/{final['checks_total']} · A8 v22 · GitHub {short_commit}"),
    ])
    notes97 = [
        "这一页把 EnsembleDesign 加入既有六方法 actual-set 矩阵，旧六方法字段逐字继承，新列从原始 CDS 独立重算。",
        f"直接比较 LinearDesign 与 EnsembleDesign 的 HV 效应为 {direct['mean_effect']:.6f}，95% CI 为 [{direct['ci95'][0]:.6f}, {direct['ci95'][1]:.6f}]。",
        f"六项 HV 比较中，{len(significant_hv)} 项的区间排除零且 Holm 校正后 p 小于 0.05；描述性最高 mean HV 为 {display[highest]}。",
        "这些结果是 eighteen 条 development records 上的实际输出集合比较，不包含 CodonFlow-RK 主模型，因此不作 SOTA 结论。",
    ]

    costs = matrix["generation_cost_descriptive_not_time_matched"]
    ld_seconds = costs["lineardesign_lambda11"]["total_seconds"]
    ensemble_scoring = matrix["reanalysis_elapsed_s_not_generation_cost"]
    content98 = "".join([
        badge("RK13 · DIVERSITY, COST + SCIENTIFIC BOUNDARY", verification_badge),
        text(56, 51, 848, 39, "NED 与成本分开报告，避免过度解读", 25, INK, True, "left", False, 1.0, "headline"),
        text(56, 94, 848, 40, ["NED = sequence diversity · negative effects are not performance losses", "generation and scorer costs use their actual worker/thread configurations"], 11, BODY),
        text(56, 142, 460, 18, "LINEARDESIGN − COMPARATOR · NED", 9, BODY, True, "left", True, 1.0, "caption"),
        table(56, 168, [80, 50, 72, 152, 62], comparison_rows(ned_items), [26] + [34] * 6, 8),
        card(544, 142, 360, 142, "rgba(239, 246, 255, 1)", "rgba(147, 197, 253, 1)"),
        text(560, 154, 328, 18, "MEASURED COST · NOT TIME-MATCHED", 9, BODY, True, "left", True, 1.0, "caption"),
        text(560, 184, 328, 82, [f"LinearDesign-11 generation: {ld_seconds:.3f} s · 1 worker", f"EnsembleDesign generation: {seconds:.3f} s · 4 threads", f"New-column shared scoring: {ensemble_scoring:.3f} s", "Hardware/parallelism/endpoints are not unified"], 9, BLUE),
        card(544, 300, 360, 122, "rgba(255, 247, 237, 1)", "rgba(253, 186, 116, 1)"),
        text(560, 312, 328, 18, "INTERPRETATION", 9, BODY, True, "left", True, 1.0, "caption"),
        text(560, 340, 328, 68, [f"NED significant after Holm: {len(significant_ned)}/6", "Positive effect = greater LinearDesign diversity", "No unified cost ranking or dense-budget AUC", "No main model, functional OOD or SOTA claim"], 9, ORANGE),
        bottom_cards(["结论 · 12 项 paired 效应、CI 与成本均可追溯", f"独立矩阵 {matrix_ind['checks_passed']}/{matrix_ind['checks_total']} PASS · finalization {final['checks_passed']}/{final['checks_total']} PASS"], ["边界 · 强 baseline 矩阵仍不是完整论文闭环", "主模型、真实 budget、time-matched、OOD 仍待完成"]),
        footer(f"Evidence: 12 frozen tests + exact legacy preservation + {verification_badge} · A8 v22 · GitHub {short_commit}"),
    ])
    notes98 = [
        "这一页单独报告 NED 多样性效应，避免把数值更低误解为功能更好或更差。",
        f"六项 NED 比较中，{len(significant_ned)} 项在 Holm 校正后显著；正效应仅表示 LinearDesign 集合多样性更高。",
        f"LinearDesign 官方生成总耗时 {ld_seconds:.3f} 秒，EnsembleDesign 为 {seconds:.3f} 秒，但二者 worker、线程和内部实现不同，不能作等时间性能排名。",
        "七方法矩阵补齐了直接 CDS 多目标 baseline，但主模型、dense budget、统一 time-matched 成本和功能 OOD 仍未闭合。",
    ]

    pages = [(96, "rk13-slide96-candidate.xml", content96, notes96, "198 次官方生成完成 18 × 11 runs"),
             (97, "rk13-slide97-candidate.xml", content97, notes97, "七方法实际集合：HV 配对效应与区间"),
             (98, "rk13-slide98-candidate.xml", content98, notes98, "NED 与成本分开报告，避免过度解读")]
    page_records = []
    for number, filename, content, notes, title in pages:
        path = args.output_dir / filename
        if path.exists():
            raise FileExistsError(path)
        path.write_text(slide(content, notes))
        page_records.append({"planned_page": number, "path": str(path), "sha256": sha256(path), "title": title})
    report = {"schema": "a8-rk13-ppt-candidates-v1", "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "status": "OFFLINE_CANDIDATES_ONLY_NOT_WRITTEN",
              "finalization_sha256": sha256(args.finalization), "ensemble_sha256": sha256(args.ensemble), "matrix_sha256": sha256(args.matrix), "pages": page_records,
              "significant_hv_comparisons": len(significant_hv), "significant_ned_comparisons": len(significant_ned), "descriptive_highest_mean_hv_method": highest, "sota_claim": False}
    args.candidate_report.parent.mkdir(parents=True, exist_ok=True)
    args.candidate_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
