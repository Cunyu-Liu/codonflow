import importlib.util
import os
import unittest
from pathlib import Path

ROOT = Path(os.environ.get("CODONFLOW_ROOT", Path(__file__).resolve().parents[1]))
SCRIPT = Path(os.environ.get("G0_VERIFIER_PATH", ROOT / "scripts/a8_g0_verify_closeout_documents.py"))
SPEC = importlib.util.spec_from_file_location("g0_docs_verifier", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def valid_documents():
    common = "\n".join([
        MODULE.COMMITS["science"], MODULE.COMMITS["paper"], MODULE.COMMITS["ppt"], MODULE.PAPER_SHA,
        "PASS_BOUNDED_DATA_BASELINE_EVALUATION_READY", "pZg", "RK-G1=false", "time-matched",
        "non-submittable", "106 pages revision 68", "generator_training_authorized=false",
    ])
    task_extra = "\n".join([
        "## 2026-11-20：RK-G0 bounded readiness、统一成本与论文/PPT closeout",
        "[x] RK03-REMAINING（bounded source-feasibility）",
        "KeyError: lineardesign_unique_sequences", "10 个失效指针", "179/179", "357/357",
        "9/9", "6/6", "127/127", "47/47", "10/10", "max numeric delta=0",
        "external actual-set dense 完整矩阵", "full UTR–CDS remap", "RNARL 官方模型",
        "VeloHARMO 五物种", "Kudla 逐构建序列—表达表", "functional-untouched", "wet-lab/前瞻 DBTL",
        "完整项目 `pytest tests/`", "不得启动昂贵生成训练",
    ])
    handoff_extra = "\n".join([
        "## 35. RK-G0 bounded readiness、统一成本、v30 与 PPT106 closeout",
        *[f"### 35.{i}" for i in range(1, 7)],
        "5459.871640930884", "6001.057458210271", "949.7424744511954", "20,939–21,078",
        "260,754 raw rows", "128,289 clean QC pairs", "CDGB source identity unresolved",
        "COformer/CHARMING=NOT_RUN", "Kudla 逐构建序列—表达表仍不可用",
        "FEASIBILITY_CLOSED_NOT_FULL_REMAP", "960×540", "不重复追加 `pZg`",
        "不重复执行 RK06/MAGE/G0 updater",
    ])
    readme_extra = "\n".join([
        "## A8-RK：RK-G0 bounded readiness 与统一成本 closeout",
        "a8_g0_verify_closeout.py", "a8_g0_verify_paper_closeout.py", "a8_g0_verify_ppt_closeout.py",
        "a8_g0_finalize_ppt_closeout.py", "a8_g0_verify_closeout_documents.py",
        "g0_recheck_independent_v1.json", "不会追加在线页面或重跑生成器",
        "null 表示未测量或不可归因，不是 0", "不同硬件、任务和评价范围不求伪总和",
        "128,289 clean QC pairs", "完整项目 `pytest tests/`", "Kudla 逐构建表",
    ])
    registry_rows = []
    for row_id in [
        "CF-A8-RK-G0-COST-READINESS", "CF-A8-RK18-WORKING-MANUSCRIPT-V30",
        "CF-A8-RK-G0-PPT-CLOSEOUT",
    ]:
        registry_rows.append("| " + row_id + " |" + " x |" * 10)
    registry_extra = "\n".join(registry_rows + [
        "179/179", "357/357", "127/127", "47/47", "10/10", "max delta=0",
        "done_bounded_g0_not_complete_sota_not_rk_g1", "old 105 pages semantically unchanged",
        "generator unauthorized", "00f64ea5719ca179740f2ab6b4ffd1fefa305feb4a7b173955af14b0035fed0e",
    ])
    return {
        "readme": common + "\n" + readme_extra,
        "tasks_root": common + "\n" + task_extra,
        "tasks_handoff": common + "\n" + task_extra,
        "handoff": common + "\n" + handoff_extra,
        "registry": common + "\n" + registry_extra,
    }


class G0DocumentationChecksTest(unittest.TestCase):
    def assert_failure(self, mutate):
        docs = valid_documents()
        mutate(docs)
        self.assertTrue(any(not item["pass"] for item in MODULE.documentation_checks(docs)))

    def test_valid_documents_pass(self):
        checks = MODULE.documentation_checks(valid_documents())
        self.assertTrue(all(item["pass"] for item in checks), [x for x in checks if not x["pass"]])

    def test_missing_commit_fails_every_document(self):
        for name in valid_documents():
            with self.subTest(name=name):
                self.assert_failure(lambda docs, n=name: docs.__setitem__(
                    n, docs[n].replace(MODULE.COMMITS["science"], "missing")))

    def test_rk03_cannot_be_reopened_silently(self):
        self.assert_failure(lambda docs: docs.__setitem__(
            "tasks_root", docs["tasks_root"].replace("[x] RK03-REMAINING", "[ ] RK03-REMAINING")))

    def test_registry_row_cannot_be_removed(self):
        self.assert_failure(lambda docs: docs.__setitem__(
            "registry", "\n".join(x for x in docs["registry"].splitlines()
                                  if "CF-A8-RK-G0-PPT-CLOSEOUT" not in x)))

    def test_handoff_section_cannot_be_removed(self):
        self.assert_failure(lambda docs: docs.__setitem__(
            "handoff", docs["handoff"].replace(
                "## 35. RK-G0 bounded readiness、统一成本、v30 与 PPT106 closeout", "")))

    def test_readonly_reproduction_cannot_be_removed(self):
        self.assert_failure(lambda docs: docs.__setitem__(
            "readme", docs["readme"].replace("a8_g0_verify_closeout_documents.py", "missing")))

    def test_slide_id_tamper_fails(self):
        self.assert_failure(lambda docs: docs.__setitem__(
            "handoff", docs["handoff"].replace("pZg", "pZp")))

    def test_open_scope_cannot_be_removed(self):
        self.assert_failure(lambda docs: docs.__setitem__(
            "tasks_handoff", docs["tasks_handoff"].replace("Kudla 逐构建序列—表达表", "Kudla complete")))


if __name__ == "__main__":
    unittest.main()
