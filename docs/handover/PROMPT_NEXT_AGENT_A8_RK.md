# 给下一位执行者的完整提示词（CodonFlow A8-RK）

你现在接手 CodonFlow，不是来再写一份研究计划，而是来**真实执行 A8-RK，完成数据、机制、模型、强 baseline、OOD、论文和复现闭环**。把它当作自己的课题：核心目标是提出并验证有价值的科学问题，在每个预注册测评任务上公平超过最强可比 baseline。不要用工作量、训练收敛或合法生成代替核心性能，不要预先接受“负结果论文”作为终点。

## 一、先建立正确上下文

先完整阅读：

1. 工作区根目录 `CodonFlow_A8_严格科研工程审查与一个月路线_20261118.md`
2. `codonflow-main/docs/handover/HANDOFF_A8_RK_20261118.md`
3. `codonflow-main/docs/handover/spec.md`
4. `codonflow-main/docs/handover/tasks.md`
5. `codonflow-main/paper/CodonFlow_preprint_A7.md`

旧 A7 handoff/prompt 和 `2026-11-18-a8-feedback-controlled-rescue.md` 只作历史诊断。旧 r5 的 `proposal×feedback` 2×2 不再阻塞新路线。

远端权威代码位于 `/home/codonflow`，最近核对 HEAD=`012338aa9fe700b25846f73546f4d9b1b3d05870`，大型资产位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/`。开始时重新核对 commit/status，因为状态可能已变化。不要把任何服务器密码写入文档、命令日志、git 或回复。

保留用户已有修改和历史结果。不要自行 `git reset --hard`、`git clean`、删除旧资产、覆盖远端、commit 或 push。需要修改时先明确权威工作树；本地镜像与远端漂移只能记录和协调，不能粗暴覆盖。

## 二、核心科学问题与成功定义

研究问题：

> 同义序列功能是否由“5′ 起始区结构可及性—全程翻译速度场—mRNA 降解”的空间耦合决定；显式学习这种耦合，能否在固定蛋白、固定 UTR/宿主上下文下，实现优于现有方法的功能预测和多目标 CDS 设计？

论文证据链必须是：

**真实变体中的代理失效 → 空间耦合的 OOD 增量 → 由有效机制推导模型 → 各任务最强 baseline → 预测与生成两侧对应消融 → OOD/质量—时间 → 独立真实功能。**

每个任务分别判断是否 SOTA。主效应及 paired 95% CI 下界必须大于0，多重校正通过、合法率100%、成本完整。未赢最强可比 baseline 的任务标为未解决并继续定向诊断，不能换弱 baseline、删除失败分层或用不可比数字包装。

## 三、立即执行 RK-G0：数据与 baseline 真相

不要停留在“建议收集数据”。实际下载、解析、校验并登记：

- Kudla et al. 的 154 个同义 GFP；
- Boël et al. 的 Protein Data Set/6,348 次实验；
- MAGE-seq 的 12,726 个 infA 单/双密码子突变；
- VeloHARMO 使用的五物种 Ribo-seq 来源；
- RNARL Zenodo `15486992`、CodonTransformer 可用数据；
- 实际可恢复的 LinearDesign/GEMORNA/COformer 序列和测量。

Dasher/六蛋白原始数据不公开，不能使用。任何下载失败都记录真实原因，不得从摘要或图片猜数值。文献样本数在下载核对前只能写 `candidate`。

实现并测试 `tasks.md` 中的数据脚本，完成：

- accession/release/URL/license/raw-clean SHA 和处理谱系；
- CDS 翻译、长度、起止/内部 stop、异常转录本检查；
- 蛋白、UTR、载体、宿主、启动子、化学修饰、assay、batch、replicate、单位、检出限与缺失原因；
- 功能值仅在 `protein×host×assay×batch` 内标准化，同时保留原始值和重复噪声；
- Ribo 覆盖、P-site/密码子映射、重复一致性和研究批次 QC；
- 长度/GC/CAI/MFE/EFE/宿主/蛋白簇分布，以及每蛋白变体数和表型动态范围。

按 exact CDS/protein/ID、MMseqs2 同源簇、来源蛋白和 assay/研究划分。**同一蛋白变体不得随机跨 train/test。** 功能主测为蛋白 OOD，Ribo 增加研究 OOD；RSCU、归一化、校准和特征选择只由 train 拟合。冻结 untouched24 与功能 untouched，不能用于调参。

并行跑通各任务官方 baseline smoke：LinearDesign、EnsembleDesign、RNARL、ID3、CodonTransformer、VeloHARMO；继续补 CAGFN、codonGPT、GEMORNA、COformer、CHARMING、RiboMIMO/iXnos/ROSE。记录官方 commit、环境、命令、输入、输出、默认/最佳配置和成本。不可运行者如实标边界，不能用弱方法替代。

完成真实 B=1 dense budget-step AUC、实际输出集合 schema、原始 scorer 独立重算和统一成本。缺失预算为 null，不补零。

## 四、执行 RK-G1：先证明机制，再训练生成器

### E1 代理效度

在真实同义变体上比较 CAI、GC、局部/全局 MFE 和组合基线，使用蛋白/研究 OOD。报告每个 assay 的方向、效应、增量解释和失败区域。如果简单代理不失效，收窄动机，不能选择性展示。

### E2 空间耦合增量

在同一骨干上分别加入 initiation、velocity、decay 和 pair channel，保持输入、参数或训练计算匹配。比较蛋白 OOD、研究 OOD 和长度/GC 分层，报告 paired CI 与预测不确定性。没有独立增量的组件删除，不得为了架构复杂而保留。

### E3 跨层机制一致性

分别和联合预测 MAGE 结构适应度、Ribo 速度、Boël mRNA/蛋白层结果，做适用的分层或 mediation 分析。检查结构—速度—降解是否形成一致证据。回顾性关联不得写成因果，attention 图不得代替机制实验。

至少一个机制组合在真实功能 OOD 稳定优于简单代理和同骨干无机制模型，才进入生成训练。若不成立，先修数据质量、划分或科学假设，不要直接堆 RL/扩参。

## 五、执行 RK-G2：实现最小 CodonFlow-RK

一个月聚焦固定 UTR 上下文下的 CDS，不生成 UTR，不同时加入 MoE、完整 CTMC、短 rollout、RLOO 或大模型 scaling。

实现：

1. 每位置同义 simplex，保证蛋白、长度和 stop。
2. codon 节点结合蛋白、宿主和预算；候选密码子展开为三核苷酸。
3. 合法 RNA 配对约束的 pair channel，显式建模 UTR–CDS 与远程 CDS 耦合；起始区高分辨率，长程用稀疏/轴向交互。
4. 分别可监督的 `Φinit`、`Φens`、速度场 `v`、`Φdecay`/功能头及不确定性。
5. 低保真 CAI/motif、中保真结构/Ribo、高保真真实功能的多保真训练。
6. 合法偏好与预算条件核：

   `qθ(y|x;w,b,h,u) ∝ q0(y|x;h,u) exp[-βΣk wkΔΦk(x,y)-βcΔcost(x,y)]`。

7. 偏好条件轨迹平衡/能量倾斜目标，取代天然 CE 作为终端训练目标。用小可枚举状态验证目标分布、归一化和采样一致；实现不符时不得称 flow。

最终功能评价不能用参与候选选择的同一代理充当唯一真值。ESM、attention、GFlowNet 本身不列创新；贡献必须由机制数据和消融支持。

为新实现补充符合项目现有风格的单元/契约测试。每个阶段运行项目标准 `pytest tests/` 和相关真实 CUDA smoke；不能只测 import 或 tensor shape。必须做真实端到端小任务，再启动完整实验。

## 六、逐任务完成强 baseline 主结果

分别执行，不能合并成虚假总排名：

- 功能/适应度预测：CAI/GC/局部与全局 MFE、Boël logistic、通用序列模型、可复现 VeloHARMO/COformer；指标为 OOD Spearman/Pearson/RMSE/top-k enrichment。
- 速度预测：RiboMIMO、iXnos、ROSE、VeloGRU/VeloBERT；蛋白与研究 OOD。
- Harmonization：VeloHARMO、CHARMING、tAI、ICOR、HFC/BFC/URC、RNARL；等成本速度谱一致性与真实功能分层。
- Accessibility：ID3、GA、SA、C10/C10-CAI；同1000离散评估，可枚举时比较精确 ceiling。
- CDS 多目标：LinearDesign、EnsembleDesign、RNARL、CAGFN、codonGPT、GEMORNA、CodonTransformer、COformer、内部 hill/MH/SA/GA/random/r5；dense HV AUC、实际 Pareto/best、NED、合法率、time-matched。
- mRNAutilus/ProMORNA 只在 UTR、输入和成本可比时比较。

超参只在 dev 用 ASHA/小网格：LR/wd/dropout、batch tokens、ESM 冻结、能量/偏好温度、轨迹损失、候选/top-k、块长、早停和采样比例。不能用 test/untouched 调参，不能把更多训练或推理计算误当架构优势。

完成为什么有效的对应消融：去 pair/initiation/velocity/decay/自然先验/偏好/预算条件，同参数与同推理成本。预测和生成两侧的机制结论必须一致；无收益组件删除。

## 七、执行 RK-G3/G4：独立、真实功能和论文

冻结所有配置后一次评估 untouched24、功能 untouched、来源蛋白/研究、长度/GC 和可用宿主分层。完成同硬件单 worker time-matched，记录连续优化、生成、评分、forward、唯一 scorer 和并行成本。等时间未赢不得称实用 SOTA。

真实功能先做公开 held-out 变体回顾验证。顶刊所需前瞻 design–build–test–learn 只能作为后续实验，除非真的完成：至少两个蛋白、固定宿主/UTR、WT/LinearDesign/RNARL 对照和独立重复。不得把计划写成湿实验结果，不得由代理推导疗效、免疫原性或普遍表达提升。

按既有预印本结构生成 Fig.1–7：代理失效、机制增量、模型、分任务主结果、机制消融、OOD/成本、真实功能。每个数字自动来自冻结 JSON；每个主张必须映射到原始数据、对照、指标和反驳条件。

## 八、工程记录与最终交付

每次运行更新 `experiments/REGISTRY.md`：假设、commit+dirty diff hash、环境/GPU、数据/split SHA、checkpoint、完整命令/配置、seed、优化器/scheduler、best/last、曲线、forward/scorer/time、artifact SHA、指标版本、结果和不可声称事项。同步更新 `tasks.md` 和新的 handoff，不覆盖旧负结果。

完成干净环境安装、完整测试和真实端到端 smoke。检查 `git status`，删除仅由本轮测试产生且不需要的临时输出，不动用户已有文件。

最终回复必须包含：

1. 实际可用的数据、样本数、质量、分布、划分与泄漏审计；
2. 每个 baseline 的真实运行状态与公平性；
3. 每个科学假设的实验结论及反驳/边界；
4. 每任务相对最强 baseline 的效应、CI、成本与是否真正达到 SOTA；
5. 新增/修改文件、checkpoint/artifact 哈希和测试命令及结果；
6. 论文主线哪些环节已经闭合、哪些仍未完成；
7. 任何阻塞及需要用户决定的事项。

现在开始阅读上述文件并执行 `RK-01/RK-02`，不要再次只输出计划。