# HANDOFF A10-03：E2 历史失败、release 工程验收与 w21 OOM 收束

- 文档日期：2026-11-25；最近复核与 w21 收束：2026-11-26
- 失败事件日期：2026-11-24（v7）；2026-11-25（v8）；2026-11-26（v10/w23/w21）
- 阶段：A10-03 / E2
- 状态：**v7、v8 历史 fail-closed 不删除；当前 release `/home/codonflow-a10-e2-release` HEAD 为 `6075ad5381800c84e99b4f4a277b26b6594a7fbf`，本次核对干净。历史 release 集成验收为 `79dcbf377b043e21f45573428128d236c9534685`，相关 144 tests、synthetic 多 worker 等价、27 checks 和 859 CTMC cases/review 通过。v10 27 workers、w23 与 w21 均 OOM、0 shard/0 曲线且失败保留；w21 已按明确 PID 收束，退出码 1，无科学恢复价值。结构化求解修复已在独立 worktree `/home/codonflow-a10-e2-structured` 完成工程验收（本地 `b6012ac50b30110636505a26aa716f5d59af6e11`，未 push）；E2/H2/G1 未完成、未裁决且未通过。**
- 本文只登记已核实的失败、恢复与数值验证事实及后续验收边界，不预写训练或科学成功。

## 1. v7 已核实的退出事实（不可变历史）

- v7 权威工作树为 `/home/codonflow-a10-e2-v2`；其 `.git` 可能是文件，后续代码工作须按实际工作树处理。
- v7 输出目录为 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/a10/e2/kinetic_development_v7`，日志为同路径加 `.log`。
- v7 于 **2026-11-24** 在真实 CUDA 运行中因 **batch sample 10 normalized residual `8.842e-06 > 1e-10`** 触发 fail-closed 退出。该残差未满足既定稳态验收阈值，不得放宽阈值或忽略该样本，**不能称训练完成**。
- v7 **没有 `summary.json`，也没有 `predictions.npz`**；因此没有完整 outer 预测、统计判决或可供科学复核的最终预测产物。
- v7 此前通过的小状态、梯度、守恒和真实 CUDA 工程检查不抵消本次运行时失败，也不构成 E2/H2/G1 证据。
- v1–v7 的日志、曲线和其他失败证据均须保留；禁止覆盖历史产物。2026-11-24 的进行中 handoff 是历史快照，不追改。

## 2. v8 solver 恢复与生产状态

### 2.1 代码与产物身份

- 权威 v8 工作树为 `/home/codonflow-a10-e2-v8`，HEAD 为 `287c02569e7af325da8578fd5973d9c98f681562`。
- 只读 `git status --short` 确认三个未提交修改文件：`src/codonflow/models/kinetic_mean_field.py`、`tests/test_a10_03_verify_mean_field.py`、`tests/test_kinetic_mean_field.py`。该工作树与 v8 产物目录作为失败证据保留；不得覆盖 v8 目录或篡改本次运行身份。
- solver 验证目录为 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/a10/e2/kinetic_solver_v8`；生产产物目录为 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/a10/e2/kinetic_development_v8`。
- `production_launch_manifest_v1.json` 登记 dirty diff SHA `06eecd870ac0091c356d353cc91553b576f0672ccb8cbfa74bca1ccf7cb0ba23`、source SHA `83b1def73e1a6949e3ed7bcb593f89c4ba8bf9422f7b7ed1298a89f947347b8f`、protocol SHA `3c4b9a3b345524d4c9ea9779aacb4c1f4afa57e131ee4c23d5d8f33b139b6b24`，协议未改且 final epoch limit 为 null。

### 2.2 已通过的工程验证

- 求解链为 **sparse normalized-residual Newton＋scaled Newton＋LSODA/Newton polishing**；所有返回仍严格检查 normalized residual `1e-10`，未放宽 v7 阈值。
- 64 项定向检查通过；全项目测试为 **889 passed、1 skipped、5 subtests**。跳过项不写成通过。
- 真实训练快照、历史失败输入以及长度 2–4096 的案例通过；真实快照不得称为 exact v7 sample-10 failing state，训练清单明确 `exact_v7_sample_10_parameters_recovered=false`。
- CUDA batch preflight 在 RTX 5090、torch 2.14.1+cu132 上执行前后向，最大 normalized residual `4.648926543739911e-14`，无 CPU fallback；独立 CUDA 前后向审计通过。
- 五组独立 least_squares 复核的最大密度误差为 `1.3766765505351941e-14`、最大梯度误差为 `1.1796119636642288e-14`、独立守恒误差为 `3.930771910082915e-14`。
- `numerical_validation_v1.json` 顶层失败保留：独立 directional 有限差分公式双重计数 `k` 方向；所有 solver cases 已通过。`directional_gradient_validation_v2.json` 修正验证公式后通过，`overall_validation_v3.json` 仅为工程总体验证通过，`scientific_gate_claimed=false`。

### 2.3 v8 生产训练已 fail-closed，无科学结果

- 2026-11-26 只读复核确认 `kinetic_development_v8.exit_code=1`，`kinetic_development_v8.finished=2026-11-25T22:33:16+08:00`，原生产 PID `3533551` 已不存在。v8 不再处于运行状态。
- `curves.jsonl` 实测为 **36/486 条曲线**。日志显示 backward 在 batch sample 13 的恢复求解后仍达到 normalized residual **`2.944e-08 > 1.000e-10`**，触发 fail-closed；严格阈值未放宽。
- `kinetic_development_v8/` 仅见 `curves.jsonl`、`provenance.json`、`splits.json`，**没有 `summary.json` 或 `predictions.npz`**。因此没有完整 outer 预测、双比较 Holm、seed-first pooled CI 或 H2/G1 判决。
- v8 solver/测试/CUDA 通过不抵消 v7、v8 运行时失败，也不证明平均场生物有效性或严格 OOD 科学增量。v8 日志、退出码和目录均保留，不覆盖。

## 3. mean-field 859 案例精确 CTMC 对照验证

### 3.1 代码、产物与独立性范围

- 验证工作树为 `/home/codonflow-a10-e2-validation`，HEAD 同为 `287c02569e7af325da8578fd5973d9c98f681562`，四个文件未跟踪：
  - `scripts/a10_03_validate_mean_field_approximation.py`
  - `scripts/a10_03_independent_review_mean_field_validation.py`
  - `tests/test_a10_03_mean_field_approximation.py`
  - `tests/test_a10_03_independent_review_mean_field_validation.py`
- 产物目录为 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/a10/e2/mean_field_validation_v1`。`manifest.json` 登记未 commit、未 push、未修改 production/Gate 文件、未读取冻结或外部生物数据。
- `independent_review_v2.json` SHA 为 `c7a99506687060b1059f7b2bec0733fb5faabd276b10cb694ed9e8e78e0e9de4`，`passed=true`：859 个精确 CTMC 案例、64 个 complex-step 敏感性案例及 25 个独立 mean-field 案例全部通过。复核未导入主验证模块、未调用 production solver，使用独立 lexicographic 状态枚举、row-generator eigendecomposition 和有界 least_squares；这是算法/实现路径独立，不扩大为整合后的独立所有权验收。

