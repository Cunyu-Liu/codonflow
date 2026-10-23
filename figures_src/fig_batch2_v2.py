#!/usr/bin/env python
"""W3.1 续：fig5 主表图 + fig6 预算曲线（house style）。

- fig5: 主对比 S1/S2/S3 三场景 × 五方法（v2conv 主表数据，3 seeds 均值±std）
  主张：约束保证全绿 + 相对自身无引导基座大提升 + 绝对差距如实呈现（三幕叙事的第三幕伏笔）
- fig6: 推断预算-质量-耗时（E6 budget curves，12 配置网格）
  主张：中间档性价比拐点（与 pCoMole 附录 D 同形态）
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PALETTE = {
    "blue_main": "#0F4D92",
    "blue_secondary": "#3775BA",
    "red_strong": "#B64342",
    "teal": "#42949E",
    "violet": "#9A4D8E",
    "neutral": "#CFCECE",
    "green_3": "#8BCF8B",
}

FIGDIR = Path("figures_v2")
DATA = Path("fig_data")

METHOD_STYLE = {
    "codonflow": ("CodonFlow", PALETTE["blue_main"]),
    "lineardesign_scan": ("LinearDesign", PALETTE["red_strong"]),
    "codongpt": ("codonGPT", PALETTE["teal"]),
    "cai_greedy": ("CAI-greedy", PALETTE["violet"]),
    "uniform_edit_flow": ("uniform flow", PALETTE["neutral"]),
}


def apply_style():
    plt.rcParams.update({
        "font.family": ("Helvetica", "Arial", "DejaVu Sans"),
        "font.size": 15,
        "axes.linewidth": 2.0,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "savefig.dpi": 300,
    })


def save(fig, name):
    FIGDIR.mkdir(exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(FIGDIR / f"{name}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {FIGDIR/name}.pdf/.png")


def fig5_main_table():
    d = json.loads((DATA / "E5v2conv_main_table.json").read_text())
    scenes = ["S1_cai", "S2_cai_mfe", "S3_quad"]
    scene_labels = ["S1: CAI", "S2: CAI+MFE", "S3: four-objective"]
    methods = list(METHOD_STYLE.keys())

    fig, axes = plt.subplots(1, 3, figsize=(15, 5.0))
    for ax, scene, sl in zip(axes, scenes, scene_labels):
        vals, stds, labels, colors = [], [], [], []
        for m in methods:
            k = f"{scene}/{m}/hv"
            xs = [row[k] for gene in d for row in d[gene] if k in row]
            if not xs:
                continue
            vals.append(np.mean(xs))
            stds.append(np.std(xs) / max(len(xs) ** 0.5, 1) * len(xs) ** 0.5)
            labels.append(METHOD_STYLE[m][0])
            colors.append(METHOD_STYLE[m][1])
        ys = np.arange(len(labels))
        ax.barh(ys, vals, 0.62, color=colors, edgecolor="black", linewidth=1.1,
                xerr=stds, capsize=3, error_kw=dict(lw=1.1))
        for y, v in zip(ys, vals):
            ax.text(v + max(vals) * 0.015, y, f"{v:.1f}", va="center",
                    fontsize=11, fontweight="bold")
        ax.set_yticks(ys, labels, fontsize=12)
        ax.set_xlabel("Hypervolume")
        ax.set_xlim(0, max(vals) * 1.22)
        ax.set_title(sl, loc="left", fontweight="bold")
        ax.invert_yaxis()
    fig.suptitle("Main comparison, equal 100-solution budget (L1, 2 genes × 3 seeds, mean ± std)",
                 fontsize=14, y=1.02)
    fig.text(0.5, -0.06,
             "identity/legality minimum = 100% for CodonFlow in every cell; "
             "absolute coverage gap vs DP/AR is reported honestly (§5.4, three-factor attribution)",
             ha="center", fontsize=11, style="italic")
    save(fig, "fig5_main_table")


def fig6_budget():
    d = json.loads((DATA / "E6_budget_curves.json").read_text())
    # 12 配置：steps × candidates × rollouts
    calls = np.array([r["scoring_calls"] for r in d])
    hv = np.array([r["hv"] for r in d])
    per_sol = np.array([r["per_sol_s"] for r in d])
    steps = sorted({r["n_steps"] for r in d})
    cands = sorted({r["n_candidates"] for r in d})

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.6))
    # A: HV vs scoring calls（按 steps 分组）
    ax = axes[0]
    cmap = {10: PALETTE["blue_main"], 20: PALETTE["teal"], 30: PALETTE["violet"]}
    mk = {10: "o", 20: "s", 30: "^"}
    for st in steps:
        idx = [i for i, r in enumerate(d) if r["n_steps"] == st]
        xs = calls[idx]
        ys = hv[idx]
        order = np.argsort(xs)
        ax.plot(xs[order], ys[order], marker=mk.get(st, "o"), ms=8, lw=2.2,
                color=cmap.get(st, PALETTE["neutral"]), label=f"steps={st}")
    # 标注性价比拐点（HV/调用 最高处）
    best = int(np.argmax(hv / np.maximum(calls, 1)))
    ax.annotate(f"best value/call\n({calls[best]} calls, HV {hv[best]:.2f})",
                xy=(calls[best], hv[best]), xytext=(calls[best] + 120, hv[best] + 0.12),
                fontsize=11, arrowprops=dict(arrowstyle="->", lw=1.4))
    ax.set_xlabel("Scoring calls per sequence (budget)")
    ax.set_ylabel("Hypervolume (guided)")
    ax.set_title("A  Quality vs budget", loc="left", fontweight="bold")
    ax.legend(fontsize=11)
    # B: per-solution wall-clock vs calls
    ax = axes[1]
    for st in steps:
        idx = [i for i, r in enumerate(d) if r["n_steps"] == st]
        xs = calls[idx]
        ys = per_sol[idx]
        order = np.argsort(xs)
        ax.plot(xs[order], ys[order], marker=mk.get(st, "o"), ms=8, lw=2.2,
                color=cmap.get(st, PALETTE["neutral"]), label=f"steps={st}")
    ax.set_xlabel("Scoring calls per sequence (budget)")
    ax.set_ylabel("Wall-clock per solution (s)")
    ax.set_title("B  Cost vs budget", loc="left", fontweight="bold")
    fig.suptitle("Inference budget-quality-cost: mid-tier sweet spot (EXP-6, 12 configs)",
                 fontsize=14, y=1.02)
    save(fig, "fig6_exp6_budget")


if __name__ == "__main__":
    apply_style()
    fig5_main_table()
    fig6_budget()
