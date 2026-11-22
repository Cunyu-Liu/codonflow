# 给下一位执行者的完整提示词（CodonFlow A9 · RK37+ · 阳性核心路线）

你现在接手 CodonFlow A9。**用户（项目 owner）已下达三项战略指令，本提示词是其执行化**：

1. **论文定位仅限阳性核心**——必须有一个公平击败最强可比 baseline 的阳性贡献；不接受阴性/资源型论文作为headline，也不把负结果预设为终点。
2. **RK-G1 授权**——生成训练已授权（`RK_G1=true`、`generator_training_authorized=true`），仅对 A9+ 新任务生效。
3. **重新补独立数据**——RK36 证明现有资产 0/4 合格独立数据，必须获取/构建新的独立数据作为阳性核心的验证基础。

先读：`docs/handover/DECISION_A9_20261122.md`、`configs/a9_positive_core_directive_v1.json`、`docs/handover/HANDOFF_A9_20261122.md`、`docs/handover/HANDOFF_A8_RK36_20261122.md`、`docs/handover/PROMPT_NEXT_AGENT_A8_RK.md`（历史铁律与 baseline 清单仍有效）、`experiments/REGISTRY.md`、`tasks.md`、`paper/CodonFlow_preprint_A8.md`。

**不要**从 RK01 重跑，**不要**重复 RK01–RK36 已验收资产，**不要**只输出计划。不要用工作量、训练收敛、拟合次数、PPT 页数或 closeout 数量代替核心性能。

## 一、权威工作树与状态核对

