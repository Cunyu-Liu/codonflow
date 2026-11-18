# CodonFlow A8 重构：真实功能约束、翻译动力学与 SOTA 执行路线

日期：2026-11-18  
版本：A8-RK v2（替代同日“反馈受控抢救版”）  
最新实现审查点：远端 `/home/codonflow`，HEAD=`012338aa9fe700b25846f73546f4d9b1b3d05870`，工作树干净；核心模型、训练和数据文件与本地镜像 SHA256 一致。  
证据标签：**[实现事实]** 代码或原始产物可复核；**[文献事实]** 已核对论文正文；**[科学假设]** 需要新实验；**[待数据审计]** 文献报告存在，尚需实际下载与解析。

---

## 一、执行摘要：为什么忙了很多，核心性能却没有提高

这不合理，也不能再用“工程已经很完整”来掩盖。此前的主线把训练收敛、run 数量、Gate、hash 和审计完成度当成了科研进展，但它们只能证明实验可追踪，不能证明模型有效。上一版 A8 又把“救活 frozen r5，失败则转负结果/benchmark”设为总路线，仍然偏离“提出重要科学问题并在各任务超过强 baseline”的目标。

性能停滞有六个直接原因：

1. **训练目标与终端任务不同。** 当前训练是天然 CDS 的同义腐蚀重建 CE，终端评价却要求 CAI/MFE/GC/motif 的 anytime Pareto 质量与时间优势。CE 下降没有通向终端 SOTA 的因果通道。
2. **模型没有解决问题所需的信息。** `EditFlowTransformer` 只读取 codon ID；不显式输入蛋白、天然 CDS、UTR、宿主、目标、结构或时间。推理 `_transition_tensors` 直接 `del time`。
3. **“离散流”名不副实。** `edit_flow_loss` 的实现说明已经明确它是 simplified masking realization，不是完整 CTMC rate objective。普通双向 Transformer、blank/token heads 和同义 mask 的组合本身也不构成前沿创新。
4. **旧对照混杂。** G2 中 learned 是 open-loop，hill/MH 使用终端反馈；T3.8 转正只说明反馈回路可能利用学习偏好，而且时间成本仍高。r5 失败不能否决其他科学模型。
5. **没有真实功能监督。** 项目主要优化计算代理，却没有用同义变体表达、适应度、半衰期或 Ribo-seq 数据回答“优化后的序列为什么更有生物功能”。
6. **baseline 没有跟上领域。** 旧清单遗漏 RNARL、ID3、CodonTransformer、COformer、VeloHARMO、EnsembleDesign 等直接强方法。即使赢内部 hill，也不足以证明 SOTA。

因此，A8 不再以“修补旧提议器”为主线，而改成一个可证伪的科学问题，并由科学问题推导数据、架构和实验。

> **核心科学问题：同义序列的功能差异，是否由“5′ 起始区结构可及性—全程翻译速度场—mRNA 降解”的空间耦合决定；显式学习这种耦合，能否在固定蛋白、固定 UTR/宿主上下文下，实现比现有方法更准确的功能预测和更高效的多目标 CDS 设计？**

一个月的目标是完成公开数据与强 baseline 的真实复现、机制假设的 OOD 检验、最小 CodonFlow-RK 及逐任务主结果。**SOTA 是实验目标，不是可以提前保证的结论；任何任务未赢最强可比 baseline，就明确保留为未解决，不能换弱 baseline 或拼接不可比数字。**

---

## 二、旧结果如何进入新故事

### 2.1 必须保留的实现事实

- G2 324/324 完成；FULL/EDIT 相对每基因最强简单搜索的中位 AUC 改善为 −94.28%/−93.47%，18/18 全负，Holm p=1.0。
- T3.8 的 15/15 个其余开发基因为正，FULL/EDIT 中位 AUC +59.95%/+68.73%，但耗时比中位 42.68×/2.41×，不是独立确认、实用优势或 SOTA。
- D4=621,306/76,444/78,724；D5=618,073/80,191/78,177。跨 split 精确 CDS/蛋白/ID 重叠为 0，D5 cluster 跨 split 重叠为 0。
- D5 是 MMseqs2 identity=0.5、双向 coverage=0.8 的操作性蛋白同源簇隔离，不是 curated family/species OOD。
- untouched24 仍未用于新模型选择。unique18 已反复开发，不再承担独立泛化证据。
- 原 sparse AUC 只在 B=50/100/500 计算并插入 `(0,0)`；新实验使用真实 B=1 起始的 dense budget-step AUC，缺失预算不补零。

