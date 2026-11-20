# CodonFlow A8-RK 正式交接（2026-11-18）

## 1. 当前权威入口

本文件是 A8-RK 的当前交接；旧 A7 handoff/prompt 只保留历史，不再指导新实验。

- 完整科学与执行路线：工作区根目录 `CodonFlow_A8_严格科研工程审查与一个月路线_20261118.md`
- 镜像：`docs/review/CodonFlow_A8_严格科研工程审查与一个月路线_20261118.md`
- 执行合同：`docs/handover/spec.md`
- 文件级任务：`docs/handover/tasks.md`
- 下一位执行者提示词：`docs/handover/PROMPT_NEXT_AGENT_A8_RK.md`
- 当前预印本工作稿：`paper/CodonFlow_preprint_A8.md`；历史快照 `paper/CodonFlow_preprint_A7.md` 保留未改

A8-RK 的实际执行位于隔离工作树 `/home/codonflow-a8-rk`、分支 `a8-rk`。RK-01 commit=`5ad3393a4f90c4a743cf7e0725b45ea62e395172`；RK-02 commit=`087b8822e14dcb15710dc2f40d8db5650b8687a4`；RK-04 代码与审计 commit=`99df1d96e041e1f78b67e69210276df66d7b5f6f`；RK-06a 评价器 commit=`db3e1667dc593b4e4e9b3605bb0eee6fc249f000`；RK-06b raw-CDS scorer commit=`56a62b4415c7e0e442ff064bb6002a4aed00798a`，均已推送 GitHub。原主工作树 `/home/codonflow` 的 `main` 及其既有未推送提交未被改写或推送。大型资产沿用 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/`。不得在交接、日志或提示词中记录服务器密码。

## 2. 本轮讨论的关键结论

此前工作把训练收敛、run 数量、Gate/hash 和审计完成度当成科研进展，但没有建立通向核心性能和科学发现的因果链。上一版“反馈受控抢救”仍把 frozen r5 的成败当作整个项目的总开关，也不符合目标。现已正式改为：

> **同义序列功能是否由“5′ 起始区结构可及性—全程翻译速度场—mRNA 降解”的空间耦合决定；显式学习这种耦合，能否在固定蛋白、固定 UTR/宿主上下文下，实现优于现有方法的功能预测与多目标 CDS 设计？**

目标是逐任务公平超过最强可比 baseline，并形成顶刊级证据链。SOTA 不能预先保证，但也不再把“转负结果/benchmark”预设为项目终点。未赢的任务必须继续定向诊断并明确为未解决，不能换弱 baseline 或拼接不可比结果。

## 3. 为什么旧路线没有核心性能提升

1. 天然 CDS 同义腐蚀 CE 与终端多目标 anytime HV/时间优势不是同一目标。
2. 当前 `EditFlowTransformer` 只读 codon ID，没有显式蛋白、天然 CDS、UTR、宿主、目标、结构或时间条件。
3. `edit_flow_loss` 是简化 masking，不是完整 CTMC；推理直接忽略 time。
4. G2 的 learned open-loop 与反馈搜索信息不对等；T3.8 的开发阳性仍有高时间成本。
5. 没有真实同义变体功能监督，CAI/MFE/GC/motif 不能替代生物功能。
6. 旧 baseline 清单遗漏 RNARL、ID3、CodonTransformer、COformer、VeloHARMO、EnsembleDesign 等直接竞争方法。

因此旧 2×2 只用于解释 r5，不再阻塞新数据、新机制和 CodonFlow-RK。

## 4. 不可改写的旧证据

- G2 324/324 完成，FULL/EDIT 中位 AUC −94.28%/−93.47%，18/18 全负，Holm p=1.0。
- T3.8 的 15/15 其余开发基因为正，FULL/EDIT +59.95%/+68.73%，时间比 42.68×/2.41×；不是独立、时间或外部优势。
- D4=621,306/76,444/78,724；D5=618,073/80,191/78,177；精确 CDS/protein/ID 跨 split 重叠为0，D5 cluster 重叠为0。
- D5 只是操作性同源簇隔离；unique18 只作开发；untouched24 尚未用于新模型选择。
- 历史权威回归为 228 passed、1 skipped；新代码必须重新运行项目标准测试，不能继承“已通过”表述。

## 5. 新数据决策

### 自然先验

D4/D5、CodonTransformer、RNARL 六物种数据只提供序列/宿主先验，不作功能真值。

### 机制数据

VeloHARMO 所用五物种 Ribo-seq、UTR–CDS 配对、tRNA/密码子参考、结构/accessibility。Ribo occupancy 只能称实验依赖的相对速度代理。

### 真实同义功能候选

- Kudla et al., Science 2009：154 个同义 GFP，表达/mRNA/生长。
- Boël et al., Nature 2016：6,348 次实验，附 Protein Data Set，含蛋白表达和 mRNA 层信息。
- Kelsic et al., Cell Systems 2016：MAGE-seq 12,726 个 infA 单/双密码子突变。
- LinearDesign/GEMORNA/COformer：只纳入实际可恢复的序列和测量上下文。

**RK-02 已实际下载、清洗并审计：8 份官方原始附件完成 SHA 登记，Boël 与 MAGE 形成 25,420 个 assay rows；Kudla 支持附件已取得，但 154 条逐构建序列—表达表仍未获得，状态为 `PARTIAL_KUDLA_ROW_DATA_UNAVAILABLE`。** RK-02 时点所有 split 仍为 `UNASSIGNED`，尚未用于训练；RK-04 的后续划分见第 12 节。Theodorou et al. 的 Dasher/六蛋白原始数据原文明确不公开，不得纳入训练承诺。

数据清洗必须保留 accession/release/license/raw-clean SHA、蛋白/UTR/载体/宿主/assay/batch/replicate、单位、检出限和缺失原因。功能值只在 `protein×host×assay×batch` 内标准化。同一蛋白变体不得随机跨 split；功能主测为蛋白 OOD，Ribo 主测增加研究 OOD；RSCU/归一化/校准只由 train 拟合。

## 6. CodonFlow-RK 设计决策

一个月聚焦固定 UTR 上下文下的 CDS，不生成 UTR。

- 每个位置在同义 simplex 上参数化，保证蛋白、长度和 stop。
- codon 节点结合蛋白/宿主/预算；候选密码子展开为三核苷酸。
- 合法碱基配对约束的 pair channel 显式建模 UTR–CDS 与远程 CDS 耦合；起始区高分辨率，长程稀疏/轴向交互。
- 分别学习 `Φinit`、`Φens`、速度场 `v`、`Φdecay`/功能头和不确定性；每项由对应数据层监督并独立消融。
- 多保真：CAI/motif → 结构/Ribo → 真实功能。最终不能用参与选择的同一代理充当唯一功能真值。
- 候选核：`qθ(y|x;w,b,h,u) ∝ q0(y|x;h,u) exp[-βΣk wkΔΦk(x,y)-βcΔcost(x,y)]`。
- 用偏好条件轨迹平衡/能量倾斜目标替代天然 CE；数学目标与代码不一致时不得称 flow。

先完成机制预测头和 OOD，再接合法生成核。不要默认同时加入 MoE、完整 CTMC、短 rollout、RLOO 或扩参。ESM、attention、GFlowNet 本身不列创新。

## 7. 强 baseline 与评价决策

- 功能/适应度：CAI/GC/局部与全局 MFE、Boël logistic、通用序列模型、可复现 VeloHARMO/COformer。
- 速度：RiboMIMO、iXnos、ROSE、VeloGRU/VeloBERT。
- Harmonization：VeloHARMO、CHARMING、tAI、ICOR、HFC/BFC/URC、RNARL。
- Accessibility：ID3、GA、SA、C10/C10-CAI；可枚举时以精确最优为 ceiling。
- CDS 多目标：LinearDesign、EnsembleDesign、RNARL、CAGFN、codonGPT、GEMORNA、CodonTransformer、COformer、内部 hill/MH/SA/GA/random/r5。
- mRNAutilus/ProMORNA 只在固定 UTR、输入与成本可比时排名。

真实初始点为 B=1；使用 dense budget-step AUC，不插 `(0,0)`，缺失预算不补零。cache-before、唯一 scorer、forward、生成/评分时间、wall-clock、硬件和并行度分开报告。SOTA 需要预注册主效应及 paired 95% CI 下界>0、Holm 校正通过、合法率100%、成本完整，不能只赢均值或 r5。

## 8. 执行顺序与 Gates

### RK-G0 / Week 1

实际下载与清洗数据、无泄漏划分、官方 baseline smoke、dense v2 和成本协议。没有真实可用数据不得进入功能训练。

### RK-G1 / Week 2

E1 量化代理效度；E2 同骨干验证 initiation/velocity/decay/pair 的蛋白/研究 OOD 增量；E3 检查 MAGE—Ribo—Boël 跨层一致性。至少一个机制组合有稳定 OOD 增量才接生成器。

### RK-G2 / Week 3

实现最小 CodonFlow-RK，完成功能、速度、harmonization、accessibility、CDS 多目标主表和机制—性能对应消融。未赢的任务继续定向诊断，不能换弱 baseline。

### RK-G3/G4 / Week 4

冻结后一次评估 untouched24/功能 untouched，完成 time-matched、失败分层、Fig.1–7、主张—证据矩阵和复现包。回顾性真实变体与前瞻湿实验严格分开。

详细输入、输出、文件和验收见 `tasks.md` RK-01–RK-19。

## 9. 论文故事已经重排

预印本现在按以下链条组织：

**真实变体中的代理失效 → 空间耦合的增量证据 → 由机制推导 CodonFlow-RK → 各任务最强 baseline → 预测与生成两侧机制消融 → OOD/质量—时间 → 真实功能验证。**

Fig.1 代理失效；Fig.2 机制增量；Fig.3 模型；Fig.4 分任务 SOTA；Fig.5 消融；Fig.6 OOD/成本；Fig.7 真实功能。新结果均标为 pending，不能把计划写成结果。

## 10. 防跑偏规则

- 不要再次只写计划；按 RK-01 开始真实执行。
- 不要把 CE、合法率、测试通过或工程资产当成核心性能。
- 不要先扩参、堆 MoE/RL/CTMC 或重新包装旧 r5。
- 不要把文献中的样本数写成已下载数据，不要使用不公开 Dasher 数据。
- 不要让同一蛋白变体跨 split，不要用 untouched 调参。
- 不要遗漏 2025–2026 强 baseline，不要把不可比外部方法强行排名。
- 不要把 Ribo occupancy 写成绝对速率、回顾性关联写成因果、计算代理写成生物功能。
- 不要 `git reset --hard`、`git clean`、删除历史结果、覆盖远端或改写主工作树；按用户本轮明确指令，仅在隔离分支 `a8-rk` 对确认完成的任务及时 commit 并 push，推送后核对远端 HEAD。
- 每个阶段完成后更新 `experiments/REGISTRY.md`、`tasks.md` 和后续 handoff，记录真实结果及不可声称事项。

## 11. RK-01/02 实际完成记录与本次交付

### 代码与数据

- 隔离工作树：`/home/codonflow-a8-rk`；分支：`a8-rk`。RK-01=`5ad3393a4f90c4a743cf7e0725b45ea62e395172`；RK-02=`087b8822e14dcb15710dc2f40d8db5650b8687a4`。推送后已通过 `git ls-remote` 核对远端与本地一致。
- 生产代码：`scripts/a8_rk_functional_data.py`；独立复核：`scripts/a8_rk_verify_functional_data.py`；测试：`scripts/tests/test_a8_rk_functional_data.py`。生产与复核均只使用 Python 标准库。
- 功能数据根：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional/`。8 份官方原始附件：Boël 2、MAGE 4、Kudla 2；无未解决的文件下载失败。
- 统一表：`clean/functional_long.csv`，25,420 行、SHA256=`c436b758369018fe0fd121ce6e741993e90a5de80b4706ab87082f7557b6a377`。该数字是 assay rows，不是 unique constructs。
- Boël raw/clean=6,348/6,348；MAGE S1=4,672/9,344（minimal/rich 两个 assay）；S2=8,192/8,192；S3=1,536/1,536；S4=4,099 行全基因组背景，排除出序列—标签长表。
- MAGE S2 对账：8,192−2 WT−63 个跨窗口重复 mutation-signature 行=8,127 个 unique non-WT signatures。Boël E0–E5=1,754/131/423/896/1,171/1,973。
- Kudla SOM 与寡核苷酸 TXT 已取得并登记；它们支持实验协议，但不包含 154 条完整 GFP 构建及表达量表。Kudla 实际 sequence-label rows=0，禁止生成合成替代行。
- 11/11 单元测试和独立 39/39 检查通过；所有表达值有限，所有 split=`UNASSIGNED`，`training_or_split_created=false`。Boël protein-family mapping 尚未完成；MAGE 共享 infA 的记录不得随机按行拆分。

### PPT 与交接

- 在线主稿：<https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g>。以既有 52 页主稿为基线，追加第 53–58 页，最终服务端 revision=20。
- 新页依次记录证据链、raw-to-clean 对账、MAGE 8,127 signature 复算、Boël 六类表达分布、Kudla 数据缺口、独立验证与 RK-G0 开放边界。
- 最终回读确认 58 页；新页 ID=`pgp/pgg/pgZ/pgS/pgP/pgi`，关键数字和备注齐全，无元素越界；原 52 页内容与结构保持不变，仅第 52 页 XML 末尾存在无语义空白差异。
- PPT 核验记录：`audits/20261118/RK02/ppt_verification.json`。本地下载的 PPT 构建脚本与完整回读仅作工作留档，不作为大型数据资产提交。

### 下一步边界（RK-02 时点）

