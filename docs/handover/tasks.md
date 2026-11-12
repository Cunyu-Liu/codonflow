# CodonFlow Tasks（A7 · warm-start 学习价值验证版）

> 生效日期：2026-11-01。与 `spec.md` 的 G0–G5 一一对应。
> 主任务：warm-start synonymous CDS editing。第一决定性关卡：learned vs 无学习简单搜索。
> 当前处于 P1/G0 实施阶段；协议代码与合成/真实 CDS 冒烟已完成，未启动新模型主训练。远端运行状态在任何后续执行前重新盘点。

## 0. 已完成的方向与审计工作

- [x] **T0.1 全量交接审计**：通读交接材料，识别旧模型退化、数据/指标/文档漂移和不可引用旧结果。
- [x] **T0.2 文献与 baseline 审计**：补入 mRNA-GPT、AReUReDi、MOG-DFM、TR2-D2；确认 RayGun/SCISOR 不属于 synonymous CDS 数值 baseline。
- [x] **T0.3 科学方向确认**：用户确认 warm-start 主任务和 learned-vs-simple-search 第一决定性关卡。
- [x] **T0.4 只读反思记录**：见 `AUDIT_REFLECTION_20261101.md`；包含主张—证据矩阵、论文推理链和合同漂移清单。
- [x] **T0.5 合同重写**：`spec.md`、`tasks.md`、`checklist.md`、`RUNBOOK_NEXT.md` 与 A6 提纲统一为 A7 逻辑。

## 1. P1 · G0 数据与协议就绪

### T1.1 数据来源、清洗与分布审计

- [x] 实现 `scripts/a7_data_audit.py`：逐步无效原因、长度/GC/CAI/RSCU、物种/簇元数据和 cleaning manifest 数量守恒；合成测试与真实 eGFP 冒烟通过。
- [x] 生成 D4/D5 六个 split 的全量长度、GC、CAI/RSCU、密码子使用和簇分布报告：`07_a7_data/full_audits_20261112_v2/`；记录数、操作合法性、唯一蛋白和 D5 簇映射全部通过。非 ATG 部分 CDS 已单列，物种占比和选择偏差限制写入 manifest。
- [x] 25 物种原始输入已恢复并生成 release、URL、恢复时间、哈希和逐步过滤数量：`07_a7_data/raw_release112/manifest.json`，25/25 `passed=true`；G0 source_recovery 检查通过。
- [x] 通过冻结 transcript ID 规则恢复 25 物种映射与逐 split 分布（`full_audits_20261112_v2/species_distribution.json`）；全部记录映射成功。非 ATG 可能部分 CDS、标准遗传代码 table 1 和异常注释处理已披露；不得据此声称 species OOD。

**DoD**：独立脚本从原始输入生成清洗流水账与分布报告；数量守恒，所有规则有审计文件，不只保留最终 FASTA 或旧汇总。

### T1.2 开发集与 untouched 确认集

- [x] 实现 `scripts/a7_build_confirmation.py`：只使用长度/GC/ID/cluster，排除旧 benchmark、精确 CDS/蛋白和同源簇；合成测试通过。
- [x] unique18 权威 FASTA 已恢复并核验 SHA256，保留 eGFP/nanoLuc + unique18 为开发集，停止将其称为最终独立测试。
- [x] 从 D5 test 实际冻结 24 个未参与既往实验的唯一蛋白/CDS，排除清单、长度/GC 分布和 SHA256 已写齐。

**DoD**：FASTA、选择脚本、排除清单、split/cluster/精确重叠报告和 SHA256 全部冻结；确认集访问日志可追踪。

### T1.3 独立评价参考与指标协议

- [x] 实现 `a7_build_calibration.py`、`FrozenReference` 和 anytime AUC；参考域只由独立 calibration 构建，退化轴拒绝，搜索效用与 AUC 共用归一化。
- [x] 冻结 `configs/a7_protocol.json` 与 `configs/a7_data_protocol.json`：指标方向、B=50/100/500、motif/codon、统计和 G1/G2 阈值。
- [x] D5 train 已独立构建 CAI/RSCU（`07_a7_data/cai_ref_d5train.json`，SHA256=`2a5e05ef…`），D4 沿用其 train 参考表，未跨版本混用。
- [x] 24 个独立 calibration pool 已全部生成并验证：25 个顶层 JSON（24 reference + manifest），record/hash 一一对应，D5 RSCU 一致，scale 全部为正且有限；每池 56–70 个唯一目标向量。

