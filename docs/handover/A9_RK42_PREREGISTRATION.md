# A9-RK42 预注册卡 · 独立数据获取审计（公开优先，标签无关）

日期：2026-11-22（UTC+8）
权威工作树：`/home/codonflow-a8-rk`，分支 `a8-rk`。
执行依据：`docs/handover/PROMPT_NEXT_AGENT_A9_RK37.md` §四（阶段 B）+ `configs/a9_positive_core_directive_v1.json`（`independent_data_mandate`）。
性质：**标签无关获取审计**。在读取任何新结局/拟合任何模型之前冻结合格要求 R1–R7、候选清单与判定规则。本卡不预设阳性或阴性终点。

## 1. 科学问题

RK36 已证明现有 4 项资产 0/4 合格独立数据。A9 阳性核心必须建立在**新的合格独立数据**上。本任务回答：在公开 construct 级同义/表达数据中，是否存在满足 R1–R7 的合格独立数据，可作为 CodonFlow 生成/功能模型公平击败最强 baseline 的验证基础？

## 2. 合格要求 R1–R7（沿用 RK36 冻结定义，不放宽）

- **R1** 独立研究/宿主（非 Kudla 训练队列）。
- **R2** 每变体完整 CDS（非仅 N 端片段/报告融合）。
- **R3** 变体特异天然 5'UTR（ATG 上游 ≥4nt），可精确重建 `UTR[-4:]+CDS[:38]` 同构建几何；固定载体/合成 leader 替代不算。
- **R4** 固定蛋白同义库（氨基酸不变；跨蛋白天然非 synonymous 池、氨基酸级设计因子均不算）。
- **R5** 蛋白身份 + family 映射，可做蛋白/研究 OOD。
- **R6** 新鲜连续结局，动态范围充足（粗 ordinal 不算）。
- **R7** 序列簇/蛋白/研究隔离可行 + license/accession/raw SHA 可文档化。

合格 ⟺ R1–R7 全 PASS。

## 3. 候选清单（公开优先，逐源 raw 核实，不得只看摘要/clean 表）

Cambray2018、Kosuri2013、Goodman2013、Mutalik2013、Rhodius2012、Salis2011、EspahBorujeni2014_2017、deBoer2020、Lind2020。

## 4. 判定规则（冻结）

- ≥1 合格 → 阶段 B2：acquire raw → clean → 全量 SHA → 预注册划分（蛋白/研究/簇 OOD，同一蛋白变体不得随机跨 split）→ 泄漏审计 → 动态范围审计 → 进入阶段 C。
- 0 合格 → 阶段 B3：记录缺失维度 + 设计前瞻 DBTL/湿实验（固定蛋白同义库 + 天然完整 UTR–CDS + 连续表达/适应度 + 独立宿主），**湿实验预算与延期须用户批准**；测量协议在读结局前预注册冻结。
- 任何源 raw 不可获取须记录真实原因（paywall/Cloudflare/限速/无 accession），不得从摘要猜数值；raw 未核实者不得判 PASS。
- 战略选项（须用户裁决，不擅自放宽冻结 R1–R7）：是否为*功能 benchmark*单独授权放宽 R3（接受固定 leader + N 端同义编辑窗），同时仅对起始结构运输主张保留严格 R3。

## 5. 边界

- 历史 MAGE functional untouched（19072 行/13569 组）仍冻结禁读；历史冻结协议/结果不追改。
- 本审计无模型拟合、无结局关联、无生成训练；RK-G1=true 仅授权后续阶段 C，不在本审计内训练。
- 公开回顾验证与前瞻 DBTL 严格分开；无真实前瞻实验不写疗效/免疫原性/普遍表达提升。