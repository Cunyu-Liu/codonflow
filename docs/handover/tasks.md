# CodonFlow Tasks（A8-RK · 一个月真实功能与 SOTA 执行版）

> 生效日期：2026-11-18，A8-RK v2。主合同：`docs/handover/spec.md`；完整科学路线：根目录 A8 文档。
> 旧 2×2 仅归因 frozen r5，不再阻塞 CodonFlow-RK。任何外部数据须实际下载解析后才能标为 available。

## 0. 已完成并可继承的工作

- [x] D4/D5、calibration、unique18、untouched24 资产与精确/操作性同源隔离复核。
- [x] FULL/EDIT r5 收敛与 G1 非退化检查。
- [x] G2 324/324 No-Go；T3.7/T3.8 learned-hill 开发诊断及成本记录。
- [x] LinearDesign/GEMORNA/codonGPT 等 54/54 实际输出重评；不是统一排名。
- [x] 2026-11-18 远端 HEAD `012338aa`、干净工作树、核心文件哈希核对；历史回归 228 passed、1 skipped。
- [x] 识别旧路线根因：目标错位、反馈混杂、无功能监督、普通 codon Transformer、baseline 不全。
- [x] RK-01：冻结六个来源、环境 manifest、数据与 run registry；隔离分支 `a8-rk`，未改写主工作树。
- [x] RK-02：8 份官方原始附件完成 SHA 登记，生成 25,420 行统一长表；11/11 测试及独立 39/39 检查通过。Kudla 逐条序列—表达表未获得，实际为 0 行并记录 `unavailable`；RK-02 时点未创建 split 或训练。
- [x] RK-04 核心功能 split：Boël 按 5,554 个 operational homology clusters 划分 train/dev/test=5,079/635/634 行；全部 19,072 个 MAGE rows 与 13,569 个 construct-signature groups 冻结为 untouched。六类跨 split 重叠均为 0，独立 33/33 checks、组合 19/19 tests 通过；commit `99df1d96e041e1f78b67e69210276df66d7b5f6f` 已推送。长度/GC OOD 与 train-only 归一化/校准仍 pending，未授权功能训练。
- [x] RK-06 bounded 子项：dense-v2/actual-set 评价器与 synthetic 10/10 审计；C01H6.8b.1 seed0 五方法 286 条 raw CDS 复核，最终 44/44 PASS，与 A7 最大差异 0。代码 `db3e1667` / `56a62b44` 已推送，第 61–62 页 PPT 已记录。真实 dense 轨迹、全记录矩阵和统一成本主比较仍 pending。
- [x] RK-03 bounded RiboMIMO 子项：四份固定官方矩阵与五份参考 FASTA 完整核验，43/43 个缺失版本化蛋白精确补回；v2 production 共 15,669 raw / 8,109 clean，独立 raw-source recompute 13/13 PASS。生产修复 commit `81c0cddf`、最终审计/交接 commit `73f93af7` 已推送，第 63 页 PPT 已记录。该子项只验收作者处理后的 A-site count 与参考蛋白 QC，不覆盖 raw-read/P-site 重比对、UTR 或功能 OOD。
- [x] RK-03 bounded CodonTransformer 全量自然序列子项：固定 raw 为 4,652,159,854 bytes，SHA256=`b319f975…`；全量 1,001,197 rows / 164 organisms 与 publisher scope 一致，clean=449,655 rows / 40 organisms。finalization PASS，独立 raw-source verifier 8/8 PASS，clean 表可作有边界自然序列分布输入；不代表功能标签、功能训练/OOD、宿主匹配 CAI、模型或 SOTA 证据。RNARL 全量、VeloHARMO 物种覆盖和 RK-03 其他维度仍 pending。PPT 第 67 页（`pgy`，revision 29）已记录并回读。
- [x] RK-07 bounded Boël 跨蛋白代理诊断：RK04 train/dev/test=`5079/635/634` 全量 frozen test 完成，独立 raw-source verifier 9/9 PASS，契约测试 10/10 PASS。production commit `a7250465`、verifier/audit/README commit `e59cc5b6` 已推送；PPT 第 64–65 页（`pgt`/`pgX`，revision 27）已记录并回读。test 上五个 paired Spearman 比较经 Holm 均不显著；只证明有限且不稳定的跨蛋白信号，不关闭固定蛋白同义 E1、RK-G1、功能 OOD 或生成器门槛。
- [x] RK-05 bounded RNARL 固定源码可用性审计：commit `88428e5d…` 的 10 份源码/示例逐字节匹配，真实 import/constructor smoke 与独立 AST 16/16 PASS 共同确认 actor 缺 `esm2_dim/device` 和 `evaluate`、reward 缺 `device`、GRPO 缺 9 个调用方法及 2 个 main globals。代码/负结果 commit `1401f63c` 已推送，PPT 第 66 页（`pgL`，revision 28）已记录。未执行完整训练/生成或复现论文指标，不授权主比较，也不证明 RNARL 方法无效。
- [x] RK-05 bounded ID3 官方 quick-test：固定 ID3=`ed23037e…`、DeepRaccess=`1a37235e…`，CPU 上 O15263 的 3 constraints × 4 variants 共 12 runs 全部完成，2 iterations、seed=42。生产 43/43 PASS；独立 v2 为 112/116，保留 `cpc-01/11` initial/best 四项失败；12/12 final 序列与分数通过，finalization 11/11 PASS。10 组全指标可用、2 组仅 final 可用，受影响 initial/best/improvement/trajectory 与 best 聚合排除。证据/复现 commit `51fcda9f95a7770cf1a4ee0f1e8b2956eab719a1` 已推送，PPT 第 68 页（`pgC`，revision 30）已记录；不构成 full-12x12、多 seed、主 baseline 排名或 SOTA。
- [x] RK-03 RNARL 21 文件下载完整性子项：主 recovery manifest 与独立 reverify manifest 均为 complete、21 records、0 failures，合计 714,327,390 bytes；独立 raw-source verifier 8/8 PASS，逐文件重算 bytes/MD5/SHA256。2 个 checksum-failed part 以唯一 rejected 名称保留，坏字节与正式 final 不同；旧 `rnarl_finalization.json` 的 FAIL 原样保留。commit `b2661456d14eca0f08c70d9a0d71a489e5b2dde7` 已推送。该子项仅为 `PASS_DOWNLOAD_ONLY_QC_PENDING`，全量行级 QC、独立 QC verifier、clean-pair 授权和新 finalization 仍 pending。
- [x] RK-18 bounded A8 工作稿自动生成：`paper/CodonFlow_preprint_A8.md` 由冻结 JSON 生成，A7 未改；新增数据、RK04、RK07、ID3/RNARL baseline 与证据哈希章节，论文 SHA256=`fcbb7f3a823fe5d91a678f3ffd5ff708f0772423feefe1232690fa01a24aae80`。独立 verifier 11/11 PASS，commit `b2661456d14eca0f08c70d9a0d71a489e5b2dde7` 已推送。仍是不可提交 working manuscript，RNARL 正式 QC、机制、模型、主 baseline、OOD、生成器与湿实验未闭合。

