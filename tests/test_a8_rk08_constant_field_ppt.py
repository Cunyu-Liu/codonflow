#!/usr/bin/env python3
import unittest
import xml.etree.ElementTree as ET

from scripts.a8_rk08_make_constant_field_ppt import (
    NS, build_slide, display_comparison, semantic_signature, signed, visible_text,
)


class ConstantFieldPPTTests(unittest.TestCase):
    def comparison(self):
        return {
            "delta_transcript_balanced_mse": 0.05771585573506995,
            "delta_mean_transcript_pearson": -0.1334937178069512,
            "transcript_balanced_mse": {"ci95": [0.05709918203103379, 0.05834085807893431], "holm_pvalue": 0.0},
            "mean_transcript_pearson": {"ci95": [-0.13779552902338732, -0.12926709989907645], "holm_pvalue": 0.0},
            "bootstrap_replicates": 2000,
            "bootstrap_seed": 20261120,
            "sensitivity_bootstrap_mean_deltas": [],
        }

    def production(self):
        row = self.comparison()
        metric = lambda mse, cor: {
            "transcript_balanced_mse": mse,
            "mean_transcript_pearson": cor,
            "position_mse": mse,
            "n_transcripts": 3630,
            "n_observed_positions": 1444596,
        }
        return {
            "primary_partition": "study_ood|Subtelny14",
            "metrics": {"study_ood|Subtelny14": {
                "model": metric(0.23056854005324243, -0.00884488119796242),
                "ridge": metric(0.1759458819436876, 0.061698354230170255),
                "constant": metric(0.17285268431817252, 0.12464883660898879),
            }},
            "primary_comparisons": {
                "model_minus_constant": row,
                "ridge_minus_constant": row,
                "model_minus_ridge": row,
            },
        }

    def test_signed_and_comparison_display(self):
        self.assertEqual(signed(-0.25, 2), "−0.25")
        self.assertEqual(signed(0, 2), "0")
        values = display_comparison(self.comparison())
        self.assertEqual(values["mse"], "+0.05772 [+0.05710, +0.05834]")
        self.assertEqual(values["cor"], "−0.13349 [−0.13780, −0.12927]")
        self.assertEqual(values["mse_p"], "<0.001")

    def test_slide_has_no_ids_and_five_notes(self):
        verification = {"check_count": 361, "passed_count": 361, "max_numeric_delta": 6.245004513516506e-17}
        finalization = {"check_count": 37, "passed_count": 37}
        slide = build_slide(self.production(), verification, finalization, verification, verification)
        self.assertTrue(all("id" not in e.attrib for e in slide.iter()))
        note = slide.find(f"{{{NS}}}note")
        self.assertEqual(len(note.findall(f".//{{{NS}}}p")), 5)
        self.assertIn("RK-G1 = false", visible_text(slide))
        self.assertIn("0.172853", visible_text(slide))

    def test_semantic_signature_ignores_whitespace_tail_only(self):
        left = ET.fromstring("<slide><data><p>same</p></data></slide>")
        right = ET.fromstring("<slide><data><p>same</p></data>  </slide>")
        self.assertEqual(semantic_signature(left), semantic_signature(right))
        right.find("data/p").text = "changed"
        self.assertNotEqual(semantic_signature(left), semantic_signature(right))


if __name__ == "__main__":
    unittest.main()
