# RK07 Boël 跨蛋白代理效度诊断（bounded）

## 科学边界

本任务使用 RK04 已冻结的 Boël operational-homology-cluster split，比较 CAI、GC、全 CDS MFE、全 CDS MFE/nt、5′ 前 48 nt MFE 与固定组合模型。Boël 的 6,348 行是**跨蛋白、天然、非同义**表达池，不是固定蛋白同义文库。因此本任务只是 E1 的前置跨蛋白序列—表达关联诊断；不证明固定蛋白同义机制，不关闭 RK-G1，不授权生成器训练，不构成功能 OOD SOTA。

## 冻结协议与输入

- protocol：`configs/a8_rk07_proxy_protocol.json`
- protocol ID：`a8_rk07_boel_cross_protein_proxy_v1`
- protocol SHA256：`d42f7d06543b8f7279cc25cb4354828f6cc9fdb27f2d6c5ba0ed9808a20f762e`
- production/smoke commit：`a7250465d5705ae7b72a844d181701eb55582136`
- split：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional/splits/rk04_v1/functional_long_split.csv`
- split SHA256：`1ea0ff63b7f5e820abca3842b690cba0ffdfbc8b5f3f7fe4bf88a25efb94c0f8`
- train/dev/test=`5079/635/634`；19,072 条 MAGE `functional_untouched` 未使用。
- 外部参考：E. coli K-12 MG1655 RefSeq CDS；SHA256=`8b7b48b7b905313082141db4b77807b7aafebca7a5c40bbd42832baacd1cfd9b`；4,297 条合法非 pseudo CDS 用于 RSCU/CAI。该参考不是 BL21(DE3) 菌株匹配或表达加权参考。
- MFE：ViennaRNA 2.7.2，18°C；full CDS 含终端 stop，local48 为 CDS 前 48 nt、不含 5′UTR。CAI/GC 排除终端 stop。
- 组合模型：train-only 均值/标准差，fixed multinomial logistic expected score，L2=0.01，max_iter=2000；无 dev/test 超参搜索。单代理定量预测使用 train OLS，raw Spearman 另行保留。
- bootstrap：按 operational protein cluster 重抽样 1,000 次，seed=20261118；报告 percentile 95% CI、五比较 Holm 校正。top-k 固定为前 10% 的 E=5 enrichment；长度/GC 分层阈值仅由 train terciles 决定。

## 真实运行命令

```bash
cd /home/codonflow-a8-rk
PY=/root/miniconda3/envs/codonflow/bin/python
BASE=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk07

$PY -m scripts.a8_rk07_proxy_features \
  --protocol configs/a8_rk07_proxy_protocol.json \
  --output-features "$BASE/full/proxy_features.csv.gz" \
  --output-summary "$BASE/full/feature_summary.json" --workers 8

$PY -m scripts.a8_rk07_proxy_evaluate \
  --protocol configs/a8_rk07_proxy_protocol.json \
  --features "$BASE/full/proxy_features.csv.gz" \
  --feature-summary "$BASE/full/feature_summary.json" \
  --evaluation-splits train dev \
  --output-result "$BASE/dev/dev_results.json" \
  --output-predictions "$BASE/dev/dev_predictions.csv.gz"

# 唯一一次冻结 test 评估；未根据 test 修改特征、模型、阈值或比较协议。
$PY -m scripts.a8_rk07_proxy_evaluate \
  --protocol configs/a8_rk07_proxy_protocol.json \
  --features "$BASE/full/proxy_features.csv.gz" \
  --feature-summary "$BASE/full/feature_summary.json" \
  --evaluation-splits train dev test --frozen-test-confirmation \
  --dev-baseline-result "$BASE/dev/dev_results.json" \
  --output-result "$BASE/final/final_results.json" \
  --output-predictions "$BASE/final/final_predictions.csv.gz"

# 独立复核：不导入生产模块，从 raw CDS/参考 FASTA 重算。
$PY scripts/a8_rk07_verify_proxy.py \
  --protocol configs/a8_rk07_proxy_protocol.json \
  --features "$BASE/full/proxy_features.csv.gz" \
  --feature-summary "$BASE/full/feature_summary.json" \
  --dev-results "$BASE/dev/dev_results.json" \
  --final-results "$BASE/final/final_results.json" \
  --predictions "$BASE/final/final_predictions.csv.gz" \
  --workers 8 --output audits/20261118/RK07/final_independent_verification.json
