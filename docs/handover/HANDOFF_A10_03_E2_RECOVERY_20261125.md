# HANDOFF A10-03：E2 历史失败、release 工程验收与 w21 OOM 收束

- 文档日期：2026-11-25；最近复核：2026-11-27（v15 四个 independent shards 只读阶段验收与 12-worker temporary 持续运行快照）
- 失败事件日期：2026-11-24（v7）；2026-11-25（v8）；2026-11-26（v10/w23/w21/v11/v12/v13）；v13 已于 2026-11-26 22:36:45+08:00 退出 1，最终无完成摘要
- 阶段：A10-03 / E2
- 状态：**v7、v8、v10/w23/w21、v11/v12/v13 历史 fail-closed 不删除。v13 使用启动时代码祖先 `40603527afa3ee2275166b4293234cdd48a9e38c`，运行 13321.0843 s 后在 position/epoch890 OOM、退出 1；2 个成功 cache shard 加 1 个 OOM 失败 shard 共 3 个终止 shard，无完成摘要。独立 verifier 当前证据基线为 `cac91df1468b0e01b4e619a5ca9f57e4b242896d`：全量 952 passed/1 failed/1 skipped/5 subtests，唯一失败为共享 GPU synthetic 多 worker OOM；干净 checkout 的 1/2-worker synthetic 各 27/27 shards、verifier 各 28/28 checks，manifest SHA `e34cba…`。受控真实 CUDA A/B 已定位为 output-gradient hook 闭包逐 batch 保留 CUDA 张量，本轮未修改生产代码、protocol、Gate 或 v13 artifacts；E2/H2/G1 未完成、未裁决且未通过。**
- **2026-11-27 当前权威更新：v14 恢复代码为 `fe11a241…`，hook 修复定向测试独立复跑为 31 passed；本轮登记时 memory 工作树 `/home/codonflow-a10-e2-memory` HEAD 为 `3ba302dfcab8dd250409bcf1b514c415a5b3f9f9`。v13 复用 oracle 严格只有 2 个成功 independent shard（outer0/1）。三臂 1000-step 无显式 GC soak 均完成并有界，kinetic 峰值约 100.58 MB、后半程下降，未见持续线性增长。outer0 正式 replay 结构完整但有 547 个字段不一致，science SHA 由 `cc3a19a7…` 变为 `d8b4817d…`，逐位不等价，按合同拒绝复用；outer1 未重放，旧 cache 不变。v14 已从全新空 cache 启动，输出 `kinetic_development_v14`，cache `kinetic_development_v14_from_scratch_shard_cache`，producer PID `4176767`，4 workers，cache hits 预期 0，不是 2 或 3；登记时未见 OOM，warnings 保留，尚无完成摘要。E2/H2/G1 仍未完成、未裁决且未通过。**
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

- 历史 release 集成验收时，权威工作树 `/home/codonflow-a10-e2-release` 的 HEAD 与 GitHub `a8-rk` 均为 **`79dcbf377b043e21f45573428128d236c9534685`**；当时 `git status --short` 无输出，工作树干净。后续代码与文档身份见第 5.5、5.6 节。
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
- w21 收束时权威 release HEAD 曾核对为 `6075ad5381800c84e99b4f4a277b26b6594a7fbf` 且干净。结构化求解修复仅在独立 worktree `/home/codonflow-a10-e2-structured` 开展，artifacts 写入新的 teams 目录；未经真实 CUDA 前后向、长序列、独立残差/梯度及定向回归验证，不声称修复完成，也不降低阈值。

### 5.4 结构化求解工程验收完成，科学运行仍未完成

- 独立 worktree 本地提交为 **`b6012ac50b30110636505a26aa716f5d59af6e11`**，只修改 `src/codonflow/models/kinetic_mean_field.py` 与 `tests/test_kinetic_mean_field_batch.py`，提交后干净、未 push。长序列 forward 使用带边双对角牛顿步并保留 sparse 回退；长序列 backward 双向结构化 adjoint 按 recovery 择优，困难样本保留逐样本 dense LU/QR 严格恢复；短序列路径不变。protocol、Gate 和 `1e-10` 未改。
- release 定向集实测 **146 passed in 212.59 s**（原 144＋新增 2），日志在新目录 `structured_solver_v1/release_directed_tests.log`。新增测试禁止长序列调用 sparse/dense 分解，并检查异质序列独立方向有限差分。
- 真实 RTX 5090、float64 CUDA 的 65/257/1025/1521-codon 变长 batch 前后向通过：峰值 **677,376 bytes**，最大生产/独立归一化残差均 `4.486e-16`，最大 backward recovery `1.405e-15`，相对独立 dense adjoint 最大梯度误差 `1.243e-13`，257-codon 方向差分绝对误差 `1.045e-9`。报告为 `structured_solver_v1/independent_cuda_v4/cuda_long_sequence_independent_validation.json`。
- 真实 Mohammad 模型探针的 1521-codon 案例残差 `4.894e-15`、峰值 142.6 MB；32×264 batch 峰值由旧 143.0 MB 降至 **70.4 MB**，但 backward 中位约 1.67 s、旧探针约 0.48 s，故只主张消除 padded dense 大额分配，不声称所有场景提速。结果在 `structured_solver_v1/real_model_probe/results.json`。
- 失败历史全部保留：病态周期长序列两次 backward recovery 失败（条件数约 1e17–1e18）、一次独立报告 NumPy JSON 序列化失败、一次真实探针导入路径失败；对应 v1/v2/v3 和首次 probe 日志均未覆盖。上述工程验收不重跑 w21、不产生 outer 预测，不裁决 H2/G1。

### 5.5 v11/v12 cache provenance 修复与真实生产状态

