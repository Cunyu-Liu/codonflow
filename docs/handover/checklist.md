# CodonFlow Checklist（A7 当前有效验收）

> 生效日期：2026-11-01。旧 A–L 勾选不再作为当前验收依据；历史轨迹见 journals、HANDOFF 和 `AUDIT_REFLECTION_20261101.md`。
> 只有产物、独立核验和对应科学问题同时满足才可勾选。文件存在、loss 下降、测试通过或 GPU 运行均不等于科学通过。

## C0. 方向、审计与合同

- [x] 主任务确认为 warm-start synonymous CDS editing。
- [x] 第一决定性关卡确认为 learned proposal vs 无学习简单搜索。
- [x] 全部交接文档完成只读审计与反思记录。
- [x] 文献审计补入 mRNA-GPT、AReUReDi、MOG-DFM、TR2-D2；RayGun/SCISOR 从数值主表排除。
- [x] 当前 spec/tasks/checklist/runbook/论文提纲已统一为 A7。
- [x] 正式模型结果产生前，已登记 G2 uniform 工程澄清：保留更强的全局逐位置同义均匀采样；局部搜索与 learned 使用单密码子核，配对初始、scorer、预算与全部 Gate 阈值不变。

## C1. 可复用历史资产（不代表性能通过）

- [x] 有限步同义 Markov 操作符与可枚举小状态精确验证存在。
- [x] 成本 trace 能区分 forward、rollout、终端请求、实际 scorer 和唯一 scorer。
- [x] D4 精确 CDS/蛋白交叉重叠审计为 0。
- [x] D5 操作定义的 protein-homology-cluster 隔离审计通过。
- [x] unique18 的 18 条输入 FASTA 已冻结并审计。
- [x] core seed-0 五方法的部分真实 baseline 结果完成身份/输入复核。
- [x] 旧 arbitrary-corruption 模型的复制退化已证伪并保留负结果。
- [x] unique18 seeds 0/1/2 均已完成 18/18、五方法真实生成和独立 MFE/NED 复算；四轴目标、identity、解数和哈希全部一致。

## C2. G0 数据与协议就绪

- [x] 25 物种来源、release、恢复时间、哈希和逐步清洗流水账完整：`07_a7_data/raw_release112/manifest.json`，25/25 通过，G0 source_recovery=true。
- [x] D4/D5 六个 split 的长度/GC/CAI/RSCU/密码子使用/簇分布审计完成，见 `07_a7_data/full_audits_20261112_v2/`；非 ATG 部分 CDS、物种元数据缺失与选择偏差限制已披露。
- [x] 25 物种 ID 元数据与逐 split 分布已恢复，标准遗传代码 table 1、非 ATG 可能部分 CDS 和异常注释处理规则明确；不支持 species OOD 宣称。
- [x] untouched 24 基因 D5 确认集已冻结于 `07_a7_data/confirmation24/`，SHA256=`a128bdbf…`；长度/GC 各档均 8 条，train/val 精确重叠为 0。
- [x] D4/D5 参考表独立；D5 train RSCU 已生成于 `07_a7_data/cai_ref_d5train.json`，SHA256=`2a5e05ef…`。
- [x] 24 个独立 calibration pool 已全部生成并验证：25 个顶层 JSON，record/hash 一一对应，D5 RSCU 一致，scale 全部为正且有限；每池 56–70 个唯一目标向量。
- [x] px2 独立 CodonFlow/GEMORNA cu132 环境、完整测试和真实 CUDA matmul 均通过；px1 CUDA 不可用已留证。
- [x] 退化轴默认拒绝，指标方向、预算网格与统计配置已冻结于 `configs/a7_protocol.json`。
- [x] uniform/hill-climbing/MH/AReUReDi-style 简单搜索通过合成行为/预算测试和真实 eGFP 四方法冒烟；主实验完整 B 网格留待 G2。
- [x] 外部 baseline 资源、复跑状态和排除理由已冻结于 `configs/a7_baseline_resources.json`；远端实际输出与 unique18 manifest 仍待复核。
- [x] anytime schema、四成本和基因级统计计划通过契约测试；真实四份结果均通过 `validate_result_payload`。

## C3. G1 模型收敛且非退化