### 2.2 旧结果在新论文中的唯一作用

旧结果用于说明：**合法生成、自然序列似然和工程收敛，并不等于功能感知的组合优化。** G2/T3.8 是引言或方法动机的诊断，不再作为整篇论文的结果中心，也不再拥有否决新数据、新机制和新架构的总 Gate。

旧 `proposal×feedback` 2×2 可低成本并行完成，以归因 r5；它不是 CodonFlow-RK 的前置许可。

---

## 三、科学假设与可证伪预测

### H1：独立标量代理不能充分解释同义变体功能

**依据。** Kudla 等在同一 GFP 的 154 个同义变体中观察到约 250 倍表达差异，CAI 不显著，而起始区折叠有较强关联；Boël 等在 6,348 次实验中发现密码子含量和 mRNA 水平的重要性，折叠主要影响初始约 16 个密码子；2026 年 Dasher 研究报告 CAI、GC、局部结构的单变量解释度有限，但其原始数据不公开，不能用于训练。

**预测。** 在统一宿主、UTR、载体和检测协议后，CAI/GC/全局 MFE 对 held-out 变体功能的增量解释低于空间结构与翻译动力学特征。

**反驳。** 若简单代理在严格蛋白/研究 OOD 上已经达到或优于复杂模型，则收窄“代理失效”叙事。

### H2：功能由空间耦合而非各位置独立偏好决定

**依据。** MAGE-seq 报告 12,726 个 infA 原位密码子突变，远端密码子可通过破坏 5′ RNA 构象影响适应度；VeloHARMO 使用五物种 Ribo-seq 表明速度谱具有宿主特异性，但真实表达验证仍很少。

**预测。** 显式 UTR–CDS/远程 pair channel、起始可及性和逐位速度场，能在相同骨干、参数和训练预算下提高蛋白 OOD、研究 OOD 的功能预测。

**反驳。** 去除 pair channel 或速度场不降低 OOD 表现，则相应机制不进入核心贡献。

### H3：翻译与降解的跨层一致性提供超出拟合标签的证据

**预测。** 同一模型或机制势应同时解释 MAGE 结构适应度、Ribo-seq 速度谱以及 Boël 的 mRNA/蛋白层变化；mRNA 水平与翻译占据应在适用数据中形成可检验的分层/mediation 关系。

**边界。** 公开回顾性数据主要支持关联和机制一致性，不能自动证明因果。

### H4：机制势能改善设计质量—成本前沿

**预测。** 偏好与预算条件的 CodonFlow-RK 在相同反馈、scorer/forward 和 wall-clock 下，超过各任务最强可比 baseline，并在 untouched/外源蛋白上重复。

**反驳。** 仅训练代理分数提高、真实 held-out 功能不提高，或等 scorer 赢而等时间输，均不能宣称实用 SOTA。

---

## 四、数据路线：先确认真正可用，再承诺任务

### 4.1 数据分层与当前状态

| 层级 | 数据集/来源 | 可提供的信息 | 当前判断与用途 |
|---|---|---|---|
| 自然先验 | 现有 D4/D5，25 物种 | CDS、蛋白、宿主先验 | 已复核；不作功能真值 |
| 自然先验 | CodonTransformer，>1M DNA–protein pairs、164 物种 | 宿主条件 codon/蛋白配对 | **[待数据审计]** 下载、版本、划分、污染 |
| 自然先验 | RNARL 六物种及多 RNA 类型，Zenodo `15486992` | 长序列、结构分布、baseline 数据 | **[待数据审计]** 直接复现其测试协议 |
| 翻译动力学 | VeloHARMO 所用五物种 Ribo-seq | 逐位 ribosome occupancy、宿主速度场 | **[待数据审计]** 只称相对速度代理；按研究/批次划分 |
| 真实功能 | Kudla et al., Science 2009 | 154 个同义 GFP，表达/mRNA/生长 | **[待数据审计]** 补充序列与测量，起始结构机制 |
| 真实功能 | Boël et al., Nature 2016，Protein Data Set | 6,348 次实验，蛋白表达、mRNA、寿命 | **[待数据审计]** 多保真功能监督与跨层验证 |
| 真实功能 | MAGE-seq, Kelsic et al., Cell Systems 2016 | 12,726 个 infA 单/双密码子突变和适应度 | **[待数据审计]** 远程结构耦合与突变效应 |
| 外部设计验证 | LinearDesign、GEMORNA、COformer 公开序列/补充表 | 已测或已发表设计 | **[待数据审计]** 只纳入序列和协议完整者 |
| 不公开 | Theodorou et al. Dasher/六蛋白数据 | HEK293/E. coli/Sf9 同义功能 | 原文明确 primary data 不公开；不得写入训练承诺 |

