# CodonFlow Tasks（A10 · Kinetic-CodonFlow 执行清单）

> 生效日期：2026-11-23。唯一执行合同为 `交接文档/PROMPT_NEXT_AGENT_A10_KINETIC.md` 与 `交接文档/spec.md`；A7–A9 仅作不可变证据引用。
> 当前 **A10-00、A10-01/E0、A10-G0 与 A10-02/E1 已完成；H1 为开发集阳性判决；A10-03/E2 release 工程验收已通过，但生产科学运行未完成，E2/G1 未完成**。release `/home/codonflow-a10-e2-release` 保持旧 HEAD `4603951295352ae20b849cc4132ba56519d34ba3` 且只有四份文档 dirty，本轮不触碰；独立 verifier `/home/codonflow-a10-e2-verifier` 与 GitHub `a8-rk` 的当前证据基线为 `cac91df1468b0e01b4e619a5ca9f57e4b242896d`，全量 952 passed/1 failed/1 skipped/5 subtests，唯一失败共享 GPU OOM；v13 启动时 HEAD 为 `f7e3fdbb7684befe947a12b06de56744defbdb96`，backend identity 代码提交 `40603527afa3ee2275166b4293234cdd48a9e38c` 是其直接祖先；历史集成 `79dcbf377b043e21f45573428128d236c9534685` 的 144 tests、synthetic 1/2/4-worker 逐位一致、每份 27 verifier checks、859 个 L1–L6 精确 CTMC cases 及 review 通过仅是 scoped 工程数值证据。v7/v8 历史失败不删除；v10 27 workers、w23 与 w21 均 CUDA OOM、退出 1、0 shard、0 曲线且失败保留。w21 已按明确 PID 收束，26 份 worker OOM failure、executor failure 与性能探针已保全，无科学恢复价值。实测约 94.8% forward 时间在 CPU Newton，padded dense backward 为 `O(BL^3)` 且单次约 593 MB 分配；结构化求解修复已完成工程验收：独立 worktree 本地 `b6012ac50b30110636505a26aa716f5d59af6e11` 未 push，146 项定向测试及真实 CUDA 长序列、独立残差/梯度、方向回归通过，科学 protocol、Gate、`1e-10` 均不变，生产科学运行未完成。v11 的 cache backend identity 缺口已修复并推送；v11 最终 CUDA OOM、v12 最终 `CUBLAS_STATUS_ALLOC_FAILED`，均退出 1、0 shard/0 曲线且无完成摘要。v13 启动时 release HEAD 为 `f7e3fdbb7684befe947a12b06de56744defbdb96`，运行 13321.0843 s 后于 position/epoch890 OOM、退出 1；2 个成功 cache shard＋1 个失败 shard，无完成摘要。受控真实 CUDA A/B 已定位 output-gradient hook 闭包逐 batch 保留 CUDA 张量，本轮未修改生产代码或 v13 artifacts。H2/G1 未裁决且未通过。G0 裁决为 `A10_G0=PASS_DATA_AND_BASELINE_READY`；E1 结果不构成最终跨研究、绝对速率或 SOTA 结论，H2、E3/G2 均未证，`final_untouched=false`、`SOTA=false`，生成训练仍须 G2。不得把历史 A8 bounded G0 或 A9 生成训练授权继承为 A10 Gate 通过。
> 2026-11-26 独立 verifier 修复已发布：修复代码提交 **`18a80c2df28e063025787a0ac853fa467c6f42b3`** 已推送 GitHub `a8-rk`，代码验收时 `/home/codonflow-a10-e2-verifier` 工作树干净，**49+3+12 tests 全部通过**。旧 verifier 缺 banded backend identity、拒绝 scheduler arm quotas 且 shard cache SHA 只验格式未重算的三项工程阻断已修复；真实 NPZ schema/spec/identity、文件与 sidecar SHA 也均纳入检查。只改 verifier 及其测试，不改 producer、protocol、统计或 Gate。release `/home/codonflow-a10-e2-release` 仍为旧 `4603951295352ae20b849cc4132ba56519d34ba3` 且只有四份文档 dirty，本轮保持不动。outer-test 逐 kinetic 成员残差复核合同仍为 **9657**（3 seeds×1073×3 selected members），由 `outer_test_member_residual_contract` 显式核对；**28971** 是全 27 kinetic models×全转录本的额外诊断，不得事后加入 Gate。19:57:14+08:00 的运行中快照仅为历史；v13 最终于 22:36:45+08:00 OOM、退出 1，无完成摘要，ready verifier 未运行，H2/G1 未裁决且未通过。
> 2026-11-26 当前证据更新：verifier `cac91df1468b0e01b4e619a5ca9f57e4b242896d` 全量为 **952 passed/1 failed/1 skipped/5 subtests**，唯一失败为共享 GPU synthetic 多 worker OOM；干净 checkout 的 1/2-worker synthetic 各 **27/27 shards**、各 **28/28 checks**，manifest SHA `e34cba1c7d33ea948eb3d6e7833c333014c7f67ab214ce0e23d5b657c2862aac`。真实 32×1487、128-step CUDA A/B 中 production 显存斜率 **2334208 bytes/step、R²=1**、128 弱引用全活且 GC 无效；仅禁用 hook 或无 failure_context 均斜率 0、弱引用 0，根因闭合为 output-gradient hook 闭包逐 batch 保留 CUDA 张量。诊断 `summary_v3.json` SHA `7b8b4fd8…`；未修改生产代码、protocol、Gate 或 v13 artifacts，不预写修复。
> 2026-11-27 v14 从头运行中：v14 恢复实现为 `fe11a241…`，独立复跑定向 **31 passed**；本轮登记时 memory 工作树 `/home/codonflow-a10-e2-memory` HEAD 为 `3ba302dfcab8dd250409bcf1b514c415a5b3f9f9`。修复仅解除 output hook 对 `capture` 的正常训练期持有，异常仍保存梯度快照，科学 protocol/Gate/`1e-10` 不变。复用合同 `memory_shard_reuse_contract_v1/manifest.json` SHA `e3bb13e0…` 只允许 v13 的 **2 个成功 independent outer0/1 shard** 作 oracle，第 3 个终止 shard 是 position OOM。三臂 1000-step 无显式 GC soak 均完成并有界，kinetic 峰值约 100.58 MB、后半程下降，未见持续线性增长。outer0 正式 replay 结构完整但有 **547 个字段不一致**，science SHA 由 `cc3a19a7…` 变为 `d8b4817d…`，逐位不等价，按合同拒绝复用；outer1 未重放，旧 cache 不变。v14 已从全新空 cache 启动：输出 `kinetic_development_v14`，cache `kinetic_development_v14_from_scratch_shard_cache`，producer PID `4176767`，4 workers，cache hits 预期 **0**，不是 2 或 3。登记时未见 OOM，warnings 保留；运行中不等于完成，不得预写 v14 或 H2/G1 通过。
> 未获相应 Gate 前禁止生成器训练；禁止读取 untouched24、MAGE functional untouched 及派生文件。v8 历史工作树为 `/home/codonflow-a10-e2-v8`，HEAD `287c02569e7af325da8578fd5973d9c98f681562`；v8 已退出，其产物目录 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/a10/e2/kinetic_development_v8` 不可覆盖。历史 integrate dirty 状态与 910 tests 记录保留；v13 启动时权威实现为干净 release `/home/codonflow-a10-e2-release@f7e3fdbb7684befe947a12b06de56744defbdb96`，其中 backend identity 代码提交为 `40603527afa3ee2275166b4293234cdd48a9e38c`；结构化求解历史工作树为 `/home/codonflow-a10-e2-structured`，cache provenance 修复直接在 release 完成并单独提交。release 集成 manifest 为 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/a10/e2/kinetic_release_integration_v1/integration_manifest.json`；w21 关闭证据在其下 `w21_oom_closeout_20261126_v1/`，性能探针为同级 `performance_probe_v1/`。v10、w23、w21 产物分别在 `kinetic_development_v10/`、`kinetic_development_v10_w23/`、`kinetic_development_v10_w21/`。solver 验证在同级 `kinetic_solver_v8/`，mean-field 原始与历史整合产物分别在同级 `mean_field_validation_v1/`、`mean_field_validation_integrate_v1/`；大型产物根目录为 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/a10/`。后续任何 untouched 读取均须先冻结最终协议并具备相应明确授权。

## A10-00 · 重核权威状态并建立任务—数据—baseline—主张矩阵

**状态：已完成（仅限本项两个交付物，不代表 E0 完成）。**
**依赖：无。**

- [x] 完成权威执行环境重核；A10-03/E2 release 为 `/home/codonflow-a10-e2-release`，A10-00 时 HEAD `6075ad5381800c84e99b4f4a277b26b6594a7fbf` 且干净。RTX 5090、torch 2.14.1+cu132 真 matmul 通过；该轮未 push。
- [x] 确认旧 A7 PID `2071716` 暂停且不重启；本轮不启动新生成器训练、不读冻结数据；保留 RK42=0/9 和冻结集边界，Goodman/Tunney/Lareau 的后续事实以 A10-01 为准。
- [x] 新建 `交接文档/A10_00_TASK_DATA_BASELINE_CLAIM_MATRIX.md`，逐任务记录实际数据、baseline 真实状态、主指标、可/不可主张和下一动作。

**验收**：远端事实与文档一致；矩阵不以旧计划代替实际状态；事实和计划分栏；本项完成不勾选 E0/G0。

## A10-01 · 完成 E0：真实数据、泄漏审计、划分与直接 baseline

**状态：已完成；E0 与 A10-G0 均已通过 closeout v3 验收。**
**依赖：A10-00（已完成）；裁决：`A10_G0=PASS_DATA_AND_BASELINE_READY`。**

G0 closeout v3 SHA 为 `93928d6b6c2599d7e18e59896863f4b3bea91b3e034f64538631d395711ac8cc`，独立复核 SHA 为 `1c6a3b1e211998f7a79959eca68af3a03c92d94548b31eefcc7e62a0ebe1ebd3`，独立复核 20/20 通过；closeout 生产与独立复核测试合计 45 passed，A10 全部定向测试 251 passed。以下勾选表示 E0/G0 readiness 已验收，不表示所有外部方法均运行成功或可比，既有失败和不可比原因继续保留。历史 schema/算法修正只修复审计与复核实现，**不是放宽 Gate、降低标准或改写历史 Gate**。

### 数据取得与任务化资格

- [x] 取得 Goodman2013 官方 construct-level raw 并记录核心谱系：官方 CSV SHA `a03071027b8c0008d07fb7737de0a7d51765c6cff25bc86e93465a6253c7c33a`，14234 行、75 列、137 Gene、4817 exact CDS、280 条 leader、33 nt N 端片段、8439 条 SetGood；clean SHA `ce64f2caa9633fefae840e220d36b6360946d39b9253adc56f3ef297b9ab9c82`。该勾选不扩展为全长 CDS、天然 UTR 或 protein OOD 资格。
- [x] 完成 Tunney 候选审计：5894 transcripts、2920075 codon rows；report SHA `9fecfb838762950b2545f6db4fb0d6ba4ab92cc9483aad20c33cd1f0d8abf9b9`，clean SHA `238d9997f6449763bed69a4ba806b74ea0f77b95ee526cb6dff61fe9ce1b7a6e`，独立复核 24/24。合并 lane 为非独立重复，采用 A-site/RSEM 加权；不把候选审计完成写成最终研究 OOD。
- [x] 纠正 Lareau 状态：`GSE58321` 已出现于 RK03/RK05，不再称“未读候选”，不得作为最终研究 OOD；该勾选仅表示旧状态纠正，不表示新增 raw 或完整 QC。
- [x] 另定一个未读 Ribo 研究作最终研究 OOD；Mohammad/Subtelny 仅作已观察开发，Lareau 也不得重新冒充未读研究。最终研究在划分、校准和评价协议冻结前不得读取结局；资格与冻结状态已由 G0 closeout v3 验收，本登记不展开研究结局。
- [x] 固定数据用途：Kudla154=GFP 开发；Boël6348=ordinal/非同义辅助；Cambray2018=片段且氨基酸变化辅助；Mordstein=已观察辅助；iCodon=禁用；MAGE functional untouched 与 untouched24=冻结。
- [x] 按 T1/T2/T3 和起始结构运输、真实功能验证分别判定资格，不再用统一 R1–R7 一刀切；不得改写 RK36/RK42 历史判定。

### E0 七类审计与冻结

- [x] 完成 Goodman 序列与构建的 scoped 审计：v3 report SHA `3036961a32502c1ea7a9bf6cd45f2ffbb0cadf2d18ff8f3405b4abd4bb1a6304`，独立复核 31/31，SHA `c78359d03a45f3bbbcc867f36be8b2c74219a9410c543a90d08e8784a6bf42ab`。结论仅限 33 nt N 端片段构建，不外推为完整 CDS 或天然 UTR 审计。
- [x] 完成 Tunney 候选的 scoped Ribo 审计并独立复核 24/24；保留合并 lane 的非独立重复性质和 A-site/RSEM 加权口径，report/clean SHA 见上。该 scoped 子项本身不替代其余 Ribo QC；完整 E0 QC 已由 G0 closeout v3 验收。
- [x] 完成其余数据的序列、构建和 Ribo QC：长度/alphabet/stop/翻译、UTR/leader/载体/宿主/批次、coverage/P-site offset/密码子映射/重复一致性/零覆盖/footprint；保留原始计数和缺失原因。
- [x] 输出长度、GC/CAI、密码子/氨基酸组成、变体位置、每蛋白/研究样本量、动态范围、重复噪声、覆盖和长尾分布；披露短序列、优势物种和大 assay 主导。
- [x] 审计 exact CDS/protein/ID、同源簇、重复测量、功能来源蛋白、研究批次和第三方预训练重叠；RSCU、归一化、校准和特征选择只由 train 拟合。
- [x] 冻结 Goodman 5 outer×4 inner 的 Gene-grouped nested CV：assignment SHA `e2d8b31bf6a5aee6f104c96ea484340b6d10654bc35494c36fa4a89a31e6a129`，split SHA `f49c93af8e2a30616d6f0e907f75dd8a08e29e5fe23e303484c120feb57683c2`，独立复核 25/25，SHA `379ef698d8f0029d929468c94bcdf594bd83384e957fcc31e4e66d46b4fc2f43`。只称 **Gene-grouped N 端片段构建 OOD**，不称 protein OOD。
- [x] 完成其余功能/Ribo 的 nested grouped CV 与开发、独立 calibration、最终 untouched 隔离；功能按蛋白/family/研究，Ribo 按转录本/研究，同蛋白变体不得随机跨 split。此勾选不表示已执行最终 untouched，`final_untouched=false`。
- [x] 缺失字段显式为 missing/null 并限制结论；不静默填补，不删除低表达或失败变体；为其余数据补齐 raw-clean SHA 和处理谱系。

### Baseline 官方资产与真实 smoke

- [x] 完成 Goodman 7 臂 nested 5 outer×4 inner **开发 baseline**：constant、CAI、GC、dG、tAI、Ridge、HistGB；共 8439 条 SetGood rows、59073 条 prediction rows（7 臂×5 折），独立复核 32/32 通过。prediction SHA `aa0cfbc280f1dc3a3b1e1e829ce71bfabe942122dbac8671d322e314bdade271`，report SHA `0dc67e5b2b38bd79cfe19211362994a28a6206020264ea819400b7b7e76eea9d`，独立复核 SHA `384519f7bfc4a6cd574694bee838176b6f4d0c871367c4a567bfffd30828e5a4`；wall-clock 370.0619 s，HistGB 85 fits 均为 52–264 iterations、0 次触及 500 上限。逐 outer 均值的 Spearman/RMSE/top-1 全表见 `交接文档/HANDOFF_A10_01_E0_20261123.md`；只称开发 baseline，不作机制、SOTA、protein OOD 或真实生物泛化结论。
- [x] 完成 T1 其余直接 baseline 的 G0 readiness 验收：局部/全局 MFE、位置场、Boël 作者模型（适用时）、通用序列模型和可复现直接竞争方法；Goodman 7 臂开发 baseline 不替代本项。勾选不表示全部方法均成功或形成 SOTA 主表。
- [x] T2 核实并按任务验收 constant、位置场、Ridge、RiboMIMO、iXnos、ROSE、VeloGRU/VeloBERT、VeloHARMO（适用时）；历史 smoke 或失败记录不能自动视为 A10 直接可比。
- [x] 完成 EnsembleDesign 官方 quick v2 资产核实与真实 smoke：成功 6/6，且 3 条输出匹配 README；该结果只证明官方 quick 样例可运行，不等于完整 A10 可比性或 SOTA 已建立。
- [x] 保留并登记当前外部资产缺陷：ID3 两条 CPC 轨迹缺陷不得删除或改写为成功；CodonTransformer 已固定官方源码 `4a447b01…` 和模型 revision `9744dcc…`，RTX 5090 上 1 deterministic＋2 stochastic 输出均为 333 nt/110 aa、翻译一致，总耗时 13.4349 s、峰值 401985024 bytes，独立复核通过；只证明可运行，不证明性能优势。
- [x] 核实 LinearDesign、ID3 的可比轨迹、RNARL、CodonTransformer、COformer、VeloHARMO 与内部 hill/MH/SA/GA/random/r5；按任务核验 CAGFN、codonGPT、GEMORNA，并完成 G0 所需 EnsembleDesign 可比性登记；不可比项保留原因，不写成运行成功。
- [x] 每个外部方法登记官方 URL/commit、环境、训练数据、输入/输出/目标、默认与最佳配置、预训练污染、真实运行状态、失败原因和成本；论文存在不等于可运行。
- [x] 其余关键直接 baseline 完成 G0 所需真实端到端 smoke 或明确的“不可比+原因”登记；不得换弱方法冒充 SOTA。EnsembleDesign quick v2 不替代本项。
- [x] 冻结各任务主指标、至少 3 seeds、相当调参预算、ASHA/小网格范围、统计方案和成本口径；无轨迹方法只评 actual set，缺失为 null。

**输出**：数据卡与来源 manifest、raw/clean/split SHA、QC/分布/泄漏报告、baseline manifest 与 smoke、冻结协议和运行台账均已由 G0 closeout v3 验收；汇总见 `交接文档/HANDOFF_A10_01_E0_20261123.md`。closeout v3 与独立复核 SHA、20/20、45 tests 和 A10 定向 251 passed 登记如上。
**验收**：**E0 与 A10-G0 已勾选完成**，裁决为 `A10_G0=PASS_DATA_AND_BASELINE_READY`。当前 E1 已完成且 H1 为开发集阳性；E2 v7 已于 2026-11-24 因 batch sample 10 normalized residual `8.842e-06 > 1e-10` fail-closed 退出，无 `summary.json` 或 `predictions.npz`，不能称训练完成，恢复工作在进行。H2/G1 未裁决且未通过，E3/G2 未证；`final_untouched=false`、`SOTA=false`，生成训练仍须 G2，E4 不称 SOTA。

## A10-02 · 完成 E1：低自由度观察模型与跨研究可分性

**状态：已完成；H1 为开发集阳性判决，不是最终跨研究阳性。**
**依赖：A10-01/E0 与 A10-G0（已完成）；冻结的 source train/独立 target calibration/target test。**
**结果边界：仅支持开发研究中的 TB-MSE 观察校准改善；Pearson/Spearman 不变，不称绝对速率、最终跨研究结论或 SOTA。**

- [x] 预注册 raw 直接运输、研究内校准、无动力学序列模型、位置场和 constant 对照；从单调或低自由度仿射 `g_s` 开始，限制 calibration 自由度。
- [x] 所有映射只在 source train 或独立 target calibration 拟合；开发 target test outcome 在分析、代码、划分和指标冻结前不可读。本次未执行最终 untouched/target test，不将开发完成写成最终跨研究评估完成。
- [x] 比较观察映射自由度、源内拟合、潜在参数稳定性、transcript-balanced MSE、mean per-transcript Pearson/Spearman 和校准；seed 先在转录本内聚合。校准斜率为 0.1580–0.1644、截距为 0.8224–0.8308，Pearson/Spearman 不变。
- [x] 用 transcript/study 为独立单位做 paired cluster bootstrap 95% CI、逐单位方向、效应量和 Holm 校正；记录覆盖、检出限、重复噪声、缺失机制及完整成本。raw_unanchored−calibrated 的 TB-MSE effects 为 0.0420274/0.0418212/0.0406288，raw_anchored−calibrated 为 0.0403316/0.0402787/0.0390835；全部 CI lower>0、Holm<0.05、3 seeds 同向。
- [x] 独立复算观察映射和主指标并保留失败研究与失败分层。E1 v2 summary SHA 为 `2902e678f93815ccd7731720d940700ae84a88b7e8d5ee3dba8f3a833e6bef5d`，独立复核 SHA 为 `cf5ebfcb450363722e7b49e2e8cf720f883778ddebea3a01b80a2a8cb35c0539`，全量检查通过。
- [x] **H1 开发判决：阳性。** 正向效应定义为 raw−calibrated TB-MSE，故校准后误差下降；该阳性只关闭开发观察过程研究，不单独等同于 A10-G1。

**成本与测试**：E1 wall-clock 51.8138 s，33 tests。
**验收**：E1 已完成，H1 有预注册的**开发集阳性**判决。不得外推为最终跨研究动力学、绝对物理速率、Pearson/Spearman 改善或 SOTA；完整登记见 `交接文档/HANDOFF_A10_02_E1_20261123.md`。

## A10-03 · 完成 E2：最小可微流守恒算子与严格 OOD 增量

**状态：release 工程验收通过，生产科学运行仍未完成。E2 v7 已于 2026-11-24 因 batch sample 10 normalized residual `8.842e-06 > 1e-10` fail-closed 退出；v8 已于 36/486 条曲线后因 backward batch sample 13 residual `2.944e-08 > 1e-10` fail-closed 退出 1，二者均无完整 outer 预测或统计判决。release 保持旧文档提交 `4603951295352ae20b849cc4132ba56519d34ba3` 且只有四份文档 dirty，v13 producer 科学实现代码提交为 `40603527afa3ee2275166b4293234cdd48a9e38c`，v14 恢复代码为 `fe11a241…`；独立 verifier 当前证据基线 `cac91df1468b0e01b4e619a5ca9f57e4b242896d` 已发布，全量 952 passed/1 failed/1 skipped/5 subtests，唯一失败共享 GPU OOM；历史集成的 144 tests、synthetic 多 worker 逐位一致、每份 27 verifier checks、859 CTMC cases/review 通过。v10 27 workers、w23 与 w21 均 OOM、0 shard 且失败保留；w21 已退出 1，26 份 failure 和性能证据已保全，无科学恢复价值。结构化求解修复已完成工程验收，本地 `b6012ac50b30110636505a26aa716f5d59af6e11` 未 push，146 项定向测试及真实 CUDA/独立数值复核通过，严格阈值不变。v11 的 cache identity 缺 banded CUDA backend SHA，属于生产 provenance 阻断而非科学失败；修复后定向 151 tests、提交后并行 12 tests 和真实 CUDA/cache 复核通过。v11 最终 OOM、v12 最终 `CUBLAS_STATUS_ALLOC_FAILED`，均退出 1、0 shard/0 曲线且无完成摘要。v13 运行 13321.0843 s 后在 position/epoch890 OOM、退出 1，2 个成功 cache shard＋1 个失败 shard，无完成摘要；受控 CUDA 诊断已定位 hook 闭包逐 batch 保留张量，科学运行仍未完成。E2/H2/G1 未完成、未裁决且未通过。**
**依赖：A10-02 的开发观察过程边界；不得先写生成器，最终跨研究解释仍须独立最终评价。**

- [x] 实现严格为正的起始率、逐位延伸率和终止率，并完成最小可微平均场稳态算子；登记稳态与守恒数值误差。该勾选不包括参数可辨识性或严格 OOD 科学增量，也不抵消 v7 运行时失败。
- [x] 为小状态、边界、通量守恒、数值残差和梯度补项目风格测试；v7 前 36 tests 与真实 CUDA 审计 SHA `3cd3add70d9d05a47e9f6662867da0faf620586685d6d9092b96b1c975d471fd` 保留为历史。v8 使用 sparse normalized-residual Newton＋scaled Newton＋LSODA/Newton polishing，严格 `1e-10`；64 项定向检查、全项目 889 passed/1 skipped/5 subtests、真实训练快照、历史失败输入、长度 2–4096 及 CUDA 前后向通过。五组独立 least_squares 复核的最大密度误差为 1.3767e-14、最大梯度误差为 1.1796e-14、独立守恒误差为 3.9308e-14；首次 directional 有限差分公式双重计数 `k` 方向的失败已保留，修正公式后通过。以上均不抵消 v7 失败，平均场不得冒称精确随机模拟。
- [x] 完成 scoped 平均场近似误差、适用边界、局部敏感性和可辨识性验证：859 个 L1–L6 精确 CTMC 案例，`independent_review_v2.passed=true`；log-uniform random 组密度最大绝对误差中位 0.0223736651、最大 0.3391923462，最大通量相对误差 0.3198444691。密度仅观测存在共同时间尺度零空间；加入绝对通量后局部满秩但条件数可很差。该勾选只登记 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/a10/e2/mean_field_validation_v1` 的合成小状态数值产物，不证明生物有效性、长转录本近似或 H2/G1；原始验证本身不表示当时代码已整合，后续 release 整合见下项。
- [x] 关闭 release producer–verifier 工程整合验收：历史 `/home/codonflow-a10-e2-integrate` dirty 状态及 **910 passed、1 skipped、5 subtests passed（6126.13 s）** 保留；历史 release 集成与 GitHub `a8-rk` 为 `79dcbf377b043e21f45573428128d236c9534685`，v11 前干净 release `/home/codonflow-a10-e2-release` HEAD 曾为 `6075ad5381800c84e99b4f4a277b26b6594a7fbf`。相关 **144 tests** 通过；synthetic 1/2/4-worker predictions/states/metrics/science records 逐位一致，每份独立 verifier **27/27 checks** 通过，859 CTMC cases 和独立 review 通过。集成 manifest 为 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/a10/e2/kinetic_release_integration_v1/integration_manifest.json`。原始 production solver SHA `68d669bd…` 与 v8 训练清单 SHA `83b1def7…` 的身份差异保留为历史。本勾选仅关闭工程整合，**不表示端到端科学生产运行或 G1 完成**；v7/v8 不覆盖，v10/w23/w21 OOM 见下。
- [x] 预注册完整动力学、同容量去流守恒、独立密码子和纯位置场对照；独立/动力学单模型均 65 参数，位置场 1 参数，统一 successive-halving、3 outer×3 inner×3 seeds 和三成员 inner ensemble。勾选只表示协议已冻结；v7 已 fail-closed，v8 科学对照未完成。
- [ ] 先研究内 transcript OOD，再按冻结协议做研究 OOD；评价 TB-MSE、mean per-transcript Pearson/Spearman、局部编辑上下游密度响应、通量和校准，不随机拆 codon 行。Yu OPT/Cwt-Opt 的直接局部同义 WIG 配对已完成描述性分析与独立复算，但每构建 1 run、无下游编码区，不能单独完成 H2；不额外改写预注册 G1 的 OOD 判决条件。
- [ ] 至少 3 seeds，按转录本/研究做 paired CI、Holm 和失败分层；v7/v8/v10/w23/w21/v11/v12 均未产生最终预测，v11/v12 也均退出 1 且 0 完成 shard/0 曲线，未完成动力学模型训练与这些科学对照前不得判 H2。
- [ ] 保留 v1–v8、v10/w23/w21/v11/v12 失败日志与产物，不覆盖任何失败目录；w21 关闭证据已独立归集，后续只有形成完整运行产物后才独立复算稳态解、密度响应和主指标。release 已执行真实 CUDA synthetic smoke，不代替完整科学运行；无 decay 数据不加 decay 头，无多位点覆盖不加远程 pair 机制。
- [x] 在独立 worktree 完成结构化求解修复，消除长序列 padded dense backward 的 `O(BL^3)` 与大额临时分配；本地 `b6012ac50b30110636505a26aa716f5d59af6e11` 未 push。146 项定向测试、65–1521-codon 真实 CUDA 前后向、独立残差/梯度和方向回归通过；未放宽 `1e-10` 或修改科学 protocol/Gate。病态输入仍 fail-closed，所有失败日志保留，本勾选不构成生产科学运行或 H2/G1 证据。
- [x] 修复 v11 shard cache provenance：代码提交 `40603527afa3ee2275166b4293234cdd48a9e38c` 已推送 `a8-rk`，仅修改并行 runner 与对应测试，将 `kinetic_banded_cuda.py` SHA 统一纳入 parent/worker/cache/failure/summary identity。定向 151 tests、提交后并行 12 tests 通过；RTX 5090 真实 CUDA/cache 报告 SHA `918343221e843a8f59e269d7b1ecfd50bdc41e76cc8bc66602ee0780a9f741c5`，最大归一化残差 `9.50439078614984e-15`，相同 identity cache 命中、变更 backend identity fail-closed。protocol SHA 与 Gate 不变；此勾选只关闭工程 provenance 缺陷，不表示 v12 或科学运行成功。
- [ ] v12 真实 CUDA 科学生产运行仍未完成：16 workers 于 2026-11-26 18:36:52+08:00 启动，18:37:17+08:00 以 `CUBLAS_STATUS_ALLOC_FAILED` 退出 1，0 shard、0 曲线且无 `summary.json`/`predictions.npz`。startup provenance 已包含正确 backend SHA，失败证据保留，不追加成功声明。
- [x] 完成 v13 共享显存与残留进程只读审计：启动前整卡 32607/13189/18923 MiB（总/用/闲），PID `3996745`=7034 MiB 属 rareseq/ProxyFunctionGap，PID `4045601`=6138 MiB 属 rna-ft-eval，均非 CodonFlow 且未触碰；未见 v11/v12 runner 或 spawn worker 残留。按预留 12 GiB（12288 MiB），6 并发总预算 6635 MiB、等效 1105.8 MiB/并发。该勾选仅关闭资源审计，不是科学 Gate。
- [ ] v13 真实 CUDA 科学生产运行未完成且已 fail-closed：启动时 HEAD `f7e3fdbb7684befe947a12b06de56744defbdb96`，`--max-workers 6`；2026-11-26 22:36:45+08:00 退出 1，wall-clock 13321.084314 s。seed1234/outer0/position/grid4/inner2 在 continuation epoch890、train-evaluation batch2 申请 2 MiB 时 OOM。cache 为 2 个成功 shard，连同失败 shard 共 3 个终止 shard；无 `summary.json`/`predictions.npz`/`parallel.json`/selected states/完整 curves，ready verifier 未运行。失败 PID 是 4057037，9.83 GiB allocated 属于该进程；4057040 是 10.51 GiB peer。`failure.json` SHA `ebc47826…`，日志 SHA `dfd54da0…`，失败快照 SHA `a0c1e2ef…`，原 artifacts 未改。
- [x] 登记 verifier 全量与干净 checkout 复现证据：`cac91df1468b0e01b4e619a5ca9f57e4b242896d` 全量 **952 passed/1 failed/1 skipped/5 subtests passed（9219.64 s）**，唯一失败为共享 GPU synthetic 多 worker OOM，不重跑、不写成全绿；日志 SHA `3e66bfb3…`。干净 checkout 的 1/2-worker synthetic 各 27/27 shards、各 28/28 checks，predictions/states/metrics/shard science 逐位一致，三个负控制按预期失败，manifest SHA `e34cba1c7d33ea948eb3d6e7833c333014c7f67ab214ce0e23d5b657c2862aac`。仅关闭 scoped 工程复现，不是 v13 科学结果。
- [x] 完成受控真实 CUDA 显存增长根因诊断：使用真实 32×1487 失败 batch，三个独立进程各 128 steps，约 2 GiB 进程配额、1 GiB allocated 停止线，不重跑全量 suite。production allocated 增长 367460864 bytes，斜率 2334208 bytes/step、R²=1，128 个 `rho` 弱引用全活且显式 GC 无效；仅禁用 hook 与无 failure_context 均斜率 0、弱引用 0。根因为 output-gradient hook lambda 闭包持有含 CUDA 张量的 capture，逐 batch 保留输出/autograd 对象。`kinetic_v13_oom_diagnostic_v1/summary_v3.json` SHA `7b8b4fd8310c7f7c77a13951b0aceed7916cbc5318811ab50903c7b7d068d600`；首轮探针 KeyError 失败保留，生产代码/protocol/Gate/`1e-10` 未改，不预写修复。
- [x] 只读复核 `fe11a2415e33300d6a8fad4e12bc85198d3abbaa` output-hook 生命周期修复与两 shard 复用合同；memory HEAD/远端一致且干净，定向测试独立复跑 31 passed。修复未改 protocol、数学模型、统计、Gate 或 `1e-10`；合同仅含 2 个成功 independent outer0/1 shard，旧 cache 未改。
- [x] 完成三臂 1000-step 无逐步显式 GC 的真实 CUDA soak：三臂均完成并有界；kinetic 峰值约 100.58 MB、后半程下降，未见持续线性增长，自动回收形成的下降不误判为泄漏或失败。既有 kinetic 128-step 无 GC 增长和 32-step 显式 GC 对照均保留，不混写；本项仅是工程通过，不裁决 H2/G1。
- [x] 执行 independent outer0 正式 replay 并逐字段、float64 位和数组字节复核：结构完整但有 **547 个字段不一致**，science SHA 由 `cc3a19a7…` 变为 `d8b4817d…`，逐位不等价；已按合同拒绝复用，旧 cache 不变，禁止改旧 cache 直接命中。
- [x] 只读登记 outer0 replay 最早分歧诊断：`kinetic_v14_recovery_v1/replay/outer0_first_divergence_analysis_v1.json` SHA256=`6866e92ee456712a30a0b895f01935c0a3cdf84f9073d51781657fc8c1c41a95`。最早记录的 train loss 差为 **2 ULP**，最大 loss 差为 **8.881784197001252e-16（约 8.88e-16）**，预测最大差为 **3.3306690738754696e-16（约 3.33e-16）**，离散选择不变；这些数值边界不满足 bitwise 合同，也不构成统计等价或科学结果。CUDA embedding backward 非确定性只是未确证的候选机制；outer0 cache 继续拒绝复用，v14 继续从全新空 cache 从头训练。
- [x] 登记 capture 修复与真实 sanitizer 复核：`/home/codonflow-a10-e2-capture@911390cbe589d46d093dec37883269242570a19e` 干净并与 `a8-rk` 一致；`20dd9f74…` 保存 pre-backward CPU 快照，`911390cb…` 使用 SM `num_warps=1` 及 public-entry bands/rhs `contiguous()`。历史 matrix_full_v8 ordinal561 有 16 次 invalid global read 和后续 719 errors；修复后同诊断 NPZ forward 逐位一致、85 次 launch 全连续、backward 完成且 memcheck 0 errors。该勾选只关闭 scoped 工程验证，不宣称原 v14 IMA 根因已闭合。
- [x] 完整保留 raw direct-kernel 矩阵结果：720/720 完成、0 guard failures、0 exceptions、memcheck 0 errors，但 **306 numeric failures、应用 exit 2**；逐 cases 独立重算为非连续 290＋contiguous SM 16，不能写成“非连续 306”或数值全绿。public-entry P0/P1 与定向 14＋3＋2 tests 通过不覆盖 raw 失败；未跑全量 suite，也未以 memcheck 替代 racecheck/initcheck/synccheck。
- [ ] v15 真实 CUDA production 已于 2026-11-27 12:44:59+08:00 从全新 cache 启动但尚未完成：capture HEAD `911390cb…`，producer `99295`，12 workers，默认 quotas 4/8/8；输出 `/dev/shm/codonflow_a10_e2/kinetic_development_v15`，cache 为 `kinetic_development_v15_from_scratch_shard_cache`，launch manifest 标 `temporary=true`、`permanent_migration_pending=true`。teams 满、public 只读，启动时 tmpfs 可用 23192823398 bytes；永久迁移待 teams 恢复，不删除历史。12:48:17 快照为 0 成功 shard/0 curves、无 summary/predictions/exit code，warnings 保留，H2/G1 未裁决且未通过。13:25:16 只读复核仍为 0 成功 NPZ/0 sidecar；13:17 observation/summary 也为 0，`failures/pre_backward_latest.npz` 只是滚动诊断快照，不可冒充成功 shard。首 shard 尚未验收，arm/outer/seed 与数值/收敛结果均不可登记；producer `99295` 仍运行，无 summary/predictions/parallel/curves/exit code/finished，H2/G1 未裁决且未通过。
- [x] 完成 v15 当前 **4 个 independent shard 的只读阶段验收**（2026-11-27 16:18:52+08:00）：seed1234 outer0/1/2 与 seed2345 outer0 的 NPZ/sidecar SHA 一致，五字段 identity、schema/spec、预测 outer 索引、有限 float64 密度与参数、6 候选×3 inner folds、18 条曲线/18 份成本记录均通过生产 loader 和补充断言复核。四者均选 grid4（LR=0.01、WD=0）、rung grids=[4,5]，outer test 未用于选择，三成员均从 rung 恢复并以 validation plateau/patience25 停止；逐 shard SHA、science SHA、best epochs 与审计边界见 recovery handoff 第 5.14 节。该勾选只关闭四份 cache shard 的 scoped 验收，**不是完整科学 verifier 或 E2/G1 通过**。producer `99295` 与 12 个 spawn workers 仍运行其余未完成 shards/arms，无 summary/predictions/parallel/curves/selected states/per-transcript metrics、exit code 或 finished，warnings 保留；H2/G1 未裁决，完整产物形成前不得运行或声称完整科学复核通过。
- [ ] **v15 最终失败，四问门槛下暂停重提**：2026-11-28 运行 108084.9561 s 后于 seed1234/outer1/kinetic/grid0/inner1、epoch2/batch11 CUDA illegal memory access，退出 1；16 个 independent/position shards 完成、0 kinetic，无完整科学产物。精确快照单进程 blocking 重放通过，根因未闭合；不得把 16 个 baseline shards 写成 H2/G1。
- [ ] **v16 保守恢复运行中**：12 进程 blocking 精确快照全部通过，16 个 baseline cache 全量校验通过；v16 复用 16 shards、仅算 11 kinetic，producer `493604`，显式 `CUDA_LAUNCH_BLOCKING=1`。原 IMA 根因未闭合，H2/G1 未裁决。
- [ ] independent outer1 正式 replay 未执行；outer0 拒绝后流程按合同停止，不得写成 outer0/1 均重放或逐位一致，也不得补写 outer1 结果。
- [ ] v14 真实 CUDA production 已从全新空 cache 启动但尚未完成：输出 `kinetic_development_v14`，cache `kinetic_development_v14_from_scratch_shard_cache`，producer PID `4176767`，4 workers，cache hits 预期 **0**，不是 2 或 3。登记时未见 OOM，warnings 保留；无完成摘要，启动不等于 E2 完成，H2/G1 未裁决且未通过。
- [x] 独立修复当前 producer–verifier schema 阻断：`18a80c2df28e063025787a0ac853fa467c6f42b3` 已推送 `a8-rk`，`/home/codonflow-a10-e2-verifier` 工作树干净，**49+3+12 tests 全部通过**。startup identity 已纳入 `banded_cuda_backend`；parallel 精确键集及 summary parallel 比较已接受 `configured_arm_max_workers`/`arm_max_workers`；shard cache SHA 已按文件重算并比对。仅修改 verifier 及其测试，不改 producer、protocol、统计或 Gate；完整产物形成后仍须执行独立科学复核。完整 v13 产物就绪后的 ready 命令见 `交接文档/HANDOFF_A10_03_E2_RECOVERY_20261125.md` 第 5.7 节。
- [ ] 完整产物形成后按冻结合同复核 **9657** 个 outer-test 逐 kinetic 成员残差项（3 seeds×1073×3 selected members）。**28971**（3×1073×3 outer×3 members）是全 27 kinetic models×全转录本的额外诊断，不是新增 Gate，不得用后验扩展替代 outer-test 合同；科学统计、Holm、paired CI 与 `1e-10` 均不变。

**验收**：当前通过数值基础、scoped 精确 CTMC 对照子项、release 工程验收、cache provenance 修复、v13 共享资源审计、干净 synthetic 复现、显存根因诊断和三臂 1000-step 无显式 GC soak；outer0 replay 已执行但 547 字段不一致并拒绝复用，outer1 未重放。最早分歧诊断的 2 ULP、8.88e-16、3.33e-16 与离散选择不变仅是数值边界，不满足 bitwise 合同；CUDA embedding backward 候选机制未确证，cache 继续拒绝复用。v14 仅以 4 workers 从全新空 cache 启动，producer PID `4176767`，cache hits 预期 0，登记时未见 OOM、warnings 保留，尚无完成摘要。v7、v8、v10、w23、w21、v11、v12、v13 均失败，v13 为 2 个成功 cache shard＋1 个 OOM 失败 shard且无完成摘要，**E2 与 A10-G1 均未通过，H2/G1 未裁决**。后续运行仍须真实 CUDA、项目风格测试和独立复核；E2 在严格 OOD 超过去守恒和简单模型，主效应 paired 95% CI 下界>0且 Holm 通过，才标 **A10-G1** 并允许相应动力学量进入 E3；无独立增量即删除动力学核心并停止 Kinetic-CodonFlow 主线。完整失败与恢复事实见 `交接文档/HANDOFF_A10_03_E2_RECOVERY_20261125.md`。

## A10-04 · 完成 E3：T1 功能 OOD 主表与功能阳性核心

**状态：待 A10-G1；无合格动力学量时不得以未验证模块替代。**
**依赖：A10-03 通过、E0 功能数据与 baseline 已冻结。**

- [ ] 仅将 E2 验证的潜在通量/密度接入功能模型；测量不支持时不添加 mRNA 丰度或其他机制项。
- [ ] 在相同 nested grouped CV outer test 上比较 T1 全部直接可比方法；outer test 不参与模型、特征、早停、超参或阈值选择。
- [ ] 依次报告构建内/转录本 OOD 及数据支持的蛋白/family/研究 OOD 的 Spearman、RMSE、top-k enrichment、校准、不确定性和逐单位方向；Goodman 只称 Gene-grouped N 端片段构建 OOD，不称 protein OOD。
- [ ] 与 constant、CAI/GC、MFE、位置场、Ridge/HistGB、Boël 作者模型（适用时）、通用序列模型及直接竞争方法做等预算比较；至少 3 seeds，功效不足时按预注册增加。
- [ ] 以蛋白/研究为独立单位，seed 先组内聚合；输出 paired cluster bootstrap 95% CI、Holm、效应量、长度/GC 分层、失败案例和完整训练/推理成本。
- [ ] 独立原始数据复算主表关键点，完成干净端到端 smoke；未赢最强 baseline 的任务标“未解决”。

**验收**：主效应 paired 95% CI 下界>0、Holm 通过、OOD 和成本完整，才标 **A10-G2** 并允许大规模生成训练；否则停止生成训练，继续诊断数据/目标，不换弱 baseline。

## A10-05 · 完成 E4/E5：合法生成核、T3 质量—成本与对应消融

**状态：待 A10-G2；本轮禁止启动。**
**依赖：A10-04 通过；T3 强 baseline、预算和硬件已冻结。**

- [ ] 在可枚举小状态实现合法同义核，验证蛋白/长度/stop 保持、合法率、精确归一化、详细平衡/平稳分布、采样一致、单/多步一致和成本；不满足则不称 CTMC/flow。
- [ ] `Fθ` 只含 E2/E3 已验证项和明确约束；自然先验、温度、偏好、候选/top-k、早停和块长仅在 inner dev 调参并全部计费。
- [ ] 同初始、反馈、目标、scorer、预算和硬件比较 T3 最强外部与内部方法；输出 dense budget-step HV AUC、实际 Pareto/best、NED、合法率、time-matched 和全成本。
- [ ] 无真实轨迹的外部方法只列 actual set；cache-before requests、唯一 scorer、forward、生成/评分/训练时间、wall-clock、硬件和并行度分别记录，缺失为 null。
- [ ] 代理设计与真实 held-out 功能分表；真实功能不得由同一 scorer 自评代替。若 ID3/simplex 梯度或其他直接方法更强，保留并如实报告。
- [ ] E5 在同参数、同训练/推理成本下去流守恒、去观察映射、去起始结构、去自然先验；检查预测与设计消融是否同向，保留长度/GC/同源/研究/宿主失败层。
- [ ] 以基因为独立单位做 paired CI、Holm 和效应量；独立原始序列复算目标与合法率，核验外部轨迹和成本。

**验收**：E4 等反馈且 time/compute-matched 超过最强可比方法、合法率 100%，E5 消融方向一致，才标 **A10-G3**。只赢 r5/hill，或只赢等 scorer 而输等时间，不算实用 SOTA。

## A10-06 · E6、最终一次 untouched、干净复现与论文证据闭环

**状态：最后执行；不得提前读冻结数据或写 PPT。**
**依赖：相关前序 Gate、最终模型/划分/统计/成本协议全部冻结； untouched 的相应明确授权。**

- [ ] 分别确认 untouched24 与 MAGE functional untouched 的授权状态；未获相应授权则继续冻结。获准者也只在最终协议后一次评估，结果不再用于选择。
- [ ] 公开 held-out 真实变体仅作回顾性独立验证，未参与模型或阈值选择；与代理设计分表，记录来源、构建、宿主/UTR、测量单位和泄漏。
- [ ] 若 owner 批准前瞻 DBTL，另冻结至少两个蛋白、明确宿主/UTR、WT 和强方法对照、独立重复、功能/稳定性测量、预算与周期；未完成前不写普遍表达、疗效或免疫原性结论。
- [ ] 汇总 T1/T2/T3 的最强 baseline 效应、paired CI、Holm、OOD、失败分层与完整成本；明确 E1/H1、E2/H2、E3/H3、E4/H4 哪些闭合、哪些未证。
- [ ] 从干净 checkout 安装并运行项目标准测试、定向测试、真实端到端 smoke 和独立原始数据复算；核对 commit+dirty hash、数据/split/artifact SHA 和逐 run 台账。
- [ ] 建立论文主张—证据矩阵：每主张映射 raw data、split、对照、指标、成本、反驳条件；不可比任务分表，失败与反例不隐藏。
- [ ] 结果独立核验后才更新论文和 PPT；不按页数追进度，不把计划写成结果，不改写 A7–A9 历史 Gate 或 artifact。

**验收**：第三方能由干净环境重建表图；每个数字定位原始 artifact；冻结数据使用次数与授权可审计；所有不可声称事项显式。任何阻塞均保留为 working 状态，不提交证据未闭环的稿件。

## 串行 Gate 与登记要求

**唯一主干**：A10-00 → A10-01/E0 → **G0** → A10-02/E1 与 A10-03/E2 → **G1** → A10-04/E3 → **G2** → A10-05/E4/E5 → **G3** → A10-06/E6/最终复现。

E1 与 E2 的数值/小状态准备可并行，但跨研究解释必须等 E1；E4/E5 不得先于 G2；最终 untouched 不得早于全部冻结和授权。任何 Gate 失败按 spec 停止相应主线，不改成弱 baseline、回顾性最佳臂或“工程完成”。

每次运行必须登记：假设、commit+dirty hash、环境、数据/split SHA、命令/配置、seed、拟合数、超参、forward/scorer/time、训练成本、硬件/并行度、artifact SHA、结果和不可声称事项。每阶段完成：①代码 diff 与契约测试；②输入/hash/schema/数量与泄漏核验；③独立原始数据复算和真实端到端 smoke；最终执行项目标准测试与干净复现。
