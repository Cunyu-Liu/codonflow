# A8-RK33 预注册卡：Mordstein observed-R1 局部覆盖判别实验

## 科学问题

在完全相同的 Mordstein HEK293 observed-R1 变体、序列簇划分、simple 特征、模型和推断下，CDS4–45 的 42-nt 局部 ViennaRNA MFE 是否比无结构、单个 full-300 MFE 及 RK28 的 full-300+48-nt 窗口三特征臂产生稳定的整簇 OOD 增量？

## 已观察现象与可判别范围

- RK32 在 Kudla 固定 GFP 上显示，−4…37 的 42-nt 局部结构臂有增量，而多个 full 结构定义未通过完整门槛。
- RK28 在同一 Mordstein 队列上，full-300 与 48-nt 窗口结构臂未显示增量。
- 本实验只改变结构覆盖与结构臂参数数目，宿主、assay、变体、标签、折和模型均不变，因此能判别 observed-R1 内“局部/全片段定义”与“单特征/三特征”差异。
- observed FASTA 从 CDS 第 4 位开始；本实验没有起始 ATG、上游 4 nt、完整 UTR–CDS 或 measured structure。它不能精确复现 Kudla −4…37，也不能区分宿主、assay、measured-vs-predicted、dangles=0/2 的效应。
- 标签已用于 RK02/RK28/RK30/RK31，本实验是 `retrospective_outcome_known_coverage_followup`，不是独立 untouched 确认。

## 冻结数据与划分

- 152 个 finalized variants、152 条唯一 300-nt observed-R1；74 个既有 90% complete-linkage 序列簇。
- 逐字复用 RK28 的 10 seeds×5 folds 共 1,520 个整簇折分配与 primary seed=20261222。
- simple 固定为 log1p(depth)、GC3、GC、CpG、CAI，与 RK28 完全一致。
- 不重新聚类、不改 split、不搜索窗口、不读取 functional untouched。

## 冻结模型臂

1. `simple`：复用 RK28 已验收预测。
2. `local42`：simple + observed sequence 第 1–42 nt（即 CDS4–45）的单个 ViennaRNA MFE。
3. `full1`：simple + 单个 full-300 MFE；用于同参数数目的覆盖对照。
4. `full3`：复用 RK28 simple + full-300 MFE + 所有 48-nt 窗口 min/mean MFE 的已验收预测。

ViennaRNA 固定 37°C、dangles=0，与 RK28 一致。Ridge/HistGB 超参数与 RK28 完全一致。新拟合仅为 local42/full1：10×5×2×2=200；复用 simple/full3 的 200 个拟合，评估总量 400。

## 主终点与 Gate

三个比较家族：`local42−simple`、`local42−full1`、`local42−full3`。每家族对 Ridge/HistGB 各评估全局 OOF Spearman 增量与 MSE 改善，共 12 个终点，统一 Holm。

每个终点须同时满足：observed effect>0、20,000 次整簇 bootstrap 95% CI 下界>0、20,000 次整簇成对置换经 12 终点 Holm 后 p<0.05、至少 8/10 seeds 正向。

分别报告三家族的 4/4 Gate；只有 12/12 全部通过才支持“局部覆盖同时超过无结构和两个完整片段对照”的完整主张。任何失败均保留，不追加窗口或调参。

## 结论与下一步

- local42−simple 4/4 通过：支持本 observed-R1 队列中的回顾性局部结构增量。
- 对 full1/full3 的家族未全通过：不得声称局部定义优于完整结构定义。
- local42−simple 未全通过：本局部覆盖假设未获支持；不把 RK28 的失败简单归因于片段过长。
- 无论结果如何，均不授权昂贵生成训练、不闭合 RK-G1、不宣称跨研究精确运输。若局部增量成立，下一关键缺口是恢复 full UTR–CDS reference 后做真正 start-aware 的预注册运输；否则应转向其他可追溯完整 CDS 数据，而非继续搜索窗口。
