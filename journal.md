
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

## 2026-10-07 (E5 3-seed 启动+吞吐危机处理+首个 seed 完成)

**E5 3-seed 三路并行教训**:
- 三路 12h+ 仍 1/6 —— 集群 load 187 下 MFE worker (34x3) 互相拖死
- 处置: 杀 s1/v2conv 保 s2 独占, s2 3h 完成剩余 (单路吞吐恢复)
- E5s2 完成: 3 seeds x 2 fams 完整

**E5s2 (最强 seed, E4 HV 5.18) vs E5v3 (rloo-v4 s0) codonflow HV**:
- S2_cai_mfe: egfp 48.6 vs 35.0 (+39%), nluc 35.0 vs 22.7 (+54%)
- S3_quad: egfp 204.4 vs 107.8 (+90%), nluc 169.5 vs 82.2 (+107%)
- S1_cai: 0.33 vs 0.31 (单目标 DP 仍领先: gpt 0.41, ld 0.36, 符合预注册预期)
- LD-scan 仍最强 (4目标专用优化器), codonflow 已达 codongpt 2/3-1/2

**进行中**: E5s1 夜间重跑 (23:20 起); E5v2conv 排队其后

## 2026-10-09 上午 (E5 3-seed 全链完成 — 里程碑)

**E5 场景主表 3-seed 定稿** (codonflow HV, mean±std, 3 seeds):
- egfp S2: v4s0 34.96±1.36 | v4s1 34.57±1.36 | v4s2 48.62±1.88 | v2conv 37.08±0.67
- egfp S3: v4s0 107.79±4.16 | v4s1 120.96±9.11 | v4s2 204.36±13.47 | v2conv 127.40±16.56
- nluc S2: 22.66±1.11 | 23.17±1.82 | 34.95±1.05 | 26.62±1.62
- nluc S3: 82.18±5.70 | 86.68±3.47 | 169.53±3.23 | 98.41±8.53
- 基线: gpt S3 egfp 307 / nluc 190; LD-scan 558 / 410

**诚实报告要点**:
1. v4s2 是异常强 seed (S3 204 vs 兄弟 seed 121/108) — seed 间方差 >> seed 内方差, 论文须报告 3 seeds 全分布而非只报最优
2. v2conv (纯预训练无 RL) 127/98 超过 2/3 的 RL seeds — 基座质量是根本, RL 增益依赖基座可挖空间
3. LD-scan 仍领先 (专用优化器), codonflow 定位: 学习式方法中领先 (超 codongpt 一半), 且提供多样性 (NED 0.22 vs codongpt 0.21)

**吞吐经验固化**: E5 单路 ~6块×(1-13h), 三路并行在高 load 下互相拖死 (MFE worker 抢核), 串行+夜间窗口是正解; ref-point 边界须先冒烟再批跑

## 2026-10-09 晚 (交接审计 + E5 协议修复 + OOD 补齐启动)

**交接审计（第 3 遍全链路检查）发现的问题与处置**:
1. E5 v1 协议 handicap（叙事⑤断链的机制根因）: codonflow 臂每场景单 ω 采样 100 解（同质化），而 LD-scan 用 7-λ 扫描、codonGPT 用随机采样自然铺开——HV 奖励前沿覆盖，我方被协议自身压低。修复: run_exp5_ood.py 的 codonflow 臂改 ω-direction scan（S2 5 方向 / S3 7 方向，每方向 100/k 解，总预算 100 不变）——与基线同等"前沿覆盖协议类"，消除协议不对称
2. OOD 表（checklist E7/R7-2）从未跑: 5 家族 bench_plus_ood 存在但 E5 只在 egfp/nluc 出表 → 本次 4 路并行补齐（in-family 2 + OOD 3 + SpCas9 长序列探针 4107nt）
3. data/README.md 数据溯源缺口（B1 未勾选）: 已补全 13 条数据集登记（URL/日期/条数/sha256 前缀），并如实记录"语料 215k vs spec 目标 1M"偏差 + 扩语料列为下一步首位
4. transformers 5.18 + torch 2.5.1 兼容性: codonGPT ckpt 转存 model.safetensors（修复 CVE 检查导致 torch.load 被拒）；tokenizer 改 from_pretrained + vocab_size=67
5. 实现细节修复: cai_greedy 从 run_exp5.py 拷贝定义（core.codon 无此函数）; synonymous_x0 的 rng 持久化（避免 x0 重复 seed 退化解集多样性）

**E5' + OOD 四路并行启动（18:35, GPU6 MIG 1g.5gb x4 空闲实例占满）**:
- arm1 egfp / arm2 nluc（in-family 基准，v2conv 基座）
- arm3 ood12（mouse 1905nt + fly 1179nt）/ arm4 ood3+spcas9（zfish 465nt + Cas9 4107nt 长探针）
- 每路 100 解 x 3 seeds x 3 场景（S1/S2/S3），监控脚本 scripts/e5ood_monitor.sh + e5ood_watch.log
- 冒烟已通过（egfp 10 解全链路 ~17min，identity/legal 100%）

**预期产出（写入 gate_C 前的最后补数）**: E5' 公平协议主表 + OOD generalization gap 表（identity/legal 衰减 <2pp 判定线）+ Cas9 长序列可行性证据（叙事⑥成本维度补强）

## 2026-10-10 凌晨 (E5' 协议公平版 3-seed 完成: egfp + nluc 全部落盘)

