# 密码子级离散流 mRNA 编辑器（CodonFlow-pCoMole）Spec

> 项目代号：**CodonFlow**（Feasibility-Gated Codon-level Discrete Flow mRNA Editor + Label-free Bi-Reward RLOO）
> 来源：《跨领域模型架构日报 2026-10-04》第四大点「今日最值得尝试的架构迁移方案」+ 第五大点行动建议
> 日期：2026-10-04 ｜ 作者角色：课题发起人（本人视角撰写，用于与导师汇报讨论）

---

## Why

**科学问题（一句话）**：在「保阅读框 + 保蛋白身份」的硬约束下，对全长 mRNA 的 CDS 做多目标同义优化（CAI / MFE / GC / motif 排除）时，现有三条路线全部存在结构性缺陷：AR + logit masking 造成「合法但平庸」的质量塌缩、MDM+后置搜索采样效率坍塌、软奖励 RL 无法保证 by-construction 的身份保持。**「约束进终端分布 + 偏好进过程 + 免标注循环一致性奖励」三件事的统一，在 mRNA 编辑上尚无公开工作（截至 2026-10-04 检索）。**

**两篇源论文已全文精读，迁移链条逐模块核实**：

| 模块 | 源论文机制（已核实） | mRNA CDS 同义编辑对应 |
|---|---|---|
| 硬约束进终端分布 | pCoMole 式(9)：G(x)=exp(β·ATC(x))·𝕀[x∈𝓕]，不可行终端零质量 | 阅读框同步 + 蛋白身份 + 终止密码子唯一 → 终端门控 |
| 多目标偏好倾斜 | pCoMole Doob-h 变换式(11)-(12)：u^G_t(y\|x)=u_t(y\|x)·h_t(y)/h_t(x)，命题 3.1 保证终端分布精确 | CAI / MFE / GC / motif 排除的 Tchebycheff 效用 |
| 调和函数近似 | pCoMole §3.3：C 个候选 × R 条短 rollout，log-domain logsumexp 稳定（附录 B） | 翻译/结构预测器作为 rollout 评分器 |
| 免标注 RL 配方 | GrammarRL Eq(4)-(8)：direct=长度归一化 log p(y\|x)，reverse=teacher-forcing 重建 log p(x\|y)，RLOO 组 N=3 采样+1 个 beam 混入，冻结正则 β=0.02，LoRA r=64 | direct=编辑似然，reverse=翻译产物循环一致性（密码子表硬翻译，确定性、免预测器噪声） |
| RLOO 组构造 | GrammarRL §3.2：LOO 优势 A⁽ⁱ⁾=r⁽ⁱ⁾−(1/N)Σ_{j≠i}r⁽ʲ⁾，beam 同权参与基线（非模仿目标） | 混入 LinearDesign/CAI-greedy 最优解作组内强对照 |

**关键核实补充**（本次精读新增，日报未载）：
1. pCoMole 代码已开源：https://huggingface.co/ChatterjeeLab/pCoMole（正文题注区 Code 链接）——基座可基于开源实现复用，复现可行性上调。
2. GrammarRL 消融确认「单奖励反噬」：WoS 1B direct-only −9.6 分、reverse-only −7.5 分低于基线；λ=0.5 等权是全设置唯一稳定配置 → 迁移时双奖励必须等权起步。
3. GrammarRL 的正则不是严格 KL 而是逐序列 log-likelihood 差线性惩罚（β=0.02）；策略梯度用**无约束概率**计算——这两个实现细节直接决定迁移代码的写法。
4. pCoMole 超参消融显示中间档预算即可（步数/候选数/rollout 数边际递减）：GFP 收缩用 10 步 × 50 候选 × 10 rollout，单序列 530s@50 步；Cas9 用 20 步 × 10 候选 × 5 rollout。mRNA CDS 同义编辑比蛋白收缩更简单（定长），成本预期更低。
5. 1/3 未胜 beam 的任务是 CoNLL（8B 上差 −7.0 分）：短序列、结构化抽取任务上训练期塑形不如推理期搜索——警示我们 CDS 任务（短、强结构）可能出现同样现象，需保留 beam/MCTS 对照组。

