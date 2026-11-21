# A8-RK41 预注册：内部多起点盆地初始化与共同输入复评

冻结时间：2026-11-22（UTC+8）  
协议：`configs/a8_rk41_internal_basin_protocol_v1.json`  
protocol_id：`RK41_INTERNAL_BASIN_INITIALIZATION_V1`  
协议 SHA256：`9ed2657dfe698bc096eb1e1fe853a723f26bd69dcd3b0bc768e4f946412dc83a`

## 冻结前状态

已观察 RK39 的共同输入 actual-set 双终点失败，以及 RK40 的归一化、预算和外部初始化诊断。尚未生成或读取任何 RK41 初始化池、新搜索轨迹或新终点结果。本文件与协议在第一次 smoke 和正式生产前冻结。

## 科学问题

1. 在同一8成员内部初始化池和相同11次 unique-scorer 总预算下，按搜索 utility 选择起点是否优于固定首起点？
2. 这种内部多起点分配是否优于原来的顺序11点 hill-climbing？
3. 新的 raw 内部设计能否在固定蛋白、固定 TAA、统一后评价和记录特异的实际输出数 k 下优于 LinearDesign-11 actual set？

前两项是机制问题，第三项直接复评 RK39 的失败。第三项失败时，即使前两项通过，也只能称内部机制得到支持，不能称共同输入任务已解决。

## 冻结设计

- 18个 development records，seeds=0/1/2。
- 接受 RK40 已独立验证的 `raw_random_b11` 和 `calibrated_random_b11` 共108个 runs。
- 新增 `raw_pool_first_b11`、`raw_pool_best_b11`、`calibrated_pool_first_b11`、`calibrated_pool_best_b11`，共216 runs/2,376 unique-scorer calls。
- 每个新 run：8个 protein-only 随机同义起点全部真实评分；首起点臂选择 index0，最佳起点臂按对应搜索 utility 选择；共享 cache 后继续 hill-climbing，直至恰好11个唯一输出，即再增加3个新点。
- 所有新臂只由蛋白翻译模板生成，不使用 LinearDesign、EnsembleDesign、天然同义 DNA 或其他外部序列。
- raw 臂在选择和搜索阶段不读取 native calibration，保持共同输入；calibrated 臂只作尺度交互诊断。

## 终点和统计

三个独立 primary families：

1. `raw_common_input_basin_selection`：raw best−raw first；终点为 best normalized weighted utility 和 best single-point normalized HV。
2. `raw_common_input_sequential_advantage`：raw best−raw random B11；同上双终点。
3. `common_input_actual_set_versus_linear_design`：raw best−LinearDesign-11；终点为记录特异 first-k actual-set HV 和 pairwise NED。

统计单位为 record，三个 seed 先取均值；20,000 paired bootstrap（seed 20261142）和20,000 sign-flip（seed 20261143）；每 family 内两个终点 Holm。family 通过要求两个终点均满足 CI 下界>0、Holm p<0.05且三个 seed 的效应均为正。

不接受 best-k、补零、外部 dense 反推、事后改变 pool size、根据 smoke 或正式结果调整选择规则。smoke 只验证执行和独立重放，不能作为正式证据。

## 验收与边界

必须完成：正式生产、独立8点池/选择/完整轨迹重放、独立四目标重算、独立指标与推断、detached clean reproduction、全项目测试、英文稿和在线 PPT 逐页验收、registry/tasks/handoff 及 GitHub 推送。

无论结果如何，均不自动授权 external SOTA、统一 time-matched、完整七方法共同 dense、functional/protein OOD、untouched、生成训练、RK-G1 或 manuscript submittable。wet-lab 不执行。