### 3.2 近似误差和可辨识性结论

- 共 **859 个 L1–L6 合成小状态案例**，包括 9 个 single-site、135 个 constant-rate、72 个 localized-rate、640 个 log-uniform random 和 3 个 common-time-scale 案例；数值检查失败数为 0。这里的 passed 指 reference、守恒、rank、sensitivity 和 CUDA 检查通过，**不是近似准确率 Gate**。
- log-uniform random 组密度最大绝对误差分位数 `[min, median, 90%, 95%, max]` 为 `[0.0000239996, 0.0223736651, 0.1416515151, 0.1934572009, 0.3391923462]`；最大通量相对误差为 `0.3198444691`。这些误差不可忽略，不能由求解残差很小推断平均场近似准确。
- 全部合成网格中更大误差也存在；multi-site 平均场忽略非零最近邻协方差。仅测试 L1–L6，不能外推热力学极限、长转录本、生物 OOD 或功能表现。
- 密度单独观测保留一个共同时间尺度零空间，只能局部识别相对速率；加入绝对通量后观察到局部满秩，但条件数可很大、奇异值可很小，实际可辨识性仍可很弱。未提供 Fisher 噪声模型、置信区间、后验、实验通量校准、全局可辨识性证明或生物参数估计。
- 精确参考是 stationary CTMC，不是随机轨迹模拟；**平均场不是精确随机模拟**。上述结果不证明平均场生物有效性、H2 或 G1。

