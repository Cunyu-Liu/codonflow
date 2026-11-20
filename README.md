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

## A8-RK：MAGE 既有 OOF 对照补全

本项只读取 nested-development 已冻结的 131 constructs × 3 seeds OOF 预测，不重训、不读取 33 个 mechanism-test constructs。`rcs_only` 含 intrinsic+RCS；outer-train mean 按 fold 仅用该 fold 之外的 development 标签。科学结论是“full 优于 fold-specific train-mean，不等于机制增量”，`DEV_NO_GO_TEST_UNTOUCHED` 不变。

```bash
cd /home/codonflow-a8-rk
export PYTHONDONTWRITEBYTECODE=1
PY=python3  # system Python with NumPy/SciPy; miniconda base lacks NumPy
CFG=configs/a8_rk03_mage_oof_comparator_closure_protocol_v2.json
A=audits/20261120/RK03

$PY -m unittest scripts.tests.test_a8_rk03_mage_oof_comparator_closure -v

$PY scripts/a8_rk03_mage_oof_comparator_closure.py \
  --protocol "$CFG" --output "$A/mage_oof_comparator_closure_v2.json"

$PY scripts/a8_rk03_verify_mage_oof_comparator_closure.py \
  --protocol "$CFG" \
  --production "$A/mage_oof_comparator_closure_v2.json" \
  --output "$A/mage_oof_comparator_closure_independent_v2.json"
```

预期为 **9/9 tests、24/24 independent PASS**，容差 `1e-12`。primary 使用 20,000 construct bootstrap + 20,000 paired permutations，五检验统一 Holm；0 new fits、0 new scorer calls。full−outer-train-mean ΔRMSE=`-0.015370339550445498`，95% CI=`[-0.0259385856740894,-0.005729286631198561]`，Holm p=`0.020748962551872408`；full−RCS 与 RCS−intrinsic 的四项机制检验 Holm p=1。v1 协议技术失败、环境兼容失败和 v2 更正记录均保留，不得删除。

在线主稿第 **104 页 `pgz`、revision 66** 已记录：候选 **20/20 PASS**，写后 **29/29 PASS**，前 103 页 ID/顺序保留，真实截图无裁切、重叠或缺失。构建器与写后核验器为 `scripts/a8_rk03_build_mage_oof_comparator_ppt.py`、`scripts/a8_rk03_verify_mage_oof_comparator_ppt.py`；后者只有在人工检查真实截图后才可传 `--visual-pass true`。小型报告在 `audits/20261120/RK03/`，大型 XML/截图在 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/ppt_mage_oof_comparator_v1/`。初版 29/31 过严备注验收和 verifier-only 更正记录保留。MAGE section 6.25 / A8 v29 已在 RK06 v28 之后完成，论文核验 **61/61 PASS**；当前稿件 SHA256=`be9fcc72f6f5b631de89084457b3011a8c966d677b916924c795753738d6d444`，可重新执行以下只读核验：

```bash
$PY scripts/a8_rk03_verify_mage_oof_comparator_paper.py --root /home/codonflow-a8-rk
```

## RK06 unique18 dense production 复现与边界

正式矩阵为 18 records × 3 seeds × 4 methods × `B=1…500`，共 **216 runs / 108,000 unique synonymous scorer calls**。dense AUC 是 `B=1…499` 的 HV 算术平均，B500 只作端点；normalized HV 不截断，外部乱序 actual sets 的 dense AUC 保持 null。每方法 54 runs / 27,000 calls。累计 wall-clock 为 uniform `20945.031473771203` s、hill-climbing `21077.843297181185` s、MH-annealing `20939.076001615264` s、AReUReDi-style `21015.123456662055` s；不是 time-matched 主比较。

```bash
cd /home/codonflow-a8-rk
export PYTHONDONTWRITEBYTECODE=1
PY=/root/miniconda3/envs/codonflow/bin/python  # Python 3.10.22 + NumPy 2.2.6 + ViennaRNA 2.7.2 + torch
CFG=configs/a8_rk06_simple_search_dense_unique18_protocol_v1.json
A=audits/20261120/RK06
IND=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk06/simple_search_dense_independent_v2

$PY -m unittest scripts.tests.test_a8_rk06_simple_search_dense_unique18 -v
$PY -m unittest scripts.tests.test_a8_rk06_verify_simple_search_dense_unique18 -v
$PY -m unittest scripts.tests.test_a8_rk06_verify_simple_search_dense_ppt -v

# 恢复既有正式矩阵；不要在未备份时覆盖冻结证据。
$PY scripts/a8_rk06_simple_search_dense_unique18.py \
  --protocol "$CFG" --workers 4 --resume