- [x] CF-A8-RK03-RNARL-FULL：21 文件全量生产 QC 得 260,754 raw / 256,578 clean / 128,289 pairs；raw 22 个 exact-CDS 跨 split key、44 行按整 protein pair 排除。修正 verifier 的 record_id 连接契约后独立 8/8 PASS、max_numeric_delta=0.0；recovery v4 finalization 10/10 PASS。历史 v1 FAIL 6/8、recovery v3 FAIL 全保留。仅为 LinearDesign-like pair table；不授权天然 CDS、lambda 分层、功能训练/OOD、官方模型或 SOTA。证据：`audits/20261118/RK03/rnarl_finalization_recovery_v4.json`；commit `d3f18124f97fc7c9f3bf9c9fcb929b5350939971`。
- [x] CF-A8-RK03-VELOHARMO-ECOLI：固定 commit `38b48079856aeb9d33a1b10844d77aa8f6640032`，处理 E. coli 矩阵 1,170 raw=clean、0 duplicate IDs、6 numeric features；独立 7/7 PASS、max_numeric_delta=0.0，finalization 8/8 PASS。官方 loader x=[1170,1520,111]、density=[1170,1520,1]、length=[1170,1]，全 finite；仅 loader，不是训练或性能。缺 Pseudomonas/Drosophila/human/yeast processed matrices，五物种、raw-read 重比对、交叉验证、OOD、SOTA 均未闭合。commit `34286ad4fa2cf74aaee40d7f9f1597052b6a8f1a`。
- [x] CF-A8-RK03-PPT-RNARL-VELOHARMO：既有在线主稿依次追加第 69 页 VeloHARMO `pgx`（revision 31）和第 70 页 RNARL `pgf`（revision 32）；每次写后回读确认所有旧页 slide ID 与语义 XML 不变、新页关键文本和备注完整。PPT verification 已归档。
- [x] CF-A8-RK18-WORKING-MANUSCRIPT-V2：A7 保持不变；A8 生成器纳入 RNARL/VeloHARMO 正式证据及哈希锚点，独立 13/13 PASS；A8 SHA256=`f7ea820b98ab946f9f12b6fc28f2095907fd88b4c7346e77870ec87552735e7a`。仍为 non-submittable working manuscript。
- [x] CF-A8-RK05-LINEARDESIGN-BOUNDED：固定官方 commit `f0126ca89a8b853088b4bccfd2cc8c378d3678be` 干净构建并通过 README 样例；C01H6.8b.1 的 λ=`0/0.5/1` 三条唯一同义 CDS 完成，官方总耗时 24.321617 s。独立 10/10 PASS、max_numeric_delta=0.0，finalization 8/8 PASS。v1 默认 `dangles=2` scorer gate FAIL 保留；v2 显式 `dangles=0` 核对官方 MFE，并保留默认 `dangles=2`。CDGB 未建立官方执行证据；全 actual-set、dense budget、主比较、OOD 和 SOTA 未闭合。
- [x] CF-A8-RK18-WORKING-MANUSCRIPT-V3：A8 生成器新增 LinearDesign 固定源码、三 λ 指标、双 dangles、v1 retained failure 和证据哈希；A7 未改。A8 SHA256=`d779ad4dd3d9d971378aa82fc1366e6eaa7e53a74a49bce1a5b227e609b088dd`，独立 **14/14 PASS**；仍为 non-submittable working manuscript。
- [x] CF-A8-RK05-LINEARDESIGN-PPT：既有在线主稿追加第 71 页 `pgB`、revision=33，记录固定源码、三 λ 官方 MFE/CAI/耗时、双 dangles、v1 retained failure、10/10 独立 PASS 与 8/8 finalization。写后回读确认前 70 页 slide ID 与语义 XML 全部不变，新页关键文本、边界和 4 段备注完整。
- [x] CF-A8-RK05-CDGB-SOURCE：候选 CDGB 题名/URL 完成九条公共 API 查询并冻结 raw JSON 与 bytes/SHA。`10.1093/bib/bbaf332` 实际对应 **Multimodal zero-shot learning of previously unseen epitranscriptomes from RNA-seq data**（ExpressRM，26(4)），与 CDGB 候选题名直接冲突；学术精确题名匹配=0，GitHub 精确查询=0+0，宽查询=14 但不能建立官方归属。独立 8/8 PASS、finalization 6/6 PASS、8/8 tests PASS；commit `ea806ff10f331ae2831cef9c9d15ddb2c3252902`。未建立官方 repo/commit/build/execution，序列和性能输出均为 0；不宣称方法无效或实现不存在。
- [x] CF-A8-RK18-WORKING-MANUSCRIPT-V4：A8 新增 CDGB 候选身份冲突、九查询、独立复核与零执行边界；A7 未改。A8 SHA256=`cc74dee890b1cf813ece45b9d62f32948046b68272915747f13c7d23fbc8df59`，独立 **15/15 PASS**；仍为 non-submittable working manuscript。
- [x] CF-A8-RK05-CDGB-PPT：既有在线主稿追加第 72 页 `pgR`、revision=34，记录 DOI 冲突、学术/GitHub 查询、8/8 独立 PASS、6/6 finalization 与零执行边界。独立写后验证 **10/10 PASS**，前 71 页 slide ID 与语义 XML 全部不变，新页表格、关键文本和 4 段备注完整。
- [x] CF-A8-RK05-ENSEMBLEDESIGN-BOUNDED：固定官方 commit `cd9324f9574a754063d421e76670bc9fd7555324` 和归档；官方 example v2 为 3 records/6 runs/4 unique CDS，C01 为 1 record/2 runs/2 unique CDS，翻译和官方 EFE 均经独立重算。example/C01 独立 **13/13 + 13/13 PASS**、单元测试 **11/11 PASS**、finalization **11/11 PASS**；v1 stop-gate 失败与 build reporting recovery 均保留。commit `5ba0a8848ccf701f5e070b61fe357ca6d05eeb3c`。这不构成 matched LinearDesign 比较、dense budget、主 baseline 矩阵、功能 OOD 或 SOTA。
- [x] CF-A8-RK18-WORKING-MANUSCRIPT-V5：A8 新增 EnsembleDesign example/C01 结果、EFE 口径、双独立复核、finalization 和五份证据哈希；A7 未改。A8 SHA256=`505c42f61e21ab1cb03f54ee661adf005f6fa996e17ffec5ae6ed481fe2f8eca`，独立 **16/16 PASS**；仍为 non-submittable working manuscript。
- [x] CF-A8-RK05-ENSEMBLEDESIGN-PPT：既有在线主稿追加第 73 页 `pgO`、revision=35，记录固定源码、example/C01 EFE、bounded 参数、双 13/13 独立 PASS、11/11 finalization、v1 retained failure 和 EFE≠LinearDesign MFE。独立写后验证 **10/10 PASS**，前 72 页 slide ID 与语义 XML 全部不变。commit `9986974ac46cc65aaf0708e509e9ad5ff2cfb2af`。
- [x] CF-A8-RK03-MAGE-DEVELOPMENT-NESTED-CV：固定 infA、rich medium、positions 10–71 的原 train+dev=131 constructs 完成 5-fold outer/4-fold inner nested CV，原 33 test constructs 在记录表、fold、特征、拟合、预测和指标中完全排除。full−intrinsic ΔRMSE=`+0.000094928`，95% CI=`[-0.001417567,0.001456402]`；full−local-MFE ΔRMSE=`−0.000155645`，95% CI=`[-0.000999395,0.000600285]`；四项 Holm p=1.0，两个敏感性 seeds 未满足方向一致性。最终 `DEV_NO_GO_TEST_UNTOUCHED`，独立 raw-source **96/96 PASS**、全部数值差 0，finalization **30/30 PASS**；v1 NO-GO 不改写，无 test/transport/RK-G1/生成器授权。A8 v26 新增 6.22，论文核验 **54/54 PASS**（候选事实 29/29），v25 可逐字恢复；生产协议与生产器 commit=`b6f9f09c9873cab7af4d8b321f2bd9a452fbb8d7`。
- [x] RK03-REMAINING（bounded source-feasibility）：完成 UTR–CDS 映射/raw read 或 P-site 独立重比对可行性报告、VeloHARMO 其余物种真实可获得性追踪；最终状态为 `FEASIBILITY_CLOSED_NOT_FULL_REMAP`。这不代表 full UTR–CDS remap、四物种信号 matrix、五物种模型覆盖或完整 RK03 main 已完成。
- [x] CF-A8-RK03-MAGE-DEVELOPMENT-PPT：既有在线主稿追加第 **102 页 `pgj`（revision 64）**，以三 KPI、四行主对比、设计与独立复核侧栏记录 nested-development NO-GO、敏感性方向失败和 test/protein-OOD/普遍证伪边界。候选写前 **52/52 PASS**，整稿写后 **79/79 PASS**；前 101 页语义 XML 完全不变，新页与候选语义一致。`--index` 参数拒绝、标题/徽章 3 px 交叠 lint 和初版字段映射 78/79 均保留并修正；未绕过 lint。PPT 仅记录已核验结果，不产生 test/transport/RK-G1/生成器结论。

