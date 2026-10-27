# Tasks（工程级 v7 · 2026-10-26/27 证据链修复版）

> 当前执行以本节 **A6 修复队列** 为准；下文 v5/v6 仅保留历史执行轨迹。
> 代码 `/home/codonflow`，数据/权重/artifacts `/teams/HoulabData_1788502323/liucunyu/codonflow`；单卡 RTX 5090 32GB。
> 历史产物可以标 done，但不等于科学结论通过。所有新主结果须符合 `spec.md` Amendment A6。

## P0：阻塞新主结果（按依赖顺序）

- [x] A6.0 读取全部本地交接文档、旧 journal、最新 sprint、38 页 PPT 与代码；恢复持久 SSH；盘点 355M 与 RLOO 评测。
- [x] A6.1 核心代码审查：识别 immediate-ATC 冒充 Doob、旧 RLOO 路径概率/环境目标/校准问题、错误 GEMORNA nanoLuc 输入、LD 随机补样、HELD18 重复及跨 split 重叠。
- [x] A6.2 全量精确 CDS/蛋白审计：报告 `eval_outputs/audits_20261026/v3_exact_overlap.json`；不再声称零泄漏或 family-disjoint。
- [x] A6.3 新增有限步同义 Markov 编辑器与精确小状态 Doob 测试；实现短 rollout 和路径概率，明确近似边界。
- [x] A6.4 GEMORNA 身份检查、蛋白去重划分、联合 HV 工具、训练最优 checkpoint/RNG 保存与 RLOO 奖励修复；本地+远端 73 tests 全绿。
- [x] A6.5 `splits_v4_protein` 构建并独立复核：零 train/val/test 精确 CDS/蛋白交叉重叠；完整 benchmark 连通簇排除有记录；数量与分布落档。
- [x] A6.6 真实 56M checkpoint 的短 rollout + 路径 RLOO 一步冒烟：reward/grad/logp/identity 全有限，且 rollout 不是 immediate ATC 替身；多步 on-policy 稳定性另行验收。
- [x] A6.7 新预训练 56M 启动：使用新 split 与新输出目录；每 epoch 保存 best/last/training_state；两臂均在第二轮，未收敛，继续至 plateau。
- [ ] A6.8 小样本 immediate vs short-rollout vs frozen-model 同预算 pilot；epoch-1 两臂 4 路径诊断已完成并修正成本，冻结对照与多基因 3 seeds 待完成。
- [ ] A6.9 修正 GEMORNA nanoLuc 及全 baseline 重跑；LD 不再随机补样；完整方法池统一输出预算与成本口径。
- [ ] A6.10 旧 355M/RLOO 队列自然结束后只归档为 legacy exploratory；不以旧 verdict 作为 Gate C 通过依据。

## P1：论文与图表证据链

- [x] A6.11 v4-test 18 条长度分层 benchmark 冻结并独立审计：18 unique ID/CDS/蛋白，train/val 精确重叠为 0；不是 HELD18 去重版，不作 family/species 声明。蛋白同源 OOD 仍需单独构建。
- [ ] A6.12 主实验四口径：输出解数、唯一 scorer calls、模型 forward、端到端时间；补齐 E2/E6 预算重跑。
- [ ] A6.13 联合 HV 完整 arms/方法池核验，零值与缺失不得静默删除；统计检验与置信区间随表提供。
- [ ] A6.14 主图按新证据重制：机制示意、数据审计、immediate-vs-rollout、独立泛化、完整基线、成本/预算；PDF+PNG，单一数据源。
- [ ] A6.15 预印本主线重写：测量定义→有限步机制→学习与泛化→边界；撤回无证据的 SOTA、capacity/RL scaling 和 masking 因果断言。
- [ ] A6.16 PPT 仅录入 A6 验收结果，修正历史错误页；保留原模板身份，减少堆字，结论与图一一对应。

## P2：工程交付

- [ ] A6.17 GPU queue 提交→active→done/failed 全链路实测；避免同轮重复分配、run_id 冲突与假完成标记。
- [ ] A6.18 训练监控：每日定时检查训练日志、收敛、NaN/OOM 和队列，不频繁读取显存；资源仅用于真实训练/短 rollout/基线。
- [ ] A6.19 每个完成任务单独 commit + push；三端核对代码 commit、数据哈希和结果清单，不上传大型权重。
- [ ] A6.20 Gate C 重审：只有 A6 新协议主结果支持时才可勾选；否则明确 No-Go/降级，不用旧勾选代替裁决。
- [ ] A6.21 构建 protein-homology-cluster v5：唯一蛋白+benchmark 种子 MMseqs2 聚类、连通簇排除、独立泄漏/守恒审计；不冒称 curated family/species OOD。
- [ ] A6.22 全参数 path-RLOO 在独立显存窗口完成多步稳定性与 held-out 评价；head-only 4 步和 OOM 记录不视为通过。

---

# 历史任务存档（v5/v6，非当前验收依据）

