#!/usr/bin/env python3
"""Append RK37 registry/tasks and create its evidence-bound handover."""
from __future__ import annotations
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUD = ROOT / "audits/20261122/RK37"

def load(name):
    return json.loads((AUD / name).read_text())

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def git_head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()

r = load("rk37_translation_pivot_result_v1.json")
ind = load("rk37_translation_pivot_independent_v1.json")
clean = load("rk37_translation_pivot_clean_result_v1.json")
clean_cmp = load("rk37_clean_reproduction_comparison_v1.json")
close = load("rk37_science_closeout_v2.json")
ma = load("rk37_manuscript_audit_v1.json")
mi = load("rk37_manuscript_integration_v1.json")
pre = load("ppt_v1/rk37_ppt_prewrite_audit_v1.json")
post = load("ppt_v1/rk37_ppt_postwrite_audit_v1.json")
assert r["status"] == "PASS_RK37_PRODUCTION_PENDING_INDEPENDENT"
assert r["scientific_decision"] == "CROSS_STUDY_TRANSLATION_TASK_UNRESOLVED_COMPONENT_DIAGNOSIS_REQUIRED"
assert ind["status"] == "PASS_RK37_INDEPENDENT" and ind["checks_passed"] == ind["checks_total"] == 771
assert clean_cmp["status"] == "PASS_RK37_CLEAN_REPRODUCTION" and clean_cmp["checks_passed"] == clean_cmp["checks_total"] == 877
assert close["status"] == "PASS_RK37_SCIENCE_CLOSEOUT" and close["checks_passed"] == close["checks_total"] == 90
assert ma["status"] == "PASS_RK37_MANUSCRIPT_AUDIT" and ma["checks_passed"] == ma["checks_total"] == 16
assert pre["status"] == "PASS" and pre["checks_passed"] == pre["checks_total"] == 61
assert post["status"] == "PASS" and post["checks_passed"] == post["checks_total"] == 54
assert not any(x["gate_pass"] for x in r["primary_endpoints"])
assert r["frozen_git_commit"] == "5786ffc0ae43eab5c74d4ac2aff98eedce2ca0f9"
assert git_head() == "192f7b40" or git_head().startswith("192f7b40")

m, c = r["primary_endpoints"]
protocol = json.loads((ROOT / "configs/a8_rk37_translation_pivot_protocol_v1.json").read_text())
source = dict(r["source_identity"], matrix_sha256=protocol["studies"]["source_matrix"]["sha256"])
target = dict(r["target_identity"], matrix_sha256=protocol["studies"]["target_matrix"]["sha256"])
target_metrics = r["source_reports"][0]["target_evaluation"]["target_metrics"]
ppt_ids = ",".join(x["slide_id"] for x in post["rk37_pages"])
registry_path = ROOT / "experiments/REGISTRY.md"
tasks_path = ROOT / "tasks.md"
handoff_path = ROOT / "docs/handover/HANDOFF_A8_RK37_20261122.md"
report_path = AUD / "rk37_documentation_closeout_v1.json"
if report_path.exists():
    raise FileExistsError(report_path)
before = {str(p.relative_to(ROOT)): sha(p) for p in (registry_path, tasks_path)}

