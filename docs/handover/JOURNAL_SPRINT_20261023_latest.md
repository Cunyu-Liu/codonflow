# CodonFlow 冲刺期运行日志（双集群 · 2026-10-23 起）

> 纪律：每次训练/评测 run 记录在此 + REGISTRY.md；结论必须写证据位置；诚实记录负结果。
> 集群A = 5090 32GB（ssh -p 28365，训练主力）；集群B = 4090 24GB（ssh -p 28055，评测机）。
> 本文件在本地维护，同步副本在集群A /home/codonflow/docs/handover/。

---

## 2026-10-24 18:10（例行巡检 · 双集群零干预 · e21 训练中 · e20 val 新最优 · v3rloo 10/17）

### 集群A（5090，训练主力）

- GPU：26570/32607 MiB，util 96%，71C，574W/575W——唯一 GPU 进程 PID 32909（train 26560 MiB）——满足 ≥26GB 要求；rloo_c0 三臂完成后会话自然退出（预期，与 15:20 记录一致）。
- 训练：**e21 b4600/18943，loss 2.7843（1299.0m）**；**e20 val 2.7880 —— 又创新低**（vs e19 2.7904 相对下降 0.086%，plateau 2/3——注意按"相对下降<0.1%"判据，e20 改善 0.086% <0.1% 仍计 1 步 plateau，日志打印 plateau 2/3）。完整最优序列：e13 2.7921 → e16 2.7912 → e19 2.7904 → **e20 2.7880**；355M vs 56M 收敛差距扩大到 **−0.017 nats/codon** 且仍未停（e21 进行中）。
- converged.pt：**不存在**——不满足全量评测触发条件，不启动。
- 会话健康：p3_v3_355m / v8wd 均在（watchdog 无需重启）。
- 异常扫描：train.log 尾部 300 行 OOM/NaN/Traceback/Killed = 0。

### 集群B（4090，评测机）

- GPU：3166/24564 MiB、util 0%、nvidia-smi 进程表空——与 15:20 同象；**ps 判活实际进程全在**：fly_s1 主进程 3149402（etime 7h16m、累计 CPU 7:16:31）+ 8 worker、mouse_s0 主进程 2985064（etime 5h11m、累计 CPU 5:11:40）+ 8 worker，均为 run_exp5_ood.py——判活以进程为准。
- 120s CPU 增量判活：mouse 2985064 与 fly 3149402 主进程 120s 各 +2:12——**满核活跃，非卡死**（cf 阶段单进程满核为该评测已知形态；worker CPU 静止属 baselines 前段 cf 计算的正常态）。
- 会话：rloo_c1 / rloo_c2 tmux 会话均在（pane 静默属日志重定向，正常）。
- rloo_c1：fly_s1 cf done 18083s（10:41 日志 mtime）→ 处 baselines 阶段已 ~7.4h（**显著超 fly_s0 baselines 对照 4.3h，进入观察窗口**；链未到重启判据——主进程满核、无 EXIT、无 JSON、无异常）。
- rloo_c2：mouse_s0 cf done 47482s（12:30 日志 mtime）→ baselines 阶段已 ~5.7h；队列剩 mouse_s1 → mouse_s2 → fly_s2。
- 落盘计数：**10/17**（egfp_s0/s1/s2、nluc_s0/s1/s2、zfish_s0/s1/s2、fly_s0）；in-flight：fly_s1(c1)、mouse_s0(c2)——与 15:20 一致无新落盘（两臂均处 baselines 长段，无卡死证据）。
- 异常扫描（勘误：e5o 日志实际位于 `logs/` 而非 `eval_outputs/`，本轮已按正确路径全量复扫）：全部 14 个 e5o_*_v3rloo56m.log grep OOM/CUDA out of memory/NaN/Traceback/Killed = **0**；无进程死亡、无 EXIT 文件（链未收官）。

### 连接事件（如实记录）

- 本轮双集群 SSH 全部一次连通，无重置事件；3 次重试协议未启用。

### 动作记录

- **零干预**：watchdog 活、e21 推进、c1/c2 双链主进程满核活跃、无 OOM/NaN/进程死亡；converged.pt 未产出，355M 全量评测不触发。
- 下次巡检关注：(1) **e21 val（预计 ~19:20 落盘）**——若相对 e20 2.7880 下降 <0.1% 则 plateau 3/3 → 自动写 converged.pt 并退出，届时立即按串行口径启动 355M 全量评测（依次 c3 → c0 → c1 → c2 → c4）；(2) fly_s1 baselines 是否落盘（已超 fly_s0 对照 4.3h，若超 ~10h 仍无 JSON/EXIT 且日志 mtime 停滞，再查卡死判据）；(3) mouse_s0 落盘与 c2 链进入 mouse_s1。

---

## 2026-10-24 15:20（例行巡检 · 双集群零干预 · e20 训练中 · v3rloo 10/17）

