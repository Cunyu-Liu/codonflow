# CodonFlow RUNBOOK（A7 · 按科学门执行）

> 生效日期：2026-11-01。与 `spec.md`、`tasks.md`、`checklist.md` 配套。
> 当前动作：**G0 已通过；两条 D4 r3 正在 CUDA 并行训练，尚未收敛或通过 G1。development calibration 18/18 已验收，G2 工具正在用随机 checkpoint 做接口验证，正式 G2 未启动。**
> 路径纪律：代码与 Git 提交在 `/home/codonflow`；大型数据、权重、日志和 artifacts 在 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/`。

## 0. 立即失效的旧入口

以下内容全部视为历史，禁止复制执行：

- 任何读取 `a6_v4_56m_r2/converged.pt` 或 `a6_v4_56m_fulltoken/converged.pt` 的下游命令；
- 任何把旧 arbitrary-corruption 模型当作有效 base 的三臂、联合 HV 或 RLOO 命令；
- 任何将 `a6_v5_syn_*` 误认为 D5 同源划分训练模型的记录；
- 任何用 per-test-output 动态估计 HV reference/scale 的聚合命令；
- 任何用 random padding 补足 LinearDesign/GEMORNA 等唯一解数的命令。

旧模型只保留作复制退化反例。2026-10-31 的 synonymous 新两臂停在 e1 b800，**无 checkpoint**；未来获授权执行时只能从已冻结的新配置开始，不能声称从 checkpoint 恢复。

## 1. 所有后续 run 的统一前置检查

每次执行前必须依次确认：

1. 用户已授权该实验动作，且当前任务位于 `tasks.md` 允许推进的任务块；
2. 前置 Gate 已通过，证据路径和冻结 JSON 存在；
3. 重新盘点远端进程、GPU、代码路径和数据挂载，不沿用上日“正在运行/已停止”状态；
4. 代码 commit、`code_dirty`、环境、RNAfold 版本和数据 SHA256 已记录；
5. 输出目录不可与历史 run 混写，配置和协议版本不可变；
6. checkpoint 使用不可变路径和 SHA256，禁止 live `best.pt`；
7. 结果 schema、预算、统计方法和停止规则已在查看结果前冻结。

任一项不满足：不执行，不通过修改旧 JSON 绕过。

## 2. G0 · 数据与协议就绪

### 输入

- D4/D5 划分、原始来源记录、清洗管线和既往 benchmark 清单；
- 当前 spec §4–§6 与 tasks P1。

### 必做产物

1. `data_cleaning_manifest`：逐步过滤数量、原因、哈希和数量守恒；
2. `data_distribution_report`：长度、GC、CAI/RSCU、密码子使用、物种、簇大小与选择偏差；
3. `development_benchmark`：eGFP/nanoLuc + unique18，明确仅用于开发；
4. `confirmation24_d5`：未参与既往实验的 24 个唯一蛋白/CDS，含排除清单和 SHA256；
5. `calibration_protocol`：对应 train 的 CAI/RSCU、独立 HV reference/scale、GC target、motif 与 folding 条件；
6. `simple_search_protocol`：uniform/hill-climbing/MH/AReUReDi-style 的 paired 初始化和预算；
7. `baseline_resource_matrix`：外部方法的版本、输入、代码/权重、复跑与排除状态；
8. `evaluation_schema` + 统计契约测试。

### 通过条件

`checklist.md` C2 全部通过。当前 G0 已通过（`07_a7_data/g0_gate.json`，SHA256=`8b5dbeea278c31792fb1a6107539c223cb9031a821d7152aee5f7e25d0ea136b`），不得把 G0 通过解释为模型有效。

## 3. G1 · 模型收敛且非退化

### 训练规则

- 仅使用 G0 冻结的 D4 开发配置和 synonymous corruption；模型名使用 `M_SYN_D4_*`。
- 保存 best/last/training_state/converged、完整配置和哈希。
- 独立 val 连续 3 epoch 相对改善 <0.1% 才允许写 converged；plateau 本身不代表可下游评测。
- full-token 与 edited-token 的 val 不直接比大小。

### 行为验收

在至少 3 个开发基因上，每基因 100 个 paired 样本：

- identity/legal = 100%；
- 至少 95% 输出不同于初始序列；
- 至少 80 个唯一终端序列；
- 最大单一终端序列频率不超过 20%；
- stay-p、P(edit)、位置覆盖、奖励响应和 uniform 逐串重合全部入档。

这些是排除明显退化的操作阈值，不是性能结果。未通过则回到训练/采样状态诊断，禁止进入 G2。

## 4. G2 · learned vs 简单搜索

### 方法池

- learned base；
- uniform synonymous；
- greedy/hill-climbing；
- Metropolis-Hastings/annealing；
- AReUReDi-style 同操作符搜索。

### 配对协议

- 同一源 CDS、同一 paired 初始状态、同一终端目标和 scorer/cache；
- 开发集、每基因至少 3 seeds；
- B = 50 / 100 / 500 唯一 terminal scorer evaluations；
- 同时保留真实唯一输出数、forward 和端到端时间，不随机补样。

### 主分析

1. 固定独立参考域的 HV anytime AUC；
2. 原始 Pareto front、逐目标 best-at-budget、non-dominated 指标和长度归一化 NED；
3. 每基因选择最强简单搜索作为对照；
4. 基因级 paired bootstrap 95% CI、Wilcoxon 和 Holm。

### Go/No-Go

必须同时满足 spec G2：中位相对改善 ≥10%、CI 下界 >0、校正后 `p<0.05`、identity/legal=100%、NED 不低于最强简单搜索的 70% 且无塌缩。

No-Go 时：停止 short-rollout 主贡献、RLOO、扩参和 SOTA 写作。不得通过删减简单基线、改变参考域或挑选 seed 使其通过。

## 5. G3 · short-rollout 净收益

仅 G2 Go 后执行：

- 同一冻结 checkpoint，immediate vs short-rollout；
- paired 初始状态、相同预算和终端势函数；
- 同时比较质量、唯一 scorer、forward 和 wall-clock；
- 记录 rollout/candidate 增加时的近似偏差与成本。

只有主终点和时间成本均有正向基因级证据才保留 short-rollout；否则主线使用 immediate，不将短 rollout 写成必要组件。

## 6. G4 · 独立确认与外部边界

### 顺序

1. 在不访问确认集的前提下训练并验收 `M_SYN_D5_*`；
2. 在 untouched 24 基因确认集重复 G2 主对照，禁止调阈值、参考域或统计口径；
3. 加入 LinearDesign、GEMORNA、codonGPT 和最强简单搜索；
4. 可复跑时才加入 mRNAutilus/ProMORNA/mRNA-GPT，否则列入 missing/not-reproduced；
5. natural-source 与 protein-only 初始化分开分析；
6. 按目标数、长度、GC 和预算写优势/失败边界。

D5 只能支持操作定义的同源泛化。确认集一旦被用于调参，原确认资格作废，必须重新建立 untouched 集合并登记 amendment。

## 7. G5 · 论文和主图

- 可先写 Introduction、Method、Evaluation Protocol 和精确小状态机制验证；不得预写学习收益。
- G2 后才写 learned-vs-simple 中心结果；G3 后写 rollout；G4 后写外部边界和 Discussion。
- 中心图为 learned vs 简单搜索的 anytime 质量—成本前沿。
- 每图必须能定位冻结 JSON、代码 commit、数据 SHA256 和 checkpoint SHA256。
- 无湿实验时，不出现表达、稳定性、安全性或疗效宣称。

## 8. 产物与成本最小字段

每个结果至少包含：

- `protocol_version`、`run_id`、`status`、`seed`；
- `source_sha256`、`benchmark_sha256`、`data_split_sha256`；
- `code_commit`、`code_dirty`、环境和配置哈希；
- `checkpoint_path`、`checkpoint_sha256`（无模型方法为 `null`）；
- 原始目标向量、唯一输出数、identity/legal、NED；
- B 网格与 anytime 指标；
- `forward_calls`、`base_state_evaluations`、`rollout_batch_forwards`、`rollout_state_transitions`；
- cache 前终端请求、实际 scorer invocations、唯一 scorer、wall-clock；
- `missing_methods`、`exclusions`、失败/部分运行状态。

官方实现不可见的计数写 `null`，不得写 0 或猜测值。

## 9. 失败与恢复纪律

- OOM、NaN、进程死亡、部分输出全部保留；不得将退出码或文件存在解释为科学成功。
- 无 training_state/checkpoint 时不得声称精确恢复；必要时从零开始并新建不可变 run ID。
- 失败 run 不覆盖原目录；恢复时核对 protocol/source/benchmark/checkpoint 哈希。
- 不为占满 GPU 制造任务，不并行跳过科学门，不删除负结果。

## 10. 当前唯一下一步

先读 `HANDOFF_A7_20261112.md` 和 `PROMPT_NEXT_AGENT_A7.md`。当前完整回归为 **178 passed, 1 skipped**，Git 工作副本为 `/home/codonflow`，最新提交以 journal 和 GitHub 为准。

G0 已通过；unique18 三 seed、25 物种来源、24 个 D5 calibration 和18个 D4 development calibration 均已验收。当前只推进 D4 r3 收敛与 G1。收敛后先运行 `a7_convergence_audit.py`，再对两臂分别运行 `a7_g1_behavior.py`。G1 全部通过后才启动 G2；G2 必须使用全局 uniform、 paired 初始状态和 `a7_g2_gate.py` 完整裁决。

独立 MFE/NED 复算入口（seeds 1/2 生成完成后运行；只读原结果，缺少 ViennaRNA 时必须失败）：

```bash
cd /home/codonflow
R=/teams/HoulabData_1788502323/liucunyu/codonflow1031
LEGACY=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow
PYTHONPATH=src /root/miniconda3/envs/codonflow/bin/python \
  scripts/a7_recompute_unique18.py \
  --input-dir $LEGACY/eval_outputs/a6_baselines/unique18_s0 \
  --benchmark-fasta $LEGACY/corpora/a6_benchmark/unique18.fasta \
  --rscu-json $R/01_code/codonflow/configs/cai_ref_v4train.json \
  --seeds 0 1 2 \
  --out $R/07_a7_data/unique18_independent_mfe_ned.json
