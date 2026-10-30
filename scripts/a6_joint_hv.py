"""Joint hypervolume across A6 CodonFlow arms and the audited baseline pool.

Protocol (matches spec §4.4 and scripts/recompute_s3_full_adaptive.pooled_reference):
  reference = min - 0.05 * (max - min)          # per axis, over the unique union
  scale     = q95 - min                          # per axis, robust range
  HV        = hypervolume((points - reference) / scale, zeros(4))

Design rules enforced here:
  * one joint reference per (gene, seed), built from EVERY available objective
    vector of EVERY method; retired or missing methods are listed, never scored 0;
  * duplicate vectors are counted once (shared baselines must not inflate the
    reference domain);
  * degenerate axes (q95 == min) raise unless --allow-degenerate, and are
    reported either way;
  * every input file is admitted only if it declares finite 4-D objectives.
"""
from __future__ import annotations

import argparse
import glob as _glob
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.eval.metrics import hypervolume  # noqa: E402

BASELINE_METHODS = ("lineardesign_scan", "codongpt", "gemorna", "cai_greedy", "uniform_synonymous")
CF_ARMS = ("base", "immediate", "short_rollout")


def joint_reference(points: np.ndarray, allow_degenerate: bool) -> tuple[np.ndarray, np.ndarray, list[int]]:
    values = np.asarray(points, dtype=float)
    if values.ndim != 2 or values.shape[1] != 4 or not len(values):
        raise ValueError("objective matrix must be nonempty and 4-D")
    if not np.isfinite(values).all():
        raise ValueError("objective matrix contains NaN or infinity")
    lo = values.min(axis=0)
    hi = np.ptp(values, axis=0)
    scale = np.quantile(values, 0.95, axis=0) - lo
    degenerate = [int(i) for i in np.where(scale <= 0)[0]]
    if degenerate and not allow_degenerate:
        raise ValueError(f"degenerate axes (q95 == min): {degenerate}; pass --allow-degenerate")
    safe = np.where(scale > 0, scale, 1.0)
    reference = np.where(scale > 0, lo - 0.05 * hi, lo - 1e-6)
    return reference, safe, degenerate


def collect_pilot(path: Path) -> dict:
    data = json.loads(path.read_text())
    gene = data["source"]
    seed = int(data["config"]["seed"])
    arms = {}
    for name, arm in data.get("arms", {}).items():
        pts = np.asarray(arm.get("objectives") or [], dtype=float)
        if pts.size == 0:
            arms[name] = {"status": "empty", "points": np.zeros((0, 4))}
            continue
        if pts.ndim != 2 or pts.shape[1] != 4:
            raise ValueError(f"{path.name}:{name} objectives are not 4-D")
        arms[name] = {
            "status": "done",
            "points": pts,
            "n_solutions": arm.get("n_solutions"),
            "n_unique": arm.get("n_unique"),
            "identity_rate": arm.get("identity_rate"),
            "ned": arm.get("ned"),
            "forward_calls": arm.get("forward_calls"),
            "unique_terminal_reward_calls": arm.get("unique_terminal_reward_calls"),
            "elapsed_s": arm.get("elapsed_s"),
        }
    return {"gene": gene, "seed": seed, "source_file": str(path), "methods": {
        f"cf_{name}": arm for name, arm in arms.items()}}


def collect_baseline(path: Path) -> dict:
    data = json.loads(path.read_text())
    gene = data["record_id"]
    seed = int(data["seed"])
    methods = {}
    for name, res in data.get("methods", {}).items():
        status = res.get("status")
        pts = np.asarray(res.get("obj_vectors") or [], dtype=float)
        if status != "done" or pts.size == 0:
            methods[name] = {"status": status or "empty", "points": np.zeros((0, 4))}
            continue
        if pts.ndim != 2 or pts.shape[1] != 4:
            raise ValueError(f"{path.name}:{name} obj_vectors are not 4-D")
        methods[name] = {
            "status": "done",
            "points": pts,
            "n_solutions": res.get("n_solutions"),
            "n_unique": res.get("n_unique"),
            "identity_rate": res.get("identity_rate"),
            "ned": res.get("ned"),
            "forward_calls": res.get("forward_calls"),
            "elapsed_s": res.get("elapsed_s"),
        }
    return {"gene": gene, "seed": seed, "source_file": str(path), "methods": methods}


