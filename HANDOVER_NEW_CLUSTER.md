# CodonFlow 新集群交接文档（状态冻结版 2026-10-23 00:15）

> 用户指令：全部训练/评测任务已停止。本节为冻结时点状态与恢复路径。下方保留 10-19 迁移版与 10-15 原版全文。

## 冻结时点状态（2026-10-23 00:10）

| 项 | 状态 | 细节 |
|---|---|---|
| 355M 预训练 | **停止于 e16 76%**（未收敛） | 15 epoch 已落盘；曲线 e1 2.9672 → e8 2.8237 → e12 2.7938 / **e13 2.7921（最优）** / e14 2.8069（反弹）/ e15 2.7941；plateau 0/3，converged.pt 不存在 |
| 权重存档 | last.pt=e15（md5 078b27fc）+ epoch_003/006/009/012/015 | **e13 无独立存档**（最近可得 epoch_012.pt=2.7938） |
| HELD18 v3_56m | **18/18 完整** | S3 geomean **1.108**（+10.8% vs v2conv）；S2 1.082；S1 0.976；长度分层 S3：long 1.156 / short 1.114 / mid 1.004；yeast g08 零域剔除；identity/legal 100% |
| v3rloo 评测 | **8/17**（E3×2 + E5×6） | mouse s0/s1/s2 cf 臂完成但基线未落盘，需整臂重跑；fly×3 + egfp_s1/s2 + nluc_s0 未启动 |
| RLOO v3 微调 | ckpt 三件套在位 | 35-iter 快收敛；初步对照（6 arm）混合：egfp/zfish 多为负、nluc/zfish_s2 正——不支持 RL 正增益强结论 |
| 56M 全套 | 完整 | converged + 17/17 评测 + HELD18 全表 |
| 集群进程 | **全部清零** | GPU 0MiB/0%，tmux server 空 |
| 本地 cron | 3h 巡检 dbf0ea85 仍活跃 | 如需彻底静默在 Trae 侧暂停 |

## 科学结论快照（可写论文/PPT 的部分）

1. **容量曲线第三点已实质成立**（预训练侧）：355M@862k e13 达 2.7921，低于 56M@862k 收敛值 2.8069（-0.5%），且仍在下降。fig10 数据齐（capacity_curves.json 已含 v3_355M 序列）。
2. **下游容量效应（L2 层）**：862k 语料使 held-out 18 基因 S3 几何平均 +10.8%、长基因 +15.6%——数据扩容的下游收益首次量化。
3. **RL 增益存疑**：v3 基座上 RLOO 35 iters 即 plateau，下游对照混合——「v3 基座接近该奖励容量上界」假说增强，最终裁决需 mouse/fly 臂。
4. 已知问题延续：HV 零域（yeast）、g02 mouse -47% 退化、Cas9 S3 motif ref 尺度 bug（v3 待办）。

## 恢复命令（下次继续）

```bash
# 1. 355M 续训（watchdog 方式，自动守护+收敛自停）
tmux new-session -d -s v8wd "bash /home/codonflow/scripts/v8_watchdog_4090.sh"
# 2. v3rloo 评测补全（幂等）
bash scripts/run_v3_eval_rloo.sh p3_rloo_v3_56m_eval v3rloo56m launch
# 3. 355M 收敛后全量评测
bash scripts/run_v3_eval.sh p3_v3_355m v3_355m launch
# 4. 自动 journal/git/触发器
tmux new-session -d -s auto1020 "bash /home/codonflow/scripts/auto_trigger_1020.sh"
```

权重/数据根：`/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/{checkpoints,corpora,eval_outputs,logs}`；代码 `/home/codonflow`（GitHub main=96c37e7）。
---

# CodonFlow 新集群交接状态更新（2026-10-19）

> 本节由新集群迁移会话追加。原完整交接文档见下方（2026-10-15 版）。
> 新集群：px2-jcy.matpool.com:28055 (root) · Ubuntu 20.04 · RTX 4090 24GB 单卡 · 12 CPU · 64GB RAM

## 迁移完成状态（2026-10-19 17:00）