RK-01、RK-02 已完成；RK-G0 尚未关闭。RK-02 之后先完成蛋白 operational cluster mapping、construct-signature 分组和无泄漏 split；后续 RK-04 实际结果见第 12 节。官方 baseline smoke、dense-v2 与成本协议仍是独立待办，不能把数据清洗或审计数量写成模型性能。

## 12. RK-04 实际完成记录与当前续作入口

### 数据划分与独立复核

- 代码与审计 commit：`99df1d96e041e1f78b67e69210276df66d7b5f6f`；推送后本地 HEAD 与 `origin/a8-rk` 一致，工作树干净。
- 生产脚本：`scripts/a8_build_rk_splits.py`；独立复核：`scripts/a8_rk_verify_splits.py`；测试：`scripts/tests/test_a8_build_rk_splits.py`。完整协议和失败修正记录见 `audits/20261118/RK04/README.md`。
- 输入仍为 25,420 行统一长表，真实 SHA256=`c436b758369018fe0fd121ce6e741993e90a5de80b4706ab87082f7557b6a377`。交接中另一串 `c436784d…` 已证实为转录错误，没有修改输入。
- Boël 6,348 行对应 6,348 个不同蛋白，是跨蛋白天然非同义变体池，不是固定蛋白同义功能文库。MAGE 19,072 行全部属于同一个 infA 蛋白，禁止按 assay 行随机拆分。
- MMseqs2 operational homology clusters 使用 identity=0.50、双向 coverage=0.80；infA 所在簇在任何训练前冻结，其余 Boël 簇只根据序列、簇行数和 seed=20261118 做 deterministic 80/10/10 balancing，不读取标签或模型输出。
- 正式输出：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional/splits/rk04_v1`。Boël train/dev/test=5,079/635/634 行，对应 4,442/556/556 clusters；MAGE 19,072 行全部 `functional_untouched`。
- 共 6,349 条蛋白序列、5,555 个 operational clusters；infA 独立成簇，本阈值下额外冻结的 Boël 行数为 0。MAGE 13,569 个 construct-signature groups 全部 untouched。
- 独立复核 33/33 checks PASS；RK-02+RK-04 组合测试 19/19 PASS。exact CDS、exact/derived protein、source protein ID、operational cluster、construct-signature group、非空 mutation signature 的跨 split 两两重叠均为 0。
- `training_ready=false`、`training_or_model_selection_performed=false`、`functional_untouched_evaluated=false`。长度/GC OOD、train-only 归一化/校准仍 pending；RK-04 不授权功能训练，也不构成功能 OOD、生成器或 SOTA 结果。

### PPT 与证据

- 在线主稿：<https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g>。在 58 页 revision 20 基线上只追加第 59–60 页，slide IDs=`pgn/pgo`，写入后 revision=22。
- 新页记录 split 数量与协议、33/33 独立复核、19/19 测试、六类零重叠、commit 和科学边界；没有把数据准备包装为核心性能。
- `audits/20261118/RK04/ppt_verification.json` 为 PASS：整稿 60 页，前 58 页内容与结构保持不变（第 58 页末尾仅有无语义空白差异），新页文本、备注和画布边界检查通过。
- 失败目录 `rk04_v1_failed_mmseqs_symlink/` 保留为失败证据，不是正式 split。正式 MMseqs2 临时目录为 `/home/codonflow-a8-rk-runtime/rk04_mmseqs_v1`，大型产物未提交 Git。

### 当前下一步

RK-G0 仍未关闭。下一步为 RK-03 机制/自然数据下载与 QC、RK-05 官方强 baseline smoke 矩阵、RK-06 dense B=1 评价器/actual-set schema/独立 scorer/统一成本协议。legacy sparse `anytime_curve` 不得改名冒充 dense-v2；`fixed_dna_folding.py` 在两个工作树的 `src` 下均未找到，不能假设存在。没有功能 OOD 机制增量、CodonFlow-RK 生成器、强 baseline 主结果、untouched 最终评估、time-matched SOTA 或前瞻湿实验结果。

## 13. RK-06 bounded 评价器与真实 actual-set 完成记录

### dense-v2 与 actual-set 评价器

- RK-06a commit=`db3e1667dc593b4e4e9b3605bb0eee6fc249f000`，已推送。新增 `dense_budget_step_auc_v2` 与 `summarize_actual_set`，未改名或修改 legacy sparse `anytime_curve`。
- dense-v2 要求从 B=1 开始每个整数预算都有真实有限向量，面积为 `sum(HV_b, b=1…Bmax−1)/(Bmax−1)`；B=500 时分母 499，Bmax 仅保留为 endpoint。缺失、重复、零预算、非整数、越界、NaN 和错误维度均拒绝。
- actual set 只报告真实输出 Pareto/HV，`curve/area/dense_budget_step_auc_v2=null`；不把外部实际集合伪造成 500 点曲线，重复目标向量不增加 Pareto 点。
- 18 passed + 8 subtests，独立 synthetic 审计 10/10 PASS。手算 `(B,HV)=(1,1),(2,2),(3,3)` 的 dense area=4、AUC=2；旧 sparse 显式同预算时仍由隐含原点得到 area=5.5。该审计只验证协议，不是模型结果。

### C01H6.8b.1 seed0 真实 raw-CDS 复核

- RK-06b scorer commit=`56a62b4415c7e0e442ff064bb6002a4aed00798a`，已推送；真实运行记录 `scorer_code_commit` 相同且 `scorer_code_dirty=false`。scorer/tests 与评价器组合为 22 passed + 8 subtests。
- 原始记录：`/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs/a6_baselines/unique18_s0/C01H6.8b.1_s0.json`；A7 raw recompute：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/eval_outputs/a7_external_actual_budget/C01H6.8b.1/C01H6.8b.1_s0.json`。
- 正确 RSCU=`/home/codonflow-a8-rk/configs/cai_ref_v4train.json`，SHA256=`80592c4eaeab61cdfc86a6f927fb1ef3c4b409b785c73bb466078df9af71bb6f`。第一次误传 D5 RSCU 时在评分前被哈希闸门拒绝，未生成输出；没有把该次尝试记为实验结果。
- 真实输出：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/eval_outputs/a8_rk06_actual_set/C01H6.8b.1_s0.json`，SHA256=`171d0768136f318a580449be9fb367479b0ca38af4137171b06e9fc20029c718`。五方法 LinearDesign/codonGPT/GEMORNA/CAI greedy/uniform synonymous 输出数为 5/100/80/1/100，总计 286 条唯一 CDS；Pareto 点数为 4/14/19/1/11。
- 独立 verifier=`scripts/a8_rk06_verify_actual_set.py`。初版 41/44，差异只在 motif 第四维：A6 保存 raw count，RK06/A7 保存 per-codon penalty。v2 对每条 CDS 独立乘以密码子数还原 legacy raw count，其余三维不变；最终 `audits/20261118/RK06/real_actual_set_C01H6_8b_1_s0_verification_v2.json` 为 44/44 PASS，五方法全 PASS。v1 失败审计保留用于诊断，未删除。
- 所有序列与原始 payload 完全一致；与 A7 raw recompute 的 CAI/MFE/GC/motif 最大绝对差异均为 0；legacy motif 口径还原后与原始报告最大差异也为 0。actual-set HV 独立重算一致，dense 指标均为 null。
- legacy generation seconds 单独保留；未知 wall-clock、hardware、parallelism 为 null，二次复核耗时 `reanalysis_elapsed_s_not_generation_cost` 不冒充生成成本。该结果只是单记录 actual-set smoke，不是方法排名、dense 主结果、功能提升或 SOTA。

### PPT、证据与续作边界

- 真实结果通过后才写入在线主稿：<https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g>。在 60 页 revision 22 基线上只追加第 61–62 页，slide IDs=`pgw/pgl`，最终 revision=24。
- 第 61 页记录 dense-v2 公式、真实整数预算、actual-set null 口径和 10/10、18+8 验证；第 62 页记录 286 条 raw CDS、44/44 PASS、与 A7 最大差异 0、scorer commit 和五方法 actual-set 表，并显式标注 single-record、非排名、非 SOTA。
- `audits/20261118/RK06/ppt_verification_v2.json` 为 PASS：整稿 62 页，前 60 页 slide ID 和语义 XML 不变；原第 60 页仅末尾空白差异；新页文本、备注、公式、表格和画布边界检查通过。
- 完整复现命令、输入/输出 SHA、失败轨迹和剩余 gate 见 `audits/20261118/RK06/README.md`；大型真实输出留在 `/teams`，未提交 Git。
- **当前下一步**：RK-G0 仍不关闭。RK-03 机制/自然数据 QC、RK-05 官方强 baseline smoke、长度/GC OOD 与 train-only 校准仍 pending；RK-06 还需真实 dense B=1…500 轨迹、完整 actual-set baseline 矩阵和统一成本协议。当前没有功能 OOD 机制增量、CodonFlow-RK 生成器、强 baseline 主结果、untouched 最终评估、time-matched SOTA、前瞻湿实验或论文闭环。

## 14. RK-03 RiboMIMO bounded 数据 QC 完成记录

### 来源、完整性与生产修复

- 下载器 commit=`1264f1a577c1c6d2bae1612d7022569828998a7d`、`8b6365f4be7456f089e53bf3089c0ef75c3f06cb`；首版 QC commit=`4b551c850e61791cd7895a2968b23c4d9fe5ca3a`；NP/YP/WP 与 supplement 修复 commit=`81c0cddf3b742a50b7f6901836ab01cba984b7d9`，均已推送。下载器/QC 合计 11/11 tests PASS。
- RiboMIMO 官方仓库固定为 `https://github.com/tiantz17/RiboMIMO` commit `094c693d4df45f4b29f5a3209b31c452a39092a5`。四份真实 CDS–A-site count 矩阵均逐文件匹配固定 commit blob ID；来源对应 Mohammad16=`GSE72899`，Mohammad19-1/2=`GSE119104` 的 `GSM3358140/GSM3358142`，Subtelny14=`GSE53268/GSM1289257`。两个 GSM 是不同样本，不在来源证据不足时推断其技术或生物学重复属性。
- 数据是作者处理后的密码子级 A-site counts，不含 raw reads 或 UTR。官方 positive 过滤为 count>0.5，严格 coverage 为>0.6，归一化均值为 positive positions 的 count mean；不得把该表称为已独立完成 read-level P-site 重比对。
- 首版 v1 把直接 `YP_...` header 误标为 missing key，Mohammad19 每批 223 条受影响；v1 仅保留诊断，不验收。v2 支持 NP/YP/WP 与真实 lcl header，并通过 NCBI E-utilities 精确补回 43/43 个缺失版本化蛋白，unresolved=0；supplement SHA256=`cab89eeb1533ce53aef6091e3996356432cd3cd8972929bf081144749e475325`。
- Mohammad19 两个批次都保留重复 key `NP_417367.1` 的两条不同 source-index CDS 于 all-QC，并从唯一映射 clean 表排除；没有字典静默覆盖。

### v2 结果与独立复核