### 3.3 保留验证失败与修正历史

- 初次新测试为 5 failed/5 passed：精确 CTMC 内部 hop flux 的 pair-joint 符号错误，修正 reference 后才运行科学验证。
- 边界测试期望曾修正：`alpha=beta=k/2` 是精确半密度 product-stationary 特例；一般 equal-rate multisite 才用于展示近似误差。
- verifier 初版 complex-step 使用加法而非乘法 log-parameter perturbation，修正后重测。
- 首次 `independent_review.json` 为 `passed=false`，一个 stiff mean-field least-squares 差异为 `1.6455891822531044e-06`；该文件保留。经 analytic-Jacobian root refinement 和 normalized residual `<=1e-12` 后，`independent_review_v2.json` 通过。
- 新验证/复核测试 15 passed；既有定向测试 60 passed、2 deselected，两个长压力测试不写成通过。早期 pytest 不在 PATH、解释器缺 pytest、900 s 超时及空测试文件转移失败均保留在 `execution_history.json`，不计作通过。

## 4. 发布前 integrate 历史（不可变记录）

1. **当时已整合但仍为未提交 dirty 状态**：`/home/codonflow-a10-e2-integrate` 的 HEAD 为 `287c02569e7af325da8578fd5973d9c98f681562`，包含全部预期 dirty 修改：7 个已跟踪修改文件和 5 个未跟踪文件，其中四个验证/复核代码与测试文件已进入该工作树。当时尚未 commit 或 push；只读 `git ls-remote` 确认远端 `refs/heads/a8-rk` 为 `287c02569e7af325da8578fd5973d9c98f681562`。当前 release 已推进，见第 5 节。
2. **原始 solver 身份差异保留为历史**：mean-field `validation.json` 的 production solver SHA 为 `68d669bd7937282c366b168c2a5e7dfd4a418417b6823a4ec35a213342eeda67`，v8 训练清单 source SHA 为 `83b1def73e1a6949e3ed7bcb593f89c4ba8bf9422f7b7ed1298a89f947347b8f`，原始 859 案例不能改写为当时已验证 v8 dirty solver。整合产物 `mean_field_validation_integrate_v1/validation.json` 与 `independent_review.json` 均为 `passed=true`，但仍只属于 scoped 数值验证。
3. **整合全量测试通过，但不是干净 checkout 或科学验收**：`/tmp/a10_e2_integrate_full_pytest_v1.log` 实测为 **910 passed、1 skipped、5 subtests passed，6126.13 s**。该结果不抵消 v8 backward 运行时失败；当时 backward 修复待完成，修复后的复测、干净 checkout 和端到端科学运行均未登记为完成。后续 release 只关闭工程与干净 checkout 验收，不关闭端到端科学运行。
4. **独立验收链未闭合**：当前 independent 指独立算法/实现路径；首次复核失败、verifier 公式修正及后续通过均须保留。尚缺提交后独立所有权/干净环境验收，不得把整合测试或 `passed=true` 扩写为科学 Gate 已通过。

以上仅登记发布前实测进展；当时不预写 v9 或 backward 修复成功，不预写 commit/push，也不据此判 H2/G1。后续 release 事实不得回改该历史记录。

## 5. 当前 release 工程验收与 v10/w23/w21 生产状态

### 5.1 release 身份与 scoped 工程证据

