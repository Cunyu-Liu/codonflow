# CodonFlow preprint skeleton（A7 · evidence-gated）

> 更新日期：2026-11-01。文件名保留 A6 仅为路径兼容，内容以 A7 合同为准。
> 状态：不是投稿草稿。当前无有效新模型 checkpoint，无 learned-vs-simple-search 结果，不可提交。
> 主任务：warm-start synonymous CDS editing。第一决定性结果：learned proposal vs 无学习简单搜索。

## 0. 一句话科学故事

**同义约束能够定义合法 CDS 空间，却不能告诉我们在指数级空间中下一步该往哪里走；本文检验学习到的有限步编辑提议，是否真的比简单搜索更节省多目标优化预算。**

Working title: **Finite-step synonymous editing for budget-aware multi-objective CDS optimization**

核心问题：在严格保持蛋白身份、相同初始状态和相同 scorer/时间预算下，learned synonymous proposal 是否优于最强无学习局部搜索？

## 1. 可证伪假设

| ID | 假设 | 对应证据与失败处理 |
|---|---|---|
| H1a | 有限步同义 Markov 核在可枚举小状态上实现精确终端 tilt | 小状态精确验证；失败则方法实现需修复 |
| H1b | 大空间 short-rollout 是带偏差和成本的近似，而非精确终端分布 | 近似偏差/成本曲线；不得把小状态结论外推为精确大空间证明 |
| H2 | learned proposal 相对最强简单搜索改善 anytime 多目标质量—成本表现 | G2：中位改善、paired CI、校正检验、identity/legal 和多样性共同裁决；失败则主贡献不成立 |
| H3 | short-rollout 相对 immediate 有净收益 | G3：质量与成本同时为正；失败则删除 short-rollout 主贡献 |
| H4 | 在 untouched 确认集和外部 CDS 方法上可界定适用/失败区域 | G4：两种初始化、分层预算和缺失方法披露；无稳定优势则写边界或负结果 |

RLOO、扩参、family/species OOD、SOTA 和生物功效不是本文预设假设。

## 2. 推理链：每一节由上一节未解决的问题触发

### ① 合法不等于会搜索

固定蛋白只定义了可行集合。DP、生成模型和局部搜索都能保持身份，真正的困难是多目标质量、多样性和有限预算之间的权衡。

**引出**：需要评价的不是合法性，而是搜索效率。

### ② 搜索效率的关键是提议分布

均匀编辑不利用自然 CDS 或目标结构；学习模型可能提供更有用的移动，但也可能只会复制自然序列或增加成本。

**引出**：引入有限步 learned proposal + terminal tilt，同时保留可审计的简单搜索对照。

### ③ 机制正确不等于学习有用

小状态精确验证、identity/legal 和 val plateau 只能说明实现与优化正确。旧复制模型已经证明 plateau 可以伴随无效下游行为。

**引出**：先排除退化，再做 learned vs 简单搜索的决定性实验。

### ④ 只有学习有必要，才值得增加 rollout 成本

如果 immediate learned proposal 不胜简单搜索，short-rollout 不能挽救主叙事；如果学习有效，再检验额外终端模拟是否带来净收益。

**引出**：G2 是 G3 的前置门。

### ⑤ 内部收益必须经独立确认和外部定位

开发集上的收益可能来自调参、参考域或初始化。需要 untouched D5 确认集、两种初始化和外部 CDS baseline 来判断适用边界。

**引出**：最终结论不是“全面 SOTA”，而是何时 learned editing 值得使用、何时不值得。

## 3. 章节提纲与当前可写范围

### 1 Introduction

**可写，但不写性能结论。**

- CDS 同义设计是多目标优化，不是单纯合法性问题。
- 三类方法的实际差别：全局/动态规划、生成先验、局部或引导搜索。
- 科学缺口：learned proposal 相对同样简单的无学习搜索是否有独立价值，常被 100% identity、单一 HV 或不等预算比较掩盖。
- 本文方法与研究问题；贡献只写“机制、对照协议和待检验假设”，不预写提升。

### 2 Related Work

**可写，必须正面覆盖以下差异。**

- CDS/密码子优化：LinearDesign、CAI-greedy、codonGPT、GEMORNA。
- 全长 mRNA 与 RL/搜索：mRNAutilus、ProMORNA、mRNA-GPT。说明它们与 CDS-only warm-start 的任务差异，不直接拼接摘要数字。
- 离散流与多目标引导：pCoMole、MOG-DFM、AReUReDi、TR2-D2。
- pCoMole 已包含 terminal gate、Tchebycheff、Doob-h 和短 rollout；本文只能主张固定长度同义空间中的新证据，不能把移植本身写成理论首创。
- RayGun/SCISOR 属于蛋白编辑/删除，不作为 synonymous CDS 数值 baseline。

### 3 Method

**可写。**

1. warm-start 任务与蛋白不变量；
2. 单密码子同义 Markov 核、显式 stay 与 learned proposal；
3. 终端势函数与精确小状态 tilt；
4. 大空间 short-rollout/候选剪枝近似及成本公式；
5. synonymous-corruption 预训练及其“自然恢复不等于偏好学习”的限制；
6. 无学习简单搜索对照和相同 scorer/cache 协议。

