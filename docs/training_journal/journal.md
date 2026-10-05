# CodonFlow 训练日志（journal）

> 纪律（spec R6-3）：每个训练 run 在此追加一节；REGISTRY.md 记 run 索引，本文件记过程与结论。

## 2026-10-04 环境交接（Phase 0 完成）

- 服务器 A100（36.137.135.49）：8×A100-PCIE-40GB；GPU 0-5 被其他项目占用，GPU 6/7 开了 MIG（6=7×1g.5gb，7=2×3g.20gb）。
- conda env `codonflow`：ViennaRNA 2.6.4 ✓、mmseqs 18.8cc5c ✓、torch 2.5.1+cu121 ✓（8 GPU 可见）、pymoo ✓、matplotlib ✓。
- GitHub：`Cunyu-Liu/codonflow` 已建立，main 分支，每完成一批工作即推送。
- 仓库测试：41/41 通过（本地与服务器双端验证）。
- GPU 冒烟：MIG 3g.20gb matmul4096 0.29s；train_smoke loss 4.76→4.62 正常下降。

## 2026-10-04 数据体系（Phase 1 完成）

- GENCODE v47 pc_transcripts（112,218 转录本）→ CDS 提取（header CDS 区间）→ 清洗（71,869 kept；主要丢弃：frame 19,430、too_short 14,763、no_terminal_stop 4,596）。
- 多物种补充：C. elegans 28,782 + D. melanogaster 27,653 + mouse 45,810 + zebrafish 41,132（同规则清洗）。
- 合并 215,246 CDS → MMseqs2 easy-cluster 0.8 → 107,811 簇 → 簇级 80-10-10（train 172,240 / val 21,149 / test 21,857，整簇不跨 split）。
- CAI 双参考表：`configs/cai_ref_refseq.json`（GENCODE 全量）+ `configs/cai_ref_train.json`（训练集，暂代 HPA，待补 TPM 过滤版）。
- 分布审计（train）：长度中位 1191nt（q5-q95: 381-3762）、GC 0.506±0.073、CAI 0.801±0.035、MFE 样本均值 -470.9、RSCU top CTG 2.22 / bottom TTA 0.46——与真核蛋白编码基因预期一致，无异常双峰。四维图落 docs/data_audit/audit_train.png。
- 基准序列：eGFP（P42212, 238aa → 717nt 合成 CDS）、nanoLuc（JQ437370.1 CDS 100..615，516nt，与 GenBank /translation 逐字符核对一致）、SpCas9（Q99ZW2, 1368aa → 4107nt）。注意：**JQ437429 是错误引用（16S rRNA），正确 accession 是 JQ437370.1**——已核实并记录。

## 2026-10-04 LinearDesign 基线（决策门 A 输入）

- 官方实现编译成功（third_party/LinearDesign，g++ -Ofast，Linux x64）。
- 计时基准（停止条件④分母，3 repeats 取均值）：
  - eGFP（238aa）：**27.7 s/seq**，LD 自报 CAI 0.753 / MFE -429.4；我方复测（ViennaRNA 2.6.4）CAI 0.794 / MFE -444.1，蛋白身份保持 ✓
  - nanoLuc（171aa）：**17.6 s/seq**，LD 自报 CAI 0.796 / MFE -337.8；我方复测 CAI 0.825 / MFE -347.5，身份保持 ✓
- 结论：CAI ∈ [0.75, 0.83] 区间，与 codonGPT 论文量级（≈0.70）和 spec 预期 [0.65,0.75] 上界附近一致——Gate A 的判据方向正确，等 codonGPT 数字齐后正式判定。
- LD 与我方 MFE 差异（-429 vs -444）原因：LD 内置热力学参数版本 vs ViennaRNA 2.6.4 参数差异 + LD 序列不含终止密码子（我方补 TAA 后 fold）。已知偏差，记录在案。

## 2026-10-04 预训练启动（CF-P2-2.1.2-pretrain-001）

- 硬件：GPU7 的 MIG 3g.20gb（21GB，与 honghuiyang 的 9GB 任务共存于同一物理卡不同 MIG 实例）。
- 模型：768d/8L/12H（56.8M 参数，pCoMole 同构档）。
- 数据：172,240 训练 CDS，token-budget 24k 长度分桶打包（3705 batches/epoch，消除 padding 浪费）。
- 超参：AdamW lr=1e-5 wd=0.03，dropout=0（预训练档），梯度裁剪 1.0。
- 早期曲线：loss 5.81（b0）→ 4.13（b800），下降健康。
- 收敛判据：val loss 连续 3 epoch 相对下降 <0.1% 触发停机（代码已实现，不设步数上限）。
- 监控：每 30 分钟自动巡检（tmux 会话存活性 + loss 走势 + NaN 检查 + 自动重启逻辑）。

## 2026-10-04 预训练巡检（CF-P2-2.1.2-pretrain-001）

