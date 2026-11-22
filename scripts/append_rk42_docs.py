#!/usr/bin/env python3
"""Idempotently append the A9-RK42 row to experiments/REGISTRY.md and the RK42
section to tasks.md, reading real full-project test counts from the test JSON.
Does not modify any existing row/section. Run after the audit chain + tests.

Run: /home/codonflow-clean-env-v1/bin/python scripts/append_rk42_docs.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "audits/20261122/RK42/rk42_full_project_tests_v1.json")
REG = os.path.join(ROOT, "experiments/REGISTRY.md")
TASKS = os.path.join(ROOT, "tasks.md")

t = json.load(open(TESTS))
counts = "%d passed/%d skipped/%d failed" % (t["passed"], t["skipped"], t["failed"])

ROW = (
    "| RK42 | 2026-11-22 | A9 phase B independent-data acquisition audit (public-first, label-free); "
    "0/9 public candidates qualify under frozen R1-R7; branch B3 wet-lab DBTL requires user approval | "
    "`a9_rk42_build_protocol.py`; `a9_rk42_acquisition_audit.py`; independent `a9_rk42_verify_acquisition.py`; `append_rk42_docs.py` | "
    "CPU single thread; `/home/codonflow-clean-env-v1`; no model fit/outcome association/generator training; raw downloads (Cambray partial CSV 19760 rows + Note1/Tables PDFs, Kosuri methods text) | "
    "protocol SHA `aa6071c3b13b0376953770e9292e17ea41e7267d1352ec91239d5b7a3fc1ddbd`; audit v2 SHA `5b73e43fbc18613913b0772b86aa4370f0ffdbfb5d3687c2edc21f530c43c0c3`; independent v2 SHA `7a520c96fd8552910ca3fc25e7d927e643f5a74946a64d69d5600596ce09bf86`; raw `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk42/raw/` | "
    "freeze/science/docs (this commit) | "
    "frozen R1-R7 reused from RK36; 9 candidates raw-verified; Cambray independent raw re-derivation gs.sequence=96bp all 19760 rows / 12394 distinct peptides (amino acids vary) / continuous P_NI 1-100; qualify iff all 7 PASS | "
    "independent v2 30/30 PASS (v1 27/29 retained as failure log); targeted tests 8/8; full project " + counts + " | "
    "0/9 qualify: Cambray R2/R3/R4/R5 fail (96bp segment, constant [-30;3] leader, amino-acid variation, single sfGFP reporter); Kosuri/Mutalik/Salis/EspahBorujeni/deBoer regulatory-grammar R4 fail; Goodman raw Cloudflare-blocked R2/R3 fail; Lind synonymous but insufficient scale; branch `B3_NO_QUALIFYING_PUBLIC_DATA_WETLAB_DBTL_REQUIRES_USER_APPROVAL`; strategic R3-relaxation option flagged for user | "
    "no transport/SOTA/mechanism/generator claim; historical MAGE functional untouched frozen; public retrospective vs prospective DBTL separated; wet-lab budget+timeline require user approval; phase C positive core blocked on qualifying independent data | "
    "done_phaseB_acquisition_audit_zero_qualifying_branchB3_independent_30of30_user_decision_pending |\n"
)

SECTION = (
    "\n## RK42 · A9 阶段 B 独立数据获取审计（2026-11-22）\n\n"
    "- [x] **预注册与冻结**：`A9_RK42_PREREGISTRATION.md` + `a9_rk42_build_protocol.py` → `configs/a9_rk42_independent_data_acquisition_protocol_v1.json`（FROZEN_BEFORE_OUTCOME_ASSOCIATION，SHA `aa6071c3b13b…`）；沿用 RK36 冻结 R1–R7，9 候选，标签无关。\n"
    "- [x] **逐源 raw 核实**：Cambray2018 Note1/Tables PDF 完整下载 + Data15 部分 zip 解压 19,760 真实行独立重导（gs.sequence 全 96bp、12,394 种翻译肽、P_NI 1–100 连续）；Kosuri2013 methods 全文+Fig.1（114 启动子×111 RBS 驱动固定 sfGFP）；Goodman2013 Table S1 被 Cloudflare 拦截（真实失败保留）；Mutalik/Salis/Espah/Rhodius/deBoer/Lind 构建几何核实。\n"
    "- [x] **判定 0/9 达标**：Cambray R2/R3/R4/R5 失败；调控语法库（Kosuri/Mutalik/Salis/Espah/deBoer）R4 失败；Goodman R2/R3 失败；Lind 同义但规模不足。`branch_decision=B3_NO_QUALIFYING_PUBLIC_DATA_WETLAB_DBTL_REQUIRES_USER_APPROVAL`。审计 v2 SHA `5b73e43fbc18…`。\n"
    "- [x] **独立复核与测试**：`a9_rk42_verify_acquisition.py` 自行重导 Cambray raw + 核验引文/工件 + 重算判定，v2 **30/30 PASS**（v1 27/29 失败日志保留；v1→v2 仅证据/复核器修正，不改 0/9 判定）；定向测试 8/8；全项目 " + counts + "。\n"
    "- [x] **文档**：REGISTRY RK42 行 + 本节 + `HANDOFF_A9_RK42_20261122.md`。\n"
    "- [ ] **阶段 C 阳性核心被数据缺口阻塞**：0/9 公开达标，无合格新独立数据做公平 benchmark + RK-G1 训练。\n"
    "- [ ] **需用户裁决**：(A) 维持严格 R1–R7 → 前瞻 DBTL/湿实验（须批准预算与延期，超一个月）；或 (B) 仅为功能 benchmark 授权放宽 R3（固定 leader + N 端同义编辑窗，Goodman 式公开快路径），保留严格 R3 仅用于起始结构运输主张。Cambray 因 R4 氨基酸变异即使放宽 R3 也不合格。不擅自放宽冻结 R1–R7。\n"
    "- [ ] **边界**：历史 MAGE functional untouched 仍冻结；RK-G1=true 仅授权阶段 C，本审计未训练；无运输/SOTA/机制/生成主张；公开回顾与前瞻 DBTL 分开。\n"
)


def main():
    reg = open(REG).read()
    if "| RK42 |" not in reg:
        if not reg.endswith("\n"):
            reg += "\n"
        open(REG, "w").write(reg + ROW)
        print("REGISTRY: appended RK42 row")
    else:
        print("REGISTRY: RK42 row already present (idempotent)")
    tk = open(TASKS).read()
    if "## RK42" not in tk:
        if not tk.endswith("\n"):
            tk += "\n"
        open(TASKS, "w").write(tk + SECTION)
        print("tasks: appended RK42 section")
    else:
        print("tasks: RK42 section already present (idempotent)")
    print("full_project_tests", counts)


if __name__ == "__main__":
    main()