- v11 代码为 `0fc413efe04506b85f847d162c9fa1fc5121e31e`，launcher `4044478`、parent `4044481`、16 workers 的早期快照显示无即时 OOM，但当时即 0 完成 shard/0 曲线。最终 `kinetic_development_v11.exit_code=1`、`.finished=2026-11-26T18:20:37+08:00`，`failure.json` 记录运行 519.4810 s 后 position shard CUDA OOM；16 个 worker 均已回收，无 `summary.json`、`predictions.npz` 或 `curves.jsonl`，cache 中 0 个完成 shard NPZ。failure SHA 为 `c2def0a5a703164c4391ba99baa60e6dd001df7b91bf5559fb415e9840106988`。
- 独立审查发现 v11 parent/worker/cache identity 缺少 `src/codonflow/models/kinetic_banded_cuda.py` SHA；v11 `provenance.json` 仅含 protocol、implementation、mean-field 三项。该缺口会使 backend 改动无法可靠隔离 shard cache，是生产 provenance 阻断，**不是科学失败或 H2/G1 判决**。只读复核时指定 parent/launcher PID 均已不存在，v11 已先行 OOM 退出，故不能写成“本轮主动中止”；若仍在运行则必须停止。
- 修复代码提交为 **`40603527afa3ee2275166b4293234cdd48a9e38c`**，父提交为 `0fc413ef…`，已推送 `a8-rk`。只修改 `scripts/a10_03_e2_kinetic_parallel.py` 与 `tests/test_a10_03_e2_kinetic_parallel.py`：统一 `source_identity`，将 `banded_cuda_backend` 纳入 parent、spawn worker、cache、failure metadata 和 summary。protocol SHA 保持 `3c4b9a3b345524d4c9ea9779aacb4c1f4afa57e131ee4c23d5d8f33b139b6b24`，backend SHA 为 `c2c70271d1a94055173926973db5c689d6fbbb08f20fc5d6c8026ac971704aa3`，Gate 和 `1e-10` 不变。
- 验证目录为 `kinetic_release_integration_v1/v11_provenance_fix_v1/`。初次新测试因误把 identity mismatch 预期为 cache miss，实测 1 failed/10 passed；保留日志后修正测试预期为既有 fail-closed 语义，并行文件 11 passed，相关定向集 **151 passed**。提交后增加 worker backend-only mismatch 测试，并行文件 **12 passed**。两次一次性 CUDA 验证脚本环境失败（stdin spawn、模块搜索路径）均保留，不计作通过。
- 最终真实 RTX 5090、torch 2.14.1+cu132 的 CUDA/cache 报告为 `cuda_cache_identity_validation.json`，SHA `918343221e843a8f59e269d7b1ecfd50bdc41e76cc8bc66602ee0780a9f741c5`：初始 cache miss 1、相同 identity cache hit 1、变更 backend identity 被拒绝、科学结果 SHA 一致、梯度有限，最大归一化残差 `9.50439078614984e-15 <= 1e-10`。这些只证明工程 identity 与 scoped CUDA 前后向，不证明 outer 科学结果。
- v12 使用 `40603527…` 和 16 workers，于 2026-11-26 18:36:52+08:00 真实启动；18:37:17+08:00 退出 1，约 19.81 s executor 内记录 position shard `CUBLAS_STATUS_ALLOC_FAILED`，0 完成 shard、0 曲线、无 `summary.json` 或 `predictions.npz`。v12 startup provenance 已含正确 backend SHA，provenance SHA 为 `70a4983fe0065d99095b1d683d5a8c48b189ac855fda6a7fab12767d005c3148`，failure SHA 为 `f5e28977c677b1cf239c0540eb58d2b9f0909cbe0d33460bf046ac610ae72056`。v12 是资源/工程失败，未产生科学预测，不据此裁决 H2/G1；未预写后续运行成功。

### 5.6 v13 共享显存审计、6-worker 启动与单次只读快照

- 启动前审计时间为 **2026-11-26 18:53:38+08:00**。RTX 5090 总显存 32607 MiB、已用 13189 MiB、空闲 18923 MiB。`nvidia-smi` 仅列 PID `3996745`=7034 MiB 和 `4045601`=6138 MiB；二者合计 13172 MiB，与整卡已用量仅差 17 MiB。
- 进程身份由完整命令行、工作目录和可执行文件共同核对：`3996745` 为 `/root/rareseq/work` 下的 `e5_rbp_holdout.py`，输出归 ProxyFunctionGap/RARESeq；`4045601` 为 `/home/cunyuliu/rna-ft-eval` 下的 `python -m rnafteval.finetune_base`。二者均非 CodonFlow，未停止、未发送信号、未改变其环境。按 `/proc` 完整命令行扫描，未发现 v11/v12 runner 或 spawn worker 残留；审计 shell 的字符串自匹配不计作训练进程。
- v13=6 的保守资源依据为：启动前空闲 18923 MiB，固定预留 **12 GiB=12288 MiB** 给共享进程波动、allocator 和临时分配，可预算总量为 `18923-12288=6635 MiB`，等效每并发 **1105.8 MiB**。这是资源上限选择而非显存不 OOM 的保证；protocol、科学 Gate 和 `1e-10` 不变。
- v13 启动时 release HEAD 与 GitHub `a8-rk` 均为 **`f7e3fdbb7684befe947a12b06de56744defbdb96`**，工作树干净；`40603527afa3ee2275166b4293234cdd48a9e38c` 是其直接代码祖先。实测 protocol SHA 仍为 `3c4b9a3b345524d4c9ea9779aacb4c1f4afa57e131ee4c23d5d8f33b139b6b24`，backend SHA 为 `c2c70271d1a94055173926973db5c689d6fbbb08f20fc5d6c8026ac971704aa3`。本轮未修改代码。
- v13 命令使用 `scripts/a10_03_e2_kinetic.py --device cuda:0 --max-workers 6`，输出为同级 `kinetic_development_v13/`。唯一一次启动后只读状态检查在 **2026-11-26 18:55:35+08:00**：主 PID `4057023` 加六个 worker GPU PID `4057034`、`4057037`、`4057038`、`4057039`、`4057040`、`4057041`，显存分别合计 **5468 MiB**；整卡已用 18694 MiB、空闲 **13417 MiB**，高于 12 GiB 预留，且 CodonFlow 占用低于 6635 MiB 总预算。两个外部 PID 仍为 7034/6138 MiB，未触碰。
- 该快照仅有 `provenance.json` 与 `splits.json`；provenance SHA 为 **`350a515bb7a621c54693fe53f1109082221cc3decd11f597b8a5d9a11a8b23b9`**。当时 **0 曲线、0 cache NPZ/0 完成 shard**，无 `summary.json`、`predictions.npz`、`.exit_code` 或 `.finished`，故只登记“真实 CUDA 运行中”的瞬时状态，不宣称训练完成。日志保留 numerical recovery 期间的 invalid/overflow RuntimeWarning；既不隐去，也不在缺少 executor 失败/退出证据时单独判为最终失败。没有 outer 预测或统计判决，H2/G1 未裁决且未通过。