### 集群A（5090，训练主力）

- GPU：26570/32607 MiB，util 100%，PID 32909（train 26560 MiB）——满足 ≥26GB 要求；rloo_c0 链三臂完成后 tmux 会话已自然退出（预期），显存全让给 355M 训练。
- 训练：**e20 b10100/18943，loss 2.7850（累计 1119.5m）**；val 序列 e19 2.7904（最优）→ plateau 1/3；converged.pt **未产出**——不满足全量评测触发条件，不启动。
- 会话健康：p3_v3_355m / v8wd 均在（v8wd 无需重启）。
- 异常扫描：train.log 尾部 300 行 OOM/NaN/Traceback/Killed = 0。

### 集群B（4090，评测机）

- GPU：1791 MiB、util 0% 且 nvidia-smi 进程列表为空——⚠️ 本轮首次观察到该现象；但 **ps 判活实际进程全在**（fly_s1 主进程 3149402、mouse_s0 主进程 2985064 各带 8 worker，均为 run_exp5_ood.py）——判活以进程为准，非 GPU 掉卡（后续巡检注意 nvidia-smi 容器显示的可靠性）。
- 会话：rloo_c1 / rloo_c2 tmux 会话均在。
- rloo_c1：fly_s1 cf done 18083s（10:41，日志 mtime）→ baselines 阶段 4.6h；主进程 120s 增量 +2:00/2:00 满核——非卡死。
- rloo_c2：mouse_s0 cf done 47482s（12:30 日志 mtime）→ baselines 阶段 2.8h；主进程 120s 增量 +2:00/2:00 满核——非卡死（对照 fly_s0 baselines 4.3h 完整序列）。
- 落盘计数：**10/17**（egfp_s0/s1/s2、nluc_s0/s1/s2、zfish_s0/s1/s2、fly_s0）；in-flight：fly_s1(c1)、mouse_s0(c2)；c1/c2 链自动接续 fly_s2 / mouse_s1、mouse_s2。
- 异常扫描：全部 14 个 e5o_*_v3rloo56m.log OOM/NaN/Traceback/Killed = 0；无进程死亡、无 EXIT 文件（链未收官）。

### 连接事件（如实记录）

- 集群A 连接重置 1 次（15:08 val 查询），等 2 分钟重试成功（重试 1/3 内）；集群B 连接重置 1 次（15:06 pane 查询），同协议重试成功。

### 动作记录

- **零干预**：watchdog 活、e20 推进、c1/c2 双链 baselines 满核活跃、无 OOM/NaN/进程死亡；converged.pt 未产出，355M 全量评测不触发。
- 下次巡检关注：(1) e20 val（预计 ~16:15 落盘）——若相对 e19 下降 <0.1% 则 plateau 2/3；(2) fly_s1 / mouse_s0 baselines 落盘（c1/c2 链各自进入下一臂）；(3) 若产出 converged.pt，立即按串行口径启动 355M 全量评测（依次 c3 → c0 → c1 → c2 → c4）。

---

## 2026-10-24 13:30（e19 新最优 · 训练继续 + v3rloo 10/17）

### 355M 训练（关键科学数据点持续更新）

- **e19 val 2.7904 — 又创新低**（vs e16 2.7912 相对下降 0.028%，plateau 计数重置）。
- 完整最优序列：e13 2.7921（旧集群）→ e16 2.7912 → **e19 2.7904**；355M vs 56M 收敛值差距扩大到 **−0.0148 nats/codon** 且未停。
- e20 训练中（b700/18943）。「训练到真收敛」纪律正在兑现：若按 e16 停就会丢掉 e19 的真实改进；watchdog plateau 3×<0.1% 自动停继续生效。
- **科学含义增强**：355M 的容量优势在 862k 语料上持续兑现（容量第三点结论从「成立」升级到「扩大中」）——预印本 §6 的核心数字将按 converged 终值写死。

### v3rloo 评测（10/17 新 arm；fly_s0 完成）

- 新完成：egfp_s1/s2、nluc_s0、**fly_s0**（集群A 11409s，EXIT 记录在案）；
- 进行中：集群B fly_s1（18083s 计时中）+ mouse_s0（47482s≈13.2h 长尾，2.2kb MFE 计算瓶颈）；
- 待排队：mouse_s1/s2、fly_s2（集群B c1/c2 链自动接续）。
- 集群A rloo_c0 链完成全部三臂（egfp_s1/nluc_s0/fly_s0）——tmux 会话将自然退出，GPU 显存全部让给 355M 训练。

---

## 2026-10-24 05:30（e17 反弹 · plateau 1/3 + RLOO 9 arm 半程）

### 集群A（5090，训练主力）

