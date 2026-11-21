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

## 工作树与干净克隆回归

- 当前工作树在 `b0128b0d66779e0e77ee638d61d14dcefa6c3de5` 上完成项目标准 `pytest tests/`：**423 passed, 1 skipped**，日志为 `project_pytest_rk30_preoutcome.log`。
- 首次 HTTPS 干净克隆因 `GnuTLS recv error (-110)` 中止，未执行测试；保留该网络失败。改用已用于推送的 SSH 通道后，在同一 HEAD 的 `/home/codonflow-a8-rk30-clean-check` 依次通过冻结测试、模型测试和完整项目测试；后者同为 **423 passed, 1 skipped**，日志为 `clean_clone_preoutcome_pytest.log`。
- 以上仅是预结局工程复现，不代替真实数据齐备后的 clean-checkout 科学结果复现。

## 本地临时 spool 传输验收

服务器到 ENA 的吞吐较低且增加服务器并发曾触发连接拒绝，因此新增 `scripts/a8_rk30_spool_transfer.py` 作为数据获取辅助工具。正式数据仍只落在 `/teams`；本地 `/tmp` 仅在远端验收前保存临时文件。该工具不改变协议、计数规则或模型。

- `SRR10714571` 端到端验收通过：103,317,045 bytes；ENA MD5 `d60cc1c913406a9c8938c7ecb87f0220`；SHA256 `59ebb3e798e5873b3a0ac481018d1f5d0641f3a716e4bdfa9123263888f5802f`。本地大小/MD5、远端大小/MD5、原子 rename 和本地临时文件清理均通过。
- 重跑同一 run 时，正式文件预检独立复算 MD5/SHA256 后返回 `existing_precheck`，不重复下载或上传。
- 初次辅助脚本通过 SSH 传递多行 `python -c` 时引用失败，未转正临时文件；改为 stdin 传脚本后重跑通过。手工末段清单曾误含非目标 run，现改为从 SRA metadata 的两个 HeLa Flow-seq 标题完整推导 56 个 run 并断言数量。
- 三组并行曾超过 SSH 复用会话上限，产生可重试的 precheck 失败；未据此判定数据缺失。现统一为一个最多 6-worker 的协调任务，为监控会话保留余量。
- 原服务器下载保留的静态 range-stage 只有在预期大小和 ENA MD5 均匹配、且 60 秒内无修改时才原子转正；`SRR10714520`、`SRR10714521` 由此通过。正在写入的临时文件不参与。

## SSH 中断与离线续传验收

2026-11-21 17:02 左右服务器 SSH 端口拒绝连接，本地 6-worker spool 与本地 watcher 调用退出；服务器端完整流水线 watcher 继续运行并持续写入等待日志，未启动计数或模型。重新认证后恢复了复用会话；凭据未写入命令、文档、Git 或回复。

- 中断前 12 个 HeLa 正式文件已有本地和远端双重记录；恢复后按 SRA 预期大小独立检查为 13 个，新增的 `SRR10714562` 来自保留的原服务器下载路径。所有临时 `.upload-local` 均不视为正式数据。
- 为利用离线时间，`a8_rk30_spool_transfer.py` 新增显式 `--local-only`：跳过远端预检，仅执行 ENA 下载、大小/MD5 与 SHA256 校验；后续默认运行仍执行原远端预检、上传、远端 MD5 和原子 rename。默认上传逻辑未改变。
- 离线模式对 7 个已完整本地文件完成独立复算并返回 `local_only_verified`；6-worker 后续 ENA 连接出现超时/截断，保留 retries，主动降为 2-worker 断点续传。部分文件没有因重试被当作完成。
- 新 HeLa `SRR10714571` 的前 100 条 reads 全部为 300 nt，序列与质量行长度一致；这只是格式/读长 QC，不是计数结局或科学结果。

## 结果口径与论文整合器验收

- 代码复核发现 `a8_rk30_closeout.py` 的绝对表现说明误写为“10 seeds 均值”；实际实现一直使用冻结 primary seed。已仅修正文档标签，并在 closeout/PPT JSON 增加 `absolute_performance_seed`，不改变任何模型、效应、CI、p 值或通过规则。
- 新增 `a8_rk30_integrate_manuscript.py`，从 RK29 独立失败报告和 RK30 release-gated closeout 自动生成章节、主要/次要终点表、绝对表现、成本、证据锚与参考文献。只有 raw/model 双复核、1,700 fits、16+12 有限终点、队列和哈希绑定全部通过才可写稿；摘要不在本阶段生成。
- 首次合成整合因早期 counting fixture 缺少 `n_runs/n_experiments` 停止，未修改真实稿件。测试路径现从冻结协议推导同一数值；真实生产仍优先读取 counting 报告字段。失败保留在本记录。
- 同一合成 closeout 连续整合两次的稿件 SHA256 均为 `4a96ed56af2df92d8d008e32a115c740535b127f46df45ceb88a8504984f74b9`，章节、参考文献和证据锚均只出现一次，输出 `PASS_IDEMPOTENT_MANUSCRIPT_INTEGRATION`。
- 将 `raw_independent_pass` 人为设为 false 的反向 fixture 在哈希检查前被拒绝，未生成稿件，输出 `PASS_NEGATIVE_RELEASE_GATE_PRE_HASH`。所有合成文本与数值只用于工程验收，不进入真实论文或 PPT。
- 复现清单已纳入整合器源码哈希。真实结果后将在干净克隆重新计数 64 runs、重跑 1,700 fits 并独立复核；该最终复现尚未执行。
- 稿件门禁回归首次误用 `python scripts/a8_rk30_test_freeze.py` 与 `python scripts/a8_rk30_test_model.py` 直接执行 pytest 模块，产生空日志和 0 tests，不能算测试通过；`freeze_tests_v6_manuscript_gate.log`、`model_tests_v4_manuscript_gate.log` 保留为失败证据。`a8_rk30_reproduce.sh` 中同样的入口错误已改为 `python -m pytest -q`，随后重跑至明确计数后才允许提交。

