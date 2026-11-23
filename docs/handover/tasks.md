# CodonFlow Tasks（A10 · Kinetic-CodonFlow 一个月执行清单）

> 生效日期：2026-11-23。唯一执行合同：`docs/handover/PROMPT_NEXT_AGENT_A10_KINETIC.md`；科学合同：`docs/handover/spec.md`；当前任务矩阵：`docs/handover/A10_00_TASK_DATA_BASELINE_CLAIM_MATRIX.md`。
> A7–A9 只作不可变证据引用。勾选只表示对应事项已有真实交付，不表示相关科学假设成立。除 A10-00 明示的两项外，以下 A10 工作均未完成；尤其 **A10-00 完成不等于 E0 或 A10-G0 完成**。

## 全局执行约束

- 每项工作先登记假设、commit+dirty hash、环境、数据/split SHA、命令、seed、拟合数、超参和成本；结束登记 artifact SHA、结果、失败分层和不可声称事项。
- 所有外部数据实际下载、解析和校验后才可标 `available`；所有 baseline 实际运行后才可标 `ran`，不可运行标 `not_comparable` 及原因，不能以计划或论文存在冒充完成。
- 不读取 `untouched24`、MAGE functional untouched 或其派生文件；最终一次使用必须以协议冻结和相应授权为前提。不重启旧 A7 PID `2071716`，不在本阶段启动训练。
- 每阶段做代码/契约测试、输入/hash/schema/数量守恒检查、独立原始数据复算和真实端到端 smoke；结果独立核验后才进入论文/PPT。
- nested grouped CV 的 outer test 不参与任何选择；同蛋白变体不得随机跨 split，Ribo 不得随机拆 codon 行；calibration 不得读取 target test outcome。

## A10-00 远端重核与任务矩阵

**状态：已完成的部分仅为远端重核和矩阵建立；E0 尚未开始交付。**

- [x] 重核 `/home/codonflow-a8-rk` 与 GitHub `a8-rk`：HEAD 均为 `8200c5617748819f6a1ef27c968620c4b723f38f`，工作树干净。
- [x] 核实 RTX 5090、`torch 2.14.1+cu132` CUDA 真 matmul 通过；旧 A7 PID `2071716` 暂停且不重启。
- [x] 建立一页任务—数据—baseline—主张矩阵，明确 RK42=0/9 同时满足 R1–R7 的真实含义、Goodman raw 未取得、Lareau `GSE58321` 仅为未读候选及所有冻结边界。

**依赖**：无。
**验收**：上述事实与计划分离；矩阵逐任务列出实际数据、baseline 真实状态、主指标、可/不可主张和下一动作；不得据此宣称 E0、数据可用、baseline 可复现或任何科学 Gate 通过。

## A10-01 E0：取得任务化数据、完成审计与真实 baseline smoke

**依赖**：A10-00。
**Gate**：全部验收后才通过 A10-G0；没有真实功能与可靠 Ribo 输入，不启动 E1–E3，关键 baseline 未跑通不在 E4 称 SOTA。

### 功能与构建数据

- [ ] 从论文公开补充材料、PMC/NCBI 或其他合法公开源取得 Goodman2013 construct-level raw；保存 accession/release/URL/license/下载时间/raw-clean SHA/处理谱系，不从网页或图中猜值。
- [ ] 审计 Goodman 的固定 leader、N 端同义窗、完整/片段 CDS、UTR、载体、宿主、启动子、assay、batch、replicate、单位、检出限和缺失原因；结论限定到实际构建几何。
- [ ] 复核 Kudla154 仅作固定 GFP 开发，Boël6348 仅作 ordinal/非同义辅助，Cambray2018 仅作 96 bp 非固定蛋白辅助，Mordstein 仅作已观察辅助；iCodon 继续禁用。
- [ ] 对全部实际取得的功能数据完成序列/构建 QC、动态范围、重复噪声、缺失与长尾报告；不删除低表达或失败变体，不静默补字段。

### Ribo 数据

- [ ] 在远端反查 Lareau `GSE58321` 及其他未读研究的实际文件、是否已读、来源和可用性；未取得 P-site/密码子映射、覆盖、重复和研究元数据前保持 `candidate`。
- [ ] Mohammad/Subtelny 只作开发；为最终研究 OOD 选定至少一个未读研究，并在读取 target outcome 前冻结 source train、独立 target calibration 和 target test 角色。
- [ ] 保留原始计数，审计 read coverage、P-site 偏移、密码子映射、重复一致性、零覆盖、footprint 长度和研究批次；occupancy 不写成绝对速率。

### 划分、泄漏与协议冻结

- [ ] 检查 exact CDS/protein/ID、同源簇、同变体、重复测量、功能来源蛋白、研究批次和第三方预训练重叠；所有 RSCU、归一化、校准、特征选择只由 train 拟合。
- [ ] 功能按蛋白/family/研究分组，Ribo 按转录本/研究分组；开发、calibration、outer test 和最终 untouched 分开。
- [ ] 冻结 T1–T3 主指标、nested grouped CV、inner-dev 调参预算、至少 3 seeds、paired cluster bootstrap 95% CI、Holm 校正和成本 schema；缺失轨迹为 null，不补零。

