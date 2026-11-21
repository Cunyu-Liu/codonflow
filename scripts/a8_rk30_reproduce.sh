#!/usr/bin/env bash
# Reproduce RK30 verification from a clean checkout without moving large assets into Git.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${RK30_PYTHON:-/home/codonflow-clean-env-v1/bin/python}"
PROTOCOL="${RK30_PROTOCOL:-${REPO}/configs/a8-rk30-mordstein-matched-context-v1.json}"
: "${RK30_ARTIFACT_ROOT:?Set RK30_ARTIFACT_ROOT to the RK30 output artifact directory}"
FREEZE_REPORT="${RK30_FREEZE_REPORT:-${RK30_ARTIFACT_ROOT}/RK30_LABEL_FREE_FREEZE.json}"
export RK30_PROTOCOL
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export PYTHONPATH="${REPO}/scripts${PYTHONPATH:+:${PYTHONPATH}}"
cd "${REPO}"

"${PYTHON}" -m pytest -q scripts/a8_rk30_test_freeze.py
"${PYTHON}" -m pytest -q scripts/a8_rk30_test_model.py
"${PYTHON}" -m pytest -q scripts/a8_rk30_test_raw_verifier.py

if [[ "${RK30_RUN_PRODUCTION:-0}" == "1" ]]; then
  "${PYTHON}" scripts/a8_rk30_fixed_reference_counts.py \
    --protocol "${PROTOCOL}" \
    --freeze-report "${FREEZE_REPORT}" \
    --output-root "${RK30_ARTIFACT_ROOT}" \
    --workers "${RK30_COUNT_WORKERS:-8}"
  "${PYTHON}" scripts/a8_rk30_run_matched_context.py \
    --protocol "${PROTOCOL}" \
    --freeze-report "${FREEZE_REPORT}" \
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

if [[ "${RK30_RUN_PRODUCTION:-0}" == "1" && "${RK30_REPRODUCTION_COMPARE:-0}" == "1" ]]; then
  : "${RK30_PRODUCTION_ARTIFACT_ROOT:?Set the separate production artifact root for equivalence comparison}"
  "${PYTHON}" scripts/a8_rk30_compare_reproduction.py \
    --production-root "${RK30_PRODUCTION_ARTIFACT_ROOT}" \
    --reproduction-root "${RK30_ARTIFACT_ROOT}" \
    --output "${RK30_ARTIFACT_ROOT}/RK30_REPRODUCTION_COMPARISON.json"
  "${PYTHON}" scripts/a8_rk30_integrate_manuscript.py \
    --protocol "${PROTOCOL}" \
    --artifact-root "${RK30_ARTIFACT_ROOT}" \
    --manuscript "${REPO}/paper/CodonFlow_preprint_A8.md" \
    --output "${RK30_ARTIFACT_ROOT}/CodonFlow_preprint_A8.reproduced.md" \
    --report "${RK30_ARTIFACT_ROOT}/RK30_MANUSCRIPT_INTEGRATION.json"
fi

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
    "a8_rk30_test_model.py", "a8_rk30_test_raw_verifier.py", "a8_rk30_verify_raw_counts.py",
    "a8_rk30_verify_model.py", "a8_rk30_closeout.py", "a8_rk30_integrate_manuscript.py",
    "a8_rk30_compare_reproduction.py", "a8_rk30_ppt_page.py", "a8_rk30_reproduce.sh",
]]
paths += [root / name for name in [
    "RK30_COUNTING.json", "RK30_MODEL_SUMMARY.json", "RK30_RAW_VERIFICATION.json",
    "RK30_MODEL_INDEPENDENT.json", "RK30_CLOSEOUT.json", "RK30_RESULTS_FOR_PPT.json",
    "RK30_REPRODUCTION_COMPARISON.json", "RK30_MANUSCRIPT_INTEGRATION.json",
    "CodonFlow_preprint_A8.reproduced.md",
]]
def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()
production_rerun = os.environ.get("RK30_RUN_PRODUCTION", "0") == "1"
comparison_requested = os.environ.get("RK30_REPRODUCTION_COMPARE", "0") == "1"
git_dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())
comparison_path = root / "RK30_REPRODUCTION_COMPARISON.json"
comparison = json.loads(comparison_path.read_text()) if comparison_path.is_file() else None
comparison_pass = bool(comparison and comparison.get("status") == "PASS_RK30_PRODUCTION_REPRODUCTION_EQUIVALENCE")
if not production_rerun:
    status = "PASS_RK30_VERIFICATION_ONLY"
elif not comparison_requested:
    status = "PASS_RK30_PRODUCTION_RUN"
elif not comparison_pass:
    status = "FAIL_RK30_REPRODUCTION_COMPARISON_MISSING"
elif git_dirty:
    status = "PASS_RK30_RERUN_DIRTY_CHECKOUT"
else:
    status = "PASS_RK30_CLEAN_CHECKOUT_REPRODUCTION"
manifest = {
    "status": status,
    "completed_utc": datetime.now(timezone.utc).isoformat(),
    "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "git_dirty": git_dirty,
    "python": os.environ.get("RK30_PYTHON", "/home/codonflow-clean-env-v1/bin/python"),
    "threads": 1,
    "production_rerun": production_rerun,
    "comparison_requested": comparison_requested,
    "production_reproduction_equivalence_pass": comparison_pass,
    "artifact_root": str(root),
    "sha256": {str(p): sha(p) for p in paths if p.is_file()},
}
(root / "RK30_REPRODUCTION_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps({"status": manifest["status"], "git_head": manifest["git_head"], "git_dirty": manifest["git_dirty"]}, indent=2))
PY
