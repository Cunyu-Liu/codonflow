# RK-04：无泄漏功能数据划分

## 结论

- 状态：`PASS_WITH_SCIENTIFIC_BOUNDARIES`；独立复核：`PASS`，33/33 checks。
- 输入保持只读：`functional_long.csv`，25,420 行，SHA256 `c436b758369018fe0fd121ce6e741993e90a5de80b4706ab87082f7557b6a377`。
- Boël 6,348 行按 operational protein clusters 划分为 train/dev/test = 5,079/635/634 行，对应 4,442/556/556 clusters。
- 全部 MAGE infA 19,072 行在聚类和任何模型训练前冻结为 `functional_untouched`；infA 独立成簇，本阈值下没有 Boël 成员被一并冻结。
- 共 6,349 条蛋白序列、5,555 个 operational clusters；这些是 MMseqs2 操作簇，不称为人工校订 protein families。
- exact CDS、exact/derived protein、source protein ID、operational cluster、construct-signature group、非空 mutation signature 的所有跨 split 两两重叠均为 0。
- MAGE 13,569 个 construct-signature groups 全部 untouched：S1 4,672、S2 8,129、S3 768；S1 两种 assay 与 S2 重复 mutation signatures 不跨 split。
- `training_ready=false`、`training_or_model_selection_performed=false`、`functional_untouched_evaluated=false`。本结果不是功能 OOD 性能、生成性能或 SOTA 证据。

## 冻结协议

- Protocol：`a8_rk_split_v1_mmseqs2_id050_cov080_seed20261118`
- MMseqs2：`ab57c0b9cd8893f1063e391c94cc845a3179bab1`
- 参数：`easy-cluster --min-seq-id 0.5 -c 0.8 --cov-mode 0 --threads 16`；coverage mode 0 为双向覆盖。
- 二进制 SHA256：`43e701faccbf58aa2c33cda15ecd0c73c06f76b79c3e2b021f6f1167b176d380`
- 分配：infA 所在簇预冻结后，其余簇只依据序列、簇行数和固定 seed `20261118` 做 deterministic 80/10/10 cluster-size balancing；不读取表达标签或模型结果。
- infA reference 由 S1 的 73 个 WT controls 重建：219 nt CDS、72 aa 蛋白，position 73 为终止密码子。

## 产物与 SHA256

团队数据目录：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional/splits/rk04_v1/`

| Artifact | SHA256 |
|---|---|
| `functional_long_split.csv` | `1ea0ff63b7f5e820abca3842b690cba0ffdfbc8b5f3f7fe4bf88a25efb94c0f8` |
| `proteins.fasta` | `38c593b73eddbf2a88f5e32258ea52e08320c9ac55427083d988b5291a9cc359` |
| `protein_clusters_cluster.tsv` | `581efab2909f5ff63aff9a3c9ead24bf9582d9b82420066663859824e08bad85` |
| `split_assignments.csv` | `9bece243752d12e8e1d9ee0cc2a69e9a94332fab0b39b676e8038fe36592e362` |

独立复核报告：`independent_split_verification.json`。生产报告：`split_summary.json`。

## 失败与修正记录

1. 非交互 SSH 首次启动未设置项目 `PYTHONPATH`，在 import 阶段退出，未创建划分产物；随后显式使用 `PYTHONPATH=.`。
2. 交接文档中的输入 SHA 为转录错误。当前输入与 RK-02 `audit_summary.json` 和 `independent_verification.json` 一致，真实 SHA 为上述 `c436b758…a377`；没有修改输入文件。
3. 团队文件系统不支持 MMseqs2 内部 symlink，首次聚类退出。失败目录保留为 `rk04_v1_failed_mmseqs_symlink/`。正式运行把临时目录改为 `/home/codonflow-a8-rk-runtime/rk04_mmseqs_v1`，最终数据产物仍写团队目录。

## 复现

```bash
cd /home/codonflow-a8-rk
export PYTHONPATH=.
/root/miniconda3/bin/python scripts/a8_build_rk_splits.py \
  --input /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional/clean/functional_long.csv \
  --expected-input-sha256 c436b758369018fe0fd121ce6e741993e90a5de80b4706ab87082f7557b6a377 \
  --output-dir /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional/splits/rk04_v1 \
  --tmp-dir /home/codonflow-a8-rk-runtime/rk04_mmseqs_v1 \
  --audit-dir /home/codonflow-a8-rk/audits/20261118/RK04 \
  --mmseqs /teams/HoulabData_1788502323/liucunyu/codonflow1031/tools/mmseqs2-latest/mmseqs/bin/mmseqs \
  --threads 16 --seed 20261118
