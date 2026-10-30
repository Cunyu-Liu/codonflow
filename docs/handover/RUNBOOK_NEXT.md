# RUNBOOK · 收敛之后按这个顺序跑（2026-10-31 编写）

> 目的：把 P0→P3 的每条命令、判据、禁止事项写死，避免 checkpoint 落盘后临时找参数、重复返工。
> 所有路径以集群为准：代码 `/home/codonflow`，数据/权重 `/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow`。
> 环境：`/root/miniconda3/envs/codonflow/bin/python`（torch cu132，ViennaRNA 2.7.2）。跑前 `PYTHONPATH=src`。

## G0 收敛判定（自动，不要人工宣布）

- 判据在代码里：`ConvergenceTracker(rel_tol=1e-3, patience=3)`，即 val 连续 3 个 epoch 相对下降 < 0.1%。
- 触发后脚本自动写 `converged.pt` + `converged.json` 并退出；**没有 converged.json 就不算收敛**。
- 核对三件事（缺一不可）：

```bash
B=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/checkpoints
cat $B/a6_v4_56m_r2/converged.json          # best_epoch / best_val_loss / history
sha256sum $B/a6_v4_56m_r2/converged.pt
sha256sum $B/a6_v4_56m_fulltoken/converged.pt
```

- **禁止**：用 `last.pt` 或 `best.pt` 冒充收敛；用 val 绝对值跨臂比较（两个目标不同量纲）。

## G1 unique18 基线（seed 0 → seeds 1/2）

```bash
C=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow
cd /home/codonflow && PYTHONPATH=src MFE_PROCS=8 \
  /root/miniconda3/envs/codonflow/bin/python scripts/run_a6_baselines.py \
  --benchmark-fasta $C/corpora/a6_benchmark/unique18.fasta \
  --rscu-json /home/codonflow/configs/cai_ref_v4train.json \
  --out-dir $C/eval_outputs/a6_baselines/unique18_s0 \
  --n-solutions 100 --seed 0 --resume
```

- seeds 1/2：同命令只改 `--seed 1` / `--seed 2`（文件名带 `_sN`，同目录不会覆盖；**不要新建数据目录**）。
- RSCU 参考表：`configs/a6/cai_ref_v4train.json` 与 `configs/cai_ref_v4train.json` 字节相同，
  SHA256 均为 `80592c4eaeab61cdfc86a6f927fb1ef3c4b409b785c73bb466078df9af71bb6f`，用任一路径均可；换表必须登记。
- 验收：18 条 × 5 方法全部 `status=done`；`identity_rate=1.0`；`n_unique` 如实记录（GEMORNA 会少于 100，不补样）；MFE/NED 全量独立复核（不能只查有限性）。

## G2 三臂同预算推断（唯一 checkpoint + 配对初始状态）

```bash
C=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow
cd /home/codonflow && PYTHONPATH=src \
  /root/miniconda3/envs/codonflow/bin/python scripts/run_a6_rollout_pilot.py \
  --benchmark-fasta $C/corpora/a6_benchmark/unique18.fasta \
  --checkpoint $C/checkpoints/a6_v4_56m_r2/converged.pt \
  --rscu-json /home/codonflow/configs/a6/cai_ref_v4train.json \
  --atc-yaml /home/codonflow/configs/atc_norm.yaml \
  --record-id <ONE_RECORD_ID> \
  --out $C/eval_outputs/a6_pilot/three_arm_converged_<record>_s0.json \
  --n-solutions 100 --terminal-step 4 --candidate-count 4 --rollout-count 4 --seed 0
```

- **这个脚本一次只能吃一条 CDS**（2026-10-31 实测：多记录 FASTA 会直接 `ValueError`）。
  已加 `--record-id` 选记录；按记录循环：

```bash
for rid in $(grep '^>' $C/corpora/a6_benchmark/unique18.fasta | sed 's/^>//' | awk '{print $1}'); do
  ... --record-id "$rid" --out $C/eval_outputs/a6_pilot/three_arm_converged_${rid}_s0.json
done
```

