# Journal 2026-11-12 · A7 执行恢复与合同同步

## 1. 本轮范围

- 逐份读取本地 `交接文档/` 全部 16 份材料；以 A7 warm-start synonymous CDS editing 合同为准，旧 scaling/RLOO/SOTA 与 arbitrary-corruption 模型结果均不进入新科学结论。
- 建立执行计划 `codonflow-main/docs/plans/2026-11-12-a7-g0-recovery.md`。
- 本轮未启动训练、未运行 GPU 评测、未修改 PPT，未将任何 smoke/proxy 结果写成结论。

## 2. 已确认的合同状态

- 当前仍为 P1/G0，G1–G4 不得越过前置门。
- 交接证据记录 confirmation24、D5 train RSCU 和 24/24 calibration pool 已完成并验证；执行时仍须在实际实例复核路径、record、hash、source role 和 scale。
- unique18 seed-0 有 18/18、五方法完成记录；seeds 1/2 与全量 MFE/NED 独立重算未完成。
- 全量数据来源、release、清洗数量守恒、分布和元数据审计未闭环。
- 没有有效的新 synonymous checkpoint；不得从旧 v4 权重恢复或评测。

## 3. 文档与配置修复

- 更新 `交接文档/spec.md` 与 `codonflow-main/docs/handover/spec.md`：写入 `/home` 代码、`/teams` 大型资产、CUDA 强制和并行不得越门的执行约束。
- 更新两处 tasks/checklist：消除确认集、RSCU、calibration 和 seed-0 状态漂移，新增 T1.8 GPU/环境验收。
- 更新 `configs/a7_data_protocol.json`：记录 confirmation24/RSCU/calibration 路径和完整 SHA256，同时明确状态为 handoff-verified、remote-recheck-required。
- 更新 `RECOVERY_A7.md` 和 `RUNBOOK_NEXT.md` 的当前执行状态。

## 4. 远端连接事件与证据边界

- px1 `px1-jcy.matpool.com:27882`：SSH 返回 `Connection closed by 125.71.97.44 port 27882`。
- px2 `px2-jcy.matpool.com:29375`：初次 askpass 文件无执行权限，修正权限后连接仍被远端关闭；随后通过 `sshpass -e` 使用本机 askpass 提供凭据，仍返回 `Connection closed by 125.71.97.44 port 29375`。
- 两端口 TCP 可达，但这不等于 SSH 会话、GPU 或数据可用。未获得本轮 `nvidia-smi`、CUDA matmul、进程或资产输出。
- 处置：保留失败证据，不启动 CPU 替代训练；后续先诊断 SSH 服务端/实例状态，再执行 G0 在线核验。

## 5. 验证记录

- `configs/a7_data_protocol.json` 已通过 `python3 -m json.tool` 解析及路径、哈希、记录数、CPU fallback 禁止断言。
- 两处 spec/tasks/checklist 已做逐字节一致性与 SHA256 检查；三份镜像均一致。
- 本地完整回归为 **128 passed, 1 skipped**，不是交接记录的 131 passed。GitHub `origin/main=4f3dac9` 尚未包含本地 A7 文件；远端共享副本可能另有 3 项测试，必须在 SSH 恢复后核对，不得把本地计数写成远端计数。
- 本地目录原为无 `.git` 的源码归档，现已关联 GitHub 并提交 `3b45775 feat: add A7 protocol and synchronize recovery contract`，提交前 `git diff --cached --check` 通过。
- 首次标准 push 遇到 HTTP/2 framing error；改用 HTTP/1.1 后遇到 GitHub 443 连接超时。代码尚未确认上传，不强推、不改写历史。

## 6. 下一步

1. 完成合同副本三重核对并运行本地完整回归。
2. 恢复 SSH 后先保存代码版本、GPU/驱动、CUDA matmul 和完整测试证据。
3. 在线复核既有资产，不重复生成 calibration；并行完成全量数据审计与 unique18 seeds 1/2、MFE/NED 独立重算。
4. 只有 C2 全部通过才启动从零 `M_SYN_D4_*` 训练；训练持续到注册的独立 val plateau，保存完整日志、训练状态和哈希。

## 7. unique18 独立 MFE/NED 复算工具

- 新增 `scripts/a7_recompute_unique18.py` 与 `tests/test_a7_recompute_unique18.py`。工具不修改原 JSON，只从冻结 solutions 重算 MFE/NED 和 CAI/GC/motif，并另写审计结果。
- 强制核对 source/benchmark/RSCU 哈希、record/seed、identity、真实唯一解数、目标向量形状和有限性；缺失方法/seed、重复或错位序列均不能通过。
- 首轮目录契约测试因本机缺少 ViennaRNA 失败，保留该事实；测试改为显式注入固定 fold 值验证逻辑，真实运行不在缺少 ViennaRNA 时降级或伪造数值。
- 最终 focused tests：**19 passed**；完整回归：**132 passed, 1 skipped**。这证明复算工具契约，不证明真实 unique18 已完成复算。
- GitHub 标准 push 再次因 443 连接超时失败；px2 本次为 `Permission denied`，未获得 SSH 会话。
