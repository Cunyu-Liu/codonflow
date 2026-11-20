# A8-RK28 英文工作稿—科学—PPT—提交最终绑定

## 状态与提交

本记录绑定 RK28 的科学结果、科学 closeout、在线研究主稿和英文工作稿。英文工作稿提交为 `b68e3fba391563ce7895a0dafd532ed84b1d7f76`，科学提交为 `71d27dd7610559c2781849c2be7b2a26933c3d0e`，科学 closeout 提交为 `868cdb1d47d71c1a266d783628e047d41ba007e0`，PPT 证据提交为 `fb2c907eb068da4417bdee85449c08afa7466186`。四个提交均须存在于本地 HEAD 和 `origin/a8-rk` 的祖先链中。

## 科学结论与边界

RK28 的权威结论为 `FIXED_GFP_HEK293_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED`。152 个固定 GFP 变体形成 74 个序列簇，完成 10 seeds × 5 folds × 2 backbones × 3 arms 的 300 次真实 CPU 拟合。四个确认性终点全部失败，ridge 两个终点在 10/10 seeds 均为负，HistGB 未显示稳定正方向。该结果否定结构增量可普遍跨研究运输的强表述，但不证明结构普遍有害，也不与 RK27 构成直接矛盾，因为研究、宿主、assay、序列覆盖与结构特征操作化不同。

本分析只是回顾性跨研究 observed-R1 序列簇运输，不是独立 untouched 或 protein OOD 确认；未恢复完整 CDS，未获得作者 GFP 身份映射，未测量结构、velocity、decay 或完整空间耦合。RK-G1 仍为 false，昂贵生成训练未授权，functional untouched 未评价。

## 英文工作稿更新

`paper/CodonFlow_preprint_A8.md` 仅以插入方式增加第 6.39 节、Table 11 和 12 条 RK28 证据行。更新后稿件 SHA256 为 `f965d37c1b7ed1e98ca36669c6b7a526124c68b9f1b465cf42dcdbc197e6a90a`，单节 SHA256 为 `6a47f1a1fba86ddc25c478dc024a63c2a0c3926ec61a1b4ab90489122f0336b2`，更新报告 SHA256 为 `fc2317f530a70ff04045b5e989e01860b016dd0bff1d124298e08c93fedf9385`。删除新增节和新增证据行后，可逐字节恢复原 RK27 稿件；RK27 及更早正文、表格、References 和证据行均未改写。

单节英文写作任务为 draft / section / markdown_only / needs_citation=no，正文 603 词。prepare 通过，draft check 通过，其 SHA256 为 `7a0c381b2e5e0424672654e76ee108f6ef4c7ce0879f7c75374d5c726f8a3e1b`；三态为 Markdown-only PASS，状态文件 SHA256 为 `03f3d50a3438b29b803777f6e15d837ec97450a22720e0d5619968e861b566d9`。Makefile 的 `finish_with_status` shell 失败已保留在交付日志中；随后由 `make status` 读取已生成终稿并确认 PASS。该单节 PASS 不证明整篇可提交，当前仍为 non-submittable working manuscript。

## 验收与失败记录

英文工作稿验收为 92/92 PASS，报告 SHA256 为 `085556c462c24b4425d0f03bc9769d06d64d2ed7d4bb7969b5c5745e7002da18`。推送后复验同为 92/92 PASS，报告与推送前字节一致，稿件哈希保持不变。科学独立复算为 54/54 PASS，科学 closeout 与 REGISTRY 绑定为 101/101 PASS。生产结果 SHA256 为 `c762484fde8fb3f7b9f13912bfbd75258a7538d45b13d604d498dd4ffd64c67f`，独立报告 SHA256 为 `edd1e14c8396b7ba3cce5b2accb94248af1020507765b8d64467a6b16e04b9d1`，科学 closeout 验收报告 SHA256 为 `deb22cf239ce46dea31a6ee5b08b782ef991d8111116216a091d0155314dd68a`。

初次生产合成测试误将 L2 ridge 当作无正则 OLS，已在读取研究标签前停止；只修正合成测试期望，最终 20/20 PASS。初次独立验收 53/54 的原因是 pandas 将字符串 `null` 读成缺失值；数值和科学结论已一致，只修正 CSV 读取，最终 54/54 PASS。两份失败记录均保留，未改写生产模型、协议、阈值或科学结果。

## 在线 PPT 绑定

RK28 页候选验收为 256/256 PASS，候选 XML SHA256 为 `680a85b3d041e3b0bcf1d3321b9ba8268406e5a259a46dd5b8a90588cd557cd1`，候选报告 SHA256 为 `90d85dc0c25c1d8e7287a49e8b45919b6d661a2e61dbdb0da7b6429969f16f64`。在线验收为 624/624 PASS，报告 SHA256 为 `d85aeba04d6a77abb5dbfe1c9603d1ca0d8b27cc713932899ff2f9bba32f4bed`。写入响应确认页面 `pZC`、revision 83，响应 SHA256 为 `7fb0db7be6b05c1273e256e95617859497961117f6aece006a4eb3ac5bb8bf5b`。前 119 页语义、几何、备注和元素 ID 全部保留，RK28 页只追加一次。

## 复验入口

权威稿件位于 `/home/codonflow-a8-rk/paper/CodonFlow_preprint_A8.md`。稿件验收、post-push 复验、科学结果、独立报告、科学 closeout、PPT 候选与在线验收均位于 `/home/codonflow-a8-rk/audits/20261121/RK28/`。大型预测、折分配、训练日志和统计数组保留在 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk28/mordstein_observed_r1_sequence_cluster_ood_v1/`，未混入 Git。
