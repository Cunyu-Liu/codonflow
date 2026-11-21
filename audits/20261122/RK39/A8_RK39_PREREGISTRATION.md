# A8-RK39 预注册：共同输入、等实际输出数的固定蛋白对照

日期：2026-11-22  
协议：`configs/a8_rk39_common_input_actual_set_protocol_v1.json`  
状态：**FROZEN_BEFORE_PRODUCTION**

## 1. 判别问题

RK38 已完成 18 records × 7 methods 的 actual-set 盘点，但尚未回答：在不向搜索提供天然 CDS 或天然来源归一化、且输出集合大小完全配对时，CodonFlow 的蛋白-only simple-search 能否在同一固定蛋白代理任务上优于最强已盘点 HV baseline LinearDesign-11。

本实验只评价 18 个 development records 的终端 actual sets，不是功能实验、独立 untouched、time-matched 或外部 SOTA 授权。

## 2. 共同输入与排除的信息

- 将天然 CDS 仅用于翻译得到蛋白；随后丢弃所有天然同义密码子选择。
- 用蛋白构建固定的首同义密码子模板，再逐位随机生成同义 `x0`。
- 终止密码子统一为 `TAA`，与所有 LinearDesign-11 和 EnsembleDesign-11 输出一致。
- `SimpleSearch(normalization=None)`；搜索阶段不读取天然来源 calibration。
- 搜索完成后才加载冻结 calibration，只用于对所有方法做相同评价归一化。
- 固定 RSCU、GC target、motif scorer、四目标权重和随机种子。

## 3. 预算与实际集合配对

每 run 生成 11 个连续 unique-scorer points，B1 为蛋白-only 随机同义初始状态。总计 18 records × 3 seeds × 3 methods = **162 runs / 1,782 unique scorer calls**。

对每个 record：

1. 从冻结矩阵读取 LinearDesign-11 的真实唯一 DNA 输出数 `k`，要求 `1≤k≤11`；
2. 取 simple-search 前 `k` 个真实 unique-scorer 输出；
3. 与 LinearDesign-11 的全部 `k` 个输出比较；
4. 禁止 best-k、事后挑子集、补零、重复点 padding 或推断外部 dense 曲线。

## 4. 主终点、统计与胜负

主方法预先固定为 `hill_climbing`；参照为 `lineardesign_lambda11`。两个共同主终点：

- normalized hypervolume，越大越好；
- pairwise NED，越大越好。

效应为 simple-search − LinearDesign-11。先对每 record 的 3 seeds 取均值，再以 18 records 为配对单位；20,000 次 paired bootstrap、20,000 次符号翻转、两终点 Holm。

**只有同时满足以下条件才通过本代理任务：**

1. 两个终点的 95% CI 下界均大于 0；
2. 两个终点 Holm-adjusted p 均小于 0.05；
3. 两个终点在 3 个单独 seed 上的平均效应均为正。

任一失败即保持 `COMMON_INPUT_ACTUAL_SET_TASK_UNRESOLVED`。MH-annealing 和 uniform 仅为诊断敏感性臂，不得替代失败的主门控。

## 5. 成本与证据边界

记录每 run 的 wall time、objective-scoring time、residual generation/cache/proposal time、请求数、缓存命中和 unique-scorer calls。LinearDesign 内部 DP 成本与外部生成成本未端到端匹配，因此不得写成统一 time-matched 效率结论。

无论结果方向如何，均不自动授权：功能有效性、protein-OOD、untouched 泛化、七方法共同 dense 排名、外部 SOTA、CodonFlow-RK 生成器提升、RK-G1 或 manuscript-submittable。
