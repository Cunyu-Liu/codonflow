# CodonFlow Tasks（A10 · Kinetic-CodonFlow 一个月执行清单）

> 生效日期：2026-11-23。唯一执行合同：`docs/handover/PROMPT_NEXT_AGENT_A10_KINETIC.md`；科学合同：`docs/handover/spec.md`；当前任务矩阵：`docs/handover/A10_00_TASK_DATA_BASELINE_CLAIM_MATRIX.md`。
> A7–A9 只作不可变证据引用。勾选只表示对应事项已有真实交付，不表示相关科学假设成立。A10-00 与 A10-01 已完成，**E0 与 A10-G0 已通过**，裁决为 `A10_G0=PASS_DATA_AND_BASELINE_READY`；A10-02（E1）v2 开发研究已完成，H1 仅开发阳性，最终跨研究结论未建立；A10-03（E2）已提交最小平均场实现，但 E2/G1 未完成，H2 未证。A10-G1–G3 均未通过，E3/G2 未证，SOTA=`false`，final untouched=`false`；不得越过 G2 生成训练。

## 全局执行约束

- 每项工作先登记假设、commit+dirty hash、环境、数据/split SHA、命令、seed、拟合数、超参和成本；结束登记 artifact SHA、结果、失败分层和不可声称事项。
- 所有外部数据实际下载、解析和校验后才可标 `available`；所有 baseline 实际运行后才可标 `ran`，不可运行标 `not_comparable` 及原因，不能以计划或论文存在冒充完成。
- 不读取 `untouched24`、MAGE functional untouched 或其派生文件；最终一次使用必须以协议冻结和相应授权为前提。不重启旧 A7 PID `2071716`，不在本阶段启动训练。
- 每阶段做代码/契约测试、输入/hash/schema/数量守恒检查、独立原始数据复算和真实端到端 smoke；结果独立核验后才进入论文/PPT。
- nested grouped CV 的 outer test 不参与任何选择；同蛋白变体不得随机跨 split，Ribo 不得随机拆 codon 行；calibration 不得读取 target test outcome。

## A10-00 远端重核与任务矩阵

**状态：远端重核和矩阵建立已完成；A10-01 与 E0 已完成，A10-G0 已通过。**

- [x] 更新版本事实：GitHub `a8-rk` 当前已推送至 `9c10fb77`；后续操作共享远端工作树前仍须重新核对 HEAD、工作树与进程，不沿用旧 HEAD。
- [x] 核实 RTX 5090、`torch 2.14.1+cu132` CUDA 真 matmul 通过；旧 A7 PID `2071716` 暂停且不重启。
- [x] 建立并更新一页任务—数据—baseline—主张矩阵，明确 RK42=0/9 同时满足 R1–R7 的真实含义、Goodman/Tunney 当前真实交付、Lareau `GSE58321` 已出现于 RK03/RK05 及所有冻结边界。

**依赖**：无。
**验收**：上述事实与计划分离；矩阵逐任务列出实际数据、baseline 真实状态、主指标、可/不可主张和下一动作；不得据此宣称 E0、数据可用、baseline 可复现或任何科学 Gate 通过。

## A10-01 E0：取得任务化数据、完成审计与真实 baseline smoke

**状态：已完成。** G0 closeout v3 SHA256=`93928d6b6c2599d7e18e59896863f4b3bea91b3e034f64538631d395711ac8cc`，独立复核 SHA256=`1c6a3b1e211998f7a79959eca68af3a03c92d94548b31eefcc7e62a0ebe1ebd3`，独立复核 20/20 通过；closeout 生产与独立复核 45 项测试通过，全部 A10 定向测试 251 passed。
**依赖**：A10-00。
**Gate**：`A10_G0=PASS_DATA_AND_BASELINE_READY`，E0/G0 已完成，E1/E2 允许启动。A10-02 v2 开发研究已完成、H1 仅开发阳性；A10-03 仅有最小平均场实现，E2/G1 未完成。G0 不证明 H2、最终跨研究、E3/G2 或 SOTA，final untouched=`false`，不得越过 G2 生成训练。以下逐项清单按本次 closeout 验收同步勾选；勾选不新增任何单项性能或科学结论。

### 功能与构建数据

