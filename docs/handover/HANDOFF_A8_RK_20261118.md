# CodonFlow A8-RK 正式交接（2026-11-18）

## 1. 当前权威入口

本文件是 A8-RK 的当前交接；旧 A7 handoff/prompt 只保留历史，不再指导新实验。

- 完整科学与执行路线：工作区根目录 `CodonFlow_A8_严格科研工程审查与一个月路线_20261118.md`
- 镜像：`docs/review/CodonFlow_A8_严格科研工程审查与一个月路线_20261118.md`
- 执行合同：`docs/handover/spec.md`
- 文件级任务：`docs/handover/tasks.md`
- 下一位执行者提示词：`docs/handover/PROMPT_NEXT_AGENT_A8_RK.md`
- 预印本工作稿：`paper/CodonFlow_preprint_A7.md`

A8-RK 的实际执行位于隔离工作树 `/home/codonflow-a8-rk`、分支 `a8-rk`。RK-01 commit=`5ad3393a4f90c4a743cf7e0725b45ea62e395172`；RK-02 commit=`087b8822e14dcb15710dc2f40d8db5650b8687a4`，均已推送 GitHub。原主工作树 `/home/codonflow` 的 `main` 及其既有未推送提交未被改写或推送。大型资产沿用 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/`。不得在交接、日志或提示词中记录服务器密码。

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

**RK-02 已实际下载、清洗并审计：8 份官方原始附件完成 SHA 登记，Boël 与 MAGE 形成 25,420 个 assay rows；Kudla 支持附件已取得，但 154 条逐构建序列—表达表仍未获得，状态为 `PARTIAL_KUDLA_ROW_DATA_UNAVAILABLE`。** 所有 split 仍为 `UNASSIGNED`，尚未用于训练。Theodorou et al. 的 Dasher/六蛋白原始数据原文明确不公开，不得纳入训练承诺。

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

### 下一步边界

RK-01、RK-02 已完成；RK-G0 尚未关闭。下一步只能继续蛋白 family mapping、construct-signature 分组、无泄漏 split、官方 baseline smoke、dense-v2 与成本协议。没有完成这些工作前，不得声称已开始 RK 功能训练、机制有效或超过 SOTA。
