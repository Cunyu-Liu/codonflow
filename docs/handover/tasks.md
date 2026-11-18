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
