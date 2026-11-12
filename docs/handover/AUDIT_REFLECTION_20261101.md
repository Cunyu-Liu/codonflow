# CodonFlow 只读审计与自我反思（2026-11-01）

## 0. 范围与证据边界

- 已通读 `交接文档/` 中全部 10 份文档，并对照 `CodonFlow_preprint_draft.md`、`CodonFlow_preprint_A6_outline.md`、本地备份清单和可访问的划分记录。
- 本轮只做检查、推理和记录；未启动训练或评测，未修改代码，未修改现有 `spec.md`、`tasks.md`、`checklist.md`。
- 下文中的“已证实”指交接材料有一致记录，不代表本轮重新运行了远端审计。当前未访问集群原始 JSON；补充文献核查见第 10 节，仍不据此宣称 benchmark/baseline 已经找全。

## 1. 总结判断

当前不是“结果已经得到但不够好”，而是**有效学习结果尚未建立**：

1. 旧 full-token 模型虽达到验证集 plateau，但已因训练使用任意密码子破坏、推理从保蛋白状态出发而塌缩为“不编辑/复制”；其三臂及联合 HV 结果作废。
2. 新的 synonymous-corruption 两臂仅运行到第一轮中途，没有 checkpoint，也没有任何有效的新下游结果。
3. 旧 SOTA、capacity scaling、RL scaling、masking 因果、family/species OOD 和四层 benchmark 结论均不能进入新论文。
4. 当前真正可保留的资产是：有限步同义操作符、可枚举小状态验证、成本记录协议、v4/v5 内部划分审计，以及部分真实 baseline 输出。

**最大盲区**：尚未证明“学习模型”相对无学习同义采样和简单局部搜索有任何必要。约束合法、loss 下降、测试通过、Doob 公式成立，都不自动等于设计质量或计算效率提升。

**最没把握的两点**：

- synonymous corruption 修复后，模型是否不仅摆脱复制退化解，还能在相同 scorer 调用和端到端时间下超过 `uniform synonymous + immediate/local search`。
- 短 rollout 的近似 Doob 引导是否能带来足以覆盖额外评分成本的收益；如果 immediate 已足够，短 rollout 和离散流叙事都不能成为主贡献。

## 2. 科学问题与创新性反思

### 2.1 100% 蛋白身份不是充分的创新点

合法源 CDS + 单密码子同义编辑天然保持蛋白身份。LinearDesign、带同义 mask 的生成器和同义局部搜索也能保证该约束。因此：

- identity/legal = 100% 是实现正确性的必要条件，不是相对优势；
- 当所有访问状态都可合法保持蛋白时，终端门控中的可行性指示函数基本是冗余的；真正起作用的是偏好势函数与有限步引导；
- 论文不能把“我们 100% 合法而其他方法需要 mask/后处理”直接写成方法学优胜，必须证明质量—多样性—成本上的收益。

### 2.2 当前机制与简单马尔可夫搜索的差异尚未被证明

有限步单密码子跳转、即时终端奖励和短 rollout，若不能体现学习到的 proposal 或精确终端 tilt 的收益，容易被审稿人理解为带模型提议的局部搜索/Gibbs 式优化，而不是新的离散流能力。

需要回答的核心科学问题应改为：

> **在严格保持蛋白身份时，学习到的同义编辑提议能否在有限计算预算内改善多目标 CDS 优化的质量—多样性—成本前沿？短程终端引导在何处优于即时引导和无学习搜索？**

这个问题能把模型、机制、对照和论文结论连起来；“能否保持蛋白”不能承担主科学问题。

### 2.3 RLOO 目前不应作为第二支柱

在严格同义状态空间中，翻译一致性奖励是常量或近常量，不能提供有意义的反向学习信号。旧“双奖励必要性”又属于不同算法语义，不能迁移到新 path-RLOO。

因此 RLOO 目前只有工程冒烟和极小负结果，没有概念上和实证上足以支撑主贡献的依据。它应在基座价值成立后重新评审，而不是继续占用主线。

## 3. 预训练、模型架构与下游任务盲区

### 3.1 synonymous corruption 只修复了蛋白约束，不保证修复任务不匹配

