"""Plot Fig-1 (EXP-1 collapse) and Fig-2 (EXP-2 gated vs filter) from the
frozen figure specs (docs/figure_specs/figs_1_to_3.md). Reads JSON outputs,
writes PNG figures to /mnt/cunyuliu/codonflow/eval_outputs/figures/.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT_DIR = Path("/mnt/cunyuliu/codonflow/eval_outputs/figures")


def plot_fig1(exp1_json: str) -> None:
    d = json.loads(Path(exp1_json).read_text())
    names = list(d.keys())
    fig, axes = plt.subplots(1, len(names), figsize=(6.5 * len(names), 4.6))
    if len(names) == 1:
        axes = [axes]
    arms = ["uniform", "rscu_weighted", "cai_greedy"]
    labels = ["uniform sampling", "RSCU-weighted (AR pref.)", "CAI-greedy"]
    colors = ["#3b7dd8", "#d86f3b", "#888888"]
    for ax, name in zip(axes, names):
        seeds = d[name]
        means = {a: [s[a]["ned_mean"] for s in seeds] for a in arms}
        ents = {a: [s[a]["codon_entropy"] for s in seeds] for a in arms}
        m = [np.mean(means[a]) for a in arms]
        e = [np.std(means[a]) for a in arms]
        ax.bar(labels, m, yerr=e, color=colors, capsize=4)
        ks = np.mean([s["ks_p_uniform_vs_rscuw"] for s in seeds])
        ax.set_title(f"{name}  (KS p={ks:.1e})")
        ax.set_ylabel("pairwise NED")
        ax.set_ylim(0, max(m) * 1.35)
        ent_m = [np.mean(ents[a]) for a in arms]
        ax2 = ax.twinx()
        ax2.plot(labels, ent_m, "go--", label="codon entropy")
        ax2.set_ylabel("codon entropy (bits)")
        ax2.set_ylim(0, max(ent_m) * 1.35)
        for i, v in enumerate(m):
            ax.text(i, v + 0.004, f"{v:.3f}", ha="center")
        ll_u = np.mean([s["codongpt_loglik_uniform"] for s in seeds])
        ll_r = np.mean([s["codongpt_loglik_rscuw"] for s in seeds])
        ax.text(
            0.02, 0.98,
            f"codonGPT log-lik:\n uniform {ll_u:.3f}\n RSCU-w {ll_r:.3f}",
            transform=ax.transAxes, va="top", fontsize=8,
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="0.7"),
        )
    fig.suptitle("EXP-1: constrained preference shrinks synonymous diversity")
    fig.tight_layout()
    out = OUT_DIR / "fig1_exp1_collapse.png"
    fig.savefig(out, dpi=200)
    print(f"saved {out}")


def plot_fig2(exp2_json: str) -> None:
    d = json.loads(Path(exp2_json).read_text())
    fams = [k for k in d.keys() if not k.startswith("_")]
    fig, axes = plt.subplots(1, len(fams), figsize=(6.0 * len(fams), 4.6))
    if len(fams) == 1:
        axes = [axes]
    arm_keys = [
        ("gated", "gated_guided", "#2a9d8f"),
        ("uniform_postfilter_topk", "uniform+filter(topK)", "#e9c46a"),
        ("uniform_postfilter", "uniform+filter(all)", "#b5838d"),
    ]
    for ax, fam in zip(axes, fams):
        seeds = d[fam]
        x = np.arange(len(arm_keys))
        hv_m = [np.mean([s[k]["hypervolume"] for s in seeds]) for k, _, _ in arm_keys]
        hv_s = [np.std([s[k]["hypervolume"] for s in seeds]) for k, _, _ in arm_keys]
        fr_m = [np.mean([s[k]["feasible_rate"] for s in seeds]) for k, _, _ in arm_keys]
        labels = [lbl for _, lbl, _ in arm_keys]
        colors = [c for _, _, c in arm_keys]
        ax.bar(x, hv_m, yerr=hv_s, color=colors, capsize=4, label="hypervolume")
        ax.set_xticks(x, labels, rotation=12)
        ax.set_ylabel("hypervolume (3-D, ref (0.5,100,-0.2))")
        ax.set_title(fam)
        ax2 = ax.twinx()
        ax2.plot(x, fr_m, "d", color="k", label="feasible rate")
        ax2.set_ylabel("feasible rate")
        ax2.set_ylim(0, 1.05)
        for i, v in enumerate(hv_m):
            ax.text(i, v + 0.02, f"{v:.2f}", ha="center")
    if "_wilcoxon_hv" in d:
        p = d["_wilcoxon_hv"]["p"]
        fig.suptitle(f"EXP-2: gated vs same-budget post-filter (Wilcoxon p={p:.1e})", y=1.02)
    else:
        fig.suptitle("EXP-2: gated vs same-budget post-filter", y=1.02)
    fig.tight_layout()
    out = OUT_DIR / "fig2_exp2_gated_vs_filter.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"saved {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp1-json", default="/mnt/cunyuliu/codonflow/eval_outputs/EXP1_collapse.json")
    ap.add_argument("--exp2-json", default="/mnt/cunyuliu/codonflow/eval_outputs/E2_gated_vs_filter.json")
    ap.add_argument("--only", choices=["fig1", "fig2"], default=None)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.only in (None, "fig1"):
        plot_fig1(args.exp1_json)
    if args.only in (None, "fig2"):
        plot_fig2(args.exp2_json)


if __name__ == "__main__":
    main()
