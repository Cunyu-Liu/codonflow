# A8-RK28 科学 Closeout：HEK293 固定 GFP 观测 R1 结构增量的序列簇 OOD

## 结论

**FIXED_GFP_HEK293_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED。**

在 Mordstein HEK293 intronless Flow-seq 的 152 个固定 GFP 观测 R1 变体上，向 depth、GC3、GC、CpG、CAI 简单基线加入 ViennaRNA 预测的全片段及 48-nt 窗口 MFE，未产生可通过预注册家族 Gate 的序列簇 OOD 增量。四个主终点全部 FAIL；ridge 的 Spearman 与 MSE 改善在 10/10 seeds 均为负，HistGB 未显示稳定正增量。

这是一项**已独立复核的回顾性跨研究否定结果**，不是工程失败，也不是“显著为负即证明普遍有害”的结论。它否定的是本数据、本片段和本特征定义下的稳健跨研究结构运输主张。

- 科学代码与结果提交：`71d27dd7610559c2781849c2be7b2a26933c3d0e`
- 生产结果 SHA256：`c762484fde8fb3f7b9f13912bfbd75258a7538d45b13d604d498dd4ffd64c67f`
- 独立复算报告 SHA256：`edd1e14c8396b7ba3cce5b2accb94248af1020507765b8d64467a6b16e04b9d1`

## 数据与冻结设计

- 源表：152 个 variant、152 条唯一 300-nt observed-R1 序列；全部翻译为同一 observed-R1 蛋白段。
- 仅使用 `variant_id` 与 `sequence_5prime_300nt` 做标签隔离覆盖审计；90% complete-linkage 在读取 outcome 和模型特征前冻结。
- 共 74 个序列簇，35 个 singleton，最大簇 12；primary 五折为 30/31/31/30/30 条，各折 15/15/16/15/13 簇。
- 10 seeds × 5 folds × 2 backbones × 3 arms，共 **300 次真实 CPU 模型拟合**；无调参、无 GPU。
- primary seed=20261222；20,000 次整簇 bootstrap 与 20,000 次整簇成对置换；四终点 Holm。

## 主结果

正方向始终有利于 structure：Spearman 为 structure−simple，MSE 为 simple−structure。

| Backbone | Endpoint | Effect | 95% cluster-bootstrap CI | Holm p | 正向 seeds | Gate |
|---|---:|---:|---:|---:|---:|---|
| ridge | ΔSpearman | -0.039264 | [-0.089517, 0.003815] | 0.403980 | 0/10 | FAIL |
| ridge | MSE improvement | -0.082105 | [-0.174100, 0.014918] | 0.403980 | 0/10 | FAIL |
| HistGB | ΔSpearman | -0.025531 | [-0.136859, 0.078912] | 0.904255 | 3/10 | FAIL |
| HistGB | MSE improvement | -0.133851 | [-0.494481, 0.193206] | 0.904255 | 5/10 | FAIL |

Primary-seed 绝对 OOF 表现：

| Backbone | Arm | Spearman | MSE |
|---|---|---:|---:|
| ridge | simple | 0.349548 | 2.057832 |
| ridge | simple + observed-R1 MFE | 0.310284 | 2.139937 |
| HistGB | simple | 0.238982 | 2.585560 |
| HistGB | simple + observed-R1 MFE | 0.213450 | 2.719411 |

MFE-only 仅为描述性参考，不替代增量对照：ridge Spearman/MSE=0.172049/2.249101，HistGB=0.119366/2.705108。

## 独立检查与保留的失败记录

- 冻结验收 **40/40 PASS**；覆盖审计 9/9 PASS；生产合成测试 **20/20 PASS**。
- 独立实现从原始 CSV 重新聚类、重新计算 CAI/GC/CpG/ViennaRNA MFE、重做全部 300 次拟合与全部 resampling；最终 **54/54 PASS**。
- 生产合成测试最初把 L2 ridge 误当作无正则 OLS，精度阈值过严而停止；未启动正式拟合，生产代码未改，失败记录已保留。
- 独立验收最初为 **53/54**，唯一失败是 pandas 将 arm 名称字符串 `null` 读成缺失值，导致 10 行描述性 null 未参与合并。所有数值检查已经一致；保留初始报告 SHA256=`8210af62d7c8d0594f1532ef26346d4dcbd38c81473b3e0ca73049bd31bd4131`，仅修正读取参数后全量重跑至 54/54 PASS。
- 生产与独立预测、1,520 个折分配、70 个指标行、40 个 seed effects、50 个训练日志行、20,000 次 bootstrap/置换数组均逐值一致。

## 与 RK27 的关系及边界

RK27 的 Kudla measured 5′ MFE 固定 GFP 序列簇 OOD 强增量，没有在 RK28 的不同研究、宿主、assay、观测片段和预测结构特征中复现。两者共同说明结构信号具有研究/宿主/片段/特征定义依赖，不能把单一研究的强增量提升为普遍空间机制。

本结果：

- 是回顾性跨研究 observed-R1 序列簇运输检验；标签曾用于 RK02 development，**不是独立 untouched 确认**。
- 仅观察 CDS 4–303 的 300 nt；中央 138 nt 未观察，不能恢复完整 CDS，也没有作者 GFP 身份映射。
- 使用 ViennaRNA 预测片段 MFE，**不是 measured structure**，也不是完整 CDS 的 5′ 起始区 measured MFE 直接外部复现。
- **不是 protein OOD**；不测量 translation velocity 或 mRNA decay；不证明起始可及性—全程速度—降解的完整空间耦合。
- CAI 沿用 RK02 的外部 raw-reference 行为，保留 whitespace/frame caveat；没有静默清洗或改作已验证人源参考集。
- **RK-G1 仍为 false，生成训练未授权。** 不根据本否定结果追加阈值搜索、重 split 或结果导向调参。

## 复现与下一步

- 代码：`/home/codonflow-a8-rk/scripts/a8_rk28_{audit_sequence_coverage,run_sequence_cluster_ood,verify_sequence_cluster_ood}.py`
- 协议、结果与独立报告：`/home/codonflow-a8-rk/audits/20261121/RK28/`
- 大型预测、折分配、训练日志、统计数组及独立重算：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk28/mordstein_observed_r1_sequence_cluster_ood_v1/`

下一步应寻找真正独立的完整 CDS、明确蛋白身份和可解释结构测量/预测的功能验证；在完成这类证据前，不启动昂贵生成训练，不宣称跨宿主普遍结构机制或 RK-G1 闭合。
