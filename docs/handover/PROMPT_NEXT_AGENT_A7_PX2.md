# CodonFlow A7 px2 下一位执行者入口（2026-11-16）

旧版“CUDA 不可用、无有效 checkpoint、先完成 G0”的提示已失效。当前统一入口为 `PROMPT_NEXT_AGENT_A7.md`，实时交接为 `HANDOFF_A7_20261116.md`，恢复指南为 `RECOVERY_A7.md`。

当前只推进 P3/G2 严格 resume；G0 与双臂 G1 已通过。先核对 `/home/codonflow` 提交 `831303b93473144482e6fa99a692f2360ecf8dbb`、`eval_outputs/a7_g2_r5/execution_status.json` 和真实进程，不得重复启动、修改运行中的代码或宣称性能结论。全部约束以当前 spec/tasks 为准。
