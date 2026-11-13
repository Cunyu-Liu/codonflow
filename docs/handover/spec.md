# CodonFlow Spec（A7 · warm-start 学习价值验证版）

> 生效日期：2026-11-01。本文是当前唯一有效合同；旧版勾选、命令和数字只在 journal/audit 中追溯。
> 已确认方向：主任务为 **warm-start synonymous CDS editing**；第一决定性关卡为 **learned proposal vs 无学习简单搜索**。
> 当前处于 P2/G1 实施阶段；G0 已于 2026-11-12 正式通过。r4 两臂已完成 e1/e2 独立验证并保存完整 checkpoint，但在 e3 中途同时中断，且现场确认 `/teams` 配额写入失败；r4 未收敛、未通过 G1。当前以新 r5 目录从已校验 e2 状态精确恢复，r4 全部证据保留。
> 2026-11-12 执行补充：代码与提交以远端 `/home/codonflow` 为工作副本；大型数据、权重、日志和 artifacts 只放 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/`。训练及 GPU 验证必须实际使用 CUDA；CUDA 不可用、kernel 不兼容或 CPU 静默降级时立即停止并保存证据。独立任务可并行，但不得为占满显存制造实验或越过 Gate。

## 0. 当前事实状态

- 2026-11-12 交接证据记录：untouched 24 基因确认集、D5 train RSCU 和 24/24 独立 calibration pool 已完成并验证；合并代码完整回归为 131 passed, 1 skipped。上述资产仍须在执行实例上复核路径、哈希和内容，不能只凭交接文字推进。
- unique18 seeds 0/1/2 均完成 18/18、五方法及独立 MFE/NED 复算；25 物种原始来源、全量清洗、分布、冻结资产和 calibration 已闭环并通过 G0。
- 当前没有通过行为验收的收敛新模型。旧 arbitrary-corruption full-token 模型虽在 e14 达到 val plateau，但已塌缩为“不编辑/复制”；其 checkpoint、三臂输出和联合 HV 均只作负结果证据，不得进入主结果。
- 2026-10-31 synonymous 两臂早期停止时无 checkpoint；r4 后续已完成 e1/e2 并保留完整恢复状态，但 e3 中断且未收敛。当前以 r5 精确恢复，不能将恢复 checkpoint 直接视为 G1 通过或新下游结果。
- 已有资产：有限步同义 Markov 操作符、小状态精确验证、成本 trace、v4/v5 内部划分审计、core seed-0 五方法 baseline 的部分结果。
- `unique18.fasta` 的 18 条输入已审计，但 baseline 输出不得仅凭文件数称为完整；正式使用前必须按 manifest 复核 done/partial/missing、MFE/NED 和种子。
- 旧 SOTA、capacity scaling、RL saturation、masking 因果、family/species OOD、四层 benchmark 结论全部撤回，不得搬入新论文。
- 当前不能提交预印本，不能宣称 Gate 通过或 CodonFlow 优于任何方法。

## 1. 主任务与科学问题

### 1.1 主任务：warm-start synonymous CDS editing

给定源 CDS `x`，其翻译蛋白为 `p`，输出一组 CDS `Y`，要求每个 `y ∈ Y`：

1. 与 `x` 等长、阅读框合法；
2. 翻译后与 `p` 完全一致；
3. 只含一个预先定义的终端 stop；
4. 在冻结的计算目标和预算下改善质量—多样性—成本前沿。

蛋白身份由同义操作符保证，是**方法不变量和正确性条件**，不是相对性能优势。

### 1.2 次级任务：protein-only 初始化

从蛋白 `p` 生成同义初始 CDS 后再编辑，只用于外部方法对照和初始化敏感性分析。它不得与 natural-source warm-start 混成一张因果对照表。

### 1.3 核心科学问题

> 在相同初始状态、终端目标和 scorer/时间预算下，学习到的有限步同义编辑提议，是否比最强无学习局部搜索更有效地进行多目标 CDS 优化？

短 rollout、RLOO、模型扩容和 OOD 都必须服从这个问题，不再各自成为预设贡献。

## 2. 可证伪假设

| ID | 假设 | 证伪条件 |
|---|---|---|
| H1a | 有限步单密码子同义核在可枚举小状态上实现精确终端 tilt | 精确小状态验证失败 |
| H1b | 大空间 short-rollout/候选剪枝只是近似，其偏差和成本可被测量 | 不把它作为“必然更优”的假设；若把近似写成精确即表述错误 |
| H2 | learned proposal 相对最强简单搜索改善 anytime 多目标质量—成本表现 | 预注册主终点未达到 G2，或 identity/legal/多样性发生不可接受退化 |
| H3 | short-rollout 相对 immediate 的净收益覆盖额外 scorer/forward/时间成本 | G3 无正向净收益；失败后删除 short-rollout 主贡献 |
| H4 | 在外部 CDS 方法和独立确认集上，可界定本方法的适用与失败区域 | 没有稳定优势区域时，结论改为边界/负结果，不写 SOTA |

以下不是预设假设：第一个、SOTA、容量瓶颈、RL 随预训练饱和、family/species 泛化、表达或稳定性提升。

## 3. 方法边界与命名

### 3.1 可保留的方法资产

- `synonymous_markov.py`：合法源检查、单密码子同义跳转、位置/密码子联合归一化、显式 stay。
- `FiniteStepSynonymousMarkovEditor`：精确小状态 Doob 验证；真实大空间仅使用 short MC rollout 与候选剪枝近似。
- `rollout_count=0` 为 immediate 消融；轨迹、forward、终端请求、实际 scorer 和唯一 scorer 必须分别记录。
- feasibility 主要来自 by-operator construction；终端势函数表达偏好，不能把全部合法性归因于 terminal gate。

### 3.2 Legacy 禁止项

- 旧 `BatchedGuidedSampler`、旧条件去噪和旧 RLOO 不得用来证明新有限步方法有效。
- 旧 full-token/e14 和 edited-token 任意腐蚀模型不得用于新对照。
- 旧 56M/355M 曲线不得解释为容量定律；旧 RLOO 结果不得解释为 RL 收益或无效。
- `live best.pt` 不得用于跨时间比较；所有对照使用不可变 checkpoint + SHA256。

### 3.3 版本命名

- `D3`：旧 862,240 条、存在精确跨 split 重叠的数据版本，仅历史。
- `D4`：`splits_v4_protein`，776,474 个唯一蛋白。
- `D5`：protein-homology-cluster，776,441 条；只是操作定义的同源隔离。
- `M_ARB_*`：旧 arbitrary-corruption 模型，统一标记 `invalid_for_downstream`。
- `M_SYN_D4_*`：使用 D4 和 synonymous corruption 的开发模型；不得再简称“v5 模型”。
- `M_SYN_D5_*`：未来使用 D5 的确认模型，只有实际训练后才存在。

## 4. 数据、清洗与泄漏合同

### 4.1 已有证据

- D4：train/val/test = 621,306/76,444/78,724；split 间及 split 与已审计 benchmark 的精确 CDS/蛋白重叠为 0。
- D5：train/val/test = 618,073/80,191/78,177；MMseqs2 identity=0.5、双向 coverage=0.8，split/benchmark 簇隔离和精确重叠审计通过。
- D5 不是 curated family 或 species OOD；没有下游结果前不能声称同源泛化。

### 4.2 G0 前必须补齐

1. **来源与清洗流水账**：数据库/release/URL/下载日期/哈希；逐步报告输入数、每条过滤规则移除数和剩余数。
2. **质量分层**：合法阅读框、ATG/单 stop/internal stop/ambiguous base、长度、翻译有效性；记录非标准遗传代码和异常注释的处理。操作合法性按 alphabet、阅读框和唯一终端 stop 判定，不强制 ATG；非 ATG 记录单列为可能部分 CDS 的质量与选择偏差，不得与操作非法混同，也不得在查看分布后静默删除。
3. **分布审计**：长度、GC、CAI/RSCU、密码子使用、物种占比、簇大小；说明 300–6000 nt 过滤和蛋白去重造成的选择偏差。
4. **元数据**：尽可能恢复 transcript ID、species、gene/protein 映射；无法恢复时明确降级，不编造 family/species 标签。
5. **参考表与归一化**：CAI/RSCU 只由对应训练 split 或独立公开参考集构建；D4 与 D5 不得混用。HV 范围来自独立 calibration pool，不能由 test 输出决定。
6. **外部方法泄漏声明**：CodonFlow 内部零重叠不等于第三方预训练模型未见过目标；无法审计时列为限制。

### 4.3 Benchmark 分为开发与确认

- **开发集**：eGFP/nanoLuc + 已冻结 unique18。可用于调试、阈值预注册和 G2/G3 开发裁决，不作为最终独立证据。
- **确认集**：在任何新模型调参前，从 D5 test 中冻结 24 个未参与既往实验的唯一蛋白/CDS；按长度和 GC 分层，尽可能保留物种元数据。排除所有旧 benchmark、unique18 及其同源连通簇。
- 确认集只能用于最终 G4；若用于调参，必须重新建立 untouched 集合并记录 amendment。
- Fluc2P/Spike/PEMax/MUC1/uAb 只作为候选外部任务；序列、许可和 CDS-only 适用性核查前不得称为统一公共 benchmark。

### 4.4 当前分布限制

unique18 平均长度 642 nt、GC 0.4396，且 13/18 为短序列，与训练总体约 1.64 kb、GC 0.514 不同。它只能作为长度分层开发集，不能代表自然总体或支撑广泛泛化结论。

## 5. Baseline 与对照层级

### 5.1 G2 必需简单搜索对照

- `uniform_synonymous`；
- greedy/hill-climbing；
- Metropolis-Hastings/annealing；
- AReUReDi-style 同操作符多目标搜索；
- learned base proposal。

所有内部方法使用相同初始状态、同义可行状态与终端目标、scorer/cache 和预算追踪。`uniform` 在首次评分使用相同 paired 初始状态，后续从完整同义空间按位置独立均匀采样，作为强全局基线；hill-climbing、MH/annealing 与 AReUReDi-style 使用相同单密码子局部核。learned base 使用其学习到的单密码子核。最强简单基线按基因取主终点最优者，形成严格对照。

### 5.2 G4 外部 CDS 对照

- LinearDesign、GEMORNA、codonGPT；
- CAI-greedy 与最强简单搜索保留为参照；
- mRNAutilus、ProMORNA、mRNA-GPT 先核查代码/权重/公开序列，能在同一 CDS-only 协议复跑才进入数值表；否则列为“相关但未数值复现”。

RayGun 与 SCISOR 是蛋白编辑/删除方法，不进入 synonymous CDS 数值主表。

### 5.3 输入信息公平

- G2 是严格的 natural-source warm-start 内部对照。
- G4 同时报告 natural-source 与 protein-only 初始化；外部方法若只使用蛋白，必须标明输入差异，禁止把两种初始化混为同一因果结论。

## 6. 指标、预算与统计

### 6.1 目标与正确性

- 计算目标：CAI、MFE、GC target deviation、长度归一化 motif penalty；所有方向统一为最大化。
- CAI 参考宿主/参考表、GC target、RNAfold 版本与 folding 条件、motif 清单必须在运行前冻结。
- 固定 GC=0.55 只能作为明确计算设定，不得宣称为跨物种最优生物目标。
- identity/legal 必须逐序列验证；任何违规都使该臂失败，不能只用均值掩盖。

### 6.2 主终点与辅助指标

- **主终点**：固定独立参考域下，多目标 HV 随唯一 terminal scorer 预算变化的 anytime AUC。
- **辅助指标**：各目标 best-at-budget、原始 Pareto front、IGD+/epsilon 或 non-dominated coverage、长度归一化 NED。
- HV 参考点和 scale 对每个基因跨方法、跨 seed 固定；不得再由当次参评输出或 test seed 重新估计。
- 退化轴默认拒绝计算并显式记录；只有运行前登记的 amendment 才允许替代规则，禁止事后选择有利口径。

### 6.3 三种预算分开报告

1. scorer 预算：唯一 terminal evaluations；
2. 输出预算：真实唯一解数，不随机补足；
3. 时间预算：同硬件端到端 wall-clock。

模型 forward、rollout batch forward、轨迹数、状态转移、cache 前请求、实际 scorer、唯一 scorer 分开记录。官方实现不可见的计数记 `null`，不得编造。

### 6.4 预算网格与统计单位

- scorer 网格：B = 50 / 100 / 500；主比较使用整条 anytime 曲线，不只看单一 B。
- 每个基因至少 3 个采样 seed；seed 只估计随机性，不作为独立生物样本。
- 主要统计单位是基因。使用 paired gene-level bootstrap 95% CI、Wilcoxon signed-rank 与 Holm 多重比较校正；同时报告中位相对效应和逐基因结果。

## 7. 验收门与停止规则

### G0：数据与协议就绪

必须完成 §4.2、开发/确认集冻结、baseline 资源表、独立 calibration 参考域和结果 schema。当前 **已通过**，裁决文件为 `07_a7_data/g0_gate.json`，SHA256=`8b5dbeea278c31792fb1a6107539c223cb9031a821d7152aee5f7e25d0ea136b`。

### G1：模型收敛且非退化

1. 独立 val 连续 3 epoch 相对改善 <0.1% 才允许写 converged；保存 best/last/training_state/converged 和哈希。
2. 在至少 3 个开发基因、每基因 100 个配对样本上：identity/legal=100%，≥95% 输出不同于初始序列，≥80 个唯一终端序列，最大单一终端序列频率 ≤20%。
3. 报告 stay-p、P(edit)、位置覆盖、奖励响应和与 uniform 的逐串重合；这些诊断不能替代 G2。
4. 上述数值是排除明显退化的操作阈值，不是性能证据；如需修改，必须在查看新输出前记录 amendment。

当前 **未通过**。r4 的 e1/e2 checkpoint 仅用于精确恢复，不是 converged 或通过行为验收的模型；r5 仍须完成全部 G1。

### G2：第一决定性关卡——learned vs 简单搜索

在开发集、3 seeds、相同初始状态与预算下比较 §5.1 方法。通过需同时满足：

- identity/legal=100%；
- learned 相对每基因最强简单搜索的主终点中位相对改善 ≥10%；
- gene-level paired bootstrap 95% CI 的下界 >0，Holm 校正后配对检验 `p<0.05`；
- 长度归一化 NED 不低于最强简单搜索的 70%，且无明显单序列塌缩。

未通过：停止 short-rollout 主贡献、RLOO、扩参和 SOTA 写作，转入训练诊断或负结果路线；不得用外部弱 baseline 绕过此门。

### G3：short-rollout 净收益

只在 G2 通过后进行。使用同一冻结 checkpoint、paired 初始状态和相同预算比较 immediate 与 short-rollout。主终点和时间成本均有正向 gene-level 证据才保留 short-rollout；否则主线只保留 immediate。

### G4：独立确认与外部边界

- 用 D5 训练最终模型，在 untouched 24 基因确认集上重复 G2 主对照；不得重新选择阈值或参考域。
- 再与 §5.2 外部方法比较两种初始化、目标数、长度和三种预算。
- 主结论可以是优势区域和失败边界，不要求所有场景 SOTA；但不得用确认集调参。
- D5 只支持操作定义的同源泛化，不支持 curated family/species OOD。

### G5：论文与发布

只有 G1–G4 对应证据齐全，才能写学习结果、外部主表和 Discussion。若 G2/G4 失败，只能按实际证据降级为测量/机制/负结果报告，不得改名为性能胜利。

## 8. RLOO、扩参和湿实验的位置

- RLOO 不是主合同组成部分。严格同义空间中翻译一致性接近常量，必须先证明存在非平凡学习信号；只有 G4 后才可单独评审。
- 355M/更大模型不是当前关键路径。只有 56M 通过 G2 且存在可重复的容量限制证据时才扩容。
- 本轮没有湿实验。CAI/MFE/GC/motif 仅为计算代理，禁止写成表达、稳定性、安全性或疗效证据。

## 9. 论文主线与可发表性边界

主线：**优化预算问题 → 可学习同义提议 → 机制正确但有效性待证 → learned vs 简单搜索 → rollout 净收益 → 独立确认与外部边界。**

- 数据审计和小状态验证是支撑证据，不再冒充全文中心结果。
- 中心结果是 learned vs 简单搜索的 anytime 质量—成本前沿。
- 当前发表状态为 **不可提交**。若 G2/G4 不成立，仅测量与机制资产不足以支撑强方法论文。
- 相关工作必须覆盖 pCoMole、AReUReDi、MOG-DFM、TR2-D2、mRNAutilus、ProMORNA、mRNA-GPT、codonGPT、GEMORNA 和 LinearDesign，并明确任务差异。

## 10. 工程与证据纪律

- 每个 run 记录数据 SHA256、代码 commit、`code_dirty`、配置、seed、checkpoint 不可变路径与 SHA256。
- 训练、baseline、负结果和失败日志全部保留；不得删除不利结果。
- 图表只从冻结 JSON 自动生成，标题不得超出数据支持范围。
- 旧 runbook 中指向 `a6_v4_56m_*` 的命令全部视为历史，禁止执行。
- 本合同修改不等于授权自动启动训练或评测；后续实验按 tasks 的依赖与用户指令执行。
