# CodonFlow Tasks（A8 · 一个月证据驱动执行版）

> 生效日期：2026-11-18。与 `交接文档/spec.md` 的 A8-G0–G5 对应。
> 原 A7 G2 已正式 No-Go；T3.7/T3.8 均已完成，不再有“正在执行90分片”的状态。外部实际预算重评也已完成 54/54，但不是排名。
> 当前唯一允许推进的是 **Phase 0–2 的真实性、指标和反馈匹配机制任务**。A8-G1 未通过前，禁止启动新预训练、D5 untouched、短 rollout、RLOO、扩参或 SOTA 写作。

## 0. 已完成并可继承的工作

- [x] D4/D5 数据、清洗、来源、独立 calibration、unique18 与 untouched 24 资产已建立；D5 只称操作性同源簇隔离。
- [x] FULL/EDIT r5 已收敛并通过非退化 G1；checkpoint 和 SHA256 已冻结。
- [x] A7 G2 324/324 完成并 No-Go：FULL/EDIT 中位相对 AUC −94.28%/−93.47%，18/18 基因全负，Holm p=1.0。
- [x] T3.7 三开发基因 learned-hill 诊断完成；正向但高成本，只形成假设。
- [x] T3.8 其余15开发基因 90/90 完成：FULL/EDIT 中位 AUC +59.95%/+68.73%，耗时比 42.68×/2.41×；FULL 15/15 基因 NED≥70%，EDIT 14/15；不是独立确认，两臂均不满足时间要求。
- [x] LinearDesign/GEMORNA/codonGPT/CAI-greedy/uniform 的 unique18 实际输出已按 A7 目标重评，54/54 完成；缺失预算与输入差异仍限制排名。
- [x] 2026-11-18 远端源码、checkpoint、G2/T3.8 hash 复核；权威回归 228 passed、1 skipped。
- [x] G2 AUC 敏感性复算完成：FULL/EDIT −94.58%/−93.61%，仍 18/18 全负；证据 `audits/20261118/g2_metric_sensitivity.json`。
- [x] 2026-11-18 全量数据独立复核：D4/D5 数量、唯一 CDS/蛋白和 split SHA一致；精确 CDS/蛋白/ID 跨 split 重叠均为0，D5 unmapped=0、cluster 跨 split 重叠=0。证据 `审计与交接_20261117/results/data_split_independent_20261118.json`。
- [x] 已识别核心新风险：终端反馈混杂、训练—终端目标错位、时间条件缺失、天然 CDS 初始化后不再输入、合法概率质量未测、sparse AUC 与外部缺失预算口径问题、本地—远端源码漂移。

## Phase 0：仓库、数据和实验真实性审计（P0，Day 0–2）

**阶段目标**：建立不可争议的代码、数据、模型、指标和实验基线。

**核心问题**：当前结果是否由同一版本、同一目标和同一预算语义产生，哪些“独立复算”其实只复用了已存目标向量？

### P0-01 冻结权威版本与源码漂移清单

- **任务**：记录远端 commit/status/diff、Python/CUDA/ViennaRNA、GPU、关键文件 SHA；对本地镜像只写 drift 报告，不用 `reset --hard` 或覆盖继承修改。建立新的干净执行工作树/分支后再改代码。
- **涉及模块**：`/home/codonflow`、本地 `codonflow-main/`、`src/codonflow/models/synonymous_markov.py`、`scripts/a7_run_learned.py`、`src/codonflow/models/simple_search.py`。
- **前置依赖**：无。
- **输出物**：`audits/20261118/source_drift.md`、`environment_manifest.json`、权威工作树路径与 hash。
- **验收标准**：每个科学文件能映射到唯一 commit+SHA；远端工作树保持干净；本地继承修改未被删除；pytest 可复跑。
- **风险**：把本地旧文件误当当前实现，或为“清理”而覆盖用户工作。
- **失败处理**：停止实验，只保留只读审计并显式标记无法统一的文件。

### P0-02 全量数据与泄漏独立复核（本轮已完成）

