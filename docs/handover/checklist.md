# Checklist（A6 验收追加版 · 2026-10-26/27）

> A-H/J-K 的旧勾选只保留历史轨迹。A6 审计发现其中若干项虽然产物存在，但科学验收不成立；当前以本节为准，不用旧勾选推导 Gate C。

## L. 当前有效验收

- [x] L1 全量交接与代码审计完成，核心实现/数据/预算问题有明确证据。
- [x] L2 v3 精确重叠报告生成，旧“零泄漏/family-disjoint/18 unique”撤回。
- [x] L3 v4 776,474 唯一蛋白；所有 split 与 benchmark 精确 CDS/蛋白交叉重叠为 0。
- [x] L4 有限步 Markov 精确小状态 Doob 验证；真实大空间仅称短 rollout 近似。
- [ ] L5 真实 56M 多步基础核 on-policy path-RLOO 稳定性通过；此前引导路径配基础核概率的一步结果只作历史诊断。
- [x] L6 本地/远端 98 tests 全绿；正确 GEMORNA nanoLuc 1/1 身份冒烟通过。
- [x] L7 训练配置含数据 SHA256、代码 commit、固定验证 corruption；R1 失败日志保留。
- [ ] L8 edited-token/full-token 两臂分别到独立验证 plateau，best/last/training_state 一致。
- [ ] L9 immediate/short-rollout/frozen 同预算 pilot；v4 三臂成本与冻结 checkpoint 冒烟已通过，多基因、3 seeds、收敛模型和统一预算尚未完成。
- [x] L10 GEMORNA 100 次采样得 81 唯一合法解、0 身份错误；不补足独立解。其余 baseline 待补齐。
- [ ] L11 完整方法池联合 HV、缺失/零值检查与统计不确定性全部通过。
- [x] L12 数据审计图、全量分布图、真实 baseline 图、机制/成本图与 43 页 PPT 已验收；旧错误 nanoLuc 已替换、旧结果标为历史探索。预印本待新证据。
- [x] L13 GPU queue 完整生命周期与日志监控通过；主要代码 commit 已推送，最终三端结果清单待训练结束。
- [ ] L14 Gate C 以 A6 新证据裁决；未达成时明确 No-Go/降级。
- [x] L15 v4-test 长度分层 18 条 benchmark 独立审计通过：全部逐字来自 test、18 unique ID/CDS/蛋白、train/val 精确重叠为 0、哈希一致。
- [x] L16 protein-homology-cluster v5 与独立审计完成；不是 curated family 注释。species 元数据与相应泛化验证仍未完成，不作 species-OOD 声明。
- [x] L17 按用户要求完成收尾：full-data RLOO 队列取消，不再新增实验；训练、baseline、旧 legacy 和监控会话全部停止。
- [x] L18 两臂 epoch-6 best/last/training_state 与 manifest 已冻结并核对哈希；明确标记 stopped_not_converged，恢复入口见 HANDOFF。
- [x] L19 unique18 的 10 条完整记录已完成身份/解数/哈希/CAI/GC/motif 审计；1 条部分运行、7 条未启动已记录，MFE/NED 留待主表前全量复核。
- [x] L20 2026-10-30 两臂 training_state 可加载、CUDA matmul 通过并恢复；**但 21:11 的并行恢复在 21:14 因 edited-token 臂 OOM 失败**（证据在 `a6_v4_56m_r2/train.log`），已按 L21 修复重启。plateau、冻结 checkpoint 与完整下游验收仍未达成。
- [x] L21 单卡共存修复：`--gpu-mem-fraction` 硬上限 + `expandable_segments`；23:36/23:37 两臂并行重启（0.58 / 0.30），有效 batch 均 60,000 token，micro-batch 差异已在 spec 披露。
- [x] L22 unique18 seed-0 以 `--resume` 在原目录续跑（23:45，MFE_PROCS=8），不新建数据目录；完成 10 条 + 1 条部分，其余 7 条在跑。
- [x] L23 PPT 修订：45 页；新增指标口径与论文逻辑链页；第 10/19/34/35/43 页重写；表格逐项对照核验 JSON；微软雅黑全量统一；无越界形状、授权页字形精确测宽无溢出。

## 历史 Checklist（原样保留，非当前验收依据）

# Checklist

> 项目：CodonFlow（密码子级离散流 mRNA 编辑器）｜验收清单
> 使用规则：实现完成后逐项核验并勾选；任一项失败 → 在 tasks.md 增补修复任务并重新核验。

## A. 调研与立项依据

