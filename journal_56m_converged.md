
---
## 56M 收敛备份（2026-10-15 17:45 · 三端 md5 全一致）

**里程碑**：56M v3 训练于 05:37 正式收敛（EXIT=0）——8 epochs，val 曲线 2.8715→2.8052→2.8056→2.8062→2.8069（e5 起四连平），plateau 3/3 触发停止准则。

| 文件 | 大小 | md5（集群=orico=Documents 三端一致） |
|---|---|---|
| `v3_final/v3_56m/converged.pt` | 227,263,802 | c8072617112d80a16a01267b2cee8b21 |
| `v3_final/v3_56m/converged.json` | 259 | 7fdeab501b1fa0c7bfa20a592cfa7d1a |
| `v3_final/v3_56m/epoch_009.pt` | 227,263,802 | 07d8ce1d6bc46a95992d67e6f0e3874e |
| `v3_final/v3_56m/log.jsonl` | 1,148 | 9e1cb9fbf8b244c5977bc7e975bb0a58 |
| `v3_final/v3_56m/train.log` | 193,092 | （随 log 同步） |

**收敛版评测已启动**（11:41，`run_v3_eval.sh p3_v3_56m v3_56m launch`，5 MIG 链 c0-c4，E5 五基因×3 seed + E3，协议与 10-12 rerun 完全一致）。已产出 6 JSON（E3 egfp/nluc + E5 egfp_s0、nluc_s1/s2 等）并备份双端 eval_outputs/。

**355M 事故与自动恢复**：e3 于 17:40 跑至 97%（b99700）时被其他用户 18.92GB 进程挤爆 GPU0 而 OOM（epoch 未落盘，进度损失）。17:45 v7 watchdog 自动在 GPU3 以 `--resume last.pt`（= e2）重新拉起，现稳定运行（8.7GB）。第三次尝试 e3，预计 ~10h/epoch。

**容量曲线当前数据点**：v1-56M@215k 收敛 4.061 / v2-56M@215k 收敛 ~2.81（含修复后 2.814 参考）/ v3-56M@862k 收敛 **2.8069**（e8）/ v3-355M@862k 待 e3-e4（历史最好 2.8844@e2）。