**与现有工作的差异化定位**（避免「工程组合」陷阱）：
- codonGPT（NAR 2025，gkaf1345）：约束在**解码期 logit masking**，RL 是 per-protein REINFORCE——非 by construction；
- mRNAutilus（arXiv 2605.31296）：约束在**搜索层 MCTG**——先生成后过滤的变体；
- ProMORNA（arXiv 2605.01513）：MO-GRPO 软奖励，无硬约束、无编辑形式——de novo 而非 source-relative；
- pCoMole（NeurIPS 2026）：方法在蛋白侧，无 mRNA/密码子任务，无免标注 RL（评分器全为预测器）；
- 本课题新增：①密码子级词表 + 阅读框同步编辑算子（64+特殊 token）②同义身份硬约束**原生进离散流终端分布**（首个）③翻译循环一致性作为 reverse reward（首个，确定性、免预测器）。

**发表潜力**：NeurIPS 2027 主会（方法 + 生物应用双轨）或 Nature Machine Intelligence（若湿实验闭环）；退档线 ICLR 2027 / Bioinformatics。pCoMole 被接收证明审稿人认可「离散流 + 硬约束 + Pareto」框架，本课题是该框架在 mRNA 侧的自然延伸 + 免标注 RL 的方法学增量，故事完整。

---

## What Changes

- **新建独立课题**（非现有 mRNAflow 项目的增量）：密码子级离散流 mRNA 编辑器 CodonFlow。
- 基座：Edit Flow（pCoMole 开源实现 / FlexFlow 谱系）改造为密码子级 token 化（64 密码子 + 起始/终止/区域标记）、阅读框同步编辑算子。
- 约束层：可行性门控终端分布（阅读框 + 蛋白身份 + 终止密码子唯一）+ 增广 Tchebycheff 多目标效用。
- RL 层：GrammarRL 式双自监督奖励 RLOO（direct=编辑似然 + reverse=翻译循环一致性）+ 冻结正则 + 组内混入经典优化器解。
- 评测层：合法率/身份保持率/CAI/MFE/GC/多样性(NED)/Pareto hypervolume + 跨家族 OOD 切分。
- 交付物：GitHub 仓库 + 3 MD 文档 + 学术汇报 PPT。
- **BREAKING**：不依赖现有 mRNAflow 的 MRL 路线结论（该线已收口为负结果）；仅复用其基础设施（A100 服务器、/mnt 纪律、训练日志模板）。

## Impact

- Affected specs: 无既有 spec 被修改（独立新课题）。
- Affected code: **独立新建** `codonflow` 仓库，远端 `git@github.com:Cunyu-Liu/codonflow.git`（独立 init，不 fork/不分支自 mRNA_editflow，零共享 git 历史）；仅以文件拷贝方式复用 mRNA_editflow 的指标实现（CAI/NED）与服务器基础设施模式（A100 / /mnt 纪律 / REGISTRY 模板）。
- 复用资产：A100 服务器（36.137.135.49，GPU 0-5 整卡）+ 既有密码子指标代码（CAI/MFE/NED 实现于 mRNA_editflow_repo/eval/metrics.py）+ 训练日志纪律模板。

---

## ADDED Requirements

### Requirement: R1 科学问题与假设

系统（研究方案）SHALL 以可证伪假设驱动：

**核心假设 H1**：把「蛋白身份 + 阅读框 + 密码子合法性」写进离散流的可行性门控终端分布（by construction），多目标偏好用 Doob-h 倾斜塑形，并用免标注双自监督奖励（direct=编辑似然 + reverse=翻译循环一致性）做 RLOO 微调，可以同时达到合法率 ≈100% 与 Pareto 质量（hypervolume）优于 logit masking 与后置搜索两条现有路线。

**子假设**：
- H1a（正交性）：约束（门控）与偏好（倾斜）可分离塑形——固定 ω 下扫描 β 验证；
- H1b（双奖励必要性）：单 direct 会模式塌缩（NED 崩）、单 reverse 退化为约束指示器——需要两者等权组合（GrammarRL 消融的迁移验证）；
- H1c（OOD 泛化）：跨蛋白家族切分下门控编辑器的合法率与身份保持不衰减（生成任务以输入为条件，预测器分布漂移是真实风险）；
- H1d（成本）：CDS 同义编辑因定长约束，rollout 成本低于 pCoMole 蛋白收缩（对标 530s/序列@50 步需显著优于）。

#### Scenario: 假设证伪路径清晰
- **WHEN** 任何一个停止条件触发（见 R6）
- **THEN** 记录证伪证据并按预注册口径归档，不做事后解释

### Requirement: R2 数据与任务定义

系统 SHALL 构建三层数据体系，全部满足「找全、清洗、分布可查」：