/root/miniconda3/bin/python scripts/a8_rk_verify_splits.py \
  --input /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional/clean/functional_long.csv \
  --audit-dir /home/codonflow-a8-rk/audits/20261118/RK04
/root/miniconda3/bin/python -m unittest discover -s scripts/tests -p 'test_a8*split*.py' -v
```

生产脚本拒绝覆盖既有输出目录；复现时应使用全新输出与临时目录，并保留本次产物哈希作为对照。

## Sequence-OOD v2 与 train-only 归一化（2026-11-19）

- 原 v1 的 train/dev/test=`5,079/635/634` 保持不变；v2 是追加的 `ood_assignment`，不是覆盖旧 split。
- 只从 original train 的序列特征计算 q05/q95：长度闭区间 `[276,1590]` nt，GC 闭区间 `[0.3294248837430009,0.7093033422956696]`。长度和 GC 均排除 terminal stop，与冻结特征表一致。
- 一个 operational cluster 的任一成员低于下限或高于上限，整个簇迁入 `sequence_ood`。因此 retained train/dev/test=`4,019/503/490`，sequence-OOD=`1,336`，分别包含 3,561/447/436/1,110 个 clusters；这不是原 v1 的 post-hoc tercile 分层。
- sequence-OOD 从原 train/dev/test 分别迁入 1,060/132/144 行；簇级原因计数为 length-low=246、length-high=277、GC-low=312、GC-high=310，原因可重叠。
- 19,072 条 MAGE functional untouched 仅原样复制，未计算长度/GC 特征、未参与阈值或归一化、未评价。
- `train_only_normalization.json` 只拟合 retained train 的 observed values；缺失值用 train observed mean 填充并增加 missing indicator，不做静默零填充。全特征表 `source_Gave144` 缺 62 条，retained train 缺 0 条，缺失样例保留在 dev/test/sequence-OOD 供显式 imputation。
- 单元测试 `13/13 PASS`；独立重算 `37/37 PASS`；finalization `11/11 PASS`。首次 v1 因 62 条缺失在导入阶段失败，空目录保留；首份 verifier 因错误假设 retained train 必有缺失而为 `35/36 FAIL`，报告同样保留，v2 修正核验假设后通过。
- 数据产物：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk04/sequence_ood_v2/`；`functional_long_sequence_ood.csv` SHA256=`b9e29eac8eeb0adc46101d81ae8f2afa650eb3d5a37722b065e052fc669e45c6`，`train_only_normalization.json` SHA256=`a1b2bc158a2669d8cf5db0f6f2ea26c26913a2203ed5e86ca020497458b210db`。
- 审计：`sequence_ood_summary.json`、`sequence_ood_independent_verification_v2.json`、`sequence_ood_finalization.json`。当前只授权 predictor 开发；`sequence_ood_evaluated=false`、`functional_untouched_evaluated=false`、`generator_training_authorized=false`，尚无 OOD 性能、功能 OOD、生成器或 SOTA 结论。

复现命令：

```bash
cd /home/codonflow-a8-rk
PYTHONPATH=. /usr/bin/python3 scripts/a8_rk04_build_sequence_ood.py \
  --input /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional/splits/rk04_v1/functional_long_split.csv \
  --input-sha256 1ea0ff63b7f5e820abca3842b690cba0ffdfbc8b5f3f7fe4bf88a25efb94c0f8 \
  --features /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk07/full/proxy_features.csv.gz \
  --features-sha256 aabb16bf36912bd761a9c5dd6c1c34797a99d1b2d3aab1b4891e34732b67941b \
  --output-dir /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk04/sequence_ood_v2 \
  --audit-dir /home/codonflow-a8-rk/audits/20261118/RK04
PYTHONPATH=. /usr/bin/python3 scripts/a8_rk04_verify_sequence_ood.py \
  --input /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional/splits/rk04_v1/functional_long_split.csv \
  --features /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk07/full/proxy_features.csv.gz \
  --summary audits/20261118/RK04/sequence_ood_summary.json \
  --production-script scripts/a8_rk04_build_sequence_ood.py \
  --output audits/20261118/RK04/sequence_ood_independent_verification_v2.json
PYTHONPATH=. /usr/bin/python3 -m unittest scripts.tests.test_a8_rk04_sequence_ood -v
```

## PPT 记录与回读

