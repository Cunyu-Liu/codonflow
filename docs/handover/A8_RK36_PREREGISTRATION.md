# A8-RK36 预注册卡 · 独立运输数据可行性审计（label-free）

## 背景与指令
交接提示词 §三/§四 明令：RK34 是同队列窗口消融终点，之后不得继续在 Kudla/Mordstein 切窗；RK35 起必须走向独立验证或转向。RK34（并行）确认联合精确起始上下文增量但不可分离上游/起始；RK35（本会话）确认自然截短窗在 Kudla 内仍携带增量（覆盖非必要）。据此触发 §四 分支 1（寻求真正独立、完整 CDS、明确蛋白身份、可重建同一精确起始窗的功能数据做运输预注册）。本任务执行 §四  mandated 的第一步：**在读结局前冻结、label-free 审计可用公开数据能否支撑严格独立运输实验**；若不存在合格数据，按 §四 分支 3 记录 feasibility 与缺失维度，并正式触发分支 2 转向。

## 科学问题
是否存在一个独立于 Kudla 训练队列的公开功能数据集，能重建与 Kudla 相同的精确天然起始窗 `UTR[-4:]+CDS[:38]`（42 nt，dangles=2，37°C），用于预注册的同义起始结构运输实验？

## 合格要求（冻结，R1–R7）
- R1 独立性：研究/宿主独立于 Kudla 训练队列（非同一 GFP 队列）。
- R2 完整 CDS：每个变体提供完整 CDS。
- R3 天然 5'UTR：提供变体特异的天然 5'UTR（ATG 上游 ≥4 nt），可精确重建 `UTR[-4:]+CDS[:38]`，构建几何与 Kudla 一致（固定载体 leader 替代不算）。
- R4 同义库：固定蛋白的同义密码子库（机制是同义选择影响起始结构；跨蛋白天然非 synonymous 池不能检验）。
- R5 蛋白身份：明确蛋白身份 + family 映射，可做蛋白/研究 OOD 隔离。
- R6 新鲜连续结局：连续表达/适合度结局，动态范围充足（粗 ordinal 评分不算）。
- R7 可隔离与溯源：序列簇/蛋白/研究隔离可行；license/accession/raw SHA 可文档化。

## 判定规则（冻结）
- 某数据集合格 ⟺ R1–R7 全 PASS。
- 若 ≥1 数据集合格 → 分支 1：起草严格运输预注册（数据/完整 CDS-UTR/宿主-assay-batch/结构定义/清洗/动态范围/隔离/simple-full-proxy-最强外部 baseline/主终点/整簇统计/Holm/功效/三结论）。
- 若 0 数据集合格 → 分支 3：记录每个数据集的失败要求与缺失维度；正式触发分支 2 转向（停止把 start-aware MFE 当核心模型创新，转向有数据支持的功能序列模型/翻译动力学，强 baseline + OOD + SOTA 判据）。
- 严禁：用宿主/assay/覆盖全不同的数据集假装回答；为获阳性读取 functional untouched（MAGE 19,072 行冻结）；启动生成训练（RK-G1=false）。

## 审计对象与源（label-free，仅读 schema/覆盖/身份元数据，不算结局效应）
- 统一长表 `/teams/.../rk_functional/clean/functional_long.csv`（25,420 行/31 列）。
- Kudla 源 `/teams/.../rk21/kudla_recovery_v1/derived/kudla154_source.csv`（训练队列对照）。
- Boël 源 `/teams/.../rk_functional/clean/boel_2016_nesg6348/sequence_expression.csv`（6,348 行）。
- Mordstein RK28 `/teams/.../rk28/mordstein_observed_r1_sequence_cluster_ood_v1/sequence_cluster_facts.csv`（152 变体）。
- MAGE/Kelsic：统一长表 infA 19,072 行（冻结，仅读 sequence_status 元数据，禁读结局）。

## 边界
本审计是可行性/数据资格判定，不是运输效应实验；不产生 SOTA/机制成立主张；不读 functional untouched 结局；不启动生成训练。结论决定后续分支。