1. **预训练语料（Edit Flow 基座）**：
   - 主语料：GENCODE v47+ / RefSeq（人类蛋白编码转录本 CDS），密码子级 token 化；
   - 补充语料：Ensembl 多物种 CDS（codonGPT 用 338,417 条；mRNAutilus 用 14.2M 全长 mRNA）；
   - 目标规模：≥1M CDS（300 万为目标，分批构建）；
   - 清洗规则：去冗余（MMseqs2 0.8 聚类留代表）、去截短 CDS（无完整阅读框）、去内部终止密码子、长度过滤 [300nt, 6000nt]、家族感知切分（pCoMole Cas9 用簇级 80-10-10 防泄漏，同法）；
   - 分布审计：长度分布、GC 分布、CAI 分布、密码子 RSCU 分布四个维度出图入档。
2. **编辑任务基准（Bench）**：
   - eGFP（UniProt P42212 / 717nt）+ nanoLuc（~510nt）+ SpCas9（~4104nt，长序列 probe）+ 每家族再加 2-3 个代表性 CDS（跨家族 OOD 用）；
   - 评测指标：蛋白身份保持率（须 100%）、合法率（密码子/阅读框/终止密码子）、CAI（HPA 高 TPM 参考集）、MFE（RNAfold 2.6.4）、GC 区间、NED 多样性、Pareto hypervolume（4 目标：CAI/−ΔMFE/−|ΔGC|/编辑距离）。
3. **评分器层（rollout 评分）**：CAI 计算器（解耦预测器，无参数）、RNAfold 2.6.4、翻译一致性（确定性密码子表翻译，零参数）——三足评分器全为**无学习组件**，规避 mRNAflow 项目教训（「瓶颈在 critic 打分质量」负结果：评分器有噪声时引导失效）。

#### Scenario: 数据集找全与清洗可追溯
- **WHEN** 任何数据进入训练管线
- **THEN** 其来源 URL、下载日期、条数、清洗规则、哈希记录于 `data/README.md` 与 `experiments/REGISTRY.md`

#### Scenario: OOD 测评必须存在
- **WHEN** 主结果表报告
- **THEN** 必须含跨家族切分（MMseqs2 簇级去冗余后 family-disjoint split）结果，同表报告 in-family 与 cross-family 的 gap（generalization gap 指标）。

### Requirement: R3 方法创新点（对比现有工作）

系统 SHALL 实现三个明确的方法学增量（每个有对应消融验证其贡献）：

1. **密码子级编辑流（CodonFlow 主干）**：词表 64 密码子 + BOS/EOS/区域标记（67 token，codonGPT 同款词表规模）；编辑算子约束为「同义替换 + 密码子级 indel（仅同步阅读框位置）」——变长编辑但阅读框同步。区别于 FlexFlow 的通用替换矩阵（未捕获 mRNA 机制）。
2. **身份门控终端分布（首个 by-construction）**：G(x)=exp(β·ATC(x))·𝕀[翻译产物=x 的蛋白 ∧ 阅读框同步 ∧ 终止密码子唯一]，ATC 为 (CAI, −MFE, −|GC−target|, motif) 的增广 Tchebycheff。区别于 codonGPT 解码期 masking、mRNAutilus 搜索层。
3. **翻译循环一致性 reverse reward（首个）**：r_reverse = 1[Trans(y)=Trans(x)]（硬翻译比较，确定性）+ 可选 log p(Trans(x)|Trans(y)) 软项。区别于 GrammarRL 的文本重建（teacher-forcing）：同义任务天然成立且无模型噪声。区别于 ProMORNA 预测器奖励：免预测器依赖（换预测器不塌）。

#### Scenario: 每个创新点有对应消融
- **WHEN** 主实验表完成
- **THEN** 消融行必须覆盖：去门控（退化为均匀 Edit Flow + 后过滤）、去 Doob-h（均匀采样）、单 direct、单 reverse、碱基级 vs 密码子级 token 化。

### Requirement: R4 基线与公平对比

系统 SHALL 覆盖三条现有路线的基线（全量找齐）：

| 基线 | 路线 | 实现 |
|---|--- |---|
| AR + logit masking | codonGPT 路线 | 官方 HF checkpoint `naniltx/codonGPT`（SHA 固定）+ 同义 logit processor |
| 搜索式 | LinearDesign 路线 | 官方实现（grid-DP，人密码子表）+ mRNAutilus 式 MDM+MCTS（若代码可得，否则文档化说明） |
| 均匀 Edit Flow | pCoMole 内部对照 | 未倾斜基座（去门控去倾斜） |
| 经典优化器 | 强对照 | CAI-greedy（全用最常用密码子）+ LinearDesign 平衡解——同时混入 RLOO 组作强 rollout |

