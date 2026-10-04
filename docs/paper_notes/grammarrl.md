# GrammarRL 精读笔记（spec R3-3 / R5 RL 档依据）

> 来源：arXiv:2609.39869
> 用途：CodonFlow 的免标注 RLOO 配方（双自监督奖励 + 组内强对照）

## 1. 核心公式（Eq (4)-(8)，已逐条核实）

- Eq(4)：direct reward = 长度归一化 log p(y|x)（编辑似然）。
- Eq(5)：reverse reward = teacher-forcing 重建 log p(x|y)。→ CodonFlow 改为翻译循环一致性 1[Trans(y)=Trans(x)]（硬翻译、确定性、免预测器噪声）。
- Eq(6)：r = (1−λ)·R_direct/σ_direct + λ·R_reverse/σ_reverse，λ=0.5。
- Eq(7)：LOO 优势 A⁽ⁱ⁾=r⁽ⁱ⁾−(1/N)Σ_{j≠i}r⁽ʲ⁾；beam 解同权进基线（非模仿目标）。
- Eq(8)：L(θ)=1/(N+1)Σ[−A⁽ⁱ⁾log π_θ + β·Δ⁽ⁱ⁾]，Δ⁽ⁱ⁾=log π_θ−log π_ref（逐序列 log-lik 差线性惩罚，**非严格 KL**）。

## 2. 关键实现细节（决定代码写法）

- 策略梯度用**无约束概率**计算：打分与训练一律无 mask 重归一化。
- 组构造：N=3 采样 + 1 个 beam 解混入（B=3 beam 对应物）→ CodonFlow 混入 LinearDesign/CAI-greedy 解。
- 温度 1.0。

## 3. 超参（附录 Table 5，实测值）

- LoRA r=64 / α=128 / dropout 0.05。
- β=0.02（冻结正则）。
- λ=0.5 等权（消融确认唯一稳定配置）。
- lr 3.3e-7 ~ 7e-7。
- 1000 步起步（≈2 epochs）。
- 硬件：1×H100 5-18h。
- σ 校准：100 个 held-out 输入的组内标准差平均。

## 4. 消融（WoS 1B，迁移验证目标）

- direct-only：−9.6 分（低于基线）；reverse-only：−7.5 分——**单奖励反噬**。
- λ=0.5 等权是全设置唯一稳定配置 → 双奖励必须等权起步。
- 1/3 未胜 beam 的任务是 CoNLL（8B 上差 −7.0 分）：短序列、结构化抽取任务上训练期塑形不如推理期搜索 → CodonFlow 保留 beam/MCTS 对照组（CDS 短、强结构，同样风险）。