- [ ] 新 synonymous-corruption 模型具有真实 converged checkpoint；r4 e1/e2 checkpoint 完整但并未收敛，r5 精确恢复仍须重新完成 G1。
- [ ] best/last/training_state/converged、配置和 SHA256 一致且不可变。
- [ ] identity/legal = 100%。
- [ ] 至少 3 个开发基因 × 100 paired 样本中，≥95% 输出不同于初始序列。
- [ ] 每 100 个输出至少 80 个唯一终端序列，最大单一终端序列频率 ≤20%。
- [ ] stay-p、P(edit)、位置覆盖、奖励响应和 uniform 逐串重合诊断归档。
- [ ] full-token 与 edited-token 只通过同一下游协议比较，不直接比较 val 绝对值。

## C4. G2 learned vs 简单搜索（第一决定性关卡）

- [ ] learned、uniform、hill-climbing、MH/annealing、AReUReDi-style 使用 paired 初始状态和相同 scorer/cache。
- [ ] 每基因至少 3 seeds，B=50/100/500 anytime 数据完整。
- [ ] 主终点为固定参考域 HV AUC；原始 Pareto front、best-at-budget 和 NED 同步报告。
- [ ] learned 相对每基因最强简单搜索的主终点中位相对改善 ≥10%。
- [ ] gene-level paired bootstrap 95% CI 下界 >0。
- [ ] Holm 校正后 Wilcoxon signed-rank `p<0.05`。
- [ ] identity/legal=100%，长度归一化 NED ≥最强简单搜索的 70%，无单序列塌缩。
- [ ] Go/No-Go 由冻结 artifact 自动裁决；失败时不以其他弱 baseline 替代。

## C5. G3 short-rollout 净收益

- [ ] immediate 与 short-rollout 使用同一冻结 checkpoint 和 paired 初始状态。
- [ ] 质量、唯一 scorer、forward 和 wall-clock 同时比较。
- [ ] 主终点与时间成本均有正向基因级证据。
- [ ] rollout/candidate 增大时的近似偏差和成本前沿完整。
- [ ] 若未通过，short-rollout 从主贡献和主标题中移除。

## C6. G4 独立确认与外部边界

- [ ] D5 最终模型在不接触确认集的情况下训练并重复 G1。
- [ ] untouched 24 基因确认集重复 G2 主对照，无阈值/参考域事后调整。
- [ ] LinearDesign、GEMORNA、codonGPT 和最强简单搜索进入统一边界分析。
- [ ] mRNAutilus/ProMORNA/mRNA-GPT 仅在相同 CDS-only 协议可复跑时进入数值表。
- [ ] natural-source 与 protein-only 初始化分开报告。
- [ ] 输出、scorer、时间三种预算和四成本字段完整。
- [ ] 缺失方法、架构性排除和第三方预训练不可审计性显式披露。
- [ ] 仅声称操作定义的同源泛化，不写 curated family/species OOD。

## C7. G5 论文与发布

- [x] 新提纲以 learned-vs-simple-search 为中心，不以测量/审计替代科学主结果。
- [ ] Introduction/Method/Evaluation Protocol 不含未验收性能承诺。
- [ ] Results 各节均有对应 G1–G4 证据。
- [ ] 中心图为 learned vs 简单搜索的 anytime 质量—成本前沿。
- [ ] 每个数字可追溯到冻结 JSON、代码 commit、数据与 checkpoint SHA256。
- [ ] 负结果、失败模式和不可复现 baseline 与正结果同等保留。
- [ ] 无湿实验时，不出现表达、稳定性、安全性或疗效宣称。
- [ ] Gate 未通过时明确 No-Go/降级，不将当前状态写成可提交预印本。

## 当前 Gate 状态

| Gate | 当前状态 | 原因 |
|---|---|---|
| G0 数据与协议 | **通过** | `g0_gate.json passed=true`，全量分布、25 物种来源、冻结资产、三 seed 复算和 CUDA 全部通过 |
| G1 模型有效 | **未通过** | r4 两期 val checkpoint 完整但未收敛，r5 恢复尚未完成；旧 plateau 模型已证伪 |
| G2 学习必要性 | **未裁决** | 没有有效 learned 模型与完整简单搜索对照 |
| G3 rollout 净收益 | **未启动** | 依赖 G2 |
| G4 独立确认/外部边界 | **未启动** | 依赖 G2/G3 与 D5 最终模型 |
| G5 论文发布 | **不可提交** | 学习与独立确认证据缺失 |

## 永久禁止沿用的旧结论

- SOTA、capacity scaling、RL saturation、masking 普遍因果；
- 旧 family/species OOD、四层 benchmark、零泄漏总括声明；
- 旧 full-token/e14 及其三臂/联合 HV；
- 不可复核旧主表和逐基因数字；
- 以 100% identity 代替学习价值，以 val plateau 代替下游有效，以文件数代替 benchmark 完整度。
