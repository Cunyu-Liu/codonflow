# A8-RK30 预注册：Mordstein 同库 matched-context 结构运输

## 状态与边界

本文件在任何 HeLa Flow-seq 结局生成、读取或模型拟合之前冻结。RK29 的 iCodon 序列—结局连接失败保持不变；RK30 是新的独立预注册，不通过行号、任意首匹配或 target-informed 选择挽救 RK29。

RK30 只使用 Mordstein 同一 GFP 文库的三种条件：HeLa 无 5′UTR intron（CM5a–e）、HeLa 含 5′UTR intron（CM9a–b）和 HEK293 无 intron（CM2）。研究、载体、变体文库、观测片段与结构定义固定；宿主和 intron 条件分别检验。它仍不是 measured structure、完整 CDS、protein OOD、translation velocity 或 decay 研究。

## 数据与计数冻结

- 固定 RK28 的 152 条 observed-R1 300-nt 序列及 74 个 complete-linkage 序列簇，不重新聚类，不重新挑选变体。
- 只下载 HeLa 的 56 个 R1 FASTQ；既有 HEK293 的 8 个 R1 同步重算。R2 不参与新计数。
- 每条 300-nt R1 用九段精确索引分配到唯一最近参考；最大 Hamming 误差 8 nt。超过 8 nt、最近参考并列、长度不符均为 unassigned。
- 每个 experiment 必须有 Bin1–8。变体在每个 replicate 的八 bin 合计至少 1,000 assigned reads 才有效。
- 单 replicate 结局为 `sum(i*count_i)/sum(count_i)`，条件结局为全部指定 replicate 分数的等权均值。
- 只有八个 experiments 全部通过 read-support 的变体进入共同队列。共同队列至少 100 variants、50 clusters，否则 `MATCHED_CONTEXT_COVERAGE_INFEASIBLE_ZERO_FITS`，不得改阈值或事后筛选。

## 特征、公平 baseline 与 folds

- simple：observed-R1 GC3、GC、CpG/100nt、CAI。测序深度只用于 QC，不作为跨条件生物预测变量。
- structure：simple + 全 300 nt MFE、所有连续 48-nt 窗口最小 MFE、窗口平均 MFE。
- MFE-only 仅作条件内描述性参考；训练折均值为 null。
- backbone：Ridge(alpha=1) 与 HistGB（完全沿用 RK28 超参数），CPU-only，不调参。
- 相同变体、相同序列簇、相同 10 seeds × 5 folds。训练折外任何目标结局均不用于拟合、缩放、选择或调参。

## 主要运输检验

四个有序方向预先固定：

1. HeLa 无 intron → HEK293 无 intron；
2. HEK293 无 intron → HeLa 无 intron；
3. HeLa 无 intron → HeLa 含 intron；
4. HeLa 含 intron → HeLa 无 intron。

每个方向仅使用源条件的非测试簇结局训练，在目标条件的整簇 held-out 变体上评价。每个 backbone 比较 structure 与 simple；主要终点为 ΔSpearman=structure−simple 和 MSE improvement=simple−structure，正值有利于 structure。

- 每方向 4 个终点，共 16 个主要终点；primary seed=20261222。
- 每方向 10,000 次整簇 bootstrap 和 10,000 次整簇 sign-swap permutation。
- 16 个主要终点统一 Holm 校正；每个终点要求 effect>0、95% CI 下界>0、校正 p<0.05 且至少 8/10 seeds 正向。
- 某方向只有四项全部通过才算该方向通过；四方向全部通过才支持广泛 context-transportable MFE increment。任何失败均记为不支持该广泛主张，并逐方向报告，不能写成普遍负机制。
- 三条件内的相同 simple/structure 评价为次要分析，12 个终点单独 Holm，不得挽救主要运输家族失败。

## 计算、验收与后续门禁

预计 800 次运输拟合 + 900 次条件内拟合 = 1,700 次真实 CPU fits。输出共同队列、逐 replicate QC、OOF predictions、fold assignments、training log、seed metrics、effects、CI、p 值、统计数组、运行时间与软件环境。

新协议、计数代码和合成测试先提交并推送 GitHub，再生成新结局。生产结果必须由不 import 生产或 RK28 模型模块的独立实现复算；通过后才写研究 PPT。每一验收阶段分别提交并推送。

无论结果正负，均不自动授权昂贵生成训练、functional untouched 读取或 RK-G1 闭合。外部 iCodon 等工具与本固定 GFP observed-R1 任务不匹配时不列为已运行 baseline，也不宣称 SOTA。