- 巡检 #1（≈16:32，训练进行 ~25 min）：tmux `cf_pretrain` 存活（16:07:59 创建）；e1 b600→b1000/3705，loss 4.1368→4.1249，稳步下降，无 NaN、无飙升；GPU7 MIG 显存 19134 MiB（与 honghuiyang 任务共卡，正常）。未收敛（epoch 1 进行中），无需干预，继续监控。
- 巡检 #2（≈17:01，训练进行 ~53 min）：tmux `cf_pretrain` 存活；e1 b1800→b2200/3705，loss 4.1128→4.1085，平稳下降，无 NaN、无飙升；GPU7 物理卡显存 30086 MiB（含同卡其他 MIG 实例，正常）。未收敛（epoch 1 进行中，约 60% 进度），无需干预，继续监控。
- 巡检 #3（≈17:35，训练进行 ~88 min）：tmux `cf_pretrain` 存活；e1 b3100→b3500/3705，loss 4.1013→4.0988，平稳下降（epoch 1 约 94.5% 进度，预计 ~5 min 后完成首个 epoch），无 NaN、无飙升；GPU7 显存 23334 MiB 正常。首个 epoch 尚未结束，暂无 val loss 记录，收敛判据未触发，无需干预，继续监控。
- 巡检 #4（≈18:03，训练进行 ~115.7 min）：tmux `cf_pretrain` 存活（16:07:59 创建）；**epoch 1 完成**：train 4.0977 / val 4.0794，lr 1.00e-05，plateau 0/3；e2 b500→b900/3705，loss 4.0758→4.0755，持续缓降，无 NaN、无飙升；GPU7 物理卡显存 27501 MiB（含同卡其他 MIG 实例，正常）。收敛判据未触发（plateau 0/3），训练未完成，无需干预，继续监控至 val loss 连续 3 epoch 相对下降 <0.1%。
- 巡检 #5（≈18:33，训练进行 ~145 min）：tmux `cf_pretrain` 存活（16:07:59 创建）；e2 b1700→b2100/3705（epoch 2 约 57% 进度），loss 4.0752→4.0747，持续缓降，无 NaN、无飙升；GPU7 显存 28481 MiB、GPU6 4482 MiB（含同卡其他 MIG 实例，正常）。收敛判据未触发（plateau 0/3，待第 2 个 epoch 结束后产生新 val loss），训练未完成，无需干预，继续监控。
- 巡检 #6（≈20:02，训练进行 ~234 min）：tmux `cf_pretrain` 存活（16:07:59 创建）；**epoch 2 完成**：train 4.0729 / val 4.0678，较 epoch 1 val 4.0794 相对下降 0.28%（>0.1%，plateau 0/3）；e3 b1500→b1900/3705（epoch 3 约 51% 进度），loss 4.0682→4.0684，平稳，无 NaN、无飙升；GPU7 显存 30535 MiB、GPU6 4316 MiB（含同卡其他 MIG 实例，正常）。另观测到新 tmux 会话 `cf_exp1`（19:40:47 创建，非本巡检职责，仅记录）。收敛判据未触发，训练未完成，无需干预，继续监控至 val loss 连续 3 epoch 相对下降 <0.1%。
- 巡检 #7（≈20:32，训练进行 ~265 min）：tmux `cf_pretrain` 存活（16:07:59 创建）；e3 b2800→b3200/3705（epoch 3 约 86% 进度，预计 ~8 min 后完成），loss 4.0677→4.0674，平稳缓降，无 NaN、无飙升（NaN 计数 0，CONVERGENCE 标记 0）；GPU7 显存 29558 MiB、GPU6 4150 MiB（含同卡其他 MIG 实例，正常）。epoch 3 的 val loss 尚未产出（plateau 0/3），收敛判据未触发，训练未完成，无需干预，继续监控至 val loss 连续 3 epoch 相对下降 <0.1%。
- 巡检 #8（≈21:05，训练进行 ~297 min）：tmux `cf_pretrain` 存活（16:07:59 创建）；**epoch 3 完成**：train 4.0671 / val 4.0638，较 epoch 2 val 4.0678 相对下降 0.098%（<0.1%），plateau 计数首次触发（1/3）；e4 b500/3705（epoch 4 约 13.5% 进度），loss 4.0637-4.0642 平稳，无 NaN、无飙升；日志最后更新 21:01:54（3 分钟前，训练活跃）；GPU7 显存 21780 MiB、GPU6 4158 MiB（含同卡其他 MIG 实例，正常）。收敛判据未触发（plateau 1/3，需连续 3 epoch 相对下降 <0.1%），训练未完成，无需干预，继续监控。val loss 轨迹：4.0794 → 4.0678 → 4.0638（缓降段，符合 1e-5 小学习率预期）。
- 巡检 #9（≈21:35，训练进行 ~327 min）：tmux `cf_pretrain` 存活（16:07:59 创建）；e4 b1400→b1800/3705（epoch 4 约 48.6% 进度），loss 4.0644→4.0648，平稳（4.0644-4.0648 窄幅波动），无 NaN、无飙升（NaN 计数 0，CONVERGENCE 标记 0）；日志最后更新 21:31:00（4 分钟前，训练活跃）；GPU7 显存 28298 MiB、GPU6 4158 MiB（含同卡其他 MIG 实例，正常）。收敛判据未触发（plateau 1/3，epoch 4 的 val loss 预计 ~22:20 产出），训练未完成，无需干预，继续监控。val loss 轨迹：4.0794 → 4.0678 → 4.0638。
- 巡检 #10（≈22:02，训练进行 ~354 min）：tmux `cf_pretrain` 存活（16:07:59 创建）；e4 b2600→b3000/3705（epoch 4 约 81% 进度，预计 ~17 min 后完成），loss 4.0646→4.0643，平稳缓降，无 NaN、无飙升（NaN 计数 0，CONVERGENCE 标记 0）；GPU7 显存 29518 MiB、GPU6 4324 MiB（含同卡其他 MIG 实例，正常）。收敛判据未触发（plateau 1/3，epoch 4 的 val loss 预计 ~22:20 产出），训练未完成，无需干预，继续监控。val loss 轨迹：4.0794 → 4.0678 → 4.0638。