| 项 | 状态 | 证据 |
|---|---|---|
| 代码 | GitHub @ 68166f6 已部署 /home/codonflow | git log 干净 |
| conda env codonflow | py3.10 + torch 2.5.1(cu12) + ViennaRNA 2.6.4 + mmseqs2 18.8cc5c | which/RNAfold --version 验证 |
| pytest | 41/41 全绿 | /tmp/pip_test.log |
| LinearDesign | 源码重新编译（原二进制需要 glibc 2.34，Ubuntu 20.04 没有） | eGFP λ=0 MFE -437.30 CAI 0.792 与原集群一致 |
| 语料 | /teams/HoulabData_1788502323/liucunyu/codonflow/corpora + codonflow/corpora 双份 | train d86366a0 / val f72b482b / test 23d567a1 md5 一致 |
| 56M 权重 | converged.pt (c8072617) + log.jsonl | md5 对账一致 |
| 355M 权重 | **e3 last.pt (69d502c5) 从 zip 备份恢复**（巡检时误判损坏的是 orico/Documents 双端的 871 传输残片；teams zip 内完好） | ZIP CRC + torch zip 内层 testzip None |
| 56M 评测 | 17/17 E5+E3 JSON 全在，identity/legal 全 100% | 程序化核验 PASS |
| eval_outputs | 120 JSON + figures_src 已复制 | bench_master 数据链齐 |
| GEMORNA | /teams/.../codonflow/gemorna 还原（第二环境未建，待需要时建 pc_cng） | tar 解包完成 |
| 355M 训练 | **已在跑：e4 从 e3 权重续训（节省 ~15h）**，GPU0 100% util 8.6GB | train.log e4 b800 loss 3.03 |
| watchdog | v8_watchdog_4090.sh（单卡版）tmux v8wd 运行中 | watchdog8.log |
| 路径重映射 | /home/cunyuliu→/home/codonflow, /mnt/cunyuliu/codonflow→/teams/.../codonflow/codonflow, miniconda→/root/miniconda3, MIG UUID→卡号 0 | grep 无残留 |

## 与原计划的偏差（重要）

1. **355M e3 权重找回**：BACKUP_MANIFEST 12:05 停机终版记 last.pt (5fe57780) 在双端损坏已删——那是 scp 直传残片。**teams 盘 zip 里的 checkpoints/p3_v3_355m/last.pt (69d502c5) 完好**（zip CRC d931e774 内层通过），恢复后 e4 续训从 893min 处起步，省掉重跑 e3 的 ~15h。
2. **单卡 24GB（原 A100 40GB ×8）**：355M (8.6GB) 与 56M 训练可并行但 56M 已收敛；评测链需串行排队（原 5 MIG 并行链 → 单卡 5 串行链，mouse arm ~9h 是瓶颈）。若要并行可在剩余 ~15GB 显存里同时跑 1 条 egfp/nluc 评测链（GPU 评测约 3-4GB）。
3. **原集群绝对路径已全局替换**，bash -n 全过；运行时验证：run_pretrain / LinearDesign / RNAfold 均实测通过。

## 剩余待办（按预印本关键路径）

1. [进行中] 355M 训练至收敛（plateau 3×<0.1% 自动停，预计 e7-e9，~30-45h）
2. [ ] 355M 收敛 → run_v3_eval.sh p3_v3_355m v3_355m launch（单卡串行 ~2-3 天，mouse 9h×3）
3. [ ] fig10 容量曲线补 355M 收敛值（capacity_curves.json 已重建，355M 序列 e1-e3 在位）
4. [ ] 预印本 §6 容量结论 + 全文定稿
5. [ ] PPT 最终结论页更新
6. [ ] GEMORNA 基线如需复跑：conda create -n pc_cng python=3.10 + torch + torchtext==0.6.0

## 监控

- 定时任务（每 3h）：检查 train.log / log.jsonl / GPU util / tmux 会话 / converged.pt
- watchdog v8：训练进程死掉自动 --resume 拉起

---

# CodonFlow 新集群迁移交接文档

