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
- [x] RK-04 核心功能 split：Boël 按 5,554 个 operational homology clusters 划分 train/dev/test=5,079/635/634 行；全部 19,072 个 MAGE rows 与 13,569 个 construct-signature groups 冻结为 untouched。六类跨 split 重叠均为 0，独立 33/33 checks、组合 19/19 tests 通过；commit `99df1d96e041e1f78b67e69210276df66d7b5f6f` 已推送。长度/GC OOD 与 train-only 归一化由后续 v2 补齐，功能/生成训练仍未授权。
- [x] RK-04 sequence-OOD v2：仅用 original train 的长度/GC q05/q95 确定 276–1590 nt 与 0.3294248837430009–0.7093033422956696 的闭区间；任一成员越界即迁移整个 operational cluster。retained train/dev/test=`4,019/503/490`，sequence-OOD=`1,336`（1,110 clusters），19,072 条 functional untouched 未计算特征或评价。train-only observed-mean imputation、缺失指示和 ddof=0 归一化已冻结；13/13 tests、独立 37/37 PASS、finalization 11/11 PASS。v1 缺失值导入失败和 verifier 35/36 错误假设均保留；本项只关闭数据协议，尚无 OOD 性能或生成器证据。commit `a17a89fb` 已推送。
- [x] RK-04 sequence-OOD PPT：既有在线主稿在 revision 41 的 79 页基线上只追加第 80 页 `pgq`，写后 revision=42；回读 10/10 PASS，前 79 页 slide IDs 与语义 XML 不变，候选与 finalization/counts 已预先核对。页面明确仅完成数据协议，不声称 OOD 性能、生成器或 SOTA。
- [x] RK-04 sequence-OOD 功能预测模型：正式实现 v2 仅用 retained train 拟合、dev 按 cluster-balanced MSE 选参，5 家族 17 候选冻结。primary=`ridge_all(alpha=100)`；retained test Spearman=0.144896、R²=0.015979，sequence-OOD Spearman=0.217873、R²=0.011709。primary 相对 GC 的 OOD ΔSpearman=+0.146000（95% CI [0.103896,0.189857]），ΔCB-MSE=-0.263944（95% CI [-0.374981,-0.144076]）；retained test 两增量区间均跨零。12/12 tests、独立 40/40 PASS、finalization 18/18 PASS，两次预测/指标/选参 SHA 完全一致；常数伪相关旧版、schema 失败和 verifier 修复均保留。仅支持有限 nonsynonymous proxy 信号，不关闭同骨干机制、生成器、functional untouched 或 SOTA。
- [x] RK-04 sequence-OOD 模型 PPT：既有在线主稿在 revision 42 的 80 页基线上只追加第 81 页 `pge`，写后 revision=43；候选证据核验 21/21 PASS、整稿回读 12/12 PASS，前 80 页 slide IDs 与语义 XML 不变。页面完整保留五家族结果、dev 冻结 primary、OOD 增量区间与低 R²/非机制/非生成器/非 SOTA 边界。
- [x] RK-18 A8 v12 sequence-OOD 模型同步：A8 v11 原快照 SHA256=`0158f579cb1634b1a36c666c4cf7c930dcabe276abc00e3c00f5546ef1005a05` 保持不变；v12 新增数据协议、五家族完整表、dev 选择、test/OOD bootstrap、失败历史与证据哈希。独立论文核验 19/19 PASS，v12 SHA256=`5ff302e51dd26decaa628e23481bedab9b6a747fbd13eac08017c578396877a9`；仍为 non-submittable working manuscript。
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
- [x] CF-A8-RK05-CODONTRANSFORMER-BOUNDED：固定官方源码 `4a447b01dab860feb81b647ff1ff88ad598517f4`、模型 `9744dcc920d813066391fc828d7a590207f148e8` 与 8 个模型文件，在隔离环境和 RTX 5090 上完成官方 example/C01 的 default 与 `match_protein=True` 共 4 次真实 deterministic 推理。4/4 输出为合法同义 CDS，共 2 unique CDS；官方 example default 与 README 精确一致，两种模式对每个蛋白输出相同，不能声称约束收益。独立重跑 **13/13 PASS**、max_numeric_delta=0.0，单元测试 **8/8 PASS**、finalization **10/10 PASS**。科学证据 commit `210d2f4c13cddc7144d1939d0ae76162d2016c8a`；不构成 matched MFE/EFE、dense budget、主矩阵、功能 OOD 或 SOTA。
- [x] CF-A8-RK18-WORKING-MANUSCRIPT-V6：A8 新增 CodonTransformer 四次推理表、源码/模型与物化证据、双模式相同输出、成本含 warm-up、13/13 独立复核和 10/10 finalization；A7 未改。A8 SHA256=`1ac702be2b38900346064ebbc56a4b20a461089f317078db1df08c73774e0d35`，独立 **17/17 PASS**；commit `f479955fefa034c5a5fde84c5f7ab37d85cf0044`。仍为 non-submittable working manuscript。
- [x] CF-A8-RK05-CODONTRANSFORMER-PPT：既有在线主稿追加第 74 页 `pgU`、revision=36，记录固定源码/模型、4/4 legal、2 unique、13/13 独立重跑、10/10 finalization、双模式输出不变和 bounded 边界。候选 preflight **8/8 PASS**，写后独立验证 **10/10 PASS**，前 73 页 slide ID、顺序与语义 XML 全部不变。commit `0c33d35580c02ae06932083200bc6fbd5dd3882c`。
- [x] CF-A8-RK05-VELOHARMO-BOUNDED：固定官方源码 `38b48079856aeb9d33a1b10844d77aa8f6640032`、E. coli 矩阵和 E. coli/yeast fold-0 权重；从 1,170 条 processed matrix 记录确定性选取 7 条最短合格记录，官方 `VeloGRU/run.py test` 在 `cuda:0` 返回码 0，mean Pearson=`0.6044025421142578`、SD=`0.17268328368663788`，仅为长度选择子集诊断。未修改 GA 的 `Mimo_data` 导入失败原样保留；runtime wrapper 只做 7 处兼容替换，population=8、generations=2、seed=20261118，在 CPU 上完成 C1P620 的 native/start/best 评价。start 与 best 完全相同，fitness=`0.34598612785339355`，迭代增益=0；相对 native 的 `0.3715937677770853` 只是初始候选的预测谱目标差，不是 GA 或实验功能增益。独立重跑 **17/17 PASS**、max_numeric_delta=0.0，单元测试 **10/10 PASS**、finalization **13/13 PASS**。科学证据 commit `8fce8dcaf5749d838f2378424b50042a8970cc27`；五物种 processed matrices、正式训练/CV、主矩阵、功能 OOD 和 SOTA 未关闭。
- [x] CF-A8-RK18-WORKING-MANUSCRIPT-V7：A8 生成器纳入 VeloHARMO 生产、独立与 finalization 三份冻结报告及哈希，新增 CUDA 长度选择诊断、CPU GA 零迭代提升、7 项兼容替换和未修改 GA 失败；A7 未改。A8 SHA256=`078228450f69c1efe6b31f7bbf7dba0d01d004c9aecdf2f330f4ad32c985fe6d`，独立 **18/18 PASS**；commit `9948b2ec251ae593ef9a864206cdd20672134923`。仍为 non-submittable working manuscript。
- [x] CF-A8-RK05-VELOHARMO-PPT：既有在线主稿追加第 75 页 `pgh`、revision=37，记录官方 CUDA test 的 mean/SD、native/start/best 预测谱适应度、GA iterative gain=0、17/17 独立 PASS、13/13 finalization 和 bounded 边界。写后独立验证最终 **10/10 PASS**，前 74 页 slide ID、顺序与语义 XML 全部不变；首次 9/10 仅由第 74 页尾部空白差异触发，失败报告与逐项 diff 均保留。commit `49ed134d4966fcc5c8d70c00c654cd414b898c51`。
- [x] CF-A8-RK05-RIBOMIMO-BOUNDED：固定官方源码 `094c693d4df45f4b29f5a3209b31c452a39092a5`，Mohammad16 最短 20 条合格记录、2 folds、2 epochs、batch=4、seed=20261118、单线程 CPU 完成官方训练；每折 train/valid/test=9/1/10，最佳验证 checkpoint 含 1,860,356 参数。两折 R²/MSE/Pearson mean=`-0.047131/2.298945/0.015289`，仅为 bounded 诊断。最终 runtime 仅六项 NumPy 兼容替换；独立重训 **17/17 PASS**、checkpoint 张量最大差=0，finalization **13/13 PASS**、测试 **10/10 PASS**。科学证据与 README commit `a6e119650c4dd52110849b43aa377cbbd1e422b0`；完整 CV、同源/study/功能 OOD、主矩阵和 SOTA 未关闭。
- [x] CF-A8-RK18-WORKING-MANUSCRIPT-V8：A8 生成器纳入 RiboMIMO 三份冻结 JSON、bounded 协议、两折指标、六项兼容替换和独立核验；A7 未改。A8 SHA256=`7f1a6d5ce3f5b17d6beb1a79958e8b91e30765fb68b58dd225635b8a696c4733`，独立 **19/19 PASS**；commit `56f9c4d559dc29f94b295f2500f7c0a3af1410e4`。仍为 non-submittable working manuscript。
- [x] CF-A8-RK05-RIBOMIMO-PPT：既有在线主稿追加第 76 页 `pgG`、revision=38，记录两折及汇总 R²/MSE/Pearson、20 genes、1,860,356 参数、17/17 独立 PASS、13/13 finalization 和 bounded 边界。候选 preflight **8/8 PASS**，写后独立验证 **11/11 PASS**，前 75 页 slide ID、顺序与语义 XML 全部不变。commit `c317eb6755a6d6f6543b6297a0fdbc417186aa4d`。
- [x] CF-A8-RK05-IXNOS-BOUNDED：固定官方源码 `1ea2337dd24d1e6fa3859f08573e99f02512810f`，以 SRR1049521 前 1,000,000 条完整 reads、20/10 genes、2 epochs、seed=20261118 和单线程 CPU 完成官方 bounded 训练，只使用最终 epoch。最终 R²/MSE/Pearson/Spearman=`0.028272/0.910627/0.195228/0.215997`，train-mean MSE=`0.937122`，只作执行诊断。独立重处理/重训 **27/27 PASS**、target/prediction/checkpoint 最大差=0，finalization **16/16 PASS**、测试 **10/10 PASS**；raw SAM 顺序差异保留，canonical 比对记录一致。科学证据与 README commit `645bc22f179dabc35f74f43144f0462de8f4a228`；完整 run/RSEM/论文协议、OOD、主矩阵和 SOTA 未关闭。
- [x] CF-A8-RK18-WORKING-MANUSCRIPT-V9：A8 生成器纳入 iXnos 三份冻结 JSON、真实 prefix reads、bounded 协议、最终指标、常数 baseline 和独立核验；A7 未改。A8 SHA256=`51b049bd9e0062d013f76b49f13b0312eb9ab204e153b4c994ad17e99abb3b79`，独立 **20/20 PASS**；commit `12d044d69519ffad8127cc9642372624b4c0a153`。仍为 non-submittable working manuscript。
- [x] CF-A8-RK05-IXNOS-PPT：既有在线主稿追加第 77 页 `pgW`、revision=39，记录生产/独立/常数 baseline 的 R-squared/MSE/Pearson/Spearman、864,464 trimmed reads、152,401 参数、27/27 独立 PASS、16/16 finalization 和 bounded 边界。候选最终 preflight **8/8 PASS**，写后独立验证 **11/11 PASS**，前 76 页 slide ID、顺序与语义 XML 全部不变；初次 7/8 仅为检查器大小写匹配问题，失败报告保留。commit `9b23048267afc808fade89cc08655464b5814467`。
- [x] CF-A8-RK05-ROSE-RELEASED-TEST：固定官方源码 `8b86d69d89ca7ef95193729e6d1a4738bc6a4451`，每研究一个发布 checkpoint、无训练、无集成，在 Pop14/Battle15 完整 1,902/9,980 条作者处理测试数组上各执行一次 CPU 前向。ROC AUC=`0.861889/0.807230`，AP=`0.859274/0.794068`，accuracy=`0.778654/0.728156`，log loss=`0.498731/0.562374`；只证明二分类停滞预测复现。独立第二次前向 **34/34 PASS**，logits/官方 float32 概率/生产指标差均为 0，finalization **60/60 PASS**、测试 **12/12 PASS**；v1–v3 数值判据失败保留。科学证据 commit `3a284efef7fab0b911473f1e1647f01bcfedf651`；训练、64-checkpoint 集成、速度回归、OOD、主矩阵和 SOTA 未关闭。
- [x] CF-A8-RK18-WORKING-MANUSCRIPT-V10：A8 生成器纳入 ROSE 协议、生产、独立 v4、finalization 和三份保留失败报告，新增完整数组分类结果、单 checkpoint/无训练及科学边界；A7 未改。A8 SHA256=`4bc071c4f8e6eecb20429e8b9ee044e116105f8a348740254f22a040840f823e`，独立 **21/21 PASS**；commit `f17f432e3ea58d6d2839bdba6ab05dedc3f4460f`。仍为 non-submittable working manuscript。
- [x] CF-A8-RK05-ROSE-PPT：既有在线主稿追加第 78 页 `pgc`、revision=40，记录 Pop14/Battle15 完整发布测试数组的 ROC AUC/AP/accuracy/log loss、常数 baseline、34/34 独立 PASS、60/60 finalization 和二分类/单 checkpoint 边界。候选 preflight **14/14 PASS**，写后独立验证 **14/14 PASS**，前 77 页 slide ID、顺序与 canonical XML 全部不变；raw artifacts 位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk05/ppt_rose_v1/`。commit `a9de66192f4d3fa2e795d8d93b05e2671248b595`。
- [x] CF-A8-RK08-VELOCITY-PROXY：在不访问功能 OOD 的前提下，使用固定 RiboMIMO 官方处理矩阵完成占据衍生速度代理实验；目标为 `-log1p(normalized density)`，首末密码子 mask，8,109 条输入排除 321 条超长记录后保留 7,788 条。Mohammad16 train/dev/test=`933/110/123`，Subtelny14=`3,630` 且与 Mohammad16 任意 split 的精确 CDS 重叠为 0；不声称 homology OOD 或物理速度实测。dev-only 选择 epoch 16；Subtelny14 主终点 model−ridge ΔTB-MSE=`+0.054623`（95% CI `[+0.054046,+0.055192]`），Δmean within-transcript Pearson=`-0.070543`（95% CI `[-0.073248,-0.067765]`），2,000 次 bootstrap 两项均反向显著，`velocity_mechanism_pass=false`。Mohammad16 内部改善与 Mohammad19 的混合结果保留，不替代主终点。两次 checkpoint/预测 bitwise 一致，独立 `26/26 PASS`、finalization `12/12 PASS`，独立前向最大误差 `6.406818248150259e-07`；A8 v12 独立论文核验 `30/30 PASS`。科学代码/报告 commit=`872bed008e5c07d310488641c15e13d471b6166a` 已推送；论文/台账 commit=`fb8cff3396c0052582aae664e927dc06b06c2e86`，PPT 证据 commit=`36fbf3ec111ea63b06e79e8120fc1d61c2f5f345`。在线主稿第 85 页已追加，候选预检 `19/19 PASS`、写后回读 `14/14 PASS`，revision=47、slide ID=`pgH`，前 84 页 ID/顺序/语义 XML 不变；RK-G1、功能迁移、跨层一致性与生成器授权仍未关闭。
- [x] CF-A8-RK08-HISTGB-DIAGNOSTIC：在看到原报告未配对的 HistGB 指标后，追加明确标记为 retrospective 的配对公平性诊断；复用冻结数据、split 和预测，不训练、不选 checkpoint、不访问 functional untouched。sequence-OOD 上 all−HistGB 的 ΔSpearman=`-0.027289`（95% CI `[-0.090520,+0.032626]`，Holm p=0.405），ΔCB-MSE=`+0.098795`（95% CI `[-0.050971,+0.252057]`，Holm p=0.396）；HistGB 点估计更优但两项 CI 均跨零，不宣称任一方显著胜出，原 RK-G1=false 不变。独立原始输入核验 `84/84 PASS`、finalization `33/33 PASS`、相关测试 `7/7 PASS`，科学代码/报告 commit=`4bc41a937614a7d7f408e9faafaa868b607a73f7` 已推送。A8 v13 新增第 6.8 节事后诊断与三条证据哈希，独立论文核验 `35/35 PASS`，A8 SHA256=`cd2c74ef1b093bb0ce5d3bfce5d0bb26939367c6d0fa5269361096c7f5aa8f0d`，A7 未改，论文/审计 commit=`3742a843df63cf5783ea75a68dccf0fe3c63760f` 已推送。在线主稿第 86 页 `pgd` 已追加，候选预检 `31/31 PASS`、写后回读 `40/40 PASS`，revision=48，前 85 页 ID/顺序/语义 XML 不变；PPT 证据 commit=`8979f8fa86e070b5fe5f45d0731eb9f99de7a62a`。本项仍不支持机制优势、固定蛋白同义机制、功能 untouched、生成器授权或 SOTA。
- [x] CF-A8-RK09-MINIMAL-KERNEL：完成冻结协议下的最小 CodonFlow-RK 数学核与小状态精确核验；64 槽合法 simplex、内部 stop/61/62 mask、no-op 或单内部密码子编辑、偏好/剩余预算、事件时间、两步拒绝采样与路径 telescope 均重算。长度 4 合法状态 `226,981`、两步可达 `10,981`，naive random-walk endpoint TV=`0.32419645032000277`；14,641 条路径、3,721 个端点的 telescope/endpoint/backward 误差均 `<1e-12`；事件时间 Monte Carlo mean=`0.249865008`、解析期望=`0.25`。生产 `22/22 PASS`、独立 `16/16 PASS`、finalization `14/14 PASS`、单元测试 `10/10 PASS`；初始生产 `19/22` 与独立 `15/16` 失败保留。科学代码/报告 commit=`f601f2b8aa7a7156f387163b63f1d0a5a19e367e` 已推送。A8 v14 新增第 6.11 节和六条证据锚点，独立论文核验 `30/30 PASS`，A8 SHA256=`963e0d7dbc9b891a127bbe61c0d25fa68276bfe7c63e6d41ccd37845b8c36c23`，A7 未改，论文 commit=`6a15d04294f8226999926c5fbd65132d84817a32` 已推送。在线主稿第 87 页 `pgb` 已追加，候选预检 `27/27 PASS`、写后回读 `25/25 PASS`，revision=49，前 86 页 ID/顺序/语义 XML 不变；PPT 证据 commit=`e9aa2a7684bb474190fa5748c000e7b236241321`。本项仅为数学核验证，未训练最小模型、未评功能/生成性能、未改变 RK-G1、未授权生成器、未支持 SOTA。
- [x] CF-A8-RK05-RIBOMIMO-MOHAMMAD19-1：固定 Mohammad19-1 官方处理矩阵（4,147 raw / 1,426 eligible，SHA256=`acc8c3ad…f9a5`），按官方 random-gene 1×10-fold/max100/early-stop5 完成生产与独立重训。重算聚合 R²=`0.461594832±0.011717629`、MSE=`0.433084291±0.015036766`、Pearson=`0.682075322±0.008264281`；10 对 fold checkpoint 张量逐位一致，独立双前向差值为 0。首次独立核验因六位日志舍入边界失败（fold-0 Pearson 差 `5.1052475e-07`），随后 finalization 复用同一旧规则再次失败；两份失败证据均保留。核验器和 finalizer 现明确采用仅针对日志量化的绝对差 `≤1e-6` 规则，预测数组独立重算仍用 `1e-7`，最终独立 `94/94 PASS`、finalization `424/424 PASS`、10 项单元测试通过。证据 commit=`558b9a2e` 已推送；本项仍只是 random-gene CV，不支持 homology/protein/study/functional OOD、统一成本主矩阵、论文数值一致或 SOTA。
- [x] CF-A8-RK05-RIBOMIMO-FOUR-MATRIX：四份作者处理矩阵均按官方 random-gene 1×10-fold/max100/early-stop5 完成生产、独立重训、独立推理和 finalization；共 15,669 raw / 8,124 eligible / 2,520,180 valid masked test codons，40 folds、8 次完整训练、40 对 bitwise checkpoint、80 次独立前向。Mohammad16 / Mohammad19-1 / Mohammad19-2 / Subtelny14 的 R²=`0.472874/0.461595/0.484536/0.397451`，MSE=`1.591470/0.433084/0.442863/0.592620`，Pearson=`0.690680/0.682075/0.696258/0.631848`；描述性 macro R²/MSE/Pearson=`0.454114/0.765009/0.675215`。Mohammad19-2 独立 `93/93`、finalization `424/424`；四矩阵独立汇总重算 `39/39 PASS`。A8 v15 SHA256=`e698949c6150c3144e326de137363aa36200be5875acacc484f7809a875bda2f`，精确增量论文核验 `14/14 PASS`，A7 未改。范围仍仅为 random-gene CV，不支持 homology/protein/study/functional OOD、统一成本主矩阵、论文数值一致或 SOTA。在线主稿第 88 页 `pgF` 已追加，候选预检 `29/29`、单页回读 `10/10`；整稿 89 页 revision=51，写后语义核验 `21/21 PASS`，前 87 页 ID/顺序/语义 XML 不变。
- [x] CF-A8-RK10-EXACT-TB：正式 CUDA float64 固定 4,000 步轨迹平衡优化已完成，3,721 状态、121 动作/状态、14,641 条固定起点两步路径与 oracle-induced target 均冻结。final loss=`1.6066016305e-29`，max path residual=`2.4868995752e-14`，endpoint/forward-target 最大误差=`5.2041704279e-18/2.6020852140e-18`，backward normalization error=`4.4408920985e-16`；theta 精确恢复 `[0.7,-0.25,0.45,-0.15]`。生产/重训各 `11/11 PASS`、独立 `25/25 PASS`、finalization `20/20 PASS`、单测 `10/10 PASS`；两次 theta 与 `[3721,121]` backward logits 逐位一致，解析 oracle residual=0，初版失败保留。A8 v16 SHA256=`14567dd97f1208a8170b8ba9d5f66e48e5005fea95273d8ed16532068eaa4625`，精确增量论文核验 `31/31 PASS`，A7 未改。本项仍是合成小状态数学结果，不是生物奖励、完整神经模型、功能/生成性能、RK-G1 改判或 SOTA。在线主稿第 89 页 `pgQ` 已追加，候选预检 `23/23`；整稿 89 页 revision=51，写后语义核验 `21/21 PASS`，前 87 页 ID/顺序/语义 XML 不变。
- [x] RK03-REMAINING（bounded source-feasibility）：完成 UTR–CDS 映射/raw read 或 P-site 独立重比对可行性报告、VeloHARMO 其余物种真实可获得性追踪；最终状态为 `FEASIBILITY_CLOSED_NOT_FULL_REMAP`。这不代表 full UTR–CDS remap、四物种信号 matrix、五物种模型覆盖或完整 RK03 main 已完成。

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
- **当前进展（2026-11-19，Mordstein 固定蛋白恢复门禁）**：Mordstein 正文将文库组成写为 22+137+58=217，STAR Methods 写为 138+59+22=219，和共同声明的 217 文库存在未解决的内部口径冲突；不得强行选定分解或把恢复表凑成 217 行，详见 `audits/20261118/RK02/mordstein_library_count_reconciliation_v1.json`。真实 reads 仅支持 CDS 4–303 与 442–720 的 observed ends，中央 138 nt/46 codons 仍无直接覆盖，不能声称完整 CDS 或作者 `GFP_###` 映射。新增独立 HEK293 下载验收器，以 16 个正式 FASTQ 的 ENA size+MD5 全通过为唯一恢复门禁并记录 SHA256；4/4 tests PASS，commit=`b7004f820feda67162a4826cc653cc48d73fb664`。完整下载、八 bin 恢复与 217 对账仍未完成，RK-02/RK-G0 不关闭。