公平性：所有方法同解码预算（同候选数/同 rollout 数）对比；AR 基线给 10× 采样的变体；报告单序列推断成本。湿实验不在 MVE 范围内（后续扩展）。

#### Scenario: 基线数字可复核
- **WHEN** 主表报告基线
- **THEN** 每行附 checkpoint 版本/参数/种子数，且至少 3 seeds 均值±std。

### Requirement: R5 训练与推断超参数设计

系统 SHALL 预注册超参数搜索空间（防事后调参偏）：

**预训练（Edit Flow 基座）**——参照 pCoMole 附录 E.3 实测值：
- 模型：768 dim / 8 层 / 12 头（pCoMole 同款）或 355M 整（预算允许时两档都跑）；密码子级 embedding 可从头训（无需 ESM，密码子语义简单）；
- 优化：AdamW，lr=1e-5，wd=0.03，cosine 衰减至 1e-6，10 epoch warm-up；epoch 数按损失收敛曲线定（pCoMole UniRef_S 30 epochs 作参照）；
- 长度扰动初始化：|x₀|~U[(1−a)|x₁|,(1+a)|x₁|]，同义任务 a=0（定长）+ 少量 a=0.25 扩展到 UTR 编辑（Phase 2）。
**RLOO 微调**——参照 GrammarRL 附录 Table 5 实测值：
- LoRA r=64 / α=128 / dropout 0.05（全参微调备选：768 dim 模型全参可承受，两种都报告）；
- lr=3e-7~7e-7 扫描（GrammarRL 任务相关范围），AdamW，1000 步起步（收敛判据见 R6）；
- 组：N=3 采样 + 1 个 LinearDesign 解混入（B=3 beam 对应物）；温度 1.0；
- 奖励：r=(1−λ)·R_direct/σ_direct+λ·R_reverse/σ_reverse，λ=0.5 起步（GrammarRL 消融：等权是全设置唯一稳定配置），σ 用 100 个 held-out 输入的组内标准差平均校准；
- 冻结正则：β=0.02，逐序列 log-likelihood 差（非 KL，按 GrammarRL 原文实现）。
**推断（引导采样）**——参照 pCoMole 附录 H 实测值：
- 步数 10-30、候选数 C=10-30、rollout 数 R=5-10（pCoMole 消融：中间档即可）；GFP 收缩预算（10×50×10）作成本上限锚点。

#### Scenario: 超参可复现
- **WHEN** 任何训练运行
- **THEN** 完整超参（含随机种子、数据版本、代码 commit）写入 `experiments/REGISTRY.md`，可由命令行参数完整复原。

### Requirement: R6 训练与收敛纪律

系统 SHALL 满足以下不可协商的工程纪律（用户明确要求）：

1. **GPU 必须并行且占满显存**：所有训练任务用 DDP/数据并行填满 A100 0-5 整卡池（或明确记录单卡原因与显存利用率）；记录每卡显存占用与利用率（nvidia-smi 周期采样）；
2. **模型必须训练到收敛**：预训练以验证损失平台期（连续 3 个 epoch 验证损失相对下降 <0.1%）为收敛判据；RLOO 以奖励平台期判据；禁止中途截断宣布结果；非收敛训练只能作为诊断输出，不得进主表；
3. **详细记录每次训练**：`experiments/REGISTRY.md` 逐行登记（run_id、时间、GPU 配置、超参全量、数据版本 commit、最终指标、收敛判据触发点）；训练日志同步到仓库 `docs/training_journal/`；
4. **GitHub 提交仓库**：`codonflow` 仓库（Cunyu-Liu 名下），main 分支保护 + 每 task 一个 PR；负结果与最强基线永不删除；
5. **大文件不放 home**：产物（checkpoint/评测输出/语料）放 `/mnt/cunyuliu/codonflow/`，代码在 /home worktree + push，home 只留代码与文档；
6. **定时任务与监控**：训练心跳（每 30 分钟 GPU 状态 + 损失曲线）→ 巡检日志（复用 mRNAflow `mrna_week_monitor_202609.md` 模式）+ 异常告警（显存 OOM、NaN、进程死亡自动邮件/飞书通知）；
6b. **GPU 显存排队脚本（Q3 已拍板）**：`scripts/gpu_queue.py` 每分钟轮询 nvidia-smi（memory.used / memory.total / utilization.gpu）；任务队列 `queue/pending.json`（FIFO + 优先级，项含 run_id / cmd / 显存需求 / 预计时长）；判定「可用显存 ≥ 需求 + 4GB 安全余量 ∧ 利用率 <30%」即自动提交（tmux + nohup），状态回写 `queue/running.json`；异常退出自动回写并触发告警；多卡 DDP 任务按「连续 N 卡同时可用」判定；提交/完成/失败事件全部入 REGISTRY.md；
7. **停止条件（预注册）**：门控导致可行样本采样率 <1%（训练不收敛）→ 降约束优先级（身份/阅读框进解码器，GC/motif 进奖励）；阅读框破坏率 >5% → 停；换第二个 CAI/MFE 参考表后多目标提升消失 → 停；rollout 推断成本 >LinearDesign 5 倍且无质量补偿 → 停；NED 低于基线 70%（模式塌缩）→ 停。