# 逐 run 独立重算；大型 checks/arrays 留在 /teams。
$PY scripts/a8_rk06_verify_simple_search_dense_unique18.py \
  --protocol "$CFG" \
  --production "$A/simple_search_dense_unique18_v1.json" \
  --output "$A/simple_search_dense_independent_v2.json" \
  --independent-root "$IND" --workers 4 --resume

$PY scripts/a8_rk06_finalize_simple_search_dense_unique18.py
$PY scripts/a8_rk06_verify_simple_search_dense_closeout.py
```

本次文档 closeout **35/35 PASS**，上述三个定向测试模块合计 **25/25 PASS**，当前 v29 论文核验 **61/61 PASS**。误用 system `python3` 导致的 `torch/RNA` 导入错误日志保留；正确环境为 `/root/miniconda3/envs/codonflow/bin/python`。closeout 的 PPT 字段适配和 README 暂缺 v29 SHA 失败历史也保留在 `simple_search_dense_closeout_correction_v1.json`。

全新复现应复制协议并使用新的 `artifact_root` 与输出路径；此时脚本会正确标为非 formal，不得把 smoke 当正式矩阵。冻结协议 SHA256=`f144397909b6961d961dd86727003accc63f3fa4d316019686f4c649b52d95fb`，production SHA256=`d060492c1d6882ad950ccde9782ee5cf2f8b98dfd5d24b0ea16757e6a8d2a052`。最终 independent **26/26 PASS**，finalization **44/44 PASS**；恢复前后 432 份 checks/arrays SHA256 完全不变，新 scoring calls=0。端点映射与 external-policy 的两次汇总 schema 失败、修复日志和 correction 均保留。

六个 primary tests 为 **4/6 SUPPORTED**：hill-climbing 与 MH-annealing 相对 uniform 的 dense AUC/B500 HV 为正向；AReUReDi-style 两项显著负向并保留 NOT SUPPORTED。完整效应、CI、Holm p、方法均值与成本见 `$A/simple_search_dense_claims_v1.json`。这些结果只支持 unique18 development proxy-search，不支持功能效果、外部 SOTA、time-matched 优势、RK-G1 关闭或生成训练授权。

RK06 section 6.24 / A8 v28 已通过 **24/24 checks + 73/73 candidate facts**，随后 MAGE section 6.25 生成当前 v29。`scripts/a8_rk06_update_paper_simple_search_dense.py` 即使传 `--help` 也会实际更新，当前 v29 上不得再次运行；RK06 v28 paper verifier 也不适用于 v29。当前稿件使用上面的 MAGE v29 verifier。

在线 PPT 已在 104 页/revision 66 基线上只追加第 **105 页 `pZp`、revision 67**。候选 **50/50 PASS**，最终写后 **16/16 PASS**，真实截图人工验收；首次 14/16 和 verifier correction 保留。科学、论文与 PPT 证据提交分别为 `0bc9ddb8a6944974ad72dce91b3eb6fd8d81690d`、`a68b07b7171093b534ad7055d7fcbddea952f350`、`1fa4ca2cde0c1272d382947b2d9bf765208cc2a6`。本段未运行完整项目 `pytest tests/` 或干净环境安装。

## A8-RK：RK-G0 bounded readiness 与统一成本 closeout

**G0 closeout 时点（2026-11-20）**：A8 工作稿为 v30，新增 §6.26；在线总稿为 106 页 / revision 68，末页 `pZg`。G0 仅达到 `PASS_BOUNDED_DATA_BASELINE_EVALUATION_READY`，不是完整 RK-G0–G4、生成模型、外部 SOTA 或真实功能闭环。后续 RK08/v31/PPT107 见下节。

- 冻结 22 份真实来源及 SHA256，形成 22 行统一成本矩阵、20 个 gate/boundary checks；13 个范围有实测 wall-clock，9 个范围显式 null。null 表示未测量或不可归因，不是 0；不同硬件、任务和评价范围不求伪总和、不作 time-matched 排名。
- production 179/179 PASS，独立复核 357/357 PASS / max delta=0，定向反篡改测试 9/9 PASS，finalization 6/6 PASS。科学证据 commit=`c1f641a17f4f2157be0d498d24ba363674bd7617`。
- v1 的 `KeyError: lineardesign_unique_sequences` 与 10 个失效指针完整保留；v2 仅修读取路径和不可证实字段，没有修改科学源、重跑 baseline 或新增 scorer calls。详见 `audits/20261120/RK06/g0_closeout_correction_v1.json`。
- LinearDesign unique18 generation=5459.871640930884 s / 131 outputs；EnsembleDesign=6001.057458210271 s / 192 outputs；RK06 四方法各 27,000 unique scorer calls、每方法约 20,939–21,078 s；RiboMIMO study-OOD 三 seed=949.7424744511954 s。外部 actual-set、official smoke、study-OOD 与 dense proxy search 不混排。
- RK03-REMAINING 仅闭合为 `FEASIBILITY_CLOSED_NOT_FULL_REMAP`；RNARL 仍是 21 文件、260,754 raw rows、128,289 clean QC pairs 的 pair-table QC，不是官方生成或训练。CDGB source identity 未解决，COformer/CHARMING=NOT_RUN。
- 论文 v30 SHA256=`6ab241c672ced7ec5f770d324487cc5deb742c0d3697afb5418d7f2b11c3024a`，独立 127/127 PASS，commit=`e8bf9d37ecee83e7caa2ec8997717e85e99f8d28`。第 106 页科学验收 47/47、closeout 10/10、视觉复核 PASS，旧 105 页语义不变；PPT 证据 commit=`44ce165e7c74419ba26bf4b422a24fc691c3de8b`。
- 大型 PPT XML、响应、截图与科学输入归档：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk06/g0_closeout_ppt_v1/`。