训练目标是从自然 CDS 的同义腐蚀中恢复原序列，采样却从随机或配对同义状态出发，并由 CAI/MFE/GC/motif 终端偏好推动序列远离自然状态。仍有两层分布差距：

1. 自然序列恢复 vs 目标驱动优化；
2. 均匀同义腐蚀状态 vs 模型实际访问的偏好引导状态。

所以“训练/推理都保蛋白”是必要条件，不是充分条件。G0b 的 stay-p 和 P(edit) 只能排除复制退化，不能证明偏好学习有效。

### 3.2 收敛判据不等于任务有效

旧模型已经证明 val plateau 可以与无效下游行为同时发生。新验收必须分为：

- 优化收敛：独立 val plateau；
- 行为非退化：编辑率、位置覆盖、转移熵、对初始状态和奖励的响应；
- 任务价值：同预算下超过无学习与简单搜索对照。

G0b 目前只有“明显下降/上升”的定性语言，没有预注册阈值，也存在事后挑选阈值的风险。高 stay-p 本身也未必错误，必须结合每步目标编辑数、序列长度和路径预算解释。

### 3.3 模型容量不是当前主要矛盾

旧 56M/355M loss 差和下游曲线已不能支持容量因果。继续扩大模型之前，必须先证明 56M 在同义状态上能学到可迁移、可用于优化的 proposal。否则扩参只会放大无效目标。

full-token 与 edited-token 的 val 不可直接比较；最终只能用同一冻结下游协议裁决。模型架构的关键消融不是“更大”，而是 learned vs unlearned、trained-from-scratch vs pretrained、full-token vs edited-token 的下游收益和成本。

### 3.4 下游任务定义混淆

当前材料混合了两种输入任务：

- warm-start：给定自然 CDS，在保持蛋白的前提下改进；
- de novo design：给定蛋白，从同义初始序列设计 CDS。

CodonFlow 使用源 CDS，而 GEMORNA/LinearDesign 可只使用蛋白，输入信息并不天然相同。必须先固定任务，再规定所有方法的输入与初始化，不能把两种任务混为“同一 benchmark”。

此外，当前方法实际是固定长度 synonymous CDS optimization，不是广义 mRNA editor；不覆盖 UTR、剪接、表达调控或真实 RNA 编辑。论文标题和结论应收窄到 CDS 设计。

## 4. 数据、清洗、分布、泄漏与划分审计

| 检查项 | 当前证据 | 审计结论与缺口 |
|---|---|---|
| 数据集找全 | v3 输入 862,240 条、25 物种；v4 776,474 唯一蛋白；v5 776,441 条同源簇隔离 | **未闭环。** 数量接近期初目标不代表覆盖充分；缺物种/基因家族/功能/长度联合覆盖表，且 v5 缺可靠物种元数据。 |
| 清洗方法 | 文档记录长度、阅读框、起止、内部 stop、ambiguous base、精确蛋白去重和 MMseqs2 聚类 | **部分闭环。** 需补 transcript/biotype、非标准遗传密码、注释质量、异常蛋白、短/长序列排除对总体偏差的影响；应报告每一步过滤数量和原因，而非只报终值。 |
| 数据分布 | 有长度/GC 全量图；v4 平均长度/GC 接近；v5 val 长度偏高 | **未闭环。** CAI/RSCU/密码子使用、物种占比、簇大小、基因家族和重复/亚型结构不完整。unique18 平均长度 642 nt、GC 0.4396，与训练集约 1640 nt、GC 0.514 差异明显，不能代表自然总体。 |
| 序列泄漏 | v4 精确 CDS/蛋白交叉重叠为 0；v5 0.5 identity、双向 0.8 coverage 簇隔离，benchmark 连通簇排除 | **内部精确/操作定义同源泄漏有证据，但不是全部泄漏。** 仍需结构域/远缘同源、聚类连通性、外部 baseline 预训练重叠和参考表来源审计。v5 不是 curated family/species OOD。 |
| 指标/参考表泄漏 | CAI 表来自 v4 train | v4 任务内方向正确；若改用 v5 数据划分，必须确认参考表只由对应 train 构建。还应检查 normalization quantile、motif 列表、超参选择是否接触 test/benchmark。 |
| 自适应泄漏 | unique18 来自 test，已被反复用于设计与调试 | **存在测试集自适应过拟合风险。** 序列不重叠不等于反复开发后的 benchmark 仍是最终独立测试；需要 untouched holdout 或外部确认集。 |
| 数据质量 | 有翻译有效、身份和输入哈希检查 | **生物质量未闭环。** 合法 CDS 不等于适合学习表达/稳定性；没有宿主、表达证据、UTR/序列上下文或湿实验质量标签。 |
| 数据集划分 | v4 蛋白唯一；v5 蛋白同源簇隔离 | **比 v3 明显改善，但仍需分层与效用验证。** 簇级随机划分造成 v5 val 长度偏移；需报告簇大小加权和序列级分布，并固定最终 test 的使用纪律。 |

