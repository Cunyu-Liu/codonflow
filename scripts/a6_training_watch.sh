#!/usr/bin/env bash
# Log-driven training monitor: no repeated nvidia-smi polling and no verdicts.
set -u
ROOT=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow
LOG=$ROOT/logs/a6_training_watch.log
INTERVAL=${A6_WATCH_INTERVAL:-1800}
mkdir -p "$ROOT/logs"
touch "$LOG"
echo "$(date -Is) watch start" >> "$LOG"
while :; do
  for run in a6_v4_56m_r2 a6_v4_56m_fulltoken; do
    dir=$ROOT/checkpoints/$run
    [ -d "$dir" ] || continue
    latest=$({ /root/miniconda3/envs/codonflow/bin/python - "$dir" <<'PY'
import json
import re
import sys
from pathlib import Path

run = Path(sys.argv[1])
records = []
if (run / "log.jsonl").exists():
    records = [json.loads(line) for line in (run / "log.jsonl").read_text().splitlines() if line.strip()]
last = records[-1] if records else {}
log = (run / "train.log").read_text() if (run / "train.log").exists() else ""
errors = [line for line in log.splitlines() if re.search(r"OOM|NaN|Traceback|RuntimeError|Killed", line)]
print(json.dumps({
    "last_epoch": last.get("epoch"),
    "train": last.get("train_loss"),
    "val": last.get("val_loss"),
    "best": (run / "best.pt").exists(),
    "state": (run / "training_state.pt").exists(),
    "converged": (run / "converged.json").exists(),
    "errors": errors[-2:],
}))
PY
    } || true)
    marker=$ROOT/logs/.a6_watch_${run}_last
    previous=$(cat "$marker" 2>/dev/null || true)
    if [ "$latest" != "$previous" ]; then
      echo "$(date -Is) $run $latest" >> "$LOG"
      printf '%s' "$latest" > "$marker"
    fi
  done
  sleep "$INTERVAL"
done
