"""Execute complete paired G2 shards only after both arms pass preflight."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.eval.protocol import validate_result_payload
from codonflow.train.run_pretrain import file_sha256, git_commit


def load_preflights(values):
    arms = {}
    for value in values:
        arm, separator, path = value.partition("=")
        if arm not in ("FULL", "EDIT") or not separator or arm in arms:
            raise ValueError("preflights must be unique FULL/EDIT entries")
        payload = json.loads(Path(path).read_text())
        if payload.get("protocol") != "a7_g2_preflight_v1" or payload.get("ready_for_g2") is not True:
            raise ValueError(f"G2 preflight has not passed: {path}")
        if payload.get("arm") != arm or payload.get("scientific_gate_passed") is not False:
            raise ValueError(f"invalid arm or premature scientific claim: {path}")
        if payload["code_dirty"] is not False or not payload["checkpoint_sha256"]:
            raise ValueError(f"invalid code or checkpoint provenance: {path}")
        arms[arm] = payload
    if set(arms) != {"FULL", "EDIT"}:
        raise ValueError("both FULL and EDIT preflights are required")
    shared = ("record_ids", "seeds", "benchmark_fasta", "benchmark_sha256",
              "calibration_dir", "rscu_sha256", "code_commit", "budget",
              "terminal_step", "path_batch_size")
    for key in shared:
        if arms["FULL"][key] != arms["EDIT"][key]:
            raise ValueError(f"unmatched arm preflight field: {key}")
    if arms["FULL"]["record_ids"] != arms["EDIT"]["record_ids"] or len(arms["FULL"]["record_ids"]) < 18:
        raise ValueError("G2 requires the complete development set")
    if arms["FULL"]["seeds"] != [0, 1, 2] or arms["FULL"]["budget"] != 500:
        raise ValueError("G2 requires seeds 0/1/2 and budget 500")
    return arms


def result_path(root, arm, record_id, seed, method):
    directory = root / "shared_simple" if arm is None else root / arm
    return directory / f"{record_id}_{method}_s{seed}.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="append", required=True, help="ARM=preflight.json")
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--simple-workers", type=int, default=4)
    parser.add_argument("--learned-workers", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.simple_workers < 1 or args.learned_workers < 1:
        raise ValueError("worker counts must be positive")
    arms = load_preflights(args.preflight)
    if Path(arms["FULL"]["out_dir"]).parent != Path(arms["EDIT"]["out_dir"]).parent:
        raise ValueError("both arms must share one G2 output root")
    for preflight in arms.values():
        if file_sha256(preflight["g1_gate_path"]) != preflight["g1_gate_sha256"]:
            raise ValueError("G1 artifact changed after preflight")
        if file_sha256(preflight["checkpoint_path"]) != preflight["checkpoint_sha256"]:
            raise ValueError("checkpoint changed after preflight")
    template = arms["FULL"]
    root = Path(template["out_dir"]).parent
    if not str(root.resolve()).startswith("/teams/"):
        raise ValueError("G2 results must remain on /teams")
    if file_sha256(args.rscu_json) != template["rscu_sha256"]:
        raise ValueError("RSCU file does not match preflight")
    commit = git_commit()
    subprocess.run(["git", "merge-base", "--is-ancestor", template["code_commit"], commit], check=True)
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError("G2 execution requires a clean source tree")
    audit = json.loads(Path(template["convergence_audit_path"]).read_text())
    if file_sha256(template["convergence_audit_path"]) != template["convergence_audit_sha256"]:
        raise ValueError("convergence audit changed after preflight")
    config = json.loads(Path(audit["config_path"]).read_text())
    if file_sha256(audit["config_path"]) != audit["config_sha256"]:
        raise ValueError("training config changed after convergence audit")
    data_split_sha256 = config["train_sha256"]
    tasks = []
    for arm, preflight in arms.items():
        for record_id in preflight["record_ids"]:
            for seed in preflight["seeds"]:
                command = [sys.executable, "scripts/a7_run_learned.py",
                           "--checkpoint", preflight["checkpoint_path"],
                           "--checkpoint-sha256", preflight["checkpoint_sha256"],
                           "--benchmark-fasta", preflight["benchmark_fasta"],
                           "--rscu-json", args.rscu_json, "--calibration-dir", preflight["calibration_dir"],
                           "--data-split-sha256", data_split_sha256,
                           "--out-dir", str(root / arm), "--record-id", record_id, "--seed", str(seed),
                           "--terminal-step", str(preflight["terminal_step"]),
                           "--path-batch-size", str(preflight["path_batch_size"]),
                           "--max-unique-scorer", str(preflight["budget"])]
                if args.resume:
                    command.append("--resume")
                tasks.append({"arm": arm, "record_id": record_id, "seed": seed,
                              "command": command, "result": result_path(root, arm, record_id, seed, "learned")})
    simple_tasks = []
    for record_id in template["record_ids"]:
        for seed in template["seeds"]:
            command = [sys.executable, "scripts/a7_run_simple_search.py",
                       "--benchmark-fasta", template["benchmark_fasta"], "--record-id", record_id,
                       "--rscu-json", args.rscu_json, "--calibration-dir", template["calibration_dir"],
                       "--data-split-sha256", data_split_sha256,
                       "--out-dir", str(root / "shared_simple"), "--seed", str(seed),
                       "--max-unique-scorer", str(template["budget"])]
            if args.resume:
                command.append("--resume")
            simple_tasks.append({"arm": None, "record_id": record_id, "seed": seed, "command": command})
    if args.dry_run:
        print(json.dumps({"ready_for_g2_execution": True, "scientific_gate_passed": False,
                          "n_learned_tasks": len(tasks), "n_simple_tasks": len(simple_tasks),
                          "root": str(root), "code_commit": commit}))
        return
    status_path = root / "execution_status.json"
    if status_path.exists() and not args.resume:
        raise FileExistsError(f"refusing to overwrite execution status: {status_path}")
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    status = {"protocol": "a7_g2_execution_v1", "status": "running", "code_commit": commit,
              "scientific_gate_passed": False, "n_learned_tasks": len(tasks),
              "n_simple_tasks": len(simple_tasks), "simple_workers": args.simple_workers,
              "learned_workers": args.learned_workers}
    if status_path.exists():
        status["previous_status"] = json.loads(status_path.read_text())
    status_path.write_text(json.dumps(status, indent=2))
    attempt = int(time.time())

    def execute(task):
        label = task["arm"] or "shared_simple"
        log_path = log_dir / f"{label}_{task['record_id']}_s{task['seed']}_{attempt}.log"
        with log_path.open("w") as log:
            subprocess.run(task["command"], stdout=log, stderr=subprocess.STDOUT, check=True)
        paths = ([result_path(root, None, task["record_id"], task["seed"], method)
                  for method in ("uniform", "hill_climbing", "mh_annealing", "areuredi_style")]
                 if task["arm"] is None else [task["result"]])
        for path in paths:
            payload = json.loads(path.read_text())
            validate_result_payload(payload)
            if payload["status"] != "done" or payload["identity_rate"] != 1.0:
                raise ValueError(f"incomplete G2 result: {path}")
            if payload["code_commit"] != commit or payload["code_dirty"] is not False:
                raise ValueError(f"code provenance mismatch: {path}")
        return {"label": label, "record_id": task["record_id"], "seed": task["seed"]}

    try:
        def run_pool(task_list, workers):
            with ThreadPoolExecutor(max_workers=workers) as pool:
                return list(pool.map(execute, task_list))

        with ThreadPoolExecutor(max_workers=2) as both:
            simple_future = both.submit(run_pool, simple_tasks, args.simple_workers)
            learned_future = both.submit(run_pool, tasks, args.learned_workers)
            simple_completed = simple_future.result()
            learned_completed = learned_future.result()
        status["simple_completed"] = len(simple_completed)
        status["learned_completed"] = len(learned_completed)
        gate = root / "g2_gate.json"
        gate_command = [sys.executable, "scripts/a7_g2_gate.py", "--out", str(gate),
                        "--benchmark-fasta", template["benchmark_fasta"],
                        "--calibration-dir", template["calibration_dir"]]
        for arm, preflight in arms.items():
            gate_command.extend(["--arm", ",".join([
                arm, preflight["checkpoint_sha256"],
                str(root / arm / "*_learned_s*.json"),
                str(root / "shared_simple" / "*_s*.json"),
            ])])
        with (log_dir / "g2_gate.log").open("w") as log:
            subprocess.run(gate_command, stdout=log, stderr=subprocess.STDOUT, check=True)
        gate_result = json.loads(gate.read_text())
        status["status"] = "g2_complete"
        status["scientific_gate_passed"] = gate_result["passed"]
        status["g2_gate"] = str(gate)
        status["g2_gate_sha256"] = file_sha256(str(gate))
    except Exception as error:
        status["status"] = "failed"
        status["error"] = str(error)
        status_path.write_text(json.dumps(status, indent=2))
        raise
    status_path.write_text(json.dumps(status, indent=2))
    print(json.dumps(status))


if __name__ == "__main__":
    main()
