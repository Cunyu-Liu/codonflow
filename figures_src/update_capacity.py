#!/usr/bin/env python3
"""更新 capacity_curves.json：把 355M 的 log.jsonl 序列（e1-e16，去重取最新）
合并进去并保持既有条目不变。幂等：每次运行都从 log.jsonl 重建 v3_355M_862k。"""
import json
from pathlib import Path

CAP = Path("/teams/HoulabData_1788502323/liucunyu/codonflow/figures_src/data/capacity_curves.json")
LOG = Path("/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/checkpoints/p3_v3_355m/log.jsonl")

d = json.loads(CAP.read_text())
vals = []
for line in LOG.read_text().splitlines():
    if line.strip():
        row = json.loads(line)
        vals.append(row["val_loss"])
# e1-e2 来自旧曲线（迁移前），log.jsonl 的 e3+ 是新集群续训；直接用 log.jsonl 全序列
# （e1 2.9672 / e2 2.8844 与旧记录一致——重放无差）
d["v3_355M_862k"] = vals
CAP.write_text(json.dumps(d, indent=1))
print("v3_355M_862k epochs:", len(vals), "best:", min(vals))
print("v3_56M_862k best:", min(d["v3_56M_862k"]))
print("gap (355M - 56M):", round(min(vals) - min(d["v3_56M_862k"]), 4))
