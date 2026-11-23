# HANDOFF A10-03：E2 v6 进行中

- 日期：2026-11-24
- 阶段：A10-03 / E2
- 状态：**IN PROGRESS；真实 CUDA 训练未完成，E2/H2/G1 尚未裁决。**
- 本文只登记已核对的运行事实，不预写科学结果。

## 1. 当前权威状态

- 工作树：`/home/codonflow-a10-e2-v2`；当前提交 `f9c0a4d5`，运行前定向回归 108 passed、1 个本机 CUDA skip。
- 数据：Mohammad16 开发集，严格 QC 后 1073 条转录本；1761 原始记录中缺 ATG 171、覆盖不足 517，其他拒绝与 ID/exact-CDS 冲突均为 0。长度 16–1521 nt。
- 输出：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/a10/e2/kinetic_development_v6`；日志为同路径加 `.log`。
- 协议：3 outer×3 inner×3 seeds；三臂为 independent、kinetic、position；65/65/1 个单模型参数，均用三成员 inner ensemble。
- 运行快照已有 36 条完整配置曲线，覆盖 seed 1234、outer 0 的 independent 与 position；kinetic 主臂及其他 outer/seed 尚未完成。此快照没有 outer 预测、效应或统计判决。
- 入选曲线均记录 `validation_plateau`；50-epoch rung 淘汰曲线均记录 `rejected_at_rung_not_converged`。入选者恢复 rung-last 的模型、AdamW 与 RNG 状态，续训无最终 epoch 上限。
- GPU 运行由进程记录与真实 CUDA 前后向探针支持；不是 CPU 降级。当前只核对运行，不以显存或利用率代替科学结果。

## 2. 训练与数值失败链

| 版本 | 已确认事实 | 判决 |
|---|---|---|
| v1/v3 | 低 LR 在 2000 epoch 时仍下降，主动停止；曲线保留 | 未收敛，不作科学结论 |
| v2 | 严格 QC 数量变化，在训练前停止 | 无训练结果 |
| v4 | 长序列的原始及缩放多维求根不收敛 | fail-closed；日志与曲线保留 |
| v5 | 瞬态后备仍有样本归一化残差 `6.395e-03 > 1e-10` | 不接受、不放宽阈值 |
| v6 | 逐段延长瞬态积分，每段检查完整残差；训练进行中 | 尚无最终结果 |

平均场实现位于 `src/codonflow/models/kinetic_mean_field.py`。它包含单样本/变长 batch、解析 Jacobian、隐式梯度、守恒检查、行缩放、iterative refinement 和自适应 LSODA 后备。平均场不是精确随机模拟；ensemble 均值不是共同稳态，只能逐成员检查守恒。

## 3. 下一步与验收

1. 不重复提交 v6，不覆盖旧产物；等待 `summary.json`、`predictions.npz`、`selected_inner_states.npz`、selection、逐转录本指标和完整 curves。
2. 用 `scripts/a10_03_verify_e2_kinetic.py` 从原始数据、split、保存状态独立重建预测；用 SciPy 独立复核每个 kinetic 成员稳态，并核对 CUDA、成本、双比较 Holm 与 seed-first pooled CI。
3. 只有完整 outer 预测和独立复核通过后，才记录 H2 开发效应、CI、成本与收敛；不能从 inner 曲线推断 outer 阳性。
4. G1 按原合同裁决：E2 严格 transcript OOD 同时超过 independent 与 position，paired 95% CI 下界大于 0 且 Holm 通过。开发结果不等于最终研究 OOD、绝对速率、SOTA 或真实功能验证。
5. 若 G1 未通过，停止动力学主线；若通过，才允许已验证动力学量进入 E3。生成训练仍须等待 G2。

## 4. 局部同义响应证据边界

局部同义响应属于 H2 的证据要求，但直接实验尚未闭合；**它不是原合同中额外添加的 G1 必要条件**，不得用这一附加条件改写预注册 Gate，也不得用模型预测冒充实验响应。

- Yu2015/GSE71032 raw tar SHA256=`851b0bbca80bd363f4e2d50766b4ca6154308c03a3df28006df199a0a1641612`。
- OPT/Cwt-Opt 均 1839 nt；CDS 为 zero-based `[100,1753)`，1653 nt/551 codons 含 stop；蛋白翻译一致，差异在 CDS 424–551，stop TGA→TAA。
- Cwt-Opt WIG 有完整 reporter，OPT WIG 没有对应 reporter；需 raw reads 重映射，不能直接配对。
- 每构建仅一个样本，不支持重复完备的局部同义响应或阳性结论。
- Tunney 无变体 Ribo；GSE189404 局部 CGA12 非同义；GSE202900 是整段 FLuc 重编码。均不能直接补足当前局部同义响应证据。

## 5. 工程与论文边界

- E2 v4 代码时项目完整回归曾为 877 passed、0 failed、2 skipped，报告 SHA256=`1abed7e5d721f7996cef363b7a96c94c81009f39a2de518707cce75d66e93d78`；v6 代码必须重新跑相应回归，不继承旧通过状态。
- 失败日志、训练曲线和历史 artifact 全保留；不以固定 epoch 上限冒充收敛，不把 smoke、proxy 或训练集指标写成最终科学结论。
- 当前不更新论文/PPT，不启动 E3 或生成训练。完成训练、独立验证和 Gate 裁决后，再同步代码、运行台账与交接。
