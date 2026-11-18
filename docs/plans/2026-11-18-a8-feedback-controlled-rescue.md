# A8 反馈受控抢救与预印本计划（2026-11-18）

> 主合同：`docs/handover/spec.md`；可执行任务：`docs/handover/tasks.md`；完整审查：`docs/review/CodonFlow_A8_严格科研工程审查与一个月路线_20261118.md`。
> 当前 A8-G1 未执行，禁止把本计划写成结果。D5 untouched、扩参、短 rollout、RLOO 和新预训练均未放行。

## 1. 要回答的唯一首要问题

在蛋白、随机同义初始状态、目标权重、终端反馈、scorer预算和硬件成本一致时，学习提议是否比随机局部提议产生更好的多目标 anytime 质量，并具有时间优势？

原 G2 的 open-loop No-Go 保持有效；本计划只解决失败归因，不撤销旧结果。

## 2. P0 顺序

1. 冻结代码/权重/数据/环境hash；本地漂移只写报告，使用新的干净工作树。
2. 保留 legacy sparse AUC v1，新增 dense budget-step AUC v2 和合成测试。
3. 从原始序列独立重算分层 CAI/MFE/GC/motif，而非仅重算已存 objectives。
4. 测量合法同义概率质量、候选分数—Δutility、编辑率、路径梯度与成本。
5. 执行反馈匹配2×2并裁决；未通过则不训练。

## 3. 2×2 因子协议

- 因子A：`proposal={random,learned}`。
- 因子B：`terminal_feedback={off,on}`。
- 模型：FULL/EDIT r5，均冻结。
- 基因：用长度/GC分层规则从 unique18 选择6个开发基因，在看到新结果前冻结ID。
- seeds：0/1/2；B=500唯一terminal scorer；同一 paired initial。
- 总单元：2 proposals×2 feedback×2 arms×6 genes×3 seeds=144。可复用旧 feedback-on 分片前必须逐字段等价审计；否则重算。
- off：random/learned 都只做单密码子open-loop提议，不按utility接受/拒绝。
- on：random/learned 使用同一 hill accept/reject、同一提议合法性和预算规则。
- 主对比：learned-on vs random-on；off与交互解释机制。不得只用learned-off vs random-on代替。

## 4. 指标

### 主指标 v2

每个真实唯一 scorer 点 `b=1…500` 计算截至该点的累计HV。令真实初始评分点的HV为 `HV_1`：

`dense_budget_step_auc_v2 = sum(HV_b for b=1…499) / 499`。

不添加 `(0,0)` 假点，不将真实初始点丢弃。参考域和尺度必须来自每个冻结的独立 per-gene/seed calibration，不能混入benchmark测试输出。

### 次要指标

- legacy sparse AUC v1，用于历史复现；
- B=50/100/500 raw Pareto、best-at-budget、双向严格支配率；
- NED、identity/legal、cache前请求、forward、wall-clock；
- 单 worker time-matched HV；高并发时间只作描述。

外部方法只有实际输出集合时，不构造500点AUC；报告实际集合Pareto/best、真实或未知成本及输入差异。

## 5. Gate与止损

- A8-G1：2×2和机制诊断决定是否有独立学习价值。
- A8-G2：18开发基因中位dense AUC改善≥10%、CI下界>0、Holm p<0.05，identity/legal=100%、逐基因NED≥70%，且time-matched改善及CI下界>0。
- A8-G3：仅在G2通过后评估D5 untouched24一次。
- A8-G4：外部输入、实际输出、目标、成本和污染边界可比。
- A8-G5：所有论文数字可回溯原始JSON，负结果与限制完整。

最多两轮终端对齐/成本实验。若 learned-on 无稳定正效应，或两轮后仍无质量—时间优势，停止学习模型主线，转交负结果和benchmark。

## 6. 一个月路径

- Day0–2：版本、数据、原始scorer、registry。
- Day1–4：dense v2、外部actual-set、单worker成本。
- Day3–7：机制诊断与2×2；并行核查代理效度。
- Day6–14：若G1通过，终端对齐轻量微调；最多两轮。
- Day12–21：开发18、消融、time-matched；通过后untouched与外部。
- Day18–25：机制、失败边界、主张—证据矩阵。
- Day23–30：干净复现、图表、预印本与最终交接。

所有训练必须写入 `experiments/REGISTRY.md`：配置、数据/代码/权重hash、GPU、命令、best/last/convergence、结果、结论和不可声称事项。