- production 目录：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/clean/ribomimo_v2`。Mohammad16 raw/clean=1,761/1,175，Mohammad19-1=4,147/1,423，Mohammad19-2=4,147/1,595，Subtelny14=5,614/3,916；合计 15,669/8,109。严格 coverage pass 分别为 1,179/1,427/1,599/3,921，参考蛋白精确翻译分别为 1,756/4,138/4,138/5,609。
- all-QC SHA256=`e8a159490e1277fdb67119c0df55eb4e5b086f619cb37ecb1036047b16ccdd5f`；clean SHA256=`4ea56f898d4126b8a258ffb4f0d75f6272199bcb338b9c22f877329c2cf0a902`；QC summary SHA256=`1f9c5bc42bdc4fde937b2b091967fc50f27d6e09dbc22c69189e54456a977b8b`。
- 独立 verifier=`scripts/a8_rk03_verify_ribomimo.py`，不导入生产 QC 模块，从 raw 与参考 FASTA 重算 accession、翻译、终端/内部 stop、coverage、positive-mean density、全部排除原因、clean 集合、replicate 统计和 artifact hash。最终 `audits/20261118/RK03/ribomimo_independent_verification.json` 为 13/13 PASS，覆盖 15,669 条 raw 与 8,109 条精确 clean 集合。
- verifier 初版把 log1p total-count 相关性也限制在有效 profile 配对，和生产的全有限 total-count 配对分母不同；最终显式分离两种配对口径后 PASS，未放宽容差。失败报告保留为 `ribomimo_independent_verification_v1_fail.json`。
- Mohammad19 shared unique keys=4,145，identical CDS pairs=4,145，both-clean pairs=1,385。双 clean 的 profile Pearson 中位数=0.6146305006、Spearman 中位数=0.5834616124、log1p total-count Pearson=0.9837482972；全部 identical pairs 的 log1p total-count Pearson=0.9831574590。以上是不同 GSM 样本的重现性诊断，不是模型性能或技术/生物学重复因果结论。

### PPT、证据与未关闭边界

- 结果通过后才写入在线主稿：<https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g>。实时基线为 62 页 revision 24，只追加第 63 页 `pgN`，写入后 revision=25。新页记录四批 raw/coverage/reference-exact/clean、13/13 PASS、43/43 蛋白补回和 paired-clean 相关性，并显式标注 processed A-site counts、无 raw-read remapping/UTR、mechanism QC only。
- `audits/20261118/RK03/ppt_verification.json` 为 PASS：最终 63 页，前 62 页 slide ID、标签、属性、文字和递归子元素顺序不变；第 62 页仅末尾空白序列化差异。新页所有关键文字和数字回读齐全。
- 复现命令、raw/reference SHA、失败修正和边界见 `audits/20261118/RK03/README.md`。大型 raw、reference、all-QC、clean 和 supplement 均在 `/teams`，未提交 Git。
- **RK-03 整体与 RK-G0 仍未关闭。** VeloHARMO 官方仓库/论文未提供五物种完整可下载矩阵，不能宣称五物种齐全；RNARL 21 文件最终 manifest 未完成，且 Zenodo 描述与论文 Methods、实际单 CDS 列的来源口径矛盾未解决；CodonTransformer 最终 byte/SHA、1,001,197 pairs/164 organisms 与行级 CDS QC 未验收。UTR–CDS、raw-read/P-site 独立重比对、长度/GC/CAI/MFE/EFE/宿主/蛋白簇完整分布报告仍 pending。当前没有功能训练授权、功能 OOD 机制增量、生成器或 SOTA 结果。

## 15. RK-07 Boël 跨蛋白代理诊断完成记录（bounded）

### 冻结协议、数据与复现

- production commit=`a7250465d5705ae7b72a844d181701eb55582136`；独立 verifier、最终审计和复现 README commit=`e59cc5b651959844cfeb074d564046aac648350a`，均已推送。提交前契约测试再次为 10/10 PASS。
- RK04 的 Boël train/dev/test=`5,079/635/634`，全量特征 6,348 行；19,072 条 MAGE `functional_untouched` 未用于拟合、调参或本次评价。Boël 是跨蛋白天然非同义表达池，本诊断不是固定蛋白同义功能文库 E1。
- 特征为 CAI、GC、全 CDS MFE、MFE/nt、5′前48 nt MFE；ViennaRNA 2.7.2，18°C。full MFE 包含终端 stop，CAI/GC 排除终端 stop，local48 不含 5′UTR。外部 CAI 参考为固定 SHA 的 4,297 条 MG1655 RefSeq CDS，不是 BL21(DE3) 菌株匹配或表达加权参考。
- 组合模型是 train-only 均值/标准差标准化的多项 logistic expected score，L2=0.01、max_iter=2000，无 dev/test 超参搜索；41 次迭代收敛，gradient max abs=`1.1256659202376132e-07`。paired Spearman 按 operational protein cluster 做 1,000 次 bootstrap、95% percentile CI 和五比较 Holm，seed=20261118。
- 复现命令、环境、完整指标与 SHA：`audits/20261118/RK07/README.md`。full feature SHA256=`aabb16bf36912bd761a9c5dd6c1c34797a99d1b2d3aab1b4891e34732b67941b`；final result SHA256=`2ba7b1dc084172e891c8d5775790b7c94ddbca8788d8a88bbb0876f6fd289838`；final predictions SHA256=`f8827eb7aa52d2908e7c00f04dbcd3c926aada654a6f0b16025b14d2d317b7f5`。大型 artifacts 均在 `/teams`，未提交 Git。

### frozen dev/test 结果与负向边界

- dev Spearman：combined=`0.2128696756`，CAI=`-0.0201141125`，GC=`0.1164536224`，full MFE=`0.1014646455`，MFE/nt=`0.1201580570`，local48=`0.1906588302`。combined−local48 点差=`0.0222108453`，95% CI=`[-0.0225304443,0.0669856004]`，Holm p=`0.3276723277`。
- test Spearman：combined=`0.1232386696`，CAI=`0.0026147695`，GC=`0.0963938616`，full MFE=`0.0463484098`，MFE/nt=`0.0949879049`，local48=`0.0776541915`。combined−local48 点差=`0.0455844781`，95% CI=`[-0.0072460994,0.1005014863]`，Holm p=`0.3516483516`。
- **test 五个 paired Spearman 比较经 Holm 后均不显著。** combined−CAI 点差=`0.1206239001`、CI=`[0.0101856517,0.2311940143]`，但 Holm p=`0.1798201798`；CI 下界大于 0 与多重校正不通过必须同时保留，不能称稳健胜出。
- test top10 E=5 enrichment：combined=`1.0319010417`，local48=`0.9803059896`，CAI=`0.7223305086`；combined−local48 的差值 CI=`[-0.378745,0.502100]`，跨 0。GC-high 中 combined/local48=`0.170224/0.195923`；GC-low 中 combined/local48/CAI=`0.070855/-0.079237/0.207418`，不同区域由不同代理占优，失败分层未删除。
- 科学结论仅为：**跨蛋白信号有限且不稳定，组合模型点估计较高但未稳健超过最强单代理。** 没有证明简单代理失效，也不构成固定蛋白同义机制、功能 OOD、SOTA 或 CodonFlow-RK 生成器授权。

### 独立验收与当前续作

- 独立 verifier=`scripts/a8_rk07_verify_proxy.py`，不导入生产模块，逐项核验 protocol/feature/prediction/dev SHA，独立构建参考 RSCU，重算全部 6,348 条 CDS 翻译、CAI、GC、18°C MFE、模型预测、train-only 标准化、univariate fit、logistic 梯度、点指标、1,000 次 bootstrap、Holm、长度/GC 分层和 dev 冻结。
- `audits/20261118/RK07/final_independent_verification.json` 为 **PASS，9/9 checks**，SHA256=`1dab1cf3405a7158bcc0a2d395dbb2882395b7a252ba671c49197b9158cfa815`。raw feature 最大差=0，prediction 最大差约 `1.3322676295501878e-15`，paired CI 最大差约 `2.23e-16`，stratum metric 最大差约 `4.45e-16`，p_raw/p_Holm/optimizer_gradient 差异均为 0。
- final artifact 与 pre-test dev baseline 完全一致，`forbidden_split_used=false`；verifier 和生产代码未因 test 结果而修改。E1 固定蛋白同义任务、RK-G0/G1、长度/GC OOD、完整 baseline、生成器和论文门槛仍未关闭。
- PPT：第 64 页（`pgt`）记录六模型 dev/test 原生分组柱状图、test 点估计最强单代理 GC 与 0/5 Holm 显著增量；第 65 页（`pgX`）记录五个 paired 比较、CAI 的 CI/Holm 区别和 GC 高/低失败分层。65 页 revision 27 实时回读通过，前 63 页 slide ID 与语义 XML 均未改变；服务端仅将 `0.212870` 归一化为数值等价的 `0.21287`。

## 16. RK-03 自然数据进展与 RK-05 RNARL 固定源码审计

### RNARL 数据 QC 与下载收尾（仍非全量验收）

- RNA-aware v2 生产 QC、独立 verifier 和下载修复以 `99f7ca1d`、`747b33e9`、`09b4d814` 推送。真实记录使用 `ACGU/AUG/UGA/UAA/UAG` 和蛋白终端 `*`；`Protein_Length` 包含 `*`。保存原始 `source_cds_rna`，canonical `cds_dna` 只供翻译和泄漏审计。任一成员的 Protein_ID、蛋白序列或 exact CDS 跨 split 重合时整对排除。
- clean-pair 授权以全量文件处理、非空 clean pairs 和整对泄漏排除为前提；raw overlap 仍如实报告，不能把 LinearDesign 生成对称为天然 CDS，也不能恢复 CSV 中不存在的 lambda 身份或授权功能训练/OOD。
- 官方 21 文件精确字节报告 `audits/20261118/RK03/rnarl_official_file_sizes.json` 合计 `714,327,390` bytes，commit=`218c6de4`；持久 finalizer commit=`42ee3984`。精确字节已在无网络激活工具中写回 21 文件配置，合成 21/21 与远端独立 21/21 复核通过，commit=`895458f1`。已知错误 Arabidopsis test final 保留在 quarantine，expected MD5 未改；全量下载、finalization/QC 仍未完成。
- v2 partial smoke 仅覆盖当时已验收的 15 文件：33,924 raw、33,510 clean、16,755 clean pairs；pair-structure 不满足 12 组，2 个 exact CDS overlap pairs 整对排除。它不是 21 文件正式结果，既有 partial 的 bounded-ready 字段也不用于否定后续授权逻辑。

### CodonTransformer 与 VeloHARMO（严格限定来源范围）

- CodonTransformer 流式生产 QC/独立 verifier commit=`1fd6cf02`，真实 1,000 行 prefix smoke/审计 commit=`81ba6525`。此后固定 raw 已完整验收：4,652,159,854 bytes，SHA256=`b319f975f4cd9814bf111a59b80000c001987abf33f3e52e77c4d96d434b4fa9`；下载 manifest complete。全量生产 QC 为 1,001,197 raw rows / 164 organisms、449,655 clean rows / 40 organisms，publisher scope 一致；独立 raw-source verifier **8/8 PASS**，finalization **PASS**。all-QC/clean SHA256 分别为 `3f675500…`、`4ce3999f…`。该子项只授权有边界自然序列分布使用，不授权功能训练/OOD、宿主匹配 CAI、模型或 SOTA 结论；prefix 仍保留为历史 smoke，不替代全量报告。
- VeloHARMO 固定 commit=`38b48079856aeb9d33a1b10844d77aa8f6640032` 的树审计 commit=`dd61dbf1`：14 个 tree entries，仅列两份 E. coli ZIP 条目，没有 yeast/Pseudomonas/Drosophila/human 处理后矩阵。`PASS_SOURCE_TREE_AUDIT_ONLY` 不表示 ZIP 已下载、解压或 QC；五物种完整性、模型训练和 SOTA 均未授权。

### RNARL 官方 baseline 负向可复现性审计（bounded 完成）

- 固定源码 commit=`88428e5d24fb2a16c29cc4dfbbfef51bd990a3d5`；原外部工作树 tracked-deleted 状态未恢复或覆盖。只读 `git archive` 导出到 `/home/codonflow-a8-rk-smoke/rnarl_88428e5d`，10 个源码/示例文件逐字节匹配固定 Git blobs，三个官方 example CSV 均为 9 行。
- 首次真实 smoke 被过新的 `huggingface-hub==2.2.0` 阻断；随后仅在 `/home/codonflow-a8-rk-smoke/rnarl_python_deps` 隔离安装 `transformers==4.46.3`、`huggingface-hub==0.27.0`，项目环境未改。第二次三个模块均成功导入，但这只是隔离 overlay，不是完整官方环境复现。
- 精确 actor 构造缺 `esm2_dim/device`，且无 `TrainingManager.evaluate`；reward 构造缺 `device`；GRPO 缺 `update_old_policy/get_esm_embeddings/sample_actions/calculate_rewards/compute_advantages/calculate_log_probs/calculate_policy_loss/calculate_kl_divergence/log_batch_stats`，另缺 `load_and_preprocess_data/save_model`，`policy_optimization_step` 读取未局部赋值的 `rewards`。
- 独立 verifier 不导入生产 smoke 模块，从固定源码 AST 重算构造参数、类方法、全局函数和 `rewards` load/store，并复核 Git bytes、示例行数、两次运行与隔离依赖。`audits/20261118/RK05/rnarl_official_independent_verification.json` 为 **PASS_NEGATIVE_REPRODUCIBILITY_AUDIT，16/16 PASS**；代码、两次真实 smoke、独立报告和复现 README 以 commit=`1401f63cf4af2e706d6e273e3a733e1d608bedb0` 推送。
- 该结论仅为：**当前公开快照不能直接形成可比 baseline。** 不证明 RNARL 科学方法无效，不表示完成训练、生成、论文指标复现、SOTA 或主比较。若修补公开源码，必须标为新实现，不能改标为未修改的官方结果。

### PPT 与续作入口

- 既有在线 deck 第 66 页=`pgL`，revision 28，标题为 `RK-05 | Public RNARL Snapshot Is Not Directly Runnable`。写入后重新读取真实 smoke/独立报告，数值合同通过；66 页全文回读通过，前 65 页 slide ID 与语义 XML 均未改变。页面明确保留负向边界，无训练/生成/论文指标/SOTA/主比较授权。
- CodonTransformer 全量结果已追加第 67 页=`pgy`，revision 29。页面记录固定 raw、1,001,197/449,655 rows、164/40 organisms、排除原因、重复、8/8 独立 PASS 与 finalization PASS；回读确认前 66 页 slide ID 和语义 XML 未改变，关键数值及 bounded 边界均在。
- 下一步只认真实 finalization 报告、final manifest、raw/quarantine 实物和独立 verifier；partial/prefix/source-tree/negative-availability 审计均不得冒充全量数据或模型性能。RK-03、RK-05 强 baseline 矩阵、RK-G0 及后续机制/生成/OOD/论文 gates 仍未关闭。

## 17. RK-05 ID3 bounded quick-test 与 RNARL 坏残片恢复补丁

### ID3 固定源码、运行协议与工程适配

- ID3 固定 commit=`ed23037e5a74ca10953954c425ac736fb89578a8`，固定 ZIP SHA256=`9566b8cc1492ed6870e792e4b8ffed00c1b08debfb1719b41de872b7107f066f`；DeepRaccess 固定 commit=`1a37235e31e1d5a7d5e2bfb705e3a00f1cdcaa9c`，ZIP SHA256=`dfcdaefe51af5a02a7a62d7a5263a261984156d4365fed86f007dbe408bf7348`。源码在 `/home/codonflow-a8-rk-external/ID3`，大型 ZIP/权重在 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/`。
- 官方 quick-test 的真实协议是 O15263 上 3 类 constraints × 4 variants=12 runs、2 iterations、1 seed、base_seed=42、`enable_cai=False`；README 的 5 iterations 与 fixed preset 不一致。full-12x12 另为 12 proteins ×12 configurations、1000 iterations、1 seed，本轮没有运行。
- 生产 wrapper 只做 UTR 的 T→U 归一化、CPU-only official-force 作用域和 CPU 子进程 CUDA 隔离，没有修改固定上游源码。三次工程失败（UTR 字母、全局 GPU gate、device 未传递）分别保留审计，不包装成科学负结果，也没有停止其他 GPU 进程。
- `cpu_v4` 官方输出目录为 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/id3_official_quick_test_ed23037_cpu_v4`。official summary：12/12 successful、0 failed、total_time=417.591162443161 s、average=34.799263536930084 s；生产审计 `id3_official_quick_test.json` 为 43/43 PASS。

### 独立复核、CPC 缺陷与可用范围

- 独立 verifier v2 不修改官方 payload、不放宽 `2e-5` 容差，重算 24 条离散轨迹记录、36 个 initial/best/final 字段和全部 12 个 final；仅对 18 条唯一序列调用模型。报告为 `BOUNDED_OFFICIAL_EXECUTION_COMPLETE_WITH_CPC_STE_TRAJECTORY_DEFECT`，112/116，四项失败原样保留。v1 108/112 报告另存为失败归档，没有删除。
- 固定源码根因由 AST 定位：`CodonProfileConstraint.forward()` 调用 `CodonPsiFunction.forward()` 时漏传 `beta`，使 CodonPsi 使用默认 0.0；runner 在 `beta==1.0` 分支又把软路径的 `accessibility_loss.item()` 当作离散分数。`cpc-01/11` 的 initial/best 因而与离散 argmax 序列不一致；final 经 deferred validation 离散重算后可用。
- `cpc-01` saved→recomputed initial=`1.7490674257→3.4766187668`，best=`1.6879907846→2.6521768570`；`cpc-11` initial=`1.7701568604→2.4008736610`，best=`1.6919028759→1.9028095007`。这两个实验的 saved initial/best/improvement/trajectory accessibility 以及 `performance_table`、`constraint_comparison`、`variant_comparison` 等 best 聚合全部排除。
- 12/12 final 通过，10 组完整 metric payload 通过，`cpc-01/11` 仅 final 可用；12 组官方 best sequence 均与独立离散 argmin 一致。final count=12、mean=`2.5201897621154785`、min=`1.902809500694275`、max=`3.240176200866699`，与官方 summary 一致；saved std=0 不使用。
- `id3_official_quick_test_finalization.json` 为 11/11 PASS、`ppt_record_ready=true`，同时明确 `all_payload_metrics_verified=false`、`main_baseline_comparison=false`、`sota_claim=false`。证据、独立复核、测试、失败归档和复现 README 以 commit=`51fcda9f95a7770cf1a4ee0f1e8b2956eab719a1` 推送；本地与远端合同测试均 9/9 PASS。

### PPT 与当前续作

- 在线主稿在 67 页 revision 29 基线上只追加第 68 页，slide ID=`pgC`，写入后 revision=30。页面保留 12/12、112/116、11/11、四项 saved→recomputed 数值、final 汇总、根因与排除边界；没有方法排名图。
- `audits/20261118/RK05/id3_ppt_verification.json` 为 PASS：整稿 68 页，前 67 页 slide ID 与语义 XML 全部不变；关键文本、表格、5 段演讲者备注、页码和 bounded 口径回读通过。复现命令与报告 SHA 见 `audits/20261118/RK05/README.md`。
- 该结果只授权单蛋白、2 iterations、单 seed 的 bounded quick-test 记录，不是 full-12x12、多 seed、功能 OOD、主 baseline 排名或 SOTA。RK-05 强 baseline 矩阵仍未关闭；后续运行必须沿用分层指标规则，不得把 CPC×1 的受影响字段重新并入比较。

### RNARL 坏 part 恢复补丁（仅工程验收）

- 旧下载器在每次重试进入 `try` 前对满尺寸 `.part` 校验，MD5/SHA 失败后异常逃出循环，坏残片会永久保留。补丁把满尺寸校验纳入重试；完整或超限且校验失败的 part 使用唯一 `.part.rejected-<time_ns>-<pid>` 名称隔离，不删除证据，再从零重下；成功记录新增 `quarantined_parts`。
- 权威脚本及测试已部署 `/home/codonflow-a8-rk`，项目模块方式运行 10/10 PASS。补丁、测试与 `rnarl_download_recovery_patch.json` 以 commit=`f0db530b2564dbc172ed78eebd610479c4ef7a06` 推送；进行中的 `rnarl_download_manifest.json` 未提交。
- 该审计状态仅为 `PASS_PATCH_TESTS__FORMAL_DATA_COMPLETION_PENDING`。没有启动第二个并发下载器，旧进程已加载的代码不会因磁盘补丁原地改变。正式恢复必须依据唯一 patched downloader 的真实 final manifest、raw/quarantine 实物、21 文件全量 QC、独立 verifier 和 finalization；10/10 工程测试与 15 文件 partial smoke 均不能替代这些证据。
- 后续 pre-recovery 实物审计逐文件重算 bytes/MD5/SHA：18 个已存在 final 全部 verified、0 个 invalid final、3 个 missing final、3 个 part，报告为 `rnarl_pre_final_recovery_audit.json`。为覆盖防御性边界，final 也采用与 part 相同的唯一命名隔离和重试路径，成功记录新增 `quarantined_destinations`；权威 final+part 补丁 11/11 tests PASS，代码与 `rnarl_download_final_recovery_patch.json` 已部署。该 11/11 仍仅是工程验收，不是正式数据完成或 PPT 结果。

## 18. RNARL 下载闭环与 A8 bounded 工作稿

### RNARL 21 文件下载完成，行级验收仍在进行

- patched downloader 已正常结束，主 recovery manifest 为 complete、21 records、0 failures，合计 **714,327,390 bytes**；19 个文件为 `reused_verified`、2 个为 `downloaded_verified`。raw 实物为 21 个 final、0 个活动 part、2 个 `.part.rejected-*`。
- finalizer 的二次全量复用核验写入独立 `rnarl_reverify_download_manifest.json`，没有覆盖首次 recovery manifest；其状态同为 complete、21 records、0 failures。首次恢复记录中的两份 quarantine 信息仍保留，reverify 不带 quarantine 属预期行为。
- 新独立 `scripts/a8_rk03_verify_download.py` 不依赖生产 QC，逐文件重算 21 个 final 的 bytes/MD5/SHA256，并核对 config、recovery/reverify manifests、final 集合、活动 part 和两份坏残片。报告 `rnarl_download_independent_verification.json` 为 **PASS_DOWNLOAD_ONLY_QC_PENDING，8/8 PASS**；两份坏 part 的 MD5 均与官方期望不同，SHA256 也不同于正式 final。
- 旧 `rnarl_finalization.json` 的真实 FAIL 原样保留；新 finalizer 目标为 `rnarl_finalization_recovery_v3.json`。截至本次提交，全量行级 QC、独立 QC verifier、clean-pair 授权和新 finalization 尚未完成，不能把 21/21 下载或 8/8 下载复核写成正式 clean 数据、天然 CDS、功能训练/OOD 或模型结果。
- 上述下载器 finalizer 保留修复、独立下载 verifier、两份 complete manifests、旧 FAIL finalization 和下载独立报告以 commit=`b2661456d14eca0f08c70d9a0d71a489e5b2dde7` 推送。PPT 尚未追加 RNARL 下载页，待正式 QC 与 finalization 验收后再记录。

### A8 工作稿由冻结证据生成并通过独立复核

- `scripts/a8_rk_paper_sync.py` 以远端 A7 为模板生成独立 `paper/CodonFlow_preprint_A8.md`，A7 SHA256 保持 `941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d423`。新增/更新第 3.1 数据事实、3.2 RK04 split、6.2 RK07、6.5 ID3/RNARL baseline 状态和 8.1 证据哈希；A8 SHA256=`fcbb7f3a823fe5d91a678f3ffd5ff708f0772423feefe1232690fa01a24aae80`。
- 同步只引用冻结 JSON，不手工新写性能数字。RK07 明确为 bounded cross-protein diagnostic；ID3 保留 112/116 与 CPC 排除范围；RNARL 公开代码负审计与 21 文件正式 QC pending 分开陈述；主 baseline、功能 OOD、生成器、SOTA 和湿实验均未宣称完成。
- `scripts/a8_rk_verify_paper.py` 不导入生产模块，独立重算 13 份来源 JSON SHA、A7/A8 SHA、关键数字字符串、四个 ID3 retained failures 和 pending/no-SOTA 边界。`paper/a8_rk_paper_independent_verification.json` 为 **PASS，11/11 checks**；同步审计为 `PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE`。
- 生成器、独立 verifier、A8 稿及两份报告以 commit=`b2661456d14eca0f08c70d9a0d71a489e5b2dde7` 推送。A8 仍是不可提交 working manuscript；Fig.1–7、机制、模型、主 baseline、OOD 和前瞻湿实验未闭合。本轮没有因工作稿生成而新增 PPT 页面。

## 19. RNARL 全量 QC、VeloHARMO E. coli 与 A8 v2 同步

### RNARL 正式 pair-table QC 已闭环，科学边界未扩大

- 正式生产 QC 完成 21 文件、260,754 raw rows、256,578 clean rows、128,289 clean pairs。raw 跨 split exact CDS 为 22 keys / 44 rows，protein ID/protein sequence overlap 均为 0；生产按 protein pair 整对排除，clean 独立重扫 exact CDS/protein sequence 均为 0。
- 首次独立 verifier 因把 protein-pair 组写出的 all_qc 错按原始 CSV 行序 zip，真实 FAIL 6/8、max_numeric_delta=0.1337448559670782；recovery v3 同步 FAIL。两份失败报告均保留，未改写历史。
- v2 verifier 改用唯一 `record_id` 精确连接、clean 精确 ID 集合、重复 ID/集合完整性和 `1e-9` 分布容差；不导入生产模块，最终 **PASS 8/8、max_numeric_delta=0.0**。专用 recovery v4 finalizer 重算 21 raw bytes/MD5、download/reverify manifests、生产计数、独立报告和 artifact hashes，并流式重扫 clean，最终 **10/10 PASS**。
- 代码、生产/独立报告、official file sizes 和历史失败以 commit=`d3f18124f97fc7c9f3bf9c9fcb929b5350939971` 推送。状态仅为 `PASS_BOUNDED_LINEARDESIGN_PAIR_TABLE_QC_ONLY`；天然 CDS、lambda 标签/分层、UTR/raw-read、功能训练/OOD、官方模型、主比较和 SOTA 均未授权。

### VeloHARMO 仅闭环 E. coli processed matrix 与 loader

- 固定 commit=`38b48079856aeb9d33a1b10844d77aa8f6640032` 的外层 ZIP SHA256=`68b029b667029827d9c7213249eebcac32e6152d80ef7c0e24e53d8437d5a0ef`。E. coli 矩阵 38,906,084 bytes，SHA256=`71008f948597daff282ccb3e124dd7e4c5b35aa92e2dbe4af43d5725d6fa740f`。
- 生产/独立 QC 为 1,170 raw=clean、0 excluded、0 duplicate gene IDs、modal numeric feature dimension=6；独立 7/7 PASS、max_numeric_delta=0.0，finalization 8/8 PASS。官方 `load_data` 输出 x=`[1170,1520,111]`、density=`[1170,1520,1]`、length=`[1170,1]`，x/density 全 finite；复现报告除 `created_at` 外语义一致。
- 代码与证据 commit=`34286ad4fa2cf74aaee40d7f9f1597052b6a8f1a`。仅物化 E. coli 矩阵与 E. coli/yeast 权重，Pseudomonas、Drosophila、human、yeast processed matrices 缺失；五物种、raw-read 重比对、训练、交叉验证、论文指标、功能 OOD 和 SOTA 未闭合。

### PPT、A8 v2 与当前续作

- 在线主稿第 69 页 `pgx` 记录 VeloHARMO，revision=31；第 70 页 `pgf` 记录 RNARL，revision=32。每次回读均确认此前所有 slide ID 与语义 XML 不变，新页关键数值、边界和备注完整。验证报告分别为 `veloharmo_ppt_verification.json`、`rnarl_ppt_verification.json`。
- A8 生成器/verifier 升级为 v2，新增 RNARL 全量 QC 与 VeloHARMO 证据锚点，A7 不变；A8 SHA256=`f7ea820b98ab946f9f12b6fc28f2095907fd88b4c7346e77870ec87552735e7a`，独立 **13/13 PASS**，仍为 `PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE`。
- 下一步不能把上述数据 QC 写成机制/模型闭环。RK03 仍需 UTR–CDS/raw-read/P-site 和缺失维度报告；RK05 仍需 LinearDesign/CDGB/GEMORNA/codonGPT 等强 baseline 真实矩阵；RK06 仍需 dense 轨迹和统一成本；RK04 长度/GC OOD、RK-G0–G4、生成器、完整 Fig.1–7 和前瞻湿实验仍未关闭。

## 20. LinearDesign 固定官方源码 bounded smoke

### 真实执行与独立复核

- 固定 `LinearDesignSoftware/LinearDesign` commit=`f0126ca89a8b853088b4bccfd2cc8c378d3678be`；codeload ZIP 为 174,011 bytes、32 members、CRC PASS，SHA256=`c27fa2a0beefd6b20359bb9b6a4f2bc43fa70b68aa577f4cd826a4a1051b8944`。
- 在隔离源码目录用 `g++ 9.4.0` 干净构建，binary SHA256=`f1f22901967cb3e0f569ff2332c326800ac355727ab58e377b14514db4fe9688`；官方 README `MNDTEAI` 样例的 sequence/MFE/CAI 与文档一致。没有回退旧主工作树的修改源码或二进制。
- 冻结 C01H6.8b.1（135 aa），λ=`0/0.5/1` 产生 3 条唯一同义 CDS。官方 MFE=`-270.60/-269.20/-265.20 kcal/mol`、CAI=`0.761/0.791/0.820`，逐次 wall time=`8.06250987527892/8.108563175890595/8.150544322095811 s`，总耗时 `24.321617373265326 s`。
- 独立 verifier 从 raw stdout 重算翻译、CAI、MFE、结构、成本和科学边界，最终 **10/10 PASS、max_numeric_delta=0.0**；finalization **8/8 PASS**。官方三位小数 CAI 的最大 rounding delta=`0.0004413928951978452`，两位小数 MFE 最大 rounding delta=`1.2207031261368684e-05`。

### v1 失败保留与 v2 双口径

- v1 的 λ=0 官方执行成功，但生产在独立 MFE gate 真实失败；λ=0.5/1 未执行，production report 未写出。默认 ViennaRNA `dangles=2` 得 `-274.29998779296875`，显式 `dangles=0` 得 `-270.6000061035156`，与官方 `-270.60` 一致；两种口径的 structure 与官方 structure 完全一致。
- `lineardesign_official_smoke_v1_failure.json` 和独立 v1 raw stdout/stderr 原样保留。v2 改用独立 output dir，以 `dangles=0` 核对官方 MFE，同时记录默认 `dangles=2` MFE/structure；没有放宽容差、覆盖失败或把 v1 写成完整三 λ 结果。

### 证据、复现与边界

- 生产报告：`audits/20261118/RK05/lineardesign_official_smoke_v2.json`；独立报告：`lineardesign_independent_verification_v2.json`；finalization：`lineardesign_finalization.json`。
- 物化/构建报告：`lineardesign_materialization.json`、`lineardesign_build.json`、`lineardesign_build.log`；完整复现命令见 `audits/20261118/RK05/README.md`。生产、独立 verifier、finalizer 和 11 个测试均在 `scripts/`、`tests/`。
- 固定归档和 raw official outputs 留在 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/`；代码、报告与提交留在 `/home`。
- 状态仅为 `BOUNDED_LINEARDESIGN_OFFICIAL_SMOKE_VERIFIED`。统一 actual-set 七 λ、dense budget、主 baseline、功能 OOD 与 SOTA 均未完成；CDGB 尚未建立可核验的官方来源/commit/build/execution artifact，通用搜索未命中不等于方法或实现不存在。
- A8 生成器/verifier 已升级为 v3，新增 LinearDesign 固定源码、三 λ 指标、双 dangles 和 v1 retained failure；A7 未改。A8 SHA256=`d779ad4dd3d9d971378aa82fc1366e6eaa7e53a74a49bce1a5b227e609b088dd`，独立 **14/14 PASS**，仍为 `PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE`。
- 代码、独立报告、A8 v3 和复现文档已以 commit=`8be5369081b614beede261b7430f1230e0783e37` 推送。既有在线主稿随后追加第 71 页 `pgB`、revision=33；回读确认前 70 页 slide ID 与语义 XML 全部不变，新页数值、边界和 4 段备注完整。PPT 验证报告为 `audits/20261118/RK05/lineardesign_ppt_verification.json`。

