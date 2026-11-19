#!/usr/bin/env python3
"""Generate the offline MAGE frozen dev no-go slide from finalized evidence."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from scripts.a8_rk12_make_ppt_pages import badge, bottom_cards, card, kpi, sha256, slide, table, text, BODY, INK, MUTED


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("protocol", "production", "independent", "finalization", "output", "candidate-report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.candidate_report.exists():
        raise FileExistsError("refusing to overwrite MAGE PPT candidates")
    production = json.loads(args.production.read_text())
    independent = json.loads(args.independent.read_text())
    final = json.loads(args.finalization.read_text())
    if not (independent["status"] == "PASS" and independent["checks_total"] == independent["checks_passed"] == 39):
        raise ValueError("MAGE independent gate is not 39/39 PASS")
    if not (final["status"] == "PASS" and final["checks_total"] == final["checks_passed"] == 12):
        raise ValueError("MAGE finalization is not 12/12 PASS")
    if final["protocol_sha256"] != sha256(args.protocol) or final["production_sha256"] != sha256(args.production) or final["independent_sha256"] != sha256(args.independent):
        raise ValueError("MAGE evidence hash mismatch")
    selection = production["rich_dev_selection"]
    counts = production["eligibility"]["split_counts"]
    full = selection["models"]["full_mechanism"]["dev"]["rmse"]
    best = min(selection["models"][k]["dev"]["rmse"] for k in ("intrinsic", "local_mfe"))
    rows = [["Feature set", "Alpha", "Dev RMSE", "Dev Spearman"]]
    for kind in ("intrinsic", "local_mfe", "rcs_only", "full_mechanism"):
        item = selection["models"][kind]
        rows.append([kind, f"{item['selected_alpha']:g}", f"{item['dev']['rmse']:.6f}", f"{item['dev']['spearman']:+.6f}"])
    rows.append(["Verification", "39/39", "12/12 final", "PASS"])
    content = "".join([
        badge("RK03 · FIXED infa MAGE", "39/39 INDEPENDENT · 12/12 FINAL"),
        text(56, 51, 848, 39, "同义全机制特征未通过 dev 增量门禁", 25, INK, True, "left", False, 1.0, "headline"),
        text(56, 94, 848, 40, ["rich medium · positions 10–71 · 164 primary constructs", f"frozen hash split · train/dev/test {counts['train']}/{counts['dev']}/{counts['test']} · alpha selected on dev only"], 11, BODY),
        kpi(56, "FULL MECHANISM · DEV RMSE", f"{full:.6f}", "must be strictly below both intrinsic and local-MFE"),
        kpi(344, "BEST REFERENCE · DEV RMSE", f"{best:.6f}", f"full-minus-best {full-best:+.6f}"),
        kpi(632, "FROZEN DECISION", "NO-GO", "test not authorized · no test metrics", True),
        text(56, 253, 544, 18, "DEV MODEL SELECTION · FOUR FEATURE SETS", 9, BODY, True, "left", True, 1.0, "caption"),
        table(56, 280, [160, 80, 140, 164], rows, [28, 28, 28, 28, 28, 22], 9),
        card(632, 252, 272, 170, "rgba(255, 247, 237, 1)", "rgba(253, 186, 116, 1)"),
        text(648, 263, 240, 18, "TEST UNTOUCHED", 9, BODY, True, "left", True, 1.0, "caption"),
        text(648, 288, 240, 116, ["no test predictions", "no test metrics or paired CIs", "no minimal-medium transport", "no N-terminal transport", "no split swapping or post-hoc tuning"], 9, BODY),
        bottom_cards(["结论 · dev 未显示机制增量", "full mechanism dev RMSE 未优于两个参考特征集"], ["边界 · 不是普遍机制证伪", "仅限固定 infA / rich / positions 10–71 · 非 SOTA"]),
        text(56, 496, 700, 18, "Evidence: independent 39/39 · finalization 12/12 · max numeric delta 4.84e-13", 9, MUTED, False, "left", True, 1.0, "caption"),
        text(776, 496, 128, 18, "RK03 · 2026-11-19", 9, MUTED, False, "right", False, 1.0, "caption"),
    ])
    notes = [
        f"这一页报告固定 infA MAGE 的冻结开发集门禁。主分析包含 164 个构建体，train/dev/test 为 {counts['train']}/{counts['dev']}/{counts['test']}。",
        f"全机制模型的 dev RMSE 为 {full:.6f}，参考特征集的最佳值为 {best:.6f}，因此没有满足严格优于 intrinsic 和 local-MFE 的预设条件。",
        "按照协议，test 未获授权，没有生成 test 预测、指标、置信区间、minimal transport 或 N 端 transport，也没有更换 split 或调参寻找阳性。",
        "独立原始数据与模型矩阵重建 39/39 通过，finalization 12/12 通过；该结果只限当前 dev 门禁，不代表普遍机制证伪。",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(slide(content, notes))
    report = {
        "schema": "a8-rk03-mage-ppt-candidate-v1", "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "OFFLINE_CANDIDATE_ONLY_NOT_WRITTEN", "planned_page": 95,
        "path": str(args.output), "sha256": sha256(args.output),
        "protocol_sha256": sha256(args.protocol), "production_sha256": sha256(args.production),
        "independent_sha256": sha256(args.independent), "finalization_sha256": sha256(args.finalization),
        "dev_no_go": True, "test_untouched": True, "universal_mechanism_falsification_claim": False, "sota_claim": False,
    }
    args.candidate_report.parent.mkdir(parents=True, exist_ok=True)
    args.candidate_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
