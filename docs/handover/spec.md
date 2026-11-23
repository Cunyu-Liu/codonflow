# CodonFlow Spec（A10 · Kinetic-CodonFlow 当前执行合同）

> 生效日期：2026-11-23。唯一执行合同为工作区根目录 `docs/handover/PROMPT_NEXT_AGENT_A10_KINETIC.md`；本文件与 `tasks.md` 是其执行化，不降低其中任何科学、数据或公平比较要求。
> A7–A9 及其 RK 结果、Gate、prompt、handoff 均为不可变历史证据，只用于动机、边界和追溯，不再指导新实验。旧 A8 的空间耦合既定核心、统一 R1–R7 准入和 RK-G0–G4 执行顺序由本合同替代；历史判定不追改。
> 文件级清单见 `docs/handover/tasks.md`；任务现状见 `docs/handover/A10_00_TASK_DATA_BASELINE_CLAIM_MATRIX.md`。

## 0. 当前事实与证据纪律

### 0.1 本轮已核实的运行事实

- GitHub 分支 `a8-rk` 当前已推送至 `b4604b09`；共享远端工作树在后续每次操作前仍须重新核对 HEAD、工作树和进程状态，不能沿用旧 HEAD 记录。
- RTX 5090 环境 `torch 2.14.1+cu132` 的 CUDA 真 matmul 已通过；G0 closeout 生产与独立复核 **45 项测试通过**，全部 A10 定向测试 **251 passed**。这些都只是工程复现证据，不是模型或科学结果。
- **G0 closeout v3 已登记**：closeout SHA256=`93928d6b6c2599d7e18e59896863f4b3bea91b3e034f64538631d395711ac8cc`，独立复核 SHA256=`1c6a3b1e211998f7a79959eca68af3a03c92d94548b31eefcc7e62a0ebe1ebd3`，独立复核 **20/20 通过**；裁决为 `A10_G0=PASS_DATA_AND_BASELINE_READY`，E0/G0 完成，允许启动 E1/E2。
- **A10-02（E1）已启动但尚无结果**；final untouched=`false`，H1/H2 未证，E3/G2 未证，SOTA=`false`。大规模生成训练仍须先通过 G2。
- 旧 A7 PID `2071716` 为暂停状态，不重启。
- 大型资产目录仍为 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/`。共享工作树每次操作前仍须重新核对 HEAD、工作树、进程和数据状态；本地继承的 dirty/untracked 文件必须保留，不覆盖远端，不 `git add -A`，不 `reset --hard`/`clean`，不记录服务器密码。

### 0.2 已确立的历史科学事实

- G2 FULL/EDIT 中位 AUC 分别为 −94.28%/−93.47%；RK39–RK41 的实际集合设计任务仍未解决。
- RK37 相对 constant 的 TB-MSE 改善为 −0.755、mean per-transcript Pearson 改善为 −0.033，跨研究直接运输失败。
- RK42 的准确含义是 **0/9 数据源同时满足全部 R1–R7**，不是“没有任务化数据”，也不是“世界上没有可用数据”。历史 RK36/RK42 判定保持不变。
- **Goodman2013 已取得并审计官方 CSV**：raw SHA256=`a03071027b8c0008d07fb7737de0a7d51765c6cff25bc86e93465a6253c7c33a`，共 14234 行、75 列、137 Gene、4817 exact CDS、280 leader、33 nt N 端片段、8439 SetGood；clean SHA256=`ce64f2caa9633fefae840e220d36b6360946d39b9253adc56f3ef297b9ab9c82`。最终 v3 audit report SHA256=`3036961a32502c1ea7a9bf6cd45f2ffbb0cadf2d18ff8f3405b4abd4bb1a6304`，独立复算 SHA256=`c78359d03a45f3bbbcc867f36be8b2c74219a9410c543a90d08e8784a6bf42ab`，31/31 通过。
- Goodman 已生成 **5 outer × 4 inner nested grouped CV** 划分：assignment SHA256=`e2d8b31bf6a5aee6f104c96ea484340b6d10654bc35494c36fa4a89a31e6a129`，split SHA256=`f49c93af8e2a30616d6f0e907f75dd8a08e29e5fe23e303484c120feb57683c2`，独立验证 25/25 通过，验证 SHA256=`379ef698d8f0029d929468c94bcdf594bd83384e957fcc31e4e66d46b4fc2f43`。该划分只支持 **Gene-grouped N 端片段构建 OOD**，不得称为 protein OOD。
- **Goodman 7臂 nested 5×4 开发 benchmark 已完成**：8439 SetGood rows，59073 prediction rows（7臂×5折），独立验证 32/32 通过。prediction SHA256=`aa0cfbc280f1dc3a3b1e1e829ce71bfabe942122dbac8671d322e314bdade271`，report SHA256=`0dc67e5b2b38bd79cfe19211362994a28a6206020264ea819400b7b7e76eea9d`，独立验证 SHA256=`384519f7bfc4a6cd574694bee838176b6f4d0c871367c4a567bfffd30828e5a4`。
  - 逐 outer 均值统一为 **Spearman/RMSE/top1**：constant=`NA/.785062/.090952`；CAI=`.992955/.015030/.784884`；GC=`.885724/.021479/.780810`；dG=`.792860/-.049617/.784445`；tAI=`.981755/.003549/.785177`；Ridge=`1.085185/.147541/.762021`；HistGB=`1.321994/.320124/.697210`。
  - 成本：wall-clock **370.0619 s**；HistGB **85 fits** 均为 **52–264 iterations**，**0 次触及 500 iterations 上限**。
  - 边界：只称开发 baseline，不构成机制、SOTA、protein OOD 或真实生物泛化结论；该子项本身不表示全部适用直接 baseline、公平功能主表、E0 或 G0 已完成，当前 E0/G0 以 closeout 整体裁决为准。
- **Tunney 已完成本轮 E0 审计**：5894 transcripts、2920075 codon rows；report SHA256=`9fecfb838762950b2545f6db4fb0d6ba4ab92cc9483aad20c33cd1f0d8abf9b9`，clean SHA256=`238d9997f6449763bed69a4ba806b74ea0f77b95ee526cb6dff61fe9ce1b7a6e`，独立验证 24/24 通过。合并 lane 是非独立重复，不增加生物学独立样本量；使用 A-site 映射与 RSEM 加权，occupancy 仍不称绝对速率。
- Lareau `GSE58321` 已出现于 RK03/RK05，**不再列为未读候选**，也不能充当新的最终研究 OOD；仍须另选真正未读研究。
- EnsembleDesign 官方 quick v2 已成功 6/6，且 3 条输出与 README 匹配；ID3 的两条 CPC 轨迹存在缺陷，缺陷与失败证据保留。CodonTransformer 尚未成功运行，不能记为 ran 或通过 smoke。
- `untouched24` 与 MAGE functional untouched 19072 行继续冻结；禁止直接或间接读取，除非相应最终协议已冻结且 owner 明确授权。

### 0.3 当前实现能声称与不能声称的内容

以下为 A10 合同记载的远端实现审查事实，不因旧命名而扩大解释：

- `EditFlowTransformer` 只读 codon ID，没有蛋白、UTR、宿主、功能或时间条件；`SynonymousJumpProposal._transition_tensors` 丢弃 `time`。
- `edit_flow_loss` 是同义腐蚀 denoising CE/BCE，不是完整 CTMC rate objective，也不监督真实功能。
- `RiboKineticModel` 的 pair channel 是合法互补碱基计数形成的 attention bias；initiation/velocity/decay 是线性位置头再加权汇聚到功能头。它不是结构系综、核糖体动力学或已验证机制模型。
- `MinimalCodonFlowRK` 是单编辑枚举＋能量 softmax 的 smoke，不是训练完成的生成器，没有轨迹平衡或生产级离散流证据。
- A9 的 `generator_training_authorized=true` 是权限，不是必须立刻训练，更不是模型有效；A10 大规模生成训练仍受 G2 约束。

所有文档必须区分实现事实、文献事实、科学假设、待审计事项、实验结果和未来计划。论文样本数不等于已拥有数据；候选方法不等于已运行 baseline；测试、hash、Gate 数和 PPT 页数不等于科学进展。

## 1. 核心科学问题与可证伪假设

> **固定宿主与构建上下文中，局部同义替换是否通过延伸速率场和核糖体流守恒产生可迁移的非局部功能效应；将潜在动力学与 assay 观察过程分离，能否提高 transcript/protein/study OOD 功能预测，并进一步改善同义序列设计的质量—成本前沿？**

核心不是证明 TASEP、Transformer、CTMC 或 GFlowNet 等概念本身，而是检验：流守恒能否解释独立密码子模型遗漏的非局部信息；分离研究特异观察映射后，潜在动力学能否比 raw occupancy 更可迁移；被证实的量能否转化为超过强 baseline 的预测和设计性能。

- **A10-H1 观察可分性**：研究特异观察映射能解释相当一部分 raw occupancy 跨研究失配。校准只使用 source train 或独立 target calibration，绝不读取 target test outcome。
- **A10-H2 流守恒增量**：同容量下去除流守恒的模型不能达到相同的转录本/变体 OOD 表现；局部编辑的上下游响应与动力学预测一致。
- **A10-H3 功能增量**：潜在通量与密度对真实功能有超出 CAI/GC/MFE、位置场和通用序列模型的独立信息。
- **A10-H4 设计增量**：由同一已验证动力学目标导出的设计器，在等反馈、等 scorer、等时间下超过最强可比方法；预测消融与设计消融方向一致。

任一假设不成立，就删除相应主张和模块，不得改名后继续作为核心。静态结构仅是起始率候选输入，必须在相同输入、参数和训练预算下显示独立 OOD 增量才保留；没有 decay 数据不添加 decay 头，没有多位点覆盖不虚构远程 pair 机制。

## 2. Kinetic-CodonFlow 的最小科学模型

### 2.1 潜在生物状态

对序列 `x`、宿主 `h` 和可用上下文 `u`，模型输出严格为正的起始率 `αθ(x,u,h)`、逐位延伸率 `kθ,i(x,u,h)` 和终止率 `βθ(x,u,h)`。先用可微排斥晶格模型或经过验证的平均场近似求稳态，最小平均场形式为：

`J_i = k_i ρ_i(1-ρ_{i+1})`，稳态要求 `J_i=J`，边界由 `α` 与 `β` 给定。

需要时再扩展全长足印、多核糖体尺度和数值残差。必须记录稳态残差、参数可辨识性和近似误差；平均场输出不得冒称精确随机模拟。

### 2.2 观察过程与功能层

每个 Ribo-seq 研究 `s` 单独建模：`y_s,i = g_s(ρ_i) + ε_s,i`。`g_s` 从单调或低自由度仿射映射开始；覆盖、检出限、重复噪声和缺失机制进入 `ε_s`。禁止高自由度 calibration 吞掉生物信号。映射只在 source train 或独立 target calibration 上拟合，target test 只最终评估。

功能层仅在测量支持时加入 mRNA 丰度 `A`、通量 `J` 等，例如 `E=f(A,J,…)`。occupancy 始终称实验依赖的相对占据/速度代理，不称绝对物理速率。

小型卷积、状态空间模型或局部上下文编码器只用于参数化速率，不列为创新。容量随数据量受控，并与独立密码子、位置场、同参数量无守恒模型公平比较。默认不加入 MoE、大 ESM、完整 pair transformer、RLOO 或扩参。

### 2.3 只有科学 Gate 通过后才接生成器

同义状态图为 `x=(c1,…,cL)`，`ci∈C(ai)`；蛋白、长度和 stop 由状态空间保证。候选可逆核为：

`rθ(x→y)=r0(x→y) exp[(Fθ(y)-Fθ(x))/(2τ)]`，并精确归一化。

若 `r0` 相对 `π0` 可逆，则目标为 `π(x)∝π0(x)exp(Fθ(x)/τ)`。`Fθ` 只能包含已验证的功能/动力学项和明确约束。必须在可枚举小状态验证合法率、归一化、详细平衡/平稳分布、采样一致、单/多步一致和成本。若实现只是 denoising 或局部搜索，不称 CTMC/flow；若 ID3 式 simplex 梯度设计更强，必须保留其为强 baseline 并如实报告，不能强行维护 CodonFlow 名称。

## 3. 数据合同：按科学主张确定资格

### 3.1 任务化数据资格

| 任务 | 必要数据条件 | 可以接受 | 不能声称 |
|---|---|---|---|
| 构建内/N 端功能预测 | 变体序列、连续结局、明确构建与批次 | Goodman 式固定 leader＋N 端同义窗 | 全长 CDS 或天然 UTR 泛化 |
| 起始结构运输 | 精确变体特异 UTR–ATG–CDS | 可重建精确起始窗的数据 | 借固定 leader 数据证明该机制 |
| 翻译动力学 | P-site/密码子映射、覆盖、重复、研究元数据 | 天然转录本 Ribo-seq，无需固定蛋白同义库 | occupancy=绝对速度 |
| 同义设计 | 固定蛋白、合法同义空间、明确目标与成本 | 公开蛋白和计算 benchmark | 代理优化=真实功能提升 |
| 真实功能验证 | 未参与选择的真实变体与独立测量 | 回顾性独立验证或前瞻 DBTL | 同一 scorer 自评即生物验证 |

R1–R7 不再作为所有任务的统一门槛；这只是按主张分配合格数据，不降低起始结构运输或独立验证标准。

### 3.2 当前数据角色与冻结边界

- **Goodman2013**：官方 CSV 已取得，raw/clean、最终 v3 审计、nested 5 outer × 4 inner 划分及7臂 nested 5×4 开发 benchmark 均已有上述 SHA 和独立验证；只用于实际 33 nt N 端片段构建几何的功能 benchmark。当前 OOD 仅称 Gene-grouped N 端片段构建 OOD，不称 protein OOD、全长 CDS 或天然 UTR 泛化；7臂结果仅为开发 baseline，不构成机制、SOTA 或真实生物泛化结论。
- **Kudla154**：固定 GFP 开发数据；已有结构结局不能重新冒充独立验证。
- **Boël6348**：ordinal、天然跨蛋白非同义变体；只作匹配测量性质的辅助任务/对照，不冒充连续同义功能库。
- **Cambray2018**：96 bp N 端片段且氨基酸变化；只作非固定蛋白辅助研究，不能进入固定蛋白同义主表。
- **Mordstein**：已观察的匹配上下文辅助证据，不是 untouched。
- **MAGE functional untouched 19072 行**：继续冻结，除非 owner 另行明确授权；不得通过派生文件间接读取。
- **iCodon**：源对齐失败，禁止使用。
- **Tunney Ribo**：5894 transcripts、2920075 codon rows 已完成本轮审计和 24/24 独立验证；合并 lane 只作非独立重复，采用 A-site/RSEM 加权，保留原始计数和 occupancy 的相对代理边界。
- **Mohammad/Subtelny/Lareau Ribo**：Mohammad/Subtelny 均已观察，只作开发；Lareau `GSE58321` 已出现于 RK03/RK05，也不再是未读候选。最终研究 OOD 必须另找真正未读研究。
- **untouched24**：继续冻结，最终一次使用。

### 3.3 E0 数据审计的必备字段

1. **来源**：accession/release/URL/license/下载时间/raw-clean SHA/处理谱系；论文样本数不等于已拥有数据。
2. **序列 QC**：长度整除 3、合法 alphabet、终端/内部 stop、翻译与蛋白一致、起始/部分 CDS、重复与合成错误。
3. **构建 QC**：蛋白、完整或片段 CDS、5′/3′UTR、leader、载体、宿主、启动子、化学修饰、assay、batch、replicate、单位、检出限和缺失原因。
4. **Ribo QC**：read coverage、P-site 偏移、密码子映射、重复一致性、零覆盖、footprint 长度和研究批次；保留原始计数，不只留归一化值。
5. **分布**：长度、GC/CAI、密码子/氨基酸组成、变体位置、每蛋白/研究样本量、功能动态范围、重复噪声、覆盖与长尾；检查短序列、优势物种和大 assay 主导。
6. **泄漏**：exact CDS/protein/ID、同源簇、同一变体、重复测量、功能来源蛋白、研究批次和第三方预训练重叠。RSCU、归一化、校准和特征选择只由 train 拟合。
7. **划分**：按实际构建与主张确定分组单位；Goodman 本轮只使用 Gene-grouped N 端片段构建 OOD，不称 protein OOD，其他功能任务按蛋白/family/研究分组；Ribo 按转录本和研究分组；同蛋白变体不得随机跨 split。开发、独立 calibration 和最终 untouched 分开。

无法获得的字段标缺失并限制结论；不静默填补，不删除低表达或失败变体。

## 4. 三个主任务与强 baseline

### T1 构建内及 OOD 功能预测

主指标为 Spearman、RMSE、top-k enrichment，独立单位必须与数据和构建几何一致。Goodman 当前只做 Gene-grouped N 端片段构建 OOD，不称 protein OOD；其他具备资格的功能任务再以蛋白/family/研究为独立单位。必须比较 constant、CAI/GC、局部/全局 MFE、位置场、Ridge/HistGB、Boël 作者模型（适用时）、通用序列模型及可复现直接竞争方法。先在构建内/转录本 OOD，再按数据资格进入蛋白/family/研究 OOD。

### T2 翻译占据与动力学预测

先在研究内 transcript OOD 验证，再做有独立 calibration 的研究 OOD。比较 constant、位置场、Ridge、RiboMIMO、iXnos、ROSE、VeloGRU/VeloBERT、VeloHARMO（适用时）。报告 transcript-balanced MSE、mean per-transcript Pearson/Spearman、密度响应和校准；不得随机拆 codon 行。

### T3 固定蛋白同义设计

代理设计与真实功能验证分表。比较 LinearDesign、EnsembleDesign、ID3、RNARL、CodonTransformer、COformer、VeloHARMO、内部 hill/MH/SA/GA/random/r5；按任务核验 CAGFN、codonGPT、GEMORNA。主指标为 dense budget-step HV AUC、实际 Pareto/best、NED、合法率和 time-matched 表现。

Harmonization、全长 UTR–CDS 联合设计和起始结构运输只在对应数据与机制通过后增加，不与三个主任务同时铺开。不得拼接不可比数字形成虚假总排名。

### 外部方法审计

已核实论文存在但代码/数据/可比性尚未全部核实的候选包括：CodonTransformer（DOI `10.1038/s41467-025-58588-7`）、COformer（`10.1016/j.omtn.2026.102991`）、VeloHARMO（`10.1093/bib/bbag558`）、RNARL（`10.1186/s13059-026-04203-x`）、ID3（`10.1093/bioinformatics/btag667`）、EnsembleDesign（`10.1093/bioinformatics/btaf245`）。另核查 ColiFormer、DeepCodon、High-Codon、CodonTranslator、CodonRL、RNAJog、NatCodon、CodonBERT、ppLM-CO，并区分预印本与同行评议状态。

每个方法记录官方 URL/commit、环境、训练数据、输入、输出、目标、默认与最佳配置、预训练污染、实际运行状态和失败原因。当前仅有 EnsembleDesign 官方 quick v2 6/6 成功且 3 条输出匹配 README，可据此记该 smoke 已完成；ID3 两条 CPC 轨迹缺陷必须保留，不能记为成功；CodonTransformer 尚未成功运行，状态不得编造。其余方法仍按真实核验结果登记，不能运行的直接强 baseline 标不可比，不换弱方法冒充 SOTA。商业工具优化序列训练的模型单独审计目标泄漏，不能直接声称真实功能监督。

## 5. 实验链 E0–E6

### E0：数据和 baseline 是否可信

完成来源、QC、分布、泄漏和分组审计，取得真实功能与可靠 Ribo 输入，完成直接 baseline 官方资产核验和真实 smoke；冻结任务、划分、主指标、调参预算与成本。**E0 已完成，A10-G0 已通过**：G0 closeout v3 SHA256=`93928d6b6c2599d7e18e59896863f4b3bea91b3e034f64538631d395711ac8cc`，独立复核 SHA256=`1c6a3b1e211998f7a79959eca68af3a03c92d94548b31eefcc7e62a0ebe1ebd3`，独立复核 20/20 通过；closeout 生产与独立复核 45 项测试通过，全部 A10 定向测试 251 passed，裁决为 `A10_G0=PASS_DATA_AND_BASELINE_READY`。现允许启动 E1/E2；A10-02（E1）已启动但尚无结果，E2 也没有新结果。Goodman 7臂结果仍只作开发 baseline，不构成机制、SOTA、protein OOD 或真实生物泛化结论。G0 通过不表示 H1/H2、E3/G2 或 SOTA 已证，final untouched=`false`，大规模生成训练仍须先通过 G2。

### E1：跨研究失败有多少来自观察过程

对照 raw 直接运输、研究内校准、无动力学序列模型、位置/constant；观察映射自由度、源内拟合、潜在参数稳定性和未读研究表现。**A10-02 已启动，当前进行中且无结果，不得写 H1、观察可分性或跨研究动力学结论。**校准后仍不优于简单模型，则不写跨研究动力学；可在研究内继续 E2，但不得外推。只有观察可分性成立，E2 非局部响应才有跨研究解释基础。

### E2：流守恒是否提供独立非局部信息

对照完整动力学、去流守恒同容量模型、独立密码子模型、纯位置场；观察局部变体上下游密度响应、通量变化、稳态残差和转录本/变体 OOD。没有超出独立模型的增量，就删除动力学核心并停止 Kinetic-CodonFlow 主线，而不是增加模块。只有通过的动力学量进入 E3。

### E3：功能预测能否公平击败最强 baseline

使用 T1 全部直接可比方法，先构建内/转录本 OOD，再蛋白/family/研究 OOD；报告主效应、逐蛋白方向、top-k、校准、不确定性和失败分层。paired 95% CI 下界>0且 Holm 通过，才形成功能阳性核心；否则继续诊断数据/目标，不接生成器。E3 验证的潜在功能场是 E4 唯一候选设计驱动力。

### E4：机制是否转化为设计质量—成本优势

对照 T3 最强外部与内部方法，同初始、反馈、目标、预算和硬件；报告 dense anytime、实际集合、time-matched、全成本和合法率，真实 held-out 功能另表。未赢最强可比方法即未解决；只赢 r5/hill，或只赢等 scorer 而输等时间，不算实用 SOTA。

### E5：为什么有效，以及在哪里失效

对照去流守恒、去观察映射、去起始结构、去自然先验，同参数、同训练/推理成本；检查预测与设计消融是否同向，长度/GC/同源/研究/宿主分层及不确定性。无独立收益组件删除，失败层保留，形成“现象→机制→模型→性能→边界”的闭环。

### E6：真实功能与前瞻验证

公开 held-out 变体只支持回顾性验证。顶刊版本另需 design–build–test–learn：至少两个蛋白、明确宿主/UTR、WT 和强方法对照、独立重复、功能/稳定性测量。预算与周期由 owner 决定；未完成前不得写疗效、免疫原性或普遍表达提升。

## 6. 科学 Gates 与停止规则

- **A10-G0 数据/baseline 可信**：E0 已全部完成，关键数据和直接 baseline 已达到 closeout 验收要求。G0 closeout v3 与独立复核 SHA 见第 0.1 节，独立复核 20/20 通过，裁决为 `A10_G0=PASS_DATA_AND_BASELINE_READY`；E1/E2 允许启动。A10-02 已启动但无结果，G0 通过不证明 H1/H2、E3/G2、SOTA 或 final untouched。
- **A10-G1 动力学增量**：E2 在严格 OOD 超过去守恒和简单模型；E1 决定能否增加跨研究主张。当前 H1/H2 均未证，G1 未通过；G1 失败则停止动力学主线。
- **A10-G2 功能阳性核心**：E3 达到预注册 SOTA 门槛后才允许大规模生成训练。当前 E3/G2 未证、SOTA=`false`；G2 失败则停止生成训练。
- **A10-G3 设计阳性核心**：E4 在等反馈/等成本下超过最强可比方法，且 E5 机制消融同向。

文档、测试、hash 和 PPT 是复现条件，不是科学 Gate。不得改成弱 baseline、回顾性最佳臂或“工程已完成”收尾；不得继续做无新科学问题的窗口、覆盖、初始化和 gating 消融。

## 7. Nested grouped CV、统计与成本合同

- 使用 nested grouped CV；outer test 不参与模型、特征、早停、超参或阈值选择。最终 untouched 在全部协议冻结后一次评估。
- 优化器 LR log-uniform、weight decay、dropout、warmup、grad clip、batch tokens、训练步数、编码器容量和正则强度只在 inner dev 用 ASHA/小网格。
- 动力学专属超参包括速率上下界、稳态容差、观察映射自由度、功能/占据损失权重和缺失数据采样；先做局部敏感性和可辨识性，再考虑大训练。
- 生成专属超参包括自然先验强度、能量温度、偏好采样、候选/top-k、早停与块长；全部计入推理成本。
- 所有方法使用相当调参预算和官方最佳可复现配置；至少 3 seeds，关键结论按功效分析增加，不能用默认超参误判架构。
- OOD 至少分 transcript、蛋白/family、研究、长度/GC；数据支持时才加宿主。已读 Subtelny、unique18 等不得再冒充 untouched。
- 功能以蛋白/研究为独立单位，Ribo 以转录本/研究为单位，设计以基因为单位；seed 先在组内聚合。报告 paired cluster bootstrap 95% CI、逐单位方向、Holm 校正和效应量。
- 分开记录 cache-before requests、唯一 scorer、模型 forward、生成时间、评分时间、训练成本、wall-clock、硬件和并行度。无真实轨迹的方法只比较 actual set；缺失为 null，不补零。
- 每个选定任务独立要求主效应及 CI 下界>0、多重校正通过、完整成本与 OOD；生成另需合法率100%。SOTA 是待验证目标，不是文档承诺。

## 8. 论文证据链

主线固定为：**独立密码子代理与 raw occupancy 的失败现象 → 测量过程和全局耦合缺口 → 非局部动力学证据 → 由守恒方程推导模型 → 功能 OOD 强 baseline → 设计质量—成本 → 对应消融与失败边界 → 真实功能验证。**

- Fig.1：真实变体/占据分布、简单代理失败、raw 跨研究失配及反例。
- Fig.2：观察校准、非局部密度响应和去守恒对照，给效应与 CI。
- Fig.3：速率参数化、稳态通量、研究观察映射和合法同义图，不画普通模块拼图。
- Fig.4：T1/T2/T3 分任务主表，不拼不可比数字或虚假总排名。
- Fig.5：预测与设计对应消融、参数可辨识性和失败案例。
- Fig.6：OOD、time-matched、全成本、不确定性与真实变体；前瞻完成后才加入生物功能结论。

每节按“问题→对照→现象→结论边界→为什么需要下一实验”写。每图只回答一个科学问题，每个主张映射 raw data、split、对照、指标和反驳条件。旧 RK21–RK42 只保留支撑动机的强证据，其余进入补充或审计档案，不按实验流水账组织 Results。

## 9. 三重核验、运行登记与一个月边界

每个阶段必须完成三重核验：

1. **代码核验**：检查 diff，运行项目风格的定向契约测试和真实端到端 smoke；最终运行项目标准测试。
2. **数据核验**：独立检查输入、hash、schema、数量守恒、split 隔离和原始计数保留。
3. **科学复算**：从独立原始序列或原始测量复算关键指标，先独立核验结果，再写论文或 PPT。

每项运行登记假设、commit+dirty hash、环境、数据/split SHA、完整命令、seed、拟合数、超参、forward/scorer/time、artifact SHA、结果和不可声称事项；`experiments/REGISTRY.md` 按实际运行更新，失败日志和历史 artifact 不删除、不覆盖。

一个月只推进 A10-00–06 与 T1–T3：先数据和 baseline，再观察过程与最小动力学，再功能 OOD，最后才是条件式生成、untouched 和论文。不得同时扩展 UTR 生成、MoE、大模型 scaling、完整 pair transformer、RLOO、 harmonization 或全长联合设计；不得先做大模型/生成训练再补数据与科学问题。公开数据优先；若需要湿实验/DBTL，预算和延期必须由 owner 决定，不能默认纳入一个月已交付结果。

禁止把训练收敛、合法率、文件数、测试数、Gate 数或 PPT 页数当作核心性能；禁止把 occupancy 写成绝对速率、回顾性关联写成因果、计算代理写成真实生物功能；禁止同蛋白随机拆分、target outcome 校准、反复 untouched、弱 baseline 或缺失预算补零制造胜利。