## 21. CDGB 来源身份负向审计、A8 v4 与 PPT 第 72 页

### 来源审计结论与冻结证据

- 候选题名为 `CDGB: a deep learning framework for codon de-optimization directed by the protein representation model`，候选 URL 中的 DOI 为 `10.1093/bib/bbaf332`。Crossref 直接 DOI 查询与 OpenAlex 均把该 DOI 映射到 **Multimodal zero-shot learning of previously unseen epitranscriptomes from RNA-seq data**（ExpressRM），Briefings in Bioinformatics volume=26、issue=4，而不是 CDGB；候选身份存在直接冲突。
- 九条 API 查询全部完成并冻结原始 JSON、bytes 和 SHA256：Crossref candidate-title=20、Crossref CDGB title=3、OpenAlex CDGB title=7、Europe PMC CDGB title=4、Europe PMC codon-deoptimization title=2，学术精确候选题名匹配总数=0；GitHub CDGB+codon=0、CDGB+protein-representation=0，宽 codon-deoptimization=14 个其他项目，不能建立官方所有权。第九个响应是直接 Crossref DOI 冲突证据。
- raw responses 位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/cdgb_source_audit_v1/`。生产报告 `cdgb_source_audit.json` SHA256=`dd8f0a8840bbf655d2731a60b7c5e7fb296665a29f4e7eb229edbc43e1e3f691`；独立报告 `cdgb_source_independent_verification.json` SHA256=`964e782264c8101dc55cced708be3834f66b02488f3bc0e838b8724ce4598980`；finalization `cdgb_source_finalization.json` SHA256=`dc49cdc6540d9f45f2cd040518e660871fc3b0dc109e929f92f7a541e4df66b2`。
- 独立 verifier 不导入生产模块，从冻结 raw responses 重算题名归一化、DOI 冲突、学术精确匹配、GitHub 计数和科学边界，最终 **8/8 PASS**；finalization **6/6 PASS**，单元测试 **8/8 PASS**。状态为 `SOURCE_IDENTITY_UNRESOLVED_OFFICIAL_EXECUTION_NOT_AUTHORIZED`。
- 未建立官方 repository、immutable commit、source build 或 execution；official sequence-output count=0、performance-result count=0。该负向结果不证明 CDGB 方法无效或实现不存在，也不授权主 baseline、功能 OOD 或 SOTA。未来执行前必须获得权威文献身份、作者/出版方链接的官方仓库、固定 commit、官方构建说明和最小输入。

### A8 v4 与 Git 证据

- A8 生成器/verifier 升级为 v4，新增 CDGB 三份冻结证据及第 6.5 节来源身份段落；A7 SHA256 仍为 `941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d423`。A8 v4 SHA256=`cc74dee890b1cf813ece45b9d62f32948046b68272915747f13c7d23fbc8df59`，独立 **15/15 PASS**，状态仍为 `PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE`。
- 生产/独立/finalization 脚本、测试、三份报告、RK05 README、A8 v4 和同步审计以 commit=`ea806ff10f331ae2831cef9c9d15ddb2c3252902` 推送。完整复现命令见 `audits/20261118/RK05/README.md`；raw API 响应不提交 Git。

### PPT 写后验收与当前续作

- 在线主稿在 71 页 revision 33 基线上只追加第 72 页，slide ID=`pgR`，写入后 revision=34。页面包含 9/9 查询、0 个学术精确题名匹配、8/8 独立 PASS、6/6 finalization、Crossref/scholarly/GitHub 三行证据表、实际 DOI 题名和零执行边界；没有性能图或方法排名。
- `audits/20261118/RK05/cdgb_ppt_verification.json` 为 **PASS，10/10 checks**：整稿 72 页，前 71 页 slide ID 与 ID-independent 语义 XML 全部不变；新页关键文本、精确 4×3 表格、4 段演讲者备注、页码和画布边界全部通过。baseline/readback XML 与完整响应保存在 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/cdgb_ppt_verification_v1/`。
- 操作记录：第一次本地 slide-only preflight 因本地证据 JSON 相对路径不存在而未完成，但同一 shell 的后续 add 请求已返回 `pgR`；没有重复追加。最终验收不依赖该 incomplete preflight，而依赖远端冻结报告与独立整稿写后复核。
- CDGB 完成时在线主稿状态为 **72 页、revision 34、末页 `pgR`**。本 PPT 验证报告、REGISTRY/tasks 和本 handoff 更新随后续文档提交推送。RK-05 强 baseline 主矩阵、RK03 剩余机制维度、RK06 dense/full matrix、功能 OOD、生成器、SOTA 和湿实验仍未关闭；EnsembleDesign 后续状态见第 22 节。