#### Scenario: 纪律可审计
- **WHEN** 检查任何一次训练
- **THEN** REGISTRY.md 行存在、GPU 利用率曲线可查、checkpoint 在 /mnt、commit hash 可追溯。

### Requirement: R7 评测充分性

系统 SHALL 满足评测充分性标准：

1. **主表**：CodonFlow vs 4 基线 × ≥3 蛋白家族 × ≥3 seeds，指标 = 合法率 + 身份保持 + Pareto hypervolume + NED + 单序列成本；
2. **OOD 表**：跨家族切分（R2）下的同表，报告 generalization gap；
3. **消融表**：R3 三个创新点逐一去除的退化数字；
3b. **叙事-现象对应表**：论文主叙事的每一步推进，必须对应一张可指认「实验现象」的图表（对不上则叙事改写或实验补做），见下方「叙事-现象验证矩阵」；
4. **超参敏感性**：λ ∈ {0.25, 0.5, 0.75}、β ∈ {0.02, 0.1}、推断预算扫描（R5）；
5. **预注册与冻结**：以上表格结构、停止条件、成功标准在实验前写入本 spec 并冻结，修改走 amendment；
6. **成功标准（预注册）**：蛋白身份保持 100% 且合法率 >99%；Pareto hypervolume 相对 AR+logit masking 与搜索式基线均提升 ≥10%；NED 不低于基线 70%；OOD 切分下身份保持率与合法率衰减 <2 个百分点。

#### Scenario: 评测协议不可事后放宽
- **WHEN** 实验完成后
- **THEN** 按预注册口径出表；任何口径变化走 amendment 并在论文中披露。

### Requirement: R8 执行路线（三阶段）

Q2 固化决策：Phase 1-2 锁定定长同义（身份可精确判定）；Phase 3 起引入框同步变长算子，UTR 编辑仅作泛化叙事。
**Phase 1（MVE，第 1-2 周）**：密码子级 token 化 + 阅读框同步编辑算子 + AR+logit masking 基线跑通（eGFP/nanoLuc，四指标）→ 决策门 A：基线数字与预期量级一致？
**Phase 2（第 3-6 周）**：Edit Flow 基座预训练（1M CDS 起步）+ 门控终端分布 + Doob-h 引导采样 + 三足评分器 → 决策门 B：合法率 >99%？身份保持 100%？rollout 成本可承受？
**Phase 3（第 7-10 周）**：RLOO 双奖励微调 + 全量基线对比 + OOD 切分 + 消融 + 论文草稿 → 决策门 C：成功标准（R7）达成？
**叙事-现象验证矩阵（论文骨架，每行缺一不可）**：

| 论文叙事推进 | 必须出现的实验现象 | 否则 |
|---|---|---|
| ① 现有路线的分布截断/质量塌缩是真问题 | 对比图：AR+masking 在身份约束下 CAI 提升但 NED/多样性显著低于无约束基线（现象：合法但雷同） | 叙事降级为工程改进，换故事 |
| ② 门控让约束「免费」 | 门控 on/off 的合法率-质量散点：门控 on 合法率 100% 且 hypervolume 不降反升 | 检查 β 退火与候选扩容 |
| ③ 偏好倾斜真正导向 Pareto 前沿 | 偏好权重 ω 扫描图：不同 ω 下解簇沿前沿分布（现象：前端覆盖） | Doob-h 实现有误的信号 |
| ④ 双奖励互补（免标注有效） | 消融表：单 direct NED 塌 / 单 reverse 退化 / 等权稳定（复现 GrammarRL 消融形态） | 叙事核心塌，回炉 |
| ⑤ 门控+RL 组合优于搜索式方法 | 同预算对比表 + time-to-design 曲线 | 方法降格为 trade-off 报告 |
| ⑥ 成本可行 | rollout 预算-质量-耗时曲线（中间档性价比拐点） | 推断效率叙事删除 |

**详细实验设计（EXP-1 至 EXP-6，与矩阵逐行对应，预注册）**：

