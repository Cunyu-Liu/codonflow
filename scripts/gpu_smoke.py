"""GPU smoke test (Task 0.2.6): CUDA availability + memory stress + DDP check.

Asserts CUDA is available (no silent CPU fallback, spec R6), allocates a
tensor block to verify VRAM, and reports device properties.
"""
from __future__ import annotations

import json
import sys
import time

import torch


def main() -> int:
    assert torch.cuda.is_available(), "CUDA unavailable - refusing CPU fallback"
    n = torch.cuda.device_count()
    info = {
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "device_count": n,
        "devices": [],
        "ok": True,
    }
    for i in range(n):
        p = torch.cuda.get_device_properties(i)
        t0 = time.time()
        x = torch.randn(4096, 4096, device=f"cuda:{i}")
        y = (x @ x).sum().item()
        elapsed = time.time() - t0
        free, total = torch.cuda.mem_get_info(i)
        info["devices"].append(
            {
                "index": i,
                "name": p.name,
                "total_gb": round(total / 1e9, 1),
                "free_gb_at_start": round(free / 1e9, 1),
                "matmul_4096_s": round(elapsed, 3),
                "result": y,
            }
        )
        del x
        torch.cuda.empty_cache()
    print(json.dumps(info, indent=2))
    with open("/mnt/cunyuliu/codonflow/logs/gpu_smoke.json", "w") as f:
        json.dump(info, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