### 5.7 独立 verifier 修复发布与 outer-test 残差合同（2026-11-26）

- 独立预检曾发现 verifier 与现行 producer 的旧 schema 阻断。现修复代码提交 **`18a80c2df28e063025787a0ac853fa467c6f42b3`** 已推送 GitHub `a8-rk`，代码验收时 `/home/codonflow-a10-e2-verifier` HEAD 一致且工作树干净；**49+3+12 tests 全部通过**。release `/home/codonflow-a10-e2-release` 仍停在旧文档提交 **`4603951295352ae20b849cc4132ba56519d34ba3`** 且只有四份文档 dirty，本轮不 checkout、rebase、reset 或修改该工作树。
- 原 verifier 重建的 startup SHA 只有 protocol、implementation、mean-field operator 三项，遗漏 parallel producer 写入的 `banded_cuda_backend`；现已在 provenance/selected-state/summary identity 中统一重建和核对。历史 synthetic 27/27 仍只作历史 scoped 证据。
- 原 verifier 对 `parallel.json` 的精确键集及 summary parallel 比较不接受 `configured_arm_max_workers`、`arm_max_workers`，且对 ledger shard SHA 仅检查 64 位十六进制格式；现已接受并精确比较两项 arm quotas，要求三臂精确键集、正整数且 effective 等于 `min(max_workers, configured)`。真实 shard cache 会重算 NPZ 与 `.sha256` sidecar 摘要，以 `allow_pickle=False` 读取 NPZ，并精确核对 metadata 四键、`a10-03-e2-kinetic-shard-v1` schema、canonical spec 和含 backend 的 identity；缺失、篡改或 backend-only mismatch 均 fail-closed。legacy 三项 identity 只对显式 synthetic 且完全无 quotas 的历史案例兼容，真实 v13 不走该回退。修复提交只修改 `scripts/a10_03_verify_e2_kinetic.py` 与 `tests/test_a10_03_verify_e2_kinetic.py`，不改 producer、protocol、统计或 Gate。
- 冻结 protocol 原文规定 `outer_test_use` 为 inner 选择/早停完成后的最终预测与指标，`final_predictor` 为对应三 selected inner-fold models 的等权 density ensemble，`evaluation.split` 为 outer test only，`steady_state_diagnostic` 为每个 selected inner kinetic member 分别计算。故 outer-test 逐成员残差合同复核项为 **`3 seeds × 1073 transcripts × 3 members = 9657`**。新 verifier 的 `REAL_OUTER_TEST_KINETIC_MEMBERS` 与 `outer_test_member_residual_contract` 显式要求实际复核数等于 9657；每个成员仍由独立稳态重建并沿用 `1e-10` 阈值。
- **`28971 = 3 seeds × 1073 transcripts × 3 outer folds × 3 members`** 对应全 27 个 kinetic models 在全转录本上的额外诊断；它不是对应 outer-test 的 9657 项，不得事后加入 Gate，也不改变 paired CI、Holm、双比较或 `1e-10`。9657/28971 均为复核范围计数，不是 H2/G1 结果。
- **历史运行中快照（已被第 5.9 节最终状态覆盖）**：19:57:14+08:00 主 PID `4057023` 仍运行，命令行仍使用原 producer/protocol/output/shard-cache；当时输出仅有 `provenance.json`、`splits.json`，shard-cache 为 0 NPZ/0 sidecar，无完成摘要或退出码。该快照只证明当时状态，不是最终结局；本轮未修改其 producer、protocol、输出或进程。
- verifier 与 release 的 producer、parallel implementation、mean-field operator、banded CUDA backend 和 protocol 五个文件已逐字比较一致。**仅在 v13 正常退出且完整产物形成后**执行以下 ready 命令；输出采用 exclusive 创建，当前不存在，不得提前运行或用不完整产物替代科学验收。真实数据默认且必须保持 20000 resamples，不加 `--allow-synthetic`：

```bash
cd /home/codonflow-a10-e2-verifier
PYTHONPATH=src:. /root/miniconda3/envs/codonflow/bin/python scripts/a10_03_verify_e2_kinetic.py \
  --protocol configs/a10_03_e2_kinetic_protocol_v1.json \
  --raw /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/raw/ribomimo/Mohammad16.txt \
  --output-dir /teams/HoulabData_1788502323/liucunyu/codonflow1031/a10/e2/kinetic_development_v13 \
  --output /teams/HoulabData_1788502323/liucunyu/codonflow1031/a10/e2/kinetic_development_v13_verifier_18a80c2_v1.json
```

### 5.8 verifier 全量测试与干净 checkout 复现证据（2026-11-26）

- 证据基线为 `/home/codonflow-a10-e2-verifier@cac91df1468b0e01b4e619a5ca9f57e4b242896d`，本轮开始时干净且与 GitHub `a8-rk` 一致。全量 `tests` 实测 **952 passed、1 failed、1 skipped、5 subtests passed，9219.64 s**，exit 1；日志 `release_full_suite_v1/pytest.log` SHA256=`3e66bfb35832ac4f1579bca320821a029ddda82ab62cce21c28633380b7d3780`。唯一失败是 `test_spawn_1_2_4_workers_real_cuda_forward_backward_are_bitwise_equivalent` 在共享 GPU 的 2-worker 阶段发生 CUDA OOM，不是数值断言或科学 Gate 失败；本轮不重跑全量 suite，也不把 952 passed 写成全绿。
- 干净 checkout `/home/codonflow-a10-e2-clean` 与 verifier 均在 `cac91df`、status 为空。`clean_reproduction_v1/run_manifest.json` SHA256=`e34cba1c7d33ea948eb3d6e7833c333014c7f67ab214ce0e23d5b657c2862aac`，`overall_passed=true`：真实 CUDA synthetic producer 在 1/2 workers 下各完成 **27/27 shards**，两份独立 verifier 均 **28/28 checks=true**，predictions/states/metrics 和 shard science 逐位一致；cache payload、backend identity 和 arm quotas 三个负控制均按预期 fail-closed。另有一例真实 Mohammad 开发样本数值 probe，训练未启动、outer split/outcome 未读取。
- 上述干净复现是 synthetic 工程复现加 scoped 数值探针，不是 v13 完整科学运行，不裁决 H2/G1。v13 启动时 producer/protocol 五文件 SHA 与该基线一致，但运行中的长训练显存缺陷须单独诊断。