**原则：论文出现样本数不等于我们拥有数据。** 第一周必须实际下载、解析、翻译校验并冻结 SHA；无法获得者标为不可用，而不是用摘要数字冒充训练数据。

### 4.2 清洗合同

1. 保存原始 accession、release、URL、下载时间、许可、raw/clean SHA 和处理谱系。
2. CDS 必须长度整除 3、 alphabet 合法、一个终端 stop、无内部 stop，翻译与蛋白一致；起始 ATG、部分 CDS、异常转录本单独标记，不静默混入完整 CDS。
3. 功能数据必须尽量固定蛋白、5′/3′UTR、载体、宿主、化学修饰、启动子和检测协议；无法对齐的实验只分层分析，不直接合并。
4. 检查重复序列、重复测量、批次、测序/合成错误、检出限、缺失原因和表型动态范围；保留负结果与低表达变体。
5. 功能值只在 `protein×host×assay×batch` 内标准化；同时保留原始值、重复间噪声和测量单位。
6. Ribo-seq 按 read coverage、P-site/密码子映射、重复一致性、零覆盖和研究批次做 QC；occupancy 不等于绝对延伸速度。

### 4.3 分布与数据质量报告

- 自然数据：每 split 的长度、GC、CAI、MFE/EFE、氨基酸/密码子组成、宿主、蛋白簇大小和长尾分布；训练采样不能只让短序列/高丰度物种主导。
- 功能数据：每蛋白变体数、每宿主/assay 样本数、表达/适应度范围、重复噪声、突变位置和单/双突变比例。
- 数据覆盖缺口：哺乳动物公开同义功能数据可能不足；在证据出现前不得声称跨宿主功能泛化。

### 4.4 划分与泄漏

- 同时检查 exact CDS、exact protein、ID、MMseqs2 同源簇和功能来源蛋白。
- **同一蛋白的同义变体不得随机跨 train/test。** 功能主测试按蛋白分组；速度主测试另做研究 OOD；自然模型保留同源簇 OOD。
- CAI/RSCU、归一化、校准域和特征选择只用 train；第三方预训练重叠单独披露。
- untouched24 只最终使用一次；真实功能数据另设 untouched protein/assay，不因结果不好反复调参。

---

## 五、CodonFlow-RK：从物理与数学结构推导模型

候选名：**CodonFlow-RK（Ribosome-Kinetic Flow）**。这是待验证设计，不是已经实现的模型，也不预先宣称概念首创。

### 5.1 数学约束空间

给定蛋白 `a=(a1,…,aL)`，每个位置只在同义集合 `C(ai)` 上定义 categorical simplex：

`x=(c1,…,cL), ci∈C(ai)`。

蛋白一致性、长度和 stop 由参数化本身保证，不靠 post-hoc filter。固定真实 5′/3′UTR、宿主和实验上下文作为条件；本阶段不生成 UTR。

### 5.2 双分辨率物理表征

- **Codon 节点**：表示当前密码子、氨基酸/蛋白上下文、宿主、位置和剩余预算。蛋白编码器可使用 ESM2，但预训练模型本身不是贡献。
- **Nucleotide pair channel**：将候选密码子展开为三个核苷酸，用合法 RNA 配对约束的 pair interaction 显式建模 5′UTR–CDS、CDS 内部远程耦合。起始窗口高分辨率，远程采用稀疏/轴向交互控制 O(L²) 成本。
- **科学必要性**：MAGE-seq 的远程 5′ 构象效应和 Kudla 的起始区效应说明，仅做 codon embedding+全局 self-attention 没有显式对应这些生物学相互作用。