额外注意：`v5 protein-homology-cluster` 数据版本与 `a6_v5_syn_*` 训练版本命名冲突，容易把“同义腐蚀修复版”误读成“v5 同源划分训练版”。后续合同必须分开命名。

## 5. Benchmark 与 baseline 审计

### 5.1 Benchmark 未找全，也未形成有说服力的任务覆盖

- core 只有 eGFP/nanoLuc；unique18 是人工长度分层的小集合，13/18 为短序列，物种映射不可靠。
- 旧 HELD18、cross-family、Cas9 等结果存在泄漏、来源或不可复核问题，不能继续作为四层证据。
- 缺少与 LinearDesign、codonGPT、GEMORNA 等原文任务相对应的公开 benchmark 对照，也缺少最终未参与开发的外部/冻结确认集。
- 长度分层、宿主/物种分层、目标组合和 warm-start/de novo 应分别定义，不能用一个小集合同时承担所有泛化主张。

### 5.2 Baseline 明确未找全

文档自身已列出 ProMORNA、mRNAutilus、RayGun、SCISOR，但并未全部形成可复现数值对照。更重要的是，当前缺少最直接检验“学习是否必要”的强简单基线：

- 相同同义操作符下的 uniform random proposal；
- greedy/hill-climbing、simulated annealing 或 Metropolis-Hastings 等同预算局部搜索；
- random restart、beam/top-k 搜索等相同 scorer/cache 的非学习优化器；
- 与 CodonFlow 相同初始状态、相同目标函数、相同终端评分的同核对照。

没有这些对照，即使胜过 LinearDesign/codonGPT，也无法判断收益来自学习、搜索协议还是评分预算。

外部 generative baseline 还有输入信息、预训练数据不可审计、上下文长度和输出解数不同等问题。架构性排除应显式报告，但不能让主结论依赖对手无法运行。

## 6. 测评方法的关键漏洞

### 6.1 “相同解数”不是相同预算

LD、GEMORNA、codonGPT 和 CodonFlow 的真实唯一解数不同，forward 不可见程度也不同。应分别报告：

1. 固定唯一输出数下的 Pareto 覆盖；
2. 固定 scorer 调用下的 best-so-far/anytime 曲线；
3. 固定端到端时间下的质量；
4. 模型 forward、RNAfold 调用和墙钟成本的分解。

不能用单一“100 解”宣称全面公平，也不能通过随机补样制造表面等预算。

### 6.2 当前 joint HV 仍不稳定

当前参考域按 gene/seed、由参评方法输出共同计算，scale 又取 q95-min，存在三个问题：

- 增删方法或改变 seed 会改变归一化，跨 seed 平均和跨表比较不稳；
- q95/min/max 会受异常点和方法池影响；
- CAI-greedy 只有 1 个解，而随机方法有多个非支配点，HV 同时混合了质量、输出数量和多样性。

共同参考域可用于同一冻结实验内部，但应增加独立校准的固定范围、原始目标前沿、每目标 best-at-budget、IGD+/epsilon 或 non-dominated coverage，避免结论只依赖 HV 单一口径。seed 间参考域应冻结，统计按 gene 分层。

### 6.3 代理指标的生物意义不足

CAI 依赖宿主参考集；跨物种共用 pooled RSCU 和固定 GC=0.55 缺乏统一生物解释。MFE 也依赖 RNAfold 版本与 folding 条件，不能直接等同稳定性或表达量。motif 数量需长度归一化并说明生物依据。