### 5.9 v13 最终 OOM 事实与 PID/shard 口径纠正

- v13 于 **2026-11-26 22:36:45+08:00** 退出 1，executor wall-clock **13321.084314 s**。失败 shard 为 seed1234、outer0、position、grid4、inner2，在 continuation **epoch890、train-evaluation batch2** 申请 **2 MiB** 时 OOM；`failure.json` SHA256=`ebc478266985075d3fb95da23981e59f152bd42c901f46e9593ca814bb515617`，日志 SHA256=`dfd54da023af0b25fe258383c1f01ba6b41f74173ac8b42d37f299c03e7606b8`。原主 PID 与六个 worker 均已回收；无 `summary.json`、`predictions.npz`、`parallel.json`、selected states 或完整 curves，第 5.7 节 ready 命令未执行。
- cache 实测 **2 个成功 NPZ＋2 个 sidecar**，第 3 个终止 shard 即本次 position OOM；故准确口径是“2 个成功 cache shard＋1 个 OOM 失败 shard，共 3 个终止 shard”，不是 3 个成功 shard。另有 6 个已提交 worker 由 scheduler 回收、18 个 shard 未提交，原始调度记录保留。
- worker failure 和快照文件名均明确失败 PID 为 **4057037**；其 self-reported non-PyTorch-inclusive/allocated 显存为 10.95/9.83 GiB。错误文本另列 peer **4057040=10.51 GiB total in use**，不能把 9.83 GiB allocated 归给 4057040。失败快照 SHA256=`a0c1e2effe2cff18fa18fbcde277dcff6543b80b608cb2b3d930da3e06c624b3`，其中 optimizer step=13350，恰为 `890 epochs×15 batches/epoch`。v13 原目录、日志、cache 和 failures 均未修改。

### 5.10 真实 CUDA 小规模显存增长根因诊断

- 新证据目录为 `kinetic_v13_oom_diagnostic_v1/`，最终摘要 `summary_v3.json` SHA256=`7b8b4fd8310c7f7c77a13951b0aceed7916cbc5318811ab50903c7b7d068d600`。诊断直接导入 release 未改动的生产函数，使用真实失败快照的 **32×1487** batch，三个条件各在独立进程运行 **128 steps**；每进程 CUDA fraction=0.0625（约 2 GiB），allocated>1 GiB 即停止，测量循环不调用 `empty_cache`，不重跑全量 suite，不读取 untouched。首轮三个探针均因记录器读取 AdamW `step` 字段触发 KeyError 而在第 1 step 后退出 1，原脚本、日志和 exit codes 保留；v2 仅修正诊断记录器后三个条件均 exit 0。
- **原始 production 条件**：128 step 后 allocated 从 512 增至 **367461376 bytes**，增长 **367460864 bytes**；warmup 后线性斜率 **2334208 bytes/step、R²=1.0**，128 个训练 `rho` 弱引用全部存活。显式 `gc.collect()` 回收 0 个对象，allocated 与 128 个存活弱引用均不变。
- **仅禁用 hook 的消融**：128 次 hook 注册被禁用后，warmup 后 allocated 恒为 **68682752 bytes**、斜率 0，旧训练 `rho` 弱引用存活数为 0。**无 failure_context 对照**同样 warmup 后恒为 **67110912 bytes**、斜率 0、弱引用为 0。两对照的常量 warmup 基线不是逐 step 增长。
- 根因闭合为 `a10_03_e2_kinetic.py:709` 的 `output["rho"].register_hook(lambda gradient: capture.__setitem__("output_gradient_rho", gradient))`：hook 闭包持有 `capture`，而 `capture` 又含 `packed/score/rho/analytic_output_gradient/output_gradient_rho` 等 CUDA 张量，使每个训练 batch 的输出与相关 autograd 对象保持强可达。长训练中逐 batch 累积最终导致 OOM；2 MiB 只是耗尽后的下一次分配，403.29 MiB reserved-unallocated 也不是 9.83 GiB allocated 增长的解释。仅禁用 hook 即同时消除弱引用保留和显存斜率，排除“单纯 allocator 碎片化”作为根因。
- 该诊断只证明资源/对象生命周期根因，**未应用或预写修复**，不改变失败快照语义、科学 protocol、outer-test 9657 合同、统计、Gate 或 `1e-10`。后续任何修复均须单独授权、项目风格测试、长训练受控复验和独立复核。

### 5.11 `fe11a241` hook 修复、复用合同与 v14 恢复进行中（2026-11-27）

