# 给下一位执行者的提示词（CodonFlow A7，G2 No-Go）

先读 `HANDOFF_A7_20261116.md`、`RECOVERY_A7.md`、`spec.md`、`tasks.md`、`checklist.md` 与 journal 第95节。不要执行旧版启动、resume、G3或D5命令，不要在文档或回复中记录服务器密码。

G0与双G1已通过；G2已正式 **No-Go**。324/324结果完成，identity/legal=100%，但FULL/EDIT中位相对改善−94.28%/−93.47%，CI完全低于0、Holm p=1.0、NED未达；两臂18/18基因均负效应，hill-climbing均为最强基线。原Gate与独立重算逐项一致，禁止进入G3、D5确认、扩参、RLOO或SOTA写作。

证据：`eval_outputs/a7_g2_r5/g2_gate.json` SHA256=`a2e157b2…`；`g2_gate_independent_rerun.json` SHA256=`9a1b5c9b…`。主图、原始Pareto、best-at-budget、非支配覆盖和成本表已生成。PPT已49页，SHA256=`493feb8d…`。

当前只允许训练诊断与负结果路线：分析搜索轨迹、目标响应、位置覆盖、NED和成本，区分有限步objective-blind proposal缺乏终端优化与实现问题。任何新实验先登记协议，不得借诊断绕过G2，不得把identity、G1或训练loss写成学习价值。
