# 给下一位执行者的完整提示词（CodonFlow A10 · Kinetic-CodonFlow）

> 生效日期：2026-11-23。A10 是当前研究与执行入口；A8/A9 只保留历史和冻结协议。
> 本轮不是继续救 frozen r5、补窗口消融或增加 PPT，而是重建“科学问题—数据—模型—性能—论文”闭环。

## 0. 先读与权威状态

先读：

- `docs/handover/DECISION_A9_20261122.md`：阳性核心、生成训练授权和公平比较要求。
- `docs/handover/HANDOFF_A9_RK42_20261122.md`：公开数据逐源审计与 0/9 的准确含义。
- `docs/handover/HANDOFF_A8_RK37_20261122.md`：跨研究翻译占据失败。
- `experiments/REGISTRY.md` 中 RK21–RK42。
- `src/codonflow/models/edit_flow.py`、`ribokinetic.py`、`minimal_neural.py`、`synonymous_markov.py`。
- 本提示词；旧 A8/A9 prompt 不再指导新实验。

最近只读核对：GitHub `a8-rk` HEAD=`8200c5617748`，RK42 已完成；开始执行时必须重新核对远端 HEAD、共享工作树、进程和数据状态，不能假设仍未变化。权威工作树为 `/home/codonflow-a8-rk`，大型资产放 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/`。本地继承的 dirty/untracked 文件必须保留，不覆盖远端，不 `git add -A`，不 `reset --hard`/`clean`。服务器密码不得写入文档、日志、git 或回复。

### 已实现与未实现，必须分清

- `EditFlowTransformer` 只读 codon ID；没有蛋白、UTR、宿主、功能或时间条件，`SynonymousJumpProposal._transition_tensors` 直接丢弃 `time`。
- `edit_flow_loss` 是同义腐蚀 denoising CE/BCE，不是完整 CTMC rate objective，也不监督真实功能。
- `RiboKineticModel` 的 pair channel 是合法互补碱基计数形成的 attention bias；initiation/velocity/decay 是线性位置头，再加权汇聚到功能头。它不是结构系综、核糖体动力学或已验证机制模型。
- `MinimalCodonFlowRK` 是合法单编辑枚举＋能量 softmax 的 smoke；不是训练完成的生成器，没有轨迹平衡或生产级离散流证据。
- A9 的 `generator_training_authorized=true` 是权限，不是“必须立刻训练”，更不是模型已经有效。

## 1. 自我反省：为什么工作很多而核心性能没有提高

这是路线错误，不能用工程完整度掩盖。

1. **目标错位**：天然 CDS 腐蚀重建 CE 不蕴含功能预测或 anytime 多目标设计能力。
2. **输入错位**：旧生成器缺少回答科学问题所需的蛋白、上下文、宿主、功能和预算变量。
3. **机制先行、证据随后**：静态 MFE 在 Kudla 内有信号，但跨蛋白/宿主/研究失败后仍被保留为主核心。
4. **观察过程与生物过程混为一谈**：raw Ribo occupancy 被当作可跨研究直接运输的速度；RK08/RK37 已否定这种简单做法。
5. **普通模块替代科学归纳偏置**：codon embedding、attention、互补碱基 bias、多个线性势能头没有表达核糖体排队、通量守恒和测量误差。
6. **任务定义过紧又过散**：统一 R1–R7 把本可回答不同问题的数据一起排除；同时又同时追逐功能、速度、harmonization、accessibility 和所有生成目标，缺少一个决定性阳性核心。
7. **工程指标替代科学进展**：Gate、hash、测试数、PPT 页数和 closeout 只证明可追踪，不能证明模型有效。

不可回避的结果：G2 FULL/EDIT 中位 AUC −94.28%/−93.47%；RK39–RK41 的实际集合设计任务仍未解决；RK37 相对 constant 的 TB-MSE 改善 −0.755、mean Pearson 改善 −0.033；RK42 是“0/9 同时满足全部 R1–R7”，不是“世界上没有可用数据”。

## 2. A10 的核心科学问题与边界

> **固定宿主与构建上下文中，局部同义替换是否通过延伸速率场和核糖体流守恒产生可迁移的非局部功能效应；将潜在动力学与 assay 观察过程分离，能否提高 transcript/protein/study OOD 功能预测，并进一步改善同义序列设计的质量—成本前沿？**

核心不是证明 TASEP、Transformer、CTMC 或 GFlowNet 这些已有概念本身，而是检验：

- 核糖体流守恒是否解释独立密码子模型遗漏的非局部信息；
- 分离研究特异观察映射后，潜在动力学是否比 raw occupancy 更可迁移；
- 这些被证实的量能否转化为超过强 baseline 的预测和设计性能。

静态结构不再是既定核心。它只能作为起始率的候选输入，必须在相同输入、参数和训练预算下有独立 OOD 增量才保留。没有 decay 数据就不添加 decay 头；没有多位点覆盖就不虚构远程 pair 机制。

### 可证伪假设

- **A10-H1 观察可分性**：研究特异观察映射能解释相当一部分 raw occupancy 跨研究失配；校准只用 train 或独立 calibration，不读 target test outcome。
- **A10-H2 流守恒增量**：同容量下去掉流守恒的模型无法达到相同的转录本/变体 OOD 表现；局部编辑的上下游响应与动力学预测一致。
- **A10-H3 功能增量**：潜在通量与密度对真实功能有超出 CAI/GC/MFE、位置场和通用序列模型的独立信息。
- **A10-H4 设计增量**：由同一动力学目标导出的设计器在等反馈、等 scorer、等时间下超过最强可比方法；预测消融与设计消融方向一致。

任何一项不成立就删除相应主张和模块。不得把失败改名后继续当核心。

## 3. Kinetic-CodonFlow：由物理与数学结构推导

### 3.1 生物隐状态，而不是位置独立分数

对序列 `x`、宿主 `h` 和可用上下文 `u`，模型输出严格为正的：

- 起始率 `αθ(x,u,h)`；
- 逐位延伸率 `kθ,i(x,u,h)`；
- 终止率 `βθ(x,u,h)`。

用可微排斥晶格模型或其经过验证的平均场近似求解稳态。最小平均场形式为：

`J_i = k_i ρ_i(1-ρ_{i+1})`，稳态要求 `J_i=J`；边界由 `α` 与 `β` 给定。

需要时用全长足印、多核糖体尺度和数值残差扩展，但先完成最小模型。记录稳态残差、参数可辨识性和近似误差；不能把平均场输出冒称精确随机模拟。

### 3.2 测量过程单独建模

对每个 Ribo-seq 研究 `s`：

`y_s,i = g_s(ρ_i) + ε_s,i`。

`g_s` 从单调或低自由度仿射映射开始，覆盖、检出限、重复噪声和缺失机制进入 `ε_s`。禁止高自由度 calibration 吞掉生物信号。所有映射只在 source train 或独立 target calibration 上拟合；target test 只做最终评估。

功能层只有在测量支持时才加入 mRNA 丰度 `A`、通量 `J` 和其他项，例如 `E=f(A,J,…)`。occupancy 始终称实验依赖的相对占据/速度代理，不称绝对物理速率。

### 3.3 表示学习服从动力学

小型卷积、状态空间模型或局部上下文编码器只能用于参数化速率，不列为创新。模型容量必须随数据量受控，并与独立密码子、位置场、同参数量无守恒模型公平比较。禁止默认加入 MoE、大 ESM、完整 pair transformer、RLOO 或扩参。

### 3.4 只有通过科学 Gate 才接生成器

同义状态图为 `x=(c1,…,cL)`，`ci∈C(ai)`；蛋白、长度和 stop 由状态空间保证。候选可逆核可写为：

`rθ(x→y)=r0(x→y) exp[(Fθ(y)-Fθ(x))/(2τ)]`，

并精确归一化。若 `r0` 相对 `π0` 可逆，则目标为 `π(x)∝π0(x)exp(Fθ(x)/τ)`。`Fθ` 只能包含已验证的功能/动力学项和明确约束。

必须在可枚举小状态验证：合法率、归一化、详细平衡/平稳分布、采样一致、单/多步一致和成本。若实现只是 denoising 或局部搜索，就不称 CTMC/flow。若 ID3 式 simplex 梯度设计更强，必须承认并把它保留为强 baseline，不能强行维护 CodonFlow 名称。

## 4. 数据：找全、洗净、分清用途，不再一刀切

### 4.1 任务化数据资格

| 任务 | 必要数据条件 | 可以接受 | 不能声称 |
|---|---|---|---|
| 构建内/N 端功能预测 | 变体序列、连续结局、明确构建与批次 | Goodman 式固定 leader＋N 端同义窗 | 全长 CDS 或天然 UTR 泛化 |
| 起始结构运输 | 精确变体特异 UTR–ATG–CDS | 可重建精确起始窗的数据 | 借固定 leader 数据证明该机制 |
| 翻译动力学 | P-site/密码子映射、覆盖、重复、研究元数据 | 天然转录本 Ribo-seq，无需固定蛋白同义库 | occupancy=绝对速度 |
| 同义设计 | 固定蛋白、合法同义空间、明确目标与成本 | 公开蛋白和计算 benchmark | 代理优化=真实功能提升 |
| 真实功能验证 | 未参与选择的真实变体与独立测量 | 回顾性独立验证或前瞻 DBTL | 同一 scorer 自评即生物验证 |

因此，RK42 的 R1–R7 不再作为所有任务的统一门槛；历史 RK36/RK42 判定不改写。A10 是为不同科学主张使用不同资格，不是降低结构运输或独立验证标准。

### 4.2 当前数据角色

- **Goodman2013**：优先从论文公开补充材料、PMC/NCBI 或其他合法公开源取得 construct-level raw；用于限定构建几何的功能 benchmark。Cloudflare 页面不是数据，不能猜值。
- **Kudla154**：固定 GFP 开发数据；已有结构结局不能重新冒充独立验证。
- **Boël6348**：ordinal、天然跨蛋白非同义变体；只作匹配其测量性质的辅助任务/对照，不冒充连续同义功能库。
- **Cambray2018**：96 bp N 端片段且氨基酸变化；只可作非固定蛋白辅助研究，不能进入固定蛋白同义主表。
- **Mordstein**：已观察的匹配上下文辅助证据，不是 untouched。
- **MAGE functional untouched 19072 行**：继续冻结，除非 owner 另行明确授权；不得通过派生文件间接读取。
- **iCodon**：源对齐失败，禁止使用。
- **Mohammad/Subtelny Ribo**：均已观察，只作开发；另找未读研究作最终研究 OOD。
- **untouched24**：继续冻结，最终一次使用。

### 4.3 E0 必须交付的数据审计

1. **来源**：accession/release/URL/license/下载时间/raw-clean SHA/处理谱系；论文样本数不等于已拥有数据。
2. **序列 QC**：长度整除 3、合法 alphabet、终端/内部 stop、翻译与蛋白一致、起始/部分 CDS、重复与合成错误。
3. **构建 QC**：蛋白、完整或片段 CDS、5′/3′UTR、leader、载体、宿主、启动子、化学修饰、assay、batch、replicate、单位、检出限、缺失原因。
4. **Ribo QC**：read coverage、P-site 偏移、密码子映射、重复一致性、零覆盖、footprint 长度与研究批次；保留原始计数，不只留归一化值。
5. **分布**：长度、GC/CAI、密码子/氨基酸组成、变体位置、每蛋白/研究样本量、功能动态范围、重复噪声、覆盖与长尾；检查短序列、优势物种和大 assay 主导。
6. **泄漏**：exact CDS/protein/ID、同源簇、同一变体、重复测量、功能来源蛋白、研究批次和第三方预训练重叠。所有 RSCU、归一化、校准、特征选择只由 train 拟合。
7. **划分**：功能按蛋白/family/研究分组；Ribo 按转录本和研究分组；同蛋白变体不得随机跨 split。开发、校准、最终 untouched 分开。

无法获得的字段标缺失并限制结论，不静默填补，不删除低表达或失败变体。

## 5. Benchmark 与强 baseline：逐任务核实，不拼虚假总排名

### 5.1 A10 只设三个主任务

**T1 构建内及 OOD 功能预测**  
主指标 Spearman、RMSE、top-k enrichment；蛋白/family/研究为独立单位。必须比较 constant、CAI/GC、局部/全局 MFE、位置场、Ridge/HistGB、Boël 作者模型（适用时）、通用序列模型及可复现直接竞争方法。

**T2 翻译占据与动力学预测**  
先在研究内 transcript OOD 验证，再做有独立 calibration 的研究 OOD。比较 constant、位置场、Ridge、RiboMIMO、iXnos、ROSE、VeloGRU/VeloBERT、VeloHARMO（适用时）。report transcript-balanced MSE、mean per-transcript Pearson/Spearman、密度响应和校准；不能随机拆 codon 行。

**T3 固定蛋白同义设计**  
代理设计与真实功能验证分表。比较 LinearDesign、EnsembleDesign、ID3、RNARL、CodonTransformer、COformer、VeloHARMO、内部 hill/MH/SA/GA/random/r5；按任务核验 CAGFN、codonGPT、GEMORNA。主指标 dense budget-step HV AUC、实际 Pareto/best、NED、合法率和 time-matched 表现。

Harmonization、全长 UTR–CDS 联合设计和起始结构运输只在对应数据与机制通过后增加，不与三个主任务同时铺开。

### 5.2 2024–2026 候选补充审计

已核实论文存在，但代码/数据/可比性尚未全部核实：

- CodonTransformer，Nature Communications 2025，DOI `10.1038/s41467-025-58588-7`。
- COformer，Molecular Therapy Nucleic Acids 2026，DOI `10.1016/j.omtn.2026.102991`。
- VeloHARMO，Briefings in Bioinformatics 2026，DOI `10.1093/bib/bbag558`。
- RNARL，Genome Biology 2026，DOI `10.1186/s13059-026-04203-x`。
- ID3，Bioinformatics 2026，DOI `10.1093/bioinformatics/btag667`。
- EnsembleDesign，Bioinformatics 2025，DOI `10.1093/bioinformatics/btaf245`。
- 另需核查 ColiFormer、DeepCodon、High-Codon、CodonTranslator、CodonRL、RNAJog、NatCodon、CodonBERT、ppLM-CO；预印本与同行评议状态分开标注。

每个方法记录官方 URL/commit、环境、训练数据、输入、输出、目标、默认与最佳配置、预训练污染、实际运行状态和失败原因。不能运行的直接强 baseline 标不可比，不得换弱方法冒充 SOTA。商业工具优化序列训练的模型需单独审计目标泄漏，不能直接声称真实功能监督。

## 6. 环环相扣的实验链

### E0：数据和 baseline 是否可信

- **意义**：排除数据不存在、构建错配、泄漏和弱 baseline 造成的假科学问题。
- **行动**：完成 4.3 审计与 5.2 官方复现；冻结任务、划分、主指标、调参预算和成本。
- **承上启下**：没有真实功能与可靠 Ribo 输入，E1–E3 不启动；关键 baseline 未跑通，E4 不称 SOTA。

### E1：跨研究失败有多少来自观察过程

- **对照**：raw 直接运输、研究内校准、无动力学序列模型、位置/constant。
- **现象**：观察映射自由度、源内拟合、潜在参数稳定性、未读研究表现。
- **判决**：校准后仍不优于简单模型，则不写跨研究动力学；可在研究内继续 E2，但不得外推。
- **承接**：只有观察可分性成立，E2 的非局部响应才有跨研究解释基础。

### E2：流守恒是否提供独立非局部信息

- **对照**：完整动力学、去流守恒同容量模型、独立密码子模型、纯位置场。
- **现象**：局部变体上下游密度响应、通量变化、稳态残差、转录本/变体 OOD。
- **判决**：没有超出独立模型的增量，删除动力学核心，停止 Kinetic-CodonFlow 主线，而不是增加模块。
- **承接**：只有通过的动力学量进入 E3 功能模型。

### E3：功能预测能否公平击败最强 baseline

- **对照**：T1 全部直接可比方法；先在构建内/转录本 OOD，再蛋白/family/研究 OOD。
- **现象**：主效应、逐蛋白方向、top-k、校准、不确定性和失败分层。
- **判决**：paired 95% CI 下界>0且 Holm 通过，才形成功能阳性核心；否则继续诊断数据/目标，不接生成器。
- **承接**：E3 验证的潜在功能场成为 E4 唯一候选设计驱动力。

### E4：机制是否转化为设计质量—成本优势

- **对照**：T3 最强外部与内部方法，同初始、反馈、目标、预算和硬件。
- **现象**：dense anytime、实际集合、time-matched、全成本、合法率；真实 held-out 功能另表。
- **判决**：未赢最强可比方法即未解决；只赢 r5/hill 或只赢等 scorer 而输等时间不算实用 SOTA。
- **承接**：E5 解释收益是否来自 E2/E3 的同一机制。

### E5：为什么有效，以及在哪里失效

- **对照**：去流守恒、去观察映射、去起始结构、去自然先验；同参数、同训练/推理成本。
- **现象**：预测与设计消融是否同向，长度/GC/同源/研究/宿主分层及不确定性。
- **判决**：无独立收益组件删除；失败层保留，不能只展示正例。
- **承接**：形成“现象→机制→模型→性能→边界”的论文闭环。

### E6：真实功能与前瞻验证

公开 held-out 变体只支持回顾性验证。顶刊版本另需 design–build–test–learn：至少两个蛋白、明确宿主/UTR、WT 和强方法对照、独立重复、功能/稳定性测量。预算与周期由 owner 决定；未完成前不得写疗效、免疫原性或普遍表达提升。

## 7. 超参、OOD、成本与统计合同

- 使用 nested grouped CV；outer test 不参与模型、特征、早停、超参或阈值选择。最终 untouched 冻结后一次评估。
- 优化器 LR log-uniform、weight decay、dropout、warmup、grad clip、batch tokens、训练步数、编码器容量和正则强度只在 inner dev 用 ASHA/小网格。
- 动力学专属：速率上下界、稳态容差、观察映射自由度、功能/占据损失权重、缺失数据采样；先局部敏感性和可辨识性，再大训练。
- 生成专属：自然先验强度、能量温度、偏好采样、候选/top-k、早停与块长；全部进入推理成本。
- 所有方法使用相当调参预算和官方最佳可复现配置；至少 3 seeds，关键结论按功效分析增加，不用默认超参误判架构。
- OOD 至少分 transcript、蛋白/family、研究、长度/GC；数据支持时才加宿主。已读 Subtelny、unique18 等不能再冒充 untouched。
- 功能以蛋白/研究为独立单位，Ribo 以转录本/研究为单位，设计以基因为单位；seed 先在组内聚合。报告 paired cluster bootstrap 95% CI、逐单位方向、Holm 校正和效应量。
- 分开记录 cache-before requests、唯一 scorer、模型 forward、生成时间、评分时间、训练成本、wall-clock、硬件和并行度。无真实轨迹的方法只比较 actual set，缺失为 null，不补零。
- 每个选定任务独立要求主效应及 CI 下界>0、多重校正通过、完整成本与 OOD；生成另需合法率100%。SOTA 是待验证目标，不是文档承诺。

## 8. 论文科学故事：每一环必须由现象推动

### 主线

**独立密码子代理与 raw occupancy 的失败现象 → 测量过程和全局耦合缺口 → 非局部动力学证据 → 由守恒方程推导模型 → 功能 OOD 强 baseline → 设计质量—成本 → 对应消融与失败边界 → 真实功能验证。**

不再使用“代理失效→预设空间耦合→堆叠模型”的旧跳跃逻辑，也不把 RK21–RK42 逐实验流水账当 Results 主线。旧结果只保留能支撑动机的少数强证据，其余进入补充或审计档案。

### 主图合同

- **Fig.1 为什么现有建模不够**：真实变体/占据分布、简单代理失败、raw 跨研究失配；同时展示反例，不选择性展示 Kudla。
- **Fig.2 什么现象要求新模型**：观察校准与非局部密度响应；去守恒对照，给出效应和 CI。
- **Fig.3 模型如何由方程产生**：速率参数化、稳态通量、研究观察映射、合法同义图；不画普通模块拼图。
- **Fig.4 是否超过最强方法**：T1/T2/T3 分任务主表，绝不拼不可比数字或虚假总排名。
- **Fig.5 为什么有效**：预测与设计对应消融、参数可辨识性、失败案例。
- **Fig.6 是否泛化且有实用价值**：OOD、time-matched、全成本、不确定性与真实变体；前瞻实验完成后才加入生物功能结论。

每节按“问题→对照→现象→结论边界→为什么需要下一实验”写。每张图只回答一个科学问题，每个主张映射 raw data、split、对照、指标和反驳条件。

## 9. 科学 Gate 与停止规则

- **A10-G0 数据/baseline 可信**：E0 完成，关键数据和直接 baseline 真实可运行。
- **A10-G1 动力学增量**：E2 在严格 OOD 超过去守恒和简单模型；E1 决定能否增加跨研究主张。
- **A10-G2 功能阳性核心**：E3 达到预注册 SOTA 门槛后才允许大规模生成训练。
- **A10-G3 设计阳性核心**：E4 等反馈/成本超过最强可比方法，E5 机制消融同向。

文档、测试、hash 和 PPT 是复现条件，不是科学 Gate。若 G1 失败，停止动力学主线；若 G2 失败，停止生成训练；不得改成弱 baseline、回顾性最佳臂或“工程已完成”收尾。

## 10. 执行顺序与真实交付

1. **A10-00**：重核远端状态；建立一页任务—数据—baseline—主张矩阵，不再复述旧计划。
2. **A10-01**：取得 Goodman 功能 raw、未读 Ribo 研究和直接 baseline 官方资产；完成 E0 数据卡、分布、泄漏、分组与真实 smoke。
3. **A10-02**：先以低自由度观察模型完成 E1；冻结分析后再读目标结局，失败保留。
4. **A10-03**：实现最小可微动力学算子和去守恒对照；小状态/数值测试后完成 E2，不先写生成器。
5. **A10-04**：完成 E3 功能 OOD 主表；只有真实赢强 baseline 才进入 E4。
6. **A10-05**：实现合法生成核并完成 E4/E5；若直接梯度设计更强，如实报告。
7. **A10-06**：最后做 untouched、干净复现和论文证据矩阵，再更新 PPT；不按页数追进度。

每项运行登记假设、commit+dirty hash、环境、数据/split SHA、命令、seed、拟合数、超参、forward/scorer/time、artifact SHA、结果和不可声称事项。为新实现补项目风格测试；每阶段做定向测试、独立原始数据复算和真实端到端 smoke，最终跑项目标准测试。结果先独立核验再写论文/PPT。

### 最终回复必须回答

1. 新数据实际来源、构建几何、质量、分布、划分和泄漏，而非论文宣称样本数。
2. 每个直接 baseline 的真实运行状态、官方配置、调参预算与公平性。
3. E1 观察过程、E2 非局部动力学是否成立；阴性不得包装成阳性。
4. 每个主任务相对最强 baseline 的效应、CI、OOD、成本及是否真正 SOTA。
5. 若训练生成器：合法核、归一化/详细平衡/采样一致、等成本和消融。
6. 论文链条哪些由实验闭合、哪些仍待证；不得把计划写成结果。
7. 修改文件、artifact SHA、测试命令和结果；任何阻塞与需要 owner 决定的事项。

## 11. 永久禁止

- 禁止再用训练收敛、合法率、文件数、测试数、Gate 数或 PPT 页数代替核心性能。
- 禁止继续做无新科学问题的窗口、覆盖、初始化和 gating 消融。
- 禁止把 pair bias、attention、MoE、ESM、GFlowNet、扩散或 RL 本身当创新。
- 禁止把 occupancy 写成绝对速率、回顾性关联写成因果、计算代理写成真实生物功能。
- 禁止用同一蛋白随机拆分、target outcome 校准、反复 untouched、弱 baseline 或缺失预算补零制造胜利。
- 禁止读取 MAGE functional untouched/untouched24，除非相应最终协议已冻结且授权明确。
- 禁止删除失败日志、覆盖历史 artifact、改写历史 Gate、伪造外部方法轨迹或成本。
- 禁止在本提示词下先做大模型/生成训练，再补数据和科学问题。

**A10 的中心不是“如何让现有 CodonFlow 看起来有效”，而是“用可证伪的核糖体流守恒与测量分离，找到可迁移的非局部同义效应，再把被证实的机制转化为可复现、超过强 baseline 的预测和设计能力”。**
