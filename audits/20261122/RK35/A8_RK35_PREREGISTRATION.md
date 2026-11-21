# A8-RK35 预注册：RK33 自然窗口覆盖运输检验（Kudla 冻结队列，回顾性）

日期：2026-11-22（UTC+8）
状态：FROZEN_BEFORE_RK35_EXPRESSION_ASSOCIATION_OR_MODEL_FIT（协议 JSON 冻结后生效）
性质：retrospective_outcome_known_followup_not_independent_confirmation（Kudla log10 表达结局自 RK27 起已公开使用；本实验不构成独立确认）

## 0. 与并行 RK34 的分工（重要）

并行执行者会话已冻结其 **RK34**（`audits/20261121/RK34/`，matched start-and-upstream context ablation）：用固定 CDS4–38 body 的 N-mask 因子设计（exact_real / start_only / upstream_only / neither）干净分解「上游 4nt」与「起始 ATG」各自的贡献。该设计**不能**表示真实的 RK33 切片（CDS4–45，body 位移到 4..45）或真实 CDS-start 窗口。

**RK35（本实验）互补**：在**同一冻结 Kudla 队列**上检验**自然（未掩码）窗口**——
- 真实 RK33 窗口 CDS[3:45]（1-based CDS4–45，无起始 ATG、无上游 UTR）在 Kudla 内是否仍携带 RK32 局部结构增量？
- 精确起始覆盖窗口是否优于该 RK33 窗口？

这直接回答「RK28/RK33 跨研究阴性究竟源于覆盖缺失还是宿主/assay」这一运输问题。RK35 的次要对比（atg_vs_trunc、exact_vs_atg）因窗口 body 位移而混杂，**仅描述性**；任何干净的上游/起始分解一律交给 RK34，RK35 不做分解性机制声称。

## 1. 数据与队列（全部冻结输入，SHA 门禁）

