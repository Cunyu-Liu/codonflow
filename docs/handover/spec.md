# CodonFlow Spec（A6 证据修复版 · 2026-10-26/27）

> 本文档为当前有效 spec。旧版已备份于会话临时归档；完整历史在 GitHub。
> 项目：有限步同义 Markov mRNA 编辑器；不再把 immediate-ATC 局部搜索或条件去噪直接等同于 pCoMole CTMC Edit Flow。
> 代码 `/home/codonflow`；大文件 `/teams/HoulabData_1788502323/liucunyu/codonflow`；GitHub `Cunyu-Liu/codonflow`。
>
> **收尾状态（2026-10-27）**：用户要求停止新增实验并交接。两臂在 epoch 6 安全停止且未收敛；unique18 仅 10/18 完整；full-data RLOO 未启动且队列已取消。完整问题、证据边界与恢复入口见 [HANDOFF_20261027_WRAPUP.md](HANDOFF_20261027_WRAPUP.md)。本文后续要求仅作为下一位的工作规范，不表示已经完成。

## 当前执行状态（2026-10-30 23:50 CST）

- 用户已明确恢复实验冲刺，2026-10-27 的停止状态仅保留为历史交接；A6 验收合同与 P0–P4 顺序不变。
- 当前单卡 RTX 4090 24GB（实例重启于 21:02，uptime 2:09）。**21:11 的“两臂并行恢复”在 21:14 即失败**：edited-token 臂在 resumption 后第一个 batch 触发 `torch.OutOfMemoryError`（free 202 MiB，另一臂已占 12.08 GiB），tmux 会话 `a6_edit_resume` 随之退出。该失败已归档在 `a6_v4_56m_r2/train.log`，不得写成“两臂已在训练”。
- **修复**：`run_pretrain.py` 新增 `--gpu-mem-fraction`（调用 `torch.cuda.set_per_process_memory_fraction`），单卡共存时给每个进程设硬上限；并启用 `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`。23:36 / 23:37 两臂以硬上限重启：full-token 0.58（micro-batch 20000 × accum 3）、edited-token 0.30（micro-batch 10000 × accum 6）。
- **可比性披露**：两臂有效 batch 均为 60,000 token/update，但 micro-batch 不同（10,000 vs 20,000），`length_bucketed_batches` 的分桶组成因此不是逐样本配对；下游对照以冻结 checkpoint 与同一评测器为准，不把训练曲线当作配对实验。
- 重启代价：full-token 从 epoch-7 的 `training_state.pt` 恢复，丢失约 35 分钟的 epoch-8 前半段（无 checkpoint 落盘，无科学结果损失）。
- 当前进度：full-token epoch 8（loss 2.8270，val e7 = 2.814013）；edited-token epoch 7（loss 4.3842，val e6 = 4.385477）。两臂均在下降，**均未触发 plateau**，无 converged.pt。
- unique18 seed-0 于 23:45 以 `--resume` 重启（CPU 侧，MFE_PROCS=8）：10 条完整 + C05E11.2.1 部分，剩余 7 条在跑。
- 当前仍无收敛模型、完整 unique18 或新 CodonFlow 下游结果。PPT 对未完成项只标“进行中/待裁决”，不得写成主结果。

## 1. 科学问题与可证伪假设

**问题**：能否在不改变蛋白的前提下，学习可控、可复现、成本可核算的同义 CDS 编辑？

- H1（机制）：有限步单密码子同义跳转核在精确 h 下可实现 `q_G(X_T) ∝ q_base(X_T)G(X_T)`；短 rollout 与候选剪枝是近似，需用真实对照判断其效用。
- H2（学习）：在蛋白去重、cluster-disjoint 的独立测试上，训练与 path-RLOO 是否比 frozen base 提高联合 HV 或效用，而不牺牲 identity/legal 与多样性。
- H3（边界）：与 LinearDesign、codonGPT、GEMORNA、uniform synonymous 在明确输出预算与成本下比较，哪些目标/长度/物种上本方法有优势，哪些没有。
- 不以“第一个”“SOTA”“容量瓶颈”“RL 随预训练饱和”作为预设结论；它们必须由新对照支持。

## 2. 实现边界

### 2.1 Legacy exploratory（不得用于证明 A6 主主张）

- 旧 `BatchedGuidedSampler` 是 `log_u + immediate_ATC`，没有短 rollout、`logsumexp(log G)-log R` 或 `h(y)/h(x)`。
- 旧 `EditFlowTransformer`/`edit_flow_loss` 是条件去噪，不是完整时间/速率参数化 CTMC Edit Flow。
- 旧 RLOO 用整段 token 打分而非真实编辑路径概率，环境效用被 `0.0 * r_env` 关闭；旧平台不能作为新算法收敛证据。
- 旧 355M e21 val=2.7875 只表示达到旧 plateau 条件；`converged.pt` 是最后权重，不是自动选出的最优权重。不同目标/验证协议下的损失差不能写成 scaling 定律。