registry_line = (
    "| RK37 | 2026-11-22 | preregistered RiboMIMO Mohammad16-to-Subtelny14 cross-study local-sequence translation-occupancy diagnostic; dual confirmatory endpoints reverse, task unresolved | "
    "`a8_rk37_run_translation_pivot.py`; independent `a8_rk37_verify_translation_pivot.py`; `a8_rk37_compare_clean.py`; `a8_rk37_science_closeout.py`; manuscript and PPT builders/auditors | "
    f"CPU single thread; `/home/codonflow-clean-env-v1`; {r['fit_accounting']['actual_unique_fits']} unique Ridge fits; production/independent/clean {r['execution']['wall_seconds']:.6f}/{ind['wall_seconds']:.6f}/{clean['execution']['wall_seconds']:.6f} s; no GPU, functional untouched or generator training | "
    f"source {source['raw_records']} raw/{source['eligible_records']} eligible, SHA `{source['matrix_sha256']}`; target {target['raw_records']} raw/{target['eligible_records']} eligible, SHA `{target['matrix_sha256']}`; exact CDS overlap=0; production `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk37/translation_pivot_v1/`; clean `/home/codonflow-rk37-clean-493a0a70`; PPT `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk37/ppt_v1/` | "
    "freeze `5786ffc0`; independent `b8cf49c7`; clean comparator `493a0a70`; closeout code `d16d5754`; science `066ee562`; clean/closeout `87a33bd4`; manuscript `f2108c0d`; PPT `192f7b40`; docs (this commit) | "
    "3 seeds x 4 families x 4 alphas=48 fits; all source fits before target outcome; local_centered_anchored versus constant TB-MSE and position_raw mean Pearson; 20,000 whole-transcript bootstrap + 20,000 sign-flip permutations; unified two-endpoint Holm; two sensitivity seeds must be positive | "
    "contract tests 11/11; independent 771/771; clean comparison 877/877 with 111 NPZ arrays exact and 3 CSV byte-identical; science closeout 90/90 after retained schema failures; project 466 passed/1 skipped; manuscript 16/16; PPT prewrite61/61/postwrite54/54 | "
    f"constant-local TB-MSE improvement {m['effect']:.12f} CI[{m['ci95_low']:.12f},{m['ci95_high']:.12f}], Holm={m['holm_pvalue']}; local-position Pearson improvement {c['effect']:.12f} CI[{c['ci95_low']:.12f},{c['ci95_high']:.12f}], Holm={c['holm_pvalue']}; both gates false and all sensitivity effects negative; decision `{r['scientific_decision']}`; local centered TB-MSE={target_metrics['local_centered_anchored']['transcript_balanced_mse']:.10f}, Pearson={target_metrics['local_centered_anchored']['mean_transcript_pearson']:.10f}; paper §6.48 + Tables28-29, 2039 lines, SHA `{ma['manuscript_sha256']}`; PPT174-180 ids `{ppt_ids}`, revision152, prior173 pages unchanged; normalized ribosome-occupancy proxy only, not translation speed, untouched confirmation, protein/homology OOD, SOTA or generator claim; RK-G1=false | "
    "done_rk37_dual_negative_cross_study_task_unresolved_independent_clean_manuscript_ppt_closeout_pass |\n"
)

tasks_block = f"""
## 2026-11-22：RK37 跨研究翻译占据局部序列诊断（双终点显著反向，任务未解决）

- [x] **预注册与生产**：冻结 Mohammad16→Subtelny14 的 study OOD 协议；source {source['raw_records']} raw/{source['eligible_records']} eligible，target {target['raw_records']} raw/{target['eligible_records']} eligible，exact CDS overlap=0。3 seeds×4 families×4 alphas=**48 次唯一 Ridge fits**全部在读取 target outcome 前完成；主候选 `local_centered_anchored`，部署锚定只用 source 均值。冻结提交 `5786ffc0`，生产 {r['execution']['wall_seconds']:.6f}s。
- [x] **双确认性终点均失败**：constant−local TB-MSE 改善 **{m['effect']:.12f}**，95%CI `[{m['ci95_low']:.12f},{m['ci95_high']:.12f}]`，Holm p=`{m['holm_pvalue']}`；local−position raw mean Pearson 改善 **{c['effect']:.12f}**，95%CI `[{c['ci95_low']:.12f},{c['ci95_high']:.12f}]`，Holm p=`{c['holm_pvalue']}`。两个 CI 全负、两个 sensitivity seeds 均同号为负；小 p 值表示稳定变差，绝不写成通过。
- [x] **组件诊断而非事后调参**：主种子 constant TB-MSE={target_metrics['constant']['transcript_balanced_mse']:.10f}；position raw={target_metrics['position_raw_unanchored']['transcript_balanced_mse']:.10f}、r={target_metrics['position_raw_unanchored']['mean_transcript_pearson']:.10f}；local centered={target_metrics['local_centered_anchored']['transcript_balanced_mse']:.10f}、r={target_metrics['local_centered_anchored']['mean_transcript_pearson']:.10f}；RiboMIMO raw/anchored TB-MSE={target_metrics['ribomimo_raw']['transcript_balanced_mse']:.10f}/{target_metrics['ribomimo_anchored']['transcript_balanced_mse']:.10f}。position centering 仅增约0.000488 Pearson，source anchoring 未挽救 local 或 RiboMIMO 误差；没有在同一 target 后选“最佳臂”包装确认。
- [x] **独立复核与 clean reproduction**：独立 COO→CSR 实现从原始矩阵重算48 fits、全部预测、系数与推断数组，**771/771 PASS**，最大数值差 `3.552713678800501e-15`；detached `/home/codonflow-rk37-clean-493a0a70` 重跑48 fits，比较 **877/877 PASS**，111个 NPZ arrays 精确一致、3个逐转录本 CSV 字节一致。提交 `b8cf49c7/493a0a70/066ee562/87a33bd4`。
- [x] **测试与科学 closeout**：全项目 **466 passed / 1 skipped / 0 failed / 5 subtests passed**；最终 `rk37_science_closeout_v2.json` **90/90 PASS**，推送后复验仍90/90。初版 `88/90 FAIL` 与三次 verifier schema KeyError 日志均保留；修正仅涉及证据读取和日志格式，不改科学代码或结果。
- [x] **英文稿 §6.48**：证据驱动生成 Tables 28–29，稿件 **2,039 行**，SHA `{ma['manuscript_sha256']}`；integration/audit **16/16 PASS**，含精确回滚、双表唯一、负 decision 和证据边界。隔离 `paper-write-en` workflow prepare/write/deliver/status 全 PASS；提交 `f2108c0d`。
- [x] **在线 PPT**：在173页/revision145后只追加 **174–180** 七页，ids `{ppt_ids}`，最终 **180页/revision152**；写前 **61/61 PASS**、写后 **54/54 PASS**，前173页 ID+语义 XML 未变，七页真实预览均逐页验收。提交 `192f7b40`；大型 XML/预览位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk37/ppt_v1/`。
- [ ] **科学任务仍未解决**：RK37 仅证明该局部线性翻译占据候选在此跨研究方向稳定反向，不支持 translation-speed、protein/homology OOD、untouched confirmation、SOTA 或生成器性能。下一项 RK38 先逐方法×任务×格盘点 GEMORNA/LD-scan/CAI-greedy 等真实运行证据，同时对翻译/功能未触碰队列做 label-free 盘点；核实前不预设主矩阵可闭合或新实验可执行，不得在同一 Subtelny14 target 继续调参后称为独立确认。
- [ ] **总项目开放边界**：完整 external actual-set SOTA、time-matched 七方法、共同 dense、多物种 VeloHARMO、真实 functional/protein OOD、独立 untouched 和前瞻 DBTL 仍未闭合；RK-G1=false、generator_training_authorized=false、functional untouched 未读、wet-lab 未执行。
"""

