# A8-RK27 Closeout：固定 GFP 序列簇 OOD 的 5′ MFE 增量

## 结论

**FIXED_PROTEIN_SEQUENCE_CLUSTER_OOD_MFE_INCREMENT_SUPPORTED_RETROSPECTIVELY**。

在 Kudla 固定 GFP 的 150 条唯一 exact CDS 上，measured 5′ MFE 相对 CAI、CDS GC、CDS GC3 的增量通过冻结的序列簇 OOD 评价：ridge 与 HistGB 的 Spearman/MSE 四个主终点全部通过，且每项在 10/10 个折分配 seeds 上方向为正。独立实现完成 47/47 PASS。

这只是**回顾性固定蛋白序列簇运输证据**。同一批标签曾用于 RK22 development；本实验不是独立 untouched 确认、不是 protein OOD，不测量 velocity 或 decay，不建立完整空间耦合，不证明 CodonFlow-RK superiority。RK-G1 仍为 false，生成训练未授权。下一步应是真正独立的外部固定蛋白功能验证，而不是生成训练。

## 冻结设计与样本链

- 预注册/覆盖提交：`93c61258cabb4a3da5f7d788ea8d9087c9ae5630`。
- 科学与独立复验提交：`8a62836bb73b34bcae529bae6a21f6e3eefc85d1`。
- 输入：Kudla 154 measurement rows → 150 exact-CDS groups → 同一 GFP 蛋白。
- 只使用 CDS/注释的覆盖审计：90% complete-linkage；37 clusters；最大簇 61；13 singleton clusters。
- primary seed=20261221；10 seeds × 5 folds；每折整簇隔离，特征缩放仅在训练折拟合。
- simple=CAI+CDS GC+CDS GC3；structure=simple+measured 5′ MFE；MFE-only 仅描述。
- 300 次真实 CPU 模型拟合；primary 20,000 次序列簇 bootstrap（seed=20261321）与 20,000 次簇内 simple/structure 成对置换（seed=20261322）；四终点 Holm。
- 大型 artifacts：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk27/kudla_sequence_cluster_ood_v1/`。

## 主结果

正方向均 favors adding measured 5′ MFE；MSE improvement=simple−structure。

| Endpoint | Observed effect | 95% cluster-bootstrap CI | Holm p | Positive seeds | Gate |
|---|---:|---:|---:|---:|---|
| ridge ΔSpearman | 0.955051 | [0.493814, 1.106833] | 0.00019999 | 10/10 | PASS |
| ridge MSE improvement | 0.157489 | [0.071313, 0.212686] | 0.00129994 | 10/10 | PASS |
| HistGB ΔSpearman | 0.412578 | [0.208828, 0.520318] | 0.00044998 | 10/10 | PASS |
| HistGB MSE improvement | 0.105907 | [0.042279, 0.140561] | 0.00129994 | 10/10 | PASS |

Primary-seed absolute OOD performance：

| Model | Simple Spearman / MSE | Structure Spearman / MSE | MFE-only Spearman / MSE |
|---|---|---|---|
| ridge | −0.318413 / 0.257149 | 0.636638 / 0.099660 | 0.605020 / 0.111354 |
| HistGB | 0.302424 / 0.198658 | 0.715002 / 0.092751 | 0.637557 / 0.101574 |

MFE-only 是描述性参照；本实验的确认性比较仍是 structure 对 simple，并未把“组合模型必须击败 MFE-only”偷换成额外 Gate。

## 独立验收与执行记录

- 生产/覆盖合成测试：14/14 PASS；独立实现合成测试：8/8 PASS。
- 独立实现未 import 生产或覆盖模块；从原始 CDS 重新聚类、聚合、拟合全部模型并重跑全部 resampling。
- 47/47 PASS：150 条聚合、1,500 行折分配与预测、40 个 seed effects、50 行训练日志、20,000 次 bootstrap/置换数组及四终点一致。
- 初次独立报告 46/47：唯一失败为 CSV 字面量 `null` 被默认读成缺失值，合并指标表时丢失 10 行；两份指标表实际均为 70 行。只修复验收器 `keep_default_na=False`，初始失败报告保留，科学结果未改。
- 初次生产运行因 46 线程低效，在预测表生成前中止；五次单线程 HistGB benchmark=0.4717438220977783 秒。使用单线程重启同一冻结协议；无结果被用于决策，中止记录保留。
- 生产结果 SHA256=`b601db3b0a5bec6b228492846f0058a0d959439c0eeebada05b749daa366ed5e`。
- 独立报告 SHA256=`1e657146110a553071b169578839cbd0c45e357d9d4ff32394f297848d2df5f4`。

## 下一步

1. 将本结果作为固定蛋白序列簇运输的正面机制证据写入研究记录，并显式保留回顾性边界。
2. 优先寻找/冻结一个真正独立、未参与模型或特征开发的固定蛋白功能数据集，再评价同一预注册增量。
3. 在独立外部确认、完整功能机制和强 baseline 闭环之前，不启动昂贵生成训练，不宣告 RK-G1 完成。
