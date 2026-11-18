# A8-RK Functional Data Registry

状态时间：2026-11-18。此表区分“论文报告”“已下载原始文件”“通过清洗的序列—标签行”。空值不得解释为 0。

| source_id | accession / DOI | 原始文件相对路径（数据根下） | raw SHA256 | clean 相对路径 | clean SHA256 | 实际行数 | 排除原因 | 协议 | 许可/状态 |
|---|---|---|---|---|---|---|---|---|---|
| kudla_2009_gfp | 10.1126/science.1170160 | RK-02 待写入 | 待写入 | 待写入 | 待写入 | 论文报告 154；实际待审计 | 待审计 | SOM + oligos；出版商未列逐条数据表 | 出版商附件；未声明开放许可 |
| boel_2016_nesg6348 | 10.1038/nature16509 | `raw/boel_2016_nesg6348/41586_2016_BFnature16509_MOESM292_ESM.xlsx` | RK-02 待写入 | RK-02 待写入 | RK-02 待写入 | 论文报告 6,348；实际待审计 | 待审计 | 异源蛋白、E=0–5；非同义库 | 出版商附件；未声明 CC |
| kelsic_2016_mage_seq | E-MTAB-4020 / 10.1016/j.cels.2016.11.004 | `raw/kelsic_2016_mage_seq/` | RK-02 待写入 | RK-02 待写入 | RK-02 待写入 | 论文报告 12,726；实际待审计 | 待审计 | infA chromosomal fitness；非分泌表达 | 作者手稿附件；未声明开放许可 |
| kudla_2006_bicistronic | 10.1371/journal.pbio.0040180 | 未下载 | — | — | — | — | 第二优先级，尚未执行 | 待核验 | 仅登记候选 |
| welch_2009_bicistronic | 10.1371/journal.pone.0007002 | 未下载 | — | — | — | — | 第二优先级，尚未执行 | 待核验 | 仅登记候选 |
| fath_2011_bicistronic | 10.1371/journal.pone.0017596 | 未下载 | — | — | — | — | 第二优先级，尚未执行 | 待核验 | 仅登记候选 |

数据根：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk_functional/`。大文件不进入 Git；仓库仅保存来源、脚本、测试、小型汇总和哈希。
