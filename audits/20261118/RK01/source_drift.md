# RK-01 来源与工作树漂移记录

日期：2026-11-18  
运行标识：CF-A8-RK01-SOURCE-ENV

## 权威起点

- 远端主工作树：`/home/codonflow`
- 起点 commit：`cd7905f48d498beec1563191d12b276b3d8c8728`
- 起点状态：`main...origin/main [ahead 4]`，工作区干净。
- 隔离工作树：`/home/codonflow-a8-rk`，分支 `a8-rk`。
- 原则：不改写既有 A8 rescue 历史，不覆盖主工作树；本轮执行用户提供的 A8-RK 合同。

## 文档漂移

| 文件 | 起点远端工作树 SHA256 | 用户 A8-RK 附件 SHA256 | 处理 |
|---|---|---|---|
| `docs/handover/spec.md` | `c4ee67039d9a23b05d569c122a49b6ae655ff809bca59fed492b1e146b8893` | `b407d8702e584b6e6fbfe2836d9caf77a843e373ace7c9f2bc1e67a1da691e43` | A8-RK 版同步到隔离分支 |
| `docs/handover/tasks.md` | `af8e7008de72a9245ea1d201fb88f2ed74709500c7b3f4d912bb6b9a5d8d` | `8af9e15167c6b81e674cf995f0d1d45312813f299f2358d0fd0652fe94` | A8-RK 版同步到隔离分支 |
| `paper/CodonFlow_preprint_A7.md` | `682a7f5031a316d0a7dc014a9ee19e73b5f909d7f2e034c43262bef755bf` | `682a7f5031a316d0a7dc014a9ee19e73b5f909d7f2e034c43262bef755bf` | 内容一致，保留 A8-RK 状态标记 |
| A8 路线审查 | `6dbde72c6eda53757538423a98143ba1df7eb6968544aecb469e57808bb9393a` | `a9dd78b516570dc18250952a1329a22628ca6ead9e8b36d2c77846f603d27ac8` | 新 A8-RK 路线替代旧 rescue 路线，仅在本分支 |
| `HANDOFF_A8_RK_20261118.md` | 不存在 | `1facae9b1ea5f915e18a1ff95d17c29a74b1d30bfd6f97c341bd1d290e6e2b5a` | 新增 |
| `PROMPT_NEXT_AGENT_A8_RK.md` | 不存在 | `e715037ca01261437109cd9400add61e8282f7f4956043025324b860898a6f6b` | 新增 |

说明：哈希按文件字节计算；Git 文本规范化可能使工作树哈希与 blob 哈希不同。环境 manifest 记录隔离工作树当前文件哈希，供独立复核。

## 范围锁定

本轮只登记来源与执行环境，不宣称任何功能数据已下载或训练完成。六个来源及许可状态见 `configs/a8_rk_functional_sources.json`；实际下载、清洗行数和 raw/clean SHA 由 RK-02 写入 `experiments/RK_DATA_REGISTRY.md` 与机器可读审计 JSON。

## 已核实的来源事实

- Boël 出版商 Supplementary Data 2 是原始 XLSX，页面明确说明含 6,348 蛋白的表达值、序列与计算参数；它不是固定蛋白同义库。
- Kudla 2009 出版商页面只列出 SOM PDF 和寡核苷酸 TXT；未发现逐条 154 序列—表达量附件。RK-02 必须将“论文报告样本数”和“实际获得行数”分开。
- MAGE-seq 的 PMC 页面列出 Data S1–S4 CSV 与 ArrayExpress `E-MTAB-4020`；只有实际下载并解析后才能登记样本数。
- 三个第二优先级 PLOS bicistronic 数据源本轮只登记，不将“候选”写成“已获得”。

## 排除项

无新增训练、模型选择、split 或 benchmark 改动。既有主工作树的 4 个未推送 commit 不由本任务改写或推送；只推送独立 `a8-rk` 分支。
