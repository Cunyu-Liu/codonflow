#!/usr/bin/env python3
import unittest
import xml.etree.ElementTree as ET

from scripts.a8_rk19_make_reproduction_ppt import (
    NS, build_slide, outcome, semantic_signature, visible_text,
)


class ReproductionPPTTests(unittest.TestCase):
    def report(self, status="PASS_CLEAN_CPU_SUITE", checks=24):
        return {
            "status": status,
            "overall_pass": True,
            "check_count": checks,
            "passed_count": checks,
            "environment_prefix": "/home/codonflow-rk19-clean-explicit-v2",
            "python_executable": "/home/codonflow-rk19-clean-explicit-v2/bin/python",
            "external_pythonpath": False,
            "package_versions": {
                "torch": "2.11.0+cu128", "numpy": "2.2.6", "scipy": "1.15.3",
                "pandas": "2.2.2", "scikit-learn": "1.7.2", "pytest": "9.1.1",
                "pymoo": "0.6.2", "rapidfuzz": "3.14.5",
            },
            "tests": {"collected": 331, "passed": 330, "skipped": 1, "failed": 0, "errors": 0},
        }

    def test_outcome_preserves_zero_failures_and_errors(self):
        self.assertEqual(outcome(self.report()), "330 passed · 1 skipped · 0 failed · 0 errors")

    def test_slide_has_no_ids_five_notes_and_negative_boundaries(self):
        existing = self.report(status="PASS_FULL_CPU_SUITE_EXISTING_ENV", checks=15)
        clean = self.report()
        slide = build_slide(existing, clean, clean)
        self.assertTrue(all("id" not in e.attrib for e in slide.iter()))
        note = slide.find(f"{{{NS}}}note")
        self.assertEqual(len(note.findall(f".//{{{NS}}}p")), 5)
        visible = visible_text(slide)
        self.assertIn("Full experimental regeneration = false", visible)
        self.assertIn("RK-G1 = false", visible)
        self.assertIn("JUnit header 336 vs 331 testcase elements", visible)
        self.assertIn("24/24 · 15.91 s", visible)

    def test_semantic_signature_ignores_whitespace_tail_only(self):
        left = ET.fromstring("<slide><data><p>same</p></data></slide>")
        right = ET.fromstring("<slide><data><p>same</p></data>  </slide>")
        self.assertEqual(semantic_signature(left), semantic_signature(right))
        right.find("data/p").text = "changed"
        self.assertNotEqual(semantic_signature(left), semantic_signature(right))


if __name__ == "__main__":
    unittest.main()
