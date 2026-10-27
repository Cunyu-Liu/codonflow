#!/bin/bash
# 巡检守护循环：每 30min 检查评测链健康。日志写 artifacts；Git 仅验收后提交。
set -u
EV=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs
LG=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/logs
LOG=$LG/patrol_loop.log
cd /home/codonflow
log(){ echo "$(date "+%F %T") $*" >> "$LOG"; }
log "patrol_loop start"

SEEN_355M=0; SEEN_RLOO=13
while :; do
  N355=$(ls $EV 2>/dev/null | grep -cE "v3_355m|V3355m")
  NRLOO=$(ls $EV 2>/dev/null | grep -c "E5_v3rloo56m")
  [ "$N355" -gt "$SEEN_355M" ] || [ "$NRLOO" -gt "$SEEN_RLOO" ] && {
    log "progress: 355m=$N355/35 rloo=$NRLOO/17"
    SEEN_355M=$N355; SEEN_RLOO=$NRLOO
    log "progress recorded; Git commit deferred to scientific review"
  }
  # 死链检测与重启
  for s in eval355_c0 eval355_c1 eval355_c2 eval355_c3 held18_355m rloo_backfill rloo_fly_s2 v3ev_v3_355m_serial; do
    tmux has-session -t $s 2>/dev/null || { log "dead session $s - not auto-relaunching (check manually)"; }
  done
  # 里程碑触发：rloo 17/17 齐即跑 RLOO 裁决（一次性）
  if [ "$NRLOO" -ge 17 ] && [ ! -f "$LG/.rloo_verdict_done" ]; then
    log "rloo 17/17 reached: running joint-reference diagnostic"
    /root/miniconda3/envs/codonflow/bin/python scripts/recompute_s3_full_adaptive.py \
      --model-tags E5_v3_56m E5_v3rloo56m \
      --out "$EV/audits_20261026/legacy_rloo_joint_hv.json" > "$LG/verdict_snapshot_rloo17.log" 2>&1 && \
    /root/miniconda3/envs/codonflow/bin/python scripts/verdict_355m_and_rloo.py \
      --report "$EV/audits_20261026/legacy_rloo_joint_hv.json" \
      --out "$EV/audits_20261026/legacy_rloo_verdict.json" >> "$LG/verdict_snapshot_rloo17.log" 2>&1 && \
    touch "$LG/.rloo_verdict_done"
    log "rloo diagnostic finished; see verdict_snapshot_rloo17.log"
  fi
  # 完成检测
  [ "$NRLOO" -ge 17 ] && [ "$N355" -ge 35 ] && {
    log "ALL DONE 35/35 + 17/17: final verdict"
    /root/miniconda3/envs/codonflow/bin/python scripts/recompute_s3_full_adaptive.py \
      --model-tags E5_v3_56m E5_v3_355m \
      --out "$EV/audits_20261026/legacy_capacity_joint_hv.json" > "$LG/verdict_final.log" 2>&1 && \
    /root/miniconda3/envs/codonflow/bin/python scripts/verdict_355m_and_rloo.py \
      --report "$EV/audits_20261026/legacy_capacity_joint_hv.json" \
      --out "$EV/audits_20261026/legacy_capacity_verdict.json" >> "$LG/verdict_final.log" 2>&1
    log "legacy evaluation chains complete; see verdict_final.log"
    break
  }
  sleep 1800
done
log "patrol_loop exit"
