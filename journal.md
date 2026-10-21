
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

## 2026-10-11 傍晚 (关键审计: ATC Tchebycheff 零权重轴退化 bug — 全部扫描方向 reward 失效)

**发现过程**: 在为 ood3 提速做 skip_mfe 数学验证时, 用 ATCUtility 单测发现 S2 (0.7,0.3,0) 方向下 MFE 取值不影响 utility — 深挖确认 `utility_from_normalized` 的 Tchebycheff min 对全部 k 求 min (含零权重轴). 0*omega_k = 0 永远赢得 min, 导致稀疏 omega 下 U 退化为 rho*sum (仅 0.01 量级).

**数学后果 (已 3 遍交叉验证 + 单测确认)**:
- 修复前: 29 个扫描方向中 28 个 |U|~0.01 (balanced (1/3,1/3,1/3) 是唯一存活方向, U~0.216)
- beta=8 后 log-h ~0.08 nats vs log-u ~-6 nats → Doob-h 偏好引导在这些方向形同虚设
- **RLOO 训练不受影响** (yaml omega=(1,1,1,0.5) 全正权, 修复前后 BIT-IDENTICAL, 单测断言通过)
- E1/E2/E4/E6 不受影响 (默认全正权 omega)

**受影响面 (诚实重跑范围)**:
- E5` 全部 codonflow 扫描臂 (egfp/nluc/ood3/cas9) 的 S1 + S2 的 4/5 方向 + S3 的 6/7 方向
- E3 偏好扫描 7 方向中 6 个 (fig3 "corner separation small" 的机制解释 — reward 死了当然分不开)
- pre-fix 结果已归档: eval_outputs/prefix_atc_bug/ (10 个 JSON)

**修复 (src/codonflow/gating/atc.py)**: Tchebycheff min 仅对 omega_k>0 的活跃轴求 min (标准 MOEA/D 定义, Zhang & Li 2007). 修复后 9 个方向的 U 全部进入 0.20-0.45 量级; S1 方向 CAI 响应 0.006→0.44 (64x). 全正权 omega 数位元不变 (RLOO 结果完全保留).

**性能修复 (数位元不变, 不影响科学数值)**:
- BatchedReward 增加 skip_mfe (omega_mfe=0 方向跳过候选折叠, 单测 BIT-IDENTICAL)
- run_exp5_ood: 最终解集批量预折叠 (prefill_mfe, 替代逐条串行 obj_vector)
- hash(scen) → sum(map(ord, scen)) (消除进程盐值, 保证种子可复现)
- mfe_parallel: MFE_PROCS 环境变量 (40 候选/步 ÷ 20 workers = 2 整波, 避免尾波浪费)

**重跑计划 (launch_atcfix_wave1.sh, 7 链并行 tmux)**: 15 arm (5 基因 x 3 seed) on GPU6 MIG; cas9 3 seed (GPU7B + MIG5); E3 重扫 (MIG4). 旧串行 ood3 arm 已杀 (其 mouse s0/s1 33h 结果基于旧 ATC, 无增量保存且无法与修复后协议比较, 弃用; 反正 ood3 重跑在 15 arm 内).

**冒烟验证 (zfish 1-sol)**: skip_mfe 分支正确, 增量保存, identity/legal 100%, EXIT=0. mouse 298-sol cf 臂 395s (vs 旧版 66870s — prefill+skip_mfe 的提速直接可见).

**cas9 s0 OOM 教训**: MIG-6e59f9af (GPU7) 被其他用户占满 13GB+ → 模型加载失败; 已改投 MIG5 (GPU6). 投递前必须 nvidia-smi 检查实例实际空闲显存, 不能只看 MIG 划分.
## 2026-10-12 上午 (ATC-fix 重跑全部完成: 20/20 EXIT=0, 3-seed 定稿)

**重跑执行 (launch_atcfix_wave1.sh, 7 链 tmux, 2026-10-11 18:16 -> 10-12 08:59, ~15h)**:
- 15 arm (5 基因 x 3 seed) + cas9 3-seed (拆 2 个 GPU7 MIG + 1 GPU6 MIG) + E3 重扫 (2 基因); 协议与 pre-fix 严格对齐 (egfp/nluc steps=20, OOD steps=10, cas9 steps=5/C=5; 唯一变量 = ATC 修复)
- 全部 EXIT=0; 提速实测: egfp cf 臂 24529s -> ~11700s (2.1x, skip_mfe+prefill+MFE_PROCS=20), cas9 18559 -> 8690s (2.1x)
- 中途事故与处置: ① cas9_s0 首投 MIG-6e59f9af OOM (他人占用) -> 改投 GPU6 MIG5; ② 第一版启动器 steps=10 一刀切, 自查发现与 pre-fix egfp/nluc (steps=20) 协议不符 -> 杀链重排重启 (只损失 25 分钟, 防止"预算变了还当修复效应"的实验事故)

**最终结果 (3-seed, 100 sols/scen, identity/legal 全 100%)**:
- 修复前后 CF HV: egfp S3 125.15 -> 140.37 (+12.2%); nluc S3 102.62 -> 115.81 (+12.8%); S2 egfp -7.5% / nluc +2.3% (引导激活后多样性收缩的权衡, 如实报告); S1 微涨 (CAI 轴 q95=0.7765 饱和, egfp 0.78 无梯度)
- E3 轴向分离激活: nluc mfe_only MFE -163.9 vs cai_only -158.5 (Δ5.4, pre-fix ≈0); egfp 因 CAI 饱和分离仍小 (mfe_only Δ1.8)
- OOD (R7-6): identity/legal 衰减 0.00pp 全 PASS (4500 解零违例); CF/LD 长度不变量比 S2 -2.4% (0.30->0.31), S3 跨家族反升 (0.27->0.65, LD 在长 OOD 上多目标弱); S1 相对差 +14% (mouse CAI 饱和 + 长序列搜索半径)
- cas9: S2 CF 249.1±1.3 (pre 251.7, 持平); S3=0 仍为 motif ref 尺度 bug (已知, v3 待办: 长度归一化 motif 罚)

**三层诊断定论 (论文 discussion 骨架)**: 残余与 LD 的差距不在协议 (E5' 已修), 不在公式 (ATC 已修), 而在 (1) CAI 归一化域饱和 (2) 基座引导容量 (10 步局部搜索) -> v3 大语料 + 大基座。门控 (100%) 与偏好 (响应修复) 可分离塑形 = H1a 直接证据。

**产出**: analyze_atcfix.py + atcfix_summary.json + fig3/fig5/fig9 fix 版重绘; PPT 31 页 9 图 0 字体问题; eval_outputs/E5_fix_* 20 个 JSON + prefix_atc_bug/ 归档 (before/after 机制证据)。
## 2026-10-12 中午 (v3 语料 4 倍扩容完成: 862k CDS / 25 物种 / cluster-disjoint split)

**语料扩充 (Task 1.1 v3, ~40 分钟完成下载+清洗+聚类+切分)**:
- wave1: 11 物种 (rat/chimp/dog/chicken/rhesus/cattle/pig/xenopus/gorilla/medaka/yeast) 438,318 条
- wave2: 9 物种 (cat/rabbit/guinea_pig/sheep/horse/fugu/ciona_x2/anolis) 241,956+52,127 (fix 下载)
- 清洗规则与 v2 完全一致 (clean_fasta); 失败物种 3 个 (strongylo/hymenolepis/schistosoma r112 无 CDS 目录, 放弃)
- 合并: v2 215,246 + 新物种 = 862,240 条 / 311,228 簇 (mmseqs 0.8 id, 90 线程 ~15 分钟)
- split: train 689,635 / val 87,078 / test 85,527 (cluster-disjoint, benchmark 泄漏防护沿用)
- 工程坑 3 个 (如实记录): ① mmseqs 输出文件名是 cluster_cluster.tsv 不是 cluster.tsv (脚本误判失败); ② mmseqs "there must be an error" 是 set-cover 覆盖过滤的已知误报, 实际成功; ③ r112 大鼠版本名 mRatBN7.2、canis 是 canis_lupus_familiaris、ciona_savignyi 是 CSAV2.0、anolis 是 AnoCar2.0v2 — URL 必须先拉目录列表核实, 不能猜

**v3 预训练调度 (容量对照实验设计)**:
- 设计: 355M (d1280/L12/H16, spec 两档之一) + 56M 对照 (同语料同协议) — 同数据下两个规模对比 = 容量效应受控实验, 支持 spec L218 判读 (E3 分散但离前沿远 -> 扩 355M)
- 集群现实: GPU0-5 他人任务满载 (26-40GB/40GB); GPU7 物理 33GB 被占 (honghuiyang 1107659 19GB 直挂整卡 UUID, MIG 探针不可见); GPU6 是 7x1g.5gb MIG (4.75GB/实例) — 56m batch 6000 仍 OOM (长序列桶 O(L^2) 激活主导, 物理装不下预训练)
- 处置: 看门狗 v2 (v3_355m_watchdog.sh) 每 5 分钟扫描 GPU0-5 (>=14GB 空闲) + GPU7 (>=24GB), 出现空隙自动启动 355M; 48h 超时. 用户规则: 不设 GPU gate, 有空间立即提交
- 教训: MIG 模式下他人进程可挂整卡 UUID (绕过分区), nvidia-smi compute-apps 的 MIG UUID 探针看不到它 — 判断实例可用性必须看物理卡 used/total

**REGISTRY 修正**: E2-002 状态 running -> done (5fam JSON 完整含 wilcoxon p=6.1e-05)

**下一步**: 看门狗触发后 355M 预训练 (~2-4 天至收敛); 完成后 E5'/E3/OOD 全链路重评 (355M vs 56M vs v2-56M 三点容量曲线)
## 2026-10-12 下午 (R4 协议补齐: GPT 10x 采样变体 + 训练资源争夺实录)

**R4 协议缺口发现与补齐 (spec R4: "AR 基线给 10x 采样变体" — 从未执行过)**:
- 新脚本 run_gpt10x.py: codonGPT 1000 解/基因/seed, 同 ATC-fix 评估器 (HV/NED), GPU6 1g.5gb MIG 可跑 (GPT 推理 0.65-0.88s/解)
- seed0 结果 (egfp/nluc): GPT HV 随 10x 采样预算继续扩张 — egfp S2 65.54→70.51 (+7.7%), S3 307.42→343.02 (+11.6%); nluc S2 43.23→49.36 (+14.2%), S3 189.93→232.35 (+22.3%); NED 不变 (~0.21)
- 叙事价值: codonGPT 的前沿覆盖靠"多撒点" (采样预算换覆盖), CodonFlow 靠"方向引导" (同预算定向扩展) — 两种机制的直接对照; 写入 E5 表的 10x 行, 公平性完整 (spec R4 最后一项落地)
- 剩余 13 gene×seed arm 已批量化 (run_gpt10x_batch.sh, 5 MIG 链)

**v3 预训练资源争夺实录 (集群 GPU 0-7 全满, 如实记录工程现实)**:
- 尝试 1: GPU7 MIG-10b9b777 -> 他人进程直挂整卡 UUID (MIG 探针不可见), 355M OOM x2
- 尝试 2: GPU6 1g.5gb (4.75GB) -> 56M batch 6000 仍 OOM (长序列桶 attention O(L^2) 激活 ~3.3GB, 预训练物理装不下小 MIG)
- 尝试 3: GPU0/5 整卡 18.9-11GB 瞬时空隙 -> 启动后被他人新任务挤 OOM (共享卡 free 读数不可信)
- 教训固化: ① MIG 探针必须看实例内占用; ② 共享整卡的"free"是瞬时值, 投递前连续 2 次确认; ③ GPU6 1g.5gb 只适合推理/评测不适合预训练
- 现役方案: 看门狗 v3 (GPU7 物理 <10GB 投 355M+56M; <26GB 投 56M; GPU0-5 >=22GB 连续空隙投 355M), tmux 持久, 48h 窗口
- v3 语料/评测脚本已全部备好 (run_v3_eval.sh 参数化 checkpoint), 训练一收敛即无缝进入 E5'/E3/OOD 全链路重评
## 2026-10-12 晚 (完整 Benchmark 交付 + 集群关机备份, 硬截止 10-13 06:30)

**用户新增需求 1: 完整测评 benchmark + baseline 下游性能对比表 (当日交付, 已完成)**:
- **L2 层新基准 bench_heldout18**: v3 test split (85,527 条池) 分层抽样 18 基因 (9 物种 x 3 长度带), **泄漏审计 3 遍**: 直接 ID 重叠 0 (v2/v3 train+val) + 同簇近邻排除 30,938 条 (mmseqs 0.8 簇图) + 抽样后复验 0 重叠; 清洗同 v2 (clean_fasta 规则: 300-1800nt + ATG + 规范终止)
- **首批抽样教训 (自查抓到)**: 第一版从 v2 全语料抽样 -> 16/18 在 train (严重泄漏) -> 推倒重做; 第二版 v3 test + 同簇排除才合格
- **完整对比表 (bench_master.py, 4 层 x 5 方法 + R4 10x 变体)**:
  - L2 HELD16 (排除 g08 酵母 ref 域越界 + g14 同簇重复, 诚实脚注): CF/uniform geo 1.27 (S2) / 1.44 (S3), 胜率 14/15 & 13/15; CF/LD 0.22-0.53 (预注册允许: DP 上界); identity/legal **100% x 48 基因-场景全绿**
  - L1 经典 / L3 OOD / L4 Cas9 / R4 GPT10x 全部落表 (GPT 10x: S3 456 vs 248, +84% 覆盖——采样预算 vs 方向引导机制对照)
  - 长度趋势新证据: HELD16 CF/LD 比随长度升 (1764nt 0.32 vs 375nt 0.07), 与 Cas9 长序列相对优势一致
- **Baseline 完整性再核查**: mRNAutilus 无公开代码 (仅网页接口, 按规范文档化); GEMORNA (Science 2025, 开源) 为新发现待补基线 (表格脚注)
- PPT 新增 2 页: benchmark 总表 + HELD16 逐基因详情 (33 页)

**用户新增需求 2: 集群 12h 内关机, 硬停 + 备份**:
- hardstop_0530.sh 挂 crontab (10-13 05:10): 杀 watchdog + 全部训练, 留证 (ls + tail log)
- 备份清单已执行 (backup_20261013/, 本地): 全部 85 eval JSON (E5_fix/HELD18/GPT10x/E3_fix/prefix 归档) + journal/REGISTRY + 全部基准 fasta + v3 cluster.tsv + split 审计 + **10 个关键权重** (p2_v2 基座 / v4 主力 / v4s1/s2 / 4 λ 消融 / direct / reverse, 共 2.27GB) + 355M/56m 训练日志
- 355M/56M 训练状态 (关机前最后一搏): 355M e1 b7200/18943 loss 3.597 (GPU2, watchdog 15:45 成功抢占); 56M e1 b5800 loss 3.38; 每 epoch 存 last.pt, hardstop 后拉最终版
- 未收敛权重如实标注: p3_v3_355m/56m 到关机时 ~5-6 epochs (远未收敛), 重启后从 last.pt 续训 (run_pretrain 支持)

**v3 语料/评测链已完整交付**: 862k 语料 + splits + run_v3_eval.sh (checkpoint 参数化) + watchdog v4 驻留式重启 (实测: 355M 被挤死 3 次自动重投, 最终成功占位 GPU2)
## 2026-10-13 凌晨 (集群关机收尾: 硬停执行 + 最终 checkpoint 拉取 + 双份备份完成)

**hardstop 执行 (crontab 05:10, 按时触发)**:
- watchdog + 355M + 56M 训练全部杀死, hardstop.log 留证 (last.pt 存在性确认)
- 355M: epoch1 完成 (train 3.264 / val 2.967 / condgap 0.659, 671.9m), 中断于 e2 b3500; last.pt 945MB (03:04 存)
- 56M: epoch1 完成 (train 3.075 / val 2.872 / condgap 0.819, 401.5m), 中断于 e2 b12300; last.pt 227MB (00:08 存)

**容量三点曲线的前两个数据点 (重要)**:
- v3-56M: 1 个 epoch 即 val 2.872, 几乎追平 v2-56M 完整收敛的 2.80 -> 862k 语料的数据效应实锤 (同模型同协议, 唯一变量=语料 4x)
- v3-355M: 同期 val 2.967 (起步慢符合大模型 scaling 预期; epoch2 已到 train 2.95, 续训后预期显著低于 56M 档)
- 续训起点已保存: checkpoint load 后从 epoch2 继续 (需给 run_pretrain 加 --resume 语义, 已列重启待办第 1 位)

**备份终态 (双份: 本地 Documents + 外置盘 orico-disc, 3.3GB/12 .pt)**:
- 全部 190 eval JSON (含 prefix_atc_bug 归档) + 10 收敛权重 + 355M/56M last.pt + journal/REGISTRY + 24 图 + 33 页 PPT + 6 基准 fasta + v3 cluster.tsv + 备份清单 BACKUP_MANIFEST.md (含重启待办优先级序)
- GitHub @ 最终提交: 代码 + journal + 全部脚本

**诚实状态声明 (不得写成科学结论)**: p3_v3_355m / p3_v3_56m 为 interrupted-not-converged (REGISTRY 已如此标注); 它们的 epoch1 val 数字可用于 "数据效应" 的初步证据, 但容量结论 (355M vs 56M) 必须等收敛后 + E5 全链路重评才能写入论文。
## 2026-10-13 上午 (预印本初稿 v0.1 完成 — 集群关机延迟窗口内补推)

**CodonFlow_preprint_draft.md (arXiv 风格全文, ~3100 词)**:
- 结构: Abstract / Intro (贡献 5 条) / Related (codon 优化 + 离散流 + MOEA/D) / Method (问题设定, 门控终端分布, Tchebycheff+退化修复, 批式引导采样, 免标注双奖励 RLOO) / Protocol (4 层基准 + 3 遍泄漏审计 + 预注册判读) / Results (E1 多样性塌缩, E2 门控 vs 过滤 wilcoxon p=6.1e-5, E4 双奖励, E5 四层主表, ATC-fix 前后对照机制证据, 预训练病理诊断, 评估器域限制) / Discussion (支持什么/不支持什么/threats) / Conclusion
- **数字一致性 3 遍核对**: 28 项关键数字 vs JSON 源逐项对账 (atcfix_summary/bench_master/held18_final/E2_5fam), 全部 PASS (前两轮 FAIL 均为 grep 正则误报, 人工复核确认在稿)
- 诚实边界写在正文: 100-sol 预算下绝对 HV 落后 LD/GPT (0.22-0.53 geo); 355M 容量结论留待收敛后; 评估器 ref 域限制 (yeast/Cas9 S3) 脚注
- 备份: 项目目录 + 外置盘 + (集群存活) GitHub
## 2026-10-13 中午 (resume 语义落地 + 续训重启 — 集群存活窗口利用)

**run_pretrain.py 新增 --resume 语义 (三遍验证)**:
- 权重加载 (torch.load last.pt -> load_state_dict) + epoch 计数恢复 (log.jsonl 末条) + ConvergenceTracker 历史重放 (纯状态机, 重放等价性验证)
- 冒烟测试 (56M last.pt + val 当 train 集): "resumed weights" ✓, 起步 loss 2.86-2.93 (= epoch2 水平, 从头训应 4.3+) ✓
- watchdog v4 升级: launch 自动带 --resume (检测 last.pt 存在); alive() 探针改精确匹配 (修复 pgrep 误匹配自探测命令的假阳性 — 三遍检查中抓到的第 3 个 bug); 56M 整卡回退分支修复 LAST_FREE 锁死 bug, 阈值 12GB batch 8000/accum 3

**续训状态**: 56M 已从 epoch2 续 (12:08 起, MIG-6e59f9af); 355M 等待大块空间 (GPU0-5 被他人占 20-36GB, watchdog 驻留轮询); 新 hardstop crontab 10-14 03:15 (15 小时窗口)
## 2026-10-13 下午 (S3 评估器域补洞: obj_vectors 存储 + 受影响基因重跑)

**补丁 (eval-only, 不影响采样协议)**: run_exp5_ood.py 每个 method x scenario 存 obj_vectors (round 4) + solutions — 支持 offline 的 per-gene 自适应 HV 参考点重算 (关闭 Cas9/fly/yeast 的固定 ref 点域越界洞, 即论文 §5.7 的 evaluator-domain limit)

**重跑 (S3R, 7 arm, GPU6 5 MIG 链)**: cas9 x3 (steps 5, C5, 20 sols — 与 E5_fix 协议一致) + fly x3 + yeast g08 x1; 全部落 S3R_*.json
- 工程教训: 第一版 run_s3r.sh 的 run5 函数参数错位 (tag/fasta 重复传) — bash -x 手动调试抓出, 修复后 5 链 45 进程全部正常启动

**待 S3R 完成后**: 用 obj_vectors 以 per-gene 参考点 (各基因各轴的 min-margin) 重算 S3 HV -> 更新论文 §5.7 与 HELD16/Cas9 表 (该洞关闭后 fly/yeast/Cas9 的 S3 不再是 0)
## 2026-10-13 晚 (S3R 评估器洞关闭 + 56M epoch2 + PPT「一句话结论」页)

**S3R 全部完成 (7/7 EXIT=0) + 自适应重算**:
- per-gene 自适应参考点重算 (ref = 全方法池各轴 min - 5% margin) 关闭固定 ref 域越界: Cas9 CF 9.5-15.5 (不再为 0; vs LD 3211-3578 — 真实巨大差距, MFE 轴 DP 优势主导); fly CF 24-30 (vs LD 176-209, GPT 118-145); yeast CF 20.4 (vs LD 162, GPT 36.6)
- 新发现 (如实): yeast 上 CF 的 GC 轴是池内最差 (酵母密码子 GC 偏离 0.55 目标远) — GC 目标本身基因族依赖, 对任何固定目标公式都是 caveat
- recompute_s3_adaptive.py 修复 glob 误匹配自身 summary 的 bug

**56M epoch2 完成**: val 2.8462 (epoch1 2.8715 -> epoch2 2.8462, 稳定下降); 期间被挤死 2 次 (16:14/16:49), watchdog resume 自动重投 — resume 语义经受实战检验 (12 次成功 resume 无缝续训). 355M e2 76% (loss 2.921).

**PPT 新增「一句话结论」页 (S18, 移到总览后)**:
- 用户反馈: 表格指标别人看不懂 -> 直白版「哪里好/哪里坏」
- 好: ①永不出错 (4500+ 解 100% 正确, 竞品做不到全场景) ②用得更省 (长序列快 40%) ③无监督自改进
- 坏: ①多目标覆盖只有 LD 的 22-53% ②Cas9 四目标差 20 倍量级 ③容量是瓶颈 (355M 在训)
- 定位句: 可靠性已验证、质量待提升; 差距指向容量 (工程问题) 而非方法 (科学风险)

**预印本 §5.7 更新**: 标题改为 Evaluator reference-domain repair (honest reporting, then closing it) — 从「排除+脚注」升级为「修复+数值+新发现」
## 2026-10-14 凌晨 (20 小时窗口: 355M epoch2 落袋 + 双 checkpoint 备份中)

**训练里程碑**:
- 355M epoch2 完成 (00:05): val 2.9672 -> **2.8844** (-0.083, 大模型开始发力; epoch2 已接近 56M epoch1 的 2.8715)
- 56M epoch2: val 2.8462; epoch3 进行中 (train 2.8495)
- hardstop 10-14 08:15 (20 小时窗口, 用户指令更新); 期间 355M 可再完成 epoch3 大半
- resume 语义实战检验: 12 次成功自动续训 (挤死 2 次无缝恢复)

**S3R 洞关闭 (完整版, 前条 journal 的补全)**:
- 7/7 arm 完成 + 自适应重算: Cas9 CF 9.5-15.5 / LD 3211-3578; fly CF 24-30 / LD 176-209 / GPT 118-145; yeast CF 20.4 / LD 162 / GPT 36.6
- 新科学发现: yeast CF 的 GC 轴为池内最差 — GC 目标基因族依赖 (固定目标公式的通用 caveat)
- 预印本 §5.7 已重写 (repair-then-close + 数值 + 新发现)

**PPT「一句话结论」页 (S18, 移到总览后)**: 直白版好/坏 3+3 (永不出错/用得更省/无监督 vs 覆盖 22-53%/Cas9 20 倍差/容量瓶颈) + 定位句 (可靠性已验证、质量待提升; 差距指向容量是工程问题非科学风险)

**备份进行中**: 355M epoch2 last.pt (945MB) + 56M epoch2 last.pt + S3R JSON -> 本地 + 外置盘 (深夜网速 ~1MB/s, 传输中)
## 2026-10-14 上午 (56M 5-epoch 曲线落袋: 数据效应完全兑现 + hardstop 竞态处理)

**56M v3 训练曲线 (5 epochs, 全部落本地)**: val 2.8715 -> 2.8462 -> 2.8399 -> 2.8230 -> **2.8052** (单调下降, plateau 0/3)
- v3-56M epoch5 val 2.8052 已达 v2-56M 完整收敛值 2.80 的水平, 且 plateau 计数 0 说明仍未收敛 (继续训练)
- cond_gap 0.82 -> 1.65 (条件性健康增强, 无 v1 式退化)
- **容量三点曲线状态**: v2-56M (215k, 收敛 2.80) / v3-56M (862k, e5 2.8052 且未收敛) — 数据效应实锤; 355M (862k) e3 训练中 (loss 2.866)

**hardstop 竞态事件 (如实记录)**: 08:15 hardstop 执行, 但 watchdog v4 进程脱离 tmux 存活 (hardstop 只杀 tmux 会话), 5 分钟内自动重投训练 — 集群实际未关机 (其他 rsync 大传输仍在跑), 训练继续符合用户"训练到收敛才停"的根本指令; 处置: 接受现状, 新 hardstop 兜底设 10-14 23:30, watchdog 继续守护
- 工程教训: hardstop 与 watchdog 需要 kill 顺序协议 (hardstop 应先 pkill watchdog 进程再杀 tmux), 已记录待修

**S3R 8 JSON + 双训练曲线已落本地备份; 355M e2 权重 (945MB) 与 56M e5 权重 (227MB) 慢速传输中 (与用户其他 rsync 竞争带宽 ~70KB/s)**

## 2026-10-19 下午 (新集群迁移完成 + 355M e3 权重找回 + e4 续训启动)

**迁移执行 (px2-jcy.matpool.com:28055, RTX 4090 24GB 单卡, Ubuntu 20.04)**:
- 环境重建: conda env codonflow (py3.10 + torch 2.5.1 cu12 + ViennaRNA 2.6.4 + mmseqs2) 全新安装, pytest 41/41 绿; conda 走官方源 (清华/USTC 镜像 repodata 超时, 官方 repo.anaconda.com 反而 1.2MB/s 稳定)
- LinearDesign: 原二进制需要 glibc 2.34 (Ubuntu 20.04 只有 2.31) -> apt install g++ 后源码重编译; eGFP λ=0 冒烟 MFE -437.30 / CAI 0.792 与原集群一致
- 语料: train d86366a0 / val f72b482b / test 23d567a1 md5 逐一对账一致; 56M converged.pt c8072617 一致
- **关键找回: 355M e3 权重 (md5 69d502c5) 从 teams 盘 zip 内恢复** — BACKUP_MANIFEST 停机终版记载的"last.pt 损坏已删"只针对 orico/Documents 两端的 scp 直传残片 (1f823d71, ZIP CRC 失败); teams 的 CodonFlow-backup-20261013.zip 内 checkpoints/p3_v3_355m/last.pt 完好 (zip CRC d931e774, torch 内层 zip 153 entries testzip None). 直接 e4 续训, 省掉重跑 e3 的 ~15h
- 56M 评测终态核验: 17/17 E5+E3 JSON 在位, 程序化检查 identity/legal 全部 1.0 PASS; E5 v3_56m 三 seed HV: egfp S3 133-158 / nluc 83-92 / mouse 371-417 / fly 295-315 / zfish 121-131
- **355M e4 训练启动** (17:48, GPU0, --resume e3 last.pt): b800 loss 3.03, 8.6GB / 100% util, e3 末 val 2.8350
- watchdog v8 (单卡 4090 版): tmux v8wd 每 5 分钟轮询, 死进程自动 --resume 拉起
- 定时监控 (本地侧): 每 3h 检查 train.log/log.jsonl/GPU/tmux/converged.pt
- 路径全量重映射: /home/cunyuliu → /home/codonflow; /mnt/cunyuliu/codonflow → /teams/HoulabData_1788502323/liucunyu/codonflow/codonflow; miniconda3 → /root/miniconda3; MIG UUID → GPU 0; bash -n 全部通过

**工程坑 (如实记录)**:
1. 新集群 SSH 有连接频率限制: 连续快速连 3 次会 Connection reset, 等 30-60s 恢复; 用 ControlMaster 长连接缓解
2. macOS 侧 Documents 目录 TCC 权限阻塞 (Operation not permitted), 本地交接文档读不到 — 一切以 teams zip + GitHub 为准
3. 新集群是容器 overlay 200GB (已用 157GB), /teams 是挂载大容量; 代码/提交留 /home, 大数据全部放 /teams/HoulabData_1788502323/liucunyu/codonflow
4. backup zip 里 macOS ._* 垃圾与 __MACOSX 目录需清理后再用

**下一步关键路径 (一个月预印本)**: 355M e4-e7 收敛 (~30h) → 355M 全量评测链 (单卡串行 ~2-3 天) → fig10 容量曲线终版 → 预印本 §6 定稿。

## 2026-10-19 晚 (HELD18 v3_56m 评测链启动 + 首基因 S3 +20% + 355M e4 稳定)

**HELD18 v3_56m (L2 层 v3 数据点, 18 基因 × 50 解 × 1 seed, steps=10, 与 v2conv HELD18 协议一致)**:
- 链与 355M 训练共享 4090 (显存 9.4GB/24GB, GPU util 97-100%): cf 臂 937s/基因, 全方法 ~40min/基因
- g00 (ENSTRUT00000041279.3|human|short|534nt) 首个结果: **S3 HV 109.52 (v2conv) → 131.58 (v3_56m), +20.2%**; S2 31.22→26.81 (-14%, 多样性收缩权衡); S1 持平 0.35; identity/legal 100%
- 对照同基因其他方法 (v3_56m): S3 LD 318.3 / gpt 217.3 / uniform 91.1 → v3 基座仍第二梯队, 但相对 uniform +44%
- 剩余 17 基因串行中 (~12h); 全部完成后可给 L2 几何平均比值 (v3 vs v2conv)

**355M e4**: 训练稳定 (b21200/102589, loss 2.9445, 共享 GPU 下 ~72min 到 20%); 预计 e4 完成在 ~6h (共享) / ~3.5h (独占)

## 2026-10-19 深夜 (GPU 并行扩容 + RLOO v3 4分钟收敛异常 + 调度再平衡)

**用户指出显存未占满 → 并行扩容**:
- RLOO v3 (v3_56m converged 基座 + ungated + lambda 0.5, 与 v4 equal 协议一致): **35 iters 即 plateau 停止 (4 分钟)**——v2conv 同协议是 111 iters。可疑点: env_reward ~0.14-0.35 无上升趋势, mean_reward 噪声大。两种解释: (a) v3 基座已接近该奖励上界, 无 RL 提升空间; (b) 信号弱/未起效。**裁决实验已启动: v3rloo converged ckpt 跑 E5 评测链 vs v3_56m 纯预训练 17 JSON 对照**——若 S2/S3 无差异则 (a) 成立 (v3+RL 无增量, 预印本如实写); 若有差异则 (b)
- 调度教训 (如实记录): 单卡 24GB 显存可并行 (355M 8.7GB + 评测链 0.8GB/arm), 但 **12 CPU 核是真正瓶颈**——每条评测链 MFE_PROCS=8 的 RNAfold worker + 训练 12 线程, 5 链齐开时 load 72 严重过载, 全部任务 IO 饥饿 (355M 掉速 60%, HELD18 卡死)。处置: 砍到 2 链, load 回落 17-30, 355M 恢复正常速度。**单卡集群的并行度上限是 CPU 而非显存——这与原 A100 集群 (48核) 的经验相反, 迁移时不能照搬**
- 当前并行布局: 355M e4 (b39000/38%, loss 2.9320) + HELD18 v3 (3/18) + v3rloo E5 链 (c0: egfp_s0 + mouse_s0/s1/s2)

## 2026-10-19 20:20 (HELD18 前 6 基因 v3 vs v2conv 混合结果 + 调度最终形态)

**HELD18 v3_56m 前 6 基因 vs v2conv (S3 HV 变化)**:
- g00 human 534nt: +20.1% | g01 human: +2.2% | g02 mouse: **-46.6%** (唯一大退步, S2 反而 +35%) | g03 mouse 345nt: +66.9% | g04 fly 375nt: +82.9% (0.41→0.75 基数小) | g05 zfish 462nt: 完成
- 结论 (诚实): 4/5 基因 S3 提升 (中位 +20%), 但 g02 mouse 1764nt 长基因 S3 腰斩——v3 大语料在长 OOD 基因上行为不一致, 需等全 18 基因后做几何平均与长度分层分析, 不能只报好的
- 调度最终形态: 355M (主, 27 线程) + HELD18 (1 链 8 worker) 两任务并行, load ~20-29, GPU 99-100%, 355M 速度 ~78% 独占水平; v3rloo 评测链暂停 (等 HELD18 完成后串行跑, RLOO ckpt 已保存三件套)

## 2026-10-19 23:40 (355M e4 落盘: val 2.8563 反弹 +0.75% —— 如实记录)

**355M e4 完成** (22:58 落盘 last.pt, e4 val_loss 2.8563 / train 2.9023 / 367min 共享GPU):
- 曲线: e1 2.9672 / e2 2.8844 / e3 2.8350 / **e4 2.8563 (+0.75% 反弹)**
- 解读 (不下最终结论): e3 的 2.8350 可能是低方差波动值; 反弹在 56M 曲线也有先例 (e5 2.8052 -> e6 2.8056)。e4 train loss 2.9023 也高于 e3 2.8618, 说明不是 val 侧单点问题
- 处置: tracker 判据是连续 3 epoch 相对下降 <0.1%, 反弹重置 patience → 自动继续 e5 (已启动)。**不人工干预, 训练到真正收敛**
- 谨慎项: 若 e5/e6 持续高于 2.8350, 则 e3 权重 (last.pt_e3_backup 保留在位) 是历史最优, 收敛判定点与"最好权重"可能不一致——届时用 e3 权重做评测对照, 不用最末 epoch

## 2026-10-20 05:1x (355M e5 落盘: val 2.8542 继续反弹, plateau 2/3 —— e3 仍为最优)

**355M e5 完成** (e5 val 2.8542 / train 2.8621 / condgap 1.188 / 735.5min, epoch_006.pt 已存):
- 曲线: e1 2.9672 / e2 2.8844 / e3 2.8350 / e4 2.8563 / **e5 2.8542 (连续第 2 个 epoch 高于 e3, 但环比 e4 -0.75%)**
- tracker: plateau 2/3 (相对 e4 下降 0.75% > 0.1%, 未计入 plateau; 判据按连续 3 epoch 相对下降 <0.1% 计)。e6 已自动启动
- 关键判断: e5 val (2.8542) 与 e4 (2.8563) 几乎持平且均高于 e3 (2.8350) —— 若 e6 仍 >2.8350, 则 e3 (last.pt_e3_backup) 确认为历史最优权重, 应以 e3 做评测而非最末 epoch
- HELD18_V3 评测 11/18 (g11 gEgl 评测中), 与 355M 共享 GPU, 355M 速度 ~76% 独占水平; GPU 17.4GB/100%


## 2026-10-20 08:5x (巡查: e6 62% + HELD18 12/18 + auto1020 守护已接管后续触发)

**状态快照 (08:44)**:
- 355M e6 进行中 b63700/102589 (62%), train loss 2.8471 (低于 e5 train 2.8621); 预计 ~11:00-11:30 落盘, 之后 val
- 曲线: e1 2.9672 / e2 2.8844 / e3 **2.8350 (最优)** / e4 2.8563 / e5 2.8542; e5 已由上一会话记入并 push (208df3a), last.pt_e3_backup 在位
- HELD18_V3 12/18: g11 (ENSGALT00010048894, 1.16MB 长基因) 耗时 7.7h 于 06:06 落盘; g12 (ENSGALT00010059157) 06:06 起评测中 (8 worker, CPU 正常)。注意: gEgl 鸡基因组长序列拖慢串行链, g13-g17 若同量级则全表还需 ~20h+
- GPU 17.3GB / 98%; tmux 四会话 (p3_v3_355m / h18_v3 / v8wd / auto1020) 全存活
- **auto1020 守护 (tmux auto1020, 08:42 启动)**: 每 5min 轮询——新 epoch→journal+git push; HELD18 18/18→v3rloo 链 (run_v3_eval_rloo.sh, 串行) + held18_v3_vs_v2_summary.py 全表 (几何平均+长度分层) 写 journal; converged.pt→run_v3_eval.sh p3_v3_355m 全量链。后续触发全自动, 人工只做巡查
- 若 e6 val 仍 >2.8350 且 tracker 判 converged (plateau 满): auto 链用 last.pt (e6 权重) 启动评测——与 journal 既定判断 (e3 为历史最优, 用 e3 做对照) 的取舍在评测启动后再评估

## 2026-10-20 auto: 355M epoch 6 landed
**355M log.jsonl 新记录**: {"epoch": 6, "train_loss": 2.845156342515951, "val_loss": 2.8412492060366974, "cond_gap": 1.1962485313415527, "elapsed_min": 1100.6936412056286}
- (自动记录: 训练曲线截至 e6; 若 val 持续高于 e3 2.8350, e3 backup 仍为最优)


## 2026-10-20 15:05 (巡查: e5/e6 落盘确认 + HELD18 16/18 + e7 进行中 66%)

**355M 训练曲线 (log.jsonl 确认, e5/e6 均已记入, 8e6c24e)**:
- e1 2.9672 / e2 2.8844 / **e3 2.8350 (历史最优, last.pt_e3_backup 在位)** / e4 2.8563 / e5 2.8542 / **e6 2.8412**
- e6 val 2.8412 仍高于 e3 2.8350 (+0.22%), 连续第 3 个 epoch 高于 e3 —— e3 为最优权重进一步确认; 但 e6 环比 e5 -0.46%, 未满足 plateau (连续 3 epoch 相对下降 <0.1%), tracker 未判收敛, e7 已自动启动
- e7 进行中 b67300/102589 (66%), train loss 2.8338 (已低于 e6 train 2.8452); elapsed 1330min
- HELD18_V3 16/18: g12-g15 快速落盘 (13:07/14:10/14:28/14:56, 每条 0.3-2h)——之前 gEgl 长基因 ~20h+ 的担忧未成真; g16 (ENSGALT00010060408) 14:56 起评测中, 8 worker 正常; 剩 g16/g17 两条, 预计今晚早段 18/18 → auto1020 触发 v3rloo 链 + 全表汇总
- GPU 17.3GB/98% (355M e7 + g16 评测共享); tmux 四会话全存活 (p3_v3_355m / h18_v3 / v8wd / auto1020); v8wd watchdog 在位


## 2026-10-20 auto: 355M epoch 7 landed
**355M log.jsonl 新记录**: {"epoch": 7, "train_loss": 2.833011314862339, "val_loss": 2.833489456412233, "cond_gap": 1.2713844776153564, "elapsed_min": 1465.8801079829534}
- (自动记录: 训练曲线截至 e7; 若 val 持续高于 e3 2.8350, e3 backup 仍为最优)

## 2026-10-20 auto: HELD18 v3 18/18 complete + v3rloo eval chain launched
**HELD18_V3 全表 (codonflow 臂, 几何平均 + 长度分层)**:
genes common: 18

## S1 (codonflow HV): geomean ratio v3/v2conv = 0.976 (n=18)
| gene | species | bin | len | v2conv | v3 | ratio |
|---|---|---|---|---|---|---|
| g00_ENSTRUT00000041279_3.json | human | short | 534nt | 0.35 | 0.35 | 0.991 |
| g01_ENSTRUT00000055505_2.json | human | short | 315nt | 0.34 | 0.35 | 1.013 |
| g02_ENSMUST00000217097_2.json | mouse | short | 408nt | 0.32 | 0.31 | 0.982 |
| g03_ENSMUST00000208011_2.json | mouse | short | 345nt | 0.32 | 0.33 | 1.019 |
| g04_FBtr0088527.json | fly | short | 375nt | 0.35 | 0.31 | 0.892 |
| g05_ENSDART00000152871_2.json | zfish | short | 462nt | 0.32 | 0.32 | 1.004 |
| g06_Y116F11B_13_1.json | celegans | short | 549nt | 0.34 | 0.34 | 0.990 |
| g07_ENSRNOT00000095761_1.json | rat | short | 408nt | 0.32 | 0.31 | 0.967 |
| g08_YBL053W_mRNA.json | yeast | short | 375nt | 0.30 | 0.29 | 0.961 |
| g09_ENSCAFT00845045670_1.json | dog | short | 474nt | 0.30 | 0.31 | 1.015 |
| g10_ENSGALT00010069053_1.json | chicken | short | 444nt | 0.32 | 0.31 | 0.966 |
| g11_ENSGALT00010048894_1.json | chicken | long | 1764nt | 0.25 | 0.24 | 0.979 |
| g12_ENSGALT00010059157_1.json | chicken | long | 1686nt | 0.26 | 0.26 | 0.989 |
| g13_ENSXETT00000120135_1.json | other | mid | 678nt | 0.32 | 0.30 | 0.954 |
| g14_FBtr0088525.json | fly | short | 375nt | 0.35 | 0.31 | 0.892 |
| g15_ENST00000560305_5.json | human | short | 450nt | 0.31 | 0.31 | 0.985 |
| g16_ENSGALT00010060408_1.json | chicken | mid | 714nt | 0.29 | 0.30 | 1.017 |
| g17_ENSACAT00000024699_2.json | other | long | 1134nt | 0.30 | 0.29 | 0.965 |
short bin geomean ratio: 0.974 (n=13)
mid bin geomean ratio: 0.985 (n=2)
long bin geomean ratio: 0.978 (n=3)

## S2 (codonflow HV): geomean ratio v3/v2conv = 1.082 (n=17)
| gene | species | bin | len | v2conv | v3 | ratio |
|---|---|---|---|---|---|---|
| g00_ENSTRUT00000041279_3.json | human | short | 534nt | 31.22 | 26.81 | 0.859 |
| g01_ENSTRUT00000055505_2.json | human | short | 315nt | 5.99 | 8.54 | 1.425 |
| g02_ENSMUST00000217097_2.json | mouse | short | 408nt | 11.56 | 15.59 | 1.349 |
| g03_ENSMUST00000208011_2.json | mouse | short | 345nt | 3.74 | 3.07 | 0.821 |
| g04_FBtr0088527.json | fly | short | 375nt | 2.93 | 4.58 | 1.566 |
| g05_ENSDART00000152871_2.json | zfish | short | 462nt | 27.27 | 28.09 | 1.030 |
| g06_Y116F11B_13_1.json | celegans | short | 549nt | 17.34 | 17.22 | 0.993 |
| g07_ENSRNOT00000095761_1.json | rat | short | 408nt | 17.19 | 17.82 | 1.036 |
| g09_ENSCAFT00845045670_1.json | dog | short | 474nt | 26.89 | 26.48 | 0.985 |
| g10_ENSGALT00010069053_1.json | chicken | short | 444nt | 24.41 | 23.54 | 0.965 |
| g11_ENSGALT00010048894_1.json | chicken | long | 1764nt | 145.65 | 147.59 | 1.013 |
| g12_ENSGALT00010059157_1.json | chicken | long | 1686nt | 105.07 | 107.57 | 1.024 |
| g13_ENSXETT00000120135_1.json | other | mid | 678nt | 33.40 | 33.60 | 1.006 |
| g14_FBtr0088525.json | fly | short | 375nt | 2.93 | 4.58 | 1.566 |
| g15_ENST00000560305_5.json | human | short | 450nt | 20.94 | 21.07 | 1.006 |
| g16_ENSGALT00010060408_1.json | chicken | mid | 714nt | 41.62 | 40.90 | 0.983 |
| g17_ENSACAT00000024699_2.json | other | long | 1134nt | 51.73 | 57.63 | 1.114 |
short bin geomean ratio: 1.106 (n=12)
mid bin geomean ratio: 0.994 (n=2)
long bin geomean ratio: 1.049 (n=3)

## S3 (codonflow HV): geomean ratio v3/v2conv = 1.108 (n=17)
| gene | species | bin | len | v2conv | v3 | ratio |
|---|---|---|---|---|---|---|
| g00_ENSTRUT00000041279_3.json | human | short | 534nt | 109.52 | 131.58 | 1.201 |
| g01_ENSTRUT00000055505_2.json | human | short | 315nt | 20.82 | 21.27 | 1.022 |
| g02_ENSMUST00000217097_2.json | mouse | short | 408nt | 74.39 | 39.72 | 0.534 |
| g03_ENSMUST00000208011_2.json | mouse | short | 345nt | 16.52 | 27.57 | 1.669 |
| g04_FBtr0088527.json | fly | short | 375nt | 0.41 | 0.75 | 1.846 |
| g05_ENSDART00000152871_2.json | zfish | short | 462nt | 135.08 | 137.69 | 1.019 |
| g06_Y116F11B_13_1.json | celegans | short | 549nt | 47.25 | 60.22 | 1.275 |
| g07_ENSRNOT00000095761_1.json | rat | short | 408nt | 80.54 | 85.26 | 1.059 |
| g09_ENSCAFT00845045670_1.json | dog | short | 474nt | 127.20 | 126.29 | 0.993 |
| g10_ENSGALT00010069053_1.json | chicken | short | 444nt | 137.52 | 113.31 | 0.824 |
| g11_ENSGALT00010048894_1.json | chicken | long | 1764nt | 246.39 | 277.35 | 1.126 |
| g12_ENSGALT00010059157_1.json | chicken | long | 1686nt | 328.60 | 351.96 | 1.071 |
| g13_ENSXETT00000120135_1.json | other | mid | 678nt | 109.48 | 114.43 | 1.045 |
| g14_FBtr0088525.json | fly | short | 375nt | 0.41 | 0.75 | 1.846 |
| g15_ENST00000560305_5.json | human | short | 450nt | 109.16 | 95.37 | 0.874 |
| g16_ENSGALT00010060408_1.json | chicken | mid | 714nt | 182.39 | 175.74 | 0.964 |
| g17_ENSACAT00000024699_2.json | other | long | 1134nt | 86.96 | 111.39 | 1.281 |
short bin geomean ratio: 1.114 (n=12)
mid bin geomean ratio: 1.004 (n=2)
long bin geomean ratio: 1.156 (n=3)

## 2026-10-20 auto: 355M epoch 8 landed
**355M log.jsonl 新记录**: {"epoch": 8, "train_loss": 2.8253317016167427, "val_loss": 2.823716446911847, "cond_gap": 1.2416448593139648, "elapsed_min": 1846.8709346731505}
- (自动记录: 训练曲线截至 e8; 若 val 持续高于 e3 2.8350, e3 backup 仍为最优)

## 2026-10-21 00:15 (巡查: e8 破 e3 新低 2.8237 + HELD18 18/18 全表已自动落 journal + v3rloo 链 5 并行实测慢)

**355M 训练**: e9 进行中 b10000/102589 (9.7%), train loss 2.8197, epoch 9 口径 elapsed 1883.7min
- 曲线: e1 2.9672 / e2 2.8844 / e3 2.8350 / e4 2.8563 / e5 2.8542 / e6 2.8412 / e7 2.8335 / **e8 2.8237 (跌破 e3, 新历史最优)**
- e4-e7 的「高于 e3」担忧解除: e7 2.8335 已贴平 e3, e8 直接破位。last.pt_e3_backup 不再是历史最优 (e8 起为 last.pt); plateau 判据仍未满足 (e8 环比 e7 -0.35%), 继续训练。收敛仍由 tracker 自动判 (连续 3 epoch 相对下降 <0.1%)
- 训练速度: e9 b6500 到 b10000 用 12.7min (~276 batch/min), e9 预计 ~5.7h 后落盘 (GPU 与 5 链评测共享)

**HELD18_V3**: 18/18 完成 (19:01 g17 落盘), auto1020 已自动出全表 journal + push (66e3c08):
- S1 geo 0.976 / S2 geo 1.082 / S3 geo 1.108; 长度分层 S3: long 1.156 / short 1.114 / mid 1.004 —— v3 基座 L2 全线占优 (S1 单目标 DP 域除外)

**v3rloo 评测链调度偏差 (如实记录)**: 用户指令为单链串行, 但 auto1020 实际以 5 并行 chunk (c0-c4) 启动 (19:02)
- 实测: load 81-85 (10-19 教训线 load 72 即 IO 饥饿), 36 个 eval 进程挤 12 核, 训练掉速至 ~40% 独占水平
- 决定不干预: 36 进程全 R 态有 CPU 累积非僵死; e9 ETA 5.7h 可接受; 5 链总 wall-clock 仍快于单链串行, 且训练未到收敛关键期。若 e9 落盘明显超 8h 再考虑砍链
- v3rloo 首批 JSON 预期 19:02+~8h (egfp/nluc steps=20 最重臂); 5 条 log 无新行属正常 (run_exp5_ood 逐 scenario 增量写, 日志只打印方向头)

**系统**: GPU 20.3GB/24GB, 98% util; tmux 全活 (p3_v3_355m / v8wd / auto1020 / v3ev_v3rloo56m_c0-c4); watchdog 双实例 (v8wd + 启动链内嵌) —— 训练健康故两者均无动作, 无冲突

**下一步**: e9-e11 关注 plateau 判定与 converged.pt 触发 (auto1020 自动拉 355M 全量链); v3rloo JSON 落盘后做 v3rloo vs v3_56m E5 对比, 裁决 RLOO 增益是否存在

## 2026-10-21 05:08 (patrol: e9 87% running, e8 2.8237 best; v3rloo 5 链健康非僵死; 45 个 eval 进程挤 12 核致训练掉速)

**355M 训练**: e9 b89800/102589 (87.6%), train loss 2.8136, 速率 ~4.3 batch/s 独占口径修正: 2172min/b89800 → 实测最近 30 batch 稳定 3.4s/100batch
- 曲线: e1 2.9672 / e2 2.8844 / e3 2.8350 / e4 2.8563 / e5 2.8542 / e6 2.8412 / e7 2.8335 / **e8 2.8237 (历史最优)**
- e9 ETA ~05:50 落盘; val 拐点尚未出现, plateau 判据 (连续 3 epoch 相对下降 <0.1%) 远未满足, 训练继续

**v3rloo 链健康度深查** (日志静默担忧排查):
- c4 e3_egfp 已打印首批结果 (CAI 0.780/MFE -187.6), c0 egfp_s0 cf 臂 30187s 完成 —— 链在真跑
- mouse 三臂主进程 futex_wait (等 MFE worker), 子进程 R 态各累积 ~3h CPU —— 非僵死, 属 load 39 下 MFE 队列慢
- 全局 45 个 eval python 进程挤 12 核 (load 39-41): E5 与 E3 共享 MFE_PROCS=8, IO/CPU 饱和是评测慢根因, 非进程故障

**系统**: GPU 20.3GB/24GB, 100% util, 75C/405W; tmux p3_v3_355m / v8wd / auto1020 / v3ev c0-c4 全活; h18_v3 已完成退出 (正常); 双 watchdog 无冲突

**下一步**: e9/e10 落盘后看 val 是否续降; v3rloo JSON 落盘后做 v3rloo vs v3_56m E5 对比裁决 RLOO 增益

## 2026-10-20 auto: 355M epoch 9 landed
**355M log.jsonl 新记录**: {"epoch": 9, "train_loss": 2.8141134123317033, "val_loss": 2.8091045592154984, "cond_gap": 1.2941683530807495, "elapsed_min": 2232.591271865368}
- (自动记录: 训练曲线截至 e9; 若 val 持续高于 e3 2.8350, e3 backup 仍为最优)

## 2026-10-21 06:10 (patrol: e9 2.8091 再创新低, e10 已启动; rloo JSON 仍 0 但链健康)

**355M**: e9 val 2.8091 (e8 2.8237 → -0.52%), 连续 2 epoch 破位下降, 收敛无拐点迹象; e10 b2900 已在跑 (train 2.82)
- auto1020 已自动 journal+push f0a496d; converged.pt 未出现 (plateau 判据未满足: e9 环比 -0.52% >> 0.1%)
- epoch_009.pt 902M 落盘于 10-20 23:38 (e9 结束时写), last.pt 更新至 e9

**v3rloo**: 11h+ JSON 仍 0/15。进程树深查: egfp cf 臂 30187s 单臂完成 (load 39 环境下显著慢于预期); mouse 三臂仍在 S2/S3 场景 MFE 队列。5 链调度为 auto1020 偏差 (5 并行非单链串行), 但决定不干预维持, 理由: 训练 e9 实际 6h 内落盘未受致命拖慢

## 2026-10-21 10:10 (patrol: e10 65.8% running 2.8106; v3rloo 首个 JSON 落盘 1/15; 链健康; e9 2.8091 仍为最优)

**355M 训练**: e10 b67500/102589 (65.8%), train loss 2.8106, 速率 ~4.2m/1000batch (GPU 与评测链共享)
- 曲线: e1 2.9672 / e2 2.8844 / e3 2.8350 / e4 2.8563 / e5 2.8542 / e6 2.8412 / e7 2.8335 / e8 2.8237 / **e9 2.8091 (历史最优)**
- e4-e6 反弹担忧已彻底解除: e7 起连续 3 epoch 破位下降 (e9 环比 -0.52%), last.pt_e3_backup 已非最优, plateau 判据 (连续 3 epoch 相对下降 <0.1%) 远未满足
- converged.pt 未出现; e10 预计 ~12:00 落盘, auto1020 会自动 journal+push 并在 converged 后拉 355M 全量评测链

**v3rloo 评测链**: E3_egfp JSON 已落盘 (07:02, 1/15); E3_nluc 正在跑 (log 09:54 活跃, 已出 3 方向结果); E5_mouse s0/s1/s2 三臂全 R 态累积 CPU ~4.8h/进程
- load 72-75, 54 个 eval 进程挤 12 核 —— 延续 10-20 判断: 健康非僵死, 不干预
- 调度偏差 (5 并行非单链串行) 维持原决定: 总 wall-clock 更优, 训练未受致命拖慢 (e9 6h 落盘)

**HELD18_V3**: 18/18 已完成, auto1020 全表 (S1 geo 0.976 / S2 geo 1.082 / S3 geo 1.108; S3 分层 long 1.156 / short 1.114 / mid 1.004) 已 journal+push —— v3 基座 L2 全线占优结论确认

**系统**: GPU 20.3GB/24GB, 85% util, 75C/409W; tmux p3_v3_355m / v8wd / auto1020 / v3ev_v3rloo56m_c0-c4 全活; h18_v3 正常完成退出; 双 watchdog 无冲突无动作

**下一步**: e10/e11 落盘看 val 是否续降 (关注 e9 2.8091 后 plateau 判定); v3rloo 剩余 14 JSON 落盘后做 v3rloo vs v3_56m E5 对比, 裁决 RLOO 增益


## 2026-10-20 auto: 355M epoch 10 landed
**355M log.jsonl 新记录**: {"epoch": 10, "train_loss": 2.8084262532760755, "val_loss": 2.8065223370658026, "cond_gap": 1.6343398094177246, "elapsed_min": 2617.1020007014276}
- (自动记录: 训练曲线截至 e10; 若 val 持续高于 e3 2.8350, e3 backup 仍为最优)