以上完成项不证明真实功能、机制、外部 SOTA 或新架构有效。

## Phase 0：数据与 baseline 真相（Day 0–4，RK-G0）

### RK-01 冻结来源与建立数据台账

- **任务**：记录远端/本地 commit、关键 SHA、环境；为每个新数据源建立 accession/release/URL/license/raw-clean SHA 条目。
- **输出**：source/environment manifest、数据 registry、run registry 更新。
- **验收**：每个文件可追溯到唯一下载与处理版本；不覆盖旧资产。

### RK-02 下载并审计真实功能数据

- **任务**：实际获取 Kudla 154 GFP、Boël Protein Data Set/6,348 实验、MAGE-seq 12,726 infA 突变及补充材料。
- **涉及**：新增 `scripts/a8_fetch_functional_data.py`、`scripts/a8_audit_functional_data.py` 与配置；原始数据只写新目录。
- **输出**：序列—测量长表、协议表、下载失败清单、raw/clean SHA。
- **验收**：样本数与论文对账；翻译、突变位置、重复、批次、单位、检出限和缺失原因明确；无法获得者保持 `unavailable`。
- **禁止**：从摘要/图中猜数值；把不公开 Dasher 数据写成训练集。

### RK-03 下载并审计机制/自然数据

- **任务**：获取 VeloHARMO 五物种 Ribo-seq 来源、RNARL Zenodo `15486992`、CodonTransformer 可用数据；保留 D4/D5。
- **输出**：UTR–CDS/蛋白映射、Ribo QC、自然数据分布报告与 SHA。
- **验收**：覆盖/映射/重复 QC 完整；长度/GC/CAI/MFE/EFE/宿主/蛋白簇分布可复算。
- **当前进展（2026-11-18）**：RiboMIMO v2 all-QC/clean 为 15,669/8,109 条，独立 13/13 PASS，详见完成项；Mohammad19 双 clean 配对相关性仅作重现性诊断。CodonTransformer 固定 raw=4,652,159,854 bytes、SHA256=`b319f975…`，全量 raw/clean=1,001,197/449,655 rows、organisms=164/40，独立 8/8 与 finalization PASS，已有第 67 页记录。RNARL 已修正 RNA 字母、终端 `*`、整对泄漏排除和 clean-pair 授权口径；21 文件精确字节合计 714,327,390，v2 partial smoke 仍为 15 文件、33,924 raw/33,510 clean，不能替代全量。坏 part/final 恢复补丁已部署权威工作树并 11/11 tests PASS；满尺寸校验失败的残片或已存在 final 均唯一命名隔离后从零重下，不删除证据。前序 part 修复 commit=`f0db530b2564dbc172ed78eebd610479c4ef7a06`，本轮 final 防御与 pre-recovery 审计另随文档提交。恢复完成后实物为 21 个 final、0 个活动 part、2 个 quarantine；主 recovery/reverify manifests 均 complete，独立下载 verifier 8/8 PASS，commit=`b2661456d14eca0f08c70d9a0d71a489e5b2dde7`。旧 FAIL finalization 保留；全量行级 QC、独立 QC verifier 和新 finalization 仍 pending，clean pairs 尚未授权。VeloHARMO 固定树仅列 14 个条目和两份 E. coli ZIP 条目，五物种矩阵完整性不成立。UTR–CDS、raw-read/P-site 重比对和完整自然分布报告仍 pending；RK-03 与 RK-G0 不关闭。

### RK-04 建立无泄漏功能与 OOD 划分

- **任务**：按 exact CDS/protein/ID、同源簇、来源蛋白、assay/研究分组；同一蛋白变体不得随机跨 split。
- **涉及**：新增 `scripts/a8_build_rk_splits.py` 与测试。
- **输出**：train/dev/test、蛋白 OOD、研究 OOD、长度/GC OOD、功能 untouched、泄漏报告。
- **验收**：所有跨 split 重叠为 0 或有明确处理；RSCU/归一化/校准仅 train 拟合；untouched 冻结。

### RK-05 强 baseline 可运行矩阵

- **任务**：按任务跑通 LinearDesign、EnsembleDesign、RNARL、ID3、CodonTransformer、VeloHARMO 官方 smoke；逐步补 CAGFN、codonGPT、GEMORNA、COformer、CHARMING、RiboMIMO/iXnos/ROSE。
- **输出**：官方 commit/环境/命令/输入/输出/默认与最佳配置/成本/失败原因矩阵。
- **验收**：关键直接 baseline 有真实输出；无法运行者标明不可比，不用弱替代冒充。
- **当前进展（2026-11-18，RNARL bounded availability）**：官方固定源码 `88428e5d24fb2a16c29cc4dfbbfef51bd990a3d5` 的 10 个文件与 Git blobs 一致，三份 example 各 9 行。首次真实 smoke 被过新的 hub 阻断；只在 `/home/codonflow-a8-rk-smoke/rnarl_python_deps` 隔离安装 `transformers==4.46.3`、`huggingface-hub==0.27.0` 后，三模块可导入，但精确构造/接口仍失败：actor 缺 `esm2_dim/device` 且无 `TrainingManager.evaluate`，reward 缺 `device`，GRPO 缺 9 个被调用方法、`load_and_preprocess_data/save_model`，并读取未局部赋值的 `rewards`。独立 verifier 不导入 smoke 模块，按 AST 重算，16/16 PASS；复现说明与两次真实记录见 `audits/20261118/RK05/`。结论是公开快照不能直接形成可比 baseline，不是方法无效结论；完整训练、生成、论文指标和主比较仍未完成，修复实现必须标为新 baseline。
- **当前进展（2026-11-18，ID3 bounded quick-test）**：固定 ID3 commit=`ed23037e5a74ca10953954c425ac736fb89578a8` 与 DeepRaccess commit=`1a37235e31e1d5a7d5e2bfb705e3a00f1cdcaa9c` 已物化并独立哈希，官方 quick-test 在 CPU 上完成 12/12 runs，official total/average wall time=417.591162/34.799264 s。独立 verifier 从离散序列重算，12/12 final 通过、10 组全指标通过；`cpc-01/11` 因固定源码 CPC 未把 `beta` 传给 CodonPsi、runner 又假定 STE 软硬分数一致，四项 initial/best 检查保留失败。12 组 best sequence 均与独立离散 argmin 一致，final mean/min/max=`2.5201897621/1.9028095007/3.2401762009`。finalization 11/11 PASS，commit=`51fcda9f95a7770cf1a4ee0f1e8b2956eab719a1`，PPT 第 68 页 `pgC`、revision 30。仅为单蛋白、2 iterations、单 seed quick-test；CPC×1 受影响历史与 best 聚合不得进入比较，RK-05 强 baseline 矩阵仍未闭合。
- **当前进展（2026-11-18，LinearDesign bounded official smoke）**：固定 commit `f0126ca89a8b853088b4bccfd2cc8c378d3678be` 的 codeload ZIP（174,011 bytes，32 members，CRC PASS）已在干净目录用 `g++ 9.4.0` 构建，官方 README 样例一致。C01H6.8b.1（135 aa）在 λ=`0/0.5/1` 得到三条唯一同义 CDS，官方 MFE=`-270.60/-269.20/-265.20 kcal/mol`、CAI=`0.761/0.791/0.820`，总耗时 24.321617373265326 s。独立 raw-output verifier 10/10 PASS、max_numeric_delta=0.0，finalization 8/8 PASS。v1 因默认 `dangles=2` 与官方 `dangles=0` 口径不同而 scorer gate FAIL，已保留 postmortem/raw output；v2 双口径记录且未放宽容差。该结果只验收单 record bounded smoke；统一 actual-set/dense/主比较/OOD/SOTA 仍 pending。
- **当前进展（2026-11-19，CDGB negative source audit）**：九条 Crossref/OpenAlex/Europe PMC/GitHub 查询均冻结原始 JSON 和 bytes/SHA；候选 URL 中的 `10.1093/bib/bbaf332` 解析为 ExpressRM 论文而非 CDGB，学术精确题名匹配为 0，GitHub 精确 CDGB 查询为 0+0，宽 codon-deoptimization 查询为 14 个其他项目。独立 verifier 8/8 PASS、finalization 6/6 PASS，commit=`ea806ff10f331ae2831cef9c9d15ddb2c3252902`，PPT 第 72 页 `pgR`、revision 34，写后独立 10/10 PASS。状态仅为 `SOURCE_IDENTITY_UNRESOLVED_OFFICIAL_EXECUTION_NOT_AUTHORIZED`；没有官方仓库、commit、build、execution、序列或性能结果，检索未命中不证明方法无效或实现不存在。统一强 baseline 主矩阵仍未闭合。
- **当前进展（2026-11-19，EnsembleDesign bounded official smoke）**：固定官方 commit=`cd9324f9574a754063d421e76670bc9fd7555324`，官方 example v2 为 3 records/6 runs/4 unique CDS、8.044502989854664 s；C01H6.8b.1 为 1 record/2 runs/2 unique CDS、52.65070143900812 s，best EFE=`-269.97 kcal/mol`。example/C01 独立 13/13+13/13 PASS，finalization 11/11 PASS，A8 v5 独立 16/16 PASS。v1 stop-gate 失败保留；EFE 不是 LinearDesign MFE，没有 matched comparison、dense budget、主矩阵、功能 OOD 或 SOTA。PPT 第 73 页 `pgO`、revision 35，写后独立 10/10 PASS，旧72页未变；科学证据 commit=`5ba0a8848ccf701f5e070b61fe357ca6d05eeb3c`，PPT 证据 commit=`9986974ac46cc65aaf0708e509e9ad5ff2cfb2af`。

