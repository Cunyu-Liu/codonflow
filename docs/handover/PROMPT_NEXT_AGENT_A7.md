# 给下一位执行者的提示词（CodonFlow A7，2026-11-16）

先核验实时状态，不要执行旧提示中的训练或恢复命令，不要在文档或回复中记录服务器密码。

必读：`HANDOFF_A7_20261116.md`、`RECOVERY_A7.md`、`spec.md`、`tasks.md`、`checklist.md`、`RUNBOOK_NEXT.md`、`JOURNAL_20261112_A7_EXECUTION.md` 第 89 节。

当前事实：G0 与双臂 G1 已通过；FULL r5 e21 和 EDIT r5 e26 收敛。当前唯一任务是 P3/G2 learned vs 最强无学习简单搜索，正式严格 resume 正在执行 108 learned+54 shared simple；尚无 Go/No-Go，预印本不可提交。

代码 `/home/codonflow`，当前提交 `831303b93473144482e6fa99a692f2360ecf8dbb`，完整回归 210 passed、1 skipped。大型资产 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/`。先读 `eval_outputs/a7_g2_r5/execution_status.json`、`07_a7_data/g2_r5_resume2/execution.log` 和 executor.pid；不得盲目重复启动。

首次运行的 25 个合法分片必须复用，不得重跑或删除。允许 commit 仅限当前修复提交及已登记祖先 `1ef8961b96cb92e539981ac2c93c046fc7780c86`、`5f9e5a560b118568d435fa68a72ef9253d4252c5`；两历史提交仅文档差异。运行中不要修改或提交 `/home/codonflow`。

完成后独立复核 Gate v2、原始 500 唯一解、identity/legal、paired initial、NED、anytime AUC、bootstrap/Wilcoxon/Holm，再运行 `a7_plot_g2.py`。G2 Go 才进入 G3；No-Go 如实记录并停止 short-rollout 主贡献、扩参、RLOO 和 SOTA 写作。训练/GPU 验证必须真实 CUDA；禁止 CPU 静默降级。确认结果后才更新 PPT 和论文 Results。
