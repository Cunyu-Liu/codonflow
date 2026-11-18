# RK-03 机制与自然序列数据：来源、QC 与独立复核

日期：2026-11-18。本文验收 RiboMIMO 机制数据与 CodonTransformer 自然序列两个 bounded 子项；RK-03 整体与 RK-G0 尚未关闭。

## 1. 权威代码与科学边界

- 工作树：`/home/codonflow-a8-rk`；分支：`a8-rk`。
- 下载器：`1264f1a577c1c6d2bae1612d7022569828998a7d`、`8b6365f4be7456f089e53bf3089c0ef75c3f06cb`。
- 首版 QC：`4b551c850e61791cd7895a2968b23c4d9fe5ca3a`，仅为诊断版本。
- v2 生产修复：`81c0cddf3b742a50b7f6901836ab01cba984b7d9`。
- 生产脚本：`scripts/a8_rk03_ribomimo_qc.py`；独立 verifier：`scripts/a8_rk03_verify_ribomimo.py`。verifier 不导入生产 QC 模块。
- 数据来源是作者处理后的 codon/A-site count 矩阵，不含 raw reads 或 UTR；occupancy/density 是实验依赖的相对速度代理，不是绝对速率、功能真值或因果证据。

官方来源：

- RiboMIMO repository：<https://github.com/tiantz17/RiboMIMO>，固定 commit `094c693d4df45f4b29f5a3209b31c452a39092a5`。
- 论文：<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008842>。
- Mohammad16=`GSE72899`；Mohammad19-1=`GSE119104/GSM3358140`；Mohammad19-2=`GSE119104/GSM3358142`；Subtelny14=`GSE53268/GSM1289257`。两个 GSM 是不同样本，不从现有来源推断其技术或生物学重复属性。

## 2. 原始文件与参考完整性

四份 raw 均逐文件匹配固定 commit 的 Git blob ID；SHA256：

| dataset | records | SHA256 |
|---|---:|---|
| Mohammad16 | 1,761 | `d093a3b0c53aa90d0626cc277a65a558c538ecbeb4d1cda091f02aad134588bc` |
| Mohammad19-1 | 4,147 | `acc8c3adc9290611a6dc84049c10345428f752f0f62ed7069ed1ac3e9105f9a5` |
| Mohammad19-2 | 4,147 | `e11f552ef958a381d1aec9a6d12f8e850d050fe001c31243491e08865b65cef1` |
| Subtelny14 | 5,614 | `d982f6d8c14ba309ce26e29c8d81793df190b11d063c1333878d3dc6c0efa118` |

参考目录：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/raw/reference/`。

| file | bytes | SHA256 |
|---|---:|---|
| `ecoli_cds.fna.gz` | 1,479,753 | `8b7b48b7b905313082141db4b77807b7aafebca7a5c40bbd42832baacd1cfd9b` |
| `ecoli_protein.faa.gz` | 902,395 | `283c91ff66d0597f2488fd1c00ad40f8d0a0b37a92f981b6148d75fa4a934896` |
| `yeast_cds.fna.gz` | 3,026,445 | `462f7658206ed614caeb045c54f3a3fa8ee7f176a88269155de851bbb8834f6a` |
| `yeast_protein.faa.gz` | 1,848,181 | `43b97707ae1a08a4b30c200aba6e5c39be47c674321b096478065a2400b1494e` |
| `orf_trans_all.fasta.gz` | 2,689,634 | `17e8b47e1ae23178c6000fbc4ab548f102d1b250ef9dff5d811feb3f03dd2c5b` |

缺失版本化蛋白通过 NCBI E-utilities 精确 accession 批量补回：请求 43、返回 43、unresolved=0。`ecoli_protein_supplement.fasta` 为 17,876 bytes，SHA256=`cab89eeb1533ce53aef6091e3996356432cd3cd8972929bf081144749e475325`。生产合并主参考和 supplement 时，重复 key 的序列冲突会直接报错。

## 3. QC 口径

- source accession 支持直接 `NP_`、`YP_`、`WP_` 及真实 lcl header 中的 protein_id；不再把直接 YP 记录误判为缺失 key。
- 每个 source index 保留一条 all-QC 记录；重复 key 不被字典静默覆盖。
- 官方 positive 口径为 count>0.5；严格 coverage 为>0.6；positive-mean normalization 只使用 positive positions 的 count mean。
- 检查参考蛋白精确翻译、alternative start、终端 stop、内部 stop、duplicate source key、有效归一化和有限值。
- clean 只保留无排除原因且 source key 唯一的记录；排除原因保存在 all-QC，不用沉默过滤掩盖原始异常。
- Mohammad19 两批均有重复 key `NP_417367.1`：source index 2723/2724 对应不同 CDS，两条都在 all-QC 保留并都从 clean 排除。

## 4. v2 真实结果

production 目录：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/clean/ribomimo_v2/`。

