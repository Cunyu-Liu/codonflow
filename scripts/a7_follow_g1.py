"""Wait for real convergence, then run CUDA G1 and a non-scientific G2 preflight."""
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


def parse_arm_configs(values):
    if not values:
        raise ValueError("at least one ARM=config is required")
    configs = {}
    for value in values:
        arm, separator, path = value.partition("=")
        if arm not in ("FULL", "EDIT") or not separator or arm in configs:
            raise ValueError("arm configs must be unique FULL/EDIT entries")
        config = json.loads(Path(path).read_text())
        if config.get("corruption") != "synonymous" or config.get("resume") is not None:
            raise ValueError(f"invalid from-scratch synonymous config: {path}")
        if config.get("max_epochs") is not None or config.get("max_steps") is not None:
            raise ValueError("step-bounded training is forbidden")
        configs[arm] = (Path(path), config)
    return configs


def launcher_running(launcher_log, config_path):
    pid_path = Path(launcher_log).with_name("train.pid")
    pid = int(pid_path.read_text().strip())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
    if "a7_run_training.py" not in command or str(config_path) not in command:
        raise RuntimeError(f"launcher PID does not match expected training command: {pid}")
    return True


def run_logged(command, log_path):
    with Path(log_path).open("w") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", action="append", required=True, help="ARM=config.json")
    parser.add_argument("--launcher-log", action="append", required=True, help="ARM=train.log")
    parser.add_argument("--g0-gate", required=True)
    parser.add_argument("--benchmark-fasta", required=True)
    parser.add_argument("--rscu-json", required=True)
    parser.add_argument("--calibration-dir", required=True)
    parser.add_argument("--g2-out-root", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--poll-seconds", type=int, default=120)
    parser.add_argument("--record-id", action="append", dest="record_ids", required=True)
    args = parser.parse_args()
    if args.poll_seconds < 1 or len(args.record_ids) < 3:
        raise ValueError("positive polling interval and at least three G1 genes required")
    out_dir = Path(args.out_dir)
    if not str(out_dir.resolve()).startswith("/teams/"):
        raise ValueError("G1 watcher artifacts must remain on /teams")
    out_dir.mkdir(parents=True, exist_ok=True)
    status_path = out_dir / "status.json"
    if status_path.exists():
        raise FileExistsError(f"refusing to overwrite watcher status: {status_path}")
    configs = parse_arm_configs(args.config)
    launcher_logs = {}
    for value in args.launcher_log:
        arm, separator, path = value.partition("=")
        if not separator or arm not in configs or arm in launcher_logs:
            raise ValueError("launcher logs must match each unique training arm")
        launcher_logs[arm] = Path(path)
    if set(launcher_logs) != set(configs):
        raise ValueError("every training arm needs its launcher log")
    status = {"protocol": "a7_g1_watcher_v1", "status": "waiting_for_convergence",
              "code_commit": git_commit(), "arms": {}, "scientific_gate_passed": False}
    for arm, (config_path, config) in configs.items():
        status["arms"][arm] = {"config": str(config_path), "config_sha256": file_sha256(str(config_path)),
                              "out_dir": config["out_dir"], "status": "waiting_for_convergence"}
    status_path.write_text(json.dumps(status, indent=2))
    try:
        for arm, (config_path, config) in configs.items():
            while not (Path(config["out_dir"]) / "converged.json").exists():
                if not launcher_running(launcher_logs[arm], config_path):
                    raise RuntimeError(f"{arm} ended without a convergence artifact")
                time.sleep(args.poll_seconds)
            audit = out_dir / f"convergence_{arm}.json"
            run_logged([sys.executable, "scripts/a7_convergence_audit.py",
                        "--config", str(config_path), "--g0-gate", args.g0_gate,
                        "--out", str(audit)], out_dir / f"convergence_{arm}.log")
            g1 = out_dir / f"g1_{arm}.json"
            command = [sys.executable, "scripts/a7_g1_behavior.py",
                       "--checkpoint", str(Path(config["out_dir"]) / "converged.pt"),
                       "--checkpoint-sha256", file_sha256(str(Path(config["out_dir"]) / "converged.pt")),
                       "--benchmark-fasta", args.benchmark_fasta, "--rscu-json", args.rscu_json,
                       "--out", str(g1), "--n-samples", "100", "--terminal-step", "4"]
            for record_id in args.record_ids:
                command.extend(["--record-id", record_id])
            run_logged(command, out_dir / f"g1_{arm}.log")
            if json.loads(g1.read_text()).get("passed") is not True:
                raise RuntimeError(f"{arm} failed G1 behavior acceptance; see {g1}")
            status["arms"][arm].update({
                "status": "g1_passed", "convergence_audit": str(audit),
                "convergence_sha256": file_sha256(str(audit)),
                "g1_gate": str(g1), "g1_sha256": file_sha256(str(g1)),
            })
            status_path.write_text(json.dumps(status, indent=2))
            preflight = out_dir / f"g2_preflight_{arm}.json"
            run_logged([sys.executable, "scripts/a7_g2_preflight.py",
                        "--convergence-audit", str(audit), "--g1-gate", str(g1),
                        "--benchmark-fasta", args.benchmark_fasta,
                        "--calibration-dir", args.calibration_dir, "--arm", arm,
                        "--out-dir", str(Path(args.g2_out_root) / arm),
                        "--out", str(preflight)], out_dir / f"g2_preflight_{arm}.log")
            status["arms"][arm]["g2_preflight"] = str(preflight)
            status["arms"][arm]["g2_preflight_sha256"] = file_sha256(str(preflight))
            status_path.write_text(json.dumps(status, indent=2))
        status["status"] = "g1_passed_g2_preflight_ready"
        status_path.write_text(json.dumps(status, indent=2))
        print(json.dumps(status), flush=True)
    except Exception as error:
        status["status"] = "failed"
        status["error"] = str(error)
        status["traceback"] = traceback.format_exc()
        status_path.write_text(json.dumps(status, indent=2))
        raise


if __name__ == "__main__":
    main()