## 2026-10-04 晚间进度（预训练前 3 epoch + Phase 1 收尾）

- 变体库（1.1.7）：eGFP/nanoLuc 各 1000 条 uniform 同义变体，抽检全量验证身份保持 100% + 合法率 100%（2000/2000）。
- OOD 家族（1.1.6）：从 test split 按长度多样性选 3 条（斑马鱼 465nt / 果蝇 1179nt / 小鼠 1905nt），簇级隔离由 split 构造保证，configs/ood_families.yaml。
- EXP-1 尝试与教训：codonGPT 逐 token 采样与 batch generate 在 CPU 争用（loadavg 75/96、gmx 分子动力学任务占 4 个满核）+ GPU 逐 step 多项式循环下都太慢（200 样本 × 3 seeds × 2 arms > 40 分钟未完成）。**决策：EXP-1 推迟到预训练收敛后在专用资源上跑**（或改用一次性 precompute 变体库 + codonGPT 打分近似，视届时负载）。此为本日的执行记录，非科学结论。
- 预训练 epoch 1-3：val 4.0794 → 4.0678 → 4.0638（每 epoch ~94 分钟）。plateau 计数 1/3。loss 收敛形态符合预期（前期快降，后期进入缓降段）。
- 定时监控：每 30 分钟自动巡检 cf_pretrain tmux 会话与 loss 走势，会话死亡自动重启（相同超参）。

## 2026-10-05 凌晨：预训练收敛 + Gate B 预评（P2 核心链路打通）

- **预训练收敛**（CF-P2-2.1.2-pretrain-001）：val loss 4.0794(e1) → 4.0678(e2) → 4.0638(e3) → 4.0610(e4) → 4.0611(e5)。第 3-5 epoch 相对下降均 <0.1%，触发「连续 3 epoch」判据自动停机，converged.pt 落盘（/mnt/cunyuliu/codonflow/checkpoints/p2_pretrain_768d/）。总时长 7.8 小时 / 5 epochs / 56.8M 参数。
- **引导采样首测**（nanoLuc，converged checkpoint，n_steps=20，C=10）：
  - 20 步采样 32.4 s/序列 —— **成本比 LinearDesign（17.6s）= 1.84x，Gate B 成本线 <5x 达标**。
  - CAI 从 x0 的 0.712 → 采样后 0.766（+0.054）—— Doob-h 倾斜有效。
  - 合法率/身份保持 100%（编辑算子 by-construction 保证生效）。
  - 5 步采样 8.8s（CAI +0.002 仅）——质量主要来自前 20 步，符合 pCoMole「中间档预算」结论。
- 正式 20 samples × 3 seeds 的评测因单卡循环慢（每步一次 GPU forward + RNAfold 串行），改为小样本已拿到 Gate B 关键数字；完整 EXP 表将在 RLOO 之后用批量推理跑。
- 教训记录：单样本逐 token 循环在 MIG 上 ~1.6s/step；后续引导采样要用批量（一次 forward 评多个候选）优化——列入 EXP-2 前的工程优化项。

## 2026-10-05 凌晨 2：RLOO 微调启动（CF-P3-3.1-rloo-001）

- Gate B = GO 已归档（合法/身份双 100%、成本 1.84× LD、CAI 倾斜 +0.054）。
- RLOO 训练器上线：GrammarRL 配方（direct 无约束长度归一化 log-lik + reverse 硬翻译 + N=3 组 + LD 解混入 + β=0.02 逐序列正则 + λ=0.5），从 converged.pt 初始化，lr=3.3e-7。
- LD 强对照解已缓存：eGFP CAI 0.794、nanoLuc CAI 0.825。
- 早期信号：iter10 reward -38.9（未归一化 direct 项量级大，属预期——direct 项是 log-lik 负值），env_reward 0.0116。
- 训练速度：~7 分钟/iter（含 4×20 步采样 + RNAfold）——1000 iter 上限 + 奖励平台期判据（patience 15）在线；预计数小时内收敛或触发停止条件。

## 2026-10-05 巡检 #11：预训练收敛终态确认（CF-P2-2.1.2-pretrain-001 完结）

