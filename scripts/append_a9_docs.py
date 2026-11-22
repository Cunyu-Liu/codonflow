#!/usr/bin/env python3
"""Idempotently append the A9-DIRECTIVE registry row and A9 tasks section."""
from __future__ import annotations
import argparse
from pathlib import Path

ROW = "| A9-DIRECTIVE | 2026-11-22 | user strategic directive: positive-core-only paper + RK-G1 authorized + independent-data acquisition (supersedes bounded/negative default for A9+) | `docs/handover/DECISION_A9_20261122.md`; `configs/a9_positive_core_directive_v1.json`; `docs/handover/PROMPT_NEXT_AGENT_A9_RK37.md`; `docs/handover/HANDOFF_A9_20261122.md` | directive only; no training this commit; RK-G1=true authorized for A9+ (historical frozen protocols unchanged) | RK36 0/4 qualifying independent data; mandate acquire new construct-level synonymous native full UTR-CDS continuous fresh outcome independent host/study data (public-first, wet-lab fallback needs user approval) | this commit (docs+directive); builds on RK36 closeout `e4e78f6a` | SOTA gate: paired 95%CI lower>0 + multiplicity pass + legality 100% + full cost + time/compute-matched + protein/study OOD strata retained; positive-only positioning; no weaker-baseline substitution | n/a (directive); next phase B independent-data acquisition audit (R1-R7 per-source raw verification) then phase C authorized generative/functional benchmark on new independent data | gates RK_G1=true / generator_training_authorized=true / new_independent_data_read_after_freeze=true; historical MAGE functional untouched still frozen; paper headline must fairly beat strongest comparable baseline; negatives retained as boundary/ablation evidence; one-month preprint vs wet-lab tension flagged for user | directive_authorized_positive_core_rkg1_true_independent_data_mandate |"

SECTION = """
## 2026-11-22：A9 用户战略指令落档（阳性核心 / RK-G1 授权 / 补独立数据）

- [x] **指令落档**：`DECISION_A9_20261122.md` + `configs/a9_positive_core_directive_v1.json` + `PROMPT_NEXT_AGENT_A9_RK37.md` + `HANDOFF_A9_20261122.md`；REGISTRY 追加 A9-DIRECTIVE 行。用户三决定：论文仅阳性核心且必须公平击败最强 baseline；RK-G1 授权；重新补独立数据。
- [x] **gates 变更**：`RK_G1=true`、`generator_training_authorized=true`、`new_independent_data_read_after_freeze=true`，仅 A9+ 生效；历史冻结协议/结果不追改；历史 MAGE functional untouched（19072 行）仍冻结除非用户另行解封。
- [x] **定位与 SOTA 门槛**：positive-only；paired 95%CI 下界>0 + 多重校正 + 合法率100% + 完整成本 + time/compute-matched + OOD 分层保留；未赢最强 baseline 标未解决，不换弱 baseline/不删失败分层；阴性保留为边界证据。
- [ ] **阶段 B 独立数据获取审计**：公开优先逐源 raw 核实（Cambray2018/Kosuri2013/Goodman2013/Mutalik2013/Rhodius2012/Salis2011/Espah Borujeni/de Boer2020/Lind2020），R1–R7 判定；合格则 acquire/clean/SHA/预注册划分/泄漏审计；无合格则湿实验 DBTL 设计需用户批准预算与延期。
- [ ] **阶段 C 阳性核心**：新独立数据上预注册公平 benchmark + RK-G1 授权训练离散流/生成核心（合法核归一化/采样一致性验证），击败最强 baseline；结构机制仅在独立运输成立时纳入。
- [ ] **阶段 D 论文重定位**：阳性核心过 SOTA 门槛后重定位英文稿 headline；未建立则保持 working 并如实报阻塞，不编造阳性。
- [ ] **时间线张力**：一个月预印本目标与湿实验补数据冲突；公开优先为快路径，湿实验需用户批准。须用户决定数据源/预算/算力/延期。
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", type=Path, required=True)
    ap.add_argument("--tasks", type=Path, required=True)
    args = ap.parse_args()
    reg = args.registry.read_text()
    if "| A9-DIRECTIVE |" in reg:
        print("registry: A9-DIRECTIVE row already present; skip")
    else:
        if not reg.endswith("\n"):
            reg += "\n"
        args.registry.write_text(reg + ROW + "\n")
        print("registry: A9-DIRECTIVE row appended")
    tsk = args.tasks.read_text()
    if "A9 用户战略指令落档" in tsk:
        print("tasks: A9 section already present; skip")
    else:
        if not tsk.endswith("\n"):
            tsk += "\n"
        args.tasks.write_text(tsk + SECTION)
        print("tasks: A9 section appended")


if __name__ == "__main__":
    main()