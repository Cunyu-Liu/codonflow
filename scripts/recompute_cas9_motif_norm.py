#!/usr/bin/env python3
"""W2.2: Cas9 S3 motif 长度归一化重算（A4 口径）。

问题：motif_penalty = 计数和（未长度归一化）。Cas9 4104nt vs eGFP 717nt 的
motif 数量天然差 ~6-8 倍，S3 四目标里 motif 轴尺度不可比 → 固定 ref 下 Cas9
的 motif 轴塌到域外。

修复（离线重算，不动原 JSON）：对每个 arm 的 obj_vectors 第 4 轴（-motif 罚）
按 n_codons 归一化（motif 计数 / 密码子数），再按 per-gene adaptive ref 重算 S3 HV。
方法：从 JSON 读取 motif 轴原始值 + 序列长度（n_solutions/log 不可得时用 obj_vector 数 ×
每解 n_codons 近似——不，直接用 arm 元数据：E5 JSON 里有 per-method obj_vectors，
序列长度由 arm 键（基因名）查 bench fasta 得到）。

输出：S3R3_cas9_norm.json + 对比打印（归一化前 vs 后 CF/LD/GPT）。

Run: python recompute_cas9_motif_norm.py   (纯 CPU)
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/codonflow/src")
from codonflow.eval.metrics import hypervolume  # noqa: E402

OUTDIR = Path("/teams/HoulabData_1788502323/liucunyu/codonflow/eval_outputs")
OUT = Path("/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/eval_outputs/S3R3_cas9_norm.json")
METHODS = ["codonflow", "lineardesign_scan", "codongpt", "cai_greedy", "uniform_edit_flow"]

# Cas9 arm JSON（E5_fix_cas9_s0/1/2）与序列长度：cas9_probe.fasta
CAS9_FASTA = Path("/teams/HoulabData_1788502323/liucunyu/codonflow/codonflow/corpora/cas9_probe.fasta")


def seq_len_from_fasta(path: Path) -> int:
    n = 0
    for line in path.read_text().splitlines():
        if not line.startswith(">"):
            n += len(line.strip())
    return n


def main():
    n_codons = seq_len_from_fasta(CAS9_FASTA) // 3
    print(f"Cas9 length: {n_codons * 3} nt = {n_codons} codons")
    results = {}
    for p in sorted(OUTDIR.glob("S3R_cas9_s[0-9].json")):
        tag = p.stem
        d = json.loads(p.read_text())
        rows = list(d.values())[0]
        row = rows[0]
        pool = {}
        for m in METHODS:
            k = f"S3_quad/{m}/obj_vectors"
            if k in row and row[k]:
                v = np.asarray(row[k], dtype=float).copy()
                # 第 4 轴是 -motif_penalty（负值，越大越好=罚越少）。
                # 归一化：把计数值除以 n_codons（每密码子平均罚）。
                # 原轴值 = -count_sum；norm 轴值 = -count_sum / n_codons
                v[:, 3] = v[:, 3] / n_codons
                pool[m] = v
        if "codonflow" not in pool or len(pool) < 2:
            print(f"[{tag}] incomplete pool, skip")
            continue
        # adaptive ref 在归一化后的轴上重取
        allpts = np.vstack(list(pool.values()))
        ref = np.array([allpts[:, i].min() - 0.05 * abs(allpts[:, i].min()) - 1e-6
                        for i in range(allpts.shape[1])])
        line = {"n_codons": n_codons, "ref": [float(r) for r in ref]}
        for m, v in pool.items():
            line[f"{m}/hv"] = float(hypervolume(v.tolist(), ref))
        results[tag] = line
        cf = line["codonflow/hv"]
        ld = line.get("lineardesign_scan/hv", 0.0)
        gp = line.get("codongpt/hv", 0.0)
        print(f"[{tag}] norm-ref HV: CF {cf:12.2f} | LD {ld:12.2f} | GPT {gp:12.2f} | CF/LD {cf/max(ld,1e-9):.3f}")
    OUT.write_text(json.dumps(results, indent=1))
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
