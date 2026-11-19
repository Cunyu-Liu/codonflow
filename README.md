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

## A8-RK：Ribo/VeloHARMO 来源可行性（metadata-only）

本项只审计官方 PMC/GEO/SRA RunInfo 元数据与固定 VeloHARMO 发布树，不下载 FASTQ/BAM/SRA，不构建 UTR–CDS，不执行 raw-read/P-site 重比对、模型训练或模型评价。`size_MB` 是公开归档元数据之和，不是本轮下载量；公开 raw source 或 GA checkpoint 不等于已发布 harmonized matrix。

```bash
cd /home/codonflow-a8-rk
export PYTHONDONTWRITEBYTECODE=1
PY=/root/miniconda3/bin/python
A=audits/20261120/RK03

$PY -m unittest scripts.tests.test_a8_rk03_source_feasibility -v

$PY scripts/a8_rk03_source_feasibility.py \
  --protocol configs/a8_rk03_source_feasibility_protocol_v1.json \
  --output "$A/source_feasibility_v1.json"

# 离线独立复核与 finalization 使用协议中的冻结路径
$PY scripts/a8_rk03_verify_source_feasibility.py
$PY scripts/a8_rk03_finalize_source_feasibility.py

$PY scripts/a8_rk03_source_feasibility_verify_paper.py \
  --paper paper/CodonFlow_preprint_A8.md \
  --a7 paper/CodonFlow_preprint_A7.md \
  --sync-audit paper/a8_rk_paper_sync_audit.json \
  --update-record paper/a8_rk03_source_feasibility_paper_update.json \
  --production "$A/source_feasibility_v1.json" \
  --independent "$A/source_feasibility_independent_v1.json" \
  --finalization "$A/source_feasibility_finalization_v1.json" \
  --output "$A/source_feasibility_paper_verification_v27.json"

# 文档/registry 收尾核验；不访问网络，不修改在线 PPT
$PY scripts/a8_rk03_verify_source_feasibility_closeout.py
```

预期验收为 14/14 unit tests、生产 **74/74 PASS**、离线独立复核 **169/169 PASS**（production-versus-independent 最大数值差 0）、finalization **47/47 PASS**、论文 **61/61 PASS**（候选事实 30/30）。终态为 `SOURCE_METADATA_RECOVERABLE_REMAP_NOT_PERFORMED` / `PUBLIC_SOURCE_RECOVERY_FEASIBLE_BUT_NOT_REMAPPED`。五个 VeloHARMO 来源合计 125 runs、143,663 MB；RiboMIMO 额外两项来源合计 13 runs、9,236 MB；七个不同 RunInfo accession 合计 138 runs、152,899 MB。固定发布树含 14 个文件，仅含 E. coli harmonized matrix，以及 E. coli/yeast GA checkpoints。

A8 v27 SHA256=`c745b3e73b7d9f380f7c0ce326cc5fba2cfae769273b2e58f606a73dba9e0952`，仍是 non-submittable working manuscript；v26 可按更新记录逐字恢复。官方 raw 响应和大型 PPT XML 分别归档于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/source_feasibility_v1/` 与 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/ppt_source_feasibility_v1/`。初次错误仓库/映射、blob 计数、finalization 日志断言和 PPT 默认属性差异的失败报告均保留在 `audits/20261120/RK03/`。

结果已写入在线主稿第 103 页（`pgM`，revision 65）：写前 **35/35 PASS**，整稿写后 **47/47 PASS**，前 102 页语义 XML 全部不变。写后规范化只允许服务端显式化 `col@span=1` 和分配 ID；首次 46/47 失败报告保留。该 bounded 子任务已闭合，但不关闭四物种 harmonization、自然分布报告、机制效度、RK-G1、生成训练授权或 manuscript submittability。

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