- 当前权威工作树为 `/home/codonflow-a10-e2-release`，HEAD 与 GitHub `a8-rk` 均为 **`79dcbf377b043e21f45573428128d236c9534685`**；登记时 `git status --short` 无输出，工作树干净。
- 相关 **144 tests** 通过（94.70 s）。release 集成 manifest 明确 `full_project_suite_run_on_release=false`，因此不得把 144 项定向测试写成 release 全项目测试。
- synthetic **1/2/4-worker** 的 predictions、states、metrics 和 science records 逐位一致；每份独立 verifier 均为 **27/27 checks** 通过，cache-hit 复核也通过。该结论限于 synthetic smoke 与并行等价性。
- **859** 个 L1–L6 合成小状态精确 CTMC cases 及独立 review 通过；mean-field 边界仍按第 3 节，不因 release 整合而扩大。
- 集成 manifest 为 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/a10/e2/kinetic_release_integration_v1/integration_manifest.json`，其中 `H2_evaluated=false`、`G1_evaluated=false`、`scientific_gate_claimed=false`。w21 manifest/closeout 的指定归集目录同为 `kinetic_release_integration_v1/`；路径登记不表示 w21 已形成完成摘要。

### 5.2 v10/w23/w21 失败保留

- **v10（27 workers）**：因 CUDA `CUBLAS_STATUS_ALLOC_FAILED` fail-closed，退出码 1；0 完成 shard、0 曲线，无完成摘要。产物目录为同级 `kinetic_development_v10/`，失败证据保留，不覆盖。
- **w23（23 workers）**：因 CUDA out of memory fail-closed，退出码 1；0 完成 shard、0 曲线，无完成摘要。产物目录为同级 `kinetic_development_v10_w23/`，失败证据保留，不覆盖。
- **w21（21 workers）**：启动后的历史快照曾登记 24.8GB 已用、7.2GB 空闲、约 25% GPU util；随后 26 份 worker failure 全部为 CUDA OOM（independent 9、kinetic 8、position 9），0 完成 shard、0 曲线。产物目录为同级 `kinetic_development_v10_w21/`，失败证据保留，不覆盖。
- v7/v8 历史失败与 v10/w23/w21 OOM 必须并列保留；工程 release 通过不抵消任何生产失败。

### 5.3 w21 收束、证据保全与性能根因（2026-11-26）

- 终止前核对唯一运行态 worker PID `3989620` 的 `spawn_main` 身份、parent `3989510` 的 w21 完整命令行和 launcher `3989507` 的 w21 脚本路径，并保存 PID/starttime/命令行。复核身份未变后仅向 worker `3989620` 发送一次 SIGTERM；worker 退出，parent/launcher 随后自行退出，无需 KILL，也未向其他 PID 发信号。
- executor 写入 `kinetic_development_v10_w21/failure.json`；`.exit_code=1`，`.finished=2026-11-26T15:56:12+08:00`。最终仍为 26 份 worker failure JSON、0 curves，且无 `summary.json` 或 `predictions.npz`，故 w21 判为无效 OOM 失败，无科学恢复价值。
- 完整 failure 目录快照、26 份摘要及 SHA、进程身份、executor failure/log、退出码与关闭清单保存在新目录 `kinetic_release_integration_v1/w21_oom_closeout_20261126_v1/`；原始目录和性能探针均未覆盖。
- 性能证据位于同级 `performance_probe_v1/`。真实 Mohammad16 开发样本、float64 CUDA 探针显示 batch-32 forward 中 CPU Newton 占约 94.8% 时间；backward 使用 padded dense 线性代数，复杂度为 `O(BL^3)`，并出现单次约 593 MB 分配。`complexity_corrected_v2.json` 纠正初版重复 outer 计数；该性能诊断不改变科学 protocol、Gate 或 `1e-10` 阈值。
- 当前权威 release HEAD 已核对为 `6075ad5381800c84e99b4f4a277b26b6594a7fbf` 且干净。结构化求解修复仅在独立 worktree `/home/codonflow-a10-e2-structured` 开展，artifacts 写入新的 teams 目录；未经真实 CUDA 前后向、长序列、独立残差/梯度及定向回归验证，不声称修复完成，也不降低阈值。

### 5.4 结构化求解工程验收完成，科学运行仍未完成

- 独立 worktree 本地提交为 **`b6012ac50b30110636505a26aa716f5d59af6e11`**，只修改 `src/codonflow/models/kinetic_mean_field.py` 与 `tests/test_kinetic_mean_field_batch.py`，提交后干净、未 push。长序列 forward 使用带边双对角牛顿步并保留 sparse 回退；长序列 backward 双向结构化 adjoint 按 recovery 择优，困难样本保留逐样本 dense LU/QR 严格恢复；短序列路径不变。protocol、Gate 和 `1e-10` 未改。
- release 定向集实测 **146 passed in 212.59 s**（原 144＋新增 2），日志在新目录 `structured_solver_v1/release_directed_tests.log`。新增测试禁止长序列调用 sparse/dense 分解，并检查异质序列独立方向有限差分。
- 真实 RTX 5090、float64 CUDA 的 65/257/1025/1521-codon 变长 batch 前后向通过：峰值 **677,376 bytes**，最大生产/独立归一化残差均 `4.486e-16`，最大 backward recovery `1.405e-15`，相对独立 dense adjoint 最大梯度误差 `1.243e-13`，257-codon 方向差分绝对误差 `1.045e-9`。报告为 `structured_solver_v1/independent_cuda_v4/cuda_long_sequence_independent_validation.json`。
- 真实 Mohammad 模型探针的 1521-codon 案例残差 `4.894e-15`、峰值 142.6 MB；32×264 batch 峰值由旧 143.0 MB 降至 **70.4 MB**，但 backward 中位约 1.67 s、旧探针约 0.48 s，故只主张消除 padded dense 大额分配，不声称所有场景提速。结果在 `structured_solver_v1/real_model_probe/results.json`。
- 失败历史全部保留：病态周期长序列两次 backward recovery 失败（条件数约 1e17–1e18）、一次独立报告 NumPy JSON 序列化失败、一次真实探针导入路径失败；对应 v1/v2/v3 和首次 probe 日志均未覆盖。上述工程验收不重跑 w21、不产生 outer 预测，不裁决 H2/G1。

## 6. 当前科学与 Gate 边界

- E0/A10-G0 已完成；E1/A10-02 已完成，H1 仅为开发集 TB-MSE 观察校准阳性。这些历史状态不变。
- E2 生产科学运行仍未完成，w21 已 OOM 退出且无完成 shard/曲线，H2 未证且 H2/G1 未裁决，A10-G1 未通过；不能从 v7/v8 部分曲线、历史进程/显存、inner 状态、工程测试、精确 CTMC 对照或局部 rank 推断 outer 阳性。
- E3/G2 未证，G3 未通过；`final_untouched=false`、`SOTA=false`。大规模生成训练仍须先通过 G2。
- 平均场不是精确随机模拟，occupancy 仍只是实验依赖的相对占据/速度代理。不得作最终跨研究、绝对物理速率、因果机制、真实生物功能或 SOTA 结论。
- untouched24、MAGE functional untouched 及其派生文件继续禁止读取；冻结数据边界未因恢复工作改变。

## 7. 后续验收合同（不变）

1. 后续任何训练或 GPU 验证必须使用真实 CUDA，不得用 CPU 降级、显存占用或无效占卡任务冒充进展。
2. 每个实现修改须补项目风格测试并独立复核；保留失败日志与完整运行登记，不覆盖 v1–v8、v10/w23 失败目录，不使用 `reset --hard`、`clean` 或 `git add -A`。
3. 只有产生完整 `summary.json`、`predictions.npz`、保存状态、selection、逐转录本指标和 curves 后，才可进入最终科学复核；缺失任一关键产物时保持未完成状态。
4. 独立复核须从原始开发数据、split 和保存状态重建预测，逐 kinetic 成员复核稳态，核对 CUDA、成本、双比较 Holm 与 seed-first pooled CI。
5. G1 仍按冻结合同裁决：E2 严格 transcript OOD 同时超过 independent 与 position，paired 95% CI 下界大于 0 且 Holm 通过。不得因恢复而降低阈值、改换弱 baseline 或追加/删除既有科学条件。
6. 若 G1 未通过，停止动力学主线；若通过，才允许已验证动力学量进入 E3。生成训练仍须 G2。

## 8. 本次文档登记范围

上一轮仅更新 `交接文档/spec.md`、`交接文档/tasks.md`、`交接文档/A10_00_TASK_DATA_BASELINE_CLAIM_MATRIX.md` 和本恢复交接并同步镜像。本轮仍只更新这四份现行文档及本地/远端镜像，登记 w21 OOM 收束与性能根因；不提交或推送远端文档，历史 handoff 与失败证据不删除。代码修改严格限制在新的 `/home/codonflow-a10-e2-structured` worktree，不 push。

当前可执行事实是：**release HEAD 为 `6075ad5381800c84e99b4f4a277b26b6594a7fbf`；历史 144 项定向测试、synthetic 多 worker 等价、27 checks 和 859 CTMC cases/review 通过只支持 scoped 工程验收；保留 v7/v8 失败链及 v10/w23/w21 OOM，不覆盖失败目录；w21 已退出 1、0 完成 shard/0 曲线，无科学恢复价值；结构化求解修复已完成 146 项定向测试和真实 CUDA/独立数值验收，本地 `b6012ac50b30110636505a26aa716f5d59af6e11` 未 push，但没有 H2、G1 或生物有效性的证据。**
