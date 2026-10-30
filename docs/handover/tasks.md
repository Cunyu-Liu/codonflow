# Tasks（A6 证据链修复版 · 2026-10-26/27）

> 历史 v5/v6 产物只作 legacy exploratory；本文档为当前验收队列。每项只有实际证据满足才勾选。

## 恢复冲刺（2026-10-30，当前执行）

- [x] R6.0 通读全部交接文档并盘点远端；确认无新增结果、无残留任务，当前 RTX 4090 24GB（uptime 2:09，实例于 21:02 重启）。
- [x] R6.1 两臂 training_state 可加载、CUDA matmul 通过；21:11 并行恢复。
- [x] R6.1b **21:11 的并行恢复失败**：edited-token 臂 21:14 首个 batch `torch.OutOfMemoryError`（free 202 MiB），会话 `a6_edit_resume` 退出；证据在 `a6_v4_56m_r2/train.log`。根因：两臂各 20000 token micro-batch 在 24GB 上无法共存（各需约 11–12 GiB）。
- [x] R6.1c 修复并重启（23:36 / 23:37）：`run_pretrain.py` 增加 `--gpu-mem-fraction` 硬上限 + `expandable_segments`；full-token 0.58（20000×3）、edited-token 0.30（10000×6），有效 batch 均 60,000 token；micro-batch 差异已写入 spec 披露段。full-token 从 epoch-7 state 恢复，损失约 35 分钟无 checkpoint 的半轮。
- [ ] R6.2 两臂分别到独立验证 plateau，冻结 converged/best/last/training_state 与哈希。当前 full-token e8 loss 2.8270 / val e7 2.814013；edited-token e7 loss 4.3842 / val e6 4.385477；均未 plateau。
- [ ] R6.3 unique18 seed-0 断点续跑中（23:45 启动，`a6_u18`，MFE_PROCS=8）：10 条完整 + C05E11.2.1 部分，剩 7 条；完成后再补 seeds 1/2 与全量独立审计。
- [ ] R6.4 收敛冻结模型上完成多基因 3 seeds、统一预算、联合 HV、四成本与统计对照。
- [x] R6.5 PPT 修订完成（45 页）：新增指标口径页与论文逻辑链总页；重写第 10/19/34/35/43 页；A6 四张图与全部表格按核验口径更新；统一微软雅黑与 1.5 倍行距（表格 1.2–1.3，两处 legacy 密集页按可用间距封顶）。未完成实验一律标“待裁决”。
- [x] R6.6 证据复核：GEMORNA A6 n=81（identity 81/81、CAI 0.9212/0.9684、MFE −194.3/−217.6、GC 0.5936）；v5 审计 776,441 保留 / 128 排除 / 三项 split 全 0 重叠；unique18 JSON 12 个（10 done + 1 running + 1 audit）。
- [x] R6.7 表格逐项复核（详见 JOURNAL 第 7 节）：第 36 页 L1 行的 CodonFlow 原值（32.4±5.9 / 128.1±16.6）在两份现存 artifact 中都无法复现，已按 `E5v2conv_main_table.json` 重算为 31.9±5.9 / 112.9±21.5；`uniform_edit_flow` 误标为“Uniform”已改为“裸编辑流”；L2–L4/R4 与第 37 页因源 JSON 未迁移，标为“不可复核、不得引用”；第 14 页 ProMORNA 行改为“仅据原文自述、实现与权重未在本仓库锁定”，不再使用未经证实的机制推断。

## 收尾交接（2026-10-27，历史状态）

- 用户要求停止新增实验并交接；full-data RLOO 队列已取消，旧 legacy、训练、baseline 和监控会话均已停止。
- 两臂在 epoch 6 安全停止并冻结 best/last/training_state，均未 plateau；恢复时必须使用 `handoff_epoch006_training_state.pt`。
- unique18 完成 10/18，C05E11.2.1 为部分运行，另 7 条未启动；10 条完整记录的收尾审计通过，MFE/NED 未做全量独立重算。
- 当前不能提交预印本或宣布 Gate C。完整问题、未完成事项和禁止事项见 [HANDOFF_20261027_WRAPUP.md](HANDOFF_20261027_WRAPUP.md)。

## P0 数据、方法与训练