## 22. EnsembleDesign 官方 bounded smoke、A8 v5 与 PPT 第 73 页

### 固定来源、真实执行与独立复核

- 官方 `LinearFold/EnsembleDesign` 固定 commit=`cd9324f9574a754063d421e76670bc9fd7555324`；codeload ZIP 为 325,276 bytes、75 members、CRC PASS，SHA256=`0179bde9afb45b891c51c4577ee5c5895b1991528f3a1ac7e626450c5be474a2`。源码位于 `/home/codonflow-a8-rk-external/EnsembleDesign-cd9324f9574a754063d421e76670bc9fd7555324`，固定归档、构建日志和 raw outputs 均在 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/`。
- 三次 `make` 分别记录返回码和日志；首轮报告进程因未把隔离 `python-gflags==3.1.2` 加入自身 `sys.path` 而未生成构建报告，原始日志保留，随后三次 confirmation build 完成，最终 `BUILD_COMPLETE`。官方源码未修改。
- bounded 参数为 beam_size=100、lr=0.03、epsilon=0.5、num_iters=3、num_runs=2、num_threads=4。官方 example v2 为 3 records/6 runs/4 unique CDS，总耗时 `8.044502989854664 s`；三条 best EFE=`-18.00/-43.71/-70.29 kcal/mol`，与 README 精确一致。C01H6.8b.1 为 1 record/2 runs/2 unique CDS，总耗时 `52.65070143900812 s`，best run=1、EFE=`-269.97 kcal/mol`，135 aa 对应 405 nt。
- 官方输出不含额外 stop。首轮 example wrapper v1 错假设额外 terminal stop，官方进程 returncode=0 但包装器 stop-gate 真实失败；v1 raw/report 原样保留。v2 只修正该包装器契约，源码、参数和 scorer tolerance 未变。
- EFE 由官方 LinearPartition `-V -d0 -b0` 与 ViennaRNA 2.7.2、37°C、`dangles=0` 独立核对。**EFE 不是 LinearDesign MFE，不能直接排名。** example/C01 独立 verifier 均从 raw stdout/results/run 文件重算，分别 **13/13 PASS**；单元测试 **11/11 PASS**，finalization **11/11 PASS**。

### A8 v5、复现和 Git 证据

- A8 生成器/verifier 升级为 v5，新增五份 EnsembleDesign 冻结来源、example/C01 EFE 表、成本、双独立复核、finalization 和失败/边界。A7 未改；A8 v5 SHA256=`505c42f61e21ab1cb03f54ee661adf005f6fa996e17ffec5ae6ed481fe2f8eca`，独立 **16/16 PASS**，状态仍为 `PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE`。
- 生产/独立/finalizer/测试、物化/构建/执行/复核/finalization 报告、RK05 README、A8 v5 和同步审计以 commit=`5ba0a8848ccf701f5e070b61fe357ca6d05eeb3c` 推送，本地与 GitHub `a8-rk` HEAD 一致。复现命令中的 C01 benchmark 路径已按冻结报告和实际文件 SHA 核对为 `/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/a6_benchmark/unique18.fasta`。

### PPT 写后验收与当前续作

- 结果经独立验收后才写入在线主稿。候选页 preflight **8/8 PASS**；在 72 页 revision 34 基线上只追加第 73 页，slide ID=`pgO`，写入后 revision=35。页面含 8/8 runs、6 unique CDS、双 13/13、11/11 四个 KPI，seq1/seq2/seq3/C01 四行 EFE 表、bounded 参数、aggregate wall time、v1 retained failure 和 EFE≠MFE 边界。
- `audits/20261118/RK05/ensembledesign_ppt_verification.json` 为 **PASS，10/10 checks**：整稿 73 页，前 72 页 slide ID 与 ID-independent 语义 XML 全部不变；新页表格由冻结 JSON 重算，4 段备注、页码、画布边界与科学边界通过。baseline/readback XML、候选页和完整响应保存在 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ppt_ensembledesign_v1/`。
- PPT verifier 与验证报告以 commit=`9986974ac46cc65aaf0708e509e9ad5ff2cfb2af` 推送，本地与 GitHub `a8-rk` HEAD 一致。当前在线主稿真实状态为 **73 页、revision 35、末页 `pgO`**。
- 本任务只关闭官方 example + 单 C01 的 bounded smoke。没有 matched LinearDesign comparison、dense budget、完整强 baseline 主矩阵、功能 OOD 或 SOTA；RK03 剩余机制维度、RK06 dense/full matrix、CodonFlow-RK 生成器、完整 Fig.1–7 和前瞻湿实验仍未关闭。

## 23. CodonTransformer 官方 bounded smoke、A8 v6 与 PPT 第 74 页

### 固定来源、真实 GPU 执行与独立复核

- 官方 `Adibvafa/CodonTransformer` 固定源码 commit=`4a447b01dab860feb81b647ff1ff88ad598517f4`，模型固定 Hugging Face revision=`9744dcc920d813066391fc828d7a590207f148e8`。8 个模型文件全部按 API bytes 核对；`model.safetensors` 为 358,342,232 bytes，SHA256=`23994e1e7324e78c9d9da71040e8677c0a635287cf1c7c9ea5096b7eadc44dfd`。固定源码 ZIP SHA256=`85fe55a10ad061b62034aaed90bce06d4be3eb9a2e25d40030db359b0d1fd132`，CRC/path/symlink 安全断言通过。
- 官方执行使用隔离环境 `/home/codonflow-a8-rk-smoke/codontransformer_venv`：Python 3.10.22、torch 2.14.1+cu132、transformers 4.40.2、NumPy 1.26.4，GPU=NVIDIA GeForce RTX 5090。错误 `CAI-PyPI==1.0.4` 安装尝试、缺失 scikit-learn 的导入失败和首次输出目录保护失败日志均保留；正确版本为 `CAI-PyPI==2.0.1`，最终 `OFFICIAL_IMPORT_PASS CodonTransformer.CodonPrediction`。
- 生产包装器调用官方 `predict_dna_sequence`，`deterministic=True`、`attention_type="original_full"`、organism=`Escherichia coli general`。官方 README example 与 C01H6.8b.1 分别执行 default 和 `match_protein=True`，共 4 次真实推理。4/4 输出为合法同义 CDS，仅一个 terminal stop、无 internal stop；default 与 constrained 各 2/2 legal，总计 2 unique CDS。官方 example default 与 README 序列逐碱基一致；两种模式对每个蛋白输出相同，因此不能声称约束模式带来收益。
- 模型加载=`4.438656704965979 s`，四次推理合计=`2.0327787059359252 s`，首次 example 含 warm-up，不是 time-matched 成本。独立 verifier 不导入生产模块，重新加载同一固定权重并逐条重跑四次推理，所有序列精确一致，**13/13 PASS、max_numeric_delta=0.0**；单元测试 **8/8 PASS**，finalization **10/10 PASS**，状态仅为 `CLOSED_BOUNDED_OFFICIAL_SMOKE`。科学证据、脚本和报告以 commit=`210d2f4c13cddc7144d1939d0ae76162d2016c8a` 推送并核对 GitHub HEAD。