- GPU：27685/32607 MiB，util 100%（train 26560 MiB + rloo_c0 1110 MiB）——满足 ≥26GB 要求。
- 训练：**e19 b15400/18943（81%），loss 2.7836（累计 937.8m）**；train.log 实测 val 序列：e16 2.7912（最优，condgap 1.416）→ e17 2.8060（plateau 1/3）→ **e18 2.7919、condgap 1.127、日志打印 plateau 0/3**——⚠️ 更正 09:20 巡检记录：e18 后日志实际打印 **plateau 0/3**（计数器对比上一 epoch val：e18 2.7919 < e17 2.8060 改善 0.5% → 计数清零），此前"plateau 2/3"系误读；但 e16 2.7912 仍为全局最优，e18 相对 e16 +0.025%。e19 val 预计 ~13:05 落盘（epoch 剩 ~56m），若 e19 相对 e18 下降 <0.1% 才计 1/3——收敛比此前预期更远，355M 全量评测触发条件继续待定。
- converged.pt：**不存在**——不满足触发条件，全量评测不启动。
- 会话健康：p3_v3_355m / rloo_c0 / v8wd 三会话全活；watchdog PID 32891 与训练主进程 PID 32909（run_pretrain.py，累计 CPU 与墙钟差连续吻合）均在运行，无重启发生。
- rloo_c0 链：egfp_s1 ✓（02:06）、nluc_s0 ✓（04:37）、**fly_s0 cf done 11409s（07:48）→ baselines 阶段运行 4.3h**：主进程 195773 R 态满核（CPU 持续累积）、8 worker 在册；JSON 未落盘、EXIT 未写——继续观察不重启。
- 异常扫描：train.log 尾部 200 行 grep OOM/NaN/Traceback/Killed = 0；全部 e5o_*_v3rloo56m.log = 0。

### 集群B（4090，评测机）

- GPU：4878/24564 MiB（3 个 eval 相关进程在册），util 0%——MFE/RNAfold CPU-bound 已知稳态，判活以进程为准；占用非 0 且会话在 → 不触发重启条件。
- 会话：rloo_c1 / rloo_c2 tmux 会话均在（pane 静默属脚本日志重定向，正常）。
- rloo_c1：egfp_s2 ✓（05:40 落盘 974932B，EXIT=0 完整序列）→ **fly_s1 cf done 18083s（10:41）→ baselines 阶段 1.5h**（对照 egfp_s2 同段 2.8h，正常）；主进程 3149402 满核活跃（120s 增量判活：CPU +2:00/2:00）。
- rloo_c2：**mouse_s0 cf 阶段 12.9h**（23:18 起跑，超 ~9h 预估但未超长臂上限）；5 worker 满核（120s 增量判活：各 +~2:00/2:00，日志 11:27 仍在更新）——非卡死；队列剩 mouse_s1 → mouse_s2 → fly_s2。
- 落盘计数：**9/17**（8 旧 + egfp_s2 新落盘；egfp_s1/nluc_s0 计入 06:05 起的 9 中）——in-flight：fly_s0(A)/fly_s1(B)/mouse_s0(B)。
- 异常扫描：全部 e5o 日志 OOM/NaN/Traceback/Killed = 0；无进程死亡。

### 连接事件（如实记录）

- 本轮双集群 SSH 全部一次连通，未遇连接重置；3 次重试协议未启用。

### 动作记录

- **零干预**：watchdog 活、训练 e19 推进、c0/c1/c2 三链全部满核活跃、无 OOM/NaN/进程死亡；converged.pt 未产出，355M 全量评测不触发。
- 下次巡检关注：(1) **e19 val（~13:05 后）——plateau 真实计数以 train.log 打印为准**，若产出 converged.pt 立即按串行口径启动 355M 全量评测（依次 c3 → c0 → c1 → c2 → c4，勿用 launch 并行模式）；(2) fly_s0 baselines 收官落盘（A 收官 c0 链）；(3) fly_s1 baselines 落盘（c1 链收官）；(4) mouse_s0 落盘（c2 链进入 mouse_s1）——若届时 mouse_s0 显著超 15h 仍无 JSON 落盘，检查日志 mtime 停滞与 worker CPU 零增量后再议重启。

---

## 2026-10-24 09:20（例行巡检 · 双集群零干预 · e19 训练中 · plateau 2/3）

### 集群A（5090，训练主力）