- **EXP-1 基线塌缩现象图（→ 叙事①）**
  - 数据：eGFP + nanoLuc CDS，每序列 1000 采样；三组对照 = AR 无约束采样 / AR+同义屏蔽（codonGPT 官方 ckpt）/ CAI-greedy（「雷同」上限锚点）
  - 指标：候选两两 NED 直方图、密码子选择熵（按氨基酸位平均）、唯一序列比例、CAI 分布
  - 统计：3 seeds；KS 检验 NED 分布位移（p<0.05 为显著）
  - 预期现象：屏蔽组 NED 分布显著左移、密码子熵显著低于无约束组（图型：三组直方图叠加）
  - 判读：若屏蔽组多样性不塌 → 叙事①撤回，问题动机降级为工程改进并如实报告
- **EXP-2 门控 vs 同预算后置过滤（→ 叙事②，最关键的公平对照）**
  - 设计：三组共享同一总 rollout 预算 B（默认 500 次评分调用/序列）：门控引导组（预算用于每步候选评估）/ 均匀生成+后置过滤组（按 G(x) 排序取 top，同预算全用于生成）/ 硬屏蔽组（对照锚）
  - 指标：可行解产出率（每千次采样中「合法 ∧ 身份保持」占比）、可行解 hypervolume、首达合格解时间（time-to-first-usable）
  - 统计：≥3 家族 × 3 seeds，Wilcoxon 配对检验
  - 预期现象：预算-质量三线图中，门控组在中低预算即达高可行率+高质量；过滤组随预算追赶缓慢或停滞
  - 判读：同预算下门控不优于过滤 → 「by construction 效率优势」断言撤回，退化为「质量不劣 + 合法率保证」弱化叙事
- **EXP-3 偏好扫描前沿图（→ 叙事③）**
  - 设计：三目标（CAI / MFE / GC）ω 取 7 方向（3 角点 + 4 边内点），每 ω 100 解；参考前沿 = 全方法解集非支配并集
  - 指标：目标空间散点（两个 2D 投影）、每组非支配率、前沿覆盖率
  - 预期现象：不同 ω 解簇沿前沿分段占据（角点 ω 落在极端 trade-off 区段）
  - 判读：解聚成一团 → β 过小或 Doob-h 实现有误，回炉；分散但离前沿远 → 基座容量不足，扩 355M 档重跑
- **EXP-4 双信号消融（→ 叙事④）**
  - 设计：{direct / reverse / 等权 λ=0.5 / 无 RL 纯引导} 4 组 + λ∈{0.25, 0.75} 补充行；rollout 由未门控策略采样（保证 reverse 信号有方差，消融有意义）；同步报告训练中策略合法率曲线
  - 指标：训练后贪心解码 hypervolume、NED、身份保持率（rollout 与贪心分别报告）、训练奖励曲线
  - 统计：3 seeds 均值±std
  - 预期现象：direct 柱质量高但 NED 塌、reverse 柱身份高但质量平、等权双高（复现 GrammarRL 反噬形态）
  - 判读：等权非双优 → λ 扫描重跑一次；仍非 → 如实报告与源论文形态的偏离
- **EXP-5 多目标+多样性锚定对比（→ 叙事⑤，主断言战场）**
  - 设计：五方法（CodonFlow / codonGPT 多目标采样 / LinearDesign 标量化权重扫描 / CAI-greedy / 均匀 Edit Flow）× 三场景（单目标 CAI / 双目标 CAI+MFE / 四目标 +GC+编辑距离）；LinearDesign 给同等 100 解预算（权重扫描实现多目标，公平）
  - 指标：每场景 hypervolume、非支配率矩阵（我方解不被各基线任何解支配的比例）、NED、单解平均耗时
  - 预注册断言：单目标场景允许输（DP 最优，如实报告）；双/四目标场景 hypervolume 与非支配率领先 ≥10%
  - 判读：不达 → 降级为 trade-off 报告（对应停止条件）
- **EXP-6 预算-质量-耗时曲线（→ 叙事⑥）**
  - 设计：预算网格 steps{10,20,30} × candidates{10,30} × rollouts{5,10}，每配置 50 解；同步记录显存占用
  - 指标：hypervolume vs 单序列耗时曲线族
  - 预期现象：存在中间档性价比拐点（与 pCoMole 附录 D 同形态）；质量饱和点耗时 < LinearDesign×5
  - 判读：超标 → 删除效率叙事（停止条件④）

