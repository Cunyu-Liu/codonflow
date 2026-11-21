# A8-RK30 预结局工程验收

## 状态

本记录只验证实现，不包含任何新 HeLa 科学结局，不作为结构机制结果。协议与模型代码已在生成新结局前提交推送。

- 协议冻结：`5f189e1f3d4aabcc5ff221d3ab52fc1ed94da141`
- 模型冻结：`5c9f9d9660d6c17ae6d0485607810a7e00cb7d85`
- 选择性计数守卫：`2203a758df3a4615cc9158eb1b7abe2624a7a235`
- 冻结/计数测试：11/11 PASS（`freeze_tests_v4.log`）
- 模型测试：8/8 PASS（`model_tests_v2.log`）

## 完整合成端到端烟测

输入为固定 152 条 observed-R1 序列、74 个序列簇和独立合成的三条件随机结局，不用于科学解释。单线程环境为 `OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=NUMEXPR_NUM_THREADS=1`。

- 实际运输拟合：800；条件内拟合：900；总计：1,700。
- 生产耗时：225.440752 秒；所有预测、fold、training log、seed metrics/effects 与 7 组统计数组均生成。
- 生产摘要 SHA256：`a5f02fa3ab90c54c0813e40fca9d1e37a20af56392e0c0262ca06d84eae8624b`。
- 独立复核 SHA256：`9d33861fce36532eda2d4fff44bd7895dd817187df66dcbed1b198b302f5c0a0`。
- 独立实现未 import RK28/RK30 生产模型模块，重算全部 1,700 fits 与 7×10,000 resampling。
- 预测最大绝对差：`8.881784197001252e-16`；主要与次要推断及数组差：0；folds 差：0。

## 保留的失败与修复

1. 初次下载因复用引擎要求 `.part` 已存在而停止；在读取 FASTQ 序列前修复临时文件初始化，失败日志保留。
2. 初次多线程烟测出现 46 线程的小样本开销，主动停止并保留 `smoke_model_multithread_aborted_v1`；正式执行固定单线程。
3. 初次独立烟测科学数值全部一致，但 pandas 将 arm 名称 `null` 读成缺失值而总体 FAIL；保留 `RK30_SMOKE_INDEPENDENT_v1.json` 和 `independent_v1.log`，仅修正独立读取参数后全量重跑至 PASS。
4. 选择性 HEK 计数首次在过滤前要求全部 64 个文件存在；未生成新结局。修复后增加回归测试并提交 `2203a758`。

## 新真实计数的首个先验 QC

既有 HEK293 `SRR10714593`（CM2_Bin1）固定参考计数为 1,245,343 assigned reads；152/152 变体与 RK28 同 bin 计数逐值一致。该 run 的 100 条 reservoir reads 经独立蛮力最近参考分配，0 mismatch。其余 run 与新 HeLa 条件必须完成同样的全量验收后才可用于正式分析。

## 并行计数等价性

新增可选 `--workers`，默认仍为 1；每个进程只写一个独立 run checkpoint，全局长表和结局仍由主进程统一生成。4 进程重算全部 8 个 HEK run 后，与原串行 checkpoint 的 `counts`、`metrics`、`audit_samples`、实验映射、输入字节数和输入 SHA256 均逐字段一致（8/8，`HEK293_PARALLEL_EQUIVALENCE.json`）。因此完整 64-run 计数使用 8 个 CPU 进程；该并行设置不改变分配规则、audit seed 或结局公式。
