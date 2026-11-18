#!/usr/bin/env python3
"""Execute bounded import/constructor contracts on the fixed public RNARL snapshot."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

COMMON = dict(d_model=768, nhead=8, num_encoder_layers=8, dim_feedforward=1536,
              dropout=0.3, num_experts=6, top_k_experts=2)
REQUIRED_GRPO_METHODS = [
    "update_old_policy", "get_esm_embeddings", "sample_actions", "calculate_rewards",
    "compute_advantages", "calculate_log_probs", "calculate_policy_loss",
    "calculate_kl_divergence", "log_batch_stats",
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def capture(callable_):
    try:
        value = callable_()
        return {"executed": True, "error": None, "value": value}
    except Exception as exc:
        return {"executed": True, "error_type": type(exc).__name__, "error": str(exc)}


def load_module(name, path, scripts):
    if str(scripts) not in sys.path: sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo, args, binary=False):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_NO_LAZY_FETCH": "1"}
    result = subprocess.check_output(["git", "-C", str(repo), *args], env=env)
    return result if binary else result.decode().strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--git-repository", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    if args.audit.exists(): raise RuntimeError(f"refusing to overwrite: {args.audit}")
    head = git(args.git_repository, ["rev-parse", "HEAD"])
    if head != args.commit: raise RuntimeError(f"HEAD mismatch: {head}")
    tree = git(args.git_repository, ["ls-tree", "-r", args.commit])
    source_records = []
    for line in tree.splitlines():
        meta, rel = line.split("\t", 1)
        if not (rel.startswith("scripts/") or rel.startswith("example_data/") or rel in {"README.md", "environment.yml"}): continue
        expected = git(args.git_repository, ["show", f"{args.commit}:{rel}"], binary=True)
        actual_path = args.source_root / rel
        actual = actual_path.read_bytes()
        if actual != expected: raise RuntimeError(f"source export mismatch: {rel}")
        record = {"path": rel, "blob_id": meta.split()[2], "bytes": len(actual), "sha256": sha(actual)}
        if rel.startswith("example_data/") and rel.endswith(".csv"):
            with actual_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            record["data_rows"] = len(rows)
            record["columns"] = list(rows[0]) if rows else []
        source_records.append(record)

    scripts = args.source_root / "scripts"
    modules = {}
    for name in ["actor_train", "reward_train", "grpo_train"]:
        result = capture(lambda name=name: load_module(f"a8_official_{name}", scripts / f"{name}.py", scripts))
        modules[name] = result

    contracts = {}
    actor = modules["actor_train"].get("value")
    if actor is not None:
        contracts["actor_import"] = {"status": "PASS"}
        constructor = capture(lambda: actor.ActorModel_encoder_esm2(
            vocab_size=len(actor.Tokenizer().tokens), **COMMON))
        constructor.pop("value", None)
        contracts["actor_exact_main_constructor"] = {
            "source_lines": "actor_train.py:232-236", **constructor,
            "status": "PASS" if constructor.get("error") is None else "FAIL",
        }
        contracts["actor_training_evaluate_method"] = {
            "present": hasattr(actor.TrainingManager, "evaluate"),
            "status": "PASS" if hasattr(actor.TrainingManager, "evaluate") else "FAIL",
        }
    reward = modules["reward_train"].get("value")
    if reward is not None:
        contracts["reward_import"] = {"status": "PASS"}
        constructor = capture(lambda: reward.RewardModel_encoder(
            vocab_size=len(reward.Tokenizer().tokens), **COMMON))
        constructor.pop("value", None)
        contracts["reward_exact_main_constructor"] = {
            "source_lines": "reward_train.py:273-280", **constructor,
            "status": "PASS" if constructor.get("error") is None else "FAIL",
        }
    grpo = modules["grpo_train"].get("value")
    if grpo is not None:
        missing = [name for name in REQUIRED_GRPO_METHODS if not hasattr(grpo.GRPOTrainer, name)]
        contracts["grpo_import"] = {"status": "PASS"}
        contracts["grpo_called_methods_defined"] = {
            "required": REQUIRED_GRPO_METHODS, "missing": missing,
            "status": "PASS" if not missing else "FAIL",
        }
        globals_missing = [name for name in ["load_and_preprocess_data", "save_model"] if not hasattr(grpo, name)]
        contracts["grpo_main_globals_defined"] = {
            "missing": globals_missing, "status": "PASS" if not globals_missing else "FAIL",
        }
    import_failures = {name: {k: v for k, v in result.items() if k != "value"}
                       for name, result in modules.items() if result.get("value") is None}
    checks = [value.get("status") == "PASS" for value in contracts.values()]
    report = {
        "schema_version": "a8-rk05-rnarl-official-contract-smoke-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_SOURCE_CONTRACTS" if contracts and all(checks) and not import_failures else "FAIL_OFFICIAL_SOURCE_CONTRACTS",
        "repository": "https://github.com/ShenggengLin/RNARL",
        "local_clone_remote_origin": git(args.git_repository, ["remote", "get-url", "origin"]),
        "commit": args.commit, "source_files_verified_against_commit": len(source_records),
        "source_records": source_records,
        "environment": {name: importlib.metadata.version(name) for name in ["torch", "transformers", "pandas", "numpy"]},
        "python": sys.version, "python_executable": sys.executable, "sys_path": sys.path,
        "imports": import_failures, "contracts": contracts,
        "official_full_training_executed": False,
        "official_generation_output_produced": False,
        "paper_metrics_reproduced": False,
        "baseline_main_comparison_authorized": False,
        "scope": "Read-only fixed-source export; actual imports and exact public-entry constructor/global contracts only. No ESM-2 weights, official checkpoint, full training, generation, or scientific comparison was claimed.",
    }
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    part = args.audit.with_name(args.audit.name + f".part.{os.getpid()}")
    part.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(part, args.audit)
    print(json.dumps({"status": report["status"], "source_files": len(source_records),
                      "contracts": {k: v.get("status") for k, v in contracts.items()}}))


if __name__ == "__main__": main()
