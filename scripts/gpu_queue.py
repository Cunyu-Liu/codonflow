"""GPU queue: poll nvidia-smi, submit pending jobs when VRAM is free (R6-6b).

Every 60s: read queue/pending.json (FIFO + priority), for each job check
available VRAM >= vram_gb + 4 (safety) AND utilization < 30% on n_gpu
contiguous GPUs. Submit via tmux + nohup, move atomically to running.json.
Non-zero exit -> failed list + alert hook. All events append to REGISTRY.md.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

QUEUE_DIR = Path(__file__).resolve().parents[1] / "queue"
PENDING = QUEUE_DIR / "pending.json"
RUNNING = QUEUE_DIR / "running.json"
FAILED = QUEUE_DIR / "failed.json"
LOGS = QUEUE_DIR / "logs"

SAFETY_MARGIN_GB = 4.0
UTIL_THRESHOLD = 30.0
POLL_SECONDS = 60


def gpu_snapshot() -> List[Dict]:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,memory.used,memory.total,utilization.gpu",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True,
    ).stdout
    gpus = []
    for line in out.strip().split("\\n"):
        idx, used, total, util = [p.strip() for p in line.split(",")]
        gpus.append(
            {
                "index": int(idx),
                "used_gb": float(used) / 1024,
                "total_gb": float(total) / 1024,
                "util": 0.0 if util == "[N/A]" else float(util),
            }
        )
    return gpus


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default


def write_json_atomic(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def find_free_gpus(gpus: List[Dict], vram_gb: float, n_gpu: int) -> Optional[List[int]]:
    need = vram_gb + SAFETY_MARGIN_GB
    ok = [
        g["index"]
        for g in gpus
        if (g["total_gb"] - g["used_gb"]) >= need and g["util"] < UTIL_THRESHOLD
    ]
    if len(ok) < n_gpu:
        return None
    return ok[:n_gpu]


def submit_job(job: Dict, gpu_ids: List[int]) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    run_id = job["run_id"]
    log_file = LOGS / f"{run_id}.log"
    env = dict(os.environ)
    if len(gpu_ids) > 1:
        env["CUDA_VISIBLE_DEVICES"] = ",".join(str(i) for i in gpu_ids)
        launch = (
            f"torchrun --nproc_per_node={len(gpu_ids)} --master_port={29500 + (hash(run_id) % 100)} "
            f"{job['cmd']} > {shlex.quote(str(log_file))} 2>&1; echo $? > {shlex.quote(str(QUEUE_DIR / 'exit_' + run_id))}"
        )
    else:
        env["CUDA_VISIBLE_DEVICES"] = str(gpu_ids[0])
        launch = (
            f"{job['cmd']} > {shlex.quote(str(log_file))} 2>&1; "
            f"echo $? > {shlex.quote(str(QUEUE_DIR / ('exit_' + run_id))}"
        )
    full_cmd = launch
    env_str = " ".join(f"{k}={shlex.quote(v)}" for k, v in [("CUDA_VISIBLE_DEVICES", env["CUDA_VISIBLE_DEVICES"])])
    tmux_cmd = f"tmux new-session -d -s cfq_{run_id} 'cd {shlex.quote(job.get(\"cwd\", str(QUEUE_DIR.parents[1])))} && {env_str} {full_cmd}'"
    subprocess.run(tmux_cmd, shell=True, check=False)
    job["gpus"] = gpu_ids
    job["submitted_at"] = datetime.now(timezone.utc).isoformat()
    job["log_file"] = str(log_file)


def check_finished(running: List[Dict]) -> List[Dict]:
    still = []
    for job in running:
        exit_file = QUEUE_DIR / f"exit_{job['run_id']}"
        if exit_file.exists():
            code = exit_file.read_text().strip()
            job["exit_code"] = int(code) if code else -1
            job["finished_at"] = datetime.now(timezone.utc).isoformat()
            exit_file.unlink(missing_ok=True)
            if job["exit_code"] != 0:
                job["status"] = "failed"
            else:
                job["status"] = "done"
        else:
            still.append(job)
    return still


def registry_append(event: Dict) -> None:
    reg = QUEUE_DIR.parents[1] / "experiments" / "REGISTRY.md"
    reg.parent.mkdir(parents=True, exist_ok=True)
    line = f"| {event.get('run_id','')} | {event.get('time','')} | auto-queue | {event.get('event','')} | {event.get('detail','')} |\\n"
    with open(reg, "a") as f:
        f.write(line)


def alert(message: str) -> None:
    alert_path = QUEUE_DIR / "alerts.log"
    with open(alert_path, "a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} {message}\\n")


def main_loop(once: bool = False) -> None:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            pending = read_json(PENDING, [])
            running = read_json(RUNNING, [])
            finished = check_finished(running)
            done_or_failed = [j for j in finished if j.get("status") in ("done", "failed")]
            if done_or_failed:
                for j in done_or_failed:
                    registry_append(
                        {"run_id": j["run_id"], "time": j["finished_at"],
                         "event": j["status"], "detail": f"exit={j['exit_code']} gpus={j.get('gpus')}"}
                    )
                    if j["status"] == "failed":
                        alert(f"job failed: {j['run_id']} exit={j['exit_code']}")
                failed = read_json(FAILED, [])
                failed.extend([j for j in done_or_failed if j["status"] == "failed"])
                write_json_atomic(FAILED, failed)
            write_json_atomic(RUNNING, finished)
            gpus = gpu_snapshot()
            if pending:
                pending.sort(key=lambda j: (-int(j.get("priority", 0)), j.get("seq", 0)))
                still_pending = []
                for job in pending:
                    if "seq" not in job:
                        job["seq"] = int(time.time())
                    n_gpu = int(job.get("n_gpu", 1))
                    vram = float(job.get("vram_gb", 8))
                    gpu_ids = find_free_gpus(gpus, vram, n_gpu)
                    if gpu_ids is None:
                        still_pending.append(job)
                        continue
                    submit_job(job, gpu_ids)
                    for g in gpus:
                        if g["index"] in gpu_ids:
                            g["used_gb"] += vram
                    running = read_json(RUNNING, [])
                    running.append(job)
                    write_json_atomic(RUNNING, running)
                    registry_append(
                        {"run_id": job["run_id"], "time": job["submitted_at"],
                         "event": "submitted", "detail": f"gpus={gpu_ids} vram={vram}GB"}
                    )
                write_json_atomic(PENDING, still_pending)
        except Exception as e:
            alert(f"queue loop error: {e}")
        if once:
            break
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    import sys

    main_loop(once="--once" in sys.argv)