## 独立 raw verifier、复现等价与 release-gated PPT 工程回归

以下均使用 `/tmp` 或本地 staging 中的显式合成副本；不是新 HeLa 结果，不进入论文或线上 PPT。

- raw verifier 现绑定协议 SHA256，记录真实耗时，强制 `64 runs × 100 reads = 6,400` 条独立蛮力审计，并从长表重新计算结局。64-run 小型 fixture 使用真实 152 个参考 ID/序列、每 run 一个 bin、每 variant 125 reads。`raw_verifier_tests_v3_actual_pytest.log` 为 **1 passed**：正向 64 checkpoints、6,400 reads、协议哈希和成本字段通过；删除一条审计 read 后以 6,399 条触发 FAIL。
- 前两次 raw fixture 回归未通过并保留日志：v1 在聚合修正部署前运行；v2 暴露 fixture 错把单 bin checkpoint 的 125 写成八 bin 汇总 1,000。仅修正 fixture 的 checkpoint 期望后 v3 通过，未改变真实计数规则、阈值或结局。
- 合成 closeout v4 完成独立模型全量重算：`PASS_INDEPENDENT_MODEL_VERIFICATION`，独立复核耗时 237.449872 秒；closeout 为 `PASS_RK30_VERIFIED_RESULT_PACKAGING`，稿件整合为 `PASS_RK29_RK30_MANUSCRIPT_INTEGRATION`。raw 成本 0 仅为该合成 fixture 占位，真实成本尚未产生。
- 生产—复现比较器对隔离合成副本比较 13 个 CSV、7 个 NPZ 的名称/shape/dtype/精确值及科学摘要，当前接口得到 `PASS_RK30_PRODUCTION_REPRODUCTION_EQUIVALENCE`；把生产与复现指向同一目录会被拒绝。该 PASS 不是 clean-clone 真实复现。
- 复现入口区分首次生产运行和 clean-checkout 等价复现。旧 watcher 保持首次生产模式；只有显式 `RK30_REPRODUCTION_COMPARE=1`、独立 artifact root 和独立 production root 才执行 CSV/NPZ/科学摘要等价比较及稿件复现。manifest 不再把 verification-only、dirty checkout 或缺少等价比较标成 clean reproduction。稿件整合调用已对齐真实 `--artifact-root/--manuscript/--output` CLI。
- 新增 `a8_rk30_ppt_page.py`：只读取冻结协议、closeout、PPT payload、稿件整合报告、clean manifest 和等价报告，不重算科学结果。九类合成页面均通过 XML、960×540、单页、画布边界和文本宽度检查；把 manifest 改为 verification-only 后明确拒绝出页。九份 XML 均未上传，线上 PPT 未被修改。
- 远端 Python 3.10 编译首次发现表头 f-string 使用了新版解释器语法，测试在正式 pytest 前停止。改为显式 `bold` 属性后，九份 XML 的 SHA256 与兼容性修复前逐一相同，并重新进入远端编译和测试门禁。
- 最终远端门禁日志为 `rk30_gate_tests_v2_actual_pytest.log` 与 `project_pytest_rk30_reproduction_gate.log`：冻结/模型/raw 合计 **20 passed**；项目标准 `pytest tests/` 为 **423 passed, 1 skipped, 11 warnings, 5 subtests passed**。此前直接 pytest 调用漏设 `RK30_PROTOCOL` 的收集错误保留在 `rk30_gate_tests_v1_actual_pytest.log`，不计为通过。
- 真实 closeout 首次发现 raw verifier 未输出 `counting_summary_sha256`，而早期合成 raw fixture 恰好自带该字段，导致烟测漏检；closeout 在发布前停止，未写论文或 PPT。现由 verifier 直接计算 counting 报告 SHA256，并在 64-run fixture 中新增该绑定断言。此修复只增加证据绑定，不改变 reads、结局、预测、效应、CI、p 值或科学判定。
