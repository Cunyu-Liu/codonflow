#!/usr/bin/env python3
import gzip
import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).with_name("a8_rk02_mordstein_reference_recovery.py")
if not MODULE_PATH.exists():
    MODULE_PATH = Path(__file__).parent.parent / "a8_rk02_mordstein_reference_recovery.py"
SPEC = importlib.util.spec_from_file_location("recovery", MODULE_PATH)
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


def codons(protein):
    result = []
    for aa in protein:
        result.append(next(codon for codon, value in recovery.CODON_TABLE.items() if value == aa))
    return "".join(result)


class RecoveryTests(unittest.TestCase):
    def test_reference_lengths(self):
        self.assertEqual(len(recovery.EGFP_PROTEIN), 239)
        self.assertEqual(len(recovery.R1_PROTEIN), 100)
        self.assertEqual(len(recovery.R2_SEED_PROTEIN), 93)
        self.assertEqual(recovery.GAP_LENGTH, 138)

    def test_r1_translation(self):
        seq = codons(recovery.R1_PROTEIN)
        self.assertEqual(len(seq), 300)
        self.assertEqual(recovery.translate(seq), recovery.R1_PROTEIN)

    def test_r2_boundary_roundtrip(self):
        coding = codons(recovery.R2_SEED_PROTEIN)
        raw = ("A" + coding + "C" * 20).translate(recovery.COMP)[::-1]
        self.assertEqual(len(raw), 300)
        self.assertEqual(recovery.r2_coding(raw), coding)
        self.assertEqual(recovery.translate(recovery.r2_coding(raw)), recovery.R2_SEED_PROTEIN)

    def test_seed_assignment_up_to_eight_errors(self):
        first = "A" * 300
        second = "A" * 150 + "C" * 150
        assigner = recovery.SeedAssigner([first, second], 8)
        query = list(first)
        for index in range(8):
            query[index * 30] = "G"
        self.assertEqual(assigner.assign("".join(query)), 0)
        query[8 * 30] = "G"
        self.assertIsNone(assigner.assign("".join(query)))
        self.assertEqual(assigner.assign(second), 1)

    def test_centroid_selection_collapses_sequencing_errors(self):
        first = "A" * 300
        second = "A" * 150 + "C" * 150
        error = "T" + first[1:]
        centroids, counts = recovery.choose_centroids({first: 100, error: 50, second: 80}, 300, 10, 10, 8)
        self.assertEqual(centroids, [first, second])
        self.assertEqual(counts, [100, 80])

    def test_external_exact_merge_matches_global_counter(self):
        first = {"A" * 300: 8, "C" * 300: 4, "G" * 300: 1}
        second = {"A" * 300: 7, "C" * 300: 6, "T" * 300: 2}
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, counter in [("one", first), ("two", second)]:
                path = Path(tmp) / f"{name}.tsv.gz"
                recovery.write_exact_cache(counter, path)
                paths.append(path)
            observed = recovery.merge_exact_caches(paths, 3)
        combined = dict(first)
        for seq, count in second.items():
            combined[seq] = combined.get(seq, 0) + count
        expected = dict(sorted(combined.items(), key=lambda item: (-item[1], item[0]))[:3])
        self.assertEqual(observed, expected)
        self.assertEqual(observed["A" * 300], 15)

    def test_bounded_assignment_cache_and_deterministic_audit_sample(self):
        first = "A" * 300
        second = "A" * 150 + "C" * 150
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reads.fastq.gz"
            with gzip.open(path, "wt") as handle:
                for index in range(40):
                    seq = first if index % 2 == 0 else second
                    handle.write(f"@read_{index}\n{seq}\n+\n{'I' * 300}\n")
            run = {"run": "TEST", "library_name": "Bin1", "bin": 1, "r1": path, "r2": None}
            r1_assigner = recovery.SeedAssigner([first, second], 8)
            r2_assigner = recovery.SeedAssigner([], 8)
            kwargs = dict(runs=[run], max_reads=0, allow_truncated=False,
                          r1_assigner=r1_assigner, r2_assigner=r2_assigner,
                          assignment_cache_max=1, audit_sample_per_run=7, audit_seed=19)
            counts1, counts2, pairs, metrics, audit1 = recovery.assign_reads(**kwargs)
            _, _, _, _, audit2 = recovery.assign_reads(**kwargs)
        self.assertEqual(counts1.sum(), 40)
        self.assertEqual(counts2.sum(), 0)
        self.assertEqual(len(audit1), 7)
        self.assertEqual(audit1, audit2)
        self.assertEqual(len({row["read_index"] for row in audit1}), 7)
        self.assertTrue(all(row["r1_distance_nt"] == 0 for row in audit1))
        self.assertEqual(metrics[0]["pairs_scanned"], 40)


if __name__ == "__main__":
    unittest.main()