- **下载编排复核（2026-11-19）**：发现一个旧 `audit_sample_per_run=100` 的重复恢复等待控制器会在下载完成后与现行冻结 `audit_sample_per_run=200` 流程争写 `recovery_full_v1`；已仅终止该旧等待 PID，六个下载 worker 和现行 fresh-16 文件门禁 runner 均保留。记录见团队 metadata `mordstein_stale_controller_retired_v1.json`；完整 16 文件 MD5/字节数验收尚未完成，不能据此形成科学结果。

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
- **当前进展（2026-11-19，CodonTransformer bounded official smoke）**：固定官方源码 `4a447b01dab860feb81b647ff1ff88ad598517f4` 和模型 revision `9744dcc920d813066391fc828d7a590207f148e8`，8 个模型文件完整，`model.safetensors` SHA256=`23994e1e7324e78c9d9da71040e8677c0a635287cf1c7c9ea5096b7eadc44dfd`。隔离环境中完成官方 example 与 C01H6.8b.1 的 default/match_protein 四次真实 GPU 推理，4/4 legal、2 unique；README default 精确一致，两种模式对每个蛋白输出相同，不能声称约束收益。独立重新加载固定权重并逐条重跑，13/13 PASS、max_numeric_delta=0.0；finalization 10/10 PASS、单元测试 8/8 PASS。模型加载 4.438657 s、推理合计 2.032779 s，含 warm-up，不是 time-matched 成本。科学证据 commit=`210d2f4c13cddc7144d1939d0ae76162d2016c8a`；A8 v6 独立 17/17 PASS，commit=`f479955fefa034c5a5fde84c5f7ab37d85cf0044`；PPT 第 74 页 `pgU`、revision 36，preflight 8/8、写后 10/10 PASS，前73页未变，PPT commit=`0c33d35580c02ae06932083200bc6fbd5dd3882c`。仍不构成 matched MFE/EFE、dense budget、主矩阵、功能 OOD 或 SOTA。

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
- **当前进展（2026-11-19，工程 smoke 已闭环）**：已实现共享 codon Transformer 的 initiation/velocity/decay/pair 四通路、UTR–CDS 合法配对偏置、功能异方差头与不确定性输出；消融仅门控信息流，不删除通路参数，pair-off 仍使用同形 dense attention。严格 functional/long-velocity loader 保留 NaN+mask，宿主词表和归一化仅拟合 train；契约测试 **12/12 PASS**。冻结 Boël sequence-OOD 表的 train/dev/test 各 8 条仅用于真实端到端 smoke，`functional_untouched` 显式排除；两次 CPU 训练指标、预测及参数张量逐位一致，RTX 5090 CUDA smoke 完成。独立核验 **31/31 PASS**、finalization **37/37 PASS**，CUDA 独立前向最大绝对误差 `4.76837158203125e-07`。这只是工程与复现里程碑，不是机制增量、功能/速度 OOD 主表、SOTA 或生成器就绪证据；RK-G1 仍未通过，昂贵生成训练不得启动。大 artifacts 位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk08/`。

- **正式占据衍生速度代理更新（2026-11-19）**：使用直接速度代理监督而不是功能标签间接训练速度头。Subtelny14 主 OOD 上 RiboKinetic/ridge TB-MSE=`0.230569/0.175946`、mean within-transcript Pearson=`-0.008845/0.061698`；model−ridge 两项差值及 95% CI 均指向 ridge 显著更优，故 `velocity_mechanism_pass=false`。Mohammad16 test 的 TB-MSE=`0.193081/0.234951`、Pearson=`0.442167/0.148476`（model/ridge）仅为同研究内部改善；Mohammad19-1/2 的 Pearson 改善伴随 MSE 变差，不构成稳健迁移。独立 26/26、finalization 12/12、论文 30/30 PASS；这是可复现负结果，不是物理速度、homology OOD、功能迁移或 RK-G1 通过证据。

### RK-09 E3：跨层机制一致性

- **任务**：联合/分别预测 MAGE 适应度、Ribo 速度、Boël mRNA/蛋白层；在适用数据做分层或 mediation。
- **输出**：跨层一致性、结构/速度/降解消融、Fig.2 机制证据。
- **验收**：结论限定为关联，除非有干预；黑箱 reward 或 attention 图不得替代机制证据。

- **全量功能 OOD 更新（2026-11-19）**：retained train/dev/test=`4019/503/490`，sequence-OOD=`1336`；all 与 none 均为 4,997 参数，仅通道门控不同，2,000 次 cluster bootstrap。all−none 的 OOD ΔSpearman=`0.199016`，95% CI=`[0.129283,0.266863]`；ΔCB-MSE=`-0.276089`，95% CI=`[-0.377439,-0.180840]`。all−GC-only 两项 CI 也支持 all；但 all−full-proxy ridge 的 ΔSpearman=`-0.025779`，95% CI=`[-0.071103,0.019376]`，ΔCB-MSE=`-0.025572`，95% CI=`[-0.124069,0.076207]`，均不显著。**RK-G1 未通过**，不启动昂贵生成训练。该实验为跨蛋白、功能单监督，不支持固定蛋白机制或速度 OOD；完整重训 bitwise 一致，独立 `224/224 PASS`、finalization `48/48 PASS`。

**RK-G1 状态：未通过**。功能 OOD 上 all 相对同骨干 none 和 GC-only 有增量，但未同时优于 full-proxy ridge；独立速度代理实验的 Subtelny14 主终点也显著落后于 ridge，`velocity_mechanism_pass=false`。修数据/假设前不得启动昂贵生成训练。

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
- **当前进展（2026-11-19，RK11 最小神经合成 CUDA 合约）**：新增独立 `src/codonflow/models/minimal_neural.py`，复用未修改的 RK08 四通路骨干，接入显式三核苷酸展开、多保真势监督、UTR–CDS pair 和精确 no-op/同义单密码子编辑条件核。冻结协议 SHA256=`6d4a319d…7725`；5,273 参数、float64 CUDA、Adam 固定 40 步、无 checkpoint 选择。教师目标损失 `0.156933581→-0.568343801`，unmasked MSE `0.185642740→0.009694968`；9 个合法候选中 5 个预算可行、4 个硬掩码，概率和=1、掩码概率=0。生产/重训各 14/14、独立 27/27、finalization 25/25、单测 10/10、A8 v17 精确增量论文核验 33/33 PASS；checkpoint bytes、状态张量、条件核数组和确定性数值历史一致，独立势/成本/条件概率误差均为 0。初版密码子映射 6 项失败、测试设置 1 项失败及两轮独立 24/27、25/27 失败均保留。项目标准 `pytest tests/` 最终 `289 passed, 1 skipped, 12 warnings`（955.01 秒；跳过项为默认未启用的 tmux 集成测试），两次环境收集失败均保留。GitHub 科学证据提交 `5c6659b8`；在线主稿第 90 页 ID=`pgu`、revision=52，预检 53/53、写后整稿核验 17/17 PASS，前 89 页语义内容未改。仅为合成教师和真实 CUDA 反向合约，不是生物机制、功能/速度、完整生成器、生成质量、OOD、SOTA 或 RK-G1 通过证据；昂贵生成训练仍禁止。

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
- **当前进展（2026-11-19，V6 CodonTransformer sync）**：生成器纳入四份 CodonTransformer 冻结来源和哈希，新增官方 example/C01 的 default/match_protein 四行结果、4/4 legal、2 unique、README 精确匹配、独立 13/13 与 finalization 10/10；明确两种模式输出相同、约束收益未证实、推理成本含 warm-up，未授权 matched MFE/EFE、dense/主矩阵/功能 OOD/SOTA。A8 v6 SHA256=`1ac702be2b38900346064ebbc56a4b20a461089f317078db1df08c73774e0d35`，独立 **17/17 PASS**，commit=`f479955fefa034c5a5fde84c5f7ab37d85cf0044`；仍为 non-submittable working manuscript。
- **当前进展（2026-11-18，V7 VeloHARMO sync）**：生成器纳入 VeloHARMO 生产、独立与 finalization 三份冻结来源及哈希，新增 7 条长度选择记录的 CUDA 官方 test 诊断、population=8/generations=2 的 CPU GA、7 项兼容替换、未修改 GA 失败、2/2 合法同义和 best=start 的零迭代提升；明确 best-native 差值不是 GA 或实验功能增益，未授权五物种、正式训练/CV、主矩阵、功能 OOD 或 SOTA。A8 v7 SHA256=`078228450f69c1efe6b31f7bbf7dba0d01d004c9aecdf2f330f4ad32c985fe6d`，独立 **18/18 PASS**，commit=`9948b2ec251ae593ef9a864206cdd20672134923`；仍为 non-submittable working manuscript。

- **当前进展（2026-11-19，V12 RK08 velocity-proxy sync）**：在实际 pre-velocity A8（含既有 RK08 全量功能新增）哈希门禁下保存快照并追加第 6.9 节，保留原始 v11 审计与当前稿件哈希链。新增 7,788 条速度记录、五个分区完整指标、Subtelny14 两项负向 bootstrap、同研究/跨研究边界、26/26 独立核验、12/12 finalization 和六份证据哈希；A7 未改。A8 v12 SHA256=`c9611d12a1c4c4e4deccbb0bb4e3718a2886a7804bc3b01e74ed64699be9ed4e`，独立 **30/30 PASS**；`velocity_mechanism_pass=false`，仍为 non-submittable working manuscript。

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

## 2026-11-20 RK06 unique18 dense production closure
- [x] 按冻结协议完成 18 records × 3 seeds × 4 methods × `B=1…500` 的真实 unique synonymous scorer 运行：216 runs、108,000 calls；dense AUC 为 `B=1…499` HV 算术平均，B500 仅端点，外部乱序 actual sets 的 dense AUC 保持 null。
- [x] 216 个逐 run 独立重计算全部通过；最终 independent 26/26 PASS、finalization 44/44 PASS。恢复前后 432 份 checks/arrays SHA256 不变，新 scoring calls=0。端点映射与 external-policy 两次 verifier schema 失败及修复均保留，production 和科学数值未改。
- [x] 六个冻结 primary comparisons 中 4/6 SUPPORTED：hill-climbing、MH-annealing 相对 uniform 的 dense AUC/B500 HV 为正向；AReUReDi-style 两项显著负向并保留 NOT SUPPORTED。完整效应、paired 95% CI、Holm p、方法均值和成本见 `audits/20261120/RK06/simple_search_dense_claims_v1.json` 与 handoff 第 33 节。
- [x] 科学证据、失败日志、修正记录和 manifest 已提交推送：`3517115061ba6e6702f03deda3a2dfd29c18994c`、`28ec8c1ee1d9d23302ab9460e1a8a609153551ea`、`0bc9ddb8a6944974ad72dce91b3eb6fd8d81690d`。
- [x] RK06 写入 A8 section 6.24 / v28，24/24 checks、73/73 candidate facts PASS；随后 MAGE comparator 写入 section 6.25 / v29，61/61 PASS。当前稿件 SHA256=`be9fcc72f6f5b631de89084457b3011a8c966d677b916924c795753738d6d444`，提交 `a68b07b7171093b534ad7055d7fcbddea952f350`。
- [x] 在线 PPT 在 104 页/revision 66 基线上只追加第 105 页 `pZp`，revision 67；candidate 50/50 PASS，最终写后 16/16 PASS，真实截图人工验收。首次 14/16 报告及 verifier correction 保留，提交 `1fa4ca2cde0c1272d382947b2d9bf765208cc2a6`。
- [x] 文档 closeout 35/35 PASS；使用冻结 `codonflow` 环境复跑定向测试 25/25 PASS，当前 v29 论文核验 61/61 PASS。closeout 字段适配、README 哈希和错误 Python 环境的失败日志均保留，未改科学数值。
- [ ] RK06 整体仍未完成：本项只是 unique18 development proxy-search evidence；LinearDesign/EnsembleDesign 等外部实际输出集的完整 dense 矩阵、统一 time-matched/forward/unique-scorer 成本、untouched24/真实功能和 CodonFlow-RK 外部 SOTA 仍开放。

## 2026-11-20 RK03 MAGE OOF comparator closure
- [x] 冻结 131 constructs × 3 outer seeds OOF comparator 完成，0 new fits、0 new scorer calls，9/9 tests、24/24 independent PASS。full−fold-specific outer-train mean ΔRMSE=`-0.015370339550445498`，95% CI=`[-0.0259385856740894,-0.005729286631198561]`，五检验 Holm p=`0.020748962551872408`，三个 seeds 均为负。
- [x] full−RCS 与 RCS−intrinsic 的四项机制对照均 CI 跨零、Holm p=1，敏感性方向不稳定；结论保留为“优于均值，不等于机制增量”。科学证据 `46f1b7f057f479da9547745c5fa657bdfff00a21`，PPT/交接 `d1d3b8027818cb8926316d2a825ca52016de76b8`。
- [x] MAGE 第 104 页 `pgz` 写后 29/29 PASS、真实截图通过；A8 section 6.25 / v29 已完成 61/61 核验，不再等待 RK06。
- [ ] 纯外部预训练模型替代、独立常数速度场臂、functional untouched、transport 与 generator authorization 未闭合；33 个 mechanism-test constructs 未读取，RK-G1=false，`DEV_NO_GO_TEST_UNTOUCHED` 不变。

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

## 2026-11-22：RK36 独立运输可行性审计与§四转向（执行交接文档核心指令）

- [x] **预注册冻结**：标签无关可行性协议冻结 R1–R7 合格要求（独立研究/宿主、完整 CDS、变体特异天然 5'UTR≥4nt、固定蛋白同义库、蛋白身份+family 映射、新鲜连续结局、隔离+溯源），合格⟺七项全 PASS；冻结于任何结局关联之前。协议 SHA `891023c8746b…`，冻结提交 `7942d6a9`。
- [x] **标签无关审计**：审计 4 个数据集（Kudla/Boël/Mordstein/MAGE infA），仅读 schema/覆盖/身份元数据，不做结局效应相关、不读 functional untouched。统一长表 25420 行/31 列**无 5'UTR 列**。结果 **0/4 合格**：Kudla R1 fail（训练队列）；Boël R3–R7 fail（跨蛋白天然非 synonymous、ordinal 0–5、固定 pET/T7 leader 无天然 UTR、family 映射缺失）；Mordstein R2–R3 fail（observed-R1 自 CDS pos4 起、缺 ATG/上游 4nt）；MAGE R2/R3/R7 fail（无完整构建、冻结禁读）。result SHA `9b02373b460a…`，科学提交 `eca9171d`。
- [x] **独立核验**：独立脚本重读原始源、重导判别事实与各数据集合格判定，**24/24 PASS**，确认 0 合格与 branch-3 转向。independent SHA `8b1c2bfbec7e…`。
- [x] **论文 §6.47**：新增 Table 27 可行性矩阵 + 缺失维度 + 转向计划 + 非主张声明；integration **12/12**、review **32/32** PASS；稿件 1931→1984 行，SHA `8011248f9686…`，提交 `cb528983`。
- [x] **在线 PPT**：在 169/revision140 后追加 170–173（4 页 `pSL/pSy/pSC/pSx`），p171 原地微调版面（revision145）；PPT 审计 **23/23** PASS（Table 27 逐格对冻结 result），4 张真实截图视觉复核 PASS；旧 169 页语义保持不变。脚本/小证据入 git `audits/20261122/RK36/ppt_v1/`，大型 XML/截图归档 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk36/ppt_v1/`。
- [x] **转向决策**：无合格独立运输数据 → §四 branch-3 记录 6 项缺失维度（同义库/天然 UTR/完整跨宿主 CDS/连续结局/family 映射/溯源），正式触发 branch-2 转向：停止以 start-aware MFE 为核心创新，转向数据支持的功能序列建模/翻译动力学；下一任务 RK37＝预注册翻译速度/功能预测 benchmark（RiboMIMO 等 bounded clean 数据，constant/ridge + CAI/GC + full-proxy MFE + 通用序列模型 baseline，蛋白/研究 OOD，SOTA 须配对 95%CI 下界>0 + 多重性 + 100% legality + 完整成本）。佐证：RK23 Boël 蛋白 OOD 0/4（Holm p=1）+ RK25 机制 0/2 已构成跨蛋白跨宿主运输失败。
- [x] **项目测试与 closeout**：`run_tests_json.py tests/` 得 **455 passed / 1 skipped / 0 failed**（18.17s）；closeout 全链路核验 PASS（协议/result/independent/integration/review/PPT/tests + 提交 + gates）。
- [ ] **仍未闭合**：external actual-set SOTA 主矩阵、time-matched 七方法、完整 dense、多物种 VeloHARMO、functional protein OOD、独立确认、wet-lab/前瞻 DBTL；RK37 转向任务待启动。RK-G1=false、generator_training_authorized=false，不得启动昂贵生成训练或把本 closeout 写成 RK-G0–G4 全通过。
- [ ] **复现边界**：本轮为标签无关可行性审计，无模型拟合，故无干净复现对比（不适用）；PASS 仅覆盖冻结协议、独立重导、稿件与页面验收及项目测试。权威工作树 `/home/codonflow-a8-rk`、分支 `a8-rk`，与并行会话共享并发提交。

