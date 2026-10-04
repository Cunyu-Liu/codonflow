# CodonFlow 训练日志（journal）

> 纪律（spec R6-3）：每个训练 run 在此追加一节；REGISTRY.md 记 run 索引，本文件记过程与结论。

## 2026-10-04 环境交接（Phase 0）

- 服务器 A100（36.137.135.49）：8×A100-PCIE-40GB；GPU 0-5 被其他项目占用（rna_sc / rna-ft-eval / toktokenbench 等），GPU 6/7 各有 8-28GB 显存空闲。
- GitHub SSH 认证 OK（Cunyu-Liu）；远端 `Cunyu-Liu/codonflow` 已建立。
- 复用资产盘点：codonGPT ckpt ee7017c4（本地缓存于 mrna_editflow external_tools）、eval/metrics.py（CAI/NED 实现来源）、monitor cron 模板。
- ViennaRNA：editflow env 为 2.7.2 → 新建 codonflow env 用 conda-forge 锁 2.6.4。
- LinearDesign 二进制不在服务器 → 需要从官方源码编译（编译期 CPU，跑 DP 快）。
- mmseqs 未安装 → conda bioconda 装。
