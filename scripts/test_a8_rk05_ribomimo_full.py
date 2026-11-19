#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(os.environ.get("RIBOMIMO_FULL_DRIVER", str(Path(__file__).with_name("a8_rk05_ribomimo_full_official.py"))))
SPEC = importlib.util.spec_from_file_location("ribomimo_full_driver", SCRIPT)
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)


def epoch_line(fold: int, split: str, r2: float, mse: float, corr: float, auc: str = "0.5") -> str:
    return f"Fold 1x{fold}/1x2, {split}, r2 {r2:.6f}, mse {mse:.6f}, corr {corr:.6f}, auc {auc}, aupr 0.500000, loss 0.100000"


def valid_two_fold_log() -> str:
    lines = [
        epoch_line(1, "Valid", 0.1, 2.0, 0.2),
        epoch_line(1, "Test", 0.2, 2.2, 0.3),
        epoch_line(1, "Valid", 0.15, 1.9, 0.25),
        epoch_line(1, "Test", 0.25, 2.1, 0.35),
        epoch_line(2, "Valid", 0.05, 3.0, -0.1, auc="nan"),
        epoch_line(2, "Test", -0.05, 3.2, 0.1, auc="nan"),
        "RiboMIMO, r2 0.100000 0.150000, mse 2.650000 0.550000, corr 0.225000 0.125000",
    ]
    return "\n".join(lines)


class FullDriverTests(unittest.TestCase):
    def test_replacement_inventory_is_seven(self):
        self.assertEqual(len(DRIVER.REPLACEMENTS), 7)
        self.assertEqual(sum(item[0] == "model.py" for item in DRIVER.REPLACEMENTS), 6)
        self.assertEqual(sum(item[0] == "runRiboMIMO.py" for item in DRIVER.REPLACEMENTS), 1)

    def test_pack_lengths_cpu_is_only_cpu_move(self):
        cpu = [item for item in DRIVER.REPLACEMENTS if ".cpu()" in item[2]]
        self.assertEqual(len(cpu), 1)
        self.assertEqual(cpu[0][2], "x = pack_padded_sequence(x, length.cpu(), batch_first=True)")

    def test_apply_all_replacements(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            model_lines = [item[1] for item in DRIVER.REPLACEMENTS if item[0] == "model.py"]
            (source / "model.py").write_text("\n".join(model_lines) + "\n")
            (source / "runRiboMIMO.py").write_text("data_pad = np.array(data_pad)\n")
            (source / "utils.py").write_text("# utils\n")
            (source / "getSaliency.py").write_text("# saliency\n")
            applied = DRIVER.apply_replacements(source, root / "runtime")
            self.assertEqual(len(applied), 7)
            for filename, old, new, _reason in DRIVER.REPLACEMENTS:
                text = (root / "runtime" / filename).read_text()
                self.assertEqual(text.count(old), 0)
                self.assertEqual(text.count(new), 1)

    def test_missing_compatibility_target_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            for filename in DRIVER.SOURCE_FILES:
                (source / filename).write_text("nothing to replace\n")
            with self.assertRaises(ValueError):
                DRIVER.apply_replacements(source, root / "runtime")

    def test_bounded_style_log_with_nan_auc(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "logging.log"
            path.write_text(valid_two_fold_log())
            parsed = DRIVER.parse_official_log(path, 2)
        self.assertEqual(len(parsed["folds"]), 2)
        self.assertEqual(parsed["folds"][0]["best_epoch"], 2)
        self.assertEqual(parsed["folds"][1]["best_epoch"], 1)
        self.assertAlmostEqual(parsed["aggregate"]["r2_mean"], 0.1)
        self.assertAlmostEqual(parsed["aggregate"]["mse_mean"], 2.65)
        self.assertAlmostEqual(parsed["aggregate"]["pearson_mean"], 0.225)

    def test_best_validation_not_last_epoch(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "logging.log"
            fold_two_valid = epoch_line(2, "Valid", 0.05, 3.0, -0.1, auc="nan")
            later_non_improving = epoch_line(1, "Valid", 0.10, 2.5, 0.1) + "\n" + epoch_line(1, "Test", -0.9, 9.9, -0.8) + "\n"
            path.write_text(valid_two_fold_log().replace(fold_two_valid, later_non_improving + fold_two_valid))
            parsed = DRIVER.parse_official_log(path, 2)
        self.assertEqual(parsed["folds"][0]["best_epoch"], 2)
        self.assertEqual(parsed["folds"][0]["epochs_logged"], 3)
        self.assertEqual(parsed["folds"][0]["test_at_best_validation"]["r2"], 0.25)

    def test_missing_fold_test_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "logging.log"
            lines = valid_two_fold_log().splitlines()
            del lines[5]
            path.write_text("\n".join(lines))
            with self.assertRaises(ValueError):
                DRIVER.parse_official_log(path, 2)

    def test_nonfinite_aggregate_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "logging.log"
            text = valid_two_fold_log().replace("RiboMIMO, r2 0.100000", "RiboMIMO, r2 nan")
            path.write_text(text)
            with self.assertRaises(ValueError):
                DRIVER.parse_official_log(path, 2)

    def test_aggregate_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "logging.log"
            text = valid_two_fold_log().replace("mse 2.650000", "mse 9.000000")
            path.write_text(text)
            with self.assertRaises(ValueError):
                DRIVER.parse_official_log(path, 2)

    def test_protocol_v2_scope_and_previous_failure(self):
        protocol_path = SCRIPT.parent.parent / "audits" / "20261118" / "RK05" / "ribomimo_full_mohammad16_protocol_v2.json"
        if not protocol_path.exists():
            self.skipTest("Frozen remote protocol is not present in this local test layout")
        protocol = json.loads(protocol_path.read_text())
        self.assertEqual(protocol["compatibility"]["replacement_count"], 7)
        self.assertEqual(protocol["official_arguments"]["num_fold"], 10)
        self.assertEqual(protocol["official_arguments"]["max_epoch"], 100)
        self.assertEqual(protocol["official_arguments"]["early_stop"], 5)
        self.assertTrue(protocol["previous_attempt"]["retained"])
        for key in ("homology_aware_split", "protein_ood", "study_ood", "functional_ood", "main_baseline_comparison", "publication_metrics_reproduced", "sota_claim"):
            self.assertFalse(protocol["scope"][key])


if __name__ == "__main__":
    unittest.main(verbosity=2)
