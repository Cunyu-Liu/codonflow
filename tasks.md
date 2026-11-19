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
- [ ] RK03-REMAINING：完成 UTR–CDS 映射/raw read 或 P-site 独立重比对可行性报告、VeloHARMO 其余物种真实可获得性追踪；不得把 processed-matrix QC 或 bounded GA 写成机制、五物种模型或功能闭环。

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

### RK-09 E3：跨层机制一致性

- **任务**：联合/分别预测 MAGE 适应度、Ribo 速度、Boël mRNA/蛋白层；在适用数据做分层或 mediation。
- **输出**：跨层一致性、结构/速度/降解消融、Fig.2 机制证据。
- **验收**：结论限定为关联，除非有干预；黑箱 reward 或 attention 图不得替代机制证据。

- **全量功能 OOD 更新（2026-11-19）**：retained train/dev/test=`4019/503/490`，sequence-OOD=`1336`；all 与 none 均为 4,997 参数，仅通道门控不同，2,000 次 cluster bootstrap。all−none 的 OOD ΔSpearman=`0.199016`，95% CI=`[0.129283,0.266863]`；ΔCB-MSE=`-0.276089`，95% CI=`[-0.377439,-0.180840]`。all−GC-only 两项 CI 也支持 all；但 all−full-proxy ridge 的 ΔSpearman=`-0.025779`，95% CI=`[-0.071103,0.019376]`，ΔCB-MSE=`-0.025572`，95% CI=`[-0.124069,0.076207]`，均不显著。**RK-G1 未通过**，不启动昂贵生成训练。该实验为跨蛋白、功能单监督，不支持固定蛋白机制或速度 OOD；完整重训 bitwise 一致，独立 `224/224 PASS`、finalization `48/48 PASS`。

**RK-G1 状态：未通过**。all 相对同骨干 none 和 GC-only 有增量，但未同时优于 full-proxy ridge；修数据/假设前不得启动昂贵生成训练。

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
- **当前进展（2026-11-19，V6 CodonTransformer sync）**：生成器纳入四份 CodonTransformer 冻结来源和哈希，新增官方 example/C01 的 default/match_protein 四行结果、4/4 legal、2 unique、README 精确匹配、独立 13/13 与 finalization 10/10；明确两种模式输出相同、约束收益未证实、推理成本含 warm-up，未授权 matched MFE/EFE、dense/主矩阵/功能 OOD/SOTA。A8 v6 SHA256=`1ac702be2b38900346064ebbc56a4b20a461089f317078db1df08c73774e0d35`，独立 **17/17 PASS**，commit=`f479955fefa034c5a5fde84c5f7ab37d85cf0044`；仍为 non-submittable working manuscript。
- **当前进展（2026-11-18，V7 VeloHARMO sync）**：生成器纳入 VeloHARMO 生产、独立与 finalization 三份冻结来源及哈希，新增 7 条长度选择记录的 CUDA 官方 test 诊断、population=8/generations=2 的 CPU GA、7 项兼容替换、未修改 GA 失败、2/2 合法同义和 best=start 的零迭代提升；明确 best-native 差值不是 GA 或实验功能增益，未授权五物种、正式训练/CV、主矩阵、功能 OOD 或 SOTA。A8 v7 SHA256=`078228450f69c1efe6b31f7bbf7dba0d01d004c9aecdf2f330f4ad32c985fe6d`，独立 **18/18 PASS**，commit=`9948b2ec251ae593ef9a864206cdd20672134923`；仍为 non-submittable working manuscript。

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
