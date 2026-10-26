# CodonFlow

CodonFlow: finite-step synonymous Markov editing for multi-objective CDS design.

> 当前 A6 验证版实现联合同义跳转核、短 rollout Doob 近似和 path-level RLOO。
> 早期条件去噪与 immediate-ATC 结果保留为 legacy exploratory，不等同于完整 CTMC Edit Flow。
> 当前实现与证据边界见 `docs/handover/spec.md` Amendment A6；不要按旧描述宣称精确终端分布。

**Spec**：`docs/handover/spec.md`；当前任务：`docs/handover/tasks.md` v7。

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
  models/      条件去噪主干、有限步同义 Markov 编辑器、短 rollout 引导
  gating/      ATC 效用与终端 feasibility 检查
  scorers/     CAI/RNAfold/翻译一致性指标
  rl/          路径级 RLOO 与 squared log-ratio trust penalty
  eval/        指标（CAI/MFE/NED/hypervolume）、停止条件断言
scripts/       gpu_queue、gpu_heartbeat、数据管线、基线
experiments/   REGISTRY.md（逐 run 登记，schema 冻结）
docs/          paper_notes / training_journal / data_audit / gates
```

## 纪律（spec R6）

- 单卡真实任务并行；训练到独立验证集 plateau（连续 3 epoch 相对下降 <0.1%），保存验证最优与完整恢复状态
- REGISTRY.md 逐 run 登记；代码在 `/home/codonflow`，大产物只进 `/teams/HoulabData_1788502323/liucunyu/codonflow`
- 停止条件五条已代码化（`src/codonflow/eval/stop_checks.py`）
