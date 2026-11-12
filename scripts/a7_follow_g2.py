"""Launch complete G2 only after the G1 watcher publishes both preflights."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codonflow.train.run_pretrain import file_sha256, git_commit
from scripts.a7_execute_g2 import load_preflights
from scripts.a7_follow_g1 import run_logged


def ready_status(path):
    status = json.loads(Path(path).read_text())
    if status.get("status") == "failed":
        raise RuntimeError("G1 watcher failed; G2 cannot start")
    if status.get("status") != "g1_passed_g2_preflight_ready":
        return None
    paths = {}
    for arm in ("FULL", "EDIT"):
        row = status["arms"][arm]
        if row["status"] != "g1_passed" or not row.get("g2_preflight"):
            raise RuntimeError(f"missing {arm} G1 or preflight evidence")
        path = Path(row["g2_preflight"])
        if file_sha256(str(path)) != row["g2_preflight_sha256"]:
            raise RuntimeError(f"{arm} preflight hash changed")
        paths[arm] = path
    return paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--g1-status", required=True)
    parser.add_argument("--g1-pid-file", required=True)
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--poll-seconds", type=int, default=120)
    args = parser.parse_args()
    if args.poll_seconds < 1:
        raise ValueError("polling interval must be positive")
    out_dir = Path(args.out_dir)
    if not str(out_dir.resolve()).startswith("/teams/"):
        raise ValueError("G2 watcher artifacts must remain on /teams")
    out_dir.mkdir(parents=True, exist_ok=True)
    status_path = out_dir / "status.json"
    if status_path.exists():
        raise FileExistsError(f"refusing to overwrite G2 watcher status: {status_path}")
    status = {"protocol": "a7_g2_watcher_v1", "status": "waiting_for_g1_preflights",
              "code_commit": git_commit(), "scientific_gate_passed": False}
    status_path.write_text(json.dumps(status, indent=2))
    try:
        while True:
            preflights = ready_status(args.g1_status)
            if preflights is not None:
                break
            pid = int(Path(args.g1_pid_file).read_text().strip())
            try:
                os.kill(pid, 0)
            except ProcessLookupError as error:
                raise RuntimeError("G1 watcher ended before both preflights were ready") from error
            time.sleep(args.poll_seconds)
        load_preflights([f"{arm}={path}" for arm, path in preflights.items()])
        command = [sys.executable, "scripts/a7_execute_g2.py",
                   "--preflight", f"FULL={preflights['FULL']}",
                   "--preflight", f"EDIT={preflights['EDIT']}",
                   "--rscu-json", args.rscu_json]
        dry = subprocess.check_output(command + ["--dry-run"], text=True, stderr=subprocess.STDOUT)
        (out_dir / "dry_run.log").write_text(dry)
        plan = json.loads(dry.strip().splitlines()[-1])
        if plan["n_learned_tasks"] != 108 or plan["n_simple_tasks"] != 54:
            raise RuntimeError("unexpected G2 task count")
        status["status"] = "running_g2"
        status["dry_run"] = plan
        status_path.write_text(json.dumps(status, indent=2))
        run_logged(command, out_dir / "execution.log")
        root = Path(load_preflights([f"{arm}={path}" for arm, path in preflights.items()])["FULL"]["out_dir"]).parent
        execution = json.loads((root / "execution_status.json").read_text())
        if execution["status"] != "g2_complete":
            raise RuntimeError("G2 executor did not complete")
        run_logged([sys.executable, "scripts/a7_plot_g2.py",
                    "--gate", str(root / "g2_gate.json"),
                    "--out-prefix", str(root / "figures" / "g2_main")], out_dir / "figure.log")
        status["status"] = "g2_complete"
        status["scientific_gate_passed"] = execution["scientific_gate_passed"]
        status["g2_execution_status"] = str(root / "execution_status.json")
        status["g2_execution_sha256"] = file_sha256(str(root / "execution_status.json"))
        status["figure_manifest"] = str(root / "figures" / "g2_main.manifest.json")
        status_path.write_text(json.dumps(status, indent=2))
        print(json.dumps(status))
    except Exception as error:
        status["status"] = "failed"
        status["error"] = str(error)
        status["traceback"] = traceback.format_exc()
        status_path.write_text(json.dumps(status, indent=2))
        raise


if __name__ == "__main__":
    main()