- GPU：27685/32607 MiB，util 100%（train 26560 + rloo_c0 1110 MiB）——满足 ≥26GB 要求。
- 训练：**e19 b2200/18943，loss 2.7918（773.2m）**。val 链：e15 2.7941 → e16 2.7912（最优，cond_gap 1.42）→ e17 2.8060（反弹，plateau 1/3）→ **e18 2.7919、cond_gap 1.127（相对 e16 无改善 +0.025%，plateau 2/3）**；e19 预计 ~13:30 落 val，若相对 e16 仍无 <0.1% 下降 → 计 3/3，自动写 converged.pt（e16 权重）并退出。
- converged.pt：**不存在**——355M 全量评测不满足触发条件，不启动。
- 会话健康：p3_v3_355m / rloo_c0 / v8wd 三会话全活；watchdog（PID 32891）与训练主进程（PID 32909，GPU 26560 MiB）均在运行。
- rloo_c0 链：egfp_s1 ✓、nluc_s0 ✓（04:37）后 **fly_s0 cf done 11409s（07:48）→ 现处 baselines 阶段**：主进程 195773 R 态 ~80% CPU 持续消耗（10 分钟内 74→85min）、23 线程；8×MFE worker TIME 静止属 cf 阶段结束后正常态（对照 nluc_s0 同构日志序列：cf done → baselines done → wrote → EXIT=0，其 baselines 段约 1h）。fly_s0 JSON 未落盘、EXIT 未写——继续观察不重启。
- 异常扫描：train.log 近 200 行 + 全部 e5o_*_v3rloo56m.log grep OOM/NaN/Traceback/Killed 均空——零异常。

### 集群B（4090，评测机）

- GPU：1531/24564 MiB，util 0%——MFE/RNAfold CPU-bound 已知稳态，判活以进程为准（nvidia-smi 进程表空但 eval 主进程在册）。
- 会话：rloo_c1 / rloo_c2 tmux 会话均在。
- rloo_c1：fly_s1（05:40 起）cf 阶段推进至 S3_quad dir3，日志 09:08 仍在更新；9×worker CPU 132→137min（10 分钟增量活跃）。
- rloo_c2：mouse_s0（23:18 起）S3_quad dir3 MFE 长尾（2.2kb 臂），日志 08:41 更新、worker CPU 432→438min 活跃；队列剩 mouse_s1 → mouse_s2 → fly_s2。
- 落盘计数：**9/17**（与 06:05 一致——fly_s0/mouse_s0/fly_s1 三 arm 均进行中，无卡死证据）。
- 无 OOM/NaN/进程死亡。

### 连接事件（如实记录）

- 集群A 中段一轮连续 3 次 SSH 失败（kex/连接重置模式，与已知偶发模式一致），等 2 分钟后重试成功取得终态快照；集群B 全连通。3 次重试上限协议生效。

### 动作记录

- **零干预**：watchdog 活、训练 e19 推进、c0/c1/c2 三链全部活跃、无活跃 OOM/NaN/进程死亡；converged.pt 未产出，355M 全量评测不触发。
- 下次巡检关注：(1) **e19 val 落盘——若 plateau 3/3 触发 converged.pt，立即按串行口径启动 355M 全量评测（依次 c3 → c0 → c1 → c2 → c4，勿用 launch 并行模式）**；(2) fly_s0 baselines 完成与 c0 链收官落盘；(3) fly_s1 cf 收尾；(4) mouse_s0 落盘与 c2 链进入 mouse_s1。

---

## 2026-10-24 06:05（例行巡检 · 双集群零干预 · e18 训练中）

### 集群A（5090，训练主力）

- GPU：27559/32607 MiB，util 100%（train 26560 + rloo_c0 984 MiB）——满足 ≥26GB 要求。
- 训练：**e18 b6600/18943，loss 2.7866（579.6m）**，低于 e17 train 2.7886，继续有效学习（e18 已 ~83m，约 35%）。
- val 趋势：e15 2.7941 → e16 2.7912（最优）→ e17 2.8060（反弹，plateau **1/3**）；e18 val 待落盘（按 ~248m/epoch 预计 ~09:00 epoch 结束）。
- converged.pt：**不存在**——355M 全量评测不满足触发条件，不启动。
- 会话健康：p3_v3_355m / rloo_c0 / v8wd 三个 tmux 会话全存活；watchdog（v8_watchdog_5090.sh，PID 32891）与训练主进程（run_pretrain.py，PID 32909，累计 CPU 9h45m ≈ 墙钟 9h43m）均在运行。
- rloo_c0 链：fly_s0 进行中（04:37 起 ~1.5h，日志 06:01 仍在更新，S1+S2×5 共 6 场景线已全打印=末段 MFE 收尾，worker CPU 1h23-26m 累计推进）；nluc_s0 已于 04:37 落盘（728097B）。c0 链 3 arm（egfp_s1/nluc_s0/fly_s0）仅剩 fly_s0。
- 历史异常复核：train.log 内 Traceback ×2 与 CUDACachingAllocator OOM 告警（20MB 映射失败）全部来自 10-23 20:21 首次启动失败（read_fasta 路径错 + 显存映射），20:22:33 重启后稳定 ~10h 推进至 e18——**非活跃异常，不处理**。

### 集群B（4090，评测机）