- [x] 取得 Goodman2013 官方 CSV 并生成 clean：raw SHA256=`a03071027b8c0008d07fb7737de0a7d51765c6cff25bc86e93465a6253c7c33a`，14234 行、75 列、137 Gene、4817 exact CDS、280 leader、33 nt N 端片段、8439 SetGood；clean SHA256=`ce64f2caa9633fefae840e220d36b6360946d39b9253adc56f3ef297b9ab9c82`。
- [x] 完成 Goodman 最终 v3 审计及独立复算：report SHA256=`3036961a32502c1ea7a9bf6cd45f2ffbb0cadf2d18ff8f3405b4abd4bb1a6304`，独立 SHA256=`c78359d03a45f3bbbcc867f36be8b2c74219a9410c543a90d08e8784a6bf42ab`，31/31 通过；结论限定到实际 N 端片段构建几何，不外推为全长 CDS 或天然 UTR。
- [x] 复核 Kudla154 仅作固定 GFP 开发，Boël6348 仅作 ordinal/非同义辅助，Cambray2018 仅作 96 bp 非固定蛋白辅助，Mordstein 仅作已观察辅助；iCodon 继续禁用。
- [x] 对全部实际取得的功能数据完成序列/构建 QC、动态范围、重复噪声、缺失与长尾报告；不删除低表达或失败变体，不静默补字段。

### Ribo 数据

- [x] 完成 Tunney 本轮 E0 审计与独立验证：5894 transcripts、2920075 codon rows；report SHA256=`9fecfb838762950b2545f6db4fb0d6ba4ab92cc9483aad20c33cd1f0d8abf9b9`，clean SHA256=`238d9997f6449763bed69a4ba806b74ea0f77b95ee526cb6dff61fe9ce1b7a6e`，独立验证 24/24 通过。合并 lane 为非独立重复，不增加独立样本量；采用 A-site 映射与 RSEM 加权。
- [x] 纠正 Lareau `GSE58321` 的历史身份：已出现于 RK03/RK05，不再记为未读候选，不作为新的最终研究 OOD。
- [x] Mohammad/Subtelny 只作开发；为最终研究 OOD 另选至少一个真正未读研究，并在读取 target outcome 前冻结 source train、独立 target calibration 和 target test 角色。
- [x] 对其余拟用 Ribo 数据保留原始计数，审计 read coverage、P-site 偏移、密码子映射、重复一致性、零覆盖、footprint 长度和研究批次；occupancy 不写成绝对速率。

### 划分、泄漏与协议冻结

- [x] 检查 exact CDS/protein/ID、同源簇、同变体、重复测量、功能来源蛋白、研究批次和第三方预训练重叠；所有 RSCU、归一化、校准、特征选择只由 train 拟合。
- [x] 生成 Goodman 5 outer × 4 inner nested grouped CV 划分并独立验证：assignment SHA256=`e2d8b31bf6a5aee6f104c96ea484340b6d10654bc35494c36fa4a89a31e6a129`，split SHA256=`f49c93af8e2a30616d6f0e907f75dd8a08e29e5fe23e303484c120feb57683c2`，独立 25/25 通过，验证 SHA256=`379ef698d8f0029d929468c94bcdf594bd83384e957fcc31e4e66d46b4fc2f43`；仅称 Gene-grouped N 端片段构建 OOD，不称 protein OOD。
- [x] 按数据资格完成其余功能与 Ribo 分组：功能按实际构建、蛋白/family/研究的适用单位分组，Ribo 按转录本/研究分组；开发、calibration、outer test 和最终 untouched 分开。
- [x] 冻结 T1–T3 主指标、nested grouped CV、inner-dev 调参预算、至少 3 seeds、paired cluster bootstrap 95% CI、Holm 校正和成本 schema；缺失轨迹为 null，不补零。Goodman 已有划分不表示全部协议已冻结，全部协议冻结以本次 G0 closeout 验收为准。

### 直接 baseline 官方资产与真实 smoke

- [x] Goodman 7臂 nested 5×4 开发 benchmark 已完成：8439 SetGood rows，59073 prediction rows（7臂×5折），独立验证 32/32 通过。prediction SHA256=`aa0cfbc280f1dc3a3b1e1e829ce71bfabe942122dbac8671d322e314bdade271`，report SHA256=`0dc67e5b2b38bd79cfe19211362994a28a6206020264ea819400b7b7e76eea9d`，独立验证 SHA256=`384519f7bfc4a6cd574694bee838176b6f4d0c871367c4a567bfffd30828e5a4`。
  - 逐 outer 均值统一为 **Spearman/RMSE/top1**：constant=`NA/.785062/.090952`；CAI=`.992955/.015030/.784884`；GC=`.885724/.021479/.780810`；dG=`.792860/-.049617/.784445`；tAI=`.981755/.003549/.785177`；Ridge=`1.085185/.147541/.762021`；HistGB=`1.321994/.320124/.697210`。
  - 成本：wall-clock **370.0619 s**；HistGB **85 fits** 均为 **52–264 iterations**，**0 次触及 500 iterations 上限**。
  - 边界：只称开发 baseline；不构成机制、SOTA、protein OOD 或真实生物泛化结论。该子项本身不表示全部适用直接 baseline、公平功能主表、E0 或 G0 已完成，当前 E0/G0 以 closeout 整体裁决为准。