没有湿实验时，论文只能声称计算代理目标优化，不能声称提高表达、稳定性、安全性或治疗效果。

### 6.4 统计单位需要重建

3 个采样 seed 不是 3 个独立生物样本；18 条人工选择序列也不能支持广泛总体推断。应以基因为主要独立单位，使用分层 bootstrap/配对检验，披露小样本和多重比较；不能把同一基因的多 seed 当作完全独立 n。

## 7. 论文主线为何仍然不清晰

现有“测量→机制→学习→边界”是工程验收顺序，不是吸引读者的科学故事。它从“我们如何把测量做对”开始，而不是从“领域内什么重要问题尚未解决”开始。

建议讨论的主线如下，暂不写入合同：

1. **重要问题**：固定蛋白的 CDS 多目标优化需要同时控制质量、多样性与计算成本；DP、生成先验和局部搜索各有适用边界。
2. **真实缺口**：尚不清楚学习到的同义编辑提议能否在非平凡多目标和有限预算下提供可迁移收益；硬约束本身不是难点。
3. **方法假设**：有限步 learned proposal + terminal tilt 可以在严格保蛋白的同时改善 anytime 优化；short rollout 只在终端收益大于额外成本时有价值。
4. **第一组证据**：小状态精确验证 + 大状态近似偏差/成本，证明机制被正确实现，而不是证明方法已经更好。
5. **决定性证据**：learned vs uniform vs immediate/local search，同初始化、同 scorer/时间预算，在 homology-disjoint 序列上比较；先证明学习有必要。
6. **外部定位**：再与 DP/AR/generative baseline 比较，按目标数、长度、任务类型和预算画能力边界。
7. **结论**：只说在哪些条件下 learned editing 有收益、在哪里没有；RLOO、扩参和湿实验只在证据成立后进入主线。

每一环的承上启下关系是：**优化效率问题 → 需要可学习提议 → 提议必须有正确机制 → 正确机制仍需证明相对简单搜索的收益 → 有收益后才讨论相对现有系统的边界。**

若决定性证据失败，诚实结论应是“学习提议未显示收益”，而不是退回 100% identity 或重新包装旧 scaling 结果。那时可形成技术报告/负结果，但强方法论文的发表性仍有限。

## 8. 自我反省

此前项目和我沿用的分析存在以下偏差：

1. 让“离散流、Doob、RLOO、scaling”等方法名词先于价值命题，导致实验围绕组件齐全而非关键反证展开。
2. 把 by-operator 的 100% identity 当成性能优势，把 val plateau 当成学习有效，忽略了最简单的无学习对照。
3. 在基座尚未通过行为 sanity check 前投入 355M、RLOO、OOD 和图表，扩大了无效实验的沉没成本。
4. 把审计通过写成“数据/指标闭环”，但审计主要覆盖内部重叠与计算一致性，没有覆盖代表性、生物有效性、测试集自适应和参考域稳定性。
5. 叙事中把相关性写成容量/RL 因果，把工程验收顺序误当科学推理链。
6. 文档更新滞后造成新的执行风险：当前 runbook 仍有指向已证伪 v4 checkpoint 的命令和旧训练路径，spec/tasks/outline 的状态也彼此不一致。讨论后必须统一重写，而不是局部补丁。

## 9. 讨论时需要先决定的五件事

1. 主任务到底是 warm-start CDS editing，还是 protein-to-CDS de novo design？二者不能混写。
2. 主贡献是否同意改为“有限预算下的 learned synonymous proposal 是否优于无学习搜索”，而非“100% 合法”或 RLOO？
3. 是否同意把 RLOO、355M scaling、species/family OOD 全部降为可选后续，先完成 learned-vs-simple-search 决定性对照？
4. 论文只声称计算代理优化，还是把湿实验作为最终发表的必要证据？这决定目标期刊和故事边界。
5. 最终 benchmark 如何划分开发集与 untouched confirmation set，并如何覆盖外部 baseline 的原始任务？

以上问题讨论定案后，再统一修改 `spec.md`、`tasks.md`、`checklist.md`、`RUNBOOK_NEXT.md` 和 A6 preprint outline，形成单一事实来源。

