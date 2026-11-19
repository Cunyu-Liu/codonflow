#!/usr/bin/env bash
set -euo pipefail
cd /home/codonflow-a8-rk
PY=/root/miniconda3/envs/codonflow/bin/python
export PYTHONPATH=/home/codonflow-a8-rk
BASE=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional/mordstein2020
META="$BASE/metadata"
ART="$BASE/recovery_full_v1"
CACHE="$BASE/recovery_full_v1_cache"
AUD=/home/codonflow-a8-rk/audits/20261118/RK02
GATE="$META/hek293_download_finalization_v1.json"
SUMMARY="$AUD/mordstein_recovery_full_summary_v1.json"
IND="$AUD/mordstein_recovery_full_independent_v1.json"
FIN="$AUD/mordstein_recovery_full_finalization_v1.json"
for path in "$SUMMARY" "$IND" "$FIN"; do
  if [[ -e "$path" ]]; then
    printf '{"status":"FAIL","reason":"refuse_to_overwrite_existing_report","path":"%s"}\n' "$path"
    exit 2
  fi
done
for ((i=0; i<5040; i++)); do
  if [[ -f "$GATE" ]] && "$PY" - "$GATE" <<'PY'
import json, sys
try:
    report = json.load(open(sys.argv[1]))
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if report.get("status") == "PASS" and report.get("passed_files") == 16 else 1)
PY
  then
    break
  fi
  if [[ $i -eq 5039 ]]; then
    printf '{"status":"FAIL","reason":"download_finalization_gate_timeout"}\n'
    exit 3
  fi
  sleep 120
done
mkdir -p "$AUD"
"$PY" -m pytest -q scripts/tests/test_a8_rk02_mordstein_reference_recovery.py | tee "$AUD/mordstein_recovery_full_unit_tests_v1.console.log"
"$PY" scripts/a8_rk02_mordstein_reference_recovery.py \
  --metadata "$META/PRJNA596086.read_run.tsv" \
  --raw-root "$BASE/raw" \
  --output "$ART" \
  --max-reads 0 \
  --top-exact 20000 \
  --min-seed 20 \
  --min-variant-support 1000 \
  --max-error 8 \
  --exact-cache "$CACHE" \
  --assignment-cache-max 0 \
  --audit-sample-per-run 200 \
  --audit-seed 20261119
cp "$ART/summary.json" "$SUMMARY"
"$PY" scripts/a8_rk02_verify_mordstein_recovery_v2.py \
  --artifacts "$ART" --scope full --report "$IND"
"$PY" scripts/a8_rk02_finalize_mordstein_recovery.py \
  --artifacts "$ART" --independent "$IND" \
  --tests scripts/tests/test_a8_rk02_mordstein_reference_recovery.py --scope full --report "$FIN"
"$PY" - "$SUMMARY" "$IND" "$FIN" <<'PY'
import json, sys
summary, independent, finalization = [json.load(open(path)) for path in sys.argv[1:]]
assert summary["status"] == "PASS_PENDING_INDEPENDENT_VERIFICATION"
assert independent["status"] == "PASS"
assert finalization["status"] == "PASS"
assert summary["library_recovery_status"] != "SMOKE_PARTIAL_LIBRARY"
print(json.dumps({"status": "PASS_FULL_OBSERVED_END_RECOVERY_VERIFIED",
                  "library_recovery_status": summary["library_recovery_status"],
                  "variants_retained": summary["variants_retained"],
                  "independent": [independent["passed"], independent["total"]],
                  "finalization": [finalization["passed"], finalization["total"]]}))
PY
(
  flock 9
  git add configs/a8_rk02_mordstein_full_protocol_v1.json \
    scripts/a8_rk02_run_mordstein_full.sh \
    "$SUMMARY" "$IND" "$FIN"
  git diff --cached --check
  git commit -m "A8-RK02 close full Mordstein observed-end recovery"
  git push origin a8-rk
) 9>.git/a8-rk02-report.lock
