#!/usr/bin/env python3
import ast
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent

def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

prod = load("a8_rk05_ribomimo_official_smoke")


def matrix_text(rows):
    return "\n".join(line for row in rows for line in row) + "\n"


class RiboMIMOSmokeTests(unittest.TestCase):
    def test_01_shortest_deterministic_selection(self):
        rows = []
        for i in range(25):
            name = f"g{24-i:02d}"
            n = 15 + (i % 5)
            rows.append((f">{name} {n}", " ".join(["ATG"] * n), " ".join(["1"] * n)))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.txt"
            path.write_text(matrix_text(rows))
            selected, subset = prod.select_records(path, 20)
        self.assertEqual(len(selected), 20)
        self.assertEqual([r["n_codons"] for r in selected], sorted(r["n_codons"] for r in selected))
        self.assertEqual(len(subset.splitlines()), 60)

    def test_02_duplicate_names_excluded(self):
        rows = [(">dup", " ".join(["ATG"] * 15), " ".join(["1"] * 15))] * 2
        rows += [(f">g{i}", " ".join(["ATG"] * 16), " ".join(["1"] * 16)) for i in range(20)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.txt"; path.write_text(matrix_text(rows))
            selected, _ = prod.select_records(path, 20)
        self.assertNotIn("dup", {r["record_id"] for r in selected})

    def test_03_strict_coverage_and_positive_rule(self):
        rows = [(">bad", " ".join(["ATG"] * 15), " ".join(["1"] * 9 + ["0"] * 6))]
        rows += [(f">g{i}", " ".join(["ATG"] * 16), " ".join(["1"] * 16)) for i in range(20)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.txt"; path.write_text(matrix_text(rows))
            selected, _ = prod.select_records(path, 20)
        self.assertNotIn("bad", {r["record_id"] for r in selected})

    def test_04_nonfinite_and_misaligned_excluded(self):
        rows = [(">nan", " ".join(["ATG"] * 15), " ".join(["1"] * 14 + ["nan"])),
                (">short", " ".join(["ATG"] * 15), " ".join(["1"] * 14))]
        rows += [(f">g{i}", " ".join(["ATG"] * 16), " ".join(["1"] * 16)) for i in range(20)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.txt"; path.write_text(matrix_text(rows))
            selected, _ = prod.select_records(path, 20)
        self.assertEqual(len(selected), 20)

    def test_05_six_replacements_applied_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"; runtime = Path(tmp) / "runtime"; source.mkdir()
            for name in prod.SOURCE_FILES:
                text = ""
                for f, old, new, reason in prod.RAGGED_REPLACEMENTS + [prod.PADDING_REPLACEMENT]:
                    if f == name: text += old + "\n"
                (source / name).write_text(text)
            applied = prod.apply_replacements(source, runtime, prod.RAGGED_REPLACEMENTS + [prod.PADDING_REPLACEMENT])
            self.assertEqual(len(applied), 6)
            for item in applied:
                path = runtime / item["file"]
                self.assertIn(item["new"], path.read_text())
                self.assertNotIn(item["old"], path.read_text().replace(item["new"], ""))

    def test_06_missing_patch_anchor_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"; runtime = Path(tmp) / "runtime"; source.mkdir()
            for name in prod.SOURCE_FILES: (source / name).write_text("")
            with self.assertRaises(ValueError):
                prod.apply_replacements(source, runtime, prod.RAGGED_REPLACEMENTS)

    def test_07_final_metric_parser(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "log"
            path.write_text("RiboMIMO, r2 -1.000000 0.200000, mse 3.000000 0.100000, corr 0.250000 0.050000\n")
            metrics = prod.parse_final_metrics(path)
        self.assertEqual(metrics["r2_mean"], -1.0)
        self.assertEqual(metrics["pearson_std"], 0.05)

    def test_08_metric_parser_requires_aggregate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "log"; path.write_text("not a metric\n")
            with self.assertRaises(ValueError): prod.parse_final_metrics(path)

    def test_09_official_source_anchors_unique(self):
        source = Path(os.environ.get("RIBOMIMO_SOURCE_DIR", str(HERE.parent / "source")))
        if not (source / "model.py").is_file():
            self.skipTest("local fixed-source inspection copy unavailable")
        for f, old, new, reason in prod.RAGGED_REPLACEMENTS + [prod.PADDING_REPLACEMENT]:
            self.assertEqual((source / f).read_text().count(old), 1, (f, old))

    def test_10_independent_does_not_import_production(self):
        source = (HERE / "a8_rk05_verify_ribomimo_official_smoke.py").read_text()
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): imported.update(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module: imported.add(node.module)
        self.assertNotIn("a8_rk05_ribomimo_official_smoke", imported)
        self.assertIn("production_module_imported", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