- **任务**：独立读取 D4/D5 六个 FASTA，复算记录数、唯一 CDS/蛋白、split SHA、长度/GC/非 ATG、跨 split 精确 CDS/蛋白/ID 重叠；D5 另从 `homology_cluster.tsv` 复算 cluster 重叠和 unmapped。
- **涉及模块**：`splits_v4_protein/`、`homology_v5/splits/`、`homology_cluster.tsv`、`a7_build_confirmation.py`。
- **前置依赖**：P0-01 环境确认。
- **输出物**：`audits/20261118/data_split_independent.json`。
- **验收标准**：D4/D5 数量与冻结值一致；所有精确重叠和 D5 cluster 交叉为0，或每个非零项都有原始 ID 和修正记录。
- **风险**：ID 解析不一致、cluster 映射遗漏、把精确去重误称同源隔离。
- **失败处理**：隔离受影响 split/benchmark，撤回相关实验，重建划分后才训练。

### P0-03 原始序列级 scorer 独立审计

- **任务**：分层抽取 G2 与 T3.8 的原始序列，使用独立脚本重新计算 CAI、MFE、GC、motif/codon、identity、唯一解数；与已存 objectives 对比。不能只读 objectives 再称全 scorer 复算。
- **涉及模块**：新增 `scripts/a8_audit_raw_scorers.py`；参考 `scripts/a7_recompute_unique18.py`、`scripts/a7_g2_gate.py`、`scripts/a7_proposal_in_loop_gate.py`。
- **前置依赖**：P0-01/02。
- **输出物**：逐点差异表、异常序列清单、`raw_scorer_audit.json`。
- **验收标准**：预注册覆盖至少 3 个长度/GC 层×3 seeds×相关方法；CAI/GC/motif 在数值容差内一致，MFE 记录 ViennaRNA 版本和容差；所有差异可解释。- **风险**：使用同一 helper 造成“假独立”、长序列 MFE 成本、RNAfold 版本漂移。
- **失败处理**：暂停所有结论；定位 scorer/存储/schema，受影响结果重算并保留旧版。

### P0-04 补齐训练台账与证据索引

- **任务**：将 FULL/EDIT r5、G2、T3.7/T3.8、外部重评和失败/恢复记录补入 `experiments/REGISTRY.md`；建立 artifact→run→claim 映射。
- **涉及模块**：`experiments/REGISTRY.md`、handover journal、`audits/`。
- **前置依赖**：P0-01。
- **输出物**：实时 registry、训练曲线/配置/命令/hash 链接。
- **验收标准**：每次训练有启动配置、best/last/convergence、成本、结果、结论和不可声称事项；无只写 running 的过期行。
- **风险**：从二手文档补错数字。
- **失败处理**：字段标 `unknown` 并链接原始 artifact，禁止猜值。

## Phase 1：可靠基线与统一评价协议（P0，Day 1–4）

**阶段目标**：消除指标和预算假象，建立公平、可复用的评价器。

**核心问题**：在真实初始点、完整预算轨迹和实际输出集合下，结论是否仍成立？

### P0-05 实现 `dense_budget_step_auc_v2`

- **任务**：保留旧 `anytime_curve` 为 legacy v1；新增真实 B=1 起始、每唯一 scorer 点累积 HV 的 budget-step AUC；保留 B=50/100/500 Pareto/best；v1/v2 并列重算 G2/T3.8。
- **涉及模块**：`src/codonflow/eval/anytime.py`、`scripts/a7_g2_gate.py`、`scripts/a7_proposal_in_loop_gate.py`、`tests/test_anytime.py`、相应 Gate 测试。
- **前置依赖**：P0-01；原始点 hash 通过。
- **输出物**：新函数、测试、`g2_auc_v1_v2_comparison.json`。
- **验收标准**：手算合成阶梯面积一致；B=1 非零初始 HV 被保留；无 `(0,0)` 假点；重复/乱序点拒绝或按合同处理；旧 Gate hash 不变。
- **风险**：事后换指标选择性报喜、重复 scorer 点被误计、退化参考域。
- **失败处理**：v2 仅作敏感性，主实验暂停至口径重新预注册。

### P0-06 修正外部实际输出语义

- **任务**：将 `actual_budget_auc` 标记为 legacy diagnostic；无真实顺序轨迹时不输出统一 AUC 排名；缺失预算为 `null`；主表使用实际集合 Pareto、best-at-actual-budget、输出数和真实/未知成本。
- **涉及模块**：`scripts/a7_recompute_external.py`、`tests/test_a7_recompute_external.py`、`configs/a7_baseline_resources.json`。
- **前置依赖**：P0-05。
- **输出物**：54/54 新 schema 重评、`external_actual_set_summary.json`。
- **验收标准**：cai-greedy 1解、LinearDesign少量解等不被隐式补到500；codonGPT架构排除显式；无 missing-budget=0 进入主表。
- **风险**：把外部无序输出误当轨迹、A6生成时间与A7端到端时间混比。
- **失败处理**：只列资源与定性边界，不给数值排名。