### 2.2 A6 验证版

- `synonymous_markov.py`：位置与密码子联合归一化、显式 stay、合法源 CDS 检查、单密码子同义跳转；默认短 rollout，记录 forward/唯一终端评分。
- `FiniteStepSynonymousMarkovEditor`：`log h = logsumexp(terminal_logG) - log R`，候选比值为 `logq + logh(y) - logh(x)`；候选剪枝近似，不能宣称大空间精确终端分布。
- `rollout_count=0` 是 immediate 消融；默认返回实际轨迹终端，incumbent 仅显式选择。
- `path-RLOO` 使用 `sampling_kernel='base'` 的实际基础核采样路径概率，环境效用实际进入奖励，squared log-ratio trust penalty（不冒称 KL）。MC-Doob 引导轨迹与基础核路径概率不同，不能混作 on-policy 目标；训练与校准 FASTA 必须蛋白不重叠。reverse 身份在同义空间只作诊断。
- 预训练必须有独立验证集、固定验证 corruption、FASTA SHA256、代码 commit、best/last/完整 optimizer+RNG 状态；验证 plateau 才停止。

## 3. 数据与泄漏审计

### 3.1 已证实的历史问题

`eval_outputs/audits_20261026/v3_exact_overlap.json`：

- train/val/test = 689,635/87,078/85,527；train 有 51,391 重复 CDS 输入、67,832 重复翻译蛋白输入。
- train–val 共享 73 CDS/187 蛋白；train–test 共享 76 CDS/188 蛋白；val–test 共享 12 CDS/28 蛋白。
- HELD18 含 18 输入但只有 17 个唯一 CDS/蛋白，均来自 test；train/val 与 benchmark 无精确重叠。
- 旧“零泄漏”“18 unique”“family-disjoint”撤回。cluster-held-out、family-OOD、species-OOD 必须分开命名。

### 3.2 当前 v4 数据

- 输入：862,240 条清洗 CDS，25 物种，300–6000nt。
- `splits_v4_protein`：保留 776,474 个唯一蛋白；train/val/test = 621,306/76,444/78,724。
- benchmark 连通簇排除：24 输入中 21 有精确匹配，eGFP/nanoLuc/SpCas9 三个合成 benchmark 无匹配并如实记录；不能声称同源已排除。
- 独立审计 `v4_exact_overlap.json`：所有 split 间、split 与 benchmark 间精确 CDS/蛋白重叠均为 0，全部保留输入唯一且翻译有效。
- 该结果不等于 deeper family/homology disjoint；后续需蛋白同源聚类与 family 级测试。

### 3.3 当前长度分层 benchmark

- 初版 `unique18` 的 17 条旧记录实际不在 v4 test，该版本作废。当前正式文件采用 `v4_test_unique18_length_stratified_v2`。
- 18 个唯一 ID/CDS/蛋白均逐字来自 v4 test；13 short、2 mid、3 long；train/val 精确 CDS/蛋白重叠均为 0。
- benchmark SHA256=`30e3dbbfc3480287b1f87177fe476d7ca283219f08949476da6d08555d0ab4e0`；独立审计见 `unique18_v4_independent_audit.json`。
- 当前 FASTA 不足以恢复可靠物种映射，因此只声称长度分层，不冒称 species-OOD，也不把该集合称为 HELD18 去重版。
- 全量分布审计：train/val/test 平均长度 1636.9/1645.0/1642.7nt、平均 GC 0.5149/0.5141/0.5137；benchmark 平均长度 642nt、GC 0.4396。组成差异已写入 41 页 PPT；描述性接近不作分布独立证明。
- v5 protein-homology-cluster 已完成：776,441 保留、85,671 精确蛋白重复、128 条 benchmark 连通簇排除；train/val/test=618,073/80,191/78,177。独立审计确认 split 簇不重叠、benchmark 簇不进入任何 split、精确重叠为 0 且数量守恒。MMseqs2 identity=0.5、双向 coverage=0.8 是操作定义，不等于 curated family；下游结果未完成前不写同源泛化结论。
- core seed-0 五方法独立复核通过：identity 全部 1.0；LD 6/6、GPT 100/100、GEMORNA 74/72、uniform 100/100、greedy 1/1。第 42 页 PPT 和 baseline 图仅作 baseline 证据，不作 CodonFlow 优劣裁决。
- 全参数 base-RLOO 逐路径反向完成 20 次更新，无 OOM，identity=1.0；梯度仍裁剪，校准效用变化 -6.9167e-05，未显示收益。不得写成收敛或性能提升。

