#!/usr/bin/env python3
"""Idempotently append the RK36 registry row (experiments/REGISTRY.md) and the
RK36 tasks section (tasks.md). Refuses to duplicate; preserves all prior content."""
from __future__ import annotations
import argparse
from pathlib import Path

ROW = "| RK36 | 2026-11-22 | label-free independent-transport feasibility audit + §4 branch-3 record + branch-2 pivot trigger (executes the handover independent-validation/pivot directive after RK34/RK35) | `a8_rk36_build_protocol.py`; `a8_rk36_feasibility_audit.py`; independent `a8_rk36_verify_feasibility.py`; `a8_rk36_integrate_manuscript.py`; `a8_rk36_review_manuscript.py`; `a8_rk36_closeout.py`; PPT `gen_rk36_pages.py`/`audit_rk36_ppt.py` | CPU single thread; `/home/codonflow-clean-env-v1`; label-free metadata audit only; no model fit, no GPU, functional untouched not read, no generator training | unified long table `rk_functional/clean/functional_long.csv` 25420 rows/31 cols (no UTR column); Kudla154 `91cd75e742f4`; Boel `boel_2016_nesg6348/sequence_expression.csv` 6348; Mordstein `rk28/.../sequence_cluster_facts.csv`; MAGE infA 19072 frozen; PPT archive `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk36/ppt_v1/` | freeze `7942d6a9`; science/independent `eca9171d`; manuscript §6.47 `cb528983`; PPT code/evidence + closeout + handoff (this commit) | frozen R1–R7 eligibility (independent study/host; full CDS; native variant-specific 5'UTR >=4nt; fixed-protein synonymous; protein+family map; fresh continuous outcome; isolation+provenance); qualify iff all 7 PASS; label-free frozen before outcome association; exact window UTR[-4:]+CDS[:38] | independent verify 24/24 PASS; manuscript integration 12/12 + review 32/32 PASS; PPT audit 23/23 PASS; project tests 455 passed/1 skipped/0 failed; closeout (this commit) | 0/4 datasets qualify (Kudla R1 fail; Boel R3–R7 fail; Mordstein R2–R3 fail; MAGE R2/R3/R7 fail); branch_3_no_qualifying_data_trigger_branch_2_pivot; 6 missing dimensions recorded; pivot to functional sequence modeling/translation dynamics, next RK37 preregistered functional prediction benchmark (RiboMIMO bounded clean; constant/ridge + CAI/GC + full-proxy MFE + general seq models; protein/study OOD; SOTA gate paired 95%CI lower>0 + multiplicity + 100% legality + full cost); result SHA `9b02373b460a`, independent `8b1c2bfbec7e`, protocol `891023c8746b`; paper §6.47 + Table 27, 1984 lines, SHA `8011248f9686`; PPT 170–173 (4 pages pSL/pSy/pSC/pSx) revision145, 173 pages total, prior 169 intact; feasibility/eligibility only — no transport effect, SOTA, mechanism, protein/functional OOD or RK-G1 claim; RK-G1=false | done_feasibility_audit_zero_qualifying_branch3_record_branch2_pivot_triggered_independent_manuscript_ppt_closeout_pass |"

