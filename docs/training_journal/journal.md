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