- GPU：20470/24564 MiB（eval 主进程 18934 MiB + 2×758 MiB），util 0-1%——MFE/RNAfold CPU-bound 阶段低占用属已知稳态，判活以进程为准。
- 会话：rloo_c1 / rloo_c2 tmux 会话均在（pane 静默，以进程表为准）。
- rloo_c1：fly_s1 05:40 起跑（前一 arm egfp_s2 已于 05:40 落盘 974932B），日志显示进行至 S2 dir1（3/6 场景线）。
- rloo_c2：mouse_s0 23:18 起跑，05:02 打印末场景线 S2 dir4（2.2kb 长臂 MFE 重，~9h 预估 08:00 前后落盘）；队列剩 mouse_s1 → mouse_s2 → fly_s2。
- 落盘计数：**9/17**（6 旧 JSON + 新 egfp_s1/egfp_s2/nluc_s0）。
- 无 OOM/NaN/进程死亡；dmesg 未复查（判据已足）。

### 连接事件

- 本轮双集群共 11 次 SSH 全部连通，**无重置事件**。

### 动作记录

- **零干预**：watchdog 活、训练推进、双评测链存活、无活跃 OOM/NaN/进程死亡；converged.pt 未产出，355M 全量评测不触发。
- 下次巡检关注：(1) e18 val 落盘与 plateau 2/3 判定（若 e18 相对 e16 降幅 <0.1% → 计 2/3）；(2) fly_s0 落盘（集群A c0 链收官）；(3) fly_s1 / mouse_s0 落盘；(4) c2 链进入 mouse_s1。

---

## 2026-10-24 05:30（e17 反弹 · plateau 1/3 + RLOO 9 arm 半程）

### 355M 训练状态

- **e17 val 2.8060（反弹）**：e16 的 2.7912 保持最优 → **plateau 计数 1/3**。e18 训练中（496min/e16 计）。若 e18/e19 相对 e16 无 <0.1% 下降 → 自动写 converged.pt（以 e16 权重为收敛点）。
- cond_gap e17 回到 1.93（e16 的 1.42 是当前最优条件信息量）。

### v3rloo 评测（9/17 新 arm 完成，入档前三遍检查通过）

- 新完成：egfp_s1 ✓、egfp_s2 ✓（集群B，12776s）、nluc_s0 ✓（集群A，+1.8%）
- **identity/legal 逐臂核验 = 1.0 全绿**（S1/S2/S3 三场景 × 2 文件全查）
- S3R2 重算（41 arm）+ fig11 更新至 8 对：**3/8 正、均值 −2.9%**——RLOO 无增益结论方向持续，且随 arm 增多均值从 −5.3% 收敛到 −2.9%（方差比想象小，结论稳）
- 进行中：集群A fly_s0（S2）；集群B mouse_s0（S2 dir3，2.2kb 长臂）
- 待跑：fly_s1/s2、mouse_s1/s2（集群B 队列）

### 一处格式细节（诚实记录）

- fig11 更新时首次跑在 /tmp 用了旧 S3R2（6 对），复跑用 eval_outputs 最新版（41 arm）得 8 对——流程已修正为「先重算 S3R2 → 再渲染」，render_figures_v2.sh 内置此顺序。

---

## 2026-10-24 01:50（v1 重写计划落档 + 训练中期快照）

### 集群A（5090，训练主力）

- GPU：27561/32607 MiB（train 26560 + rloo_c0 986 MiB），util 100%——满足 ≥26GB 要求。
- 训练：**e17 b12100/18943，loss 2.7884（399.7m）**，batch 级噪声内波动，仍低于 e16 train 2.7925，继续有效学习。
- converged.pt：**不存在**——log.jsonl 末条 e16 val 2.7912（新最优，cond_gap 1.42）；plateau 三点判定（e15 2.7941→e16 2.7912 降幅 0.1% 边缘）待 e17 val 落盘观察——不启动 355M 全量评测。
- 会话健康：p3_v3_355m / rloo_c0 / v8wd 三个 tmux 会话全存活；watchdog（v8_watchdog_5090.sh）与训练主进程（run_pretrain.py --d-model 1280，PID 32909）均在运行。
- rloo_c0 链：nluc_s0 运行中（02:06 起 ~1h，9×worker CPU 累计 55m/each 持续推进，986MiB GPU 占用在册）→ fly_s0 排队。train.log tail 50 无 OOM/NaN/Traceback/Killed，dmesg 无 GPU 异常。

### 集群B（4090，评测机）

- GPU：2946/24564 MiB，util 11%——判活依据进程而非 GPU：rloo_c1 主进程 2985063（R+，CPU 16:49+）与 rloo_c2 主进程 2985064（CPU 2:56+）均存活，MFE/RNAfold CPU-bound 阶段 GPU 低占用属已知稳态——**不重启**（重启将丢弃进行中 arm 的 MFE 进度）。
- 会话：rloo_c1 / rloo_c2 tmux 会话均在（pane 静默，以进程表为准）。
- arm 进度：egfp_s2（c1）9×worker 推进中（~4h）；mouse_s0（c2）长尾推进（worker CPU 151m）。
- 落盘计数：**7/17**（6 旧 JSON：egfp_s0、nluc_s1/s2、zfish_s0/1/2 + 新 egfp_s1 02:06 落盘 974927B）——与 02:38 巡检一致，无新落盘（nluc_s0/egfp_s2/mouse_s0 三 arm 进行中）；mouse_s1/s2 旧臂 JSON 缺口仍由 c2 链回填兜底。
- dmesg 无异常。