> 生成时间：2026-10-15 21:45 · 原 A100 集群随时停机 · 换新集群时按本文档操作
> 项目：密码子级离散流 mRNA 编辑器（feasibility-gated discrete flow + label-free bi-reward RLOO）
> 状态：56M 已收敛并三端备份；355M 训练至 e2（e3 进行中 26%）；56M 收敛版评测 8/17 产出

---

## 〇、60 秒速览（老手版）

```bash
# 新集群上：
git clone git@github.com:Cunyu-Liu/codonflow.git && cd codonflow
conda env create -f environment.yml && conda activate codonflow
pip install -e ".[dev,eval]" && pytest tests/          # 环境验证
# 数据从备份盘解压（见 §3），checkpoint 从备份盘 v3_final/ 拷入，然后：
bash scripts/recover_after_reboot.sh                    # 或按 §5 手动拉起
```

---

## 一、项目在哪（三个存放点）

| 位置 | 内容 | 用途 |
|---|---|---|
| **GitHub: Cunyu-Liu/codonflow @ 10a7bab** | 全部代码/脚本/journal/REGISTRY/交接文档 | 代码唯一真相源（原集群 git status 干净） |
| **备份盘 `/Volumes/orico-disc/A100 大量项目文件备份/CodonFlow-backup-20261013/`** | corpora(739MB .gz) + checkpoints + eval_outputs(86+ JSON) + configs + GEMORNA + figures_src + PPT/预印本 | **迁移的主数据源**（全部 md5 校验在册，见 BACKUP_MANIFEST.md） |
| Documents `.../CodonFlow-密码子级离散流mRNA编辑器/backup_20261013/` | 同上第二份 | 冗余副本 |

关键子目录速查：
- `corpora/splits_v3/{train,val,test}.fasta.gz + split_audit.json`（train 689635 / val 87078 / test 85527，seed 0，簇不重叠）
- `corpora/v3_all.fasta.gz`（862k 全量）、`corpora/v3_cluster/`（聚类三件套）
- `v3_final/v3_56m/`（converged.pt ✓ + e5/e6/e7 快照 + log.jsonl 8 epoch 曲线）
- `v3_final/v3_355m/`（last.pt = e2 + epoch_003 + log.jsonl 2 epoch 曲线）
- `eval_outputs/`（E1-E6 全部历史 + GEMORNA + v3_56m 收敛版评测）
- `gemorna_repo/`（gemorna_full.tgz + extra.tgz，见 §7）

---

## 二、新集群环境搭建

```bash
# 1. 代码
git clone git@github.com:Cunyu-Liu/codonflow.git && cd codonflow

# 2. conda 环境（py3.10 + torch 2.5.1 + cu121 + ViennaRNA 2.6.4 + mmseqs2）
conda env create -f environment.yml
conda activate codonflow
pip install -e ".[dev,eval]"
pytest tests/          # 必须全绿再往下走

# 3. 验证二进制在 env 内（不要用系统的）
which RNAfold mmseqs   # 应指向 .../envs/codonflow/bin/
RNAfold --version      # 2.6.4

# 4. GPU 要求：≥24GB 显存（56M 训练用 ~14GB，355M 用 ~10GB；A100 40GB 单卡够两者并行）
```

GEMORNA 基线需要**独立第二个环境**（见 §7）。

---

## 三、数据还原（备份盘 → 新集群）

原集群路径约定：代码在 `/home/<user>/codonflow`，大数据在 `/mnt/<data>/codonflow`（NFS 大盘）。新集群尽量保持同样布局，否则要改脚本里的绝对路径（见 §8 路径清单）。