- 在线主稿：<https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g>。
- 在 revision 20 的 58 页基线上只追加第 59–60 页，slide IDs=`pgn/pgo`，写入后 revision=22。
- 第 59 页记录 split 数量、冻结协议和科学含义；第 60 页记录 33/33 独立复核、19/19 测试、零重叠、GitHub 证据和不可声称事项。
- `ppt_verification.json` 为 PASS：整稿 60 页，前 58 页内容与结构保持不变（第 58 页末尾仅有无语义空白差异），新页关键文本和备注齐全，所有带坐标的元素均在 960×540 画布内。
- 回读 XML SHA256=`b7c5f9651df573723953a4545037fb06f338bf329eca51238dcc482aad8311ef`。
- sequence-OOD v2 在 revision 41 的 79 页基线上只追加第 80 页，slide ID=`pgq`，写入后 revision=42。候选 XML 先与 finalization 11/11 和真实 counts 核对；写后回读 10/10 PASS，前 79 页 slide IDs 与语义 XML 不变。回读 XML SHA256=`956991838376d9b07f3073aa83ae8064c23c6e1446b866bd41ce663ff0f4206d`。

## 12. Sequence-OOD 功能预测模型（2026-11-19，正式实现 v2）

### 12.1 冻结协议与模型选择

协议：`configs/a8_rk04_sequence_ood_model_protocol.json`，protocol ID=`a8_rk04_sequence_ood_model_v1_dev_cbmse`。只用 retained train 拟合，dev 按 operational-cluster-balanced MSE 为每个家族选一个候选，再冻结 overall primary family；test 与 sequence-OOD 不参与选择。没有在 train+dev 重训。19,072 条 MAGE functional untouched 不读取用于训练或评价。

共 5 个家族、17 个候选：train 加权均值常数、GC-only Ridge、5 个基础序列特征 Ridge、10 个代理特征 Ridge、全代理特征 HistGradientBoosting。Ridge alpha 网格为 0.1/1/10/100；HistGB 为 4 个冻结候选。训练权重为 retained train 内 cluster 行数倒数，归一化沿用冻结 train-only JSON，Gave144 仅用 train observed mean 和 missing indicator。

dev 选择结果：

| family | selected parameters | dev cluster-balanced MSE |
|---|---|---:|
| constant | train weighted mean | 3.905366 |
| ridge_gc | alpha=0.1 | 3.834222 |
| ridge_basic | alpha=100 | 3.743059 |
| **ridge_all (primary)** | **alpha=100** | **3.725576** |
| histgb_all | leaves=7, iter=200, lr=0.05, min_leaf=20, L2=1 | 3.763559 |

### 12.2 最终分区结果

以下为最终冻结指标；CB-MSE=cluster-balanced MSE。常数模型的相关指标无定义，记为 `null`，不补零。

| family | test Spearman | test R² | test CB-MSE | sequence-OOD Spearman | sequence-OOD R² | sequence-OOD CB-MSE |
|---|---:|---:|---:|---:|---:|---:|
| constant | null | -0.004095 | 4.400064 | null | -0.057252 | 4.388894 |
| ridge_gc | 0.119209 | 0.011011 | 4.338435 | 0.071873 | -0.050378 | 4.378262 |
| ridge_basic | 0.124036 | 0.009743 | 4.292031 | 0.203876 | -0.009653 | 4.211838 |
| **ridge_all (primary)** | **0.144896** | **0.015979** | **4.257835** | **0.217873** | **0.011709** | **4.114318** |
| histgb_all | 0.203076 | 0.037747 | 4.207758 | 0.219383 | 0.032386 | 3.989950 |

HistGB 在 retained test 的 Spearman 数值高于 primary，但不能在看到 test 后替换 dev 冻结的 primary；完整非主家族结果保留，避免选择性报告。绝对解释度仍低，不能把 sequence-OOD 排名相关提升包装成强功能预测或机制增益。

dev 冻结 primary `ridge_all` 相对 dev-selected `ridge_gc` 的 paired operational-cluster bootstrap（1000 次，seed=20261119）：

| partition | Δrow Spearman | 95% CI | ΔCB-MSE | 95% CI |
|---|---:|---|---:|---|
| retained test | +0.025687 | [-0.066372, 0.119629] | -0.080600 | [-0.233242, 0.078749] |
| sequence-OOD | +0.146000 | [0.103896, 0.189857] | -0.263944 | [-0.374981, -0.144076] |

