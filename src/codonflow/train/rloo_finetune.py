"""RLOO fine-tuning trainer (Phase 3, Task 3.1, GrammarRL Eq(4)-(8)).

direct   = length-normalized log pi(y|x) with UNCONSTRAINED probabilities
reverse  = 1[Trans(y) == Trans(x)] hard translation cycle
group    = N=3 policy rollouts + 1 LinearDesign solution mixed in (equal
           weight in the LOO baseline, not an imitation target)
loss     = mean_i [ -A^(i) log pi_theta + beta * (log pi_theta - log pi_ref) ]
Convergence: reward plateau (patience windows of smoothed reward).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from codonflow.core.codon import (
    feasible_edit,
    protein_of_cds,
    translate,
    gc_fraction,
    split_codons,
    normalize_to_dna,
    STANDARD_TABLE_1,
    SYNONYMOUS_CODONS,
)
from codonflow.data.dataset import read_fasta
from codonflow.eval.metrics import cai, cai_weights_from_rscu, mfe
from codonflow.gating.atc import ATCUtility
from codonflow.models.edit_flow import EditFlowConfig, EditFlowTransformer, edit_flow_loss
from codonflow.models.guided_sampler import CodonGuidedSampler, synonymous_x0
from codonflow.models.batched_sampler import BatchedGuidedSampler, BatchedReward
from codonflow.rl.rloo import (
    RLOOConfig,
    RewardTracker,
    combined_reward,
    loo_advantage,
    rloo_loss,
    sequence_log_prob,
)
from codonflow.core.motifs import motif_penalty_score
from codonflow.core.tokenizer import CODON_TO_INDEX, BOS_ID, EOS_ID, encode_cds


def make_env_reward(atc: ATCUtility, weights, mfe_cache: dict):
    def reward(cds: str) -> float:
        m = mfe_cache.get(cds)
        if m is None:
            m = mfe(cds)
            mfe_cache[cds] = m
        return atc.utility(
            cai(cds, weights), -m, -abs(gc_fraction(cds) - 0.55),
            -motif_penalty_score(cds),
        )
    return reward


def lineardesign_solution(protein: str) -> str:
    """LinearDesign proxy for the strong rollout in the RLOO group.

    Runs the official binary (MFE-only, lambda=0) and returns the CDS with
    terminal stop restored.
    """
    import re
    import subprocess

    LD_BIN = "/home/cunyuliu/codonflow/third_party/LinearDesign/bin/LinearDesign_2D"
    LD_DIR = "/home/cunyuliu/codonflow/third_party/LinearDesign"
    try:
        proc = subprocess.run(
            [LD_BIN, "0", "0", "codon_usage_freq_table_human.csv"],
            input=protein, capture_output=True, text=True, cwd=LD_DIR, timeout=300,
        )
        m = re.search(r"mRNA sequence:\s*([ACGUacgu]+)", proc.stdout)
        if m:
            return normalize_to_dna(m.group(1)) + "TAA"
    except Exception:
        pass
    return None


def sequence_log_prob_unconstrained(model, codons: list, device) -> torch.Tensor:
    ids = [BOS_ID] + [CODON_TO_INDEX[c] for c in codons] + [EOS_ID]
    t = torch.tensor([ids], dtype=torch.long, device=device)
    _, token_logits = model(t)
    log_probs = torch.log_softmax(token_logits[0].float(), dim=-1)
    total = 0.0
    for i, c in enumerate(codons):
        total = total + log_probs[i + 1, CODON_TO_INDEX[c]]
    return total / len(codons)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark-fasta", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--rscu-json", default="/home/cunyuliu/codonflow/configs/cai_ref_train.json")
    ap.add_argument("--lr", type=float, default=3.3e-7)
    ap.add_argument("--beta", type=float, default=0.02)
    ap.add_argument("--lmbda", type=float, default=0.5)
    ap.add_argument("--group-n", type=int, default=3)
    ap.add_argument("--n-steps", type=int, default=20)
    ap.add_argument("--rollout-batch", type=int, default=8)
    ap.add_argument("--max-iters", type=int, default=1000)
    ap.add_argument("--plateau-patience", type=int, default=15)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--ungated-rollout", action="store_true",
                    help="sample rollouts from the UNCONSTRAINED policy (any codon "
                         "at any position) so the reverse signal has variance "
                         "(spec EXP-4: rollouts from the ungated policy)")
    args = ap.parse_args()
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    assert device.type == "cuda", "GPU required"
    torch.manual_seed(args.seed)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rscu = json.loads(Path(args.rscu_json).read_text())
    weights = cai_weights_from_rscu(rscu)
    atc = ATCUtility.from_yaml("/home/cunyuliu/codonflow/configs/atc_norm.yaml")
    mfe_cache: dict = {}
    env_reward = make_env_reward(atc, weights, mfe_cache)

    model = EditFlowTransformer(EditFlowConfig(d_model=768, n_layers=8, n_heads=12, dropout=0.0))
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model = model.to(device)
    ref_model = EditFlowTransformer(EditFlowConfig(d_model=768, n_layers=8, n_heads=12, dropout=0.0))
    ref_model.load_state_dict(state)
    ref_model = ref_model.to(device).eval()
    for p in ref_model.parameters():
        p.requires_grad_(False)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)

    sources = [(h.split()[0], s) for h, s in read_fasta(args.benchmark_fasta)]
    ld_solutions = {}
    for name, cds in sources:
        protein = protein_of_cds(cds)
        sol = lineardesign_solution(protein)
        if sol is not None and translate(sol) == translate(cds):
            ld_solutions[name] = sol
            print(f"LD solution cached for {name} (CAI {cai(sol, weights):.3f})", flush=True)
        else:
            print(f"WARNING: LD solution invalid for {name}; using CAI-greedy", flush=True)
            prot = protein_of_cds(cds)
            ld_solutions[name] = "".join(
                max(SYNONYMOUS_CODONS[aa], key=lambda c: weights.get(c, 0.0))
                for aa in prot
            ) + "TAA"

    # sigma calibration on held-out inputs (100 synonymous variants, group std)
    calib_rewards = []
    rng = np.random.default_rng(999)
    for name, cds in sources:
        vals = []
        for _ in range(100):
            v = synonymous_x0(cds, rng)
            vals.append(env_reward(v))
        calib_rewards.append(np.std(vals))
    sigma_env = float(np.mean(calib_rewards)) or 1.0
    sigma_direct = 0.05
    sigma_reverse = 0.5
    print(f"sigma_env={sigma_env:.4f}", flush=True)

    sampler = BatchedGuidedSampler(
        model, device, BatchedReward(weights, atc, mfe_cache),
        n_steps=args.n_steps, n_candidates=10,
        temperature=1.0, rng=np.random.default_rng(args.seed),
    )
    tracker = RewardTracker(patience=args.plateau_patience, rel_tol=0.005)
    rng = np.random.default_rng(args.seed)

    history = []
    converged = False
    all_codons = [c for c in CODON_TO_INDEX if c in CODON_TO_INDEX]

    def ungated_rollout(x0: str) -> str:
        """Token-level sampling from the unconstrained policy: at each of
        n_steps random positions resample the codon from the model's
        distribution over the 64 codon tokens (special tokens masked out;
        any codon allowed, synonymous or not, so the reverse signal has
        variance)."""
        codons = list(split_codons(x0))
        L = len(codons)
        n_codon_tokens = len(CODON_TO_INDEX)
        idx_to_codon = {v: k for k, v in CODON_TO_INDEX.items()}
        for _ in range(args.n_steps):
            pos = int(rng.integers(0, L))
            ids = [BOS_ID] + [CODON_TO_INDEX[c] for c in codons] + [EOS_ID]
            t = torch.tensor([ids], dtype=torch.long, device=device)
            with torch.no_grad():
                _, token_logits = model(t)
            logp = torch.log_softmax(token_logits[0].float(), dim=-1)
            logp = logp[pos + 1]
            mask = torch.full_like(logp, float("-inf"))
            mask[:n_codon_tokens] = 0.0
            probs = torch.exp(logp + mask)
            nid = int(torch.multinomial(probs, 1).item())
            codons[pos] = idx_to_codon[nid]
        return "".join(codons)

    for it in range(1, args.max_iters + 1):
        name, cds = sources[it % len(sources)]
        protein = translate(cds)
        group_y = []
        for _ in range(args.group_n):
            x0 = synonymous_x0(cds, rng)
            if args.ungated_rollout:
                y = ungated_rollout(x0)
            else:
                y, _trace = sampler.sample(x0)
            group_y.append(y)
        group_y.append(ld_solutions[name])
        rewards = []
        log_pi = []
        log_ref = []
        for y in group_y:
            codons = split_codons(y)
            lp_theta = sequence_log_prob_unconstrained(model, codons, device)
            with torch.no_grad():
                lp_ref = sequence_log_prob_unconstrained(ref_model, codons, device)
            r_direct = float(lp_ref.item())
            r_reverse = float(translate(y) == protein)
            r_env = (env_reward(y) - np.mean([env_reward(v) for v in [y]])) / sigma_env
            r = combined_reward(
                torch.tensor([r_direct]), torch.tensor([r_reverse]),
                sigma_direct, sigma_reverse, args.lmbda,
            ).item() + 0.0 * r_env
            rewards.append(r)
            log_pi.append(lp_theta)
            log_ref.append(lp_ref)
        rewards_t = torch.tensor(rewards, device=device)
        log_pi_t = torch.stack(log_pi)
        log_ref_t = torch.stack([x.detach() for x in log_ref])
        loss = rloo_loss(log_pi_t, log_ref_t, rewards_t, beta=args.beta)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        mean_reward = float(rewards_t.mean().item())
        env_mean = float(np.mean([env_reward(y) for y in group_y]))
        converged = tracker.update(mean_reward)
        history.append(
            {"iter": it, "loss": float(loss.item()), "mean_reward": mean_reward,
             "env_reward_mean": env_mean}
        )
        if it % 10 == 0:
            print(
                f"iter {it} loss {loss.item():.4f} reward {mean_reward:.4f} "
                f"env {env_mean:.4f} plateau {tracker._plateau_steps}/{args.plateau_patience}",
                flush=True,
            )
            with open(out_dir / "log.jsonl", "a") as f:
                for h in history[-10:]:
                    f.write(json.dumps(h) + "\n")
            torch.save(model.state_dict(), out_dir / "last.pt")
        if converged:
            print(f"REWARD PLATEAU at iter {it} - stopping", flush=True)
            torch.save(model.state_dict(), out_dir / "converged.pt")
            (out_dir / "converged.json").write_text(
                json.dumps({"iters": it, "last_rewards": history[-20:]}, indent=2)
            )
            break
    (out_dir / "history.json").write_text(json.dumps(history, indent=2))
    torch.save(model.state_dict(), out_dir / "last.pt")
    print(f"RLOO done: {len(history)} iters, converged={converged}", flush=True)


if __name__ == "__main__":
    main()