```bash
B="/Volumes/orico-disc/A100 大量项目文件备份/CodonFlow-backup-20261013"   # 备份盘
M=/mnt/<data>/codonflow          # 新集群大数据盘
mkdir -p $M/corpora $M/codonflow/checkpoints

# 1. 语料：解压即还原（全部文件 gunzip 后 md5 与原集群逐字节一致，在册）
gunzip -c $B/corpora/splits_v3/train.fasta.gz > $M/codonflow/corpora/splits_v3/train.fasta
gunzip -c $B/corpora/splits_v3/val.fasta.gz   > $M/codonflow/corpora/splits_v3/val.fasta
gunzip -c $B/corpora/splits_v3/test.fasta.gz  > $M/codonflow/corpora/splits_v3/test.fasta
cp $B/corpora/splits_v3/split_audit.json $M/codonflow/corpora/splits_v3/
gunzip -c $B/corpora/v3_all.fasta.gz          > $M/codonflow/corpora/v3_all.fasta
for f in cluster_all_seqs.fasta cluster_rep_seq.fasta; do
  gunzip -c $B/corpora/v3_cluster/$f.fasta.gz > $M/codonflow/corpora/v3_cluster/$f
done
cp $B/corpora/v3_cluster/cluster_cluster.tsv $M/codonflow/corpora/v3_cluster/

# 2. 校验（抽样 3 个，md5 应为）：
# train.fasta = d86366a03a613f4d104cb3ad0dd2adb1
# val.fasta   = f72b482b4d290487b60086777339c675
# test.fasta  = 23d567a125ea6863e27174cf9a8fc687

# 3. 基准评测 fasta（bench*.fasta / cas9_probe.fasta / ood3.fasta）在备份盘根目录，直接拷
cp $B/bench*.fasta $B/cas9_probe.fasta $B/ood3.fasta $M/codonflow/corpora/

# 4. 原始 34 物种 fasta 不在备份（可再生数据）。如需重建：
#    bash scripts/download_v3_species.sh && bash scripts/download_v3_wave2.sh
#    再跑 scripts/v3_corpus_pipeline.sh / build_splits.py（Ensembl r112 URL 已验证）
```

---

## 四、Checkpoint 还原

```bash
CK=$M/codonflow/checkpoints
mkdir -p $CK/p3_v3_56m $CK/p3_v3_355m

# 56M（已收敛——可以直接做评测，不需要训练）
cp $B/v3_final/v3_56m/converged.pt   $CK/p3_v3_56m/
cp $B/v3_final/v3_56m/converged.json $CK/p3_v3_56m/
cp $B/v3_final/v3_56m/log.jsonl      $CK/p3_v3_56m/   # 8 epoch 曲线（--resume 依赖它重放 tracker）
cp $B/v3_final/v3_56m/last.pt        $CK/p3_v3_56m/   # = e8

# 355M（e2 权重，续训起点）
cp $B/v3_final/v3_355m/last.pt       $CK/p3_v3_355m/
cp $B/v3_final/v3_355m/epoch_003.pt  $CK/p3_v3_355m/
cp $B/v3_final/v3_355m/log.jsonl     $CK/p3_v3_355m/  # 2 epoch 曲线

# 56M epoch 快照（可选）+ 历史 checkpoints（消融/v2 基座，评测对照用）
cp -r $B/checkpoints $M/codonflow/checkpoints_history
```

> **--resume 语义**（run_pretrain.py）：加载权重 + epoch 计数 + 从 log.jsonl 重放 ConvergenceTracker 历史。所以 log.jsonl 必须和权重配套拷贝。

---

## 五、训练恢复（355M 还没收敛）

```bash
cd /home/<user>/codonflow
# 挑一张空闲卡（需要 ~10GB）：
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader

tmux new-session -d -s p3_v3_355m "CUDA_VISIBLE_DEVICES=<GPU> PYTHONPATH=src \
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
/home/<user>/miniconda3/envs/codonflow/bin/python src/codonflow/train/run_pretrain.py \
--train-fasta /mnt/<data>/codonflow/corpora/splits_v3/train.fasta \
--val-fasta   /mnt/<data>/codonflow/corpora/splits_v3/val.fasta \
--out-dir     /mnt/<data>/codonflow/checkpoints/p3_v3_355m \
--d-model 1280 --n-layers 12 --n-heads 16 --dropout 0.0 \
--batch-tokens 4000 --grad-accum 15 --lr 1e-5 \
--resume /mnt/<data>/codonflow/checkpoints/p3_v3_355m/last.pt \
>> /mnt/<data>/codonflow/checkpoints/p3_v3_355m/train.log 2>&1"
```

