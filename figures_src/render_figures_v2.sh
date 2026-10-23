#!/bin/bash
# 集群侧批量重渲染全部 v2 图（数据路径指向 /teams eval_outputs，与本地 fig_data 对应）
# 用法: bash render_figures_v2.sh   （在 /home/codonflow 下执行）
set -u
PY=/root/miniconda3/envs/codonflow/bin/python
cd /home/codonflow
E=/teams/HoulabData_1788502323/liucunyu/codonflow
OUT=$E/codonflow/eval_outputs/figures_v2
OLD=$E/eval_outputs          # 原备份全集（E1/E2/E4/E5v2/E6 历史评测 JSON）
mkdir -p $OUT /tmp/fig_data

# 1. 准备 fig_data/（脚本期望的相对路径）：把所需 JSON 链接/拷贝到 /tmp/fig_data + cwd
for f in E1_codongpt.json E2_gated_vs_filter.json E3_preference_scan_rloov4.json \
         E4_ablation_3seed.json E5v2conv_main_table.json E5v4s1_main_table.json \
         E5v4s2_main_table.json E6_budget_curves.json; do
  if [ -s $OLD/$f ]; then cp -f $OLD/$f /tmp/fig_data/; fi
done
cp -f $E/codonflow/eval_outputs/S3R2_full_adaptive.json /tmp/ 2>/dev/null

# 2. 逐图渲染（fig_batch* 期望 cwd 有 fig_data/ 与 S3R2；输出 figures_v2/）
( cd /tmp && PYTHONPATH=src $PY /home/codonflow/figures_src/fig_batch_v2.py 2>&1 | grep saved )
( cd /tmp && PYTHONPATH=src $PY /home/codonflow/figures_src/fig_batch2_v2.py 2>&1 | grep saved )
( cd /tmp && PYTHONPATH=src $PY /home/codonflow/figures_src/fig11_rloo_gain.py /tmp/S3R2_full_adaptive.json /tmp/figures_v2/fig11_rloo_gain 2>&1 | grep saved )
( cd /tmp && PYTHONPATH=src $PY /home/codonflow/figures_src/fig10_capacity_v2.py $E/figures_src/data/capacity_curves.json /tmp/figures_v2/fig10_capacity 2>&1 | grep saved )

# 3. 汇总到 /teams
cp -f /tmp/figures_v2/* $OUT/ 2>/dev/null
ls -la $OUT/
echo RENDER_DONE