- [x] A6.0 全部交接文档、journal、PPT、代码与运行状态审计；恢复持久 SSH。
- [x] A6.1 全量精确 CDS/蛋白审计；确认旧跨 split 重叠、HELD18 重复与错误 baseline。
- [x] A6.2 有限步同义 Markov 编辑器、短 rollout Doob 近似与可微路径概率；精确小状态验证。
- [x] A6.3 `splits_v4_protein`：776,474 唯一蛋白，独立审计所有精确交叉重叠为 0。
- [x] A6.4 真实 56M 一步 path-RLOO 冒烟：identity=1.0，效用进入奖励，loss/logp/grad 有限。
- [x] A6.5 本地/远端 98 tests 全绿；历史交接已合并推送，最新修复通过 bundle 同步，GitHub 网络恢复后补推。
- [ ] A6.6 edited-token 在 epoch 6 停止，val=4.3854775，未 plateau；best/last/training_state 已冻结，后续从 handoff manifest 精确恢复。
- [ ] A6.7 full-token 在 epoch 6 停止，val=2.8195373，未 plateau；best/last/training_state 已冻结，不与 edited-token 直接比较 val。
- [ ] A6.8 小样本 immediate vs short-rollout vs frozen control；v4 三臂成本冒烟已用冻结 epoch-5 checkpoint 通过，后续在收敛模型上扩到多基因 3 seeds 和统一预算。
- [x] A6.9 正确 GEMORNA nanoLuc 批量结果与身份报告：100 次调用得 81 个唯一合法解，0 身份错误；CAI 0.9212、MFE −194.32。其余 baseline 仍待补齐，LD 不随机补样。
- [ ] A6.10 旧 355M/RLOO 队列自然结束，归档 legacy；旧 verdict 不作为 Gate C 依据。

## P1 证据、图表与预印本

- [x] A6.11 v4-test 18 条长度分层 benchmark 冻结并独立审计；全部来自 v4 test、唯一 ID/CDS/蛋白、train/val 精确重叠为 0。不是 HELD18 去重版，不作 species/family 声明。
- [ ] A6.12 联合 HV 完整方法池与预设 arms；缺失/零值显式报告，统计不确定性与置信区间随表。
- [ ] A6.13 按新证据制作机制、数据、学习、baseline、成本图，PDF+PNG 双输出；机制/成本图已完成，收敛对照与泛化图待新结果。
- [ ] A6.14 预印本主线重写：测量→机制→学习/泛化→边界，撤回无证据的 SOTA/scaling/masking 因果。
- [x] A6.15 PPT 只录入核验结果：新增数据审计、证据分级、全量分布、真实 baseline 与机制/成本页；43 页新增范围 0 issues、内容与中文渲染通过。预印本正文仍待新结果。

## P2 工程与交接

- [x] A6.16 GPU queue 提交→active→done/failed 实测：隔离 `true` 作业与 REGISTRY 通过，无真实显存浪费。
- [x] A6.17 日志驱动训练监控已完成阶段任务；项目收尾时 watch/patrol 与所有科学计算会话均已停止，不再维持显存占用。
- [ ] A6.18 每个任务完成即独立 commit+push；三端核对 commit、数据哈希、结果清单。
- [ ] A6.19 Gate C 重审；新协议不支持时明确 No-Go/降级，不以旧勾选替代。
- [x] A6.20 protein-homology-cluster v5 聚类、连通簇排除和独立审计完成；776,441 保留、128 排除，split/benchmark 簇与精确重叠均为 0；不冒称 curated family/species OOD。
- [ ] A6.21 全参数 path-RLOO 在独立显存窗口完成多步稳定性与 held-out 评价；OOM 和 head-only 诊断不作为通过。

## 当前运行与证据锚点

- `checkpoints/a6_v4_56m_r2`：edited-token 56M，v4 数据，固定验证 corruption，运行中。
- `checkpoints/a6_v4_56m_fulltoken`：相同数据与有效 batch 的 full-token 对照，运行中。
- `eval_outputs/audits_20261026/v3_exact_overlap.json`：旧数据真实重叠。
- `eval_outputs/audits_20261026/v4_exact_overlap.json`：新数据精确重叠全 0。
- `eval_outputs/audits_20261026/rloo_smoke`：真实一步 path-RLOO 工程冒烟，不是性能结论。
- `eval_outputs/a6_baselines/GEMORNA_nluc_a6_scored.json`：81 个唯一合法解，0 身份错误，CAI 0.9212、MFE −194.32，已核验。
- `eval_outputs/a6_baselines`：所有新基线输出；正式主表需完整方法池后生成。
- `eval_outputs/a6_pilot/a6_three_arm_protocol_smoke_v4.json`：冻结 epoch-5（`74a542c1`）与代码 `2854ebb6` 的三臂成本协议冒烟；仅作诊断，不作收敛模型收益结论。
