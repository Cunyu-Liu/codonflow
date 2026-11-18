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

## PPT 记录与回读

- 在线主稿：<https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g>。
- 在 revision 20 的 58 页基线上只追加第 59–60 页，slide IDs=`pgn/pgo`，写入后 revision=22。
- 第 59 页记录 split 数量、冻结协议和科学含义；第 60 页记录 33/33 独立复核、19/19 测试、零重叠、GitHub 证据和不可声称事项。
- `ppt_verification.json` 为 PASS：整稿 60 页，前 58 页内容与结构保持不变（第 58 页末尾仅有无语义空白差异），新页关键文本和备注齐全，所有带坐标的元素均在 960×540 画布内。
- 回读 XML SHA256=`b7c5f9651df573723953a4545037fb06f338bf329eca51238dcc482aad8311ef`。