| dataset | raw | coverage pass | reference exact | alternative start | clean |
|---|---:|---:|---:|---:|---:|
| Mohammad16 | 1,761 | 1,179 | 1,756 | 167 | 1,175 |
| Mohammad19-1 | 4,147 | 1,427 | 4,138 | 387 | 1,423 |
| Mohammad19-2 | 4,147 | 1,599 | 4,138 | 387 | 1,595 |
| Subtelny14 | 5,614 | 3,921 | 5,609 | 0 | 3,916 |
| **total** | **15,669** | **8,126** | **15,641** | **941** | **8,109** |

artifact SHA256：

- `ribomimo_all_qc.jsonl.gz`：`e8a159490e1277fdb67119c0df55eb4e5b086f619cb37ecb1036047b16ccdd5f`。
- `ribomimo_clean.jsonl.gz`：`4ea56f898d4126b8a258ffb4f0d75f6272199bcb338b9c22f877329c2cf0a902`。
- `qc_summary.json`：`1f9c5bc42bdc4fde937b2b091967fc50f27d6e09dbc22c69189e54456a977b8b`。

Mohammad19 配对：shared unique keys=4,145；identical CDS pairs=4,145；both-clean pairs=1,385。

- 双 clean：profile Pearson 中位数 `0.6146305006034896`，Spearman 中位数 `0.5834616123762902`，log1p total-count Pearson `0.983748297195987`。
- 全部 identical pairs：有效 profile correlation=4,049；log1p total-count Pearson `0.9831574589558024`。
- profile 相关性只在有效归一化 profile 上计算；total-count 相关性在全部有限 total-count 配对上计算。两个分母不得混用。

这些是不同 GSM 样本的重现性诊断，不是模型性能，也不证明技术/生物学重复属性。

## 5. 独立复核与失败修正

最终 `ribomimo_independent_verification.json`：**13/13 PASS**。检查包括 raw SHA、record ID 唯一性、clean 子集、四数据集逐行 raw recompute、精确 clean 集合、all-QC 排除原因、翻译/density、replicate 和 artifact SHA。

开发中保留并修正了三类真实格式/口径问题：

1. Mohammad16 CDS/count 行统一带行尾 tab；Subtelny14 密码子字段需逐密码子 strip。
2. NCBI FAA 不写末端 `*`，SGD 参考可能写；生产蛋白统一去末端终止符，同时单独检查 CDS 终端和内部 stop。
3. verifier 初版曾把 total-count 相关性限制在 profile-valid 配对，与生产口径不同；最终显式分离配对分母后 PASS，未放宽容差。失败报告保留为 `ribomimo_independent_verification_v1_fail.json`。

首版 v1 production 把直接 YP header 误标为 missing key，Mohammad19 每批影响 223 条；v1 位于 `clean/ribomimo_v1/`，仅作诊断，未验收、未写入 PPT。

## 6. 复现命令