**DoD**：协议 JSON + 单元/契约测试 + 独立重算一致；不允许从 test 输出估计归一化范围。

### T1.4 简单搜索对照协议

- [x] 实现 uniform、hill-climbing、MH/annealing、AReUReDi-style 的同义操作符、paired 初始化、唯一 scorer 预算和成本 trace。
- [x] 真实 eGFP 四方法各 12 个唯一评分的端到端冒烟通过；结果只作协议验证，不作性能结论。
- [x] 所有内部方法使用同一 scorer 接口、归一化和 B=50/100/500 网格；完整主实验留待 G2。

**DoD**：小状态/短序列行为测试通过；同一输入下逐方法身份、目标、唯一解数和成本可复核。

### T1.5 外部 baseline 与资源表

- [x] 建立 `configs/a7_baseline_resources.json`：LinearDesign、GEMORNA、codonGPT 的输入/限制/成本，mRNAutilus、ProMORNA、mRNA-GPT 的未复现状态，以及 RayGun/SCISOR 的任务排除理由。
- [ ] 远端恢复后复核 LinearDesign、GEMORNA、codonGPT 的权威输入、版本和实际输出。
- [x] `a7_audit_unique18.py` 已确认 seed-0 的 18/18、五方法均 `done`、identity=1、目标有限且 benchmark 哈希匹配；seeds 1/2 与全量 MFE/NED 独立重算仍待完成。
- [x] `a7_recompute_unique18.py` 已完成 seed-0 真实独立复算：18/18 的 MFE/NED、四轴目标、identity、唯一解数及 source/benchmark/RSCU 哈希全部匹配，RNAfold 2.7.2；报告 `07_a7_data/unique18_seed0_independent_mfe_ned.json`，SHA256=`c0425d18…`。seeds 1/2 生成与复算仍待完成。

**DoD**：资源表含任务、输入、版本、代码/权重、预训练重叠限制、可复跑状态和排除理由。

### T1.6 结果 schema 与统计计划

- [x] 实现 `validate_result_payload`：数据/代码/checkpoint 哈希、`code_dirty`、seed、配置和不可变 artifact 路径。
- [x] 固定四成本、anytime 点、原始目标向量、缺失方法和 architectural exclusion 字段；真实四份结果全部通过 schema。
- [x] 实现基因级 paired bootstrap、Wilcoxon、Holm 和 3 seeds 聚合，模拟 paired 数据契约测试通过。

**DoD**：空结果模板通过 schema 校验；统计脚本在模拟 paired 数据上通过契约测试。

### T1.7 代码恢复与整体验证

- [x] 从 GitHub 源码归档恢复到工作区 `codonflow-main/`，已上传并合并到共享目录 `codonflow1031/01_code/codonflow/`；A6 原代码另有备份。
- [x] 合并后远端完整回归 **131 passed, 1 skipped**；真实 CDS 数据审计和四方法搜索产物已落盘 `eval_outputs/a7_smoke/`。
- [ ] 在执行实例重新确认 `/home/codonflow` 代码版本、共享资产挂载和完整回归；旧共享目录不得直接覆盖新版本。

### T1.8 GPU 与运行环境验收

- [x] px2 RTX 5090、driver 595.84/CUDA 13.2 已实测同步 CUDA matmul 成功；其他项目约 9GB 显存进程未触碰。独立 `codonflow` cu132 环境仍在重建，当前成功 matmul 使用 `llr_env` 仅作硬件验证。
- [x] 独立 `codonflow`/`pc_cng` cu132 环境在 px2 部署完成；完整回归 142 passed、1 skipped，ViennaRNA 2.7.2、rapidfuzz 3.14.5 和真实 CUDA matmul 均通过。
- [x] seeds 1/2 已使用两个真实 CUDA 进程并行启动；无 CPU 静默降级。主训练仍须等待 G0 全部通过。
- [x] 仅为合同内任务并行分配 GPU；保留其他项目进程，记录日志、PID 与资源边界，不 kill 或修改其他项目。

**P1 尚未完成 = G0 未通过。确认集、D5 RSCU 和 24 个 calibration 池有完成并验证的交接证据；剩余项为远端资产复核、全量数据审计、unique18 seeds 1/2 与 MFE/NED 重算，以及 GPU/CUDA 验收。此前不启动新模型主训练。**

## 2. P2 · G1 模型收敛且非退化