```

## 结果（最终状态以独立 verifier 为准）

组合 logistic 在 41 次迭代后收敛，独立梯度检查阈值由 verifier 复核；production 最大梯度绝对值=`1.1256659202376132e-07`。

### Spearman

| model | train | dev | frozen test |
|---|---:|---:|---:|
| CAI | 0.059256 | -0.020114 | 0.002615 |
| GC（train OLS 方向） | 0.081455 | 0.116454 | 0.096394 |
| full CDS MFE | 0.057373 | 0.101465 | 0.046348 |
| full CDS MFE/nt | 0.083237 | 0.120158 | 0.094988 |
| 5′前48 nt MFE | 0.145277 | 0.190659 | 0.077654 |
| combined logistic | 0.214632 | 0.212870 | 0.123239 |

GC 的 raw Spearman 与 OLS 方向相反：train/dev/test 分别为 -0.081455/-0.116454/-0.096394。CAI 在 dev/test 接近零，显示跨蛋白关联不稳定。

### Frozen-test：combined − 单代理

| proxy | ΔSpearman | cluster-bootstrap 95% CI | Holm p |
|---|---:|---:|---:|
| CAI | 0.120624 | [0.010186, 0.231194] | 0.179820 |
| full CDS MFE | 0.076890 | [-0.020242, 0.170661] | 0.351648 |
| full CDS MFE/nt | 0.028251 | [-0.059478, 0.112687] | 0.943057 |
| GC | 0.026845 | [-0.062697, 0.114032] | 0.943057 |
| 5′前48 nt MFE | 0.045584 | [-0.007246, 0.100501] | 0.351648 |

所有 test paired Spearman 比较均未通过 Holm；CAI 比较虽然 percentile CI 下界大于零，但 Holm 不通过，仍不能称为稳健胜出。Dev 上组合模型相对 5′局部 MFE 的 ΔSpearman=`0.022211`，95% CI=`[-0.022530, 0.067986]`，Holm p=`0.327672`，同样未显著。

Frozen-test top-10% E=5 enrichment：combined=`1.031901`、5′局部 MFE=`0.980306`、CAI=`0.722331`；combined−5′局部 MFE 的差值 95% CI=`[-0.378745, 0.502100]`，未证明 top-k 优势。

### 失败分层

- GC-high test：5′局部 MFE Spearman=`0.195923`，高于 combined=`0.170224`。
- GC-low test：CAI Spearman=`0.207418`，高于 combined=`0.070855`；5′局部 MFE=`-0.079237`。
- 因此没有任何单代理或组合模型在所有长度/GC 区域一致占优；不得删除这些区域或选择性展示。

**科学结论：组合模型在 frozen test 的 Spearman 点估计最高，但增量小且经 cluster bootstrap/Holm 后不稳健；简单代理失效未被证明，跨蛋白动机必须收窄。该结果不支持进入机制生成器训练，也不构成 SOTA。**

## Artifact 与环境

- Python 3.10.22；NumPy 2.2.6；SciPy 1.15.3；ViennaRNA 2.7.2；8 CPU workers。
- feature code SHA256：`667a40e0bfced43f47d37e377509f971188ca2a8a495ddf96d8608449063c8eb`
- evaluation code SHA256：`63a229e5e2b406939d217bb7ad6dc29180814f833d063cb9d2caa441f84a2b08`
- independent verifier SHA256：`763e46bd92532b5cb6836729c1c441ad323cd02f4e4ea0db864649ff7cd3daee`
- features SHA256：`aabb16bf36912bd761a9c5dd6c1c34797a99d1b2d3aab1b4891e34732b67941b`
- feature summary SHA256：`64a50488a523a46cb4359c36598a8dfde3278be23e921e58e3b206a5ac0acd5b`
- dev result SHA256：`76c44ddad746d5f3e4714dd237a1493a126cf87308aa00b6d258d053519c5ee7`
- dev predictions SHA256：`8fd4c62e05f82091e029b05065ff08c7177303e432fcf119fff7c83e9b5d1006`
- final result SHA256：`2ba7b1dc084172e891c8d5775790b7c94ddbca8788d8a88bbb0876f6fd289838`
- final predictions SHA256：`f8827eb7aa52d2908e7c00f04dbcd3c926aada654a6f0b16025b14d2d317b7f5`
- independent report SHA256：`1dab1cf3405a7158bcc0a2d395dbb2882395b7a252ba671c49197b9158cfa815`
- large artifacts 均留在 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk07/`，未提交 Git。

## 验证状态

- 合成与真实 smoke：10/10 tests PASS；真实 smoke 仅用于开发，不包含 test 指标。
- 全量独立 raw-source verification：**PASS，9/9 checks**；报告为 `audits/20261118/RK07/final_independent_verification.json`。独立重算全部 6,348 条 raw CDS、参考 RSCU、预测、bootstrap/Holm 和分层；raw feature 最大差=0，prediction 最大差=`1.33e-15`，paired CI 最大差=`2.23e-16`，stratum metric 最大差=`4.45e-16`。
- dev freeze：final artifact 与 pre-test dev baseline 完全一致；`forbidden_split_used=false`，19,072 条 `functional_untouched` 未参与拟合、调参或本次评价。
- 预印本未修改；Fig.1 的真实固定蛋白同义代理失效证据仍 pending。
