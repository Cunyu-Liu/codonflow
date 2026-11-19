#!/usr/bin/env python3
"""Generate two offline RK-12 slide candidates from finalized evidence only."""
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
    return (
        f'<shape type="text" topLeftX="{x}" topLeftY="{y}" width="{w}" height="{h}">'
        f'<content textType="{text_type}" fontSize="{size}" fontFamily="{FONT}" color="{color}" '
        f'bold="{str(bold).lower()}" textAlign="{align}" wrap="{str(wrap).lower()}" lineSpacing="multiple:{spacing}">'
        f'{paragraphs}</content></shape>'
    )


def card(x, y, w, h, fill="rgba(255, 255, 255, 1)", border="rgba(226, 232, 240, 1)"):
    return (
        f'<shape type="round-rect" topLeftX="{x}" topLeftY="{y}" width="{w}" height="{h}" presetHandlers="12">'
        f'<fill><fillColor color="{fill}"/></fill><border color="{border}" width="1"/></shape>'
    )


def badge(label, value="35/35 · INDEPENDENT"):
    return "".join([
        card(736, 24, 168, 30, "rgba(220, 252, 231, 1)", "rgba(220, 252, 231, 1)"),
        text(744, 29, 152, 20, value, 10, GREEN, True, "center", False, 1.0, "caption"),
        text(56, 25, 660, 20, label, 10, "rgba(37, 99, 235, 1)", True, "left", False, 1.0, "caption"),
    ])


def kpi(x, label, value, note, green=False):
    fill = "rgba(240, 253, 244, 1)" if green else "rgba(239, 246, 255, 1)"
    border = "rgba(134, 239, 172, 1)" if green else "rgba(147, 197, 253, 1)"
    color = GREEN if green else BLUE
    return "".join([
        card(x, 142, 272, 90, fill, border),
        text(x + 16, 152, 240, 18, label, 10, BODY, True, "left", True, 1.0, "caption"),
        text(x + 16, 174, 240, 31, value, 22, color, True, "left", False, 1.0, "headline"),
        text(x + 16, 210, 240, 15, note, 9, MUTED, False, "left", True, 1.0, "caption"),
    ])


def table(x, y, widths, rows, row_heights=None, font_size=9, header_fill="rgba(30, 64, 175, 1)"):
    if row_heights is None:
        row_heights = [26] + [28] * (len(rows) - 1)
    assert len(rows) == len(row_heights)
    total_w = sum(widths)
    total_h = sum(row_heights)
    out = [f'<table topLeftX="{x}" topLeftY="{y}" width="{total_w}" height="{total_h}"><colgroup>']
    out.extend(f'<col width="{w}"/>' for w in widths)
    out.append('</colgroup>')
    for r, (row, height) in enumerate(zip(rows, row_heights)):
        out.append(f'<tr height="{height}">')
        for c, value in enumerate(row):
            header = r == 0
            fill = header_fill if header else ("rgba(239, 246, 255, 1)" if r == len(rows) - 1 and str(row[0]).startswith("Verification") else None)
            color = "rgba(255, 255, 255, 1)" if header else (BLUE if fill else BODY)
            align = "left" if c == 0 else "center"
            out.append('<td>')
            if fill:
                out.append(f'<fill><fillColor color="{fill}"/></fill>')
            out.append(
                f'<content textType="body" fontSize="{font_size}" fontFamily="{FONT}" color="{color}" '
                f'bold="{str(header or bool(fill)).lower()}" textAlign="{align}" lineSpacing="multiple:1.0">'
                f'<p>{escape(str(value))}</p></content></td>'
            )
        out.append('</tr>')
    out.append('</table>')
    return "".join(out)


def bottom_cards(conclusion, boundary):
    return "".join([
        card(56, 436, 410, 44, "rgba(239, 246, 255, 1)", "rgba(239, 246, 255, 1)"),
        text(70, 443, 382, 31, conclusion, 10, BLUE, False, "left", True, 1.2),
        card(486, 436, 418, 44, "rgba(255, 247, 237, 1)", "rgba(255, 247, 237, 1)"),
        text(500, 443, 390, 31, boundary, 10, ORANGE, False, "left", True, 1.2),
    ])


def slide(content, notes):
    note_xml = "".join(f"<p>{escape(note)}</p>" for note in notes)
    return (
        f'<slide xmlns="{NS}"><style><fill><fillColor color="rgba(248, 250, 252, 1)"/></fill></style>'
        f'<data>{content}</data><note><content textType="body">{note_xml}</content></note></slide>\n'
    )


def footer(evidence, short_commit):
    return "".join([
        text(56, 496, 700, 18, evidence, 9, MUTED, False, "left", True, 1.0, "caption"),
        text(776, 496, 128, 18, f"RK12 · 2026-11-19", 9, MUTED, False, "right", False, 1.0, "caption"),
    ])