```bash
cd /home/codonflow-a8-rk
PY=/root/miniconda3/envs/codonflow/bin/python
BASE=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03

$PY -m pytest -q \
  scripts/tests/test_a8_rk03_download.py \
  scripts/tests/test_a8_rk03_ribomimo_qc.py

$PY -m scripts.a8_rk03_ribomimo_qc \
  --raw-dir "$BASE/raw/ribomimo" \
  --reference-dir "$BASE/raw/reference" \
  --ecoli-protein-fasta "$BASE/raw/reference/ecoli_protein.faa.gz" \
  --ecoli-supplement-fasta "$BASE/raw/reference/ecoli_protein_supplement.fasta" \
  --yeast-protein-fasta "$BASE/raw/reference/yeast_protein.faa.gz" \
  --output-dir "$BASE/clean/ribomimo_v2"

$PY -m scripts.a8_rk03_verify_ribomimo \
  --raw-dir "$BASE/raw/ribomimo" \
  --reference-dir "$BASE/raw/reference" \
  --clean-dir "$BASE/clean/ribomimo_v2" \
  --repo /home/codonflow-a8-rk \
  --output /home/codonflow-a8-rk/audits/20261118/RK03/ribomimo_independent_verification.json
```

注意：production 命令会重写同名 v2 输出。若只需复核，保留现有冻结 artifact，仅运行独立 verifier；新实验必须使用新目录，不能覆盖旧结果。

## 7. PPT 与交接

- 在线稿：<https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g>。
- 独立 13/13 PASS 后才追加第 63 页 `pgN`；revision 24→25，最终 63 页。
- `ppt_verification.json` 为 PASS：前 62 页 slide ID 与语义 XML 不变；第 62 页只有末尾空白序列化差异；新页关键文字/数字全部回读。
- `docs/handover/tasks.md`、`experiments/REGISTRY.md` 和 `docs/handover/HANDOFF_A8_RK_20261118.md` 已同步更新。

## 8. 尚未完成

- VeloHARMO E. coli processed matrix 与官方 loader 已完成 bounded 验收，见第 11 节；Pseudomonas、Drosophila、human、yeast processed matrices 仍缺失，不能宣称五物种数据齐全。
- RNARL 21 文件全量行级 QC 与 finalization 已完成，见第 10 节；Zenodo 描述、论文 Methods 与实际 pair-table 列的来源口径仍不支持天然 CDS、lambda 或功能标签声明。
- CodonTransformer 全量自然序列 QC 已完成，见第 9 节；该子项仍不提供功能标签、功能训练/OOD 或模型性能授权。
- UTR–CDS 映射、raw-read/P-site 独立重比对、长度/GC/CAI/MFE/EFE/宿主/蛋白簇完整分布报告仍 pending。
- 本结果不授权功能训练，不构成功能 OOD、机制增量、生成器、SOTA 或前瞻湿实验结论。

## 9. CodonTransformer 全量自然序列 QC（bounded 完成）

固定来源为 Zenodo <https://zenodo.org/records/12509224> 与 HF mirror commit `29e564325d09a650b59f061a4e69a13d8e3ea1e4`。最终 raw 为 4,652,159,854 bytes，SHA256=`b319f975f4cd9814bf111a59b80000c001987abf33f3e52e77c4d96d434b4fa9`；`codontransformer_download_manifest.json` 为 complete，1 record、0 failure。

全量结果：