- [x] A1 GrammarRL 论文（arXiv:2609.39869）已全文精读：RLOO 配方（N=3+beam 混入、β=0.02、λ=0.5、LoRA r=64）、双奖励公式、消融数字均已抄录入 `docs/paper_notes/grammarrl.md`
- [x] A2 pCoMole 论文（arXiv:2610.01663）已全文精读：门控终端分布式(9)-(12)、短 rollout 近似式(13)-(15)、log-domain 技巧（附录 B）、采样超参（附录 H）均已抄录入 `docs/paper_notes/pcomole.md`
- [x] A3 pCoMole 代码开源地址已核实（huggingface.co/ChatterjeeLab/pCoMole）并已克隆锁定 commit
- [x] A4 基线生态找全：codonGPT（NAR 2025）/ mRNAutilus（2605.31296）/ ProMORNA（2605.01513）/ LinearDesign / RayGun / SCISOR 均有出处与实现路径记录
- [x] A5 评测生态找全：CAI（Sharp & Li 1987，HPA 参考集）、RNAfold 2.6.4、NED 定义、Pareto hypervolume 计算方式均已定义并给出处

## B. 数据与任务（R2）

- [x] B1 预训练语料 ≥1M CDS（GENCODE/RefSeq 人类），来源 URL + 下载日期 + 哈希已记录
- [x] B2 清洗规则全执行：MMseqs2 0.8 去冗余、去截短/内部 stop、长度过滤、簇级 80-10-10 split
- [x] B3 数据分布审计图（长度/GC/CAI/RSCU）四维入档
- [x] B4 编辑任务基准集就位：eGFP/nanoLuc/SpCas9 + 跨家族 OOD 代表序列
- [x] B5 family-disjoint OOD split 定义文件存在且与训练集无簇重叠（近邻审计通过）

## C. 方法实现（R3、R5）

- [x] C1 密码子级 Edit Flow 主干：67 token 词表、阅读框同步编辑算子、损失式(6)实现
- [x] C2 可行性门控终端分布：G(x)=exp(β·ATC)·𝕀[身份∧阅读框∧终止密码子]，log-domain 实现
- [x] C3 Doob-h 引导：候选×rollout 重加权式(15)，稳定 softmax
- [x] C4 三足评分器（CAI/RNAfold/翻译一致性）全部无学习组件
- [x] C5 RLOO 双奖励：direct 长度归一化无约束概率 + reverse 硬翻译一致性 + σ 校准 + LinearDesign 解混入组
- [x] C6 超参数均按 spec R5 预注册范围设置，无未注册超参进入主表

## D. 训练纪律（R6）

- [x] D1 GPU 并行且占满：DDP 4-6 卡 A100，显存利用率曲线入档（利用率 <80% 的 run 有书面解释）
- [x] D2 训练到收敛：预训练验证损失 3 epoch 相对下降 <0.1% 判据触发记录；RLOO 奖励平台期判据记录；无「中途截断宣布结果」
- [x] D3 REGISTRY.md 逐 run 登记完整（run_id/GPU 配置/超参全量/数据版本 commit/最终指标/收敛判据触发点）
- [x] D4 GitHub 仓库 `codonflow` 建立（远端 git@github.com:Cunyu-Liu/codonflow.git，独立 init 零共享历史）：main 分支保护、每 task 一 PR、负结果不删除
- [x] D5 大文件纪律：checkpoint/评测输出/语料在 /mnt/cunyuliu/codonflow/，home 无大产物（抽查 home 磁盘占用确认）
- [x] D6 监控与告警：GPU 心跳 30 分钟采样、OOM/NaN/进程死亡自动通知，巡检日志每周归档
- [x] D7 停止条件（预注册 5 条）全部写入实验代码的断言/检查点，触发即停并归档证据
- [x] D8 GPU 显存排队脚本上线：轮询→队列 FIFO+优先级→自动提交→状态回写→异常告警全链路实测一次（含多卡 DDP 判定）

## E. 评测充分性（R7）

- [x] E1 主表：CodonFlow vs 4 基线 × ≥3 家族 × ≥3 seeds，5 指标（合法率/身份保持/Pareto hypervolume/NED/单序列成本）
- [x] E2 OOD 表：family-disjoint 切分 generalization gap 已报告
- [x] E3 消融表：去门控/去 Doob-h/单 direct/单 reverse/碱基 vs 密码子级，数字齐全
- [x] E4 λ 与 β 敏感性扫描完成
- [x] E5 预测器独立性检验（换第二参考表）通过——多目标提升不消失
- [x] E6 预注册成功标准核对：身份保持 100% ∧ 合法率 >99% ∧ hypervolume 提升 ≥10% ∧ NED ≥ 基线 70% ∧ OOD 衰减 <2pp
- [x] E7 侧重 OOD 的专项分析：低同源/跨家族场景下的性能保持报告（借鉴 RipplePLM 双切分与 mRNABench homology-aware 协议思想）
- [x] E8 叙事-现象对应表逐行有图：六条叙事推进各有可指认的实验现象图，无「叙事无证据」行
- [x] E9 弱链对照落实：EXP-2 用「同预算后置过滤」而非简单门控开关；EXP-5 锚定双/四目标（单目标如实认输 DP 最优）且 LinearDesign 给同等 100 解预算（权重扫描）
- [x] E10 统计口径执行：六实验 ≥3 家族 × 3 seeds、KS/Wilcoxon 配对检验、图型先冻结后出数

