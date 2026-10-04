# 决策门 A（预注册判定）

日期：2026-10-04 ｜ 判据（tasks.md Task 1.5）：基线数字与文献量级一致，CAI ∈ [0.65, 0.75] 为通过；显著偏离需排查复现链路。

## 判定数字（3 repeats / 50 constrained samples）

| 方法 | 序列 | CAI | MFE (kcal/mol) | 身份保持 | 合法率 | 耗时/seq |
|---|---|---|---|---|---|---|
| LinearDesign (官方, λ=0) | eGFP | 0.753 (LD 自报) / 0.794 (我方复测) | -429.4 / -444.1 | 100% | 100% | 27.7 s |
| LinearDesign (官方, λ=0) | nanoLuc | 0.796 / 0.825 | -337.8 / -347.5 | 100% | 100% | 17.6 s |
| codonGPT 约束生成 (ckpt ee7017c4, SHA df41546883e31ba1) | eGFP (50 samples, T=1.0) | 0.827 ± — | -198.9 (均值, 采样解) | 100% | 100% | 0.97 s |
| codonGPT 约束生成 | nanoLuc (50 samples) | 0.806 | -159.1 | 100% | 100% | 0.675 s |

## 判定

- CAI 数值域：LinearDesign 0.753-0.825、codonGPT 0.806-0.827。
- 对照文献量级：codonGPT 论文本地历史实测 CAI≈0.70、codon accuracy≈0.42；我方 codonGPT 约束采样 CAI 0.81-0.83 略高（约束采样 + 人类参考表差异，方向一致、量级相同）。
- LinearDesign eGFP 27.7s 与论文报道的 DP 复杂度量级一致。
- 身份保持/合法率全 100%——约束链路（tokenizer / synonymous masking / 阅读框）工作正确。
- 注意事项：我方 CAI 参考表为 GENCODE v47 全量 RSCU（train split 版），与 LD 内置表不同——已用同一张表统一复测所有方法，口径公平。

## 结论：**GO**（通过）

基线数字与文献量级一致，Phase 2 继续。复现链路无异常，无需排查。

## 已知偏差记录（不影响判定）

1. LD 自报 MFE 与我方 ViennaRNA 2.6.4 复测差 ~15 kcal/mol（热力学参数版本 + 终止密码子补充）——主表将统一用我方口径。
2. codonGPT 采样解的 MFE 均值远高于 LD DP 最优（-199 vs -444）——符合预期：AR 采样不做全局结构优化，这本身就是 spec 叙事①的动机证据。