**退出策略**：任一决策门失败 → 降级路线（门控约束改解码器硬保证 + 奖励只留 direct + 多目标软项，如实报告偏离）或转向 DeltaBench 式评测论文（负结果也归档）。**湿实验不做**（资源约束，纯 in silico 完成验证闭环）。

---

## MODIFIED Requirements

无（独立新课题，不修改既有 spec）。

## REMOVED Requirements

无。

---

## Amendment A1（2026-10-04，实现细节补齐）

**动机**：tasks.md 工程级细化时发现 spec R3-2 缺一个实现必需细节——ATC 效用的四目标量纲不可比（CAI∈[0.6,1]、MFE 数百 kcal/mol、GC 偏差小数、motif 罚分整数），直接进 Tchebycheff 会让 MFE 单轴支配 min 项。

**修改内容（补入 R3-2 / R5）**：
- 四目标 f=(CAI, −MFE, −|GC−0.55|, motif 罚分) 进 ATC 前**各自 min-max 归一化到 [0,1]**；
- 定标统计量：从 Task 1.2 基线解集计算各轴 5/95 分位数，冻结于 `configs/atc_norm.yaml`（评测期间不改，改动走 amendment）；
- ρ（增广系数）=0.01 起步；ω 默认 [1,1,1,0.5]（motif 减权——软目标）；β=1.0 起步（H1a 扫描 {0.5,1,2}）。

**不修改**：H1 假设、成功标准、停止条件、EXP-1~6 设计——归一化只影响实现，不改预注册口径。

---

## Amendment A3（2026-10-23 · 阶段性冻结与容量研究结果记录）

**背景**：主训练在原 A100 集群失联后迁移新集群（px2-jcy RTX4090）续跑；2026-10-23 用户指令冻结全部训练/评测。本条记录截至冻结点的容量研究结果与遗留事项，不改预注册口径。

**新增已证事实（全部有 JSON/日志在档）**：
1. v3-56M@862k **收敛**（val 2.8069，plateau 3/3）——R5 容量档第一个完整收敛点。
2. v3-355M@862k 冻结于 e16 76%：**e13 val 2.7921 已低于 56M 收敛值**（容量第三点在预训练侧成立）；converged.pt 未产出，恢复续训即可（见 tasks.md v4 恢复命令）。
3. HELD18 L2 层 v3 vs v2conv：S3 几何平均 **1.108**、S2 1.082、S1 0.976；长度分层 S3 long 1.156 / short 1.114 / mid 1.004；g02 mouse -47% 为唯一大退化（如实报告）；identity/legal 100%。
4. RLOO v3（v2conv 协议复刻）：35 iters 快速 plateau（对照 v2conv 111 iters），初步下游 6 arm 混合——RL 增益假说待 mouse/fly 臂裁决。

**遗留事项（下次恢复优先级）**：
- 355M 续训至真收敛 → converged.pt → 全量评测链（容量曲线下游终点）
- v3rloo 评测 9 arm 补全（8/17 冻结）
- Cas9 S3 motif ref 尺度 bug 修复（长度归一化 motif 罚，原 v3 待办）
- yeast g08 零域：沿用 §5.7 adaptive reference 口径剔除

**不修改**：H1/H2 假设、R6 停止条件、EXP 预注册、成功标准——容量研究结论按「如实报告」纪律进论文 §6。

---

## Amendment A4（2026-10-23 · 新集群恢复 + 冲刺期口径固化）

**背景**：项目迁移至新集群 px2-jcy（RTX 5090 32GB ×1，Ubuntu 20.04，16 核/64GB），环境重装。用户指令：一个月内产出可提交预印本的一版优秀结果。同步完成深度自检与故事线重构（见 REFLECTION_20261023.md）。

**新增固化事项**：

