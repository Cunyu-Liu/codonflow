#!/usr/bin/env python3
"""Mutation tests proving the pure-RCS documentation verifier can fail."""
from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pure_docs", Path(__file__).with_name("a8_rk03_verify_pure_external_documents.py"))
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DocumentationMutationTests(unittest.TestCase):
    def make_root(self, temporary: Path) -> Path:
        for directory in ("audits", "paper", "configs"):
            (temporary / directory).symlink_to(ROOT / directory, target_is_directory=True)
        for rel in MODULE.DOC_PATHS.values():
            destination = temporary / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, destination)
        return temporary

    def assert_mutation_fails(self, document: str, old: str, new: str, replace_all: bool = False) -> None:
        with tempfile.TemporaryDirectory(prefix="pure_rcs_doc_mutation_") as tmp:
            root = self.make_root(Path(tmp))
            path = root / MODULE.DOC_PATHS[document]
            text = path.read_text(encoding="utf-8")
            marker = MODULE.NEW_MARKERS[document]
            prefix, section = text.split(marker, 1)
            self.assertIn(old, section)
            section = section.replace(old, new) if replace_all else section.replace(old, new, 1)
            path.write_text(prefix + marker + section, encoding="utf-8")
            report = MODULE.run_verification(root)
            self.assertFalse(report["overall_pass"], (document, old))
            self.assertGreater(report["checks_failed"], 0)

    def test_unmodified_records_pass(self) -> None:
        report = MODULE.run_verification(ROOT)
        self.assertTrue(report["overall_pass"], report["failed_checks"])

    def test_reject_pure_spearman_sign_flip(self) -> None:
        self.assert_mutation_fails("readme", "-0.13201530863899236", "0.13201530863899236")

    def test_reject_wrong_slide_id(self) -> None:
        self.assert_mutation_fails("root_tasks", "pZS", "pZT", replace_all=True)

    def test_reject_replacement_claim_flip(self) -> None:
        self.assert_mutation_fails("handover_tasks", "replacement=false", "replacement=true")

    def test_reject_old_full_intrinsic_effect_change(self) -> None:
        self.assert_mutation_fails("handoff", "0.022899062089363098", "0.122899062089363098")

    def test_reject_registry_gate_status_flip(self) -> None:
        self.assert_mutation_fails("registry", "done_pure_rcs_replacement_false_mechanism_and_rk_g1_false_test_generator_unauthorized", "done_pure_rcs_replacement_true_mechanism_and_rk_g1_true_test_generator_authorized")

    def test_reject_test_exclusion_removal(self) -> None:
        self.assert_mutation_fails("handoff", "33 个 test constructs 不参与特征选择、拟合或评价", "33 个 test constructs 参与特征选择、拟合或评价")

    def test_reject_revision_change(self) -> None:
        self.assert_mutation_fails("readme", "revision 70", "revision 71", replace_all=True)

    def test_reject_holm_claim_change(self) -> None:
        self.assert_mutation_fails("root_tasks", "Holm p=1", "Holm p=0", replace_all=True)

    def test_reject_missing_science_commit(self) -> None:
        self.assert_mutation_fails("registry", "b95e1244537a23c95cdda986cb60e343cfd7e4da", "0" * 40, replace_all=True)

    def test_reject_reproduction_overclaim(self) -> None:
        self.assert_mutation_fails("handover_tasks", "未运行完整项目 `pytest tests/`", "已运行完整项目 `pytest tests/`", replace_all=True)

    def test_reject_idempotency_key_change(self) -> None:
        self.assert_mutation_fails("handoff", "codonflow-pure-rcs-20261120-v01", "codonflow-pure-rcs-20261120-v02")


if __name__ == "__main__":
    unittest.main(verbosity=2)