## 2026-11-22：RK37 跨研究翻译占据局部序列诊断（双终点显著反向，任务未解决）

- [x] **预注册与生产**：冻结 Mohammad16→Subtelny14 的 study OOD 协议；source 1761 raw/1179 eligible，target 5614 raw/3921 eligible，exact CDS overlap=0。3 seeds×4 families×4 alphas=**48 次唯一 Ridge fits**全部在读取 target outcome 前完成；主候选 `local_centered_anchored`，部署锚定只用 source 均值。冻结提交 `5786ffc0`，生产 155.860567s。
- [x] **双确认性终点均失败**：constant−local TB-MSE 改善 **-0.755228937381**，95%CI `[-0.762597457560,-0.748005346336]`，Holm p=`9.99950002499875e-05`；local−position raw mean Pearson 改善 **-0.033028385490**，95%CI `[-0.035758013452,-0.030296139561]`，Holm p=`9.99950002499875e-05`。两个 CI 全负、两个 sensitivity seeds 均同号为负；小 p 值表示稳定变差，绝不写成通过。
- [x] **组件诊断而非事后调参**：主种子 constant TB-MSE=0.9669159810；position raw=1.0069665422、r=0.0375001498；local centered=1.7221449184、r=0.0044717643；RiboMIMO raw/anchored TB-MSE=2.1866082213/2.1580795860。position centering 仅增约0.000488 Pearson，source anchoring 未挽救 local 或 RiboMIMO 误差；没有在同一 target 后选“最佳臂”包装确认。
- [x] **独立复核与 clean reproduction**：独立 COO→CSR 实现从原始矩阵重算48 fits、全部预测、系数与推断数组，**771/771 PASS**，最大数值差 `3.552713678800501e-15`；detached `/home/codonflow-rk37-clean-493a0a70` 重跑48 fits，比较 **877/877 PASS**，111个 NPZ arrays 精确一致、3个逐转录本 CSV 字节一致。提交 `b8cf49c7/493a0a70/066ee562/87a33bd4`。
- [x] **测试与科学 closeout**：全项目 **466 passed / 1 skipped / 0 failed / 5 subtests passed**；最终 `rk37_science_closeout_v2.json` **90/90 PASS**，推送后复验仍90/90。初版 `88/90 FAIL` 与三次 verifier schema KeyError 日志均保留；修正仅涉及证据读取和日志格式，不改科学代码或结果。
- [x] **英文稿 §6.48**：证据驱动生成 Tables 28–29，稿件 **2,039 行**，SHA `ff1fe05bfc761a8026b2528082fdb354ef5ba717c8f02b0d60e5a7cea1b76368`；integration/audit **16/16 PASS**，含精确回滚、双表唯一、负 decision 和证据边界。隔离 `paper-write-en` workflow prepare/write/deliver/status 全 PASS；提交 `f2108c0d`。
- [x] **在线 PPT**：在173页/revision145后只追加 **174–180** 七页，ids `pSf,pSB,pSR,pSO,pSU,pSh,pSG`，最终 **180页/revision152**；写前 **61/61 PASS**、写后 **54/54 PASS**，前173页 ID+语义 XML 未变，七页真实预览均逐页验收。提交 `192f7b40`；大型 XML/预览位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk37/ppt_v1/`。
- [ ] **科学任务仍未解决**：RK37 仅证明该局部线性翻译占据候选在此跨研究方向稳定反向，不支持 translation-speed、protein/homology OOD、untouched confirmation、SOTA 或生成器性能。下一项 RK38 先逐方法×任务×格盘点 GEMORNA/LD-scan/CAI-greedy 等真实运行证据，同时对翻译/功能未触碰队列做 label-free 盘点；核实前不预设主矩阵可闭合或新实验可执行，不得在同一 Subtelny14 target 继续调参后称为独立确认。
- [ ] **总项目开放边界**：完整 external actual-set SOTA、time-matched 七方法、共同 dense、多物种 VeloHARMO、真实 functional/protein OOD、独立 untouched 和前瞻 DBTL 仍未闭合；RK-G1=false、generator_training_authorized=false、functional untouched 未读、wet-lab 未执行。

## 2026-11-22：RK38 真实 baseline 与 untouched 元数据盘点（资产闭环，科学门禁未闭合）

- [x] **冻结真实布局协议**：逐文件 SHA、record/seed/method、原始 DNA 序列集、500 点连续预算、唯一序列和成本字段均按实际 schema 读取；禁止把缺失 dense AUC、重复调用、forward 或统一时间零填充/推断。协议 SHA `025006e43ec1bc5ba17c53ea1b4771cb89ffd3cb61bb4229bddf2f3a75eeaadf`。
- [x] **完成 846 + 126 真实覆盖**：846 个原始运行/方法格（A7=324、RK06=216、A6=270、LinearDesign-11=18、EnsembleDesign-11=18）与 18×7=126 个 seed0 外部 actual-set 格全部核验；126 格原始 DNA 序列集与 RK13 矩阵精确一致。RK16 的 792 次 B11 generation calls 独立保留。
- [x] **外部结果仅作描述性参考**：LinearDesign-11 平均 normalized HV=`29.9728874903` 为七方法描述性最高，但总实际输出仅131且输入语义、共同 dense 与成本口径不齐；不得写成 CodonFlow 胜负、外部 SOTA 或 time-matched 结论。
- [x] **untouched 保持关闭**：仅读取 MAGE infA 既有 split 摘要、独立验证和元数据；19,072 行/13,569 groups 只有1个 operational cluster，362 行 synonymous single-codon 不能支撑多蛋白普遍结论。`new_functional_labels_read=false`、`functional_untouched_evaluated=false`；RK20 仍仅2/8 sequence-OOD 通过。
- [x] **独立与 clean 验收**：独立 v2 **1851/1851 PASS**，clean independent **1851/1851 PASS**，clean closeout **9/9 PASS**；详细与外部格 CSV 逐字节一致，bounded summary 一致。全项目 **472 passed / 1 skipped / 0 failed / 5 subtests passed**。首版独立失败及所有 schema/layout 修正记录均保留。
- [x] **英文稿 §6.49**：新增 Tables 30–31，2,096 行，SHA `7660294a876314c5ed9b24d70e49c68be3199d995f24cf53be0246d47a600f61`；隔离写作 workflow 全 PASS，integration/audit **19/19 PASS**；科学提交 `83469e5b`，论文提交 `dfc7cc69`。
- [x] **在线 PPT181–186**：六页 IDs `pSW,pSc,pSD,pSq,pSe,pSa`，最终 **186页/revision158**；内容/几何审计 **15/15 PASS**，前180页无语义 XML 差异，六张最终在线截图人工验收无截断/溢出/遮挡/缺列，closeout **11/11 PASS**。v1/v2 失败审计保留；PPT 提交 `0cb827ed57b438868ea0efc352f3cc21cf4ec3bf`，大型归档 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk38/ppt_v1/`。
- [x] **文档 closeout**：独立核验 registry/tasks/handoff、论文/PPT 哈希和科学边界，v2 **23/23 PASS**；v1 21/23 的 `n_pass/n_checks` 字段假定失败保留。
- [ ] **科学任务仍未闭合**：本轮状态仅为 `PASS_INVENTORY_ONLY_SCIENTIFIC_GATES_UNRESOLVED`。完整 external SOTA、统一 time-matched、七方法共同 dense、多物种 VeloHARMO、真实 functional/protein OOD、独立 untouched、前瞻 DBTL、RK-G1 和可投稿稿件均未完成；昂贵生成训练未授权，wet-lab 未执行。
- [ ] **下一项必须产生判别证据**：RK39 优先核实同一蛋白、同一初始化语义、同一真实 scorer 与完整成本口径下的 fixed-protein actual-set 对照是否可真实执行；满足冻结条件才运行，否则转向新的合格数据源判别实验，不再重复同类盘点。

