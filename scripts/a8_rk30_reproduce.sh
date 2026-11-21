#!/usr/bin/env bash
# Reproduce RK30 verification from a clean checkout without moving large assets into Git.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${RK30_PYTHON:-/home/codonflow-clean-env-v1/bin/python}"
PROTOCOL="${RK30_PROTOCOL:-${REPO}/configs/a8-rk30-mordstein-matched-context-v1.json}"
: "${RK30_ARTIFACT_ROOT:?Set RK30_ARTIFACT_ROOT to the verified RK30 artifact directory}"
export RK30_PROTOCOL
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export PYTHONPATH="${REPO}/scripts${PYTHONPATH:+:${PYTHONPATH}}"
cd "${REPO}"

"${PYTHON}" scripts/a8_rk30_test_freeze.py
"${PYTHON}" scripts/a8_rk30_test_model.py

if [[ "${RK30_RUN_PRODUCTION:-0}" == "1" ]]; then
  "${PYTHON}" scripts/a8_rk30_fixed_reference_counts.py \
    --protocol "${PROTOCOL}" \
    --freeze-report "${RK30_ARTIFACT_ROOT}/RK30_LABEL_FREE_FREEZE.json" \
    --output-root "${RK30_ARTIFACT_ROOT}" \
    --workers "${RK30_COUNT_WORKERS:-8}"
  "${PYTHON}" scripts/a8_rk30_run_matched_context.py \
    --protocol "${PROTOCOL}" \
    --freeze-report "${RK30_ARTIFACT_ROOT}/RK30_LABEL_FREE_FREEZE.json" \
    --artifact-root "${RK30_ARTIFACT_ROOT}" \
    --summary "${RK30_ARTIFACT_ROOT}/RK30_MODEL_SUMMARY.json"
fi

"${PYTHON}" scripts/a8_rk30_verify_raw_counts.py \
  --protocol "${PROTOCOL}" --artifact-root "${RK30_ARTIFACT_ROOT}" \
  --report "${RK30_ARTIFACT_ROOT}/RK30_RAW_VERIFICATION.json"
"${PYTHON}" scripts/a8_rk30_verify_model.py \
  --protocol "${PROTOCOL}" --artifact-root "${RK30_ARTIFACT_ROOT}" \
  --production-summary "${RK30_ARTIFACT_ROOT}/RK30_MODEL_SUMMARY.json" \
  --report "${RK30_ARTIFACT_ROOT}/RK30_MODEL_INDEPENDENT.json"
"${PYTHON}" scripts/a8_rk30_closeout.py \
  --protocol "${PROTOCOL}" --artifact-root "${RK30_ARTIFACT_ROOT}"

"${PYTHON}" - <<'PY'
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

repo = Path.cwd()
root = Path(os.environ["RK30_ARTIFACT_ROOT"]).resolve()
paths = [Path(os.environ["RK30_PROTOCOL"]).resolve()]
paths += [repo / "scripts" / name for name in [
    "a8_rk30_download_hela_r1.py", "a8_rk30_spool_transfer.py", "a8_rk30_fixed_reference_counts.py",
    "a8_rk30_run_matched_context.py", "a8_rk30_test_freeze.py",
    "a8_rk30_test_model.py", "a8_rk30_verify_raw_counts.py",
    "a8_rk30_verify_model.py", "a8_rk30_closeout.py", "a8_rk30_integrate_manuscript.py", "a8_rk30_reproduce.sh",
]]
paths += [root / name for name in [
    "RK30_COUNTING.json", "RK30_MODEL_SUMMARY.json", "RK30_RAW_VERIFICATION.json",
    "RK30_MODEL_INDEPENDENT.json", "RK30_CLOSEOUT.json", "RK30_RESULTS_FOR_PPT.json",
]]
def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()
manifest = {
    "status": "PASS_RK30_CLEAN_CHECKOUT_REPRODUCTION",
    "completed_utc": datetime.now(timezone.utc).isoformat(),
    "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "git_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
    "python": os.environ.get("RK30_PYTHON", "/home/codonflow-clean-env-v1/bin/python"),
    "threads": 1,
    "production_rerun": os.environ.get("RK30_RUN_PRODUCTION", "0") == "1",
    "artifact_root": str(root),
    "sha256": {str(p): sha(p) for p in paths if p.is_file()},
}
(root / "RK30_REPRODUCTION_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps({"status": manifest["status"], "git_head": manifest["git_head"], "git_dirty": manifest["git_dirty"]}, indent=2))
PY