只读复核命令（不会追加在线页面或重跑生成器）：

```bash
cd /home/codonflow-a8-rk
python3 scripts/a8_g0_verify_closeout.py \
  --root /home/codonflow-a8-rk \
  --protocol configs/a8_g0_closeout_protocol_v2.json \
  --production audits/20261120/RK06/g0_unified_cost_closeout_v2.json \
  --output /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk06/g0_recheck_independent_v1.json \
  --tests-log audits/20261120/RK06/g0_closeout_targeted_tests_v1.console.log \
  --finalization-output /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk06/g0_recheck_finalization_v1.json
python3 scripts/a8_g0_verify_paper_closeout.py --root /home/codonflow-a8-rk
python3 scripts/a8_g0_verify_ppt_closeout.py \
  --workdir /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk06/g0_closeout_ppt_v1
python3 scripts/a8_g0_finalize_ppt_closeout.py \
  --workdir /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk06/g0_closeout_ppt_v1
python3 scripts/a8_g0_verify_closeout_documents.py --root /home/codonflow-a8-rk
```

仍未闭合：external actual-set dense 完整矩阵、time-matched、完整自然分布、full UTR–CDS remap、RNARL 官方模型、VeloHARMO 五物种、完整外部 SOTA、Kudla 逐构建表、functional-untouched、wet-lab/前瞻 DBTL。RK-G1=false，generator_training_authorized=false。本轮未在 G0/v30 后运行完整项目 `pytest tests/`、干净环境安装或端到端总复现。

## A8-RK：RK08 十臂机制通道筛选、v31 与 PPT107 closeout

**当前状态（2026-11-20）**：工作稿为 **v31**，新增 §6.27；在线总稿为 **107 页 / revision 69**，末页 `pZZ`。十臂同骨干 screen 的 development 唯一入选臂为 `all`，但其相对 full-proxy `ridge_all` 的 sequence-OOD Spearman 与 CB-MSE 两项均不显著，故 `channel_screen_gate_pass=false`、`rk_g1_pass=false`，**未授权昂贵生成训练**。