## 2026-11-22：RK39 共同输入、固定 TAA 与等实际输出数对照（双终点显著负向，任务未解决）

- [x] **公平性缺口转为冻结协议**：确认旧 simple-search 的 `synonymous_x0` 不是天然 CDS，且 LinearDesign-11/EnsembleDesign-11 外部实际输出全部为 TAA。新协议仅以天然 CDS 翻译蛋白，随后丢弃天然同义选择与终止子；protein-only 首同义密码子模板加随机初始化，固定 TAA，搜索不使用天然 calibration normalization，评价阶段对所有方法施加相同归一化。协议 SHA `6e72fc94bd395a524fd2ecc825625f17c0bb86583fda3871e338f0508f1d15e1`。
- [x] **真实执行与配对规则**：18 records ×3 seeds ×3 methods ×11 点，共 **162 runs / 1,782 unique-scorer calls**；每 record 按 LinearDesign-11 的真实唯一 DNA 数 k 取 simple-search 前 k 个 unique-scorer 输出，禁止 best-k、补零、事后子集或推断外部 dense。k 合计131、均值7.278、范围4–11；四个单线程 workers，wall=342.521745 s，逐 run scoring 总和=1311.997885 s。
- [x] **双主终点均显著反向**：hill-climbing−LinearDesign-11 的 normalized HV 效应=`-29.7146177809`，95% CI=`[-41.9256988380,-19.5525350779]`；pairwise NED 效应=`-0.0665977004`，CI=`[-0.0822465948,-0.0511346818]`；两终点 Holm p 均为 `9.99950002499875e-05`，18/18 records 和3/3 seeds 均为负。状态为 `COMMON_INPUT_ACTUAL_SET_TASK_UNRESOLVED`，小 p 值表示稳定变差，不是通过。
- [x] **绝对表现与敏感性不救回主门禁**：LinearDesign-11 HV/NED=`29.9728874903/0.0712892803`；hill-climbing=`0.2582697094/0.0046915799`；MH-annealing=`0.2593831165/0.0048574044`；uniform=`0.7202456320/0.2408663156`。uniform NED 效应=`+0.1695770352` 且18/18为正，但 HV 效应=`-29.2526418583` 且18/18为负，只是质量—多样性代理权衡。
- [x] **独立与 clean 验收**：独立复核不导入生产脚本，重翻译蛋白、重建初始化、重算四目标、HV/NED 与推断，**1216/1216 PASS**，独立重评1,594条唯一序列，四目标最大绝对误差0.0；clean 完整162 runs后逐点 closeout **830/830 PASS**。全项目 **477 passed / 1 skipped / 0 failed / 5 subtests passed**。科学提交 `b3f89b948b707a56e9ae9ab8e9726a5fa0acaa41`，clean/论文提交 `9bbac1a68a8f71cfa328a15cc3fd270ed933590a`。
- [x] **英文稿 §6.50**：新增 Tables 32–33，稿件2,154行，SHA `611a0ceec7adb305fdfb47f6ac2566b37c2e500ffd8210a49835e3d0439230bf`；隔离写作 prepare/write/deliver 全 PASS，638词小节、0 failure/0 warning，幂等集成两次输出一致。首次缺依赖与两次远程内联 shell 失败均保留，未绕过门禁。
- [x] **在线 PPT187–192**：六页 IDs `pSA,pSr,pSH,pSd,pSb,pSF`，最终 **192页/revision164**；逐页预上传审计合计 **421/421 PASS**，每页在线 XML 文字精确一致并完成真实截图人工复核。第192页初版标题溢出在上传前拦截并修正；新增前186页结构/属性/文字全部一致，第186页仅末尾两个序列化空格差异。PPT closeout=`audits/20261122/RK39/rk39_ppt_closeout.json`，大型归档 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk39/ppt_v1/`。
- [ ] **科学任务仍未解决**：共同输入与等实际输出数只消除一类公平性混杂，不构成 CodonFlow 胜利、外部 SOTA、time-matched、共同 dense、功能/protein OOD 或 untouched confirmation。完整七方法统一成本、真实功能标签、前瞻 DBTL 和 wet-lab 均未完成；RK-G1=false，昂贵生成训练未授权，manuscript_submittable=false。
- [ ] **下一项必须是机制可判别实验**：优先预注册预算／初始化诊断，区分“短预算不足”与“protein-only 初始化／目标景观不匹配”是否导致 RK39 的巨大 HV 缺口；外部 LinearDesign 只能使用真实可执行的新预算轨迹，不能从 actual-set 反推 dense。若没有可执行的公平外部对照，则转向新的合格数据源，不重复同一11点负结果，不以敏感性臂或工程数量包装胜利。
