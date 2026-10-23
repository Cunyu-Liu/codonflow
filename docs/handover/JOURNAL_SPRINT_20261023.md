# CodonFlow 冲刺期运行日志（双集群 · 2026-10-23 起）

> 纪律：每次训练/评测 run 记录在此 + REGISTRY.md；结论必须写证据位置；诚实记录负结果。
> 集群A = 5090 32GB（ssh -p 28365，训练主力）；集群B = 4090 24GB（ssh -p 28055，评测机）。
> 本文件在本地维护，同步副本在集群A /home/codonflow/docs/handover/。

---

## 2026-10-24 凌晨（W3 图表重制 + 双集群推进）

### 训练与评测进度（00:30 快照）

- **355M e16 即将落盘**（b18900/18943，236.5min）——watchdog 将自动继续 e17；plateau 计数待 e17-e19 观察（e13 最优 2.7921 为锚）。
- v3rloo 评测 **8/17**（8 旧 + egfp_s1 新完成：cf done 9069s，2.5h 符合预期）：
  - 集群A rloo_c0：egfp_s1 ✓ → nluc_s0 运行中
  - 集群B rloo_c1：egfp_s2 S2 dir3；rloo_c2：mouse_s0 S2 dir1
- GPU：集群A 27.6GB/100%（训练+评测共存）；集群B ~20GB（双评测链）。

### W3.1 主图重制（7 张全部完成，house style）

统一视觉系统：CodonFlow=蓝 #0F4D92 / LinearDesign=红 #B64342 / codonGPT=teal / CAI-greedy=violet / uniform=neutral / GEMORNA=绿；Helvetica 15pt、spine 2.0、无顶右边框、legend 无框、PDF(矢量)+PNG(300dpi) 双输出、Type 42 字体（期刊可编辑）。

| 图 | 主张（一句话） | 数据源 | 校验 |
|---|---|---|---|
| fig1 塌缩 | masking 在引导之前就塌多样性 | E1_codongpt.json（50 样本/arm 真实 NED/熵/CAI） | PASS 3349×1340 |
| fig2 门控vs过滤 | 同预算下门控买到可行性+首达效率 | E2_gated_vs_filter.json（3 seeds + Wilcoxon p=6.1e-5 面板） | PASS |
| fig4 消融 | 单奖励反噬在密码子域复现（等权双优） | E4_ablation_3seed.json（18 arm 3 seeds 聚合） | PASS |
| fig5 主表 | 五方法×三场景；100% 保证脚注+绝对差距如实 | E5v2conv_main_table.json | PASS 3871×1690 |
| fig6 预算 | 中间档性价比拐点（12 配置网格） | E6_budget_curves.json（best value/call 标注） | PASS |
| fig10 容量 | 4× 数据在 56M 上饱和；355M 打开新档 | capacity_curves.json（355M 收敛点待补） | PASS |
| fig11 RLOO | RL 增益随预训练充分度衰减（6 arm 初版，15 arm 终版待 17/17） | S3R2_full_adaptive.json | PASS |

- 全部脚本本地 fig_batch_v2.py / fig_batch2_v2.py / fig10_capacity_v2.py / fig11_rloo_gain.py；已同步集群A figures_src/。
- **GitHub 7e72206**（figures v2 commit，走 patch→本地代理推送流）。
- 程序化校验：分辨率 >2000px、非空白率 0.06–0.39（每张独立阈值检查）——不靠目测靠数据。

### 待续

- e16 落盘 → log.jsonl 追加 → fig10 数据自动可补（capacity_curves.json 由 auto_trigger 或巡检更新）
- v3rloo 剩 9 arm（nluc_s0 + fly×4 + mouse×3 + egfp_s2）预计 ~20h
- 355M 评测链待收敛触发（巡检任务提示人工启动，串行 c3→c0→c1→c2→c4）

---

## 2026-10-23 深夜（双集群并行 + W2 推进）——存档摘要

- 集群B 接入验收（环境现成 torch cuda OK + pytest 41/41）；rloo_c1/c2 链拉起；GitHub a1e9326。
- W2.2/W2.3 完成：S3R2_full_adaptive.json（39 arm per-gene adaptive ref 重算；g08 零域修复验证）；S3R3_cas9_norm.json（Cas9 motif 长度归一化）。
- RLOO 初步裁决（6 arm，adaptive 口径）：无正向增益（2/6 正、均值 −5.3%）——A4 条件性结论待 17/17 终裁。
- 数据自检 9 项全 PASS（862k md5 复验一致 / 三重泄漏审计 0 / 四层 benchmark / 5 基线+2 补强）。

## 2026-10-23 恢复日——存档摘要

- 集群A 环境重建：conda codonflow + torch 2.14.1+cu132（**RTX 5090 sm_120 与 cu126 不兼容事故**：is_available True 但 matmul 报 no kernel image——静默降级陷阱，重装 cu132 后实测 OK）+ ViennaRNA 2.7.2 + pytest 41/41。
- 355M 续训拉起（watchdog v8-5090：batch 20000×3 = 26.5GB/100%util，比 4090 快 37%；28000 OOM 留证回退）。
- 交接文档三件套更新（spec A4 / tasks v5 / checklist J）+ GitHub 6dda1fa。
- fig10 house-style 首张。