### P0-07 统一内部简单搜索与时间预算

- **任务**：冻结 uniform-global、random-open-loop、random-hill、MH、AReUReDi-style 的操作符和反馈；单 worker 重新测时间子集；区分质量运行与成本运行。
- **涉及模块**：`src/codonflow/models/simple_search.py`、`scripts/a7_run_simple_search.py`、`configs/a7_protocol.json`。
- **前置依赖**：P0-05。
- **输出物**：方法矩阵、单 worker 成本基线、baseline manifest。
- **验收标准**：相同 initial/scorer/calibration；forward/cache-before/unique scorer/wall-clock 完整；同硬件重复成本记录。
- **风险**：高并发时间误导、全局 uniform 与局部 open-loop 混为同一因子。
- **失败处理**：只报告等 scorer 质量，不写实用速度结论。

## Phase 2：验证核心科学假设（P0，Day 3–7）

**阶段目标**：判断学习提议是否有独立价值，及其收益来自提议还是反馈。

**核心问题**：控制终端反馈后，learned 是否仍优于 random？训练分数是否与终端改进相关？

### P0-08 提议机制诊断，不训练

- **任务**：测量合法同义 token 概率质量、blank/stay、位置覆盖、实际编辑率、候选 model score 与 Δutility/接受收益相关、路径 log-prob 梯度和数值有限性；比较天然源与 protein-only 在相同随机初始后的信息等价性。
- **涉及模块**：新增 `scripts/a8_diagnose_proposal.py`；`edit_flow.py`、`synonymous_markov.py`、`corrupt_x_t_synonymous`、`a7_run_learned.py`。
- **前置依赖**：P0-01/05。
- **输出物**：逐基因/逐位置 JSON、散点/分位图、梯度 smoke。
- **验收标准**：合法概率质量在[0,1]且有分母审计；配对候选和相同 current state；相关分析不只报均值；路径 log-prob `requires_grad=True` 且梯度有限。
- **风险**：把相关当因果、只看开发阳性基因、随机初始化混淆天然条件。
- **失败处理**：若无目标信号，禁止直接终端微调；先检查训练/掩码/数据或转负结果。

### P0-09 预注册并执行 2×2 因子对照

- **任务**：`proposal={random,learned} × feedback={off,on}`，FULL/EDIT；用确定性长度/GC 分层规则在看结果前选6个 unique18 开发基因，seeds0/1/2，B=500。主对比 learned-on vs random-on，off 与交互解释机制。
- **涉及模块**：新增 `scripts/a8_run_factorial.py`、`scripts/a8_factorial_gate.py`、对应 tests；复用 `SimpleSearch(proposal_fn=...)` 与 learned proposal。
- **前置依赖**：P0-03/05/07/08，协议和 run ID 冻结。
- **输出物**：每分片原始结果、paired hash、factorial gate、v1/v2、成本表。
- **验收标准**：144个因子单元（72个新open-loop分片 + 72个经等价性审计后复用或重算的feedback-on分片）全部 done；identity/legal=100%；500唯一scorer；反馈语义代码审查；独立原始点重算；基因级 CI 与逐基因方向完整。
- **风险**：复用不等价旧分片、FULL 成本过高、选择阳性基因、NED 被当质量替代。
- **失败处理**：若 learned-on 无稳定正效应，停止新训练；若只在 off/on 一格有效，结论限制在该机制，不写普遍学习优势。

### P0-10 代理效度最小核查

- **任务**：整理公开同义变体表达/稳定性数据，核查 CDS-only、宿主、UTR、检测协议；评估 CAI/MFE/GC/motif 在控制蛋白、长度、UTR和宿主后的增量关联。
- **涉及模块**：新增 `docs/plans/2026-11-18-proxy-validity.md` 与分析脚本；不修改模型。
- **前置依赖**：可靠公开数据与许可；不得用当前 benchmark 输出替代真实测量。
- **输出物**：效度报告、可比/不可比数据清单。
- **验收标准**：数据来源和样本单位可追溯；相关/增量模型及混杂控制明确；无功能数据时明确“材料不足”。
- **风险**：把跨 UTR/宿主差异当同义效应。
- **失败处理**：若无增量效度，论文只称算法代理优化，撤销广泛生物价值主张。