- 巡检 #11：tmux `cf_pretrain` 会话已消失，日志尾部出现 `CONVERGENCE CRITERION TRIGGERED - stopping`——非崩溃，属收敛判据正常停机（epoch 5 train 4.0623 / val 4.0611，plateau 3/3，elapsed 469.0m），**不触发重启分支**（收敛即终态）。日志末段 loss 稳定于 4.062x，无 NaN、无飙升（<10），无告警。GPU7 显存 24653 MiB 为 `cf_rloo`（RLOO 微调）任务所在 MIG 实例，与预训练无关；GPU6 4544 MiB 同卡他项。**预训练 run 正式完结**：val 轨迹 4.0794 → 4.0678 → 4.0638 → 4.0610 → 4.0611，末 3 epoch 相对下降均 <0.1%，收敛完成条件（非步数约束）满足。

## 2026-10-05 巡检 #12：预训练终态复核（无干预）

- 巡检 #12：终态复核与 #11 结论一致——tmux `cf_pretrain` 仍不存在，日志尾部 `CONVERGENCE CRITERION TRIGGERED - stopping`（e5 b3500-3700 loss 4.0622-4.0623，epoch 5 train 4.0623 / val 4.0611，plateau 3/3，elapsed 469.0m）。全日志 NaN 计数 0、无 loss >10 飙升，无告警写入。**不重启**（收敛即完成）。epoch 汇总：e1 4.0977/4.0794 → e2 4.0729/4.0678 → e3 4.0671/4.0638 → e4 4.0641/4.0610 → e5 4.0623/4.0611。GPU7 27903 MiB（`cf_rloo` RLOO 任务，与预训练无关）、GPU6 4378 MiB 同卡他项。预训练 run 保持完结状态。

## 2026-10-05 上午：三项关键 bug 修复（A2 修正案）+ EXP-1 完成 + EXP-2/RLOO v3 启动

### 发现并修复的 bug（全部三次核对+解析验证）

1. **ATC 死轴（根本性）**：configs/atc_norm.yaml v1 对 neg_gc_dev/neg_motif 存的是「幅值」分位数（q5=0/q95=0.15、q5=0/q95=5），而代码传入的是负值目标 → 两轴归一化后恒被 clamp 到 0 → Tchebycheff min 项恒 0 → U(x) 塌缩到 ~0.01 → **Doob-h 引导实际无效**（引导强度相对策略 logit 可忽略）。
   - 修复：按 A1 规定程序从 Task 1.2 基线解集（codonGPT 约束采样 + LD + uniform，206 条）实测**带符号** 5/95 分位数，重写 atc_norm.yaml（v2）；ATCUtility.from_yaml() 工厂方法接线；DEFAULT_NORM_STATS 同步 v2。
   - 证据：修复后 U(x) 从恒 ~0.01 → 0.07-0.50（健康方差）；RLOO sigma_env 从 0.0007 → 0.1337（**190×**）。
   - 归档：Amendment A2（atc_norm.yaml 头注释 + 本日志）。
   - **影响声明**：RLOO v2（iter 1-70+）与 Gate B 预评的「CAI 0.712→0.766」均使用死轴 ATC——其中 CAI 提升主要来自预训练策略先验（常用密码子偏好）而非 Doob-h 引导。RLOO v2 保留为「弱引导」诊断 run（其 direct/reverse 训练信号本身不受死轴影响，只影响 rollout 质量）。**主结果以 v3 为准。**

2. **hypervolume 方向错误（影响全部 EXP 的主指标）**：metrics.py 直接把最大化目标喂给 pymoo（pymoo 是**最小化**语义）→ 所有 EXP 的 HV 数字一律为 0。
   - 修复：负向转换 HV(ref_point=-ref)(-pts) + ref-point 合法性断言。
   - 验证：2D 解析例 0.6×1.4+0.4×1.0=1.24 == 实测 1.24 ✓。

3. **pairwise NED 纯 Python Levenshtein 慢 ~1000×**：EXP-1 原 7-13 小时 → rapidfuzz C++ 路径后 15 分钟完成。同义变体等长，Levenshtein=Hamming，语义不变。

### EXP-1 完成（叙事①证据落地）

- `EXP1_collapse.json` + `EXP1_collapse.png`：3 seeds × 2 基因（eGFP/nanoLuc），每基因 1000 样本/seed。
- **核心数字**：uniform vs RSCU-weighted 的 NED 分布 KS p=0.0（显著左移）；密码子熵 1.10→1.06 / 1.17→1.12 bits；CAI-greedy 锚点 NED=0/熵=0（塌缩上限可视化）；**codonGPT 自身 loglik 显著偏好塌缩方向**（eGFP -4.08 vs -4.14；nanoLuc -4.12 vs -4.18）——AR 模型偏好低多样性解的直接证据，叙事①成立。
- 注意（诚实记录）：本 EXP 的 AR 侧用 RSCU-weighted 代理（codonGPT 站在 RSCU 上的偏好 = codonGPT 对塌缩分布的估计）；严格的「AR free vs AR masked」对照按 pre-register 跑 50 样本小规模作为检查（后续补）。

### 并行任务状态

