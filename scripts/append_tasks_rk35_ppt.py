#!/usr/bin/env python3
"""Idempotently append the RK35 PPT/handoff closeout item to docs/handover/tasks.md.
Additive only; does not modify any existing (parallel-authored) content."""
from pathlib import Path

p = Path("docs/handover/tasks.md")
text = p.read_text()
marker = "研究 PPT165–169 与 handoff（本会话闭合）"
if marker in text:
    print("ALREADY_PRESENT")
    raise SystemExit(0)
bullet = (
    "\n- [x] **研究 PPT165–169 与 handoff（本会话闭合）**：在线 deck 从 164 页/rev131"
    "（并行 RK34 占 156–164）追加 RK35 五页 165–169（设计/冻结执行/主判定 D1+Table25/"
    "绝对+次要 Table26/证据+边界），slide_id `pSw/pSl/pSN/pSt/pSX`，rev136；设计系统复用既有 "
    "A8-RK（Inter/浅灰底/teal 强调/导航栏+判断句标题+KPI 卡+深色表头表格+结论带+来源行+页码），"
    "前 164 页规范化内容不变。PPT 审计 10/10 PASS（页数/末5页ID/冻结值渲染/旧页不变/无emoji），"
    "五张真实 960×540 截图逐页视觉 PASS。源 XML/回执/审计入 `audits/20261122/RK35/ppt_v1/`，"
    "截图与全文回读入 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk35/ppt_v1/`。"
    "完整交接见 `docs/handover/HANDOFF_A8_RK35_20261122.md`。REGISTRY RK35 行与 tasks RK35 节由并行 "
    "`a24c3dac` 写入，本会话核验后尊重不覆盖。边界张力（提示词 §三/§四 明令 RK34 为同队列切窗终点、"
    "RK35 起须独立验证或转向）仍待用户裁决；裁决前不冻结/启动任何新编号任务。\n"
)
if not text.endswith("\n"):
    text += "\n"
p.write_text(text + bullet)
print("APPENDED", len(bullet))