```

若实际 seed 目录按 `unique18_s1`/`unique18_s2` 分目录保存，须分别复算并在汇总 manifest 中合并，不能假设所有 seed 都在 `unique18_s0`。

G0 最终统一裁决（所有输入存在后运行；任一检查失败退出码为 1）：

```bash
cd /home/codonflow
R=/teams/HoulabData_1788502323/liucunyu/codonflow1031
PYTHONPATH=src /root/miniconda3/envs/codonflow/bin/python \
  scripts/a7_g0_gate.py \
  --full-audit $R/07_a7_data/full_audits_20261112_v2/manifest.json \
  --frozen-assets $R/07_a7_data/frozen_asset_verification_20261112.json \
  --source-manifest $R/07_a7_data/raw_release112/manifest.json \
  --unique-audit $R/07_a7_data/unique18_seed0_independent_mfe_ned.json \
  --unique-audit $R/07_a7_data/unique18_seed1_independent_mfe_ned.json \
  --unique-audit $R/07_a7_data/unique18_seed2_independent_mfe_ned.json \
  --cuda-evidence $R/07_a7_data/cuda_evidence_px2.json \
  --registry /home/codonflow/configs/a7_source_recovery.json \
  --out $R/07_a7_data/g0_gate.json
```

`g0_gate.json` 的 `passed=true` 是唯一允许启动 `M_SYN_D4_*` 的 G0 放行证据；不得以单项完成记录替代。
