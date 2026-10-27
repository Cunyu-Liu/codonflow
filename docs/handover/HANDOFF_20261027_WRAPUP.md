# CodonFlow 收尾交接（2026-10-27）

> 目的：按用户要求停止新增实验、结束当前任务，把已核验资产、真实问题、不能声称的结论和后续接手入口完整交给下一位。
> 当前不是预印本完成版，也不是主实验 Gate C 通过版。请从本文件的“未完成事项与验收标准”继续，不要从旧 SOTA/容量/RL 结论继续。

## 1. 当前停止状态

- 未启动的 full-data RLOO 队列 `a6_rloo_queue` 已取消，未产生训练结果；不再新增实验。
- edited-token 与 full-token 两臂均在 epoch 7 进行中停止，使用已完整落盘的 epoch 6 checkpoint 收尾。退出码 143 是主动停止，不是崩溃；两臂均未达到独立验证 plateau。
- 旧 `run_exp5_ood.py` legacy 评测、unique18 baseline、`a6_watch` 与 `patrol_v2` 均已停止。停止后无 tmux 会话和剩余科学计算进程。
- unique18 仅完成 10/18 条完整记录；C05E11.2.1 是部分运行记录，另外 7 条未启动。不得称其为完整 unique18 benchmark。
- 不再为了占满显存制造工作。当前 GPU 空闲是用户要求项目收尾的直接结果。

## 2. 已核验、可复用的资产

### 2.1 代码、回归与发布

- 本地和 RTX 5090 集群均为 **98 passed, 1 skipped**。
- 有限步同义 Markov 实现支持：合法源 CDS、单密码子同义编辑、位置/密码子联合归一化、显式 stay、基础核路径概率、短 rollout 和候选剪枝 Doob 近似。
- 精确小状态后向递推已验证；大状态空间只支持 Monte Carlo/候选剪枝近似，不能写成完整 CTMC 或精确大空间终端分布。
- 合法性来自合法源和同义操作符，即 **by-operator feasibility**，不能全部归因于终端门控。
- GitHub 草稿 PR：<https://github.com/Cunyu-Liu/codonflow/pull/1>。git receive-pack 失败时改用 GitHub API 创建分支和提交；每次同步均逐文件比较 blob SHA。API 提交不等于本地逐提交历史，后续仍需正常 Git 对齐。

### 2.2 数据与 benchmark

- v4 exact-protein + nucleotide-cluster split：776,474 条，train/val/test=621,306/76,444/78,724；所有 split 间和 split 与 benchmark 的精确 CDS/蛋白重叠为 0。
- v5 protein-homology-cluster：776,441 条，train/val/test=618,073/80,191/78,177；85,671 个精确蛋白重复、128 条 benchmark 连通簇排除。MMseqs2 0.5 identity、双向 0.8 coverage；20 个 benchmark 簇均不进入 split，独立 cluster/leakage/守恒审计通过。
- v5 只是操作定义的同源簇隔离，不是 curated family 或 species OOD；val 长度偏移需要在下游结果中披露。
- 当前 unique18 来自冻结 v4 test：18 个唯一 ID/CDS/蛋白，13 short/2 mid/3 long，SHA256=`30e3dbbfc3480287b1f87177fe476d7ca283219f08949476da6d08555d0ab4e0`。它不是 HELD18 去重版，也没有可靠物种映射。

### 2.3 三臂机制与成本协议

- canonical artifact：`eval_outputs/a6_pilot/a6_three_arm_protocol_smoke_v4.json`。
- 固定输入：冻结 epoch-5 edited-token checkpoint，SHA256=`74a542c165f0a1ebe425d78b012fd7f2c64c228f5cd8ddcc0f7f13370f26f5e2`；代码 merge=`2854ebb68a6070f0d8ca3200aedf0bec32ef681a`。
- 2 条 paired paths，T=4、C=4、R=2、seed=0；base/immediate/short-rollout 的 identity 均为 1.0。
- forward=8/8/76；终端请求=2/42/74；唯一 scorer=2/11/66；short-rollout 有 64 条轨迹、68 次批量 rollout forward、136 次逐轨迹状态转移。
- 恒定 C、T 且 R>0 时：首 guided step=`1+T+C(T-1)`，整路径 `F=T+T(T+1)/2+C*T(T-1)/2`。T=4,C=4 时为 17/38，与 R 无关；实际 trace 优先于公式。
- v3 将每步累计 scorer 请求再次求和，旧 102/194 已作废。v4 只聚合每条路径最终累计行，并区分请求、实际 scorer invocations 和唯一 scorer。
- 该实验只验证协议，不能证明收敛模型、short-rollout 或 immediate 的普遍优劣。

### 2.4 Baseline 与图表

