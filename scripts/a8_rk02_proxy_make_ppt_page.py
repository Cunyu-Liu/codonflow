#!/usr/bin/env python3
"""Generate the offline fixed-GFP observed-end proxy slide from finalized evidence."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from scripts.a8_rk12_make_ppt_pages import (
    badge, bottom_cards, card, kpi, sha256, slide, table, text,
    BODY, INK, MUTED, ORANGE,
)


def f3(value: float) -> str:
    return f"{value:+.3f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("primary", "primary-independent", "primary-finalization", "robustness", "robustness-independent", "robustness-finalization", "output", "candidate-report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.candidate_report.exists():
        raise FileExistsError("refusing to overwrite proxy PPT candidates")
    primary = json.loads(args.primary.read_text())
    primary_ind = json.loads(args.primary_independent.read_text())
    primary_final = json.loads(args.primary_finalization.read_text())
    robust = json.loads(args.robustness.read_text())
    robust_ind = json.loads(args.robustness_independent.read_text())
    robust_final = json.loads(args.robustness_finalization.read_text())
    if not (primary_ind["status"] == "PASS" and primary_ind["checks_total"] == primary_ind["checks_passed"] == 18):
        raise ValueError("primary independent gate is not 18/18 PASS")
    if not (primary_final["status"] == "PASS" and primary_final["checks_total"] == primary_final["checks_passed"] == 12):
        raise ValueError("primary finalization is not 12/12 PASS")
    if primary_final["production_sha256"] != sha256(args.primary) or primary_final["independent_sha256"] != sha256(args.primary_independent):
        raise ValueError("primary evidence hash mismatch")
    if not (robust_ind["status"] == "PASS" and robust_ind["checks_total"] == robust_ind["checks_passed"] == 8):
        raise ValueError("robustness independent gate is not 8/8 PASS")
    if not (robust_final["status"] == "PASS" and robust_final["checks_total"] == robust_final["checks_passed"] == 8):
        raise ValueError("robustness finalization is not 8/8 PASS")
    if robust_final["production_sha256"] != sha256(args.robustness) or robust_final["independent_sha256"] != sha256(args.robustness_independent):
        raise ValueError("robustness evidence hash mismatch")
    gc3 = primary["associations"]["gc3_observed_5prime"]
    gc = primary["associations"]["gc_observed_5prime"]
    cpg = primary["associations"]["cpg_per_100nt_observed_5prime"]["spearman"]
    support = robust["support_sensitivity"]
    threshold_text = f"support {support[0]['threshold']:,}–{support[-1]['threshold']:,} · n {support[0]['n']}→{support[-1]['n']}"
    range_lines = []
    positive_counts = {}
    for feature, label in (("gc3_observed_5prime", "GC3"), ("gc_observed_5prime", "GC")):
        values = [item["features"][feature]["observed"] for item in support]
        positive_counts[feature] = sum(item["features"][feature]["ci95_percentile"][0] > 0 for item in support)
        range_lines.append(f"{label} rho range {min(values):+.3f} to {max(values):+.3f} · {positive_counts[feature]}/7 CI > 0")
    partial = robust["partial_spearman_controlling_depth"]
    depth_score = robust["depth_associations"]["flowseq_score_r1_only"]
    content = "".join([
        badge("RK02 · FIXED-GFP OBSERVED-END PROXY", "18/18 + 8/8 · INDEPENDENT"),
        text(56, 51, 848, 39, "固定 GFP 观测端存在中等 GC/GC3 正相关", 25, INK, True, "left", False, 1.0, "headline"),
        text(56, 94, 848, 40, ["HEK293 · 8-bin weighted Flow-seq score · support at least 1,000", "20,000 bootstrap + 20,000 permutations · Holm across 2 primary tests"], 11, BODY),
        kpi(56, "GC3 · SPEARMAN", f3(gc3["spearman"]["observed"]), f"95% CI [{gc3['spearman']['ci95_percentile'][0]:.3f}, {gc3['spearman']['ci95_percentile'][1]:.3f}]"),
        kpi(344, "GC · SPEARMAN", f3(gc["spearman"]["observed"]), f"95% CI [{gc['spearman']['ci95_percentile'][0]:.3f}, {gc['spearman']['ci95_percentile'][1]:.3f}]"),
        kpi(632, "CpG · SECONDARY", f3(cpg["observed"]), f"95% CI [{cpg['ci95_percentile'][0]:.3f}, {cpg['ci95_percentile'][1]:.3f}] · unadjusted", True),
        text(56, 253, 544, 18, "PRIMARY ASSOCIATION · 152 RECOVERED R1 VARIANTS", 9, BODY, True, "left", True, 1.0, "caption"),
        table(56, 280, [100, 84, 150, 104, 106], [
            ["Feature", "Metric", "Observed", "95% CI", "Holm p"],
            ["GC3", "Spearman", f3(gc3["spearman"]["observed"]), f"[{gc3['spearman']['ci95_percentile'][0]:.3f}, {gc3['spearman']['ci95_percentile'][1]:.3f}]", f"{gc3['spearman']['holm_p']:.4g}"],
            ["GC3", "Pearson", f3(gc3["pearson"]["observed"]), f"[{gc3['pearson']['ci95_percentile'][0]:.3f}, {gc3['pearson']['ci95_percentile'][1]:.3f}]", "secondary"],
            ["GC", "Spearman", f3(gc["spearman"]["observed"]), f"[{gc['spearman']['ci95_percentile'][0]:.3f}, {gc['spearman']['ci95_percentile'][1]:.3f}]", f"{gc['spearman']['holm_p']:.4g}"],
            ["GC", "Pearson", f3(gc["pearson"]["observed"]), f"[{gc['pearson']['ci95_percentile'][0]:.3f}, {gc['pearson']['ci95_percentile'][1]:.3f}]", "secondary"],
            ["Verification", "primary + post-hoc", "18/18 + 8/8", "12/12 + 8/8 final", "PASS"],
        ], [24, 24, 24, 24, 24, 22], 8),
        card(632, 252, 272, 170, "rgba(239, 246, 255, 1)", "rgba(147, 197, 253, 1)"),
        text(648, 263, 240, 18, "POST-HOC ROBUSTNESS", 9, BODY, True, "left", True, 1.0, "caption"),
        text(648, 288, 240, 116, [
            threshold_text,
            *range_lines,
            f"depth–score {depth_score['observed']:+.3f} [{depth_score['ci95_percentile'][0]:.3f}, {depth_score['ci95_percentile'][1]:.3f}]",
            f"partial GC3 {partial['gc3_observed_5prime']['observed']:+.3f} · GC {partial['gc_observed_5prime']['observed']:+.3f}",
            "exploratory · not a new gate",
        ], 8, BODY),
        bottom_cards(
            ["结论 · 简单序列代理并非无信号", "固定 GFP 观测端关联成立 · 支持阈值/深度已复核"],
            ["边界 · 不等于机制增量或功能迁移", "非完整 CDS · 非蛋白 OOD · 非因果 · 非 SOTA"],
        ),
        text(56, 496, 700, 18, "Evidence: primary 18/18 + 12/12 · robustness 8/8 + 8/8 · observed CDS 4–303", 9, MUTED, False, "left", True, 1.0, "caption"),
        text(776, 496, 128, 18, "RK02 · 2026-11-19", 9, MUTED, False, "right", False, 1.0, "caption"),
    ])
    notes = [
        f"这一页只分析固定 GFP 的 152 个观测端 R1 变体。GC3 与 Flow-seq score 的 Spearman 相关为 {gc3['spearman']['observed']:.3f}，GC 为 {gc['spearman']['observed']:.3f}。",
        "两项主假设均使用 20,000 次变体 bootstrap 和 20,000 次标签置换，Holm 校正后显著，说明简单序列代理具有中等强度信号。",
        f"事后分析覆盖 7 个支持阈值；GC3/GC 分别有 {positive_counts['gc3_observed_5prime']}/7 和 {positive_counts['gc_observed_5prime']}/7 个阈值的 CI 下界大于 0，最高阈值仅 {support[-1]['n']} 个变体，不能称全阈值稳健。控制 reads 深度后的 partial Spearman 分别为 {partial['gc3_observed_5prime']['observed']:.3f} 和 {partial['gc_observed_5prime']['observed']:.3f}。",
        "这些关联不构成因果、机制模型增量、完整 CDS、作者变体身份、蛋白 OOD 或 SOTA 证据，也不改变生成训练门禁。",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(slide(content, notes))
    report = {
        "schema": "a8-rk02-mordstein-proxy-ppt-candidate-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "OFFLINE_CANDIDATE_ONLY_NOT_WRITTEN",
        "planned_page": 94,
        "path": str(args.output), "sha256": sha256(args.output),
        "primary_sha256": sha256(args.primary), "primary_independent_sha256": sha256(args.primary_independent),
        "primary_finalization_sha256": sha256(args.primary_finalization),
        "robustness_sha256": sha256(args.robustness), "robustness_independent_sha256": sha256(args.robustness_independent),
        "robustness_finalization_sha256": sha256(args.robustness_finalization),
        "gc3_spearman": gc3["spearman"]["observed"], "gc_spearman": gc["spearman"]["observed"],
        "association_only": True, "protein_ood_claim": False, "mechanism_increment_claim": False, "sota_claim": False,
    }
    args.candidate_report.parent.mkdir(parents=True, exist_ok=True)
    args.candidate_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
