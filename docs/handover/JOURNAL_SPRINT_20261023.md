# CodonFlow 冲刺期运行日志（新集群 px2-jcy · 2026-10-23 起）

> 纪律：每次训练/评测 run 记录在此 + REGISTRY.md；结论必须写证据位置；诚实记录负结果。
> 延续原 journal.md（700+ 行）的格式与口径。

---

## 2026-10-23（恢复日）

### 环境重建（W1.3，进行中）

- 13:00 SSH 接入新集群：RTX 5090 32GB（32607MiB）×1、16 核 Xeon Gold 6530、64GB RAM、Ubuntu 20.04.6。GPU 空闲（2MiB/0%）。
- 资产盘点（W1.1 ✓）：/teams/HoulabData_1788502323/liucunyu/codonflow 全部在位——code_repo（git HEAD eef0310，tree clean）、corpora（md5 对账：train d86366a0 / val f72b482b / test 23d567a1，与 HANDOVER 记录一致）、checkpoints（56M converged c8072617；355M last.pt=078b27fc(e15) + epoch_003/006/009/012/015 + log.jsonl 15 epochs）、eval_outputs 120+ JSON（含 HELD18 18/18、v3rloo 8/17）、gemorna、codonGPT_hf。
- 代码运行副本：cp code_repo → /home/codonflow（6.9M，git 验证干净）。
- conda 修复：默认 channels 指向已失效的阿里云镜像（HTTP 404）→ 重写 .condarc 为 conda-forge+bioconda → `conda create -n codonflow python=3.10` 成功。
- pip 安装（后台 nohup，日志 /tmp/env3.log）：torch 2.14.1+cu126（5090 sm_120 必须用 cu126 轮子；torch 869MB + cudnn 707MB + triton 247MB 等依赖 ~2.5GB，集群网速波动 3-20MB/s，预计 ~40min）→ numpy/scipy/pytest/transformers/pymoo/tqdm → ViennaRNA（pip 包，Python `import RNA` API 与 2.6.4 行为对齐，版本断言需在 pytest 中验证）。
- **教训**：新集群不带旧环境是常态；conda 镜像 404 优先查 .condarc；nohup + 日志文件方式防 SSH 断连（今天 SSH 3 次被服务器断开）。

### 深度反思与文档更新（W1 伴生工作 ✓）

- 完成 REFLECTION_20261023.md：P0-1 绝对 HV 落后 2-4×（容量归因，355M 裁决）；P0-2 RLOO 增益存疑（9 arm 裁决 + 条件性结论备案）；P0-3 评测器参考域（Cas9 motif 归一化 + adaptive ref 正式化）；P1-4 语料 862k 不扩容决策；P1-5 图表全重制计划；三幕故事线重构。
- 交接文档三件套更新：spec.md + Amendment A4（评测口径升级/降级备案/RLOO 条件性结论/环境变更）；tasks.md v5（W1-W4 冲刺任务 + 验收标准）；checklist.md + J 系列（冲刺期核验项）。

### 图表重制（W3.1 预演，首个样张 ✓）

- fig10 容量曲线 house-style 版完成（fig10_capacity_v2.py → figures_v2/fig10_capacity.pdf+png，3696×1289@300dpi，程序化校验 PASS）。
- 数据：capacity_curves.json（v1_mask 4.06 塌缩死目标 / v2_corrupt 2.8035@e15 / v3_56M 2.8052@e5 / v3_355M e1-e3 旧序列）。355M 收敛后补第三点终值。
- 配色系统固化：CodonFlow=蓝 #0F4D92、LinearDesign=红 #B64342、codonGPT=teal、CAI-greedy=violet、uniform=neutral、GEMORNA=绿。后续所有图沿用。

### 待办（按优先级）

1. pip 完成后：CUDA 验证（`torch.cuda.is_available()` + 5090 实测 matmul）→ pytest 41/41 → 无 CPU 静默降级断言
2. watchdog v8 适配 5090（free_mem 32607 + batch-tokens 放大占满 32GB）→ tmux 拉起 355M 续训（从 e15 last.pt）
3. GPU 空隙插跑 v3rloo 评测 9 arm
4. Cas9 motif 归一化修复 + adaptive reference 全量重算
5. 355M 收敛 → run_v3_eval.sh 全量 → fig10 终版
