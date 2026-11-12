"""Generate the G2 figure and gene table only from a frozen gate and its raw inputs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.train.run_pretrain import git_commit

NAVY = "#1b2a5c"
STEEL = "#4f6aa2"
GRAY = "#777777"
GOLD = "#e8a917"
RED = "#d1242f"
TEAL = "#2a7f62"


def load_gate_inputs(gate_path):
    gate = json.loads(Path(gate_path).read_text())
    if gate.get("protocol") != "a7_g2_gate_v1" or len(gate["arms"]) != 2:
        raise ValueError("G2 figure requires the two-arm frozen gate")
    arms = []
    for arm in gate["arms"]:
        payloads = {}
        for item in arm["inputs"]:
            path = Path(item["path"])
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError(f"raw result hash mismatch: {path}")
            payload = json.loads(path.read_text())
            if payload["status"] != "done" or payload["identity_rate"] != 1.0:
                raise ValueError(f"invalid figure input: {path}")
            key = (payload["record_id"], payload["seed"], payload["method"])
            if key in payloads:
                raise ValueError(f"duplicate figure input: {key}")
            payloads[key] = payload
        arms.append((arm, payloads))
    return gate, arms


def arm_curves(arm, payloads):
    learned = []
    baseline = []
    for row in arm["statistics"]["per_gene"]:
        gene = row["gene"]
        method = row["strongest_simple_method"]
        gene_learned = []
        gene_baseline = []
        for seed in (0, 1, 2):
            for method_name, destination in (("learned", gene_learned), (method, gene_baseline)):
                payload = payloads[(gene, seed, method_name)]
                curve = payload["anytime"]["curve"]
                if [point["budget"] for point in curve] != [50, 100, 500]:
                    raise ValueError("unexpected anytime budget grid")
                destination.append([point["hv"] for point in curve])
        learned.append(np.mean(gene_learned, axis=0))
        baseline.append(np.mean(gene_baseline, axis=0))
    return np.asarray(learned), np.asarray(baseline)


def generate_figure(gate_path, out_prefix):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "serif", "font.size": 8.5,
                         "pdf.fonttype": 42, "axes.linewidth": 0.8})
    gate, arms = load_gate_inputs(gate_path)
    fig = plt.figure(figsize=(10.2, 5.8))
    grid = fig.add_gridspec(1, 3, left=0.07, right=0.98, top=0.81, bottom=0.16, wspace=0.34)
    status = "Go" if gate["passed"] else "No-Go"
    fig.suptitle(f"Learned proposal versus strongest simple search — G2 {status}",
                 fontsize=12, fontweight="bold", color=NAVY)
    fig.text(0.07, 0.885,
             "18 development genes; paired initialization and three seeds; 500 unique scorer evaluations per run",
             fontsize=8.5, color="#444444")
    for index, (arm, payloads) in enumerate(arms):
        learned, baseline = arm_curves(arm, payloads)
        ax = fig.add_subplot(grid[0, index])
        for gene_learned, gene_baseline in zip(learned, baseline):
            ax.plot([50, 100, 500], gene_learned, color=STEEL, alpha=0.15, lw=0.65)
            ax.plot([50, 100, 500], gene_baseline, color=GRAY, alpha=0.13, lw=0.65)
        ax.plot([50, 100, 500], np.median(learned, axis=0), color=NAVY, lw=2.1,
                marker="o", ms=4, label="Learned base")
        ax.plot([50, 100, 500], np.median(baseline, axis=0), color=GRAY, lw=1.8,
                marker="s", ms=3.5, ls="--", label="Strongest simple per gene")
        ax.set_title(f"({'ab'[index]}) {arm['arm']} — anytime quality", fontweight="bold")
        ax.set_xlabel("Unique terminal-scorer budget")
        ax.set_xscale("log")
        ax.set_xticks([50, 100, 500], ["50", "100", "500"])
        ax.set_ylabel("Normalized hypervolume" if index == 0 else "")
        ax.grid(axis="y", color="#dddddd", lw=0.45, ls=(0, (1, 2)))
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False, fontsize=7.3, loc="best")
    ax = fig.add_subplot(grid[0, 2])
    for index, (arm, _payloads) in enumerate(arms):
        stats = arm["statistics"]
        center = 100 * stats["median_relative_improvement"]
        low, high = [100 * value for value in stats["paired_bootstrap_95ci"]]
        y = len(arms) - index
        ax.plot([low, high], [y, y], color=NAVY, lw=2.5)
        ax.scatter([center], [y], color=NAVY, s=42, zorder=3)
        ax.text(high, y + 0.19, f"{center:.1f}%", ha="center", fontsize=7.8)
    ax.axvline(0, color=GRAY, lw=0.9)
    ax.axvline(10, color=GOLD, lw=1.1, ls="--", label="10% threshold")
    ax.set_yticks([1, 2], [arms[1][0]["arm"], arms[0][0]["arm"]])
    ax.set_ylim(0.45, 2.65)
    ax.set_title("(c) Gene-level relative effect", fontweight="bold")
    ax.set_xlabel("Median AUC improvement (95% bootstrap CI)")
    ax.grid(axis="x", color="#dddddd", lw=0.45, ls=(0, (1, 2)))
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=7.3, loc="best")
    gate_text = "  |  ".join(
        f"{arm['arm']}: Holm p={arm['holm_adjusted_p']:.3g}, min NED ratio={min(row['ratio'] for row in arm['diversity']):.2f}"
        for arm, _payloads in arms
    )
    fig.text(0.07, 0.065, gate_text, fontsize=7.5, color=TEAL if gate["passed"] else RED)
    fig.text(0.07, 0.025,
             f"Gate {gate_path}\nEach line is one gene; bold curves are medians. The gate may be negative.",
             fontsize=6.5, color="#555555")
    out = Path(out_prefix)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out.with_suffix(".png"), dpi=300)
    fig.savefig(out.with_suffix(".pdf"))
    plt.close(fig)
    table_path = out.with_suffix(".csv")
    with table_path.open("w", newline="") as handle:
        fields = ["arm", "gene", "learned_auc", "strongest_simple_method", "strongest_simple_auc",
                  "absolute_improvement", "relative_improvement", "ned_ratio"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for arm, _payloads in arms:
            diversity = {row["gene"]: row for row in arm["diversity"]}
            for row in arm["statistics"]["per_gene"]:
                writer.writerow({"arm": arm["arm"], **{key: row[key] for key in fields[1:7]},
                                 "ned_ratio": diversity[row["gene"]]["ratio"]})
    manifest = {"protocol": "a7_g2_figure_v1", "gate_path": str(gate_path),
                "gate_sha256": hashlib.sha256(Path(gate_path).read_bytes()).hexdigest(),
                "gate_passed": gate["passed"], "code_commit": git_commit(),
                "outputs": {path.suffix: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                            for path in (out.with_suffix(".png"), out.with_suffix(".pdf"), table_path)}}
    manifest_path = out.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", required=True)
    parser.add_argument("--out-prefix", required=True)
    args = parser.parse_args()
    print(generate_figure(args.gate, args.out_prefix))


if __name__ == "__main__":
    main()
