# CodonFlow Spec（A10 · Kinetic-CodonFlow 当前执行合同）

> 生效日期：2026-11-23。唯一执行入口为 `交接文档/PROMPT_NEXT_AGENT_A10_KINETIC.md`；本文将其落实为科学、数据、评价与 Gate 合同，`交接文档/tasks.md` 负责执行分解。
> A7–A9 的 spec、Gate、artifact 和负结果均为不可变历史证据，不得追改或用新命名翻案。A9 的 `generator_training_authorized=true` 只是权限，不是立即训练指令，更不是模型有效证据。
> 2026-11-23 上一轮文档任务中的“仅更新执行文档、禁止训练、禁止修改 `codonflow-main/`”仅为该次任务的 scoped 历史限制，不是后续授权的永久禁令；当前训练与代码工作仍须遵循本合同的科学 Gate、真实 CUDA、独立复核和 owner 明确授权。禁止读取 untouched24、MAGE functional untouched 及其派生文件的冻结约束不变。

## 0. 权威状态、证据等级与当前边界

### 0.1 已核实的当前事实

- A10-03/E2 权威 release 工作树为 `/home/codonflow-a10-e2-release`，2026-11-26 v12 复核时代码 HEAD 与 GitHub `a8-rk` 均为 `40603527afa3ee2275166b4293234cdd48a9e38c`，工作树干净；其父提交为 v11 的 `0fc413efe04506b85f847d162c9fa1fc5121e31e`。v13 启动及单次只读检查时 release HEAD 与 GitHub `a8-rk` 均为文档提交 `f7e3fdbb7684befe947a12b06de56744defbdb96`，工作树干净，`40603527…` 是其直接代码祖先；本轮之后仅允许新的文档提交改变 HEAD。大型资产仍位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/`。不再沿用 A10-00/A10-01、integrate 或 v11 阶段的旧 HEAD 作为当前代码版本。
- RTX 5090 上 CUDA 真 matmul 已通过，环境为 torch 2.14.1+cu132；这只证明计算后端可用，不证明任何科学模型有效。
- 旧 A7 PID `2071716` 为暂停状态，不重启。未启动新生成器训练，未读取 untouched24 或 MAGE functional untouched。
- RK42 的准确含义是 **0/9 个候选同时满足旧统一 R1–R7**，不是“没有可任务化的数据”。A10 按科学主张分别判定数据资格，但不降低起始结构运输或独立验证标准。
- Goodman2013 官方 construct-level CSV 已取得：raw SHA `a03071027b8c0008d07fb7737de0a7d51765c6cff25bc86e93465a6253c7c33a`，共 14234 行、75 列、137 Gene、4817 exact CDS、280 条 leader、33 nt N 端片段和 8439 条 SetGood。clean SHA 为 `ce64f2caa9633fefae840e220d36b6360946d39b9253adc56f3ef297b9ab9c82`；v3 report SHA 为 `3036961a32502c1ea7a9bf6cd45f2ffbb0cadf2d18ff8f3405b4abd4bb1a6304`，独立复核 31/31，SHA 为 `c78359d03a45f3bbbcc867f36be8b2c74219a9410c543a90d08e8784a6bf42ab`。
- Goodman 已冻结 5 outer×4 inner 的 Gene-grouped nested CV：assignment SHA `e2d8b31bf6a5aee6f104c96ea484340b6d10654bc35494c36fa4a89a31e6a129`，split SHA `f49c93af8e2a30616d6f0e907f75dd8a08e29e5fe23e303484c120feb57683c2`，独立复核 25/25，SHA `379ef698d8f0029d929468c94bcdf594bd83384e957fcc31e4e66d46b4fc2f43`。这只支持 **Gene-grouped N 端片段构建 OOD**，不称 protein OOD。
- Goodman constant、CAI、GC、dG、tAI、Ridge、HistGB 7 臂 nested 5×4 **开发 baseline** 已完成：8439 SetGood rows、59073 prediction rows（7 臂×5 折），独立复核 32/32；wall-clock 370.0619 s，HistGB 85 fits 均为 52–264 iterations、0 次触及 500 上限。prediction/report/独立复核 SHA 与逐 outer 均值的 Spearman/RMSE/top-1 全表见 `交接文档/HANDOFF_A10_01_E0_20261123.md`。该结果不替代其余 T1 方法，不作机制、SOTA、protein OOD 或真实生物泛化结论。
- Tunney 候选审计已完成：5894 transcripts、2920075 codon rows；report SHA `9fecfb838762950b2545f6db4fb0d6ba4ab92cc9483aad20c33cd1f0d8abf9b9`，clean SHA `238d9997f6449763bed69a4ba806b74ea0f77b95ee526cb6dff61fe9ce1b7a6e`，独立复核 24/24。合并 lane 不是独立重复；加权采用 A-site/RSEM。
- Lareau `GSE58321` 已出现于 RK03/RK05，不再称未读候选，也不得冒充最终研究 OOD。
- EnsembleDesign 官方 quick v2 已成功 6/6，且 3 条输出匹配 README；ID3 两条 CPC 轨迹缺陷保留。CodonTransformer 固定官方源码与模型 revision 后已在 RTX 5090 完成 1 deterministic＋2 stochastic 真实输出，333 nt/110 aa 翻译一致，独立复核通过；这只证明可运行，不证明可比性能或 SOTA。G0 时 A10 全部定向测试为 251 passed；E1、E2 初始数值基础分别登记 33、36 tests，均不替代科学 Gate。
- **E0 与 A10-G0 已完成**：裁决为 `A10_G0=PASS_DATA_AND_BASELINE_READY`。G0 closeout v3 SHA 为 `93928d6b6c2599d7e18e59896863f4b3bea91b3e034f64538631d395711ac8cc`；独立复核 SHA 为 `1c6a3b1e211998f7a79959eca68af3a03c92d94548b31eefcc7e62a0ebe1ebd3`，20/20 通过；closeout 生产与独立复核测试合计 45 passed，G0 时 A10 全部定向测试 251 passed。
- **E1/A10-02 已完成，H1 获开发集阳性判决**：E1 v2 summary SHA 为 `2902e678f93815ccd7731720d940700ae84a88b7e8d5ee3dba8f3a833e6bef5d`，独立复核 SHA 为 `cf5ebfcb450363722e7b49e2e8cf720f883778ddebea3a01b80a2a8cb35c0539`，全量检查通过；wall-clock 51.8138 s，33 tests。raw_unanchored−calibrated 的 TB-MSE effects 为 0.0420274/0.0418212/0.0406288，raw_anchored−calibrated 为 0.0403316/0.0402787/0.0390835；全部 CI lower>0、Holm<0.05、3 seeds 同向。
- E1 校准斜率为 0.1580–0.1644、截距为 0.8224–0.8308；Pearson/Spearman 不变。该判决只支持开发研究中的 TB-MSE 观察校准改善，不是最终跨研究结论，不把 occupancy 称为绝对速率，也不构成 SOTA。
- **A10-03/E2 v7 已于 2026-11-24 fail-closed 退出，恢复工作在进行**：真实 CUDA 运行中 batch sample 10 normalized residual 为 `8.842e-06 > 1e-10`，未满足既定稳态阈值。v7 无 `summary.json` 或 `predictions.npz`，不能称训练完成；没有完整 outer 预测，H2/G1 未裁决且未通过。最小平均场数值基础已独立复核；真实 CUDA 审计 SHA 为 `3cd3add70d9d05a47e9f6662867da0faf620586685d6d9092b96b1c975d471fd`。五组独立 least_squares 复核的最大密度误差为 1.33e-14、最大梯度误差为 1.16e-14、独立守恒误差为 3.94e-14；这些工程检查不抵消 v7 运行时失败。平均场不是精确随机模拟。
- **E2 v8 已 fail-closed 退出（历史失败保留）**：权威工作树为 `/home/codonflow-a10-e2-v8`，HEAD `287c02569e7af325da8578fd5973d9c98f681562`。实现为 sparse normalized-residual Newton＋scaled Newton＋LSODA/Newton polishing，所有返回仍严格检查 normalized residual `1e-10`；64 项定向检查、全项目 889 passed/1 skipped/5 subtests、真实训练快照、历史失败输入、长度 2–4096 及 CUDA 前后向通过仅为运行前工程证据。2026-11-26 只读复核确认 v8 在已有 **36/486 条曲线**时于 backward batch sample 13 以 residual **`2.944e-08 > 1e-10`** fail-closed，退出码为 **1**。产物仅见 `curves.jsonl`、`provenance.json`、`splits.json`，无 `summary.json` 或 `predictions.npz`，没有 outer/H2/G1 结果；v8 目录不可覆盖。历史整合工作树 `/home/codonflow-a10-e2-integrate` 曾保留全部预期 dirty 修改，全量测试实测 **910 passed、1 skipped、5 subtests passed，6126.13 s**；当时尚未 commit/push，HEAD 与远端 `a8-rk` 均为 `287c025…`。该记录是发布前历史，当前 release 状态见下条。这些工程检查不抵消 v7/v8 失败，也不证明 H2/G1。
- **mean-field 精确 CTMC 对照验证已完成 scoped 数值复核**：独立工作树 `/home/codonflow-a10-e2-validation` 有四个未跟踪的验证/复核代码与测试文件，产物在 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/a10/e2/mean_field_validation_v1`。859 个 L1–L6 小状态精确 CTMC 案例零数值检查失败，`independent_review_v2.json` 为 `passed=true`；log-uniform random 组密度最大绝对误差中位数 0.0223736651、最大值 0.3391923462，最大通量相对误差 0.3198444691。密度单独观测保留一个共同时间尺度零空间；加入绝对通量后局部满秩，但条件数可很差、实际可辨识性仍可很弱。该验证仅覆盖合成小状态，不是精确随机模拟，不证明平均场生物有效性、长转录本近似、H2 或 G1。
- **E2 release 工程验收已完成，但生产科学运行未完成**：历史 release 集成为 `79dcbf377b043e21f45573428128d236c9534685`；v11 前 `/home/codonflow-a10-e2-release` HEAD 曾为 `6075ad5381800c84e99b4f4a277b26b6594a7fbf`，当时核对工作树干净。相关 **144 tests** 通过；synthetic 1/2/4-worker 的 predictions/states/metrics/science records 逐位一致，每份独立 verifier **27/27 checks** 通过；**859** 个合成小状态精确 CTMC cases 及独立 review 通过。集成 manifest 为 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/a10/e2/kinetic_release_integration_v1/integration_manifest.json`。这些仅是 scoped 工程与数值证据，不是完整 outer 科学结果。
- **v10 27 workers、w23 与 w21 均因 CUDA 内存失败保留**：v10 以 `CUBLAS_STATUS_ALLOC_FAILED` 失败，w23/w21 以 CUDA OOM 失败，均退出 1、0 shard、0 曲线且无完成摘要。w21 已有 26 份 worker OOM failure；最后活跃 worker `3989620` 经身份复核后 SIGTERM 退出，parent/launcher 自行结束，未 KILL、未触碰其他 PID。失败快照与退出证据在 `kinetic_release_integration_v1/w21_oom_closeout_20261126_v1/`。性能探针 `performance_probe_v1/` 实测约 94.8% forward 时间用于 CPU Newton，padded dense backward 为 `O(BL^3)` 且出现单次约 593 MB 分配；结构化求解修复已在 `/home/codonflow-a10-e2-structured` 完成工程验收，本地 `b6012ac50b30110636505a26aa716f5d59af6e11` 未 push；146 项定向测试、65–1521-codon 真实 CUDA 前后向、独立残差/梯度与方向回归通过，protocol、Gate 与 `1e-10` 阈值不变，科学运行仍未完成。**H2/G1 未裁决且未通过**。
- **v11/v12 均未形成科学运行**：v11 使用 `0fc413efe04506b85f847d162c9fa1fc5121e31e`、16 workers，早期无即时 OOM 的快照保留，但最终于 2026-11-26 18:20:37+08:00 因 CUDA OOM 退出 1，0 完成 shard、0 曲线且无完成摘要。独立审查另发现 shard cache identity 缺少 `src/codonflow/models/kinetic_banded_cuda.py` SHA，属于生产 provenance 阻断，不是科学失败；只读复核时 v11 两指定 PID 均已退出，因此不得虚写为本轮主动中止。修复提交 `40603527afa3ee2275166b4293234cdd48a9e38c` 已推送，统一 parent/worker/cache/failure/summary 的 backend identity；定向 151 tests、提交后并行 12 tests 和真实 RTX 5090 CUDA/cache 复核通过，protocol SHA `3c4b9a3b…`、Gate 与 `1e-10` 不变。v12 使用该提交和 16 workers 真实启动，但于 18:37:17+08:00 以 `CUBLAS_STATUS_ALLOC_FAILED` 退出 1，0 shard、0 曲线、无完成摘要；其 startup provenance 已包含正确 backend SHA `c2c70271d1a94055173926973db5c689d6fbbb08f20fc5d6c8026ac971704aa3`。两次运行均为工程/资源失败，**H2/G1 未裁决且未通过**。
- **v13 共享显存审计与 6-worker 启动已登记，科学运行仍未完成**：启动前 2026-11-26 18:53:38+08:00，RTX 5090 总显存 32607 MiB、已用 13189 MiB、空闲 18923 MiB；PID `3996745`（7034 MiB）属于 `/root/rareseq/work` 的 `e5_rbp_holdout.py`/ProxyFunctionGap，PID `4045601`（6138 MiB）属于 `/home/cunyuliu/rna-ft-eval` 的 `rnafteval.finetune_base`，均非 CodonFlow，未停止或信号操作。按完整命令行扫描未见 v11/v12 runner 或 spawn worker 残留。以预留 12 GiB（12288 MiB）为约束，6 并发预算为 `(18923-12288)/6=1105.8 MiB/并发`，总预算 6635 MiB。v13 使用启动时 HEAD `f7e3fdbb…`、`--device cuda:0 --max-workers 6`；2026-11-26 18:55:35+08:00 唯一一次启动后只读快照中，主 PID `4057023` 加 6 个 worker GPU PID，CodonFlow 进程合计 5468 MiB，整卡已用 18694 MiB、空闲 13417 MiB，仍高于预留量。当时仅有 `provenance.json`（SHA `350a515bb7a621c54693fe53f1109082221cc3decd11f597b8a5d9a11a8b23b9`）和 `splits.json`，0 曲线、0 cache NPZ、无 `summary.json`/`predictions.npz`、无退出码；日志保留 numerical recovery 期间的 invalid/overflow RuntimeWarning，不能据此宣称收敛、完成或科学成功。protocol SHA `3c4b9a3b…`、backend SHA `c2c70271…`、Gate 与 `1e-10` 不变，**H2/G1 未裁决且未通过**。
- E3/G2 未证，G3 未通过；`final_untouched=false`、`SOTA=false`。大规模生成训练仍须 G2；E1 开发阳性、E2 数值测试或 G0 均不构成最终跨研究、机制、功能、设计 SOTA 或真实生物功能结论。完整恢复交接见 `交接文档/HANDOFF_A10_03_E2_RECOVERY_20261125.md`。

### 0.2 不可变历史证据，不是 A10 结果

- A7 G2：FULL/EDIT 相对每基因最强简单搜索的中位 AUC 改善为 −94.28%/−93.47%，18/18 基因均负；只支持旧 open-loop 设计失败，不支持新动力学或新生成器结论。
- RK39–RK41 的实际集合设计任务仍未解决；历史外部 actual-set 输出不能自动变成完整 anytime 排名。
- RK37 相对 constant 的 TB-MSE 改善为 −0.755、mean Pearson 改善为 −0.033，支持跨研究 raw occupancy 简单运输失败；occupancy 仍只是实验依赖的相对占据/速度代理。
- RK23/RK25/RK28/RK30/RK31 等历史结果表明静态起始结构信号跨蛋白、宿主或研究运输失败。静态结构不再是既定核心。
- 权威历史引用包括远端 `docs/handover/HANDOFF_A8_RK37_20261122.md`、`docs/handover/HANDOFF_A9_RK42_20261122.md`、`experiments/REGISTRY.md` 的 RK21–RK42，以及本地只读镜像中的 `codonflow-main/docs/handover/DECISION_A9_20261122.md`。本地镜像缺项不得猜写。

### 0.3 当前实现不能被误述为科学证据

- `EditFlowTransformer` 只读 codon ID，没有蛋白、UTR、宿主、功能或时间条件；`SynonymousJumpProposal._transition_tensors` 直接丢弃 `time`。
- `edit_flow_loss` 是同义腐蚀 denoising CE/BCE，不是完整 CTMC rate objective，也不监督真实功能。
- `RiboKineticModel` 的 pair channel 是合法互补碱基计数形成的 attention bias；initiation/velocity/decay 是线性位置头，再加权汇聚到功能头。它不是结构系综、核糖体动力学或已验证机制模型。
- `MinimalCodonFlowRK` 是合法单编辑枚举＋能量 softmax 的 smoke，不是训练完成的生成器，没有轨迹平衡或生产级离散流证据。

### 0.4 事实与计划必须分离

每项记录必须标为：**仓库/数据事实、历史实验事实、合理假设、待新增证据**。代码存在、测试通过、训练收敛、Gate 数、hash、文档或 PPT 页数均不得替代核心性能。任何假设不成立，就删除相应主张和模块，不得改名后继续当核心。

## 1. 核心科学问题与可证伪假设

### 1.1 核心问题

> **固定宿主与构建上下文中，局部同义替换是否通过延伸速率场和核糖体流守恒产生可迁移的非局部功能效应；将潜在动力学与 assay 观察过程分离，能否提高 transcript/protein/study OOD 功能预测，并进一步改善同义序列设计的质量—成本前沿？**

需要检验的是：流守恒是否解释独立密码子模型遗漏的非局部信息；分离研究特异观察映射后潜在动力学是否比 raw occupancy 更可迁移；被证实的量能否转化为超过强 baseline 的预测和设计性能。目标不是证明 TASEP、Transformer、CTMC 或 GFlowNet 等已有概念本身。

没有 decay 数据就不添加 decay 头；没有多位点覆盖就不虚构远程 pair 机制。静态结构只能作为起始率候选输入，只有在相同输入、参数和训练预算下显示独立 OOD 增量才保留。

### 1.2 H1–H4

| ID | 可证伪假设 | 失败后的强制处理 |
|---|---|---|
| A10-H1 观察可分性 | 研究特异观察映射能解释相当一部分 raw occupancy 跨研究失配；校准只用 source train 或独立 target calibration，不读 target test outcome | 校准后仍不优于简单模型，则不写跨研究动力学；可在研究内继续 E2，但不得外推 |
| A10-H2 流守恒增量 | 同容量去流守恒模型无法达到相同的转录本/变体 OOD 表现；局部编辑上下游响应与动力学预测一致 | 无独立增量即删除动力学核心并停止 Kinetic-CodonFlow 主线，不靠加模块救场 |
| A10-H3 功能增量 | 潜在通量与密度对真实功能有超出 CAI/GC/MFE、位置场和通用序列模型的独立信息 | E3 未达到预注册门槛则不接生成器，继续诊断数据和目标 |
| A10-H4 设计增量 | 同一动力学目标导出的设计器在等反馈、等 scorer、等时间下超过最强可比方法；预测与设计消融方向一致 | 未赢最强可比方法即未解决；若直接 simplex 梯度设计更强，如实保留其为强 baseline |

## 2. Kinetic-CodonFlow 模型合同

### 2.1 先求最小生物隐状态

对序列 `x`、宿主 `h` 和可用上下文 `u`，模型只输出严格为正的起始率 `αθ(x,u,h)`、逐位延伸率 `kθ,i(x,u,h)` 和终止率 `βθ(x,u,h)`。用可微排斥晶格模型或经验证的平均场近似求稳态；最小平均场为：

`J_i = k_i ρ_i(1-ρ_{i+1})`，稳态要求 `J_i=J`，边界由 `α`、`β` 给定。

先完成最小模型，再按数据需要扩展全长足印、多核糖体尺度和数值残差。必须记录稳态残差、参数可辨识性和近似误差；平均场输出不得冒称精确随机模拟。

### 2.2 观察过程单独建模

对每个 Ribo-seq 研究 `s`：`y_s,i = g_s(ρ_i) + ε_s,i`。`g_s` 从单调或低自由度仿射映射开始；覆盖、检出限、重复噪声和缺失机制进入 `ε_s`。禁止高自由度 calibration 吞掉生物信号。映射只能在 source train 或独立 target calibration 上拟合，target test 只做最终评估。

功能层仅在测量支持时加入 mRNA 丰度 `A`、通量 `J` 等，例如 `E=f(A,J,…)`。所有 occupancy 表述都必须保留实验依赖与相对代理边界，不称绝对物理速率。

### 2.3 容量与归纳偏置

小型卷积、状态空间模型或局部上下文编码器只能参数化速率，不列为创新。容量随数据量受控，并与独立密码子、位置场、同参数量无守恒模型公平比较。默认禁止加入 MoE、大 ESM、完整 pair transformer、RLOO 或扩参。

### 2.4 只有通过科学 Gate 才接生成器

同义状态图为 `x=(c1,…,cL)`，`ci∈C(ai)`；蛋白、长度和 stop 由状态空间保证。候选可逆核为：

`rθ(x→y)=r0(x→y) exp[(Fθ(y)-Fθ(x))/(2τ)]`，并精确归一化。

若 `r0` 相对 `π0` 可逆，目标为 `π(x)∝π0(x)exp(Fθ(x)/τ)`。`Fθ` 只能包含已验证的功能/动力学项和明确约束。必须在可枚举小状态验证合法率、归一化、详细平衡/平稳分布、采样一致、单/多步一致和成本。若实现只是 denoising 或局部搜索，就不称 CTMC/flow。

## 3. 数据资格、当前角色与 E0 审计

### 3.1 任务化数据资格

| 任务 | 必要数据条件 | 可以接受 | 不能声称 |
|---|---|---|---|
| 构建内/N 端功能预测 | 变体序列、连续结局、明确构建与批次 | Goodman 式 33 nt N 端同义窗＋明确 leader/构建背景 | 全长 CDS、天然 UTR 或 protein OOD 泛化 |
| 起始结构运输 | 精确变体特异 UTR–ATG–CDS | 可重建精确起始窗的数据 | 借固定 leader 数据证明该机制 |
| 翻译动力学 | P-site/密码子映射、覆盖、重复、研究元数据 | 天然转录本 Ribo-seq，无需固定蛋白同义库 | occupancy=绝对速度 |
| 同义设计 | 固定蛋白、合法同义空间、明确目标与成本 | 公开蛋白和计算 benchmark | 代理优化=真实功能提升 |
| 真实功能验证 | 未参与选择的真实变体与独立测量 | 回顾性独立验证或前瞻 DBTL | 同一 scorer 自评即生物验证 |

旧 RK36/RK42 判定不改写；R1–R7 不再作为所有任务的统一门槛。

### 3.2 当前数据角色

- **Goodman2013**：官方 construct-level raw 已取得并完成 v3 审计；数据为 33 nt N 端片段、280 条 leader，包含 8439 条 SetGood。仅用于限定构建几何的功能 benchmark；已冻结的 5 outer×4 inner Gene-grouped nested CV 只支持 **Gene-grouped N 端片段构建 OOD**，不支持全长 CDS、天然 UTR 或 protein OOD 泛化。constant/CAI/GC/dG/tAI/Ridge/HistGB 7 臂开发 baseline 已完成，独立复核 32/32；只作为开发 baseline，不构成机制、SOTA 或真实生物泛化证据。完整 SHA、逐 outer 指标、成本与独立复核结果见第 0.1 节和 A10-01 handoff。
- **Tunney**：候选审计已完成，包含 5894 transcripts 和 2920075 codon rows，独立复核 24/24；合并 lane 只能作为非独立重复，加权使用 A-site/RSEM。该完成项不等于最终未读研究 OOD 已建立。
- **Lareau GSE58321**：已出现于 RK03/RK05，属于已观察资料，不再称未读 Ribo 候选，不得作为最终研究 OOD。
- **Kudla154**：固定 GFP 开发数据；已有结构结局不能重新冒充独立验证。
- **Boël6348**：ordinal、天然跨蛋白非同义变体；只作匹配测量性质的辅助任务/对照，不冒充连续同义功能库。
- **Cambray2018**：96 bp N 端片段且氨基酸变化；只作非固定蛋白辅助研究，不能进入固定蛋白同义主表。
- **Mordstein**：已观察的匹配上下文辅助证据，不是 untouched。
- **Mohammad/Subtelny Ribo**：均已观察，只作开发；最终研究 OOD 必须另找未读研究。
- **iCodon**：源对齐失败，禁止使用。
- **MAGE functional untouched 19072 行**：继续冻结，除非 owner 另行明确授权；不得通过派生文件间接读取。
- **untouched24**：继续冻结，最终协议冻结且授权明确后一次使用。

### 3.3 E0 必须交付的数据审计

1. **来源**：accession/release/URL/license/下载时间/raw-clean SHA/处理谱系；论文样本数不等于已拥有数据。
2. **序列 QC**：长度整除 3、合法 alphabet、终端/内部 stop、翻译与蛋白一致、起始/部分 CDS、重复与合成错误。
3. **构建 QC**：蛋白、完整或片段 CDS、5′/3′UTR、leader、载体、宿主、启动子、化学修饰、assay、batch、replicate、单位、检出限、缺失原因。
4. **Ribo QC**：read coverage、P-site 偏移、密码子映射、重复一致性、零覆盖、footprint 长度与研究批次；保留原始计数，不只留归一化值。
5. **分布**：长度、GC/CAI、密码子/氨基酸组成、变体位置、每蛋白/研究样本量、功能动态范围、重复噪声、覆盖与长尾；检查短序列、优势物种和大 assay 主导。
6. **泄漏**：exact CDS/protein/ID、同源簇、同一变体、重复测量、功能来源蛋白、研究批次和第三方预训练重叠。RSCU、归一化、校准和特征选择只由 train 拟合。
7. **划分**：功能按蛋白/family/研究分组；Ribo 按转录本和研究分组；同蛋白变体不得随机跨 split。开发、校准和最终 untouched 分开。

无法获得的字段标缺失并限制结论，不静默填补，不删除低表达或失败变体。

## 4. 三个主任务与强 baseline

### T1 构建内及 OOD 功能预测

- **主指标**：Spearman、RMSE、top-k enrichment；蛋白/family/研究为独立单位。
- **必须比较**：constant、CAI/GC、局部/全局 MFE、位置场、Ridge/HistGB、Boël 作者模型（适用时）、通用序列模型及可复现直接竞争方法。
- **顺序**：先构建内/转录本 OOD，再蛋白/family/研究 OOD；不得把构建内相关外推为普遍功能提升。

当前 scoped 状态：Goodman constant/CAI/GC/dG/tAI/Ridge/HistGB 7 臂 nested 5×4 开发 baseline 已完成；这仅关闭该开发子项，局部/全局 MFE、位置场、Boël 作者模型、通用序列模型及可复现直接竞争方法仍须核实和运行，完整 T1 主表尚未建立。

### T2 翻译占据与动力学预测

- **主指标**：transcript-balanced MSE、mean per-transcript Pearson/Spearman、密度响应和校准；不得随机拆 codon 行。
- **必须比较**：constant、位置场、Ridge、RiboMIMO、iXnos、ROSE、VeloGRU/VeloBERT、VeloHARMO（适用时）。
- **顺序**：先研究内 transcript OOD，再做有独立 calibration 的研究 OOD；未读研究在协议冻结前不得读取结局。

### T3 固定蛋白同义设计

- **主指标**：dense budget-step HV AUC、实际 Pareto/best、NED、合法率和 time-matched 表现；代理设计与真实功能验证分表。
- **必须比较**：LinearDesign、EnsembleDesign、ID3、RNARL、CodonTransformer、COformer、VeloHARMO、内部 hill/MH/SA/GA/random/r5；按任务核验 CAGFN、codonGPT、GEMORNA。
- **公平性**：等初始、反馈、目标、 scorer、预算和硬件；无真实轨迹的方法只比较 actual set，缺失为 null，不补零。

Harmonization、全长 UTR–CDS 联合设计和起始结构运输只在对应数据与机制通过后增加，不与三个主任务同时铺开。

### 4.1 外部方法资产审计

CodonTransformer（`10.1038/s41467-025-58588-7`）、COformer（`10.1016/j.omtn.2026.102991`）、VeloHARMO（`10.1093/bib/bbag558`）、RNARL（`10.1186/s13059-026-04203-x`）、ID3（`10.1093/bioinformatics/btag667`）、EnsembleDesign（`10.1093/bioinformatics/btaf245`）的论文存在不等于代码、数据和可比性已核实。另需核查 ColiFormer、DeepCodon、High-Codon、CodonTranslator、CodonRL、RNAJog、NatCodon、CodonBERT、ppLM-CO，并区分预印本与同行评议状态。

每个方法记录官方 URL/commit、环境、训练数据、输入、输出、目标、默认与最佳配置、预训练污染、实际运行状态和失败原因。不能运行的直接强 baseline 标不可比，不得换弱方法冒充 SOTA。商业工具优化序列训练的模型需单独审计目标泄漏，不能直接声称真实功能监督。

当前 scoped 资产事实：EnsembleDesign 官方 quick v2 成功 6/6，3 条输出匹配 README，但这不等于完整 A10 可比性已关闭；ID3 两条 CPC 轨迹缺陷必须保留；CodonTransformer 已完成真实 CUDA 输出和独立复核，但尚无可比性能结论。G0 时 A10 全部定向测试 251 passed，E1 与 E2 初始数值基础分别为 33/36 tests；这些测试只支持工程复核，不替代科学 Gate。

## 5. E0–E6 环环相扣的实验链

| 阶段 | 核心行动与对照 | 判决与承接 |
|---|---|---|
| **E0 数据和 baseline 可信** | 完成第 3.3 节审计与外部官方资产复现；冻结任务、划分、主指标、调参预算和成本 | 没有真实功能与可靠 Ribo 输入，E1–E3 不启动；关键 baseline 未跑通，E4 不称 SOTA；通过后才是 A10-G0 |
| **E1 观察过程** | raw 直接运输、研究内校准、无动力学序列模型、位置/constant；观察映射自由度、源内拟合、潜在参数稳定性、未读研究表现 | 检验 H1；失败则不写跨研究动力学。只有观察可分性成立，E2 才有跨研究解释基础 |
| **E2 流守恒非局部增量** | 完整动力学、去流守恒同容量模型、独立密码子模型、纯位置场；上下游密度响应、通量、稳态残差、转录本/变体 OOD | 检验 H2；无增量即停止动力学主线。只有通过的动力学量进入 E3；通过后为 A10-G1 |
| **E3 功能 OOD** | T1 全部直接可比方法；主效应、逐蛋白方向、top-k、校准、不确定性和失败分层 | 检验 H3；paired 95% CI 下界>0且 Holm 通过才形成功能阳性核心。通过后才允许大规模生成训练，为 A10-G2 |
| **E4 设计质量—成本** | T3 最强外部与内部方法，同初始、反馈、目标、预算和硬件；dense anytime、实际集合、time-matched、全成本、合法率，真实 held-out 另表 | 检验 H4；只赢 r5/hill，或只赢等 scorer 而输等时间，均不算实用 SOTA |
| **E5 对应机制消融** | 去流守恒、去观察映射、去起始结构、去自然先验；同参数、同训练/推理成本；预测与设计消融、分层和不确定性 | 无独立收益组件删除；失败层保留。E4 与 E5 同向才构成 A10-G3 |
| **E6 真实功能与前瞻验证** | 公开 held-out 变体只支持回顾性验证；顶刊版本另需至少两个蛋白、明确宿主/UTR、WT 和强方法对照、独立重复、功能/稳定性测量的 DBTL | 预算与周期由 owner 决定；未完成前不得写疗效、免疫原性或普遍表达提升 |

## 6. Nested grouped CV、统计与成本合同

### 6.1 划分与调参

- 使用 nested grouped CV；outer test 不参与模型、特征、早停、超参或阈值选择。最终 untouched 在全部协议冻结后一次评估。
- Goodman 已冻结 5 outer×4 inner 的 Gene-grouped nested CV，独立复核 25/25；其评价名称严格限定为 **Gene-grouped N 端片段构建 OOD**，不称 protein OOD。assignment/split/独立复核 SHA 见第 0.1 节。
- 功能按蛋白/family/研究分组，Ribo 按转录本/研究分组，设计按基因分组；同蛋白变体不得随机跨 split。已读 Subtelny、unique18 等不能再冒充 untouched。
- 优化器 LR log-uniform、weight decay、dropout、warmup、grad clip、batch tokens、训练步数、编码器容量和正则强度只在 inner dev 用 ASHA/小网格。
- 动力学专属调参包括速率上下界、稳态容差、观察映射自由度、功能/占据损失权重、缺失数据采样；先局部敏感性和可辨识性，再大训练。
- 生成专属调参包括自然先验强度、能量温度、偏好采样、候选/top-k、早停与块长；全部进入推理成本。
- 所有方法使用相当调参预算和官方最佳可复现配置；至少 3 seeds，关键结论按功效分析增加，不用默认超参误判架构。

### 6.2 OOD 与统计

- OOD 至少分 transcript、蛋白/family、研究、长度/GC；数据支持时才加宿主。失败分层不得删除。
- 功能以蛋白/研究为独立单位，Ribo 以转录本/研究为单位，设计以基因为单位；seed 先在组内聚合。
- 报告 paired cluster bootstrap 95% CI、逐单位方向、Holm 校正和效应量。每个选定任务独立要求主效应及 CI 下界>0、多重校正通过、完整成本与 OOD；生成另需合法率 100%。
- SOTA 是待验证目标，不是文档承诺；不可比任务分别列表，不拼虚假总排名。

### 6.3 成本与轨迹

分别记录 cache-before requests、唯一 scorer、模型 forward、生成时间、评分时间、训练成本、wall-clock、硬件和并行度。等反馈、等 scorer 与 time-matched 结论分开。无真实轨迹的方法只比较 actual set；缺失为 null，不补零，不伪造外部轨迹或成本。

## 7. A10-G0–G3 与停止规则

| Gate | 必要条件 | 失败处理 |
|---|---|---|
| **A10-G0 数据/baseline 可信** | E0 完成；关键数据、划分、泄漏审计和直接 baseline 真实可运行，主指标/预算/成本冻结 | 不启动 E1–E3；E4 不称 SOTA |
| **A10-G1 动力学增量** | E2 在严格 OOD 超过去守恒和简单模型；E1 决定能否增加跨研究主张 | 停止动力学主线，不靠扩参或换弱 baseline 翻案 |
| **A10-G2 功能阳性核心** | E3 达到预注册 SOTA 门槛：主效应 paired 95% CI 下界>0、Holm 通过、完整 OOD 与成本 | 停止生成训练，继续诊断数据/目标；不得把 A9 授权当通行证 |
| **A10-G3 设计阳性核心** | E4 等反馈/成本超过最强可比方法，E5 机制消融同向，合法率 100% | 不写实用设计 SOTA；保留直接梯度等更强方法与失败边界 |

文档、测试、hash 和 PPT 是复现条件，不是科学 Gate。不得通过弱 baseline、回顾性最佳臂、target outcome 校准或反复 untouched 制造通过。

当前登记：**E0/A10-G0、E1/A10-02 已完成**；H1 仅为开发集阳性，最终跨研究结论仍未建立。A10-03/E2 v7 已于 2026-11-24 因 batch sample 10 normalized residual `8.842e-06 > 1e-10` fail-closed 退出，无 `summary.json` 或 `predictions.npz`，不能称训练完成。v8 保持严格 `1e-10`，但已在 36/486 条曲线后因 backward batch sample 13 residual `2.944e-08 > 1e-10` fail-closed 退出 1，无 `summary.json`、`predictions.npz`、outer 或科学结果。历史 integrate 全量测试为 910 passed、1 skipped、5 subtests passed（6126.13 s）；历史 release 集成 `79dcbf377b043e21f45573428128d236c9534685` 的相关 144 tests、synthetic 多 worker 逐位一致、每份 27 verifier checks 和 859 CTMC cases/review 均只支持 scoped 工程数值结论；v13 启动时 release HEAD 为 `f7e3fdbb7684befe947a12b06de56744defbdb96`（backend identity 代码提交为 `40603527afa3ee2275166b4293234cdd48a9e38c`）。v10 27 workers、w23 与 w21 均 OOM 失败、0 shard；w21 已收束并退出 1，0 完成 shard/0 曲线，结构化求解修复已完成 146 项定向测试与真实 CUDA/独立数值验收（本地 `b6012ac50b30110636505a26aa716f5d59af6e11`，未 push）且严格阈值不变。v11 最终 CUDA OOM、v12 最终 `CUBLAS_STATUS_ALLOC_FAILED`，均退出 1、0 shard/0 曲线且无完成摘要；cache backend identity 已在 `40603527…` 修复并经真实 CUDA 验证，但不抵消资源失败。v13 以 6 workers 真实 CUDA 启动，唯一启动后快照符合共享显存预算但 0 曲线/0 shard、无退出码，科学运行未完成。E2/H2 未证且未裁决，**G1 未通过**；E3/G2、G3 也未通过。G0 只关闭数据与 baseline readiness，E1 的 TB-MSE 改善不证明 Pearson/Spearman 增量或动力学增量；`final_untouched=false`、`SOTA=false`，生成训练仍须 G2。历史 schema/算法修正只修复审计与复核实现，**不是放宽 Gate、降低标准或改写历史 Gate**。

## 8. 三重核验、运行登记与论文证据

### 8.1 三重核验

1. **代码与契约**：审查 diff，新增实现补项目风格测试；小状态验证数学性质，定向测试必须通过。
2. **数据与守恒**：核对输入/hash/schema/数量、raw-clean 谱系、split 隔离、缺失和成本字段；缺失不得补零。
3. **独立复算与真实 smoke**：从原始数据/序列独立重算关键点，执行真实端到端 smoke；最终跑项目标准测试和干净环境复现。

结果先独立核验，再写论文或 PPT；失败日志保留，历史 artifact 不覆盖。

### 8.2 每项运行登记

每次运行登记：假设、commit+dirty hash、环境/CUDA/GPU、数据与 split SHA、完整命令和配置、seed、拟合数、超参、训练/收敛信息、forward/scorer/time/硬件/并行度、artifact 路径与 SHA、指标版本、结果、不可声称事项、失败/恢复历史、独立复核脚本与结果。

### 8.3 论文主线

主线必须是：**独立密码子代理与 raw occupancy 失败现象 → 测量过程和全局耦合缺口 → 非局部动力学证据 → 守恒方程推导模型 → 功能 OOD 强 baseline → 设计质量—成本 → 对应消融与失败边界 → 真实功能验证**。

Fig.1 展示真实分布、简单代理失败与反例；Fig.2 展示观察校准、非局部响应及去守恒对照；Fig.3 只画由方程产生的模型；Fig.4 分 T1/T2/T3 列主表；Fig.5 对应消融、可辨识性和失败案例；Fig.6 展示 OOD、time-matched、全成本、不确定性与真实变体。每节按“问题→对照→现象→结论边界→下一实验”写，每主张映射 raw data、split、对照、指标和反驳条件。

## 9. 一个月执行边界

- **第 1 周：A10-00/A10-01、E0/G0（已完成）。** G0 closeout v3 裁决为 `A10_G0=PASS_DATA_AND_BASELINE_READY`；完整登记与 SHA 见 `交接文档/HANDOFF_A10_01_E0_20261123.md`。仍不训练新生成器，不写机制、SOTA、protein OOD 或真实生物泛化结论。
- **第 2 周：A10-02/E1 已完成；A10-03/E2 release 工程验收、cache provenance 修复与 v13 共享资源审计通过，但 v7、v8、v10、w23、w21、v11、v12 均失败，v13 科学运行未完成，G1 未通过。** v7 于 2026-11-24 因 batch sample 10 normalized residual `8.842e-06 > 1e-10` 退出，无 `summary.json` 或 `predictions.npz`。v8 于 36/486 条曲线后因 backward batch sample 13 residual `2.944e-08 > 1e-10` 退出 1，同样无完整预测或科学结果。历史 integrate 全量测试 910 passed、1 skipped、5 subtests passed（6126.13 s）保留；历史 release 集成 `79dcbf377b043e21f45573428128d236c9534685` 的相关 144 tests、synthetic 1/2/4-worker 逐位一致、每份 27 verifier checks 和 859 CTMC cases/review 只支持工程与 scoped 数值状态；v13 启动时 release HEAD 为 `f7e3fdbb7684befe947a12b06de56744defbdb96`（backend identity 代码提交为 `40603527afa3ee2275166b4293234cdd48a9e38c`）。v10 27 workers、w23 与 w21 均 OOM、0 shard 且失败保留；w21 已退出 1，26 份 worker failure 和性能根因已保全，结构化求解修复已完成 146 项定向测试与真实 CUDA/独立数值验收（本地 `b6012ac50b30110636505a26aa716f5d59af6e11`，未 push），严格 `1e-10` 不变。v11 cache backend identity 缺口已修复，定向 151 tests、提交后并行 12 tests 与真实 CUDA/cache 复核通过；v11 最终 OOM、v12 最终 `CUBLAS_STATUS_ALLOC_FAILED`，均退出 1、0 shard/0 曲线且无完成摘要。v13 以 6 workers 真实 CUDA 启动，唯一启动后快照符合共享显存预算但 0 曲线/0 shard、无退出码，科学运行未完成。859 个 L1–L6 精确 CTMC 对照揭示了不可忽略的平均场近似误差、共同时间尺度零空间和病态可辨识性，但不证明生物有效性、H2 或 G1。H1 为开发集阳性，仅限 TB-MSE 校准改善，Pearson/Spearman 不变，不外推为最终跨研究结论；SHA 与完整指标见 `交接文档/HANDOFF_A10_02_E1_20261123.md`。保留 v1–v8、v10/w23/w21/v11/v12 失败证据且不覆盖任何失败目录；后续运行只有形成完整产物后才可独立重建稳态与指标，并按冻结合同完成同容量严格 OOD 判决；G1 未过则停止动力学主线。
- **第 3 周：A10-04、E3/G2；有条件进入 A10-05。** 只有 G1 通过后做动力学驱动的功能主表；只有 G2 通过后才允许大规模生成训练及 E4/E5。
- **第 4 周：有条件完成 A10-05/A10-06，或如实收束缺口。** 通过前序 Gate 才做设计、对应消融和最终一次 untouched；随后干净复现、论文证据矩阵和 PPT。未建立阳性核心时稿件保持 working，不用工程量包装成功。

E6 的前瞻 DBTL 不是默认一个月关键路径，预算、至少两个蛋白的实验范围和延期由 owner 决定。Harmonization、完整 UTR–CDS 联合设计、大 ESM、MoE、RLOO、扩参及无新科学问题的窗口/覆盖/初始化/gating 消融均不在本轮范围。

永久禁止：把 occupancy 写成绝对速率、回顾性关联写成因果、计算代理写成真实生物功能；同蛋白随机拆分、target test 校准、反复 untouched、弱 baseline、缺失预算补零；删除失败日志、改写历史 Gate、伪造轨迹/成本；先做大模型或生成训练再补数据与科学问题。