**Phase 2 Go/No-Go**：只有 P0-08/09 支持 learned-on 的独立提议价值，才进入 Phase 3。P0-10 可与机制实验并行，但决定论文能否使用生物学叙事。

## Phase 3：模型与解码迭代（P1，Day 6–14；最多两轮）

**阶段目标**：在不扩参的前提下解决已测目标错位和成本瓶颈。

**核心问题**：终端对齐与成本感知是否带来超出 frozen r5 learned-hill 的新增能力？

### P1-11 终端对齐轻量微调

- **任务**：从 D4/D5 train 而非 unique18 生成 random-hill accepted/rejected 候选轨迹；以合法同义 masked CE、位置/替换目标及候选 Δutility 排序构成终端对齐损失；先 head-only/低秩适配，再决定是否需要全量微调。加入目标权重、剩余预算/时间步条件时必须有同名消融。
- **涉及模块**：新增 `a8_build_search_trajectories.py`、`a8_terminal_finetune.py`；`run_pretrain.py`、`edit_flow.py`、新配置。
- **前置依赖**：A8-G1、trajectory train/val 划分、registry。
- **输出物**：训练曲线、trajectory hash、checkpoint、配置、开发小门结果。
- **验收标准**：同骨干、同初始、同反馈、同预算优于 random-hill；相对 frozen r5 learned-hill 有独立消融收益；合法率和数值稳定100%。
- **风险**：模仿 hill 而无泛化、目标权重过拟合、训练分布与搜索分布不一致。
- **失败处理**：第一轮失败允许一次损失/数据修正；第二轮仍失败即停止学习模型主线。

### P1-12 成本感知块提议与解码

- **任务**：仅在 P1-11 有质量信号后，比较单密码子与2–4密码子块提议、top-k候选、早停和批量推理；所有操作保持同义，成本全计。
- **涉及模块**：`synonymous_markov.py`、`simple_search.py`、新 decoder 与测试。
- **前置依赖**：P1-11 小型阳性。
- **输出物**：质量—scorer—时间前沿和单/块消融。
- **验收标准**：等 scorer 质量不劣于预注册非劣界，time-matched HV 改善且 CI 下界>0。
- **风险**：组合相关错误、近似剪枝隐藏 scorer、长序列显存。
- **失败处理**：回退最佳单密码子 learned-hill，不保留复杂 decoder。

### P2-13 真正时间/目标条件离散流（可选）

- **任务**：仅当时间齐次核被证明是剩余瓶颈时，加入时间/目标条件并定义一致 rate objective；同参数比较。
- **涉及模块**：`edit_flow.py`、训练与采样核、理论说明。
- **前置依赖**：P1-11/12 明确诊断。
- **输出物**：最小实现、数学定义、time/CTMC消融。
- **验收标准**：相对时间齐次同参模型有预注册质量—成本收益。
- **风险**：理论/实现不一致、优化不稳、一个月范围膨胀。
- **失败处理**：放弃“离散流”主命名，保留诚实的 Markov editor。

## Phase 4：SOTA对比、消融与泛化（P1，Day 12–21）

**阶段目标**：在开发、独立和外部边界上验证最终冻结方案。

**核心问题**：结果是否超过强基线，而不是只超过旧 CodonFlow？

- **任务**：18开发基因完整比较；终端损失、目标条件、时间条件、块提议、合法mask逐项消融；通过 A8-G2 后训练D5最终模型并只一次评估 untouched24；LinearDesign等按实际任务/输入/输出/时间对比。
- **涉及模块**：Phase1评价器、Phase3最终checkpoint、外部baseline工具。
- **前置依赖**：A8-G2、最终配置和统计分析计划在 untouched 前冻结。
- **输出物**：主表、逐基因表、消融表、长度/GC分层、外部实际集合表、失败区域。
- **验收标准**：spec A8-G2/G3/G4 全部满足；确认集不参与任何选择；第三方不可比项显式。
- **风险**：外部预算/输入不公平、 untouched 反复使用、只选有利分层。
- **失败处理**：不写SOTA；报告边界或转负结果/benchmark。