1. **评测口径升级（修复性，非放宽）**：S3 四目标 HV 的参考点从「固定校准域」升级为「per-gene adaptive reference」（各轴参考 = 全方法池化 min − 5% margin）。动机：固定域在 yeast/Cas9 上产生零域假象（§5.7 已证明是评估器问题而非解质量问题）。Cas9 motif 罚分同步做长度归一化（motif/n_codons）。**全部已有 JSON 的 obj_vectors 重算，不重新生成**（幂等、无采样方差引入）。此项走 amendment 而非静默修改，论文 §5.7 如实披露修复时间线。
2. **主断言降级备案（预执行，防事后解释）**：R7 成功标准中「S3 hypervolume 提升 ≥10% vs AR+masking 与搜索式」在 100-解预算下未达成（当前 0.22–0.53 几何平均比）。若 355M 容量档 + 预算扩展对照仍不达成，主断言按预注册降级路线改写为：「约束保证 + 双通道独立可控 + 同预算首达效率 + 长序列长度优势」的 trade-off 定位，绝对覆盖差距按三因素归因框架如实报告（协议差异已修 / 效用退化已修 / 基座容量未决→本冲刺裁决）。
3. **RLOO 增益的条件性结论（若 9+4 arm 裁决为负）**：改写为「RL 增益随基座预训练充分度衰减」的 scaling 洞察（215k 基座 +RL 显著 vs 862k 基座 +RL 边际消失），与容量曲线合并成「数据-容量-RL 三角」叙事，而非方法失败。
4. **环境变更记录**：新集群 conda codonflow 重建（py3.10 + torch 2.14.1+cu126，RTX 5090 sm_120 需 cu126 轮子）；watchdog v8 参数适配（free_mem 阈值 32607MiB、batch-tokens 按显存放大占满卡）；355M 续训从 last.pt(e15, md5 078b27fc) 起步。数据/权重 md5 三处对账一致（语料 d86366a0/f72b482b/23d567a1；56M converged c8072617）。

**不修改**：H1 假设本体、R6 工程纪律、E1-E6 实验设计、停止条件五条、单目标认输条款——A4 只固化「冲刺期新增对照的口径」与「降级预案的预注册」。

---

## Amendment A5（2026-10-25 · 355M 收敛事实固化 + 交接收官）

**背景**：2026-10-24/25 交接会话。A4 预注册的「355M 容量档裁决」的预训练侧已完成，评测链全面启动。本条固化新事实，不改预注册口径。

**新增已证事实（全部有日志/JSON 在档）**：

1. **v3-355M@862k 正式收敛**（2026-10-24 21:13）：21 epochs，val 2.7875，plateau 3/3 触发自动停止（e19 2.7904 / e20 2.7880 / e21 2.7875，连续三 epoch 相对下降 <0.1%）。converged.pt（945MB）+ converged.json + log.jsonl 21 epoch 全曲线在位。
   - 容量三点终值：215k-56M 2.8141 / 862k-56M 2.8069 / **862k-355M 2.7875**（355M 相对 56M -0.70%，相对 215k 基线 -0.95%）——**模型容量效应在预训练侧确证**（56M→355M 打开了 862k 语料的第二个损失台阶；对照 862k-56M vs 215k-56M 仅 -0.25%）。
   - 训练曲线全程：e16 2.7912（新最优）→ e17 2.8060（反弹）→ e18 2.7919 → e19 2.7904 → e20 2.7880 → e21 2.7875（plateau）。
2. **评测架构自动检测补丁**（patch_eval_arch.py）：run_exp3.py / run_exp5_ood.py 从 checkpoint 权重形状推断 d_model/n_layers/n_heads（768→12 heads / 1280→16 heads），移除 56M 硬编码。首跑 E3 nluc 因 `import re` 遗漏 NameError，已修复复跑成功（e3_v3_355m_nluc_retry.log）。
3. **9 链并行评测矩阵**（2026-10-25 起）：355M E5 15 臂（c0-c4）+ E3 2 臂 + HELD18 18 基因 + v3rloo 补全（mouse×3 + fly_s2）+ patrol_loop 常驻守护（30min journal+git）。全部幂等（JSON 已存在即跳过）。
4. **GPU 资源纪律执行情况**：RTX 5090 32GB 上 8-9 条评测链并行实测显存 12-14GB；瓶颈实测为 CPU（load 72-104，RNAfold ProcessPool 是主导）——继续加链边际收益为负（CPU 过载会拖慢所有链的 MFE 阶段），GPU 高占用密度以「当前 CPU 容量下的最大并行度」为限，特此记录（用户显存占满纪律在 CPU 密集阶段以最大有效并行度解释执行）。

**交接状态（本会话收官）**：
- 代码真相源 GitHub Cunyu-Liu/codonflow main（经本地 bundle 中继同步至 e494488+，集群 SSH key 失效后走本地代理推送通道）；
- 集群 patrol_loop.sh 每 30min 自动 journal + git commit（本地代理推送待 SSH key 恢复后一并上传，日志先落 /teams）；
- 预印本 §6 容量结论、fig10 第三点、RLOO 条件性裁决、PPT 更新——全部等 35 JSON 评测完成后一次性收口（W2.4a/W2.6/W2.7/W2.8）。

**不修改**：H1 假设、R6 停止条件、预注册成功标准、A4 降级备案（其触发条件「355M+预算扩展仍不达 S3 ≥10%」需等下游评测裁决）。