### 连接事件

- 本轮双集群 SSH 各一次连通，无重置事件。

### 动作记录

- **零干预**：watchdog 活、训练推进、双评测链存活、无活跃 OOM/NaN/进程死亡；converged.pt 未产出，355M 全量评测不满足触发条件。
- 下次巡检关注：(1) e17 val 落盘（plateau 三点判定 e15/e16/e17）；(2) nluc_s0 EXIT（集群A c0 链）；(3) egfp_s2 / mouse_s0 完成与落盘；(4) mouse_s1/s2 旧臂 JSON 缺失核对。

## 2026-10-24 02:38（例行巡检 · 双集群零干预）

### 集群A（5090，训练主力）

- GPU：27561/32607 MiB（train 26560 + rloo_c0 986 MiB），util 100%——满足 ≥26GB 要求。
- 训练：**e17 b9200/18943，loss 2.7879（363.5m）**，低于 e16 train 2.7925，持续有效下降；log.jsonl 确认 e16 val 2.7912（新最优）落档，watchdog 自动推进 e17。
- converged.pt：**不存在**（plateau 未触发：e15→e16 val 相对下降约 0.1% 处阈值边缘，待 e17-e19 观察）——不启动 355M 全量评测。
- 会话健康：p3_v3_355m / rloo_c0 / v8wd 三个 tmux 会话全部存活，watchdog 进程（v8_watchdog_5090.sh）与训练主进程（run_pretrain.py --d-model 1280）均在运行。
- rloo_c0 链：egfp_s1 ✓ EXIT=0（02:06）→ **nluc_s0 运行中**（02:33 过半，S1/S2 五向已完成）→ fly_s0 排队。日志无新增 OOM/NaN/Traceback（本轮 grep 到的 CUDACachingAllocator OOM 与 Traceback 均为 10-23 20:21 历史事件留档，无活跃失败）。

### 集群B（4090，评测机）

- GPU：1515/24564 MiB，util 0%——**判活依据进程而非 GPU**：rloo_c1 主进程 2985063 + rloo_c2 主进程 2985064 均存活（R+ 状态，累计 CPU 5:41/2:50 且 8×MFE worker 持续推进，与 01:50 快照一致——MFE/RNAfold 为 CPU-bound 阶段，GPU 空转属已知稳态，非链死亡）。**不重启**（重启将丢弃 mouse_s0 已跑 3h+ 的 MFE 进度）。
- 会话：rloo_c1 / rloo_c2 tmux 会话均在（capture-pane 输出为空系链 pane 静默，非退出——以进程表为准）。
- arm 进度：egfp_s2 处 S3_quad dir6（13/14 行进度）；mouse_s0 处 S2 dir2（长尾符合 ~9h 预期）。
- 落盘计数：**7/17**（egfp_s0、nluc_s1/s2、zfish_s0/1/2 共 7 旧 + egfp_s1 新完成；**疑点：mouse_s1/s2 旧臂日志仅见 "cf done 120841s" 无 JSON 落盘——与"8 旧"口径存在出入，待 17/17 终验核对**）。
- B_ERRORS：全部日志 grep OOM/NaN/Traceback/Killed 为空——零异常。

### 连接事件（如实记录）

- 本轮 B 集群 SSH 两次失败：attempt1 `kex_exchange_identification: Connection reset`、attempt2 `Permission denied (publickey,password)`，attempt3 成功——与"偶发连接重置"已知模式一致，3 次重试机制生效。

### 动作记录

- **零干预**：watchdog 活、训练推进中、评测链双端存活、无活跃 OOM/NaN/进程死亡。355M 全量评测不满足触发条件（converged.pt 未产出）。
- 下次巡检关注：(1) e17 落盘 val（plateau 三点判定 e15/e16/e17）；(2) B 集群 mouse_s1/s2 旧臂 JSON 缺失核对；(3) nluc_s0 / egfp_s2 / mouse_s0 三个进行中 arm 的 EXIT 状态。

## 2026-10-24 01:50（v1 重写计划落档 + 训练中期快照）

### PREPRINT_V1_PLAN.md 落档（三幕重写的执行清单）

- 摘要五句话定式（正向断言前置、gap 带归因）；§5.5 双通道证据提前；新 §5.6 合并「容量 + RL 条件性」为 scaling 研究章节；每图对号表。
- 写作触发条件：v3rloo 17/17 + 355M converged（两数据点落地后一次成文，避免半成品返工）。
- 计划文件本地 temp 目录 + 待素材齐后随 v1 草稿一起归档项目目录。

### 训练中期快照（01:50）

