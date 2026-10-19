#!/bin/bash
# Monitor ATC-fix wave1: log tail + JSON completion + dead-arm detection
LOG=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/logs
OUT=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs
echo "=== $(date) ==="
echo "--- tmux chains alive:"; tmux ls 2>/dev/null | grep atx | wc -l
echo "--- progress:"
for f in $(ls $LOG/e5o_*_fix.log $LOG/e3_fix_*.log 2>/dev/null); do
  tag=$(basename $f .log)
  last=$(tail -1 $f)
  done_line=$(grep -c "EXIT=" $f)
  cf_line=$(grep "cf done" $f | tail -1)
  echo "  $tag | exits=$done_line | $cf_line"
done
echo "--- fix JSONs done:"
ls -la $OUT/E5_fix_*.json $OUT/E3_fix_*.json 2>/dev/null | wc -l
ls $OUT/E5_fix_*.json $OUT/E3_fix_*.json 2>/dev/null
echo "--- dead without exit:"
for f in $(ls $LOG/e5o_*_fix.log $LOG/e3_fix_*.log 2>/dev/null); do
  if ! grep -q "EXIT=" $f && ! tmux ls 2>/dev/null | grep -q $(basename $f .log | sed "s/e5o_/atx_/;s/_fix//;s/e3_fix_/atx_/"); then
    proc_alive=$(ps -eo args | grep -c "[r]un_exp5_ood.*$(echo $(basename $f .log) | sed "s/e5o_//;s/_fix//")")
    :
  fi
done