### A8 v6 与证据边界

- A8 生成器/verifier 升级为 v6，新增 materialization、production、independent、finalization 四份冻结来源及哈希，写入四次推理表、固定源码/模型、4/4 legal、2 unique、双模式相同输出、13/13 独立复核和 10/10 finalization。A7 未改；A8 v6 SHA256=`1ac702be2b38900346064ebbc56a4b20a461089f317078db1df08c73774e0d35`，独立 **17/17 PASS**。论文同步同时修正了旧 verifier 将 EnsembleDesign 检查字典直接转为布尔值的问题。commit=`f479955fefa034c5a5fde84c5f7ab37d85cf0044`。
- 本结果仍只是官方 example + 单 C01 的 bounded smoke；没有 matched MFE/EFE、dense budget、完整强 baseline 主矩阵、功能 OOD 或 SOTA。default/constrained 输出相同不等于约束选项无效，也不证明性能提升；短推理耗时含 warm-up，不得直接用于公平速度排名。

### PPT 写后验收与当前续作

- 结果经独立验收后写入既有在线主稿。候选页首版因两处模式名与冻结 JSON 不一致得到 preflight 7/8 FAIL，保留为 v01；修正为 `official_default` 后 v02 preflight **8/8 PASS**。在 73 页 revision 35 基线上只追加第 74 页，slide ID=`pgU`，写入后 revision=36。
- `audits/20261118/RK05/codontransformer_ppt_independent_verification.json` 为 **PASS，10/10 checks**：整稿 74 页，前 73 页 slide ID、顺序与 ID-independent 语义 XML 全部不变；新页四行表由冻结 JSON 重算，4 段备注、页码、画布边界和科学边界通过。baseline/readback XML、两个候选版本、preflight 和完整响应保存在 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ppt_codontransformer_v1/`。
- PPT verifier/preflight 与验证报告以 commit=`0c33d35580c02ae06932083200bc6fbd5dd3882c` 推送，本地与 GitHub `a8-rk` HEAD 一致。当前在线主稿真实状态为 **74 页、revision 36、末页 `pgU`**。本 handoff、REGISTRY、tasks 和 RK05 README 随后续文档提交推送。
- RK-05 强 baseline 主矩阵仍未关闭；RK03 剩余机制维度、RK06 dense/full matrix、真实功能 OOD、CodonFlow-RK 生成器、完整 Fig.1–7、SOTA 和前瞻湿实验仍未关闭。未跟踪的 `audits/20261118/RK05/id3_independent_verification.pid` 不是科学结果，不应提交。

## 24. VeloHARMO 官方 bounded smoke、A8 v7 与 PPT 第 75 页

### 固定来源、真实双设备执行与独立复核

- 官方 VeloHARMO 固定 commit=`38b48079856aeb9d33a1b10844d77aa8f6640032`；固定归档为 31,429,853 bytes，SHA256=`68b029b667029827d9c7213249eebcac32e6152d80ef7c0e24e53d8437d5a0ef`。E. coli processed matrix 为 38,906,084 bytes，SHA256=`71008f948597daff282ccb3e124dd7e4c5b35aa92e2dbe4af43d5725d6fa740f`。E. coli/yeast fold-0 权重均为 `models:BiGRU`，输入维度=105、hidden=128、2 层、477,185 参数，SHA256 分别为 `a22badecac33e6c34f736dbf18274982b734ebb293cf1d632aff65ac6af9f35d` 与 `b73691027121c1cadb3a4ed3b45c04ab4ca477163b0e39b5b4e3bdfdc52c5ddc`。官方整对象 checkpoint 只在固定且已校验的文件上使用 `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1`。
- 从 1,170 条 E. coli 记录中确定性选取 7 条最短合格记录：至少 30 codons、序列/count/feature 长度一致、count finite 且非常数、至少一个 count>0.5，按长度、record ID、source index 排序。子集 SHA256=`ba42db8a99b3d35e87c5c8c57d9333a7c01d62eff85aa8b3309c1bbdefef93ac`；记录为 A5A616/P03061/P62522/P0ADF3/P0DSF5/Q2EES6/C1P620。GA 原生硬编码 subset index=6，因此目标为 C1P620，36 codons。
- 未修改官方 `VeloGRU/run.py test` 在 `cuda:0` 返回码 0，feature dimension=105、records=7、parameters=477,185，wall=`4.6736052692867815 s`。mean Pearson=`0.6044025421142578`，官方 SD=`0.17268328368663788`；独立直接重算 mean 相同、SD=`0.17268326878547668`，`metric_delta=1.4901161193847656e-08`。这是完整 processed matrix 上的长度选择子集诊断，不是 held-out、OOD 或五物种性能。
- 真实 GA 为 242 行，SHA256=`9631c15d7d373584e519966eb9382db34dba191ca21c1fedf599e4c4407299af`。未修改入口真实返回码 1，`ModuleNotFoundError: No module named 'Mimo_data'`，失败日志原样保留。生产 wrapper 只做 7 处可审计替换：缺失导入、矩阵路径、两个权重路径、输出图路径、population 与 generations 预算；算法主体不变。population=8、generations=2、seed=20261118，GA 在 CPU 单线程运行，wall=`1.2729171668179333 s`。
- GA 目标是原生 E. coli 模型参考速度谱与 yeast 模型候选速度谱的 Pearson 相似度，不是实验功能。native/start/best 适应度分别为 `-0.02560763992369175 / 0.34598612785339355 / 0.34598612785339355`；start 与 best 序列完全相同，`best_minus_start=0`、`start_to_best_improved=false`。`best_minus_native=0.3715937677770853` 仅描述初始随机候选相对原生序列的预测谱目标差，不是 GA 迭代提升或实验功能增益。2/2 序列为合法同义 CDS，unique=2；原生矩阵没有 terminal stop，未套用 C01 的额外终止子合同。
- 独立 verifier 不导入生产模块，重新执行固定 GA、重算双模型速度谱、复核原始 GA 失败、7 项补丁、输入子集、序列/适应度、官方 GPU 预测、float32 聚合、环境、FASTA 和 artifacts 哈希，结果 **17/17 PASS、max_numeric_delta=0.0**。单元测试 **10/10 PASS**，finalization **13/13 PASS**，状态仅为 `CLOSED_BOUNDED_OFFICIAL_SMOKE`。早期 stop-contract、补丁路径/引号、float32 密度容差及 CUDA/CPU 路径失败均保留；最终密度量化最大差 `1.9747801438541046e-07`，明确使用 `5e-7` 容差。科学证据 commit=`8fce8dcaf5749d838f2378424b50042a8970cc27`，已推送并核对远端。

### A8 v7、复现记录与科学边界

- A8 生成器/verifier 升级为 v7，新增生产、独立和 finalization 三份冻结 JSON 及哈希锚点，并设置硬门槛：官方 test 返回码 0、105 维、7 记录；未修改 GA 失败与 7 项补丁保留；2/2 合法同义；best=start 且零迭代提升；独立 17/17、finalization 13/13；禁止宣称五物种、主矩阵、功能 OOD 或 SOTA。A7 未改；A8 v7 SHA256=`078228450f69c1efe6b31f7bbf7dba0d01d004c9aecdf2f330f4ad32c985fe6d`，独立 **18/18 PASS**，状态仍为 `PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE`。commit=`9948b2ec251ae593ef9a864206cdd20672134923`。
- 生产、独立 verifier、finalizer、单元测试、v1–v4 测试日志和完整复现命令见 `audits/20261118/RK05/README.md`。最终 raw 输出位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/veloharmo_official_smoke_38b480_v1/`；独立 raw 输出位于同目录级别的 `veloharmo_independent_v1/`。早期失败目录与 driver 日志均保留，大型数据、权重和 artifacts 未提交 Git。
- 官方 test/原生预测使用 `cuda:0`，GA 使用 CPU，二者耗时与数值不得混作同一公平成本口径。E. coli/yeast fold-0 权重存在不等于五物种模型闭环；正式训练/交叉验证、研究 OOD、完整 harmonization 主结果和公平成本仍未完成。

### PPT 写后验收与当前续作

- 结果经独立验收后才写入既有在线主稿。实时基线为 74 页、revision 36、末页 `pgU`，只追加第 75 页 `pgh`，写入后 revision=37。页面记录 mean=`0.604403`、SD=`0.172683`、GA iterative gain=`0.000000`、独立 17/17、finalization 13/13，并用四行表区分官方 CUDA test、native reference、GA start 和 GA best；明确 start=best、无迭代提升，以及五物种、主矩阵、功能 OOD、SOTA 未关闭。
- `audits/20261118/RK05/veloharmo_ppt_independent_verification.json` 最终为 **PASS，10/10 checks**：整稿 75 页，前 74 页 slide ID、顺序与 ID-independent 语义 XML 全部不变，新页数值、表格、备注、画布边界和科学边界通过。readback XML SHA256=`863fb78d364a05b21a9ceceb133f72aa8751d404643d8f9b58b877953164ae12`。首次 9/10 失败仅由第 74 页 `</slide>` 后 tail whitespace 触发；逐项 diff 证明旧页标签、属性、文字和子元素未变，失败报告与 diff 均保留。
- PPT verifier/report 以 commit=`49ed134d4966fcc5c8d70c00c654cd414b898c51` 推送并核对 GitHub 远端。当前在线主稿真实状态为 **75 页、revision 37、末页 `pgh`**；raw artifacts 位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ppt_veloharmo_v1/`。
- 本任务只关闭 bounded official smoke。RK-05 强 baseline 主矩阵、RK03 剩余机制维度、RK04 长度/GC OOD 与 train-only 校准、RK06 dense/full matrix、真实功能 OOD、CodonFlow-RK 生成器、完整 Fig.1–7、SOTA、前瞻湿实验与可投稿论文仍未关闭。

## 25. RiboMIMO 官方 bounded training、A8 v8 与 PPT 第 76 页

### 固定来源、真实训练与独立复核

- 官方 RiboMIMO 固定 commit=`094c693d4df45f4b29f5a3209b31c452a39092a5`；codeload 归档 SHA256=`0f46f4469b1f6d06e967ffab39dce0c25b7e52fc4923f60e3ac106dbe811a162`。原始 partial-clone 工作树不完整，最终只使用 `/home/codonflow-a8-rk-external/RiboMIMO-094c693d4df45f4b29f5a3209b31c452a39092a5` 的固定归档恢复源码；归档内四份矩阵与 RK03 已核验 raw 逐 SHA 一致。
- 冻结协议为 Mohammad16 最短 20 条合格 unique-name 记录、一次 repeat、2 folds、2 epochs、batch=4、seed=20261118、官方 random gene split、单线程 CPU、97 维输入、hidden=256、depth=2。子集 SHA256=`bd2bcd2566d7d02271c35548c18695a8ec151377568c6422a24a0f60b864998b`；每折 train/valid/test=9/1/10，派生 split seed=136。作者 prediction pickle 未用作本次训练输出。
- 未修改入口在 NumPy 变长数组处失败；只修 ragged array 后又在 padding 的 object dtype 转 Tensor 处失败。探索性 LongTensor 补丁经 unseeded 对照证明非必要，最终 runtime 只保留六项兼容替换：五处 ragged `dtype=object` 和一处 numeric padding `dtype=float`，模型、优化器、split 与训练逻辑不变。v1–v4 原始目录、driver logs、环境误读的 superseded 报告均保留；最终 v4 从真实训练进程确认 CPU、单线程、deterministic=true、无可见 GPU。
- 两个最佳验证 checkpoint 各含 22 个参数张量、1,860,356 参数。fold-0 的 163 个 positive masked positions 上，独立 checkpoint 重算 R²/MSE/Pearson=`-0.0909230222/2.5958190157/0.0077743819`；fold-1 的 185 个位置为 `-0.0033395900/2.0020711321/0.0228037406`。两折 mean=`-0.047131/2.298945/0.015289`，population SD=`0.043792/0.296874/0.007515`。这些是极小 bounded 子集的执行诊断，不是论文性能复现、预测效用或方法排名。
- 独立 verifier 不导入生产模块，重新筛选并重训两折，checkpoint 张量 `max_abs_delta=0.0`，总体 **17/17 PASS**；最大指标差 `4.099541271911436e-07` 与官方日志六位小数一致。finalization **13/13 PASS**，最终单元测试 **10/10 PASS**。生产报告 SHA256=`ce79120bef6f25aefcd9e3b5e440c764a300f78c6da3d6cecd01c9f55bf4a9b6`，独立报告 SHA256=`d97874904cca4b4e1589ee4eb4daac482450762c7b9d8dee840c0756eb443195`，finalization SHA256=`69c532e20612b7d8de83486f7c2ced7961ac416f7c3e5218946f2804956407d8`。科学证据与 RK05 README commit=`a6e119650c4dd52110849b43aa377cbbd1e422b0`，已推送并核对远端。

### A8 v8、复现记录与科学边界

- A8 生成器/verifier 升级为 v8，纳入 RiboMIMO 三份冻结 JSON 及哈希、bounded 训练协议、两折指标、六项兼容替换、17/17 与 13/13 核验；A7 未改。A8 v8 SHA256=`7f1a6d5ce3f5b17d6beb1a79958e8b91e30765fb68b58dd225635b8a696c4733`，独立论文核验 **19/19 PASS**，状态仍为 `PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE`。commit=`56f9c4d559dc29f94b295f2500f7c0a3af1410e4`。
- 最终生产 raw 位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ribomimo_official_smoke_094c_v4/`，独立 raw 位于 `ribomimo_independent_v1/`；完整失败史、证据哈希和复现命令见 `audits/20261118/RK05/README.md`。大型矩阵、归档、checkpoint、runtime copy 和日志均未提交 Git。
- 本结果只关闭 bounded official training smoke。完整官方 10-fold/100-epoch、同源/蛋白/study OOD、功能 OOD、统一成本强 baseline 主矩阵、CodonFlow-RK 生成器、SOTA、前瞻湿实验和可投稿论文均未关闭；负 R² 与近零 Pearson 不得包装为可推广预测性能。