该 pair channel 是学习结构归纳偏置，不声称等价于精确 partition function；ensemble free energy 可由可靠物理计算或专门头监督。

### 5.3 统一的结构—翻译—降解势

同一上下文表示产生以下可分别监督、分别消融的量：

- `Φinit`：完整 5′UTR 与起始 CDS 的 accessibility/结构遮挡；
- `Φens`：全链 ensemble 结构项，而非只优化一个 MFE 构象；
- `v=(v1,…,vL)`：宿主条件逐位翻译速度场，含 native/host profile harmonization；
- `Φdecay` 与功能头：mRNA 降解、表达或适应度及不确定性；
- 独立约束项：motif、splice、重复序列等可明确计算的 penalties。

这些量不是任意黑箱 reward 的拼盘：结构项由结构/功能数据约束，速度场由 Ribo-seq 约束，功能项由同义变体测量约束。实验必须回答每一项是否有增量信息。

### 5.4 偏好与预算条件的合法 Markov flow

在自然先验核 `q0` 上，以候选编辑引起的势差定义提议：

`qθ(y|x;w,b,h,u) ∝ q0(y|x;h,u) × exp[-β Σk wk ΔΦk(x,y) - βc Δcost(x,y)]`，

其中 `w` 是 Pareto 偏好，`b` 是剩余预算，`h` 是宿主，`u` 是固定 UTR 上下文。用偏好条件轨迹平衡/能量倾斜目标训练，使终端反馈从训练开始就是模型的一部分，而不是训练 CE、推理再外挂 hill。

轨迹平衡、GFlowNet、ESM、attention 均不是新贡献。候选贡献是：**由真实数据约束的结构—速度—降解势、UTR–CDS 双分辨率交互，以及该势在同义合法空间中的统一生成。** 若数学目标与实现不一致，则不用“flow”命名。

### 5.5 多保真与不确定性

- 低保真：CAI、GC、motif，用于低成本预训练/筛选；
- 中保真：结构、accessibility、Ribo 速度场；
- 高保真：真实表达、适应度、半衰期。

模型输出预测区间/集成不确定性。最终功能评估不得只用参与候选选择的同一代理；优先使用 held-out 实验测量，其次使用完全独立 assay/模型并明确局限。

### 5.6 最小实现，不再堆模块

先只做机制预测头与 OOD 消融；成立后再接入现有合法单密码子核。暂不扩参、不同时加入 MoE、完整 CTMC、短 rollout 和 RLOO。任何保留组件都必须相对同输入、同参数/同成本的去组件模型有独立收益。

---

## 六、任务、benchmark 与 baseline 完整性矩阵

| 任务 | 数据/benchmark | 必须直面的 baseline | 主指标与 SOTA 判据 |
|---|---|---|---|
| 同义功能/适应度预测 | Kudla、Boël、MAGE-seq | CAI/GC/局部与全局 MFE、Boël logistic/codon-influence、通用序列模型、可复现的 VeloHARMO/COformer | 蛋白/研究 OOD Spearman、Pearson、RMSE、top-k enrichment；效应及 paired CI 下界>0 |
| 翻译速度预测 | 五物种 Ribo-seq | RiboMIMO、iXnos、ROSE、VeloGRU、VeloBERT | 蛋白 OOD 与研究 OOD R²/相关/RMSE；不能随机拆 codon 行造成泄漏 |
| 翻译 harmonization 设计 | VeloHARMO benchmark | VeloHARMO、CHARMING、tAI、ICOR、HFC/BFC/URC、RNARL | native/host 速度谱一致性与真实功能分层验证；等成本 |
| 起始区 accessibility 设计 | ID3 12 蛋白与固定 UTR | ID3 全部关键变体、GA、SA、C10/C10-CAI | 同 1000 离散评估；小窗口以枚举精确最优为 ceiling |
| CDS 多目标设计 | unique18+扩充蛋白、RNARL 六物种、untouched24 | LinearDesign、EnsembleDesign、RNARL、CAGFN、codonGPT、GEMORNA、CodonTransformer、COformer、hill/MH/SA/GA/random/r5 | dense budget-step HV AUC、实际预算 Pareto/best、NED、合法率、time-matched HV |
| 全长转录本外部边界 | 与固定 UTR 可比者 | mRNAutilus、ProMORNA | 只有输入/UTR/成本可统一才排名，否则单列不可比 |