- raw/clean rows=`1,001,197 / 449,655`；raw/clean organisms=`164 / 40`，publisher-reported 1,001,197 rows 与 164 organisms 精确一致。
- 排除原因计数：accession/coordinates missing=546,395，invalid GeneID=34,929，start not ATG=56,137，accession coordinate length mismatch=70。原因可在同一行重叠，不可相加解释净排除数。
- fine_tuned True/False=`45,875 / 955,322`；duplicate DNA rows after first=18,366、keys=14,844，全部为跨 organism 重复，未静默删除。
- clean protein length 中位数=427 aa（含 stop），GC 中位数=`0.48171368861024033`。
- 生产目录：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/clean/codontransformer_v1/`。
- all-QC/clean/QC summary SHA256 分别为 `3f675500147820efa53718e5896f4580ecd50639ecbe98557a01bb5c39656b2a`、`4ce3999f10319d858c8d1c11402d74253393cf22f6e8eeb9fe519cdadb97f694`、`2943c0c99a717db20232ddf7234f7a91b083841b074e3024508b144df8bf7c27`。

`codontransformer_independent_verification.json` 为 **8/8 PASS**，不导入生产模块，从 raw 逐行重算翻译、token、accession 坐标、clean 精确集合、计数、重复、分布和 artifact SHA；最大数值差=0。`codontransformer_finalization.json` 为 **PASS**，确认 `bounded_natural_sequence_distribution_ready=true`、`functional_training_authorized=false`、`functional_ood_claim_authorized=false`。

该子项只授权 bounded 自然 DNA–protein 序列分布使用，不提供功能标签、宿主匹配 CAI、训练模型、功能 OOD、生成质量或 SOTA 证据。结果已写入既有在线 deck 第 67 页（`pgy`，revision 29）；回读确认前 66 页 slide ID 和语义 XML 均未改变，核验记录为 `codontransformer_ppt_verification.json`。

报告中的 `config_sha256=01a20b19…` 是全量运行时的配置快照；后续 commit `895458f1` 只激活 RNARL 21 文件的 expected_bytes，未改变 CodonTransformer source record、raw bytes 或 raw SHA。独立行级 QC 不等于重新下载并核对每一条 NCBI accession。

复现命令：

```bash
cd /home/codonflow-a8-rk
PY=/root/miniconda3/envs/codonflow/bin/python
BASE=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03

$PY scripts/a8_rk03_codontransformer_qc.py \
  --config configs/a8_rk03_sources.json \
  --raw "$BASE/raw/codontransformer_training/dataset.csv" \
  --output-dir "$BASE/clean/codontransformer_v1" \
  --audit audits/20261118/RK03/codontransformer_qc.json

$PY scripts/a8_rk03_verify_codontransformer.py \
  --config configs/a8_rk03_sources.json \
  --raw "$BASE/raw/codontransformer_training/dataset.csv" \
  --qc-dir "$BASE/clean/codontransformer_v1" \
  --audit audits/20261118/RK03/codontransformer_independent_verification.json \
  --production-script scripts/a8_rk03_codontransformer_qc.py
```

production 会写同名输出；复核时保留冻结 artifact，只运行独立 verifier，新实验必须使用新目录。大型 raw/all-QC/clean 均在 `/teams`，Git 只提交小型审计与 manifest。

## 10. RNARL 全量 pair-table QC（bounded 完成）

固定 Zenodo 记录 <https://zenodo.org/records/15486992>，21 个 final 文件精确合计 714,327,390 bytes。正式生产目录为 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/clean/rnarl_v2`。

- raw/clean=`260,754/256,578` rows，clean pairs=128,289；pair groups=130,377，pair-structure-pass groups=130,287，pair-pass groups=128,311。clean pair 数比 pair-pass groups 少 22，对应 raw 跨 split exact-CDS 22 keys/44 rows 的整对排除。
- raw protein ID/protein sequence overlap=0；clean exact CDS/protein sequence overlap=0。
- 首次独立 verifier 按原始 CSV 行序 zip，与生产按 protein-pair 组输出不一致，真实 FAIL 6/8；recovery v3 FAIL。两份失败均保留。v2 改用唯一 `record_id` 精确连接、clean 精确 ID 集合和 `1e-9` 分布容差，独立 **8/8 PASS、max_numeric_delta=0.0**。
- `rnarl_finalization_recovery_v4.json` 为 **10/10 PASS**，重算 raw bytes/MD5、两份 manifest、生产计数、v2 报告、artifact hashes，并流式重扫 clean pairs 和跨 split overlap。
- 证据 commit=`d3f18124f97fc7c9f3bf9c9fcb929b5350939971`。只授权 publisher-provided LinearDesign-like pair table QC；天然 CDS、lambda、UTR/raw-read、功能训练/OOD、官方模型和 SOTA 均未授权。
- 在线主稿第 70 页=`pgf`，revision=32；`rnarl_ppt_verification.json` 确认前 69 页 slide ID 与语义 XML 不变。

复核命令（production 会写同名输出，常规复核只运行 verifier/finalizer）：