### PPT 写后验收与当前续作

- 结果和 A8 v8 经独立验收后才写入既有在线主稿。实时基线为 75 页、revision 37、末页 `pgh`；候选页 preflight **8/8 PASS** 后只追加第 76 页，slide ID=`pgG`，写入后 revision=38。页面展示两折与汇总 R²/MSE/Pearson、20 genes、1,860,356 参数、17/17 独立 PASS、13/13 finalization，并显式标注 bounded、非完整协议、非 OOD、非主矩阵、非 SOTA。
- `audits/20261118/RK05/ribomimo_ppt_verification.json` 为 **PASS，11/11 checks**：整稿 76 页，前 75 页 slide ID、顺序与 ID-independent 语义 XML 全部不变；新页数值、四行表、4 段备注、画布边界和科学边界通过。候选、baseline/readback XML 与完整响应位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ppt_ribomimo_v1/`。PPT verifier/report commit=`c317eb6755a6d6f6543b6297a0fdbc417186aa4d`，已推送并核对 GitHub 远端。
- 当前在线主稿真实状态为 **76 页、revision 38、末页 `pgG`**。RK-05 强 baseline 主矩阵、RK03 剩余机制维度、RK04 长度/GC OOD 与 train-only 校准、RK06 dense/full matrix、真实功能 OOD、CodonFlow-RK 生成器、完整 Fig.1–7、SOTA、前瞻湿实验与可投稿论文仍未关闭；遗留 `id3_independent_verification.pid` 不属于本任务，不应提交。

## 26. iXnos 官方 bounded prefix-read training、A8 v9 与 PPT 第 77 页

### 固定来源、真实 reads、训练与独立复核

- 官方 iXnos 固定 commit=`1ea2337dd24d1e6fa3859f08573e99f02512810f`，归档 SHA256=`523e6105acdf52d792d96c272594655b2765a9c369892f78bac9452f7d20c1c8`。真实输入为 ENA `SRR1049521` 的前 **1,000,000 条完整 reads**，不是随机抽样或完整 run；官方 trimming 后 864,464 条，756,168 条进入转录组比对，723,724 条至少一个 alignment。使用官方 P-site offsets、paralog filtering 和 simple uniform multimapping weights，未复现 RSEM。
- bounded 协议为 seed=20261118、20/10 train/test genes、min counts=50、min codons=20、2 epochs、只使用预先指定的最终 epoch；官方 760-feature tanh 网络含 152,401 参数，train/test codons=`3816/1963`。最终 R²/MSE/Pearson/Spearman=`0.0282723404/0.9106269870/0.1952275552/0.2159973420`；train-mean baseline MSE=`0.9371216081`、R² 约为零。以上只说明 bounded 流程可训练，不是论文性能、主 baseline 排名或 SOTA。
- 独立 verifier 不导入生产 driver，重新处理并重训，**27/27 PASS**，target/prediction/checkpoint tensors 最大差均为 0；finalization **16/16 PASS**、单元测试 **10/10 PASS**。首次 `_tkinter` 失败保留，成功运行只增加 `MPLBACKEND=Agg`。独立 verifier 未重跑 Bowtie；另一次生产重跑确认 prefix/trimmed 字节一致，1,255,357 条完整比对记录 canonical sort 后一致，raw SAM 顺序与 run-specific PG 路径差异仍保留。科学证据 commit=`645bc22f179dabc35f74f43144f0462de8f4a228`。

### A8 v9、PPT 写后验收与当前续作

- A8 生成器/verifier 纳入 iXnos 三份冻结 JSON 及哈希、真实 reads、bounded 协议、最终指标、常数 baseline、27/27 与 16/16 核验；A7 未改。A8 v9 SHA256=`51b049bd9e0062d013f76b49f13b0312eb9ab204e153b4c994ad17e99abb3b79`，独立论文核验 **20/20 PASS**，状态仍为 `PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE`。commit=`12d044d69519ffad8127cc9642372624b4c0a153`。
- 实时 PPT 基线为 76 页、revision 38、末页 `pgG`。候选初次 preflight 7/8 仅由检查器大小写字符串不匹配引起，失败报告保留；修正后 **8/8 PASS**，只追加第 77 页 `pgW`，revision=39。`audits/20261118/RK05/ixnos_ppt_verification.json` 为 **PASS，11/11 checks**：前 76 页 slide ID、顺序与 ID-independent 语义 XML 全部不变，新页生产/独立/常数 baseline 表、KPI、4 段备注、画布边界和科学边界通过。raw artifacts 位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ppt_ixnos_v1/`；PPT commit=`9b23048267afc808fade89cc08655464b5814467`。
- 当前在线主稿真实状态为 **77 页、revision 39、末页 `pgW`**。完整 102,187,657-read run、RSEM、333/167-gene 60-epoch、多 replicate、study/功能 OOD、统一成本强 baseline 主矩阵、RK03/RK04/RK06 剩余项、CodonFlow-RK 生成器、完整 Fig.1–7、SOTA、前瞻湿实验与可投稿论文均未关闭；遗留 `id3_independent_verification.pid` 不应提交。

## 27. ROSE 官方发布测试集单 checkpoint 推理、A8 v10 与 PPT 第 78 页

### 固定来源、完整数组与独立复核

- 官方 ROSE 固定 commit=`8b86d69d89ca7ef95193729e6d1a4738bc6a4451`，归档 SHA256=`8bd85ae8593de547e6790aefcef311f098de7e3219d69b8b4b898266a8eae73b`，官方 demo SHA256=`9ab4df2c7bfaa022cb731f76588d263e88a8d15dcf3547081435c58726272548`。恢复源码位于 `/home/codonflow-a8-rk-external/rose-8b86d69d89ca7ef95193729e6d1a4738bc6a4451`。本任务固定为 codon-resolution binary ribosome-stalling classification，不是 RiboMIMO/iXnos 的连续速度回归。
- 每研究只使用一个发布 `best_model_0.caffemodel`，单次完整前向，无训练、无虚构的 64-checkpoint 集成。输入为 183 nt / 61 codons，按官方 ATCG 嵌套顺序编码成 `N×64×1×61 float32`；只改 HDF5 路径、TEST batch size 与 CPU 环境，网络结构和权重未改。Pop14 为 1,902 条、正负各 951、128,834 参数；Battle15 为 9,980 条、正负各 4,990、265,858 参数，共 11,882 条完整发布测试记录。
- Pop14 的 ROC AUC/AP/accuracy/log loss/Brier=`0.8618886976/0.8592736843/0.7786540484/0.4987314376/0.1550820795`；Battle15=`0.8072302521/0.7940684857/0.7281563126/0.5623744450/0.1860703555`。两套常数 prevalence baseline 均为 ROC AUC=0.5、AP=0.5、log loss=ln(2)、Brier=0.25。以上是作者处理数组上的单 checkpoint 分类输出，不是功能 OOD、统一成本排名或 SOTA。
- 独立 verifier 不导入生产脚本，独立编码、构建 HDF5/网络路径与 batch 改写并执行第二次 Caffe 前向。v4 **34/34 PASS**：两研究 logits、官方 float32 概率公式及全部生产指标差均为 0；稳定 float64 仅作次级舍入/近并列诊断。finalization **60/60 PASS**、单元测试 **12/12 PASS**。生产报告 SHA256=`03cacac5d8378bc9120fc48c78a7bc52bb24e83314543e82a03058d121194d0a`，独立 v4 SHA256=`904d370e0b6c87c86484a74c2b572dca964bdc5289110a1d37d00e4a3d378861`，finalization SHA256=`c1733d1c937af26892fbfebf6385bcd9ca80b9825bd07f7597e7188716d48817`。科学证据 commit=`3a284efef7fab0b911473f1e1647f01bcfedf651`，已推送。
- v1–v3 失败报告全部保留：v1 对两种概率公式误用 `1e-15` 容差；v2 对 log loss/Brier 的统一 `1e-12` 指标容差过严；v3 的稳定 float64 打破官方 float32 近并列，使 Battle15 AP 差 `3.4728404374e-08`。这些均为 verifier 数值判据问题，不是模型、数据或生产失败；最终 v4 要求生产公式与生产指标完全一致，没有删除失败或改写生产结果。
- 生产 raw 位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/rose_official_single_checkpoint_v1/`，独立 raw 位于 `rose_independent_v4/`，v1–v3 独立失败目录均保留。代码/报告在 `/home/codonflow-a8-rk`；完整复现命令见 `audits/20261118/RK05/README.md`。

### A8 v10、PPT 写后验收与当前续作

- A8 生成器/verifier 纳入协议、生产、独立 v4、finalization 与三份失败报告，新增完整数组、参数、分类指标、34/34、60/60、单 checkpoint/无训练和科学边界。A7 未改；A8 v10 SHA256=`4bc071c4f8e6eecb20429e8b9ee044e116105f8a348740254f22a040840f823e`，独立论文核验 **21/21 PASS**，报告 SHA256=`4461070a39fa8d8ec68fa6edc51240be4c7c942344e4fd6f13087380ca31bdc1`，状态仍为 `PASS_WORKING_MANUSCRIPT_NOT_SUBMITTABLE`。commit=`f17f432e3ea58d6d2839bdba6ab05dedc3f4460f`，已推送。
- 实时 PPT 基线为 77 页、revision 39、末页 `pgW`。候选页独立 preflight **14/14 PASS** 后只追加第 78 页 `pgc`，revision=40。页面展示 Pop14/Battle15 的 ROC AUC、AP、accuracy、log loss 和常数 baseline，明确二分类、单 checkpoint、无训练、非速度回归及 OOD/SOTA 未关闭，并保留 v1–v3 数值判据失败说明。
- `audits/20261118/RK05/rose_ppt_final_verification_v1.json` 为 **PASS，14/14 checks**：整稿 78 页，前 77 页 slide ID、顺序与 canonical XML 全部不变；新页文本与候选一致，指标由冻结 JSON 复核，4 段备注、画布边界与科学边界通过。raw artifacts 位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ppt_rose_v1/`；PPT 验证代码/报告 commit=`a9de66192f4d3fa2e795d8d93b05e2671248b595`，本地和服务器复跑结果逐字节一致。
- 当前在线主稿真实状态为 **78 页、revision 40、末页 `pgc`**。本任务只关闭 ROSE 发布测试集单 checkpoint 推理及其论文/PPT 记录；完整训练、100000-iteration 协议、64-checkpoint 集成、连续速度回归、raw-read/P-site 重映射、蛋白/study/功能 OOD、统一成本强 baseline 主矩阵、RK03/RK04/RK06 剩余项、CodonFlow-RK 生成器、完整 Fig.1–7、SOTA、前瞻湿实验与可投稿论文均未关闭。遗留 `id3_independent_verification.pid` 不属于本任务，不应提交。

## 28. MAGE 固定 infA 同义机制 nested-development 诊断与 A8 v26

### 冻结协议、生产结果与独立复核