## 10. 补充文献与资源审计（2026-11-01）

本轮通过论文原文页面补查了直接相关工作。以下来源证明“baseline 已找全”不成立，也进一步收窄了可主张的创新点。

### 10.1 直接竞争的 mRNA 设计方法

- [mRNAutilus, arXiv:2605.31296](https://arxiv.org/abs/2605.31296)：masked discrete diffusion + Monte Carlo Tree Guidance，多目标优化 CDS 与 UTR；原文报告从 14.2M vertebrate mRNA 起始、清洗后 5,526,848 条，并在 Fluc、SARS-CoV-2 Spike、PEMax、uAb 等任务做了体外验证。它已覆盖“离散生成 + 推理时搜索 + 多目标 + 湿实验”，因此 CodonFlow 不能以这些组件的组合作为独立创新。访问版本的 Data and Code Availability 小节未给出可用实现链接，数值复跑状态仍待核查。
- [ProMORNA v2, arXiv:2605.01513](https://arxiv.org/abs/2605.01513v2)：6M+ protein–mRNA pairs、SFT + multi-objective RL、全长 mRNA 生成；在 Fluc2P 上使用独立 Saluki 评价器并进行了三次独立体外实验。它直接削弱“label-free/multi-objective RL 本身是新贡献”的空间。访问文本中未找到公开实现链接，不能把“未复跑”写成“方法不可复现”。
- [mRNA-GPT, bioRxiv 2026](https://www.biorxiv.org/content/10.64898/2026.03.31.715707v1)：30M full-length natural mRNA 预训练，PPO + oracle rewards，支持多目标全长设计。该方法不在现有交接 baseline 清单中，至少必须进入 related work 与复现资源核查表。
- [codonGPT, Nucleic Acids Research 2025](https://doi.org/10.1093/nar/gkaf1345)：正式题名即为“reinforcement learning on a generative language model enables scalable mRNA design”。因此“把 RL 用于 codon/mRNA 设计”本身也不是空白；CodonFlow 若保留 RL，必须证明特定路径目标或奖励机制的差异与收益。

这些方法的任务和指标并不与 CodonFlow 的 CDS-only 设定完全相同，不能拿论文摘要数字直接横向比较；但它们是定位创新性时必须正面讨论的强相关工作。

### 10.2 离散流与多目标搜索的直接方法学对照

- [AReUReDi, arXiv:2510.00352](https://arxiv.org/abs/2510.00352)：已经结合 Tchebycheff scalarization、locally balanced proposals、annealed Metropolis-Hastings，面向多目标离散序列优化，并报告 Pareto 收敛性质。虽然其实验域是 peptide/SMILES，不是 mRNA，但它与 CodonFlow 的“同义状态空间 + 多目标 + 局部离散搜索”高度同构，是最重要的缺失方法学对照之一。至少应实现同操作符、同评分预算的 AReUReDi-style MH/annealing 对照，或清楚解释为何不适用。
- [MOG-DFM, arXiv:2505.07086](https://arxiv.org/abs/2505.07086)：逐步计算 candidate transition 的 rank-directional score，并用 adaptive hypercone filter 引导多目标离散流，实验覆盖 peptide 与 enhancer DNA。其 [ICLR 2026 OpenReview 页面](https://openreview.net/forum?id=I8JpOPrVDX)标记为 withdrawn；公开评审提出长序列逐位置更新效率、等计算成本 best-of-N、新颖性和缺失强 baseline 等质疑。这些评审不是对 CodonFlow 的结论，也不是对该工作的最终质量裁决，但正好是 CodonFlow 应提前回答的审稿风险。
- [TR2-D2, arXiv:2509.25171](https://arxiv.org/abs/2509.25171)：tree-search 构造轨迹 replay buffer，再做 trajectory-aware discrete diffusion fine-tuning。它与“rollout + 路径训练”的论证直接相关，应进入 RLOO/轨迹微调相关工作。
- [pCoMole, arXiv:2610.01663](https://arxiv.org/abs/2610.01663)：已经给出 feasibility-gated terminal distribution、augmented Tchebycheff、Doob-h 和短 MC rollout，并有蛋白编辑湿实验。CodonFlow 当前实质上是其在固定长度同义 CDS 空间的特化，必须证明该特化带来了新的科学现象或测量结论，不能只更换生物域。

### 10.3 对 benchmark/baseline 清单的修正

1. **P0 数值对照**：同操作符 uniform、greedy/hill-climbing、Metropolis-Hastings/annealing、AReUReDi-style 搜索，以及 base/immediate/short-rollout。它们回答“学习和引导是否必要”。
2. **P1 外部 CDS 对照**：LinearDesign、GEMORNA、codonGPT；保持现有真实输入核验与成本口径。
3. **P1 资源核查**：mRNAutilus、ProMORNA、mRNA-GPT。若有代码/权重或公开候选序列，在相同 CDS-only 协议下比较；若无法复跑，列入“相关但未能数值复现”，不得用不同任务的摘要数字拼表。
4. **已从数值 baseline 排除**：[RayGun](https://doi.org/10.1038/s41586-026-10842-8)是蛋白缩短/改造方法；[SCISOR, arXiv:2511.07390](https://arxiv.org/abs/2511.07390)是蛋白删除扩散模型。二者都不是固定蛋白的同义 CDS 设计，不应为了名单完整进入主表；至多作为更广义的蛋白编辑相关工作。
5. **候选外部任务**：Fluc2P/GenScript F-Luc、Spike、PEMax、MUC1 和 uAb 是上述论文使用过的任务，可帮助覆盖 reporter、antigen、长编辑器和非报告基因；但它们尚不能被一概称为统一公开 benchmark，需逐条核查序列、实验条件和许可。

### 10.4 对发表性的进一步影响

直接竞争工作已经具备更大数据、多目标引导或 RL、独立预测器验证及湿实验。CodonFlow 若没有 learned-vs-simple-search 的明确收益，仅靠“同义合法性 + pCoMole 转移 + 计算代理指标”难以形成有竞争力的方法论文。最可行的差异化仍是：**固定蛋白 CDS 上，对有限步学习提议、近似终端引导和真实计算预算做严格、可复现的因果对照。**这是一条窄而清楚的主线，不应再扩展到全转录本或疗效宣称。

## 11. 讨论用主张—证据矩阵与推荐默认方向

本节只是把审计结论整理成可讨论形式，不替代用户对主任务的最终决定，也未写入现有合同。

### 11.1 推荐默认方向

基于当前实现以源 CDS、同义初始状态和配对编辑路径为中心，较自然的默认主任务是 **warm-start synonymous CDS editing**：给定一个已经编码目标蛋白的 CDS，在严格保持蛋白的前提下改善计算代理目标。protein-to-CDS de novo design 可作为单独初始化条件的次级压力测试，但不能与 warm-start 混成同一结果表。

相应的主假设建议收敛为：

> 在相同初始蛋白/CDS、相同终端目标和相同 scorer 或时间预算下，学习到的有限步同义提议相对最强无学习局部搜索改善 anytime 多目标优化；short-rollout 只有在收益覆盖额外成本时才被保留。

该假设允许被明确证伪，并把身份保持放在方法性质而非性能结果的位置。

### 11.2 主张—证据—缺口—降级矩阵

| 论文主张 | 当前可用证据 | 仍缺的决定性证据 | 若证据不成立 |
|---|---|---|---|
| C1 有限步同义核和终端 tilt 被正确实现 | 合法操作符、小状态精确验证、成本 trace | 大空间近似偏差随 rollout/候选预算的变化 | 只能保留小状态机制结果，降低大空间理论表述 |
| C2 预训练产生非退化编辑器 | 旧模型反例；新 synonymous run 无 checkpoint | 新模型的行为检查、奖励响应、位置覆盖和独立 val | 停止下游宣传，先修训练/采样状态匹配 |
| C3 learned proposal 相对简单搜索有必要 | 无有效新结果 | learned vs uniform/hill-climbing/MH/AReUReDi-style 的同预算配对比较 | 不能写学习方法优势；转为负结果或测量研究 |
| C4 short-rollout 值得额外成本 | 只有协议冒烟和已作废旧三臂 | immediate vs short-rollout 的 anytime 质量—成本前沿 | 删除 short-rollout 主贡献，只保留 immediate 或负结果 |
| C5 相对现有 CDS 方法有明确适用边界 | 部分 LinearDesign/GEMORNA/codonGPT 等 baseline 输出 | 有效 CodonFlow 列、统一输入任务、联合指标和四成本 | 只能描述 baseline，不写 CodonFlow 外部优势 |
| C6 具有同源泛化能力 | v4/v5 划分与内部泄漏审计 | v5 训练后的独立下游结果和最终确认集 | 仅写数据划分，不写 OOD 泛化 |
| C7 改善表达、稳定性或治疗效果 | 无 | 独立生物预测器和/或湿实验 | 全文禁止生物功效宣称，仅限计算代理优化 |

### 11.3 与证据对应的论文推理链

1. **问题不是合法性，而是受限优化的预算效率。**同义操作使蛋白身份成为不变量，真正未解决的是多目标质量—多样性—成本。
2. **因此需要一个可学习但仍可审计的提议核。**介绍有限步 learned proposal 与 terminal tilt，并立即区分精确小状态和大空间近似。
3. **正确实现并不蕴含学习有用，所以先做行为与简单搜索反证。**C2 是 C3 的前置门，C3 是整篇论文第一个决定性结果。
4. **只有 learned proposal 有收益，才追问 rollout 是否进一步改善。**C4 必须同时呈现质量和成本，不能只报 HV。
5. **内部机制成立后，才定位相对外部方法的边界。**C5/C6 回答何时使用 CodonFlow、何时选择 DP、生成模型或简单搜索。
6. **最后讨论限制。**代理指标、小样本、外部预训练不可审计和无湿实验均进入边界，不用讨论章补写未做的实验。

这条链中每一步都由上一环未解决的问题触发，避免“数据审计做完了，所以下面讲模型；模型跑完了，所以下面讲 RL”的工程日志式结构。

### 11.4 主图顺序建议

- **F1 方法与不变量**：同义状态空间、有限步核、终端 tilt；identity 是方法性质。
- **F2 非退化与机制检查**：新旧状态分布、编辑响应、小状态精确性和近似成本；旧复制模型只作诊断对照。
- **F3 决定性结果**：learned vs 简单搜索的 anytime 质量—成本前沿；这是全文中心图。
- **F4 rollout 消融**：immediate/short-rollout 在相同冻结基座上的收益和额外成本。
- **F5 外部边界**：与 CDS baseline 按目标数、长度和预算分层比较。
- 数据泄漏修复、历史错误 baseline、OOM 和不可复核旧表放补充材料或审计附录，不占主叙事。

当前能诚实写作的是 Introduction、Method、Evaluation Protocol 和机制验证；C2–C6 没有证据前，不应先写 Results 结论或 Discussion。

## 12. 合同文档漂移与误执行风险清单

以下只登记问题，不在本轮修复。讨论后应以一个带时间戳的权威状态块同步全部文件，而不是继续追加互相覆盖的“当前状态”。

| 位置 | 已发现的问题 | 后续修订要求 |
|---|---|---|
| `spec.md:9-18` | 仍停留在 2026-10-30：旧两臂训练中、无 converged；未反映旧 full-token 已证伪和新 synonymous run 无 checkpoint | 用最新事实替换；区分“优化收敛”与“下游有效” |
| `spec.md:20-27` | H2 将预训练与 path-RLOO 捆成一个假设，缺少 learned-vs-simple-search 的第一价值假设 | 拆成非退化、学习必要性、rollout 净收益、外部边界；RLOO 降级 |
| `spec.md:72`、`tasks.md:4-8`、`RUNBOOK_NEXT.md:8-15` | `v5` 同时指 protein-homology 数据版本和 synonymous-corruption 训练版本；新 run 实际仍使用 v4 split | 数据版本与训练版本使用不同名称，命令显式写数据 SHA256 |
| `tasks.md:3` | “数据/指标/机制已闭环”超过证据：参考域稳定性、代表性、自适应测试和生物有效性仍开放 | 改为逐项状态，禁止总括闭环 |
| `tasks.md:20-22`、`tasks.md:67-68` | 仍将旧 v4 两臂写成当前运行/待收敛，锚点已失效 | 标记旧臂证伪，仅保留负结果证据；新臂无 checkpoint |
| `checklist.md:133-139` | G0 已勾选只代表旧 plateau，不能代表有效模型；G0b 只有“明显下降/上升”没有阈值 | 将 G0 与 G0b 绑定；在运行前预注册行为阈值和任务价值门 |
| `RUNBOOK_NEXT.md:33-38` | G0 核验命令仍指向已证伪 v4 checkpoint | 禁止用于新实验；旧命令移到历史附录 |
| `RUNBOOK_NEXT.md:61-71` | G2 示例仍读取 `a6_v4_56m_r2/converged.pt` | 标为不可执行；新命令只能接受通过 G0b 的冻结 checkpoint |
| `RUNBOOK_NEXT.md:90-105` | 方法池缺同操作符简单搜索/AReUReDi-style；通过 G0–G3 就写 Results，缺少学习必要性门 | 在 G2 前加入 learned-vs-simple-search；联合 HV 不是唯一通过标准 |
| `spec.md:81`、`RUNBOOK_NEXT.md:103` | 退化轴一处写“用 1 并记录”，另一处写“拒绝，allow-degenerate 才继续” | 统一成一个预注册规则，并说明对可比性的影响 |
| `checklist.md:43` | 历史 A4 将 RayGun/SCISOR 等名称存在视为 baseline 找全；新文献又发现 mRNA-GPT/AReUReDi 等遗漏 | 历史勾选标记 superseded；按任务相关性、可复现性、必要性重建清单 |
| `CodonFlow_preprint_A6_outline.md:34-37` | Measurement 标为 closed，但 joint-HV 跨 seed/方法池稳定性和最终确认集未解决 | 降为“内部计算口径已统一，外部有效性待验收” |
| `CodonFlow_preprint_A6_outline.md:48-64` | Learning/Boundary 状态仍引用旧 e7/e8 和 unique18 12/18，已经过期 | 从最新 manifest 生成状态，禁止手工沿用旧计数 |
| `CodonFlow_preprint_A6_outline.md:18-20` | H1 将“精确机制失败”与“short-rollout 不如 immediate”作为同一证伪条件；机制正确性和算法效用被混合 | 拆成 H1a 实现正确性、H1b 近似效用与成本 |
| `CodonFlow_preprint_A6_outline.md:99` | F5 仍是旧两臂训练曲线，旧 full-token 已证伪 | 只能放审计附录，不能作为当前学习进展图 |

另有两个结构性问题需要一并处理：

1. **Gate 命名漂移**：旧 Gate A/B/C、RUNBOOK 的 G0–G4、后续 G0b 并非同一套稳定语义。后续合同应给每个门固定 ID、科学问题、输入条件、量化阈值、失败后的降级路径。
2. **历史与当前混排**：大量文件用顶部追加新状态、正文保留旧“当前”。后续应将历史日志与有效合同分离；合同只保留一个当前状态，旧内容通过链接追溯。

## 13. 决策落实记录（2026-11-01）

用户已确认采用推荐默认方向：以 warm-start synonymous CDS editing 为主任务，以 learned vs 无学习简单搜索为第一决定性关卡。

据此已完成以下文档重写：

- `spec.md`：固定主任务、H1a/H1b/H2/H3/H4、数据与评测合同、G0–G5 和降级规则；
- `tasks.md`：按 G0→G5 重排任务依赖，RLOO/扩参移出主关键路径；
- `checklist.md`：废弃旧勾选继承，建立当前有效验收清单；
- `RUNBOOK_NEXT.md`：撤下已证伪 checkpoint 命令，改为按科学门执行的操作手册；
- `CodonFlow_preprint_A6_outline.md`：以 learned-vs-simple-search 为中心结果重建科学故事。

统一后的顺序为：**G0 数据与协议 → G1 模型收敛且非退化 → G2 learned vs 简单搜索 → G3 rollout 净收益 → G4 独立确认与外部边界 → G5 论文发布。**

本轮仅修改文档，未启动训练或评测。当前唯一允许推进的任务块为 P1/G0 数据与协议就绪。
