"""Path-level RLOO for finite-step synonymous CDS design.

The legacy unconditional-token scorer and zero-weight environment reward are
replaced by actual sampled-path log probabilities and an explicit terminal
utility. Translation identity is retained as a diagnostic hard constraint, not
counted twice as a learning reward when the proposal is already synonymous.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from codonflow.core.codon import protein_of_cds, split_codons
from codonflow.data.dataset import read_fasta
from codonflow.eval.metrics import cai_weights_from_rscu
from codonflow.gating.atc import ATCUtility
from codonflow.models.batched_sampler import BatchedReward
from codonflow.models.edit_flow import EditFlowConfig, EditFlowTransformer
from codonflow.models.guided_sampler import synonymous_x0
from codonflow.models.synonymous_markov import (
    FiniteStepSynonymousMarkovEditor,
    SynonymousJumpProposal,
)
from codonflow.rl.rloo import RewardTracker, rloo_loss


def load_model(checkpoint: str, device: torch.device) -> EditFlowTransformer:
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    key = next(k for k in state if k.endswith("self_attn.in_proj_weight"))
    d_model = state[key].shape[0] // 3
    n_layers = max(
        int(k.split(".")[2]) for k in state
        if k.startswith("encoder.layers.") and k.endswith("self_attn.in_proj_weight")
    ) + 1
    n_heads = {768: 12, 1280: 16}.get(d_model)
    if n_heads is None:
        raise ValueError(f"unsupported model width {d_model}")
    model = EditFlowTransformer(EditFlowConfig(
        d_model=d_model, n_layers=n_layers, n_heads=n_heads, dropout=0.0,
    ))
    model.load_state_dict(state)
    return model.to(device)


def path_from_trace(initial: str, trace: list[dict]) -> list[str]:
    if not trace:
        raise ValueError("RLOO requires at least one edit transition")
    return [initial] + [row["sequence"] for row in trace]


def reward_scale(values: list[float], floor: float = 1e-6) -> float:
    return max(float(np.std(values)), floor)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--calibration-fasta", required=True,
                        help="disjoint held-out CDS; never use benchmark rewards for tuning")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--rscu-json", default="/home/codonflow/configs/cai_ref_train.json")
    parser.add_argument("--atc-yaml", default="/home/codonflow/configs/atc_norm.yaml")
    parser.add_argument("--lr", type=float, default=3.3e-7)
    parser.add_argument("--beta", type=float, default=0.02,
                        help="squared path log-ratio trust penalty, not a KL claim")
    parser.add_argument("--direct-weight", type=float, default=0.0,
                        help="optional frozen-model path-likelihood reward; 0 avoids duplication")
    parser.add_argument("--env-weight", type=float, default=1.0)
    parser.add_argument("--group-n", type=int, default=4)
    parser.add_argument("--terminal-step", type=int, default=4)
    parser.add_argument("--candidate-count", type=int, default=8)
    parser.add_argument("--rollout-count", type=int, default=4)
    parser.add_argument("--max-iters", type=int, default=100000,
                        help="safety bound only; smoothed plateau determines normal stopping")
    parser.add_argument("--plateau-patience", type=int, default=30)
    parser.add_argument("--reward-smoothing", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    if args.group_n < 2 or args.direct_weight < 0 or args.env_weight < 0:
        raise ValueError("group-n >= 2 and nonnegative reward weights are required")
    if args.direct_weight == args.env_weight == 0:
        raise ValueError("at least one reward component must be active")
    device = torch.device("cuda:0")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required; silent CPU fallback is forbidden")
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    config = vars(args)
    (out_dir / "config.json").write_text(json.dumps(config, indent=2))

    model = load_model(args.checkpoint, device)
    ref_model = copy.deepcopy(model).eval()
    for parameter in ref_model.parameters():
        parameter.requires_grad_(False)
    proposal = SynonymousJumpProposal(model, device)
    ref_proposal = SynonymousJumpProposal(ref_model, device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    weights = cai_weights_from_rscu(json.loads(Path(args.rscu_json).read_text()))
    atc = ATCUtility.from_yaml(args.atc_yaml)
    mfe_cache: dict = {}
    terminal_reward = BatchedReward(weights, atc, mfe_cache, skip_mfe=atc.omega[1] == 0)

    sources = [s for _, s in read_fasta(args.benchmark_fasta)]
    calibration = [s for _, s in read_fasta(args.calibration_fasta)]
    if not sources or not calibration:
        raise ValueError("both training and calibration FASTA files must be nonempty")
    if set(sources) & set(calibration):
        raise ValueError("calibration sequences must be disjoint from training sources")

    def sample_group(source: str, use_model=True):
        group = []
        for index in range(args.group_n):
            initial = synonymous_x0(source, rng)
            editor = FiniteStepSynonymousMarkovEditor(
                proposal, terminal_reward,
                terminal_step=args.terminal_step,
                rollout_count=args.rollout_count,
                candidate_count=args.candidate_count,
                rng=rng,
            )
            terminal, trace = editor.sample(initial)
            path = path_from_trace(initial, trace)
            group.append({
                "initial": initial, "terminal": terminal, "path": path,
                "utility": terminal_reward([terminal])[0],
                "identity": protein_of_cds(terminal) == protein_of_cds(source),
                "index": index,
            })
        return group

    # Frozen-policy within-group standard deviations on held-out CDS. The
    # terminal utility and path log likelihood have separate scales.
    calibration_env, calibration_direct = [], []
    with torch.no_grad():
        for source in calibration[:100]:
            group = sample_group(source)
            utilities = [row["utility"] for row in group]
            calibration_env.append(reward_scale(utilities))
            calibration_direct.append(reward_scale([
                float(ref_proposal.sampled_path_log_probability(row["initial"], row["path"]))
                for row in group
            ]))
    sigma_env = max(float(np.mean(calibration_env)), 1e-6)
    sigma_direct = max(float(np.mean(calibration_direct)), 1e-6)
    scales = {"sigma_env": sigma_env, "sigma_direct": sigma_direct,
              "n_calibration_sequences": min(100, len(calibration))}
    (out_dir / "reward_calibration.json").write_text(json.dumps(scales, indent=2))

    tracker = RewardTracker(
        patience=args.plateau_patience, rel_tol=0.005, smoothing=args.reward_smoothing,
    )
    history, converged = [], False
    for iteration in range(1, args.max_iters + 1):
        source = sources[(iteration - 1) % len(sources)]
        group = sample_group(source)
        env = torch.tensor([row["utility"] for row in group], dtype=torch.float32)
        direct_rewards = []
        with torch.no_grad():
            for row in group:
                direct_rewards.append(ref_proposal.sampled_path_log_probability(
                    row["initial"], row["path"],
                ))
        direct = torch.stack(direct_rewards).cpu()
        rewards = (
            args.env_weight * env / sigma_env
            + args.direct_weight * direct / sigma_direct
        ).to(device)
        log_pi = torch.stack([
            proposal.sampled_path_log_probability(row["initial"], row["path"])
            for row in group
        ])
        with torch.no_grad():
            log_ref = torch.stack([
                ref_proposal.sampled_path_log_probability(row["initial"], row["path"])
                for row in group
            ])
        loss = rloo_loss(log_pi, log_ref, rewards, beta=args.beta)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        if not torch.isfinite(grad_norm):
            raise FloatingPointError(f"non-finite gradient at iteration {iteration}")
        optimizer.step()
        record = {
            "iteration": iteration,
            "loss": float(loss.detach()),
            "grad_norm": float(grad_norm),
            "env_reward_mean": float(env.mean()),
            "direct_reward_mean": float(direct.mean()),
            "identity_rate": float(np.mean([row["identity"] for row in group])),
            "reward_mean": float(rewards.mean()),
            "log_pi_mean": float(log_pi.detach().mean()),
            "log_ref_mean": float(log_ref.mean()),
            "sigma_env": sigma_env,
            "sigma_direct": sigma_direct,
        }
        if not all(np.isfinite(v) for k, v in record.items() if k != "iteration"):
            raise FloatingPointError(f"non-finite metric at iteration {iteration}")
        history.append(record)
        converged = tracker.update(record["reward_mean"])
        with (out_dir / "log.jsonl").open("a") as handle:
            handle.write(json.dumps(record) + "\n")
        if iteration % 10 == 0:
            torch.save(model.state_dict(), out_dir / "last.pt")
            print(json.dumps(record), flush=True)
        if converged:
            break
    if not converged and args.max_iters >= 100000:
        raise RuntimeError("safety iteration bound reached before reward plateau")
    torch.save(model.state_dict(), out_dir / "converged.pt" if converged else out_dir / "last.pt")
    (out_dir / "converged.json").write_text(json.dumps({
        "converged": converged, "iterations": len(history),
        "smoothed_rewards": tracker.smoothed_history,
        "config": config, "calibration": scales,
    }, indent=2))
    (out_dir / "history.json").write_text(json.dumps(history, indent=2))


if __name__ == "__main__":
    main()