## Phase 5：机制分析、科学发现与论文叙事（P1，Day 18–25）

**阶段目标**：解释何时、为何学习提议有效或无效。

**核心问题**：是否存在超出单一benchmark的可推广认识？

- **任务**：完成2×2交互、accepted-move质量、位置/密码子偏好、目标权重敏感性、长度/GC/预算分层、成本来源和代理效度；将机制图与主结果一一对应。
- **涉及模块**：审计与分析脚本、论文工作稿。
- **前置依赖**：Phase4原始结果冻结。
- **输出物**：机制图、失败模式图、主张—证据矩阵、Discussion边界。
- **验收标准**：每个机制主张有对照/消融；无“蛋白一致性是创新”“代理等于功能”“开发等于独立”。
- **风险**：事后编故事、相关当因果。
- **失败处理**：删除机制因果措辞，仅保留描述性发现。

## Phase 6：复现、代码整理与投稿准备（P1，Day 23–30）

**阶段目标**：交付可重建的完整结果和与实际证据一致的预印本。

**核心问题**：第三方能否从干净环境重建每个表图并审计负结果？

- **任务**：清理新分支而非删除历史；环境锁、run registry、数据卡、模型卡、artifact hash、自动图表、从头 smoke；修正预印本 zero-budget、raw audit、warm-start和外部AUC旧表述。
- **涉及模块**：`paper/CodonFlow_preprint_A7.md`（版本升级时另存A8）、`docs/handover/`、`experiments/REGISTRY.md`、release脚本。
- **前置依赖**：最终Gate与代码冻结。
- **输出物**：预印本、复现包、最终交接、负结果附录。
- **验收标准**：干净环境安装/测试/smoke通过；每个数字可定位原始JSON；所有旧撤回内容无回流。
- **风险**：论文数字手抄、本地/远端再次漂移。
- **失败处理**：不提交，保留工作稿和缺口清单。

## P0 立即执行顺序与串并行

### 串行主干

1. **P0-01版本冻结** → 2. **P0-05/06指标与外部口径** → 3. **P0-03原始scorer审计** → 4. **P0-08机制诊断** → 5. **P0-09因子实验** → 6. **A8-G1裁决**。

### 可并行

- P0-02数据复核与P0-04台账可在P0-01后并行。
- P0-03原始scorer审计与P0-07单worker成本基线可在指标冻结后并行（CPU/GPU资源分开记录）。
- P0-08诊断与P0-10代理效度可并行，但因子实验启动前必须完成P0-08的合法性/梯度/协议检查。
- FULL与EDIT可分 worker；统计Gate必须等所有预注册分片齐备。

### 每项输入→输出与可信判据

| 顺序 | 输入 | 新增/修改文件 | 必须测试/实验 | 输出 | 可信判据 |
|---|---|---|---|---|---|
| P0-01 | 本地/远端源码与环境 | 仅审计报告，新干净工作树 | git diff、SHA、pytest、CUDA smoke | source/environment manifest | 无覆盖，版本唯一，测试通过 |
| P0-05 | 已存原始点、calibration | `anytime.py`、Gate与tests | 合成面积、B=1、乱序/重复、退化轴 | v1/v2对照JSON | 手算一致，旧hash不变 |
| P0-06 | 54份外部结果 | 外部重评脚本/schema/tests | 1解/少量解/100解/架构排除 | actual-set表 | 不补零、不伪造轨迹/成本 |
| P0-03 | 原始序列与已存目标 | 独立scorer审计脚本 | 分层逐点重算 | scorer差异表 | 容差、版本、异常全解释 |
| P0-08 | r5、开发初始状态、候选 | 机制诊断脚本/tests | legal mass、相关性、梯度、初始化等价 | 机制JSON/图 | 配对正确、梯度有限、非只报均值 |
| P0-09 | 冻结协议、r5、6开发基因 | 因子worker/Gate/tests | 2×2×2臂×6基因×3seeds | 原始分片+Gate | paired initial/反馈/预算/hash/独立复算一致 |
| P0-04 | 原始训练与实验artifact | registry | 字段链接抽查 | 实时台账 | 无过期running，无猜值 |

**P0期间禁止**：新预训练、读取 untouched24 结果、删除旧结果、将敏感性分析写成新Gate、把外部actual-budget诊断写成排名。
