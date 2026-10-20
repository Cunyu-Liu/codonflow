#!/bin/bash
# auto-trigger 2026-10-20: HELD18 18/18 -> v3rloo chain + summary; 355M converge -> full eval; epoch -> journal+git
set -u
PY=/root/miniconda3/envs/codonflow/bin/python
EV=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs
CK=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/checkpoints
LG=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/logs
cd /home/codonflow
STATE=/tmp/auto1020_state
mkdir -p $STATE
log(){ echo "$(date '+%F %T') $*" >> $LG/auto1020.log; }

seen_jsonl=$(wc -l < $CK/p3_v3_355m/log.jsonl 2>/dev/null || echo 0)
log "start: log.jsonl lines=$seen_jsonl"

while :; do
  n=$(wc -l < $CK/p3_v3_355m/log.jsonl 2>/dev/null || echo 0)
  if [ "$n" -gt "$seen_jsonl" ]; then
    seen_jsonl=$n
    rec=$(tail -1 $CK/p3_v3_355m/log.jsonl)
    {
      echo ""
      echo "## 2026-10-20 auto: 355M epoch $n landed"
      echo '**355M log.jsonl 新记录**: '$rec
      echo "- (自动记录: 训练曲线截至 e$n; 若 val 持续高于 e3 2.8350, e3 backup 仍为最优)"
    } >> /home/codonflow/journal.md
    git add journal.md >/dev/null 2>&1
    git commit -m "journal(auto): 355M epoch $n landed: $rec" >/dev/null 2>&1
    git push origin HEAD >/dev/null 2>&1
    log "epoch $n journaled+pushed"
  fi

  if [ ! -f $STATE/h18_done ] && [ "$(ls $EV | grep -c HELD18_V356m_)" -ge 18 ]; then
    touch $STATE/h18_done
    log "HELD18 18/18 reached: launching v3rloo eval chain (serial)"
    bash /home/codonflow/scripts/run_v3_eval_rloo.sh p3_rloo_v3_56m_eval v3rloo56m launch >> $LG/auto1020.log 2>&1
    {
      echo ""
      echo "## 2026-10-20 auto: HELD18 v3 18/18 complete + v3rloo eval chain launched"
      echo '**HELD18_V3 全表 (codonflow 臂, 几何平均 + 长度分层)**:'
      $PY /home/codonflow/scripts/held18_v3_vs_v2_summary.py
    } >> /home/codonflow/journal.md
    git add journal.md >/dev/null 2>&1
    git commit -m "journal(auto): HELD18 v3 18/18 full table (geomean+length bins), v3rloo chain launched" >/dev/null 2>&1
    git push origin HEAD >/dev/null 2>&1
    log "HELD18 summary journaled+pushed"
  fi

  if [ ! -f $STATE/conv_done ] && [ -f $CK/p3_v3_355m/converged.pt ]; then
    touch $STATE/conv_done
    log "355M converged.pt found: launching run_v3_eval.sh full chain"
    bash /home/codonflow/scripts/run_v3_eval.sh p3_v3_355m v3_355m launch >> $LG/auto1020.log 2>&1
    {
      echo ""
      echo "## 2026-10-20 auto: 355M converged.pt 出现, 全量评测链已启动 (run_v3_eval.sh p3_v3_355m v3_355m launch)"
      cat $CK/p3_v3_355m/converged.json 2>/dev/null
    } >> /home/codonflow/journal.md
    git add journal.md >/dev/null 2>&1
    git commit -m "journal(auto): 355M converged, full eval chain launched" >/dev/null 2>&1
    git push origin HEAD >/dev/null 2>&1
    log "convergence journaled+pushed"
  fi

  [ -f $STATE/h18_done ] && [ -f $STATE/conv_done ] && break
  sleep 300
done
log "all triggers complete, exit"
