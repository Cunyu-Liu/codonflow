# CodonFlow Spec（A8-RK · 真实功能与翻译动力学执行合同）

> 生效日期：2026-11-18，A8-RK v2。主审查与完整路线：根目录 `CodonFlow_A8_严格科研工程审查与一个月路线_20261118.md`。
> 最新权威实现审查点：远端 `/home/codonflow`，HEAD=`012338aa9fe700b25846f73546f4d9b1b3d05870`，工作树干净。核心文件与本地镜像 SHA 一致；本地继承的 dirty/untracked 文件不得删除或反向覆盖远端。
> 旧 A7/G2/T3.8 是不可变诊断证据。旧“2×2 不通过即终止所有学习模型”的总 Gate 作废，仅保留其对 frozen r5 的归因意义。

## 0. 证据纪律

信息必须分为：实现事实、文献事实、科学假设、待数据审计、实验结果。文献报告样本数不等于数据已经下载；候选架构不等于已经实现；计划不等于结果。

禁止混淆：CE 收敛与终端性能、合法生成与优化能力、计算代理与生物功能、开发集与独立确认、相关与因果、单任务胜利与通用 SOTA。

### 已冻结旧事实

- FULL/EDIT r5 已收敛；G2 中位 AUC −94.28%/−93.47%，18/18 全负，原 open-loop 方案 No-Go。
- T3.8 开发集 FULL/EDIT +59.95%/+68.73%，但时间比 42.68×/2.41×，不是独立、时间或外部优势。
- D4/D5 数量、精确重叠、D5 cluster 隔离已复核；D5 不是 curated family/species OOD。
- untouched24 未用于新模型选择；unique18 只作开发。
- 当前 `EditFlowTransformer` 只读 codon ID，无蛋白/UTR/宿主/目标/时间条件；损失是简化 masking，不是完整 CTMC。

## 1. 核心科学问题与任务

> 同义序列功能是否由“5′ 起始区结构可及性—全程翻译速度场—mRNA 降解”的空间耦合决定；显式学习这种耦合，能否在固定蛋白、固定 UTR/宿主上下文下实现优于现有方法的功能预测和多目标 CDS 设计？

一个月聚焦固定 UTR 上下文下的 CDS，不生成 UTR。蛋白一致性、长度与 stop 由同义 simplex 参数化保证。

### 可证伪假设

- **RK-H1**：CAI/GC/全局 MFE 在真实同义变体的蛋白/研究 OOD 上不如空间机制特征；若简单代理不劣，收窄动机。
- **RK-H2**： initiation、velocity、decay、UTR–CDS pair channel 有独立增量；无消融收益的成分删除。
- **RK-H3**：结构适应度、Ribo 速度、mRNA/蛋白功能可形成跨层一致证据；回顾性相关不称因果。
- **RK-H4**：机制势改善同预算设计与 time-matched 表现；仅代理提高不算真实功能提高。

## 2. 数据合同

### 2.1 三层数据

1. **自然先验**：D4/D5、CodonTransformer、RNARL 六物种。只作序列/宿主先验。
2. **机制数据**：五物种 Ribo-seq、tRNA/密码子参考、UTR–CDS 配对、结构/accessibility。occupancy 只称相对速度代理。
3. **真实功能**：Kudla 154 GFP、Boël 6,348 次实验/Protein Data Set、MAGE-seq 12,726 infA 突变，以及实际可获得的 LinearDesign/GEMORNA/COformer 序列与测量。

Dasher/六蛋白原始数据原文明确不公开，禁止写入训练承诺。所有外部数据先下载、解析和校验，状态才能从 `candidate` 改为 `available`。

### 2.2 清洗与 QC

- 保存 accession/release/URL/时间/许可/raw-clean SHA。
- CDS 检查长度、alphabet、终端/内部 stop、翻译一致性；ATG/部分 CDS 单独标记。
- 功能记录保留蛋白、UTR、载体、宿主、启动子、化学修饰、assay、batch、replicate、单位、检出限和缺失原因。
- 功能值只在 `protein×host×assay×batch` 内标准化，原始值与重复噪声保留。
- Ribo-seq 检查覆盖、P-site/密码子映射、重复一致性、零覆盖和研究批次。
- 报告长度/GC/CAI/MFE/EFE/宿主/蛋白簇分布，以及每蛋白变体数和表型范围。

### 2.3 划分与泄漏

- 检查 exact CDS/protein/ID、MMseqs2 同源簇、功能来源蛋白与 assay。
- 同一蛋白的同义变体不得随机跨 split；功能主测为蛋白 OOD，速度另做研究 OOD，自然模型保留同源 OOD。
- RSCU、归一化、calibration、特征选择只由 train 拟合。
- untouched24 与功能 untouched 均只最终评估一次；第三方预训练污染单独披露。
- 哺乳动物/跨宿主功能数据不足时，不得声称跨宿主功能泛化。

## 3. CodonFlow-RK 候选架构

### 3.1 约束与输入

状态 `x=(c1,…,cL), ci∈C(ai)`；输入包括当前同义状态、蛋白/氨基酸、固定 5′/3′UTR、宿主、Pareto 偏好和剩余预算。本阶段不生成 UTR。

### 3.2 必要组成

- codon 节点与候选密码子的三核苷酸展开；
- 合法碱基配对约束的 pair channel，显式建模 UTR–CDS 和远程 CDS 耦合；
- 起始窗口高分辨率与长程稀疏/轴向交互；
- 分别可监督的 `Φinit`、`Φens`、速度场 `v`、`Φdecay`/功能头及不确定性；
- 低保真 CAI/motif、中保真结构/Ribo、高保真真实功能的多保真训练。

pair channel 不宣称等价精确 partition function；ESM、attention、GFlowNet 本身均不列创新。

