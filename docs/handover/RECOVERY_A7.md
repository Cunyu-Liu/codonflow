# CodonFlow A7 恢复指南（2026-11-16，G2 No-Go）

## 当前唯一有效状态

G0 与双臂 G1 已通过；G2 已正式 **No-Go**。不得进入 G3、D5 确认、扩参、RLOO 或 SOTA 写作；仅允许训练诊断与负结果路线。预印本不可提交。

- 324/324 结果完成，108 learned 全部真实 CUDA，identity/legal=100%。
- FULL/EDIT 中位相对改善 −94.28%/−93.47%，CI均完全低于0，Holm p=1.0，最低NED ratio=0.133/0.163。
- 两臂18/18基因均负效应，最强基线均为hill-climbing。
- 原Gate SHA256=`a2e157b2635860460cde95d8c3a03d12a7b948b2cd6d20dab5ce37deb8923cbc`；独立重算SHA256=`9a1b5c9b0b6313789c1608bfecf39d31587fbc4ea624035a78b0589cc9c475e1`，逐项一致。

## 恢复检查

1. 先读 `HANDOFF_A7_20261116.md`、`spec.md`、`tasks.md`、`checklist.md` 与 journal 第95节。
2. 读取 `eval_outputs/a7_g2_r5/execution_status.json`，应为 `g2_complete` 且 `scientific_gate_passed=false`。不要重新启动G2或G3。
3. 核对原Gate与独立重算的统计、NED和输入哈希；主图与二级manifest已生成，540个二级run记录包含两臂共享baseline。
4. 代码 `/home/codonflow` 可 fast-forward 到最新分析提交；G2历史执行提交831303b及两个登记祖先只用于追溯，不要回滚或重跑。
5. 大型资产仅在 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/`。所有失败日志、负结果和旧分片保留。

## 后续允许动作

只分析训练目标、learned/hill-climbing轨迹、目标响应、位置覆盖、NED和成本。G1非退化不等于G2有效，identity不等于学习价值。任何新诊断实验先登记协议，不得借诊断进入short-rollout、D5确认、扩参或SOTA路线。

PPT 已49页，SHA256=`493feb8df0ba1048672a45dccdee75116d6d78903a7a855b0a3a4f25ef983ba6`。分析修复提交 `3d09147e9b8a3aab50faddbc89269b0609bbfeb4`，回归212 passed、1 skipped。