### RK-06 统一评价器与成本

- **任务**：完成真实 B=1 dense AUC、实际集合 schema、原始 scorer 独立重算和单 worker 成本。
- **涉及**：`src/codonflow/eval/anytime.py`、外部重评、独立 scorer 脚本及现有 tests。
- **验收**：合成手算面积、乱序/重复/退化轴、缺失预算不补零；forward/scorer/wall-clock 全计。
- **当前进展（2026-11-18）**：dense-v2 与 actual-set 评价器完成，18 passed + 8 subtests、synthetic 10/10 PASS；raw-CDS scorer 与评价器组合测试 22 passed + 8 subtests。C01H6.8b.1 seed0 的五个外部方法共 286 条 CDS 已独立复核，最终 44/44 PASS；与 A7 raw recompute 的最大差异为 0，legacy motif raw-count 与 per-codon penalty 已按密码子数精确还原。当前仅为单记录 actual-set smoke，所有 dense 指标为 null；真实 B=1…500 轨迹、其余外部记录及统一单 worker wall-clock/forward/scorer 成本主比较尚未完成，因此 RK-G0 不关闭。

**RK-G0 通过**：真实功能数据可用且划分可靠；关键 baseline 可复现；统一指标通过测试。未通过时先修数据/协议，不训练生成器。

## Phase 1：回答机制科学问题（Day 3–11，RK-G1）

### RK-07 E1：真实变体上的代理效度

- **任务**：比较 CAI、GC、全局/局部 MFE、组合基线与功能/适应度；按蛋白/研究 OOD。
- **输出**：分 assay 效应、相关方向、增量解释、失败分层与 Fig.1 数据。
- **验收**：对照与划分一致；不复现失效则收窄动机，不选择性展示。
- **当前进展（2026-11-18，bounded cross-protein）**：Boël 不是固定蛋白同义文库，本结果不关闭本任务整体。frozen test Spearman：combined/CAI/GC/full MFE/MFE per nt/local48=`0.123239/0.002615/0.096394/0.046348/0.094988/0.077654`。combined−local48 点差=`0.045584`，95% CI=`[-0.007246,0.100501]`，Holm p=`0.351648`；五个 paired Spearman 比较经 Holm 均不显著。combined−CAI 的 CI 下界虽大于 0，但 Holm p=`0.179820`，仍非稳健胜出。top10 E=5 enrichment combined/local48=`1.031901/0.980306`，差值 CI 跨 0；GC-high 由 local48 占优，GC-low 由 CAI 占优，失败分层保留。独立 verifier 9/9 PASS，raw feature 最大差=0、prediction 最大差约 `1.33e-15`；复现命令和 SHA 见 `audits/20261118/RK07/README.md`。结论仅为有限且不稳定的跨蛋白信号；未证明简单代理失效、固定蛋白同义机制、功能 OOD、SOTA 或生成器授权。PPT 第 64–65 页已追加；65 页 revision 27 回读确认前 63 页 slide ID 与语义 XML 未变。

### RK-08 E2：最小机制预测模型

- **任务**：同一骨干分别加入 initiation、velocity、decay、pair channel；参数/训练计算匹配。
- **涉及**：新增 `src/codonflow/models/ribokinetic.py`、功能/速度 dataset 与训练脚本；先不接生成器。
- **输出**：功能与速度 OOD 主表、预测区间、去组件消融。
- **验收**：至少一个机制组合稳定优于简单代理和同骨干无机制模型；每项增量有 paired CI。

### RK-09 E3：跨层机制一致性

- **任务**：联合/分别预测 MAGE 适应度、Ribo 速度、Boël mRNA/蛋白层；在适用数据做分层或 mediation。
- **输出**：跨层一致性、结构/速度/降解消融、Fig.2 机制证据。
- **验收**：结论限定为关联，除非有干预；黑箱 reward 或 attention 图不得替代机制证据。

**RK-G1 通过**：机制组合在真实功能 OOD 有稳定增量。未通过则修数据/假设，不启动昂贵生成训练。

## Phase 2：最小 CodonFlow-RK（Day 8–18，RK-G2）

### RK-10 双分辨率约束表示

- **任务**：实现同义 simplex、固定 UTR/宿主条件、候选密码子三核苷酸展开与合法 pair channel；长序列使用稀疏/轴向交互。
- **输出**：合法率、pair 形状/掩码、长度外推、显存与速度测试。
- **验收**：蛋白/长度/stop 100% 合法；UTR–CDS 与远程 pair 可审计；不错误宣称精确 partition function。

### RK-11 多保真势与不确定性

- **任务**：接入经 RK-G1 支持的 `Φinit/Φens/v/Φdecay` 和功能头；低/中/高保真分层采样，输出不确定性。
- **输出**：各头 OOD 与校准、噪声/采样权重消融、独立功能评价协议。
- **验收**：最终功能评价不使用参与选择的同一代理充当唯一真值。

### RK-12 偏好与预算条件合法核

- **任务**：实现 `q0×exp(-βwΔΦ-βcΔcost)`、偏好/剩余预算条件和轨迹平衡/能量倾斜目标；保留 stay 与 stop 保护。
- **输出**：小状态可枚举分布/归一化测试、训练曲线、checkpoint 与配置。
- **验收**：小状态目标分布与采样一致；数学目标与代码一致，否则取消 flow 命名。

### RK-13 逐任务主结果与强 baseline

- **任务**：功能预测、速度、harmonization、accessibility、CDS 多目标分别比较最强可比方法。
- **输出**：主表、逐单位效应/CI/Holm、真实轨迹、成本与失败区域。
- **验收**：主效应及 CI 下界>0、合法率100%、外部配置公平；未赢任务标为未解决并定向诊断。

### RK-14 机制—性能对应消融

- **任务**：去 pair/initiation/velocity/decay/自然先验/偏好/预算条件；同参数与同推理成本。
- **输出**：预测与生成两侧消融对照图。
- **验收**：性能解释与 RK-08/09 机制证据一致；无收益组件删除。

## Phase 3：独立、OOD 与实用优势（Day 16–24，RK-G3）

### RK-15 untouched 与 OOD

- **任务**：冻结全部配置后一次评估 untouched24、功能 untouched、来源蛋白/研究、长度/GC 与可用宿主层。
- **输出**：独立主表、分层效应、不确定性与失败案例。
- **验收**：确认集未参与任何选择；未重复效应不写普遍泛化。