### 3.3 生成目标

候选核形式：

`qθ(y|x;w,b,h,u) ∝ q0(y|x;h,u) exp[-βΣk wkΔΦk(x,y)-βcΔcost(x,y)]`。

用偏好条件轨迹平衡/能量倾斜目标替代天然 CE，使反馈从训练起进入模型。数学目标与实现不一致时不得使用 flow 命名。

先验证机制预测头，再接入合法单密码子核。不得默认同时加入 MoE、完整 CTMC、短 rollout、RLOO 或扩参。每个组件需同输入、同参数/成本消融。

## 4. 任务—baseline—指标合同

| 任务 | 必需 baseline | 主终点 |
|---|---|---|
| 功能/适应度预测 | CAI/GC/局部与全局 MFE、Boël logistic、通用序列模型、可复现 VeloHARMO/COformer | 蛋白/研究 OOD Spearman/Pearson/RMSE/top-k enrichment |
| 速度预测 | RiboMIMO、iXnos、ROSE、VeloGRU/VeloBERT | 蛋白与研究 OOD R²/相关/RMSE |
| Harmonization | VeloHARMO、CHARMING、tAI、ICOR、HFC/BFC/URC、RNARL | 速度谱一致性、真实功能分层、等成本 |
| Accessibility 设计 | ID3、GA、SA、C10/C10-CAI | 同 1000 离散评估；可枚举时精确 ceiling |
| CDS 多目标设计 | LinearDesign、EnsembleDesign、RNARL、CAGFN、codonGPT、GEMORNA、CodonTransformer、COformer、内部强搜索/r5 | dense HV AUC、实际 Pareto/best、NED、time-matched |
| 全长外部边界 | mRNAutilus、ProMORNA | 仅同 UTR/输入/成本可比时排名 |

benchmark 由 unique18 扩展到 ID3 12 蛋白、RNARL 六物种、真实功能蛋白和 untouched24。外部方法按官方最佳可复现配置，不得故意弱化。

## 5. 评价与统计

- 真实初始 B=1；dense budget-step AUC，不插 `(0,0)`；缺失预算 `null`，不补零。
- 保留 B=50/100/500 Pareto/best、双向支配、NED、identity/legal。
- cache-before、唯一 scorer、forward、生成/评分时间、wall-clock、硬件和并行度分开。
- 无轨迹的外部集合不构造统一 AUC；ID3 等连续优化内部成本不得隐藏。
- 超参只在 dev 用 ASHA/小网格：LR/wd/dropout、batch tokens、ESM 冻结、能量/偏好温度、轨迹损失、候选/top-k、块长、早停与采样权重。
- 功能以蛋白/研究为独立单位，搜索以基因为单位，seed 组内聚合；报告 paired bootstrap 95% CI、逐单位方向和 Holm 校正。
- SOTA 判据：预注册主效应及 CI 下界>0、多重校正通过、合法率100%、成本完整；不能只赢均值或 r5。

## 6. 实验链与 Gates

### RK-G0：数据与强 baseline 真相

完成实际下载、QC、分布、无泄漏划分、官方 smoke、dense v2 和统一成本。数据不可用不得冒充；关键 baseline 不可运行需记录原因与边界。

### RK-G1：机制成立

E1 量化代理效度；E2 同骨干验证 initiation/velocity/decay/pair 的蛋白/研究 OOD 增量；E3 检查结构—速度—mRNA/蛋白跨层一致性。

至少一个机制组合稳定优于简单代理和同骨干无机制模型，才启动生成训练。失败时先修正科学问题，不默认接受“负结果论文”。

### RK-G2：逐任务性能

接入最小 CodonFlow-RK，完成功能、速度、accessibility、CDS 多目标主表和对应消融。未赢最强可比 baseline 的任务继续定向诊断，不能换弱 baseline。

### RK-G3：独立与实用泛化

冻结后一次评估 untouched24/功能 untouched；完成长度/GC/同源/研究/可用宿主分层和 time-matched。未重复则不写普遍泛化。

### RK-G4：论文与真实价值

每项主张映射原始数据、对照、指标和反驳条件。公开变体回顾验证只支持相应计算/机制结论；顶刊版本另需前瞻 design–build–test–learn，含 WT、LinearDesign/RNARL 等对照与独立重复。

## 7. 论文推理链

代理失效现象 → 真实数据中的空间耦合 → 由有效耦合推导模型 → 同预算强 baseline → 预测与生成两侧机制消融 → OOD/成本 → 真实变体验证 → 前瞻实验闭环。

Fig.1 代理失效；Fig.2 机制增量；Fig.3 模型推导；Fig.4 各任务主结果；Fig.5 机制消融；Fig.6 OOD/成本；Fig.7 真实验证。每图只承担一个科学问题。

## 8. 记录与复现

每次运行登记：假设、commit+dirty diff hash、环境/GPU、数据与 split SHA、checkpoint、完整命令/配置、seed、优化器/scheduler、best/last、训练曲线、forward/scorer/time、artifact SHA、指标版本、结果、结论与不可声称事项。

三重检查：代码 diff 与契约测试；输入/hash/schema/数量守恒；独立原始序列或原始测量复算。`experiments/REGISTRY.md` 实时更新，旧负结果与失败分层不得删除。

## 9. 范围与停止规则

- 一个月不同时扩展 UTR 生成、MoE、完整 CTMC、RLOO 和大模型 scaling。
- 数据无法获得或机制无 OOD 增量时，不启动昂贵生成训练；先修数据或科学问题。
- 某任务未赢不得宣称该任务 SOTA；不用不可比数字、弱 baseline 或重复 untouched 制造胜利。
- 计算代理不等于生物功能；未做前瞻实验不得声称疗效、免疫原性或普遍表达提升。
