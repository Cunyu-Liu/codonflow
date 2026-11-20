# A8-RK28 预注册卡：HEK293 固定 GFP 观测 R1 结构增量的序列簇 OOD

## 科学问题

在不同研究、宿主和 assay 中，向同一简单基线加入观测 R1 的 ViennaRNA MFE 特征，能否在固定 GFP 的整序列簇 OOD 下稳定改善 HEK293 intronless Flow-seq 预测？

## 已观察现象

- RK27 在 Kudla 固定 GFP、E. coli、完整 CDS 的序列簇 OOD 上发现 measured 5′ MFE 强增量。
- RK02 已在 Mordstein HEK293 的 152 个观测 R1 变体上完成随机变体 development 五折，结构增量为 no-go；该数据从未做整序列簇运输检验。
- RK28 使用的是 300 nt 观测片段的计算 MFE，不是 RK27 的完整 CDS measured MFE，也不是完整 CDS 或作者 GFP 身份恢复。

## 可证伪假设

对 ridge 与 HistGB，simple+structure 相对 simple 的全局 OOF Spearman 差和 MSE 改善均为正；序列簇 bootstrap 95% CI 全部高于 0，四项 Holm 校正整簇置换 p<0.05，且每项至少 8/10 个折分配 seed 方向为正。

## 数据、标签隔离与划分

- 152 个 finalized 变体；只允许覆盖脚本读取 `variant_id` 与 `sequence_5prime_300nt`。
- 90% complete-linkage 阈值现在冻结，不允许根据覆盖或结果另选阈值。
- 至少 10 簇、最大簇≤121、primary 五折各≥5 条且各≥2 簇，并要求 152 个唯一 ID 和唯一 300-nt ACGT 序列。
- 不满足即 `COVERAGE_INFEASIBLE_ZERO_FITS`，不读取 outcome、不计算模型特征、不拟合。

## 对照与主指标

- simple：log1p 测序深度、观测 R1 GC3/GC/CpG/CAI。
- structure：simple + 300 nt 全长 MFE、所有 48 nt 窗口最小/平均 MFE。
- MFE-only 仅描述，训练折均值为 null；不偷换确认性对照。
- 四终点：ridge/HistGB 的 structure−simple Spearman 与 simple−structure MSE。

## 统计与计算

- 10 seeds×5 folds×2 backbones×3 arms，若可行共 300 次 CPU 拟合。
- primary seed 20261222；20,000 次整簇 bootstrap（20261323）与 20,000 次整簇成对置换（20261324）；四终点 Holm。
- 无调参、无 GPU、无 functional untouched 访问；生产与独立实现不得共享模型/统计实现。

## 反驳条件与下一步

任一主终点失败，即否定本研究的 HEK293 观测 R1 结构运输主张。通过只支持回顾性跨研究结构增量，并促使寻找真正独立的完整 CDS 功能验证；失败则去除跨宿主/assay 稳健结构增量的主张。两种结果均不单独完成 RK-G1、不授权昂贵生成训练。