### 直接 baseline 官方资产与真实 smoke

- [ ] T1：核实并运行适用的 constant、CAI/GC、局部/全局 MFE、位置场、Ridge/HistGB、Boël 作者模型、通用序列模型和直接竞争方法。
- [ ] T2：核实并运行适用的 constant、位置场、Ridge、RiboMIMO、iXnos、ROSE、VeloGRU/VeloBERT、VeloHARMO；先做研究内 transcript OOD smoke。
- [ ] T3：核实 LinearDesign、EnsembleDesign、ID3、RNARL、CodonTransformer、COformer、VeloHARMO 及内部 hill/MH/SA/GA/random/r5；按任务核验 CAGFN、codonGPT、GEMORNA，保留真实轨迹或 actual set。
- [ ] 对 CodonTransformer、COformer、VeloHARMO、RNARL、ID3、EnsembleDesign 及补充候选记录官方 URL/commit、环境、训练数据、输入输出、目标、默认/最佳配置、预训练污染、运行状态和失败原因；不换弱 baseline 冒充 SOTA。

**交付**：E0 数据卡、raw/clean/split manifest、分布与泄漏报告、分组文件、baseline 真实运行矩阵、评价与成本协议、定向测试及独立复算记录。
**验收**：关键功能/Ribo 数据真实可用且分组无未处理泄漏；关键直接 baseline 有真实输出和公平配置；主指标、预算、成本及 OOD 全部冻结。任一关键项缺失，G0 保持未通过。

## A10-02 E1：检验观察过程可分性

**依赖**：A10-G0；Ribo 数据角色和校准协议已冻结。
**对应**：A10-H1、T2；本阶段不训练生成器。

- [ ] 实现低自由度单调或仿射研究观察映射，将覆盖、检出限、重复噪声和缺失机制纳入观察噪声；限制 calibration 容量。
- [ ] 对比 raw 直接运输、研究内校准、无动力学序列模型、位置场和 constant；先完成研究内 transcript OOD。
- [ ] 仅在 source train 或独立 target calibration 拟合映射；冻结全部分析后再读 target test outcome，并保留完整读取日志。
- [ ] 报告映射自由度、源内拟合、潜在参数稳定性、transcript-balanced MSE、mean per-transcript Pearson/Spearman、校准、效应与 CI。

**交付**：E1 冻结协议、观察模型、研究内/研究 OOD 表、校准诊断、独立复算和失败分层。
**验收**：若校准后仍不优于简单模型，明确不写跨研究动力学，只允许在研究内继续 E2；只有观察可分性成立，后续非局部响应才可作跨研究解释。

## A10-03 E2：最小动力学与流守恒增量

**依赖**：A10-G0；E1 已冻结并完成。若 E1 阴性，只做研究内问题，不继承跨研究主张。
**Gate**：A10-G1；本阶段不写生成器。

- [ ] 实现严格为正的起始率、逐位延伸率和终止率，以及最小可微排斥晶格/经验证平均场稳态算子；不添加无数据支持的 decay 或远程 pair 头。
- [ ] 在小状态和数值对照上验证稳态残差、通量守恒、边界、梯度、参数可辨识性和近似误差；平均场不冒称精确随机模拟。
- [ ] 对比完整动力学、去流守恒同容量模型、独立密码子模型和纯位置场，匹配输入、参数量和训练预算。
- [ ] 在 transcript/变体 OOD 检验局部编辑上下游密度响应、通量变化及主指标；先做局部敏感性和可辨识性，不直接扩大训练。
- [ ] 报告至少 3 seeds、逐转录本方向、paired cluster bootstrap 95% CI、Holm、效应量、失败层和完整成本。

**交付**：最小动力学实现与测试、去守恒对照、E2 OOD 主表、数值/响应诊断和不可声称清单。
**验收**：只有严格 OOD 稳定超过去守恒与简单模型才通过 G1，并仅将通过的动力学量送入 E3；无独立增量则删除动力学核心并停止 Kinetic-CodonFlow 主线，不增加模块救场。

## A10-04 E3：功能 OOD 阳性核心

**依赖**：A10-G0、A10-G1；E2 已确定可进入功能模型的动力学量。
**Gate**：A10-G2；通过前不大规模训练生成器。

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

1. **Day 0–4 / A10-00–01**：完成数据与 baseline 真相，决定 G0；A10-00 已完成不代表本周目标完成。
2. **Day 3–11 / A10-02–03**：先观察过程，再最小动力学；决定跨研究解释资格与 G1。
3. **Day 8–18 / A10-04**：功能 OOD 对强 baseline，决定 G2；未通过则停止生成训练。
4. **Day 16–24 / A10-05（条件式）**：仅 G2 通过后做 E4/E5，决定 G3。
5. **Day 21–30 / A10-06**：最终 untouched、复现和论文证据闭环；E6 湿实验不默认压缩进一个月。

任何 Gate 未通过都保留未完成并执行对应停止规则；不得换弱 baseline、重复 untouched、删除失败分层、伪造外部轨迹/成本，或用文档、测试、hash、训练收敛和 PPT 页数替代核心性能。
