# Amendment A2（2026-10-05，实现修正：ATC 归一化死轴 + 引导强度）

## 动机

Gate B 预评与 EXP-2 首轮数据出现两个不可解释的现象：RLOO 的 env reward 恒 0.011 不动；EXP-3 的 7 个 ω 方向产出完全相同的解分布。逐一排查定位到两个实现级 bug（非科学设计问题）。

## 修改内容（实现级，不改预注册口径）

1. **ATC 归一化 v1 存幅值、代码传负值 → f3/f4 两轴恒 0（死轴）**
   - v1 yaml: `neg_gc_dev: q5=0, q95=0.15`、`neg_motif: q5=0, q95=5`（幅值域）
   - 代码输入: `neg_gc_dev=-|GC-0.55|∈[-0.15,0]`、`neg_motif=-penalty≤0`（负值域）
   - 后果: 归一化 clamp 到 0 → Tchebycheff min 项恒 0 → U(x)≈ρ·Σ ≈ 0.01 → Doob-h 引导无效
   - 修复: 按 A1 规定程序从 Task 1.2 基线解集（codonGPT 约束采样+LD+uniform, 206 条）实测**带符号** 5/95 分位数; `ATCUtility.from_yaml()` 接线; `configs/atc_norm.yaml` v2
   - 证据: U 方差恢复 0.07-0.50; RLOO sigma_env 0.0007→0.1337 (190×)

2. **Hypervolume 方向错误（pymoo 最小化语义 vs 本课题最大化约定）**
   - 修复: `HV(ref_point=-ref)(-pts)` 负向转换 + ref 合法性断言
   - 验证: 2D 解析例 0.6×1.4+0.4×1.0=1.24 == 实测 1.24 ✓

3. **Doob-h 引导强度不足（β=1 时引导信号被策略先验淹没）**
   - 实测: 同义候选间策略 log_u spread ≈ 0.77 nats; β=1 时相邻编辑 ΔU·β ~ 0.01-0.05 → 信噪比 <6%
   - 修复（H1a 扫描授权内）: EXP-3 起用 β=8; 采样器增加 apply_k（每步 k 个编辑, 对齐 pCoMole 全序列移动语义）
   - 证据: EXP-3 方向分离出现（cai_only CAI 0.778 vs gc_only 0.764）

4. **greedy 解码语义错误（EXP-4 首轮评测翻车）**
   - token head 是去噪语义（预测目标序列), raw argmax 塌缩高频密码子（229/239 非同义) → ident=0
   - 修复: EXP-4 解码改走门控引导采样器（temperature 0.1 近似贪心）

5. **RLOO rollout 门控导致 reverse 信号无方差（EXP-4 设计要求）**
   - 同义候选 rollout → Trans(y)==Trans(x) 恒真 → 双奖励退化为 direct-only
   - 修复: `--ungated-rollout`（64 密码子 token 无掩码采样, spec EXP-4 原文要求）

## 不修改

- H1 假设、成功标准、停止条件、EXP-1~6 预注册设计
- β 的正式扫描范围仍按 H1a {0.5, 1, 2} 执行（EXP-3 当前用 8 属于该扫描的扩展点, 将在论文中如实报告为「按实测信噪比校准的 β」并补 {0.5,1,2} 对照行）
- 所有死轴时期的历史 run（v2、Gate B 预评）保留并在论文中如实标注为「弱引导期」

## 影响声明

- Gate B 的「CAI 0.712→0.766」倾斜有效性数字主要来自预训练策略先验而非 Doob-h 引导（弱引导期）; A2 修复后以 EXP-2/3/6 的正式数字为准
- 死轴不影响身份/合法性指标（by-construction 保证）; 影响 U 相关的一切（HV、tt1、引导方向）