- [x] T1：在上述7臂开发 benchmark 基础上，完成其余适用的局部/全局 MFE、位置场、Boël 作者模型、通用序列模型和直接竞争方法的 G0 核验，并补齐适用直接 baseline；不得以7臂结果代替全部 T1 公平性核验，E3 公平功能主表仍未完成。
- [x] T2：完成适用的 constant、位置场、Ridge、RiboMIMO、iXnos、ROSE、VeloGRU/VeloBERT、VeloHARMO 的 G0 官方资产、适用性与研究内 transcript OOD smoke 核验；E1/E2 科学结果仍待后续实验。
- [x] EnsembleDesign 官方 quick v2 真实 smoke 成功 6/6，且 3 条输出与 README 匹配；该勾选仅限此 quick smoke，不代表完整公平设计比较完成。
- [x] T3：完成 LinearDesign、ID3、RNARL、CodonTransformer、COformer、VeloHARMO 及内部 hill/MH/SA/GA/random/r5 的 G0 核验；按任务核验 CAGFN、codonGPT、GEMORNA，保留真实轨迹或 actual set。ID3 两条 CPC 轨迹缺陷保留，不得记为成功；CodonTransformer 尚未成功运行，不得编造运行状态。
- [x] 对 CodonTransformer、COformer、VeloHARMO、RNARL、ID3、EnsembleDesign 及补充候选完成 G0 所需官方 URL/commit、环境、训练数据、输入输出、目标、默认/最佳配置、预训练污染、运行状态和失败原因登记；不换弱 baseline 冒充 SOTA。

### 本轮工程核验

- [x] G0 closeout 生产与独立复核 45 项测试通过，全部 A10 定向测试 251 passed。测试只支持工程状态，不代表科学假设或后续 Gate 通过。
- [x] G0 closeout v3 及独立复核完成：SHA256 分别为 `93928d6b6c2599d7e18e59896863f4b3bea91b3e034f64538631d395711ac8cc`、`1c6a3b1e211998f7a79959eca68af3a03c92d94548b31eefcc7e62a0ebe1ebd3`，独立复核 20/20 通过，裁决 `A10_G0=PASS_DATA_AND_BASELINE_READY`。

**交付**：E0 数据卡、raw/clean/split manifest、分布与泄漏报告、分组文件、baseline 真实运行矩阵、评价与成本协议、定向测试及独立复算记录。
**验收**：关键功能/Ribo 数据真实可用且分组无未处理泄漏；关键直接 baseline 有真实输出和公平配置；主指标、预算、成本及 OOD 全部冻结。本次 G0 closeout 已完成验收；E0/G0 通过不外推为 H1/H2、E3/G2、SOTA 或 final untouched 完成。

## A10-02 E1：检验观察过程可分性

**状态：v2 开发研究已完成，独立复核全量通过；H1=`development_positive`。最终未读跨研究验证未完成，不得写成最终跨研究、绝对速率或 SOTA 结论。**
**依赖**：A10-G0 已通过；Ribo 数据角色和校准协议已冻结。
**对应**：A10-H1、T2；本阶段不训练生成器。

- [x] 实现低自由度单调或仿射研究观察映射，将覆盖、检出限、重复噪声和缺失机制纳入观察噪声；限制 calibration 容量。
- [x] 在开发研究中对比 raw 直接运输与研究内校准：raw_unanchored−calibrated 的 TB-MSE effects 为 **0.0420274/0.0418212/0.0406288**，raw_anchored−calibrated 为 **0.0403316/0.0402787/0.0390835**；全部 CI lower>0、Holm<0.05，3 seeds 同向，校准后 TB-MSE 降低。
- [x] 开发研究按冻结协议仅在 source train 或独立 target calibration 拟合映射；未读取最终 untouched，final untouched=`false`。
- [x] 报告开发研究的映射、TB-MSE、Pearson/Spearman、校准、效应与 CI：仿射斜率 **0.1580–0.1644**、截距 **0.8224–0.8308**；Pearson/Spearman 不变，不得声称相关结构改善。
- [x] 登记 E1 v2 证据：summary SHA256=`2902e678f93815ccd7731720d940700ae84a88b7e8d5ee3dba8f3a833e6bef5d`，独立复核 SHA256=`cf5ebfcb450363722e7b49e2e8cf720f883778ddebea3a01b80a2a8cb35c0539`，独立复核全量通过；**33 项测试通过**，wall-clock **51.8138 s**。
- [ ] 最终未读跨研究评估仍须在全部协议冻结后按独立 calibration/target test 角色执行；当前不据此建立最终跨研究结论。