### RK-16 time-matched 与全成本

- **任务**：同硬件单 worker 比较等 scorer 与等时间；记录连续优化、生成、评分和并行成本。
- **输出**：质量—scorer—时间前沿与成本分解。
- **验收**：无隐藏 forward/scorer；等时间未赢不得称实用 SOTA。

### RK-17 真实功能回顾验证

- **任务**：对公开 held-out 变体进行候选排序和 top-k enrichment；条件允许时设计前瞻 DBTL 协议。
- **输出**：独立真实功能表、前瞻性实验设计与对照清单。
- **验收**：计划与已完成分开；无湿实验不写疗效或普遍表达提升。

## Phase 4：论文与复现（Day 21–30，RK-G4）

### RK-18 自动生成论文证据链

- **任务**：Fig.1–7、主张—证据矩阵、强 baseline 主表、机制/失败图、Discussion 边界。
- **验收**：每图回答一个科学问题；每个数字来自冻结 JSON；无计划冒充结果。
- **当前进展（2026-11-18，bounded manuscript sync）**：`scripts/a8_rk_paper_sync.py` 已从 13 份冻结 JSON 生成独立 A8 工作稿，A7 保持不变；第 3.1、3.2、6.2、6.5、8.1 节写入已验收数据/诊断/baseline 状态与证据 SHA。`scripts/a8_rk_verify_paper.py` 不导入生产模块，独立复核 source/template/output hashes、全部关键数字、四项 ID3 retained failures、RNARL 负审计及 pending/no-SOTA 边界，11/11 PASS。commit=`b2661456d14eca0f08c70d9a0d71a489e5b2dde7`；A8 仍不可提交，Fig.1–7 与科学闭环未完成。
- **当前进展（2026-11-19，V5 EnsembleDesign sync）**：生成器纳入五份 EnsembleDesign 冻结来源和哈希，新增 example/C01 EFE 表、bounded 成本、双 13/13 独立复核、11/11 finalization 和 v1 retained failure；明确 EFE≠LinearDesign MFE，未授权 matched comparison/dense/主矩阵/功能 OOD/SOTA。A8 v5 SHA256=`505c42f61e21ab1cb03f54ee661adf005f6fa996e17ffec5ae6ed481fe2f8eca`，独立 16/16 PASS；仍为 non-submittable working manuscript。

### RK-19 干净复现与交接

- **任务**：环境锁、数据/模型卡、registry、artifact SHA、干净环境测试和端到端 smoke。
- **验收**：项目标准 pytest 与关键真实运行通过；无旧 warm-start/完整 CTMC/缺失预算零填充等表述回流。

## 低成本并行遗留任务（不阻塞 RK 主线）

- [ ] r5 `proposal×feedback` 2×2，仅用于解释旧 G2/T3.8。
- [ ] G2/T3.8 dense v1/v2 并列重算与原始 scorer 分层审计。
- [ ] 外部 fixed-500 生成仅在不会挤占 RK 数据/机制/主 baseline 资源时运行；不能替代 RNARL/ID3 等新强 baseline。

## 每周决策点

1. **Week 1 / RK-G0**：数据和 baseline 是否真实存在、可运行、无泄漏？
2. **Week 2 / RK-G1**：机制是否在真实功能 OOD 有增量？
3. **Week 3 / RK-G2**：各任务是否赢最强可比 baseline，消融是否解释收益？
4. **Week 4 / RK-G3/G4**：独立与等时间是否重复，论文每个主张是否闭合？

任何未通过项保留为未完成；不得换弱 baseline、重复使用 untouched、删除失败分层或用计划文档宣称 SOTA。

## 2026-11-19 RK05 RiboMIMO cross-study OOD increment

- [x] 冻结并完成 Mohammad16→Subtelny14 RiboMIMO/ridge/constant study-OOD：1,062/117 source train/validation、3,921 target、exact CDS overlap=0，主 seed=1234，敏感性 seeds=2345/3456，target 在 source 训练与 alpha 选择后才评估。10/10 tests、独立 203/203、finalization 30/30 通过。
- [x] 两项冻结主终点均显著有利于 ridge：ΔTB-MSE=1.179641679，95% CI=[1.162686549,1.196288204]；Δmean-r=-0.038507716，95% CI=[-0.041406162,-0.035536052]；两者 Holm p=0.000999500。常数 baseline 的 TB-MSE 也低于两个学习模型，不能写成强绝对迁移。
- [x] A8 v25 已写入该负迁移结果并完成 44/44 论文核验；仍为 non-submittable working manuscript。复现说明见 `audits/20261119/RK05/README.md`，新交接见 `docs/handover/HANDOFF_A8_RK05_RIBOMIMO_STUDY_OOD_20261119.md`。
- [x] 在线 PPT 第 101 页 `pgI`、revision 63：写前候选事实 33/33、写后整稿回读 206/206 通过，前 100 页语义 XML 全部不变；严格 XML 的 6 处差异仅为已披露的服务端默认属性规范化。
- [ ] 本实验不关闭全局 untouched、物理速度、功能/homology/protein OOD、RK-G1、生成训练授权、time-matched 成本或完整 baseline 主矩阵；下一优先仍是机制支持的真实功能 OOD。

## 2026-11-20 RK03 Ribo/VeloHARMO source-feasibility increment

- [x] 完成 metadata-only 来源可行性审计：五个 VeloHARMO 来源均有公开 run-level records，合计 125 runs、143,663 MB；RiboMIMO 额外 Mohammad19/Subtelny14 合计 13 runs、9,236 MB；七个不同 RunInfo accession 合计 138 runs、152,899 MB。`size_MB` 不是本轮下载量。
- [x] 纠正并复核 Dunn13=Drosophila/GSE49197、Pop14=yeast/GSE63789；Subtelny14/GSE53268 使用 BioProject PRJNA231671 回退；固定 VeloHARMO 树与物化 payload 均为 14 个逐文件 SHA/bytes 匹配条目。只有 E. coli harmonized matrix 被发布，E. coli/yeast GA checkpoints 不代表其他矩阵存在。
- [x] 14/14 tests、生产 74/74、离线独立 169/169（最大数值差 0）、finalization 47/47 全部通过；终态为 `SOURCE_METADATA_RECOVERABLE_REMAP_NOT_PERFORMED`，科学结论为 `PUBLIC_SOURCE_RECOVERY_FEASIBLE_BUT_NOT_REMAPPED`。错误映射、计数和 finalization 的失败报告均保留。
- [x] A8 v27 新增 6.23 节与六个证据 anchors，论文 61/61、候选事实 30/30 通过，v26 逐字恢复核验通过；仍为 non-submittable working manuscript。科学证据 commit=`c0fd2b32a4919734747214ae06336efb67e03dcd`，论文 commit=`c5046b9c25a700f6231f0411b95f4d881dcda5d8`。
- [x] 在线 PPT 第 103 页 `pgM`、revision 65：写前 35/35、写后整稿 47/47 通过，前 102 页语义 XML 全部不变；首次 46/47 报告保留，唯一差异为服务端显式化 schema-default `col@span=1`。PPT 证据 commit=`dc567587aa9b3a1db67be0fcebcd26fdf450e16a`。
- [ ] 本 bounded 子任务不下载 reads、不构建 UTR–CDS、不执行 raw-read/P-site 重比对，也不生成四个非 E. coli harmonized matrices；自然分布报告、机制验证、模型训练、RK-G1、昂贵生成训练授权与可投稿论文仍未关闭。

## 2026-11-20 RK03 MAGE OOF comparator closure