def fmt_signed(value):
    return f"{value:+.6f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalization", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate-report", type=Path, required=True)
    args = parser.parse_args()
    if args.candidate_report.exists():
        raise FileExistsError(args.candidate_report)
    final = json.loads(args.finalization.read_text())
    matrix = json.loads(args.matrix.read_text())
    if not final["status"].startswith("PASS_") or final["checks_passed"] != final["checks_total"] == 15:
        raise ValueError("RK-12 finalization has not passed")
    if final["matrix_sha256"] != sha256(args.matrix):
        raise ValueError("matrix hash differs from finalization")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    grid_ind = final["checks"][1]["evidence"]
    matrix_ind = final["checks"][6]["evidence"]
    short_commit = matrix["scorer_code_commit"][:8]
    seconds = final["lineardesign_generation_seconds"]

    content91 = "".join([
        badge("RK12 · OFFICIAL LINEARDESIGN UNIQUE18 GRID", f"{grid_ind}/{grid_ind} · INDEPENDENT"),
        text(56, 51, 848, 39, "198 次官方进程完成 18 × 11 lambda 网格", 25, INK, True, "left", False, 1.0, "headline"),
        text(56, 94, 848, 40, ["fixed f0126ca8 · single worker · raw stdout/stderr retained", "official MFE/CAI · independent scoring timed separately"], 11, BODY),
        kpi(56, "OFFICIAL RUNS", str(final["run_count"]), f"{final['record_count']} records × 11 lambda values"),
        kpi(344, "UNIQUE RECORD–SEQUENCE PAIRS", str(final["unique_output_sequences_global"]), "deterministic C01 replay: 3/3 compatible"),
        kpi(632, "GENERATION WALL CLOCK", f"{seconds:.3f} s", f"single worker · {seconds / 60:.1f} min · scoring excluded", True),
        text(56, 253, 544, 18, "FROZEN ACCEPTANCE + RAW-OUTPUT RECOMPUTE", 9, BODY, True, "left", True, 1.0, "caption"),
        table(56, 280, [178, 174, 192], [
            ["Check", "Scale", "Observed"],
            ["Official grid", "18 × 11", f"{final['run_count']}/198 complete"],
            ["Protein identity", "all official outputs", "198/198"],
            ["Independent grid", "raw stdout + CAI/MFE", f"{grid_ind}/{grid_ind} PASS"],
            ["C01 compatibility", "3 overlapping lambda", "3/3 exact sequence"],
            ["Verification", "final + tests", f"15/15 · 10/10"],
        ], [24, 24, 24, 24, 24, 22], 9),
        card(632, 252, 272, 170),
        text(648, 263, 240, 18, "MEASURED CONTRACT", 9, BODY, True, "left", True, 1.0, "caption"),
        text(648, 290, 240, 110, [
            "official CPU binary · one worker",
            "TAA appended only for evaluation",
            "lambda is not a scorer budget",
            "dense budget-step AUC = null",
            f"finalization {final['checks_passed']}/{final['checks_total']} PASS",
        ], 9, BLUE),
        bottom_cards(
            ["结论 · 官方网格与成本已经闭合", f"{final['unique_output_sequences_global']} 个唯一记录–序列对 · 原始输出全保留"],
            ["边界 · 不是跨方法 SOTA 证据", "dense AUC 未构造 · untouched/功能/OOD 未评价"],
        ),
        footer(f"Evidence: {grid_ind}/{grid_ind} + 15/15 + tests 10/10 · GitHub {short_commit}", short_commit),
    ])
    notes91 = [
        f"这一页记录固定来源 LinearDesign 在 unique18 开发面板上的正式网格，共 {final['run_count']} 次官方 CPU 进程。",
        f"输出形成 {final['unique_output_sequences_global']} 个唯一记录–序列对，官方生成 wall-clock 合计 {seconds:.3f} 秒，独立评分时间单独记录。",
        f"独立网格核验 {grid_ind}/{grid_ind} 通过，三个重叠 C01 输出与早期 smoke 完全一致，finalization 为 15/15。",
        "lambda 是目标权重而不是真实 scorer 预算，因此本页不构造 dense budget-step AUC，也不作 SOTA 或生物功能结论。",
    ]

    method_order = ["lineardesign_lambda11", "gemorna", "codongpt", "cai_greedy", "uniform_synonymous", "lineardesign_scan"]
    display = {
        "lineardesign_lambda11": "LinearDesign-11",
        "gemorna": "GEMORNA",
        "codongpt": "codonGPT",
        "cai_greedy": "CAI-greedy",
        "uniform_synonymous": "Uniform",
        "lineardesign_scan": "LD-scan (secondary)",
    }
    summary = matrix["method_summary"]
    method_rows = [["Method", "Outputs", "Mean HV", "Mean NED"]]
    for name in method_order:
        item = summary[name]
        method_rows.append([display[name], item["total_actual_outputs"], f"{item['mean_hypervolume_normalized']:.6f}", f"{item['mean_ned']:.6f}"])
    comparisons = list(matrix["primary_comparisons"].values())
    comparison_rows = [["Comparator", "Metric", "Effect", "95% CI", "Holm p"]]
    for item in comparisons:
        comparison_rows.append([
            display[item["comparator"]],
            "HV" if item["metric"] == "hypervolume_normalized" else "NED",
            fmt_signed(item["mean_effect"]),
            f"[{fmt_signed(item['ci95'][0])}, {fmt_signed(item['ci95'][1])}]",
            f"{item['holm_p_four_primary']:.4g}",
        ])
    significant = [item for item in comparisons if item["ci_excludes_zero"] and item["holm_p_four_primary"] < 0.05]
    if significant:
        effect_conclusion = f"{len(significant)}/4 项 paired 效应经 Holm 后显著"
    else:
        effect_conclusion = "4 项 paired 效应均未形成校正后显著差异"
    highest = matrix["descriptive_highest_mean_hv_method"]
    content92 = "".join([
        badge("RK12 · SHARED-SCORER ACTUAL-SET MATRIX", f"{matrix_ind}/{matrix_ind} · INDEPENDENT"),
        text(56, 51, 848, 39, "同一 scorer 下，六方法实际集合完成配对比较", 25, INK, True, "left", False, 1.0, "headline"),
        text(56, 94, 848, 40, ["18 development records · raw CDS rescore · frozen calibration", "20,000 paired bootstraps · percentile 95% CI · Holm across 4 tests"], 11, BODY),
        text(56, 142, 400, 18, "ACTUAL-SET SUMMARY · DESCRIPTIVE", 9, BODY, True, "left", True, 1.0, "caption"),
        table(56, 168, [166, 70, 90, 82], method_rows, [26] + [28] * 6, 9),
        text(488, 142, 416, 18, "LINEARDESIGN − COMPARATOR · PAIRED EFFECTS", 9, BODY, True, "left", True, 1.0, "caption"),
        table(488, 168, [80, 50, 72, 152, 62], comparison_rows, [26] + [34] * 4, 8),
        card(488, 348, 416, 74, "rgba(239, 246, 255, 1)", "rgba(147, 197, 253, 1)"),
        text(504, 358, 384, 52, [
            effect_conclusion,
            f"描述性 mean HV 最高：{display[highest]}",
            "HV/NED：正效应表示 LinearDesign 数值更高",
        ], 9, BLUE),
        bottom_cards(
            ["结论 · 原始 CDS 目标与统计已独立重算", f"{matrix_ind}/{matrix_ind} PASS · identity minimum = 1.000"],
            ["边界 · 不是主模型或等时间排名", "dense/time-matched 未完成 · 非功能评价 · 非 SOTA"],
        ),
        footer(f"Evidence: {matrix_ind}/{matrix_ind} + 15/15 · A8 v18 · GitHub {short_commit}", short_commit),
    ])
    notes92 = [
        "这一页把新 LinearDesign 与五类 legacy 输出放到同一个冻结 scorer 下，所有目标均从原始 CDS 重算。",
        f"四项主比较采用 18 条记录的 20,000 次 paired bootstrap 和 Holm 校正；{effect_conclusion}。",
        f"描述性 mean normalized HV 最高的方法为 {display[highest]}，但这一描述不构成 SOTA 排名。",
        "旧方法成本并非同硬件、同并行度、同端到端口径；本页不包含 CodonFlow-RK 主模型、dense AUC、time-matched 或功能结论。",
    ]

    page91 = args.output_dir / "rk12-slide91-candidate.xml"
    page92 = args.output_dir / "rk12-slide92-candidate.xml"
    if page91.exists() or page92.exists():
        raise FileExistsError("refusing to overwrite slide candidates")
    page91.write_text(slide(content91, notes91))
    page92.write_text(slide(content92, notes92))
    report = {
        "schema": "a8-rk12-ppt-candidates-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "OFFLINE_CANDIDATES_ONLY_NOT_WRITTEN",
        "finalization_sha256": sha256(args.finalization),
        "matrix_sha256": sha256(args.matrix),
        "pages": [
            {"planned_page": 91, "path": str(page91), "sha256": sha256(page91), "title": "198 次官方进程完成 18 × 11 lambda 网格"},
            {"planned_page": 92, "path": str(page92), "sha256": sha256(page92), "title": "同一 scorer 下，六方法实际集合完成配对比较"},
        ],
        "effect_conclusion": effect_conclusion,
        "descriptive_highest_mean_hv_method": highest,
        "significant_primary_comparisons": len(significant),
        "sota_claim": False,
    }
    args.candidate_report.parent.mkdir(parents=True, exist_ok=True)
    args.candidate_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
