"""GPU heartbeat: sample nvidia-smi every 30 minutes into a CSV log."""
from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

LOG = Path(os.environ.get("CF_HEARTBEAT_LOG", "/mnt/cunyuliu/codonflow/logs/gpu_heartbeat.csv"))
INTERVAL = int(os.environ.get("CF_HEARTBEAT_INTERVAL", "1800"))
HEADER = "timestamp,index,used_gb,total_gb,util\n"


def sample() -> None:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,memory.used,memory.total,utilization.gpu",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True,
    ).stdout
    ts = datetime.now(timezone.utc).isoformat()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new_file = not LOG.exists()
    with open(LOG, "a") as f:
        if new_file:
            f.write(HEADER)
        for line in out.strip().split("\n"):
            if not line.strip():
                continue
            idx, used, total, util = [p.strip() for p in line.split(",")]
            f.write(f"{ts},{idx},{float(used)/1024:.2f},{float(total)/1024:.2f},{util}\n")


if __name__ == "__main__":
    import sys

    if "--once" in sys.argv:
        sample()
    else:
        while True:
            sample()
            time.sleep(INTERVAL)