- core seed-0 五方法已完整独立复核，identity 均为 1.0：LD 6/6、codonGPT 100/100、GEMORNA 74/72、uniform 100/100、CAI-greedy 1/1（eGFP/nanoLuc）。无随机补样。
- unique18 收尾时完成 10 条：C31E10.3b.1、C14A6.7.1、C01H6.8b.1、ENSACAT00000027077.3、ENSACAT00000025296.3、C07E3.9.1、ENSACAT00000037188.1、ENSACAT00000011420.3、ENSACAT00000044901.1、C47A4.1.1。
- 这 10 条的身份、解数、输入哈希、CAI/GC/motif 和有限值均复核一致，无 architectural exclusion、无错误记录。审计文件：`eval_outputs/a6_baselines/unique18_s0/wrapup_independent_audit.json`。
- 收尾审计没有重新计算全部 NED/MFE，只检查其有限性；若用于主表，仍需完整独立 MFE/NED 复核。
- 已验收图：`fig_a6_data_audit`、`fig_a6_split_distributions`、`fig_a6_baseline_objectives`、`fig_a6_mechanism_costs`，均有 PDF+PNG。
- PPT 已更新为 43 页。第 40 页明确“已收尾、未收敛”，第 43 页为机制/成本；原 PPT 与交付副本哈希一致，新增页布局/重叠检查、markitdown 和 LibreOffice 中文渲染通过。

## 3. 当前项目的真实问题与反思

### 3.1 科学主线尚未闭环

1. 当前最扎实的是数据审计、测量协议和 baseline，而不是“学习模型已优于现有方法”。
2. 没有收敛的新模型、完整多基因多种子对照和联合统计结果，无法证明预训练、short-rollout 或 RLOO 带来下游收益。
3. 因此不能提交预印本，不能写 SOTA、capacity scaling、RL scaling 或 masking 因果结论。旧正文 `CodonFlow_preprint_draft.md` 仍是 LEGACY DRAFT — DO NOT SUBMIT。
4. 正确主线仍是：测量定义→有限步机制→学习与泛化→方法边界。目前只完成前两段的大部分基础设施，后两段证据不足。

### 3.2 训练与学习证据不足

1. 两臂都在 epoch 6 主动停止，未 plateau。edited-token 最优 val=4.385477；full-token 最优 val=2.819537。目标不同，不能直接比较 val 大小。
2. 既有 full-parameter path-RLOO 仅 2 个训练源、2 个评估源、20 次更新；校准效用变化 -6.9167e-05，梯度仍裁剪。它既不能证明收益，也不能证明算法无效。
3. full-data RLOO 已取消，尚未解决足量训练源、奖励方差、独立 held-out 增益和收敛判据问题。
4. 旧 RLOO、旧 35/111-iteration 曲线与当前 base-kernel on-policy path-RLOO 不共享算法语义，不能拼接成统一故事。

### 3.3 Benchmark、baseline 与统计不完整

1. unique18 只有 10 条完整结果，1 条部分结果、7 条未启动；seed 1/2 未做，CodonFlow 收敛臂未加入。
2. 没有完整方法池的联合 HV、置信区间、Wilcoxon/配对统计和统一预算下的多基因三臂比较。
3. 各方法真实唯一解数不同，不能伪称等输出预算。官方 LD/GEMORNA forward 不可见，必须记 `null`；共享 GPU 时间不是隔离硬件基准。
4. codonGPT 有上下文长度限制；长序列需显式 architectural exclusion，不能把缺失方法当零分或静默删除。
5. 旧 time-to-first、steps×candidates 和累计行重复求和都不能作为效率证据。新的四成本口径必须保留：输出解数、唯一 scorer、模型 forward、端到端时间，并保留请求/实际调用细分。

### 3.4 数据与 OOD 仍有缺口

1. v5 只有划分和泄漏审计，没有新训练与下游泛化结果，不能声称 protein-homology OOD 已证明。
2. 缺少 curated family/species 元数据和相应独立评价，unique18 的人工长度分层、较短和低 GC 组成也不能代表自然总体。
3. 长度/GC 已有全量分布，CAI/RSCU/密码子使用分布与更多质量分层仍未形成同等完整的审计。
4. 所有目标目前都是计算代理（CAI/MFE/GC/motif），没有湿实验、表达量或真实稳定性验证。

### 3.5 机制与工程边界

1. MC-Doob 的短 rollout 与候选剪枝会引入近似偏差和较高成本；尚未形成质量—预算前沿，也没有证明近似终端分布。
2. live `best.pt` 会在训练中更新，已造成两次输出哈希不同。正式对照必须使用冻结 checkpoint；旧 artifact 若无可变路径和不可变哈希，需重新审查。
3. `code_commit` 不能单独证明工作树干净。后续结果 schema 应增加 `code_dirty`，并保留 immutable checkpoint 路径和 SHA256。
4. 本地、集群和 GitHub 目前包含 merge/API 提交，内容已按 blob 核验，但历史并不完全一致；应在网络恢复后正常 fetch/push 对齐，不强推。
5. MMseqs 临时索引尚未清理；正式 artifacts 在 teams，home 只保留代码和小型工具。

