# CodonFlow

Feasibility-Gated Codon-level Discrete Flow mRNA Editor + Label-free Bi-Reward RLOO.

> 密码子级离散流 mRNA 编辑器：把「蛋白身份 + 阅读框 + 终止密码子唯一」写进离散流的
> 可行性门控终端分布（by construction），多目标偏好用 Doob-h 倾斜塑形，
> 免标注双自监督奖励（direct=编辑似然 + reverse=翻译循环一致性）做 RLOO 微调。

**Spec**：见交接文档 `spec.md`（含 Amendment A1 归一化细节）；本仓库为独立课题，
不与 mRNA_editflow 共享 git 历史。

## 复现入口

```bash
conda env create -f environment.yml      # ViennaRNA 2.6.4 + torch DDP
pip install -e ".[dev,eval]"
pytest tests/                            # 全部单测

python scripts/gpu_queue.py              # GPU 排队守护（60s 轮询）
python scripts/gpu_heartbeat.py          # 30min 心跳采样
```

## 目录

```
src/codonflow/
  core/        密码子表、tokenizer(67)、motif 目录、硬约束 F
  data/        FASTA 读取、CDS 清洗、MMseqs2 聚类切分、数据集
  models/      Edit Flow 主干、Doob-h 引导采样
  gating/      ATC 效用（A1 归一化）、门控终端分布权重
  scorers/     三足评分器（CAI/RNAfold/翻译一致性，零学习）+ LRU 缓存
  rl/          RLOO 双奖励（GrammarRL Eq(4)-(8)）
  eval/        指标（CAI/MFE/NED/hypervolume）、停止条件断言
scripts/       gpu_queue、gpu_heartbeat、数据管线、基线
experiments/   REGISTRY.md（逐 run 登记，schema 冻结）
docs/          paper_notes / training_journal / data_audit / gates
```

## 纪律（spec R6）

- GPU 并行占满显存；训练到收敛（预训练：验证损失连续 3 epoch 相对下降 <0.1%）
- REGISTRY.md 逐 run 登记；大产物只进 `/mnt/cunyuliu/codonflow/`
- 停止条件五条已代码化（`src/codonflow/eval/stop_checks.py`）