补充要求：

- LinearDesign 的 DP/beam 实际输出不能伪造成 500 点轨迹；生成模型请求数与真实唯一解数分开。
- ID3 的连续 forward、离散 scorer 和内部更新成本全部记录，不能只计离散评估而隐藏优化成本。
- 每任务按官方默认/最佳可复现配置运行强 baseline，不用未经调优的外部实现反衬本模型。
- 每任务预注册“最强可比 baseline”选择规则；输给它即该任务尚未 SOTA。

---

## 七、环环相扣的实验链

### E0：数据与 baseline 是否真实可复现

**意义。** 排除“数据不存在、baseline 缺失、评价不可比”造成的假科学问题。  
**行动。** 完成下载/清洗/划分、官方方法 smoke、统一 scorer 与成本。  
**承上启下。** 只有真实功能数据成立，E1–E3 才具有生物意义；只有强 baseline 可运行，E4 的 SOTA 才有意义。

### E1：代理指标在真实同义变体上何时失效

**对照。** CAI/GC/全局 MFE/局部 MFE 与组合基线，在相同蛋白/研究 OOD 下比较。  
**观察。** 各 assay 的相关方向、强度、增量解释和失败区域。  
**结论边界。** 不复现失效就收窄动机；不能选择性只展示 Kudla。

### E2：空间耦合是否提供独立增量信息

**对照。** 同骨干依次加入起始结构、速度场、降解项和 pair channel；参数/训练计算匹配。  
**观察。** OOD 功能预测、跨长度/GC 层表现和不确定性。  
**承接。** 只有有效组件进入生成势；无效组件删除，不进入论文方法堆砌。

### E3：机制是否跨生物层一致

**对照。** MAGE 结构适应度、Ribo 速度、Boël mRNA/蛋白层的分别预测与联合预测；结构/速度/降解消融。  
**观察。** 跨层一致性、分层关联及适用条件下的 mediation。  
**承接。** 为 E4 的设计收益提供机制解释；若只有单 assay 拟合，不能写普遍机制。

### E4：机制引导是否真正提高设计性能

**对照。** 每任务最强外部与内部 baseline，同初始、反馈、目标和预算。  
**观察。** dense anytime 质量、实际 Pareto、功能 held-out、time-matched 和成本分解。  
**SOTA 判据。** 预注册主效应及 95% paired CI 下界均大于 0，Holm 校正通过，合法率 100%；不能只赢均值或 frozen r5。

### E5：优势来自哪个机制，而不是哪个额外模块

**对照。** 去 pair、去 initiation、去 velocity、去 decay、去自然先验、去偏好/预算条件；同参数与同推理成本。  
**观察。** 主性能下降是否对应 E2/E3 的机制结果。  
**承接。** 形成“组件→机制→性能”闭环，而不是事后按结果编解释。

### E6：能否 OOD 泛化并具有实用价值

**对照。** untouched 同源蛋白、功能来源蛋白、研究、长度/GC、宿主分层；等 scorer 与等时间。  
**观察.** 效应重复、失败区域、预测不确定性和是否只适用短序列。  
**边界。** 数据不支持的宿主/功能泛化不写；某一层失败必须展示。

### E7：真实功能与前瞻验证

**一个月目标。** 在公开 held-out 同义变体上做回顾性验证，候选排序不能只看训练代理。  
**顶刊必要后续。** 前瞻 design–build–test–learn：至少两个蛋白、明确宿主/UTR、WT/LinearDesign/RNARL 等对照、独立重复和功能/稳定性测量。未完成前不得写疗效、免疫原性或普遍表达提升。

---

## 八、统一评价、超参与统计

### 8.1 评价口径

