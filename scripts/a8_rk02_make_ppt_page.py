#!/usr/bin/env python3
"""Generate one offline Mordstein full observed-end slide from final evidence."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from scripts.a8_rk12_make_ppt_pages import (
    badge, bottom_cards, card, kpi, sha256, slide, table, text,
    BODY, INK, MUTED, ORANGE,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-finalization", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--independent", type=Path, required=True)
    parser.add_argument("--finalization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-report", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.candidate_report.exists():
        raise FileExistsError("refusing to overwrite Mordstein PPT candidates")
    download = json.loads(args.download_finalization.read_text())
    summary = json.loads(args.summary.read_text())
    independent = json.loads(args.independent.read_text())
    final = json.loads(args.finalization.read_text())
    if not (download["status"] == "PASS" and download["passed_files"] == download["expected_files"] == 16):
        raise ValueError("download gate has not passed")
    if not (independent["status"] == "PASS" and independent["scope"] == "full" and
            independent["passed"] == independent["total"] == len(independent["checks"])):
        raise ValueError("independent gate has not passed")
    if not (final["status"] == "PASS" and final["scope"] == "full" and
            final["passed"] == final["total"] == len(final["checks"])):
        raise ValueError("finalization gate has not passed")
    if final["summary_sha256"] != sha256(args.summary) or final["independent_sha256"] != sha256(args.independent):
        raise ValueError("finalization does not bind supplied evidence")

    pairs = sum(row["reads_scanned"] for row in summary["exact_collection"])
    r1_valid = sum(row["r1_orf_valid_reads"] for row in summary["exact_collection"])
    r2_valid = sum(row["r2_orf_valid_reads"] for row in summary["exact_collection"])
    independent_label = f"{independent['passed']}/{independent['total']}"
    content = "".join([
        badge("RK02 · MORDSTEIN FULL OBSERVED-END RECOVERY", f"{independent_label} · INDEPENDENT"),
        text(56, 51, 848, 39, "8 bins / 16 mates 完成观测端恢复与独立重算", 25, INK, True, "left", False, 1.0, "headline"),
        text(56, 94, 848, 40, ["max_reads = 0 · all raw pairs scanned · exact caches retained", "central 138 nt remains unobserved · no author GFP identity mapping"], 11, BODY),
        kpi(56, "RAW MATE PAIRS RECOUNTED", f"{pairs:,}", "8 runs · 16 SHA/MD5-verified mates"),
        kpi(344, "R1 VARIANTS · SUPPORT ≥ 1,000", str(summary["variants_retained"]), f"{summary['r1_centroids']} R1 centroids before support filter"),
        kpi(632, "MUTUAL-BEST R1–R2 LINKS", str(summary["mutual_best_links"]), f"{summary['r2_centroids']} R2 centroids · central gap = 138 nt", True),
        text(56, 253, 544, 18, "RECOVERY + INDEPENDENT ACCEPTANCE", 9, BODY, True, "left", True, 1.0, "caption"),
        table(56, 280, [186, 158, 200], [
            ["Check", "Scale", "Observed"],
            ["Verified input", "8 runs / 16 mates", "16/16 PASS"],
            ["ORF-valid reads", "R1 / R2", f"{r1_valid:,} / {r2_valid:,}"],
            ["R1 reads retained", "assigned to 152 variants", f"{summary['selected_r1_assigned_reads']:,}"],
            ["Raw audit", "200 reads × 8 bins", f"{independent['audit_rows_reassigned']:,} reassigned"],
            ["Verification", "independent + final + tests", f"{independent_label} · {final['passed']}/{final['total']} · 7/7"],
        ], [24, 24, 24, 24, 24, 22], 9),
        card(632, 252, 272, 170, "rgba(255, 247, 237, 1)", "rgba(254, 215, 170, 1)"),
        text(648, 263, 240, 18, "SCIENTIFIC GATE · NOT COMPLETE", 9, BODY, True, "left", True, 1.0, "caption"),
        text(648, 290, 240, 110, [
            summary["library_recovery_status"],
            "152 variants ≠ 217 candidates",
            "17 mutual-best links ≠ complete CDS",
            "central 138 nt / 46 codons = N",
            "CF_MORD_* ≠ author GFP_###",
        ], 9, ORANGE),
        bottom_cards(
            ["结论 · 原始 reads 与恢复表已独立核对", f"{independent_label} PASS · {final['passed']}/{final['total']} finalization"],
            ["边界 · 技术通过不等于文库完整", "非完整 CDS · 非作者身份 · 非功能/SOTA 证据"],
        ),
        text(56, 496, 700, 18, f"Evidence: {independent_label} + {final['passed']}/{final['total']} + tests 7/7 · full observed-end only", 9, MUTED, False, "left", True, 1.0, "caption"),
        text(776, 496, 128, 18, "RK02 · 2026-11-19", 9, MUTED, False, "right", False, 1.0, "caption"),
    ])
    notes = [
        f"这一页记录 8 个 HEK293 Flow-seq bins 的全量观测端恢复，16 个 mates 均通过完整性门禁，共独立重数 {pairs:,} 对 reads。",
        f"冻结 support=1,000 后保留 {summary['variants_retained']} 个 R1 variants，并形成 {summary['mutual_best_links']} 条 mutual-best R1-R2 links。",
        f"独立核验 {independent_label} 通过，finalization {final['passed']}/{final['total']} 通过，7 项契约测试通过；这些结果证明计算一致性。",
        "科学文库门禁仍为 REVIEW_REQUIRED_COUNT_NOT_217；中央 138 nt 未观测，不能声称完整 CDS、作者 GFP 身份、独立功能验证或 SOTA。",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(slide(content, notes))
    report = {
        "schema": "a8-rk02-mordstein-ppt-candidate-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "OFFLINE_CANDIDATE_ONLY_NOT_WRITTEN",
        "planned_page": 93,
        "path": str(args.output), "sha256": sha256(args.output),
        "summary_sha256": sha256(args.summary), "independent_sha256": sha256(args.independent),
        "finalization_sha256": sha256(args.finalization),
        "library_recovery_status": summary["library_recovery_status"],
        "variants_retained": summary["variants_retained"], "mutual_best_links": summary["mutual_best_links"],
        "complete_cds_claim": False, "author_identity_claim": False, "sota_claim": False,
    }
    args.candidate_report.parent.mkdir(parents=True, exist_ok=True)
    args.candidate_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