> 项目：CodonFlow（密码子级离散流 mRNA 编辑器）｜spec 见同目录 `spec.md`（含 Amendment A1/A2/A3/A4）
> 本版替代 v4 冻结版：用户指令恢复全部训练/评测，一个月冲刺预印本。深度自检与故事线重构见同目录 `REFLECTION_20261023.md`。
> 集群数据唯一根：`/teams/HoulabData_1788502323/liucunyu/codonflow`；代码运行副本 `/home/codonflow`（GitHub `Cunyu-Liu/codonflow`，快照 HEAD eef0310）；本地交接文档目录同步维护。
> 新集群：px2-jcy.matpool.com:28365 · RTX 5090 32GB 单卡 · 16 核 · 64GB RAM · Ubuntu 20.04。

---

## 冲刺期任务（W1-W4，2026-10-23 起）

### W1 环境与训练恢复（进行中）

- [x] W1.1 集群资产盘点：代码/语料/权重/评测 120 JSON/基线（GEMORNA、codonGPT）全部在位，md5 对账（train d86366a0 / val f72b482b / test 23d567a1 / 56M converged c8072617 / 355M last 078b27fc）
- [x] W1.2 代码运行副本部署 /home/codonflow（git log 干净、working tree clean）
- [ ] W1.3 conda env codonflow 重建：py3.10 + torch 2.14.1+cu126（5090 sm_120）+ numpy/scipy/pytest/transformers/pymoo + ViennaRNA pip 包 —— 验收：`python -c "import torch; assert torch.cuda.is_available()"` + RNAfold 版本 2.6.4 等价 API
- [ ] W1.4 pytest 41/41 全绿（GPU 侧用例在 5090 上跑通）—— 验收：pytest tests/ 全 pass，无 CPU 静默降级（有 GPU 断言用例）
- [ ] W1.5 watchdog v8 适配 5090（free_mem=32607、355M batch-tokens 放大至占满显存）+ tmux 拉起 355M 续训 —— 验收：nvidia-smi 显存占用 ≥28GB、train.log 出现 e16 步
- [ ] W1.6 恢复 auto_trigger_1020（epoch 落盘自动 journal/git/触发评测）+ 本地监控定时任务（每 3h 巡检）

### W1-W2 评测补全与修复

- [ ] W2.1 v3rloo 评测 9 arm 补全（egfp_s1/s2、nluc_s0、mouse×3、fly×3）——GPU 空隙插跑；验收：26/26 JSON 齐（8 旧 + 9 新 + 基线复用）
- [ ] W2.2 Cas9 motif 罚长度归一化修复 + Cas9 S3 臂重跑 —— 验收：归一化后 motif 轴 4104nt 与 717nt 尺度可比
- [ ] W2.3 per-gene adaptive reference 全量重算 S3（obj_vectors 已存，纯重算）—— 验收：g08/yeast 不再零域；全表数字更新 + amendment 披露
- [ ] W2.4 355M 收敛判定（plateau 3×<0.1% 自动停）→ converged.pt → run_v3_eval.sh p3_v3_355m v3_355m 全量 17/17 —— 验收：容量曲线第三点落定
- [ ] W2.5 355M 短程 RLOO（可选，若 W2.4 提前完成）—— 构成容量-数据-RL 三角第三边

### W3 图表与论文

- [ ] W3.1 主图全部重制（house style：方法色固定/矢量 PDF+PNG/300dpi）：fig1 塌缩直方图、fig2 门控vs过滤、fig3 偏好扫描、fig4 消融、fig5 主表图、fig6 预算曲线、fig7 pipeline、fig8 arch limit、fig10 容量曲线（+355M 点）+ 新增 fig11 RL 增益条件性图
- [ ] W3.2 预印本 v1 重写：三幕结构（问题真实→by-construction 兑现→差距归因与 frontier）；摘要正向断言前置；A4 降级备案生效则如实切换
- [ ] W3.3 叙事-现象对应表逐行复核（6 行每行有图有数）

### W4 收尾

- [ ] W4.1 内部评审 3 轮 + 修订
- [ ] W4.2 中期汇报 PPT 更新（确认后的结果才进 PPT）
- [ ] W4.3 GitHub 最终 commit + 三端备份对账

---

## 冻结前已完成（存档，证据在 /teams 与本地 backup_20261013）

（内容同 v4 版「已完成」清单：Phase 0-3 全部推进到冻结点——基础设施/三代语料/四基线/两条重大修复（mask 塌缩死目标→corruption 目标；ATC 零权重轴退化）/56M@862k 收敛+17/17 评测+HELD18 18/18（S3 geomean +10.8%）/355M 冻结 e16 76%（e13 2.7921 最优）/RLOO v3 35 iters 快 plateau/预印本 v0.2/中期 PPT 36 页/journal 700+ 行）

## 恢复命令（数据根 = /teams 公共目录）