**交付**：E1 v2 开发研究的冻结协议、观察模型、校准诊断、独立复算、统计与成本已登记；最终跨研究交付仍待后续合格研究。
**验收**：开发阳性只允许写限定范围内的观察过程可分性证据；E2 可继续研究内数值与动力学检验，但 E2/G1 未完成，且只有后续相应证据成立，非局部响应才可作跨研究解释。

## A10-03 E2：最小动力学与流守恒增量

**状态：最小平均场实现已提交，工程与数值审计已登记；完整 E2 科学实验和 A10-G1 未完成。**
**依赖**：A10-G0 已通过；E2 可按冻结协议推进，但跨研究解释仍受 E1 开发证据边界约束，最终跨研究主张仍未建立。
**Gate**：A10-G1；当前 H1 仅开发阳性、H2 未证，本阶段不写生成器，不越过 G2 生成训练。

- [x] 提交最小平均场稳态算子；平均场不冒称精确随机模拟，不添加无数据支持的 decay 或远程 pair 头。
- [x] 完成该最小实现的工程/数值审计：**36 项测试通过**，真实 CUDA 审计 SHA256=`3cd3add70d9d05a47e9f6662867da0faf620586685d6d9092b96b1c975d471fd`；五组独立 least_squares 的最大密度误差 **1.33e-14**、梯度误差 **1.16e-14**、独立守恒误差 **3.94e-14**。
- [ ] 完成严格为正的起始率、逐位延伸率和终止率的完整参数化及训练动力学模型；当前未训练动力学模型。
- [ ] 完成小状态和数值对照上的稳态残差、通量守恒、边界、梯度、参数可辨识性和近似误差完整验收；现有误差登记不等于全部科学验收。
- [ ] 对比完整动力学、去流守恒同容量模型、独立密码子模型和纯位置场，匹配输入、参数量和训练预算。
- [ ] 在 transcript/变体 OOD 检验局部编辑上下游密度响应、通量变化及主指标；先做局部敏感性和可辨识性，不直接扩大训练。
- [ ] 报告至少 3 seeds、逐转录本方向、paired cluster bootstrap 95% CI、Holm、效应量、失败层和完整成本。

**交付**：最小平均场实现与测试已交付；去守恒对照、E2 OOD 主表、完整数值/响应诊断和不可声称清单仍未完成。
**验收**：只有严格 OOD 稳定超过去守恒与简单模型才通过 G1，并仅将通过的动力学量送入 E3；无独立增量则删除动力学核心并停止 Kinetic-CodonFlow 主线，不增加模块救场。

## A10-04 E3：功能 OOD 阳性核心

**状态：未通过；当前无 E3 结果。**
**依赖**：A10-G0 已通过，仍须 A10-G1；E2 已确定可进入功能模型的动力学量。
**Gate**：A10-G2；当前 E3/G2 未证、SOTA=`false`，通过前不大规模训练生成器。

- [ ] 将验证后的潜在通量/密度接入功能层，仅在测量支持时加入 mRNA 丰度等项；静态结构须独立消融后才保留。
- [ ] 在 T1 全部直接可比 baseline 上先完成构建内/转录本 OOD，再完成蛋白/family/研究 OOD；Boël/Cambray 等只进入匹配其测量性质的辅助表。
- [ ] 使用 nested grouped CV 和相当调参预算；outer test 不用于模型、特征、早停、超参或阈值选择。
- [ ] 报告 Spearman、RMSE、top-k enrichment、主效应、逐蛋白方向、校准、不确定性、失败分层、效应量、95% CI、Holm 和完整成本。

**交付**：E3 功能 OOD 主表、强 baseline 公平性审计、消融、统计与成本记录、独立复算。
**验收**：预注册主效应 paired 95% CI 下界>0且 Holm 通过，才建立功能阳性核心并允许进入 E4；否则继续诊断数据/目标，不接生成器，不把工程完成当作阳性。