因此，retained test 的增量区间跨零；sequence-OOD 上组合代理特征相对 GC 的排名和 CB-MSE 改善区间未跨零。该结果只支持 **Boël nonsynonymous proxy prediction 的有限 sequence-OOD 信号**，不支持固定蛋白同义机制、同骨干 initiation/velocity/decay/pair-channel 增量、CodonFlow-RK 生成器、SOTA、functional untouched 或湿实验声称。

### 12.3 独立复核、失败保留与复现

- 单元测试：`sequence_ood_model_unit_tests.log`，12/12 PASS。
- 独立验证：`sequence_ood_model_independent_verification.json`，40/40 PASS；独立重算所有分区指标、origin strata、bootstrap 和 dev 选择，逐行加载模型前向，最大预测误差 0.0。
- 第二次完整训练：`sequence_ood_model_retrain_summary.json`；两次 `predictions.csv.gz`、`metrics.json` 和 `dev_model_selection.csv` SHA256 完全一致。
- 最终化：`sequence_ood_model_finalization.json`，18/18 PASS；同时确认常数相关修正没有改变模型选择、非恒定模型结果或主比较。
- 首次 schema 失败保留为 `sequence_ood_model_training_v1_fail.console.log`：真实字段是 `expression_value` 与 `operational_protein_cluster`，代理特征表不含表达标签。
- 默认 47 线程的小数据超额订阅运行被终止，保留 `sequence_ood_model_training_v2_incomplete_multithread.console.log`；正式运行和复现仅限制数值库为单线程，模型协议不变。
- 首次完成结果中的常数簇均值出现浮点末位差异，产生伪相关；旧 summary/log 保留为 `*_v1_constant_corr_artifact.*`，旧大文件目录保留为 `sequence_ood_model_v1/`。正式实现 v2 对全局常数预测的所有相关指标明确记 `null`。
- 独立 verifier 初次遗漏派生 `log_length_nt`，在独立前向阶段停止；修正后 40/40 PASS，生产结果未因此改变。

正式 artifacts：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk04/sequence_ood_model_v2/`；第二次训练：`sequence_ood_model_v2_retrain/`。预测和模型权重不进入 Git；summary、metrics、dev selection、日志和验证报告进入 Git。

```bash
cd /home/codonflow-a8-rk
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
/root/miniconda3/envs/llr_env/bin/python scripts/a8_rk04_sequence_ood_model.py \
  --protocol configs/a8_rk04_sequence_ood_model_protocol.json \
  --output-dir /teams/HoulabData_1788502323/liucunyu/codonflow1031/rk04/sequence_ood_model_v2 \
  --report audits/20261118/RK04/sequence_ood_model_summary.json
/root/miniconda3/envs/llr_env/bin/python scripts/a8_rk04_verify_sequence_ood_model.py \
  --protocol configs/a8_rk04_sequence_ood_model_protocol.json \
  --summary audits/20261118/RK04/sequence_ood_model_summary.json \
  --production-script scripts/a8_rk04_sequence_ood_model.py \
  --output audits/20261118/RK04/sequence_ood_model_independent_verification.json
```

## 13. 模型 PPT 与 A8 v12 论文记录

- 在线主稿在 revision 42 的 80 页实时基线上只追加第 81 页 `pge`，写后 revision=43。候选 XML 先经 `rk04_model_ppt_candidate_verification.json` **21/21 PASS**，写后整稿回读经 `rk04_model_ppt_verification.json` **12/12 PASS**；前 80 页 slide IDs 与语义 XML 均不变，新页五家族数值、4 段备注和画布边界全部通过。
- 写后整稿 XML SHA256=`64044fb689f537f35c9cb59fb4d9302ea0d39037a5642708a8fa8241c0099d3b`。完整 before/after XML 保存在 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk04/reporting/sequence_ood_model_ppt/`；候选 XML、写入响应、验证脚本与报告进入 Git。
- PPT 链接：https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g 。本页只报告 sequence-OOD proxy 性能，不支持机制、生成器或 SOTA。
- `paper/CodonFlow_preprint_A8.md` 已升级为 v12，新增 sequence-OOD 数据协议、五家族完整结果、dev 选择、test/OOD bootstrap、失败历史和证据哈希；A8 v11 原快照 SHA256=`0158f579cb1634b1a36c666c4cf7c930dcabe276abc00e3c00f5546ef1005a05` 保持不变。
- 独立论文报告 `rk04_model_paper_verification.json` **19/19 PASS**；v12 SHA256=`5ff302e51dd26decaa628e23481bedab9b6a747fbd13eac08017c578396877a9`。仍为 non-submittable working manuscript，functional untouched、同骨干机制、主模型、强 baseline 主矩阵、生成器和湿实验未关闭。