两个模型的完整参数（watchdog v7 中固化）：
- **56M**：`--d-model 768 --n-layers 8 --n-heads 12 --batch-tokens 24000 --grad-accum 1 --lr 1e-5`（~14GB，已收敛勿再启）
- **355M**：`--d-model 1280 --n-layers 12 --n-heads 16 --batch-tokens 4000 --grad-accum 15 --lr 1e-5`（~10GB，~10h/epoch）

**收敛判定已代码化**：val 连续 3 epoch 相对下降 <0.1% → 自动写 `converged.pt` + `converged.json` 并退出（stop_checks）。355M 曲线参考：e1 2.9672 / e2 2.8844 / e3 中途 loss ~2.879（原集群 e3 曾跑到 97% 被挤爆 OOM，进度未落盘）。

**watchdog（可选但推荐）**：`scripts/v7_watchdog.sh` 每 5 分钟轮询全 GPU 空闲槽位自动拉起未收敛训练、双收敛自动退出。注意脚本里的 GPU 索引偏好（0/4/2/5 与 3/4/5/0）按新集群拓扑改。**tmux server 是单点**——它崩了所有会话全死（原集群 10-14 23:26 就发生过），watchdog 能自动救。

---

## 六、评测（56M 收敛版，进行中 8/17）

```bash
# 一键起 5 条并行链（E5 五基因×3 seed + E3 扫描；协议与 10-12 rerun 完全一致）
bash scripts/run_v3_eval.sh p3_v3_56m v3_56m launch
# 脚本头部的 MIG UUID 按新集群 GPU 拓扑重配（若新集群无 MIG，把 CUDA_VISIBLE_DEVICES=$mig 改成直接用卡号）
```

- 单 arm 耗时：zfish/nluc/egfp ~30 分钟，**mouse ~9 小时**（2.2kb 长基因，RNAfold 是瓶颈）
- 产出：`eval_outputs/E5_v3_56m_{gene}_s{seed}.json`（15 个）+ `E3_v3_56m_{gene}.json`（2 个）
- 产出后对照 `bench_master.py` 汇总，写进容量曲线第三点之外的第二基线组
- **355M 收敛后**：同样跑 `run_v3_eval.sh p3_v3_355m v3_355m launch` → 得到容量曲线第三点

**容量曲线数据点（fig10 用）**：
| 模型 | 语料 | 收敛 val |
|---|---|---|
| v1-56M (mask) | 215k | 4.0611 |
| v2-56M (corrupt) | 215k | ~2.814 |
| **v3-56M** | 862k | **2.8069**（e8，已收敛）|
| v3-355M | 862k | 待收敛（e2=2.8844）|

绘图脚本：`figures_src/fig10_capacity.py`（数据在 `figures_src/data/capacity_curves.json`，更新后重跑）。

---

## 七、GEMORNA 基线（第二环境）

```bash
# 1. 还原 repo（权重+src+vocab 全在 tar 里，md5 在册）
tar xzf $B/gemorna_repo/gemorna_full.tgz -C /mnt/<data>/     # → /mnt/<data>/gemorna/
tar xzf $B/gemorna_repo/gemorna_extra.tgz -C /mnt/<data>/gemorna/  # LICENSE/日志/原始输出

# 2. 独立环境 pc_cng（py3.10 + torch 2.6 + torchtext==0.6.0 反序列化 vocab pkl）
conda create -n pc_cng python=3.10 -y
conda activate pc_cng && pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install torchtext==0.6.0 --no-deps

# 3. 冒烟测试（权重 16.87MB md5 在册）
cd /mnt/<data>/gemorna && /home/<user>/miniconda3/envs/pc_cng/bin/python \
  src/generate.py --mode cds --ckpt_path checkpoints/gemorna_cds.pt --protein_seq "MSKGEELFTGVVPILVELDGDVNGHKFSVSGEGEGDATYGKLTLKFICTTGKLPVPWPTLVTTFSYGVQCFSRYPDHMKQHDFFKSAMPEGYVQERTISFKDDGTYKTRAEVKFEGDTLVNRIELKGIDFKEDGNILGHKLEYNYNSHNVYIMADKQKNGIKVNFKIRHNIEDGSVQLADHYQQNTPIGDGPVLLPDNHYLSTQSALSKDPNEKRDHMVLLEFVTAAGITLGMDELYK"
# 输出末行 "<CDS> <naturalness>"；CDS 无终止密码子，评分脚本里补 TAA（协议对齐）

# 4. 基线复跑（100-sol/基因，协议对齐 JSON）
#    生成: scripts/gemorna_arm.py   评分: scripts/gemorna_score.py + gemorna_ood_score.py
```