### 4 Evaluation Protocol

**可写方法，G0 产物未齐前不能写“已闭环”。**

- D4 开发、D5 确认；精确去重与操作定义同源隔离的区别；
- 开发 unique18 与 untouched 24 基因确认集；
- CAI/MFE/GC/motif 的计算代理性质、宿主参考和 folding 条件；
- 固定独立 HV reference/scale、anytime AUC、原始 Pareto front 与 NED；
- scorer/输出/时间三种预算和四成本；
- 基因为统计单位，3 seeds 只估计采样随机性；
- 第三方预训练重叠不可完全审计和 missing-method 规则。

### 5 Results

#### 5.1 机制正确性与成本核算

**当前可写。**小状态精确验证、by-operator 合法性和成本 trace。结论仅限实现正确。

#### 5.2 非退化学习行为

**阻塞于 G1。**新模型收敛、非源编辑、唯一解、位置覆盖和奖励响应；旧复制模型只作诊断反例。

#### 5.3 决定性结果：learned vs 简单搜索

**阻塞于 G2，是全文中心结果。**比较 learned、uniform、hill-climbing、MH/annealing、AReUReDi-style 的 anytime 质量—成本前沿，并给出逐基因统计和负结果。

#### 5.4 short-rollout 是否值得额外成本

**阻塞于 G3。**immediate 与 short-rollout 的净收益及近似偏差；无净收益则删除本节主贡献定位。

#### 5.5 独立确认与外部方法边界

**阻塞于 G4。** untouched 确认、两种初始化、外部 CDS 方法、长度/目标/预算分层和缺失方法。

#### 5.6 失败模式与适用范围

**只能在 5.2–5.5 后定稿。**包括简单搜索胜出的区域、长序列成本、代理目标敏感性和外部模型不可复现性。

### 6 Discussion

**当前不写。**必须回答：学习是否有必要、rollout 是否值得、何时选择其他方法、计算代理与真实生物功效之间还有什么距离。

## 4. 主图设计：一图一个科学问题

| 图 | 要回答的问题 | 当前状态 |
|---|---|---|
| F1 方法与不变量 | 合法空间、learned proposal 和 terminal tilt 如何分工？ | 方法图可准备，不写性能 |
| F2 非退化与机制 | 新模型是否摆脱复制，机制是否正确且成本可追踪？ | 等 G1；旧模型仅作反例 |
| **F3 learned vs 简单搜索** | **学习是否真的节省多目标优化预算？** | **等 G2；全文中心图** |
| F4 rollout 消融 | 更多终端模拟是否带来超过成本的收益？ | 等 G3 |
| F5 独立确认与外部边界 | 何时选择 CodonFlow、DP、生成模型或简单搜索？ | 等 G4 |

数据泄漏修复、数据分布、旧错误 baseline、OOM、不可复核旧表放补充材料或审计附录，不占主线。

## 5. 摘要的逻辑模板（不是可提交摘要）

1. **背景**：固定蛋白的 CDS 多目标优化需要在指数级同义空间中有效使用评分预算。
2. **缺口**：学习方法常与简单搜索在不一致预算下比较，难以判断学习本身的贡献。
3. **方法**：提出/评估有限步 learned synonymous proposal，身份由操作符保证，偏好由终端势函数控制。
4. **中心证据**：填入 G2 的真实效应、CI 和成本；没有结果前保留空白。
5. **边界**：填入 G3/G4 的 rollout 净收益、独立确认和失败区域。
6. **限制**：计算代理不等于表达或稳定性；不补写湿实验含义。

摘要不以“100% identity”作为第一句话，也不使用 SOTA、首次、scaling law 或 RL saturation 作为吸引力来源。

## 6. 当前允许与禁止的主张

### 当前允许

- 同义操作符在合法源上保持蛋白身份；
- 可枚举小状态的终端 tilt 已验证；
- 大空间实现使用 short-rollout/候选剪枝近似；
- D4/D5 内部精确/同源簇审计结果；
- 旧 arbitrary-corruption 模型发生复制退化，说明 plateau 不足以证明学习有效。

### 当前禁止

- learned 模型优于 uniform、局部搜索或任何外部方法；
- short-rollout、RLOO、355M 或扩容带来收益；
- family/species OOD、零泄漏总括声明、四层 benchmark 已验证；
- 旧 SOTA、capacity scaling、RL saturation、masking 普遍因果；
- 旧 full-token/e14、三臂和联合 HV 数字；
- CAI/MFE/GC/motif 对应表达、稳定性、安全性或疗效；
- 当前称为可提交预印本。

## 7. 发表路线

- **G2/G4 成立**：可形成预算感知的同义 CDS 学习方法论文，创新点在严格对照下发现的适用机制与边界，而不是组件名称。
- **G2 成立、G3 不成立**：保留 learned immediate editor，删除 short-rollout 主贡献。
- **G2 不成立**：转为训练诊断/负结果或测量研究；现有机制与审计资产不足以支撑强方法论文。
- **生物功效路线**：需要另立独立预测器和/或湿实验计划，不能由当前计算代理结果外推。
