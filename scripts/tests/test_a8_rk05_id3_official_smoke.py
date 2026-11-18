#!/usr/bin/env python3
import importlib.util
import json
import math
import tempfile
import unittest
from pathlib import Path


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT_DIR = Path(__file__).resolve().parent
if SCRIPT_DIR.name == "tests":
    SCRIPT_DIR = SCRIPT_DIR.parent
VERIFY = load_module(SCRIPT_DIR / "a8_rk05_verify_id3_official_smoke.py", "verify_id3")
PRODUCE = load_module(SCRIPT_DIR / "a8_rk05_id3_official_smoke.py", "produce_id3")


def valid_result():
    return {
        "protein_name": "O15263",
        "constraint_type": "ams",
        "variant": "00",
        "seed": 42,
        "status": "completed",
        "iterations": 2,
        "initial_accessibility": 2.0,
        "final_accessibility": 1.0,
        "best_accessibility": 1.0,
        "improvement": 1.0,
        "amino_acids_match": True,
        "actual_amino_acids": "MA",
        "final_sequence": "AUGGCC",
        "best_seq_design": {"discrete_sequence": "AUGGCC", "accessibility": 1.0, "iteration": 1},
        "trajectory": {
            "iterations": [0, 1],
            "discrete_sequences": ["AUGGCU", "AUGGCC"],
            "accessibility": [2.0, 1.0],
        },
    }


class ID3VerificationHelpersTest(unittest.TestCase):
    def test_translation_and_terminal_stop(self):
        self.assertEqual(VERIFY.translate_rna("AUGGCUGCC"), "MAA")
        self.assertEqual(VERIFY.translate_rna("AUGUAA"), "M*")
        with self.assertRaises(ValueError):
            VERIFY.translate_rna("ATGGCU")

    def test_valid_payload_and_best_minimum(self):
        checked = VERIFY.validate_result_payload(valid_result(), "MA")
        self.assertEqual(checked["issues"], [])
        self.assertEqual(checked["candidate_count"], 2)
        self.assertEqual(checked["valid_candidate_count"], 2)
        self.assertEqual(checked["initial_sequence"], "AUGGCU")

    def test_protein_mismatch_is_rejected(self):
        result = valid_result()
        result["final_sequence"] = "AUGAAA"
        result["actual_amino_acids"] = "MK"
        checked = VERIFY.validate_result_payload(result, "MA")
        self.assertIn("final_translation_mismatch", checked["issues"])

    def test_invalid_best_candidate_cannot_define_minimum(self):
        result = valid_result()
        result["trajectory"]["discrete_sequences"][0] = "AUGAAA"
        result["best_accessibility"] = 1.0
        checked = VERIFY.validate_result_payload(result, "MA")
        self.assertEqual(checked["issues"], [])
        self.assertEqual(checked["valid_candidate_count"], 1)
        result["best_accessibility"] = 2.0
        checked = VERIFY.validate_result_payload(result, "MA")
        self.assertIn("best_accessibility_not_independent_minimum", checked["issues"])

    def test_source_ast_and_experiment_matrix(self):
        text = """\nclass X:\n    def quick_test():\n        return UnifiedExperimentConfig(proteins=['O15263'], constraints=['lagrangian','ams','cpc'], variants=['00','01','10','11'], iterations=2, seeds=1, enable_cai=False)\n"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.py"
            path.write_text(text)
            preset = VERIFY.extract_preset(path, "quick_test")
        self.assertEqual(preset["iterations"], 2)
        self.assertEqual(len(VERIFY.expected_experiment_keys(preset)), 12)

    def test_dna_utr_is_normalized_for_acgu_preflight(self):
        self.assertEqual(PRODUCE.normalize_id3_rna("ATGCUatgu"), "AUGCUAUGU")
        self.assertNotIn("T", PRODUCE.normalize_id3_rna("TTAT"))

    def test_result_file_selection_and_nonfinite_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ["config.json", "summary.json", "progress.json", "a.json", "b.json"]:
                (root / name).write_text("{}")
            self.assertEqual([p.name for p in PRODUCE.select_result_files(root)], ["a.json", "b.json"])
            self.assertIsNone(VERIFY.json_safe(float("inf")))
            self.assertIsNone(PRODUCE.json_safe(float("nan")))

    def test_cpc_beta_omission_detection(self):
        template = """\nclass CodonProfileConstraint:\n    def forward(self, alpha=0.0, beta=0.0, tau=1.0):\n        return CodonPsiFunction.forward(codon_probs, self.codon_encodings{})\n"""
        omitted = VERIFY.detect_cpc_beta_omission(template.format(""))
        self.assertTrue(omitted["detected"])
        self.assertFalse(omitted["beta_keyword_passed"])
        forwarded = VERIFY.detect_cpc_beta_omission(template.format(", beta=beta"))
        self.assertFalse(forwarded["detected"])
        self.assertTrue(forwarded["beta_keyword_passed"])

    def test_runner_beta1_discrete_assumption_detection(self):
        source = """\nif beta == 1.0:\n    accessibility = accessibility_loss.item()\nelse:\n    accessibility = accessibility_discrete.item()\n"""
        detected = VERIFY.detect_runner_ste_assumption(source)
        self.assertTrue(detected["detected"])
        self.assertEqual(detected["assignment_lineno"], 3)
        corrected = source.replace("accessibility_loss.item()", "accessibility_discrete.item()")
        self.assertFalse(VERIFY.detect_runner_ste_assumption(corrected)["detected"])


if __name__ == "__main__":
    unittest.main()
