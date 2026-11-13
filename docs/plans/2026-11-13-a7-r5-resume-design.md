# A7 r5 精确恢复设计

## 背景与选择

r4 FULL/EDIT 在 e3 中途同时终止，日志无 Python traceback，watcher 状态被截断，随后写入实测返回 `Disk quota exceeded`。e1/e2 独立验证和 checkpoint 完整。采用新 r5 目录从 e2 精确恢复；不覆盖 r4，也不从零重训。配额通过移除可重建的冗余环境归档恢复，未删除数据、权重或他人文件。

## 数据流与防错

- r5 配置标记 `frozen_resume_from_complete_epoch`，保留 r4 数据、模型、优化器、验证和收敛参数，只更换 run ID、输出目录与 resume 来源。
- 启动前核对 G0、数据 SHA、连续 epoch history、best epoch/loss、优化器、CUDA RNG、源 training_state SHA 和目标目录不存在。
- 将 e2 `log.jsonl`、`best.pt`、`training_state.pt` 复制到 r5；复制后重新计算 SHA。实际 `--resume` 指向 r5 内冻结副本，并写 `resume_provenance.json`。
- 先确认 CUDA 可用再复制和启动；任何检查失败均不启动训练。r4 文件和空 watcher 状态永久保留。
- 新建 `g1_r5_watcher` 与 `g2_r5_watcher`，仅在 r5 真实收敛、G1 和双 preflight 后运行 G2，不继承 r4 的等待或失败状态。

## 验证

回归测试覆盖：原 from-scratch 守卫不变、合法恢复命令与 provenance、历史/状态不一致拒绝、目标目录拒绝覆盖、G1 watcher 只接受带有效 provenance 的恢复配置。部署后先 dry-run 和哈希复核，再并行启动两臂；完整 pytest 通过后才提交 GitHub。
