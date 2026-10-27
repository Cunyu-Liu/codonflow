"""Render the verified finite-step mechanism and three-arm accounting smoke."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

EXPECTED_CODE = "2854ebb68a6070f0d8ca3200aedf0bec32ef681a"
EXPECTED_CHECKPOINT = "74a542c165f0a1ebe425d78b012fd7f2c64c228f5cd8ddcc0f7f13370f26f5e2"
ARMS = ("base", "immediate", "short_rollout")
ARM_LABELS = {"base": "base", "immediate": "immediate", "short_rollout": "short rollout"}
ARM_COLORS = {"base": "#A9B2BA", "immediate": "#42949E", "short_rollout": "#0F4D92"}
COST_FIELDS = (
    "forward_calls", "base_state_evaluations", "rollout_batch_forwards",
    "rollout_trajectories", "rollout_state_transitions", "terminal_reward_evaluations",
)


def expected_forward_count(terminal_step: int, candidate_count: int) -> int:
    return (
        terminal_step
        + terminal_step * (terminal_step + 1) // 2
        + candidate_count * terminal_step * (terminal_step - 1) // 2
    )


def validate_pilot(pilot: dict) -> None:
    assert pilot["protocol"] == "paired_same_initial_states_v4"
    assert pilot["code_commit"] == EXPECTED_CODE
    assert pilot["checkpoint_sha256"] == EXPECTED_CHECKPOINT
    config = pilot["config"]
    assert (config["n_solutions"], config["terminal_step"]) == (2, 4)
    assert (config["candidate_count"], config["rollout_count"], config["seed"]) == (4, 2, 0)
    assert config["checkpoint"].endswith("/frozen_epoch005.pt")
    assert set(pilot["arms"]) == set(ARMS)
    for name, arm in pilot["arms"].items():
        assert arm["identity_rate"] == 1.0 and arm["n_solutions"] == 2
        final_rows = []
        for trace in arm["traces"]:
            assert len(trace) == 4
            first, final = trace[0], trace[-1]
            for key in COST_FIELDS:
                values = [row[key] for row in trace]
                assert all(right >= left for left, right in zip(values, values[1:]))
            assert final["forward_calls"] == final["base_state_evaluations"] + final["rollout_batch_forwards"]
            assert final["rollout_state_transitions"] == 2 * final["rollout_batch_forwards"]
            if name == "short_rollout":
                assert first["forward_calls"] == 17
                assert final["forward_calls"] == expected_forward_count(4, 4) == 38
                assert final["rollout_trajectories"] == 32
                assert final["terminal_reward_evaluations"] == 37
            else:
                assert final["forward_calls"] == 4
                assert final["rollout_batch_forwards"] == 0
            final_rows.append(final)
        for key in COST_FIELDS:
            assert sum(row[key] for row in final_rows) == arm[key]
        assert arm["terminal_scorer_invocations"] == sum(arm["new_terminal_scores_per_path"])
        assert arm["unique_terminal_reward_calls"] <= arm["terminal_scorer_invocations"] <= arm["terminal_reward_evaluations"]


def box(ax, xy, width, height, title, detail, color):
    patch = FancyBboxPatch(
        xy, width, height, boxstyle="round,pad=0.018,rounding_size=0.025",
        facecolor=color, edgecolor="#252B31", linewidth=1.0,
    )
    ax.add_patch(patch)
    ax.text(xy[0] + width / 2, xy[1] + height * 0.64, title,
            ha="center", va="center", fontsize=9.5, fontweight="bold", color="#252B31")
    ax.text(xy[0] + width / 2, xy[1] + height * 0.31, detail,
            ha="center", va="center", fontsize=7.8, color="#46535E", linespacing=1.35)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-json", type=Path, required=True)
    parser.add_argument("--out-prefix", type=Path, required=True)
    args = parser.parse_args()
    pilot = json.loads(args.pilot_json.read_text())
    validate_pilot(pilot)

    plt.rcParams.update({
        "font.family": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "font.size": 9.5, "axes.linewidth": 1.0, "axes.spines.top": False,
        "axes.spines.right": False, "legend.frameon": False,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    })
    fig, axes = plt.subplots(2, 2, figsize=(12.8, 8.4), gridspec_kw={"wspace": 0.29, "hspace": 0.43})
    fig.subplots_adjust(left=0.065, right=0.985, bottom=0.14, top=0.80)
    fig.text(0.065, 0.955, "Finite-step synonymous editing links mechanism to auditable compute",
             fontsize=16, fontweight="bold", color="#252B31")
    fig.text(0.065, 0.905,
             "Frozen epoch-5 protocol smoke · 2 paired paths · T=4, C=4, R=2 · identity=1.0 for every output",
             fontsize=10.2, color="#64707A")

    ax = axes[0, 0]
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("a  Finite-step MC-Doob approximation", loc="left", fontweight="bold")
    box(ax, (0.02, 0.57), 0.26, 0.25, "Base kernel", "joint codon + position\nexplicit stay", "#DCE9F5")
    box(ax, (0.37, 0.57), 0.26, 0.25, "R rollouts", "shared batch at\neach time step", "#DDF3DE")
    box(ax, (0.72, 0.57), 0.26, 0.25, "Terminal log G", "CAI · MFE · GC\nmotif penalty", "#F6E7E5")
    for start, end in ((0.29, 0.36), (0.64, 0.71)):
        ax.add_patch(FancyArrowPatch((start, 0.695), (end, 0.695), arrowstyle="-|>",
                                     mutation_scale=12, color="#64707A", linewidth=1.2))
    ax.text(0.5, 0.405, r"$\log \hat{h}_t(x)=\mathrm{LSE}_r(\log G(X_T^{(r)}))-\log R$",
            ha="center", va="center", fontsize=11, color="#0F4D92")
    ax.text(0.5, 0.285, r"$q_G(x,y)=q(x,y)\,\hat h_{t+1}(y)/\hat h_t(x)$",
            ha="center", va="center", fontsize=11, color="#0F4D92")
    ax.text(0.5, 0.11,
            "Valid source CDS + synonymous single-codon operators\nExact small-state check; candidate-pruned Monte Carlo at scale",
            ha="center", va="center", fontsize=8.4, color="#64707A", linespacing=1.45)

    ax = axes[0, 1]
    rollout_counts = np.asarray([1, 2, 4, 8, 16])
    ax.plot(rollout_counts, np.full_like(rollout_counts, 38), marker="o", color="#0F4D92",
            linewidth=2.0, label="total model forwards = 38")
    ax.plot(rollout_counts, np.full_like(rollout_counts, 34), marker="s", color="#767676",
            linewidth=1.6, linestyle="--", label="rollout batch forwards = 34")
    ax.plot(rollout_counts, 16 * rollout_counts, marker="^", color="#42949E",
            linewidth=2.0, label="rollout trajectories = 16R")
    ax.plot(rollout_counts, 16 * rollout_counts + 5, marker="D", color="#B64342",
            linewidth=1.8, label="terminal requests = 16R + 5")
    ax.axvline(2, color="#CFCECE", linewidth=1.0, zorder=0)
    ax.set_xscale("log", base=2)
    ax.set_xticks(rollout_counts, [str(value) for value in rollout_counts])
    ax.set_xlabel("Rollouts per value estimate, R (log2 scale)")
    ax.set_ylabel("Count per short-rollout path")
    ax.set_ylim(0, 280)
    ax.set_title("b  R changes sampling, not batched forward count", loc="left", fontweight="bold")
    ax.legend(loc="upper left", fontsize=8.0)

    ax = axes[1, 0]
    x = np.arange(len(ARMS))
    base_values = [pilot["arms"][name]["base_state_evaluations"] for name in ARMS]
    rollout_values = [pilot["arms"][name]["rollout_batch_forwards"] for name in ARMS]
    ax.bar(x, base_values, width=0.62, color="#3775BA", label="current-state base evaluations")
    ax.bar(x, rollout_values, width=0.62, bottom=base_values, color="#DDF3DE",
           edgecolor="#42949E", linewidth=0.8, label="rollout batch forwards")
    for index, name in enumerate(ARMS):
        total = pilot["arms"][name]["forward_calls"]
        ax.text(index, total + 2, str(total), ha="center", va="bottom", fontweight="bold", fontsize=9)
    ax.set_xticks(x, [ARM_LABELS[name] for name in ARMS])
    ax.set_ylabel("Model forward calls")
    ax.set_ylim(0, 88)
    ax.set_title("c  Forward accounting by origin", loc="left", fontweight="bold")
    ax.legend(loc="upper left", fontsize=8.0)

    ax = axes[1, 1]
    metrics = (
        ("terminal_reward_evaluations", "requests", "#B64342"),
        ("terminal_scorer_invocations", "scorer invocations", "#42949E"),
        ("unique_terminal_reward_calls", "unique scored CDS", "#0F4D92"),
    )
    x = np.arange(len(ARMS))
    width = 0.24
    for metric_index, (key, label, color) in enumerate(metrics):
        values = [pilot["arms"][name][key] for name in ARMS]
        bars = ax.bar(x + (metric_index - 1) * width, values, width=width, color=color, label=label)
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, value + 1.5, str(value),
                    ha="center", va="bottom", fontsize=7.6)
    ax.set_xticks(x, [ARM_LABELS[name] for name in ARMS])
    ax.set_ylabel("Terminal log-G accounting")
    ax.set_ylim(0, 88)
    ax.set_title("d  Requests are not unique scorer calls", loc="left", fontweight="bold")
    ax.legend(loc="upper left", fontsize=8.0)

    fig.text(0.065, 0.048,
             "Protocol diagnostic only; no convergence or algorithm-benefit claim. Short rollout: 64 trajectories and 136 individual transitions.\n"
             "Code 2854ebb6 · checkpoint 74a542c1 · requests are pre-cache; invocations include repeats; unique counts distinct scored CDS.",
             fontsize=8.5, color="#64707A", linespacing=1.45)
    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out_prefix.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(args.out_prefix.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(json.dumps({"out": str(args.out_prefix), "arms": {
        name: {key: pilot["arms"][name][key] for key in (
            "forward_calls", "terminal_reward_evaluations",
            "terminal_scorer_invocations", "unique_terminal_reward_calls",
        )} for name in ARMS
    }}))


if __name__ == "__main__":
    main()
