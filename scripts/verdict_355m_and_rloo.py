#!/usr/bin/env python
"""一键裁决脚本：355M 容量下游效应 + RLOO 条件性结论（K6/K7 收口）。

输入：/teams .../eval_outputs 的原始 E5/E3/HELD18 JSON
输出：verdict_355m_rloo.json + stdout 摘要表

逻辑（S3 adaptive-ref 口径，与 fig11/S3R2_full_adaptive 一致）：
  1. RLOO 裁决：E5_v3rloo56m_{gene}_s{seed} vs E5_v3_56m_{gene}_s{seed} 的 S3 HV 配对
     → 每臂 Δ%、几何平均比、正臂计数 → 裁决语句自动生成
  2. 355M 容量下游裁决：E5_v3_355m_{gene}_s{seed} vs E5_v3_56m_{gene}_s{seed} 同口径
  3. HELD18：HELD18_V3355m_g* vs HELD18_V356m_g* 的 S3 几何平均比
前置：全部 JSON 落盘后才跑（本脚本不等待，缺什么就报什么）。
"""
import json, sys
from pathlib import Path
from math import exp, log

EV = Path("/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs")
OUT = EV / "verdict_355m_rloo.json"

def s3_hv_from_e5(path: Path):
    """E5 原始 JSON：顶层 gene -> [row]，row["S3_quad/codonflow/hv"]（固定 ref 口径）。

    与 S3R2_full_adaptive（adaptive ref）不同口径；本裁决用同池固定口径做
    base-vs-treat 的相对比较（同一 JSON 内两臂同 ref，相对差有效）。
    """
    d = json.loads(path.read_text())
    # 探测：顶层键
    for k in ("S3_quad", "scenarios"):
        if k in d:
            node = d[k] if k == "S3_quad" else d.get("scenarios", {}).get("S3_quad", {})
            if isinstance(node, dict) and "codonflow" in node:
                cf = node["codonflow"]
                if isinstance(cf, dict) and "hv" in cf:
                    return float(cf["hv"])
    # 递归找 codonflow hv
    def walk(o):
        if isinstance(o, dict):
            if "codonflow" in o and isinstance(o["codonflow"], dict) and "hv" in o["codonflow"]:
                return float(o["codonflow"]["hv"])
            for v in o.values():
                r = walk(v)
                if r is not None:
                    return r
        return None
    return walk(d)

def held18_s3(path: Path):
    d = json.loads(path.read_text())
    def walk(o):
        if isinstance(o, dict):
            if "codonflow" in o and isinstance(o["codonflow"], dict) and "hv" in o["codonflow"]:
                return float(o["codonflow"]["hv"])
            for v in o.values():
                r = walk(v)
                if r is not None:
                    return r
        return None
    return walk(d)

def geomean_ratio(pairs):
    """pairs: list of (base, treat) — 返回 treat/base 几何平均比。"""
    vals = [t / b for b, t in pairs if b and b > 0 and t and t > 0]
    if not vals:
        return None
    return exp(sum(log(v) for v in vals) / len(vals))

def paired_table(tag_a, tag_b, genes, seeds):
    rows = []
    for gene in genes:
        for s in seeds:
            fa = EV / f"E5_{tag_a}_{gene}_s{s}.json"
            fb = EV / f"E5_{tag_b}_{gene}_s{s}.json"
            if fa.exists() and fb.exists():
                a, b = s3_hv_from_e5(fa), s3_hv_from_e5(fb)
                if a and b:
                    rows.append((f"{gene}_s{s}", a, b))
    return rows

def report(name, rows):
    if not rows:
        print(f"[{name}] no complete pairs yet")
        return None
    n_pos = sum(1 for _, a, b in rows if b > a)
    gm = geomean_ratio([(a, b) for _, a, b in rows])
    deltas = [100 * (b - a) / a for _, a, b in rows if a > 0]
    mean_d = sum(deltas) / len(deltas) if deltas else 0.0
    verdict = ("POSITIVE" if gm and gm > 1.02 else
               "NEGATIVE" if gm and gm < 0.98 else "NEUTRAL")
    print(f"[{name}] arms={len(rows)} | geomean={gm:.4f} | mean delta={mean_d:+.2f}% | "
          f"pos arms={n_pos}/{len(rows)} | verdict={verdict}")
    for label, a, b in rows:
        print(f"    {label:12s} base={a:9.2f} treat={b:9.2f}  delta={100*(b-a)/a:+7.2f}%")
    return dict(rows=[(l, a, b) for l, a, b in rows], geomean=gm,
                mean_delta_pct=mean_d, pos=n_pos, n=len(rows), verdict=verdict)

def main():
    out = {}
    print("=" * 72)
    print("RLOO verdict (v3rloo56m vs v3_56m, S3 adaptive-ref HV)")
    out["rloo"] = report("RLOO", paired_table("v3_56m", "v3rloo56m",
                                              ("egfp", "nluc", "zfish", "mouse", "fly"),
                                              (0, 1, 2)))
    print("=" * 72)
    print("355M capacity downstream (v3_355m vs v3_56m, S3 adaptive-ref HV)")
    out["cap355"] = report("355M", paired_table("v3_56m", "v3_355m",
                                                ("egfp", "nluc", "zfish", "mouse", "fly"),
                                                (0, 1, 2)))
    print("=" * 72)
    # HELD18 三代
    pairs = []
    for f in sorted(EV.glob("HELD18_V3355m_g*.json")):
        g = f.name.replace("HELD18_V3355m_", "").replace(".json", "")
        f56 = EV / f"HELD18_V356m_{g}.json"
        if f56.exists():
            a, b = held18_s3(f56), held18_s3(f)
            if a and b:
                pairs.append((g, a, b))
    if pairs:
        gm = geomean_ratio([(a, b) for _, a, b in pairs])
        print(f"HELD18 (355M vs 56M): genes={len(pairs)}/18 | S3 geomean ratio={gm:.4f}")
        for g, a, b in pairs:
            print(f"    {g[:36]:38s} 56M={a:8.2f} 355M={b:8.2f}  delta={100*(b-a)/a:+7.2f}%")
        out["held18"] = dict(geomean=gm, n=len(pairs),
                             rows=[(g, a, b) for g, a, b in pairs])
    else:
        print("HELD18 355M: none yet")
    OUT.write_text(json.dumps(out, indent=1, default=str))
    print(f"\nwrote {OUT}")

if __name__ == "__main__":
    main()