def build_group(pilot: dict, baselines: list[dict], allow_degenerate: bool) -> dict:
    merged = dict(pilot["methods"])
    for base in baselines:
        for name, res in base["methods"].items():
            merged.setdefault(name, res)
    done = {n: r for n, r in merged.items() if r["status"] == "done" and len(r["points"])}
    expected = {f"cf_{arm}" for arm in CF_ARMS} | set(BASELINE_METHODS)
    missing = sorted(n for n in expected
                     if merged.get(n, {}).get("status") != "done" or not len(merged.get(n, {}).get("points", [])))
    if not done:
        raise ValueError("no method with objectives in this group")
    pool = np.unique(np.vstack([r["points"] for r in done.values()]), axis=0)
    reference, scale, degenerate = joint_reference(pool, allow_degenerate)
    out = {
        "gene": pilot["gene"],
        "seed": pilot["seed"],
        "reference": reference.tolist(),
        "scale": scale.tolist(),
        "degenerate_axes": degenerate,
        "n_union_points": int(len(pool)),
        "missing_methods": missing,
        "methods": {},
        "inputs": [pilot["source_file"]] + [b["source_file"] for b in baselines],
    }
    for name, res in done.items():
        normalized = (res["points"] - reference) / scale
        out["methods"][name] = {
            "hv": float(hypervolume(normalized.tolist(), np.zeros(4))),
            "n_solutions": res.get("n_solutions"),
            "n_unique": res.get("n_unique"),
            "identity_rate": res.get("identity_rate"),
            "ned": res.get("ned"),
            "forward_calls": res.get("forward_calls"),
            "unique_terminal_reward_calls": res.get("unique_terminal_reward_calls"),
            "elapsed_s": res.get("elapsed_s"),
        }
    return out


def self_test() -> None:
    rng = np.random.default_rng(0)
    base = rng.uniform(0.2, 0.8, size=(40, 4))
    ref, scale, deg = joint_reference(base, allow_degenerate=False)
    assert deg == []
    # a point exactly at the reference has (numerically) zero hypervolume
    hv_ref = float(hypervolume(((ref - ref) / scale).tolist(), np.zeros(4)))
    assert hv_ref < 1e-9, hv_ref
    # adding a dominating point cannot reduce hypervolume
    hv_a = float(hypervolume(((base - ref) / scale).tolist(), np.zeros(4)))
    dominated = np.vstack([base, base.max(axis=0) + 0.01])
    ref2, scale2, _ = joint_reference(dominated, allow_degenerate=False)
    hv_b = float(hypervolume(((dominated - ref2) / scale2).tolist(), np.zeros(4)))
    assert hv_b >= hv_a - 1e-12, (hv_a, hv_b)
    # duplicate vectors must not change the union size
    dup = np.vstack([base, base])
    assert len(np.unique(dup, axis=0)) == len(base)
    # degenerate axis must raise, and be reported when allowed
    flat = np.column_stack([base[:, :3], np.full(len(base), 7.0)])
    try:
        joint_reference(flat, allow_degenerate=False)
        raise AssertionError("degenerate axis was not rejected")
    except ValueError:
        pass
    _, _, deg2 = joint_reference(flat, allow_degenerate=True)
    assert deg2 == [3], deg2
    # p95 (not max) drives the scale: a single extreme outlier must not change it
    with_outlier = np.vstack([base, base.max(axis=0) * 10])
    _, scale3, _ = joint_reference(with_outlier, allow_degenerate=True)
    ptp_out = np.ptp(with_outlier, axis=0)
    assert np.all(scale3 < ptp_out), (scale3, ptp_out)   # p95, not max, sets the scale
    assert np.allclose(scale3, np.quantile(with_outlier, 0.95, axis=0) - with_outlier.min(axis=0))
    print("self_test: OK  (zero-at-reference, monotone, dedup, degenerate, p95-scale)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot-glob", action="append", default=[],
                    help="glob for run_a6_rollout_pilot outputs (repeatable)")
    ap.add_argument("--baseline-glob", action="append", default=[],
                    help="glob for run_a6_baselines per-gene outputs (repeatable)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--allow-degenerate", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.pilot_glob:
        raise SystemExit("--pilot-glob required")
    pilots = {}
    for pattern in args.pilot_glob:
        for path in ([Path(x) for x in sorted(_glob.glob(pattern))] if "*" in pattern else [Path(pattern)]):
            rec = collect_pilot(path)
            key = (rec["gene"], rec["seed"])
            if key in pilots:
                raise ValueError(f"duplicate pilot group {key}")
            pilots[key] = rec
    bases = []
    for pattern in args.baseline_glob:
        for path in ([Path(x) for x in sorted(_glob.glob(pattern))] if "*" in pattern else [Path(pattern)]):
            bases.append(collect_baseline(path))
    groups = []
    for (gene, seed), pilot in sorted(pilots.items()):
        matched = [b for b in bases if b["gene"] == pilot["gene"] and b["seed"] == pilot["seed"]]
        groups.append(build_group(pilot, matched, args.allow_degenerate))
    payload = {
        "protocol": "a6_joint_hv_v1",
        "protocol_notes": {
            "reference": "per-axis min - 0.05 * ptp over the unique union of all methods",
            "scale": "per-axis q95 - min",
            "hv": "hypervolume((points - reference) / scale, zeros(4))",
            "missing_policy": "listed in missing_methods, never scored as zero",
        },
        "groups": groups,
    }
    text = json.dumps(payload, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text)
        print(f"wrote {args.out}  groups={len(groups)}")
    else:
        print(text)


if __name__ == "__main__":
    main()
