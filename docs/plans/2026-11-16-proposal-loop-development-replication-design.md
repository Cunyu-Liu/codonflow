# Proposal-in-the-loop 开发集复现协议（2026-11-16）

## 目的与不可逾越的边界

T3.7在3个G1开发基因上显示：learned T=1提议置于terminal hill-climbing后，AUC关联多为正，但所有run更慢，FULL一个基因近零收益。本协议检验该关联在unique18其余15个开发基因上是否可复现，并同时评价成本。它不是G2重跑、G3、独立确认或新科学验收门；不得翻案G2，不得接触D5 untouched确认集，不得启动short-rollout、扩参、RLOO或SOTA写作。

## 路线选择

1. **采用：其余15个开发基因复现。** 扩展基因覆盖，排除参与T3.7设计的三基因；成本可接受，能检验方向稳定性，但仍只属开发证据。
2. 不采用：原三基因增加seeds。只能更精确估计已有三基因的随机性，不能回答跨基因稳定性。
3. 禁止：使用D5 untouched 24基因。当前G2 No-Go，不得将诊断转为确认集调参。

## 冻结样本、模型与对照

- 样本：unique18中排除`C31E10.3b.1`、`C14A6.7.1`、`C01H6.8b.1`后的全部15个ID，不按长度、GC、既有结果或资源挑选。seeds 0/1/2，基因是统计单位，seed不是独立生物样本。
- 模型：FULL r5 e21 SHA256=`e6a26102b0f5ae9443dbfb9526d418169ba577138016e70430203d80eef16d1c`；EDIT r5 e26 SHA256=`77e81b5b9af886c2cc4a712fc064e5fc3c3c6f7386369a27916d67758736a9df`。
- 提议：与T3.7相同`SynonymousJumpProposal`，T=1、path_batch=1、无terminal guidance、无rollout，每次只产生一个候选。
- 优化器：冻结calibration normalization、四目标权重`(1,1,1,0.5)`、`delta >= 0`接受规则和每run独立cache。
- 对照：复用G2相同基因/seed的random single-codon hill-climbing，不更换为较弱baseline。逐项核对source、paired initial、benchmark、data split、calibration、RSCU、500唯一解和SHA。
- 新分片：FULL/EDIT各15×3=45，共90个learned-hill结果。每run恰好500唯一terminal evaluations；尝试上限100,000，与T3.7技术修正1一致。 learned必须使用真实CUDA，禁止CPU降级。
- 输出：独立目录`eval_outputs/a7_proposal_loop_development15/`，不得覆盖G2、T3.7或partial。代码/commit允许集合启动前冻结，dirty tree直接失败。

## 共同主要结局与分析

1. **质量**：固定独立参考域anytime AUC。每基因先在3 seeds内取均值，再计算learned-minus-random绝对与相对差；报告中位相对变化、15/15逐基因值、seed方向、paired bootstrap 95% CI、Wilcoxon和双臂Holm校正。统计仅描述开发集关联，不构成Go/No-Go或独立确认。
2. **成本**：每基因learned/random wall-clock均值比、逐run耗时、forward calls、cache前terminal请求和唯一scorer。记录实际并发和共享硬件限制；wall-clock不是隔离微基准，不得用质量正向掩盖时间劣势。
3. **辅助**：长度归一化NED及ratio、四目标best-at-budget。不得事后选择更有利参考域、baseline、基因或预算。

Gate必须独立重算原始点identity、500唯一解、AUC、NED、配对哈希与聚合。第二套原始点审计复核数值和成本，保留所有不利结果。输出固定`exploratory_not_gate=true`、`scientific_gate_passed=false`。

## 停止与解释规则

CUDA不可用、checkpoint/RSCU/calibration/benchmark哈希错误、初始不配对、dirty code、partial、identity<100%、唯一解<500、重复分片或未登记commit均停止并留证，不进入统计。partial按内容SHA移入独立`partials/`目录，不能覆盖或删除。尝试上限耗尽时不得再事后提高；如需修改必须另写技术修正且仍不得翻案G2。

完成前不得挑选基因写结论。正向质量关联若伴随显著时间成本，只能形成效率改进假设；负向或不稳定关联支持当前No-Go。任何后续效率实验必须另行预登记，不得借本复现进入G3或D5。

## 实施与验证

复用T3.7 worker、严格resume、partial隔离和独立Gate；仅增加显式15基因任务生成与统计，不改变模型、采样或accept/reject。测试覆盖15基因完整集合、排除三基因、缺失/重复/错误基因拒绝、混合commit白名单、partial拒绝、原始指标与成本聚合。先聚焦测试、完整回归和真实dry-run，再双臂各一个worker并行执行。smoke和单基因结果不得写成最终结论。


## 技术修正 2：development15剩余FULL分片并行恢复（启动前登记）

用户明确要求提高GPU并行度。原执行器PID 2071716的EDIT 45/45已完成，FULL仅单worker运行且显存空余。原父执行器先SIGSTOP，当前C47A4.1.1 seed2子进程继续至原子写出；只有该子进程完成后才结束旧父进程，不中断或丢弃当前分片。旧running状态保留，随后以唯一任务列表resume，不允许新旧两个执行器同时启动新分片。

执行器新增`--workers-per-arm`，默认1保持原行为，本次仅FULL剩余分片显式使用12。所有任务仍是原15基因×3 seeds，已完成分片严格校验后跳过，不改变checkpoint、paired initial、T=1、accept/reject、calibration、500唯一scorer、100,000尝试上限、代码白名单或统计规则。子进程真实CUDA、identity、500唯一解及dirty-tree停止条件不变。

资源实测：GPU总显存32607MiB，当前16289MiB；CPU 16核、内存60GB。12个worker按每片约972MiB估算总显存约28.9GB，不继续增加进程。并发、代码commit和恢复历史必须写入状态。不同并发的wall-clock只作实际成本描述，不作为隔离微基准或直接速度胜负；最终AUC/NED/scorer口径不变。