- **EXP-2**（MIG-d2b486bc，PID 643991）：门控 vs 同预算后置过滤，严格预算语义（评分调用数），2 家族 × 3 seeds，Hypervolume + time-to-first-usable + Wilcoxon。运行中。
- **RLOO v3**（MIG-82791eab，PID 672145）：修复后 ATC，sigma_env=0.1337，其余超参同 v2。运行中，环境奖励现在有真实梯度信号。
- **RLOO v2**：保留运行作弱引导对照（iter 70+，plateau 0/15）。
- GitHub：修复已推送（commit 9e2deea + fc387c1，含 LinearDesign embedded repo 清理）。

## 2026-10-05 上午 2：EXP-2 首轮结果（预训练模型，2 家族）——负向，如实记录

- **结果**：500 评分预算下，uniform+post-filter(topK) 的 hypervolume **高于** gated guided（eGFP 3.5-3.8 vs 2.8-2.9；nanoLuc 2.3-3.0 vs 1.8-2.0；Wilcoxon p=0.031，方向利于 filter）。tt1（首达合格解）gated 略优（idx 5 vs 5-57）。
- **判读（按 spec 预注册）**：同预算下门控不优于过滤 → 「by construction 效率优势」强断言**当前不成立**（至少在预训练模型 + 该预算粒度下）。
- **机制分析**：
  1. topK 是从 500 个独立样本中选 5 个极端值（独立样本天然多样性高、HV 占优）；gated 5 个解来自 5 条爬山轨迹，彼此相关。
  2. 预算粒度问题：100 calls/rollout → 仅 5 rollouts。门控的价值在「逐步把预算转化为质量」，但 5 条轨迹太少，无法体现。
  3. 预训练模型（无 RLOO）的引导方向可能次优。
- **后续动作**（不掩盖、不修饰）：①5 家族正式版在跑（含 OOD，满足 Wilcoxon 样本量）；②RLOO v3 收敛后同配置重跑（预注册公平对照）；③若仍不优 → 按 spec 退化为「质量不劣 + 合法率保证 + tt1 优」弱化叙事，或者提高 rollout 数的预算粒度消融（EXP-6 网格会覆盖）。
- Wilcoxon p=0.031 的 n=6（2fam×3seed）是边缘显著——5 家族版 n=15 后再定论。

## 2026-10-05 上午 3：RLOO v4（未门控双奖励，GrammarRL 严格配方）收敛 + EXP-4 消融矩阵并行启动

- **关键设计修正**：v2/v3 的 rollout 走门控采样器（同义候选）→ reverse=1[Trans(y)==protein] 恒 1 无方差 → 双奖励退化为 direct-only。spec EXP-4 明确要求 rollout 未门控。新增 --ungated-rollout：n_steps 个随机位置从全 64 密码子 token 分布重采样（BOS/EOS/PAD masked）。
- **RLOO v4 收敛**（p3_rloo_v4_ungated）：iter 111 触发 plateau 15/15 自然停止；末段 env reward 0.17-0.36（均值 ~0.27）。converged.pt 落盘。
- **EXP-4 消融矩阵**（6 组全并行，各占 1 MIG）：
  | 组 | λ | rollout | 状态 |
  |---|---|---|---|
  | v4 等权 | 0.5 | 未门控 | **已收敛**（iter 111）|
  | v3（=消融「门控 rollout」变体）| 0.5 | 门控 | 运行中（env 0.26-0.32）|
  | lam025 | 0.25 | 未门控 | 刚启动 |
  | lam075 | 0.75 | 未门控 | 刚启动 |
  | reverse_only | 1.0 | 未门控 | 刚启动 |
  | direct_only | 0.0 | 未门控 | 刚启动 |
  | v2（弱引导对照，死轴 ATC 时期）| 0.5 | 门控 | 运行中 iter 130+ |
- 指标出口：训练后贪心解码 hypervolume / NED / 身份保持率（rollout vs 贪心分别报告）+ 训练奖励曲线——写评测脚本待所有 run 收敛后统一执行。

## 2026-10-05 上午 4：EXP-4 消融评测 + EXP-3 引导强度诊断与修复

### EXP-4 消融首轮评测（eGFP，guided decode 口径，20 decodes/组）

| 组 | HV | ident | NED |
|---|---|---|---|
| v4_equal (λ=0.5 ungated) | 4.43 | 1.00 | 0.221 |
| v4_lam025 | 4.41 | 1.00 | 0.221 |
| v4_lam075 | 4.43 | 1.00 | 0.221 |
| v4_direct_only | 4.36 | 1.00 | 0.222 |
| v4_reverse_only | 4.02 | 1.00 | 0.225 |
| v3_gated (gated rollout) | 4.21 | 1.00 | 0.223 |
| v2_weak_guide | 4.65 | 1.00 | 0.221 |
| pretrain (无 RL) | 待出 | | |

- 消融梯度形态初现：equal ≈ lam025 ≈ lam075 > direct_only > reverse_only（reverse-only 最弱，与 GrammarRL 预期一致）。v2 意外最高（弱引导 + 训练时间最长 iter 180+）——需要在 RLOO 收敛终态时统一比较（v2 仍在跑，届时用 converged 版重评）。
- **首轮评测翻车修复（重要）**：原 greedy_decode 用 raw argmax——但 token head 是去噪语义（预测目标序列），argmax 塌缩到高频密码子（229/239 位置预测改变，仅 13 个同义）→ ident=0。修复：解码必须走门控引导采样器（同义候选 + Doob-h 权重，temperature 0.1 近似贪心）。