## A10-05 E4/E5：合法设计核、质量—成本优势与机制消融

**依赖**：A10-G2；E3 验证的潜在功能场是唯一候选设计驱动力。
**Gate**：A10-G3。

- [ ] 实现合法同义图上的候选可逆核并精确归一化，保证蛋白、长度和 stop；`Fθ` 只含已验证项与明确约束。
- [ ] 在可枚举小状态验证合法率、归一化、详细平衡/平稳分布、采样一致、单/多步一致和成本；实现不符就不称 CTMC/flow。
- [ ] 与 T3 最强外部和内部方法按同初始、反馈、目标、预算、scorer、调参投入和硬件比较；保留 dense budget-step HV AUC、实际 Pareto/best、NED、合法率及 time-matched。
- [ ] 分开记录 cache-before requests、唯一 scorer、forward、生成/评分时间、训练成本、wall-clock、硬件和并行度；无真实轨迹只比 actual set，缺失为 null。
- [ ] 完成去流守恒、去观察映射、去起始结构、去自然先验的同参数/同成本消融，检查预测与设计方向、长度/GC/同源/研究/宿主分层及不确定性。
- [ ] 若 ID3 式 simplex 梯度或其他直接方法更强，保留并如实报告；代理设计与真实功能验证分表。

**交付**：合法核数学/代码一致性证据、E4 主表、完整轨迹/集合和成本、E5 对应消融与失败边界。
**验收**：等反馈/等成本超过最强可比方法且消融同向才通过 G3；只赢 r5/hill，或只赢等 scorer 而输等时间，不称实用 SOTA。无独立收益组件删除。

## A10-06 最终 untouched、E6 边界、干净复现与论文

**状态**：final untouched=`false`，本轮未读取、未执行最终 untouched。
**依赖**：选定任务的科学 Gate 已完成，全部模型、split、统计和成本协议冻结；untouched 使用具备相应授权。
**顺序**：最后执行，不因一个月期限提前读冻结数据或先写结论。

- [ ] 最终 untouched 只评估一次；分别确认 `untouched24` 与 MAGE functional untouched 的授权和协议，未获明确授权则完全不读，并如实保留未完成项。
- [ ] 在干净环境复现关键路径，运行定向测试、项目标准测试、真实端到端 smoke、输入/hash/schema/数量守恒检查和独立原始数据复算。
- [ ] 汇总 transcript、蛋白/family、研究、长度/GC 及数据支持时的宿主 OOD；保留不确定性、逐单位方向、失败层和全成本。
- [ ] 公开 held-out 变体只写回顾性验证；E6 前瞻 DBTL 另列至少两个蛋白、明确宿主/UTR、WT、强方法、独立重复和功能/稳定性测量，预算与周期交 owner 决定。
- [ ] 建立论文主张—raw data—split—对照—指标—反驳条件矩阵，按 Fig.1–6 科学问题组织；独立核验后才更新论文/PPT，不按页数追进度。

**交付**：一次性 untouched 记录或明确未执行原因、干净复现包、最终统计/成本表、论文证据矩阵和边界说明。
**验收**：每个数字可追溯到冻结 artifact，每项主张有真实对照和独立复算；未完成 E6 不写疗效、免疫原性或普遍表达提升，未赢最强 baseline 的任务保持“未解决”。

## 一个月顺序与决策点

1. **Day 0–4 / A10-00–01**：数据与 baseline closeout 已完成，`A10_G0=PASS_DATA_AND_BASELINE_READY`。
2. **Day 3–11 / A10-02–03**：A10-02 v2 开发研究已完成，H1 仅开发阳性，最终跨研究验证未完成；A10-03 已提交最小平均场实现，但完整 E2/G1 未完成、H2 未证。继续完成去守恒/简单模型公平比较和严格 OOD，不把数值误差当作动力学增量。
3. **Day 8–18 / A10-04**：功能 OOD 对强 baseline，决定 G2；当前 E3/G2 未证、SOTA=`false`，未通过则停止生成训练。
4. **Day 16–24 / A10-05（条件式）**：仅 G2 通过后做 E4/E5，决定 G3。
5. **Day 21–30 / A10-06**：最终 untouched、复现和论文证据闭环；E6 湿实验不默认压缩进一个月。

任何 Gate 未通过都保留未完成并执行对应停止规则；不得换弱 baseline、重复 untouched、删除失败分层、伪造外部轨迹/成本，或用文档、测试、hash、训练收敛和 PPT 页数替代核心性能。