handoff = f"""# HANDOFF · A8-RK37 · 跨研究翻译占据局部序列诊断

日期：2026-11-22（UTC+8）
权威工作树：`/home/codonflow-a8-rk`，分支 `a8-rk`，remote `git@github.com:Cunyu-Liu/codonflow.git`
科学环境：`/home/codonflow-clean-env-v1/bin/python`；OPENBLAS/OMP/MKL/NUMEXPR 各1线程。

## 0. 结论先行

RK37 是 RK36 branch-2 转向后的第一项预注册跨研究翻译占据实验。主候选 `local_centered_anchored` 必须同时战胜 constant 的 TB-MSE 和 source-fitted position ridge 的 mean Pearson。**两个确认性终点均显著反向，科学任务未解决**。完成的是可复现负结果及报告闭环，不是运输、translation-speed、SOTA、生成器或 RK-G1 通过。

最终 decision：`{r['scientific_decision']}`。

## 1. 冻结协议与数据

- 协议：`configs/a8_rk37_translation_pivot_protocol_v1.json`；预注册：`audits/20261122/RK37/A8_RK37_PREREGISTRATION.md`。
- 冻结 commit：`5786ffc0ae43eab5c74d4ac2aff98eedce2ca0f9`。
- source Mohammad16：{source['raw_records']} raw / {source['eligible_records']} eligible；matrix SHA256 `{source['matrix_sha256']}`。
- target Subtelny14：{target['raw_records']} raw / {target['eligible_records']} eligible；matrix SHA256 `{target['matrix_sha256']}`。
- exact CDS overlap = {r["target_identity"]["exact_cds_overlap"]}；seeds=1234/2345/3456；alpha grid=[0.1,1,10,100]。
- position=86维，local=477维。centered target 在 source-train 转录本内去均值；部署锚定只使用 source 均值，不读取 target outcome。
- 48 次唯一 source fits 全部完成后才读取 target 结局。primary bootstrap=20,000、sign-flip permutation=20,000，统一双终点 Holm。

## 2. 双终点与种子敏感性

| 终点 | effect | 95% CI | Holm p | seed2345 | seed3456 | gate |
|---|---:|---:|---:|---:|---:|---|
| constant−local TB-MSE improvement | {m['effect']:.12f} | [{m['ci95_low']:.12f}, {m['ci95_high']:.12f}] | {m['holm_pvalue']} | {m['sensitivity_effects'][0]:.12f} | {m['sensitivity_effects'][1]:.12f} | false |
| local−position raw mean Pearson improvement | {c['effect']:.12f} | [{c['ci95_low']:.12f}, {c['ci95_high']:.12f}] | {c['holm_pvalue']} | {c['sensitivity_effects'][0]:.12f} | {c['sensitivity_effects'][1]:.12f} | false |

两个 CI 全负，两个 sensitivity seeds 均同号为负。很小的 p 值说明“变差”稳定，不能解释为科学通过。

## 3. 主种子八臂绝对表现与诊断

| Arm | TB-MSE | mean Pearson | mean Spearman |
|---|---:|---:|---:|
"""
for name in ["constant", "position_raw_unanchored", "position_raw_anchored", "position_centered_anchored", "local_raw_anchored", "local_centered_anchored", "ribomimo_raw", "ribomimo_anchored"]:
    a = target_metrics[name]
    sp = "NA" if a["mean_transcript_spearman"] is None else f"{a['mean_transcript_spearman']:.10f}"
    handoff += f"| {name} | {a['transcript_balanced_mse']:.10f} | {a['mean_transcript_pearson']:.10f} | {sp} |\n"
