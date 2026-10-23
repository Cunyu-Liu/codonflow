# Tasks（工程级 v5 · 2026-10-23 新集群恢复版）

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