### EXP-3 引导强度诊断（数值实验，证据在案）

- 实测：策略 log_u spread（同义候选间）≈ 0.77 nats；β=1 时 U spread ≤ 0.5（理想情形），实际相邻编辑 ΔU ~ 0.01-0.05 → 引导信号被策略先验淹没 → 7 方向全部输出相同分布。
- 修复（H1a 授权范围内）：β=8 + apply_k=4（每步 4 个编辑，对齐 pCoMole 全序列移动语义）。修复后方向分离出现：cai_only CAI 0.778 vs gc_only 0.764（eGFP）。
- sampler 增加 apply_k 参数（multi-position edits/step），评分调用核算不变。

### 版本纪律

- 代码 commits: c75d635（apply_k + exp3 修复）之前 959bd77（exp4 解码修复）。全部推送。

## 2026-10-05 上午 5：v2 处置（人工停止，证据已归档）

- v2 iter 220：reward last-60 mean -39.134 (std 0.18) vs first-60 -39.172，env 恒 0.011（死轴 ATC）。实质收敛但 tracker 因 mean_reward 微幅漂移未触发 plateau（rel_tol 0.5% 对 -39 量级 = 0.2 绝对值，振荡 std 0.18 恰好在阈值边缘）。
- 决策：人工停止 v2（其弱引导对照证据已在 EXP-4 表中：HV 4.65/3.50，为各 RLOO 变体最高——反映其训练 iter 最长 220，但 env 无改善，即「direct 信号把 log-lik 推高但环境目标不动」的现象本身是死轴时期的证据）。
- 释放 MIG 资源给 EXP-5 主表。

## 2026-10-05 上午 6：EXP-2 五家族正式版（负结果定论）+ 资源处置

- **EXP-2 五家族 × 3 seeds 定论**（E2_gated_vs_filter_5fam.json）：filter topK 15/15 全胜（Wilcoxon p=6.1e-05）；gated 仅 tt1（首达合格解 4-6×快：idx 5 vs 12-30）与合法率（100% by construction）占优。
- **预注册判读执行**：叙事②「by construction 效率优势」强断言撤回，退化为「质量不劣 + 合法率保证 + tt1 优」弱化叙事（spec 停止条件预案）。
- **机制归因（诚实）**：本对照的 gated 臂用 pretrain 模型 + 10 步引导（u 仅 0.02-0.27）——引导强度不足以翻过 top-K 的极端值统计优势。RLOO v4 收敛模型 + β=8 + apply_k 的重跑列为必要补充实验（E2-v2），若仍负则结论稳固成立。
- 资源：EXP-2 释放 MIG-d2b486bc；立即投入 E2-v2（RLOO v4 模型 + β=8 + apply_k=4 同预算重跑）。

## 2026-10-05 中午：EXP-5 首轮（弱引导）+ 强引导 v2 系列启动

### EXP-5 首轮结果（诚实记录，弱引导配置的教训）

- CodonFlow 臂用了 β=1/apply_k=1（当时 flag 尚未加入）→ 与 EXP-3 诊断相同的引导强度问题 → S1-S3 各场景 HV 均低于 codonGPT/LinearDesign-scan/CAI-greedy。
- S1（单目标 CAI）CAI-greedy 全支配（NDS 1.00）——预注册允许（DP 最优单目标如实认输）。
- LinearDesign-scan 的大 HV 部分来自极端 MFE 贡献 + LD λ-scan 解的 GC 高方差；同时发现脚本 cai_greedy 臂重复同一解 10 次的设计缺陷（NDS 计算无害但 NED 语义失真——记录为已知问题）。
- **判定：EXP-5 首轮数字仅作管线验证，不进主表。主表 = E5-v2（RLOO v4 + β=8 + apply_k=4）。**

### 在途任务（截至 10:20）

| 任务 | 状态 |
|---|---|
| E2-v2（RLOO-v4 + β8 + ak4，5 家族） | 运行中 |
| E5-v2（同配置主表） | 运行中 |
| EXP-3（β8+ak4，7 方向×2 基因） | 12/14 方向完成 |
| RLOO v3（gated rollout 对照） | iter 240，env 0.19-0.45 波动上行 |

### 今日整体科学进展（供预印本草稿用）

1. **叙事① 成立**（EXP-1）：AR 偏好塌缩 KS p=0，codonGPT loglik 偏好塌缩方向。
2. **叙事② 弱化**（EXP-2 5 家族定论）：同预算 filter topK 15/15 全胜——「by construction 效率优势」强断言撤回；保留 tt1 4-6× 优势 + 合法率 100%。E2-v2（强引导）若翻盘则需修改结论，若不翻则结论稳固。
3. **叙事④ 成立**（EXP-4）：8 组消融全部 RL 变体 > pretrain（3.51→4.0-4.65）；等权/近等权最优、reverse-only 最差——GrammarRL 反噬形态迁移成功。
4. **叙事③ 部分成立**（EXP-3 eGFP）：方向分离出现（balanced 支配单目标方向），β=8 + apply_k=4 后 Doob-h 偏好塑形有效。
5. RL 环境目标改善证据链：v3 env 0.24→0.45（修复 ATC 后引导真正生效）。