- v2 协议在拟合前冻结，只复用 v1 的 train+dev=131 constructs（98/33），保持四组特征、分类/数值变量、StandardScaler、OneHotEncoder、ridge solver 与 alpha grid 不变。5-fold outer/4-fold inner nested CV 仅以 inner OOF RMSE 选 alpha；primary seed=`40261119`，敏感性 seeds=`40261120/40261121`。原 33 个 test constructs 在记录表、fold、特征矩阵、拟合、预测和指标中完全排除。协议/生产器/12 项测试已以 commit=`b6f9f09c9873cab7af4d8b321f2bd9a452fbb8d7` 推送。
- 主 seed 的 intrinsic/local-MFE/RCS-only/full-mechanism RMSE 分别为 `0.034133275/0.034383848/0.034152774/0.034228203`，Spearman 分别为 `0.612399084/0.627265588/0.616352629/0.635298146`。full−intrinsic ΔSpearman=`0.022899062`，95% CI=`[-0.037905777,0.090116393]`，ΔRMSE=`+0.000094928`，95% CI=`[-0.001417567,0.001456402]`；full−local-MFE ΔSpearman=`0.008032557`，95% CI=`[-0.028646739,0.048858482]`，ΔRMSE=`−0.000155645`，95% CI=`[-0.000999395,0.000600285]`。20,000 bootstrap、20,000 paired sign-flip 后四项 Holm p=1.0。
- 两个敏感性重复未满足所有方向一致性，最终为 `DEV_NO_GO_TEST_UNTOUCHED`。这只说明当前固定 infA、rich medium、positions 10–71 的开发设计下 full-mechanism 增量小且不稳定，不证明 RNA 结构普遍无效；RCS 是外部监督结构评分。独立 raw-source 复核 **96/96 PASS**，prediction/metric/inference/inner-RMSE 最大差均为 0；finalization **30/30 PASS**。生产报告、独立报告和 finalization 位于 `audits/20261119/RK03/`，大型 OOF/fold artifacts 位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/mage_development_nested_cv_v2/`。

### A8 v26、复现与后续边界

- A8 在 v25 后以 append-only 方式新增 6.22 和证据锚点，A7 未改；v25 SHA256=`f399fceead66b231b998e073fa02aab0d4bd830aa7a6d4dffd0bb2bec836c15b`，v26 SHA256=`88cc89ccf83958110fb2fb20454df691ecebdfa164f7e7806fd8797aa6e482c5`。论文独立核验 **54/54 PASS**，其中候选事实 **29/29 PASS**；v25 可由更新记录逐字恢复，快照保存在 `paper/snapshots/rk03_mage_development_nested_cv_v26/`。
- 完整生产、独立复核、finalization 和论文核验命令见根目录 `README.md`；run 已登记 `experiments/REGISTRY.md`。初次 `FileNotFoundError` 工程失败与最终 12/12 测试日志均保留。
- 本项没有读取或评价 33 个 mechanism-test constructs，没有 minimal-medium、rich-to-minimal 或 N-terminal transport，没有使用 RK04 的 19,072 个 functional-untouched MAGE assay rows。RK-G1=false，昂贵生成训练未授权；真实功能 OOD、主模型、完整 baseline、统一成本、生成器、SOTA、前瞻湿实验和可投稿论文仍未关闭。

## 29. MAGE nested-development 在线 PPT 记录与写后验收

- 写前实时基线为 **101 页、revision 63**，末页 RiboMIMO=`pgI`；再次 precommit 回读与基线 SHA256 完全一致。候选页复用第 100 页的学术 NO-GO 版式，以三张 KPI、四行 full-minus-reference 主对比表、设计/独立复核侧栏、结论和边界卡记录 MAGE v2；数值由 finalization/independent/paper JSON 程序化生成，不手写科学结果。
- 候选最终 **52/52 PASS**，覆盖全部模型/对比值、四项 Holm、敏感性失败、33 test untouched、development-only、RCS supervised、非蛋白 OOD/非普遍结构证伪、论文和 GitHub 事实，以及画布和保守单行宽度。初次 `--index` 参数在发送前被本机 CLI 拒绝；第一次正式提交被服务端 lint 拦截，原因是标题框与右上角验证徽章存在 3 px 几何交叠。两次均未写入，原始错误保留；随后将标题下移到徽章下方并保持原底线，不使用 `--no-lint`。
- 成功追加后在线主稿为 **102 页、revision 64**，新页为第 **102 页 `pgj`**。完整 XML 回读确认前 101 页在忽略元素 ID 后的语义 XML 全部不变，RiboMIMO 第 101 页保留；新页与候选在忽略元素 ID 后语义完全一致。新页含 20 个文本框、6×5 表格和 5 段备注，主数值、敏感性 seeds、RCS/test/protein-OOD/RK-G1/生成器边界均完整。
- 独立写后核验 `audits/20261119/RK03/mage_development_nested_cv_ppt_verification.json` 为 **79/79 PASS**；候选核验为 **52/52 PASS**。核验器初版把 finalization 的英文 `conclusion` 误认为冻结状态字符串，得到 78/79；该报告保留在大型证据目录，修正为从 production `status` 读取 `DEV_NO_GO_TEST_UNTOUCHED` 后全部通过。科学报告和在线页面未因该工程映射修正而改变。
- 候选、候选失败版本、写前/写后整稿 XML、add/readback 响应、CLI 错误、控制台日志和页面文本位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/ppt_mage_development_nested_cv_v1/`。科学证据来源 commit=`85feef400ec1bd477c817416cfe5928108eef8da`；本次新增仅为 PPT 核验代码、报告和交接文档。PPT 记录不读取 33 个 test constructs，不产生 test/transport/functional-untouched 结果，不关闭 RK-G1，不授权生成器训练，也不使 manuscript 变为可提交。

## 30. Ribo/VeloHARMO metadata-only 来源可行性与 A8 v27

### 固定协议、真实 RunInfo 与独立验收

- 本项在生产前冻结 `a8_rk03_source_feasibility_v1_frozen_before_production`，只读取官方 PMC 正文、GEO SOFT、SRA/BioProject RunInfo 和既有固定 VeloHARMO source-tree/materialization/E. coli QC 证据。没有实际 FASTQ/BAM/SRA 下载、参考版本冻结、UTR–CDS 构建、比对或模型训练。`size_MB` 是公开归档元数据之和，不是本轮下载量。
- 初版协议错误写入不存在的 CU-Boulder-ESIL 来源，并交换 Dunn13/Pop14；正式证据纠正为 `BianBian2021/VeloHARMO` commit=`38b48079856aeb9d33a1b10844d77aa8f6640032`，Dunn13=*Drosophila melanogaster*/GSE49197/SRP028243，Pop14=*Saccharomyces cerevisiae*/GSE63789/SRP050443。GSE53268 无 SRA SRP relation，RunInfo 使用 BioProject=`PRJNA231671`。source-tree 与 materialization 均为 14 个文件，不是早期摘要的 13；14 个实时 SHA256/bytes 全部匹配。上述错误及 65/71、73/74、45/46 失败报告均保留。
- 五项 VeloHARMO 来源为：Mohammad16/GSE72899/SRP063562=5 runs/3,594 MB；Grady17/PRJNA379630=24/58,639；Dunn13/GSE49197/SRP028243=14/34,020；Pop14/GSE63789/SRP050443=10/13,780；Battle15/GSE61742/SRP047476=72/33,630，合计 **125 runs、143,663 MB**。RiboMIMO 额外 Mohammad19/GSE119104/SRP158945=10/5,202，Subtelny14/GSE53268/PRJNA231671=3/4,034，额外合计 **13 runs、9,236 MB**；七个不同 RunInfo accession 合计 **138 runs、152,899 MB**。
- 固定快照包含两个 byte-identical E. coli harmonized ZIP，以及 E. coli/yeast fold-0 GA checkpoints；只有 E. coli harmonized matrix 被发布。公开 raw source 或 GA checkpoint 不得写成其他四个物种的 harmonized matrix 已发布。
- 14/14 tests、生产 **74/74 PASS**、离线独立 **169/169 PASS**（不导入生产器、不用网络，最大数值差 0）、finalization **47/47 PASS**。终态为 `SOURCE_METADATA_RECOVERABLE_REMAP_NOT_PERFORMED`，科学结论为 `PUBLIC_SOURCE_RECOVERY_FEASIBLE_BUT_NOT_REMAPPED`。科学报告、独立报告、finalization、日志和 artifact manifest 位于 `audits/20261120/RK03/`，raw responses 位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/source_feasibility_v1/`；科学证据 commit=`c0fd2b32a4919734747214ae06336efb67e03dcd`，已推送。

### A8 v27、复现与边界

- A8 以 v26 SHA256=`88cc89ccf83958110fb2fb20454df691ecebdfa164f7e7806fd8797aa6e482c5` 为冻结输入，append-only 新增 6.23 节和六个证据 anchors，A7 未改。v27 SHA256=`c745b3e73b7d9f380f7c0ce326cc5fba2cfae769273b2e58f606a73dba9e0952`；独立论文核验 **61/61 PASS**，候选事实 **30/30 PASS**，删除新增 section/anchors 可逐字恢复 v26。更新记录、sync audit、快照和核验报告已以 commit=`c5046b9c25a700f6231f0411b95f4d881dcda5d8` 推送。
- 完整复现命令见根目录 `README.md`，run 已登记 `experiments/REGISTRY.md`。实时 OUP 403、真实 GitHub tree API 404 和旧仓库访问失败只保留为 optional access 记录，不覆盖已固定并重新哈希的 materialized-tree 证据。
- 该 bounded 子任务只关闭 metadata-level source feasibility。四物种 harmonized matrix 生成、整体自然分布报告、UTR–CDS 实际映射、raw-read/P-site 独立重比对、机制验证、模型结果、RK-G1、昂贵生成训练授权与 manuscript submittability 均未关闭；v27 仍是 non-submittable working manuscript。

## 31. Source-feasibility 在线 PPT 第 103 页与写后验收

- 写前实时基线为 **102 页、revision 64**，末页 MAGE=`pgj`。新页沿用科研数据版式，记录三项总量卡、七项来源表、固定发布范围和“来源可恢复但本轮未重比对”的边界；所有数值由正式 JSON 重新计算。候选写前核验 **35/35 PASS**，随后真实追加第 **103 页 `pgM`**，在线 revision=65。
- 整稿回读确认 103 页，前 102 页 ID、顺序和语义 XML 全部不变；新页文本、备注、表格与候选一致。首次写后为 **46/47 PASS**，唯一失败是服务端仅在七个 `<col>` 上显式化 schema-default `span=1`；失败报告保留。核验器只规范化该默认属性和服务端分配 ID，文本、数值、表格、几何及其他属性仍严格比较，最终 **47/47 PASS**，远端仓库独立重跑结果相同。
- 候选 XML、写前/写后报告、首次失败报告、真实写入响应和核验脚本位于 `audits/20261120/RK03/`，大型基线/回读 XML 与完整证据位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/ppt_source_feasibility_v1/`。PPT 证据 commit=`dc567587aa9b3a1db67be0fcebcd26fdf450e16a`，已推送。当前在线主稿真实状态为 **103 页、revision 65、末页 `pgM`**，不得重复追加本页。
- PPT 记录不产生 reads 下载、UTR–CDS、重比对、P-site、机制或模型结果，不关闭 RK-G1，不授权生成器训练，也不使 manuscript 变为可提交。

## 32. MAGE 既有 OOF 对照补全与在线 PPT 第 104 页

### 冻结分析、失败更正与独立复核

- 本项只复用 nested-development 已冻结的 **131 constructs × 3 outer seeds** OOF 预测，不重训、不读取新序列或标签、不接触原 33 个 mechanism-test constructs，也不改变 `DEV_NO_GO_TEST_UNTOUCHED`。保留 intrinsic、local-MFE、`rcs_only`、full-mechanism 四个冻结臂；其中 `rcs_only` 实际包含 intrinsic+RCS，不能写成纯外部预训练模型。
- v2 协议新增三项 development-only 探索对照：full−RCS、RCS−intrinsic 和 full−outer-train-mean。前两项各检验 ΔSpearman/ΔRMSE，均值基线只作 RMSE 推断；五检验统一 Holm，primary 为 20,000 construct bootstrap + 20,000 paired permutations，另两个 outer seeds 仅报告点估计。outer-train mean 在每个 fold 只使用该 fold 之外的 development 标签均值，独立复核确认无 evaluation-fold 标签泄漏。
- v1 错把 fold-specific train means 当成全局常数并要求 Spearman=null，正式运行在技术门禁失败，未生成 production report；v2 明确 fold 间 train mean 可变，OOF Spearman 仅描述、不作 paired Spearman 推断。v1/v2 协议、环境兼容失败、v1 技术失败和更正记录全部保留。
- 最终 **9/9 tests、24/24 independent PASS**，独立实现以 `1e-12` 容差重算模型指标、效应、CI、置换、Holm、三 seed 点估计及均值基线无泄漏条件。0 new fits、0 new scorer calls；primary 共 120,000 resample replicates，production wall time=55.9064832450822 s。科学代码与证据 commit=`46f1b7f057f479da9547745c5fa657bdfff00a21`，已推送。

### 结果、边界与论文同步顺序

- full RMSE=`0.03422820302559988`，outer-train mean RMSE=`0.04959854257604538`；full−mean ΔRMSE=`-0.015370339550445498`，95% CI=`[-0.0259385856740894,-0.005729286631198561]`，Holm p=`0.020748962551872408`，三个 seeds 均为负。结论仅为优于 fold-specific train-mean baseline。
- full−RCS：ΔSpearman=`0.01894551686269652`，95% CI=`[-0.035360666095523505,0.0812104898567834]`；ΔRMSE=`0.0000754291571132687`，95% CI=`[-0.001304659287456654,0.0013410731145082557]`。RCS−intrinsic：ΔSpearman=`0.003953545226666688`，95% CI=`[-0.0360723999783062,0.04841834750571718]`；ΔRMSE=`0.000019499256082820826`，95% CI=`[-0.0007529122397496208,0.0007030615007199467]`。四项机制对照 Holm p=1，敏感性方向不稳定，不能宣称机制增量。
- 纯外部预训练模型替代、独立常数速度场臂、functional untouched、transport 和 generator authorization 均未闭合。RK-G1=false，昂贵生成训练仍未授权。
- 为避免与正在运行的 RK06 finalization/paper updater 争用 v27 精确增量基线，本项论文 section/anchors 暂不改写；待 RK06 论文更新完成后再以最新实时稿件追加 MAGE comparator 证据。当前科学审计和 PPT 已闭合，manuscript 仍是 non-submittable working manuscript。

### 第 104 页写入、回读与视觉验收

- 写前实时基线为 **103 页、revision 65、末页 `pgM`**。候选页由 production/independent JSON 和 9/9 测试日志程序化生成，含三张 RMSE 卡、三行探索对照、三 seed 方向及边界；候选 **20/20 preflight PASS**。首次 CLI 参数校验失败未发生外部写入，错误响应保留。
- 成功追加第 **104 页 `pgz`，revision 66**。完整 XML 回读确认 104 页、前 103 页 slide ID/顺序不变、marker 仅一次，新页可见文字和备注与候选语义一致；真实截图人工检查标题、卡片、表格、底部结论均完整，无裁切、重叠或缺失。
- 写后最终 **29/29 PASS**。初版验收器额外要求两个探索对照的 raw permutation p 必须写入备注，得到 29/31；页面按冻结设计已含 CI/Holm p，raw p 保留在科学 JSON，因此只更正验收规则，页面、科学数值和容差均未改。失败报告、更正记录和最终报告均保留。远端 closeout 复跑先因 miniconda base 缺 NumPy 在测试导入阶段失败，v5 日志保留；改用本项既有 system Python 后 v6 为 **9/9 tests + 29/29 PPT PASS**，远端报告 SHA 与本地最终报告完全一致。
- PPT builder=`scripts/a8_rk03_build_mage_oof_comparator_ppt.py`，写后 verifier=`scripts/a8_rk03_verify_mage_oof_comparator_ppt.py`；小型候选/响应/报告位于 `audits/20261120/RK03/`，大型 baseline/readback XML 与截图位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/ppt_mage_oof_comparator_v1/`。当前在线主稿真实状态为 **104 页、revision 66、末页 `pgz`**，不得重复追加本页。
