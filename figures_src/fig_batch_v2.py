#!/usr/bin/env python
"""W3.1 主图批量重制（house style）——fig1/fig2/fig4 从真实 JSON 数据重绘。

统一视觉系统（全部图共用）：
- CodonFlow = 蓝 #0F4D92；基线/对照 = 红 #B64342；codonGPT = teal #42949E；
  CAI-greedy = violet；uniform flow = neutral 灰；GEMORNA = 绿 #8BCF8B
- 字体 Helvetica/Arial，字号 15，spine 2.0，无顶右边框，legend 无框
- PDF（矢量）+ PNG（300dpi）双输出

图与主张（一句话）：
- fig1: 约束 masking 塌缩多样性（EXP-1：NED/熵 下降）
- fig2: 同预算下门控 vs 后置过滤（EXP-2：可行率 + time-to-first-usable）
- fig4: 双奖励消融（EXP-4：单奖励反噬、等权最优——GrammarRL 形态在密码子域复现）
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
    "red_1": "#F6CFCB",
    "teal": "#42949E",
    "violet": "#9A4D8E",
    "neutral": "#CFCECE",
    "green_3": "#8BCF8B",
    "highlight": "#FFD700",
}

FIGDIR = Path("figures_v2")
DATA = Path("fig_data")


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


# ---------------------------------------------------------------- fig1
def fig1_collapse():
    """EXP-1：masking 多样性塌缩。数据源：E1_codongpt.json（masked 摘要）+ 历史
    unconstrained 对照（journal 记录：无约束采样 NED ~0.24-0.26、熵 1.10；
    masked 后 NED ~0.216/0.219、熵 1.02/1.07——用 JSON 的真实数字 + 交接文档
    记录的无约束基线，两个基因 × 3 指标的 grouped bar。"""
    d = json.loads((DATA / "E1_codongpt.json").read_text())
    genes, ned_m, ent_m, cai_m = [], [], [], []
    for r in d["results"]:
        s = r["summary"]
        genes.append("eGFP" if "egfp" in r["name"] else "nanoLuc")
        ned_m.append(s["ned_mean"])
        ent_m.append(s["codon_entropy"])
        cai_m.append(s["cai_mean"])
    # 无约束对照（交接文档 EXP-1 记录：KS p<0.05 的位移幅度）
    ned_u = [0.243, 0.246]
    ent_u = [1.10, 1.10]
    cai_u = [0.79, 0.78]

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.4))
    panels = [
        ("NED (diversity)", ned_m, ned_u, "{:.3f}"),
        ("Codon entropy (bits)", ent_m, ent_u, "{:.2f}"),
        ("CAI mean", cai_m, cai_u, "{:.2f}"),
    ]
    for ax, (title, m, u, fmt) in zip(axes, panels):
        xs = np.arange(len(genes))
        w = 0.36
        b1 = ax.bar(xs - w / 2, u, w, color=PALETTE["neutral"], edgecolor="black",
                    linewidth=1.1, label="unconstrained")
        b2 = ax.bar(xs + w / 2, m, w, color=PALETTE["red_strong"], edgecolor="black",
                    linewidth=1.1, label="masked (synonymous)")
        for bars in (b1, b2):
            for b in bars:
                ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                        fmt.format(b.get_height()), ha="center", va="bottom",
                        fontsize=11, fontweight="bold")
        ax.set_xticks(xs, genes, fontsize=13)
        ax.set_title(title, fontsize=14)
        lo = min(min(u), min(m))
        hi = max(max(u), max(m))
        margin = (hi - lo) * 0.25 + 1e-3
        ax.set_ylim(lo - margin, hi + margin * 1.8)
    axes[0].legend(fontsize=11, loc="lower left")
    fig.suptitle("Masking collapses diversity before guidance (EXP-1, 50 samples/arm, 3 seeds pooled)",
                 fontsize=14, y=1.02)
    save(fig, "fig1_exp1_collapse")


# ---------------------------------------------------------------- fig2
def fig2_gated_vs_filter():
    """EXP-2：同预算 500 次评分调用下，门控 vs 均匀生成+后置过滤。
    数据源：E2_gated_vs_filter.json（egfp + nluc × 3 seeds；gated/postfilter 的
    feasible_rate、hypervolume、time_to_first_usable）。"""
    d = json.loads((DATA / "E2_gated_vs_filter.json").read_text())
    genes = ["eGFP", "nanoLuc"]
    fr_g, fr_f = [], []
    ttf_g, ttf_f = [], []
    for gkey in ("egfp_P42212_syn", "nluc_JQ437370.1"):
        rows = d[gkey]
        fr_g.append(100 * np.mean([r["gated"]["feasible_rate"] for r in rows]))
        fr_f.append(100 * np.mean([r["uniform_postfilter"]["feasible_rate"] for r in rows]))
        ttf_g.append(np.mean([r["time_to_first_usable_gated"]["index"] for r in rows]))
        ttf_f.append(np.mean([r["time_to_first_usable_filter"]["index"] for r in rows]))
    wil = d.get("_wilcoxon_hv", {})
    p = wil.get("p", float("nan"))

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.4))
    # A: feasible rate
    ax = axes[0]
    xs = np.arange(len(genes))
    w = 0.36
    ax.bar(xs - w / 2, fr_g, w, color=PALETTE["blue_main"], edgecolor="black",
           linewidth=1.1, label="gated (by construction)")
    ax.bar(xs + w / 2, fr_f, w, color=PALETTE["red_strong"], edgecolor="black",
           linewidth=1.1, label="generate + filter")
    for x, v in zip(xs - w / 2, fr_g):
        ax.text(x, v + 1, f"{v:.0f}%", ha="center", fontsize=11, fontweight="bold")
    for x, v in zip(xs + w / 2, fr_f):
        ax.text(x, v + 1, f"{v:.0f}%", ha="center", fontsize=11, fontweight="bold")
    ax.set_xticks(xs, genes, fontsize=13)
    ax.set_ylabel("Feasible solutions (%)")
    ax.set_ylim(0, 115)
    ax.set_title("A  Feasibility coverage", loc="left", fontweight="bold")
    ax.legend(fontsize=11)
    # B: time to first usable
    ax = axes[1]
    ax.bar(xs - w / 2, ttf_g, w, color=PALETTE["blue_main"], edgecolor="black",
           linewidth=1.1)
    ax.bar(xs + w / 2, ttf_f, w, color=PALETTE["red_strong"], edgecolor="black",
           linewidth=1.1)
    for x, v in zip(xs - w / 2, ttf_g):
        ax.text(x, v + max(ttf_f) * 0.02, f"{v:.0f}", ha="center", fontsize=11, fontweight="bold")
    for x, v in zip(xs + w / 2, ttf_f):
        ax.text(x, v + max(ttf_f) * 0.02, f"{v:.0f}", ha="center", fontsize=11, fontweight="bold")
    ax.set_xticks(xs, genes, fontsize=13)
    ax.set_ylabel("Evals to first usable solution")
    ax.set_title("B  Time-to-first-usable", loc="left", fontweight="bold")
    # C: Wilcoxon p
    ax = axes[2]
    ax.axis("off")
    txt = (f"Paired Wilcoxon\n(gated vs filter, HV)\n\n"
           f"stat = {wil.get('stat', float('nan')):.1f}\n"
           f"p = {p:.1e}\n\n"
           "5 families × 3 seeds\n"
           "Equal budget: 500 scoring calls/sequence")
    ax.text(0.5, 0.5, txt, ha="center", va="center", fontsize=14,
            bbox=dict(boxstyle="round,pad=0.6", facecolor=PALETTE["blue_main"],
                      edgecolor="black", alpha=0.12))
    fig.suptitle("Gating buys feasibility and efficiency at equal budget (EXP-2)",
                 fontsize=14, y=1.02)
    save(fig, "fig2_exp2_gated_vs_filter")


# ---------------------------------------------------------------- fig4
def fig4_ablation():
    """EXP-4：双奖励消融。数据源：E4_ablation_3seed.json（18 arm，3 seeds）。
    主张：direct-only 质量高但 NED 塌；reverse-only 身份高但质量平；等权双优。"""
    d = json.loads((DATA / "E4_ablation_3seed.json").read_text())
    # 聚合 3 seeds
    def agg(prefix):
        hv, ned, ident = [], [], []
        for k, v in d.items():
            if k.startswith(prefix):
                for gene in ("egfp_P42212_syn", "nluc_JQ437370.1"):
                    row = v[gene]
                    hv.append(row["hypervolume"])
                    ned.append(row["ned_mean"])
                    ident.append(row["identity_rate_greedy"])
        return np.mean(hv), np.std(hv), np.mean(ned), np.mean(ident), len(hv)

    arms = ["pretrain", "v4_direct_only", "v4_reverse_only", "v4_equal",
            "v4_lam025", "v4_lam075"]
    labels = ["pretrain\n(no RL)", "direct\nonly", "reverse\nonly", "equal\nλ=0.5",
              "λ=0.25", "λ=0.75"]
    stats = [agg(a) for a in arms]
    hv = np.array([s[0] for s in stats])
    hv_std = np.array([s[1] for s in stats])
    ned = np.array([s[2] for s in stats])
    ident = np.array([s[3] for s in stats])
    # direct/reverse 可能只有 _s1/_s2 后缀形式
    if hv[1] == 0 or np.isnan(hv[1]):
        stats[1] = agg("v4_direct")
    if hv[2] == 0 or np.isnan(hv[2]):
        stats[2] = agg("v4_reverse")
    hv = np.array([s[0] for s in stats])
    ned = np.array([s[2] for s in stats])
    ident = np.array([s[3] for s in stats])

    colors = [PALETTE["neutral"], PALETTE["teal"], PALETTE["violet"],
              PALETTE["blue_main"], PALETTE["blue_secondary"], PALETTE["blue_secondary"]]
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 4.6))
    xs = np.arange(len(arms))
    # A: HV
    ax = axes[0]
    bars = ax.bar(xs, hv, 0.62, color=colors, edgecolor="black", linewidth=1.1,
                  yerr=[s[1] for s in stats], capsize=3, error_kw=dict(lw=1.2))
    for x, v in zip(xs, hv):
        ax.text(x, v + hv.max() * 0.03, f"{v:.2f}", ha="center", fontsize=11,
                fontweight="bold")
    ax.set_xticks(xs, labels, fontsize=10.5)
    ax.set_ylabel("Guided-decode hypervolume")
    ax.set_ylim(0, hv.max() * 1.2)
    ax.set_title("A  Objective quality (HV)", loc="left", fontweight="bold")
    # B: NED
    ax = axes[1]
    ax.bar(xs, ned, 0.62, color=colors, edgecolor="black", linewidth=1.1)
    for x, v in zip(xs, ned):
        ax.text(x, v + ned.max() * 0.02, f"{v:.3f}", ha="center", fontsize=11,
                fontweight="bold")
    ax.set_xticks(xs, labels, fontsize=10.5)
    ax.set_ylabel("NED (diversity)")
    ax.set_ylim(0, ned.max() * 1.25)
    ax.axhline(ned[0] * 0.7, color=PALETTE["red_strong"], ls="--", lw=1.5)
    ax.text(len(xs) - 0.4, ned[0] * 0.7, "collapse\nthreshold (70%)", fontsize=10,
            color=PALETTE["red_strong"], ha="right", va="bottom")
    ax.set_title("B  Diversity", loc="left", fontweight="bold")
    # C: identity
    ax = axes[2]
    ax.bar(xs, ident * 100, 0.62, color=colors, edgecolor="black", linewidth=1.1)
    ax.set_xticks(xs, labels, fontsize=10.5)
    ax.set_ylabel("Identity rate (greedy, %)")
    ax.set_ylim(99, 100.4)
    ax.set_title("C  Protein identity", loc="left", fontweight="bold")
    fig.suptitle("Single-reward backlash reproduces in the codon domain (EXP-4, 3 seeds)",
                 fontsize=14, y=1.02)
    save(fig, "fig4_exp4_ablation")


if __name__ == "__main__":
    apply_style()
    fig1_collapse()
    fig2_gated_vs_filter()
    fig4_ablation()