## 2026-10-05 下午：E5-v2 结果与 E5-v3 场景化修正 + 值守状态

### E5-v2（balanced 引导全局用）结果

- CodonFlow HV 在 S1-S3 仍落后（S2 29.7%/23.5%、S3 21.6%/19.0% 相对 LD-scan）。S1 CAI-greedy 全支配（预注册允许）。
- **设计缺陷定位**：S1/S2/S3 共用同一批 balanced 引导解 → 单/双目标场景天然吃亏（用 balanced 解去打 CAI-greedy 的单目标 DP 最优）。
- **E5-v3 修正**：每场景独立引导方向（S1→ω=(1,0,0), S2→(0.5,0.5,0), S3→balanced）+ 修正 per-scen 目标核算 bug（method_objs 混淆）。已启动。
- LD-scan 的 HV 优势部分来自极端 MFE 单点（λ=0 解 MFE -444）撑开体积——主表脚注需要说明 HV 参考点语义（记录为论文 known-issue）。

### 值守状态（本 session 收尾）

| 任务 | MIG | 预计完成 |
|---|---|---|
| E2-v2 强引导 5 家族 | d2b486bc | ~2h |
| E5-v3 场景化主表 | 27707c52 | ~5h |
| RLOO v3 对照 | 82791eab | plateau 后自然停 |
| 30min 自动巡检 | — | 持续 |

- 所有结果 JSON 在 /mnt/cunyuliu/codonflow/eval_outputs/；图在 eval_outputs/figures/。
- 定时任务（本地 7747de16）持续巡检 ssh+grep。

## 2026-10-05 下午 2：用户质询「loss 好高」触发根因诊断——预训练 v1 信息论退化确认 + v2 修复启动

### 诊断（三重铁证）

1. **信息论地板分析**：训练集密码子边际熵 H=4.0267 nats；v1 预训练 val loss 终值 4.0611 = 4.0267（频率查表）+ ~0.034（blank BCE 残差）。56.8M 参数模型收敛成「64 格密码子频率查表」——形式收敛真、实质平凡解。
2. **条件性测试**：同一目标、两份不同噪声 x0 → 模型预测分布平均 |Δlogp| = 0.031 nats（近乎零反应，即模型输出与输入无关）。
3. **预测分布检查**：任意位置 top-5 全局高频密码子（CTG 0.038 / AAG 0.033 / ...），与输入内容无关。

### 根因

x0 = fixed_length_noise_like（纯均匀随机）与目标序列**零互信息**。token head 的最优解就是全局频率分布。且训练只见 t=1（全噪声）极端态，而推理时 sampler 每步面对的是「大部分正确的半成品」——**训练-推理分布错配**。

### 修复：预训练 v2（腐蚀式中间态训练）

- 新函数 corrupt_x_t(ids, t)：每条序列采 t~U[0,1]，替换 t 比例位置为随机密码子。t=1 纯噪声 / t~0.5 半成品 / t=0 干净——模型被迫学习「用存活证据做条件补全」，与 sampler 推断分布对齐。
- 冒烟测试通过（t=0 全保留、t=1 全换、t~0.5 保留率 ~50%）。
- 新监控指标 cond_gap（conditionality probe：同 t 下两份腐蚀的 |Δlogp|）——v1 = 0.031 nats（退化），v2 应显著增长，这是「模型是否真的在学条件性」的直接读数，防止再次收敛到平凡解而不自知。
- 运行于 GPU7 MIG-7-1（3g.20gb 共 6.5GB 空闲），batch-tokens 12000，其余超参与 v1 一致（768d/8L/12H 56.8M）。

### 影响声明（哪些既有结论需要重新标注）

- **v1 checkpoint 衍生的一切结果**（EXP-2/3/5-v1/v2、RLOO v2/v3/v4、Gate B 预评）都基于「频率查表 + β·U 硬引导」的基座——**HV 绝对值不可与 v2 基座直接比较**。
- 但 EXP-1（数据侧塌缩现象）、EXP-4 的「RL 相对 pretrain 的提升形态」（组内相对比较）、EXP-2 的负结果（filter 优势来自统计机制，与基座无关）**定性结论仍成立**。
- 待 v2 收敛后重跑：RLOO 主线、EXP-2/3/5 正式表。这一轮「发现退化-修复-重跑」本身就是按预注册纪律（非收敛训练不得进主表）执行的结果。

## 2026-10-05 下午 3：E2-v2 强引导结果（差距收敛至不显著）+ 预训练 v2 中期

### E2-v2（RLOO-v4 + beta=8 + apply_k=4，5 家族 × 3 seeds）

| 指标 | E2-v1 | E2-v2 |
|---|---|---|
| HV 差距（gated-filter） | -0.28 (11%) | -0.14 (5.5%) |
| paired 胜率 | 0/15 | 5/15 |
| Wilcoxon p | 6.1e-05 | 0.107（不显著） |
| tt1 优势 | 4-6× | 4-13×（gated tt1 idx 2.3-5.0 vs filter 12-30） |