handoff += f"""

主种子 local alpha=0.1；两个 sensitivity seeds local alpha=100；三个 seeds position alpha=100。position centering 的 Pearson 增量仅约0.000488，仍输给 constant 的 MSE；local 与 RiboMIMO 的 source anchoring 均未挽救 TB-MSE。辅助臂只用于组件诊断，没有从同一 target 后选“最佳臂”包装成新结果。

## 4. 独立、clean、测试和 closeout

| 阶段 | 验收 | 证据 |
|---|---|---|
| contract tests | 11/11 PASS；两项初始测试夹具失败保留 | `rk37_contract_tests_v1.log` / `rk37_contract_tests_failure_v1.log` |
| 独立复核 | 771/771 PASS；最大数值差 3.552713678800501e-15 | `rk37_translation_pivot_independent_v1.json` |
| clean checkout | 48 fits；{clean['execution']['wall_seconds']:.6f}s | `/home/codonflow-rk37-clean-493a0a70` |
| clean comparison | 877/877 PASS；111 NPZ arrays exact；3 CSV byte-identical | `rk37_clean_reproduction_comparison_v1.json` |
| 全项目测试 | 466 passed / 1 skipped / 0 failed / 5 subtests passed | `rk37_project_tests_v1.log` |
| 科学 closeout | v2 90/90 PASS；v1 88/90 FAIL及三次schema日志保留 | `rk37_science_closeout_v2.json` |

独立复核器未导入生产模块，使用独立 COO→CSR 特征构造，从原始矩阵重算48 fits、验证指标、target预测、系数和推断数组。三次 verifier schema 错误只修证据读取键与日志判定，不改科学公式或结果。

## 5. 稿件与在线 PPT

- 稿件：`paper/CodonFlow_preprint_A8.md`，§6.48 + Tables 28–29，2,039行；SHA256 `{ma['manuscript_sha256']}`；integration/audit 16/16 PASS，原稿 SHA `{mi['before_sha256']}` 精确回滚。提交 `f2108c0d`。
- 隔离英文写作 workflow：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk37/manuscript_v1/`；prepare/write/deliver/status 全 PASS，正文947词。
- 在线 deck：`https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g`，174–180页，ids `{ppt_ids}`，180页/revision152。
- PPT 写前61/61、写后54/54；前173页 ID+语义 XML 未改变。七页预览均逐页查看，无溢出、遮挡或截断。提交 `192f7b40`。
- 大型 PPT 工作目录：`/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk37/ppt_v1/`。

## 6. 关键产物与复现

生产结果 SHA256 `{sha(AUD/'rk37_translation_pivot_result_v1.json')}`；独立报告 SHA256 `{sha(AUD/'rk37_translation_pivot_independent_v1.json')}`；clean comparison SHA256 `{sha(AUD/'rk37_clean_reproduction_comparison_v1.json')}`；closeout SHA256 `{sha(AUD/'rk37_science_closeout_v2.json')}`。

大型资产：
- `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk37/translation_pivot_v1/production/`
- `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk37/translation_pivot_v1/independent/`
- `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk37/translation_pivot_v1/clean_reproduction_493a0a70/`

生产脚本要求新 output-dir 和新 report，拒绝覆盖既有证据：

```bash
cd /home/codonflow-a8-rk
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
/home/codonflow-clean-env-v1/bin/python scripts/a8_rk37_run_translation_pivot.py \
  --protocol configs/a8_rk37_translation_pivot_protocol_v1.json \
  --output-dir <new_empty_output_dir> --report <new_result.json>
/home/codonflow-clean-env-v1/bin/python scripts/a8_rk37_science_closeout.py --report <new_closeout.json>
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
/home/codonflow-clean-env-v1/bin/python scripts/run_tests_json.py tests/ <new_tests.json>
```

clean reproduction 使用 detached commit `493a0a70`，其 comparator 为 `scripts/a8_rk37_compare_clean.py`。所有既有 result/report 均不可覆盖，复现时换新文件名。

## 7. 提交链

`5786ffc0` freeze → `b8cf49c7` independent → `493a0a70` clean comparator → `d16d5754` closeout code → `066ee562` production+independent → `87a33bd4` clean+closeout → `f2108c0d` manuscript → `192f7b40` PPT → 本交接提交。

## 8. 下一步与不可声称事项

RK38 先做两类 label-free inventory，再依据真实证据选择任务，不预设哪个方向一定可执行：① 全项目未闭合项与已有 baseline 的逐方法×任务×格实际输出、repeated-call 位置、运行状态、时间和缺失原因，核实 GEMORNA/LD-scan/CAI-greedy 等证据能否支持 external actual-set SOTA 主矩阵；② 未触碰翻译/功能队列的研究/宿主、完整构建、结局类型、样本量、exact CDS 重叠和既有读取状态。只有盘点证明覆盖与独立性强条件成立，才冻结相应主矩阵或新实验；否则如实记录不可计算格和缺失维度，不在 Subtelny14 上反复调参后宣称确认。

- normalized ribosome-occupancy proxy ≠ 物理翻译速度。
- study OOD ≠ protein/homology OOD；Subtelny14 已被 RK05/RK37 观察，不是 untouched。
- 本结果不支持 SOTA、生成器性能、因果机制、wet-lab 或前瞻 DBTL。
- functional untouched 未读取；昂贵生成训练未授权；RK-G1=false。
- 完整 external SOTA、time-matched、七方法共同 dense、多物种 VeloHARMO、真实 functional/protein OOD、独立 untouched 和前瞻 DBTL 仍开放。
"""