- [x] 仅基于既有 131×3 development OOF 冻结预测完成 full−RCS、RCS−intrinsic、full−outer-train-mean 三项探索对照；0 new fits、0 new scorer calls、33 test constructs 未读取。`rcs_only` 明确为 intrinsic+RCS；fold-specific train means 无 evaluation-fold 标签泄漏。
- [x] v1 的全局常数 Spearman 技术假设失败保留，v2 改为均值基线仅作 RMSE 推断。最终 9/9 tests、24/24 independent PASS；五检验 Holm、20,000 bootstrap + 20,000 paired permutations、三 outer-seed 点估计完整。科学证据 commit=`46f1b7f057f479da9547745c5fa657bdfff00a21`。
- [x] full−mean ΔRMSE=`-0.015370339550445498`，95% CI=`[-0.0259385856740894,-0.005729286631198561]`，Holm p=`0.020748962551872408`，三 seeds 均负；full−RCS 与 RCS−intrinsic 四项机制检验 Holm p=1、CI 跨 0，敏感性方向不稳定。结论为优于均值但不等于机制增量，`DEV_NO_GO_TEST_UNTOUCHED` 与 RK-G1=false 不变。
- [x] 在线 PPT 第 104 页 `pgz`、revision 66：候选 20/20、写后 29/29 PASS，前 103 页 ID/顺序保留，真实截图无裁切/重叠/缺失；初版 29/31 过严备注要求及 verifier-only 更正记录保留。未重复加页。
- [x] 真实论文增量已完成：先由 RK06 updater 生成 A8 v28 / section 6.24，再以 v28 精确 SHA 为基线写入 MAGE section 6.25 / v29。MAGE paper verifier **61/61 PASS**，删除新 section/anchors 后逐字恢复 v28。当前稿件 SHA256=`be9fcc72f6f5b631de89084457b3011a8c966d677b916924c795753738d6d444`，论文与快照 commit=`a68b07b7171093b534ad7055d7fcbddea952f350`。纯外部模型、常数速度场、functional untouched、transport、生成器授权和可投稿状态仍未关闭。

### RK06 unique18 dense production 完成边界
- [x] 冻结协议 `configs/a8_rk06_simple_search_dense_unique18_protocol_v1.json` 的正式矩阵已完成：18 records × 3 seeds × 4 methods × `B=1…500`，216 runs、108,000 unique synonymous scorer calls。dense AUC=`B=1…499` HV 算术平均，B500 仅端点；normalized HV 不截断，外部乱序 actual sets 不补零、不把 lambda 转 budget。
- [x] production SHA256=`d060492c1d6882ad950ccde9782ee5cf2f8b98dfd5d24b0ea16757e6a8d2a052`；independent SHA256=`2e24fb6434f7e2a6967bd051ca2491fcddac88a408351a2ce0dd2520546ef6df`，26/26 PASS；finalization SHA256=`bcbf1cc2bf299c212588740eb2f15d4ccc2bb693be6d672ebd46145018eab947`，44/44 PASS。
- [x] 216 个逐 run 独立重计算全部通过；恢复前后 432 份 checks/arrays SHA256 完全不变，新 scoring calls=0。端点别名和 external-policy 两次汇总 schema 失败均保留并修复：7/7、8/8 tests PASS；科学证据 commits=`3517115061ba6e6702f03deda3a2dfd29c18994c`、`28ec8c1ee1d9d23302ab9460e1a8a609153551ea`、`0bc9ddb8a6944974ad72dce91b3eb6fd8d81690d`。
- [x] 六个 primary tests 为 4/6 SUPPORTED：hill-climbing−uniform dense AUC/B500 HV 与 MH-annealing−uniform dense AUC/B500 HV 获支持；AReUReDi-style−uniform 两项显著负向并保留 NOT SUPPORTED。完整数值、方法均值、双向 dominance 与成本见 `simple_search_dense_claims_v1.json` 和 handoff 第 33.3 节。
- [x] A8 v28 / section 6.24 已写入并通过 24/24 checks、73/73 candidate facts；当前真实稿件已为 v29，不得再次执行 RK06 updater，也不得在 v29 上重跑只接受 v28 的 RK06 paper verifier。
- [x] RK06 PPT 候选 50/50 PASS；在实时 104 页/revision 66 基线上只追加第 105 页 `pZp` / revision 67。首次写后 14/16，定位为服务端空白/default 属性规范化差异；verifier anti-weakening tests 4/4 PASS 后最终 16/16 PASS，真实截图人工验收。commit=`1fa4ca2cde0c1272d382947b2d9bf765208cc2a6`。
- [x] 文档 closeout 35/35 PASS，冻结 `codonflow` 环境定向测试 25/25 PASS，当前 v29 论文核验 61/61 PASS；closeout 失败历史和 correction 均保留。
- [ ] 不将上述 bounded 结果标为 RK06 全部完成：外部实际输出集的完整 dense 矩阵、time-matched、真实功能、untouched24、全任务外部 SOTA 和 CodonFlow-RK 生成训练仍未闭合；未读取 untouched/test，未启动昂贵生成训练。

## 2026-11-20：RK-G0 bounded readiness、统一成本与论文/PPT closeout