## F. 交付物

- [x] F1 3 个 MD 文档（spec/tasks/checklist）已落盘 `/Users/liucunyu/Documents/课题idea 数据 结论/浙江大学/RNA 相关模型/CodonFlow-密码子级离散流mRNA编辑器/`
- [x] F2 学术汇报 PPT 已落盘同目录：微软雅黑字体、1.5 倍行距、逻辑链完整（科学问题→数据→方法→实验→SOTA→发表→执行路线）
- [x] F3 汇报讨论问题清单（3 个开放问题）已附
- [x] F4 PPT 程序化检查通过：字体一致（无缺字体回退）、无文本溢出、页面布局无异常

## G. 决策门

- [x] G1 Gate A（基线量级一致）：Go/No-Go 记录在档
- [x] G2 Gate B（门控可行 + 成本可承受）：Go/No-Go 记录在档
- [ ] G3 Gate C（成功标准达成）：Go/No-Go 记录在档
- [ ] G4 若任一门 No-Go：降级路线或负结果归档执行完毕（不静默放弃）

> 勾选状态说明（2026-10-23 冻结点二次核验，见文末更新）：A4/A5、F1-F4 已核验通过；A1-A3 的「落档/克隆」动作属 Phase 0 任务（调研内容已完整形成于本会话，未落仓库笔记）；B-G 为实验执行期检查项，待后续。
## H. tasks v3 工程对齐核验（2026-10-04 增补）

- [x] H1 0.2.5 排队脚本全链路冒烟通过（提交→运行→回写→告警）
- [x] H2 1.1.5 基准序列所在 MMseqs2 簇已从训练 split 剔除（泄漏防护）
- [x] H3 1.2.2 LinearDesign 单序列耗时基准已入 REGISTRY（停止条件④分母）
- [x] H4 2.2.2 ATC 四目标按 Amendment A1 归一化，定标量冻结于 configs/atc_norm.yaml
- [x] H5 2.2.3 评分缓存命中报告 ≥60%（RNAfold 去重）
- [x] H6 3.1.1 direct 用无约束概率、reverse 硬翻译、σ 校准集与训练/测试互斥
- [x] H7 3.3.1 停止条件五条已代码化（src/eval/stop_checks.py 断言）并有单测
- [x] H8 全部任务带 DoD，spec↔task 对齐索引表与实际任务一致

## I. 2026-10-23 冻结点核验更新（证据位置：/teams 公共目录 + GitHub main=c850478）

- [x] I1 上述 A-H 勾选依据：paper_notes（A1/A2/A3 落 docs/paper_notes）、语料 v3 862k（B1-B5，corpora md5 对账）、src/ 各模块单测（C1-C6）、REGISTRY.md（D3）、watchdog v3-v8 + cron（D6/D8）、stop_checks.py（D7）、E1-E10 全部 JSON 在 eval_outputs（E 系）+ gate_A/B.md 在档（G1/G2）
- [ ] I2 G3 Gate C 未决：依赖 355M 收敛 + 全量评测（冻结未完成）；G4 未触发（无 No-Go）
- [ ] I3 355M 收敛 + v3rloo 9 arm 补全 + fig10 终版 → Gate C 判定（恢复路径见 tasks.md v4）

## J. 2026-10-23 冲刺期核验（新集群恢复，见 tasks.md v5 / REFLECTION_20261023.md）

- [x] J1 新集群资产盘点 + md5 对账（语料 3 件 / 56M converged / 355M last）
- [x] J2 代码运行副本 /home/codonflow 部署（HEAD eef0310，tree clean）
- [ ] J3 环境重建验收：torch cuda True + ViennaRNA API + pytest 41/41 全绿（5090）
- [ ] J4 355M 续训拉起 + watchdog 5090 适配（显存 ≥28GB 占用截图/记录）
- [ ] J5 v3rloo 26/26 JSON + RLOO 增益裁决（对照表落档）
- [ ] J6 Cas9 motif 归一化 + adaptive reference 全量重算（A4 口径，amendment 披露）
- [ ] J7 355M converged.pt + 17/17 评测 + 容量曲线第三点 → Gate C 判定
- [ ] J8 主图 house-style 重制（PDF+PNG 双格式）+ 叙事-现象对应表复核
- [ ] J9 预印本 v1（三幕结构）+ PPT 更新 + GitHub 最终 commit + 三端备份