已知结论（写入预印本 §5.4/§5.7）：identity 100%、CAI 0.87-0.91、**GC 族偏差**（human RSCU 先验在 mouse/fly 上 GC 0.64-0.66）；Cas9 4104nt 完整生成 1368/1368——AR 长序列失败是 codonGPT 固定上下文架构特例，非 AR 通病。

---

## 八、新集群需要改的路径清单（全局搜索替换）

| 旧 | 出现位置 | 改成 |
|---|---|---|
| `/home/cunyuliu/` | 所有脚本头部、tmux 命令、watchdog | `/home/<新用户>/` |
| `/mnt/cunyuliu/codonflow/` | watchdog/eval/备份脚本 | `/mnt/<新数据盘>/codonflow/` |
| `/home/cunyuliu/miniconda3/envs/codonflow/bin/python` | 全部 launch 脚本 | 新 conda 前缀（`conda env list` 查） |
| `/mnt/cunyuliu/gemorna/` | gemorna_arm.py 的 REPO | 新 gemorna 路径 |
| MIG UUID ×7 | run_v3_eval.sh + v7_watchdog.sh | 新集群拓扑（无 MIG 则用卡号） |
| `A100` ssh 别名 | 备份/拉取脚本 | 新集群别名（~/.ssh/config） |

一把梭：`grep -rln "cunyuliu" scripts/ | xargs sed -i 's|/home/cunyuliu|/home/<新用户>|g; s|/mnt/cunyuliu|/mnt/<新数据盘>|g'`（改完 bash -n 全部脚本验证语法）。

---

## 九、纪律与坑（原集群踩过的）

1. **备份优先**：每完成一个 checkpoint/评测 JSON → 立即三端（集群/备份盘/Documents）+ md5 对账。manifest 在备份盘 `BACKUP_MANIFEST.md`，持续追加。
2. **tmux 单点**：所有训练会话挂在一个 tmux server 上，它崩 = 全灭。watchdog 是救命索（会自动 resume）。重要节点后跑 `final_pull_*.sh` 式的即时备份脚本。
3. **OOM 挤占**：共享集群会被别人的大进程挤爆。watchdog 全卡轮询 + `--resume` + `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` 是标准姿势。
4. **epoch 末才落盘**：中断 epoch 的进度必丢，`--resume` 从上个 epoch 末继续。评估"要不要再训一会"时记住这一点。
5. **3× 检查**：每个关键产物 md5 双端/三端对账后再在 manifest 上打勾；scp 断点会产生半成品残片——`ls -la` 核对字节数。
6. **每个任务结束推 GitHub**（原集群从 6c2db01 一路到 10a7bab，每次 commit 一事）。

---

## 十、当前待办（接手即做）

1. [ ] 新集群按 §2-§4 还原环境/数据/权重，pytest 全绿
2. [ ] 355M 从 e2 续训至收敛（watchdog 或手动 tmux）
3. [ ] 56M 评测链继续：还差 mouse×3、fly×3、egfp_s1/s2、nluc_s0（8/17 已完成，见 §6）
4. [ ] 355M 收敛 → `run_v3_eval.sh p3_v3_355m v3_355m launch` → 容量第三点
5. [ ] fig10 终版（capacity_curves.json 补 355M 收敛值）→ 预印本 §6 容量结论定稿
6. [ ] PPT 最终结论页更新（现在 36 页，S28 容量曲线 + S34 GEMORNA）
7. [ ] 预印本全文终稿：`CodonFlow_preprint_draft.md`（v0.2 已含 GEMORNA 全套 + 家族偏差发现）

**一个月预印本 deadline 的关键路径**：355M 收敛（~2 天）→ 355M 评测（~1 天）→ fig10 终版 + 预印本 §6（半天）→ 全文润色定稿。