- [x] **真实来源与协议**：冻结 22 份来源及 SHA256、22 个成本行、20 个 gate/boundary checks。v1 的 `KeyError: lineardesign_unique_sequences` 和 10 个失效指针保留；v2 只修协议读取与不可证实字段，科学源和测量值未改，baseline 重跑与新增 scorer calls 均为 0。
- [x] **独立验收**：production 179/179 PASS；独立 verifier 357/357 PASS、max numeric delta=0；定向反篡改测试 9/9 PASS；finalization 6/6 `PASS_BOUNDED_G0_CLOSEOUT`。证据提交 `c1f641a17f4f2157be0d498d24ba363674bd7617` 已推送。
- [x] **统一成本**：13 个范围有实测 wall-clock，9 个范围显式 null；null 不是 0。LinearDesign unique18=5459.871640930884 s/131 outputs，EnsembleDesign=6001.057458210271 s/192 outputs；RK06 四方法各 27,000 unique scorer calls、每方法约 20,939–21,078 s；RiboMIMO study-OOD 三 seed=949.7424744511954 s。不同硬件、任务和评价范围不合成伪总成本，也不形成 time-matched 排名。
- [x] **G0 结论**：状态仅为 `PASS_BOUNDED_DATA_BASELINE_EVALUATION_READY`。Boël/MAGE/Mordstein 等真实功能数据、可靠划分、关键 baseline 输出、dense 与 actual-set 评价器具有 bounded readiness；不是所有数据源、官方模型或完整外部 SOTA 的豁免。RK03-REMAINING 仅闭合为 `FEASIBILITY_CLOSED_NOT_FULL_REMAP`。
- [x] **论文 v30**：新增 §6.26 `Bounded RK-G0 readiness and unified cost ledger`，SHA256=`6ab241c672ced7ec5f770d324487cc5deb742c0d3697afb5418d7f2b11c3024a`；独立论文验收 127/127 PASS，v29 可精确恢复。提交 `e8bf9d37ecee83e7caa2ec8997717e85e99f8d28` 已推送。
- [x] **在线 PPT**：第 106 页 `pZg`、revision 68；旧 105 页语义全部保持不变。页面科学验收 47/47 PASS、closeout 10/10 `PASS_G0_PPT_CLOSEOUT`、真实截图视觉复核 PASS。PPT 脚本、报告、日志和 correction 已在 `44ce165e7c74419ba26bf4b422a24fc691c3de8b` 提交并推送；大型 XML/响应/截图归档于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk06/g0_closeout_ppt_v1/`。
- [ ] **仍未闭合**：external actual-set dense 完整矩阵、time-matched、完整自然分布、full UTR–CDS remap、RNARL 官方模型、VeloHARMO 五物种、完整外部 SOTA、Kudla 逐构建序列—表达表、functional-untouched 和 wet-lab/前瞻 DBTL。RK-G1=false，generator_training_authorized=false；不得启动昂贵生成训练或把本 closeout 写成 RK-G0–G4 全部通过。
- [ ] **复现边界**：本轮未在 G0/v30 后运行完整项目 `pytest tests/`、干净环境安装或端到端总复现；179/357/9/6、127/127、47/47 与 10/10 只覆盖各自冻结证据和定向验收。

## 2026-11-20：RK08 十臂机制通道筛选、论文 v31 与 PPT107 closeout

- [x] **训练前预注册**：冻结 10 个同参数臂（`all`、`none`、3 个单通道、3 个 leave-one-out、`pair_only`、`no_pair`），每臂 4,997 参数；统一 backbone、训练超参数、seed 和 dev checkpoint 规则。screen 只读 train/dev，选臂前不加载 test、sequence-OOD 或 functional untouched。协议/configs/准备报告提交 `669b2735c21bf9bda8fdac12fc0c9f69635a38b5`。
- [x] **development 唯一选择**：10/10 臂真实完成，独立 dev cluster-balanced MSE 最小为 `all=3.761769367012553`，无同分。train/dev-only `all`、`none` 与旧全量实验 `state_dict` 逐张量 bitwise 相等；selected epoch、best 权重及 predictions 一致。选择报告=`audits/20261118/RK08/channel_screen_selection_v1.json`。
- [x] **OOD 支持但非机制充分证据**：2,000 次 operational-protein-cluster paired bootstrap、6 个 OOD 比较 Holm。`all−none` ΔSpearman=`+0.19901564752464795`、CI=`[0.12925907591173844,0.26781646706339085]`、p=0，ΔCB-MSE=`-0.2760885716873087`、CI=`[-0.37608880535590633,-0.18123318545616485]`、p=0；`all−ridge_gc` 两项亦方向正确且 p=0。
- [x] **full-proxy 对照失败**：`all−ridge_all` ΔSpearman=`-0.025779039513507546`、95% CI=`[-0.0755256519724216,0.020488139619787824]`、Holm p=`0.532`；ΔCB-MSE=`-0.025572097048845777`、CI=`[-0.1282439258338166,0.07253420347846523]`、p=`0.636`。因此 `channel_screen_gate_pass=false`，即使 dev 选出 `all` 也未稳定超过 full-proxy ridge；不能改写为某一通道机制贡献。
- [x] **独立验收**：8/8 定向测试 PASS；从原始预测独立重算选臂、指标、bootstrap、CI、p 和 Holm，320/320 PASS，max numeric delta=`1.9095836023552692e-14`；42/42 `PASS_CHANNEL_SCREEN_CLOSEOUT`。科学证据/closeout=`9fc6353399db2e33ccb56c2a6b1afbd4d4340170` / `d628fb8b71f5a9a264dcc14952d6f3b7eccf8a6f`；大文件位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk08/channel_screen_v1/`。
- [x] **论文 v31**：新增 §6.27 Development-selected mechanism-channel screen；真实稿件 SHA256=`9c0b453d5b3fbc0e2672dc776fa718d13cc50dcc072ab654aafdfcbe3e0a3c1a`，115/115 PASS，推送后复验 115/115。保留 113/115 字面检查失败与 correction，科学证据未改。提交 `7d5e51a17f93218e831bc22b845c030065362a35`。
- [x] **在线 PPT107**：在 106/revision 68/`pZg` 后只追加第 107 页 `pZZ`、revision 69；candidate 103/103、写后 223/223、closeout 18/18、真实截图视觉 PASS，推送后复验仍为 223/223 和 18/18。首次 102/103 与 222/223 的 verifier 失败及 correction 保留。提交 `d4afbf79e55da335f66b05507448ecd6e2fbc798`；归档位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk08/channel_screen_ppt_v1/`。
- [ ] **仍未通过 RK-G1 / 未授权生成训练**：既有 velocity 主终点失败，MAGE full−RCS 与 RCS−intrinsic 未支持稳定机制增量；functional untouched 未读取或评测。纯外部预训练模型替代、独立常数速度场、transport、完整外部 SOTA 和 G0 未闭合边界仍保留。不得把 proxy/search/OOD 提升写成真实功能或因果机制。
- [ ] **复现边界**：v31/channel screen/PPT107 后未运行完整项目 `pytest tests/`、干净环境安装或端到端总复现；本轮 PASS 只覆盖冻结证据、定向测试、独立重算、论文与页面验收。权威工作树仍为 `/home/codonflow-a8-rk`、分支 `a8-rk`。

## 2026-11-20：MAGE 纯外部 RCS 对照、论文 v32 与 PPT108 closeout

- [x] **拟合前冻结纯外部特征臂**：`pure_external_rcs` 仅含 variant RCS、相对 matched wild-type 的 RCS 差值及绝对差，不含 position、position interaction、codon/amino-acid identity、GC、local MFE 或其他 intrinsic 特征。复用 131 个 train+dev constructs 的冻结 OOF/folds，沿用 5 outer × 4 inner × 3 seeds × 6 alphas，新增 375 次真实拟合；33 个 test constructs 始终排除。协议 SHA256=`9efd39ef21672722adde333e28f4e1144983949dfab5a6437a1f45a68e930b45`，预注册提交=`0a08eb90c3ee787578f5fac1d5f01a2b2fe72a5d`。
- [x] **纯 RCS 替代失败**：主 seed 纯 RCS RMSE=`0.04929761172417739`、Spearman=`-0.13201530863899236`，intrinsic RMSE=`0.03413327461240379`、Spearman=`0.6123990835404937`。pure−intrinsic ΔSpearman=`-0.744414392179486`，95% CI=`[-0.9403491867053566,-0.5300791533185797]`，Holm p=`0.0002999850007499625`；ΔRMSE=`+0.015164337111773597`，CI=`[0.005846359530413134,0.02506527402042598]`，p=`0.009449527523623819`；两个 sensitivity seeds 方向均不利于纯 RCS，故 replacement=false。
- [x] **机制解释不变**：full−pure 与 intrinsic+RCS−pure 的两项终点均满足 development-only 支持规则，但这只是优于弱纯 RCS 臂，不等于优于 intrinsic。旧 full−intrinsic ΔSpearman/ΔRMSE 的 CI 均跨零、两项 Holm p=1；mechanism_increment=false、RK-G1=false，test 与生成训练仍未授权。
- [x] **科学独立验收**：正确环境 `/root/miniconda3/envs/llr_env/bin/python` 下 10/10 单元测试 PASS；独立实现重新抽取特征并重跑 375 fits、nested alpha、预测、bootstrap、permutation 和 Holm，174/174 PASS、max numeric delta=0；finalization 43/43 `PASS_PURE_EXTERNAL_COMPARATOR_CLOSEOUT`，推送后独立复验仍为 174/174。科学证据提交=`b95e1244537a23c95cdda986cb60e343cfd7e4da`，大型 predictions/logs/postpush 位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/mage_pure_external_nested_cv_v1/`。
- [x] **论文 v32**：新增 §6.28 `Pure external-RCS comparator on reused MAGE development folds`，真实稿件 SHA256=`6c3d2a0329a46ca70d4dd782748a06c60fbecbf91fd8d8fe5d7ea1c42e2b73f0`；独立与 postpush 均 100/100 PASS，可精确恢复 v31，摘要、旧章节和参考文献未改。提交=`d5959f73ac4f4812d614eee6d6c04d320dff38fc`；写作交付 shell 错误与 correction 保留，未修改科学正文门禁。
- [x] **在线 PPT108**：在 107/revision 69/`pZZ` 后仅追加第 108 页 `pZS`、revision 70；candidate 227/227、写后 553/553、closeout 32/32，真实在线截图视觉 PASS，旧 107 页及备注语义不变。两次 `+add-slide` server timeout 后均回读确认未落库；随后使用带幂等键的原生创建接口成功一次，未产生重复页。closeout 的报告字段和末尾换行修正不改变科学或在线内容。PPT 提交=`3460c2e07d6e44d09afa38e747db737aae939911`；归档位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/mage_pure_external_nested_cv_v1/pure_external_ppt_v1/`。
- [ ] **仍未闭合**：本项只闭合旧 `rcs_only` 并非纯外部臂的歧义及纯 RCS 替代诊断，不闭合所有外部预训练模型替代、独立常数速度场、transport、functional untouched、full UTR–CDS remap、完整外部 SOTA 或真实功能验证；不得据此启动昂贵生成训练。
- [ ] **复现边界**：v32/pure-RCS/PPT108 后未运行完整项目 `pytest tests/`、干净环境安装或端到端总复现；上述 PASS 只覆盖冻结证据、定向测试、独立重算、论文与页面验收。权威工作树仍为 `/home/codonflow-a8-rk`、分支 `a8-rk`。

## 2026-11-21：RK29 iCodon 来源可识别性停止、PPT121 与复现 closeout

- [x] **来源与无结局覆盖**：Goodman 出版商逐变体 CSV 持续 403；Mauger 官方补充包含 ORF/SHAPE-MaP 但无可一一连接的逐变体功能结局。改选 iCodon/GSE207584，在读取结局前冻结 950 variants、96 proteins、96 evaluation groups，跨蛋白 identity≥0.90 配对为 0，四个 ViennaRNA 28°C MFE 特征均有限；状态 `PASS_LABEL_FREE_COVERAGE_AUDIT_FEASIBLE`。
- [x] **协议先冻结再读结局**：冻结 simple93/structure97/MFE-only/iCodon-only、Ridge/HistGB、10 seeds×5 folds、四终点 Holm 和唯一一对一序列—结局连接门禁；协议提交 `9496e1797470e5dd007e990d3760855f8bd43f0a`，9/9 合成测试通过后授权生产。
- [x] **完整对齐审计按预注册停止**：GEO 10,227 行是每个蛋白内部 FASTA 名称×测量向量的笛卡尔积；候选分布 240/598/117（1/2/3 candidates），715/955 S6 行无唯一序列，338/578 蛋白×设计组有多重合法分配。禁止以行号、首匹配、最近值或 target-informed 选择挽救；400 planned fits 实际为 0，无 analysis/prediction/metric/inference 或 `RK29_RESULT.json`。
- [x] **独立与干净复现**：独立 verifier 不 import 生产/覆盖模块，重新解析原始 S6/GEO/FASTA 并复算全部 10,227 配对，状态 `PASS_INDEPENDENT_ALIGNMENT_FAILURE_VERIFICATION`；科学停止提交 `3f75dc79cab881eb18eb65e10b15e0a5c0345dc8` 已推送。完整项目测试 423 passed/1 skipped；独立 clean clone 中 9/9 测试与独立 verifier 复跑通过，20 个声明字段完全一致，clone 前后 0 dirty files。离线 v3–v5 失败及在线/Torch 下载停止日志保留，最终 20-wheel 递归闭包 v6 安装和 `PASS_RK29_REPRODUCTION` 已核实。
- [x] **研究 PPT 与论文边界**：既有 PPT 从 120 页/revision83/`pZC` 仅追加第 121 页 `pZx`/revision84；前 120 页 ID、顺序和规范化语义 XML 不变，4 段 notes，所有对象在 960×540 内，状态 `PASS_RK29_PPT_READBACK`。本轮按 Skill 做服务器 XML 回读与画布检查，未声称截图视觉验收。英文稿不变，因为 RK29 是来源可识别性失败，不是结构增量阳性或阴性科学结果。
- [ ] **下一步仍需新证据**：只有取得权威逐变体序列键/明确映射表，或选取已独立连接序列与功能结局的新数据集，才可新预注册判别实验。当前失败连接不得事后修订；functional untouched 未访问，昂贵生成训练未授权，RK-G1=false。

## 2026-11-21：RK30 Mordstein matched-context 运输、独立复核、PPT130 与干净复现

- [x] **判别数据与冻结设计**：在 RK29 来源连接不可判别后，改用 Mordstein 2020 同一 GFP 文库，固定研究、载体、变体、observed-R1 300 nt 和 predicted-MFE 定义；沿用 RK28 的 152 references/74 clusters，不重新聚类或按结局选变体。新增 56 个 HeLa R1 文件，与既有 8 个 HEK293 文件组成 64 runs/8 experiments；Bin1–8、唯一最近参考、最大 Hamming 8 nt、每 variant/replicate 至少 1,000 assigned reads。共同队列为 126 variants/69 clusters，计数 9,728 行、71,814,214 assigned reads。
- [x] **公平 simple/structure 与整簇运输**：simple=GC3+GC+CpG+CAI；structure 仅增加 full-300-nt MFE、48-nt minimum-window MFE、window-mean MFE；depth 仅 QC。四个有序运输方向按整序列簇 held-out，目标结局不进入源训练；Ridge/HistGB、10 seeds×5 folds、10,000 次整簇 bootstrap/permutation，16 个主要终点统一 Holm。完成 800 transport + 900 within=1,700 fits，单线程 CPU。
- [x] **科学结论**：`MATCHED_CONTEXT_MFE_TRANSPORT_NOT_SUPPORTED`。16/16 primary endpoints 均未通过，四个方向全部失败；12/12 secondary within-context endpoints 也未通过。`HeLa with-intron→HeLa no-intron` Ridge Spearman 虽有 9/10 positive seeds，但 effect=0.047546、95% CI=[−0.043187,0.216765]、Holm p=1，仍失败。该结果只否定本冻结 matched-context 设计的广泛 context-transportable MFE increment，不表示 MFE 在所有宿主/intron 条件均无作用，也不构成因果宿主机制、translation velocity/decay、protein OOD 或外部 SOTA 结论。
- [x] **独立 raw/model/泄漏复核**：64/64 checkpoints、6,400 次蛮力重分配、0 MD5/long-count mismatch；126 条结局独立重算最大差 8.881784197001252e-16。全部 1,700 fits、seed metrics/effects 与 7×10,000 inference arrays 独立重算通过；200 transport folds 与 150 within folds 均无训练/测试簇交集，`target_outcome_used_for_fit=false`。项目测试 423 passed/1 skipped，raw counting-binding 专项 20/20 PASS。
- [x] **干净 checkout 复现**：科学 HEAD `42d4c9926921e3c59316c7d6787103a927a4665c`，`git_dirty=false`。初始任务在 raw verification 后停止，保留已完成 counting/model/raw 后断点续跑缺失步骤；原始中断、字段 gate 错误和成功日志均保留，未虚构不中断 wall-time。最终 `PASS_RK30_CLEAN_CHECKOUT_REPRODUCTION`、`PASS_RK30_PRODUCTION_REPRODUCTION_EQUIVALENCE`：13 CSV 字节一致，7 NPZ/70 arrays 名称/shape/dtype/数值完全一致；独立审查 `PASS_RK30_CLEAN_REPRODUCTION_REVIEW`。
- [x] **论文、PPT 与 GitHub**：英文工作稿新增 §6.40–6.41 和 Tables 12–16，原 1,414 行顺序保留，新稿 1,543 行，13/13 manuscript review PASS，SHA256=`b7b3d6d06c86418b7177f73eb8db52cc7689b67b14a77bac03c4bd66e666d89f`，仍为 non-submittable working draft。线上 PPT 从 121/revision84 追加到 130/revision93，第 122–130 页记录设计、队列、四方向、Ridge/HistGB 主要与绝对表现、次要分析和复现；原 121 页语义未变，九页全文、来源、notes、页码、对象数量与画布检查通过。关键提交：科学 `42d4c992…`、论文 `9dcc839a…`、复现 `36aff1d0…`、PPT `10b8d5ba…`、handoff `a87de45e…`。
- [x] **artifacts 与成本**：生产根 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk30/mordstein_matched_context_v1/`；clean 根 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk30/mordstein_matched_context_v1_clean_reproduction_42d4c992/`。生产 counting/model/raw-independent/model-independent=`214.9145/249.5825/149.7702/230.0754 s`；clean=`270.3273/233.3241/115.6205/208.0617 s`，不合并成虚假全流程总成本。
- [ ] **按原合同继续而非终止**：RK30 只闭合运输条件判别，不替代 RK13 强 baseline、机制适用域、time-matched 和真实功能路线。下一项继续执行已授权的定向科学任务；完整外部 SOTA 和 RK-G1 仍标为未解决，不宣称已经达成。昂贵生成训练仍未授权，functional untouched 继续冻结，wet-lab/前瞻 DBTL 未执行；这些是明确门控/阻塞，不得改写为完成。