- 355M e17 b6200/18943（loss 2.789，仍低于 e16 的 2.7925 train 水平——继续有效学习）；
- v3rloo 仍 6 新 JSON 落盘（nluc_s0 集群A S3 阶段；egfp_s2 集群B S3 dir1；mouse_s0 S2 dir1——mouse 2.2kb 臂 MFE 计算是长尾，预计 9h 级）；
- 双 GPU 满载：A 27.6GB 训练+评测；B 5.5GB 双链（4090 24GB 上双链 + MFE_PROCS=8 是稳态配置，CPU 12 核是 RNAfold 瓶颈——如实记录：集群B GPU util 波动是评测 batch 间隙，非空转）。

---

## 2026-10-24 00:47（e16 落盘 · 新最优 + fig10 更新）

### 355M 容量研究关键数据点

- **e16 val 2.7912（新最优）**：低于 e13 的 2.7921，且 **cond_gap 从 1.92 降至 1.42**（条件信息量显著改善，非噪声波动）。
- 容量差距：355M@e16 最优 2.7912 vs 56M 收敛 2.8052 → **−0.014 nats/codon**（56M 用了 8 epochs 收敛，355M e16 仍在下降且尚未触发 plateau）。
- 判断更新：355M 在 862k 语料上**尚未饱和**——继续训到 plateau 才是容量第三点的严谨落点（watchdog 自动推进 e17+）。
- capacity_curves.json 已更新（v3_355M_862k 16 epochs），fig10 已重渲染并同步 /teams figures_v2/ + 本地（update_capacity.py 幂等，收敛后重跑一次即得终版）。

### 工程事件记录

- 本地工作目录被用户清理（fig 脚本/journal）——已从集群侧拉回全部内容（脚本在集群 figures_src/、journal 在 docs/handover/，git GitHub bb117fe 兜底）。**教训：集群侧 + GitHub 双份冗余在本次事件中生效，工作零丢失。**
- 新增 figures_src/render_figures_v2.sh（集群侧批量重渲染，自动准备 fig_data → 渲染 → 归档 /teams）；全部 7 张图（14 文件）集群归档验证。GitHub 225b9fd。

---

## 2026-10-24 凌晨（W3 图表重制 + 双集群推进）

### 训练与评测进度（00:30 快照）

- **355M e16 即将落盘**（b18900/18943，236.5min）——watchdog 将自动继续 e17；plateau 计数待 e17-e19 观察（e13 最优 2.7921 为锚）。
- v3rloo 评测 **8/17**（8 旧 + egfp_s1 新完成：cf done 9069s，2.5h 符合预期）：
  - 集群A rloo_c0：egfp_s1 ✓ → nluc_s0 运行中
  - 集群B rloo_c1：egfp_s2 S2 dir3；rloo_c2：mouse_s0 S2 dir1
- GPU：集群A 27.6GB/100%（训练+评测共存）；集群B ~20GB（双评测链）。

### W3.1 主图重制（7 张全部完成，house style）

统一视觉系统：CodonFlow=蓝 #0F4D92 / LinearDesign=红 #B64342 / codonGPT=teal / CAI-greedy=violet / uniform=neutral / GEMORNA=绿；Helvetica 15pt、spine 2.0、无顶右边框、legend 无框、PDF(矢量)+PNG(300dpi) 双输出、Type 42 字体（期刊可编辑）。

| 图 | 主张（一句话） | 数据源 | 校验 |
|---|---|---|---|
| fig1 塌缩 | masking 在引导之前就塌多样性 | E1_codongpt.json（50 样本/arm 真实 NED/熵/CAI） | PASS 3349×1340 |
| fig2 门控vs过滤 | 同预算下门控买到可行性+首达效率 | E2_gated_vs_filter.json（3 seeds + Wilcoxon p=6.1e-5 面板） | PASS |
| fig4 消融 | 单奖励反噬在密码子域复现（等权双优） | E4_ablation_3seed.json（18 arm 3 seeds 聚合） | PASS |
| fig5 主表 | 五方法×三场景；100% 保证脚注+绝对差距如实 | E5v2conv_main_table.json | PASS 3871×1690 |
| fig6 预算 | 中间档性价比拐点（12 配置网格） | E6_budget_curves.json（best value/call 标注） | PASS |
| fig10 容量 | 4× 数据在 56M 上饱和；355M 打开新档 | capacity_curves.json（355M 收敛点待补） | PASS |
| fig11 RLOO | RL 增益随预训练充分度衰减（6 arm 初版，15 arm 终版待 17/17） | S3R2_full_adaptive.json | PASS |

- 全部脚本本地 fig_batch_v2.py / fig_batch2_v2.py / fig10_capacity_v2.py / fig11_rloo_gain.py；已同步集群A figures_src/。
- **GitHub 7e72206**（figures v2 commit，走 patch→本地代理推送流）。
- 程序化校验：分辨率 >2000px、非空白率 0.06–0.39（每张独立阈值检查）——不靠目测靠数据。