- 主表：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk21/kudla_recovery_v1/derived/kudla154_source.csv`（154 测量行 → 150 exact-CDS 组，4 个多测量组；target=组内 log10_expression 均值；CAI 组内常数）。
- 簇事实：RK27 `sequence_cluster_facts.csv`（37 簇，SHA 由 RK27 覆盖报告绑定）；覆盖报告 status=PASS_LABEL_FREE_COVERAGE_AUDIT。
- 折：5 折整簇 OOD，seeds 20261221..20261230（主 seed 20261221，主折大小 [23,61,22,22,22] 与 RK27 冻结覆盖一致）；折分配算法与 RK32 逐位相同；每折簇泄漏断言。
- RK32 复用源：protocol_v2 / result_v2 / preflight CSV / oof_predictions.csv / fold_assignments.csv / seed_effects.csv（完整 SHA 写入协议）。

## 2. 臂与特征（禁止事后增删）

| 臂 | 结构特征 | 窗口定义 | 拟合来源 |
|---|---|---|---|
| simple | CAI, gc_cds, gc3_cds | — | 复用 RK32 OOF |
| exact_local | + vienna_exact_local_mfe | UTR[-4:]+CDS[:38]，42nt，d2，37°C | 复用 RK32 vienna_local OOF |
| cds_start_local | + vienna_cds_start_mfe | CDS[0:42]，42nt，含 ATG 无 UTR，d2，37°C | 新拟合（能量取 RK32 preflight local_cds42__dangles2 列） |
| trunc_local | + vienna_trunc_mfe | CDS[3:45]（1-based CDS4–45），42nt，无 ATG 无 UTR，d2，37°C | 新拟合（RK35 preflight 新算） |
| trunc_local_d0 | + vienna_trunc_d0_mfe | 同上窗口，d0，37°C（RK33 预测定义） | 新拟合；**仅次要敏感性** |

模型：ridge（StandardScaler+Ridge alpha=1）与 histgb（lr=0.05, max_iter=200, max_leaf_nodes=7, min_samples_leaf=10, l2=1.0, early_stopping=False, random_state=seed+fold）——与 RK32 完全一致。
拟合账目：新 3 臂×2 模型×50 折=300；复用 2 臂×2 模型×50 折=200；评估合计 500。

## 3. 终点与推断（冻结）

**主确认终点 8 个 = 2 对比 × 2 模型 × 2 指标（Spearman 差、MSE 改善），统一 Holm(8)：**
- C1 trunc_vs_simple（trunc_local − simple）：RK33 覆盖在 Kudla 内是否携带增量。
- C2 exact_vs_trunc（exact_local − trunc_local）：精确起始覆盖是否优于 RK33 覆盖。

推断：主 seed OOF 上 20000 次整簇 bootstrap（seed 20261321，int16 簇索引）+ 20000 次簇内置换（seed 20261322，int8 符号）；percentile 95% CI；plus-one 双侧 p=(1+#{|null|≥|obs|})/20001。
单终点 PASS = effect>0 ∧ CI 下界>0 ∧ Holm p<0.05 ∧ ≥8/10 seeds 正向；对比支持 = 4/4。

**一致性门禁（gate，先于一切解释）**：exact_vs_simple（=RK32 vienna_local 对比）的 observed/CI/raw-p/seed-effects 必须与 RK32 冻结值差 ≤1e-12，且自身 4-test Holm 4/4 通过。失败 → 结论 CONSISTENCY_GATE_FAILED_NOT_EVALUATED，停止科学解释，进入工程审计。

**次要描述性对比（不入主 Holm、不参与判定，own Holm(12) 仅描述）**：atg_vs_trunc、exact_vs_atg（body 位移混杂，分解交给 RK34）、trunc_d0_vs_simple（RK33 d0 预测定义敏感性）。

## 4. 判定树（冻结优先级 gate > D1 > D2 > D3）

- **D1 RK33_COVERAGE_RETAINS_INCREMENT_WITHIN_KUDLA_RETROSPECTIVELY**：C1 4/4 → 自然 RK33 截短覆盖在 Kudla 内仍携带增量；覆盖**非必要**；RK28/RK33 跨研究阴性不能归因覆盖缺失；宿主/assay/研究级因素成为主候选。下一步：寻找跨宿主、全覆盖的公开数据做运输检验；不再在 Kudla 内挖窗口。
- **D2 START_AWARE_COVERAGE_NECESSARY_WITHIN_KUDLA_RETROSPECTIVELY**：C1 失败 ∧ C2 4/4 ∧ gate 过 → 精确起始覆盖优于 RK33 窗口且 RK33 窗口失去增量；起始覆盖为 Kudla 内必要条件（自然窗口证据）；干净上游/起始分解交给 RK34；跨宿主运输仍未证明，宿主因素不可判别。
- **D3 COVERAGE_TRANSPORT_NOT_DISCRIMINATED_RETROSPECTIVELY**：gate 过但 C1、C2 均失败 → 对比水平不可判别（含小效应/功效不足情形），不得声称覆盖必要或非必要。

## 5. 禁止事项与边界

- 禁止事后加特征、改 Gate、重 split、改容差；verifier-only 修复不得改科学值。
- functional untouched（19,072 MAGE 行）冻结不读；生成训练未授权（RK-G1=false 不变）。
- 不声称：独立确认、宿主机制因果、protein OOD、外部 SOTA、生成授权；**不得用 body 混杂的次要对比做干净上游/起始分解**（交给 RK34）。
- 功效说明：37 簇、20000 重采样可检出 RK32 量级的大覆盖效应；<0.2 ΔSpearman 的小效应可能落入 D3，不做功效事后调整。主族收窄到 8 检验（相对早期 16 检验草图）以在 RK34 接管匹配 body 分解后把功效集中到运输问题。

## 6. 流程门禁

label-free preflight（不读任何表达结局列）→ 合成单元测试 → 协议冻结（含全部输入/脚本 SHA）→ **冻结提交后才允许生产拟合** → 独立验证器从原始表全量重算 500 fits + 24 对比推断 → 干净 checkout 复现（CSV 逐字节 + NPZ 精确）→ closeout → 稿件 §6.46 → PPT 追加 → tasks/REGISTRY/HANDOFF → GitHub 推送。