权威工作树 `/home/codonflow-a8-rk`，分支 `a8-rk`，remote `git@github.com:Cunyu-Liu/codonflow.git`。大型数据/权重/artifacts 放 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/` 相关子目录；代码与提交留 `/home`。

开始时重新核对 HEAD、origin/a8-rk、工作树、进程与结果文件（状态可能已变）。该工作树由多会话共享并发提交：**每次提交前 `git fetch` 重核 LOCAL/REMOTE，仅 stage 自己的路径，绝不 `git add -A`**；不得 `reset --hard`/`clean`/删旧资产/覆盖对方文件。服务器密码严禁写入文档、日志、git 或回复。

运行环境 `/home/codonflow-clean-env-v1/bin/python`（Py3.10.22/numpy2.2.6/pandas2.3.3/scipy1.15.3/sklearn1.7.2/ViennaRNA2.7.2/pytest9.2.0）。CPU 单线程 OPENBLAS/OMP/MKL/NUMEXPR=1；GPU 训练须先核对真实显存占用与授权。项目测试用 `scripts/run_tests_json.py tests/ <out.json>`（位置参数，非 --out）。

## 二、gates 与 SOTA 门槛（必须遵守）

gates（A9+）：`RK_G1=true`、`generator_training_authorized=true`、`new_independent_data_read_after_freeze=true`；**历史 MAGE functional untouched（19072 行/13569 组）仍冻结**，除非用户另行明确解封；历史冻结协议/结果不被追改。

SOTA 门槛（阳性核心验收）：预注册主效应 paired 95% CI 下界>0 + 多重校正通过 + 合法率100% + 成本完整（time/compute-matched）+ 蛋白/研究 OOD 分层保留。**未赢最强可比 baseline 的任务标"未解决"并继续定向诊断；不得换弱 baseline、不得删除失败分层、不得用更多训练/推理计算冒充架构优势。**

## 三、RK36 已确立的数据缺口（A9 的起点）

RK36 标签无关审计：统一长表 25420 行/31 列**无 5'UTR 列**；Kudla 是训练队列（R1 fail）；Boël 跨蛋白天然非 synonymous、ordinal 0–5、固定 pET/T7 leader、family 缺失（R3–R7 fail）；Mordstein observed-R1 自 CDS pos4 起缺 ATG/上游4nt（R2–R3 fail）；MAGE 无完整构建且冻结（R2/R3/R7 fail）。**0/4 合格**。合格要求 R1–R7 见 directive JSON，A9 复用。

因此 A9 的第一科学任务不是再切窗，而是**补上独立数据缺口**，然后在其上建立阳性核心。

## 四、阶段 B · 独立数据获取与审计（先做，公开优先）

B1 **公开候选逐源核实 raw**（不得只看摘要/clean 表）：Cambray2018、Kosuri2013、Goodman2013、Mutalik2013、Rhodius2012、Salis2011、Espah Borujeni2014/2017、de Boer2020、Lind2020 等 construct 级同义/表达数据。对每个候选用 R1–R7 判定：独立研究/宿主、每变体完整 CDS、**变体特异天然 5'UTR（ATG 上游≥4nt，固定载体 leader 不算）**、固定蛋白同义库、蛋白身份+family 映射、连续新鲜结局（粗 ordinal 不算）、隔离+license/accession/raw SHA。Cambray2018 固定 UTR 必须先核 raw 构建才可作运输主张。

B2 **若存在合格公开数据**：获取 raw → clean → 全量 SHA → 预注册划分（蛋白/研究/序列簇 OOD，同一蛋白变体不得随机跨 split）→ 泄漏审计 → 动态范围/检出限/缺失原因审计 → 功能值只在 `protein×host×assay×batch` 内标准化，RSCU/归一化/校准只由 train 拟合。结构特征区分 measured/predicted、完整 CDS/片段、精确起始窗/其他/全局、dangles 与温度。

B3 **若公开无合格数据**：设计前瞻 DBTL/湿实验构建独立数据（固定蛋白同义库 + 天然完整 UTR–CDS + 连续表达/适应度读数 + 独立宿主），**湿实验预算与延期须用户批准**；测量协议在读结局前预注册冻结。公开回顾验证与前瞻 DBTL 严格分开；无真实前瞻实验不写疗效/免疫原性/普遍表达提升。

B4 产出 `audits/<date>/RK37/independent_data_acquisition_v1.json`：候选清单、逐源 R1–R7 证据、合格判定、raw/clean SHA、划分与泄漏审计、动态范围；独立复核脚本重导判定。这是阶段 C 的输入门禁。

## 五、阶段 C · 阳性核心 benchmark 与 RK-G1 授权训练

C1 **预注册公平 benchmark**（读结局前冻结）：在新独立数据上，CodonFlow 生成/功能模型 vs 最强可比 baseline——full-proxy ridge、CAI/GC/局部与全局 MFE、Boël logistic、LinearDesign、EnsembleDesign、RNARL 官方快照（缺接口不得自修冒充官方）、CodonTransformer、COformer、RiboMIMO（速度）、通用序列模型（ESM/Transformer）。主终点蛋白/研究 OOD Spearman/RMSE/top-k enrichment；整簇 bootstrap/permutation + Holm；time/compute-matched 真实测量。

C2 **RK-G1 授权训练**：训练离散流/生成核心。小可枚举状态必须验证归一化、目标分布与采样一致；实现不符不得称 flow。合法核 `qθ(y|x;w,b,h,u) ∝ q0(y|x;h,u) exp[-βΣk wkΔΦk(x,y)-βcΔcost(x,y)]` 只在机制获独立支持后启用；`gk` 只由训练上下文学习并经独立 OOD 验证，不得按 test 调。超参只在 dev 用 ASHA/小网格，不得用 test/untouched 调参。

C3 **机制与阳性核心的关系**：start-aware 起始结构机制在新独立数据上重测；若运输且击败 baseline，可成为阳性核心的一部分；若不运输，阳性核心必须来自生成/功能模型本身击败 baseline，**不得**再把结构当既定核心。消融（去 initiation/velocity/decay/pair/自然先验/偏好/预算/transport）在机制授权后做。

C4 每个任务独立验收：独立 raw-source 复算 + 干净 checkout 复现 + 定向测试；未赢最强 baseline 标未解决并定向诊断，不伪造阳性。

## 六、模型架构从证据推导（不堆砌）

物理世界：真实 UTR–起始ATG–CDS 翻译起始几何、局部碱基配对、宿主上下文；全局 MFE 与局部 initiation potential 分开。数学世界：同义 simplex、局部势坐标、共享/上下文特异效应、域外不确定性、Pareto 偏好、完整成本。真实世界：宿主/assay/覆盖/测量误差/数据支持域；域外不外推。ESM/Transformer/MoE/GFlowNet/扩散/RL/普通 gate 本身都不是创新；pair channel 仅在真实多位点同义覆盖足够时进入主模型。架构答案必须证明比 simple、full-proxy ridge、无运输模型与最强外部方法更好。

## 七、逐任务 SOTA 矩阵（不合并虚假总排名）

功能/适应度、速度、Harmonization（VeloHARMO/CHARMING/tAI/ICOR/HFC/BFC/URC/RNARL）、Accessibility（ID3/GA/SA/C10/C10-CAI，同1000离散、可枚举精确 ceiling）、CDS 多目标（LinearDesign/EnsembleDesign/RNARL/CAGFN/codonGPT/GEMORNA/CodonTransformer/COformer/内部 hill/MH/SA/GA/random/r5，真实 dense HV AUC、实际 Pareto/best、NED、合法率、time-matched）。mRNAutilus/ProMORNA 仅在 UTR/输入/成本可比时比较。统一七方法 time-matched 在合规可控硬件真实测量；无真实轨迹的外部方法只比 actual set，缺失为 null，不伪造预算/时间。

## 八、论文阳性主线重定位

一旦在新独立数据上建立通过 SOTA 门槛的阳性核心，把英文稿 headline 重定位为该阳性贡献；**保留** RK29 映射失败、RK30/31 运输/gating 阴性、RK32 定义依赖、RK33 覆盖阴性、RK34 联合增量不可分离、RK35 覆盖非必要、RK36 数据缺口作为诚实边界/消融证据，不藏附录后仍宣称普遍机制。每个数字来自冻结 JSON，每个主张映射原始数据/对照/指标/反驳条件。**若阳性核心尚未建立，稿件保持 working 状态并如实报告阻塞，不得编造阳性。**

## 九、铁律与最终交付

每任务结束把确认好的代码推送 GitHub；结果先独立检查、没问题再写入在线 PPT（`WB1KsYGualerMUddEzMcCw1En0g`，简洁清晰大方美观，只追加、写后回读审计+真实截图验收、旧页语义不变）。每轮更新 `experiments/REGISTRY.md`、`tasks.md`、新 handoff（假设、commit+dirty hash、环境、数据/split SHA、完整命令/配置、seed、拟合数、forward/scorer/time、artifact SHA、指标版本、结果、不可声称事项）。为新实现补项目风格测试；每阶段定向测试+独立复算+端到端 smoke；最终 `pytest tests/` + 干净环境复现。verifier-only 修复不改科学值/容差；失败日志全保留。

最终回复必须包含：
1. 新独立数据的获取来源、质量、分布、划分与泄漏审计（R1–R7 逐源证据）；
2. 每个 baseline 的真实运行状态与公平性（time/compute-matched）；
3. 阳性核心相对最强 baseline 的效应、CI、成本与是否真正 SOTA；
4. RK-G1 授权下生成器训练、合法核归一化/采样一致性、消融结果；
5. 起始结构机制在新独立数据上的运输结论与边界；
6. 新增/修改文件、artifact 哈希、测试命令与结果；
7. 论文阳性主线哪些闭合、哪些未完成；
8. 任何阻塞及需用户决定事项（湿实验预算/数据源/算力/延期）。

## 十、立即行动

先核对工作树与进程状态；随即启动阶段 B 独立数据获取审计（公开候选逐源 raw 核实），产出 acquisition 审计与独立复核；若公开无合格数据，向用户提交湿实验/DBTL 设计与预算请求。**不要只输出计划，不要重复启动旧任务，不要把工程繁忙当科学进展。**