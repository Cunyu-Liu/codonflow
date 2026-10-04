# CodonFlow 训练日志（journal）

> 纪律（spec R6-3）：每个训练 run 在此追加一节；REGISTRY.md 记 run 索引，本文件记过程与结论。

## 2026-10-04 环境交接（Phase 0 完成）

- 服务器 A100（36.137.135.49）：8×A100-PCIE-40GB；GPU 0-5 被其他项目占用，GPU 6/7 开了 MIG（6=7×1g.5gb，7=2×3g.20gb）。
- conda env `codonflow`：ViennaRNA 2.6.4 ✓、mmseqs 18.8cc5c ✓、torch 2.5.1+cu121 ✓（8 GPU 可见）、pymoo ✓、matplotlib ✓。
- GitHub：`Cunyu-Liu/codonflow` 已建立，main 分支，每完成一批工作即推送。
- 仓库测试：41/41 通过（本地与服务器双端验证）。
- GPU 冒烟：MIG 3g.20gb matmul4096 0.29s；train_smoke loss 4.76→4.62 正常下降。

## 2026-10-04 数据体系（Phase 1 完成）

- GENCODE v47 pc_transcripts（112,218 转录本）→ CDS 提取（header CDS 区间）→ 清洗（71,869 kept；主要丢弃：frame 19,430、too_short 14,763、no_terminal_stop 4,596）。
- 多物种补充：C. elegans 28,782 + D. melanogaster 27,653 + mouse 45,810 + zebrafish 41,132（同规则清洗）。
- 合并 215,246 CDS → MMseqs2 easy-cluster 0.8 → 107,811 簇 → 簇级 80-10-10（train 172,240 / val 21,149 / test 21,857，整簇不跨 split）。
- CAI 双参考表：`configs/cai_ref_refseq.json`（GENCODE 全量）+ `configs/cai_ref_train.json`（训练集，暂代 HPA，待补 TPM 过滤版）。
- 分布审计（train）：长度中位 1191nt（q5-q95: 381-3762）、GC 0.506±0.073、CAI 0.801±0.035、MFE 样本均值 -470.9、RSCU top CTG 2.22 / bottom TTA 0.46——与真核蛋白编码基因预期一致，无异常双峰。四维图落 docs/data_audit/audit_train.png。
- 基准序列：eGFP（P42212, 238aa → 717nt 合成 CDS）、nanoLuc（JQ437370.1 CDS 100..615，516nt，与 GenBank /translation 逐字符核对一致）、SpCas9（Q99ZW2, 1368aa → 4107nt）。注意：**JQ437429 是错误引用（16S rRNA），正确 accession 是 JQ437370.1**——已核实并记录。

## 2026-10-04 LinearDesign 基线（决策门 A 输入）

- 官方实现编译成功（third_party/LinearDesign，g++ -Ofast，Linux x64）。
- 计时基准（停止条件④分母，3 repeats 取均值）：
  - eGFP（238aa）：**27.7 s/seq**，LD 自报 CAI 0.753 / MFE -429.4；我方复测（ViennaRNA 2.6.4）CAI 0.794 / MFE -444.1，蛋白身份保持 ✓
  - nanoLuc（171aa）：**17.6 s/seq**，LD 自报 CAI 0.796 / MFE -337.8；我方复测 CAI 0.825 / MFE -347.5，身份保持 ✓
- 结论：CAI ∈ [0.75, 0.83] 区间，与 codonGPT 论文量级（≈0.70）和 spec 预期 [0.65,0.75] 上界附近一致——Gate A 的判据方向正确，等 codonGPT 数字齐后正式判定。
- LD 与我方 MFE 差异（-429 vs -444）原因：LD 内置热力学参数版本 vs ViennaRNA 2.6.4 参数差异 + LD 序列不含终止密码子（我方补 TAA 后 fold）。已知偏差，记录在案。

## 2026-10-04 预训练启动（CF-P2-2.1.2-pretrain-001）

- 硬件：GPU7 的 MIG 3g.20gb（21GB，与 honghuiyang 的 9GB 任务共存于同一物理卡不同 MIG 实例）。
- 模型：768d/8L/12H（56.8M 参数，pCoMole 同构档）。
- 数据：172,240 训练 CDS，token-budget 24k 长度分桶打包（3705 batches/epoch，消除 padding 浪费）。
- 超参：AdamW lr=1e-5 wd=0.03，dropout=0（预训练档），梯度裁剪 1.0。
- 早期曲线：loss 5.81（b0）→ 4.13（b800），下降健康。
- 收敛判据：val loss 连续 3 epoch 相对下降 <0.1% 触发停机（代码已实现，不设步数上限）。
- 监控：每 30 分钟自动巡检（tmux 会话存活性 + loss 走势 + NaN 检查 + 自动重启逻辑）。
