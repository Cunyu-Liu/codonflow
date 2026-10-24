#!/usr/bin/env python3
"""W2.3: 全量 per-gene adaptive reference S3 重算（A4 口径）。

与既有 recompute_s3_adaptive.py 的差异：
- 覆盖全部 E5/E5v2/E5v3/E5rloo JSON（不只 S3R_*），按 gene+seed 分组；
- 输出对照表 JSON：每 arm 内各方法按「per-gene adaptive ref（各轴 = 池化 min − 5% margin）」重算 S3 HV；
- 幂等只读，不修改原 JSON；产出 S3R2_full_adaptive.json 供图表与论文使用。
- 同时处理 yeast g08 零域修复验证（HELD18 V356m 文件）。

Run: python recompute_s3_full_adaptive.py   (纯 CPU，与 GPU 训练并行)
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/codonflow/src")
from codonflow.eval.metrics import hypervolume  # noqa: E402

DATA = Path("/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs")
OUT = DATA / "S3R2_full_adaptive.json"

METHODS = ["codonflow", "lineardesign_scan", "codongpt", "cai_greedy",
           "uniform_edit_flow", "gemorna"]


def load_rows(path):
    d = json.loads(path.read_text())
    for gene_rows in d.values():
        return gene_rows
    return []


def recomputize_row(row, label, results):
    pool = {}
    for m in METHODS:
        k = f"S3_quad/{m}/obj_vectors"
        if k in row and row[k]:
            pool[m] = np.asarray(row[k], dtype=float)
    if "codonflow" not in pool or len(pool) < 2:
        return False
    allpts = np.vstack([v for v in pool.values() if len(v)])
    ref = np.array([allpts[:, i].min() - 0.05 * abs(allpts[:, i].min()) - 1e-6
                    for i in range(allpts.shape[1])])
    line = {"n_methods": len(pool), "ref": [float(r) for r in ref]}
    for m, v in pool.items():
        line[f"{m}/hv"] = float(hypervolume(v.tolist(), ref)) if len(v) else 0.0
    results[label] = line
    return True


def main():
    results = {}
    files = sorted(DATA.glob("E5_*_s[0-9].json"))
    files += sorted(DATA.glob("E5v2_*.json"))
    files += sorted(DATA.glob("E5v2conv_*.json"))
    files += sorted(DATA.glob("E5v4s*_*.json"))
    files += sorted(DATA.glob("HELD18_V356m_*.json"))
    n_ok = n_skip = 0
    for p in files:
        tag = p.stem
        try:
            rows = load_rows(p)
        except Exception as e:
            print(f"[{tag}] load fail: {e}")
            n_skip += 1
            continue
        for row in rows:
            if "S3_quad/codonflow/obj_vectors" not in row:
                n_skip += 1
                continue
            label = f"{tag}|seed{row.get('seed', '?')}"
            if recomputize_row(row, label, results):
                n_ok += 1
            else:
                n_skip += 1
    OUT.write_text(json.dumps(results, indent=1))
    print(f"recomputed arms: {n_ok}, skipped: {n_skip}")
    print(f"written: {OUT}")

    # 快速汇总：按 tag 前缀分组打 CF vs 最强基线比
    groups = {}
    for label, line in results.items():
        base = label.split("|")[0]
        g = groups.setdefault(base, {"cf": [], "best": []})
        cf = line.get("codonflow/hv", 0.0)
        others = {m: line.get(f"{m}/hv", 0.0) for m in METHODS if m != "codonflow"}
        best = max(others.values()) if others else 0.0
        if cf > 0 or best > 0:
            g["cf"].append(cf)
            g["best"].append(best)
    print("\n== per-file geomean(CF / best-baseline) ==")
    for base in sorted(groups):
        g = groups[base]
        if not g["cf"]:
            continue
        ratios = [c / b if b > 0 else np.nan for c, b in zip(g["cf"], g["best"])]
        ratios = [r for r in ratios if r == r and r > 0]
        if ratios:
            gm = float(np.exp(np.mean(np.log(ratios))))
            print(f"{base:36s} CF/best geomean = {gm:.3f}  (n={len(ratios)})")


if __name__ == "__main__":
    main()