## 4. Baseline、预算与指标

1. GEMORNA 必须从权威 benchmark FASTA 读取蛋白，逐条翻译核验后评分。旧 nanoLuc 239-aa EGFP-like 输入错误，旧结果作废；独立 `pc_cng` 环境可复现正确冒烟。
2. LinearDesign 的确定性 DP 解不能用随机同义序列补足 100 后冒名；旧 100 解含 7 DP + 93 random。uniform baseline 是 `uniform_synonymous`，不是无门控 Edit Flow。
3. 成本分开报告：输出解数、唯一 scorer 调用、模型 forward、端到端时间；旧 `steps*candidates` 和解序号 time-to-first 不可用于效率结论。
4. S3：同一基因/seed、全部模型联合参考域，轴 `min−5%×(p95−min)`，按 scale 归一化 HV；缺模型、缺 arm、零基线均显式列出，禁止静默剔除。
5. 主结果先通过 98+ 测试、真实 checkpoint 冒烟、identity/legal、完整方法池和预算核验，再写图/PPT/论文。
6. 初版 epoch-1 pilot 的 arm 级 forward/scorer 仅含末条轨迹，旧字段撤回；重算 immediate/short-rollout forward=16/944、唯一新评分=46/419、归一化 HV=0.1451/0.0804。仅为 4 条配对路径诊断，不用于收敛模型裁决。
7. `paired_same_initial_states_v4` 分开记录当前状态 base 枚举、rollout 批量 forward、rollout 轨迹、逐轨迹转移、cache 前终端请求、实际 scorer invocations 与跨路径唯一 scorer。v3 把每步累计请求再次求和，旧 102/194 作废；聚合只读每路径最终累计行。
8. 批量 rollout 中 R 条轨迹在同一时刻共享一次 forward。恒定 C、T 且 R>0 时，首 guided step=`1+T+C(T-1)`，完整路径 `F=T+T(T+1)/2+C*T(T-1)/2`；T=4,C=4 为 17/38，与 R 无关。实际 trace 是变候选数或截断路径的唯一依据。
9. canonical 冒烟使用冻结 epoch-5 checkpoint（`74a542c1`）和代码 `2854ebb6`，不再引用会更新的 live `best.pt`。base/immediate/short-rollout：identity=1.0，forward=8/8/76，终端请求=2/42/74，唯一 scorer=2/11/66，short-rollout 轨迹=64。HV 仅为 2 路径诊断，不作算法收益结论；本地/集群 98 passed、1 skipped，独立 JSON 复核通过。
10. `fig_a6_mechanism_costs` 与 PPT 第 43 页已完成，仅呈现机制和成本，不展示诊断 HV；新增页布局与 43 页中文渲染通过。
11. RLOO 的 2 源/20 步结果不作否定依据。`a6_rloo_queue` 曾计划使用完整 v4 train/val 和 32 个配对校准源，但已按用户收尾要求取消且未启动；后续须在收敛基座上重新评审。
12. 两臂于 epoch 6 主动停止并冻结恢复状态：edited-token val=4.3854775，full-token val=2.8195373，均未 plateau。unique18 仅 10/18 完整，1 条部分运行、7 条未启动；当前不能提交预印本或宣布 Gate C。

## 5. 论文逻辑与实验门

主线：**测量定义 → 有限步机制 → 学习与泛化 → 与经典方法的边界**。

1. 先证明可行性、预算、独立测试、联合 HV 的定义正确。
2. 在可枚举小状态精确验证 Doob 核，再用真实 immediate-vs-rollout 检验近似是否带来增益。
3. 在 v4 独立测试上比较 frozen base、不同目标函数与 path-RLOO；保存负结果。
4. 与真实基线比较目标覆盖、成本与长度/物种分层；未证实优势时写边界，不写领先。
5. 湿实验与真实表达量验证不在本轮声称范围内，CAI/MFE/GC/motif 只是计算目标，不能替代表达/稳定性证据。

## 6. 工程纪律

- 代码/commit 在 `/home`，大权重、数据与 artifacts 在 `/teams`，不上传大权重到 GitHub。
- 每个完成任务独立 commit + push，不强推；训练/评测日志、负结果与失败启动均保留。
- GPU 只用于真实任务；在 CPU 瓶颈或已有训练时不制造无意义显存占用。有效 batch 以实测吞吐与收敛选择。
- 模型训练到独立验证 plateau，禁止固定步数提前宣布收敛；最佳 checkpoint 与完整恢复状态必须可核验。
- 定时巡检若被用户取消不得重建；可用远端事件驱动日志与手动核验替代。
