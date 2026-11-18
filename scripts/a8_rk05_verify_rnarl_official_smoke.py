#!/usr/bin/env python3
"""Independently verify RNARL source-contract smoke using AST and fixed Git blobs."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def git(repo, args):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_NO_LAZY_FETCH": "1"}
    return subprocess.check_output(["git", "-C", str(repo), *args], env=env)


def class_node(tree, name):
    return next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)


def method(node, name):
    return next(n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)


def required_init(tree, class_name):
    fn = method(class_node(tree, class_name), "__init__")
    args = fn.args.args
    defaults = set(args[len(args) - len(fn.args.defaults):]) if fn.args.defaults else set()
    return [arg.arg for arg in args if arg.arg != "self" and arg not in defaults]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument("--git-repository", type=Path, required=True)
    p.add_argument("--commit", required=True)
    p.add_argument("--smoke-v1", type=Path, required=True)
    p.add_argument("--smoke-v2", type=Path, required=True)
    p.add_argument("--audit", type=Path, required=True)
    a = p.parse_args()
    if a.audit.exists(): raise RuntimeError(f"refusing to overwrite: {a.audit}")
    v1, v2 = load(a.smoke_v1), load(a.smoke_v2)
    scripts = a.source_root / "scripts"
    trees = {name: ast.parse((scripts / f"{name}.py").read_text(encoding="utf-8"))
             for name in ["actor_train", "reward_train", "grpo_train", "utils"]}
    actor_missing = [x for x in required_init(trees["utils"], "ActorModel_encoder_esm2")
                     if x not in {"vocab_size", "d_model", "nhead", "num_encoder_layers", "dim_feedforward", "dropout", "num_experts", "top_k_experts"}]
    reward_missing = [x for x in required_init(trees["utils"], "RewardModel_encoder")
                      if x not in {"vocab_size", "d_model", "nhead", "num_encoder_layers", "dim_feedforward", "dropout", "num_experts", "top_k_experts"}]
    manager_methods = {n.name for n in class_node(trees["actor_train"], "TrainingManager").body if isinstance(n, ast.FunctionDef)}
    grpo_methods = {n.name for n in class_node(trees["grpo_train"], "GRPOTrainer").body if isinstance(n, ast.FunctionDef)}
    grpo_required = set(v2["contracts"]["grpo_called_methods_defined"]["required"])
    grpo_missing = sorted(grpo_required - grpo_methods)
    global_functions = {n.name for n in trees["grpo_train"].body if isinstance(n, ast.FunctionDef)}
    globals_missing = sorted({"load_and_preprocess_data", "save_model"} - global_functions)
    policy = method(class_node(trees["grpo_train"], "GRPOTrainer"), "policy_optimization_step")
    rewards_stores = [n for n in ast.walk(policy) if isinstance(n, ast.Name) and n.id == "rewards" and isinstance(n.ctx, ast.Store)]
    rewards_loads = [n for n in ast.walk(policy) if isinstance(n, ast.Name) and n.id == "rewards" and isinstance(n.ctx, ast.Load)]

    checks = {}
    checks["fixed_head"] = git(a.git_repository, ["rev-parse", "HEAD"]).decode().strip() == a.commit == v2["commit"]
    tree_lines = git(a.git_repository, ["ls-tree", "-r", a.commit]).decode().splitlines()
    source_ok = True
    source_count = 0
    for line in tree_lines:
        rel = line.split("\t", 1)[1]
        if not (rel.startswith("scripts/") or rel.startswith("example_data/") or rel in {"README.md", "environment.yml"}): continue
        source_count += 1
        source_ok &= (a.source_root / rel).read_bytes() == git(a.git_repository, ["show", f"{a.commit}:{rel}"])
    checks["fixed_source_bytes"] = bool(source_ok and source_count == 10 == v2["source_files_verified_against_commit"])
    checks["official_examples_9_each"] = sorted(r.get("data_rows") for r in v2["source_records"] if "data_rows" in r) == [9, 9, 9]
    checks["v1_environment_failures_preserved"] = (
        v1["imports"]["actor_train"]["error_type"] == "ImportError" and
        "huggingface-hub" in v1["imports"]["actor_train"]["error"] and
        v1["contracts"]["reward_exact_main_constructor"]["error_type"] == "TypeError")
    checks["v2_imports_unblocked"] = not v2["imports"]
    checks["actor_missing_args_ast"] = actor_missing == ["esm2_dim", "device"]
    actor_error = v2["contracts"]["actor_exact_main_constructor"]["error"]
    checks["actor_runtime_matches_ast"] = v2["contracts"]["actor_exact_main_constructor"]["error_type"] == "TypeError" and all(x in actor_error for x in actor_missing)
    checks["actor_evaluate_absent"] = "evaluate" not in manager_methods and not v2["contracts"]["actor_training_evaluate_method"]["present"]
    checks["reward_missing_arg_ast"] = reward_missing == ["device"]
    checks["reward_runtime_matches_ast"] = v2["contracts"]["reward_exact_main_constructor"]["error_type"] == "TypeError" and "device" in v2["contracts"]["reward_exact_main_constructor"]["error"]
    checks["grpo_missing_methods_ast"] = grpo_missing == sorted(v2["contracts"]["grpo_called_methods_defined"]["missing"]) and len(grpo_missing) > 0
    checks["grpo_missing_globals_ast"] = globals_missing == sorted(v2["contracts"]["grpo_main_globals_defined"]["missing"]) == ["load_and_preprocess_data", "save_model"]
    checks["grpo_undefined_rewards_load"] = len(rewards_loads) > 0 and len(rewards_stores) == 0
    checks["declared_transformers_overlay"] = v2["environment"]["transformers"] == "4.46.3"
    checks["declared_hub_overlay"] = importlib.metadata.version("huggingface-hub") == "0.27.0"
    checks["negative_scientific_scope"] = (
        v2["status"] == "FAIL_OFFICIAL_SOURCE_CONTRACTS" and
        not v2["official_full_training_executed"] and not v2["official_generation_output_produced"] and
        not v2["paper_metrics_reproduced"] and not v2["baseline_main_comparison_authorized"])
    report = {
        "schema_version": "a8-rk05-rnarl-official-independent-verification-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_NEGATIVE_REPRODUCIBILITY_AUDIT" if all(checks.values()) else "FAIL",
        "commit": a.commit, "checks": checks, "pass_count": sum(checks.values()), "total": len(checks),
        "independent_ast_findings": {"actor_missing_constructor_args": actor_missing,
            "reward_missing_constructor_args": reward_missing, "actor_evaluate_present": "evaluate" in manager_methods,
            "grpo_missing_called_methods": grpo_missing, "grpo_missing_main_globals": globals_missing,
            "grpo_rewards_load_without_local_store": bool(rewards_loads and not rewards_stores)},
        "smoke_v1_sha256": hashlib.sha256(a.smoke_v1.read_bytes()).hexdigest(),
        "smoke_v2_sha256": hashlib.sha256(a.smoke_v2.read_bytes()).hexdigest(),
        "huggingface_hub_verified": importlib.metadata.version("huggingface-hub"),
        "scope": "PASS verifies a negative availability/reproducibility result only; it does not validate RNARL science, full training, generation, paper metrics, or baseline ranking.",
    }
    a.audit.parent.mkdir(parents=True, exist_ok=True)
    part = a.audit.with_name(a.audit.name + f".part.{os.getpid()}")
    part.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(part, a.audit)
    print(json.dumps({"status": report["status"], "pass": report["pass_count"], "total": report["total"], "checks": checks}))


if __name__ == "__main__": main()