if "| RK37 |" not in registry_path.read_text():
    with registry_path.open("a") as f:
        f.write(registry_line)
if "## 2026-11-22：RK37 跨研究翻译占据局部序列诊断" not in tasks_path.read_text():
    with tasks_path.open("a") as f:
        f.write(tasks_block)
if handoff_path.exists():
    raise FileExistsError(handoff_path)
handoff_path.write_text(handoff)
after = {str(p.relative_to(ROOT)): sha(p) for p in (registry_path, tasks_path, handoff_path)}
checks = {
    "registry_single_rk37": registry_path.read_text().count("| RK37 |") == 1,
    "tasks_single_rk37": tasks_path.read_text().count("## 2026-11-22：RK37 跨研究翻译占据局部序列诊断") == 1,
    "handoff_decision": r["scientific_decision"] in handoff_path.read_text(),
    "handoff_both_negative": f"{m['effect']:.12f}" in handoff and f"{c['effect']:.12f}" in handoff,
    "handoff_untouched_boundary": "functional untouched 未读取" in handoff_path.read_text(),
}
report = {
    "schema_version": "a8_rk37_documentation_closeout_v1",
    "status": "PASS_RK37_DOCUMENTATION_CLOSEOUT" if all(checks.values()) else "FAIL_RK37_DOCUMENTATION_CLOSEOUT",
    "head_before_docs_commit": git_head(),
    "before_sha256": before,
    "after_sha256": after,
    "handoff_sha256": sha(handoff_path),
    "checks": checks,
    "summary": {"pass": sum(checks.values()), "total": len(checks), "failures": [k for k,v in checks.items() if not v]},
}
report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
print(json.dumps(report, indent=2))
if not all(checks.values()):
    raise SystemExit(1)