- 真实初始点为 B=1；主曲线为 `ΣHV_b/(Bmax-1)` 的 dense budget-step AUC，不插入 `(0,0)`。
- 保留 B=50/100/500 Pareto/best、双向严格支配、NED、identity/legal。
- 分开报告 cache-before requests、唯一 scorer、模型 forward、生成时间、评分时间、wall-clock、GPU/CPU、并行度。
- 无真实轨迹的外部方法只比较实际输出集合；缺失为 `null`，不补零。
- 功能模型以蛋白/研究为独立单位；搜索以基因为独立单位，seed 先在组内聚合。

### 8.2 超参数设计

| 类别 | 预注册范围/策略 | 防止的问题 |
|---|---|---|
| 优化 | LR log-uniform、weight decay、dropout、grad clip、warmup；只在 dev 用 ASHA/小网格 | 不用 test 调参，不因默认 LR 误判架构 |
| 训练成本 | batch tokens、梯度累积、ESM 冻结层数、训练步数；同骨干比较计算匹配 | 把更多计算误当架构优势 |
| 物理/生成 | 能量温度、Pareto 偏好采样、轨迹损失系数、自然先验强度 | 任意 reward 权重和过优化 |
| 解码 | top-k、候选数、单/块长度、早停、batch；全部计入成本 | 隐藏 scorer/forward、时间虚高 |
| 数据采样 | 长度/宿主平衡、功能 batch reweight、多保真采样比例 | 短序列、优势物种和大 assay 主导 |
| 稳健性 | 至少 3 seeds 开发，最终按功效分析增加；关键超参做局部敏感性 | 单 seed 假阳性 |

超参选择只在开发集；test/untouched 冻结后一次评估。最小有效提升不机械统一为 10%，功能任务依据重复测量噪声预注册，设计任务依据 paired gene-level 效应与成本预注册。

### 8.3 统计

报告效应量、95% paired bootstrap CI、逐蛋白/逐基因方向和 Holm 校正。外部方法不可比时只报告边界，不强行合并排名。所有失败分层保留。

---

## 九、论文主线与图表合同

### 9.1 结果推理链

1. **现象**：同义变体功能差异巨大，而常用独立代理在统一上下文中解释有限。
2. **机制缺口**：自然语言模型与标量 reward 没有显式表达起始结构、远程配对、翻译速度和降解之间的空间耦合。
3. **科学发现候选**：真实数据表明哪些耦合项具有跨蛋白/跨研究的增量信息。
4. **方法推导**：由这些有效耦合项构造 CodonFlow-RK，而非先选 Transformer/RL 再找理由。
5. **性能证明**：在每个预注册任务上超过最强可比 baseline，并通过成本与 OOD。
6. **机制回扣**：生成性能消融与预测机制消融方向一致，解释何时、为何有效。
7. **真实价值**：公开变体回顾验证，最终以前瞻实验闭环。

### 9.2 主图安排

| 图 | 回答的问题 | 必要内容 |
|---|---|---|
| Fig.1 | 为什么现有代理不够 | 真实变体分布、代理失效、科学缺口 |
| Fig.2 | 什么机制有增量证据 | 起始结构、速度场、降解和 pair 的 OOD 结果 |
| Fig.3 | 模型如何由机制产生 | 约束空间、双分辨率交互、势函数与生成核 |
| Fig.4 | 是否达到各任务 SOTA | 强 baseline 主表、效应与 CI，不拼不可比任务 |
| Fig.5 | 为什么有效 | 预测与生成两侧对应消融、跨层机制一致性 |
| Fig.6 | 是否实用和泛化 | dense/time-matched、长度/GC/同源/宿主 OOD、失败区域 |
| Fig.7 | 是否有真实功能价值 | held-out 变体验证；前瞻实验完成后才加入 |

### 9.3 主张—证据矩阵

| 主张 | 必需证据 | 禁止替代物 |
|---|---|---|
| 空间耦合优于独立代理 | E1/E2 蛋白与研究 OOD 增量 | 随机变体拆分、单 assay 相关 |
| 模型学习翻译—降解机制 | E3 跨层一致性与消融 | 黑箱 reward 提高、注意力图 |
| 各任务性能 SOTA | E4 最强可比 baseline、同预算、CI | 只赢 r5/hill、弱外部配置 |
| 实用质量—成本优势 | E4/E6 time-matched 与全成本 | 只计 scorer、不计 forward |
| 可泛化 | untouched、来源蛋白/研究/长度/宿主分层 | 反复使用 unique18 |
| 生物功能提升 | 独立真实变体或前瞻实验 | CAI/MFE 代理提升 |