- [ ] **T2.1 开发模型训练**：G0 后从零训练 `M_SYN_D4_*`；当前无 checkpoint，禁止从旧 arbitrary-corruption 权重冒充恢复。
- [ ] **T2.2 收敛与冻结**：独立 val 连续 3 epoch 相对改善 <0.1%；保存 best/last/training_state/converged 和 SHA256。
- [ ] **T2.3 行为门**：至少 3 个开发基因 × 100 paired 样本，满足 spec G1 的非源序列率、唯一解数、最大单序列频率和 identity/legal。
- [ ] **T2.4 诊断归档**：报告 stay-p、P(edit)、位置覆盖、奖励响应和与 uniform 的逐串重合；旧复制模型仅作反例。

**DoD**：G1 所有阈值由独立 JSON 验证；full-token 与 edited-token 不跨目标比较 val 绝对值。

## 3. P3 · G2 第一决定性关卡：learned vs 简单搜索

- [ ] **T3.1 开发集 paired 主实验**：learned base 对 uniform/hill-climbing/MH/AReUReDi-style，同初始化、同 scorer/cache、3 seeds。
- [ ] **T3.2 anytime 质量—成本分析**：输出 B=50/100/500 曲线、固定参考域 HV AUC、原始 Pareto front、逐目标 best-at-budget 和 NED。
- [ ] **T3.3 统计裁决**：按基因计算最强简单基线、相对效应、paired bootstrap 95% CI、Wilcoxon 与 Holm。
- [ ] **T3.4 Go/No-Go**：完整核对 spec G2 的 ≥10% 中位改善、CI、p 值、identity/legal 和多样性条件。

**DoD**：中心图与逐基因表由冻结 JSON 自动生成；任一失败均明确 No-Go，不转向外部弱 baseline 掩盖。

**若 No-Go**：停止 short-rollout 主贡献、RLOO、扩参和 SOTA 写作，只保留训练诊断或负结果路线。

## 4. P4 · G3 short-rollout 净收益

- [ ] 同一冻结 checkpoint 上比较 immediate 与 short-rollout，初始状态和预算严格配对。
- [ ] 同时报告 scorer/forward/时间成本和质量收益，拒绝只比较 HV。
- [ ] 近似偏差随 rollout/candidate 预算变化入档。

**DoD**：spec G3 通过才保留 short-rollout 主贡献；否则主线只保留 immediate。

## 5. P5 · G4 独立确认与外部边界

- [ ] **T5.1 D5 最终模型**：协议冻结后训练 `M_SYN_D5_*`，重复 G1，不在确认集调参。
- [ ] **T5.2 untouched 确认**：24 基因上重复 learned-vs-simple-search 主对照和统计。
- [ ] **T5.3 外部方法边界**：LinearDesign/GEMORNA/codonGPT 等按 natural-source 与 protein-only 两种初始化分层报告。
- [ ] **T5.4 分层分析**：按目标数、长度、GC 和预算报告优势/失败区域；缺失方法显式列出。
- [ ] **T5.5 泛化措辞审计**：D5 只称操作定义的同源隔离，不写 curated family/species OOD。

**DoD**：确认集只用于最终裁决；所有数值可追溯到冻结输入、代码、模型和统计 artifact。

## 6. P6 · G5 论文、图和发布

- [x] **T6.1 新论文提纲**：中心结果改为 learned vs 简单搜索的 anytime 前沿；旧 scaling/RLOO/SOTA 撤出主线。
- [ ] **T6.2 方法/协议正文**：可在无新结果时撰写，但不预写性能结论。
- [ ] **T6.3 Results 与 Discussion**：仅在相应 G1–G4 证据完成后填写。
- [ ] **T6.4 主图**：方法与不变量、非退化机制、learned-vs-simple 中心图、rollout 消融、外部边界。
- [ ] **T6.5 可复核发布**：代码、配置、数据清单、冻结 JSON、负结果和不可复现 baseline 说明齐全。

**DoD**：每个主张都能指向证据；每个图可自动重建；无湿实验时不出现表达/稳定性/疗效宣称。

## 7. 可选后续，不在主关键路径

- [ ] RLOO：仅 G4 后重新评审；先证明严格同义空间内存在非平凡奖励信号。
- [ ] 355M/扩参：仅 56M 通过 G2 且有可重复容量限制证据后评审。
- [ ] 外部任务/湿实验：单独立项，不作为当前计算代理结论的隐含承诺。

## 8. 当前唯一允许推进的任务块

**P1 / G0 数据与协议就绪。** P2–P5 均受前置门约束；不得并行跳过 G0/G1/G2。所有实验执行仍需按用户后续指令启动。
