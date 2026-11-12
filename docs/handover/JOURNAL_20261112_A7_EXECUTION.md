
## 9. px1 在线核验与 synonymous 修复合并

- 用户提供新 px1 凭据后 SSH 恢复。远端共享副本完整回归确认为 **131 passed, 1 skipped**。
- px1 `torch 2.14.1+cu132` 可导入，但 `torch.cuda.is_available()=False`、`device_count=0`；`nvidia-smi` 输出为空，CUDA assert 退出码 1。证据保存于 `07_a7_data/gpu_px1_20261112_{nvidia-smi,cuda-check}.txt`，未启动任何训练。
- 通过 Git bundle 找回共享提交 `1bdc4061`，合并至 GitHub 主线为 `3022f11`；只保留代码、3 项 synonymous 契约测试，历史 journal 冲突采用当前 A7 版本。合并后本地完整回归 **135 passed, 1 skipped**，已标准 push。
- 新增 `a7_verify_frozen_assets.py` 与 3 项契约测试。px1 实际验收 confirmation24/RSCU/calibration24 全部通过；报告 `07_a7_data/frozen_asset_verification_20261112.json`，SHA256=`fe45f06697f08eb47dbbddd5bee84062dbe4bd0ca9be8b33fa53606ca7f15879`。
- 六个 D4/D5 train/val/test 全量 CPU 数据审计已并行启动；完成前不得勾选全量分布审计或 G0。