- **判读**：强引导把显著负结果拉到统计不显著；方向正确但未翻正。与基座退化诊断自洽——RLOO-v4 也是查表基座的产物。
- **待预训练 v2 收敛后跑 E2-v3**（全新基座 + 强引导）才是叙事②的最终检验。若 v3 基座下仍不优于 filter，则按预注册退化为弱化叙事（质量不劣 + 合法率 100% + tt1 4-13×），这一负结果本身有科学价值（「同预算下引导采样 vs 极端值选择」的边界刻画）。

### 预训练 v2 中期信号（健康）

- e1 b3200/7432：train loss 5.19 → 3.68（持续下降；条件任务生效的间接证据——v1 同期在 4.10 附近即触底，因为它的地板是 4.03）
- 期望：val loss 显著低于 4.03 + cond_gap >> 0.031（epoch 1 结束出首个读数）

## 2026-10-05 下午 4：预训练 v2 epoch 1 读数——退化修复验证成功

| 指标 | v1（退化） | v2 epoch 1 | 说明 |
|---|---|---|---|
| val loss | 4.0611 | **2.9742** | 破频率查表地板（4.027）1.05 nats |
| cond_gap | 0.031 nats | **0.705 nats** | 条件性 ×22.7——模型对输入真实响应 |

- v2 仅 1 epoch 就完成质变：腐蚀式中间态训练（t~U[0,1]）迫使模型学习条件补全，训练-推理分布对齐。
- v1 的「收敛」确认为假地板（信息论退化）；v2 将训练到真正的 val 平台期（判据不变：连续 3 epoch 相对下降 <0.1%）。
- v2 预计 5-8 epoch 收敛（94.8 min/epoch），全部重跑计划：RLOO v5（新基座）→ E2-v3 / EXP-3-v2 / E5-v4 正式表。

## 2026-10-05 傍晚：EXP-6 完成——预算-质量-耗时曲线定型（叙事⑥成立）

- 12 配置网格（steps{10,20,30}×C{10,30}×R{5,10}）全部完成（E6_budget_curves.json + fig6）。
- **核心发现（拐点形态与 pCoMole 附录 D 一致）**：
  - 深度 > 广度：steps=30/C=10/R=5 在 1500 calls 达 HV 5.38，而 steps=10/C=30/R=10 用 3000 calls 只有 3.94——**一半预算，1.4× 质量**。
  - C=30 反而稀释 Doob-h 权重集中度（steps=30/C=30 的 HV 4.06 < steps=30/C=10 的 5.38）。
  - 最优配置 steps=30/C=10/R=10：HV 5.55，57.5s/解。
- **成本线**：57.5s/解 < LinearDesign（27.7s）×5 = 138.5s——满足 spec 成本约束（停止条件④达标）。
- 注意（诚实记录）：本网格用 RLOO-v4（v1 退化基座）模型；v2 基座收敛后曲线绝对值会变，但「深度>广度」的相对形态预期稳定（源于 Doob-h 采样结构而非基座）。
- E5-v3（场景化 ω）同日完成：LD-scan 绝对 HV 仍领先——待 v2 基座重跑后再定主表终值。

## 2026-10-06 凌晨：多卡并行批次（用户指令「gpu 空余较多」响应）

### 并行任务矩阵（峰值 8 任务）

| 任务 | MIG | 状态/结果 |
|---|---|---|
| v2 预训练 | 7-1 3g.20gb | epoch 8 进行中，epoch 7 val 2.8501 plateau 1/3 |
| v4s2_equal 补跑 | 7-1 共存 | **收敛 iter 531**（首跑 OOM 死亡——MIG-13 被他人进程 3.8GB 挤占） |
| RLOO v3 gated 对照 | 7-2 | **收敛 iter 903**，终态 env ~0.39（对照点：高于 v4-ungated 的 0.27） |
| EXP-4 3seed 评测 | 27707c52 | 11 组出数，seed 间形态一致（lam025: 4.41/4.20/4.40；lam075: 4.43/4.19/4.43） |
| EXP-3 v4 基座版 | 121d5489 | cai_only CAI 0.780 MFE -192.8——**全面优于 v1 基座版**（0.778/-187.1） |
| EXP-6 v4 基座版 | d2b486bc | 刚启动 |

### 修复的执行问题

- exp4_seed_sweep.sh 的 seed 笔误（v4s2 系列误传 seed 1）→ 修正为逐行显式 seed
- v4s2_equal 在 MIG-e157a761 被 OOM 挤死（他人进程 3.8GB）→ 换 MIG-7-1（3g.20gb 有 6GB 余量）+ PYTORCH_CUDA_ALLOC_CONF=expandable_segments 成功重跑
- sweep 脚本 wait 返回≠全部成功（静默 OOM）——教训：批量任务后必须 ls converged.json 核对数量

### GPU 资源纪律

- 发现 GPU1/5 显存富余但为他人整卡项目（非我方 MIG 池），不越界
- 我方池内 MIG-11/12 空闲即用（EXP-3-v4/EXP-6-v4 即时提交）
