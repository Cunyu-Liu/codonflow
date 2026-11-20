# A8-RK27 预注册卡：Kudla 固定 GFP 序列簇 OOD 运输验证

- **状态**：已在任何 RK27 模型拟合或新表达关联分析前冻结；本分析为回顾性运输验证，不是独立 untouched 确认。
- **候选问题**：RK22 中 measured 5′ MFE 相对 CAI、CDS GC、CDS GC3 的增量，能否通过固定 GFP 的序列簇 OOD，而不只在随机 exact-CDS 五折中成立？
- **可证伪假设**：ridge 与 HistGB 的 structure−simple Spearman、simple−structure MSE 四项均为正，簇 bootstrap 95% CI 均不含 0，簇内置换 Holm p 均小于 0.05，且每项至少 8/10 个划分 seeds 方向为正。
- **既有观察**：RK22 随机五折显示强 MFE 增量，但 150 个 exact-CDS 组均参与开发，且没有序列簇运输检验。
- **强对照**：同模型、同折、同训练的 CAI+GC+GC3；MFE-only 仅作描述性参照，train-fold mean 为 null。
- **划分**：只读取 CDS/蛋白注释。90% complete-linkage 为预声明覆盖规则选出的最低合格阈值；150 条唯一 CDS、同一蛋白、37 簇、最大簇 61、13 个 singleton。表达值不参与聚类、折分配或调参。
- **推断**：primary seed 20261221；20,000 次序列簇 bootstrap（20261321）和 20,000 次簇内成对置换（20261322）；四终点 Holm。其余 seeds 只检验稳定性，不当作独立样本。
- **通过/证伪**：四项主终点及 8/10 方向规则全部满足才通过；任一失败即不支持序列簇运输增量。
- **下一步决策**：通过仅支持固定蛋白序列簇运输，并要求真正独立外部验证；失败则删除稳健运输主张。两种结果均不单独授权生成训练，不证明 velocity、decay 或完整空间耦合。
- **边界**：不读取 functional-untouched；不声称 protein OOD、独立确认、RK-G1 完成或 CodonFlow-RK superiority。