## 4. 未完成事项与建议验收顺序

### P0：先恢复并结束两臂训练

- 从各自的 `handoff_epoch006_training_state.pt` 精确恢复 optimizer/RNG，继续到独立验证 plateau；不得从 model-only 权重冒充精确恢复。
- 每轮保存 best/last/training_state，冻结实际用于评测的 checkpoint 和哈希。
- edited-token manifest：`checkpoints/a6_v4_56m_r2/handoff_epoch006_manifest.json`。
- full-token manifest：`checkpoints/a6_v4_56m_fulltoken/handoff_epoch006_manifest.json`。
- 两个 manifest 均包含完整 6 epoch 历史、best/last/training_state 路径与 SHA256。

### P1：完成 baseline，而不是先做新模型宣传

- 用 `--resume` 完成 unique18 seed-0 的剩余 8 条，再按同一协议运行 seeds 1/2。
- 保留 C05E11.2.1 的部分记录，不删除失败/部分状态；恢复时核对 benchmark/source/RSCU 哈希。
- 对全部 18 条重新执行身份、解数、目标向量和成本审计；主表若使用 MFE/NED，补做全量独立复核。

### P2：在收敛模型上完成真正的科学对照

- base/immediate/short-rollout 使用同一冻结 checkpoint、paired 初始状态、多个基因和至少 3 seeds。
- 同时报告输出解数、唯一 scorer、forward、端到端时间，以及 rollout 轨迹/批量 forward；不能只做 2 路径 HV。
- 完整方法池使用唯一目标向量构建联合参考域，补置信区间和配对统计；缺失方法和 architectural exclusion 显式列出。

### P3：回答学习与 OOD，而不是包装负结果

- full-data path-RLOO 只有在收敛基座、足量训练源和独立校准/测试上才可启动；以 smoothed reward plateau 和 held-out 增益共同判断，不再用 2 源 20 步下结论。
- 用 v5 新划分训练并做 downstream generalization；在取得 curated 注释前，不写 family/species OOD。
- 保留负结果和弱项，不把“没有收益证据”改写成“已证明无效”，也不把“工程可运行”改写成“方法有效”。

### P4：最后再写论文和主图

- 只有 P0–P3 的核心证据成立后，才重写预印本正文、学习/泛化/主结果图和 Gate C。
- 旧量化页继续标为历史探索；主文不得混入旧 HELD18、错误 nanoLuc、随机补足 LD、旧 RLOO 或可变 checkpoint 结果。
- 图表必须继续由冻结数据源自动生成，标题不得超出数据支持的结论。

## 5. 接手时的禁止事项

- 不把当前状态称为预印本可提交版、完整 unique18、收敛模型、SOTA 或 Gate C 通过。
- 不比较 edited-token 与 full-token 的 val 数值大小来得出架构优劣。
- 不使用 live `best.pt` 做跨时间对照，不把不同 epoch 输出当同一模型复现。
- 不把 2 源/20 步 RLOO 负差值、2 路径 pilot 或旧 exploratory JSON 当成普遍结论。
- 不把 v5 写成 curated family/species OOD，不把计算代理指标写成湿实验表达证据。
- 不随机补足 baseline，不把共享 baseline 重复计入联合参考域，不把缺失方法静默删除。

## 6. 权威位置与恢复入口

- 集群代码：`/home/codonflow`。
- 数据/权重/artifacts：`/teams/HoulabData_1788502323/liucunyu/codonflow`。
- 本地开发镜像：`/tmp/codonflow-dev`。
- 本交接同时保存在仓库 `docs/handover/HANDOFF_20261027_WRAPUP.md` 和用户交接目录。
- 原 PPT：`/Users/liucunyu/Documents/课题idea 数据 结论/浙江大学/RNA 相关模型/CodonFlow-密码子级离散流mRNA编辑器/CodonFlow-中期汇报-20261009.pptx`。
- 交付目录：`/Users/liucunyu/Documents/all_code/ZJU/mRNA_editflow/temp_20261026_02`。
- 回归命令：`cd /home/codonflow && PYTHONPATH=src /root/miniconda3/envs/codonflow/bin/python -m pytest -q`。
- unique18 恢复：在 `/home/codonflow` 运行原 `scripts/run_a6_baselines.py` 命令并添加 `--resume`，输出仍写 `eval_outputs/a6_baselines/unique18_s0`；不要新建另一套数据目录。
- 两臂恢复：使用各自 `handoff_epoch006_training_state.pt` 作为 `--resume` 输入，沿用原数据、输出目录和超参数；`--token-only-at-edits` 仅用于 edited-token 臂。