SECTION = """
## 2026-11-22：RK36 独立运输可行性审计与§四转向（执行交接文档核心指令）

- [x] **预注册冻结**：标签无关可行性协议冻结 R1–R7 合格要求（独立研究/宿主、完整 CDS、变体特异天然 5'UTR≥4nt、固定蛋白同义库、蛋白身份+family 映射、新鲜连续结局、隔离+溯源），合格⟺七项全 PASS；冻结于任何结局关联之前。协议 SHA `891023c8746b…`，冻结提交 `7942d6a9`。
- [x] **标签无关审计**：审计 4 个数据集（Kudla/Boël/Mordstein/MAGE infA），仅读 schema/覆盖/身份元数据，不做结局效应相关、不读 functional untouched。统一长表 25420 行/31 列**无 5'UTR 列**。结果 **0/4 合格**：Kudla R1 fail（训练队列）；Boël R3–R7 fail（跨蛋白天然非 synonymous、ordinal 0–5、固定 pET/T7 leader 无天然 UTR、family 映射缺失）；Mordstein R2–R3 fail（observed-R1 自 CDS pos4 起、缺 ATG/上游 4nt）；MAGE R2/R3/R7 fail（无完整构建、冻结禁读）。result SHA `9b02373b460a…`，科学提交 `eca9171d`。
- [x] **独立核验**：独立脚本重读原始源、重导判别事实与各数据集合格判定，**24/24 PASS**，确认 0 合格与 branch-3 转向。independent SHA `8b1c2bfbec7e…`。
- [x] **论文 §6.47**：新增 Table 27 可行性矩阵 + 缺失维度 + 转向计划 + 非主张声明；integration **12/12**、review **32/32** PASS；稿件 1931→1984 行，SHA `8011248f9686…`，提交 `cb528983`。
- [x] **在线 PPT**：在 169/revision140 后追加 170–173（4 页 `pSL/pSy/pSC/pSx`），p171 原地微调版面（revision145）；PPT 审计 **23/23** PASS（Table 27 逐格对冻结 result），4 张真实截图视觉复核 PASS；旧 169 页语义保持不变。脚本/小证据入 git `audits/20261122/RK36/ppt_v1/`，大型 XML/截图归档 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk36/ppt_v1/`。
- [x] **转向决策**：无合格独立运输数据 → §四 branch-3 记录 6 项缺失维度（同义库/天然 UTR/完整跨宿主 CDS/连续结局/family 映射/溯源），正式触发 branch-2 转向：停止以 start-aware MFE 为核心创新，转向数据支持的功能序列建模/翻译动力学；下一任务 RK37＝预注册翻译速度/功能预测 benchmark（RiboMIMO 等 bounded clean 数据，constant/ridge + CAI/GC + full-proxy MFE + 通用序列模型 baseline，蛋白/研究 OOD，SOTA 须配对 95%CI 下界>0 + 多重性 + 100% legality + 完整成本）。佐证：RK23 Boël 蛋白 OOD 0/4（Holm p=1）+ RK25 机制 0/2 已构成跨蛋白跨宿主运输失败。
- [x] **项目测试与 closeout**：`run_tests_json.py tests/` 得 **455 passed / 1 skipped / 0 failed**（18.17s）；closeout 全链路核验 PASS（协议/result/independent/integration/review/PPT/tests + 提交 + gates）。
- [ ] **仍未闭合**：external actual-set SOTA 主矩阵、time-matched 七方法、完整 dense、多物种 VeloHARMO、functional protein OOD、独立确认、wet-lab/前瞻 DBTL；RK37 转向任务待启动。RK-G1=false、generator_training_authorized=false，不得启动昂贵生成训练或把本 closeout 写成 RK-G0–G4 全通过。
- [ ] **复现边界**：本轮为标签无关可行性审计，无模型拟合，故无干净复现对比（不适用）；PASS 仅覆盖冻结协议、独立重导、稿件与页面验收及项目测试。权威工作树 `/home/codonflow-a8-rk`、分支 `a8-rk`，与并行会话共享并发提交。
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", type=Path, required=True)
    ap.add_argument("--tasks", type=Path, required=True)
    args = ap.parse_args()
    reg = args.registry.read_text()
    if "| RK36 |" in reg:
        print("registry: RK36 row already present; skip")
    else:
        if not reg.endswith("\n"):
            reg += "\n"
        args.registry.write_text(reg + ROW + "\n")
        print("registry: RK36 row appended")
    tsk = args.tasks.read_text()
    if "RK36 独立运输可行性审计" in tsk:
        print("tasks: RK36 section already present; skip")
    else:
        if not tsk.endswith("\n"):
            tsk += "\n"
        args.tasks.write_text(tsk + SECTION)
        print("tasks: RK36 section appended")


if __name__ == "__main__":
    main()