# pCoMole 精读笔记（spec R2/R3/R5 依据）

> 来源：arXiv:2610.01663（NeurIPS 2026）；代码 https://huggingface.co/ChatterjeeLab/pCoMole（已核实开源）
> 用途：CodonFlow 的基座方法（Edit Flow + 门控终端分布 + Doob-h 倾斜）

## 1. 核心公式（已逐条核实）

- 式(3)-(6)：Edit Flow 损失。总出度惩罚 + 对齐隐含编辑 log 速率提升。
- 式(9)：G(x)=exp(β·ATC(x))·𝕀[x∈𝓕] —— 可行终端零质量（by-construction 约束）。
- 式(11)-(12)：Doob-h 变换 u^G_t(y|x)=u_t(y|x)·h_t(y)/h_t(x)；命题 3.1 保证终端分布精确等于 G。
- 式(13)-(15)：调和函数近似——C 个候选 × R 条短 rollout，h 的估计用经验平均。
- 附录 B 式(16)-(20)：log-domain 实现；log ĥ 用 logsumexp；候选选择 s_c=log u_t(y_c|x_t)+log ĥ_t(y_c) 稳定 softmax。

## 2. 超参（附录 E.3 / H，实测值）

- 模型：768 dim / 8 层 / 12 头（蛋白侧接 ESM，mRNA 侧可从头训）。
- 优化：AdamW lr=1e-5，wd=0.03，cosine 衰减至 1e-6，warm-up 10 epochs；UniRef_S 30 epochs。
- 推断：步数 10-30、候选 C=10-30、rollout R=5-10（中间档即可，边际递减）。
- GFP 收缩预算：10 步 × 50 候选 × 10 rollout，单序列 530s@50 步（成本上限锚点）。
- Cas9 用 20 步 × 10 候选 × 5 rollout。
- 长度扰动初始化：|x₀|~U[(1−a)|x₁|,(1+a)|x₁|]。

## 3. 迁移到 CodonFlow 的要点

- mRNA CDS 同义编辑为定长任务（a=0），成本预期低于蛋白收缩。
- 词表 64 密码子 + 特殊 token（67），密码子语义简单，embedding 从头训。
- 消融启示：GFP 中间档预算已饱和 → 推断预算网格 steps{10,20,30}×C{10,30}×R{5,10}。

## 4. 差异化（防「工程组合」质疑）

pCoMole 在蛋白侧、评分器全为预测器；CodonFlow 新增：密码子级词表 + 同义身份硬约束原生进离散流终端分布（首个）+ 翻译循环一致性 reverse reward（首个，确定性免预测器）。