---

## 十、一个月执行路线与新 Gates

### Week 1：数据与强 baseline 真相（RK-G0）

- 实际下载并解析三类数据；冻结 raw/clean/hash、分布、QC、分组划分和数据卡。
- 跑通 LinearDesign、RNARL、ID3、CodonTransformer、VeloHARMO 等各自任务官方 smoke；不可运行者记录原因与替代边界。
- 完成 dense v2、原始 scorer 审计和统一成本口径。
- **通过条件**：数据真实可用，功能划分无同源/同蛋白泄漏，关键 baseline 有可复现输出。

### Week 2：机制科学假设（RK-G1）

- 完成 E1/E2/E3 的最小模型和蛋白/研究 OOD。
- 同骨干消融 initiation、velocity、decay、pair；估计测量噪声和不确定性。
- **通过条件**：至少一个机制组合在真实功能 OOD 上稳定优于简单代理和同骨干无机制模型。无增量则不启动昂贵生成训练，先修正科学问题。

### Week 3：最小 CodonFlow-RK 与逐任务 SOTA（RK-G2）

- 接入合法核与偏好/预算条件；只实现被 E2/E3 支持的组件。
- 完成功能预测、速度、accessibility、CDS 多目标主表和机制消融。
- **通过条件**：目标任务相对最强可比 baseline 的主效应与 CI 下界>0，合法率100%，成本完整。未获胜任务继续定向诊断，不换弱 baseline。

### Week 4：独立、机制回扣与论文（RK-G3/G4）

- 冻结模型后评估 untouched24、功能 untouched 和 OOD；完成 time-matched。
- 自动生成主图、消融图、失败图和主张矩阵；补齐预印本与复现包。
- **通过条件**：主要效应独立重复，故事每项主张有对应实验；否则收窄或删除主张。

旧 r5 2×2 只在低成本空闲资源并行，不阻塞 RK-G0/G1。不得读取 untouched 结果来修复模型。

---

## 十一、立即执行清单

1. **P0 数据下载审计**：Kudla、Boël Protein Data Set、MAGE-seq、VeloHARMO Ribo-seq、RNARL Zenodo、CodonTransformer；产出可下载性、样本数、协议、许可和 SHA。
2. **P0 功能数据卡与分组划分**：先按蛋白/研究隔离，再训练任何功能模型。
3. **P0 强 baseline 可运行矩阵**：优先 RNARL、ID3、LinearDesign、CodonTransformer、VeloHARMO；记录官方 commit、环境、输入、输出和成本。
4. **P1 代理效度 E1**：统一真实变体上的简单代理、组合基线和 OOD 结果。
5. **P1 最小机制模型 E2**：先不加生成器，验证 initiation/velocity/decay/pair 的增量。
6. **P2 CodonFlow-RK**：只有 RK-G1 通过后实现最小生成核与偏好/预算条件。
7. **并行遗留诊断**：dense v2、原始 scorer、r5 2×2，仅用于旧结果归因。

---

## 十二、不可逾越的表述边界

- 未实际下载的数据写“候选/待审计”，不能写“已利用”。
- Ribo occupancy 写相对速度代理，不能直接写绝对翻译速率。
- 公开回顾性关联不能直接写因果；因果需要干预或前瞻实验。
- 计算代理 SOTA 不等于表达、稳定性、安全性、免疫原性或疗效 SOTA。
- 未在某任务超过最强可比 baseline，不得宣称该任务 SOTA。
- 蛋白一致性、合法 mask、工程测试和 hash 是必要条件，不是核心创新。
- 顶刊版本需要真实功能与机制证据，最终仍需要前瞻湿实验；不能用文档中的计划冒充已完成结果。

**新的项目中心不是“如何救活旧模型”，而是“用真实数据识别同义序列功能的可推广机制，再把被证实的机制转化为各任务可测量、可复现、超过强 baseline 的设计能力”。**
