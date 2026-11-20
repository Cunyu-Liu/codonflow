# A8-RK27 英文工作稿 closeout

## 交付边界

- 在 `paper/CodonFlow_preprint_A8.md` 追加第 6.38 节和 Table 10，记录固定 GFP 序列簇 OOD 的 measured 5′ MFE 增量。
- 追加 12 条 RK27 证据行；去除新节和这些证据行后，逐字节恢复原 RK26 稿件，既有章节、表格、引用与状态声明未改。
- 原稿 SHA256：`91e8bf226225d6d621617128618012b9333086646af9cd315b34be156f130f9a`。
- 新稿 SHA256：`1a4f84e16179d6ef7d4d7d59dd1f21f7d5313635e6e3d27f31ec6f7e2149bc5c`。
- 单节与 Markdown final SHA256：`4bac16de3b0bf16164940a522de619d1a3a1d6cbb3b41b19c00786ef49eb88a4`。

## 写作与独立验收

- 英文单节 workflow：`mode=draft`、`task_scope=section`、`needs_citation=no`、`output_target=markdown_only`。
- `prepare=pass`；`write=pass`，519 词，450–850 词范围内；三态脚本返回 `PASS`。
- 初次 write 因复制后的脚本缺少共享模块搜索路径而报 `ModuleNotFoundError: revision_guard`；补充 `PYTHONPATH` 后通过。初始失败日志保留，未修改技能源码。
- `make deliver` 已生成 Markdown final，但技能自带 shell 的 `finish_with_status` 调用失败；失败日志保留，随后直接运行三态脚本得到 `PASS`。该结果只证明单节 Markdown 工作流，不证明整篇可提交。
- 更新报告 SHA256：`5b5f5c09e9cf92dc3d5e0e9fe47b6c4d73d22b6edbfaa5713c7cea521bb7ed96`。
- 写作状态 SHA256：`03f3d50a3438b29b803777f6e15d837ec97450a22720e0d5619968e861b566d9`。
- 独立验收 83/83 PASS：四个 primary endpoint、绝对 OOD 数值、样本链、否定边界、12 条证据行和旧文保留均通过。
- 验收报告 SHA256：`ff35333fcc2250d2cdc28d1e342d45025db36ec39cde58c11f0d8ff5eae63e6d`。
- 英文稿提交并推送：`7b15f98533c053c2e987e648bcf000176ec3d9f6`。
- post-push 复验 83/83 PASS，报告与 Git 内验收报告字节一致：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk27/kudla_sequence_cluster_ood_v1/manuscript/rk27_manuscript_verification_postpush_v1.json`。

## 与科学和 PPT 证据的绑定

- 科学提交 `8a62836bb73b34bcae529bae6a21f6e3eefc85d1`：独立复算 47/47 PASS。
- 科学结论为 `FIXED_PROTEIN_SEQUENCE_CLUSTER_OOD_MFE_INCREMENT_SUPPORTED_RETROSPECTIVELY`。
- 科学 closeout 提交 `95257f290062d0f7d1ad2ab7bab21eef0b485437`：97/97 PASS。
- PPT 证据提交 `f827a549e988698448d5601f3fd869050633215e`：在线回读 57/57 PASS，证据绑定 21/21 PASS。
- 在线研究主稿第 119 页为 `pZy`，revision 82；英文工作稿与 PPT 均绑定同一科学结果 SHA256 `b601db3b0a5bec6b228492846f0058a0d959439c0eeebada05b749daa366ed5e`。
- RK27 仅支持回顾性固定 GFP 序列簇 OOD 的 measured-MFE 增量；不是独立 untouched 或 protein OOD 确认，不测量 velocity、decay 或完整空间耦合，不证明 CodonFlow-RK superiority。
- RK-G1 仍为 false，昂贵生成训练未授权；functional untouched 未评价。
- 整篇英文稿仍是 non-submittable working manuscript；Fig.1–7、完整主张—证据矩阵、最终强 baseline 主表和全局复现仍未闭合。