- 三个臂由脚本内部固定展开：`base` / `immediate`（rollout=0，消融）/ `short_rollout`（R=rollout-count）。
- 每基因 × seed 至少各一次；论文主表要 2 个 core 基因 × 3 seeds，另加 unique18 子集做长度分层。
- 验收：三臂 `identity=1.0`；四成本字段齐全（`forward_calls`、`base_state_evaluations`、`rollout_batch_forwards`、`rollout_state_transitions`、终端请求、唯一 scorer）；恒定 C/T 时 forward 与公式 `F=T+T(T+1)/2+C*T(T-1)/2` 对得上。
- **禁止**：把 2 路径协议诊断写成算法优劣；把不同 checkpoint 的臂拼成一组对照。

## G3 联合 HV 主表

- 参考域：同一基因/seed、**全部方法**的 obj_vectors 取唯一并集；参考点 `min − 0.05×(max−min)`，scale `q95 − min`，HV 在 `(points−ref)/scale` 上以 0 为参考（实现：`scripts/a6_joint_hv.py`，与 `recompute_s3_full_adaptive.pooled_reference` 等价）。
- 方法池固定：CodonFlow（收敛臂）、LinearDesign、codonGPT、GEMORNA、CAI-greedy、uniform_synonymous。缺失/架构性排除必须显式列出，不记零分、不静默删除。

```bash
# 联合 HV 聚合（唯一并集参考域；缺失方法进 missing_methods）
C=/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow
cd /home/codonflow && PYTHONPATH=src \
  /root/miniconda3/envs/codonflow/bin/python scripts/a6_joint_hv.py \
  --pilot-glob "$C/eval_outputs/a6_pilot/three_arm_converged_*_s0.json" \
  --baseline-glob "$C/eval_outputs/a6_baselines/core_s0/*_s0.json" \
  --out $C/eval_outputs/a6_pilot/joint_hv_converged_s0.json
```

- 口径（与 spec §4.4、`pooled_reference` 一致）：参考点 `min − 5%×(max−min)`，scale `q95 − min`，HV 在 `(points−ref)/scale` 上以 0 为参考。退化轴会被拒绝；确有需要时加 `--allow-degenerate` 并记录轴号。
- 自检：`scripts/a6_joint_hv.py --self-test`（5 条不变量），并有 `tests/test_a6_joint_hv.py` 5 项契约测试。
- 验收：HV + 置信区间（bootstrap）；NED；identity/legal；四成本；配对检验（同基因同 seed 的 Wilcoxon/符号检验）。预注册线：HV 相对最强基线 ≥+10%、NED ≥基线 70%、OOD 衰减 <2pp。

## G4 论文与图

- 只有 G0–G3 全部通过才写 Results 章和主图；否则按“测量 + 机制”方法学论文降级。
- 每张图必须能指到冻结 JSON + checkpoint SHA256 + 代码 commit；图上标题不得超出数据支持的结论。

## 本轮已知的坑（照抄会出错）

1. 两个 56M 臂在 24 GB 卡上**不能**用同样的 20000 token micro-batch 并行（各需 11–12 GiB）。必须带 `--gpu-mem-fraction`（当前 0.58 / 0.30），且有效 batch 都是 60,000 token。
2. `--resume` 基线脚本会校验 `protocol / source_sha256 / benchmark_sha256`，换 benchmark 文件会被拒绝，别硬改 JSON。
3. `unique18.fasta` 的 SHA256 必须是 `30e3dbbf…`；不是这个就别跑。
4. GEMORNA 必须从权威 benchmark FASTA 逐条翻译核验，旧 239 aa EGFP-like 输入已作废。
5. LinearDesign 只给 7 个确定性解时**不许随机补样到 100**。
6. 训练曲线跨臂不可比 val 绝对值；`live best.pt` 会变，对照必须用冻结文件。
