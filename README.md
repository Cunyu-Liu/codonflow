# CodonFlow

CodonFlow: finite-step synonymous Markov editing for multi-objective CDS design.

> 当前 A7 以 warm-start synonymous CDS editing 为主任务，以 learned proposal 对无学习简单搜索的预算收益为第一决定性关卡。
> 早期条件去噪、immediate-ATC、旧 RLOO 和旧 scaling 结果保留为 legacy exploratory，不进入当前主结论。
> 当前实现与证据边界见 `docs/handover/spec.md`；大空间 short-rollout 仍是近似，不得宣称精确终端分布。

**Spec**：`docs/handover/spec.md`；当前任务：`docs/handover/tasks.md`（P1/G0）。

## 复现入口

```bash
conda env create -f environment.yml      # ViennaRNA 2.6.4 + torch DDP
pip install -e ".[dev,eval]"
pytest tests/                            # 全部单测

python scripts/gpu_queue.py              # GPU 排队守护（60s 轮询）
python scripts/gpu_heartbeat.py          # 30min 心跳采样
```

## A8-RK：MAGE 固定 infA 同义机制 nested-development 复现

本项只复算已用于 v1 的 train+dev 共 131 个 constructs；原 33 个 test constructs 不得进入记录表、fold、特征、拟合、预测或指标。v1 的 `DEV_NO_GO_TEST_UNTOUCHED` 不改写，本项也不是独立确认、功能 untouched、protein OOD 或生成器实验。

```bash
cd /home/codonflow-a8-rk
export PYTHONDONTWRITEBYTECODE=1
PY=/root/miniconda3/bin/python
CFG=configs/a8_rk03_mage_development_nested_cv_protocol_v2.json
A=audits/20261119/RK03

$PY -m unittest scripts.tests.test_a8_rk03_mage_development_nested_cv -v

$PY scripts/a8_rk03_mage_development_nested_cv.py \
  --config "$CFG" --output "$A/mage_development_nested_cv_v2.json"

$PY scripts/a8_rk03_verify_mage_development_nested_cv.py \
  --config "$CFG" \
  --report "$A/mage_development_nested_cv_v2.json" \
  --production-script scripts/a8_rk03_mage_development_nested_cv.py \
  --output "$A/mage_development_nested_cv_independent_v2.json"

$PY scripts/a8_rk03_finalize_mage_development_nested_cv.py \
  --config "$CFG" \
  --production "$A/mage_development_nested_cv_v2.json" \
  --independent "$A/mage_development_nested_cv_independent_v2.json" \
  --output "$A/mage_development_nested_cv_finalization_v2.json"

$PY scripts/a8_rk03_mage_development_verify_paper.py \
  --paper paper/CodonFlow_preprint_A8.md \
  --a7 paper/CodonFlow_preprint_A7.md \
  --sync-audit paper/a8_rk_paper_sync_audit.json \
  --update-record paper/a8_rk03_mage_development_nested_cv_paper_update.json \
  --production "$A/mage_development_nested_cv_v2.json" \
  --independent "$A/mage_development_nested_cv_independent_v2.json" \
  --finalization "$A/mage_development_nested_cv_finalization_v2.json" \
  --output "$A/mage_development_nested_cv_paper_verification_v2.json"

# 核验已写入的在线 PPT 证据（不修改在线稿）
$PY scripts/a8_rk03_verify_mage_development_ppt.py
```

预期验收为 12/12 unit tests、独立 96/96 PASS、finalization 30/30 PASS、论文 54/54 PASS；科学结果为 `DEV_NO_GO_TEST_UNTOUCHED`。大型 OOF/fold 文件由冻结协议写入 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/mage_development_nested_cv_v2/`：`development_oof_predictions.csv`（131 constructs × 3 seeds 的模型预测记录）和 `development_fold_assignments.csv`（393 行）。初次测试路径失败日志与最终日志均保留在 `audits/20261119/RK03/`，不得删除。

MAGE 结果已写入在线主稿第 102 页（`pgj`，revision 64）。候选页写前 **52/52 PASS**，整稿写后 **79/79 PASS**；前 101 页语义 XML 完全不变，新页与候选语义一致。候选、响应、失败调用、整稿 XML 与回读证据位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/ppt_mage_development_nested_cv_v1/`，小型核验报告位于 `audits/20261119/RK03/`。PPT 记录不是新科学实验，不改变 test untouched、RK-G1=false 或 non-submittable 状态。

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
