# CodonFlow Spec（A8 · 证据驱动抢救与预印本合同）

> 生效日期：2026-11-18。本文是当前执行合同；A7 的 spec、Gate、负结果和恢复历史只作不可变证据，不得静默改写。
> 权威科学代码：远端 `/home/codonflow`，审查时 HEAD=`dc75b0561b8773b28ef81ce9d551c110ea1ad992`，工作树干净，完整回归 228 passed、1 skipped。大型数据、权重、日志和 artifacts 位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/`。
> 本地 `codonflow-main/` HEAD=`5f9e5a560b118568d435fa68a72ef9253d4252c5`，有继承的 modified/untracked 文件且部分核心文件落后于远端；它是交接镜像，不得直接当作干净训练基线，也不得反向覆盖远端。
> 当前裁决：原始 A7 open-loop 方案正式 No-Go；learned-hill 在开发集有正向但高成本信号；尚无可提交预印本、独立确认、外部 SOTA 或生物功能结论。下一阶段首先修正对照和指标，不是扩参。

## 0. 证据纪律与当前事实

### 0.1 四类信息必须分开

1. **仓库事实**：可由代码、配置、原始 JSON、FASTA、checkpoint hash、进程或测试直接复核。
2. **合理推断**：与事实一致但尚未由因子实验唯一识别的机制解释。
3. **材料不足**：缺少输入、原始序列、资源记录、第三方预训练信息或可比实验。
4. **待新增证据**：必须经新实验、独立复算或文献全文核验才能回答。

禁止把“已有代码”“测试通过”“跑完训练”“开发集阳性”“独立确认”“论文主张成立”混为一谈。

### 0.2 已冻结事实

- FULL r5：`checkpoints/a7_full_r5/converged.pt`，SHA256=`e6a26102b0f5ae9443dbfb9526d418169ba577138016e70430203d80eef16d1c`；best epoch 18、停止 epoch 21、best val=1.159711169985858。
- EDIT r5：`checkpoints/a7_edit_r5/converged.pt`，SHA256=`77e81b5b9af886c2cc4a712fc064e5fc3c3c6f7386369a27916d67758736a9df`；best epoch 23、停止 epoch 26、best val=1.2313300454448592。
- G2：324/324 完成，identity/legal=100%；FULL/EDIT 相对每基因最强简单搜索的中位 AUC 改善 −94.28%/−93.47%，18/18 基因均负，最强基线均为 hill-climbing，Holm p=1.0。Gate=`eval_outputs/a7_g2_r5/g2_gate.json`，SHA256=`a2e157b2635860460cde95d8c3a03d12a7b948b2cd6d20dab5ce37deb8923cbc`。
- T3.8：90/90 learned-hill 分片完成；15/15 个其余开发基因为正，FULL/EDIT 中位 AUC 改善 +59.95%/+68.73%，Holm p=6.1035e-5；耗时比中位 42.68×/2.41×，FULL 最大 242.65×。FULL 15/15 基因 NED≥70%，EDIT 14/15；两臂时间要求均不满足。Gate SHA256=`835ffe644098a75a6cfcec2f9440dd9f84a004cd4eb9ce95ac0fe1cba0a0bdf5`。它仅是开发诊断，不翻案 G2。
- 2026-11-18 AUC 敏感性：从实际初始评分 B=1 起，增加 B=10/25/250 后，FULL/EDIT 中位效应为 −94.58%/−93.61%，仍均 18/18 负。证据=`audits/20261118/g2_metric_sensitivity.json`，本地副本 SHA256=`cb0698f21e15a36d092bedd4050026a4d511a87360e01e85d0d47cec68dfbaa9`。这只是已存目标向量的敏感性分析，不是新 Gate 或全 scorer 独立重算。
- 外部实际预算重评：54/54 完成、18/18 record，状态=`external_reference_complete`，但 `scientific_gate_passed=false`、`not_a_method_ranking=true`。缺少真实顺序轨迹和完整预算的方法不得进入统一 AUC 排名。
- D4=621,306/76,444/78,724；D5=618,073/80,191/78,177。D5 是 MMseqs2 identity=0.5、双向 coverage=0.8 的操作性蛋白同源簇隔离，不是 curated family/species OOD。
- 2026-11-18 全量独立复核再次确认上述记录数、唯一 CDS/蛋白和 split SHA；D4/D5 跨 split 精确 CDS/蛋白/ID 重叠均为0，D5 unmapped=0且跨 split cluster 重叠=0。证据=`审计与交接_20261117/results/data_split_independent_20261118.json`。非 ATG 记录仍须作为可能部分 CDS 与选择偏差披露。
- unique18 已反复用于开发；untouched 24 未用于新评价，仍禁止调参、选择模型或反复查看。
- 全部目标是计算代理；没有湿实验，禁止表达、稳定性、安全性、免疫原性或疗效提升表述。

### 0.3 已撤回内容

旧 arbitrary-corruption、capacity scaling、RLOO、family/species OOD、联合 HV、旧 SOTA 与生物功能宣称均不得搬入 A8 主结果。蛋白一致性由同义操作符保证，不是模型创新。

## 1. 核心科学问题与任务命名

### 1.1 当前真正实现的任务

**protein-defined synonymous CDS search from randomized synonymous initialization**：

给定天然 CDS 所定义的蛋白序列、固定长度和终端 stop，从该蛋白的随机同义 CDS 初始状态出发，在 CAI、MFE、GC target deviation、长度归一化 motif penalty、scorer/forward/wall-clock 预算下，输出一组同义 CDS，并比较质量—多样性—成本前沿。

输入蛋白来自天然 CDS；`scripts/a7_run_learned.py` 与简单搜索均以 `synonymous_x0(source, rng)` 初始化。初始化后，模型只读取当前随机同义状态，不再读取天然密码子序列。因此“natural-source warm-start editing”不是当前信息流的准确名称；若要主张天然 CDS 条件编辑，必须新增显式天然序列条件输入及对应消融。

### 1.2 新核心科学问题

> 在蛋白、随机同义初始分布、终端反馈、目标权重、scorer 预算和硬件成本严格一致的条件下，学习到的局部/块编辑提议，能否相对最强无学习搜索改善 dense anytime 多目标质量，并在 untouched 同源隔离基因上保持时间匹配优势？

### 1.3 创新定位

当前可检验的创新是**成本可审计的同义提议学习及反馈匹配评估设计**。它是建模/训练策略与实验整合的候选创新，不是已成立的概念首创。有限步离散流、time conditioning、短 rollout、RLOO、扩容和天然序列条件都必须经消融后才能进入贡献列表。

## 2. 可证伪假设

| ID | 假设 | 最小证伪证据 |
|---|---|---|
| A8-H1 | G2 的惨败部分来自 open-loop 与反馈搜索的信息不对等，而不只是模型容量不足 | `proposal={random,learned} × terminal_feedback={off,on}` 中 learned 无独立效应，且交互不成立 |
| A8-H2 | 自然序列去噪训练与终端 CAI/MFE/GC/motif 优化错位；终端对齐训练能改善 learned-hill | 终端对齐模型在相同骨干、预算和反馈下不优于 frozen r5 learned-hill 或 random-hill |
| A8-H3 | 当前模型包含可利用的目标/密码子偏好 | 合法同义概率质量、候选分数与 Δutility/接受收益无稳定关联，或因子实验无 learned 主效应 |
| A8-H4 | 提议优势可转化为实用质量—成本优势 | 等 scorer 有质量优势但 time-matched 无优势，或成本优化后仍不具竞争力 |
| A8-H5 | CAI/MFE/GC/motif 前沿对真实同义变体功能有增量效度 | 外部同义变体数据中无增量关联；若成立则仅保留算法 benchmark，撤销广泛生物价值叙事 |
| A8-H6 | D5 untouched 基因上可复现开发效应 | 独立确认效应方向/幅度不复现，或只在单一长度/GC 层成立 |

## 3. 当前架构事实与边界

### 3.1 实际数据流

- `src/codonflow/models/edit_flow.py::EditFlowTransformer`：67 个 codon/special token，8 层双向 Transformer，`d_model=768`、`n_heads=12`，输出 blank head 与 token head。
- `src/codonflow/train/run_pretrain.py` 与 `src/codonflow/data/dataset.py::corrupt_x_t_synonymous`：腐蚀比例随时间参数变化，但网络 forward 不接收时间、目标权重、CAI/MFE/GC/motif、物种、蛋白 embedding 或结构信息。
- `src/codonflow/models/synonymous_markov.py::SynonymousJumpProposal._transition_tensors`：当前推理忽略 `time`；T=4 是重复时间齐次局部核，不是时间条件离散流。
- FULL 对全部位置计算 token CE，EDIT 只对实际变化位置计算 token CE。token CE 在全部 67 类上计算，推理却在合法同义集合内重新归一化；合法概率质量及其与优化失败的关系尚未测量。
- `edit_flow_loss` 的 docstring 已说明是简化 masking realization，不是完整 CTMC Edit Flow rate objective。论文不得把当前实现包装为完整离散流理论验证。
- `scripts/a7_run_learned.py::learned_search`：模型从同一随机同义初始状态重复采样，scorer 只记录，不根据终端反馈改变后续提议。
- `src/codonflow/models/simple_search.py::SimpleSearch.run`：hill/MH/AReUReDi-style 使用终端 utility 决定接受/后续搜索。G2 的“同 scorer 预算”没有控制终端信息，不能单独归因于架构或容量。
- A7 blank head 参与“位置×替换密码子”联合核，stay 被聚合；旧 `CodonGuidedSampler` 只使用 token logits，二者不得混写。
- 双向全注意力长度复杂度为 O(L²)，token 最大长度 2002；RNAfold 还引入额外长序列成本。当前没有证据支持靠扩容解决 G2。

### 3.2 优化与工程风险

- 训练使用固定 length-bucketed batches、动态腐蚀、AdamW、梯度裁剪，无实际 LR scheduler；验证 loss 是 packed-batch 均值，不是严格全 token 加权。
- `conditionality_probe` 含远端固定路径，影响可移植性。
- 本地与远端源码漂移、`experiments/REGISTRY.md` 停更、多个历史训练入口并存，均是复现风险。
- G2/T3.8 独立审计主要重算已存 `objectives` 的 HV/AUC，并独立重算 NED；`a7_recompute_unique18.py` 才从序列重算完整目标。不得把前者写成全 scorer 独立复算。

## 4. 数据、划分与公平性

1. D4 仅精确蛋白去重/划分，D5 才是操作性同源簇隔离；旧通用 pipeline 的核苷酸 MMseqs2 默认参数不得与 D5 的蛋白参数混写。
2. CAI/RSCU 只能来自对应 train split 或独立公共参考；D4/D5 不混用。
3. untouched 24 的选择只用长度、GC、ID、cluster，并排除精确 CDS/蛋白及同源簇；它只能在 A8-G3 使用一次。
4. LinearDesign、codonGPT、GEMORNA 等第三方的预训练数据重叠无法完整审计，必须披露，不能宣称完全无污染。
5. 参数量、预训练数据、请求数、真实唯一 scorer、forward、输出数、硬件、并行度和 wall-clock 分开报告。
6. 外部方法只有实际输出集合时，报告 Pareto/best-at-actual-budget/实际成本；不得用零填充伪造 500 点，也不得把无序输出当 anytime 轨迹。

## 5. A8 评价合同

### 5.1 不可变 legacy 指标

A7 `anytime_curve` 只在 B=50/100/500 计算 HV，额外从 `(0,0)` 做梯形积分并除以 500；真实初始序列在 B=1 评分。它应命名为 `legacy_sparse_3point_auc_v1`，仅用于复现历史，不称完整连续 anytime 曲线。预印本中“including the initial point at zero budget”必须撤回。

`a7_recompute_external.py` 的 `actual_budget_auc` 对尚无点的预算会给 HV=0，与“缺失预算不补零、不进入统一 AUC 排名”冲突；该字段只作探索性诊断，不能排名。

### 5.2 新主终点 `dense_budget_step_auc_v2`

- 每个真实唯一 scorer 点按预算 b=1…500 排序，HV_b 为截至 b 的累计最优 hypervolume；B=1 使用真实初始 HV，不添加零预算假点。
- 主指标为 `Σ_{b=1}^{499} HV_b / 499`，即完整 budget-step 面积；B=50/100/500 的 Pareto、四目标 best-at-budget 为共同次要终点。
- 同时报告 time-matched HV、NED、identity/legal、唯一解数、forward、cache-before requests、真实 scorer、wall-clock。
- 主成本实验固定单 worker、同 GPU/CPU、同 ViennaRNA 版本与并发；高并发历史时间只作描述，不能当公平速度对比。
- v1 与 v2 必须并存输出，任何结论变化都需解释；旧结果不得覆盖。

### 5.3 反馈匹配因子对照

最小核心设计为：

| proposal | feedback=off | feedback=on（同一 hill accept/reject） |
|---|---|---|
| random single-codon | random-open-loop | random-hill |
| learned single-codon | learned-open-loop | learned-hill |

每组使用相同 paired initial、目标权重、calibration、独立 cache 和 500 唯一 scorer。主对比为 feedback=on 内 learned vs random；off 组及交互用于识别机制。不得再拿 learned-off 直接对比 random-on 后宣称架构无效。

### 5.4 统计

基因为独立单位，seed 先在基因内聚合。报告中位相对效应、10,000 次基因级 paired bootstrap 95% CI、双侧效应方向、预注册单侧 Wilcoxon、FULL/EDIT 或多臂 Holm 校正。确认集不做模型选择。开发集显著不等于独立确认。

## 6. A8 Gates 与停止规则

| Gate | 必要内容 | 通过条件 | 失败处理 |
|---|---|---|---|
| A8-G0 真实性/口径 | 版本、原始序列、scorer、hash、环境、v2、外部缺失预算 | 关键 artifact 可追溯；独立重算无未解释差异；228+ 回归及新增测试通过 | 停止训练，先修数据/代码 |
| A8-G1 机制 | 2×2 因子、合法概率质量、候选—Δutility、成本诊断 | 预注册 6 个开发基因×3 seeds 完整；learned-on 相对 random-on 有稳定正效应且能区分反馈作用 | 不训练新骨干；若 learned 无价值，转负结果/benchmark |
| A8-G2 开发模型 | 18 开发基因、v2、成本、消融 | 相对最强简单搜索中位 dense AUC 改善≥10%、CI 下界>0、Holm p<0.05、identity/legal=100%、逐基因 NED≥70%；time-matched 改善>0且CI下界>0 | 最多两轮目标/训练迭代；仍失败则停止学习模型主线 |
| A8-G3 独立确认 | D5 模型、untouched 24、只跑一次 | 重复主要质量/时间门槛，报告长度/GC 分层与失败区域 | 不写泛化/SOTA；转开发诊断或负结果 |
| A8-G4 外部边界 | LinearDesign 等按任务、输入、实际输出和成本比较 | 至少一个预注册可比任务显示有竞争力的质量—成本，并披露不可比项 | 不写外部 SOTA，仅内部算法结论 |
| A8-G5 预印本 | 主张—证据矩阵、原始结果、图、代码、负面结果 | 每项主张有对应 Gate；无代理→生物功能越界 | 不提交 |

任何 Gate 不得通过挑选弱 baseline、删除失败基因、补零、事后改指标或重复使用 untouched 24 来“修复”。

## 7. 架构迭代约束

1. 首先冻结骨干做机制实验；不得先扩参。
2. 最多三个候选方向，优先级依次为：终端对齐的轻量微调；成本感知的块提议/解码；有时间与目标条件的真实离散流。
3. 每个方案必须写明瓶颈、修改、理论/经验依据、风险、最小实现、对照、消融、量化成功标准和失败退出。
4. 新架构必须解决已测瓶颈，并证明相对同参数/同成本随机搜索和 frozen r5 的新增能力。
5. 若简化模型或 head-only 微调已足够，不保留无收益的复杂模块。

## 8. 论文与科学表述边界

- 当前阶段为 **A：工程原型和评估资产较完整，但论文级核心贡献尚未成立**。
- 可保留的论文主线：领域痛点 → 简单搜索强且便宜 → 原 open-loop 学习提议失败 → 反馈匹配揭示提议价值 → 终端对齐与成本优化 → 独立/外部边界 → 何时学习有优势。
- 若 2×2 或独立确认失败，主线必须改为严格的负结果与 benchmark，不得继续写 SOTA。
- 计算代理只能支持算法优化结论。没有外部功能效度或湿实验时，不得写“提升 mRNA 表达/稳定性”。
- LinearDesign、codonGPT、CAGFN 等已经覆盖联合 CAI/MFE、同义约束 RL、多目标条件/Pareto 等相关能力，不能把“使用学习模型/离散生成/同义 mask”本身写成首创。

## 9. 训练与实验记录强制模板

每次训练或评价在启动前建立 run ID，结束后补齐：

`日期｜假设｜代码commit+dirty diff hash｜环境/CUDA/GPU｜数据版本与split SHA｜checkpoint SHA｜完整命令与配置｜seed｜batch/optimizer/scheduler/clip｜best/last epoch与收敛依据｜train/val曲线｜forward/scorer/wall-clock｜artifact路径与SHA｜指标版本｜结果｜结论与不可声称事项｜失败/恢复历史｜复核人/复核脚本`。

三重检查固定为：①代码 diff、单元/契约测试；②输入/hash/schema/数量守恒；③独立原始点或原始序列复算。`experiments/REGISTRY.md` 必须在下次训练前补齐 A7 记录并恢复实时更新；journal 不能成为唯一训练台账。

## 10. 一个月范围

第 1 周只完成真实性、指标、因子机制和基线；第 2 周最多两轮终端对齐/成本实验；第 3 周完成开发消融、untouched 确认和外部可比实验；第 4 周完成机制图、复现包和预印本。短 rollout、RLOO、355M、完整 CTMC、湿实验均非默认关键路径。

一个月的目标是得到**可证伪、可复核、达到门槛才宣称竞争力的完整结果**。若学习模型持续失败，按时交付严格负结果和可复现 benchmark，而不是用不可比数字包装成功。