- 只读 diff 核对确认 `fe11a2415e33300d6a8fad4e12bc85198d3abbaa` 仅修改 `scripts/a10_03_e2_kinetic.py` 及其测试：正常训练时 output hook 梯度写入独立 `output_gradients`，异常时才合并进 `capture` 保存失败快照，避免 `capture` 与 hook 闭包相互持有 CUDA 对象。修复不改变数学模型、优化/停止/选择/预测语义、protocol、Gate 或 `1e-10`。当前 implementation SHA 为 `5a3067f10ce36cdf178c83839ecadadd743b5e0119d7ad791acbcc860a8e79b9`，protocol SHA 仍为 `3c4b9a3b345524d4c9ea9779aacb4c1f4afa57e131ee4c23d5d8f33b139b6b24`；mean-field、banded backend、parallel implementation SHA 与复用合同一致。独立复跑两个定向测试文件为 **31 passed in 111.81 s**，未在共享 GPU 跑全量 suite。
- 既有 `kinetic_memory_fix_v1/cuda_ab_final_comparison.json`（SHA `b7be3e9f1eb82bdd22f9e2f1b0728ea910b2cc42ac900516e5bbe6423b8e2824`）支持三臂 128-step curves/model/optimizer/RNG 数值一致及 position/independent 无 GC 显存平坦；其 kinetic 无 GC 128-step 仍有 40386.6325 bytes/step 斜率和 46 个弱引用，通过项来自另行 32-step 显式 GC 对照，不能写成 kinetic 无 GC 已平坦。
- 复用合同 `memory_shard_reuse_contract_v1/manifest.json` SHA 为 `e3bb13e0fb85dea20e7e44f269b5f3b83f121c5fecc0131f6313572b3a12c3f5`。严格只有 seed1234 的 independent outer0/1 **2 个成功 shard**，不是 3 个；第 3 个终止 shard 是 position OOM。旧 NPZ/sidecar SHA 和五字段 identity 必须先核验，新实现须逐字段、float64 标量位、tensor/ndarray dtype/shape/C 连续字节及 science SHA 一致；只允许排除合同声明的 cost/timing，禁止改旧 cache 或在 changed identity 下直接命中。
- 权威恢复目录为 `kinetic_v14_recovery_v1/`。三臂各 1000-step、无逐步显式 GC 的真实 CUDA soak 现均已完成并有界。position/independent 后半程 allocated 增长均为 0、末端弱引用均为 0，尾部 allocated 分别恒为 67145216、67147264 bytes；JSON SHA 分别为 `da06cd99f6f0581e92e399d2974043e595cf45aa1c6553db7b46716604223be1`、`d9c1869cbf3d7f4521df585791c6d862cde3caec69d6cd7a25ad1d6e5b5b0628`。kinetic 最终 allocated 峰值约 **100.58 MB**，后半程下降，未出现持续高 R² 正斜率线性增长；自动回收导致的下降不写成逐步恒定，也不误判为失败。**bounded-soak overall 通过仅关闭工程内存前提**。
- `oracle_self_checks_v2/outer0.json`、`outer1.json` 均 `passed=true`，SHA 分别为 `c3bcd853f040d12cb057edf04b919c2b9c1c9dc88d90692d21f2539bf2ad430f`、`f83aca6f628cd4e8ddbbb242992258e727d7bd0c530cf1d9ab51ae1ab0c7673d`；这只证明 oracle 可解析、自检和结构前提成立。outer0 正式 replay 已执行，结构完整但逐字段、float64 位和数组字节复核共有 **547 个字段不一致**；science SHA 由 **`cc3a19a7…`** 变为 **`d8b4817d…`**，因此逐位不等价，按合同 `passed=false`、`reuse_authorized=false` 并拒绝复用。outer1 未重放，旧 cache 不变，不得写成两臂 replay 或逐位一致。
- v14 production 已从**全新空 cache** 启动，输出目录为 `kinetic_development_v14/`，cache 为 `kinetic_development_v14_from_scratch_shard_cache/`；producer PID **`4176767`**，`--max-workers 4`。from-scratch preflight 的 `expected_cache_hits=0`，因为 outer0 复用被拒绝且 outer1 未重放，**不得沿用两个或三个成功 shard 命中的旧预期**。登记时未见 OOM，日志 warnings 保留；尚无完成摘要，producer 实际 cache_hits 只能在完整 `parallel.json` 形成后读取，启动不等于 E2 完成。
- 独立复核的临时 replay 入口首次因合同字段路径 KeyError 在训练前退出；发现更早的权威 1000-step 流程后，为避免重复 GPU 工作，仅取消了本轮重复 soak/replay worker，分别保留 exit143 和 BrokenProcessPool，无完成 shard、无残留进程。这些验证 harness 事件不是数值不一致，也不替代权威 soak/replay 结果。旧 cache、producer 和其他项目进程未修改或触碰。

### 5.12 outer0 replay 最早分歧诊断（2026-11-27）

