# G2 proposal-in-the-loop diagnostic design（2026-11-16）

## 目的与边界

G2 已正式 No-Go，不得翻案或进入 G3。本诊断只回答：在完全相同的 accept/reject 局部优化器中，learned 单密码子提议是否比随机单密码子提议含有更可用的目标偏好。阳性结果只形成后续研究假设，阴性结果支持当前负结果，均不称为通过 G2、模型优势或预印本性能结论。

## 路线比较

1. **推荐：proposal-in-the-loop 消融。** 复用现有模型、校准和 G2 hill-climbing 结果，只新增 learned-hill 分片。直接隔离提议分布，成本与混杂因素最小。
2. 新目标条件模型训练。可研究终端目标学习，但需重新收敛/G1/G2，成本高且不能先回答现有核是否有用。
3. 仅写负结果、不再诊断。证据完整，但不能进一步区分 objective-blind 提议与优化器不足。

## 冻结协议

- 模型：FULL r5 与 EDIT r5 converged checkpoint，SHA 与 G2 相同；不得使用 live best。
- 数据：G1 三基因 `C31E10.3b.1`、`C14A6.7.1`、`C01H6.8b.1`，seeds 0/1/2，只作开发诊断，不是独立确认。
- 提议：当前 `SynonymousJumpProposal`，T=1、无 terminal guidance、无 rollout。每一步只生成一个候选。
- 优化器：与 G2 hill-climbing 相同 frozen calibration normalization、四目标权重 `(1,1,1,0.5)`、`delta >= 0` 接受规则和独立 cache。
- 对照：直接复用 G2 同基因/seed 的随机单密码子 hill-climbing 结果，核对 source、paired initial、benchmark、calibration、RSCU、split、500唯一解和SHA；不重新生成随机基线。
- 新分片：每臂3基因×3 seeds=9，共18个 learned-hill 结果，每run恰好500个唯一 terminal evaluations。learned 使用真实 CUDA，禁止CPU降级。
- 记录： anytime AUC、四目标 best-at-budget、NED、forward、终端请求、唯一scorer和wall-clock。所有输出在 `/teams/.../eval_outputs/a7_g2_proposal_in_loop_diagnostic/`。

## 停止与解释规则

CUDA不可用、checkpoint/RSCU/calibration哈希不符、初始不配对、dirty code、partial、identity<100%、唯一解<500或未登记commit均立即停止并留证，不进入统计。诊断前冻结代码提交和输出目录，不覆盖G2。

主要描述 learned-hill 相对既有 random-hill 的逐基因AUC方向、四目标差距、NED和耗时，不设置事后Go阈值，不修改G2。只有预先登记的后续独立实验才可检验新假设；不得据此启动short-rollout、D5确认、扩参、RLOO或SOTA写作。

## 技术修正 1：唯一解不足时的尝试上限（恢复前登记）

FULL `C14A6.7.1 seed1` 首次运行在25,000次提议后仅得到388个唯一解，以`max_attempts_exhausted`结束；其SHA256=`1c127354c11944d2d7f3e5069996c44d42b2b184530c80aa93c37eea8c11fb6c`。这是重复候选导致的工程上限，不是CUDA故障或科学Gate结果。原执行器与自动Gate均已停止，partial未进入统计。

在读取该分片结局后、任何重跑前，将后续诊断的提议尝试上限统一登记为100,000；500唯一terminal scorer、paired initial、模型、seed、accept/reject、calibration、NED/AUC和全部科学解释边界均不变。已完成分片未触及该上限，不重跑。缺失分片从相同初始和seed完整重算，原partial连同SHA移入独立`partials/`目录，禁止覆盖、删除或作为完成结果。新运行若仍不足500唯一解，继续保留partial并停止，不进入Gate。

## 实施与验证

为 `SimpleSearch` 增加可选 proposal callable，默认行为逐字节保持不变；学习提议适配器只负责T=1候选。单元测试覆盖默认路径不变、非法提议、cache/唯一预算、接受规则与CUDA缺失拒绝。先跑聚焦和完整回归，再做小规模CUDA工程检查；smoke不进入科学结论。完成后独立重算原始指标并提交代码、日志和负/正诊断，不选择性删除结果。
