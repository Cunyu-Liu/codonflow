# CodonFlow A7 恢复指南（2026-11-12）

## 1. 是否可以重新做

> 2026-11-12 本轮执行状态：已重新通读全部本地交接文档并同步合同副本。px1:27882 与 px2:29375 的 TCP 端口可连接，但 SSH 会话均被远端提前关闭，尚未取得本轮 GPU、进程或资产证据；不沿用下方旧 CUDA 状态，不启动训练。代码工作副本必须为 `/home/codonflow`，大型资产保留在 `/teams`，不得反向覆盖。

可以，而且不需要重新立项目。当前可恢复的是 A7 warm-start synonymous CDS editing 路线：先完成 G0 数据与协议，再从零训练新 synonymous-corruption 模型，最后做 learned-vs-simple-search 决定性对照。

没有可合法 resume 的新模型 checkpoint。旧 v4 权重已证伪，只能保留作负结果；新 synonymous 模型必须从零训练。

## 2. 已上传/已核验的资产

共享根目录：`/teams/HoulabData_1788502323/liucunyu/codonflow1031`

- `01_code/codonflow/`：A6 最新基座叠加 A7 新代码；合并后远端测试 **131 passed, 1 skipped**。
- `01_code/codonflow_a6_85c36606/`：上传前的 A6 完整代码备份。
- `04_deliverables/`：A7 合同、论文提纲、PPT、图表和历史文档。
- `06_backup/backup_20261013/`：5.2GB 历史备份已传完，共 181 个文件，manifest 哈希一致。
- 外部既有数据：`/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/{corpora,checkpoints,eval_outputs}`。

D4/D5 最终 split、unique18 和 seed-0 五方法输出已核验。D4/D5 的数量和哈希与既有独立审计一致。

## 3. 恢复前仍必须补齐

### G0-A GPU 与执行环境

- `codonflow` 和 `pc_cng` 环境存在，CPU 测试通过。
- 当前服务器 `torch.cuda.is_available()=False`。在确认 GPU 分配、驱动和 CUDA matmul 前，只能做 CPU 协议工作，不能启动 GPU 主训练。
- 用 `/home/codonflow` 执行前，先从共享目录恢复/同步代码；不要直接用旧的 `/home` 文件覆盖共享 A7 代码。

### G0-B 数据与 benchmark

- 若只做训练：D4/D5 最终 split 足够，不必先重新下载全部原始物种。完整 `v3_all.fasta` 也已找到，SHA256=`5e106f9e…`。
- 若要从头重建清洗数据：还需 25 物种原始文件、release/URL/下载日期和逐步清洗记录。
- unique18 只能作开发集。untouched 24 基因确认集已冻结于 `07_a7_data/confirmation24/confirmation24.fasta`，SHA256=`a128bdbf…`。
- D5 train RSCU 已生成于 `07_a7_data/cai_ref_d5train.json`；24 个独立 calibration pool 已全部生成并验证，每池 56–70 个唯一目标向量，reference/pool 哈希、D5 RSCU 和正 scale 均通过检查。

### G0-C 既有输出复核

- unique18 seed-0 已有 18/18、五方法 `done`；还需 seeds 1/2 和全量 MFE/NED 独立复核。
- 不能把旧 v4 三臂、联合 HV、SOTA、scaling 或 RLOO 结果用于新论文。

## 4. 推荐恢复顺序

1. 确认 GPU 与 CUDA matmul，恢复 `/home/codonflow` 工作副本。
2. 运行 `PYTHONPATH=src /root/miniconda3/envs/codonflow/bin/python -m pytest -q`，应达到 131 passed、1 skipped。
3. 完成全量清洗/分布审计、untouched 确认集、独立 calibration 和 baseline manifest 复核。
4. G0 通过后，从零训练 `M_SYN_D4_*`，冻结 converged/best/last/training_state 与 SHA256。
5. G1 行为门通过后，做 learned vs uniform/hill-climbing/MH/AReUReDi-style 同预算对照。
6. 只有 G2 证明 learned 优于最强简单搜索，才继续 short-rollout、D5 确认和外部方法边界；RLOO/扩参不在当前关键路径。

## 5. 禁止事项

- 不读取旧 `a6_v4_56m_*` checkpoint 做新对照。
- 不把旧文件数量当完整 benchmark，不把 val plateau 当模型有效。
- 不用 test 输出估计 HV 归一化范围，不随机补足 baseline 解数。
- 不在 GPU 不可用时静默改 CPU 训练，不删除失败日志或负结果。
