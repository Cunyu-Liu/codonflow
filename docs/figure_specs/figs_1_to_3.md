# Figure specs v2（2026-10-26/27 · A6 证据修复版）

> 下方 v1 为历史方案，不再作为当前图的验收依据。图标题必须陈述数据支持的结论，不得用图形美观掩盖协议问题。

## 当前主图规范

### Fig-1 数据与测量协议

- Panel A：v3 输入 vs 精确 CDS/蛋白去重数量；Panel B：各 split 长度/GC 分布。
- Panel C：train/val/test 的精确 CDS 与蛋白交叉重叠审计，含修复前后对照。
- 所有数字来自同一 `overlap_audit.json` 与冻结 split manifest，禁止手工填数。
- 补充 `fig_a6_split_distributions`：Panel A 全量长度直方图，Panel B 全量 GC 直方图，Panel C train/val/test/benchmark 长度分层组成。输入 SHA256、计数守恒、train/val 与 benchmark 零重叠及 test–benchmark=18 子集关系均经断言核验。
- 当前 benchmark 为 13 short / 2 mid / 3 long；1200nt 属于 long。自然 split 与人工分层不得混作同一随机代表性或逐基因 OOD 证据。

### Fig-2 有限步机制与验证

- Panel A：源 CDS→联合同义跳转核→短 rollout→终端效用→路径更新的机制图。
- Panel B：可枚举小状态上 `q_G(X_T) ∝ q_base(X_T)G(X_T)` 的精确数值验证。
- 标题使用“finite-step synonymous Markov editing”；短 rollout/候选剪枝标注 approximate，禁止画成已证明的 CTMC 精确采样。
- 成本面板必须分别展示当前状态 base 枚举、rollout 批量 forward、rollout 轨迹、终端请求、实际 scorer invocations 与唯一 scorer；不得把 R 乘入批量 forward，也不得对累计 trace 行再次求和。图注记录冻结 checkpoint 与代码哈希，live `best.pt` 不作为可复现输入。

### Fig-3 学习与基线边界

- 主比较只使用 A6 新协议：真实 DP 解、正确 GEMORNA 输入、identity/legal 全检查、完整方法池联合 HV。
- 同页报告输出解数、唯一 scorer calls、forward 与端到端时间；不把不同成本口径混为一个“同预算”数字。
- immediate 与 short-rollout 是不同推理算法臂；旧 RLOO 与新 path-RLOO 不共享曲线或结论。
- `fig_a6_baseline_objectives`：仅使用独立复核的 core seed-0 五方法，Panel A/B 展示 CAI–MFE 分布，Panel C 展示真实唯一解数，Panel D 展示端到端生成时间（log scale）。明确 identity=1.0、无随机补足、官方 LD/GEMORNA forward 不可得及共享 GPU 时间边界；不添加 CodonFlow 胜负标题。

## 历史图规范存档（v1）

- Fig-1 代理采样不支持 AR masking 的因果结论，最多描述 codon-preference 与多样性的关联；若需 masking 因果，必须同 checkpoint 比较 AR-free 与 AR+synonymous-mask。
- Fig-2 旧 equal-scoring/首达效率图撤回：scorer 计数漏掉 apply_k，首达记录是解序号；旧 filter 胜出也必须保留。
- Fig-3 前沿必须使用全部方法非支配并集，不得只由 CodonFlow 自身 7 个方向构造参考前沿。
- 所有图导出 PDF + 300dpi PNG，统一方法色、无顶右边框、直接标注样本量/seed/不确定性。

## Fig-1 (EXP-1) Baseline preference collapse

- Type: 1×2 panel bar chart (eGFP | nanoLuc), shared style.
- Bars: pairwise NED mean (3 arms: uniform / RSCU-weighted / CAI-greedy),
  colors #3b7dd8 / #d86f3b / #888888, error = 3-seed std (thin black caps).
- Overlaid line (twin axis, green circles dashed): codon entropy (bits).
- Title per panel: gene name + KS p-value (uniform vs RSCU-weighted).
- Bottom annotation: codonGPT mean log-lik for uniform vs RSCU-weighted
  (the AR model prefers the collapsed direction).
- Caption claim: constrained AR preference shrinks synonymous diversity.

## Fig-2 (EXP-2) Gated vs same-budget post-filter

- Type: 1×2 panel grouped bar chart per family.
- Groups (x): gated_guided / uniform+filter(topK) / uniform+filter(all).
- Bars: hypervolume (3-D: CAI, -MFE, -|GC-0.55|), ref point
  (0.5, 100, -0.2); error = 3-seed std.
- Overlaid markers (right axis): feasible rate (diamonds), time-to-first-
  usable (inverted triangles, normalized 0-1).
- Annotation: Wilcoxon p-value gated vs filter topK (paired, n=6).
- Caption claim: under equal scoring budget the gated terminal
  distribution converts budget into feasible quality faster.

## Fig-3 (EXP-3) Preference scan

- Type: 2 scatter panels (CAI vs -MFE; CAI vs -|GC-0.55|).
- 7 direction clusters (colored, marker per direction; corner directions
  annotated at edges).
- Reference front: non-dominated union of all methods (black step line).
- Per-cluster non-dominated share in legend.
- Caption claim: Doob-h preference shaping spans the Pareto front.

Frozen 2026-10-05 (A2 state: ATC v2 normalization, hypervolume
maximization convention). Any change = amendment.