```bash
# 355M 续训（watchdog 自动守护 + 收敛自停，5090 适配版）
tmux new-session -d -s v8wd "bash /teams/HoulabData_1788502323/liucunyu/codonflow/code_repo/scripts/v8_watchdog_5090.sh"
# v3rloo 评测补全（幂等）
bash /teams/HoulabData_1788502323/liucunyu/codonflow/code_repo/scripts/run_v3_eval_rloo.sh p3_rloo_v3_56m_eval v3rloo56m launch
# 355M 收敛后全量评测
bash /teams/HoulabData_1788502323/liucunyu/codonflow/code_repo/scripts/run_v3_eval.sh p3_v3_355m v3_355m launch
# 自动 journal/git/触发器
tmux new-session -d -s auto1020 "bash /teams/HoulabData_1788502323/liucunyu/codonflow/code_repo/scripts/auto_trigger_1020.sh"
```

## 冻结时点关键数字（基线锚，供对照）

| 模型 | 状态 | val loss | 说明 |
|---|---|---|---|
| v2-56M@215k | 收敛 | 2.8141 | RLOO v4 系列基座（+RL 有正增益） |
| v3-56M@862k | 收敛 | 2.8069 | converged.pt + 17/17 + HELD18 18/18（RLOO 增益存疑） |
| v3-355M@862k | 冻结 e16 76% | 2.7921@e13 | 容量第三点预训练侧已成立，待收敛+下游裁决 |
| RLOO v3 | 35 iters plateau | — | 6 arm 混合，剩 9 arm |

## 已知问题（诚实记录，进论文 limitations）

- 绝对 S3 HV 落后 LD/GPT 2-4×（三因素归因中，355M 裁决）——A4 降级备案
- RLOO v3 增益存疑（9 arm 裁决中）——A4 条件性结论备案
- yeast g08 零域（adaptive ref 升级为正式口径）；g02 mouse -47%；Cas9 motif 尺度（W2.2 修复）
- v3 语料 862k vs spec 1M 偏差（容量饱和证据支持不扩容，如实报告）

---

## Tasks 增补 v6（2026-10-25 交接收官版 · 本会话）

> 背景更新：**355M 已于 10-24 21:13 正式收敛**（e21 val 2.7875，plateau 3/3 触发，converged.pt 945MB 在位）；评测架构自动检测补丁已上（run_exp3/run_exp5_ood 从权重推断 d_model/n_layers/n_heads，修复 56M 硬编码）；9 条评测链并行中。

### W1 收官（本会话已完成）

- [x] W1.7 355M 训练至收敛：e16 2.7912（新最优）/ e17 2.8060 / e18 2.7919 / e19 2.7904 / e20 2.7880 / e21 2.7875 → plateau 3/3 → converged.pt（945MB）+ converged.json 落盘
- [x] W1.8 评测脚本架构自动检测补丁（patch_eval_arch.py）：E3 nluc 首次运行 NameError（re 未导入）已修复并复跑成功
- [x] W1.9 9 链并行评测启动：eval355_c0-c4（E5 15 臂 + E3 2 臂）、eval355_e3nluc（E3 nluc 复跑）、rloo_backfill c2（mouse×3）、rloo_fly_s2（补 rloo 最后 1 臂）、held18_355m（HELD18 18 基因）、v3ev_v3_355m_serial（总调度）
- [x] W1.10 patrol_loop.sh 常驻守护上线（30min 周期：进度 journal + git push + 死链告警）

### W2 当前进行中（预计 10-25 至 10-27）

- [ ] W2.4a 355M 全量评测 17+18=35 JSON（mouse 臂 ~9h×3 是长尾，预计 10-26 完成全量）
- [ ] W2.1a v3rloo 补全至 17/17（fly_s2 + mouse×3 在跑）
- [ ] W2.6 RLOO 增益最终裁决：17/17 后跑 fig11 数据（E5_v3_56m vs E5_v3rloo56m S3 HV 全表对照）→ 写入预印本 §5.3 条件性结论
- [ ] W2.7 容量第三点落定：355M converged 2.7875 vs 56M 2.8069（-0.70%），fig10 更新 + 预印本 §6 定稿
- [ ] W2.8 HELD18 355M vs 56M vs v2conv 三代全表（容量下游效应 L2 层的第三点）

### W3 图表与论文（10-27 至 10-31）

- [ ] W3.1 主图重制（house style 已建：fig_batch_v2.py/fig_batch2_v2.py/fig10_v2/fig11 已渲染 7 张，355M 新数据出来后重渲）
- [ ] W3.2 预印本 v1：三幕结构重写 + 355M 容量结果 + RLOO 条件性结论
- [ ] W3.3 PPT 更新（CodonFlow-中期汇报 后续版）

### 数据链交接锚点

| 产物 | 位置 | 状态 |
|---|---|---|
| 355M converged.pt | codonflow/checkpoints/p3_v3_355m/ | e21, val 2.7875, plateau 3/3 |
| 355M 评测 JSON×35 | codonflow/eval_outputs/E5_v3_355m_* + E3_v3_355m_* + HELD18_V3355m_* | 生成中 |
| v3rloo 17 JSON | codonflow/eval_outputs/E5_v3rloo56m_* | 13/17 → 17/17 |
| 容量曲线数据 | figures_src/data/capacity_curves.json + update_capacity.py | 已含 e1-e21 全序列 |
| figures_v2 | figures_src/figures_v2/ + /teams eval_outputs/figures_v2 | 7 张 house style 图在位 |