- 只读诊断报告为 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/a10/e2/kinetic_v14_recovery_v1/replay/outer0_first_divergence_analysis_v1.json`，SHA256=`6866e92ee456712a30a0b895f01935c0a3cdf84f9073d51781657fc8c1c41a95`。报告记录的最早 train loss 差为 **2 ULP**；最大 loss 差为 **8.881784197001252e-16（约 8.88e-16）**，预测最大差为 **3.3306690738754696e-16（约 3.33e-16）**，离散选择不变。
- 上述数值只限定本次 replay 中观察到的浮点尾差，**仍不满足 bitwise 复用合同**，不得据此声称统计等价、科学等价或任何科学结果。报告明确不能从这些 NPZ 定位具体 CUDA kernel；CUDA embedding backward 非确定性只是候选机制，**尚未确证**，不得写成根因已经闭合。
- 因此 outer0 cache 继续拒绝复用，outer1 未重放，旧 cache 不变；v14 继续从全新空 cache 从头训练。该诊断不修改 producer、protocol、统计、Gate 或 `1e-10`，E2/H2/G1 仍未完成、未裁决且未通过。

### 5.13 capture sanitizer 修复、720-case 数值边界与 v15 temporary 启动（2026-11-27）

- 权威 capture 工作树 `/home/codonflow-a10-e2-capture` 的 HEAD 为 **`911390cbe589d46d093dec37883269242570a19e`**，`git status --porcelain` 为空，`origin/a8-rk` 一致。直接祖先 `20dd9f74be9e626e378c34bced59ba45f43a6464` 在 backward 前持久化 CPU batch/capture/model/optimizer/RNG 快照；`911390cb…` 仅修改 `kinetic_banded_cuda.py` 及其测试，SM launch 固定 `num_warps=1`，rank-one/QR public entry 对 bands/rhs 调用 `contiguous()`。protocol SHA 保持 `3c4b9a3b…`，backend SHA 为 `fdd7881a…`。
- 原始真实 memcheck 在 `matrix_full_v8` ordinal561（size8、batch32、transpose、SM、forced pivot、contiguous）记录 **16 次 invalid global read** 和后续 **719 CUDA errors**，位置为旧 backend source line 116；单例 blocking replay 未复现，full blocking v9 为 0 errors，因此时序/序列相关根因未完全建立。上述最小修复关闭了后续 scoped memcheck 观察，不据此宣称原 v14 IMA 根因闭合。
- 修复后同诊断 NPZ（SHA `b105790c…`，明确不是原 v14 failure snapshot）forward 含 NaN 逐位一致，rank-one 53＋QR 32 共 **85 次 launch** 全连续，backward 完成、梯度有限，memcheck **0 errors**、exit 0。定向测试分别为 banded **14 passed/3 warnings**、pre-backward **3 passed/32 deselected**、parallel real-CUDA/synthetic **2 passed/14 deselected**；本轮不跑全量 suite。
- raw direct-kernel bypass 矩阵 **720/720** 完成，0 guard failures、0 exceptions、memcheck 0 errors，但应用因有 **306 numeric failures** 返回 exit 2，不得写成数值通过。逐 `cases.jsonl` 独立重算：transposed SM 94＋padded SM 16＋transposed QR 90＋padded QR 90＝**非连续 290**；另有 **contiguous SM 16**，contiguous QR 0。故 306 是 raw direct-kernel 总失败，不是“非连续 306”。public-entry P0/P1 layout/long regressions 通过只证明 wrapper 的 scoped 修复，不删除 raw 数值失败；memcheck 也不替代 racecheck/initcheck/synccheck。
- 原证据 `/tmp/a10_e2_v15_capture_validation_v1/` 保留，并复制到 `/dev/shm/codonflow_a10_e2/capture_validation_v1_temporary/`；独立分解报告为 `capture_validation_fact_refresh_v1.temporary.json`，SHA `d34b616f89df7c66819d61c05ec2d741601a2432357d659d425e276d9b226078`。全部均属 temporary，未删除或覆盖历史。
- v15 于 **2026-11-27 12:44:59+08:00** 从全新 cache 启动，producer PID **`99295`**、`--max-workers 12`，默认 configured/effective arm quotas 均为 independent/kinetic/position=`4/8/8`。输出 `/dev/shm/codonflow_a10_e2/kinetic_development_v15`，cache `/dev/shm/codonflow_a10_e2/kinetic_development_v15_from_scratch_shard_cache`；launch manifest 明确 `temporary=true`、`permanent_migration_pending=true`，cache hits 启动预期 0，实际值只能待完整 parallel 记录。teams quota 满，public 挂载 `ro`；启动时 tmpfs 可用 **23192823398 bytes**（df 当时显示 22G），永久迁移待 teams 恢复，不删除历史。
- 12:48:17+08:00 快照显示 producer＋12 workers 存活、真实 CUDA 工作进行中，0 成功 shard、0 curves，无 `summary.json`、`predictions.npz`、exit code 或 finished；RuntimeWarning 保留。启动和显存快照不等于完成，E2/H2/G1 未完成、未裁决且未通过，protocol、统计、Gate 和 `1e-10` 不变。
- **13:25:16+08:00 首 shard 复核纠偏**：指定 cache 根目录仍为 **0 成功 NPZ/0 sidecar**，且根目录 mtime 自 12:45:11 起未变；13:17:10 observation 与 13:17:56 摘要均明确 `successful_shard_npz_count=0`，摘要状态为 `running_no_successful_shard_after_bounded_observation`。`failures/pre_backward_latest.npz` 是持续覆盖的 pre-backward 诊断快照，不是成功 shard，不能据此登记首 shard 或数值通过。故首 shard 尚未验收，实际 arm/outer/seed、数值与收敛结果均不可登记。producer `99295` 与 12 workers 仍运行，无 `summary.json`、`predictions.npz`、`parallel.json`、`curves.jsonl`、exit code 或 finished；capture HEAD 为文档提交 `63b54aae879753f4d624ddc682f3f73350458e40`，直接父提交为生产启动代码 `911390cb…`，工作树干净，本轮未同步或修改 capture。observation summary SHA256=`ba5abd7269e7b7db05b638c9b120ea19b97258772c78705022c9e551f984f6ab`，observation JSONL SHA256=`3d73460151ddeec64fff70cc2bc739d910d35250c1267e74523eb8a9eac3fdc4`，launch manifest SHA256=`2b9f4dfc7384c93ac913a26f3b0bba0c4e76a9ba2e14304ca4acbc02fc570454`。protocol、统计、Gate 与 `1e-10` 不变；首 shard 即使后续形成也不等于 H2/G1。

### 5.14 v15 四个 independent shards 只读阶段验收（2026-11-27）

- **快照边界**：2026-11-27 16:18:52+08:00，指定临时 cache 中已有 **4 个完成 independent shard**：seed1234 的 outer0/1/2 与 seed2345 的 outer0。producer PID `99295` 和 **12 个 spawn workers** 仍在执行其余未完成 shards/arms；另一个子进程是 multiprocessing resource tracker，不计作 worker。输出目录仍只有 `provenance.json` 与 `splits.json`，没有 `summary.json`、`predictions.npz`、`parallel.json`、`curves.jsonl`、`selection.json`、`selected_inner_states.npz`、per-transcript metrics、exit code 或 finished；日志 RuntimeWarning 保留。capture 当前 HEAD 为文档提交 `63b54aae879753f4d624ddc682f3f73350458e40`，直接父提交为生产启动代码 `911390cb…`，工作树干净，本轮未修改 capture、producer 或训练产物。
- **验收方法与通过范围**：以生产 `parallel.load_shard` 重算 NPZ/sidecar SHA，校验 `a10-03-e2-kinetic-shard-v1`、canonical spec 和五字段 identity 并解包；再用独立补充断言核对冻结 outer splits、候选/曲线/成本数量、选择顺序、早停语义、参数与预测有限性。四份 shard 均含 6 候选×3 inner folds=**18 条曲线和 18 份成本记录**，rung grids 均为 `[4,5]`，最终均选 **grid4、learning_rate=0.01、weight_decay=0**；`outer_test_used_for_selection=false`，最终三成员均从 rung last state 恢复，并按 validation plateau、patience25 停止。rung 未入选者仍标 `rejected_at_rung_not_converged`，不得改写为收敛。预测索引与各 outer 的冻结 `test_indices` 精确一致，density 全为有限 float64 且位于 `(0,1)`；independent 的 flux/residual 字段按合同为 null。该结果仅为 **4-shard scoped 阶段验收通过**，不是完整科学 verifier。
- 首轮补充审计脚本误将每个 outer 的开发转录本数固定为 715，outer2 按冻结 splits 应为 716；该脚本断言失败后已改为按各 outer test 数量计算并完整复跑通过。此为本轮审计 harness 假设纠偏，未发现 shard 内容异常，也不改变 protocol、数据或科学 Gate。

| shard | NPZ SHA256 | canonical science SHA256 | outer 预测数 | selected best epochs |
|---|---|---|---:|---|
| seed1234 / outer0 / independent | `4ad0fdf65efbd45333c33c89fcb9ac0c858ec2780c9c5f5aac0817df4a227861` | `857e20ee37f6d605283870b5b50b5174c29653b5d916fd1ddb41813aa11b030e` | 358 | 543 / 315 / 429 |
| seed1234 / outer1 / independent | `ebc3aca6944bfb91c0191bdcb494b82f10a83ad29a949446f0832f002dc640d2` | `eec636cf01ba58a04bd00f4a54cd832d02dcbc3ff687a6207fdb1c6e0e33ae90` | 358 | 407 / 392 / 470 |
| seed1234 / outer2 / independent | `d6ae8660b8318d7366a0a11237ef2c062567de35f2a45d15ad7b9a283c7eb1e6` | `57a68e0c6f78446918eed0ffb211f920c648a7917da6e1237c00c2cf6c3868da` | 357 | 413 / 418 / 504 |
| seed2345 / outer0 / independent | `72f94381a6484c687cdb40fc46d5d27359418b64437b0415419ab5fc10f6ab47` | `bf86ac1922a465b760652c9c3018d5813769df56ee106d487d1a35184d380f3f` | 358 | 417 / 322 / 421 |

- 四份 cache 的五字段 identity 相同并与当前 capture 对应源码重算一致：protocol=`3c4b9a3b345524d4c9ea9779aacb4c1f4afa57e131ee4c23d5d8f33b139b6b24`、implementation=`c26afcc6ac2ec1338134bffa95c76b16645e1164cee06a8bd0205211ab48579c`、mean-field operator=`f4805ace98c83b85884ebc10f2e77cacf3020787bd8c9e6c30c28d26ab4c94f8`、banded CUDA backend=`fdd7881a3aa77e254fe4e0d12435f784a1bd9c004669ef6b8299590a05e5734c`、parallel implementation=`425d5eaa8e34c12b9f734a175fcf2eabf32388ccf32ad0399f43cfff6738ca80`。startup provenance 含前四项且一致，其文件 SHA256=`8b2c493f7835c6bc677f7fe79735417958125bc31c9039599e3d5408201db95f`；splits SHA256=`3a96c66737befd53d37c7c8539d0e9f8e6c34b5d06f353bdc71c1e4b4a6c3371`。
- **科学边界不变**：这 4 个 shard 只覆盖 independent 的部分 seed/outer 组合，没有三臂完整预测、seed-first pooled CI、双比较 Holm 或 kinetic 逐成员 outer-test 残差复核。完整 verifier 未运行，H2/G1 未裁决且未通过；不能从 inner 选择或局部 shard 推断 outer 科学增量。protocol、统计、Gate 和 `1e-10` 均未修改，temporary 产物永久迁移仍待 teams 恢复。

## 6. 当前科学与 Gate 边界

- E0/A10-G0 已完成；E1/A10-02 已完成，H1 仅为开发集 TB-MSE 观察校准阳性。这些历史状态不变。
- E2 生产科学运行仍未完成，w21、v11、v13 已 OOM 退出，v12 已 `CUBLAS_STATUS_ALLOC_FAILED` 退出；v13 只有 2 个成功 cache shard 和 1 个 OOM 失败 shard，无完成摘要或 outer 预测。三臂 1000-step 无显式 GC soak 有界通过仅是工程证据；outer0 replay 有 547 字段不一致、science SHA 改变并拒绝复用，outer1 未重放，旧 cache 不变。v14 已以 4 workers 从全新空 cache 启动，producer PID `4176767`，cache hits 预期 0，登记时未见 OOM、warnings 保留，但仍无完成摘要或新的完整 outer 科学结论。H2 未证且 H2/G1 未裁决，A10-G1 未通过；不能从 v7/v8 部分曲线、历史进程/显存、inner 状态、工程测试、干净 synthetic 复现、soak/replay、cache/CUDA provenance 验证、精确 CTMC 对照或局部 rank 推断 outer 阳性。
- E3/G2 未证，G3 未通过；`final_untouched=false`、`SOTA=false`。大规模生成训练仍须先通过 G2。
- 平均场不是精确随机模拟，occupancy 仍只是实验依赖的相对占据/速度代理。不得作最终跨研究、绝对物理速率、因果机制、真实生物功能或 SOTA 结论。
- untouched24、MAGE functional untouched 及其派生文件继续禁止读取；冻结数据边界未因恢复工作改变。

## 7. 后续验收合同（不变）

1. 后续任何训练或 GPU 验证必须使用真实 CUDA，不得用 CPU 降级、显存占用或无效占卡任务冒充进展。
2. 每个实现修改须补项目风格测试并独立复核；保留失败日志与完整运行登记，不覆盖 v1–v8、v10/w23/w21/v11/v12 失败目录，不使用 `reset --hard`、`clean` 或 `git add -A`。
3. 只有产生完整 `summary.json`、`predictions.npz`、保存状态、selection、逐转录本指标和 curves 后，才可进入最终科学复核；缺失任一关键产物时保持未完成状态。
4. 独立复核须从原始开发数据、split 和保存状态重建预测，逐 kinetic 成员复核稳态，核对 CUDA、成本、双比较 Holm 与 seed-first pooled CI。
5. G1 仍按冻结合同裁决：E2 严格 transcript OOD 同时超过 independent 与 position，paired 95% CI 下界大于 0 且 Holm 通过。不得因恢复而降低阈值、改换弱 baseline 或追加/删除既有科学条件。
6. 若 G1 未通过，停止动力学主线；若通过，才允许已验证动力学量进入 E3。生成训练仍须 G2。

## 8. 本次文档登记范围

上一轮仅更新 `交接文档/spec.md`、`交接文档/tasks.md`、`交接文档/A10_00_TASK_DATA_BASELINE_CLAIM_MATRIX.md` 和本恢复交接并同步镜像。w21 轮次只登记 OOM 收束与性能根因，历史 handoff 与失败证据不删除；代码修改曾严格限制在新的 `/home/codonflow-a10-e2-structured` worktree。v11/v12 轮已推送 cache provenance 代码提交 `40603527…` 和文档提交 `f7e3fdbb…`，v13 审计文档提交为 `46039512…`。此前已登记 verifier `cac91df` 全量/干净复现证据、v13 最终 OOM 和受控真实 CUDA 显存根因。本轮登记 outer0 replay 最早分歧诊断及其数值边界、候选机制未确证、cache 继续拒绝复用和 v14 继续从全新空 cache 从头训练的事实，同步四份现行文档的本地、`codonflow-main/docs/handover` 和 memory 镜像；仅将这四份文档单独提交并推送 `a8-rk`。不修改 release dirty docs、producer、protocol、v13/v14 训练输出或其他项目进程，不预写 v14 或科学通过。

当前可执行事实是：**verifier `cac91df1468b0e01b4e619a5ca9f57e4b242896d` 的全量证据为 952 passed/1 failed/1 skipped/5 subtests，唯一失败是共享 GPU synthetic 多 worker OOM；干净 checkout 的 1/2-worker synthetic 各 27/27 shards、各 28/28 checks，manifest SHA `e34cba…`。v13 运行 13321.0843 s 后于 position/epoch890 OOM、退出 1，2 个成功 cache shard＋1 个失败 shard，无完成摘要，未运行 ready verifier。失败 PID 是 4057037，9.83 GiB allocated 属于该进程；4057040 是 peer。真实 32×1487、128-step A/B 证明 output-gradient hook 闭包逐 batch 保留 CUDA 张量：production 斜率 2334208 bytes/step、128 弱引用全活且 GC 无效；禁用 hook 或无 failure_context 均斜率 0、弱引用 0。诊断摘要 SHA `7b8b4fd8…`。release 仍为旧 `46039512…` 且只有四份文档 dirty，producer 科学实现代码提交仍为 `40603527…`；未修改生产代码、protocol、Gate、`1e-10` 或 v13 artifacts，未预写修复。outer-test 残差复核合同为 9657，28971 不是新增 Gate。E2/H2/G1 未完成、未裁决且未通过，没有生物有效性的新证据。**


**2026-11-27 当前可执行事实：hook 修复代码 `fe11a241…` 已发布，31 项定向测试独立复跑通过；本轮登记时 memory 工作树 HEAD 为 `3ba302dfcab8dd250409bcf1b514c415a5b3f9f9`，v13 仍只有 2 个成功 independent oracle shard。三臂 1000-step 无显式 GC soak 均完成并有界，kinetic 峰值约 100.58 MB、后半程下降，未见持续线性增长。outer0 正式 replay 结构完整但有 547 个字段不一致，science SHA 由 `cc3a19a7…` 变为 `d8b4817d…`，逐位不等价，按合同拒绝复用；outer1 未重放，旧 cache 不变。v14 已从全新空 cache 启动，输出 `kinetic_development_v14`，cache `kinetic_development_v14_from_scratch_shard_cache`，producer PID `4176767`，4 workers，cache hits 预期 0；登记时未见 OOM，warnings 保留，无完成摘要。outer0 最早分歧诊断报告 SHA256=`6866e92ee456712a30a0b895f01935c0a3cdf84f9073d51781657fc8c1c41a95`，最早 train loss 差为 2 ULP，最大 loss 差为 8.88e-16，预测最大差为 3.33e-16，离散选择不变但不满足 bitwise 合同；CUDA embedding backward 非确定性仅为未确证候选，cache 继续拒绝复用，v14 继续从全新空 cache 从头训练。科学 protocol、Gate、统计与 `1e-10` 不变，E2/H2/G1 未完成、未裁决且未通过。**


## 9. 2026-11-28：v15 最终失败与四问门槛

- v15 运行 `108084.95606188197 s` 后于 seed1234/outer1/kinetic/grid0/inner1、epoch2/batch11 发生 CUDA illegal memory access，退出 1。已有 **16 个完成 independent/position shards、0 个 kinetic shard**；无 `summary.json`、`predictions.npz` 或完整 outer 统计，H2/G1 未裁决。
- 精确失败快照：`/dev/shm/codonflow_a10_e2/kinetic_development_v15_from_scratch_shard_cache/failures/seed_1234_outer_01_kinetic_grid_0_inner_1_epoch_2_batch_11_1795862778466204005_99351.npz`。使用同一输入、当前模型状态和 `CUDA_LAUNCH_BLOCKING=1` 单进程重放，forward 含 NaN 逐位一致，backward 完成、梯度有限，89 次 rank-one＋27 次 QR，wall 172.9057 s。该结果排除“此输入在单进程路径必然越界”，但不排除多进程/异步执行边界，原 IMA 根因未闭合。
- **四问审查**：①失效点：raw occupancy 跨研究直接运输失败，独立密码子模型是否遗漏非局部信息仍待 E2 判决；②问题独立性：删除 CodonFlow 后，测量可分性、非局部同义效应和流守恒仍是独立问题；③机制解释：局部速率经排斥/通量守恒影响上下游密度只是数学候选机制，尚未由严格 OOD 和变体响应证实；④可预测性：强耦合/慢位点/边界受限应更明显，弱耦合应减弱，平均场误差也应在强相关情形增大，须预注册分层验证。机制与预测未闭合前，不新增 idea、不重提完整训练。
- 16 个完成 shards 只支持 baseline 工程与训练记录验收，不能推出动力学增量。temporary 产物继续保留，永久迁移仍待 teams 恢复。