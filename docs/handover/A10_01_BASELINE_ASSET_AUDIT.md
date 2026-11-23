# A10-01 官方 baseline 资产审计台账

> 记录日期：2026-11-23。范围仅限下列固定官方资产及已有运行证据；本页不是性能表，也不代表官方配置、训练数据、预训练污染、调参预算或统一成本审计已经完成。所有方法均不得据此写成 SOTA 或完整公平比较。

## 资产台账

统一状态 `asset_verified_not_A10_comparable_yet` 仅表示官方资产来源已经核实，但尚未建立 A10 所需的同输入、同反馈、同 scorer、同预算和同硬件可比结果。真实运行状态独立列出，不由资产存在推断可运行性。

| 方法 | 固定官方资产 | 许可、依赖与资产边界 | 输入 / 输出或适用边界 | A10 状态 | 真实运行状态 |
|---|---|---|---|---|---|
| CodonTransformer | `Adibvafa/CodonTransformer@4a447b01dab860feb81b647ff1ff88ad598517f4`；[Zenodo 12509224](https://zenodo.org/records/12509224)；HF 模型 revision `9744dcc920d813066391fc828d7a590207f148e8` | Apache-2.0 | 输入蛋白序列和宿主，输出 DNA 序列 | `asset_verified_not_A10_comparable_yet` | 固定权重真实 RTX 5090 CUDA smoke v7 完成：1 条 deterministic＋2 条 seed0 随机输出均 333 nt、110 aa 翻译一致；独立复核通过。总 wall-clock 13.4349 s，推理 0.5099 s，峰值显存 401,985,024 bytes。仅为执行 smoke，不是科学性能或统一排名。 |
| EnsembleDesign | `LinearFold/EnsembleDesign@cd9324f9574a754063d421e76670bc9fd7555324` | C++ 实现；无需预训练权重 | 输入蛋白 FASTA，输出同义 RNA 与 ensemble free energy | `asset_verified_not_A10_comparable_yet` | 官方 3 示例 quick run 已完成，6/6 runs，三条 EFE/序列与 README 预期一致；首次因 `/usr/bin/env python` 缺失失败的日志保留，修正 PATH 后成功。仅为执行 smoke，不是统一成本或科学比较。 |
| ID3 | `Li-Hongmin/ID3@ed23037e5a74ca10953954c425ac736fb89578a8` | 依赖 DeepRaccess；GitHub 标为 CC BY-NC-SA，而 Zenodo 元数据标为 CC-BY，许可不一致，未解决前不得按单一开放许可处理 | 依赖与许可边界尚未闭合，不能仅凭 quick test 进入统一设计主表 | `asset_verified_not_A10_comparable_yet` | 远端已有 quick test，硬件为 **CPU**。两条 CPC STE 轨迹因上游 `beta` 未传递而不可用；`112/116` 是 **bounded 验证计数而非通过**；最终序列分数可独立复算。上述证据均不是 A10 公平比较。 |
| RNARL | `xlab-BioAI/RNARL@88428e5d24fb2a16c29cc4dfbbfef51bd990a3d5`；[Zenodo 15486992](https://zenodo.org/records/15486992) | MIT；官方快照缺独立推理入口及 actor/reward 权重 | 缺少完整官方推理链，不能用自行补接口或替代权重冒充官方结果 | `asset_verified_not_A10_comparable_yet` | 本次未运行；官方独立推理仍受阻，无 A10 端到端结果或成本记录。 |
| COformer | `PNUMLB/COformer@b943a1b83e6476d19001ef8459db8181e055fc90` | 固定快照无 LICENSE、无已训练权重 | 权重缺失且再分发权限未明，训练或替代权重均不能直接视为官方模型复现 | `asset_verified_not_A10_comparable_yet` | 本次未训练或运行；无官方权重推理、A10 端到端结果或成本记录。 |
| VeloHARMO | `BianBian2021/VeloHARMO@38b48079856aeb9d33a1b10844d77aa8f6640032` | 固定快照无 LICENSE；仅有 E. coli / yeast 版权重 | 需要 SS 特征；宿主覆盖仅限现有权重范围，不得外推为任意宿主可用 | `asset_verified_not_A10_comparable_yet` | 本次未运行；SS 特征、宿主适用范围和统一输入尚未闭合，无 A10 端到端结果或成本记录。 |

## 运行证据、成本与结论边界

- ID3 的远端 quick test 只证明特定 CPU 环境下的有限工程连通性。无效 CPC STE 轨迹不得进入 anytime、Pareto、HV 或 time-matched 指标；`112/116` 不得改写为全部通过；最终序列分数的独立复算只核验该分数，不补全轨迹，也不构成科学性能结论。
- 本次本地工作仅新增文档和执行静态校验：外部 baseline 训练、推理及 GPU 使用均为 0；文档校验 wall-clock 未测量。历史 ID3 quick test 除 CPU 外，wall-clock、CPU 时、内存和完整命令成本均为未测量（`null`），不得补零或估算。
- 六项方法的 A10 训练、forward、生成、scorer 和端到端成本均未建立统一测量，记为 `null`。后续必须保存原始轨迹和成本，不得用资产下载、测试计数或 smoke 替代实际 benchmark。
- 本次未读取 `untouched24`、MAGE functional untouched 或其派生数据，未形成任何真实功能、泛化、设计优势或生物学结论。

## 本地复现记录

- 基线：`main@5f9e5a560b118568d435fa68a72ef9253d4252c5`。工作树在任务开始前已有 tracked 修改和 untracked 文件，全部保留；本文件为新增文档，上述 commit 不表示本文件已经入库。
- 本地环境：macOS，`Darwin 25.2.0 arm64`，`Python 3.13.5`；校验只使用 Python 标准库和 Git。远端运行环境仅确认 ID3 quick test 使用 CPU，其余环境字段未核实。
- 输出保护：本文件仅以新路径创建，未覆盖既有文件。后续自动生成必须使用独占创建模式（如 Python `Path.open("x", encoding="utf-8")`），路径已存在即停止；历史 artifact 不得覆盖。
- 以下命令均从仓库根目录执行，使用相对路径，不依赖本机绝对目录：

```bash
git rev-parse HEAD
python --version
uname -srm
python - <<'PY'
from pathlib import Path

p = Path("docs/handover/A10_01_BASELINE_ASSET_AUDIT.md")
s = p.read_text(encoding="utf-8")
assets = {
    "CodonTransformer": "4a447b01dab860feb81b647ff1ff88ad598517f4",
    "EnsembleDesign": "cd9324f9574a754063d421e76670bc9fd7555324",
    "ID3": "ed23037e5a74ca10953954c425ac736fb89578a8",
    "RNARL": "88428e5d24fb2a16c29cc4dfbbfef51bd990a3d5",
    "COformer": "b943a1b83e6476d19001ef8459db8181e055fc90",
    "VeloHARMO": "38b48079856aeb9d33a1b10844d77aa8f6640032",
}
for name, commit in assets.items():
    assert name in s and commit in s
assert sum(line.startswith("| ") and "| `asset_verified_not_A10_comparable_yet` |" in line for line in s.splitlines()) == 6
for evidence in ("真实运行状态", "CPU", "CPC STE", "beta", "112/116", "bounded 验证计数而非通过", "最终序列分数可独立复算"):
    assert evidence in s
assert all(not line.endswith((" ", "\t")) for line in s.splitlines())
print("A10-01 asset ledger: targeted checks passed")
PY
git diff --check
shasum -a 256 docs/handover/A10_01_BASELINE_ASSET_AUDIT.md
```
