"""Render independently audited A6 core-baseline objective and cost panels."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

METHODS = ("lineardesign_scan", "codongpt", "gemorna", "cai_greedy", "uniform_synonymous")
LABELS = {"lineardesign_scan": "LinearDesign", "codongpt": "codonGPT",
          "gemorna": "GEMORNA", "cai_greedy": "CAI-greedy", "uniform_synonymous": "uniform"}
COLORS = {"lineardesign_scan": "#0F4D92", "codongpt": "#42949E", "gemorna": "#9A4D8E",
          "cai_greedy": "#B64342", "uniform_synonymous": "#A9B2BA"}
GENES = ("egfp_P42212_syn", "nluc_JQ437370.1")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-dir", type=Path, required=True)
    parser.add_argument("--out-prefix", type=Path, required=True)
    args = parser.parse_args()
    audit = json.loads((args.core_dir / "independent_audit.json").read_text())
    assert all(audit["checks"].values())
    rows = {}
    for gene in GENES:
        row = json.loads((args.core_dir / f"{gene}_s0.json").read_text())
        assert set(row["methods"]) == set(METHODS)
        for method in METHODS:
            result = row["methods"][method]
            assert result["status"] == "done" and result["identity_rate"] == 1.0
            assert result["n_unique"] == len(result["solutions"]) == len(set(result["solutions"]))
            assert result["n_invalid_identity"] == 0
            assert np.isfinite(result["obj_vectors"]).all()
            assert result["n_unique"] == audit["genes"][gene][method]["n_unique"]
        rows[gene] = row

    plt.rcParams.update({
        "font.family": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "font.size": 9, "axes.linewidth": 0.9, "axes.spines.top": False,
        "axes.spines.right": False, "legend.frameon": False,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    })
    fig, axes = plt.subplots(2, 2, figsize=(12.4, 8.0), gridspec_kw={"wspace": 0.29, "hspace": 0.45})
    fig.subplots_adjust(left=0.065, right=0.985, bottom=0.13, top=0.76)
    fig.text(0.065, 0.96, "Baselines span different CAI–MFE trade-offs and compute costs",
             fontsize=16, fontweight="bold", color="#252B31")
    fig.text(0.065, 0.915,
             "Seed 0 · identity = 1.0 for every retained solution · no random padding · not a CodonFlow verdict",
             fontsize=10, color="#64707A")
    handles = []
    for column, gene in enumerate(GENES):
        ax = axes[0, column]
        for method in METHODS:
            result = rows[gene]["methods"][method]
            points = np.asarray(result["obj_vectors"])
            stochastic = result["n_unique"] > 10
            scatter = ax.scatter(points[:, 0], points[:, 1], s=16 if stochastic else 48,
                                 color=COLORS[method], alpha=0.56 if stochastic else 0.95,
                                 marker="." if stochastic else ("X" if method == "cai_greedy" else "D"),
                                 edgecolors="none" if stochastic else "#252B31",
                                 linewidths=0.4, label=LABELS[method])
            if column == 0:
                handles.append(scatter)
        ax.set_xlabel("CAI (higher is better)")
        ax.set_ylabel("−MFE (higher is better)")
        ax.set_title(f"{'ab'[column]}  {'eGFP' if column == 0 else 'nanoLuc'} objective distributions",
                     loc="left", fontweight="bold")
    fig.legend(handles, [LABELS[m] for m in METHODS], loc="upper center",
               bbox_to_anchor=(0.5, 0.865), ncol=5, fontsize=8.5)

    x = np.arange(len(METHODS))
    for row_index, metric in enumerate(("n_unique", "elapsed_s")):
        ax = axes[1, row_index]
        for gene_index, gene in enumerate(GENES):
            values = [rows[gene]["methods"][method][metric] for method in METHODS]
            if metric == "elapsed_s":
                values = np.maximum(values, 0.001)
            bars = ax.bar(x + (gene_index - 0.5) * 0.34, values, width=0.34,
                          color=[COLORS[method] for method in METHODS],
                          bottom=0.001 if metric == "elapsed_s" else 0,
                          alpha=0.96 if gene_index == 0 else 0.48,
                          label="eGFP" if gene_index == 0 else "nanoLuc")
            if metric == "n_unique":
                for bar, value in zip(bars, values):
                    ax.text(bar.get_x() + bar.get_width() / 2, value + 2, str(int(value)),
                            ha="center", va="bottom", fontsize=7.5)
        ax.set_xticks(x, ["LD", "codonGPT", "GEMORNA", "CAI-greedy", "uniform"], rotation=18)
        if metric == "n_unique":
            ax.set_ylim(0, 116)
            ax.set_ylabel("Unique identity-valid solutions")
            ax.set_title("c  Actual compact solution sets", loc="left", fontweight="bold")
            ax.legend(loc="upper left", fontsize=8)
        else:
            ax.set_yscale("log")
            ax.set_ylim(bottom=0.001)
            ax.set_ylabel("Generation time (s, log scale)")
            ax.set_title("d  End-to-end generation cost", loc="left", fontweight="bold")
    fig.text(0.065, 0.045,
             "100 requests per stochastic method; LD = 7 DP calls; CAI-greedy = 1 deterministic solution.\n"
             "Forward counts are unavailable for official LD/GEMORNA. Shared-GPU timings are not isolated hardware benchmarks.",
             fontsize=8.5, color="#64707A", linespacing=1.45)
    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out_prefix.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(args.out_prefix.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(json.dumps({"out": str(args.out_prefix), "genes": list(rows)}))


if __name__ == "__main__":
    main()
