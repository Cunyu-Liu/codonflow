#!/bin/bash
# 巡检守护循环：每 30min 检查评测链健康 + 自动 journal/git。集群常驻。
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
    if [ "$N355" -ne "$SEEN_355M" ] || true; then
      echo "" >> journal.md
      echo "## $(date "+%F %H:%M") (patrol): eval progress 355m=$N355/35 rloo=$NRLOO/17" >> journal.md
      git add journal.md >/dev/null 2>&1
      git commit -m "journal(patrol): eval progress 355m=$N355 rloo=$NRLOO" >/dev/null 2>&1
      git push origin HEAD >/dev/null 2>&1
    fi
  }
  # 死链检测与重启
  for s in eval355_c3 eval355_c4 held18_355m; do
    tmux has-session -t $s 2>/dev/null || { log "dead session $s - not auto-relaunching (check manually)"; }
  done
  # 完成检测
  [ "$NRLOO" -ge 17 ] && [ "$N355" -ge 35 ] && { log "ALL DONE 35/35 + 17/17"; break; }
  sleep 1800
done
log "patrol_loop exit"
