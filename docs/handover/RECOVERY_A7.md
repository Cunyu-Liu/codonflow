# CodonFlow A7 恢复指南（2026-11-16 当前版）

> 本文取代 2026-11-12/13 的“CUDA 不可用、无有效 checkpoint、等待 G0”状态；那些内容仅是历史。

## 当前状态

- G0 已通过，FULL r5 e21 与 EDIT r5 e26 已收敛并通过 G1，双 preflight 就绪。
- 当前仅允许 P3/G2。首次 G2 完成 25 个有效分片后因混合 code commit 停止；已修复并严格 resume，尚无科学 Go/No-Go。
- G2 执行目录 `/home/codonflow` HEAD 固定为 `831303b93473144482e6fa99a692f2360ecf8dbb`，完整回归 **210 passed, 1 skipped**。GitHub 最新 main=`07d115ae6f2fbf73d84be3ec230cec07fa5a562b`，新增二级分析且回归 212 passed / 1 skipped；执行目录显示 behind 是刻意冻结，不得在运行中 pull。
- 代码与提交在 `/home`；大型资产在 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/`。

## 恢复顺序

1. 先读 `HANDOFF_A7_20261116.md`、`spec.md`、`tasks.md`、`checklist.md` 和 journal 第 89 节。
2. 核对 `/home/codonflow` HEAD、origin/main 与 clean 状态。运行期间不得修改或提交该目录。
3. 读取 `eval_outputs/a7_g2_r5/execution_status.json` 和 `07_a7_data/g2_r5_resume2/execution.log`；用 `executor.pid` 核对真实进程，不能仅凭 PID 存在推断成功，也不能重复启动。
4. 若干预前状态为 running，先确认 learned worker 的 `device=cuda:0` 和真实 CUDA 进程；CUDA 不可用或 CPU 静默降级必须停止并留证。
5. 若执行器 failed，保留状态、日志和现有分片。只有登记的祖先 commit 才可进入允许集合，且必须做差异审计；不得任意加入 HEAD 或重跑合法旧分片。
6. 只有 `g2_complete` 后运行 Gate 独立复核和 `a7_plot_g2.py`。G2 Go 才能进入 G3，No-Go 按 spec 停止后续性能路线。

## 已验证恢复证据

- dry-run：108 learned+54 shared simple；SHA256=`c87e85441ca0b94fbebb168dc9d28111b989e8d343d31f4ab191d99eb9feb06d`。
- 25 个旧分片 precheck passed=true；SHA256=`905fe45abd8937b9316c0a7d612bb7f2a8de8b97585418df782117d8504531e4`。
- 旧分片均为 done、identity=1、code_dirty=false，恢复日志显示 `skipped_existing`。

不得使用旧 arbitrary-corruption checkpoint，不得把训练 loss、G1、smoke、identity 或文件数量写成 G2 性能结论。