- **预注册与隔离**：协议、10 份 train/dev-only configs、准备报告和运行脚本在训练前以 `669b2735c21bf9bda8fdac12fc0c9f69635a38b5` 推送。每臂 4,997 参数，统一 backbone、训练超参数、seed 和 dev checkpoint 规则；选臂前不加载 test、sequence-OOD 或 functional untouched。
- **development 选择**：10/10 臂真实完成；独立 cluster-balanced MSE 最小值为 `all=3.761769367012553`，其余臂均更高，无同分。train/dev-only `all` 与 `none` 的 `state_dict` 分别与既有全量实验逐张量 bitwise 相等；selected epoch、best 权重及 train/dev/最终评估 predictions 一致，排除了旧训练仅因加载 test/OOD 行而改变权重的可能。
- **sequence-OOD 主结果**：2,000 次 operational-protein-cluster paired bootstrap，6 个 OOD 比较内 Holm 校正。`all−none`：ΔSpearman=`+0.19901564752464795`，95% CI=`[0.12925907591173844,0.26781646706339085]`，Holm p=0；ΔCB-MSE=`-0.2760885716873087`，CI=`[-0.37608880535590633,-0.18123318545616485]`，p=0。`all−ridge_gc`：ΔSpearman=`+0.12022060447388114`，CI=`[0.0819592276678431,0.1602983907730725]`，p=0；ΔCB-MSE=`-0.2895163999162387`，CI=`[-0.3565435053891241,-0.226815730607076]`，p=0。
- **full-proxy 关键对照未通过**：`all−ridge_all` ΔSpearman=`-0.025779039513507546`，95% CI=`[-0.0755256519724216,0.020488139619787824]`，Holm p=`0.532`；ΔCB-MSE=`-0.025572097048845777`，CI=`[-0.1282439258338166,0.07253420347846523]`，p=`0.636`。即使 dev 选出 `all`，也没有稳定超过 full-proxy ridge；不是换一个单通道臂即可解除的门禁。
- **独立验收与边界**：通道筛选定向测试 8/8 PASS；独立 verifier 从原始预测重算选臂、指标、bootstrap、CI、p 值和 Holm，320/320 PASS，max numeric delta=`1.9095836023552692e-14`；finalization 42/42 `PASS_CHANNEL_SCREEN_CLOSEOUT`。科学证据与 closeout 分别为 `9fc6353399db2e33ccb56c2a6b1afbd4d4340170`、`d628fb8b71f5a9a264dcc14952d6f3b7eccf8a6f`。既有 velocity 主终点已失败，MAGE 机制对照亦未支持稳定机制增量；functional untouched 未评测，外部预训练模型替代、独立常数速度场、transport 和完整外部 SOTA 未闭合。
- **论文 v31**：真实稿件 `paper/CodonFlow_preprint_A8.md`，SHA256=`9c0b453d5b3fbc0e2672dc776fa718d13cc50dcc072ab654aafdfcbe3e0a3c1a`；新增 §6.27 和证据锚点，可精确恢复 v30。115/115 PASS；首次 113/115 的英文同义字面检查失败报告和 correction 均保留，未改变科学证据。论文提交 `7d5e51a17f93218e831bc22b845c030065362a35`，推送后复验仍为 115/115。
- **PPT107**：在 106 页/revision 68/`pZg` 基线上只追加第 107 页 `pZZ`、revision 69；candidate 103/103、写后 223/223、closeout 18/18，真实服务端截图人工视觉验收 PASS。保留 candidate 102/103 的 `Holm p=0` 前缀误计失败、写后 222/223 的旧末页 whitespace-only tail 失败及 correction；科学内容与旧页语义未改。PPT 提交 `d4afbf79e55da335f66b05507448ecd6e2fbc798`，推送后复验仍为 223/223 和 18/18。
- **证据入口**：选择、评估、paired/metrics、320/320 独立报告和 42/42 finalization 位于 `audits/20261118/RK08/`；大型 checkpoints、predictions、bootstrap deltas 与 PPT before/after XML、响应和截图分别位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk08/channel_screen_v1/`、`channel_screen_ppt_v1/`。小型验收与脚本进入 Git，大型数据/权重不进入 Git。
- **复现边界**：本轮定向证据验收不能替代完整项目 `pytest tests/`、干净环境安装或端到端总复现；这些仍未在 v31/channel screen/PPT107 后执行。RK08 不改变 `DEV_NO_GO_TEST_UNTOUCHED`，不把 train/dev proxy 或 sequence-OOD 提升写成真实生物功能，也不把未训练生成器写成已完成。

文档只读验收：`python3 scripts/a8_rk08_verify_channel_screen_documents.py --root /home/codonflow-a8-rk --output audits/20261118/RK08/channel_screen_documentation_verification_v1.json`。PPT 只读复验：`python3 scripts/a8_rk08_verify_channel_screen_ppt.py --mode final --work-dir /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk08/channel_screen_ppt_v1 --visual-reviewed --output /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk08/channel_screen_ppt_v1/rk08_ppt_verification_posthandover_v01.json`；finalizer 同样只读：`python3 scripts/a8_rk08_finalize_channel_screen_ppt.py --root /home/codonflow-a8-rk --work-dir /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk08/channel_screen_ppt_v1 --output /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk08/channel_screen_ppt_v1/rk08_ppt_closeout_finalization_posthandover_v1.json`。

## A8-RK：MAGE 纯外部 RCS 对照、v32 与 PPT108 closeout

**当前状态（2026-11-20）**：工作稿为 **v32**，新增 §6.28；在线总稿为 **108 页 / revision 70**，末页 `pZS`。纯外部 RCS 特征臂在复用 MAGE development folds 上显著差于 intrinsic，不能替代 intrinsic（replacement=false）；full 或 intrinsic+RCS 优于纯 RCS 也不构成 full−intrinsic 机制增量。`rk_g1_pass=false`，test 与生成训练仍未授权。

- **纯外部臂定义与隔离**：仅使用 variant RCS、matched wild-type 差值及绝对差，不使用 position、codon/amino-acid identity、GC、local MFE 或其他 intrinsic 特征。131 个 train+dev constructs 沿用冻结 OOF/folds，5 outer × 4 inner × 3 seeds × 6 alphas，共 375 次新拟合；33 个 test constructs 始终排除。协议 SHA256=`9efd39ef21672722adde333e28f4e1144983949dfab5a6437a1f45a68e930b45`，预注册提交 `0a08eb90c3ee787578f5fac1d5f01a2b2fe72a5d`。
- **替代结论**：纯 RCS 主 seed RMSE=`0.04929761172417739`、Spearman=`-0.13201530863899236`；intrinsic 分别为 `0.03413327461240379`、`0.6123990835404937`。pure−intrinsic ΔSpearman=`-0.744414392179486`，95% CI=`[-0.9403491867053566,-0.5300791533185797]`，Holm p=`0.0002999850007499625`；ΔRMSE=`+0.015164337111773597`，CI=`[0.005846359530413134,0.02506527402042598]`，p=`0.009449527523623819`，两个 sensitivity seeds 方向一致不利于纯 RCS。
- **不能挽救机制增量**：full−pure 与 intrinsic+RCS−pure 的 Spearman/RMSE 比较均满足 development-only 支持规则，但 comparator 是弱纯 RCS 臂。旧 full−intrinsic 两项 CI 均跨零、Holm p=1，因此 `pure_external_replacement_supported_development_only=false`、`mechanism_increment_pass=false`；不得把“优于纯 RCS”写成“机制优于 intrinsic”。
- **独立验收**：10/10 单元测试 PASS；独立实现重跑 375 fits 及全部统计，174/174 PASS、max numeric delta=0；finalization 43/43 `PASS_PURE_EXTERNAL_COMPARATOR_CLOSEOUT`，postpush 174/174。科学证据提交 `b95e1244537a23c95cdda986cb60e343cfd7e4da`；生产/独立/finalization SHA256 分别为 `c39e3f3b42e126abdc3fdc0838c053c17b6c95374e841500e34196b340d663c9`、`eb4153a3cb3109aff34a6e73006af30387409a64531d4b28143bec17f71da0d2`、`29561b13922e4319715fd511c4b2ac4fa911d893815c722df17e0a96fb58f8e0`。
- **论文 v32**：真实稿件 SHA256=`6c3d2a0329a46ca70d4dd782748a06c60fbecbf91fd8d8fe5d7ea1c42e2b73f0`，独立及 postpush 均 100/100 PASS，可精确恢复 v31；论文提交 `d5959f73ac4f4812d614eee6d6c04d320dff38fc`。写作交付的 Makefile shell 错误与 correction 保留，未因此修改科学内容或门禁脚本。
- **PPT108**：candidate 227/227、写后 553/553、closeout 32/32，真实在线截图视觉 PASS；旧 107 页及备注语义不变。两次 `+add-slide` server timeout 后均确认未写入，再以带幂等键的原生接口追加一次 `pZS`，revision 70；没有重复页。PPT 提交 `3460c2e07d6e44d09afa38e747db737aae939911`。closeout 的报告字段与末尾换行修正记录保留，科学内容和在线页面未因此改变。
- **证据入口**：科学报告位于 `audits/20261120/RK03/`，PPT 小型报告同目录以 `pure_external_ppt_` 为前缀；大型 predictions、日志、整稿 XML 和截图位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/mage_pure_external_nested_cv_v1/` 及其 `pure_external_ppt_v1/` 子目录，大型 artifacts 不进入 Git。
- **复现边界**：本项只闭合纯 RCS 特征臂的替代诊断，不闭合所有外部预训练模型、独立常数速度场、transport、functional untouched、真实功能或完整外部 SOTA。v32/pure-RCS/PPT108 后未运行完整项目 `pytest tests/`、干净环境安装或端到端总复现。

文档只读验收：`python3 scripts/a8_rk03_verify_pure_external_documents.py --root /home/codonflow-a8-rk --asset-root /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/mage_pure_external_nested_cv_v1 --output audits/20261120/RK03/pure_external_documentation_verification_v1.json`。PPT 只读复验：`python3 scripts/a8_rk03_verify_pure_external_slide_postwrite.py --base /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/mage_pure_external_nested_cv_v1/pure_external_ppt_v1 --output /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/mage_pure_external_nested_cv_v1/pure_external_ppt_v1/pure_rcs_slide_postwrite_verification_posthandover_v01.json`；finalizer 使用同一 `--work-dir` 和独立输出文件。

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
