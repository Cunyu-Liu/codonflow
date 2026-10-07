
## 2026-10-06 下午 (refseq 独立性检验 + v2 收敛前夜)

**S4b CAI 表独立性检验（E4_refseq_check.json）**:
- cai_ref_hpa.json == cai_ref_train.json (L1=0，确证 train 复本担忧)
- cai_ref_refseq.json 真独立 (L1=4.07, Spearman 0.943, 差异集中 Arg/Gly)
- RL 优势稳健: v4_equal refseq +0.95 HV (7.31 vs 6.35) ≈ train 表 +1.17 —— RL 结论非 CAI 表 artifact
- 次级发现: v2-ep12 pretrain 在 refseq 表下 CAI 0.728 < v1 0.734 —— v2 学到了 train 语料条件结构（v1 是退化边际），对表更敏感; RL 模型换表最稳 (4.29/4.43)
- v4_equal 与 v4_equal_refseq 两行相同（同 ckpt 同表重跑，确定性 decode 验证可复现）

**v2 pretrain**: epoch 14, val 2.8362, plateau 2/3 —— ep15 判定收敛, watcher 将自动触发 RLOO v5

## 2026-10-06 晚 (v2 收敛 + RLOO v5 自动链完成 + v5 短平台分析)

**v2 腐蚀式预训练 CONVERGED** (18:34):
- 18 epochs, 28.5h, best val 2.8035 @ ep15, cond_gap ~1.5-1.76
- v1 对比: val 4.0611 (边际熵地板), cond_gap 0.031 → 修复幅度 val -1.26, cond_gap ×50

**RLOO v5 自动链触发** (18:34 → 18:37, watcher PID 789895 工作正常):
- 但 17 iters REWARD PLATEAU 停止 (vs v4 111 iters)
- v5 reward 尺度根本不同: -0.70±0.33 (v4: -39.93±0.19)
- 假设: v2 基座逐 token logp 分布改变 → direct reward (lp_ref) 尺度变化

**待判定** (e4_v5_probe 运行中): 
- (a) v2 已达 RL 不可提升的性能饱和 → v5≈v2-conv, RL 章节叙事反转
- (b) v5 训练有 bug → v5 < v2-conv, 需查 RLOO 适配

## 2026-10-06 深夜 (v5 判定: v2 基座上 RL 饱和)

**e4_v5_probe 结果** (egfp / nluc HV):
- pretrain_v2_conv (ep15): 3.84 / 2.44 (sum 6.28)
- rloo_v5 (17 iters):      3.78 / 2.52 (sum 6.30)
- 判定: RL 在 v2 基座上无提升 (Δ ≈ +0.02, 噪声级) → 17-iter plateau 是真实饱和
- 机制: v2 通过腐蚀式训练直接学会了 p(x_t|x_0) 全轨迹条件分布, RL 的 direct-reward (逐 token logp 提升) 可挖空间已被 pretrain 占据

**v2 快照轨迹 (egfp HV)**: ep12: 4.73 → ep15(val 最优): 3.84 → ep18: 待测
- 下游采样质量与 val loss 解耦! checkpoint 选择需以下游 eval 为准 (论文方法学要点)

**叙事总图 (egfp HV)**: v1 3.51 → v4(v1+RL) 4.43 (+0.92) → v2-ep12 4.73 (纯 pretrain 超过 v1+RL) → v5(v2+RL) 3.78 (无增益)
- "RL 修复弱基座, 腐蚀式训练修复根因" —— 两阶段互补叙事成立

## 2026-10-06 夜 (EXP-3 3-seed 完成定论)

**E3_preference_scan_v4s1/v4s2 完成**（14 行/个, 3-seed 齐）:
- balanced 方向增益 3-seed 稳健: egfp MFE {-192.5, -197.5, -221.4} vs v1 -191.0; nluc {-158.1, -161.5, -188.3} vs -153.7
- 方向响应性 cai_only vs mfe_only CAI delta < 0.001 跨 3 seed → omega 控制弱是系统性特征（负发现可报告）
- v4s2 最强 seed（与 E4 的 HV 5.18 一致, 迭代 531 次最多）

**E5 3-seed 重跑启动** (v4s1/v4s2/v2conv 三路, 1g.5gb MIG)

## 2026-10-07 凌晨 (E5 ref-point 崩溃发现+修复)

**E5 3-seed 三路首次运行全部崩溃**于 hypervolume reference-point 守卫 (S2/S3 ref=-mfe 100 但弱解 MFE > -100 即 -mfe < 100 劣于 ref):
- 数学正确做法: 劣于 ref 的点超体积贡献=0, 过滤而非 raise
- 修复 metrics.py: 越界点过滤而非报错; 验证 violation→0.0, normal→1.875
- 5.5h x2 + 4.5h x1 白跑教训: 并行批次前应先单路冒烟 (尤其 ref/边界逻辑)
- E5s1/E5s2/E5v2conv 已全部用修复版重启 (01:35 / 03:05)
- 副作用: 重启后 E5v3 (原版) 与新版 (过滤) 的 HV 不严格可比, 最终表格统一用重跑版