```bash
cd /home/codonflow-a8-rk
PY=/root/miniconda3/envs/codonflow/bin/python
BASE=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03
AUD=/home/codonflow-a8-rk/audits/20261118/RK03

$PY scripts/a8_rk03_verify_rnarl.py \
  --config configs/a8_rk03_sources.json \
  --raw-dir "$BASE/raw/rnarl_v1" \
  --qc-dir "$BASE/clean/rnarl_v2" \
  --audit "$AUD/rnarl_independent_verification_v2.json" \
  --production-script scripts/a8_rk03_rnarl_qc.py

$PY scripts/a8_rk03_finalize_rnarl_recovery.py \
  --repo /home/codonflow-a8-rk \
  --data-root "$BASE" \
  --output "$AUD/rnarl_finalization_recovery_v4.json"
```

## 11. VeloHARMO E. coli matrix 与官方 loader（bounded 完成）

固定 commit=`38b48079856aeb9d33a1b10844d77aa8f6640032`，外层 ZIP SHA256=`68b029b667029827d9c7213249eebcac32e6152d80ef7c0e24e53d8437d5a0ef`。payload 根目录为 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/veloharmo_official_38b48079856aeb9d33a1b10844d77aa8f6640032`，source 为 `/home/codonflow-a8-rk-external/VeloHARMO-38b48079856aeb9d33a1b10844d77aa8f6640032`。

- E. coli 矩阵 38,906,084 bytes，SHA256=`71008f948597daff282ccb3e124dd7e4c5b35aa92e2dbe4af43d5725d6fa740f`；raw=clean=1,170、excluded=0、duplicate gene IDs=0、numeric feature dimension=6。
- 独立 verifier 不导入生产模块，从固定 ZIP 重新解压并逐记录重算，**7/7 PASS、max_numeric_delta=0.0**；finalization **8/8 PASS**。
- 官方 loader 在 `/root/miniconda3/envs/llr_env/bin/python` 成功，torch=2.11.0+cu128；x=`[1170,1520,111]`、density=`[1170,1520,1]`、length=`[1170,1]`，length min/max=16/1520，density min/max=0/77.14354705810547，x/density 全 finite。
- 证据 commit=`34286ad4fa2cf74aaee40d7f9f1597052b6a8f1a`。只有 E. coli 矩阵和 E. coli/yeast 权重；Pseudomonas、Drosophila、human、yeast processed matrices 缺失。没有训练、交叉验证、论文指标、功能 OOD 或 SOTA。
- 在线主稿第 69 页=`pgx`，revision=31；`veloharmo_ppt_verification.json` 确认前 68 页 slide ID 与语义 XML 不变。

复核命令：

```bash
cd /home/codonflow-a8-rk
PY=/root/miniconda3/envs/codonflow/bin/python
BASE=/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03
ARC="$BASE/veloharmo_official_38b48079856aeb9d33a1b10844d77aa8f6640032.zip"
PAY="$BASE/veloharmo_official_38b48079856aeb9d33a1b10844d77aa8f6640032"
SRC=/home/codonflow-a8-rk-external/VeloHARMO-38b48079856aeb9d33a1b10844d77aa8f6640032
AUD=/home/codonflow-a8-rk/audits/20261118/RK03

$PY scripts/a8_rk03_verify_veloharmo.py \
  --archive "$ARC" --source-dir "$SRC" --payload-dir "$PAY" --audit-dir "$AUD"
/root/miniconda3/envs/llr_env/bin/python scripts/a8_rk03_veloharmo_loader_smoke.py \
  --source-dir "$SRC" --output "$AUD/veloharmo_official_loader_smoke_reproduction.json"
$PY scripts/a8_rk03_finalize_veloharmo.py \
  --archive "$ARC" --source-dir "$SRC" --payload-dir "$PAY" --audit-dir "$AUD"
```

loader 的 `codonflow` 环境首次缺 `sklearn` 失败作为环境事实保留，未修改官方源码；复用已有 `llr_env` 只证明 processed-matrix loader 可运行。
