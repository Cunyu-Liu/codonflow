"""Render full-population v4 length/GC distributions and panel composition."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

COLORS = {"train": "#0F4D92", "val": "#42949E", "test": "#B64342", "benchmark": "#4D4D4D"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-prefix", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.audit.read_text())
    manifest = json.loads(args.manifest.read_text())
    assert data["input_sha256"]["test"] == manifest["test_sha256"]
    assert data["input_sha256"]["benchmark"] == manifest["benchmark_sha256"]
    assert manifest["n"] == 18
    names = ("train", "val", "test", "benchmark")
    for name in names:
        split = data["splits"][name]
        for histogram in split["histograms"].values():
            assert sum(histogram["counts"]) == split["n"]
            assert len(histogram["counts"]) + 1 == len(histogram["edges"])
    for pair in ("train__val", "train__test", "val__test", "train__benchmark", "val__benchmark"):
        overlap = data["overlaps"][pair]
        assert overlap["n_shared_cds"] == overlap["n_shared_protein"] == 0
    assert data["overlaps"]["test__benchmark"]["n_shared_cds"] == 18
    assert data["overlaps"]["test__benchmark"]["n_shared_protein"] == 18

    plt.rcParams.update({
        "font.family": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "font.size": 9.5, "axes.linewidth": 1.0, "axes.spines.top": False,
        "axes.spines.right": False, "legend.frameon": False,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    })
    fig, axes = plt.subplots(1, 3, figsize=(12.8, 4.6), gridspec_kw={"wspace": 0.34})
    fig.subplots_adjust(left=0.06, right=0.99, bottom=0.23, top=0.74)
    fig.text(0.06, 0.95, "Frozen v4 splits and the length-stratified 18-gene evaluation panel",
             fontsize=15.5, fontweight="bold", color="#252B31")
    fig.text(0.06, 0.875,
             "Full-population distributions; no sampling or model-based selection",
             fontsize=10.5, color="#64707A")

    for name in names:
        split = data["splits"][name]
        for axis, metric in zip(axes[:2], ("length_nt", "gc")):
            histogram = split["histograms"][metric]
            edges = np.asarray(histogram["edges"], dtype=float)
            centers = (edges[:-1] + edges[1:]) / 2
            fractions = np.asarray(histogram["counts"], dtype=float) / split["n"]
            axis.step(centers, fractions, where="mid", color=COLORS[name],
                      linewidth=1.5 if name != "benchmark" else 1.25,
                      linestyle="-" if name != "benchmark" else "--",
                      label=f"{name} (n={split['n']:,})")
    axes[0].set_xscale("log")
    axes[0].set_xticks([300, 600, 1200, 2400, 6000], ["300", "600", "1,200", "2,400", "6,000"])
    axes[0].set_xlabel("CDS length (nt, log scale)")
    axes[0].set_ylabel("Fraction per 300-nt bin")
    axes[0].set_title("a  Length distribution", loc="left", fontweight="bold")
    axes[0].legend(loc="upper right", fontsize=8)
    axes[1].set_xlabel("GC fraction")
    axes[1].set_ylabel("Fraction per 0.02 bin")
    axes[1].set_title("b  GC distribution", loc="left", fontweight="bold")
    axes[1].set_xlim(0, 1)

    strata_colors = ["#DDF3DE", "#8BCF8B", "#0F4D92"]
    bottom = np.zeros(len(names))
    benchmark_counts = []
    for stratum, color in zip(("short", "mid", "long"), strata_colors):
        fractions = []
        for name in names:
            split = data["splits"][name]
            histogram = split["histograms"]["length_nt"]
            edges = np.asarray(histogram["edges"])
            centers = (edges[:-1] + edges[1:]) / 2
            if stratum == "short":
                selected = centers < 600
            elif stratum == "mid":
                selected = (centers >= 600) & (centers < 1200)
            else:
                selected = centers >= 1200
            count = int(np.asarray(histogram["counts"])[selected].sum())
            if name == "benchmark":
                benchmark_counts.append(count)
            fractions.append(count / split["n"])
        axes[2].bar(names, fractions, bottom=bottom, color=color, width=0.66,
                    edgecolor="white", linewidth=0.8, label=stratum)
        bottom += fractions
    axes[2].set_ylim(0, 1.0)
    axes[2].set_ylabel("Fraction of sequences")
    axes[2].set_title("c  Length-bin composition", loc="left", fontweight="bold")
    axes[2].legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), ncol=3, fontsize=8)
    axes[2].text(3, 1.025, "benchmark: " + " / ".join(map(str, benchmark_counts)),
                 ha="center", va="bottom", fontsize=8.5, color="#252B31")
    for ax in axes:
        ax.tick_params(axis="both", length=3, color="#64707A")
        ax.grid(False)
    fig.text(0.06, 0.075,
             "Curves are sequence-weighted. The benchmark is length-stratified, not a random corpus sample.\n"
             "Scope: exact-protein and nucleotide-cluster holdout; no family/species independence claim.",
             fontsize=9, color="#64707A", linespacing=1.5)
    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out_prefix.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(args.out_prefix.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(json.dumps({"out": str(args.out_prefix), "n": {name: data["splits"][name]["n"] for name in names}}))


if __name__ == "__main__":
    main()