### 待续

- e16 落盘 → log.jsonl 追加 → fig10 数据自动可补（capacity_curves.json 由 auto_trigger 或巡检更新）
- v3rloo 剩 9 arm（nluc_s0 + fly×4 + mouse×3 + egfp_s2）预计 ~20h
- 355M 评测链待收敛触发（巡检任务提示人工启动，串行 c3→c0→c1→c2→c4）

---

## 2026-10-23 深夜（双集群并行 + W2 推进）——存档摘要

- 集群B 接入验收（环境现成 torch cuda OK + pytest 41/41）；rloo_c1/c2 链拉起；GitHub a1e9326。
- W2.2/W2.3 完成：S3R2_full_adaptive.json（39 arm per-gene adaptive ref 重算；g08 零域修复验证）；S3R3_cas9_norm.json（Cas9 motif 长度归一化）。
- RLOO 初步裁决（6 arm，adaptive 口径）：无正向增益（2/6 正、均值 −5.3%）——A4 条件性结论待 17/17 终裁。
- 数据自检 9 项全 PASS（862k md5 复验一致 / 三重泄漏审计 0 / 四层 benchmark / 5 基线+2 补强）。

## 2026-10-23 恢复日——存档摘要

- 集群A 环境重建：conda codonflow + torch 2.14.1+cu132（**RTX 5090 sm_120 与 cu126 不兼容事故**：is_available True 但 matmul 报 no kernel image——静默降级陷阱，重装 cu132 后实测 OK）+ ViennaRNA 2.7.2 + pytest 41/41。
- 355M 续训拉起（watchdog v8-5090：batch 20000×3 = 26.5GB/100%util，比 4090 快 37%；28000 OOM 留证回退）。
- 交接文档三件套更新（spec A4 / tasks v5 / checklist J）+ GitHub 6dda1fa。
- fig10 house-style 首张。
# 冲刺 journal 增补（本地缓冲，将合并进集群 JOURNAL_SPRINT_20261023.md）

## 2026-10-25 01:00（★ 355M 评测 6 链并行 · E3 nluc 瞬时 NameError 修复重启 · fig10 21-epoch 终版落档）

### 进度快照

- 355M 评测 JSON：0/17（egfp_s0 主链到 S3_quad dir3；mouse_s1/s2 到 S2 dir1；E3 egfp 30 解扫 7 omega 推进中）。
- v3rloo：11/17 落盘（mouse_s0 补全臂进行中，S2 dir1；rloo_backfill c2 链 23:42 拉起——集群B 已停用后全部迁回集群A）。
- 五 tmux 会话 + eval355_e3nluc = 6 链并行；GPU 7.8GB（推理 + MFE_PROCS=12 CPU 满载，load ~72/16 核，RNAfold 主导——正常稳态）。

### 事件与处置（3 遍检查记录）

1. **E3 nluc 臂 22:47 瞬时失败**：`NameError: name 're' is not defined`。根因：补丁部署时序——22:47 c4 链启动时 run_exp3.py 还是「arch patch 无 import re」的中间版本，22:54 文件才写入完整版（含 import re）。
   - 验证 ×3：(a) grep 确认当前文件 import re 在位（line 16）；(b) py_compile OK；(c) 手动 smoke 跑 nluc 2 解 ×2 步 → `[arch] d_model=1280 n_layers=12 n_heads=16` 正常输出 EXIT=0。
   - 处置：00:52 tmux eval355_e3nluc 重启 nluc E3 臂（n-solutions 30 / n-steps 20 与链定义一致）。egfp 臂无需重启（用的已是修复后文件，arch 行已打印）。
2. **fig10 容量图 21-epoch 终版**：update_capacity.py 重跑（epochs 21, best 2.7875, gap −0.0178 vs 56M）→ fig10_capacity_v2.py 渲染（3699×1289, nonblank 0.108）→ 归档 /teams + 本地拉回。集群 commit f1888b5 → 本地代理 am → GitHub main 9258de4 推送完成。
3. **S3R2_full_adaptive 44-arm 重算验证**：E3_* JSON 为 CF-only 单方法格式（无基线 obj_vectors），确认无需纳入 S3 glob——排除「E3 计数虚低」误判。44 arm = E5_v3_56m×15 + E5_v3rloo×11 + HELD18×18。

### 用户指令执行记录

- 定时巡检任务更新（bf61f514 改为 355M 专用版）：用户主动取消——**遵从，不再动定时任务，全部手动巡检**。

### 下一步

- 等待 355M 17/17 + v3rloo 17/17（预计 24-36h；mouse 长尾臂 ~9h ×3 是关键路径）。
- 全落盘后：S3R2 重算纳入 355M → 容量第三点下游裁决表（CF 355M vs 56M vs 基线同表）→ fig10/fig11 终版 → Gate C → 预印本 v1 动笔。