**E5' (protocol-fair, codonflow 臂 ω-scan) 3-seed 结果 (v2conv 基座, 100 解/场景/seed)**:

| 场景 | codonflow E5' | E5v1 | 变化 | gpt | LD-scan | identity/legal |
|---|---|---|---|---|---|---|
| egfp S2 | 40.36±1.92 | 37.08 | +8.8% | 65.5 | 124.1 | 100%/100% |
| egfp S3 | 125.15±9.69 | 127.40 | -1.8% (seed 方差内) | 307.4 | 558.3 | 100%/100% |
| nluc S2 | 26.82±2.75 | 26.62 | +0.8% | 43.2 | 93.1 | 100%/100% |
| nluc S3 | 102.62±0.60 | 98.41 | +4.3% | 189.9 | 410.4 | 100%/100% |

**诚实结论 (写入叙事⑤修订)**:
1. 协议公平化在 S2 提升明确 (+8.8% egfp / +4.3% nluc S3), S3 egfp 在 seed 方差内持平——协议 handicap 是真实存在但幅度有限
2. 残余差距 (vs LD-scan 558 vs 125) 的主因不是协议, 是基座质量: 56.8M 模型在 215k 语料上的容量/数据上限 (v2conv 纯预训练 S3 127 已超 RLOO-v4 均值 108-121, 佐证)
3. LD-scan 作为"DP 专用优化器"上界定位不变; codonflow 站位: 学习式方法第二梯队 (超 uniform 30%, 落后 gpt 一半), 与 codongpt 差距 2.4-2.5x
4. 全部红线保持: identity 100%, legal 100% (E5' 两家族 x 3 seeds x 3 场景 x 100 解 = 1800 解零违例)

**工程耗时记录**: egfp 单 seed cf 臂 24000-24500s (~6.8h, 67600 folds, 5.9 folds/s 受 CPU 竞争), nluc 13140s; 四路并行 + seed 拆分后总 wall-clock 7.5h 覆盖 6 arm-seeds + ood3/cas9 在跑

## 2026-10-10 下午 (图表全面重设计 + PPT 升级 + Cas9 arch-limit 发现)

**图表重设计 (plot-is-all-you-need skill, 顶刊风格)**:
- 8 张图全部重绘 (fig1-fig8): serif 字体 + navy/steel/red 色系 + 红框高亮主角 + 面板内 metric box + 配对哑铃图 + 中位数徽章; 300dpi PNG + 矢量 PDF 双格式
- 每张图带诚实负结果标注 (EXP-3 轴向弱、EXP-6 低预算 RL 略输、E5' 协议公平化的有限提升)
- 新增 fig7 (pipeline+四大核心数字一页图) + fig8 (AR 1024 密码子墙: 长度阶梯图 + O(n^3) 折叠成本)
- PPT 29 页: 6 张旧图替换 + 2 新页; 字体统一 Microsoft YaHei, 程序化检查通过

**Cas9 探针的意外发现 (论文新论点)**:
- codonGPT (GPT-2 架构, 1024 位置) 在生成 SpCas9 (1368 aa) 时第 1024 个密码子触发 CUDA device-side assert —— AR 生成器架构上无法产 >1023 aa 蛋白
- 编辑式 CodonFlow 直接改写源序列无位置限制 —— 长治疗性蛋白 (Cas9/vaccine抗原/基因治疗 ORF) 唯一的学习式方法路线
- 已修复脚本: codongpt 臂遇 >1024 密码子自动 SKIP 并记录 arch limit; 每个 seed 完成即增量写 JSON (防中途崩溃丢数据)

**进行中**: ood3 (mouse/fly/zfish OOD 3-seed, cf 臂 ETA ~17:00); cas9 (seed0 cf 完成于 17645s, 正跑 seed1+LD 基线)

## 2026-10-11 中午 (Cas9 3-seed 定稿: 长序列正面证据 + PPT 29 页更新)

**Cas9 长序列探针 3-seed 最终结果 (缩减预算 20 sols, steps=5, C=5, 全方法同预算)**:
- S1: cf 0.3 (greedy 0.5, LD 0.4) — 单目标 DP/greedy 领先如预注册预期
- S2: cf 251.7±2.3 (LD 889.6, greedy 586.2, uniform 260.2) — LD DP 最优在 4.1kb 上依然统治双目标
- **关键新证据: wall-clock cf 310 s/sol vs LD 510 s/sol (0.61x) —— 长序列上 DP 变慢, 编辑式反而更快** (叙事⑥的直接加强: 成本竞争力在长序列反转)
- 身份/合法率 100% (3 seeds x 60 解零违例)
- S3 motif 轴 ref-point 尺度 bug 确诊: 随机 4107nt 变体罚 63-82 vs 固定参考点 -25 → HV 归零. 这是评估器 bug 非模型失败 (greedy 罚 11 在 ref 内). 论文处理: Cas9 报 S1/S2 + S3 用长度归一化 motif 罚重算 (v3 待办), 如实文档化
- codonGPT: arch limit (1024 位置) 跳过并记录 —— 见 fig8

**PPT 29 页终版**: 6 张旧图替换为顶刊风格新图 + fig7 pipeline 总览页 + fig8 arch-limit 页 (已更新 Cas9 实测数字); 字体统一; 程序化检查通过 (29 slides, 8 pics, 0 font issues)

**剩余**: ood3 (mouse seed0/1 cf done 66870s/59155s; fly/zfish 在跑; 全部完成 ETA ~今晚); 完成后出 OOD generalization gap 表 + PPT 最后一页
